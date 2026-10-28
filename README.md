# Kanban-Board im Terminal

Ein Kanban-Board für die Kommandozeile, mit Terminal-Look im Stil von Alien: Isolation.
Karten liegen in drei Spalten (Todo, In Arbeit, Fertig) und werden gespeichert.

## Voraussetzungen

- Python 3.9 oder neuer
- Windows empfohlen (Signaltöne funktionieren nur unter Windows)

## Starten

- Im Ordner des Programms: `py kanban.py` (Windows) oder `python3 kanban.py` (Mac/Linux)
- Unter Windows mit `kb.bat`: Im Ordner `kb` eingeben. Damit `kb` in jedem Ordner funktioniert, muss der Ordner im PATH stehen.

Beim Start läuft eine kurze Boot-Sequenz. Danach siehst du das Board.

## Befehle

| Befehl | Funktion |
|---|---|
| `s` | Board anzeigen |
| `f <text>` | Karten nach Text durchsuchen (ohne Text: alle anzeigen) |
| `a` | Karte anlegen: Spalte, Titel, Beschreibung, Fälligkeit und Priorität |
| `v` | Karte verschieben (Karten-ID und Zielspalte angeben) |
| `l` | Karte löschen |
| `u` | Letzte Aktion rückgängig machen (Anlegen, Verschieben, Löschen) |
| `b <name>` | Anderes Board öffnen, wird neu angelegt, falls es nicht existiert |
| `e` | Board als Markdown exportieren (`board_<name>.md`) |
| `t` | Farbthema wechseln (Grün, Amber, Blau) |
| `h` | Hilfe |
| `q` | Speichern und beenden |

Du kannst auch Wörter wie **Hallo**, **Danke** oder **Tschüss** schreiben. Das Programm antwortet darauf. Mit „Tschüss“ wird es beendet.

## Karten

- **Titel:** Pflichtfeld.
- **Beschreibung:** optional, wird unter der Karte angezeigt.
- **Fällig bis:** optional im Format `JJJJ-MM-TT`, zum Beispiel `2026-10-31`. Überfällige Karten, die nicht in „Fertig“ liegen, werden rot markiert.
- **Priorität:** optional 1 bis 3. Wird als `!`, `!!` oder `!!!` angezeigt.

Unter dem Board siehst du einen Fortschrittsbalken: Wie viele Karten in „Fertig“ liegen.

## Effekte

- **Glitch:** Alle 5 Sekunden verzerrt sich die Eingabezeile kurz.
- **Ladebalken:** Nach jeder Eingabe läuft ein kurzer Balken.
- **Kommentare:** Nach 45 Sekunden ohne Eingabe kommt ein Kommentar.
- **Begrüßung:** Je nach Uhrzeit (morgens, abends, Späte Schicht).
- **Signaltöne:** Bei Aktionen und Fehlern (nur Windows).

## Dateien

| Datei | Inhalt |
|---|---|
| `kanban.py` | Das Programm |
| `kanban.json` | Das Standard-Board |
| `kanban_<name>.json` | Weitere Boards, zum Beispiel `kanban_werkstatt.json` |
| `board_<name>.md` | Export als Markdown, entsteht mit `e` |
| `kb.bat` | Startdatei für Windows |

Die Daten liegen im selben Ordner wie das Programm. Sichere die `.json`-Dateien, wenn du deine Karten behalten willst.

## Fehlerbehebung

- **`Python wurde nicht gefunden`:** Python ist nicht installiert oder nicht im PATH. Installiere Python von python.org und setze den Haken bei „Add python.exe to PATH“.
- **`kb` funktioniert nicht:** Prüfe, ob `kb.bat` und `kanban.py` im selben Ordner liegen. Die Datei darf nicht `kb.bat.txt` heißen.
- **Keine Farben oder Zeichen falsch:** Nutze Windows Terminal oder eine aktuelle Eingabeaufforderung.
- **Pfeiltasten** sind nicht enthalten. Karten verschiebst du mit `v`, indem du die Karten-ID und die Zielspalte angibst.
