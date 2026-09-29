"""
sudoku_core.py

Kernlogik fuer das Hofgefluester-Raetsel: Validierung, eindeutige Loesbarkeit,
Ketten-Zaehlung (Produktionsketten), negative Nachbarschafts-Ziele, ein
"menschlicher" Logik-Solver mit gaengigen UND fortgeschrittenen Sudoku-
Techniken, sowie ein schwierigkeitsgesteuerter Level-Generator.

Komplett unabhaengig von der GUI, damit es einzeln getestet werden kann.

Wichtig: Bei einem NxN-Sudoku-Grid muss die Anzahl der verwendeten Symbole
IMMER genau N sein (klassische Sudoku-Regel: jedes Symbol genau einmal pro
Zeile/Spalte/Region). Das gilt auch, wenn eigene/zusaetzliche Symbole
definiert werden - die Symbolliste, die ein Level tatsaechlich benutzt,
wird deshalb immer als Parameter mitgegeben statt global fest zu sein.
"""

import random as _random
from itertools import combinations

N = 6
REGION_ROWS = 2   # jede Region ist 2 Zeilen hoch
REGION_COLS = 3   # und 3 Spalten breit


def configure_grid(region_rows, region_cols):
    """
    Stellt die Gitter-Dimensionen um. Ein Sudoku-Gitter mit Regionen der
    Groesse region_rows x region_cols ist immer N x N mit
    N = region_rows * region_cols (z.B. 2x3-Regionen -> 6x6-Feld mit 6
    Regionen, 3x3-Regionen -> 9x9-Feld mit 9 Regionen - klassisches Sudoku).

    Veraendert das Modul-weite N/REGION_ROWS/REGION_COLS, auf das alle
    anderen Funktionen dieses Moduls zugreifen. Nicht thread-sicher, aber
    fuer die Verwendung aus einer einzelnen Editor-Instanz/einem einzelnen
    Browser-Tab heraus unproblematisch.
    """
    global N, REGION_ROWS, REGION_COLS
    if region_rows < 1 or region_cols < 1:
        raise ValueError("region_rows und region_cols muessen positiv sein.")
    REGION_ROWS = region_rows
    REGION_COLS = region_cols
    N = region_rows * region_cols

# Eingebaute Standard-Symbole. Zusaetzliche, selbst erstellte Symbole werden
# im Editor verwaltet und zusammen mit dem Level exportiert/importiert -
# dieses Modul selbst schreibt hier nichts fest vor.
#
# Felder:
#   color -> Hintergrundfarbe (immer gesetzt, dient als Fallback)
#   abbr  -> 2-3-Buchstaben-Kuerzel (Fallback-Darstellung, v.a. im Editor,
#            da Emoji-Fonts unter Linux/Tkinter oft nicht zuverlaessig sind)
#   icon  -> Emoji (optional). Wird auf der Website bevorzugt angezeigt,
#            wenn vorhanden.
#   image -> Pfad zu einer Bilddatei, z.B. Pixel-Art-Sprite (optional,
#            fuer spaetere Erweiterung). Wird noch nirgends gerendert,
#            das Feld ist nur schon vorbereitet.
DEFAULT_SYMBOLS = [
    {"id": "wald", "name": "Wald", "color": "#2f6b3a", "abbr": "WA", "icon": "🌲", "image": None},
    {"id": "saegewerk", "name": "Sägewerk", "color": "#8a5a2b", "abbr": "SW", "icon": "🪚", "image": None},
    {"id": "feld", "name": "Feld", "color": "#c9a227", "abbr": "FE", "icon": "🌾", "image": None},
    {"id": "scheune", "name": "Scheune", "color": "#a8402f", "abbr": "SC", "icon": "🏚️", "image": None},
    {"id": "brunnen", "name": "Brunnen", "color": "#3d7a91", "abbr": "BR", "icon": "💧", "image": None},
    {"id": "haus", "name": "Haus", "color": "#6b4a2f", "abbr": "HA", "icon": "🏠", "image": None},
    # Zusaetzliche Standard-Symbole, damit auch ein 3x3-Regionen-Feld (9x9,
    # 9 Symbole benoetigt) direkt mit sinnvollen Vorgaben starten kann.
    {"id": "teich", "name": "Teich", "color": "#2f6b91", "abbr": "TE", "icon": "🐟", "image": None},
    {"id": "zaun", "name": "Zaun", "color": "#7a5c3d", "abbr": "ZA", "icon": "🚧", "image": None},
    {"id": "windmuehle", "name": "Windmühle", "color": "#8a7a5a", "abbr": "WM", "icon": "🎡", "image": None},
]

# ---------------------------------------------------------------------------
# Technik-Stufen (fuer Schwierigkeitsgrad-Steuerung)
# ---------------------------------------------------------------------------
# Jede "menschliche" Loesungstechnik wird einer Stufe zugeordnet. Je hoeher
# die Stufe, desto fortgeschrittener/schwieriger ist die Technik. Der
# Level-Generator und die Bewertung nutzen das, um einen Schwierigkeitsgrad
# einzustellen bzw. zu ermitteln.
#
# Ziel-Deduktion ("goal_deduction") ist bewusst NICHT Teil dieser Tier-Skala:
# ob sie gebraucht werden darf/muss, wird unabhaengig von der Schwierigkeit
# ueber ein eigenes Flag gesteuert (siehe require_goal_logic bei
# generate_level() bzw. allow_goal_deduction bei is_logically_solvable()) -
# im Editor entspricht das der Checkbox "Nur mit Zielvorgaben lösbar".
TECHNIQUE_TIER = {
    "naked_single": 1,
    "hidden_single": 2,
    "locked_candidates": 3,
    "naked_pair": 3,
    "hidden_pair": 3,
    "negative_goal_pruning": 3,
    "naked_triple": 4,
    "hidden_triple": 4,
    "x_wing": 4,
}

# Schwierigkeitsgrade, wie sie im Editor/Generator ausgewaehlt werden koennen.
# Steuert, bis zu welcher Technik-Stufe der Solver beim Herleiten der Loesung
# greifen darf. "beginner" ist bewusst noch einfacher als "easy": es kommt
# ganz ohne Hidden Single aus (nur Naked Single).
DIFFICULTY_TIERS = {
    "beginner": 1,
    "easy": 2,
    "medium": 3,
    "hard": 4,
}

DIFFICULTY_LABELS = {1: "anfänger", 2: "leicht", 3: "mittel", 4: "schwer"}


def _tier_to_difficulty_label(max_tier_used):
    """Ordnet die hoechste tatsaechlich benutzte Technik-Stufe einem
    Schwierigkeitslabel zu. Ob zusaetzlich Ziel-Deduktion gebraucht wird,
    wird davon unabhaengig ueber `requires_goal_logic` berichtet."""
    return DIFFICULTY_LABELS.get(max(max_tier_used, 1), "leicht")


def empty_grid():
    return [[None for _ in range(N)] for _ in range(N)]


def region_bounds(r, c):
    br = (r // REGION_ROWS) * REGION_ROWS
    bc = (c // REGION_COLS) * REGION_COLS
    return br, bc


def row_ok(grid, r):
    vals = [v for v in grid[r] if v is not None]
    return len(vals) == len(set(vals))


def col_ok(grid, c):
    vals = [grid[r][c] for r in range(N) if grid[r][c] is not None]
    return len(vals) == len(set(vals))


def box_ok(grid, r, c):
    br, bc = region_bounds(r, c)
    vals = [
        grid[rr][cc]
        for rr in range(br, br + REGION_ROWS)
        for cc in range(bc, bc + REGION_COLS)
        if grid[rr][cc] is not None
    ]
    return len(vals) == len(set(vals))


def all_conflicts(grid):
    """Liefert die Menge aller Zellkoordinaten, die an einem Konflikt beteiligt sind."""
    conflicts = set()

    for r in range(N):
        seen = {}
        for c in range(N):
            v = grid[r][c]
            if v is None:
                continue
            if v in seen:
                conflicts.add((r, c))
                conflicts.add((r, seen[v]))
            else:
                seen[v] = c

    for c in range(N):
        seen = {}
        for r in range(N):
            v = grid[r][c]
            if v is None:
                continue
            if v in seen:
                conflicts.add((r, c))
                conflicts.add((seen[v], c))
            else:
                seen[v] = r

    for br in range(0, N, REGION_ROWS):
        for bc in range(0, N, REGION_COLS):
            seen = {}
            for r in range(br, br + REGION_ROWS):
                for c in range(bc, bc + REGION_COLS):
                    v = grid[r][c]
                    if v is None:
                        continue
                    if v in seen:
                        conflicts.add((r, c))
                        conflicts.add(seen[v])
                    else:
                        seen[v] = (r, c)

    return conflicts


def is_full(grid):
    return all(grid[r][c] is not None for r in range(N) for c in range(N))


def count_solutions(grid, symbol_ids, limit=2):
    """
    Zaehlt gueltige Vervollstaendigungen des Grids mit den gegebenen Symbolen,
    bricht aber ab sobald `limit` erreicht ist.
    symbol_ids muss genau N Eintraege haben (Sudoku-Grundregel).
    """
    if len(symbol_ids) != N:
        raise ValueError(f"Es werden genau {N} Symbole benoetigt, {len(symbol_ids)} gegeben.")
    g = [row[:] for row in grid]
    return _count_solutions_recursive(g, symbol_ids, limit)


def _count_solutions_recursive(grid, symbol_ids, limit):
    for r in range(N):
        for c in range(N):
            if grid[r][c] is None:
                total = 0
                for v in symbol_ids:
                    grid[r][c] = v
                    if row_ok(grid, r) and col_ok(grid, c) and box_ok(grid, r, c):
                        total += _count_solutions_recursive(grid, symbol_ids, limit - total)
                    if total >= limit:
                        grid[r][c] = None
                        return total
                grid[r][c] = None
                return total
    return 1


def has_unique_solution(grid, symbol_ids):
    return count_solutions(grid, symbol_ids, limit=2) == 1


# ---------------------------------------------------------------------------
# Negative Ziele
# ---------------------------------------------------------------------------
# Ein negatives Ziel beschraenkt, wie oft bestimmte Symbole INSGESAMT im Grid
# orthogonal nebeneinander liegen duerfen - im Unterschied zu den (positiven)
# Ketten-Zielen, die eine bestimmte Anzahl verlangen. Format:
#   {"symbols": [sym_id, ...], "max_count": int}
# Gezaehlt wird jede orthogonal benachbarte Zellenpaarung, bei der BEIDE
# Zellen ein Symbol aus der angegebenen Menge enthalten (auch zweimal
# dasselbe Symbol, z.B. um Cluster desselben Symbols zu verhindern).
# max_count = 0 bedeutet: die Symbole duerfen NIE nebeneinander liegen.

def count_negative_adjacency(grid, symbols):
    symset = set(symbols)
    count = 0
    for r in range(N):
        for c in range(N):
            v = grid[r][c]
            if v is None or v not in symset:
                continue
            if c + 1 < N:
                v2 = grid[r][c + 1]
                if v2 is not None and v2 in symset:
                    count += 1
            if r + 1 < N:
                v2 = grid[r + 1][c]
                if v2 is not None and v2 in symset:
                    count += 1
    return count


def negative_goals_satisfied(grid, negative_goals):
    if not negative_goals:
        return True
    for ng in negative_goals:
        if count_negative_adjacency(grid, ng["symbols"]) > ng["max_count"]:
            return False
    return True


def goals_satisfied(grid, goals, negative_goals=None):
    """Prueft, ob ALLE positiven Ziele (Liste von {chain, target_count}) UND
    alle negativen Ziele im (vollen) Grid erfuellt sind."""
    for goal in goals:
        cnt, _ = chain_count(grid, goal["chain"])
        if cnt != goal["target_count"]:
            return False
    return negative_goals_satisfied(grid, negative_goals)


def count_solutions_with_goals(grid, symbol_ids, goals, negative_goals=None, limit=2):
    """
    Zaehlt gueltige Vervollstaendigungen des Grids, die ZUSAETZLICH alle
    gegebenen positiven UND negativen Ziele erfuellen. Im Unterschied zu
    count_solutions() wird hier bis zu einer vollstaendigen Loesung
    durchgesucht (Ketten/Nachbarschaften lassen sich erst an der fertigen
    Belegung auswerten), aber die Suche bricht ab, sobald `limit` passende
    Loesungen gefunden wurden.

    Das ist deutlich teurer als count_solutions() (kein frueher Abbruch durch
    Zeilen/Spalten/Regionen-nahe Pruning der Ziele selbst), daher fuer groessere
    Grids/viele Vorgaben mit Bedacht einsetzen.
    """
    if len(symbol_ids) != N:
        raise ValueError(f"Es werden genau {N} Symbole benoetigt, {len(symbol_ids)} gegeben.")
    negative_goals = negative_goals or []
    g = [row[:] for row in grid]
    found = [0]

    def backtrack():
        for r in range(N):
            for c in range(N):
                if g[r][c] is None:
                    for v in symbol_ids:
                        g[r][c] = v
                        if row_ok(g, r) and col_ok(g, c) and box_ok(g, r, c):
                            backtrack()
                            if found[0] >= limit:
                                g[r][c] = None
                                return
                        g[r][c] = None
                    return
        # volles, gueltiges Sudoku-Grid erreicht - jetzt Ziele pruefen
        if goals_satisfied(g, goals, negative_goals):
            found[0] += 1

    backtrack()
    return found[0]


def classify_puzzle(grid, symbol_ids, goals, negative_goals=None):
    """
    Klassifiziert ein Puzzle (Vorgabe-Grid + Ziele) danach, WIE es eindeutig
    loesbar ist. Das ist der Kern der Frage "wird das Level wirklich durch
    die besonderen Ziele geloest, oder waeren die Sudoku-Regeln allein schon
    genug?".

    Rueckgabe: einer der folgenden Strings:
      "unsolvable"        - selbst mit Zielen keine oder keine eindeutige Loesung
      "sudoku_only"       - Sudoku-Regeln ALLEIN ergeben schon genau eine Loesung,
                             UND diese Loesung erfuellt auch alle (evtl. gesetzten)
                             positiven/negativen Ziele; die Ziele sind dann nur ein
                             Fakt ueber diese Loesung, aber fuers Loesen nicht noetig
      "goals_required"    - Sudoku-Regeln allein sind mehrdeutig (oder die
                             einzige rein-rechnerische Loesung erfuellt die
                             Ziele nicht), aber zusammen mit den Zielen ergibt
                             sich genau eine Loesung; der Spieler MUSS die
                             Ziele mitdenken, um zu loesen

    Hinweis: Das ist eine rein RECHNERISCHE Klassifikation (Backtracking-
    Solver, darf raten). Ob ein Mensch die Loesung auch tatsaechlich ohne
    Raten herleiten kann, prueft zusaetzlich is_logically_solvable() bzw.
    evaluate_puzzle() weiter unten.
    """
    negative_goals = negative_goals or []
    sudoku_only_count = count_solutions(grid, symbol_ids, limit=2)
    if sudoku_only_count == 1:
        unique_solution = solve_full_random(symbol_ids, grid=[row[:] for row in grid])
        if unique_solution is not None and goals_satisfied(unique_solution, goals, negative_goals):
            return "sudoku_only"
        return "unsolvable"

    with_goals_count = count_solutions_with_goals(grid, symbol_ids, goals, negative_goals, limit=2)
    if with_goals_count == 1:
        return "goals_required"

    return "unsolvable"


def evaluate_puzzle(grid, symbol_ids, goals, negative_goals=None):
    """
    Umfassende Bewertung eines Puzzles (Vorgabe-Grid + Ziele), die sowohl die
    rechnerische Klassifikation als auch die tatsaechliche, menschliche
    Loesbarkeit (ohne Raten) beruecksichtigt - inklusive aller gaengigen und
    fortgeschrittenen Techniken (siehe is_logically_solvable()).

    Rueckgabe: dict mit
      classification         -> wie classify_puzzle() (s.o.)
      logically_solvable_without_goals -> True, wenn alle Techniken AUSSER
                                 Ziel-Deduktion (positive Ketten-Ziele) zur
                                 Loesung fuehren (negative Ziele zaehlen
                                 dabei als normale, immer aktive Randbedingung)
      logically_solvable_with_goals    -> True, wenn zusaetzlich Ziel-
                                 Deduktion einbezogen zur Loesung fuehrt
      requires_goal_logic     -> True, wenn die (positive) Ziel-Deduktion
                                 tatsaechlich gebraucht wird, um ohne Raten
                                 zur Loesung zu kommen
      playable                -> True, wenn das Raetsel ueberhaupt sinnvoll
                                 spielbar ist: rechnerisch eindeutig loesbar
                                 UND durch reine Logik (mit oder ohne
                                 Ziel-Deduktion) ohne Raten loesbar
      techniques_used         -> sortierte Liste der tatsaechlich benutzten
                                 Techniken (inkl. Ziel-Deduktion, falls
                                 gebraucht)
      max_technique_tier      -> hoechste benutzte "konventionelle" Technik-
                                 Stufe (1=Naked Single, 2=+Hidden Single,
                                 3=+Locked Candidates/Paare/Negative-Ziel-
                                 Pruning, 4=+Tripel/X-Wing). Ziel-Deduktion
                                 zaehlt hier NICHT mit rein, siehe
                                 requires_goal_logic.
      difficulty              -> grobes Schwierigkeitslabel allein aufgrund
                                 von max_technique_tier ('anfänger',
                                 'leicht', 'mittel', 'schwer') - unabhaengig
                                 davon, ob zusaetzlich requires_goal_logic gilt
    """
    negative_goals = negative_goals or []
    classification = classify_puzzle(grid, symbol_ids, goals, negative_goals)

    without = is_logically_solvable(
        grid, symbol_ids, goals=None, negative_goals=negative_goals,
        max_tier=4, allow_goal_deduction=False, return_details=True
    )
    with_ = is_logically_solvable(
        grid, symbol_ids, goals=goals, negative_goals=negative_goals,
        max_tier=4, allow_goal_deduction=True, return_details=True
    )

    logically_without = without["solvable"]
    logically_with = with_["solvable"]
    requires_goal_logic = logically_with and not logically_without

    playable = classification in ("sudoku_only", "goals_required") and logically_with

    return {
        "classification": classification,
        "logically_solvable_without_goals": logically_without,
        "logically_solvable_with_goals": logically_with,
        "requires_goal_logic": requires_goal_logic,
        "playable": playable,
        "techniques_used": sorted(with_["techniques_used"], key=lambda t: TECHNIQUE_TIER.get(t, 0)),
        "max_technique_tier": with_["max_tier_used"],
        "difficulty": _tier_to_difficulty_label(with_["max_tier_used"]),
    }


# ---------------------------------------------------------------------------
# "Menschlicher" Logik-Solver
# ---------------------------------------------------------------------------
#
# count_solutions() / has_unique_solution() pruefen nur, ob es rechnerisch
# GENAU EINE gueltige Endbelegung gibt. Das sagt aber nichts darueber aus, ob
# ein Mensch diese Loesung auch tatsaechlich durch Nachdenken (ohne Raten)
# herleiten kann - ein Backtracking-Solver darf raten und bei Sackgassen
# zuruecksetzen, ein sauberes Raetsel sollte das nicht erfordern.
#
# is_logically_solvable() simuliert stattdessen einen Menschen, der die
# folgenden, in der Sudoku-Community gaengigen Techniken anwendet, bis
# entweder das Grid voll ist oder keine Technik mehr greift. Die Techniken
# sind nach Schwierigkeit geordnet (siehe TECHNIQUE_TIER):
#
#   Stufe 1 (Anfänger):
#     - Naked Single    - eine Zelle hat nur noch genau einen moeglichen Wert
#   Stufe 2 (Leicht):
#     - Hidden Single    - ein Wert passt in einer Zeile/Spalte/Region nur
#                          noch in eine einzige Zelle
#   Stufe 3 (Mittel):
#     - Locked Candidates (Pointing/Claiming) - ein Kandidat ist innerhalb
#                          einer Region auf eine Zeile/Spalte beschraenkt
#                          (oder umgekehrt) und kann anderswo entfernt werden
#     - Naked Pair       - zwei Zellen einer Einheit haben zusammen nur zwei
#                          moegliche Werte -> diese koennen anderswo in der
#                          Einheit entfernt werden
#     - Hidden Pair      - zwei Werte passen in einer Einheit nur noch in
#                          dieselben zwei Zellen
#     - Negative-Ziel-Pruning - wenn ein negatives Ziel durch bereits fest
#                          stehende Zellen schon ausgeschoepft ist, koennen
#                          weitere Kandidaten, die die Grenze ueberschreiten
#                          wuerden, direkt entfernt werden
#   Stufe 4 (Schwer):
#     - Naked Triple / Hidden Triple - wie Paare, nur mit drei Zellen/Werten
#     - X-Wing           - ein Wert bildet in zwei Zeilen (oder Spalten)
#                          exakt dasselbe Spalten-Paar (Zeilen-Paar) als
#                          Kandidaten -> kann in diesen Spalten/Zeilen sonst
#                          ueberall entfernt werden
#   Zusaetzlich, UNABHAENGIG von der Stufe (siehe allow_goal_deduction):
#     - Ziel-Deduktion   - wenn ein Nachbarschafts-Ziel (Kette) schon so weit
#                          eingeschraenkt ist, dass eine bestimmte Zelle in
#                          JEDER verbleibenden gueltigen Zielerfuellung
#                          denselben Wert haben muss, wird dieser Wert
#                          uebernommen. Bewusst auf kleine Suchraeume
#                          begrenzt (Endspiel-Faelle), sonst waere es
#                          verstecktes Brute-Force-Raten.
#
# Kein Raten/Backtracking - wenn keine dieser Techniken mehr greift, bevor
# das Grid voll ist, gilt das Raetsel als NICHT durch reine Logik loesbar,
# selbst wenn es rechnerisch eindeutig waere.

def _candidates_grid(grid, symbol_ids, eliminated=None):
    """Fuer jede leere Zelle: Menge der noch moeglichen Werte, basierend auf
    Zeilen-, Spalten- und Regionsregeln, abzueglich per `eliminated` explizit
    entfernter Kandidaten (r, c, value)."""
    eliminated = eliminated or set()
    cands = {}
    for r in range(N):
        for c in range(N):
            if grid[r][c] is not None:
                continue
            used = set()
            used.update(v for v in grid[r] if v is not None)
            used.update(grid[rr][c] for rr in range(N) if grid[rr][c] is not None)
            br, bc = region_bounds(r, c)
            for rr in range(br, br + REGION_ROWS):
                for cc in range(bc, bc + REGION_COLS):
                    if grid[rr][cc] is not None:
                        used.add(grid[rr][cc])
            options = {v for v in (set(symbol_ids) - used) if (r, c, v) not in eliminated}
            cands[(r, c)] = options
    return cands


def _all_units():
    """Alle Einheiten (Zeilen, Spalten, Regionen) als Zellkoordinatenlisten."""
    units = []
    for r in range(N):
        units.append([(r, c) for c in range(N)])
    for c in range(N):
        units.append([(r, c) for r in range(N)])
    for br in range(0, N, REGION_ROWS):
        for bc in range(0, N, REGION_COLS):
            units.append([(rr, cc) for rr in range(br, br + REGION_ROWS) for cc in range(bc, bc + REGION_COLS)])
    return units


def _apply_naked_singles(grid, symbol_ids, eliminated):
    """Sucht Zellen mit genau einem Kandidaten. Setzt den ERSTEN gefundenen
    und gibt True zurueck, falls etwas gesetzt wurde."""
    cands = _candidates_grid(grid, symbol_ids, eliminated)
    for (r, c), options in cands.items():
        if len(options) == 1:
            grid[r][c] = next(iter(options))
            return True
        if len(options) == 0:
            # Widerspruch - diese Zelle hat gar keinen gueltigen Kandidaten mehr
            return "contradiction"
    return False


def _apply_hidden_singles(grid, symbol_ids, eliminated):
    """Sucht Werte, die in einer Zeile/Spalte/Region nur noch in eine
    einzige Zelle passen. Setzt den ERSTEN gefundenen Fall."""
    cands = _candidates_grid(grid, symbol_ids, eliminated)

    for cells in _all_units():
        for v in symbol_ids:
            spots = [cell for cell in cells if grid[cell[0]][cell[1]] is None and v in cands.get(cell, set())]
            if len(spots) == 1:
                r, c = spots[0]
                grid[r][c] = v
                return True
    return False


def _apply_locked_candidates(grid, symbol_ids, eliminated):
    """Pointing: ein Kandidat, der innerhalb einer Region nur in einer
    einzigen Zeile/Spalte vorkommt, kann ausserhalb der Region in dieser
    Zeile/Spalte entfernt werden.
    Claiming: umgekehrt - ein Kandidat, der innerhalb einer Zeile/Spalte nur
    in einer einzigen Region vorkommt, kann ausserhalb dieser Zeile/Spalte
    in der Region entfernt werden."""
    cands = _candidates_grid(grid, symbol_ids, eliminated)

    boxes = []
    for br in range(0, N, REGION_ROWS):
        for bc in range(0, N, REGION_COLS):
            boxes.append([(rr, cc) for rr in range(br, br + REGION_ROWS) for cc in range(bc, bc + REGION_COLS)])

    # Pointing: Region -> Zeile/Spalte
    for box in boxes:
        for v in symbol_ids:
            spots = [cell for cell in box if grid[cell[0]][cell[1]] is None and v in cands.get(cell, set())]
            if len(spots) < 2:
                continue
            rows = {cell[0] for cell in spots}
            cols = {cell[1] for cell in spots}
            if len(rows) == 1:
                r = next(iter(rows))
                for c in range(N):
                    if (r, c) not in box and grid[r][c] is None and v in cands.get((r, c), set()):
                        if (r, c, v) not in eliminated:
                            eliminated.add((r, c, v))
                            return True
            if len(cols) == 1:
                c = next(iter(cols))
                for r in range(N):
                    if (r, c) not in box and grid[r][c] is None and v in cands.get((r, c), set()):
                        if (r, c, v) not in eliminated:
                            eliminated.add((r, c, v))
                            return True

    # Claiming: Zeile/Spalte -> Region
    lines = []
    for r in range(N):
        lines.append([(r, c) for c in range(N)])
    for c in range(N):
        lines.append([(r, c) for r in range(N)])

    for line in lines:
        for v in symbol_ids:
            spots = [cell for cell in line if grid[cell[0]][cell[1]] is None and v in cands.get(cell, set())]
            if len(spots) < 2:
                continue
            boxes_touched = {region_bounds(*cell) for cell in spots}
            if len(boxes_touched) == 1:
                br, bc = next(iter(boxes_touched))
                for rr in range(br, br + REGION_ROWS):
                    for cc in range(bc, bc + REGION_COLS):
                        if (rr, cc) not in line and grid[rr][cc] is None and v in cands.get((rr, cc), set()):
                            if (rr, cc, v) not in eliminated:
                                eliminated.add((rr, cc, v))
                                return True
    return False


def _apply_naked_subset(grid, symbol_ids, eliminated, size):
    """Generalisiertes Naked Pair (size=2) / Naked Triple (size=3): `size`
    Zellen einer Einheit, deren Kandidaten zusammen genau `size` Werte
    ergeben, koennen diese Werte bei allen anderen Zellen der Einheit
    entfernen."""
    cands = _candidates_grid(grid, symbol_ids, eliminated)

    for cells in _all_units():
        empty_cells = [cell for cell in cells if grid[cell[0]][cell[1]] is None]
        candidate_cells = [cell for cell in empty_cells if 1 < len(cands.get(cell, set())) <= size]
        if len(candidate_cells) < size:
            continue
        for combo in combinations(candidate_cells, size):
            union = set()
            for cell in combo:
                union |= cands.get(cell, set())
            if len(union) != size:
                continue
            changed = False
            for cell in empty_cells:
                if cell in combo:
                    continue
                for v in cands.get(cell, set()) & union:
                    if (cell[0], cell[1], v) not in eliminated:
                        eliminated.add((cell[0], cell[1], v))
                        changed = True
            if changed:
                return True
    return False


def _apply_hidden_subset(grid, symbol_ids, eliminated, size):
    """Generalisiertes Hidden Pair (size=2) / Hidden Triple (size=3): `size`
    Werte, die innerhalb einer Einheit nur noch in denselben `size` Zellen
    vorkommen koennen, schliessen dort alle anderen Kandidaten dieser Zellen
    aus."""
    cands = _candidates_grid(grid, symbol_ids, eliminated)

    for cells in _all_units():
        empty_cells = [cell for cell in cells if grid[cell[0]][cell[1]] is None]
        if len(empty_cells) <= size:
            continue
        value_positions = {}
        for v in symbol_ids:
            spots = [cell for cell in empty_cells if v in cands.get(cell, set())]
            if 1 < len(spots) <= size:
                value_positions[v] = spots
        candidate_values = list(value_positions.keys())
        if len(candidate_values) < size:
            continue
        for combo in combinations(candidate_values, size):
            union_cells = set()
            for v in combo:
                union_cells |= set(value_positions[v])
            if len(union_cells) != size:
                continue
            changed = False
            for cell in union_cells:
                for v in cands.get(cell, set()) - set(combo):
                    if (cell[0], cell[1], v) not in eliminated:
                        eliminated.add((cell[0], cell[1], v))
                        changed = True
            if changed:
                return True
    return False


def _apply_x_wing(grid, symbol_ids, eliminated):
    """X-Wing: bildet ein Kandidat in zwei Zeilen jeweils exakt dasselbe
    Spaltenpaar (bzw. in zwei Spalten dasselbe Zeilenpaar), kann er in
    diesen Spalten/Zeilen ausserhalb der beiden Zeilen/Spalten entfernt
    werden."""
    cands = _candidates_grid(grid, symbol_ids, eliminated)

    # Zeilen -> Spalten
    for v in symbol_ids:
        row_spots = {}
        for r in range(N):
            spots = tuple(c for c in range(N) if grid[r][c] is None and v in cands.get((r, c), set()))
            if len(spots) == 2:
                row_spots[r] = spots
        rows = list(row_spots.keys())
        for r1, r2 in combinations(rows, 2):
            if row_spots[r1] != row_spots[r2]:
                continue
            cols = row_spots[r1]
            changed = False
            for c in cols:
                for r in range(N):
                    if r in (r1, r2):
                        continue
                    if grid[r][c] is None and v in cands.get((r, c), set()):
                        if (r, c, v) not in eliminated:
                            eliminated.add((r, c, v))
                            changed = True
            if changed:
                return True

    # Spalten -> Zeilen
    for v in symbol_ids:
        col_spots = {}
        for c in range(N):
            spots = tuple(r for r in range(N) if grid[r][c] is None and v in cands.get((r, c), set()))
            if len(spots) == 2:
                col_spots[c] = spots
        cols = list(col_spots.keys())
        for c1, c2 in combinations(cols, 2):
            if col_spots[c1] != col_spots[c2]:
                continue
            rows = col_spots[c1]
            changed = False
            for r in rows:
                for c in range(N):
                    if c in (c1, c2):
                        continue
                    if grid[r][c] is None and v in cands.get((r, c), set()):
                        if (r, c, v) not in eliminated:
                            eliminated.add((r, c, v))
                            changed = True
            if changed:
                return True
    return False


def _apply_negative_goal_pruning(grid, symbol_ids, negative_goals, eliminated):
    """Wenn ein negatives Ziel durch bereits FEST stehende Zellen schon
    ausgeschoepft ist (Grenzwert erreicht), duerfen keine weiteren Symbole
    dieser Gruppe mehr direkt neben ein bereits feststehendes Symbol
    derselben Gruppe gesetzt werden - diese Kandidaten koennen entfernt
    werden."""
    if not negative_goals:
        return False
    cands = _candidates_grid(grid, symbol_ids, eliminated)
    changed = False
    for ng in negative_goals:
        symset = set(ng["symbols"])
        max_count = ng["max_count"]
        fixed_count = count_negative_adjacency(grid, symset)
        if fixed_count < max_count:
            continue
        for r in range(N):
            for c in range(N):
                if grid[r][c] is not None:
                    continue
                has_fixed_neighbor_in_group = any(
                    grid[nr][nc] is not None and grid[nr][nc] in symset
                    for (nr, nc) in neighbors(r, c)
                )
                if not has_fixed_neighbor_in_group:
                    continue
                for v in list(cands.get((r, c), set())):
                    if v in symset and (r, c, v) not in eliminated:
                        eliminated.add((r, c, v))
                        changed = True
    return changed


def _apply_goal_deduction(grid, symbol_ids, goals, negative_goals=None, eliminated=None,
                           max_empty_cells=8, max_completions_to_check=3000):
    """
    Ziel-Deduktion: Fuer jedes Ziel wird geprueft, ob unter allen noch
    moeglichen Vervollstaendigungen der LEEREN Zellen (unter Beachtung der
    normalen Sudoku-Regeln UND evtl. negativer Ziele) JEDE davon zur
    geforderten target_count der Kette fuehrt UND dabei mindestens eine
    leere Zelle in ALLEN diesen Vervollstaendigungen denselben Wert hat.
    Falls ja, wird dieser Wert uebernommen.

    Bewusst auf kleine Suchraeume begrenzt: greift NUR, wenn hoechstens
    `max_empty_cells` Zellen noch leer sind (Endspiel-Faelle, die ein Mensch
    tatsaechlich im Kopf durchprobieren koennte). Bei mehr leeren Zellen waere
    die vollstaendige Aufzaehlung aller Vervollstaendigungen bereits
    verstecktes Brute-Force-Raten statt echter menschlicher Logik - die
    Technik wird dann bewusst NICHT angewendet, selbst wenn sie rechnerisch
    moeglich waere.
    """
    negative_goals = negative_goals or []
    empty_cells = [(r, c) for r in range(N) for c in range(N) if grid[r][c] is None]
    if not empty_cells or not goals:
        return False
    if len(empty_cells) > max_empty_cells:
        return False

    cands = _candidates_grid(grid, symbol_ids, eliminated)

    completions = []
    truncated = [False]

    def backtrack(idx):
        if len(completions) >= max_completions_to_check:
            truncated[0] = True
            return
        if idx == len(empty_cells):
            completions.append(dict((cell, grid[cell[0]][cell[1]]) for cell in empty_cells))
            return
        r, c = empty_cells[idx]
        for v in cands.get((r, c), set(symbol_ids)):
            grid[r][c] = v
            if row_ok(grid, r) and col_ok(grid, c) and box_ok(grid, r, c):
                backtrack(idx + 1)
            grid[r][c] = None
            if len(completions) >= max_completions_to_check:
                truncated[0] = True
                return

    backtrack(0)

    if truncated[0] or not completions:
        return False

    valid_completions = [comp for comp in completions if _completion_satisfies_goals(grid, comp, goals, negative_goals)]

    if not valid_completions:
        return False

    # Suche eine Zelle, die in ALLEN gueltigen (zielerfuellenden)
    # Vervollstaendigungen denselben Wert hat, aber nicht in allen rein
    # Sudoku-gueltigen Vervollstaendigungen (sonst waere es keine echte
    # Ziel-Deduktion, sondern bereits durch andere Techniken abgedeckt).
    for cell in empty_cells:
        goal_values = set(comp[cell] for comp in valid_completions)
        if len(goal_values) == 1:
            all_values = set(comp[cell] for comp in completions)
            if len(all_values) > 1:
                r, c = cell
                grid[r][c] = next(iter(goal_values))
                return True

    return False


def _completion_satisfies_goals(grid, completion, goals, negative_goals=None):
    """Prueft, ob eine gegebene Vervollstaendigung (dict cell->value) der
    leeren Zellen zusammen mit dem aktuellen Grid alle positiven UND
    negativen Ziele erfuellt."""
    temp = [row[:] for row in grid]
    for (r, c), v in completion.items():
        temp[r][c] = v
    return goals_satisfied(temp, goals, negative_goals)


def is_logically_solvable(grid, symbol_ids, goals=None, negative_goals=None, max_steps=500,
                           max_tier=4, allow_goal_deduction=False, return_details=False):
    """
    Simuliert einen Menschen, der ausschliesslich die oben beschriebenen
    Techniken einsetzt (kein Raten/Backtracking), begrenzt auf "konventionelle"
    Techniken bis einschliesslich Stufe `max_tier` (siehe TECHNIQUE_TIER),
    plus optional Ziel-Deduktion.

    Gibt True (bzw. bei return_details=True ein Detail-Dict) zurueck, wenn
    das Grid dadurch bis zur vollstaendigen, gueltigen Loesung gebracht
    werden kann, die auch alle Ziele erfuellt. Gibt False zurueck, wenn
    irgendwann keine erlaubte Technik mehr greift, obwohl das Grid noch
    nicht voll ist (das Raetsel waere dann nur durch Raten/Ausprobieren mit
    dieser Technik-Obergrenze loesbar), oder falls ein Widerspruch auftritt.

    max_tier: hoechste erlaubte "konventionelle" Technik-Stufe:
      1 = nur Naked Single (Anfänger)
      2 = + Hidden Single (Leicht)
      3 = + Locked Candidates, Naked/Hidden Pair, Negative-Ziel-Pruning (Mittel)
      4 = + Naked/Hidden Triple, X-Wing (Schwer)
    allow_goal_deduction: ob zusaetzlich Ziel-Deduktion (positive Ketten-
    Ziele) als Technik erlaubt ist - UNABHAENGIG von max_tier. Das
    entspricht im Editor der Checkbox "Nur mit Zielvorgaben lösbar".
    negative_goals: optionale Liste von {symbols, max_count} - werden immer
    als Randbedingung beruecksichtigt (End-Check UND Negative-Ziel-Pruning
    ab Stufe 3), unabhaengig von `goals`/`allow_goal_deduction`.
    """
    if len(symbol_ids) != N:
        raise ValueError(f"Es werden genau {N} Symbole benoetigt, {len(symbol_ids)} gegeben.")

    g = [row[:] for row in grid]
    goals = goals or []
    negative_goals = negative_goals or []
    eliminated = set()
    techniques_used = set()

    def finish(ok):
        if return_details:
            max_tier_used = max((TECHNIQUE_TIER.get(t, 0) for t in techniques_used), default=0)
            return {"solvable": ok, "techniques_used": techniques_used, "max_tier_used": max_tier_used}
        return ok

    for _ in range(max_steps):
        if is_full(g):
            ok = (not all_conflicts(g)) and goals_satisfied(g, goals, negative_goals)
            return finish(ok)

        progress = _apply_naked_singles(g, symbol_ids, eliminated)
        if progress == "contradiction":
            return finish(False)
        if progress:
            techniques_used.add("naked_single")
            continue

        if max_tier >= 2:
            if _apply_hidden_singles(g, symbol_ids, eliminated):
                techniques_used.add("hidden_single")
                continue

        if max_tier >= 3:
            if negative_goals and _apply_negative_goal_pruning(g, symbol_ids, negative_goals, eliminated):
                techniques_used.add("negative_goal_pruning")
                continue
            if _apply_locked_candidates(g, symbol_ids, eliminated):
                techniques_used.add("locked_candidates")
                continue
            if _apply_naked_subset(g, symbol_ids, eliminated, 2):
                techniques_used.add("naked_pair")
                continue
            if _apply_hidden_subset(g, symbol_ids, eliminated, 2):
                techniques_used.add("hidden_pair")
                continue

        if max_tier >= 4:
            if _apply_naked_subset(g, symbol_ids, eliminated, 3):
                techniques_used.add("naked_triple")
                continue
            if _apply_hidden_subset(g, symbol_ids, eliminated, 3):
                techniques_used.add("hidden_triple")
                continue
            if _apply_x_wing(g, symbol_ids, eliminated):
                techniques_used.add("x_wing")
                continue

        if allow_goal_deduction and goals:
            if _apply_goal_deduction(g, symbol_ids, goals, negative_goals, eliminated):
                techniques_used.add("goal_deduction")
                continue

        # keine erlaubte Technik greift mehr - nur durch Raten fortsetzbar
        return finish(False)

    return finish(is_full(g) and not all_conflicts(g) and goals_satisfied(g, goals, negative_goals))


def neighbors(r, c):
    if r > 0: yield (r - 1, c)
    if r < N - 1: yield (r + 1, c)
    if c > 0: yield (r, c - 1)
    if c < N - 1: yield (r, c + 1)


def adjacency_count(grid, sym_a, sym_b):
    """Zaehlt orthogonale Nachbarschaften zwischen zwei Symbolen.
    Bleibt fuer Abwaertskompatibilitaet erhalten (Spezialfall einer 2er-Kette)."""
    return chain_count(grid, [sym_a, sym_b])


def chain_count(grid, chain_symbols):
    """
    Zaehlt, wie oft eine Produktionskette (Liste von Symbolen in Reihenfolge)
    im Grid als zusammenhaengender Pfad vorkommt, bei dem jedes Element
    orthogonal an das vorherige angrenzt (beliebig gewinkelt, KEINE gerade
    Linie noetig). Jede Zelle wird innerhalb eines einzelnen Kettenfundes nur
    einmal benutzt (kein Wiederbenutzen derselben Zelle in einem Pfad).

    Rueckgabe: (anzahl_gefundener_ketten, liste_der_zell-pfade)
    """
    if len(chain_symbols) < 2:
        return 0, []

    found_paths = []

    def dfs(path, used_cells):
        step = len(path)
        if step == len(chain_symbols):
            found_paths.append(list(path))
            return
        last_r, last_c = path[-1]
        needed_symbol = chain_symbols[step]
        for (nr, nc) in neighbors(last_r, last_c):
            if (nr, nc) in used_cells:
                continue
            if grid[nr][nc] == needed_symbol:
                path.append((nr, nc))
                used_cells.add((nr, nc))
                dfs(path, used_cells)
                path.pop()
                used_cells.discard((nr, nc))

    for r in range(N):
        for c in range(N):
            if grid[r][c] == chain_symbols[0]:
                dfs([(r, c)], {(r, c)})

    return len(found_paths), found_paths


def solve_full_random(symbol_ids, grid=None, rng=None):
    """Fuellt ein (moeglicherweise leeres) Grid zu einer zufaelligen, gueltigen
    Komplettloesung auf, unter Verwendung der gegebenen Symbolliste
    (muss Laenge N haben). Gibt das fertige Grid oder None zurueck.

    Hinweis: beruecksichtigt KEINE Ziele (positiv oder negativ) - falls diese
    gebraucht werden, muss das Ergebnis zusaetzlich mit goals_satisfied() /
    negative_goals_satisfied() geprueft werden (siehe generate_level(), das
    genau das tut)."""
    if len(symbol_ids) != N:
        raise ValueError(f"Es werden genau {N} Symbole benoetigt, {len(symbol_ids)} gegeben.")
    rng = rng or _random
    g = grid if grid is not None else empty_grid()

    def backtrack():
        for r in range(N):
            for c in range(N):
                if g[r][c] is None:
                    order = list(symbol_ids)
                    rng.shuffle(order)
                    for v in order:
                        g[r][c] = v
                        if row_ok(g, r) and col_ok(g, c) and box_ok(g, r, c):
                            if backtrack():
                                return True
                        g[r][c] = None
                    return False
        return True

    ok = backtrack()
    return g if ok else None


def generate_random_solution_with_negative_goals(symbol_ids, negative_goals=None, grid=None, rng=None, max_tries=200):
    """Wie solve_full_random(), erzeugt aber nur Loesungen, die zusaetzlich
    alle negativen Ziele erfuellen (durch Wiederholung, da negative Ziele
    beim Backtracking selbst nicht foerderlich eingebaut sind - bei einem
    6x6-Grid ist das schnell genug). Gibt None zurueck, wenn in `max_tries`
    Versuchen keine passende Loesung gefunden wurde."""
    rng = rng or _random
    negative_goals = negative_goals or []
    base = grid
    for _ in range(max_tries):
        start = [row[:] for row in base] if base is not None else None
        solution = solve_full_random(symbol_ids, grid=start, rng=rng)
        if solution is not None and negative_goals_satisfied(solution, negative_goals):
            return solution
    return None


# ---------------------------------------------------------------------------
# Schwierigkeitsgesteuerter Level-Generator
# ---------------------------------------------------------------------------

def _puzzle_from_solution_and_givens(solution, givens):
    """Erzeugt das spielbare Puzzle-Grid aus einer Komplettloesung und der
    Menge der als Vorgabe erhaltenen Zellen.

    Diese kleine Hilfsfunktion ist bewusst zentralisiert, damit Generator und
    nachgelagerte Validierung garantiert dasselbe Grid pruefen.
    """
    given_set = set(givens)
    return [
        [solution[r][c] if (r, c) in given_set else None for c in range(N)]
        for r in range(N)
    ]


def _validate_generated_candidate(
    solution,
    givens,
    symbol_ids,
    goals,
    negative_goals,
    target_tier,
    require_goal_logic,
):
    """Validiert einen komplett erzeugten Generator-Kandidaten.

    Wichtig: Der Generator darf sich nicht allein darauf verlassen, dass die
    beim Entfernen einer einzelnen Zelle gemachte Zwischenpruefung bestanden
    wurde. Jede spaetere Entfernung veraendert das Gesamtproblem. Deshalb wird
    das am Ende entstandene Puzzle noch einmal von Grund auf geprueft.

    Die Pruefung verlangt insbesondere:
      * die gespeicherte Komplettloesung ist selbst gueltig und erfuellt alle
        Ziele;
      * es gibt genau eine Sudoku-Loesung, wenn Ziele nicht gebraucht werden,
        bzw. genau eine zielkonforme Loesung insgesamt;
      * die tatsaechliche logische Loesbarkeit entspricht der Generator-
        Einstellung;
      * die Schwierigkeitsobergrenze wird eingehalten;
      * bei require_goal_logic=True wird die Ziel-Deduktion tatsaechlich
        benoetigt;
      * die endgueltige Bewertung meldet das Puzzle als spielbar.

    Dadurch kann keine veraltete Zwischenbewertung aus dem Entfernungs-
    Durchlauf versehentlich als fertiges Level durchrutschen.
    """
    if len(symbol_ids) != N:
        raise ValueError(f"Es werden genau {N} Symbole benoetigt, {len(symbol_ids)} gegeben.")

    # 1. Die vom Generator behauptete Komplettloesung muss unabhaengig von
    #    allen weiteren Schritten eine gueltige Sudoku-Loesung sein.
    if not is_full(solution) or all_conflicts(solution):
        return None
    if any(solution[r][c] not in symbol_ids for r in range(N) for c in range(N)):
        return None
    if not goals_satisfied(solution, goals, negative_goals):
        return None

    puzzle = _puzzle_from_solution_and_givens(solution, givens)

    # 2. Die Vorgaben selbst muessen gueltig sein.
    if all_conflicts(puzzle):
        return None

    # 3. Rechnerische Eindeutigkeit wird explizit und unabhaengig vom
    #    Entfernungsdurchlauf erneut geprueft.
    sudoku_solution_count = count_solutions(puzzle, symbol_ids, limit=2)
    goal_solution_count = count_solutions_with_goals(
        puzzle,
        symbol_ids,
        goals,
        negative_goals,
        limit=2,
    )

    if goal_solution_count != 1:
        return None

    # Wenn das Puzzle bereits ohne Ziele eindeutig ist, muss diese eindeutige
    # Sudoku-Loesung ebenfalls die Zielvorgaben erfuellen. Andernfalls waeren
    # die Ziele mit dem erzeugten Level widerspruechlich.
    if sudoku_solution_count == 1:
        only_solution = solve_full_random(symbol_ids, grid=[row[:] for row in puzzle])
        if only_solution is None or not goals_satisfied(only_solution, goals, negative_goals):
            return None

    classification = classify_puzzle(puzzle, symbol_ids, goals, negative_goals)
    if classification not in ("sudoku_only", "goals_required"):
        return None

    # 4. Jetzt wird genau die Loeselogik ausgefuehrt, die das fertige Level
    #    spaeter ebenfalls verwendet. Das ist bewusst eine frische Pruefung.
    logical = is_logically_solvable(
        puzzle,
        symbol_ids,
        goals=goals,
        negative_goals=negative_goals,
        max_tier=target_tier,
        allow_goal_deduction=require_goal_logic,
        return_details=True,
    )
    if not logical["solvable"]:
        return None
    if logical["max_tier_used"] > target_tier:
        return None

    # Ohne Checkbox darf Ziel-Deduktion nicht heimlich fuer die Loesbarkeit
    # verantwortlich sein. Mit Checkbox muss sie dagegen wirklich notwendig
    # sein; sonst wuerde ein normales Sudoku-Level mit beliebigen Zielwerten
    # als "zielabhaengig" exportiert.
    logical_without_goals = is_logically_solvable(
        puzzle,
        symbol_ids,
        goals=None,
        negative_goals=negative_goals,
        max_tier=target_tier,
        allow_goal_deduction=False,
        return_details=True,
    )
    requires_goal_logic = logical["solvable"] and not logical_without_goals["solvable"]
    if require_goal_logic != requires_goal_logic:
        return None

    # 5. Letzte Gesamtbewertung. Diese darf die obigen Einzelpruefungen nicht
    #    ersetzen, weil wir hier absichtlich mehrere unabhaengige Bedingungen
    #    kontrollieren.
    evaluation = evaluate_puzzle(puzzle, symbol_ids, goals, negative_goals)
    if not evaluation["playable"]:
        return None
    if evaluation["classification"] != classification:
        return None
    if evaluation["max_technique_tier"] > target_tier:
        return None
    if evaluation["requires_goal_logic"] != require_goal_logic:
        return None

    return evaluation


def generate_level(
    symbol_ids,
    goals_template=None,
    negative_goals=None,
    difficulty="easy",
    require_goal_logic=False,
    max_solution_tries=40,
    max_removal_attempts=3,
    rng=None,
):
    """
    Erzeugt ein neues Level passend zur gewuenschten Schwierigkeit.

    difficulty: 'beginner' | 'easy' | 'medium' | 'hard'
      Begrenzt, bis zu welcher "konventionellen" Technik-Stufe die Loesung
      durch reine Logik hergeleitet werden darf (siehe TECHNIQUE_TIER/
      DIFFICULTY_TIERS): je hoeher, desto mehr fortgeschrittene Techniken
      duerfen (aber muessen nicht) noetig sein. 'beginner' ist noch
      einfacher als 'easy' und kommt ganz ohne Hidden Single aus.

    require_goal_logic: UNABHAENGIG von der Schwierigkeit waehlbar (im
      Editor eine Checkbox). Wenn True, muss die (positive) Ziel-Deduktion
      tatsaechlich gebraucht werden (requires_goal_logic == True in der
      Bewertung). Wenn False, wird ein Level gesucht, das OHNE
      Ziel-Deduktion auskommt.

    goals_template: Liste von Ketten OHNE target_count (dann wird die
      tatsaechliche Anzahl in der gefundenen Loesung uebernommen), oder mit
      vorgegebenem target_count (dann muss die Loesung genau das erreichen).

    negative_goals: Liste von {symbols, max_count} - werden bereits bei der
      Erzeugung der Zufallsloesung erzwungen.

    Der entscheidende Unterschied zur alten Generatorversion ist die letzte
    unabhaengige Gesamtvalidierung: Nicht nur jede einzelne Zell-Entfernung,
    sondern das ENTSTANDENE ENDPUZZLE muss rechnerisch eindeutig und mit den
    konkreten Zielvorgaben logisch loesbar sein. Ein Kandidat wird verworfen,
    sobald irgendeine dieser Bedingungen nicht mehr stimmt.

    Rueckgabe: dict mit solution, givens, goals, negative_goals, evaluation
    - oder None, falls in den Versuchslimits nichts Passendes gefunden wurde.
    """
    rng = rng or _random
    goals_template = goals_template or []
    negative_goals = negative_goals or []

    if len(symbol_ids) != N:
        raise ValueError(f"Es werden genau {N} Symbole benoetigt, {len(symbol_ids)} gegeben.")
    if difficulty not in DIFFICULTY_TIERS:
        raise ValueError(f"Unbekannter Schwierigkeitsgrad: {difficulty!r}")

    target_tier = DIFFICULTY_TIERS[difficulty]
    best = None

    for _ in range(max_solution_tries):
        solution = generate_random_solution_with_negative_goals(
            symbol_ids,
            negative_goals,
            rng=rng,
            max_tries=50,
        )
        if solution is None:
            continue

        # Die Zielanzahlen werden immer aus GENAU DIESER Komplettloesung
        # bestimmt. Damit kann das exportierte Ziel niemals zu einer anderen
        # Loesung gehoeren als die vom Generator gespeicherte solution.
        resolved_goals = []
        template_ok = True
        for g in goals_template:
            if isinstance(g, dict):
                chain = list(g.get("chain", []))
                wanted = g.get("target_count")
            else:
                chain = list(g)
                wanted = None

            if len(chain) < 2:
                template_ok = False
                break

            cnt, _ = chain_count(solution, chain)
            if wanted is not None and cnt != wanted:
                template_ok = False
                break
            resolved_goals.append({"chain": chain, "target_count": cnt})

        if not template_ok:
            continue

        for _attempt in range(max_removal_attempts):
            cells = [(r, c) for r in range(N) for c in range(N)]
            rng.shuffle(cells)
            givens = set(cells)
            puzzle = [row[:] for row in solution]

            # Greedy removal. Jede Entfernung wird bereits gegen die
            # tatsaechlichen Zielbedingungen geprueft. Die Endvalidierung
            # weiter unten ist trotzdem zwingend, weil mehrere Entfernungen
            # zusammen einen Zustand erzeugen koennen, der von den lokalen
            # Zwischenpruefungen nicht ausreichend beschrieben wird.
            for (r, c) in cells:
                saved = puzzle[r][c]
                puzzle[r][c] = None

                classification = classify_puzzle(
                    puzzle,
                    symbol_ids,
                    resolved_goals,
                    negative_goals,
                )
                still_unique = classification in ("sudoku_only", "goals_required")

                still_solvable = False
                if still_unique:
                    logical = is_logically_solvable(
                        puzzle,
                        symbol_ids,
                        goals=resolved_goals,
                        negative_goals=negative_goals,
                        max_tier=target_tier,
                        allow_goal_deduction=require_goal_logic,
                    )
                    still_solvable = logical

                if still_solvable:
                    givens.discard((r, c))
                else:
                    puzzle[r][c] = saved

            evaluation = _validate_generated_candidate(
                solution,
                givens,
                symbol_ids,
                resolved_goals,
                negative_goals,
                target_tier,
                require_goal_logic,
            )
            if evaluation is None:
                continue

            result = {
                "solution": [row[:] for row in solution],
                "givens": sorted(givens),
                "goals": [
                    {"chain": list(g["chain"]), "target_count": g["target_count"]}
                    for g in resolved_goals
                ],
                "negative_goals": [dict(g) for g in negative_goals],
                "evaluation": evaluation,
            }

            if best is None or len(result["givens"]) < len(best["givens"]):
                best = result

    return best
