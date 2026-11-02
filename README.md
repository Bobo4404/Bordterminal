# Bordterminal

Ein spielerisches Produktivitäts-Tool für das Terminal im Retro-Stil eines Raumschiff-Bordcomputers (inspiriert von MU/TH/UR aus „Alien“).
Statt vieler einzelner Apps laufen Aufgaben, Notizen, Termine und Finanzen an einem Ort zusammen, mit Befehlen, Dialogen und kleinen Effekten, die die Arbeit am Rechner etwas lebendiger machen.

## Funktionen

- **Kanban-Board:** Aufgaben anlegen, verschieben, durchsuchen und löschen, mit Fälligkeitsdatum, Priorität, Undo und mehreren Boards
- **Notizen:** Notizen schreiben, anzeigen und durchsuchen
- **Kalender:** Termine verwalten, Tagesübersicht und Erinnerungen an anstehende Fristen
- **Wiederkehrende Aufgaben:** Regeln für Aufgaben, die sich wiederholen
- **Finanzen:** Einnahmen, Ausgaben und Fixkosten erfassen, Sparziele verfolgen
- **Einkaufsliste**
- **Berichte und Export:** Statusberichte („Sitrep“) und Export als Markdown
- **Atmosphäre:** Farbthemen, ASCII-Art, Dialoge, Soundeffekte und Kommentare bei Leerlauf

## Technik

- Python 3.9 oder neuer, nur Standardbibliothek (keine zusätzlichen Pakete nötig)
- Datenspeicherung in JSON-Dateien im Ordner `daten/`
- Läuft unter Windows, Linux und macOS (Soundeffekte nur unter Windows)

## Starten

Windows:

```
py bordterminal.py
```

Linux / macOS:

```
python3 bordterminal.py
```

Mit `h` wird die Hilfe angezeigt, mit `q` wird gespeichert und beendet.

## Über das Projekt

Bordterminal ist mein erstes größeres eigenes Projekt, entstanden neben meiner Umschulung zum Fachinformatiker für Anwendungsentwicklung. Dabei habe ich vor allem Programmstruktur, Datenhaltung mit JSON, Benutzereingaben im Terminal und plattformübergreifende Entwicklung geübt.
