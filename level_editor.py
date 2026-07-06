#!/usr/bin/env python3
"""
level_editor.py

Grafischer Level-Editor fuer "Hofgefluester".

Neu in dieser Version:
 - Beliebig viele Ziele pro Level (nicht nur eines)
 - Ziele koennen Produktionsketten beliebiger Laenge sein (A->B->C->D->...),
   wobei jedes Kettenglied irgendwo orthogonal an das vorherige angrenzen muss
   (kein gerader Pfad noetig, kann sich schlaengeln)
 - Eigene Symbol-Typen koennen hinzugefuegt/entfernt werden (Name + Farbe +
   2-stelliges Kuerzel), zusaetzlich zu den 6 Standard-Symbolen
 - Symbole werden als farbige Rechtecke mit Kuerzel-Text gezeichnet, nicht
   als Emoji - funktioniert unabhaengig von Schriftart/Emoji-Unterstuetzung

Workflow:
 1. Symbole verwalten (Standard nutzen oder eigene hinzufuegen).
 2. Grid mit Symbolen fuellen (Zelle anklicken, Symbol aus Palette waehlen).
 3. Beliebig viele Ziele anlegen: je eine Kette aus 2+ Symbolen + Zielanzahl.
 4. Festlegen, welche Zellen als Vorgaben (givens) sichtbar sein sollen.
 5. "Level pruefen": Sudoku-Gueltigkeit, Eindeutigkeit der Loesung bei den
    gewaehlten Vorgaben, und ob ALLE Ziele in der Loesung erfuellt sind.
 6. Level als JSON-Datei in den levels/-Ordner exportieren.

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


class LevelEditor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Hofgeflüster — Level-Editor")
        self.configure(bg="#3a2c1e")
        self.resizable(False, False)

        # Symbol-Verwaltung: Liste von dicts {id, name, color, abbr}
        self.symbols = [dict(s) for s in sc.DEFAULT_SYMBOLS]

        self.grid_data = sc.empty_grid()
        self.given_cells = set()
        self.selected_cell = None
        self.selected_symbol_id = self.symbols[0]["id"]

        # Ziele: Liste von dicts {chain: [sym_id, sym_id, ...], target_count: int}
        self.goals = []

        os.makedirs(DEFAULT_LEVELS_DIR, exist_ok=True)

        self._build_layout()
        self._redraw_grid()
        self._redraw_palette()
        self._redraw_goal_list()

    # ------------------------------------------------------------------ UI

    def _build_layout(self):
        outer = tk.Frame(self, bg="#3a2c1e", padx=16, pady=16)
        outer.pack()

        title = tk.Label(
            outer, text="Hofgeflüster — Level-Editor",
            font=("Georgia", 18, "bold"), fg="#f2e6c9", bg="#3a2c1e"
        )
        title.grid(row=0, column=0, columnspan=2, pady=(0, 12), sticky="w")

        # linke Seite: Grid + Symbolpalette
        left = tk.Frame(outer, bg="#3a2c1e")
        left.grid(row=1, column=0, sticky="n")

        self.canvas = tk.Canvas(
            left, width=CELL_PX * sc.N, height=CELL_PX * sc.N,
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

        tk.Label(right, text="Aktionen", font=("Georgia", 14, "bold"),
                 fg="#d4a949", bg="#4a3320").pack(anchor="w", pady=(0, 8))

        actions = [
            ("🎲 Zufällige Lösung erzeugen", self._generate_random_solution),
            ("🎯 Level generieren (nur mit Zielen lösbar)", self._generate_goals_required_level),
            ("🧹 Grid leeren", self._clear_grid),
            ("🔍 Level prüfen", self._check_level),
            ("💾 Level exportieren...", self._export_level),
            ("📂 Level laden...", self._load_level),
        ]
        for label, cmd in actions:
            tk.Button(right, text=label, font=("Segoe UI", 11), width=28, anchor="w", command=cmd).pack(
                anchor="w", pady=3
            )

        tk.Label(right, text="Status", font=("Georgia", 14, "bold"),
                 fg="#d4a949", bg="#4a3320").pack(anchor="w", pady=(16, 8))

        self.status_text = tk.Text(
            right, width=38, height=12, wrap="word", font=("Segoe UI", 9),
            bg="#3a2c1e", fg="#e4d3a8", relief="flat", padx=8, pady=8
        )
        self.status_text.pack(anchor="w")
        self._log("Willkommen! Verwalte Symbole, fülle das Grid, lege Ziele fest und prüfe dein Level.")

    # ------------------------------------------------------------- helpers

    def _log(self, msg):
        self.status_text.insert("end", msg + "\n\n")
        self.status_text.see("end")

    def symbol_by_id(self, sid):
        for s in self.symbols:
            if s["id"] == sid:
                return s
        return None

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

    def _update_symbol_highlight(self):
        for sid, btn in self.symbol_buttons.items():
            btn.configure(highlightbackground=("#ffffff" if sid == self.selected_symbol_id else "#c9b98a"),
                          highlightthickness=(3 if sid == self.selected_symbol_id else 1))

    def _select_symbol(self, sym_id):
        self.selected_symbol_id = sym_id
        self._update_symbol_highlight()
        self._place_selected(sym_id)

    def _place_selected(self, sym_id):
        if self.selected_cell is None:
            return
        r, c = self.selected_cell
        if sym_id is not None and (r, c) in self.given_cells and self.grid_data[r][c] is None:
            pass
        self.grid_data[r][c] = sym_id
        self._redraw_grid()

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
        # ID-Kollisionen vermeiden
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
        warn = []
        if used_in_grid:
            warn.append("Es befinden sich noch Zellen mit diesem Symbol im Grid (werden geleert).")
        if used_in_goals:
            warn.append("Es gibt noch Ziele, die dieses Symbol verwenden (werden entfernt).")
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
        if self.selected_symbol_id == sid:
            self.selected_symbol_id = self.symbols[0]["id"]

        self._redraw_palette()
        self._redraw_grid()
        self._redraw_goal_list()
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
        c = event.x // CELL_PX
        r = event.y // CELL_PX
        if 0 <= r < sc.N and 0 <= c < sc.N:
            self.selected_cell = (r, c)
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
            # Vorab pruefen, ob die bestehenden Zellen ueberhaupt in sich
            # widerspruchsfrei sind - sonst kann drumherum gar nichts geloest werden.
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

        solution = sc.solve_full_random(self._current_symbol_ids(), grid=base_grid)

        if solution is None:
            self._log(
                "❌ Um die bestehenden Zellen herum konnte keine gültige Lösung gefunden werden. "
                "Die vorgegebenen Zellen lassen sich nicht zu einem vollständigen, gültigen "
                "Sudoku ergänzen (z.B. weil eine Zeile/Spalte/Region schon zu eingeschränkt ist)."
            )
            messagebox.showwarning(
                "Keine Lösung gefunden",
                "Um die bestehenden Zellen herum ließ sich keine gültige Komplettlösung finden.\n"
                "Entferne ein paar der gesetzten Zellen und versuche es erneut."
            )
            return

        self.grid_data = solution
        self.selected_cell = None
        self._redraw_grid()
        if keep_existing:
            self._log(
                "Bestehende Zellen, Vorgaben und Ziele wurden beibehalten - das restliche "
                "Grid wurde passend dazu mit einer gültigen Lösung aufgefüllt."
            )
        else:
            self._log("Zufällige, gültige Komplettlösung erzeugt. Wähle jetzt Zellen als Vorgaben aus.")

    def _generate_goals_required_level(self):
        """
        Erzeugt gezielt ein Level, bei dem die Sudoku-Regeln ALLEIN nicht
        ausreichen, um die Vorgaben eindeutig zu loesen - erst zusammen mit
        den definierten Zielen wird die Loesung eindeutig. Das ist ein
        staerkerer Anspruch als der normale Uniqueness-Check.
        """
        if len(self.symbols) != sc.N:
            messagebox.showwarning(
                "Falsche Symbolanzahl",
                f"Es sind aktuell {len(self.symbols)} Symbole definiert, benötigt werden aber "
                f"genau {sc.N}."
            )
            return
        if not self.goals:
            messagebox.showwarning(
                "Keine Ziele definiert",
                "Lege zuerst mindestens ein Ziel an (➕ Neues Ziel hinzufügen). "
                "Ohne Ziele kann kein 'nur durch Ziele lösbares' Level erzeugt werden."
            )
            return
        if not messagebox.askyesno(
            "Grid & Vorgaben ersetzen?",
            "Dies erzeugt eine komplett neue Lösung und neue Vorgaben passend zu "
            "deinen aktuellen Zielen (Symbole der Kette bleiben, Zielanzahl wird ggf. "
            "neu bestimmt). Das aktuelle Grid und die Vorgaben werden ersetzt. Fortfahren?"
        ):
            return

        self._log("🎯 Suche ein Level, das NUR durch die Ziele eindeutig lösbar ist... (kann einige Sekunden dauern)")
        self.update_idletasks()

        goals_template = [{"chain": g["chain"], "target_count": None} for g in self.goals]
        result = sc.find_goals_required_puzzle(
            self._current_symbol_ids(),
            goals_template,
            num_givens=12,
            max_solution_tries=300,
            max_given_tries=4000,
        )

        if result is None:
            self._log(
                "❌ Kein passendes Level gefunden (in den Versuchslimits). "
                "Versuch es nochmal (Zufall) oder mit anderen/weniger Zielen."
            )
            messagebox.showwarning(
                "Nicht gefunden",
                "Es konnte kein Level gefunden werden, das nur durch die Ziele eindeutig "
                "lösbar ist. Versuch es nochmal oder ändere die Ziele (z.B. andere Ketten "
                "oder weniger gleichzeitige Ziele - das ist rechnerisch aufwändiger)."
            )
            return

        self.grid_data = result["solution"]
        self.given_cells = set(result["givens"])
        # target_count wurde ggf. neu bestimmt (passend zur gefundenen Loesung)
        self.goals = result["goals"]
        self.selected_cell = None
        self._redraw_grid()
        self._redraw_goal_list()

        goal_strs = [
            f"{' → '.join(self.symbol_by_id(s)['name'] if self.symbol_by_id(s) else s for s in g['chain'])} "
            f"({g['target_count']}x)"
            for g in self.goals
        ]

        evaluation = result.get("evaluation")
        if evaluation and evaluation.get("requires_goal_logic"):
            solvability_note = (
                "✅ Zusätzlich bestätigt: Ein Mensch MUSS die Ziele mitdenken, um ohne "
                "Raten auf die Lösung zu kommen (ohne die Ziele bliebe an einer Stelle "
                "nur Ausprobieren übrig)."
            )
        elif evaluation and evaluation.get("playable"):
            solvability_note = (
                "ℹ️ Die Lösung ist ohne Raten herleitbar, allerdings reichen dabei schon "
                "Naked/Hidden Single aus - die Ziel-Deduktion war für die Herleitung nicht "
                "zwingend nötig, obwohl die Ziele rechnerisch zur Eindeutigkeit beitragen."
            )
        else:
            solvability_note = (
                "⚠️ Hinweis: Es konnte kein Level gefunden werden, das zusätzlich ohne "
                "Raten lösbar ist - dieses Level ist nur rechnerisch eindeutig. Prüfe es "
                "über '🔍 Level prüfen' und generiere ggf. erneut."
            )

        self._log(
            "✅ Level gefunden! Die Sudoku-Regeln ALLEIN reichen rechnerisch NICHT aus, um die "
            "Vorgaben eindeutig zu lösen - erst zusammen mit diesen Zielen wird die "
            "Lösung eindeutig:\n" + "\n".join(f"- {s}" for s in goal_strs) + "\n\n" + solvability_note
        )

    # -------------------------------------------------------------- drawing

    def _redraw_grid(self):
        self.canvas.delete("all")
        conflicts = sc.all_conflicts(self.grid_data)

        for r in range(sc.N):
            for c in range(sc.N):
                x0, y0 = c * CELL_PX, r * CELL_PX
                x1, y1 = x0 + CELL_PX, y0 + CELL_PX

                val = self.grid_data[r][c]
                sym = self.symbol_by_id(val) if val else None
                fill = sym["color"] if sym else EMPTY_BG

                self.canvas.create_rectangle(x0 + 2, y0 + 2, x1 - 2, y1 - 2, fill=fill, outline="")

                if sym:
                    text_color = "white"
                    self.canvas.create_text(
                        x0 + CELL_PX / 2, y0 + CELL_PX / 2,
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

        for c in range(0, sc.N + 1, sc.REGION_COLS):
            self.canvas.create_line(c * CELL_PX, 0, c * CELL_PX, sc.N * CELL_PX, width=3, fill=GRID_LINE)
        for r in range(0, sc.N + 1, sc.REGION_ROWS):
            self.canvas.create_line(0, r * CELL_PX, sc.N * CELL_PX, r * CELL_PX, width=3, fill=GRID_LINE)

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

        if not self.goals:
            problems.append("Es ist noch kein Ziel definiert (mindestens eines wird benötigt).")

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

        evaluation = None
        if not problems:
            puzzle = self._build_puzzle_from_givens()
            evaluation = sc.evaluate_puzzle(puzzle, self._current_symbol_ids(), self.goals)
            if evaluation["classification"] == "unsolvable":
                problems.append(
                    "Die markierten Vorgaben erzwingen KEINE eindeutige Lösung "
                    "(auch nicht zusammen mit den Zielen). Markiere mehr Zellen als Vorgabe."
                )
            elif not evaluation["logically_solvable_with_goals"]:
                problems.append(
                    "Die Lösung ist zwar rechnerisch eindeutig, aber NICHT ohne Raten "
                    "herleitbar (auch nicht mit Hilfe der Ziele). Ein Mensch müsste an "
                    "irgendeiner Stelle raten/ausprobieren, um weiterzukommen. Markiere "
                    "mehr oder andere Zellen als Vorgabe, damit die Lösung durch reine "
                    "Logik (Naked/Hidden Single, Ziel-Deduktion) erreichbar wird."
                )

        ok = len(problems) == 0
        if ok:
            if evaluation["requires_goal_logic"]:
                solvability_line = (
                    "🎯 Die Ziel-Deduktion wird tatsächlich gebraucht: ohne die Ziele "
                    "würde ein Mensch an einer Stelle raten müssen, mit den Zielen ist "
                    "die Lösung vollständig durch Logik herleitbar!"
                )
            elif evaluation["classification"] == "goals_required":
                solvability_line = (
                    "🎯 Die Sudoku-Regeln ALLEIN reichen rechnerisch nicht für eine "
                    "eindeutige Lösung - die Ziele sind nötig, auch wenn die konkrete "
                    "Herleitung hier schon durch Naked/Hidden Single gelingt."
                )
            else:
                solvability_line = (
                    "ℹ️ Die Sudoku-Regeln ALLEIN ergeben bereits eine eindeutige und "
                    "durch Logik herleitbare Lösung - die Ziele sind nur ein zusätzlicher "
                    "Fakt, aber zum Lösen nicht nötig. Nutze "
                    "'🎯 Level generieren (nur mit Zielen lösbar)', wenn du willst, dass "
                    "die Ziele wirklich gebraucht werden."
                )
            report = (
                f"✅ Level ist gültig!\n"
                f"- Sudoku-Regeln erfüllt\n"
                f"- {len(self.given_cells)} Vorgabe-Zellen erzwingen eine eindeutige Lösung\n"
                f"- Lösung ist ohne Raten herleitbar (Naked/Hidden Single"
                f"{' + Ziel-Deduktion' if evaluation['requires_goal_logic'] else ''})\n"
                f"- {solvability_line}\n"
                f"- Alle {len(self.goals)} Ziel(e) erfüllt:\n" + "\n".join(goal_reports)
            )
        else:
            report = "❌ Level noch nicht spielbar:\n" + "\n".join(f"- {p}" for p in problems)

        if not silent:
            self._log(report)
            if ok:
                messagebox.showinfo("Level geprüft", "Level ist gültig, eindeutig und ohne Raten lösbar!")
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

        loaded_symbols = data.get("symbols", [dict(s) for s in sc.DEFAULT_SYMBOLS])
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
        self.selected_cell = None
        self.selected_symbol_id = self.symbols[0]["id"]

        self._redraw_palette()
        self._redraw_grid()
        self._redraw_goal_list()
        self._log(f"📂 Level geladen: {path}")


def main():
    app = LevelEditor()
    app.mainloop()


if __name__ == "__main__":
    main()
