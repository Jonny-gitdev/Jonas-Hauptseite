/* Doppelkopf-Poker – Regel-Engine (unabhängig von UI und Bots) */
(function (root) {
  'use strict';
  var PK = root.PK = root.PK || {};

  /* ------------------------------------------------------------------ */
  /* Handbewertung                                                      */
  /* ------------------------------------------------------------------ */

  // Kategorien (höher = besser). Reihenfolge laut Anleitung:
  // Royal Flush > Straight Flush > Four of a Kind > Straße > Full House > Flush > Drilling > Zwei Paare > Paar > High Card
  var CAT_NAME = [
    '', 'High Card', 'Paar', 'Zwei Paare', 'Drilling', 'Flush',
    'Full House', 'Stra\u00dfe', 'Four of a Kind', 'Straight Flush', 'Royal Flush'
  ];
  var BONUS = { 7: 1, 8: 1, 9: 3, 10: 4 };

  function activeHalf(entry) { return entry.flipped ? entry.card.b : entry.card.a; }
  function hiddenHalf(entry) { return entry.flipped ? entry.card.a : entry.card.b; }

  // true, wenn alle vier Farben unter den 5 Hälften vorkommen
  function fourSuits(halves) {
    var seen = {}, n = 0;
    halves.forEach(function (h) { if (!seen[h.s]) { seen[h.s] = true; n++; } });
    return n === 4;
  }

  // halves: Array aus 5 Hälften {s, r}
  function evaluate5(halves) {
    var ranks = halves.map(function (h) { return h.r; }).sort(function (a, b) { return b - a; });
    var flush = halves.every(function (h) { return h.s === halves[0].s; });
    var uniq = ranks.filter(function (r, i) { return ranks.indexOf(r) === i; });
    var straight = false, high = 0;
    if (uniq.length === 5) {
      if (ranks[0] - ranks[4] === 4) { straight = true; high = ranks[0]; }
      else if (ranks[0] === 14 && ranks[1] === 5 && ranks[2] === 4 && ranks[3] === 3 && ranks[4] === 2) {
        straight = true; high = 5; // A-2-3-4-5 ("Wheel")
      }
    }
    var cnt = {};
    ranks.forEach(function (r) { cnt[r] = (cnt[r] || 0) + 1; });
    var groups = Object.keys(cnt).map(function (r) { return { r: +r, c: cnt[r] }; })
      .sort(function (x, y) { return y.c - x.c || y.r - x.r; });
    var shape = groups.map(function (g) { return g.c; }).join('');
    var tb = groups.map(function (g) { return g.r; });
    var cat;
    if (straight && flush) { cat = high === 14 ? 10 : 9; tb = [high]; }
    else if ((shape === '5' || shape === '41') && fourSuits(halves)) cat = 8; // Four of a Kind nur mit vier verschiedenen Farben
    else if (shape === '5' || shape === '41') cat = 4; // vier/fünf gleiche Werte mit doppelten Farben zählen nur als Drilling
    else if (straight) { cat = 7; tb = [high]; }
    else if (shape === '32') cat = 6;
    else if (flush) { cat = 5; tb = ranks; }
    else if (shape === '311') cat = 4;
    else if (shape === '221') cat = 3;
    else if (shape === '2111') cat = 2;
    else { cat = 1; tb = ranks; }
    return { cat: cat, tb: tb, name: CAT_NAME[cat] };
  }

  function cmpEv(a, b) {
    if (!a && !b) return 0;
    if (!a) return -1;
    if (!b) return 1;
    if (a.cat !== b.cat) return a.cat - b.cat;
    var n = Math.max(a.tb.length, b.tb.length);
    for (var i = 0; i < n; i++) {
      var x = a.tb[i] || 0, y = b.tb[i] || 0;
      if (x !== y) return x - y;
    }
    return 0;
  }

  function describe(ev) {
    if (!ev) return 'Gepasst';
    if (ev.cat === 1) return 'High Card (' + PK.rankName(ev.tb[0]) + ')';
    if (ev.cat === 2) return 'Paar (' + PK.rankName(ev.tb[0]) + ')';
    return ev.name;
  }

  function windowHalves(hand, start) {
    return hand.slice(start, start + 5).map(activeHalf);
  }

  function bestWindow(hand) {
    var best = null;
    for (var s = 0; s + 5 <= hand.length; s++) {
      var ev = evaluate5(windowHalves(hand, s));
      if (!best || cmpEv(ev, best.ev) > 0) best = { start: s, ev: ev };
    }
    return best;
  }

  PK.Eval = {
    CAT_NAME: CAT_NAME, BONUS: BONUS,
    activeHalf: activeHalf, hiddenHalf: hiddenHalf,
    evaluate5: evaluate5, cmpEv: cmpEv, describe: describe,
    windowHalves: windowHalves, bestWindow: bestWindow
  };

  /* ------------------------------------------------------------------ */
  /* Spiel                                                              */
  /* ------------------------------------------------------------------ */

  var ROUNDS = 5;
  var TURNS_PER_ROUND = 4;      // Z\u00fcge pro Spieler und Wertungsrunde
  var HAND_SIZE = 7;
  var POINTS = { 2: [3, 0], 3: [3, 2, 0], 4: [4, 3, 1], 5: [5, 4, 2] };

  function shuffle(arr, rng) {
    for (var i = arr.length - 1; i > 0; i--) {
      var j = Math.floor(rng() * (i + 1));
      var t = arr[i]; arr[i] = arr[j]; arr[j] = t;
    }
    return arr;
  }

  // opts: { players: [{name, human, level}], rng }
  function Game(opts) {
    this.rng = opts.rng || Math.random;
    this.n = opts.players.length;
    if (this.n < 2 || this.n > 5) throw new Error('2-5 Spieler');
    this.players = opts.players.map(function (p, i) {
      return {
        id: i, name: p.name, human: !!p.human, level: p.level || null,
        hand: [], score: 0, protectUntil: 0, skipNext: false, doubleDraw: false,
        turnsTaken: 0, lastEv: null
      };
    });
    this.drawPile = shuffle(PK.DECK.slice(), this.rng);
    this.discardPile = [];  // Eintr\u00e4ge: {card, flipped}; oberste = letzte
    this.removed = [];      // offen ausgespielte Aktionskarten / gewertete H\u00e4nde (werden bei Bedarf neu gemischt)
    this.round = 1;
    this.start = Math.floor(this.rng() * this.n);
    this.phase = 'collect'; // collect | scoring | results | over
    this.turn = null;
    this.turnCount = 0;
    this.current = this.start;
    this.lastResult = null;
    this.log = [];
    this.logSeq = 0;
    for (var k = 0; k < HAND_SIZE; k++) {
      for (var i = 0; i < this.n; i++) {
        this.players[i].hand.push({ card: this.drawPile.pop(), flipped: this.rng() < 0.5 });
      }
    }
    this.say('Runde 1 von ' + ROUNDS + ' beginnt. ' + this.players[this.start].name + ' f\u00e4ngt an.', 'round');
  }

  var G = Game.prototype;

  G.say = function (msg, kind) {
    this.log.push({ id: ++this.logSeq, msg: msg, kind: kind || 'info' });
    if (this.log.length > 200) this.log.shift();
  };

  G.cur = function () { return this.players[this.current]; };

  // Nachziehstapel auff\u00fcllen, falls leer (Ablage ohne oberste Karte + ausgespielte Karten neu mischen)
  G.ensureDrawPile = function () {
    if (this.drawPile.length > 0) return true;
    var top = this.discardPile.length ? this.discardPile.pop() : null;
    var pool = this.discardPile.map(function (e) { return e.card; }).concat(this.removed);
    this.discardPile = top ? [top] : [];
    this.removed = [];
    if (!pool.length) return false;
    this.drawPile = shuffle(pool, this.rng);
    this.say('Der Nachziehstapel wird neu gemischt.', 'info');
    return true;
  };

  G.canDraw = function (source) {
    if (source === 'discard') return this.discardPile.length > 0;
    return this.drawPile.length > 0 || this.discardPile.length > 1 || this.removed.length > 0;
  };

  /* ---- Zugablauf ---- */

  // Beginnt den Zug des aktuellen Spielers (setzt ausgesetzte Z\u00fcge automatisch durch).
  G.startTurn = function () {
    while (this.phase === 'collect' && !this.turn) {
      var p = this.cur();
      if (p.skipNext) {
        p.skipNext = false;
        this.say(p.name + ' muss diesen Zug aussetzen.', 'attack');
        this.endTurn();
        continue;
      }
      this.turn = {
        player: this.current, need: p.doubleDraw ? 2 : 1, drawn: 0, drawnIds: [],
        stage: 'draw', pending: null, refill: false
      };
    }
    return this.turn;
  };

  G.endTurn = function () {
    var p = this.cur();
    p.turnsTaken++;
    this.turn = null;
    this.turnCount++;
    if (this.turnCount === this.n * (TURNS_PER_ROUND - 1)) {
      this.say('Das ist die letzte Runde dieser Wertungsphase.', 'round');
    }
    if (this.turnCount >= this.n * TURNS_PER_ROUND) {
      this.phase = 'scoring';
      this.say('Wertungsphase!', 'round');
      return;
    }
    this.current = (this.current + 1) % this.n;
  };

  function assertStage(t, stage) {
    if (!t || t.stage !== stage) throw new Error('Aktion jetzt nicht erlaubt (Stage: ' + (t && t.stage) + ', erwartet: ' + stage + ')');
  }

  G.draw = function (source) {
    var t = this.turn, p = this.cur();
    assertStage(t, 'draw');
    if (t.refill && source !== 'stack') throw new Error('Zum Auff\u00fcllen nur vom Nachziehstapel');
    var card;
    if (source === 'discard') {
      if (!this.discardPile.length) throw new Error('Ablagestapel leer');
      card = this.discardPile.pop().card;
      this.say(p.name + ' nimmt ' + PK.halfText(card.a) + '/' + PK.halfText(card.b) + ' vom Ablagestapel.', 'draw');
    } else {
      if (!this.ensureDrawPile()) throw new Error('Keine Karten mehr');
      card = this.drawPile.pop();
      this.say(p.name + ' zieht vom Nachziehstapel.', 'draw');
    }
    if (t.need === 2 && t.drawn === 0 && !t.refill) p.doubleDraw = false;
    t.pending = card;
    t.stage = 'place';
    return card;
  };

  G.place = function (pos, flipped) {
    var t = this.turn, p = this.cur();
    assertStage(t, 'place');
    if (pos < 0 || pos > p.hand.length) throw new Error('Ung\u00fcltige Position');
    p.hand.splice(pos, 0, { card: t.pending, flipped: !!flipped });
    t.drawnIds.push(t.pending.id);
    t.pending = null;
    t.drawn++;
    if (t.refill) { t.stage = 'done'; this.endTurn(); return; }
    t.stage = t.drawn < t.need ? 'draw' : 'discard';
  };

  // Ablegen: indices = Handpositionen. opts: { action: bool, target: Spielerindex (nur bei Assen) }
  G.discardCards = function (indices, opts) {
    opts = opts || {};
    var t = this.turn, p = this.cur(), self = this;
    assertStage(t, 'discard');
    var uniq = indices.filter(function (v, i) { return indices.indexOf(v) === i; });
    if (uniq.length !== indices.length) throw new Error('Doppelte Auswahl');
    var sorted = uniq.slice().sort(function (a, b) { return a - b; });
    var entries = sorted.map(function (i) {
      if (i < 0 || i >= p.hand.length) throw new Error('Ung\u00fcltige Karte');
      return p.hand[i];
    });
    entries.forEach(function (e) {
      if (t.drawnIds.indexOf(e.card.id) >= 0) throw new Error('Eine gerade gezogene Karte darf nicht abgelegt werden');
    });
    var rank = entries.length === 2 && activeHalf(entries[0]).r === activeHalf(entries[1]).r ? activeHalf(entries[0]).r : 0;
    var action = !!opts.action;
    if (action) {
      if (entries.length !== 2 || (rank !== 14 && rank !== 13 && rank !== 12)) throw new Error('Kein g\u00fcltiges Aktionspaar');
      if (rank === 14) {
        if (opts.target == null || opts.target === this.current || !this.players[opts.target]) throw new Error('Ung\u00fcltiges Ziel');
      }
    } else if (entries.length !== t.need) {
      throw new Error('Falsche Anzahl abzulegender Karten');
    }
    // Karten aus der Hand nehmen
    for (var k = sorted.length - 1; k >= 0; k--) p.hand.splice(sorted[k], 1);
    var txt = entries.map(function (e) { return PK.halfText(activeHalf(e)); }).join(' ');

    if (!action) {
      entries.forEach(function (e) { self.discardPile.push({ card: e.card, flipped: e.flipped }); });
      this.say(p.name + ' legt ' + txt + ' ab.', 'discard');
    } else if (rank === 14) {
      this.removed.push(entries[0].card, entries[1].card);
      var tg = this.players[opts.target];
      if (tg.protectUntil >= this.round) {
        this.say(p.name + ' greift ' + tg.name + ' mit zwei Assen an \u2013 der K\u00f6nig-Schutz wehrt den Angriff ab!', 'attack');
      } else {
        tg.skipNext = true;
        this.say(p.name + ' legt zwei Asse vor ' + tg.name + ' \u2013 ' + tg.name + ' muss den n\u00e4chsten Zug aussetzen.', 'attack');
      }
    } else if (rank === 13) {
      this.removed.push(entries[0].card, entries[1].card);
      p.protectUntil = this.round + 1;
      this.say(p.name + ' legt zwei K\u00f6nige \u2013 Schutz bis Ende von Runde ' + (this.round + 1) + '.', 'action');
    } else {
      entries.forEach(function (e) { self.discardPile.push({ card: e.card, flipped: e.flipped }); });
      p.doubleDraw = true;
      this.say(p.name + ' legt zwei Damen \u2013 zieht im n\u00e4chsten Zug zwei Karten.', 'action');
    }

    if (action && t.need === 1) {
      // Hand hat jetzt 6 Karten -> mit einer Karte vom Nachziehstapel auff\u00fcllen
      if (this.canDraw('stack')) {
        t.refill = true;
        t.stage = 'draw';
        return;
      }
    }
    t.stage = 'done';
    this.endTurn();
  };

  // Handman\u00f6ver (ersetzt den ganzen Zug). m: {type:'flip', i} | {type:'move', from, to} | {type:'swap', i, j}
  G.manoeuvre = function (m) {
    var t = this.turn, p = this.cur(), h = p.hand;
    assertStage(t, 'draw');
    if (t.drawn !== 0 || t.refill) throw new Error('Handman\u00f6ver nur anstelle eines Zuges');
    function chk(i) { if (i < 0 || i >= h.length) throw new Error('Ung\u00fcltige Karte'); }
    if (m.type === 'flip') {
      chk(m.i);
      h[m.i].flipped = !h[m.i].flipped;
      this.say(p.name + ' dreht eine Karte um (Position ' + (m.i + 1) + ').', 'manoeuvre');
    } else if (m.type === 'move') {
      chk(m.from); chk(m.to);
      if (m.from === m.to) throw new Error('Karte bleibt an derselben Stelle');
      var e = h.splice(m.from, 1)[0];
      h.splice(m.to, 0, e);
      this.say(p.name + ' versetzt eine Karte (Position ' + (m.from + 1) + ' \u2192 ' + (m.to + 1) + ').', 'manoeuvre');
    } else if (m.type === 'swap') {
      chk(m.i); chk(m.j);
      if (m.i === m.j) throw new Error('Zwei verschiedene Karten w\u00e4hlen');
      var x = h[m.i]; h[m.i] = h[m.j]; h[m.j] = x;
      this.say(p.name + ' tauscht zwei Karten (Position ' + (m.i + 1) + ' \u2194 ' + (m.j + 1) + ').', 'manoeuvre');
    } else {
      throw new Error('Unbekanntes Handman\u00f6ver');
    }
    t.stage = 'done';
    this.endTurn();
  };

  /* ---- Wertung ---- */

  // decisions: Array je Spieler: null = passen, Zahl = Startposition des 5er-Fensters
  G.resolveScoring = function (decisions) {
    if (this.phase !== 'scoring') throw new Error('Keine Wertungsphase');
    var self = this, n = this.n;
    var entries = this.players.map(function (p, i) {
      var d = decisions[i];
      if (d == null) return { id: i, played: false, ev: null, start: null, cards: [], place: 0, points: 0, bonus: 0 };
      if (d < 0 || d + 5 > p.hand.length) throw new Error('Ung\u00fcltiges Fenster');
      var win = p.hand.slice(d, d + 5);
      return { id: i, played: true, start: d, entry: win, cards: win.map(function (e) { return { card: e.card, flipped: e.flipped }; }),
               ev: evaluate5(win.map(activeHalf)), place: 0, points: 0, bonus: 0 };
    });
    var players = entries.filter(function (e) { return e.played; });
    players.forEach(function (e) {
      e.place = 1 + players.filter(function (o) { return cmpEv(o.ev, e.ev) > 0; }).length;
      var table = POINTS[n];
      e.points = table[e.place - 1] || 0;
      e.bonus = BONUS[e.ev.cat] || 0;
    });
    entries.forEach(function (e) {
      var p = self.players[e.id];
      p.score += e.points + e.bonus;
      p.lastEv = e.ev;
    });

    // Gespielte Karten aus der Hand nehmen, 5 neue links anlegen
    var order = [];
    for (var k = 0; k < n; k++) order.push((this.start + k) % n);
    order.forEach(function (i) {
      var e = entries[i];
      if (!e.played) return;
      var p = self.players[i];
      var rest = p.hand.filter(function (_, idx) { return idx < e.start || idx >= e.start + 5; });
      e.entry.forEach(function (x) { self.removed.push(x.card); });
      var fresh = [];
      for (var c = 0; c < 5; c++) {
        if (!self.ensureDrawPile()) break;
        fresh.push({ card: self.drawPile.pop(), flipped: self.rng() < 0.5 });
      }
      p.hand = fresh.concat(rest);
      e.newCards = fresh.length;
    });

    entries.forEach(function (e) {
      var nm = self.players[e.id].name;
      if (!e.played) self.say(nm + ' passt.', 'score');
      else self.say(nm + ': ' + describe(e.ev) + ' \u2013 Platz ' + e.place + ', ' + (e.points + e.bonus) + ' Punkt(e)' + (e.bonus ? ' (inkl. ' + e.bonus + ' Bonus)' : '') + '.', 'score');
    });

    var result = { round: this.round, entries: entries.map(function (e) { return { id: e.id, played: e.played, start: e.start, cards: e.cards, ev: e.ev, place: e.place, points: e.points, bonus: e.bonus }; }) };
    this.lastResult = result;
    this.round++;
    this.phase = this.round > ROUNDS ? 'over' : 'results';
    if (this.phase === 'over') this.say('Das Spiel ist beendet.', 'round');
    return result;
  };

  G.nextRound = function () {
    if (this.phase !== 'results') throw new Error('Keine Rundenpause');
    this.start = (this.start - 1 + this.n) % this.n; // Spieler "rechts" vom bisherigen Startspieler
    this.current = this.start;
    this.turnCount = 0;
    this.turn = null;
    this.players.forEach(function (p) { p.turnsTaken = 0; });
    this.phase = 'collect';
    this.say('Runde ' + this.round + ' von ' + ROUNDS + ' beginnt. ' + this.players[this.start].name + ' f\u00e4ngt an.', 'round');
  };

  // Endwertung: sortierte Liste mit Platz; Gleichstand -> st\u00e4rkere Hand der letzten Wertung, sonst geteilt
  G.standings = function () {
    var list = this.players.slice().sort(function (a, b) {
      if (b.score !== a.score) return b.score - a.score;
      return cmpEv(b.lastEv, a.lastEv);
    });
    var out = [];
    list.forEach(function (p, i) {
      var prev = out[i - 1];
      var shared = prev && prev.player.score === p.score && cmpEv(prev.player.lastEv, p.lastEv) === 0;
      out.push({ player: p, place: shared ? prev.place : i + 1 });
    });
    return out;
  };

  PK.Game = Game;
  PK.CONST = { ROUNDS: ROUNDS, TURNS_PER_ROUND: TURNS_PER_ROUND, HAND_SIZE: HAND_SIZE, POINTS: POINTS };
  PK.shuffle = shuffle;
})(typeof window !== 'undefined' ? window : globalThis);
