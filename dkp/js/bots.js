/* Doppelkopf-Poker – Bots (easy / medium / hard)
 *
 * Aufbau: Bots.step(game) f\u00fchrt GENAU EINE atomare Aktion des aktuellen Bots aus
 * (Ziehen, Einsetzen, Ablegen oder Handman\u00f6ver). Die UI ruft step() mit Pausen auf.
 * Bots.decideScoring(game, playerId) liefert die Wertungsentscheidung (null = passen, sonst Startposition).
 *
 * Alle Stufen nutzen dieselbe Bewertungsfunktion; die Stufen unterscheiden sich in
 * Genauigkeit (Rauschen), Vorausschau (Potenziale, Monte-Carlo) und Nutzung der Spezialaktionen.
 */
(function (root) {
  'use strict';
  var PK = root.PK = root.PK || {};
  var E = PK.Eval;

  var LEVELS = {
    easy:   { noise: 70, potential: 0.35, discardTake: 45, manoeuvre: Infinity, pairChance: 0.12, mc: 0 },
    medium: { noise: 8,  potential: 0.80, discardTake: 18, manoeuvre: 200,      pairChance: 0,    mc: 0 },
    hard:   { noise: 0,  potential: 1.00, discardTake: 0,  manoeuvre: 110,      pairChance: 0,    mc: 24 }
  };
  var BONUS_VALUE = { 14: 80, 13: 55, 12: 65 }; // Wert der Spezialaktionen (Aces/Kings/Queens) in Bewertungspunkten
  var REFILL_VALUE = 25;                         // erwarteter Gewinn der Auff\u00fcllkarte nach einem Aktionspaar

  /* ---------------- Bewertung ---------------- */

  var CAT_BASE = [0, 0, 100, 220, 300, 420, 520, 600, 700, 900, 1000];

  function evScore(ev) {
    return CAT_BASE[ev.cat] + ev.tb[0] * 2 + (ev.tb[1] || 0) * 0.2;
  }

  // N\u00e4he zu besseren H\u00e4nden (Flush-/Stra\u00dfen-Draws)
  function potential(h) {
    var sc = {}, m = 0, i;
    for (i = 0; i < h.length; i++) { sc[h[i].s] = (sc[h[i].s] || 0) + 1; if (sc[h[i].s] > m) m = sc[h[i].s]; }
    var p = 0;
    if (m === 4) p += 40; else if (m === 3) p += 10;
    var has = {};
    for (i = 0; i < h.length; i++) { has[h[i].r] = true; if (h[i].r === 14) has[1] = true; }
    var best = 0, run = 0;
    for (var r = 1; r <= 14; r++) {
      if (has[r]) { run++; if (run > best) best = run; } else run = 0;
    }
    if (best === 4) p += 45; else if (best === 3) p += 12;
    return p;
  }

  function windowValue(halves, w) {
    var ev = E.evaluate5(halves);
    var v = evScore(ev);
    if (w > 0 && ev.cat < 5) v += w * potential(halves);
    return v;
  }

  // Bewertung einer ganzen Hand (beliebige L\u00e4nge >= 5)
  function handScore(hand, w) {
    var vals = [];
    for (var s = 0; s + 5 <= hand.length; s++) {
      vals.push(windowValue(E.windowHalves(hand, s), w));
    }
    if (!vals.length) return 0;
    vals.sort(function (a, b) { return b - a; });
    var rest = 0;
    for (var i = 1; i < vals.length; i++) rest += vals[i];
    return vals[0] + 0.12 * rest;
  }

  function without(hand, idxs) {
    return hand.filter(function (_, i) { return idxs.indexOf(i) < 0; });
  }

  function noiseOf(cfg, rng) { return cfg.noise ? (rng() * 2 - 1) * cfg.noise : 0; }

  /* Beste Platzierung einer Karte (Position + Orientierung), mit anschlie\u00dfendem Ablegen von k Karten.
     forbidden: IDs, die nicht abgelegt werden d\u00fcrfen. */
  function bestPlacement(hand, card, k, forbidden, w, cfg, rng) {
    var best = null;
    for (var pos = 0; pos <= hand.length; pos++) {
      for (var f = 0; f < 2; f++) {
        var nh = hand.slice();
        nh.splice(pos, 0, { card: card, flipped: f === 1 });
        var sc = -Infinity;
        if (k === 0) sc = handScore(nh, w);
        else {
          var n = nh.length, i, j;
          var ok = function (x) { return forbidden.indexOf(nh[x].card.id) < 0; };
          if (k === 1) {
            for (i = 0; i < n; i++) if (ok(i)) sc = Math.max(sc, handScore(without(nh, [i]), w));
          } else {
            for (i = 0; i < n; i++) if (ok(i)) for (j = i + 1; j < n; j++) if (ok(j)) {
              sc = Math.max(sc, handScore(without(nh, [i, j]), w));
            }
          }
        }
        sc += noiseOf(cfg, rng);
        if (!best || sc > best.score) best = { pos: pos, flip: f === 1, score: sc };
      }
    }
    return best;
  }

  /* ---------------- Wissen \u00fcber unbekannte Karten (f\u00fcr Hard) ---------------- */

  function unseenPool(game, p) {
    var seen = {};
    p.hand.forEach(function (e) { seen[e.card.id] = true; });
    game.discardPile.forEach(function (e) { seen[e.card.id] = true; });
    game.removed.forEach(function (c) { seen[c.id] = true; });
    if (game.turn && game.turn.pending) seen[game.turn.pending.id] = true;
    return PK.DECK.filter(function (c) { return !seen[c.id]; });
  }

  function sample(pool, k, rng) {
    var a = pool.slice(), out = [];
    for (var i = 0; i < k && a.length; i++) {
      var j = Math.floor(rng() * a.length);
      out.push(a[j]); a[j] = a[a.length - 1]; a.pop();
    }
    return out;
  }

  function weightFor(game, p, cfg) {
    // Je weniger Z\u00fcge noch kommen, desto weniger z\u00e4hlen Potenziale
    var left = PK.CONST.TURNS_PER_ROUND - p.turnsTaken - 1;
    var f = Math.min(1, Math.max(0, left / 2));
    return cfg.potential * f;
  }

  // erwarteter Wert einer unbekannten Karte vom Nachziehstapel (Monte Carlo)
  function expectedStackScore(game, p, cfg, w, forbidden) {
    var pool = unseenPool(game, p);
    var cards = sample(pool, cfg.mc, game.rng);
    if (!cards.length) return -Infinity;
    var total = 0, noNoise = { noise: 0 };
    cards.forEach(function (c) {
      total += bestPlacement(p.hand, c, 1, forbidden, w, noNoise, game.rng).score;
    });
    return total / cards.length;
  }

  /* ---------------- Schritt: Zug ---------------- */

  function manoeuvreOptions(hand) {
    var out = [], i, j, n = hand.length;
    for (i = 0; i < n; i++) out.push({ type: 'flip', i: i });
    for (i = 0; i < n; i++) for (j = 0; j < n; j++) if (i !== j) out.push({ type: 'move', from: i, to: j });
    for (i = 0; i < n; i++) for (j = i + 1; j < n; j++) out.push({ type: 'swap', i: i, j: j });
    return out;
  }

  function applyManoeuvre(hand, m) {
    var h = hand.map(function (e) { return { card: e.card, flipped: e.flipped }; });
    if (m.type === 'flip') h[m.i].flipped = !h[m.i].flipped;
    else if (m.type === 'move') { var e = h.splice(m.from, 1)[0]; h.splice(m.to, 0, e); }
    else { var x = h[m.i]; h[m.i] = h[m.j]; h[m.j] = x; }
    return h;
  }

  function chooseManoeuvre(game, p, cfg) {
    if (cfg.manoeuvre === Infinity) return null;
    var cur = evScore(E.bestWindow(p.hand).ev);
    var left = PK.CONST.TURNS_PER_ROUND - p.turnsTaken - 1;
    var threshold = left === 0 ? Math.min(cfg.manoeuvre, 60) : cfg.manoeuvre;
    var best = null;
    manoeuvreOptions(p.hand).forEach(function (m) {
      var nv = evScore(E.bestWindow(applyManoeuvre(p.hand, m)).ev);
      if (!best || nv > best.value) best = { m: m, value: nv };
    });
    if (best && best.value - cur >= threshold) return best.m;
    return null;
  }

  function stepDraw(game, p, cfg) {
    var t = game.turn;
    if (t.refill) { game.draw('stack'); return; }
    var w = weightFor(game, p, cfg);

    if (t.drawn === 0) {
      var m = chooseManoeuvre(game, p, cfg);
      if (m) { game.manoeuvre(m); return; }
    }
    if (!game.discardPile.length) { game.draw('stack'); return; }

    var forbidden = t.drawnIds.slice();
    var top = game.discardPile[game.discardPile.length - 1].card;
    var base = handScore(p.hand, w);
    var viaDiscard = bestPlacement(p.hand, top, 1, forbidden.concat([top.id]), w, { noise: 0 }, game.rng).score;
    var gain = viaDiscard - base;

    var takeDiscard;
    if (cfg.mc > 0 && game.canDraw('stack')) {
      var exp = expectedStackScore(game, p, cfg, w, forbidden);
      takeDiscard = viaDiscard > exp + 2;
    } else {
      takeDiscard = gain + noiseOf(cfg, game.rng) * 0.5 >= cfg.discardTake;
    }
    if (!game.canDraw('stack')) takeDiscard = true;
    game.draw(takeDiscard ? 'discard' : 'stack');
  }

  function stepPlace(game, p, cfg) {
    var t = game.turn;
    var w = weightFor(game, p, cfg);
    var forbidden = t.drawnIds.concat([t.pending.id]);
    var k;
    if (t.refill) k = 0;
    else if (t.drawn + 1 < t.need) k = 1;   // Zwischenschritt beim Doppelzug (grobe N\u00e4herung)
    else k = t.need;
    var b = bestPlacement(p.hand, t.pending, k, forbidden, w, cfg, game.rng);
    game.place(b.pos, b.flip);
  }

  function chooseTarget(game, p) {
    var cands = game.players.filter(function (o) { return o.id !== p.id && o.protectUntil < game.round; });
    if (!cands.length) return null;
    cands.sort(function (a, b) { return b.score - a.score || game.rng() - 0.5; });
    return cands[0].id;
  }

  function stepDiscard(game, p, cfg) {
    var t = game.turn, hand = p.hand, n = hand.length, i, j;
    var w = weightFor(game, p, cfg);
    var forb = t.drawnIds;
    var okIdx = function (x) { return forb.indexOf(hand[x].card.id) < 0; };

    // normale Ablage
    var bestNormal = null;
    if (t.need === 1) {
      for (i = 0; i < n; i++) if (okIdx(i)) {
        var s1 = handScore(without(hand, [i]), w) + noiseOf(cfg, game.rng);
        if (!bestNormal || s1 > bestNormal.score) bestNormal = { idx: [i], score: s1 };
      }
    } else {
      for (i = 0; i < n; i++) if (okIdx(i)) for (j = i + 1; j < n; j++) if (okIdx(j)) {
        var s2 = handScore(without(hand, [i, j]), w) + noiseOf(cfg, game.rng);
        if (!bestNormal || s2 > bestNormal.score) bestNormal = { idx: [i, j], score: s2 };
      }
    }

    // Aktionspaare (Asse/K\u00f6nige/Damen, nach aktuell oben liegendem Wert)
    var bestPair = null;
    for (i = 0; i < n; i++) if (okIdx(i)) for (j = i + 1; j < n; j++) if (okIdx(j)) {
      var a = E.activeHalf(hand[i]), b = E.activeHalf(hand[j]);
      if (a.r !== b.r || (a.r !== 14 && a.r !== 13 && a.r !== 12)) continue;
      var bonus = BONUS_VALUE[a.r], target = null;
      if (a.r === 14) {
        target = chooseTarget(game, p);
        if (target == null) bonus = 0;
      } else if (a.r === 13) {
        if (p.protectUntil >= game.round + 1) bonus = 0;
      } else if (p.doubleDraw) bonus = 0;
      if (cfg.pairChance > 0 && bonus > 0) bonus = game.rng() < cfg.pairChance ? 400 : 0; // Easy: eher zuf\u00e4llig
      if (bonus <= 0) continue;
      var sc = handScore(without(hand, [i, j]), w) + (t.need === 1 ? REFILL_VALUE : 0) + bonus + noiseOf(cfg, game.rng);
      if (!bestPair || sc > bestPair.score) bestPair = { idx: [i, j], score: sc, target: target, rank: a.r };
    }

    if (bestPair && (!bestNormal || bestPair.score > bestNormal.score)) {
      game.discardCards(bestPair.idx, { action: true, target: bestPair.target });
    } else {
      game.discardCards(bestNormal.idx, {});
    }
  }

  function step(game) {
    var t = game.turn;
    if (!t) throw new Error('Kein aktiver Zug');
    var p = game.cur();
    var cfg = LEVELS[p.level] || LEVELS.medium;
    if (t.stage === 'draw') stepDraw(game, p, cfg);
    else if (t.stage === 'place') stepPlace(game, p, cfg);
    else if (t.stage === 'discard') stepDiscard(game, p, cfg);
    else throw new Error('Unerwartete Stage ' + t.stage);
  }

  /* ---------------- Wertung: mitspielen oder passen ---------------- */

  function simulateOpponentEv(game, p, pool, cfg) {
    // grobe Sch\u00e4tzung: 7 zuf\u00e4llige Karten + 3 gierige Z\u00fcge
    var cards = sample(pool, 7 + 3, game.rng);
    var hand = cards.slice(0, 7).map(function (c) { return { card: c, flipped: game.rng() < 0.5 }; });
    var noNoise = { noise: 0 };
    for (var k = 0; k < 3; k++) {
      var c = cards[7 + k];
      var b = bestPlacement(hand, c, 1, [c.id], 0.5, noNoise, game.rng);
      hand.splice(b.pos, 0, { card: c, flipped: b.flip });
      // schlechteste Karte entfernen (nicht die neue)
      var bestS = -Infinity, bestI = -1;
      for (var i = 0; i < hand.length; i++) {
        if (hand[i].card.id === c.id) continue;
        var s = handScore(without(hand, [i]), 0.5);
        if (s > bestS) { bestS = s; bestI = i; }
      }
      hand.splice(bestI, 1);
    }
    return E.bestWindow(hand).ev;
  }

  function decideScoring(game, id) {
    var p = game.players[id];
    var cfg = LEVELS[p.level] || LEVELS.medium;
    var bw = E.bestWindow(p.hand);
    var cat = bw.ev.cat;

    if (p.level === 'easy') {
      if (cat === 1 && game.rng() < 0.5) return null;
      if (game.rng() < 0.08) return null;
      return bw.start;
    }
    if (p.level === 'medium') {
      if (cat >= 2) return bw.start;
      return game.n >= 4 && game.rng() < 0.5 ? bw.start : null;
    }
    // hard: Erwartungswert der Punkte sch\u00e4tzen
    if (cat >= 7) return bw.start;
    var pool = unseenPool(game, p);
    var S = 14, total = 0, table = PK.CONST.POINTS[game.n];
    for (var s = 0; s < S; s++) {
      var better = 0;
      for (var o = 0; o < game.n - 1; o++) {
        var ev = simulateOpponentEv(game, p, pool, cfg);
        if (E.cmpEv(ev, bw.ev) > 0) better++;
      }
      total += (table[better] || 0) + (E.BONUS[cat] || 0);
    }
    return total / S >= 0.45 ? bw.start : null;
  }

  PK.Bots = { step: step, decideScoring: decideScoring, handScore: handScore, LEVELS: LEVELS };
  PK.LEVEL_NAMES = { easy: 'Leicht', medium: 'Mittel', hard: 'Schwer' };
})(typeof window !== 'undefined' ? window : globalThis);
