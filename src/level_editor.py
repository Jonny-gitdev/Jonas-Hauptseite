#!/usr/bin/env python3
"""
level_editor.py

Grafischer Level-Editor fuer "Hofgefluester".

Neu in dieser Version:
 - Negative Ziele: bestimmte Symbole duerfen im GANZEN Grid hoechstens eine
   festgelegte Anzahl mal (oder gar nicht) orthogonal nebeneinander liegen
 - Schwierigkeitsgrad waehlbar (leicht/mittel/schwer/experte) - steuert bei
   der Level-Generierung, bis zu welcher Sudoku-Technik (Naked/Hidden Single,
   Locked Candidates, Paare/Tripel, X-Wing, Ziel-Deduktion) die Loesung
   hergeleitet werden darf bzw. (bei "experte") tatsaechlich gebraucht wird
 - Story-Texte: optionaler Text, der beim OEFFNEN und beim ABSCHLIESSEN
   eines Levels auf der Website als Popup angezeigt wird
 - Beliebig viele (positive) Ziele pro Level (Produktionsketten beliebiger
   Laenge, Kettenglieder muessen orthogonal benachbart sein, duerfen sich
   schlaengeln)
 - Eigene Symbol-Typen koennen hinzugefuegt/entfernt werden (Name + Farbe +
   Kuerzel + optionales Emoji), zusaetzlich zu den 6 Standard-Symbolen

Workflow:
 1. Symbole verwalten (Standard nutzen oder eigene hinzufuegen).
 2. Grid mit Symbolen fuellen (Zelle anklicken, Symbol aus Palette waehlen)
    ODER direkt per Generator eine passende Loesung + Vorgaben erzeugen.
 3. Beliebig viele positive Ziele (Ketten) und negative Ziele (Cluster-
    Beschraenkungen) anlegen.
 4. Optional Story-Text fuer Level-Start und Level-Ende eintragen.
 5. Festlegen, welche Zellen als Vorgaben (givens) sichtbar sein sollen
    (manuell, oder automatisch durch den Generator).
 6. "Level pruefen": Sudoku-Gueltigkeit, Eindeutigkeit der Loesung bei den
    gewaehlten Vorgaben, ob ALLE Ziele erfuellt sind, und mit welcher
    Schwierigkeit/welchen Techniken es sich loesen laesst.
 7. Level als JSON-Datei in den levels/-Ordner exportieren.

Benoetigt nur die Python-Standardbibliothek (tkinter + json).
"""

import json
import os
import tkinter as tk
from tkinter import messagebox, filedialog, simpledialog, colorchooser, ttk

import sudoku_core as sc

DEFAULT_LEVELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "levels")

CELL_PX = 64
GIVEN_BORDER = "#d4a949"
SELECTED_BORDER = "#ffffff"
CONFLICT_BG = "#f3d2c9"
GRID_LINE = "#2b2118"
EMPTY_BG = "#f2e6c9"
HIGHLIGHT_SAME_SYMBOL = "#e0453a"
FULLY_PLACED_BORDER = "#e0453a"

DIFFICULTY_OPTIONS = [
    ("beginner", "Anfänger (nur Naked Single)"),
    ("easy", "Leicht (+ Hidden Single)"),
    ("medium", "Mittel (+ Locked Candidates, Paare)"),
    ("hard", "Schwer (+ Tripel, X-Wing)"),
]
DIFFICULTY_LABEL_BY_ID = dict(DIFFICULTY_OPTIONS)
DIFFICULTY_ID_BY_LABEL = {label: key for key, label in DIFFICULTY_OPTIONS}

REGION_SHAPE_OPTIONS = [
    ((2, 3), "2×3-Regionen (6×6-Feld, 6 Symbole)"),
    ((3, 3), "3×3-Regionen (9×9-Feld, 9 Symbole, klassisches Sudoku)"),
]
REGION_SHAPE_LABEL_BY_KEY = dict(REGION_SHAPE_OPTIONS)
REGION_SHAPE_KEY_BY_LABEL = {label: key for key, label in REGION_SHAPE_OPTIONS}


class LevelEditor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Hofgeflüster — Level-Editor")
        self.configure(bg="#3a2c1e")
        self.resizable(False, False)

        # Sudoku-Grunddimensionen: standardmaessig 2x3-Regionen (6x6-Feld).
        sc.configure_grid(2, 3)

        # Symbol-Verwaltung: Liste von dicts {id, name, color, abbr, icon, image}
        # - nur so viele Standard-Symbole, wie fuer die aktuelle Feldgroesse
        # gebraucht werden.
        self.symbols = [dict(s) for s in sc.DEFAULT_SYMBOLS[:sc.N]]

        self.grid_data = sc.empty_grid()
        self.given_cells = set()
        self.selected_cell = None
        self.selected_symbol_id = self.symbols[0]["id"]
        # Symbol, dessen Vorkommen im Grid gerade rot umrandet hervorgehoben
        # werden (durch Klick auf eine belegte Zelle oder ein Palette-Symbol).
        self.highlight_symbol_id = None

        # Positive Ziele: Liste von dicts {chain: [sym_id, ...], target_count: int}
        self.goals = []
        # Negative Ziele: Liste von dicts {symbols: [sym_id, ...], max_count: int}
        self.negative_goals = []

        self.difficulty_var = tk.StringVar(value="easy")
        self.require_goal_logic_var = tk.BooleanVar(value=False)
        self.region_shape_var = tk.StringVar(value=REGION_SHAPE_LABEL_BY_KEY[(2, 3)])

        os.makedirs(DEFAULT_LEVELS_DIR, exist_ok=True)

        self._build_layout()
        self._redraw_grid()
        self._redraw_palette()
        self._redraw_goal_list()
        self._redraw_negative_goal_list()

    # ------------------------------------------------------------------ UI

    def _build_layout(self):
        outer = tk.Frame(self, bg="#3a2c1e", padx=16, pady=16)
        outer.pack()

        title = tk.Label(
            outer, text="Hofgeflüster — Level-Editor",
            font=("Georgia", 18, "bold"), fg="#f2e6c9", bg="#3a2c1e"
        )
        title.grid(row=0, column=0, columnspan=2, pady=(0, 12), sticky="w")

        # linke Seite: Grid + Symbolpalette + Story
        left = tk.Frame(outer, bg="#3a2c1e")
        left.grid(row=1, column=0, sticky="n")

        self.canvas = tk.Canvas(
            left, width=self._cell_px() * sc.N, height=self._cell_px() * sc.N,
            bg=EMPTY_BG, highlightthickness=0
        )
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self._on_canvas_click)

        tk.Label(left, text="Symbol-Palette", font=("Georgia", 12, "bold"),
                 fg="#d4a949", bg="#3a2c1e").pack(anchor="w", pady=(12, 4))

        self.palette_frame = tk.Frame(left, bg="#3a2c1e")
        self.palette_frame.pack(anchor="w")

        symbol_mgmt = tk.Frame(left, bg="#3a2c1e", pady=8)
        symbol_mgmt.pack(anchor="w")
        tk.Button(symbol_mgmt, text="➕ Neues Symbol", command=self._add_symbol).grid(row=0, column=0, padx=2)
        tk.Button(symbol_mgmt, text="✏️ Symbol bearbeiten", command=self._edit_symbol).grid(row=0, column=1, padx=2)
        tk.Button(symbol_mgmt, text="🗑 Symbol löschen", command=self._delete_symbol).grid(row=0, column=2, padx=2)
        tk.Button(symbol_mgmt, text="🗑 Zelle löschen", command=lambda: self._place_selected(None)).grid(row=0, column=3, padx=2)

        tk.Button(left, text="⭐ Zelle als Vorgabe an/aus", command=self._toggle_given).pack(anchor="w", pady=(4, 0))

        # Story-Texte
        story_frame = tk.Frame(left, bg="#3a2c1e", pady=10)
        story_frame.pack(anchor="w", fill="x")
        tk.Label(story_frame, text="Story (optional)", font=("Georgia", 12, "bold"),
                 fg="#d4a949", bg="#3a2c1e").pack(anchor="w")
        tk.Label(story_frame, text="Wird als Popup gezeigt, wenn das Level geoeffnet bzw. abgeschlossen wird.",
                 font=("Segoe UI", 8), fg="#e4d3a8", bg="#3a2c1e", justify="left", wraplength=380).pack(anchor="w", pady=(0, 6))

        tk.Label(story_frame, text="Beim Öffnen anzeigen:", font=("Segoe UI", 9),
                 fg="#f2e6c9", bg="#3a2c1e").pack(anchor="w")
        self.story_intro_text = tk.Text(story_frame, width=46, height=4, wrap="word", font=("Segoe UI", 9))
        self.story_intro_text.pack(anchor="w", pady=(2, 8))

        tk.Label(story_frame, text="Beim Abschließen anzeigen:", font=("Segoe UI", 9),
                 fg="#f2e6c9", bg="#3a2c1e").pack(anchor="w")
        self.story_outro_text = tk.Text(story_frame, width=46, height=4, wrap="word", font=("Segoe UI", 9))
        self.story_outro_text.pack(anchor="w", pady=(2, 0))

        # rechte Seite: Ziele + Aktionen + Status
        right = tk.Frame(outer, bg="#4a3320", padx=16, pady=16)
        right.grid(row=1, column=1, sticky="n", padx=(16, 0))

        tk.Label(right, text="Ziele (beliebig viele)", font=("Georgia", 14, "bold"),
                 fg="#d4a949", bg="#4a3320").pack(anchor="w")
        tk.Label(right, text="Jedes Ziel ist eine Kette: Symbol A → B → (C → D → ...).\n"
                              "Kettenglieder müssen jeweils orthogonal benachbart sein\n"
                              "(dürfen sich schlängeln, keine gerade Linie nötig).",
                 font=("Segoe UI", 8), fg="#e4d3a8", bg="#4a3320", justify="left").pack(anchor="w", pady=(2, 8))

        self.goal_list_frame = tk.Frame(right, bg="#4a3320")
        self.goal_list_frame.pack(anchor="w", fill="x")

        tk.Button(right, text="➕ Neues Ziel hinzufügen", command=self._add_goal).pack(anchor="w", pady=(6, 16))

        tk.Label(right, text="Negative Ziele (beliebig viele)", font=("Georgia", 14, "bold"),
                 fg="#d4a949", bg="#4a3320").pack(anchor="w")
        tk.Label(right, text="Legt fest, dass bestimmte Symbole INSGESAMT im Grid\n"
                              "höchstens N-mal orthogonal nebeneinander liegen dürfen\n"
                              "(N=0: dürfen nie nebeneinander liegen).",
                 font=("Segoe UI", 8), fg="#e4d3a8", bg="#4a3320", justify="left").pack(anchor="w", pady=(2, 8))

        self.negative_goal_list_frame = tk.Frame(right, bg="#4a3320")
        self.negative_goal_list_frame.pack(anchor="w", fill="x")

        tk.Button(right, text="➕ Neues negatives Ziel hinzufügen", command=self._add_negative_goal).pack(
            anchor="w", pady=(6, 16)
        )

        tk.Label(right, text="Feldgröße", font=("Georgia", 14, "bold"),
                 fg="#d4a949", bg="#4a3320").pack(anchor="w", pady=(0, 4))
        region_menu = ttk.Combobox(
            right, textvariable=self.region_shape_var, state="readonly", width=44,
            values=[label for _, label in REGION_SHAPE_OPTIONS]
        )
        region_menu.pack(anchor="w", pady=(0, 4))
        region_menu.set(REGION_SHAPE_LABEL_BY_KEY[(2, 3)])
        region_menu.bind("<<ComboboxSelected>>", self._on_region_shape_changed)
        self.region_menu = region_menu
        tk.Label(right, text="Ändert die Größe des GANZEN Grids - leert Grid und Vorgaben.",
                 font=("Segoe UI", 8), fg="#e4d3a8", bg="#4a3320", justify="left").pack(anchor="w", pady=(0, 12))

        tk.Label(right, text="Schwierigkeit", font=("Georgia", 14, "bold"),
                 fg="#d4a949", bg="#4a3320").pack(anchor="w", pady=(0, 4))
        diff_menu = ttk.Combobox(
            right, textvariable=self.difficulty_var, state="readonly", width=36,
            values=[label for _, label in DIFFICULTY_OPTIONS]
        )
        diff_menu.set(DIFFICULTY_LABEL_BY_ID["easy"])
        diff_menu.pack(anchor="w", pady=(0, 8))
        self.diff_menu = diff_menu

        tk.Checkbutton(
            right, text="Nur mit Zielvorgaben lösbar (Ziel-Deduktion zwingend nötig)",
            variable=self.require_goal_logic_var, fg="#f2e6c9", bg="#4a3320",
            selectcolor="#2b2118", activebackground="#4a3320", activeforeground="#f2e6c9",
            wraplength=320, justify="left", anchor="w"
        ).pack(anchor="w", pady=(0, 12))

        tk.Label(right, text="Aktionen", font=("Georgia", 14, "bold"),
                 fg="#d4a949", bg="#4a3320").pack(anchor="w", pady=(0, 8))

        actions = [
            ("🎲 Zufällige Lösung erzeugen", self._generate_random_solution),
            ("🎯 Level generieren (gewählte Schwierigkeit)", self._generate_level_for_difficulty),
            ("🧹 Grid leeren", self._clear_grid),
            ("🔍 Level prüfen", self._check_level),
            ("💾 Level exportieren...", self._export_level),
            ("📂 Level laden...", self._load_level),
        ]
        for label, cmd in actions:
            tk.Button(right, text=label, font=("Segoe UI", 11), width=32, anchor="w", command=cmd).pack(
                anchor="w", pady=3
            )

        tk.Label(right, text="Status", font=("Georgia", 14, "bold"),
                 fg="#d4a949", bg="#4a3320").pack(anchor="w", pady=(16, 8))

        self.status_text = tk.Text(
            right, width=42, height=14, wrap="word", font=("Segoe UI", 9),
            bg="#3a2c1e", fg="#e4d3a8", relief="flat", padx=8, pady=8
        )
        self.status_text.pack(anchor="w")
        self._log("Willkommen! Verwalte Symbole, fülle das Grid, lege Ziele (positiv/negativ) "
                   "fest, wähle eine Schwierigkeit und prüfe dein Level.")

    # ------------------------------------------------------------- helpers

    def _log(self, msg):
        self.status_text.insert("end", msg + "\n\n")
        self.status_text.see("end")

    def symbol_by_id(self, sid):
        for s in self.symbols:
            if s["id"] == sid:
                return s
        return None

    def _selected_difficulty_id(self):
        return DIFFICULTY_ID_BY_LABEL.get(self.diff_menu.get(), "easy")

    def _selected_region_shape(self):
        return REGION_SHAPE_KEY_BY_LABEL.get(self.region_menu.get(), (2, 3))

    def _cell_px(self):
        # Kleinere Zellen bei groesseren Feldern (9x9), damit das Fenster
        # nicht zu riesig wird.
        return 64 if sc.N <= 6 else 48

    def _on_region_shape_changed(self, event=None):
        region_rows, region_cols = self._selected_region_shape()
        if (region_rows, region_cols) == (sc.REGION_ROWS, sc.REGION_COLS):
            return

        has_content = any(
            self.grid_data[r][c] is not None for r in range(sc.N) for c in range(sc.N)
        ) or bool(self.goals) or bool(self.negative_goals) or bool(self.given_cells)

        if has_content and not messagebox.askyesno(
            "Feldgröße ändern?",
            f"Das ändert die Größe des GANZEN Grids auf {region_rows*region_cols}x{region_rows*region_cols} "
            f"({region_rows}x{region_cols}-Regionen). Das aktuelle Grid, alle Vorgaben und Ziele "
            f"werden dabei geleert. Fortfahren?"
        ):
            # Auswahl zuruecksetzen auf die aktuell aktive Feldgroesse
            self.region_menu.set(REGION_SHAPE_LABEL_BY_KEY[(sc.REGION_ROWS, sc.REGION_COLS)])
            return

        sc.configure_grid(region_rows, region_cols)
        self.symbols = [dict(s) for s in sc.DEFAULT_SYMBOLS[:sc.N]]
        self.grid_data = sc.empty_grid()
        self.given_cells = set()
        self.goals = []
        self.negative_goals = []
        self.selected_cell = None
        self.highlight_symbol_id = None
        self.selected_symbol_id = self.symbols[0]["id"]

        self.canvas.config(width=self._cell_px() * sc.N, height=self._cell_px() * sc.N)
        self._redraw_grid()
        self._redraw_palette()
        self._redraw_goal_list()
        self._redraw_negative_goal_list()
        self._log(
            f"Feldgröße geändert: {sc.N}x{sc.N} mit {sc.REGION_ROWS}x{sc.REGION_COLS}-Regionen. "
            f"Grid, Vorgaben und Ziele wurden geleert. Es werden jetzt genau {sc.N} Symbole benötigt "
            f"(automatisch mit den Standard-Symbolen vorbelegt)."
        )

    # --------------------------------------------------------- symbol mgmt

    def _redraw_palette(self):
        for w in self.palette_frame.winfo_children():
            w.destroy()
        self.symbol_buttons = {}
        for i, sym in enumerate(self.symbols):
            btn = tk.Canvas(self.palette_frame, width=110, height=32, highlightthickness=1,
                             highlightbackground="#c9b98a", bg=sym["color"], cursor="hand2")
            btn.create_text(55, 16, text=f"{sym['abbr']} · {sym['name']}", fill="white",
                             font=("Segoe UI", 9, "bold"))
            btn.bind("<Button-1>", lambda e, s=sym["id"]: self._select_symbol(s))
            btn.grid(row=i // 2, column=i % 2, padx=3, pady=3)
            self.symbol_buttons[sym["id"]] = btn
        self._update_symbol_highlight()

    def _symbol_fully_placed(self, sym_id):
        """True, wenn `sym_id` bereits in JEDER Region des Grids mindestens
        einmal vorkommt (d.h. das Symbol hat bereits seine maximal
        moegliche Anzahl an Vorkommen erreicht und kann nirgendwo mehr
        gueltig platziert werden)."""
        for br in range(0, sc.N, sc.REGION_ROWS):
            for bc in range(0, sc.N, sc.REGION_COLS):
                present = any(
                    self.grid_data[r][c] == sym_id
                    for r in range(br, br + sc.REGION_ROWS)
                    for c in range(bc, bc + sc.REGION_COLS)
                )
                if not present:
                    return False
        return True

    def _update_symbol_highlight(self):
        for sid, btn in self.symbol_buttons.items():
            fully_placed = self._symbol_fully_placed(sid)
            if sid == self.selected_symbol_id:
                border_color, border_width = "#ffffff", 3
            elif fully_placed:
                border_color, border_width = FULLY_PLACED_BORDER, 3
            else:
                border_color, border_width = "#c9b98a", 1
            btn.configure(highlightbackground=border_color, highlightthickness=border_width)

    def _select_symbol(self, sym_id):
        self.selected_symbol_id = sym_id
        self.highlight_symbol_id = sym_id
        self._update_symbol_highlight()
        self._place_selected(sym_id)
        self._redraw_grid()

    def _place_selected(self, sym_id):
        if self.selected_cell is None:
            return
        r, c = self.selected_cell
        self.grid_data[r][c] = sym_id
        self._redraw_grid()
        self._update_symbol_highlight()

    def _add_symbol(self):
        name = simpledialog.askstring("Neues Symbol", "Name des neuen Feldtyps (z.B. 'Mühle'):", parent=self)
        if not name:
            return
        abbr = simpledialog.askstring("Kürzel", "2-3 Buchstaben-Kürzel (für die Anzeige im Editor):", parent=self,
                                       initialvalue=name[:2].upper())
        if not abbr:
            abbr = name[:2].upper()
        icon = simpledialog.askstring(
            "Emoji (optional)",
            "Emoji für die Website-Anzeige (optional, kann leer bleiben):",
            parent=self
        )
        color = colorchooser.askcolor(title="Farbe wählen")[1]
        if not color:
            color = "#666666"
        sym_id = "".join(ch for ch in name.lower() if ch.isalnum()) or f"sym{len(self.symbols)}"
        base_id = sym_id
        i = 2
        existing_ids = {s["id"] for s in self.symbols}
        while sym_id in existing_ids:
            sym_id = f"{base_id}{i}"
            i += 1

        if len(self.symbols) >= sc.N:
            messagebox.showwarning(
                "Zu viele Symbole",
                f"Bei einem {sc.N}x{sc.N}-Grid werden GENAU {sc.N} Symbole benötigt "
                f"(Sudoku-Regel: jedes Symbol einmal pro Zeile/Spalte/Region).\n"
                f"Du hast bereits {len(self.symbols)}. Entferne zuerst eines, wenn du "
                f"ein anderes hinzufügen möchtest."
            )
            return

        self.symbols.append({
            "id": sym_id, "name": name, "color": color, "abbr": abbr[:3].upper(),
            "icon": icon or None, "image": None,
        })
        self._redraw_palette()
        self._log(f"Symbol '{name}' hinzugefügt ({len(self.symbols)}/{sc.N} Symbole).")

    def _edit_symbol(self):
        sid = self.selected_symbol_id
        sym = self.symbol_by_id(sid)
        if not sym:
            return
        name = simpledialog.askstring("Symbol bearbeiten", "Name:", initialvalue=sym["name"], parent=self)
        if name:
            sym["name"] = name
        abbr = simpledialog.askstring("Symbol bearbeiten", "Kürzel:", initialvalue=sym["abbr"], parent=self)
        if abbr:
            sym["abbr"] = abbr[:3].upper()
        icon = simpledialog.askstring(
            "Symbol bearbeiten", "Emoji (optional, für Website-Anzeige):",
            initialvalue=sym.get("icon") or "", parent=self
        )
        sym["icon"] = icon or None
        color = colorchooser.askcolor(title="Farbe wählen", initialcolor=sym["color"])[1]
        if color:
            sym["color"] = color
        self._redraw_palette()
        self._redraw_grid()
        self._redraw_goal_list()
        self._redraw_negative_goal_list()

    def _delete_symbol(self):
        sid = self.selected_symbol_id
        sym = self.symbol_by_id(sid)
        if not sym:
            return
        if len(self.symbols) <= 1:
            messagebox.showwarning("Nicht möglich", "Mindestens ein Symbol muss übrig bleiben.")
            return
        used_in_grid = any(self.grid_data[r][c] == sid for r in range(sc.N) for c in range(sc.N))
        used_in_goals = any(sid in g["chain"] for g in self.goals)
        used_in_negative_goals = any(sid in ng["symbols"] for ng in self.negative_goals)
        warn = []
        if used_in_grid:
            warn.append("Es befinden sich noch Zellen mit diesem Symbol im Grid (werden geleert).")
        if used_in_goals:
            warn.append("Es gibt noch (positive) Ziele, die dieses Symbol verwenden (werden entfernt).")
        if used_in_negative_goals:
            warn.append("Es gibt noch negative Ziele, die dieses Symbol verwenden (werden entfernt).")
        msg = f"Symbol '{sym['name']}' wirklich löschen?"
        if warn:
            msg += "\n\n" + "\n".join(warn)
        if not messagebox.askyesno("Symbol löschen", msg):
            return

        self.symbols = [s for s in self.symbols if s["id"] != sid]
        for r in range(sc.N):
            for c in range(sc.N):
                if self.grid_data[r][c] == sid:
                    self.grid_data[r][c] = None
                    self.given_cells.discard((r, c))
        self.goals = [g for g in self.goals if sid not in g["chain"]]
        self.negative_goals = [ng for ng in self.negative_goals if sid not in ng["symbols"]]
        if self.selected_symbol_id == sid:
            self.selected_symbol_id = self.symbols[0]["id"]

        self._redraw_palette()
        self._redraw_grid()
        self._redraw_goal_list()
        self._redraw_negative_goal_list()
        self._log(f"Symbol '{sym['name']}' gelöscht.")

    # ------------------------------------------------------------ grid ui

    def _toggle_given(self):
        if self.selected_cell is None:
            messagebox.showinfo("Keine Zelle gewählt", "Klicke zuerst auf eine Zelle im Grid.")
            return
        r, c = self.selected_cell
        if self.grid_data[r][c] is None:
            messagebox.showinfo("Leere Zelle", "Diese Zelle hat noch kein Symbol — kann nicht als Vorgabe markiert werden.")
            return
        if (r, c) in self.given_cells:
            self.given_cells.discard((r, c))
        else:
            self.given_cells.add((r, c))
        self._redraw_grid()

    def _on_canvas_click(self, event):
        cell_px = self._cell_px()
        c = event.x // cell_px
        r = event.y // cell_px
        if 0 <= r < sc.N and 0 <= c < sc.N:
            self.selected_cell = (r, c)
            val = self.grid_data[r][c]
            self.highlight_symbol_id = val if val is not None else None
            self._redraw_grid()

    def _clear_grid(self):
        if messagebox.askyesno("Grid leeren", "Wirklich das gesamte Grid und alle Vorgaben löschen?"):
            self.grid_data = sc.empty_grid()
            self.given_cells = set()
            self.selected_cell = None
            self._redraw_grid()
            self._log("Grid geleert.")

    def _current_symbol_ids(self):
        return [s["id"] for s in self.symbols]

    def _generate_random_solution(self):
        if len(self.symbols) != sc.N:
            messagebox.showwarning(
                "Falsche Symbolanzahl",
                f"Es sind aktuell {len(self.symbols)} Symbole definiert, benötigt werden aber "
                f"genau {sc.N} für ein {sc.N}x{sc.N}-Grid. Füge Symbole hinzu oder entferne welche."
            )
            return

        has_existing_cells = any(
            self.grid_data[r][c] is not None for r in range(sc.N) for c in range(sc.N)
        )

        keep_existing = False
        if has_existing_cells:
            conflicts = sc.all_conflicts(self.grid_data)
            if conflicts:
                messagebox.showwarning(
                    "Widerspruch im Grid",
                    f"Die aktuelle Belegung verletzt bereits an {len(conflicts)} Zelle(n) die "
                    f"Sudoku-Regeln. Bitte erst die Konflikte auflösen (rot markierte Zellen), "
                    f"bevor eine Lösung drumherum erzeugt werden kann."
                )
                return

            answer = messagebox.askyesnocancel(
                "Bestehende Zellen behalten?",
                "Es sind schon Zellen und/oder Vorgaben gesetzt.\n\n"
                "Ja: bestehende Zellen (inkl. Vorgaben und Ziele) BEHALTEN und die "
                "restlichen Zellen passend dazu auffüllen.\n"
                "Nein: alles verwerfen und eine komplett neue, leere Lösung erzeugen.\n"
                "Abbrechen: nichts tun."
            )
            if answer is None:
                return
            keep_existing = answer

        if keep_existing:
            base_grid = [row[:] for row in self.grid_data]
        else:
            base_grid = sc.empty_grid()
            self.given_cells = set()

        solution = sc.generate_random_solution_with_negative_goals(
            self._current_symbol_ids(), self.negative_goals, grid=base_grid, max_tries=200
        )

        if solution is None:
            self._log(
                "❌ Um die bestehenden Zellen herum konnte keine gültige Lösung gefunden werden, "
                "die auch alle negativen Ziele erfüllt. Entweder lassen sich die vorgegebenen "
                "Zellen nicht zu einem vollständigen Sudoku ergänzen, oder die negativen Ziele "
                "sind zu streng (z.B. max_count zu niedrig für die aktuelle Symbolwahl)."
            )
            messagebox.showwarning(
                "Keine Lösung gefunden",
                "Um die bestehenden Zellen herum ließ sich keine gültige, alle negativen Ziele "
                "erfüllende Komplettlösung finden.\nEntferne ein paar der gesetzten Zellen oder "
                "lockere die negativen Ziele und versuche es erneut."
            )
            return

        self.grid_data = solution
        self.selected_cell = None
        self._redraw_grid()
        if keep_existing:
            self._log(
                "Bestehende Zellen, Vorgaben und Ziele wurden beibehalten - das restliche "
                "Grid wurde passend dazu (inkl. negativer Ziele) mit einer gültigen Lösung aufgefüllt."
            )
        else:
            self._log("Zufällige, gültige Komplettlösung erzeugt (negative Ziele beachtet). "
                       "Wähle jetzt Zellen als Vorgaben aus.")

    def _generate_level_for_difficulty(self):
        """
        Erzeugt ein komplett neues Level (Lösung + Vorgaben), das zur
        gewählten Schwierigkeit UND zur Checkbox "Nur mit Zielvorgaben
        lösbar" passt. Die Symbole der bereits definierten (positiven)
        Ziel-Ketten und alle negativen Ziele bleiben erhalten, die konkrete
        Zielanzahl (target_count der positiven Ziele) wird ggf. neu anhand
        der gefundenen Lösung bestimmt.
        """
        if len(self.symbols) != sc.N:
            messagebox.showwarning(
                "Falsche Symbolanzahl",
                f"Es sind aktuell {len(self.symbols)} Symbole definiert, benötigt werden aber genau {sc.N}."
            )
            return

        difficulty = self._selected_difficulty_id()
        require_goal_logic = self.require_goal_logic_var.get()
        if require_goal_logic and not self.goals:
            messagebox.showwarning(
                "Keine Ziele definiert",
                "Für 'Nur mit Zielvorgaben lösbar' muss mindestens ein (positives) Ziel definiert "
                "sein, das dann tatsächlich zum Lösen gebraucht wird (➕ Neues Ziel hinzufügen)."
            )
            return

        if not messagebox.askyesno(
            "Grid & Vorgaben ersetzen?",
            f"Dies erzeugt eine komplett neue Lösung und neue Vorgaben passend zur Schwierigkeit "
            f"'{self.diff_menu.get()}'"
            + (" (Ziel-Deduktion zwingend nötig)" if require_goal_logic else "")
            + f" (Ketten-Symbole und negative Ziele bleiben, Zielanzahlen werden ggf. neu bestimmt). "
              f"Das aktuelle Grid und die Vorgaben werden ersetzt. Fortfahren?"
        ):
            return

        self._log(
            f"🎯 Suche ein {sc.N}x{sc.N}-Level mit Schwierigkeit '{self.diff_menu.get()}'"
            + (", Ziel-Deduktion zwingend nötig" if require_goal_logic else "")
            + ("... (kann einige Sekunden dauern)" if sc.N <= 6 else
               "... (bei 9x9 kann das je nach Zufall zwischen ca. 10 Sekunden und "
               "gut 1-2 Minuten dauern - bitte etwas Geduld; das Fenster reagiert "
               "in der Zeit nicht)")
        )
        self.update_idletasks()

        # Bei einem 9x9-Feld ist jeder einzelne Eindeutigkeits-/Logik-Check
        # deutlich teurer als bei 6x6 - die Versuchsanzahl wird daher
        # reduziert, damit die Suche interaktiv nutzbar bleibt (auf Kosten
        # von etwas weniger optimalen/wenigeren Vorgaben-Kandidaten).
        if sc.N <= 6:
            max_solution_tries, max_removal_attempts = 25, 3
        else:
            # Ein 9x9-Feld ist bei jedem Eindeutigkeits-/Logik-Check deutlich
            # teurer als 6x6 (auch mit Constraint-Propagation) - die Laufzeit
            # kann hier stark schwanken (von wenigen Sekunden bis über eine
            # Minute), daher bewusst niedrige Versuchsanzahl.
            max_solution_tries, max_removal_attempts = 2, 1

        goals_template = [{"chain": g["chain"], "target_count": None} for g in self.goals]
        result = sc.generate_level(
            self._current_symbol_ids(),
            goals_template=goals_template,
            negative_goals=self.negative_goals,
            difficulty=difficulty,
            require_goal_logic=require_goal_logic,
            max_solution_tries=max_solution_tries,
            max_removal_attempts=max_removal_attempts,
        )

        if result is None:
            self._log(
                "❌ Kein passendes Level gefunden (in den Versuchslimits). Versuch es nochmal "
                "(Zufall) oder mit anderen Zielen/negativen Zielen/einer anderen Schwierigkeit "
                "bzw. der Checkbox."
            )
            messagebox.showwarning(
                "Nicht gefunden",
                "Es konnte kein Level gefunden werden, das zur gewählten Schwierigkeit (und Checkbox) "
                "passt. Versuch es nochmal oder ändere die Ziele bzw. die Schwierigkeit."
            )
            return

        self.grid_data = result["solution"]
        self.given_cells = set(result["givens"])
        self.goals = result["goals"]
        self.negative_goals = result["negative_goals"]
        self.selected_cell = None
        self.highlight_symbol_id = None
        self._redraw_grid()
        self._redraw_goal_list()
        self._redraw_negative_goal_list()

        evaluation = result["evaluation"]
        goal_strs = [
            f"{' → '.join(self.symbol_by_id(s)['name'] if self.symbol_by_id(s) else s for s in g['chain'])} "
            f"({g['target_count']}x)"
            for g in self.goals
        ]
        neg_strs = [
            f"{', '.join(self.symbol_by_id(s)['name'] if self.symbol_by_id(s) else s for s in ng['symbols'])} "
            f"(max. {ng['max_count']}x nebeneinander)"
            for ng in self.negative_goals
        ]

        requested_id = self._selected_difficulty_id()
        actual_id = DIFFICULTY_TIERS_REVERSE.get(evaluation["difficulty"], evaluation["difficulty"])
        note = ""
        if actual_id != requested_id:
            note = (
                f"\n\nℹ️ Hinweis: Die tatsächlich erreichte Schwierigkeit ist '{evaluation['difficulty']}' "
                f"(angefragt war '{DIFFICULTY_LABEL_BY_ID[requested_id]}'). Bei einem {sc.N}x{sc.N}-Feld sind "
                f"fortgeschrittene Techniken manchmal schlicht nicht zwingend nötig - das ist dann "
                f"bereits das schwerstmögliche Level mit den aktuellen Zielen."
            )
        if require_goal_logic and not evaluation["requires_goal_logic"]:
            note += (
                "\n\n⚠️ Hinweis: Ziel-Deduktion wird in diesem Level entgegen der Anfrage NICHT "
                "zwingend gebraucht (sollte bei erfolgreicher Suche eigentlich nicht vorkommen - "
                "bitte Level trotzdem prüfen)."
            )

        self._log(
            f"✅ Level gefunden! {len(self.given_cells)} Vorgaben, tatsächliche Schwierigkeit: "
            f"'{evaluation['difficulty']}'"
            + (", Ziel-Deduktion nötig" if evaluation["requires_goal_logic"] else "")
            + f" (Techniken: {', '.join(evaluation['techniques_used']) or '—'}).\n"
            + ("Positive Ziele:\n" + "\n".join(f"- {s}" for s in goal_strs) + "\n" if goal_strs else "")
            + ("Negative Ziele:\n" + "\n".join(f"- {s}" for s in neg_strs) if neg_strs else "")
            + note
        )

    # -------------------------------------------------------------- drawing

    def _redraw_grid(self):
        self.canvas.delete("all")
        conflicts = sc.all_conflicts(self.grid_data)
        cell_px = self._cell_px()

        for r in range(sc.N):
            for c in range(sc.N):
                x0, y0 = c * cell_px, r * cell_px
                x1, y1 = x0 + cell_px, y0 + cell_px

                val = self.grid_data[r][c]
                sym = self.symbol_by_id(val) if val else None
                fill = sym["color"] if sym else EMPTY_BG

                self.canvas.create_rectangle(x0 + 2, y0 + 2, x1 - 2, y1 - 2, fill=fill, outline="")

                if sym:
                    text_color = "white"
                    self.canvas.create_text(
                        x0 + cell_px / 2, y0 + cell_px / 2,
                        text=sym["abbr"], font=("Segoe UI", 15, "bold"), fill=text_color
                    )

                border_color = "#c9b98a"
                border_width = 1
                if self.selected_cell == (r, c):
                    border_color, border_width = SELECTED_BORDER, 3
                elif (r, c) in conflicts:
                    self.canvas.create_rectangle(x0 + 2, y0 + 2, x1 - 2, y1 - 2, outline=CONFLICT_BG, width=3)
                elif (r, c) in self.given_cells:
                    border_color, border_width = GIVEN_BORDER, 3

                self.canvas.create_rectangle(x0, y0, x1, y1, outline=border_color, width=border_width)

                if (r, c) in self.given_cells:
                    self.canvas.create_text(x1 - 8, y0 + 8, text="★", font=("Segoe UI", 9), fill="#d4a949", anchor="ne")

                # Alle Zellen mit dem gerade hervorgehobenen Symbol bekommen
                # zusaetzlich einen roten Rahmen (Klick auf eine belegte
                # Zelle oder ein Palette-Symbol setzt die Hervorhebung).
                if self.highlight_symbol_id is not None and val == self.highlight_symbol_id:
                    self.canvas.create_rectangle(
                        x0 + 3, y0 + 3, x1 - 3, y1 - 3, outline=HIGHLIGHT_SAME_SYMBOL, width=3
                    )

        for c in range(0, sc.N + 1, sc.REGION_COLS):
            self.canvas.create_line(c * cell_px, 0, c * cell_px, sc.N * cell_px, width=3, fill=GRID_LINE)
        for r in range(0, sc.N + 1, sc.REGION_ROWS):
            self.canvas.create_line(0, r * cell_px, sc.N * cell_px, r * cell_px, width=3, fill=GRID_LINE)

    # ------------------------------------------------------------ goal ui

    def _redraw_goal_list(self):
        for w in self.goal_list_frame.winfo_children():
            w.destroy()

        if not self.goals:
            tk.Label(self.goal_list_frame, text="(noch keine Ziele definiert)",
                     font=("Segoe UI", 9, "italic"), fg="#e4d3a8", bg="#4a3320").pack(anchor="w")
            return

        for idx, goal in enumerate(self.goals):
            row = tk.Frame(self.goal_list_frame, bg="#3a2c1e", padx=6, pady=4)
            row.pack(anchor="w", fill="x", pady=2)

            chain_labels = []
            for sid in goal["chain"]:
                sym = self.symbol_by_id(sid)
                chain_labels.append(sym["abbr"] if sym else sid)
            chain_str = " → ".join(chain_labels)

            tk.Label(row, text=f"{chain_str}   (Ziel: {goal['target_count']}x)",
                     font=("Segoe UI", 9), fg="#f2e6c9", bg="#3a2c1e").pack(side="left")
            tk.Button(row, text="✏️", command=lambda i=idx: self._edit_goal(i), width=2).pack(side="left", padx=(6, 2))
            tk.Button(row, text="🗑", command=lambda i=idx: self._delete_goal(i), width=2).pack(side="left")

    def _add_goal(self):
        self._goal_editor_dialog()

    def _edit_goal(self, idx):
        self._goal_editor_dialog(existing_index=idx)

    def _delete_goal(self, idx):
        del self.goals[idx]
        self._redraw_goal_list()

    def _goal_editor_dialog(self, existing_index=None):
        dialog = tk.Toplevel(self)
        dialog.title("Ziel bearbeiten" if existing_index is not None else "Neues Ziel")
        dialog.configure(bg="#4a3320", padx=16, pady=16)
        dialog.grab_set()

        tk.Label(dialog, text="Kette (Reihenfolge der Symbole):", fg="#f2e6c9", bg="#4a3320",
                 font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Label(dialog, text="Jedes Glied muss im Grid orthogonal an das vorherige angrenzen.",
                 fg="#e4d3a8", bg="#4a3320", font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 8))

        chain_frame = tk.Frame(dialog, bg="#4a3320")
        chain_frame.pack(anchor="w", fill="x", pady=(0, 8))

        current_chain = []
        if existing_index is not None:
            current_chain = list(self.goals[existing_index]["chain"])
        else:
            current_chain = [self.symbols[0]["id"], self.symbols[1]["id"] if len(self.symbols) > 1 else self.symbols[0]["id"]]

        chain_vars = []

        def render_chain_editor():
            for w in chain_frame.winfo_children():
                w.destroy()
            chain_vars.clear()
            for i, sid in enumerate(current_chain):
                var = tk.StringVar(value=sid)
                chain_vars.append(var)
                om = tk.OptionMenu(chain_frame, var, *self._current_symbol_ids())
                om.grid(row=0, column=i * 2, padx=2)
                if len(current_chain) > 2:
                    tk.Button(chain_frame, text="✕", width=2,
                              command=lambda idx=i: remove_link(idx)).grid(row=0, column=i * 2 + 1)
                if i < len(current_chain) - 1:
                    tk.Label(chain_frame, text="→", fg="#f2e6c9", bg="#4a3320").grid(row=1, column=i * 2)

        def add_link():
            for i, var in enumerate(chain_vars):
                current_chain[i] = var.get()
            current_chain.append(self.symbols[0]["id"])
            render_chain_editor()

        def remove_link(idx):
            for i, var in enumerate(chain_vars):
                current_chain[i] = var.get()
            del current_chain[idx]
            render_chain_editor()

        render_chain_editor()

        tk.Button(dialog, text="➕ Kettenglied hinzufügen", command=add_link).pack(anchor="w", pady=(4, 12))

        count_frame = tk.Frame(dialog, bg="#4a3320")
        count_frame.pack(anchor="w", pady=(0, 12))
        tk.Label(count_frame, text="Zielanzahl im gesamten Grid:", fg="#f2e6c9", bg="#4a3320").grid(row=0, column=0)
        target_var = tk.IntVar(value=self.goals[existing_index]["target_count"] if existing_index is not None else 2)
        tk.Spinbox(count_frame, from_=1, to=20, textvariable=target_var, width=5).grid(row=0, column=1, padx=6)

        def save():
            for i, var in enumerate(chain_vars):
                current_chain[i] = var.get()
            if len(current_chain) < 2:
                messagebox.showwarning("Zu kurz", "Eine Kette braucht mindestens 2 Glieder.", parent=dialog)
                return
            goal = {"chain": list(current_chain), "target_count": target_var.get()}
            if existing_index is not None:
                self.goals[existing_index] = goal
            else:
                self.goals.append(goal)
            self._redraw_goal_list()
            dialog.destroy()

        btn_frame = tk.Frame(dialog, bg="#4a3320")
        btn_frame.pack(anchor="e")
        tk.Button(btn_frame, text="Abbrechen", command=dialog.destroy).pack(side="left", padx=4)
        tk.Button(btn_frame, text="Speichern", command=save).pack(side="left")

    # ------------------------------------------------------ negative goal ui

    def _redraw_negative_goal_list(self):
        for w in self.negative_goal_list_frame.winfo_children():
            w.destroy()

        if not self.negative_goals:
            tk.Label(self.negative_goal_list_frame, text="(noch keine negativen Ziele definiert)",
                     font=("Segoe UI", 9, "italic"), fg="#e4d3a8", bg="#4a3320").pack(anchor="w")
            return

        for idx, ng in enumerate(self.negative_goals):
            row = tk.Frame(self.negative_goal_list_frame, bg="#3a2c1e", padx=6, pady=4)
            row.pack(anchor="w", fill="x", pady=2)

            labels = []
            for sid in ng["symbols"]:
                sym = self.symbol_by_id(sid)
                labels.append(sym["abbr"] if sym else sid)
            syms_str = " + ".join(labels)

            tk.Label(row, text=f"{syms_str}   (max. {ng['max_count']}x nebeneinander)",
                     font=("Segoe UI", 9), fg="#f2e6c9", bg="#3a2c1e").pack(side="left")
            tk.Button(row, text="✏️", command=lambda i=idx: self._edit_negative_goal(i), width=2).pack(side="left", padx=(6, 2))
            tk.Button(row, text="🗑", command=lambda i=idx: self._delete_negative_goal(i), width=2).pack(side="left")

    def _add_negative_goal(self):
        self._negative_goal_editor_dialog()

    def _edit_negative_goal(self, idx):
        self._negative_goal_editor_dialog(existing_index=idx)

    def _delete_negative_goal(self, idx):
        del self.negative_goals[idx]
        self._redraw_negative_goal_list()

    def _negative_goal_editor_dialog(self, existing_index=None):
        dialog = tk.Toplevel(self)
        dialog.title("Negatives Ziel bearbeiten" if existing_index is not None else "Neues negatives Ziel")
        dialog.configure(bg="#4a3320", padx=16, pady=16)
        dialog.grab_set()

        tk.Label(dialog, text="Symbole (mind. 1), die eingeschränkt werden sollen:", fg="#f2e6c9", bg="#4a3320",
                 font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Label(dialog, text="Jede orthogonale Nachbarschaft zwischen zwei Zellen, die BEIDE ein Symbol\n"
                              "aus dieser Auswahl enthalten (auch zweimal dasselbe Symbol), zählt mit.",
                 fg="#e4d3a8", bg="#4a3320", font=("Segoe UI", 8), justify="left").pack(anchor="w", pady=(0, 8))

        existing_symbols = set(self.negative_goals[existing_index]["symbols"]) if existing_index is not None else set()

        check_frame = tk.Frame(dialog, bg="#4a3320")
        check_frame.pack(anchor="w", pady=(0, 12))
        check_vars = {}
        for i, sym in enumerate(self.symbols):
            var = tk.BooleanVar(value=sym["id"] in existing_symbols)
            check_vars[sym["id"]] = var
            tk.Checkbutton(
                check_frame, text=f"{sym['abbr']} · {sym['name']}", variable=var,
                fg="#f2e6c9", bg="#4a3320", selectcolor="#2b2118", activebackground="#4a3320",
                activeforeground="#f2e6c9", anchor="w"
            ).grid(row=i // 2, column=i % 2, sticky="w", padx=4, pady=2)

        count_frame = tk.Frame(dialog, bg="#4a3320")
        count_frame.pack(anchor="w", pady=(0, 12))
        tk.Label(count_frame, text="Maximal erlaubte Nachbarschaften im gesamten Grid:",
                 fg="#f2e6c9", bg="#4a3320").grid(row=0, column=0)
        max_var = tk.IntVar(value=self.negative_goals[existing_index]["max_count"] if existing_index is not None else 0)
        tk.Spinbox(count_frame, from_=0, to=30, textvariable=max_var, width=5).grid(row=0, column=1, padx=6)
        tk.Label(dialog, text="(0 = die gewählten Symbole dürfen NIE nebeneinander liegen)",
                 fg="#e4d3a8", bg="#4a3320", font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 12))

        def save():
            chosen = [sid for sid, var in check_vars.items() if var.get()]
            if not chosen:
                messagebox.showwarning("Keine Symbole gewählt", "Wähle mindestens ein Symbol aus.", parent=dialog)
                return
            ng = {"symbols": chosen, "max_count": max_var.get()}
            if existing_index is not None:
                self.negative_goals[existing_index] = ng
            else:
                self.negative_goals.append(ng)
            self._redraw_negative_goal_list()
            dialog.destroy()

        btn_frame = tk.Frame(dialog, bg="#4a3320")
        btn_frame.pack(anchor="e")
        tk.Button(btn_frame, text="Abbrechen", command=dialog.destroy).pack(side="left", padx=4)
        tk.Button(btn_frame, text="Speichern", command=save).pack(side="left")

    # ------------------------------------------------------------ checking

    def _build_puzzle_from_givens(self):
        puzzle = sc.empty_grid()
        for (r, c) in self.given_cells:
            puzzle[r][c] = self.grid_data[r][c]
        return puzzle

    def _check_level(self, silent=False):
        problems = []

        if len(self.symbols) != sc.N:
            problems.append(
                f"Es sind {len(self.symbols)} Symbole definiert, benötigt werden aber genau {sc.N}."
            )

        if not sc.is_full(self.grid_data):
            problems.append("Das Grid ist noch nicht vollständig gefüllt — die Lösung muss komplett sein.")

        conflicts = sc.all_conflicts(self.grid_data)
        if conflicts:
            problems.append(f"Die aktuelle Belegung verletzt die Sudoku-Regeln in {len(conflicts)} Zelle(n).")

        if not self.given_cells:
            problems.append("Es sind keine Vorgabe-Zellen markiert.")

        if not self.goals and not self.negative_goals:
            problems.append("Es ist noch kein Ziel definiert (mindestens ein positives oder negatives Ziel wird benötigt).")

        goal_reports = []
        if sc.is_full(self.grid_data) and not conflicts and not problems:
            for goal in self.goals:
                cnt, _ = sc.chain_count(self.grid_data, goal["chain"])
                chain_str = " → ".join(
                    (self.symbol_by_id(sid)["name"] if self.symbol_by_id(sid) else sid) for sid in goal["chain"]
                )
                if cnt != goal["target_count"]:
                    problems.append(
                        f"Ziel '{chain_str}' nicht erfüllt: gefunden {cnt}x, Ziel war {goal['target_count']}x."
                    )
                goal_reports.append(f"- {chain_str}: {cnt}x (Ziel: {goal['target_count']}x)")

            for ng in self.negative_goals:
                cnt = sc.count_negative_adjacency(self.grid_data, ng["symbols"])
                names = ", ".join(
                    (self.symbol_by_id(sid)["name"] if self.symbol_by_id(sid) else sid) for sid in ng["symbols"]
                )
                if cnt > ng["max_count"]:
                    problems.append(
                        f"Negatives Ziel '{names}' verletzt: {cnt}x nebeneinander, erlaubt max. {ng['max_count']}x."
                    )
                goal_reports.append(f"- (negativ) {names}: {cnt}x nebeneinander (max. erlaubt: {ng['max_count']}x)")

        evaluation = None
        if not problems:
            puzzle = self._build_puzzle_from_givens()
            evaluation = sc.evaluate_puzzle(puzzle, self._current_symbol_ids(), self.goals, self.negative_goals)
            if evaluation["classification"] == "unsolvable":
                problems.append(
                    "Die markierten Vorgaben erzwingen KEINE eindeutige Lösung, die alle Ziele "
                    "erfüllt (auch nicht zusammen mit den Zielen). Markiere mehr Zellen als Vorgabe."
                )
            elif not evaluation["logically_solvable_with_goals"]:
                problems.append(
                    "Die Lösung ist zwar rechnerisch eindeutig, aber NICHT ohne Raten "
                    "herleitbar (auch nicht mit Hilfe der Ziele). Ein Mensch müsste an "
                    "irgendeiner Stelle raten/ausprobieren, um weiterzukommen. Markiere "
                    "mehr oder andere Zellen als Vorgabe, damit die Lösung durch reine "
                    "Logik erreichbar wird."
                )

        ok = len(problems) == 0
        if ok:
            if evaluation["requires_goal_logic"]:
                solvability_line = (
                    "🎯 Die Ziel-Deduktion wird tatsächlich gebraucht: ohne die (positiven) Ziele "
                    "würde ein Mensch an einer Stelle raten müssen, mit den Zielen ist "
                    "die Lösung vollständig durch Logik herleitbar!"
                )
            elif evaluation["classification"] == "goals_required":
                solvability_line = (
                    "🎯 Die Sudoku-Regeln ALLEIN reichen rechnerisch nicht für eine "
                    "eindeutige Lösung - die Ziele sind nötig, auch wenn die konkrete "
                    "Herleitung hier schon durch einfachere Techniken gelingt."
                )
            else:
                solvability_line = (
                    "ℹ️ Die Sudoku-Regeln ALLEIN ergeben bereits eine eindeutige und "
                    "durch Logik herleitbare Lösung - die Ziele sind nur ein zusätzlicher "
                    "Fakt, aber zum Lösen nicht nötig."
                )
            report = (
                f"✅ Level ist gültig!\n"
                f"- Sudoku-Regeln erfüllt\n"
                f"- {len(self.given_cells)} Vorgabe-Zellen erzwingen eine eindeutige Lösung\n"
                f"- Schwierigkeit: {evaluation['difficulty']} "
                f"(Techniken: {', '.join(evaluation['techniques_used']) or '—'})\n"
                f"- {solvability_line}\n"
                f"- Ziele:\n" + "\n".join(goal_reports)
            )
        else:
            report = "❌ Level noch nicht spielbar:\n" + "\n".join(f"- {p}" for p in problems)

        if not silent:
            self._log(report)
            if ok:
                messagebox.showinfo("Level geprüft", f"Level ist gültig, eindeutig und ohne Raten lösbar!\nSchwierigkeit: {evaluation['difficulty']}")
            else:
                messagebox.showwarning("Level noch nicht gültig", "Siehe Status-Log für Details.")

        return ok, report

    # ------------------------------------------------------------ export/import

    def _export_level(self):
        ok, report = self._check_level(silent=True)
        self._log(report)
        if not ok:
            if not messagebox.askyesno(
                "Trotzdem exportieren?",
                "Das Level besteht die Prüfung noch nicht (siehe Status-Log).\n"
                "Willst du es trotzdem exportieren?"
            ):
                return

        name = simpledialog.askstring("Level-Name", "Interner Name/ID für dieses Level (z.B. 'level_02'):")
        if not name:
            return
        title = simpledialog.askstring("Anzeige-Titel", "Titel, der im Spiel angezeigt wird:", initialvalue=name)
        if title is None:
            title = name

        safe_name = "".join(ch for ch in name if ch.isalnum() or ch in ("_", "-")).strip() or "level"

        path = filedialog.asksaveasfilename(
            initialdir=DEFAULT_LEVELS_DIR,
            initialfile=f"{safe_name}.json",
            defaultextension=".json",
            filetypes=[("Level-Datei (JSON)", "*.json")]
        )
        if not path:
            return

        story_intro = self.story_intro_text.get("1.0", "end").strip()
        story_outro = self.story_outro_text.get("1.0", "end").strip()

        puzzle = self._build_puzzle_from_givens()
        evaluation = sc.evaluate_puzzle(puzzle, self._current_symbol_ids(), self.goals, self.negative_goals) if ok else None

        data = {
            "id": safe_name,
            "title": title,
            "size": sc.N,
            "region_rows": sc.REGION_ROWS,
            "region_cols": sc.REGION_COLS,
            "symbols": self.symbols,
            "solution": self.grid_data,
            "givens": sorted([list(rc) for rc in self.given_cells]),
            "goals": self.goals,
            "negative_goals": self.negative_goals,
            "story_intro": story_intro or None,
            "story_outro": story_outro or None,
            "difficulty": self._selected_difficulty_id(),
            "requires_goal_logic": evaluation["requires_goal_logic"] if evaluation else self.require_goal_logic_var.get(),
            "verified_unique": ok,
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        self._log(f"💾 Level gespeichert unter: {path}")
        messagebox.showinfo("Exportiert", f"Level wurde gespeichert:\n{path}")

    def _load_level(self):
        path = filedialog.askopenfilename(
            initialdir=DEFAULT_LEVELS_DIR,
            filetypes=[("Level-Datei (JSON)", "*.json")]
        )
        if not path:
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        region_rows = data.get("region_rows", 2)
        region_cols = data.get("region_cols", 3)
        sc.configure_grid(region_rows, region_cols)
        self.region_menu.set(
            REGION_SHAPE_LABEL_BY_KEY.get((region_rows, region_cols), REGION_SHAPE_LABEL_BY_KEY[(2, 3)])
        )
        self.canvas.config(width=self._cell_px() * sc.N, height=self._cell_px() * sc.N)

        loaded_symbols = data.get("symbols", [dict(s) for s in sc.DEFAULT_SYMBOLS[:sc.N]])
        for s in loaded_symbols:
            s.setdefault("icon", None)
            s.setdefault("image", None)
        self.symbols = loaded_symbols
        self.grid_data = data["solution"]
        self.given_cells = set(tuple(rc) for rc in data["givens"])
        self.goals = data.get("goals", [])
        if not self.goals and "goal" in data:
            # Abwaertskompatibilitaet zu altem Einzel-Ziel-Format
            g = data["goal"]
            self.goals = [{"chain": [g["symbol_a"], g["symbol_b"]], "target_count": g["target_count"]}]
        self.negative_goals = data.get("negative_goals", [])
        self.selected_cell = None
        self.highlight_symbol_id = None
        self.selected_symbol_id = self.symbols[0]["id"]

        self.story_intro_text.delete("1.0", "end")
        self.story_intro_text.insert("1.0", data.get("story_intro") or "")
        self.story_outro_text.delete("1.0", "end")
        self.story_outro_text.insert("1.0", data.get("story_outro") or "")

        loaded_difficulty = data.get("difficulty", "easy")
        self.diff_menu.set(DIFFICULTY_LABEL_BY_ID.get(loaded_difficulty, DIFFICULTY_LABEL_BY_ID["easy"]))
        self.require_goal_logic_var.set(bool(data.get("requires_goal_logic", False)))

        self._redraw_palette()
        self._redraw_grid()
        self._redraw_goal_list()
        self._redraw_negative_goal_list()
        self._log(f"📂 Level geladen: {path}")


# Umgekehrtes Mapping (Schwierigkeitslabel wie von evaluate_puzzle(), z.B.
# 'schwer' -> Schwierigkeits-ID wie im Auswahlmenue, z.B. 'hard'), nur fuer
# die informative Hinweis-Meldung nach der Generierung.
_label_to_tier = {label: tier for tier, label in sc.DIFFICULTY_LABELS.items()}
_tier_to_id = {tier: diff_id for diff_id, tier in sc.DIFFICULTY_TIERS.items()}
DIFFICULTY_TIERS_REVERSE = {label: _tier_to_id[tier] for label, tier in _label_to_tier.items()}


def main():
    app = LevelEditor()
    app.mainloop()


if __name__ == "__main__":
    main()
