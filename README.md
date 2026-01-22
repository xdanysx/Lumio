# Lumio (PySide6) – Lernkarten/Free-Text Trainer

Lumio ist eine kleine Desktop-App (Python + PySide6) zum Lernen mit **Free-Text Fragen**.  
Du wählst **mehrere Decks** aus, beantwortest täglich eine automatisch berechnete Anzahl an Fragen und bekommst direktes Feedback anhand einer Rubrik (Keyword-Gruppen). Fortschritt wird lokal gespeichert.

---

## Features

- **Multi-Deck Auswahl** (Checkboxen): mehrere JSON-Decks gleichzeitig lernen
- **Tagespaket (“Daily Pack”)**: pro Deck wird eine **Tagesquote** berechnet (basierend auf `due_date`)
- **Mischen über Decks**: Tagespakete aus mehreren Decks werden zu einer Session kombiniert
- **Textbewertung**:
  - Mindestwortanzahl (`min_words`)
  - Rubrik-Gruppen (jede Gruppe zählt, wenn mind. ein Begriff vorkommt)
  - Bestehen, wenn `pass_ratio` und Mindestwortanzahl erfüllt sind
- **Beispielantwort** wird nach dem Check angezeigt
- **Persistenter Fortschritt**:
  - mastered / attempts / fails / points
  - gespeichert in `data/progress.json`

---

## Projektstruktur

Empfohlenes Layout:

- `decks/` enthält deine Deck-Dateien (`*.json`).
- `data/progress.json` speichert Fortschritt pro Deck + Frage.

---

## Installation

### Voraussetzungen
- Python 3.10+ (empfohlen)
- PySide6

### Setup

```bash
pip install PySide6
