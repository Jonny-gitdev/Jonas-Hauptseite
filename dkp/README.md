# Doppelkopf-Poker (Browser-Version)

Reines HTML/CSS/JavaScript – kein Build-Schritt, keine Abhängigkeiten.

## Struktur
- `index.html` – Seite
- `css/style.css` – Layout & Karten
- `js/cards.js` – die 52 Doppelkarten (aus der Karten-Checkliste)
- `js/game.js` – Regel-Engine (Handbewertung, Züge, Aktionspaare, Wertung)
- `js/bots.js` – Bots (Leicht / Mittel / Schwer)
- `js/ui.js` – Oberfläche & Eingaben

## Hosting (Cloudflare Pages über GitHub)
Dateien ins Repo legen (oder in einen Unterordner deiner Seite). Bei einem eigenen Pages-Projekt:
Framework preset: None, Build command: leer, Output directory: `/`.
Lokal testen: `index.html` im Browser öffnen (funktioniert auch ohne Server).
