/* Doppelkopf-Poker – Oberfläche */
(function () {
  'use strict';
  var PK = window.PK, E = PK.Eval, Bots = PK.Bots;

  var BOT_NAMES = ['Anna', 'Ben', 'Clara', 'Daniel'];
  var STORE_KEY = 'doppelkopfPoker.setup.v1';

  var cfg = { opp: 2, levels: ['medium', 'medium', 'medium', 'medium'], name: 'Du', speed: 500 };
  var game = null;
  var ui = { mode: 'idle', sel: [], mv: null, pendFlip: false, pumping: false, gen: 0, scoreSel: 0, error: '' };

  function $(id) { return document.getElementById(id); }
  function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  function loadCfg() {
    try {
      var s = JSON.parse(localStorage.getItem(STORE_KEY) || 'null');
      if (s && typeof s === 'object') {
        if (s.opp >= 1 && s.opp <= 4) cfg.opp = s.opp;
        if (Array.isArray(s.levels)) cfg.levels = cfg.levels.map(function (d, i) { return PK.LEVEL_NAMES[s.levels[i]] ? s.levels[i] : d; });
        if (typeof s.name === 'string' && s.name.trim()) cfg.name = s.name.slice(0, 16);
        if (typeof s.speed === 'number') cfg.speed = s.speed;
      }
    } catch (e) { /* localStorage evtl. nicht verfügbar */ }
  }
  function saveCfg() { try { localStorage.setItem(STORE_KEY, JSON.stringify(cfg)); } catch (e) { /* ignorieren */ } }

  /* ------------------------------------------------------------------ */
  /* Karten-HTML                                                        */
  /* ------------------------------------------------------------------ */

  function halfHTML(h, pos) {
    var red = h.s === 'H' || h.s === 'D';
    return '<div class="half ' + pos + ' ' + (red ? 'red' : 'blk') + '"><span class="rk">' + PK.rankLabel(h.r) +
      '</span><span class="st">' + PK.SUIT_SYMBOL[h.s] + '</span></div>';
  }
  function cardHTML(card, flipped, o) {
    o = o || {};
    var cls = 'card' + (flipped ? ' flipped' : '') + (o.size ? ' ' + o.size : '') + (o.clickable ? ' clickable' : '') +
      (o.selected ? ' selected' : '') + (o.dim ? ' dim' : '') + (o.isnew ? ' isnew' : '') + (o.extra ? ' ' + o.extra : '');
    var act = flipped ? card.b : card.a, oth = flipped ? card.a : card.b;
    var attrs = o.attrs || '';
    return '<div class="' + cls + '" ' + attrs + ' title="Oben: ' + PK.SUIT_NAME[act.s] + ' ' + PK.rankName(act.r) +
      ' / Unten: ' + PK.SUIT_NAME[oth.s] + ' ' + PK.rankName(oth.r) + '">' + halfHTML(card.a, 'top') + halfHTML(card.b, 'bottom') + '</div>';
  }

  /* ------------------------------------------------------------------ */
  /* Hilfsfunktionen Spielzustand                                       */
  /* ------------------------------------------------------------------ */

  function me() { return game.players[0]; }
  function humanTurn() {
    return game && game.phase === 'collect' && game.turn && game.cur().human ? game.turn : null;
  }
  function pairRank(i, j) {
    var h = me().hand;
    var a = E.activeHalf(h[i]), b = E.activeHalf(h[j]);
    return a.r === b.r && (a.r === 14 || a.r === 13 || a.r === 12) ? a.r : 0;
  }
  function delay() { return cfg.speed; }

  /* ------------------------------------------------------------------ */
  /* Setup                                                              */
  /* ------------------------------------------------------------------ */

  function renderSetup() {
    var h = '<h2>Neues Spiel</h2>';
    h += '<div class="field"><label class="title" for="nameIn">Dein Name</label><input type="text" id="nameIn" maxlength="16" value="' + esc(cfg.name) + '"></div>';
    h += '<div class="field"><label class="title">Anzahl Gegner (Bots)</label><div class="seg">';
    for (var k = 1; k <= 4; k++) h += '<button data-act="opp-count" data-v="' + k + '" class="' + (cfg.opp === k ? 'on' : '') + '">' + k + '</button>';
    h += '</div></div><div class="field"><label class="title">Schwierigkeit je Bot</label>';
    for (var i = 0; i < cfg.opp; i++) {
      h += '<div class="bot-row"><span class="nm">' + BOT_NAMES[i] + '</span><select data-bot="' + i + '">';
      Object.keys(PK.LEVEL_NAMES).forEach(function (lv) {
        h += '<option value="' + lv + '"' + (cfg.levels[i] === lv ? ' selected' : '') + '>' + PK.LEVEL_NAMES[lv] + '</option>';
      });
      h += '</select></div>';
    }
    h += '</div><div class="actions"><button class="btn" data-act="start">Spiel starten</button><button class="btn ghost" data-act="rules">Regeln lesen</button></div>';
    $('setup').innerHTML = h;
  }

  function showSetup() {
    ui.gen++; ui.pumping = false; game = null; hideModal();
    $('table').classList.add('hidden');
    $('setup').classList.remove('hidden');
    $('roundInfo').textContent = '';
    renderSetup();
  }

  function startGame() {
    var nameEl = $('nameIn');
    if (nameEl) cfg.name = nameEl.value.trim().slice(0, 16) || 'Du';
    saveCfg();
    var players = [{ name: cfg.name, human: true }];
    for (var i = 0; i < cfg.opp; i++) players.push({ name: BOT_NAMES[i], human: false, level: cfg.levels[i] });
    ui.gen++; ui.pumping = false;
    ui.mode = 'idle'; ui.sel = []; ui.mv = null; ui.pendFlip = false; ui.error = '';
    game = new PK.Game({ players: players });
    $('setup').classList.add('hidden');
    $('table').classList.remove('hidden');
    hideModal();
    render();
    pump();
  }

  /* ------------------------------------------------------------------ */
  /* Rendering                                                          */
  /* ------------------------------------------------------------------ */

  function render() {
    if (!game) return;
    if (!humanTurn()) { ui.mode = 'idle'; ui.sel = []; ui.mv = null; }
    renderTop(); renderOpponents(); renderPiles(); renderStatus(); renderControls(); renderMe(); renderLog();
  }

  function renderTop() {
    var pass = Math.min(PK.CONST.TURNS_PER_ROUND, Math.floor(game.turnCount / game.n) + 1);
    var r = Math.min(game.round, PK.CONST.ROUNDS);
    $('roundInfo').textContent = 'Wertung ' + r + '/' + PK.CONST.ROUNDS + (game.phase === 'collect' ? ' \u00b7 Zugrunde ' + pass + '/' + PK.CONST.TURNS_PER_ROUND : '');
  }

  function badgesFor(p) {
    var b = '';
    if (p.protectUntil >= game.round) b += '<span class="badge good" title="Gesch\u00fctzt vor Assen">\ud83d\udee1 Schutz bis Wertung ' + p.protectUntil + '</span>';
    if (p.skipNext) b += '<span class="badge warn">\u23ed setzt n\u00e4chsten Zug aus</span>';
    if (p.doubleDraw) b += '<span class="badge good">zieht 2 Karten</span>';
    return b;
  }

  function renderOpponents() {
    var h = '';
    for (var i = 1; i < game.n; i++) {
      var p = game.players[i];
      var active = game.phase === 'collect' && game.current === i;
      var backs = '';
      for (var k = 0; k < p.hand.length; k++) backs += '<span class="mini-back"></span>';
      h += '<div class="opp' + (active ? ' active' : '') + '"><div class="nm"><span>' + esc(p.name) + ' <span class="lv">' + PK.LEVEL_NAMES[p.level] + '</span></span><span class="sc">' + p.score + ' P</span></div>' +
        '<div class="backs">' + backs + '</div><div class="badges">' + badgesFor(p) + '</div></div>';
    }
    $('opponents').innerHTML = h;
  }

  function renderPiles() {
    var t = humanTurn();
    var canDrawNow = t && t.stage === 'draw' && ui.mode === 'idle';
    var dp = $('drawPile'), dc = $('discardPile');
    var remaining = game.drawPile.length;
    dp.innerHTML = '<div class="back-card"></div><span class="count">' + remaining + '</span>';
    dp.className = 'pile' + (canDrawNow && game.canDraw('stack') ? ' clickable' : '');
    dp.setAttribute('data-act', canDrawNow && game.canDraw('stack') ? 'draw-stack' : '');
    var topE = game.discardPile.length ? game.discardPile[game.discardPile.length - 1] : null;
    var canDisc = canDrawNow && !t.refill && topE;
    dc.innerHTML = topE ? cardHTML(topE.card, topE.flipped, {}) + '<span class="count">' + game.discardPile.length + '</span>' : '<span style="font-size:.7rem;color:#a9bfb0">leer</span>';
    dc.className = 'pile' + (canDisc ? ' clickable' : '');
    dc.setAttribute('data-act', canDisc ? 'draw-discard' : '');
  }

  function renderStatus() {
    var t = humanTurn(), s = '';
    if (game.phase === 'collect') {
      if (t) {
        if (ui.mode === 'flip') s = 'Handman\u00f6ver: Klicke die Karte, die du umdrehen willst.';
        else if (ui.mode === 'move1') s = 'Handman\u00f6ver: W\u00e4hle die Karte, die du versetzen willst.';
        else if (ui.mode === 'move2') s = 'Klicke eine L\u00fccke (+), an die die markierte Karte soll.';
        else if (ui.mode === 'swap1') s = 'Handman\u00f6ver: W\u00e4hle die erste von zwei Karten.';
        else if (ui.mode === 'swap2') s = 'W\u00e4hle die zweite Karte zum Tauschen.';
        else if (t.stage === 'draw') {
          if (t.refill) s = 'Auff\u00fcllen: Ziehe eine Karte vom Nachziehstapel.';
          else if (t.need === 2) s = 'Damen-Bonus: Ziehe Karte ' + (t.drawn + 1) + ' von 2 (Nachzieh- oder Ablagestapel).';
          else s = 'Du bist dran: Ziehe eine Karte (Stapel anklicken) oder f\u00fchre ein Handman\u00f6ver aus.';
        } else if (t.stage === 'place') s = 'Setze die Karte an eine L\u00fccke (+) in deine Hand \u2013 du kannst sie vorher drehen.';
        else if (t.stage === 'discard') s = t.need === 2
          ? 'W\u00e4hle zwei Karten zum Ablegen (nicht die neu gezogenen).'
          : 'W\u00e4hle eine Karte zum Ablegen \u2013 oder zwei gleiche Asse/K\u00f6nige/Damen als Aktionspaar.';
      } else {
        s = esc(game.cur().name) + ' ist am Zug \u2026';
      }
    } else if (game.phase === 'scoring') s = 'Wertungsphase';
    if (ui.error) s += ' <span style="color:#ff9c8f">(' + esc(ui.error) + ')</span>';
    $('status').innerHTML = s;
    var last = game.log.slice(-2).map(function (l) { return esc(l.msg); });
    $('ticker').innerHTML = last.join('<br>');
  }

  function btn(act, label, extra, cls) {
    return '<button class="btn ' + (cls || '') + '" data-act="' + act + '" ' + (extra || '') + '>' + label + '</button>';
  }

  function renderControls() {
    var t = humanTurn(), h = '';
    if (t) {
      if (ui.mode !== 'idle') {
        h += btn('mv-cancel', 'Abbrechen', '', 'ghost');
      } else if (t.stage === 'draw' && t.drawn === 0 && !t.refill) {
        h += btn('mv-flip', 'Karte umdrehen', '', 'ghost') + btn('mv-move', 'Karte versetzen', '', 'ghost') + btn('mv-swap', 'Zwei Karten tauschen', '', 'ghost');
      } else if (t.stage === 'place') {
        h += btn('flip-pend', '\u21bb Karte drehen', '', '');
      } else if (t.stage === 'discard') {
        var sel = ui.sel, hand = me().hand;
        if (sel.length === t.need && !(t.need === 1 && sel.length !== 1)) {
          h += btn('discard-sel', t.need === 2 ? 'Beide ablegen' : 'Ablegen');
        }
        if (sel.length === 2) {
          var rk = pairRank(sel[0], sel[1]);
          if (rk === 14) {
            game.players.forEach(function (p) {
              if (p.id === 0) return;
              h += btn('action', '\u2694 Angriff auf ' + esc(p.name) + (p.protectUntil >= game.round ? ' \ud83d\udee1' : ''), 'data-target="' + p.id + '"');
            });
          } else if (rk === 13) h += btn('action', '\ud83d\udee1 K\u00f6nigs-Schutz aktivieren', 'data-target="-1"');
          else if (rk === 12) h += btn('action', 'Damen ablegen (n\u00e4chster Zug: 2 Karten)', 'data-target="-1"');
        }
        if (!h) h = '<span style="font-size:.8rem;color:#a9bfb0">Karten antippen zum Ausw\u00e4hlen</span>';
      }
    }
    $('controls').innerHTML = h;
  }

  function renderMe() {
    var p = me(), t = humanTurn();
    var bw = p.hand.length >= 5 ? E.bestWindow(p.hand) : null;
    $('meBar').innerHTML = '<span><span class="nm">' + esc(p.name) + '</span> ' + badgesFor(p) + '</span>' +
      '<span>' + (bw ? '<small style="color:#a9bfb0">Beste Hand: ' + E.describe(bw.ev) + ' (Pos. ' + (bw.start + 1) + '\u2013' + (bw.start + 5) + ')</small> ' : '') +
      '<span class="sc">' + p.score + ' P</span></span>';

    var pend = '';
    if (t && t.stage === 'place' && t.pending) {
      var act = ui.pendFlip ? t.pending.b : t.pending.a;
      pend = cardHTML(t.pending, ui.pendFlip, { size: '' }) + '<span class="lbl">Oben liegt: ' + PK.SUIT_SYMBOL[act.s] + ' ' + PK.rankName(act.r) + '</span>';
    }
    $('pendingArea').innerHTML = pend;

    var placing = t && t.stage === 'place';
    var h = '';
    var hand = p.hand;
    for (var i = 0; i <= hand.length; i++) {
      var slotOK = false;
      if (placing) slotOK = true;
      else if (t && ui.mode === 'move2' && ui.mv) slotOK = (i !== ui.mv.from && i !== ui.mv.from + 1);
      if (slotOK) h += '<button class="slot" data-act="slot" data-i="' + i + '" aria-label="Einf\u00fcgen an Position ' + (i + 1) + '">+</button>';
      else if (i > 0 && i < hand.length) h += '<div class="gap"></div>';
      if (i < hand.length) {
        var e = hand[i], o = { clickable: false };
        var isNew = t && t.drawnIds && t.drawnIds.indexOf(e.card.id) >= 0;
        if (t) {
          if (ui.mode === 'flip' || ui.mode === 'move1' || ui.mode === 'swap1') o.clickable = true;
          else if (ui.mode === 'move2') { o.clickable = true; o.selected = ui.mv && ui.mv.from === i; }
          else if (ui.mode === 'swap2') { o.clickable = true; o.selected = ui.mv && ui.mv.i === i; }
          else if (t.stage === 'discard') {
            if (isNew) o.dim = false; else o.clickable = true;
            o.selected = ui.sel.indexOf(i) >= 0;
          }
          if (t.stage === 'discard' && isNew) o.isnew = true;
        }
        o.attrs = 'data-act="card" data-i="' + i + '"';
        h += '<div class="hc">' + cardHTML(e.card, e.flipped, o) + '<div class="idx">' + (i + 1) + '</div></div>';
      }
    }
    $('hand').innerHTML = h;
    $('handIdx').innerHTML = '';
  }

  function renderLog() {
    var items = game.log.slice(-60).map(function (l) { return '<li class="' + l.kind + '">' + esc(l.msg) + '</li>'; });
    $('log').innerHTML = items.join('');
  }

  /* ------------------------------------------------------------------ */
  /* Modals                                                             */
  /* ------------------------------------------------------------------ */

  function showModal(html) {
    $('modalCard').innerHTML = html;
    $('modal').classList.remove('hidden');
    $('modal').scrollTop = 0;
  }
  function hideModal() { $('modal').classList.add('hidden'); $('modalCard').innerHTML = ''; }

  function rulesHTML() {
    return '<h2>Regeln \u2013 Doppelkopf-Poker</h2>' +
      '<p>Jede Karte hat zwei H\u00e4lften. Nur die <b>obere</b> H\u00e4lfte z\u00e4hlt; mit Umdrehen wird die untere zur oberen. Ziel: \u00fcber 5 Wertungsrunden die meisten Punkte holen, indem du zur richtigen Zeit eine starke Pokerhand aus <b>5 nebeneinanderliegenden</b> Karten ausspielst.</p>' +
      '<h3>Hand</h3><p>Du hast 7 Karten in fester Reihenfolge \u2013 kein freies Sortieren. Die Reihenfolge \u00e4ndert sich nur durch Z\u00fcge und Handman\u00f6ver.</p>' +
      '<h3>Ein Zug</h3><ul><li><b>Ziehen:</b> oberste Karte vom Nachziehstapel oder Ablagestapel. Du setzt sie an eine beliebige Stelle in die Hand ein, normal oder gedreht (jetzt 8 Karten).</li>' +
      '<li><b>Ablegen:</b> eine andere Karte auf den Ablagestapel (nicht die gerade gezogene) \u2013 wieder 7 Karten.</li>' +
      '<li><b>Aktionspaar</b> statt einer Einzelkarte: zwei gleiche <b>Asse</b>, <b>K\u00f6nige</b> oder <b>Damen</b> (nach oben liegendem Wert).</li></ul>' +
      '<ul><li><b>Zwei Asse \u2013 Angriff:</b> Der gew\u00e4hlte Mitspieler muss <b>einen Zug aussetzen</b>.</li>' +
      '<li><b>Zwei K\u00f6nige \u2013 Schutz:</b> wehrt Asse-Angriffe in dieser und der n\u00e4chsten Wertungsrunde ab.</li>' +
      '<li><b>Zwei Damen:</b> Im n\u00e4chsten Zug ziehst du zwei Karten und legst zwei ab.</li></ul>' +
      '<h3>Handman\u00f6ver (ersetzt den ganzen Zug)</h3><p>Eine Karte umdrehen, eine Karte versetzen oder zwei Karten tauschen. Es z\u00e4hlt als einer deiner 4 Z\u00fcge.</p>' +
      '<h3>Wertung</h3><p>Nach 4 Z\u00fcgen pro Spieler: Jeder entscheidet, ob er mitspielt (5 nebeneinanderliegende Karten) oder passt. Wer mitspielt, bekommt 5 neue Karten links angelegt; die 2 \u00fcbrigen bleiben. Wer passt, beh\u00e4lt alles.</p>' +
      '<p><b>Rangfolge:</b> Royal Flush \u203a Straight Flush \u203a Four of a Kind \u203a Stra\u00dfe \u203a Full House \u203a Flush \u203a Drilling \u203a Zwei Paare \u203a Paar \u203a High Card.</p>' +
      '<p><b>Bonus (immer):</b> Stra\u00dfe oder Four of a Kind +1, Straight Flush +3, Royal Flush +4.</p>' +
      '<p><b>Platzpunkte (1./2./3.):</b> 2 Spieler 3/0 \u00b7 3 Spieler 3/2/0 \u00b7 4 Spieler 4/3/1 \u00b7 5 Spieler 5/4/2.</p>' +
      '<h3>Festlegungen dieser Online-Version</h3><ul>' +
      '<li>52 Doppelkarten (104 H\u00e4lften): jede Pokerkarte kommt genau zweimal vor. Ass ist hoch und niedrig (A-2-3-4-5).</li>' +
      '<li><b>Four of a Kind</b> braucht vier gleiche Werte in vier <b>verschiedenen</b> Farben (bei doppelten Farben z\u00e4hlt es nur als Drilling). Drilling gilt auch mit gleichen Farben.</li><li>Gleiche Hand = geteilter Platz (beide bekommen die Punkte des besseren Platzes); Farben haben keinen Rang.</li>' +
      '<li>Ein ausgesetzter Zug z\u00e4hlt als einer der 4 Z\u00fcge. Wurde man im letzten Zug einer Runde angegriffen, gilt es f\u00fcr den ersten Zug der n\u00e4chsten Runde.</li>' +
      '<li>Nach einem Aktionspaar (Hand hat 6 Karten) ziehst du zum Auff\u00fcllen eine Karte vom Nachziehstapel. Im Damen-Doppelzug ersetzt das Paar die beiden Pflichtablagen.</li>' +
      '<li>Der n\u00e4chste Startspieler ist der Spieler rechts vom bisherigen (Gegen-Uhrzeigersinn). Gleichstand am Ende: bessere Hand der letzten Wertung.</li></ul>' +
      '<div class="actions"><button class="btn" data-act="close-modal">Schlie\u00dfen</button></div>';
  }

  function openScoringModal() {
    var p = me();
    var wins = [];
    for (var s = 0; s + 5 <= p.hand.length; s++) wins.push({ start: s, ev: E.evaluate5(E.windowHalves(p.hand, s)) });
    var best = E.bestWindow(p.hand);
    if (ui.scoreSel == null || ui.scoreSel > wins.length - 1) ui.scoreSel = best.start;
    ui.scoreSel = best.start;
    renderScoringModal(wins);
  }

  function renderScoringModal(wins) {
    var p = me();
    var h = '<h2>Wertung \u2013 Runde ' + game.round + '</h2><p>W\u00e4hle ein 5er-Fenster und spiele mit \u2013 oder passe.</p><div class="hand-preview">';
    p.hand.forEach(function (e, i) {
      var inWin = i >= ui.scoreSel && i < ui.scoreSel + 5;
      h += cardHTML(e.card, e.flipped, { size: 'small', extra: inWin ? 'inwin' : 'outwin' });
    });
    h += '</div><div class="win-opts">';
    wins.forEach(function (w) {
      h += '<button class="win-opt' + (w.start === ui.scoreSel ? ' on' : '') + '" data-act="win" data-v="' + w.start + '">Karten ' + (w.start + 1) + '\u2013' + (w.start + 5) + ': <b>' + E.describe(w.ev) + '</b></button>';
    });
    h += '</div><div class="actions"><button class="btn" data-act="score-play">Mitspielen</button><button class="btn ghost" data-act="score-pass">Passen</button></div>';
    ui.wins = wins;
    showModal(h);
  }

  function finishScoring(humanChoice) {
    showModal('<h2>Wertung</h2><p>Die Bots entscheiden \u2026</p>');
    setTimeout(function () {
      var gen = ui.gen;
      var decisions = game.players.map(function (p) { return p.human ? humanChoice : Bots.decideScoring(game, p.id); });
      if (gen !== ui.gen) return;
      var res = game.resolveScoring(decisions);
      showResults(res);
      render();
    }, 30);
  }

  function showResults(res) {
    var entries = res.entries.slice().sort(function (a, b) {
      if (a.played !== b.played) return a.played ? -1 : 1;
      return a.place - b.place;
    });
    var h = '<h2>Ergebnis der ' + res.round + '. Wertung</h2>';
    entries.forEach(function (e) {
      var p = game.players[e.id];
      h += '<div class="res-row"><div class="head"><span>' + (e.played ? e.place + '. ' : '') + esc(p.name) + '</span>';
      if (e.played) h += '<span class="pts">' + E.describe(e.ev) + ' \u00b7 +' + (e.points + e.bonus) + ' P' + (e.bonus ? ' (davon ' + e.bonus + ' Bonus)' : '') + '</span>';
      else h += '<span>gepasst \u00b7 +0 P</span>';
      h += '</div>';
      if (e.played) {
        h += '<div class="cards">';
        e.cards.forEach(function (c) { h += cardHTML(c.card, c.flipped, { size: 'small' }); });
        h += '</div>';
      }
      h += '</div>';
    });
    h += '<table class="score"><tr><th>Spieler</th><th class="num">Gesamt</th></tr>';
    game.players.slice().sort(function (a, b) { return b.score - a.score; }).forEach(function (p) {
      h += '<tr><td>' + esc(p.name) + '</td><td class="num">' + p.score + '</td></tr>';
    });
    h += '</table><div class="actions">';
    h += game.phase === 'over' ? '<button class="btn" data-act="show-final">Endstand anzeigen</button>' : '<button class="btn" data-act="next-round">N\u00e4chste Runde starten</button>';
    h += '</div>';
    showModal(h);
  }

  function showFinal() {
    var st = game.standings();
    var h = '<h2>Spielende</h2>';
    var winners = st.filter(function (x) { return x.place === 1; });
    h += '<p><b>' + (winners.length > 1 ? 'Geteilter Sieg: ' : 'Sieger: ') + winners.map(function (w) { return esc(w.player.name); }).join(', ') + '</b></p>';
    h += '<table class="score"><tr><th>Platz</th><th>Spieler</th><th class="num">Punkte</th></tr>';
    st.forEach(function (x) { h += '<tr><td>' + x.place + '</td><td>' + esc(x.player.name) + '</td><td class="num">' + x.player.score + '</td></tr>'; });
    h += '</table><div class="actions"><button class="btn" data-act="start">Nochmal spielen</button><button class="btn ghost" data-act="to-menu">Men\u00fc</button></div>';
    showModal(h);
  }

  /* ------------------------------------------------------------------ */
  /* Bot-Schleife                                                       */
  /* ------------------------------------------------------------------ */

  async function pump() {
    if (ui.pumping || !game) return;
    ui.pumping = true;
    var my = ui.gen;
    try {
      while (game && my === ui.gen) {
        if (game.phase === 'collect') {
          game.startTurn();
          if (game.phase !== 'collect') { render(); continue; }
          if (game.cur().human) { render(); break; }
          render();
          await sleep(delay());
          if (my !== ui.gen) break;
          Bots.step(game);
          render();
        } else if (game.phase === 'scoring') {
          render();
          openScoringModal();
          break;
        } else break;
      }
    } catch (err) {
      console.error(err);
      ui.error = 'Fehler: ' + err.message;
      render();
    } finally {
      if (my === ui.gen) ui.pumping = false;
    }
  }

  /* ------------------------------------------------------------------ */
  /* Eingaben                                                           */
  /* ------------------------------------------------------------------ */

  function humanDo(fn) {
    ui.error = '';
    try { fn(); } catch (e) { console.error(e); ui.error = e.message; render(); return; }
    ui.sel = []; ui.mode = 'idle'; ui.mv = null; ui.pendFlip = false;
    render();
    pump();
  }

  function onCard(i) {
    var t = humanTurn();
    if (!t) return;
    var hand = me().hand;
    if (ui.mode === 'flip') { humanDo(function () { game.manoeuvre({ type: 'flip', i: i }); }); return; }
    if (ui.mode === 'move1') { ui.mv = { from: i }; ui.mode = 'move2'; render(); return; }
    if (ui.mode === 'move2') { ui.mv = { from: i }; render(); return; }
    if (ui.mode === 'swap1') { ui.mv = { i: i }; ui.mode = 'swap2'; render(); return; }
    if (ui.mode === 'swap2') {
      if (ui.mv.i === i) { ui.mv = null; ui.mode = 'swap1'; render(); return; }
      var a = ui.mv.i;
      humanDo(function () { game.manoeuvre({ type: 'swap', i: a, j: i }); });
      return;
    }
    if (t.stage === 'discard') {
      if (t.drawnIds.indexOf(hand[i].card.id) >= 0) return;
      var k = ui.sel.indexOf(i);
      if (k >= 0) ui.sel.splice(k, 1);
      else if (ui.sel.length < 2) ui.sel.push(i);
      else ui.sel = [ui.sel[1], i];
      render();
    }
  }

  function onSlot(pos) {
    var t = humanTurn();
    if (!t) return;
    if (t.stage === 'place') { humanDo(function () { game.place(pos, ui.pendFlip); }); return; }
    if (ui.mode === 'move2' && ui.mv) {
      var from = ui.mv.from, to = pos > from ? pos - 1 : pos;
      humanDo(function () { game.manoeuvre({ type: 'move', from: from, to: to }); });
    }
  }

  document.addEventListener('click', function (ev) {
    var el = ev.target.closest('[data-act]');
    if (!el) return;
    var act = el.getAttribute('data-act');
    if (!act) return;
    var t = humanTurn();
    switch (act) {
      case 'opp-count': cfg.opp = parseInt(el.getAttribute('data-v'), 10); renderSetup(); break;
      case 'start': hideModal(); startGame(); break;
      case 'rules': showModal(rulesHTML()); break;
      case 'close-modal': if (game && game.phase === 'scoring') openScoringModal(); else hideModal(); break;
      case 'to-menu': showSetup(); break;
      case 'draw-stack': if (t) humanDo(function () { game.draw('stack'); }); break;
      case 'draw-discard': if (t) humanDo(function () { game.draw('discard'); }); break;
      case 'card': onCard(parseInt(el.getAttribute('data-i'), 10)); break;
      case 'slot': onSlot(parseInt(el.getAttribute('data-i'), 10)); break;
      case 'flip-pend': ui.pendFlip = !ui.pendFlip; render(); break;
      case 'mv-flip': ui.mode = 'flip'; ui.sel = []; render(); break;
      case 'mv-move': ui.mode = 'move1'; ui.sel = []; render(); break;
      case 'mv-swap': ui.mode = 'swap1'; ui.sel = []; render(); break;
      case 'mv-cancel': ui.mode = 'idle'; ui.mv = null; render(); break;
      case 'discard-sel': var s1 = ui.sel.slice(); humanDo(function () { game.discardCards(s1, {}); }); break;
      case 'action':
        var tg = parseInt(el.getAttribute('data-target'), 10), s2 = ui.sel.slice();
        humanDo(function () { game.discardCards(s2, { action: true, target: tg >= 0 ? tg : null }); });
        break;
      case 'win': ui.scoreSel = parseInt(el.getAttribute('data-v'), 10); renderScoringModal(ui.wins); break;
      case 'score-play': finishScoring(ui.scoreSel); break;
      case 'score-pass': finishScoring(null); break;
      case 'show-final': showFinal(); break;
      case 'next-round': hideModal(); game.nextRound(); ui.error = ''; render(); pump(); break;
    }
  });

  document.addEventListener('change', function (ev) {
    var t = ev.target;
    if (t.hasAttribute && t.hasAttribute('data-bot')) {
      cfg.levels[parseInt(t.getAttribute('data-bot'), 10)] = t.value;
      saveCfg();
    }
  });

  $('btnRules').addEventListener('click', function () { showModal(rulesHTML()); });
  $('btnMenu').addEventListener('click', function () {
    if (!game || window.confirm('Aktuelles Spiel beenden und zum Men\u00fc?')) showSetup();
  });
  $('speedSel').addEventListener('change', function (e) { cfg.speed = parseInt(e.target.value, 10); saveCfg(); });
  $('modal').addEventListener('click', function (e) {
    if (e.target === $('modal') && !(game && (game.phase === 'scoring' || game.phase === 'results' || game.phase === 'over'))) hideModal();
  });

  loadCfg();
  $('speedSel').value = String(cfg.speed);
  if (!$('speedSel').value) { cfg.speed = 500; $('speedSel').value = '500'; }
  renderSetup();

  // für Tests/Debugging
  window.PK.__ui = { get game() { return game; }, ui: ui, render: render, startGame: startGame };
})();
