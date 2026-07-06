"""
sudoku_core.py

Kernlogik fuer das Hofgefluester-Raetsel: Validierung, eindeutige Loesbarkeit,
Ketten-Zaehlung (Produktionsketten), dynamische Symbol-Sets.
Komplett unabhaengig von der GUI, damit es einzeln getestet werden kann.

Wichtig: Bei einem NxN-Sudoku-Grid muss die Anzahl der verwendeten Symbole
IMMER genau N sein (klassische Sudoku-Regel: jedes Symbol genau einmal pro
Zeile/Spalte/Region). Das gilt auch, wenn eigene/zusaetzliche Symbole
definiert werden - die Symbolliste, die ein Level tatsaechlich benutzt,
wird deshalb immer als Parameter mitgegeben statt global fest zu sein.
"""

N = 6
REGION_ROWS = 2   # jede Region ist 2 Zeilen hoch
REGION_COLS = 3   # und 3 Spalten breit

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
]


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


def goals_satisfied(grid, goals):
    """Prueft, ob ALLE Ziele (Liste von {chain, target_count}) im (vollen)
    Grid erfuellt sind."""
    for goal in goals:
        cnt, _ = chain_count(grid, goal["chain"])
        if cnt != goal["target_count"]:
            return False
    return True


def count_solutions_with_goals(grid, symbol_ids, goals, limit=2):
    """
    Zaehlt gueltige Vervollstaendigungen des Grids, die ZUSAETZLICH alle
    gegebenen Ziele erfuellen. Im Unterschied zu count_solutions() wird hier
    bis zu einer vollstaendigen Loesung durchgesucht (Ketten lassen sich erst
    an der fertigen Belegung auswerten), aber die Suche bricht ab, sobald
    `limit` passende Loesungen gefunden wurden.

    Das ist deutlich teurer als count_solutions() (kein frueher Abbruch durch
    Zeilen/Spalten/Regionen-nahe Pruning der Ziele selbst), daher fuer groessere
    Grids/viele Vorgaben mit Bedacht einsetzen.
    """
    if len(symbol_ids) != N:
        raise ValueError(f"Es werden genau {N} Symbole benoetigt, {len(symbol_ids)} gegeben.")
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
        if goals_satisfied(g, goals):
            found[0] += 1

    backtrack()
    return found[0]


def classify_puzzle(grid, symbol_ids, goals):
    """
    Klassifiziert ein Puzzle (Vorgabe-Grid + Ziele) danach, WIE es eindeutig
    loesbar ist. Das ist der Kern der Frage "wird das Level wirklich durch
    die besonderen Ziele geloest, oder waeren die Sudoku-Regeln allein schon
    genug?".

    Rueckgabe: einer der folgenden Strings:
      "unsolvable"        - selbst mit Zielen keine oder keine eindeutige Loesung
      "sudoku_only"       - Sudoku-Regeln ALLEIN ergeben schon genau eine Loesung;
                             die Ziele sind nur ein Fakt ueber diese Loesung, aber
                             fuers Loesen nicht noetig
      "goals_required"    - Sudoku-Regeln allein sind mehrdeutig, aber zusammen
                             mit den Zielen ergibt sich genau eine Loesung; der
                             Spieler MUSS die Ziele mitdenken, um zu loesen

    Hinweis: Das ist eine rein RECHNERISCHE Klassifikation (Backtracking-
    Solver, darf raten). Ob ein Mensch die Loesung auch tatsaechlich ohne
    Raten herleiten kann, prueft zusaetzlich is_logically_solvable() bzw.
    evaluate_puzzle() weiter unten.
    """
    sudoku_only_count = count_solutions(grid, symbol_ids, limit=2)
    if sudoku_only_count == 1:
        return "sudoku_only"

    with_goals_count = count_solutions_with_goals(grid, symbol_ids, goals, limit=2)
    if with_goals_count == 1:
        return "goals_required"

    return "unsolvable"


def evaluate_puzzle(grid, symbol_ids, goals):
    """
    Umfassende Bewertung eines Puzzles (Vorgabe-Grid + Ziele), die sowohl die
    rechnerische Klassifikation als auch die tatsaechliche, menschliche
    Loesbarkeit (ohne Raten) beruecksichtigt.

    Rueckgabe: dict mit
      classification         -> wie classify_puzzle() (s.o.)
      logically_solvable_without_goals -> True, wenn Naked/Hidden Single ALLEIN
                                 (ohne Ziel-Deduktion) zur Loesung fuehren
      logically_solvable_with_goals    -> True, wenn Naked/Hidden Single +
                                 Ziel-Deduktion zur Loesung fuehren
      requires_goal_logic     -> True, wenn die Ziel-Deduktion tatsaechlich
                                 gebraucht wird, um ohne Raten zur Loesung zu
                                 kommen (d.h. logically_solvable_with_goals
                                 True ist, aber ...without_goals False)
      playable                -> True, wenn das Raetsel ueberhaupt sinnvoll
                                 spielbar ist: rechnerisch eindeutig loesbar
                                 UND durch reine Logik (mit oder ohne Ziele)
                                 ohne Raten loesbar
    """
    classification = classify_puzzle(grid, symbol_ids, goals)

    logically_without = is_logically_solvable(grid, symbol_ids, goals=None)
    logically_with = is_logically_solvable(grid, symbol_ids, goals=goals)

    playable = classification in ("sudoku_only", "goals_required") and logically_with

    return {
        "classification": classification,
        "logically_solvable_without_goals": logically_without,
        "logically_solvable_with_goals": logically_with,
        "requires_goal_logic": logically_with and not logically_without,
        "playable": playable,
    }


def find_goals_required_puzzle(
    symbol_ids, goals_template, num_givens=12,
    max_solution_tries=300, max_given_tries=4000, rng=None,
    require_logical_solvability=True
):
    """
    Sucht gezielt nach einem Level, das als "goals_required" klassifiziert,
    d.h. bei dem die Ziele wirklich gebraucht werden, um die Vorgaben zu
    einer eindeutigen Loesung aufzuloesen (Sudoku-Regeln allein reichen
    NICHT).

    Wenn require_logical_solvability=True (Standard), wird zusaetzlich
    verlangt, dass das Raetsel auch tatsaechlich OHNE Raten loesbar ist
    (Naked Single, Hidden Single, Ziel-Deduktion) - nicht nur rechnerisch
    eindeutig. Das ist der Unterschied zwischen "es gibt nur eine Loesung"
    und "ein Mensch kann diese Loesung auch herleiten". Bevorzugt werden
    dabei Faelle, in denen die Ziel-Deduktion tatsaechlich der entscheidende
    Schritt ist (requires_goal_logic), das ist aber keine harte Vorgabe -
    falls das Grid schon durch Naked/Hidden Single allein durchgehend loesbar
    ist, ist es ebenfalls gueltig (playable), auch wenn die Ziele dann "nur"
    ein zusaetzlicher Fakt sind.

    goals_template: Liste von Ketten OHNE target_count, z.B. [['wald','saegewerk']],
    oder mit vorgegebenem target_count (dann wird nur nach Loesungen gesucht,
    die genau diese Anzahl erreichen). Wenn target_count fehlt/None, wird die
    tatsaechliche Anzahl in der gefundenen Loesung als Ziel uebernommen.

    Rueckgabe: dict mit solution, givens, goals (mit ausgefuellten
    target_count), evaluation (das volle evaluate_puzzle()-Ergebnis) - oder
    None, falls in den Versuchslimits nichts gefunden wurde.
    """
    import random
    rng = rng or random

    best_fallback = None  # falls kein "goals_required + logisch loesbar"-Fall gefunden wird,
                           # merken wir uns den besten "goals_required" Fall (auch wenn er
                           # Raten braucht) als Fallback, um nicht komplett leer auszugehen

    for _ in range(max_solution_tries):
        solution = solve_full_random(symbol_ids, rng=rng)
        if solution is None:
            continue

        resolved_goals = []
        for g in goals_template:
            chain = g["chain"] if isinstance(g, dict) else g
            wanted = g.get("target_count") if isinstance(g, dict) else None
            cnt, _ = chain_count(solution, chain)
            if wanted is not None and cnt != wanted:
                break
            resolved_goals.append({"chain": chain, "target_count": cnt})
        else:
            # alle Ziele mit passendem count gefunden (oder count uebernommen)
            for _ in range(max_given_tries):
                givens = []
                for br in range(0, N, REGION_ROWS):
                    for bc in range(0, N, REGION_COLS):
                        cells = [
                            (r, c)
                            for r in range(br, br + REGION_ROWS)
                            for c in range(bc, bc + REGION_COLS)
                        ]
                        k = min(len(cells), max(1, num_givens // ((N // REGION_ROWS) * (N // REGION_COLS))))
                        givens.extend(rng.sample(cells, k))

                puzzle = empty_grid()
                for (r, c) in givens:
                    puzzle[r][c] = solution[r][c]

                classification = classify_puzzle(puzzle, symbol_ids, resolved_goals)
                if classification != "goals_required":
                    continue

                if not require_logical_solvability:
                    return {
                        "solution": solution,
                        "givens": sorted(givens),
                        "goals": resolved_goals,
                        "evaluation": None,
                    }

                evaluation = evaluate_puzzle(puzzle, symbol_ids, resolved_goals)

                if evaluation["requires_goal_logic"]:
                    # Idealfall: Ziel-Deduktion ist tatsaechlich der entscheidende
                    # Schritt - sofort zurueckgeben.
                    return {
                        "solution": solution,
                        "givens": sorted(givens),
                        "goals": resolved_goals,
                        "evaluation": evaluation,
                    }

                if evaluation["playable"] and best_fallback is None:
                    # Immerhin: rechnerisch goals_required UND ohne Raten loesbar,
                    # auch wenn die Ziel-Deduktion technisch nicht der entscheidende
                    # Schritt war (z.B. weil Naked/Hidden Single schon reichen).
                    # Als Fallback merken, aber weitersuchen fuer den Idealfall.
                    best_fallback = {
                        "solution": solution,
                        "givens": sorted(givens),
                        "goals": resolved_goals,
                        "evaluation": evaluation,
                    }
            # bei dieser Loesung keine passenden Givens gefunden -> naechste Loesung probieren

    return best_fallback


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
# is_logically_solvable() simuliert stattdessen einen Menschen, der nur
# folgende Techniken anwendet, bis entweder das Grid voll ist oder keine
# Technik mehr greift:
#   1. Naked Single   - eine Zelle hat nur noch genau einen moeglichen Wert
#   2. Hidden Single   - ein Wert passt in einer Zeile/Spalte/Region nur noch
#                        in eine einzige Zelle (auch wenn diese Zelle selbst
#                        noch mehrere Kandidaten haette)
#   3. Ziel-Deduktion  - wenn ein Nachbarschafts-Ziel (Kette) schon so weit
#                        eingeschraenkt ist, dass eine bestimmte Zelle in
#                        JEDER verbleibenden gueltigen Zielerfuellung densel-
#                        ben Wert haben muss, wird dieser Wert uebernommen
#
# Kein Raten/Backtracking - wenn keine dieser Techniken mehr greift, bevor
# das Grid voll ist, gilt das Raetsel als NICHT durch reine Logik loesbar,
# selbst wenn es rechnerisch eindeutig waere.

def _candidates_grid(grid, symbol_ids):
    """Fuer jede leere Zelle: Menge der noch moeglichen Werte, basierend auf
    Zeilen-, Spalten- und Regionsregeln."""
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
            cands[(r, c)] = set(symbol_ids) - used
    return cands


def _apply_naked_singles(grid, symbol_ids):
    """Sucht Zellen mit genau einem Kandidaten. Setzt den ERSTEN gefundenen
    und gibt True zurueck, falls etwas gesetzt wurde."""
    cands = _candidates_grid(grid, symbol_ids)
    for (r, c), options in cands.items():
        if len(options) == 1:
            grid[r][c] = next(iter(options))
            return True
        if len(options) == 0:
            # Widerspruch - diese Zelle hat gar keinen gueltigen Kandidaten mehr
            return "contradiction"
    return False


def _apply_hidden_singles(grid, symbol_ids):
    """Sucht Werte, die in einer Zeile/Spalte/Region nur noch in eine
    einzige Zelle passen. Setzt den ERSTEN gefundenen Fall."""
    cands = _candidates_grid(grid, symbol_ids)

    def try_unit(cells):
        for v in symbol_ids:
            spots = [cell for cell in cells if cell in cands and v in cands[cell]]
            if len(spots) == 1:
                r, c = spots[0]
                if grid[r][c] is None:
                    grid[r][c] = v
                    return True
        return False

    for r in range(N):
        if try_unit([(r, c) for c in range(N)]):
            return True
    for c in range(N):
        if try_unit([(r, c) for r in range(N)]):
            return True
    for br in range(0, N, REGION_ROWS):
        for bc in range(0, N, REGION_COLS):
            cells = [(rr, cc) for rr in range(br, br + REGION_ROWS) for cc in range(bc, bc + REGION_COLS)]
            if try_unit(cells):
                return True

    return False


def _apply_goal_deduction(grid, symbol_ids, goals, max_empty_cells=8, max_completions_to_check=3000):
    """
    Ziel-Deduktion: Prueft, ob unter allen noch moeglichen Vervollstaendigungen
    der LEEREN Zellen (unter Beachtung der normalen Sudoku-Regeln) JEDE davon,
    die zusaetzlich alle Ziele erfuellt, eine bestimmte Zelle auf denselben
    Wert festlegt - waehrend das ohne die Ziel-Bedingung nicht der Fall waere.
    Falls ja, wird dieser Wert uebernommen.

    WICHTIG - zwei Korrekturen gegenueber einer natzeitentischen Volltext-
    Aufzaehlung:

    1. max_empty_cells begrenzt diese Technik bewusst auf Situationen mit
       WENIGEN verbleibenden leeren Zellen (Standard: 8). Das Durchprobieren
       aller Vervollstaendigungen ist nur dann eine realistische Technik fuer
       einen Menschen (vergleichbar mit "es gibt nur eine Handvoll Arten, die
       letzten paar Felder zu fuellen, schauen wir sie durch"). Bei vielen
       leeren Zellen (z.B. 19) waere das faktisch eine versteckte Brute-Force-
       Suche, die kein Mensch von Hand nachvollziehen kann - das war ein Bug
       in einer frueheren Version, der faelschlich als "logisch herleitbar"
       durchging, obwohl es praktisch Raten in großem Stil war.

    2. Wenn die Aufzaehlung der Vervollstaendigungen durch max_completions_to_check
       abgeschnitten wird (mehr Vervollstaendigungen existieren, als geprueft
       wurden), wird KEINE Deduktion zurueckgegeben, selbst wenn die gepruefte
       Teilmenge zufaellig einheitlich aussieht. Alles andere waere unsauber:
       eine abgeschnittene Stichprobe kann eine Uebereinstimmung vortaeuschen,
       die bei vollstaendiger Aufzaehlung gar nicht bestehen wuerde.
    """
    empty_cells = [(r, c) for r in range(N) for c in range(N) if grid[r][c] is None]
    if not empty_cells or not goals:
        return False
    if len(empty_cells) > max_empty_cells:
        return False

    cands = _candidates_grid(grid, symbol_ids)

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

    if truncated[0]:
        # Aufzaehlung war nicht vollstaendig - keine verlaessliche Aussage moeglich.
        return False

    if not completions:
        return False

    valid_completions = [comp for comp in completions if _completion_satisfies_goals(grid, comp, goals)]

    if not valid_completions:
        return False

    # Suche eine Zelle, die in ALLEN gueltigen (zielerfuellenden)
    # Vervollstaendigungen denselben Wert hat, aber nicht in allen rein
    # Sudoku-gueltigen Vervollstaendigungen (sonst waere es keine echte
    # Ziel-Deduktion, sondern bereits durch Naked/Hidden Single abgedeckt).
    for cell in empty_cells:
        goal_values = set(comp[cell] for comp in valid_completions)
        if len(goal_values) == 1:
            all_values = set(comp[cell] for comp in completions)
            if len(all_values) > 1:
                r, c = cell
                grid[r][c] = next(iter(goal_values))
                return True

    return False


def _completion_satisfies_goals(grid, completion, goals):
    """Prueft, ob eine gegebene Vervollstaendigung (dict cell->value) der
    leeren Zellen zusammen mit dem aktuellen Grid alle Ziele erfuellt."""
    temp = [row[:] for row in grid]
    for (r, c), v in completion.items():
        temp[r][c] = v
    return goals_satisfied(temp, goals)


def is_logically_solvable(grid, symbol_ids, goals=None, max_steps=500):
    """
    Simuliert einen Menschen, der NUR folgende Techniken einsetzt (kein
    Raten/Backtracking): Naked Single, Hidden Single, Ziel-Deduktion.

    Gibt True zurueck, wenn das Grid dadurch bis zur vollstaendigen, gueltigen
    Loesung gebracht werden kann. Gibt False zurueck, wenn irgendwann keine
    Technik mehr greift, obwohl das Grid noch nicht voll ist (das Raetsel
    waere dann nur durch Raten/Ausprobieren loesbar), oder falls ein
    Widerspruch auftritt.

    goals: optionale Liste von {chain, target_count} - falls gegeben, wird
    Ziel-Deduktion als dritte Technik einbezogen (das ist der Kern, warum
    Ziele bei Hofgefluester tatsaechlich beim Loesen helfen koennen). Diese
    Technik greift bewusst nur im "Endspiel" (wenige leere Zellen uebrig,
    siehe _apply_goal_deduction) - bei vielen leeren Zellen waere ein
    vollstaendiges Durchprobieren aller Vervollstaendigungen fuer einen
    Menschen nicht praktikabel und wuerde faelschlich als "Logik" durchgehen,
    obwohl es faktisch verstecktes Raten waere.
    """
    if len(symbol_ids) != N:
        raise ValueError(f"Es werden genau {N} Symbole benoetigt, {len(symbol_ids)} gegeben.")

    g = [row[:] for row in grid]
    goals = goals or []

    for _ in range(max_steps):
        if is_full(g):
            return not all_conflicts(g)

        progress = _apply_naked_singles(g, symbol_ids)
        if progress == "contradiction":
            return False
        if progress:
            continue

        if _apply_hidden_singles(g, symbol_ids):
            continue

        if goals and _apply_goal_deduction(g, symbol_ids, goals):
            continue

        # keine Technik greift mehr - nur durch Raten fortsetzbar
        return False

    return is_full(g) and not all_conflicts(g)


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
    (muss Laenge N haben). Gibt das fertige Grid oder None zurueck."""
    import random
    if len(symbol_ids) != N:
        raise ValueError(f"Es werden genau {N} Symbole benoetigt, {len(symbol_ids)} gegeben.")
    rng = rng or random
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
