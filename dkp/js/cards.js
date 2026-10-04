/* Kartensatz: 52 Doppelkarten (104 Hälften = jede Pokerkarte genau 2x).
   Format: [oben, unten] – Farbe (H=Herz, D=Karo, S=Pik, C=Kreuz) + Rang (11=Bube, 12=Dame, 13=König, 14=Ass). */
(function (root) {
  'use strict';
  var PK = root.PK = root.PK || {};

  var RAW = [
  ['H14','S8'],
  ['H14','C3'],
  ['H2','S12'],
  ['H2','S6'],
  ['H3','S6'],
  ['H3','S5'],
  ['H4','C2'],
  ['H4','S2'],
  ['H5','S13'],
  ['H5','C4'],
  ['H6','S4'],
  ['H6','S13'],
  ['H7','C9'],
  ['H7','C2'],
  ['H8','S5'],
  ['H8','S4'],
  ['H9','S2'],
  ['H9','S12'],
  ['H10','C11'],
  ['H10','C13'],
  ['H11','C14'],
  ['H11','S8'],
  ['H12','S3'],
  ['H12','S14'],
  ['H13','C7'],
  ['H13','C9'],
  ['D14','S11'],
  ['D14','C8'],
  ['D2','C6'],
  ['D2','S3'],
  ['D3','C4'],
  ['D3','S7'],
  ['D4','C5'],
  ['D4','S9'],
  ['D5','C13'],
  ['D5','S11'],
  ['D6','C8'],
  ['D6','C14'],
  ['D7','S14'],
  ['D7','C10'],
  ['D8','S9'],
  ['D8','S10'],
  ['D9','C3'],
  ['D9','C11'],
  ['D10','S7'],
  ['D10','C5'],
  ['D11','S10'],
  ['D11','C12'],
  ['D12','C10'],
  ['D12','C7'],
  ['D13','C12'],
  ['D13','C6']
  ];

  var SUIT_SYMBOL = { H: '\u2665', D: '\u2666', S: '\u2660', C: '\u2663' };
  var SUIT_NAME = { H: 'Herz', D: 'Karo', S: 'Pik', C: 'Kreuz' };
  var RANK_LABEL = { 11: 'B', 12: 'D', 13: 'K', 14: 'A' };
  var RANK_NAME = { 11: 'Bube', 12: 'Dame', 13: 'K\u00f6nig', 14: 'Ass' };

  function half(code) { return { s: code.charAt(0), r: parseInt(code.slice(1), 10) }; }

  var DECK = RAW.map(function (pair, i) {
    return { id: i + 1, a: half(pair[0]), b: half(pair[1]) };
  });

  PK.DECK = DECK;
  PK.SUIT_SYMBOL = SUIT_SYMBOL;
  PK.SUIT_NAME = SUIT_NAME;
  PK.rankLabel = function (r) { return RANK_LABEL[r] || String(r); };
  PK.rankName = function (r) { return RANK_NAME[r] || String(r); };
  PK.halfText = function (h) { return SUIT_SYMBOL[h.s] + PK.rankLabel(h.r); };
})(typeof window !== 'undefined' ? window : globalThis);
