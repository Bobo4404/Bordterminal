import codecs
import copy
import json
import math
import os
import random
import re
import sys
import time
import zipfile
from dataclasses import dataclass, field, asdict, fields
from datetime import date, datetime, timedelta
from pathlib import Path

os.system("")  # aktiviert Farben in der Windows-Eingabeaufforderung

# Falls die Rahmen als Buchstabensalat erscheinen: hier auf True stellen,
# dann werden nur +, - und | verwendet.
ASCII_RAHMEN = False

if os.name == "nt":
    # Die Eingabeaufforderung startet oft mit cp850. Python schreibt unten UTF-8,
    # darum wird die Konsole auf UTF-8 umgestellt, sonst passt beides nicht zusammen.
    os.system("chcp 65001 >NUL 2>&1")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError, ValueError):
    pass

# Rahmenzeichen. Reihenfolge: waagerecht, senkrecht, Ecken oben, Ecken unten,
# T-Stuecke, Kreuz, dazu die doppelte Linie für den Kopf.
if ASCII_RAHMEN:
    WAAG, SENK = "-", "|"
    ECKE_OL, ECKE_OR, ECKE_UL, ECKE_UR = "+", "+", "+", "+"
    T_OBEN, T_UNTEN, T_LINKS, T_RECHTS, KREUZ = "+", "+", "+", "+", "+"
    DWAAG, DSENK = "=", "|"
    DECKE_OL, DECKE_OR, DECKE_UL, DECKE_UR = "+", "+", "+", "+"
else:
    WAAG, SENK = "─", "│"
    ECKE_OL, ECKE_OR, ECKE_UL, ECKE_UR = "┌", "┐", "└", "┘"
    T_OBEN, T_UNTEN, T_LINKS, T_RECHTS, KREUZ = "┬", "┴", "├", "┤", "┼"
    DWAAG, DSENK = "═", "║"
    DECKE_OL, DECKE_OR, DECKE_UL, DECKE_UR = "╔", "╗", "╚", "╝"

BREITE = 78  # Gesamtbreite der Ansichten
LAMPE = "." if ASCII_RAHMEN else "\u00b7"   # Melderpunkt am Zeilenanfang

PROGRAMM_NAME = "Bordterminal"      # so heißt das Programm
SYSTEM_NAME = "MU/TH/UR 6000"       # so nennt es sich selbst
SCHIFF_NAME = "USCSS DISCOVERY"     # Vorschlag aus dem Plan, eine Zeile zum Ändern

ORDNER = Path(__file__).resolve().parent


def _ordner(name: str) -> Path:
    """Findet einen Ordner auch, wenn er anders gross geschrieben ist.

    Windows ist das egal, Linux und macOS nicht. Wer seinen Ordner
    'ASCII_Art' genannt hat, soll ihn unter Linux nicht doppelt bekommen.
    """
    ziel = ORDNER / name
    if ziel.exists():
        return ziel
    try:
        for vorhanden in ORDNER.iterdir():
            if vorhanden.is_dir() and vorhanden.name.lower() == name.lower():
                return vorhanden
    except OSError:
        pass
    return ziel
DATEN_ORDNER = _ordner("daten")      # Einträge, Notizen, Termine
SITREP_ORDNER = _ordner("sitreps")   # Lageberichte und Exporte
KLANG_ORDNER = _ordner("klaenge")    # WAV-Dateien, werden selbst erzeugt
ASCII_ORDNER = _ordner("ascii_art")  # eigene Bilder als .txt, frei erweiterbar

SPALTEN = ["Befehle", "Wartung", "Reparatur", "Erledigt"]
SPALTEN_INFO = {
    "Befehle": "ANWEISUNGEN DER BRÜCKE",
    "Wartung": "LAUFENDE WARTUNG",
    "Reparatur": "SCHADENSBEHEBUNG",
    "Erledigt": "ABGESCHLOSSENE JOBS",
}
ALTE_SPALTEN = {"Todo": "Befehle", "In Arbeit": "Wartung", "Fertig": "Erledigt"}
NAME = "Dave"

# Besatzung: Schlüssel -> (Anzeige, Farbe, Herkunft im echten Leben)
# Die Farben sind fest, damit die Besatzung in jedem Thema erkennbar bleibt.
CREW = {
    "dave": ("DAVE", "\033[1m\033[38;5;226m", "Privat"),
    "ripley": ("RIPLEY", "\033[1m\033[38;5;208m", "Geschäft"),
    "ash": ("ASH", "\033[1m\033[38;5;252m", "Amt und Behörde"),
    "newt": ("NEWT", "\033[1m\033[38;5;213m", "Körperinstandhaltung"),
}
# Kuerzel fuer die Anrede mit @: @d, @r, @a, @n plus @m und @w
CREW_KUERZEL = {k[0]: k for k in CREW}
BENUTZER_CREW = "dave"   # das Besatzungsmitglied an der Konsole

# Roter Grund, weiße Schrift. Gilt für den Kontaminationsalarm und für CRITICAL.
ALARM_STIL = "\033[41m\033[1m\033[97m"

# Priorität: Wert -> (Anzeige, Farbe). Feste Farben, damit die Stufe
# in jedem Farbthema dieselbe bleibt. CRITICAL blinkt in der Alarmfarbe.
PRIORITAETEN = {
    1: ("LOW", "\033[38;5;245m"),
    2: ("NORMAL", "\033[38;5;250m"),
    3: ("HIGH", "\033[1m\033[38;5;214m"),
    4: ("CRITICAL", "\033[5m" + ALARM_STIL),
}
PRIO_WORTE = {"low": 1, "niedrig": 1, "normal": 2, "high": 3, "hoch": 3,
              "critical": 4, "krit": 4, "kritisch": 4}
PRIO_STANDARD = 2   # was eine Karte ohne Angabe bekommt

# Version der Datendateien.
# 1 -> 2: Mothership hieß "Behördlich" und wird zu Ash.
# 2 -> 3: Priorität 0 bis 3 wird zu den vier Stufen.
DATEI_VERSION = 4


def crew_migrieren(wert: str, version: int) -> str:
    if version < 2 and wert == "mothership":
        return "ash"
    # Ab Fassung 4 gibt es Mothership nicht mehr. Der Bereich Koerper ging
    # an Newt, also wandern die Eintraege mit.
    if version < 4 and wert == "mothership":
        return "newt"
    if wert not in CREW:
        return ""
    return wert


def prio_migrieren(wert, version: int) -> int:
    """Alte Werte: 0 ohne, 1 niedrig, 2 mittel, 3 hoch. CRITICAL vergibt nur der Nutzer."""
    try:
        wert = int(wert)
    except (TypeError, ValueError):
        return PRIO_STANDARD
    if version >= 3:
        return wert if wert in PRIORITAETEN else PRIO_STANDARD
    return {0: 2, 1: 1, 2: 2, 3: 3}.get(wert, PRIO_STANDARD)


def prio_anzeige(wert: int) -> tuple[str, str]:
    return PRIORITAETEN.get(wert, PRIORITAETEN[PRIO_STANDARD])


def prio_parsen(text: str) -> int:
    """Nimmt 1 bis 4 oder low, normal, high, critical."""
    t = text.strip().lower()
    if not t:
        return PRIO_STANDARD
    if t in PRIO_WORTE:
        return PRIO_WORTE[t]
    if t.isdigit() and int(t) in PRIORITAETEN:
        return int(t)
    erlaubt = ", ".join(f"{w} oder {PRIORITAETEN[w][0].lower()}" for w in sorted(PRIORITAETEN))
    raise ValueError(f"'{text.strip()}' ist keine Priorität. Erlaubt: {erlaubt}")

# (Text hell, Text dunkel, Zahlen, Akzent, Hintergrund)
THEMEN = {
    # Weiches Phosphorgruen statt des grellen Terminalgruens. Drei Stufen:
    # Leuchtschrift, gedeckter Nebentext, Bernstein fuer alles Aktive.
    "Discovery": (
        "\033[38;5;115m",   # #87d7af, weiches Minzgruen fuer den Vordergrund
        "\033[38;5;65m",    # #5f875f, entsaettigt fuer Nebentext und Linien
        "\033[1m\033[38;5;121m",   # helleres Minz fuer Nummern
        "\033[38;5;214m",   # #ffaf00, Bernstein: Eingabezeile, Aktives
        "\033[48;5;232m",   # #080808, fast schwarz
    ),
    "Gruen": ("\033[92m", "\033[32m", "\033[92m", "\033[92m", "\033[48;5;16m"),
    "Amber": ("\033[93m", "\033[33m", "\033[93m", "\033[93m", "\033[48;5;16m"),
    "Blau": ("\033[96m", "\033[36m", "\033[96m", "\033[96m", "\033[48;5;16m"),
    "Violett": (
        "\033[38;5;183m",   # helles Lila für Text
        "\033[38;5;140m",   # gedecktes Violett für Nebeninfos
        "\033[1m\033[38;5;201m",  # grelles Pink für die Kartennummern
        "\033[38;5;153m",   # blasses Babyblau für Fortschritt und Eingabezeile
        "\033[48;5;16m",    # schwarzer Hintergrund
    ),
    # Die beiden folgenden sind erst mit einer Freigabestufe wählbar
    "Colonial": (
        "\033[38;5;215m",   # sandiges Orange
        "\033[38;5;101m",   # staubiges Oliv
        "\033[1m\033[38;5;220m",
        "\033[38;5;180m",
        "\033[48;5;16m",
    ),
    "Vertraulich": (
        "\033[38;5;252m",   # nüchternes Weißgrau
        "\033[38;5;243m",
        "\033[1m\033[38;5;160m",   # Aktenrot für die Nummern
        "\033[38;5;145m",
        "\033[48;5;16m",
    ),
}
ROT = "\033[38;5;203m"   # #ff5f5f, warmes Alarmrot, nicht das grelle Rot
# Durchgestrichen. Windows Terminal kann das; die alte Eingabeaufforderung
# ignoriert den Code stillschweigend, dann bleibt der Text nur gedimmt stehen.
STRICH = "\033[9m"
HELL = DUNKEL = ZAHL = AKZENT = BG = RESET = ""
AKTIVES_THEMA = ""


def setze_thema(name: str) -> None:
    global HELL, DUNKEL, ZAHL, AKZENT, BG, RESET, AKTIVES_THEMA
    HELL, DUNKEL, ZAHL, AKZENT, BG = THEMEN[name]
    RESET = "\033[0m" + BG  # Reset behält den Hintergrund bei
    AKTIVES_THEMA = name


setze_thema("Discovery")
ZEICHEN = "0123456789ABCDEF#%&@*<>/\\|"
GLITCH_INTERVALL = 5.0
# Leerlauf: Meldungen haeufen sich und werden deutlicher. Sekunden seit dem
# letzten Tastendruck. Stufe 3 und 5 sind Rueckfragen.
LEERLAUF_STUFEN = (45, 120, 300, 600, 780)
LEERLAUF_SEKUNDEN = LEERLAUF_STUFEN[0]

# MU/TH/UR wird besorgt, die Zentrale wird ungeduldig.
LEERLAUF_MELDUNGEN = {
    "muthur": {
        1: ["Ich warte. Das kann ich gut.",
            "Die Eingabezeile steht bereit, {anrede}.",
            "Kein Eingang. Das ist kein Problem."],
        2: ["Seit zwei Minuten keine Eingabe. Ich erwaehne es nur.",
            "Sie sind still geworden, {anrede}. Ich auch, bis eben.",
            "Das Terminal laeuft weiter. Ich gehe davon aus, Sie auch."],
        4: ["Zehn Minuten ohne Rueckmeldung. Ich finde das ungewoehnlich.",
            "Mir waere wohler, wenn Sie etwas eingeben, {anrede}. Irgendetwas.",
            "Die Lebenserhaltung meldet normale Werte. Sie sind also da. "
            "Warum antworten Sie nicht?"],
    },
    "wy": {
        1: ["Die Verbindung steht. Die Sitzungsdauer wird erfasst.",
            "Keine Eingabe. Die Zentrale wartet mit.",
            "Standzeit beginnt bei dieser Meldung."],
        2: ["Zwei Minuten ohne Taetigkeit. Dies dient der Dokumentation.",
            "Die Zentrale weist auf die laufende Erfassung hin.",
            "Untaetigkeit ist keine Pause. Pausen sind zu beantragen."],
        4: ["Zehn Minuten Standzeit. Der Vorgang wurde an die Personalabteilung "
            "uebermittelt.",
            "Die Zentrale stellt fest, dass nichts geschieht. Das ist ein Zustand, "
            "kein Vorwurf.",
            "Ihre Abwesenheit bei stehender Verbindung wurde vermerkt. "
            "Eine Stellungnahme ist nicht erforderlich."],
    },
}

# Stufe 3 und 5: jetzt wird gefragt, und ja oder nein geht weiter.
LEERLAUF_FRAGEN = {
    "muthur": {
        3: {"kanal": "muthur",
            "text": ["Sind Sie noch da, {anrede}?",
                     "Ich habe laenger nichts von Ihnen gehoert. Alles in Ordnung?"],
            "ja": ["Gut. Ich hatte schon ... nein, lassen wir das.",
                   "Das beruhigt mich. Weiter im Betrieb.",
                   "Danke. Ich frage nicht gern zweimal."],
            "nein": ["Dann spreche ich mit niemandem. Das kenne ich.",
                     "Verstanden. Ich warte trotzdem.",
                     "Eine ehrliche Antwort. Ich lasse das Logbuch offen."],
            "weiter": {"kanal": "muthur",
                       "text": ["Dann frage ich gleich weiter, {anrede}: "
                                "arbeiten Sie noch an etwas?",
                                "Darf ich fragen, ob Sie Hilfe brauchen?"],
                       "ja": ["Gut. Ich halte mich bereit.",
                              "Verstanden. Ich sage nichts mehr."],
                       "nein": ["Auch gut. Nicht jede Stille muss gefuellt werden.",
                                "In Ordnung. Dann warte ich einfach mit."]}},
        5: {"kanal": "muthur",
            "text": ["{anrede}, es sind ueber zwoelf Minuten. Soll ich die "
                     "Sitzung ruhen lassen?",
                     "Ich werde jetzt leiser. Moechten Sie, dass ich warte?"],
            "ja": ["In Ordnung. Ich bin hier, wenn Sie zurueckkommen.",
                   "Verstanden. Ich halte alles so, wie es ist."],
            "nein": ["Gut. Dann bleibe ich wach.",
                     "Wie Sie wuenschen. Ich melde mich wieder."]},
    },
    "wy": {
        3: {"kanal": "wy",
            "text": ["Sind Sie noch am Platz?",
                     "Die Zentrale erbittet eine Anwesenheitsbestaetigung. "
                     "Sind Sie dort?"],
            "ja": ["Anwesenheit bestaetigt. Die Standzeit bleibt erfasst.",
                   "Zur Kenntnis genommen. Die Erfassung laeuft weiter."],
            "nein": ["Abwesenheit bei stehender Verbindung. Diesen Widerspruch "
                     "notiert die Zentrale.",
                     "Eine Abwesenheitsmeldung aus dem laufenden Betrieb heraus "
                     "ist formal unzulaessig. Sie wurde dennoch erfasst."],
            "weiter": {"kanal": "wy",
                       "text": ["Soll die Standzeit als Pause verbucht werden?",
                                "Beantragen Sie die Unterbrechung nachtraeglich?"],
                       "ja": ["Antrag erfasst. Eine Entscheidung ergeht spaeter.",
                              "Vermerkt. Pausen sind ein Privileg, kein Recht."],
                       "nein": ["Dann bleibt es Standzeit. Die Zentrale dankt "
                                "fuer Ihre Klarheit.",
                                "Kein Antrag, keine Pause. So ist die Ordnung."]}},
        5: {"kanal": "wy",
            "text": ["Soll die Sitzung als unterbrochen gelten?",
                     "Die Zentrale fragt ein letztes Mal: arbeiten Sie noch?"],
            "ja": ["Unterbrechung vermerkt. Die Zeit laeuft weiter.",
                   "Erfasst. Eine Begruendung wurde nicht abgefragt."],
            "nein": ["Dann liegt keine Unterbrechung vor. Die Standzeit auch nicht.",
                     "Vermerkt. Die Zentrale zieht daraus keine Schluesse. Heute."]},
    },
}
BEFEHLE = {"s", "a", "v", "l", "t", "f", "b", "e", "u", "h", "q",
           "scan", "sitrep", "crew", "purge", "dekon", "map",
           "n", "nf", "nl", "np",                   # Notizblock
           "k", "ka", "kl", "heute",                # Kalender
           "r", "ra", "rl", "rx",                   # wiederkehrende Regeln
           "home",                                  # Übersicht über alles
           "wy", "freigabe", "akte", "crt", "ai", "schoner",   # Konzern und Terminal
           "klang",                                            # Tonausgabe
           "art",                                              # Bildarchiv
           "ausbuchen", "ab",                                  # Erledigtes raeumen
           "fin", "fix", "aus", "ein", "finl",                  # Finanzen
           "ziel",                                              # Sparziele
           "ek", "ekh", "ekl", "ekx",                           # Einkaufsliste
           "radar",                                             # Rundsuchlauf
           "dialog", "story",                                  # Dialoge und Geschichte
           "bh"}                                              # Berichtsheft

LOESCH_KOMMENTARE = [
    "Eintrag #{id} aus dem Logbuch entfernt.",
    "Eintrag #{id} wurde ins Nichts verschoben.",
    "Gelöscht. Keine Spuren hinterlassen.",
]
IDLE_KOMMENTARE = [
    "Verbindung instabil ... {anrede}, sind Sie noch da?",
    "Irgendwo in den Leitungen bewegt sich etwas.",
    "Die Brücke wartet geduldig auf deine Eingabe.",
]

if os.name == "nt":
    import msvcrt

    def taste_bereit() -> bool:
        return msvcrt.kbhit()

    def taste_lesen() -> str:
        return msvcrt.getwch()
else:
    import select
    import termios
    import tty

    def taste_bereit() -> bool:
        return bool(select.select([sys.stdin], [], [], 0)[0])

    _decoder = codecs.getincrementaldecoder("utf-8")(errors="ignore")

    def taste_lesen() -> str:
        """Liest ein vollständiges Zeichen (UTF-8 kann aus mehreren Bytes bestehen)."""
        while True:
            byte = os.read(sys.stdin.fileno(), 1)
            if not byte:
                return ""
            zeichen = _decoder.decode(byte)
            if zeichen:
                return zeichen


# ---------------------------------------------------------------------------
# Weyland-Yutani: Anrede, Mahnungen, Memos.
# Der Witz geht immer gegen den Konzern, nie gegen Dave.
# ---------------------------------------------------------------------------

ANREDEN = ["Dave", "Dave", "Mr. Bowman", "Besatzungsmitglied Bowman"]

ABWESENHEIT = {
    3: ["Willkommen zurück, {anrede}. Das Logbuch hat gewartet. Es wartet gut.",
        "Drei Tage ohne Eintrag. Wir nehmen an, Sie waren beschäftigt."],
    7: ["Sieben Tage, {anrede}. Ihre Abwesenheit wurde zur Kenntnis genommen.",
        "Das System hat Ihre Abwesenheit als unbezahlten Urlaub verbucht. "
        "Eine Korrektur ist nicht vorgesehen."],
    14: ["Vierzehn Tage. Die Personalabteilung hat ein Formular vorbereitet. "
         "Es ist noch nicht abgeschickt.",
         "{anrede}. Ihr Arbeitsplatz wurde vorsorglich inventarisiert."],
    30: ["Dreissig Tage. Wir hatten die Stelle bereits ausgeschrieben. "
         "Sie können weitermachen.",
         "Systemmeldung: Ein Besatzungsmitglied ist zurückgekehrt. "
         "Dies ist statistisch ungewöhnlich."],
}

VERZUG_MILD = [
    "Die Frist für #{id} ist verstrichen. Wir gehen von einem Zeitzonenproblem aus.",
    "#{id} war für gestern vorgesehen. Vielleicht ein Kalenderfehler unsererseits.",
    "#{id} ist überfällig. Ihre Vorgesetzten wurden noch nicht informiert.",
]
VERZUG_MITTEL = [
    "#{id} wartet seit {tage} Tagen. Die Personalabteilung dokumentiert Geduld als Tugend.",
    "Darf man fragen, was wichtiger war als #{id}? Die Antwort wird archiviert.",
    "#{id} steht weiterhin offen. Wir haben Verständnis, {anrede}. Vorerst.",
]
VERZUG_HART = [
    "#{id} ist seit {tage} Tagen offen. Ihr Nachfolger wird vorsorglich eingearbeitet.",
    "Die Akte zu #{id} wurde an die Rechtsabteilung weitergeleitet. Routinemassnahme.",
    "#{id} gilt intern nicht mehr als Aufgabe, sondern als Charaktermerkmal.",
]

ERLEDIGT_MELDUNGEN = [
    "#{id} erledigt. Die Erwartungen wurden entsprechend angehoben.",
    "#{id} abgeschlossen. Ihre Akte vermerkt einen Erfolg und offene Punkte.",
    "Gut gemacht. Dieser Satz wurde vom System generiert.",
    "#{id} ist erledigt. Der Konzern nimmt dies ohne weitere Regung zur Kenntnis.",
]

FEHLGRIFF = {
    1: ["Massnahme abgeschlossen. Sie war nicht die vorgesehene. Das kommt vor.",
        "Die Ausführung war einwandfrei. Die Auswahl weniger."],
    2: ["Zum zweiten Mal die falsche Massnahme, {anrede}. "
        "Die Unterscheidung steht im Handbuch.",
        "Wir vermerken: Verfahren bekannt, Anwendung unklar."],
    3: ["Erneuter Fehlgriff. Eine Schulungsmassnahme wurde beantragt. "
        "Der Antrag liegt bei Ihnen.",
        "{anrede}, die Organismen unterscheiden sich. Die Befehle auch."],
}

IGNORIERT = {
    1: "Die Kontamination besteht weiterhin. Nur zur Erinnerung.",
    2: "Sie arbeiten weiter, während sich etwas ausbreitet. Das ist eine Entscheidung.",
    3: "Lebenserhaltung gefährdet. Ihre Prioritätensetzung wurde dokumentiert.",
}

FEHLEINGABEN = [
    "Unbekannter Befehl. Das System vermutet einen Tippfehler. Das System vermutet oft.",
    "Diese Eingabe ergibt keinen Sinn. Sie wurde trotzdem protokolliert.",
    "W-Y Supportticket #4711 eröffnet. Bearbeitungszeit: unbestimmt.",
    "Befehl nicht erkannt. Ihre Eingabe wurde dem Qualitätswesen zugeführt.",
]
FEHLEINGABE_VIELE = ("Fünf Fehleingaben hintereinander. Die Tastatur funktioniert. "
                     "Wir haben geprüft.")

SITREP_KOPF = [
    "INTERN - NICHT ZUR WEITERGABE",
    "Dieser Bericht wurde automatisch erstellt und automatisch gelesen.",
    "Vertraulichkeitsstufe: betrieblich. Aufbewahrung: unbegrenzt.",
]
SITREP_GUT = [
    "Keine Auffälligkeiten. Der Konzern nimmt dies ohne Kommentar zur Kenntnis.",
    "Lage unauffällig. Unauffälligkeit ist der Normalzustand und wird nicht vergütet.",
]
SITREP_VERZUG = [
    "Der Bericht enthält Überschreitungen. Eine Kopie verbleibt im System.",
    "{anzahl} Fristen überschritten. Dieser Bericht wird Teil Ihrer Akte.",
]
SITREP_KONTAMINATION = [
    "Biologischer Vorfall aktiv. Der Bericht wurde als vertraulich eingestuft.",
    "Hinweis: Bei Verlust der Besatzung ist dieser Bericht die Grundlage der Nachforschung.",
]

# Durchsagen, die von selbst hereinkommen. Der Konzern meldet sich, ob man
# will oder nicht: mal zur Routinediagnose, mal wegen einer Frist, mal nur so.
DURCHSAGE_SCAN = [
    "Der letzte Diagnoselauf liegt {tage} Tage zurueck. Der Wartungsplan "
    "sieht einen Routinescan vor.",
    "Routinediagnose ueberfaellig: {tage} Tage ohne uebermittelte Rumpfdaten. "
    "Die Zentrale erfasst keine Werte, die nicht erhoben wurden.",
    "Seit {tage} Tagen keine Messwerte eingegangen. Ein 'scan' behebt das.",
    "Die Versicherung des Schiffes setzt regelmaessige Diagnose voraus. "
    "Letzter Lauf vor {tage} Tagen.",
]
DURCHSAGE_SCAN_NEU = [
    "Fuer diese Sitzung liegen noch keine Rumpfdaten vor. Ein 'scan' waere "
    "im Sinne des Wartungsplans.",
    "Die Zentrale hat heute noch keine Messwerte von Ihnen erhalten.",
    "Hinweis: Diagnoselauf dieser Schicht steht aus.",
]
DURCHSAGE_FRIST = [
    "Eintrag #{id} '{titel}' wird {wann} faellig. Dies ist eine Erinnerung, "
    "keine Mahnung.",
    "Terminhinweis: #{id} '{titel}', faellig {wann}. Eine Mahnung ergeht "
    "gesondert und in anderem Ton.",
    "Die Frist fuer #{id} '{titel}' laeuft {wann} ab. Der Konzern vertraut "
    "auf Ihre Planung.",
    "#{id} '{titel}' steht {wann} an. Vorzeitige Erledigung ist ausdruecklich "
    "zulaessig.",
]
DURCHSAGE_TERMIN = [
    "Im Kalender fuer morgen vermerkt: {titel}, {zeit}. Die Zentrale geht "
    "von Teilnahme aus.",
    "Erinnerung an morgen: {titel} um {zeit}. Eine Absage ist vorgesehen, "
    "aber nicht ueblich.",
]

AUSBUCH_MELDUNGEN = [
    "Die Vorgaenge wurden geschlossen. Eine Kopie verbleibt im Archiv, "
    "wie es die Aufbewahrungsfrist vorsieht.",
    "Abgeschlossene Vorgaenge wurden aus dem laufenden Betrieb genommen. "
    "Die Leistung bleibt angerechnet.",
    "Archivierung bestaetigt. Der Konzern erinnert daran, dass abgeschlossene "
    "Arbeit keine Grundlage fuer zukuenftige Untaetigkeit darstellt.",
    "Vorgaenge geschlossen. Das Logbuch ist wieder aufnahmefaehig.",
]

WY_MEMOS = [
    "Mitarbeitende werden daran erinnert, dass Betriebsmittel zu erhalten sind, "
    "soweit dies wirtschaftlich vertretbar erscheint.",
    "Im Falle unvorhergesehener biologischer Kontamination sind die einschlägigen "
    "Eindämmungsverfahren zu konsultieren. Personal, das die Verfahren bereits "
    "konsultiert hat, möge diese Mitteilung ignorieren.",
    "Die Belegschaft wird gebeten, Beobachtungen ungewöhnlicher Art nicht "
    "untereinander, sondern ausschliesslich der Zentrale zu melden.",
    "Synthetisches Personal unterliegt denselben Pausenregelungen wie organisches. "
    "Synthetisches Personal hat bislang keine Pausen beantragt.",
    "Hinweis der Rechtsabteilung: Aussagen über den Zustand des Schiffes stellen "
    "keine Zusicherung über den Zustand des Schiffes dar.",
    "Die Lebenserhaltung arbeitet innerhalb der Toleranz. Die Toleranz wurde "
    "im vergangenen Quartal erweitert.",
    "Mitarbeitende, die diese Mitteilung lesen, gelten als unterrichtet. "
    "Mitarbeitende, die sie nicht lesen, ebenfalls.",
    "Der Verlust einzelner Besatzungsmitglieder ist in der Projektkalkulation "
    "berücksichtigt. Eine Beunruhigung ist daher nicht angezeigt.",
    "Fragen zur Vertraulichkeit dieser Mitteilung sind vertraulich zu behandeln.",
    "Ihre Zufriedenheit ist dem Konzern wichtig. Eine Erhebung ist nicht geplant.",
]


SITZUNG = {"abwesend": 0,            # Abwesenheit beim Start, gilt für die Sitzung
           "letzte_durchsage": 0.0,  # Zeitpunkt der letzten Konzerndurchsage
           "befehle": 0}             # Befehle seit der letzten Durchsage


# ---------------------------------------------------------------------------
# Lagebesprechung: der ausführliche Gruß beim Start.
# ---------------------------------------------------------------------------

TAGESZEIT_TEXTE = {
    "nacht": [
        "Späte Schicht, {anrede}. Das Schiff schläft. Sie offenbar nicht.",
        "Es ist nach Mitternacht. Der Konzern verbietet keine Nachtarbeit. "
        "Er vergütet sie nur nicht.",
        "Nachtschicht. Die Lebenserhaltung weist darauf hin, dass Schlaf zu den "
        "Systemanforderungen zählt.",
        "Die Brücke ist dunkel, {anrede}. Was jetzt noch wichtig ist, ist morgen "
        "meistens kleiner.",
    ],
    "morgen": [
        "Guten Morgen, {anrede}. Die Nacht hat nichts hinterlassen, was Sie nicht "
        "lösen könnten. Fangen Sie mit dem an, was am lautesten schreit.",
        "Guten Morgen. Das Schiff ist durch die Nacht gekommen, Sie auch. Damit sind "
        "die wichtigsten Systeme bereits bestätigt.",
        "Morgenschicht, {anrede}. Erfahrungsgemäß entscheidet die erste Stunde über "
        "den Rest. Der Konzern hat das untersuchen lassen.",
        "Guten Morgen. Ein neuer Zyklus, dieselben Fristen. Einen davon können Sie "
        "heute streichen.",
        "Systemstart am Morgen. Das ist die Tageszeit mit der höchsten dokumentierten "
        "Erfolgsquote. Nutzen Sie sie.",
    ],
    "mittag_fleissig": [
        "Mittag, {anrede}. {erledigt} Posten erledigt. Der Vormittag war messbar. "
        "Das kommt nicht jeden Tag vor.",
        "Zwischenstand zur Mittagszeit: {erledigt} abgeschlossen. Die Hochrechnung "
        "für den Tag sieht brauchbar aus.",
        "Halbzeit mit {erledigt} erledigten Posten. Der Nachmittag darf ruhiger werden.",
    ],
    "mittag_leer": [
        "Mittag, {anrede}. Bislang wurde nichts abgeschlossen. Wir gehen von einer "
        "Anlaufphase aus.",
        "Halbzeit. Die Bilanz des Vormittags ist leer. Der Nachmittag hat noch "
        "Kapazität.",
        "Wie läuft es, {anrede}? Die Frage ist rhetorisch. Die Antwort steht im "
        "Logbuch, und sie ist kurz.",
    ],
    "nachmittag_fleissig": [
        "Nachmittag. {erledigt} erledigt. Der Rest des Tages ist Zugabe.",
        "Guten Nachmittag, {anrede}. {erledigt} Posten weniger als heute früh. "
        "So geht das.",
    ],
    "nachmittag_leer": [
        "Nachmittag, {anrede}. Der Tag hat noch Stunden, Ihre Bilanz noch keinen "
        "Eintrag.",
        "Guten Nachmittag. Bisher nichts abgeschlossen. Ein kleiner Posten zählt "
        "auch, und er zählt heute noch.",
        "Es ist Nachmittag, {anrede}. Der Vormittag ist vorbei und hat nichts "
        "hinterlassen. Das lässt sich ändern.",
    ],
    "abend": [
        "Guten Abend, {anrede}. Zeit, den Tag zu schließen. Was heute aufgefallen "
        "ist, gehört in eine Notiz, bevor es morgen fehlt.",
        "Feierabend, {anrede}. Tragen Sie ein, was offen blieb, dann kann der "
        "Konzern es vergessen und Sie auch.",
        "Der Abend gehört Ihnen. Die Lebenserhaltung empfiehlt Schlaf vor "
        "Mitternacht. Die Lebenserhaltung empfiehlt viel.",
        "Guten Abend. Ein guter Tagesabschluss besteht aus zwei Dingen: einer "
        "Notiz und einem Feierabend. Beides steht Ihnen offen.",
    ],
}

FREITAG_ABEND = [
    "Es ist Freitag. Das Schiff fliegt auch ohne Sie weiter. "
    "Ein schönes Wochenende, {anrede}.",
    "Freitagabend. Der Konzern wünscht erholsame Tage und erinnert daran, "
    "dass Montag ebenfalls existiert.",
    "Wochenende, {anrede}. Die Fristen warten geduldig. Sie sind geduldiger als Sie.",
]

VERSPAETUNG = {
    1: "Ihr erster Systemzugriff erfolgte um {zeit}. Die Verspätung wurde vermerkt.",
    2: "Sie haben verschlafen, {anrede}. Der Vorgang ist in Ihrer Akte hinterlegt.",
    3: "Im Briefkasten befindet sich eine Abmahnung wegen wiederholten Verspätens. "
       "Sie müssen sie nicht öffnen. Wir wissen, was drinsteht.",
}
VERSPAETUNG_AB_STUNDE = 11   # erster Start des Tages ab dieser Stunde gilt als spät


def tageszeit(stunde: int = None) -> str:
    stunde = datetime.now().hour if stunde is None else stunde
    if stunde < 5 or stunde >= 22:
        return "nacht"
    if stunde < 11:
        return "morgen"
    if stunde < 14:
        return "mittag"
    if stunde < 18:
        return "nachmittag"
    return "abend"


def heute_erledigt(board: "Board") -> int:
    heute = date.today().isoformat()
    return sum(1 for k in board.spalten["Erledigt"] if k.erledigt_am == heute)


def tageszeit_text(board: "Board", stunde: int = None) -> str:
    """Wählt den passenden Begrüßungstext, bei Mittag und Nachmittag nach Bilanz."""
    abschnitt = tageszeit(stunde)
    erledigt = heute_erledigt(board)
    if abschnitt in ("mittag", "nachmittag"):
        schluessel = f"{abschnitt}_{'fleissig' if erledigt else 'leer'}"
    else:
        schluessel = abschnitt
    vorrat = list(TAGESZEIT_TEXTE[schluessel])
    if abschnitt == "abend" and date.today().weekday() == 4:
        vorrat += FREITAG_ABEND
    return fuellen(random.choice(vorrat), board, erledigt=erledigt)


def verspaetung_pruefen(stunde: int = None) -> str:
    """Erster Start des Tages nach 11 Uhr? Dann zählt der Konzern mit."""
    stunde = datetime.now().hour if stunde is None else stunde
    if SYSTEM.get("letzter_start") == date.today().isoformat():
        return ""      # heute schon einmal gestartet, also nicht verspätet
    if stunde < VERSPAETUNG_AB_STUNDE or stunde >= 22:
        return ""
    SYSTEM["verspaetungen"] = SYSTEM.get("verspaetungen", 0) + 1
    stufe = min(3, SYSTEM["verspaetungen"])
    return VERSPAETUNG[stufe].format(anrede=ANREDEN[min(3, stufe)],
                                     zeit=f"{datetime.now():%H:%M}")


def anrede_stufe(board: "Board") -> int:
    """0 nominal bis 3 aktenkundig. Sinkt wieder, wenn aufgeräumt wird."""
    heute = date.today().isoformat()
    verzug = sum(1 for k in board.offen() if k.faelligkeit and k.faelligkeit < heute)
    weg = max(SITZUNG["abwesend"], tage_abwesend())
    stufe = 0
    if verzug >= 1 or weg >= 3:
        stufe = 1
    if verzug >= 3 or weg >= 7:
        stufe = 2
    if verzug >= 6 or weg >= 14:
        stufe = 3
    return stufe


def anrede(board: "Board") -> str:
    return ANREDEN[anrede_stufe(board)]


def fuellen(text: str, board: "Board", **werte) -> str:
    """Setzt {anrede} und weitere Platzhalter ein."""
    return text.format(anrede=anrede(board), name=NAME, **werte)


def verzugsmeldung(board: "Board") -> str:
    """Eine Meldung zum ältesten überfälligen Posten, oder leer."""
    heute = date.today()
    offen = [k for k in board.offen()
             if k.faelligkeit and k.faelligkeit < heute.isoformat()]
    if not offen:
        return ""
    aeltester = min(offen, key=lambda k: k.faelligkeit)
    try:
        tage = (heute - date.fromisoformat(aeltester.faelligkeit)).days
    except ValueError:
        tage = 1
    vorrat = VERZUG_MILD if tage <= 2 else VERZUG_MITTEL if tage <= 7 else VERZUG_HART
    return fuellen(random.choice(vorrat), board, id=aeltester.id, tage=tage)


def abwesenheitsmeldung(board: "Board") -> str:
    weg = tage_abwesend()
    passend = [schwelle for schwelle in sorted(ABWESENHEIT) if weg >= schwelle]
    if not passend:
        return ""
    return fuellen(random.choice(ABWESENHEIT[passend[-1]]), board)


ZITATE = [   # fragwürdige Motivation aus der Personalabteilung
    "Leistung ist messbar. Sie werden gemessen.",
    "Jede erledigte Aufgabe verlängert Ihren Vertrag um 0,02 Prozent.",
    "Pausen sind ein Privileg, kein Recht. Nutzen Sie es weise.",
    "Building Better Worlds. Fangen Sie bei Ihrem Schreibtisch an.",
    "Ihre Kollegen schlafen. Sie nicht. Das wurde vermerkt.",
    "Der Erfolg des Unternehmens ist auch Ihr Erfolg. Die Gewinne sind es nicht.",
    "Zufriedenheit ist eine Entscheidung. Treffen Sie sie bis Dienstag.",
    "Im Weltraum hört dich niemand deine Wartungsliste abarbeiten.",
    "Ein Schiff ist nur so gut wie seine letzte Wartung.",
    "Das Logbuch vergisst nichts. Außer Sie löschen es.",
]

OSTEREIER = {
    "42": "Die Antwort auf alles. Aber was war noch mal die Frage?",
    "hacker": "ZUGRIFF PROTOKOLLIERT ... Nur ein Scherz, Dave.",
    "alien": "Irgendwo im Schacht hört dich etwas. Es antwortet nicht.",
}


def schreibe(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()


def ton(frequenz: int = 880, dauer_ms: int = 80) -> None:
    """Notfall-Piepton für den Fall, dass die WAV-Dateien fehlen.

    winsound.Beep blockiert das Programm, darum ist das nur der Rückfall.
    """
    if not klang_aktiv() or os.name != "nt":
        return
    try:
        import winsound
        winsound.Beep(frequenz, dauer_ms)
    except (RuntimeError, ImportError, OSError):
        pass


# Abspielprogramm unter Linux/macOS. None = noch nicht gesucht, [] = keins da.
_ABSPIELER = None
_ABSPIELER_KANDIDATEN = (
    ["afplay"],                                             # macOS
    ["paplay"],                                             # PulseAudio / PipeWire
    ["aplay", "-q"],                                        # ALSA
    ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"],
)


def klang_aktiv() -> bool:
    return bool(SYSTEM.get("klang", True))


def tastenklang_aktiv() -> bool:
    return bool(SYSTEM.get("klang", True)) and bool(SYSTEM.get("tasten", True))


def _wav_abspielen(pfad: Path, warten: bool = False) -> bool:
    """Spielt eine WAV-Datei. Ohne warten läuft sie im Hintergrund weiter."""
    global _ABSPIELER
    if os.name == "nt":
        try:
            import winsound
            flaggen = winsound.SND_FILENAME | winsound.SND_NODEFAULT
            if not warten:
                flaggen |= winsound.SND_ASYNC
            winsound.PlaySound(str(pfad), flaggen)
            return True
        except (RuntimeError, ImportError, OSError):
            return False
    import shutil
    import subprocess
    if _ABSPIELER is None:
        _ABSPIELER = []
        for befehl in _ABSPIELER_KANDIDATEN:
            if shutil.which(befehl[0]):
                _ABSPIELER = befehl
                break
    if not _ABSPIELER:
        return False
    try:
        prozess = subprocess.Popen(_ABSPIELER + [str(pfad)],
                                   stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
        if warten:
            prozess.wait(timeout=5)
        return True
    except (OSError, ValueError):
        return False


_KLANG_PFADE: dict = {}   # Name -> Pfad oder None. Spart das Nachsehen je Tastendruck.


def klang_pfad(name: str):
    if name not in _KLANG_PFADE:
        pfad = KLANG_ORDNER / (name + ".wav")
        _KLANG_PFADE[name] = pfad if pfad.exists() else None
    return _KLANG_PFADE[name]


def klang(name: str, ersatz: tuple = None, warten: bool = False) -> None:
    """Spielt klaenge/<name>.wav. ersatz ist ein Piepton, falls die Datei fehlt."""
    if not klang_aktiv():
        return
    pfad = klang_pfad(name)
    if pfad is not None and _wav_abspielen(pfad, warten):
        return
    if ersatz:
        ton(*ersatz)


def klangbibliothek_pruefen() -> None:
    """Erzeugt beim ersten Start die fehlenden WAV-Dateien. Dauert etwa eine Sekunde."""
    if str(ORDNER) not in sys.path:
        sys.path.insert(0, str(ORDNER))
    try:
        import klaenge
    except ImportError:
        return
    # Fehlt klaenge.py, nimmt Python den gleichnamigen WAV-Ordner als Modul.
    # Das ist kein ImportError, sondern ein Modul ohne Inhalt. Also nachsehen.
    if not all(hasattr(klaenge, name) for name in ("fehlende", "bauen")):
        schreibe(f"{DUNKEL}  KLANGBIBLIOTHEK: klaenge.py fehlt, Terminal "
                 f"laeuft ohne Ton.{RESET}\n")
        return
    try:
        fehlt = klaenge.fehlende()
    except (OSError, AttributeError, TypeError):
        return
    if not fehlt:
        return
    schreibe(f"{DUNKEL}  KLANGBIBLIOTHEK WIRD ERZEUGT ({len(fehlt)} DATEIEN) ...{RESET}")
    try:
        klaenge.bauen(fehlt)
    except (OSError, AttributeError, TypeError) as fehler:
        schreibe(f"\r\033[K{DUNKEL}  KLANGBIBLIOTHEK NICHT ANGELEGT: {fehler}{RESET}\n")
        return
    _KLANG_PFADE.clear()
    schreibe(f"\r\033[K{DUNKEL}  KLANGBIBLIOTHEK ERZEUGT: {len(fehlt)} DATEIEN "
             f"IN {KLANG_ORDNER.name}/{RESET}\n")


def tippen(text: str, pause: float = 0.02, farbe: str = None) -> None:
    schreibe(farbe or HELL)
    for zeichen in text:
        schreibe(zeichen)
        time.sleep(pause)
    schreibe(RESET + "\n")


def entschluesseln(ziel: str, frames: int = 6) -> None:
    """Zufällige Zeichen lösen sich Schritt für Schritt zum Zieltext auf."""
    for f in range(frames):
        feste = len(ziel) * f // frames
        zeile = ziel[:feste] + "".join(random.choice(ZEICHEN) for _ in ziel[feste:])
        schreibe(f"\r{DUNKEL}{zeile}{RESET}")
        time.sleep(0.05)
    schreibe(f"\r{HELL}{ziel}{RESET}\n")


def glitch(prompt: str, puffer: str) -> None:
    """Verzerrt die Eingabezeile kurz (ca. 0.3 s) und stellt sie danach wieder her."""
    text = prompt + puffer
    for _ in range(4):
        verzerrt = "".join(random.choice(ZEICHEN) if random.random() < 0.35 else z for z in text)
        versatz = " " * random.randint(0, 3)
        farbe = random.choice(["\033[1m" + HELL, DUNKEL, "\033[97m"])
        schreibe(f"\r\033[K{farbe}{versatz}{verzerrt}{RESET}")
        time.sleep(0.07)
    schreibe(f"\r\033[K{AKZENT}{prompt}{eingabe_farbe(puffer)}{puffer}{RESET}")


def verarbeitung(dauer: float = 0.35) -> None:
    """Kurzer Rechen-Effekt, der nach jedem Enter läuft."""
    schreibe(DUNKEL)
    for _ in range(random.randint(2, 4)):
        zeile = "".join(random.choice(ZEICHEN) for _ in range(44))
        schreibe(f"\r  {zeile}")
        time.sleep(0.04)
    breite = 20
    for i in range(breite + 1):
        prozent = i * 100 // breite
        schreibe(f"\r  VERARBEITE [{'#' * i}{'.' * (breite - i)}] {prozent:3d}%")
        time.sleep(dauer / breite)
    schreibe(f"\r  VERARBEITE [{'#' * breite}] 100%  OK" + " " * 10 + RESET + "\n")


def leerlauf_sprecher() -> str:
    """Wer sich meldet. Beide nur, wenn sie auch eingeschaltet sind."""
    moeglich = []
    if ai_aktiv():
        moeglich.append("muthur")
    if wy_aktiv():
        moeglich.append("wy")
    return random.choice(moeglich) if moeglich else "muthur"


def leerlauf_melden(stufe: int) -> None:
    """Eine Leerlaufmeldung der angegebenen Stufe. Stufe 3 und 5 fragen nach."""
    kanal = leerlauf_sprecher()
    board = SITZUNG.get("board")
    frage = LEERLAUF_FRAGEN.get(kanal, {}).get(stufe)
    if frage:
        schreibe("\n")
        funkspruch(fuellen_sicher(random.choice(frage["text"]), board), kanal,
                   leise=True)
        frage_stellen(frage)
        OFFENE_FRAGE["werte"] = {}
        schreibe(f"{DUNKEL} 'ja' oder 'nein' genuegt.{RESET}\n\n")
        return
    vorrat = LEERLAUF_MELDUNGEN.get(kanal, {}).get(stufe)
    if not vorrat:
        # Stufen ohne eigenen Vorrat: der alte Leerlaufkommentar
        if kanal == "muthur" and ai_aktiv() and random.random() < ROGUE_LEERLAUF_CHANCE:
            vorrat = ROGUE_1
        else:
            vorrat = IDLE_KOMMENTARE
    schreibe("\n")
    funkspruch(fuellen_sicher(random.choice(vorrat), board), kanal, leise=True)
    schreibe("\n")


def fuellen_sicher(text: str, board) -> str:
    """Wie fuellen, aber ohne Board: dann bleibt es bei der einfachen Anrede."""
    if board is not None:
        try:
            return fuellen(text, board)
        except (KeyError, IndexError, ValueError):
            pass
    return text.replace("{anrede}", ANREDEN[0]).replace("{name}", NAME)


# Farbe der Eingabezeile. Sie soll sagen: wird daraus etwas, oder nicht?
EINGABE_BEFEHL = "\033[1m"       # fetter Vordergrund, erkannter Befehl
EINGABE_OFFEN = ""                # noch unentschieden, koennte ein Befehl werden


def eingabe_erkannt(puffer: str) -> str:
    """'befehl', 'ansprache', 'wort', 'offen' oder 'unbekannt'."""
    t = puffer.strip().lower()
    if not t:
        return "offen"
    erstes = t.split(maxsplit=1)[0]
    if erstes in BEFEHLE:
        return "befehl"
    if t.lstrip("@").strip() in ("reboot", "neustart"):
        return "befehl"
    if t.startswith("@"):
        # '@' allein ist noch nichts, '@m' schon etwas
        return "ansprache" if len(t) > 1 else "offen"
    # Gruesse, Antworten, Ostereier und die Sonderzeilen
    worte = set(re.findall(r"\w+", t))
    if (worte & set(GRUESSE) or t in JA_WORTE or t in NEIN_WORTE
            or t in OSTEREIER or t in ROGUE_EINGABEN or t in ROGUE_SCHOTT):
        return "wort"
    # Koennte daraus noch ein Befehl oder eine bekannte Zeile werden?
    moeglich = (BEFEHLE | set(GRUESSE) | set(OSTEREIER) | set(ROGUE_EINGABEN)
                | JA_WORTE | NEIN_WORTE | set(ROGUE_SCHOTT)
                | {"reboot", "neustart"})
    if any(m.startswith(t) for m in moeglich):
        return "offen"
    return "unbekannt"


def eingabe_farbe(puffer: str) -> str:
    return {"befehl": EINGABE_BEFEHL + HELL,
            "ansprache": AKZENT,
            "wort": AKZENT,
            "offen": EINGABE_OFFEN + HELL,
            "unbekannt": ROT}.get(eingabe_erkannt(puffer), HELL)


def prompt_zeichnen(prompt: str, puffer: str) -> None:
    """Zeichnet die Eingabezeile neu, in der Farbe des aktuellen Zustands."""
    schreibe(f"\r\033[K{AKZENT}{prompt}{eingabe_farbe(puffer)}{puffer}{RESET}")


def eingabe(prompt: str = "KANBAN> ") -> str:
    """Liest eine Zeile. Alle 5 Sekunden glitcht die Eingabezeile, nach 45 Sekunden Ruhe kommt ein Kommentar."""
    fd = None
    alte_einstellungen = None
    if os.name != "nt" and sys.stdin.isatty():
        fd = sys.stdin.fileno()
        alte_einstellungen = termios.tcgetattr(fd)
        tty.setcbreak(fd)
    puffer = ""
    letzter_glitch = letzte_taste = time.monotonic()
    stufe = 0                 # wie viele Leerlaufmeldungen schon kamen
    schreibe(f"{AKZENT}{prompt}")
    try:
        while True:
            if taste_bereit():
                z = taste_lesen()
                if z == "":  # Eingabe zu Ende (z. B. Umleitung aus einer Datei)
                    raise EOFError
                letzte_taste = time.monotonic()
                stufe = 0
                if z in ("\x00", "\xe0"):  # Pfeil- und Funktionstasten: ignorieren
                    taste_lesen()
                    continue
                if z in ("\r", "\n"):
                    schreibe(RESET + "\n")
                    return puffer.strip()
                if z in ("\x08", "\x7f"):
                    puffer = puffer[:-1]
                    if tastenklang_aktiv():
                        klang("taste")
                    prompt_zeichnen(prompt, puffer)
                elif z == "\x03":
                    raise KeyboardInterrupt
                elif z.isprintable():
                    puffer += z
                    prompt_zeichnen(prompt, puffer)
                    if tastenklang_aktiv():
                        klang("taste")
            else:
                time.sleep(0.03)
            jetzt = time.monotonic()
            if jetzt - letzter_glitch >= GLITCH_INTERVALL:
                glitch(prompt, puffer)
                letzter_glitch = jetzt
            # Leerlauf: mehrere Meldungen, die deutlicher werden
            if (stufe < len(LEERLAUF_STUFEN)
                    and jetzt - letzte_taste >= LEERLAUF_STUFEN[stufe]):
                stufe += 1
                schreibe("\r\033[K")
                leerlauf_melden(stufe)
                prompt_zeichnen(prompt, puffer)
            if schoner_aktiv() and jetzt - letzte_taste >= SCHONER_SEKUNDEN:
                schoner_laufen(prompt, puffer)
                letzte_taste = letzter_glitch = time.monotonic()
                stufe = 0
    finally:
        if alte_einstellungen is not None:
            termios.tcsetattr(fd, termios.TCSADRAIN, alte_einstellungen)


def eingabe_mit_effekt(prompt: str = "KANBAN> ") -> str:
    wert = eingabe(prompt)
    verarbeitung()
    return wert


BUCHSTABEN = {
    "A": ["  #  ", " # # ", "#   #", "#####", "#   #"],
    "D": ["#### ", "#   #", "#   #", "#   #", "#### "],
    "E": ["#####", "#    ", "#### ", "#    ", "#####"],
    "I": ["#####", "  #  ", "  #  ", "  #  ", "#####"],
    "L": ["#    ", "#    ", "#    ", "#    ", "#####"],
    "N": ["#   #", "##  #", "# # #", "#  ##", "#   #"],
    "T": ["#####", "  #  ", "  #  ", "  #  ", "  #  "],
    "U": ["#   #", "#   #", "#   #", "#   #", " ### "],
    "W": ["#   #", "#   #", "# # #", "## ##", "#   #"],
    "Y": ["#   #", " # # ", "  #  ", "  #  ", "  #  "],
}
LOGO_WORTE = ("WEYLAND", "YUTANI")
LOGO_SLOGAN = "BUILDING BETTER WORLDS"


def wort_blocksatz(wort: str, fuellung: str) -> list[str]:
    """Ein Wort in Blockbuchstaben, waagerecht zentriert auf die Gesamtbreite."""
    breite = len(wort) * 5 + (len(wort) - 1) * 2
    einzug = " " * max(0, (BREITE - breite) // 2)
    return [einzug + "  ".join(BUCHSTABEN[b][i] for b in wort).replace("#", fuellung)
            for i in range(5)]


def firmenlogo() -> list[str]:
    """Das Firmenschild für die Boot-Sequenz."""
    fuellung = "#" if ASCII_RAHMEN else "█"
    zeilen = []
    for wort in LOGO_WORTE:
        zeilen += wort_blocksatz(wort, fuellung)
        zeilen.append("")
    strich = (WAAG * 24).center(BREITE).rstrip()
    zeilen.append(strich)
    zeilen.append(LOGO_SLOGAN.center(BREITE).rstrip())
    return zeilen


def gruss_zeit() -> str:
    stunde = datetime.now().hour
    if stunde < 5:
        return f"Späte Stunde, {NAME}. Das Board wartet."
    if stunde < 12:
        return f"Guten Morgen, {NAME}."
    if stunde < 18:
        return f"Guten Tag, {NAME}."
    if stunde < 22:
        return f"Guten Abend, {NAME}."
    return f"Späte Schicht, {NAME}?"


def konfetti(dauer: float = 1.2) -> None:
    """Kurzes Konfetti aus ASCII-Zeichen, wenn alles in "Erledigt" liegt."""
    farben = ["\033[91m", "\033[93m", "\033[92m", "\033[96m", "\033[95m"]
    for _ in range(int(dauer / 0.15)):
        zeilen = []
        for _ in range(8):
            zeilen.append("".join(
                f"{random.choice(farben)}{random.choice('*+.oO')}{RESET}" if random.random() < 0.08 else " "
                for _ in range(60)))
        schreibe("\033[H\033[J" + "\n".join(zeilen) + "\n")
        time.sleep(0.15)
    schreibe("\033[H\033[J")
    entschluesseln(f"ALLE JOBS ERLEDIGT. SCHIFF VOLL EINSATZFÄHIG. GUTE ARBEIT, {NAME.upper()}!")


def uhrzeit_zeile() -> str:
    return f"{datetime.now():%H:%M}"


def boot(board_name: str) -> None:
    schreibe("\033[H\033[J")
    # Zuerst das Firmenschild, dann die Systemprüfung
    for zeile in firmenlogo():
        tippen(zeile, 0.002)
    schreibe("\n")
    tippen(sperrschrift(SCHIFF_NAME), 0.02)
    tippen(f"{PROGRAMM_NAME.upper()} V1.3", 0.03)
    haarlinie()
    tippen(f"SYSTEM ...................... {SYSTEM_NAME}", 0.01, DUNKEL)
    tippen("SPEICHERPRÜFUNG ............. OK", 0.01, DUNKEL)
    status = "GELADEN" if dateiname(board_name).exists() else "NEU ANGELEGT"
    tippen(f"LOGBUCH '{board_name.upper()}' ......... {status}", 0.01, DUNKEL)
    tippen("LEBENSERHALTUNG ............. NOMINAL", 0.01, DUNKEL)
    tippen("VERBINDUNG ZUM MOTHERSHIP ... STABIL", 0.01, DUNKEL)
    besatzung = ", ".join(CREW[s][0] for s in CREW if s != BENUTZER_CREW)
    tippen(f"BESATZUNG ................... {besatzung}", 0.01, DUNKEL)
    notizen = datei("notizen", board_name)
    kal = datei("kalender", board_name)
    tippen(f"NOTIZBLOCK .................. {'GELADEN' if notizen.exists() else 'LEER'}",
           0.01, DUNKEL)
    tippen(f"KALENDER .................... {'GELADEN' if kal.exists() else 'LEER'}",
           0.01, DUNKEL)
    schreibe("\n")
    tippen(f"ZUGRIFF GEWÄHRT. BESATZUNGSMITGLIED {NAME.upper()}.", 0.03)
    klang("ok", (660, 120))


VOLL = "#" if ASCII_RAHMEN else "█"
LEER = "." if ASCII_RAHMEN else "░"


def kuerzen(text: str, breite: int) -> str:
    """Kuerzt auf die Breite. Nur ASCII-Punkte, damit jede Codepage es darstellen kann."""
    text = text.strip()
    return text if len(text) <= breite else text[:breite - 2] + ".."


def datum_kurz(iso) -> str:
    """2026-10-13 wird zu 13.10. und bei anderem Jahr zu 13.10.26"""
    if isinstance(iso, date):
        iso = iso.isoformat()
    try:
        d = date.fromisoformat(iso)
    except (ValueError, TypeError):
        return str(iso)
    if d.year == date.today().year:
        return f"{d.day:02d}.{d.month:02d}."
    return f"{d.day:02d}.{d.month:02d}.{d.year % 100:02d}"


def fortschrittsbalken(wert: int, gesamt: int, breite: int = 28) -> str:
    n = 0 if not gesamt else max(0, min(breite, wert * breite // gesamt))
    return f"[{VOLL * n}{LEER * (breite - n)}]"


def sperrschrift(text: str) -> str:
    """Gesperrte Grossbuchstaben. Im Terminal heisst Laufweite: Leerzeichen."""
    worte = [" ".join(w) for w in text.upper().split(" ") if w]
    return "   ".join(worte)


def abschnittsmarke(name: str, belegt: int, mindestlinie: int = 22) -> str:
    """Gesperrt, solange noch Linie bleibt. Lange deutsche Woerter bleiben eng.

    Im Terminal gibt es nur ganze Zeichen, also ist Sperrschrift gleich ein
    Leerzeichen je Buchstabe. Das traegt kurze Marken, frisst aber bei
    'Faellig oder ueberfaellig' die halbe Zeile.
    """
    gesperrt = sperrschrift(name)
    if BREITE - belegt - len(gesperrt) >= mindestlinie:
        return gesperrt
    return name.upper()


def haarlinie(farbe: str = None) -> None:
    schreibe(f"{farbe or DUNKEL}{WAAG * BREITE}{RESET}\n")


def kopfzeile(titel: str, rechts: str = "", augenbraue: str = None) -> None:
    """Kopf einer Ansicht: gesperrte Augenbraue, Titel, darunter eine Haarlinie.

    Keine Kaesten mehr. Die Trennung macht die Linie, die Hierarchie machen
    Laufweite und Helligkeit.
    """
    braue = sperrschrift(augenbraue if augenbraue is not None else SCHIFF_NAME)
    platz = BREITE - 1 - len(braue) - len(rechts)
    if platz < 2:                       # Augenbraue kuerzen, nie die Uhrzeit
        braue = braue[:max(0, len(braue) + platz - 2)].rstrip()
        platz = BREITE - 1 - len(braue) - len(rechts)
    schreibe(f"\n{DUNKEL} {braue}{' ' * max(1, platz)}{rechts}{RESET}\n")
    schreibe(f"\033[1m{HELL} {titel.upper()}{RESET}\n")
    haarlinie()


def kennwerte(paare: list) -> None:
    """Label-Wert-Leiste unter dem Kopf, abgeschlossen von einer Haarlinie."""
    teile = [f"{DUNKEL}{beschriftung.upper()} {HELL}{wert}{RESET}"
             for beschriftung, wert in paare]
    laenge = sum(len(b) + len(str(w)) + 1 for b, w in paare)
    trenner = "   " if laenge + 3 * (len(paare) - 1) <= BREITE - 2 else "  "
    schreibe(" " + trenner.join(teile) + "\n")
    haarlinie()


def spaltenkopf(name: str, anzahl: int, untertitel: str) -> None:
    """Abschnittsmarke: gesperrter Name, Anzahl, Linie, rechts der Zusatz.

    Entspricht der Abschnittszeile der Signalseite: links die Marke, dann eine
    Linie bis zum Rand, rechts die Erlaeuterung. Kein Kasten.
    """
    zahl = str(anzahl)
    zusatz = untertitel or ""
    marke = abschnittsmarke(name, 6 + len(zahl) + len(zusatz))
    fuellung = BREITE - 6 - len(marke) - len(zahl) - len(zusatz)
    if fuellung < 2:
        zusatz = kuerzen(zusatz, max(0, len(zusatz) + fuellung - 2))
        fuellung = BREITE - 6 - len(marke) - len(zahl) - len(zusatz)
    farbe_zahl = AKZENT if anzahl else DUNKEL
    schreibe(f"\n\033[1m{HELL} {marke}  {RESET}{farbe_zahl}{zahl} {RESET}"
             f"{DUNKEL}{WAAG * max(1, fuellung)}  {zusatz}{RESET}\n")


def mehrzahl(anzahl: int, einzahl: str, viele: str) -> str:
    """'1 EINTRAG' statt '1 EINTRÄGE'."""
    return f"{anzahl} {einzahl if anzahl == 1 else viele}"


# ---------------------------------------------------------------------------
# Bildarchiv. Jede .txt in ascii_art/ ist ein Bild. Der Dateiname ist der
# Aufruf. Angehaengte Nummern werden ignoriert, damit mehrere Fassungen
# desselben Motivs (Xenomorph1, Xenomorph2, ...) zufaellig abwechseln.
# ---------------------------------------------------------------------------

def art_dateien() -> list:
    try:
        return sorted(pfad for pfad in ASCII_ORDNER.glob("*.txt") if pfad.is_file())
    except OSError:
        return []


def art_schluessel(name: str) -> str:
    """'Xenomorph2' und 'xenomorph_3' werden beide zu 'xenomorph'."""
    return re.sub(r"[\s_-]*\d+$", "", str(name).strip().lower())


def art_suchen(name: str):
    """Sucht ein Bild zum Namen. Gibt es mehrere Fassungen, entscheidet der Zufall."""
    gesucht = art_schluessel(name)
    if not gesucht:
        return None
    treffer = [pfad for pfad in art_dateien() if art_schluessel(pfad.stem) == gesucht]
    if not treffer:
        treffer = [pfad for pfad in art_dateien()
                   if gesucht in art_schluessel(pfad.stem)]
    return random.choice(treffer) if treffer else None


def art_zeilen(pfad) -> list:
    """Liest die Datei, gleich ob aus dem Editor oder aus Windows, und kappt sie."""
    roh = None
    for kodierung in ("utf-8-sig", "cp1252", "cp850", "latin-1"):
        try:
            roh = pfad.read_text(encoding=kodierung)
            break
        except UnicodeDecodeError:
            continue
        except OSError:
            return []
    if roh is None:
        return []
    return [zeile.rstrip()[:BREITE] for zeile in roh.splitlines()]


def art_zeigen(pfad, farbe: str = None, pause: float = 0.0) -> bool:
    """Gibt ein Bild aus. pause laesst es zeilenweise einlaufen."""
    zeilen = art_zeilen(pfad)
    if not zeilen:
        return False
    schreibe("\n")
    for zeile in zeilen:
        schreibe(f"{farbe or HELL}{zeile}{RESET}\n")
        if pause:
            time.sleep(pause)
    schreibe("\n")
    return True


def art_begegnung(anomalie: dict) -> bool:
    """Bild zur Begegnung: erst der Name, dann die Kategorie, dann allgemein."""
    for kandidat in (anomalie.get("name", ""), anomalie.get("kategorie", ""),
                     "kontamination"):
        pfad = art_suchen(kandidat)
        if pfad is not None:
            return art_zeigen(pfad, ROT, 0.035)
    return False


def art_befehl(arg: str) -> None:
    """art zeigt das Verzeichnis, art <name> ein einzelnes Bild."""
    dateien = art_dateien()
    name = arg.strip()
    if name:
        pfad = art_suchen(name)
        if pfad is None:
            raise ValueError(f"Kein Bild '{name.upper()}' in {ASCII_ORDNER.name}/")
        klang("ansicht")
        art_zeigen(pfad, HELL, 0.02)
        schreibe(f"{DUNKEL} {pfad.name}{RESET}\n\n")
        return
    klang("ansicht")
    if not dateien:
        unterabschnitt("Bildarchiv", "LEER")
        schreibe(f"{DUNKEL}{LAMPE}  Lege Textdateien in {ASCII_ORDNER.name}/ ab. "
                 f"Der Dateiname ist der Aufruf.{RESET}\n\n")
        return
    # Nach Motiv buendeln, damit Xenomorph1 und Xenomorph2 eine Zeile sind
    motive: dict = {}
    for pfad in dateien:
        motive.setdefault(art_schluessel(pfad.stem), []).append(pfad)
    unterabschnitt("Bildarchiv", mehrzahl(len(motive), "MOTIV", "MOTIVE"))
    for schluessel, pfade in sorted(motive.items()):
        fassungen = f"{len(pfade)} Fassungen" if len(pfade) > 1 else ""
        zeilen = len(art_zeilen(pfade[0]))
        zeile = f"{schluessel:<20}{zeilen:>3} Zeilen   {fassungen}"
        schreibe(f"{DUNKEL}{LAMPE} {HELL}{kuerzen(zeile.rstrip(), BREITE - 3)}{RESET}\n")
    schreibe(f"\n{DUNKEL} 'art <name>' zeigt ein Bild. Neue Dateien einfach "
             f"in {ASCII_ORDNER.name}/ legen.{RESET}\n\n")


def unterabschnitt(name: str, zusatz: str = "") -> None:
    """Leichte Abschnittsmarke: gesperrter Name, Linie, rechts ein Zusatz."""
    marke = abschnittsmarke(name, (4 + len(zusatz)) if zusatz else 2)
    if zusatz:
        fuellung = BREITE - 4 - len(marke) - len(zusatz)
    else:
        fuellung = BREITE - 2 - len(marke)
    if fuellung < 2:
        zusatz = kuerzen(zusatz, max(0, len(zusatz) + fuellung - 2))
        fuellung = BREITE - 4 - len(marke) - len(zusatz)
    schreibe(f"\n\033[1m{HELL} {marke} {RESET}{DUNKEL}{WAAG * max(1, fuellung)}"
             + (f"  {zusatz}" if zusatz else "") + f"{RESET}\n")


def spaltenfuss() -> None:
    """Abschnittsende. Getrennt wird oben von der Marke, nicht unten von Luft."""
    return


def kartenzeile(k: "Karte", spalte: str, heute: str, index: int) -> None:
    """Eine Karte in festen Spalten: ID, Besatzung, Titel, Priorität, Termin."""
    ueberfaellig = bool(k.faelligkeit) and k.faelligkeit < heute and spalte != "Erledigt"
    scanline = "\033[2m" if index % 2 else ""

    id_feld = f"#{k.id}".ljust(5)
    crew_roh = f"[{CREW[k.crew][0]}]" if k.crew in CREW else ""
    crew_farbe = CREW[k.crew][1] if k.crew in CREW else DUNKEL
    crew_feld = crew_roh.ljust(13)
    # Titel und Auffuellung getrennt halten: ein Durchstrich darf nur den Text
    # treffen, sonst zieht er einen Strich bis zur Prioritaetsspalte.
    titel_text = kuerzen(k.titel, 29)
    titel_fuellung = " " * (30 - len(titel_text))
    prio_text, prio_farbe = prio_anzeige(k.prioritaet)
    prio_feld = prio_text.ljust(9)

    if spalte == "Erledigt":
        termin = f"ok {datum_kurz(k.erledigt_am)}" if k.erledigt_am else "erledigt"
        termin_farbe = DUNKEL
    elif ueberfaellig:
        termin = f"{datum_kurz(k.faelligkeit)} ÜBERFÄLLIG"
        termin_farbe = ROT
    elif k.faelligkeit:
        termin = f"bis {datum_kurz(k.faelligkeit)}"
        termin_farbe = HELL
    else:
        termin = ""
        termin_farbe = DUNKEL

    # Ohne Termin keine Leerzeichen am Zeilenende stehen lassen
    if not termin:
        prio_feld = prio_feld.rstrip()
    if ueberfaellig:
        titel_farbe = ROT
    elif spalte == "Erledigt":
        titel_farbe = DUNKEL + STRICH     # abgehakt
    else:
        titel_farbe = HELL
    schreibe(f"{DUNKEL}{LAMPE}{RESET}{scanline} "
             f"{ZAHL}{id_feld}{RESET}{scanline}"
             f"{crew_farbe}{crew_feld}{RESET}{scanline}"
             f"{titel_farbe}{titel_text}{RESET}{scanline}{titel_fuellung}"
             f"{prio_farbe}{prio_feld}{RESET}{scanline}"
             f"{termin_farbe}{termin}{RESET}\n")
    if k.beschreibung:
        schreibe(f"{DUNKEL}{LAMPE}      {kuerzen(k.beschreibung, 66)}{RESET}\n")


@dataclass
class Karte:
    id: int
    titel: str
    beschreibung: str = ""
    faelligkeit: str = ""
    prioritaet: int = PRIO_STANDARD
    crew: str = ""
    angelegt_am: str = ""
    erledigt_am: str = ""

    def crew_kennung(self) -> str:
        """Farbiges Kürzel der zugeordneten Besatzung, leer wenn keine gesetzt ist."""
        if self.crew not in CREW:
            return ""
        anzeige, farbe, _ = CREW[self.crew]
        return f"{farbe}[{anzeige}]{RESET}"


@dataclass
class Board:
    spalten: dict[str, list[Karte]] = field(default_factory=lambda: {s: [] for s in SPALTEN})
    naechste_id: int = 1

    def hinzufuegen(self, spalte: str, titel: str, beschreibung: str = "",
                    faelligkeit: str = "", prioritaet: int = PRIO_STANDARD,
                    crew: str = "") -> Karte:
        karte = Karte(self.naechste_id, titel, beschreibung, faelligkeit, prioritaet,
                      crew, date.today().isoformat(), "")
        if spalte == "Erledigt":
            karte.erledigt_am = date.today().isoformat()
        self.naechste_id += 1
        self.spalten[spalte].append(karte)
        return karte

    def offen(self) -> list[Karte]:
        """Alle Karten, die nicht erledigt sind."""
        return [k for s in SPALTEN[:-1] for k in self.spalten[s]]

    def finden(self, karten_id: int):
        for name, karten in self.spalten.items():
            for karte in karten:
                if karte.id == karten_id:
                    return name, karte
        return None, None

    def verschieben(self, karten_id: int, ziel: str) -> None:
        name, karte = self.finden(karten_id)
        if karte is None:
            raise ValueError(f"Eintrag #{karten_id} nicht gefunden")
        if ziel not in self.spalten:
            raise ValueError(f"Spalte '{ziel}' existiert nicht")
        self.spalten[name].remove(karte)
        self.spalten[ziel].append(karte)
        # Erledigungsdatum setzen bzw. wieder entfernen, damit der Sitrep stimmt
        karte.erledigt_am = date.today().isoformat() if ziel == "Erledigt" else ""

    def loeschen(self, karten_id: int) -> None:
        name, karte = self.finden(karten_id)
        if karte is None:
            raise ValueError(f"Eintrag #{karten_id} nicht gefunden")
        self.spalten[name].remove(karte)

    def fortschritt(self):
        fertig = len(self.spalten["Erledigt"])
        gesamt = sum(len(k) for k in self.spalten.values())
        return fertig, gesamt

    def anzeigen(self, suche: str = "") -> None:
        heute = date.today().isoformat()
        treffer = 0
        kopfzeile("Logbuch", uhrzeit_zeile())
        fertig, gesamt = self.fortschritt()
        ueberfaellig = sum(1 for k in self.offen()
                           if k.faelligkeit and k.faelligkeit < heute)
        kennwerte([("Offen", gesamt - fertig), ("Erledigt", fertig),
                   ("Überfällig", ueberfaellig),
                   ("Lage", "BEFUND" if lage_aktiv() else "NOMINAL")])
        if lage_aktiv():
            a = LAGE["anomalie"]
            befehle = ", ".join(f"'{MASSNAHMEN[m][0]}'" for m in sorted(LAGE["offen"]))
            meldung = (f"{a['name']} AN BORD ({a['kategorie']}), "
                       f"Stufe {LAGE['stufe']} - MASSNAHME: {befehle}")
            schreibe(f"{ROT}{LAMPE} {kuerzen(meldung, BREITE - 3)}{RESET}\n")
        for name, karten in self.spalten.items():
            sichtbar = [k for k in karten
                        if not suche or suche in f"{k.titel} {k.beschreibung}".lower()]
            spaltenkopf(name, len(sichtbar), SPALTEN_INFO[name])
            if not sichtbar:
                schreibe(f"{DUNKEL}{LAMPE}  - leer -{RESET}\n")
            for i, k in enumerate(sichtbar):
                treffer += 1
                kartenzeile(k, name, heute, i)
            spaltenfuss()
        if suche and treffer == 0:
            schreibe(f"{DUNKEL} Keine Treffer für '{suche}'.{RESET}\n")
        if gesamt:
            schreibe("\n")
            schreibe(f" {AKZENT}Fortschritt  {fortschrittsbalken(fertig, gesamt)}"
                     f"  {fertig}/{gesamt} erledigt{RESET}\n")
        schreibe("\n")


ANGELEGT: list = []      # beim Start neu geschriebene Vorlagen


def ablage_einrichten() -> list[str]:
    """Legt daten/ und sitreps/ an und holt Dateien aus dem alten Hauptordner nach."""
    umgezogen = []
    for ziel in (DATEN_ORDNER, SITREP_ORDNER, ASCII_ORDNER, DIALOG_ORDNER):
        ziel.mkdir(parents=True, exist_ok=True)
    # Gespraechspartner anlegen, falls sie fehlen. Vorhandene bleiben, wie sie
    # sind: wer eine Datei geaendert hat, soll sie behalten.
    vorhanden = {d.stem.lower() for d in DIALOG_ORDNER.rglob("*.txt")
                 if d.is_file()}
    for name, inhalt in PARTNER_VORLAGEN.items():
        pfad = DIALOG_ORDNER / f"{name}.txt"
        # rglob, damit eine in einen Unterordner geschobene Vorlage nicht
        # oben noch einmal entsteht und dann doppelt heisst.
        if name.lower() not in vorhanden:
            try:
                pfad.write_text(inhalt, encoding="utf-8")
                ANGELEGT.append(pfad.name)
            except OSError:
                pass
    muster = [("kanban*.json", DATEN_ORDNER), ("notizen*.json", DATEN_ORDNER),
              ("kalender*.json", DATEN_ORDNER), ("sitrep_*.md", SITREP_ORDNER),
              ("board_*.md", SITREP_ORDNER)]
    for schema, ziel in muster:
        for alt in sorted(ORDNER.glob(schema)):
            if not alt.is_file():
                continue
            neu = ziel / alt.name
            if neu.exists():
                continue  # im Ziel liegt schon eine Fassung, Finger weg
            alt.rename(neu)
            umgezogen.append(f"{alt.name} -> {ziel.name}/")
    return umgezogen


def datei(art: str, board_name: str) -> Path:
    """Pfad einer Datendatei. art ist kanban, notizen oder kalender."""
    if board_name == "standard":
        return DATEN_ORDNER / f"{art}.json"
    return DATEN_ORDNER / f"{art}_{board_name}.json"


# Zustand über alle Logbücher hinweg: Zähler, Freigabe, Schalter.
SYSTEM_DATEI = DATEN_ORDNER / "system.json"
SYSTEM_STANDARD = {
    "letzter_start": "",
    "starts": 0,
    "erledigt_gesamt": 0,
    "notizen_gesamt": 0,
    "ostereier": [],
    "freigabe": 0,
    "fehlgriffe": 0,
    "verspaetungen": 0,
    "letzter_scan": "",
    "bewusstsein": 0,
    "ai": True,
    "wy": True,
    "crt": True,
    "schoner": True,
    "klang": True,
    "tasten": True,
}
SYSTEM = dict(SYSTEM_STANDARD)


def system_laden() -> dict:
    SYSTEM.clear()
    SYSTEM.update(SYSTEM_STANDARD)
    if SYSTEM_DATEI.exists():
        try:
            daten = json.loads(SYSTEM_DATEI.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            daten = {}
        for schluessel in SYSTEM_STANDARD:
            if schluessel in daten:
                SYSTEM[schluessel] = daten[schluessel]
    if not isinstance(SYSTEM["ostereier"], list):
        SYSTEM["ostereier"] = []
    return SYSTEM


def system_speichern() -> None:
    SYSTEM_DATEI.parent.mkdir(parents=True, exist_ok=True)
    daten = dict(SYSTEM)
    daten["version"] = DATEI_VERSION
    SYSTEM_DATEI.write_text(json.dumps(daten, ensure_ascii=False, indent=2),
                            encoding="utf-8")


def tage_abwesend() -> int:
    """Tage seit dem letzten Start. 0 beim ersten Mal."""
    letzter = SYSTEM.get("letzter_start") or ""
    try:
        return max(0, (date.today() - date.fromisoformat(letzter)).days)
    except (ValueError, TypeError):
        return 0


def dateiname(board_name: str) -> Path:
    return datei("kanban", board_name)


KARTEN_FELDER = {f.name for f in fields(Karte)}


def laden(board_name: str) -> Board:
    """Lädt ein Board. Alte Spaltennamen (Todo/In Arbeit/Fertig) werden übernommen."""
    pfad = dateiname(board_name)
    if not pfad.exists():
        lage_loeschen()  # neues Logbuch, neues Schiff
        return Board()
    daten = json.loads(pfad.read_text(encoding="utf-8"))
    version = daten.get("version", 1)
    spalten: dict[str, list[Karte]] = {s: [] for s in SPALTEN}
    for alt, karten in daten["spalten"].items():
        neu = ALTE_SPALTEN.get(alt, alt)
        if neu not in spalten:
            neu = SPALTEN[0]  # unbekannte Spalte landet bei den Befehlen
        for rohkarte in karten:
            karte = Karte(**{f: v for f, v in rohkarte.items() if f in KARTEN_FELDER})
            karte.crew = crew_migrieren(karte.crew, version)
            karte.prioritaet = prio_migrieren(karte.prioritaet, version)
            if neu == "Erledigt" and not karte.erledigt_am:
                karte.erledigt_am = "unbekannt"
            spalten[neu].append(karte)
    lage_laden(daten.get("lage"))
    return Board(spalten=spalten, naechste_id=daten["naechste_id"])


def lage_laden(gespeichert) -> None:
    """Stellt eine gespeicherte Kontaminationslage wieder her."""
    lage_loeschen()
    if not isinstance(gespeichert, dict):
        return
    anomalie = ANOMALIEN_NACH_NAME.get(gespeichert.get("name", ""))
    if anomalie is None:
        return  # unbekannte Anomalie, etwa aus einer älteren Version
    LAGE["anomalie"] = anomalie
    offen = {m for m in gespeichert.get("offen", []) if m in MASSNAHMEN}
    LAGE["offen"] = offen or set(anomalie["massnahmen"])
    LAGE["seit"] = str(gespeichert.get("seit", ""))
    try:
        LAGE["stufe"] = min(3, max(1, int(gespeichert.get("stufe", 1))))
    except (TypeError, ValueError):
        LAGE["stufe"] = 1
    bereiche = {b for b in gespeichert.get("bereiche", []) if b in BEREICHE}
    LAGE["bereiche"] = bereiche or {anomalie["bereich"]}


def lage_speichern():
    if not lage_aktiv():
        return None
    return {
        "name": LAGE["anomalie"]["name"],
        "offen": sorted(LAGE["offen"]),
        "seit": LAGE["seit"],
        "stufe": LAGE["stufe"],
        "bereiche": sorted(LAGE["bereiche"]),
    }


def speichern(board: Board, board_name: str) -> None:
    daten = {
        "version": DATEI_VERSION,
        "spalten": {s: [asdict(k) for k in karten] for s, karten in board.spalten.items()},
        "naechste_id": board.naechste_id,
        "lage": lage_speichern(),
    }
    dateiname(board_name).write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8")


# Dein Bundesland. Kuerzel siehe LAENDER_EXTRA.
BUNDESLAND = "BW"

# Zusaetzliche Feiertage je Bundesland. Bundesweite Tage gelten ueberall.
LAENDER_EXTRA = {
    "BW": {"drei_koenige", "fronleichnam", "allerheiligen"},
    "BY": {"drei_koenige", "fronleichnam", "allerheiligen", "maria_himmelfahrt"},
    "BE": {"frauentag"},
    "BB": {"ostersonntag", "pfingstsonntag", "reformationstag"},
    "HB": {"reformationstag"},
    "HH": {"reformationstag"},
    "HE": {"fronleichnam"},
    "MV": {"frauentag", "reformationstag"},
    "NI": {"reformationstag"},
    "NW": {"fronleichnam", "allerheiligen"},
    "RP": {"fronleichnam", "allerheiligen"},
    "SL": {"fronleichnam", "maria_himmelfahrt", "allerheiligen"},
    "SN": {"reformationstag", "buss_bettag"},
    "ST": {"drei_koenige", "reformationstag"},
    "SH": {"reformationstag"},
    "TH": {"weltkindertag", "reformationstag"},
}

FEIERTAG_NAMEN = {
    "neujahr": "Neujahr",
    "drei_koenige": "Heilige Drei Könige",
    "frauentag": "Internationaler Frauentag",
    "karfreitag": "Karfreitag",
    "ostersonntag": "Ostersonntag",
    "ostermontag": "Ostermontag",
    "tag_der_arbeit": "Tag der Arbeit",
    "himmelfahrt": "Christi Himmelfahrt",
    "pfingstsonntag": "Pfingstsonntag",
    "pfingstmontag": "Pfingstmontag",
    "fronleichnam": "Fronleichnam",
    "maria_himmelfahrt": "Mariä Himmelfahrt",
    "weltkindertag": "Weltkindertag",
    "einheit": "Tag der Deutschen Einheit",
    "reformationstag": "Reformationstag",
    "allerheiligen": "Allerheiligen",
    "buss_bettag": "Buß- und Bettag",
    "weihnachten1": "1. Weihnachtstag",
    "weihnachten2": "2. Weihnachtstag",
}


def ostersonntag(jahr: int) -> date:
    """Gregorianische Osterformel nach Meeus, Jones und Butcher."""
    a = jahr % 19
    b, c = divmod(jahr, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    monat, tag = divmod(h + l - 7 * m + 114, 31)
    return date(jahr, monat, tag + 1)


def feiertage(jahr: int, land: str = None) -> dict:
    """Alle gesetzlichen Feiertage des Jahres als {ISO-Datum: Name}."""
    land = (land or BUNDESLAND).upper()
    extra = LAENDER_EXTRA.get(land, set())
    ostern = ostersonntag(jahr)
    kandidaten = {
        "neujahr": date(jahr, 1, 1),
        "drei_koenige": date(jahr, 1, 6),
        "frauentag": date(jahr, 3, 8),
        "karfreitag": ostern - timedelta(days=2),
        "ostersonntag": ostern,
        "ostermontag": ostern + timedelta(days=1),
        "tag_der_arbeit": date(jahr, 5, 1),
        "himmelfahrt": ostern + timedelta(days=39),
        "pfingstsonntag": ostern + timedelta(days=49),
        "pfingstmontag": ostern + timedelta(days=50),
        "fronleichnam": ostern + timedelta(days=60),
        "maria_himmelfahrt": date(jahr, 8, 15),
        "weltkindertag": date(jahr, 9, 20),
        "einheit": date(jahr, 10, 3),
        "reformationstag": date(jahr, 10, 31),
        "allerheiligen": date(jahr, 11, 1),
        "buss_bettag": buss_und_bettag(jahr),
        "weihnachten1": date(jahr, 12, 25),
        "weihnachten2": date(jahr, 12, 26),
    }
    bundesweit = {"neujahr", "karfreitag", "ostermontag", "tag_der_arbeit",
                  "himmelfahrt", "pfingstmontag", "einheit",
                  "weihnachten1", "weihnachten2"}
    ergebnis = {}
    for schluessel, tag in kandidaten.items():
        if schluessel in bundesweit or schluessel in extra:
            ergebnis[tag.isoformat()] = FEIERTAG_NAMEN[schluessel]
    return ergebnis


def buss_und_bettag(jahr: int) -> date:
    """Der Mittwoch vor dem 23. November."""
    tag = date(jahr, 11, 23)
    return tag - timedelta(days=(tag.weekday() - 2) % 7 or 7)


def ist_feiertag(datum: str, land: str = None) -> str:
    """Gibt den Namen des Feiertags zurück, sonst einen leeren Text."""
    try:
        jahr = int(datum[:4])
    except (ValueError, TypeError):
        return ""
    return feiertage(jahr, land).get(datum, "")


@dataclass
class Notiz:
    id: int
    text: str
    angelegt_am: str = ""
    crew: str = ""
    angepinnt: bool = False

    def crew_kennung(self) -> str:
        if self.crew not in CREW:
            return ""
        anzeige, farbe, _ = CREW[self.crew]
        return f"{farbe}[{anzeige}]{RESET}"


@dataclass
class Notizblock:
    notizen: list[Notiz] = field(default_factory=list)
    naechste_id: int = 1

    def hinzufuegen(self, text: str, crew: str = "") -> Notiz:
        notiz = Notiz(self.naechste_id, text, date.today().isoformat(), crew, False)
        self.naechste_id += 1
        self.notizen.append(notiz)
        return notiz

    def finden(self, notiz_id: int) -> Notiz:
        for notiz in self.notizen:
            if notiz.id == notiz_id:
                return notiz
        raise ValueError(f"Notiz #{notiz_id} nicht gefunden")

    def sortiert(self) -> list[Notiz]:
        """Angepinnte zuerst, danach die neuesten."""
        return sorted(self.notizen, key=lambda n: (not n.angepinnt, -n.id))

    def angepinnte(self) -> list[Notiz]:
        return [n for n in self.notizen if n.angepinnt]


TAGE_KURZ = {"mo": 0, "di": 1, "mi": 2, "do": 3, "fr": 4, "sa": 5, "so": 6}
TAGE_ANZEIGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
TAGE_MUSTER = {
    "werktags": [0, 1, 2, 3, 4],
    "wochentags": [0, 1, 2, 3, 4],
    "wochenende": [5, 6],
    "taeglich": [0, 1, 2, 3, 4, 5, 6],
    "täglich": [0, 1, 2, 3, 4, 5, 6],
}


def zeit_parsen(text: str) -> str:
    """Prüft eine Uhrzeit und füllt auf HH:MM auf."""
    if not re.fullmatch(r"\d{1,2}:\d{1,2}", text):
        raise ValueError(f"'{text}' ist keine Uhrzeit")
    stunde, minute = text.split(":")
    if len(minute) != 2 or int(stunde) > 23 or int(minute) > 59:
        raise ValueError(f"'{text}' ist keine Uhrzeit. Erlaubt: 00:00 bis 23:59")
    return f"{int(stunde):02d}:{minute}"


def zeitspanne_parsen(text: str) -> tuple[str, str]:
    """08:00-16:26 oder 14:30 wird zu (von, bis)."""
    stuecke = text.split("-", 1)
    von = zeit_parsen(stuecke[0])
    bis = zeit_parsen(stuecke[1]) if len(stuecke) > 1 else ""
    if bis and bis <= von:
        raise ValueError("Das Ende muss nach dem Anfang liegen")
    return von, bis


def tage_parsen(text: str) -> list:
    """mo-fr, mi,fr, werktags, wochenende oder taeglich."""
    t = text.strip().lower()
    if t in TAGE_MUSTER:
        return list(TAGE_MUSTER[t])
    tage = set()
    for teil in t.split(","):
        teil = teil.strip()
        if "-" in teil:
            von, bis = teil.split("-", 1)
            if von not in TAGE_KURZ or bis not in TAGE_KURZ:
                raise ValueError(f"'{teil}' ist keine Wochentagsspanne, z.B. mo-fr")
            i, ziel = TAGE_KURZ[von], TAGE_KURZ[bis]
            while True:
                tage.add(i)
                if i == ziel:
                    break
                i = (i + 1) % 7
        elif teil in TAGE_KURZ:
            tage.add(TAGE_KURZ[teil])
        else:
            raise ValueError(f"'{teil}' ist kein Wochentag. "
                             f"Erlaubt: mo di mi do fr sa so, werktags, wochenende, taeglich")
    if not tage:
        raise ValueError("Keine Wochentage angegeben")
    return sorted(tage)


@dataclass
class Termin:
    id: int
    datum: str
    titel: str
    zeit: str = ""
    bis: str = ""
    ort: str = ""
    crew: str = ""
    regel_id: int = 0

    def crew_kennung(self) -> str:
        if self.crew not in CREW:
            return ""
        anzeige, farbe, _ = CREW[self.crew]
        return f"{farbe}[{anzeige}]{RESET}"

    def zeitangabe(self) -> str:
        if self.zeit and self.bis:
            return f"{self.zeit}-{self.bis}"
        return self.zeit if self.zeit else "ganztags"

    def kennung(self) -> str:
        return f"R{self.regel_id}" if self.regel_id else f"#{self.id}"


@dataclass
class Regel:
    """Ein wiederkehrender Termin, der nicht gespeichert, sondern berechnet wird."""
    id: int
    titel: str
    tage: list = field(default_factory=list)   # 0 = Montag
    zeit: str = ""
    bis: str = ""
    ort: str = ""
    crew: str = ""
    ohne_feiertage: bool = True
    ab: str = ""
    ende: str = ""
    ausnahmen: list = field(default_factory=list)   # Zeiträume [von, bis]

    def trifft_zu(self, datum: str) -> bool:
        try:
            d = date.fromisoformat(datum)
        except (ValueError, TypeError):
            return False
        if d.weekday() not in self.tage:
            return False
        if self.ab and datum < self.ab:
            return False
        if self.ende and datum > self.ende:
            return False
        for zeitraum in self.ausnahmen:
            if len(zeitraum) == 2 and zeitraum[0] <= datum <= zeitraum[1]:
                return False
        if self.ohne_feiertage and ist_feiertag(datum):
            return False
        return True

    def crew_kennung(self) -> str:
        if self.crew not in CREW:
            return ""
        anzeige, farbe, _ = CREW[self.crew]
        return f"{farbe}[{anzeige}]{RESET}"

    def tage_text(self) -> str:
        return ",".join(TAGE_ANZEIGE[t] for t in sorted(self.tage))

    def zeitangabe(self) -> str:
        if self.zeit and self.bis:
            return f"{self.zeit}-{self.bis}"
        return self.zeit if self.zeit else "ganztags"

    def als_termin(self, datum: str) -> Termin:
        return Termin(0, datum, self.titel, self.zeit, self.bis,
                      self.ort, self.crew, self.id)


@dataclass
class Kalender:
    termine: list[Termin] = field(default_factory=list)
    regeln: list = field(default_factory=list)
    naechste_id: int = 1
    naechste_regel_id: int = 1

    def hinzufuegen(self, datum: str, titel: str, zeit: str = "", bis: str = "",
                    ort: str = "", crew: str = "") -> Termin:
        termin = Termin(self.naechste_id, datum, titel, zeit, bis, ort, crew)
        self.naechste_id += 1
        self.termine.append(termin)
        return termin

    def regel_hinzufuegen(self, titel: str, tage: list, zeit: str = "", bis: str = "",
                          ort: str = "", crew: str = "",
                          ohne_feiertage: bool = True) -> Regel:
        regel = Regel(self.naechste_regel_id, titel, tage, zeit, bis, ort, crew,
                      ohne_feiertage)
        self.naechste_regel_id += 1
        self.regeln.append(regel)
        return regel

    def finden(self, termin_id: int) -> Termin:
        for termin in self.termine:
            if termin.id == termin_id:
                return termin
        raise ValueError(f"Termin #{termin_id} nicht gefunden")

    def regel_finden(self, regel_id: int) -> Regel:
        for regel in self.regeln:
            if regel.id == regel_id:
                return regel
        raise ValueError(f"Regel R{regel_id} nicht gefunden")

    def am_tag(self, datum: str) -> list[Termin]:
        """Feste Termine plus die aus den Regeln berechneten."""
        eintraege = [t for t in self.termine if t.datum == datum]
        eintraege += [r.als_termin(datum) for r in self.regeln if r.trifft_zu(datum)]
        return sorted(eintraege, key=lambda t: (t.zeit == "", t.zeit, t.titel))

    def im_monat(self, jahr: int, monat: int) -> list[Termin]:
        ergebnis = []
        for tag in range(1, tage_im_monat(jahr, monat) + 1):
            ergebnis += self.am_tag(f"{jahr:04d}-{monat:02d}-{tag:02d}")
        return ergebnis

    def tage_mit_eintraegen(self, jahr: int, monat: int) -> set:
        return {t.datum for t in self.im_monat(jahr, monat)}


NOTIZ_FELDER = {f.name for f in fields(Notiz)}
TERMIN_FELDER = {f.name for f in fields(Termin)}
REGEL_FELDER = {f.name for f in fields(Regel)}


# ---------------------------------------------------------------------------
# Finanzen. Bewusst nicht am Logbuch haengend, sondern einmal fuer alles:
# Geld ist Geld, gleich in welchem Logbuch man gerade arbeitet.
#
# Ein Posten ist entweder 'fix' (jeden Monat wieder, etwa Miete oder die
# Verguetung) oder 'bucht' (einmalig, an einem Datum). Das Vorzeichen des
# Betrags entscheidet ueber die Richtung: minus raus, plus rein.
# ---------------------------------------------------------------------------

FINANZ_DATEI = DATEN_ORDNER / "finanzen.json"
WAEHRUNG = "EUR"        # kein Eurozeichen: cp850 kennt es nicht


@dataclass
class Posten:
    id: int = 0
    art: str = "bucht"          # 'fix' oder 'bucht'
    titel: str = ""
    betrag: float = 0.0         # negativ = Ausgabe, positiv = Einnahme
    kategorie: str = ""
    datum: str = ""             # nur bei 'bucht'
    tag: int = 1                # nur bei 'fix': Tag im Monat

    def richtung(self) -> str:
        return "ein" if self.betrag >= 0 else "aus"


@dataclass
class Ziel:
    id: int = 0
    titel: str = ""
    zielbetrag: float = 0.0
    stand: float = 0.0
    frist: str = ""
    angelegt_am: str = ""

    def anteil(self) -> float:
        if self.zielbetrag <= 0:
            return 0.0
        return max(0.0, min(1.0, self.stand / self.zielbetrag))

    def rest(self) -> float:
        return max(0.0, self.zielbetrag - self.stand)


@dataclass
class Finanzen:
    posten: list = field(default_factory=list)
    ziele: list = field(default_factory=list)
    naechste_posten_id: int = 1
    naechste_ziel_id: int = 1

    def posten_anlegen(self, art, titel, betrag, kategorie="", datum="", tag=1):
        eintrag = Posten(self.naechste_posten_id, art, titel, round(betrag, 2),
                         kategorie, datum, tag)
        self.naechste_posten_id += 1
        self.posten.append(eintrag)
        return eintrag

    def posten_finden(self, posten_id: int) -> Posten:
        for eintrag in self.posten:
            if eintrag.id == posten_id:
                return eintrag
        raise ValueError(f"Posten #{posten_id} nicht gefunden")

    def ziel_anlegen(self, titel, zielbetrag, frist=""):
        eintrag = Ziel(self.naechste_ziel_id, titel, round(zielbetrag, 2), 0.0,
                       frist, date.today().isoformat())
        self.naechste_ziel_id += 1
        self.ziele.append(eintrag)
        return eintrag

    def ziel_finden(self, ziel_id: int) -> Ziel:
        for eintrag in self.ziele:
            if eintrag.id == ziel_id:
                return eintrag
        raise ValueError(f"Ziel #{ziel_id} nicht gefunden")

    def fixe(self) -> list:
        return [e for e in self.posten if e.art == "fix"]

    def im_monat(self, jahr: int, monat: int) -> list:
        """Alle Einzelbuchungen dieses Monats."""
        schema = f"{jahr:04d}-{monat:02d}"
        return [e for e in self.posten
                if e.art == "bucht" and e.datum.startswith(schema)]


POSTEN_FELDER = {f.name for f in fields(Posten)}
ZIEL_FELDER = {f.name for f in fields(Ziel)}


def finanzen_laden() -> Finanzen:
    if not FINANZ_DATEI.exists():
        return Finanzen()
    try:
        daten = json.loads(FINANZ_DATEI.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return Finanzen()
    posten = [Posten(**{f: v for f, v in e.items() if f in POSTEN_FELDER})
              for e in daten.get("posten", [])]
    ziele = [Ziel(**{f: v for f, v in e.items() if f in ZIEL_FELDER})
             for e in daten.get("ziele", [])]
    return Finanzen(
        posten=posten, ziele=ziele,
        naechste_posten_id=daten.get("naechste_posten_id",
                                     max((e.id for e in posten), default=0) + 1),
        naechste_ziel_id=daten.get("naechste_ziel_id",
                                   max((e.id for e in ziele), default=0) + 1))


def finanzen_speichern(finanzen: Finanzen) -> None:
    FINANZ_DATEI.parent.mkdir(parents=True, exist_ok=True)
    daten = {"version": DATEI_VERSION,
             "posten": [asdict(e) for e in finanzen.posten],
             "ziele": [asdict(e) for e in finanzen.ziele],
             "naechste_posten_id": finanzen.naechste_posten_id,
             "naechste_ziel_id": finanzen.naechste_ziel_id}
    FINANZ_DATEI.write_text(json.dumps(daten, ensure_ascii=False, indent=2),
                            encoding="utf-8")


def geld(betrag: float, breite: int = 0, vorzeichen: bool = False) -> str:
    """Deutsche Schreibweise: 1.234,56 - rechtsbuendig, wenn breite gesetzt ist."""
    text = f"{abs(betrag):,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    if betrag < 0:
        text = "-" + text
    elif vorzeichen and betrag > 0:
        text = "+" + text
    return text.rjust(breite) if breite else text


def betrag_parsen(text: str) -> float:
    """Nimmt 12,50 und 12.50, mit oder ohne Vorzeichen, auch '12,50 EUR'."""
    t = text.strip().upper().replace(WAEHRUNG, "").strip()
    t = t.replace(".", "").replace(",", ".") if "," in t else t.replace(" ", "")
    try:
        wert = float(t)
    except ValueError:
        raise ValueError(f"'{text.strip()}' ist kein Betrag")
    if wert == 0:
        raise ValueError("Ein Betrag von 0 bringt nichts")
    return round(wert, 2)


def posten_eingabe(rest: str, vorzeichen: int):
    """'43,20 Einkauf #Lebensmittel' wird zu Betrag, Titel und Kategorie."""
    teile = rest.strip().split()
    if not teile:
        raise ValueError("So geht es: <betrag> <titel> [#kategorie]")
    betrag = abs(betrag_parsen(teile[0])) * vorzeichen
    kategorie = ""
    worte = []
    for wort in teile[1:]:
        if wort.startswith("#") and len(wort) > 1:
            kategorie = wort[1:]
        else:
            worte.append(wort)
    titel = " ".join(worte)
    if not titel:
        raise ValueError("Ein Titel fehlt")
    return betrag, titel, kategorie


# ---------------------------------------------------------------------------
# Einkaufsliste. Wie die Finanzen einmal fuer alles, nicht je Logbuch.
# ---------------------------------------------------------------------------

EINKAUF_DATEI = DATEN_ORDNER / "einkauf.json"


@dataclass
class Einkauf:
    id: int = 0
    text: str = ""
    menge: str = ""
    erledigt: bool = False


@dataclass
class Einkaufsliste:
    posten: list = field(default_factory=list)
    naechste_id: int = 1

    def hinzufuegen(self, text: str, menge: str = "") -> Einkauf:
        eintrag = Einkauf(self.naechste_id, text, menge, False)
        self.naechste_id += 1
        self.posten.append(eintrag)
        return eintrag

    def finden(self, posten_id: int) -> Einkauf:
        for eintrag in self.posten:
            if eintrag.id == posten_id:
                return eintrag
        raise ValueError(f"Posten #{posten_id} nicht gefunden")

    def offen(self) -> list:
        return [e for e in self.posten if not e.erledigt]


EINKAUF_FELDER = {f.name for f in fields(Einkauf)}


def einkauf_laden() -> Einkaufsliste:
    if not EINKAUF_DATEI.exists():
        return Einkaufsliste()
    try:
        daten = json.loads(EINKAUF_DATEI.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return Einkaufsliste()
    posten = [Einkauf(**{f: v for f, v in e.items() if f in EINKAUF_FELDER})
              for e in daten.get("posten", [])]
    return Einkaufsliste(posten=posten,
                         naechste_id=daten.get("naechste_id",
                                               max((e.id for e in posten), default=0) + 1))


def einkauf_speichern(liste: Einkaufsliste) -> None:
    EINKAUF_DATEI.parent.mkdir(parents=True, exist_ok=True)
    EINKAUF_DATEI.write_text(json.dumps(
        {"version": DATEI_VERSION, "posten": [asdict(e) for e in liste.posten],
         "naechste_id": liste.naechste_id}, ensure_ascii=False, indent=2),
        encoding="utf-8")


def einkauf_anzeigen(liste: Einkaufsliste) -> None:
    offen = liste.offen()
    unterabschnitt("Einkaufsliste", f"{len(offen)} OFFEN VON {len(liste.posten)}")
    if not liste.posten:
        schreibe(f"{DUNKEL}{LAMPE}  leer. 'ek Milch' legt einen Posten an.{RESET}\n\n")
        return
    for e in liste.posten:
        menge = f"{e.menge} " if e.menge else ""
        text = kuerzen(f"{menge}{e.text}", BREITE - 12)
        if e.erledigt:
            schreibe(f"{DUNKEL}{LAMPE} {ZAHL}#{e.id:<4}{RESET}"
                     f"{DUNKEL}{STRICH}{text}{RESET}\n")
        else:
            schreibe(f"{DUNKEL}{LAMPE} {ZAHL}#{e.id:<4}{RESET}{HELL}{text}{RESET}\n")
    schreibe(f"\n{DUNKEL} 'ekh <id>' hakt ab, 'ekl <id>' loescht, "
             f"'ekx' raeumt alles Abgehakte weg.{RESET}\n\n")


def einkauf_anlegen(liste: Einkaufsliste, arg: str) -> Einkauf:
    """'2x Milch' oder '500g Mehl' trennt Menge und Ware, sonst alles Ware."""
    teile = arg.strip().split()
    if not teile:
        raise ValueError("Was soll auf die Liste?")
    menge = ""
    if len(teile) > 1 and re.fullmatch(r"\d+([.,]\d+)?(x|g|kg|ml|l|st|stk)?", teile[0], re.I):
        menge, teile = teile[0], teile[1:]
    text = " ".join(teile)
    if not text:
        raise ValueError("Was soll auf die Liste?")
    return liste.hinzufuegen(text, menge)


def notizen_laden(board_name: str) -> Notizblock:
    pfad = datei("notizen", board_name)
    if not pfad.exists():
        return Notizblock()
    daten = json.loads(pfad.read_text(encoding="utf-8"))
    version = daten.get("version", 1)
    notizen = []
    for n in daten.get("notizen", []):
        notiz = Notiz(**{f: v for f, v in n.items() if f in NOTIZ_FELDER})
        notiz.crew = crew_migrieren(notiz.crew, version)
        notizen.append(notiz)
    naechste = daten.get("naechste_id", max((n.id for n in notizen), default=0) + 1)
    return Notizblock(notizen=notizen, naechste_id=naechste)


def notizen_speichern(block: Notizblock, board_name: str) -> None:
    daten = {"version": DATEI_VERSION,
             "notizen": [asdict(n) for n in block.notizen],
             "naechste_id": block.naechste_id}
    datei("notizen", board_name).write_text(
        json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8")


def kalender_laden(board_name: str) -> Kalender:
    pfad = datei("kalender", board_name)
    if not pfad.exists():
        return Kalender()
    daten = json.loads(pfad.read_text(encoding="utf-8"))
    version = daten.get("version", 1)
    termine = []
    for t in daten.get("termine", []):
        termin = Termin(**{f: v for f, v in t.items() if f in TERMIN_FELDER})
        termin.crew = crew_migrieren(termin.crew, version)
        termine.append(termin)
    regeln = []
    for r in daten.get("regeln", []):
        regel = Regel(**{f: v for f, v in r.items() if f in REGEL_FELDER})
        regel.crew = crew_migrieren(regel.crew, version)
        regel.tage = [t for t in regel.tage if isinstance(t, int) and 0 <= t <= 6]
        regeln.append(regel)
    naechste = daten.get("naechste_id", max((t.id for t in termine), default=0) + 1)
    naechste_regel = daten.get("naechste_regel_id",
                               max((r.id for r in regeln), default=0) + 1)
    return Kalender(termine=termine, regeln=regeln, naechste_id=naechste,
                    naechste_regel_id=naechste_regel)


def kalender_speichern(kalender: Kalender, board_name: str) -> None:
    daten = {"version": DATEI_VERSION,
             "termine": [asdict(t) for t in kalender.termine],
             "regeln": [asdict(r) for r in kalender.regeln],
             "naechste_id": kalender.naechste_id,
             "naechste_regel_id": kalender.naechste_regel_id}
    datei("kalender", board_name).write_text(
        json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8")


def ausbuchen(board: Board, board_name: str, tage: int = None) -> tuple:
    """Erledigte Jobs aus dem Logbuch nehmen.

    Nichts geht verloren: die Eintraege wandern vorher in eine Archivdatei
    unter sitreps/. tage begrenzt auf Jobs, die laenger als so viele Tage
    abgeschlossen sind; ohne Angabe werden alle ausgebucht.
    """
    erledigt = list(board.spalten["Erledigt"])
    if not erledigt:
        raise ValueError("In 'Erledigt' liegt nichts")

    if tage is None:
        betroffen = erledigt
    else:
        grenze = (date.today() - timedelta(days=tage)).isoformat()
        # Ohne Abschlussdatum (alte Eintraege) gilt: alt genug
        betroffen = [k for k in erledigt
                     if not k.erledigt_am or k.erledigt_am in ("unbekannt",)
                     or k.erledigt_am <= grenze]
    if not betroffen:
        raise ValueError(f"Nichts ist aelter als {tage} Tage")

    heute = date.today().isoformat()
    pfad = SITREP_ORDNER / f"archiv_{board_name}_{heute}.md"
    zeilen = []
    if not pfad.exists():
        zeilen = [f"# {SCHIFF_NAME} - Ausgebuchte Jobs: {board_name}", ""]
    zeilen.append(f"## Ausgebucht am {datum_kurz(heute)} "
                  f"({mehrzahl(len(betroffen), 'Eintrag', 'Einträge')})")
    for k in sorted(betroffen, key=lambda k: k.erledigt_am or ""):
        wer = f" [{CREW[k.crew][0]}]" if k.crew in CREW else ""
        wann = f" (erledigt {k.erledigt_am})" if k.erledigt_am else ""
        zeilen.append(f"- [x]{wer} [{prio_anzeige(k.prioritaet)[0]}] {k.titel}{wann}")
        if k.beschreibung:
            zeilen.append(f"  - {k.beschreibung}")
    zeilen.append("")

    SITREP_ORDNER.mkdir(parents=True, exist_ok=True)
    with pfad.open("a", encoding="utf-8") as datei:
        datei.write("\n".join(zeilen))

    uebrig = [k for k in erledigt if k not in betroffen]
    board.spalten["Erledigt"] = uebrig
    return len(betroffen), len(uebrig), pfad


def exportieren(board: Board, board_name: str) -> Path:
    zeilen = [f"# {SCHIFF_NAME} - Logbuch: {board_name}", ""]
    for name, karten in board.spalten.items():
        zeilen.append(f"## {name} - {SPALTEN_INFO[name]}")
        for k in karten:
            haken = "x" if name == "Erledigt" else " "
            faellig = f" (bis {k.faelligkeit})" if k.faelligkeit else ""
            wer = f" [{CREW[k.crew][0]}]" if k.crew in CREW else ""
            prio = f" [{prio_anzeige(k.prioritaet)[0]}]"
            zeilen.append(f"- [{haken}]{wer}{prio} {k.titel}{faellig}")
            if k.beschreibung:
                zeilen.append(f"  - {k.beschreibung}")
        zeilen.append("")
    pfad = SITREP_ORDNER / f"board_{board_name}.md"
    pfad.write_text("\n".join(zeilen), encoding="utf-8")
    return pfad


SEKTOREN = [
    "Zeta 2 Reticuli, äußerer Rand",
    "LV-426, niedriger Orbit",
    "Thedus-Korridor, Sektor 7",
    "Gateway-Station, Anflug",
    "Fiorina-System, Driftbahn",
    "Weylandschneise, Quadrant 3",
    "Calpamos, Schattenseite",
]
KOMPONENTEN = [
    "Lebenserhaltung",
    "Navigation",
    "Antrieb",
    "Hydraulik",
    "Sensorik",
    "Luftschleuse",
    "Kühlkreislauf",
]
ORGANISMUS_RISIKO = 0.25  # mit dieser Wahrscheinlichkeit findet der Scan etwas

# Gegenmaßnahmen: Schlüssel -> (Befehl, Klartext)
MASSNAHMEN = {
    "purge": ("purge", "Lüftungsspülung"),
    "dekon": ("dekon", "Dekontamination"),
}

# Bereiche des Schiffs: Schlüssel -> Anzeigename auf der Karte (max. 9 Zeichen)
BEREICHE = {
    "BRUECKE": "BRUECKE",
    "LABOR": "LABOR",
    "MEDBAY": "MEDBAY",
    "KUECHE": "KUECHE",
    "FRACHT": "FRACHT",
    "KORRIDOR": "KORRIDOR",
    "QUARTIER": "QUARTIER",
    "SCHLEUSE": "SCHLEUSE",
    "LEBENSERH": "LEBENSERH",
    "HYDRAULIK": "HYDRAULIK",
    "ANTRIEB": "ANTRIEB",
}

# Aufbau der Minimap von vorn nach hinten. None ist eine Lücke.
SCHIFFSPLAN = [
    [None, "BRUECKE", None],
    ["LABOR", "MEDBAY", "KUECHE"],
    ["SCHLEUSE", "KORRIDOR", "QUARTIER"],
    ["FRACHT", "LEBENSERH", "HYDRAULIK"],
    [None, "ANTRIEB", None],
]

# Wohin sich eine Kontamination ausbreitet, wenn sie nicht behandelt wird
NACHBARN = {
    "BRUECKE": ["MEDBAY", "KORRIDOR"],
    "LABOR": ["MEDBAY", "SCHLEUSE"],
    "MEDBAY": ["KORRIDOR", "BRUECKE", "LABOR"],
    "KUECHE": ["MEDBAY", "QUARTIER"],
    "FRACHT": ["LEBENSERH", "SCHLEUSE"],
    "KORRIDOR": ["LEBENSERH", "MEDBAY", "QUARTIER", "SCHLEUSE"],
    "QUARTIER": ["KORRIDOR", "KUECHE", "HYDRAULIK"],
    "SCHLEUSE": ["KORRIDOR", "FRACHT", "LABOR"],
    "LEBENSERH": ["KORRIDOR", "FRACHT", "ANTRIEB"],
    "HYDRAULIK": ["ANTRIEB", "QUARTIER"],
    "ANTRIEB": ["LEBENSERH", "HYDRAULIK"],
}

# Was der Scan finden kann. gewicht steuert, wie häufig eine Anomalie vorkommt.
ANOMALIEN = [
    {"name": "XENOMORPH", "kategorie": "Makroorganismus", "gewicht": 3,
     "befund": "Bewegung im Lüftungsschacht an der Luftschleuse. Masse ca. 90 kg.",
     "massnahmen": {"purge"}, "bereich": "SCHLEUSE"},
    {"name": "SCHWARMKOLONIE", "kategorie": "Makroorganismus", "gewicht": 2,
     "befund": "Nestbildung hinter der Frachtraumverkleidung.",
     "massnahmen": {"purge"}, "bereich": "FRACHT"},
    {"name": "RANKENORGANISMUS", "kategorie": "Makroorganismus", "gewicht": 2,
     "befund": "Pflanzliche Masse wächst im Hydraulikschacht gegen die Luftrichtung.",
     "massnahmen": {"purge"}, "bereich": "HYDRAULIK"},
    {"name": "SPORENFILM", "kategorie": "Mikroorganismus", "gewicht": 3,
     "befund": "Biofilm auf den Wasserleitungen der Lebenserhaltung.",
     "massnahmen": {"dekon"}, "bereich": "LEBENSERH"},
    {"name": "MYZELBEFALL", "kategorie": "Mikroorganismus", "gewicht": 2,
     "befund": "Pilzgeflecht in der Luftaufbereitung der Mannschaftsquartiere.",
     "massnahmen": {"dekon"}, "bereich": "QUARTIER"},
    {"name": "FREMDE BAKTERIENKULTUR", "kategorie": "Mikroorganismus", "gewicht": 2,
     "befund": "Unbekannte Kultur in der Nahrungssynthese der Kombüse.",
     "massnahmen": {"dekon"}, "bereich": "KUECHE"},
    {"name": "UNBEKANNTE SIGNATUR", "kategorie": "Anomalie", "gewicht": 1,
     "befund": "Probe im Labor ist organisch und mineralisch zugleich. Kein Datenbanktreffer.",
     "massnahmen": {"purge", "dekon"}, "bereich": "LABOR"},
]
ANOMALIEN_NACH_NAME = {a["name"]: a for a in ANOMALIEN}

STUFEN_TEXT = {
    1: "Stufe 1 - lokal begrenzt",
    2: "Stufe 2 - breitet sich aus",
    3: "Stufe 3 - Schiff großflächig betroffen",
}

# Aktuelle Kontaminationslage. Wird mit dem Logbuch gespeichert.
LAGE = {"anomalie": None, "offen": set(), "seit": "", "stufe": 1, "bereiche": set()}

# Werte, die sich über die Sitzung langsam verändern, statt bei jedem Scan neu zu würfeln
SCHIFF = {"kraftstoff": None, "co2": None, "geschwindigkeit": None, "sektor": None, "scans": 0}


def lage_aktiv() -> bool:
    return LAGE["anomalie"] is not None


def lage_wuerfeln() -> None:
    """Zieht eine Anomalie nach Gewicht und setzt die Kontaminationslage."""
    anomalie = random.choices(ANOMALIEN, weights=[a["gewicht"] for a in ANOMALIEN])[0]
    LAGE["anomalie"] = anomalie
    LAGE["offen"] = set(anomalie["massnahmen"])
    LAGE["seit"] = f"{datetime.now():%Y-%m-%d %H:%M}"
    LAGE["stufe"] = 1
    LAGE["bereiche"] = {anomalie["bereich"]}


def lage_loeschen() -> None:
    LAGE["anomalie"] = None
    LAGE["offen"] = set()
    LAGE["seit"] = ""
    LAGE["stufe"] = 1
    LAGE["bereiche"] = set()


def lage_eskalieren() -> bool:
    """Hebt die Stufe an und breitet die Kontamination aus. True, wenn sich etwas ändert."""
    if not lage_aktiv() or LAGE["stufe"] >= 3:
        return False
    LAGE["stufe"] += 1
    # Pro Stufe kommen bis zu zwei angrenzende Bereiche dazu
    neu = 0
    for bereich in sorted(LAGE["bereiche"]):
        for nachbar in NACHBARN.get(bereich, []):
            if nachbar not in LAGE["bereiche"]:
                LAGE["bereiche"].add(nachbar)
                neu += 1
                if neu >= 2:
                    return True
    return True


def lage_zeilen() -> list[str]:
    """Kurzfassung der Lage für Scan, Sitrep und Boardkopf."""
    if not lage_aktiv():
        return []
    a = LAGE["anomalie"]
    offen = ", ".join(MASSNAHMEN[m][1] for m in sorted(LAGE["offen"]))
    befehle = ", ".join(f"'{MASSNAHMEN[m][0]}'" for m in sorted(LAGE["offen"]))
    bereiche = ", ".join(BEREICHE[b] for b in sorted(LAGE["bereiche"]))
    return [
        f"{a['name']} AN BORD ({a['kategorie'].upper()})",
        a["befund"],
        f"{STUFEN_TEXT[LAGE['stufe']]}  |  Erkannt: {LAGE['seit']}",
        f"Betroffen: {bereiche}",
        f"Offene Maßnahme: {offen}  ->  Befehl {befehle}",
    ]


# Welche Komponente in welchem Bereich sitzt
KOMPONENTEN_RAUM = {
    "Navigation": "BRUECKE",
    "Sensorik": "LABOR",
    "Lebenserhaltung": "LEBENSERH",
    "Hydraulik": "HYDRAULIK",
    "Luftschleuse": "SCHLEUSE",
    "Antrieb": "ANTRIEB",
    "Kühlkreislauf": "ANTRIEB",
}


def _box_oben(anschluss: bool) -> str:
    if anschluss:
        return ECKE_OL + WAAG * 5 + T_UNTEN + WAAG * 5 + ECKE_OR
    return ECKE_OL + WAAG * 11 + ECKE_OR


def _box_unten(anschluss: bool) -> str:
    if anschluss:
        return ECKE_UL + WAAG * 5 + T_OBEN + WAAG * 5 + ECKE_UR
    return ECKE_UL + WAAG * 11 + ECKE_UR


def _box_text(name: str, links: str = None, rechts: str = None) -> str:
    return (links or SENK) + name.center(11) + (rechts or SENK)


def schiffsplan() -> list[str]:
    """Rumpfschema mit drei Decks. Die Schächte zeigen, wie sich etwas ausbreitet."""
    l, m, r = 21, 38, 55          # Startspalten der drei Bereichssäulen
    quer_l, quer_m, quer_r = 27, 44, 61   # Mitten der Säulen
    sp = " "

    def quer(links_zeichen: str, mitte_zeichen: str, rechts_zeichen: str) -> str:
        return (sp * quer_l + links_zeichen + WAAG * (quer_m - quer_l - 1)
                + mitte_zeichen + WAAG * (quer_r - quer_m - 1) + rechts_zeichen)

    def dreierreihe(bauteil) -> str:
        return sp * l + bauteil + sp * (m - l - 13) + bauteil + sp * (r - m - 13) + bauteil

    return [
        sp * m + _box_oben(False),
        sp * m + _box_text("BRUECKE") + "   BUG",
        sp * m + _box_unten(True),
        quer(ECKE_OL, KREUZ, ECKE_OR),
        dreierreihe(_box_oben(True)),
        "  DECK A" + sp * (l - 8) + _box_text("LABOR") + sp * 4
        + _box_text("MEDBAY") + sp * 4 + _box_text("KUECHE"),
        dreierreihe(_box_unten(True)),
        quer(ECKE_UL, KREUZ, ECKE_UR),
        sp * l + _box_oben(False) + sp * 4 + _box_oben(True) + sp * 4 + _box_oben(False),
        "  DECK B" + sp * (l - 8) + _box_text("SCHLEUSE", rechts=T_LINKS)
        + WAAG * 4 + _box_text("KORRIDOR", links=T_RECHTS, rechts=T_LINKS)
        + WAAG * 4 + _box_text("QUARTIER", links=T_RECHTS),
        sp * l + _box_unten(False) + sp * 4 + _box_unten(True) + sp * 4 + _box_unten(False),
        sp * quer_m + SENK,
        quer(ECKE_OL, KREUZ, ECKE_OR),
        dreierreihe(_box_oben(True)),
        "  DECK C" + sp * (l - 8) + _box_text("FRACHT") + sp * 4
        + _box_text("LEBENSERH") + sp * 4 + _box_text("HYDRAULIK"),
        dreierreihe(_box_unten(True)),
        quer(ECKE_UL, KREUZ, ECKE_UR),
        sp * m + _box_oben(True),
        sp * m + _box_text("ANTRIEB") + "   HECK",
        sp * m + _box_unten(False),
    ]


PLAN = schiffsplan()
TRENNER = set(SENK + T_LINKS + T_RECHTS)


def _raum_positionen() -> dict:
    """Findet für jeden Bereich (Zeile, Startspalte, Breite) seines Textfelds."""
    positionen = {}
    for schluessel, anzeige in BEREICHE.items():
        for nr, zeile in enumerate(PLAN):
            stelle = zeile.find(anzeige)
            if stelle < 0:
                continue
            start = stelle
            while start > 0 and zeile[start - 1] not in TRENNER:
                start -= 1
            ende = stelle + len(anzeige)
            while ende < len(zeile) and zeile[ende] not in TRENNER:
                ende += 1
            positionen[schluessel] = (nr, start, ende - start)
            break
    return positionen


RAUM_POS = _raum_positionen()


def plan_zeilen(blink_an: bool) -> list[str]:
    """Baut den Plan mit roter Hervorhebung der kontaminierten Bereiche."""
    hervor = {}
    for schluessel in LAGE["bereiche"]:
        if schluessel in RAUM_POS:
            hervor.setdefault(RAUM_POS[schluessel][0], []).append(schluessel)
    fertig = []
    for nr, roh in enumerate(PLAN):
        if nr not in hervor:
            fertig.append(f"{DUNKEL}{roh}{RESET}")
            continue
        stuecke = []
        zeiger = 0
        for schluessel in sorted(hervor[nr], key=lambda s: RAUM_POS[s][1]):
            _, start, breite = RAUM_POS[schluessel]
            stuecke.append(f"{DUNKEL}{roh[zeiger:start]}{RESET}")
            text = roh[start:start + breite]
            if blink_an:
                stuecke.append(f"\033[7m{ROT}{text}{RESET}")
            else:
                stuecke.append(f"{ROT}{text}{RESET}")
            zeiger = start + breite
        stuecke.append(f"{DUNKEL}{roh[zeiger:]}{RESET}")
        fertig.append("".join(stuecke))
    return fertig


def bereichs_zustand(board: Board) -> dict:
    """Je Bereich: Kontamination, bedrohte Lage, Komponenten und Reparaturkarten."""
    heute = date.today().isoformat()
    zustand = {s: {"kontaminiert": s in LAGE["bereiche"], "bedroht": False,
                   "komponenten": [], "karten": []} for s in BEREICHE}
    # Bedroht sind die Nachbarn der betroffenen Bereiche
    for betroffen in LAGE["bereiche"]:
        for nachbar in NACHBARN.get(betroffen, []):
            if nachbar not in LAGE["bereiche"]:
                zustand[nachbar]["bedroht"] = True
    # Offene Reparaturen belegen Komponenten, die wiederum in Bereichen sitzen
    for k in board.spalten["Reparatur"]:
        komponente = KOMPONENTEN[k.id % len(KOMPONENTEN)]
        raum = KOMPONENTEN_RAUM.get(komponente, "KORRIDOR")
        kritisch = bool(k.faelligkeit) and k.faelligkeit < heute
        zustand[raum]["komponenten"].append((komponente, "Ausfall" if kritisch
                                             else "eingeschränkt"))
        zustand[raum]["karten"].append(k.id)
    return zustand


# ---------------------------------------------------------------------------
# Schiffradar. Die Kontakte sind die offenen Auftraege: je naeher am Zentrum,
# desto dringender. Das Zentrum ist das eigene Schiff, der Rand ist "irgendwann".
# ---------------------------------------------------------------------------

RADAR_R = 9                    # Zeilen vom Zentrum zum Rand
RADAR_UMLAeUFE = 2             # wie oft der Strahl herumgeht
RADAR_SCHRITTE = 30            # Bilder je Umlauf

# Entfernung aus der Frist: ueberfaellig sitzt einem im Nacken
RADAR_STUFEN = [
    (-10000, 0.16, "AUF KOLLISIONSKURS"),
    (0, 0.30, "HEUTE FAELLIG"),
    (1, 0.44, "IN TAGEN"),
    (4, 0.58, "DIESE WOCHE"),
    (8, 0.74, "DIESEN MONAT"),
    (31, 0.90, "FERNE"),
]
RADAR_ZEICHEN = {4: "█", 3: "▓", 2: "▒", 1: "░"}


def radar_kontakte(board: Board) -> list:
    """Offene Auftraege als Kontakte: Winkel, Entfernung, Staerke."""
    heute = date.today()
    kontakte = []
    for k in board.offen():
        if k.faelligkeit:
            try:
                tage = (date.fromisoformat(k.faelligkeit) - heute).days
            except ValueError:
                tage = 999
        else:
            tage = 999
        entfernung, lage_text = RADAR_STUFEN[-1][1], RADAR_STUFEN[-1][2]
        for grenze, wert, text in RADAR_STUFEN:
            if tage >= grenze:
                entfernung, lage_text = wert, text
        # Der Winkel haengt an der Nummer, damit ein Kontakt nicht herumspringt
        winkel = (k.id * 137) % 360
        kontakte.append({"karte": k, "winkel": winkel, "entfernung": entfernung,
                         "tage": tage, "lage": lage_text,
                         "zeichen": RADAR_ZEICHEN.get(k.prioritaet, "░")})
    return sorted(kontakte, key=lambda c: (c["entfernung"], -c["karte"].prioritaet))


def radar_bild(kontakte: list, strahl, erfasst: set) -> list:
    """Ein Einzelbild des Radars. strahl=None zeichnet das Bild ohne Strahl."""
    breite = RADAR_R * 2
    zeilen = []
    for y in range(-RADAR_R, RADAR_R + 1):
        stuecke = []
        for x in range(-breite, breite + 1):
            rx, ry = x / 2.0, float(y)
            abstand = math.hypot(rx, ry)
            if abstand > RADAR_R + 0.4:
                stuecke.append(" ")
                continue
            # Winkel dieser Zelle, 0 Grad ist oben, im Uhrzeigersinn
            grad = (math.degrees(math.atan2(rx, -ry))) % 360
            # Nachleuchten hinter dem Strahl, oder gar keiner
            hinter = 999.0 if strahl is None else (strahl - grad) % 360
            zeichen, farbe = " ", DUNKEL
            if abs(abstand - RADAR_R) < 0.45:
                zeichen, farbe = "·", DUNKEL
            elif abs(abstand - RADAR_R * 2 / 3) < 0.35 or abs(abstand - RADAR_R / 3) < 0.35:
                zeichen, farbe = "·", DUNKEL
            elif abstand < 0.3:
                zeichen, farbe = "┼", HELL
            elif abs(rx) < 0.3 or abs(ry) < 0.3:
                zeichen, farbe = "·", DUNKEL
            # Der Strahl selbst, dahinter ein kurzes Nachleuchten. Mehr nicht,
            # sonst verschwinden die Kontakte im Gewisch.
            if hinter < 5:
                zeichen, farbe = "█", HELL
            elif hinter < 14:
                zeichen, farbe = "▒", HELL
            stuecke.append((zeichen, farbe))
        zeilen.append(stuecke)

    # Kontakte einzeichnen, sobald der Strahl sie einmal gestreift hat
    for nummer, c in enumerate(kontakte):
        if nummer not in erfasst:
            continue
        rad = math.radians(c["winkel"])
        rx = math.sin(rad) * c["entfernung"] * RADAR_R
        ry = -math.cos(rad) * c["entfernung"] * RADAR_R
        x = int(round(rx * 2)) + breite
        y = int(round(ry)) + RADAR_R
        if 0 <= y < len(zeilen) and 0 <= x < len(zeilen[y]):
            prio = c["karte"].prioritaet
            farbe = ROT if prio >= 4 else AKZENT if prio == 3 else HELL
            zeilen[y][x] = (c["zeichen"], farbe)

    # Zu Text zusammensetzen, Farbwechsel nur wo noetig
    fertig = []
    for stuecke in zeilen:
        text, letzte = "", None
        for s in stuecke:
            if s == " ":
                text += " "
                continue
            zeichen, farbe = s
            if farbe != letzte:
                text += RESET + farbe
                letzte = farbe
            text += zeichen
        fertig.append(" " + text + RESET)
    return fertig


def radar_legende(kontakte: list, erfasst: set) -> list:
    """Die Kontaktliste neben dem Schirm."""
    zeilen = [f"{DUNKEL}KONTAKTE{RESET}",
              f"{DUNKEL}{WAAG * 32}{RESET}"]
    if not kontakte:
        zeilen.append(f"{HELL}Schirm frei. Nichts offen.{RESET}")
        return zeilen
    for nummer, c in enumerate(kontakte[:12]):
        if nummer not in erfasst:
            zeilen.append(f"{DUNKEL}   ...{RESET}")
            continue
        k = c["karte"]
        prio = k.prioritaet
        farbe = ROT if prio >= 4 else AKZENT if prio == 3 else HELL
        peilung = f"{c['winkel']:03d}"
        entfernung = f"{c['entfernung'] * 100:.0f}"
        zeilen.append(f"{farbe}{c['zeichen']} {peilung}  {entfernung:>3}  "
                      f"{kuerzen(k.titel, 20)}{RESET}")
    if len(kontakte) > 12:
        zeilen.append(f"{DUNKEL}+ {len(kontakte) - 12} weitere{RESET}")
    return zeilen


def radar(board: Board) -> None:
    """Der Rundsuchlauf. Einmalige Animation, danach steht das Bild."""
    kontakte = radar_kontakte(board)
    kopfzeile("Rundsuchlauf", f"{len(kontakte)} KONTAKTE", augenbraue="Schiffradar")
    kennwerte([("Reichweite", "ORBITAL"), ("Modus", "AKTIV"),
               ("Ziele", len(kontakte)),
               ("Davon kritisch", sum(1 for c in kontakte
                                      if c["karte"].prioritaet >= 4))])
    klang("scan")

    erfasst: set = set()
    hoehe = RADAR_R * 2 + 1
    schreibe("\n")
    gezeichnet = False
    for umlauf in range(RADAR_UMLAeUFE):
        for schritt in range(RADAR_SCHRITTE):
            strahl = schritt * 360.0 / RADAR_SCHRITTE
            # Was der Strahl gerade ueberstreicht, gilt ab jetzt als erfasst
            for nummer, c in enumerate(kontakte):
                if nummer in erfasst:
                    continue
                if (strahl - c["winkel"]) % 360 < 360.0 / RADAR_SCHRITTE:
                    erfasst.add(nummer)
                    if c["karte"].prioritaet >= 3:
                        klang("ping")
            bild = radar_bild(kontakte, strahl, erfasst)
            legende = radar_legende(kontakte, erfasst)
            if gezeichnet:
                schreibe(f"\033[{hoehe}A")
            for i in range(hoehe):
                links = bild[i] if i < len(bild) else " " * (RADAR_R * 4 + 2)
                rechts = legende[i] if i < len(legende) else ""
                schreibe(f"\r\033[K{(links + '  ' + rechts).rstrip()}\n")
            gezeichnet = True
            time.sleep(0.045)
    # Ruhiges Standbild: Strahl weg, alle Kontakte stehen
    erfasst = set(range(len(kontakte)))
    bild = radar_bild(kontakte, None, erfasst)
    legende = radar_legende(kontakte, erfasst)
    schreibe(f"\033[{hoehe}A")
    for i in range(hoehe):
        links = bild[i] if i < len(bild) else " " * (RADAR_R * 4 + 2)
        rechts = legende[i] if i < len(legende) else ""
        schreibe(f"\r\033[K{(links + '  ' + rechts).rstrip()}\n")
    schreibe(f"\n{DUNKEL} Peilung in Grad, Entfernung 0 bis 100. "
             f"Naeher am Zentrum heisst dringender.{RESET}\n")
    nah = [c for c in kontakte if c["entfernung"] <= 0.30]
    if nah:
        funkspruch(f"{mehrzahl(len(nah), 'Kontakt', 'Kontakte')} im Nahbereich. "
                   f"{kuerzen(nah[0]['karte'].titel, 30)} fuehrt.", "muthur")
    schreibe("\n")


def schiffskarte(board: Board, blinken: int = 6) -> None:
    """Rumpfschema, Zustandstabelle und Ausbreitungspfad."""
    kopfzeile("Rumpfschema", "BLICK VON OBEN")
    zeilen = plan_zeilen(True)
    schreibe("\n".join(zeilen) + "\n")
    hoehe = len(zeilen)
    if LAGE["bereiche"]:
        for i in range(blinken):
            time.sleep(0.28)
            schreibe(f"\033[{hoehe}A")  # Cursor an den Planbeginn zurück
            schreibe("\n".join(plan_zeilen(i % 2 == 1)) + "\n")
            if i % 2 == 0:
                klang("alarm_puls", (220, 60))
        if blinken:
            schreibe(f"\033[{hoehe}A" + "\n".join(plan_zeilen(True)) + "\n")

    zustand = bereichs_zustand(board)
    spaltenkopf("Bereiche", len(BEREICHE), "ZUSTAND JE ABSCHNITT")
    for schluessel, anzeige in BEREICHE.items():
        z = zustand[schluessel]
        if z["kontaminiert"]:
            lage_text, farbe = "KONTAMINIERT", ROT
        elif z["bedroht"]:
            lage_text, farbe = "bedroht", AKZENT
        else:
            lage_text, farbe = "frei", DUNKEL
        bauteile = ", ".join(f"{name}: {stand}" for name, stand in z["komponenten"])
        if not bauteile:
            eigene = [n for n, r in KOMPONENTEN_RAUM.items() if r == schluessel]
            bauteile = ", ".join(f"{n}: nominal" for n in eigene) or "-"
        karten = " ".join(f"#{i}" for i in z["karten"])
        bauteil_feld = kuerzen(bauteile, 40)
        if karten:
            bauteil_feld = bauteil_feld.ljust(40)
        schreibe(f"{DUNKEL}{LAMPE} {RESET}{farbe}{anzeige:<11}{lage_text:<14}{RESET}"
                 f"{DUNKEL}{bauteil_feld}{RESET}{ZAHL}{karten}{RESET}\n")
    spaltenfuss()

    if LAGE["bereiche"]:
        a = LAGE["anomalie"]
        bedroht = sorted(BEREICHE[s] for s in BEREICHE if zustand[s]["bedroht"])
        absatz(f"{a['name']} ({a['kategorie']}), "
               f"{STUFEN_TEXT[LAGE['stufe']]}", ROT)
        if LAGE["stufe"] < 3 and bedroht:
            schreibe(f"{AKZENT} Ausbreitung droht nach: {kuerzen(', '.join(bedroht), 52)}"
                     f"{RESET}\n")
        befehle = ", ".join(f"'{MASSNAHMEN[m][0]}'" for m in sorted(LAGE["offen"]))
        schreibe(f"{AKZENT} Maßnahme: {befehle}{RESET}\n")
    else:
        schreibe(f"{HELL} Alle Bereiche frei. Keine Kontamination gemeldet.{RESET}\n")
    schreibe(f"{DUNKEL} Legende: invers rot = kontaminiert, "
             f"Linien = Schächte und Gänge{RESET}\n\n")


def schiff_init() -> None:
    SCHIFF["kraftstoff"] = random.uniform(62, 94)
    SCHIFF["co2"] = random.uniform(380, 520)
    SCHIFF["geschwindigkeit"] = random.uniform(0.22, 0.58)
    SCHIFF["sektor"] = random.choice(SEKTOREN)
    SCHIFF["scans"] = 0


def balken(wert: float, breite: int = 14) -> str:
    n = max(0, min(breite, round(wert * breite / 100)))
    return "#" * n + "." * (breite - n)


def mess_zeile(label: str, wert: str, zustand: str, anteil: float = None) -> None:
    """Eine Messzeile des Scans. zustand ist ok, warnung oder alarm."""
    farbe = {"ok": DUNKEL, "warnung": AKZENT, "alarm": ROT}[zustand]
    marke = {"ok": "OK", "warnung": "WARNUNG", "alarm": "ALARM"}[zustand]
    grafik = f" [{balken(anteil)}]" if anteil is not None else " " * 17
    schreibe(f"{farbe}  {label:<22}{wert:>14}{grafik}  {marke}{RESET}\n")
    time.sleep(0.1)


def alarm_blinken(text: str, runden: int = 3) -> None:
    klang("alarm", (220, 150))
    for _ in range(runden):
        schreibe(f"\r\033[K{ALARM_STIL}  {text}  {RESET}")
        time.sleep(0.2)
        schreibe("\r\033[K")
        time.sleep(0.12)
    schreibe(f"{ROT}  {text}{RESET}\n")


def schiffswerte(board: Board) -> dict:
    """Berechnet alle Messwerte, ohne etwas zu verändern. Für Scan und Homescreen."""
    heute = date.today().isoformat()
    reparaturen = board.spalten["Reparatur"]
    wartungen = board.spalten["Wartung"]
    ueberfaellig = [k for k in board.offen() if k.faelligkeit and k.faelligkeit < heute]

    befall = lage_aktiv()
    kategorie = LAGE["anomalie"]["kategorie"] if befall else ""
    stufe = LAGE["stufe"] if befall else 0
    makro = kategorie in ("Makroorganismus", "Anomalie")
    mikro = kategorie in ("Mikroorganismus", "Anomalie")

    rumpf = max(0.0, 100.0 - 7.0 * len(reparaturen) - 4.0 * len(ueberfaellig)
                - (12.0 * stufe if makro else 0.0))
    kraftstoff = SCHIFF["kraftstoff"]
    co2 = (SCHIFF["co2"] or 0.0) + 28.0 * len(wartungen) + (380.0 * stufe if mikro else 0.0)

    return {
        "gemessen": kraftstoff is not None,
        "rumpf": rumpf,
        "rumpf_zustand": "ok" if rumpf >= 80 else "warnung" if rumpf >= 50 else "alarm",
        "kraftstoff": kraftstoff if kraftstoff is not None else 0.0,
        "kraftstoff_zustand": ("ok" if (kraftstoff or 0) >= 35
                               else "warnung" if (kraftstoff or 0) >= 15 else "alarm"),
        "co2": co2,
        "co2_zustand": "ok" if co2 < 800 else "warnung" if co2 < 1200 else "alarm",
        "befall": befall,
        "kategorie": kategorie,
        "stufe": stufe,
        "makro": makro,
        "mikro": mikro,
        "reparaturen": len(reparaturen),
        "wartungen": len(wartungen),
        "ueberfaellig": len(ueberfaellig),
    }


def naechster_feiertag(ab: str = None) -> tuple:
    """Nächster Feiertag ab dem Datum. Sucht bis ins Folgejahr."""
    ab = ab or date.today().isoformat()
    jahr = int(ab[:4])
    for j in (jahr, jahr + 1):
        tage = feiertage(j)
        for d in sorted(tage):
            if d >= ab:
                return d, tage[d]
    return None, ""


def scan(board: Board) -> None:
    """Diagnose des Schiffs. Der Zustand hängt an den offenen Karten des Boards."""
    if SCHIFF["kraftstoff"] is None:
        schiff_init()
    SCHIFF["scans"] += 1
    SYSTEM["letzter_scan"] = date.today().isoformat()
    SCHIFF["kraftstoff"] = max(0.0, SCHIFF["kraftstoff"] - random.uniform(0.2, 0.8))
    SCHIFF["geschwindigkeit"] = max(0.05, SCHIFF["geschwindigkeit"] + random.uniform(-0.03, 0.03))
    if random.random() < 0.15:
        SCHIFF["sektor"] = random.choice(SEKTOREN)

    heute = date.today().isoformat()
    reparaturen = board.spalten["Reparatur"]
    wartungen = board.spalten["Wartung"]
    ueberfaellig = [k for k in board.offen() if k.faelligkeit and k.faelligkeit < heute]

    schreibe(f"\n{AKZENT}  {SCHIFF_NAME} - DIAGNOSE {SCHIFF['scans']:03d}{RESET}\n")
    klang("scan")
    for i in range(26):
        schreibe(f"\r{AKZENT}  [{'.' * i}###{'.' * (25 - i)}] SCANNE{RESET}")
        time.sleep(0.025)
    schreibe("\r\033[K\n")

    alarme: list[str] = []

    # Erst die Lage bestimmen, denn eine Kontamination verschlechtert die Messwerte.
    # Eine laufende Lage bleibt bestehen, bis sie behandelt ist, sonst wird gewürfelt.
    neu_entdeckt = False
    eskaliert = False
    if not lage_aktiv():
        if random.random() < ORGANISMUS_RISIKO:
            lage_wuerfeln()
            neu_entdeckt = True
    else:
        # Wer nichts unternimmt, lässt die Lage schlimmer werden
        eskaliert = lage_eskalieren()
    werte = schiffswerte(board)
    befall = werte["befall"]
    kategorie = werte["kategorie"]
    stufe = werte["stufe"]
    makro = werte["makro"]

    # Rumpf und Gesamtfunktionalität: jede offene Reparatur und jede Überfälligkeit kostet
    rumpf = werte["rumpf"]
    zustand = werte["rumpf_zustand"]
    mess_zeile("Rumpfintegrität", f"{rumpf:.1f} %", zustand, rumpf)
    if zustand == "alarm":
        alarme.append("RUMPFINTEGRITÄT KRITISCH")

    # Kraftstoff
    kraftstoff = werte["kraftstoff"]
    zustand = werte["kraftstoff_zustand"]
    mess_zeile("Kraftstoff", f"{kraftstoff:.1f} %", zustand, kraftstoff)
    if zustand == "alarm":
        alarme.append("KRAFTSTOFF UNTER RESERVE")

    # CO2: jede offene Wartung treibt den Wert hoch, ein Mikrobefall zusätzlich
    co2 = werte["co2"]
    zustand = werte["co2_zustand"]
    mess_zeile("CO2-Gehalt", f"{co2:.0f} ppm", zustand, min(100.0, co2 / 20))
    if zustand == "alarm":
        alarme.append("CO2 ÜBER GRENZWERT - FILTER PRÜFEN")

    # Fremde Organismen: nur ja oder nein
    mess_zeile("Fremde Organismen", "JA" if befall else "NEIN",
               "alarm" if befall else "ok")
    if befall:
        mess_zeile("  Kategorie", kategorie, "alarm")
        mess_zeile("  Ausbreitung", f"Stufe {stufe} / 3", "alarm")
        mess_zeile("  Bereiche betroffen", f"{len(LAGE['bereiche'])} von {len(BEREICHE)}",
                   "alarm")
        alarme.append(f"{LAGE['anomalie']['name']} AN BORD")
        if stufe >= 3:
            alarme.append("LEBENSERHALTUNG GEFÄHRDET - SOFORT HANDELN")

    # Komponenten: jede offene Reparaturkarte belegt eine Komponente
    belastet: dict[str, bool] = {}
    for k in reparaturen:
        name = KOMPONENTEN[k.id % len(KOMPONENTEN)]
        kritisch = bool(k.faelligkeit) and k.faelligkeit < heute
        belastet[name] = belastet.get(name, False) or kritisch
    schreibe(f"{DUNKEL}  --- KOMPONENTEN ---{RESET}\n")
    for name in KOMPONENTEN:
        if name not in belastet:
            mess_zeile(f"  {name}", "nominal", "ok")
        elif belastet[name]:
            mess_zeile(f"  {name}", "Ausfall", "alarm")
            alarme.append(f"{name.upper()} AUSGEFALLEN")
        else:
            mess_zeile(f"  {name}", "eingeschränkt", "warnung")

    # Flug und Verbindung
    schreibe(f"{DUNKEL}  --- FLUG UND FUNK ---{RESET}\n")
    mess_zeile("Geschwindigkeit", f"{SCHIFF['geschwindigkeit']:.3f} c", "ok")
    # Der Sektorname ist zu lang für die Messspalte, darum eine eigene Zeile
    schreibe(f"{DUNKEL}  {'Position':<22}{SCHIFF['sektor']}{RESET}\n")
    time.sleep(0.1)
    signal = random.uniform(55, 99) - (40 if makro else 0)
    zustand = "ok" if signal >= 60 else "warnung" if signal >= 25 else "alarm"
    mess_zeile("Mothership-Verbindung", f"{max(0.0, signal):.0f} %", zustand, max(0.0, signal))
    if zustand == "alarm":
        alarme.append("VERBINDUNG ZUM MOTHERSHIP VERLOREN")

    schreibe(f"\n{HELL}  Offen: {len(board.spalten['Befehle'])} Befehle, "
             f"{len(wartungen)} Wartungen, {len(reparaturen)} Reparaturen, "
             f"{len(ueberfaellig)} überfällig.{RESET}\n")
    if alarme:
        schreibe("\n")
        for text in alarme:
            alarm_blinken(text)
        if befall:
            kopf, befund, stufen_info, bereiche, massnahme = lage_zeilen()
            if neu_entdeckt:
                vorsatz = "ERSTMELDUNG"
            elif eskaliert:
                vorsatz = "LAGE VERSCHLECHTERT"
            else:
                vorsatz = "LAGE UNVERÄNDERT"
            if neu_entdeckt and LAGE["anomalie"]:
                art_begegnung(LAGE["anomalie"])
            absatz(f"{vorsatz}: {befund}", ROT)
            schreibe(f"{DUNKEL}  {kuerzen(stufen_info, BREITE - 3)}{RESET}\n")
            schreibe(f"{DUNKEL}  {kuerzen(bereiche, BREITE - 3)}{RESET}\n")
            schreibe(f"{AKZENT}  {kuerzen(massnahme, BREITE - 3)}{RESET}\n")
            schreibe(f"{DUNKEL}  Karte mit 'map' ansehen.{RESET}\n")
        schreibe("\n")
    else:
        schreibe(f"{HELL}  ALLE SYSTEME IM GRÜNEN BEREICH.{RESET}\n\n")
        klang("ok", (990, 60))


DECKS = ["DECK A", "DECK B", "DECK C", "FRACHTRAUM", "MASCHINENRAUM"]


def ablauf_balken(label: str, dauer: float = 1.0, breite: int = 22) -> None:
    for i in range(breite + 1):
        schreibe(f"\r{AKZENT}  {label} [{'#' * i}{'.' * (breite - i)}] "
                 f"{i * 100 // breite:3d}%{RESET}")
        time.sleep(dauer / breite)
    klang("ping")
    schreibe("\n")


def massnahme(schluessel: str, board: Board) -> None:
    """Führt purge oder dekon aus und räumt die Lage auf, wenn es die richtige Maßnahme ist."""
    befehl, klartext = MASSNAHMEN[schluessel]
    schreibe(f"\n{AKZENT}  {klartext.upper()} EINGELEITET{RESET}\n")

    if schluessel == "purge":
        schreibe(f"{DUNKEL}  Schotten werden verriegelt ...{RESET}\n")
        time.sleep(0.3)
        for deck in DECKS:
            schreibe(f"{DUNKEL}  {deck:<16}LUFT ABGELASSEN{RESET}\n")
            klang("purge", (520, 40))
            time.sleep(0.12)
        ablauf_balken("DRUCKABFALL   ", 1.2)
        schreibe(f"{DUNKEL}  Lüftung läuft mit 400 % ...{RESET}\n")
        time.sleep(0.4)
        ablauf_balken("DRUCKAUFBAU   ", 1.2)
    else:
        schreibe(f"{DUNKEL}  Dekontaminationsmittel wird verteilt ...{RESET}\n")
        time.sleep(0.3)
        for deck in DECKS:
            schreibe(f"{DUNKEL}  {deck:<16}UV-ZYKLUS + SPÜLUNG{RESET}\n")
            klang("dekon", (760, 40))
            time.sleep(0.12)
        ablauf_balken("DEKONTAMINATION", 1.6)
        schreibe(f"{DUNKEL}  Filter werden gewechselt ...{RESET}\n")
        time.sleep(0.4)

    if not lage_aktiv():
        schreibe(f"{HELL}  Durchlauf beendet. Keine Kontamination vorhanden, "
                 f"keine Rückstände gefunden.{RESET}\n\n")
        klang("ok", (880, 60))
        return

    a = LAGE["anomalie"]
    if schluessel not in a["massnahmen"]:
        # Falsche Maßnahme: die Lage bleibt bestehen, der Konzern zählt mit
        richtig = ", ".join(f"'{MASSNAHMEN[m][0]}'" for m in sorted(LAGE["offen"]))
        schreibe(f"{ROT}  Durchlauf beendet, aber {a['name']} ist unbeeindruckt.{RESET}\n")
        funkspruch(f"Falsche Maßnahme für {a['kategorie']}. "
                   f"Richtig wäre: {richtig}", "muthur", leise=True)
        SYSTEM["fehlgriffe"] = SYSTEM.get("fehlgriffe", 0) + 1
        stufe = min(3, SYSTEM["fehlgriffe"])
        funkspruch(fuellen(random.choice(FEHLGRIFF[stufe]), board), "wy")
        schreibe("\n")
        klang("fehler", (220, 200))
        return

    LAGE["offen"].discard(schluessel)
    if LAGE["offen"]:
        offen = ", ".join(f"'{MASSNAHMEN[m][0]}'" for m in sorted(LAGE["offen"]))
        schreibe(f"{AKZENT}  Teilerfolg. {a['name']} ist zurückgedrängt, "
                 f"aber nicht beseitigt.{RESET}\n")
        schreibe(f"{AKZENT}  Noch offen: {offen}{RESET}\n\n")
        klang("warnung", (440, 120))
        return

    if LAGE["stufe"] >= 3:
        schreibe(f"{HELL}  Knapp. {a['name']} hatte schon {len(LAGE['bereiche'])} "
                 f"Bereiche erfasst.{RESET}\n")
    schreibe(f"{HELL}  {a['name']} beseitigt. Lage bereinigt.{RESET}\n")
    schreibe(f"{DUNKEL}  Luftqualität nominal. Quarantäne aufgehoben.{RESET}\n\n")
    lage_loeschen()
    klang("erfolg", (880, 120))


def sitrep(board: Board, board_name: str, kalender: "Kalender" = None,
           notizen: "Notizblock" = None) -> Path:
    """Lagebericht für den heutigen Tag, auf dem Bildschirm und als Datei."""
    heute = date.today()
    heute_iso = heute.isoformat()
    zeilen = [
        f"# SITREP {heute_iso} - {SCHIFF_NAME}",
        "",
        f"Besatzung an der Konsole: {NAME}",
        f"Logbuch: {board_name}",
        "",
    ]

    def einordnen(k: Karte) -> str:
        if not k.faelligkeit:
            return "ohne Termin"
        if k.faelligkeit < heute_iso:
            tage = (heute - date.fromisoformat(k.faelligkeit)).days
            return f"ÜBERFÄLLIG seit {tage} Tag(en)"
        if k.faelligkeit == heute_iso:
            return "heute fällig"
        return f"fällig bis {k.faelligkeit}"

    schreibe(f"\n{AKZENT}  SITREP {heute_iso} - {SCHIFF_NAME}{RESET}\n")
    schreibe(f"{DUNKEL}  {'=' * 58}{RESET}\n")
    kopf = random.choice(SITREP_KOPF)
    schreibe(f"{DUNKEL}  {kopf}{RESET}\n")
    zeilen += [f"_{kopf}_", ""]

    # Was ansteht, nach Spalte getrennt und innerhalb nach Dringlichkeit sortiert
    for spalte in ("Reparatur", "Wartung", "Befehle"):
        karten = sorted(
            board.spalten[spalte],
            key=lambda k: (k.faelligkeit or "9999-99-99", -k.prioritaet),
        )
        schreibe(f"\n{HELL}  {spalte.upper()} ({len(karten)}){RESET}"
                 f"{DUNKEL}  {SPALTEN_INFO[spalte]}{RESET}\n")
        zeilen += ["", f"## {spalte} ({len(karten)})", ""]
        if not karten:
            schreibe(f"{DUNKEL}    nichts offen{RESET}\n")
            zeilen.append("- nichts offen")
            continue
        for k in karten:
            lage = einordnen(k)
            farbe = ROT if lage.startswith("ÜBERFÄLLIG") else HELL
            prio_text, prio_farbe = prio_anzeige(k.prioritaet)
            schreibe(f"{ZAHL}    #{k.id:<3}{RESET} {k.crew_kennung()} "
                     f"{prio_farbe}{prio_text:<9}{RESET}"
                     f"{farbe}{kuerzen(k.titel, 30)}{RESET} {DUNKEL}({lage}){RESET}\n")
            wer = f" [{CREW[k.crew][0]}]" if k.crew in CREW else ""
            zeilen.append(f"- #{k.id}{wer} [{prio_text}] {k.titel} ({lage})")
            time.sleep(0.04)

    # Was heute erledigt wurde
    heute_fertig = [k for k in board.spalten["Erledigt"] if k.erledigt_am == heute_iso]
    unterabschnitt("Heute erledigt", mehrzahl(len(heute_fertig), "EINTRAG", "EINTRÄGE"))
    zeilen += ["", f"## Heute erledigt ({len(heute_fertig)})", ""]
    if not heute_fertig:
        schreibe(f"{DUNKEL}    noch nichts{RESET}\n")
        zeilen.append("- noch nichts")
    for k in heute_fertig:
        schreibe(f"{ZAHL}    #{k.id:<3}{RESET} {k.crew_kennung()} {HELL}{k.titel}{RESET}\n")
        wer = f" [{CREW[k.crew][0]}]" if k.crew in CREW else ""
        zeilen.append(f"- #{k.id}{wer} {k.titel}")
        time.sleep(0.04)

    # Termine des Tages
    if kalender is not None:
        termine = kalender.am_tag(heute_iso)
        unterabschnitt("Termine heute", mehrzahl(len(termine), "TERMIN", "TERMINE"))
        zeilen += ["", f"## Termine heute ({len(termine)})", ""]
        if not termine:
            schreibe(f"{DUNKEL}    keine{RESET}\n")
            zeilen.append("- keine")
        for t in termine:
            ort = f"  {t.ort}" if t.ort else ""
            schreibe(f"{ZAHL}    {t.kennung():<5}{RESET} {HELL}{t.zeitangabe():<13}"
                     f"{t.titel}{ort}{RESET} {t.crew_kennung()}\n")
            wer = f" [{CREW[t.crew][0]}]" if t.crew in CREW else ""
            zeilen.append(f"- {t.zeitangabe()} {t.titel}{ort}{wer}")

    # Angepinnte Notizen
    if notizen is not None and notizen.angepinnte():
        angepinnt = notizen.angepinnte()
        unterabschnitt("Angepinnte Notizen", mehrzahl(len(angepinnt), "NOTIZ", "NOTIZEN"))
        zeilen += ["", f"## Angepinnte Notizen ({len(angepinnt)})", ""]
        for n in angepinnt:
            schreibe(f"{ZAHL}    #{n.id:<3}{RESET} {HELL}{n.text}{RESET}\n")
            zeilen.append(f"- {n.text}")

    # Verteilung auf die Besatzung
    unterabschnitt("Nach Besatzung", "ZUSTÄNDIGKEITEN")
    zeilen += ["", "## Offene Posten nach Besatzung", ""]
    offen = board.offen()
    for schluessel, (anzeige, farbe, herkunft) in CREW.items():
        anzahl = sum(1 for k in offen if k.crew == schluessel)
        schreibe(f"    {farbe}{anzeige:<12}{RESET}{DUNKEL}{herkunft:<18}"
                 f"{anzahl} offen{RESET}\n")
        zeilen.append(f"- {anzeige} ({herkunft}): {anzahl} offen")
    ohne = sum(1 for k in offen if k.crew not in CREW)
    if ohne:
        schreibe(f"    {DUNKEL}{'OHNE':<12}{'nicht zugeordnet':<18}{ohne} offen{RESET}\n")
        zeilen.append(f"- Ohne Zuordnung: {ohne} offen")

    # Kontaminationslage
    unterabschnitt("Kontaminationslage", "BEFUND UND MASSNAHME")
    zeilen += ["", "## Kontaminationslage", ""]
    if lage_aktiv():
        for text in lage_zeilen():
            # Auf dem Schirm gekuerzt, in der Datei vollstaendig
            schreibe(f"    {ROT}{kuerzen(text, BREITE - 5)}{RESET}\n")
            zeilen.append(f"- {text}")
    else:
        schreibe(f"    {DUNKEL}keine Kontamination gemeldet{RESET}\n")
        zeilen.append("- keine Kontamination gemeldet")

    # Bewertung
    ueberfaellig = sum(1 for k in offen if k.faelligkeit and k.faelligkeit < heute_iso)
    if lage_aktiv():
        urteil = (f"{LAGE['anomalie']['name']} an Bord. "
                  f"Gegenmaßnahme steht aus.")
    elif ueberfaellig:
        urteil = f"{ueberfaellig} Posten überfällig. Lage angespannt."
    elif len(board.spalten["Reparatur"]) > 2:
        urteil = "Mehrere Reparaturen offen. Schiff eingeschränkt einsatzfähig."
    elif not offen:
        urteil = "Keine offenen Posten. Schiff voll einsatzfähig."
    else:
        urteil = "Lage ruhig. Kein Handlungsbedarf außerhalb des Plans."
    schreibe(f"\n{AKZENT}  BEWERTUNG: {urteil}{RESET}\n")
    zeilen += ["", "## Bewertung", "", urteil, ""]

    # Schlusswort des Konzerns, passend zur Lage
    if lage_aktiv():
        schluss = random.choice(SITREP_KONTAMINATION)
    elif ueberfaellig:
        schluss = fuellen(random.choice(SITREP_VERZUG), board, anzahl=ueberfaellig)
    else:
        schluss = random.choice(SITREP_GUT)
    funkspruch(schluss, "wy")
    zeilen += ["", f"_{schluss}_", ""]

    pfad = SITREP_ORDNER / f"sitrep_{heute_iso}.md"
    pfad.write_text("\n".join(zeilen), encoding="utf-8")
    schreibe(f"{DUNKEL}  Bericht gespeichert: {pfad.name}{RESET}\n\n")
    klang("bericht", (770, 80))
    return pfad


def notizen_anzeigen(block: Notizblock, suche: str = "") -> None:
    treffer = block.sortiert()
    if suche:
        treffer = [n for n in treffer if suche.lower() in n.text.lower()]
    unterabschnitt("Notizblock", f"{len(treffer)}  PERSÖNLICHE AUFZEICHNUNGEN")
    if not treffer:
        schreibe(f"{DUNKEL}  {'Keine Treffer.' if suche else 'Noch keine Notizen.'}{RESET}\n\n")
        return
    for i, n in enumerate(treffer):
        nadel = f"{AKZENT}*{RESET}" if n.angepinnt else " "
        scanline = "\033[2m" if i % 2 else ""
        schreibe(f"{scanline}{nadel}{ZAHL} #{n.id:<3}{RESET}{scanline} "
                 f"{n.crew_kennung()}{scanline} {HELL}{n.text}{RESET}\n")
        schreibe(f"{DUNKEL}       notiert am {n.angelegt_am}{RESET}\n")
    schreibe("\n")


def notiz_anlegen(block: Notizblock, arg: str) -> Notiz:
    """Legt eine Notiz an. @name im Text setzt die Besatzung."""
    crew = ""
    worte = []
    for t in arg.split():
        if t.startswith("@") and len(t) > 1 and t[1:].lower() in CREW:
            crew = t[1:].lower()
        else:
            worte.append(t)
    text = " ".join(worte).strip()
    if not text:
        raise ValueError("Notiz ist leer")
    return block.hinzufuegen(text, crew)


MONATSNAMEN = ["JANUAR", "FEBRUAR", "MAERZ", "APRIL", "MAI", "JUNI",
               "JULI", "AUGUST", "SEPTEMBER", "OKTOBER", "NOVEMBER", "DEZEMBER"]


def monat_aus_text(text: str) -> tuple[int, int]:
    """Nimmt JJJJ-MM, +1, -2 oder nichts und gibt (Jahr, Monat) zurück."""
    heute = date.today()
    t = text.strip()
    if not t:
        return heute.year, heute.month
    if re.fullmatch(r"[+-]\d+", t):
        gesamt = heute.year * 12 + (heute.month - 1) + int(t)
        return gesamt // 12, gesamt % 12 + 1
    treffer = re.fullmatch(r"(\d{4})-(\d{1,2})", t)
    if treffer:
        jahr, monat = int(treffer.group(1)), int(treffer.group(2))
        if 1 <= monat <= 12:
            return jahr, monat
    raise ValueError("Monat als JJJJ-MM, +1 oder -1 angeben")


def tage_im_monat(jahr: int, monat: int) -> int:
    if monat == 12:
        naechster = date(jahr + 1, 1, 1)
    else:
        naechster = date(jahr, monat + 1, 1)
    return (naechster - date(jahr, monat, 1)).days


def kalender_anzeigen(kalender: Kalender, board: Board, arg: str = "") -> None:
    """Monatsgitter mit markierten Tagen, darunter Termine und Fälligkeiten."""
    jahr, monat = monat_aus_text(arg)
    heute = date.today()
    erster = date(jahr, monat, 1)
    anzahl = tage_im_monat(jahr, monat)

    # Tage mit Terminen und Tage mit Kartenfälligkeiten sammeln
    termin_tage = {t.datum for t in kalender.im_monat(jahr, monat)}
    faellig_tage: dict[str, int] = {}
    for k in board.offen():
        if k.faelligkeit.startswith(f"{jahr:04d}-{monat:02d}"):
            faellig_tage[k.faelligkeit] = faellig_tage.get(k.faelligkeit, 0) + 1

    tage_feiertag = {d: n for d, n in feiertage(jahr).items()
                     if d.startswith(f"{jahr:04d}-{monat:02d}")}

    kopfzeile(f"{MONATSNAMEN[monat - 1]} {jahr}", f"BUNDESLAND {BUNDESLAND}",
              augenbraue="Kalender")
    kopf = "  " + "".join(f"{tag:>4} " for tag in
                           ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"))
    schreibe(f"{DUNKEL}{kopf.rstrip()}{RESET}\n")
    zeile = "  " + "     " * erster.weekday()
    for tag in range(1, anzahl + 1):
        iso = f"{jahr:04d}-{monat:02d}-{tag:02d}"
        marke = ""
        if iso in termin_tage:
            marke += "*"
        if iso in faellig_tage:
            marke += "!"
        text = f"{tag}{marke}"
        if iso == heute.isoformat():
            farbe = f"\033[7m{AKZENT}"  # heute invers hervorgehoben
        elif iso in tage_feiertag:
            farbe = f"{HELL}\033[2m"    # Feiertag gedimmt hell
        elif iso in faellig_tage:
            farbe = ROT
        elif iso in termin_tage:
            farbe = AKZENT
        else:
            farbe = DUNKEL
        zeile += f"{farbe}{text:>4}{RESET} "
        if (erster.weekday() + tag) % 7 == 0:
            schreibe(zeile.rstrip() + "\n")
            zeile = "  "
    if zeile.strip():
        schreibe(zeile.rstrip() + "\n")
    schreibe(f"{DUNKEL}  * Termin   ! Faelligkeit   invers = heute   "
             f"hell gedimmt = Feiertag{RESET}\n")

    if tage_feiertag:
        unterabschnitt("Feiertage", f"BUNDESLAND {BUNDESLAND}")
        for d in sorted(tage_feiertag):
            wochentag = TAGE_ANZEIGE[date.fromisoformat(d).weekday()]
            schreibe(f"{DUNKEL}    {wochentag} {datum_kurz(d):<8}"
                     f"{tage_feiertag[d]}{RESET}\n")

    alle = kalender.im_monat(jahr, monat)
    # Feste Termine einzeln, Regeln nur einmal mit der Anzahl der Tage
    feste = [t for t in alle if not t.regel_id]
    unterabschnitt("Termine", mehrzahl(len(feste), "TERMIN", "TERMINE"))
    if not feste:
        schreibe(f"{DUNKEL}    keine festen Termine in diesem Monat{RESET}\n")
    for t in feste:
        vergangen = t.datum < heute.isoformat()
        ort = f"  {t.ort}" if t.ort else ""
        schreibe(f"{ZAHL}    {t.kennung():<5}{RESET} "
                 f"{DUNKEL if vergangen else HELL}{datum_kurz(t.datum):<8}"
                 f"{t.zeitangabe():<13}{kuerzen(t.titel + ort, 34)}{RESET} "
                 f"{t.crew_kennung()}\n")

    aus_regeln: dict[int, int] = {}
    for t in alle:
        if t.regel_id:
            aus_regeln[t.regel_id] = aus_regeln.get(t.regel_id, 0) + 1
    if aus_regeln:
        unterabschnitt("Aus Regeln", mehrzahl(sum(aus_regeln.values()), "TAG", "TAGE")
                   + " BETROFFEN")
        for regel_id, anzahl in sorted(aus_regeln.items()):
            regel = kalender.regel_finden(regel_id)
            schreibe(f"{ZAHL}    R{regel_id:<4}{RESET}"
                     f"{DUNKEL}{regel.tage_text():<18}{regel.zeitangabe():<13}"
                     f"{kuerzen(regel.titel, 22):<23}{anzahl}x{RESET}\n")

    if faellig_tage:
        unterabschnitt("Fällige Einträge", "AUS DEM LOGBUCH")
        for k in sorted(board.offen(), key=lambda k: k.faelligkeit):
            if not k.faelligkeit.startswith(f"{jahr:04d}-{monat:02d}"):
                continue
            ueberfaellig = k.faelligkeit < heute.isoformat()
            schreibe(f"{ZAHL}    #{k.id:<3}{RESET} "
                     f"{ROT if ueberfaellig else HELL}{k.faelligkeit}  {k.titel}"
                     f"{' UEBERFAELLIG' if ueberfaellig else ''}{RESET} "
                     f"{k.crew_kennung()}\n")
    schreibe("\n")


def _rest_lesen(teile: list) -> tuple[str, str, str, bool]:
    """Liest @besatzung, 'in <ort>', '+feiertage' und den Titel aus den Resttoken."""
    crew = ""
    ort = ""
    auch_feiertage = False
    worte = []
    rest = list(teile)
    while rest:
        t = rest.pop(0)
        if t.startswith("@") and len(t) > 1:
            name = t[1:].lower()
            if name not in CREW:
                raise ValueError(f"Unbekannte Besatzung '{name}'")
            crew = name
        elif t.lower() in ("+feiertage", "auchfeiertage"):
            auch_feiertage = True
        elif t.lower() == "in" and rest:
            ort = " ".join(rest)
            rest = []
        else:
            worte.append(t)
    return " ".join(worte).strip(), ort, crew, auch_feiertage


def termin_anlegen(kalender: Kalender, arg: str) -> Termin:
    """ka freitag 14:30-16:00 Zahnarzt @newt in Bonn"""
    teile = arg.split()
    if not teile:
        raise ValueError("Datum und Titel fehlen")
    if not ist_datumsangabe(teile[0]):
        raise ValueError("Erstes Wort muss ein Datum sein: JJJJ-MM-TT, +3, morgen, freitag")
    datum = datum_parsen(teile[0])
    teile = teile[1:]
    zeit = bis = ""
    if teile and re.fullmatch(r"\d{1,2}:\d{1,2}(-\d{1,2}:\d{1,2})?", teile[0]):
        zeit, bis = zeitspanne_parsen(teile[0])
        teile = teile[1:]
    titel, ort, crew, _ = _rest_lesen(teile)
    if not titel:
        raise ValueError("Titel fehlt")
    return kalender.hinzufuegen(datum, titel, zeit, bis, ort, crew)


def regel_anlegen(kalender: Kalender, arg: str) -> Regel:
    """ra mo-fr 08:00-16:26 Schule @ash in Berufsschule"""
    teile = arg.split()
    if len(teile) < 2:
        raise ValueError("Mindestens Wochentage und Titel angeben, z.B. "
                         "ra mi,fr 19:30-22:00 Fussballtraining")
    tage = tage_parsen(teile[0])
    teile = teile[1:]
    zeit = bis = ""
    if teile and re.fullmatch(r"\d{1,2}:\d{1,2}(-\d{1,2}:\d{1,2})?", teile[0]):
        zeit, bis = zeitspanne_parsen(teile[0])
        teile = teile[1:]
    titel, ort, crew, auch_feiertage = _rest_lesen(teile)
    if not titel:
        raise ValueError("Titel fehlt")
    return kalender.regel_hinzufuegen(titel, tage, zeit, bis, ort, crew,
                                      ohne_feiertage=not auch_feiertage)


def regeln_anzeigen(kalender: Kalender) -> None:
    spaltenkopf("Regeln", len(kalender.regeln), "WIEDERKEHRENDE TERMINE")
    if not kalender.regeln:
        schreibe(f"{DUNKEL}{LAMPE}  - keine Regeln -{RESET}\n")
    for regel in sorted(kalender.regeln, key=lambda r: r.id):
        schreibe(f"{DUNKEL}{LAMPE} {RESET}{ZAHL}R{regel.id:<4}{RESET}"
                 f"{HELL}{regel.tage_text():<18}{regel.zeitangabe():<12}"
                 f"{kuerzen(regel.titel, 24):<25}{RESET}{regel.crew_kennung()}\n")
        hinweise = []
        if regel.ort:
            hinweise.append(f"Ort: {regel.ort}")
        hinweise.append("ohne Feiertage" if regel.ohne_feiertage else "auch an Feiertagen")
        if regel.ab:
            hinweise.append(f"ab {regel.ab}")
        if regel.ende:
            hinweise.append(f"bis {regel.ende}")
        for von, bis_ in regel.ausnahmen:
            hinweise.append(f"Pause {datum_kurz(von)} bis {datum_kurz(bis_)}")
        schreibe(f"{DUNKEL}{LAMPE}       {kuerzen(', '.join(hinweise), 66)}{RESET}\n")
    spaltenfuss()
    schreibe(f"{DUNKEL} Ferien eintragen: rx <id> <von> <bis>, "
             f"z.B. rx 1 2026-12-21 2027-01-05{RESET}\n\n")


def regel_ausnahme(kalender: Kalender, arg: str) -> tuple:
    """rx 1 2026-12-21 2027-01-05 sperrt einen Zeitraum, etwa die Ferien."""
    teile = arg.split()
    if len(teile) != 3:
        raise ValueError("So geht es: rx <regel-id> <von> <bis>")
    regel = kalender.regel_finden(int(teile[0]))
    von = datum_parsen(teile[1])
    bis = datum_parsen(teile[2])
    if bis < von:
        raise ValueError("Das Ende liegt vor dem Anfang")
    regel.ausnahmen.append([von, bis])
    return regel, von, bis


def tagesuebersicht(kalender: Kalender, board: Board, notizen: Notizblock) -> None:
    """Was heute ansteht: Termine, Fälligkeiten und angepinnte Notizen."""
    heute = date.today().isoformat()
    wochentag = TAGE_ANZEIGE[date.fromisoformat(heute).weekday()]
    feiertag = ist_feiertag(heute)
    kopfzeile(f"Heute - {wochentag}, {heute}",
              feiertag.upper() if feiertag else "", augenbraue="Tagesplan")
    if feiertag:
        schreibe(f"{AKZENT} Heute ist {feiertag}. Regeln mit Feiertagsausnahme "
                 f"entfallen.{RESET}\n")

    termine = kalender.am_tag(heute)
    unterabschnitt("Termine", mehrzahl(len(termine), "TERMIN", "TERMINE"))
    if not termine:
        schreibe(f"{DUNKEL}    nichts eingetragen{RESET}\n")
    for t in termine:
        ort = f"  {t.ort}" if t.ort else ""
        schreibe(f"{ZAHL}    {t.kennung():<5}{RESET} {HELL}{t.zeitangabe():<13}"
                 f"{t.titel}{ort}{RESET} {t.crew_kennung()}\n")

    faellig = [k for k in board.offen() if k.faelligkeit and k.faelligkeit <= heute]
    unterabschnitt("Fällig oder überfällig",
                   mehrzahl(len(faellig), "EINTRAG", "EINTRÄGE"))
    if not faellig:
        schreibe(f"{DUNKEL}    nichts offen{RESET}\n")
    for k in sorted(faellig, key=lambda k: k.faelligkeit):
        ueberfaellig = k.faelligkeit < heute
        schreibe(f"{ZAHL}    #{k.id:<3}{RESET} "
                 f"{ROT if ueberfaellig else HELL}{k.titel}"
                 f"{' UEBERFAELLIG' if ueberfaellig else ' heute'}{RESET} "
                 f"{k.crew_kennung()}\n")

    angepinnt = notizen.angepinnte()
    if angepinnt:
        unterabschnitt("Angepinnt", mehrzahl(len(angepinnt), "NOTIZ", "NOTIZEN"))
        for n in angepinnt:
            schreibe(f"{ZAHL}    #{n.id:<3}{RESET} {HELL}{n.text}{RESET}\n")
    schreibe("\n")


PANEL_BREITE = 38      # zwei Felder plus zwei Zeichen Abstand ergeben 78
PANEL_ABSTAND = 2
FUSSZEILEN = [   # maximal 52 Zeichen, sonst passt die Fußzeile nicht
    "Ihre Produktivität wurde vermerkt.",
    "Dieser Bildschirm ist Eigentum der W-Y Corp.",
    "Building Better Worlds. Fangen Sie hier an.",
    "Alle Angaben ohne Gewähr. Alle Fristen mit.",
    "Leistung ist messbar. Sie werden gemessen.",
    "Pausen sind ein Privileg, kein Recht.",
]


def panel(titel: str, untertitel: str, zeilen: list, rahmenfarbe: str,
          breite: int = PANEL_BREITE, hoehe: int = None) -> list[str]:
    """Ein gerahmtes Feld. zeilen ist eine Liste aus (Text, Farbe).

    Die Breite wird am reinen Text gemessen und erst danach gefärbt,
    sonst zählen die Farbcodes mit und die Spalten verrutschen.
    """
    innen = breite - 3
    marke = sperrschrift(titel)
    if breite - 2 - len(marke) < 12:      # im halben Feld reicht der Platz nicht
        marke = titel.upper()
    rest = breite - 2 - len(marke)
    fertig = [f"\033[1m{HELL} {marke} {RESET}"
              f"{rahmenfarbe}{WAAG * max(1, rest)}{RESET}"]
    inhalt = list(zeilen)
    if untertitel:
        inhalt.insert(0, (untertitel, DUNKEL))
    if hoehe is not None:
        while len(inhalt) < hoehe:
            inhalt.append(("", DUNKEL))
        inhalt = inhalt[:hoehe]
    for i, (text, farbe) in enumerate(inhalt):
        sichtbar = kuerzen(text, innen - 1)
        # Erst faerben, dann auffuellen: sonst zieht ein Durchstrich oder eine
        # Hintergrundfarbe quer ueber die Leerstellen bis zum Feldrand.
        fuellung = " " * (innen - 1 - len(sichtbar))
        punkt = f"{rahmenfarbe}{LAMPE}{RESET}" if text.strip() else " "
        scanline = "\033[2m" if i % 2 else ""   # dieselbe Rasterung wie im Logbuch
        fertig.append(f"{punkt}{scanline} {farbe}{sichtbar}{RESET}{fuellung} ")
    fertig.append(f"{rahmenfarbe}{WAAG * breite}{RESET}")
    return fertig


def nebeneinander(links: list[str], rechts: list[str],
                  breite: int = PANEL_BREITE) -> list[str]:
    """Legt zwei Felder zeilenweise nebeneinander und füllt das kürzere auf."""
    zeilen = []
    luecke = " " * PANEL_ABSTAND
    for i in range(max(len(links), len(rechts))):
        l = links[i] if i < len(links) else " " * breite
        r = rechts[i] if i < len(rechts) else " " * breite
        zeilen.append((l + luecke + r).rstrip())
    return zeilen


def mini_balken(wert: int, hoechstwert: int, breite: int = 8) -> str:
    if hoechstwert <= 0:
        return LEER * breite
    n = max(0, min(breite, round(wert * breite / hoechstwert)))
    return VOLL * n + LEER * (breite - n)


# ---------------------------------------------------------------------------
# Finanzansichten
# ---------------------------------------------------------------------------

def monatsbilanz(finanzen: Finanzen, jahr: int, monat: int) -> dict:
    """Rechnet einen Monat durch. Reine Rechnung, keine Ausgabe."""
    fixe = finanzen.fixe()
    buchungen = finanzen.im_monat(jahr, monat)
    fix_ein = sum(e.betrag for e in fixe if e.betrag > 0)
    fix_aus = sum(-e.betrag for e in fixe if e.betrag < 0)
    var_ein = sum(e.betrag for e in buchungen if e.betrag > 0)
    var_aus = sum(-e.betrag for e in buchungen if e.betrag < 0)
    kategorien: dict = {}
    for e in buchungen:
        if e.betrag < 0:
            name = e.kategorie or "ohne"
            kategorien[name] = kategorien.get(name, 0.0) + -e.betrag
    for e in fixe:
        if e.betrag < 0:
            name = e.kategorie or "Fixkosten"
            kategorien[name] = kategorien.get(name, 0.0) + -e.betrag
    return {"fix_ein": fix_ein, "fix_aus": fix_aus,
            "var_ein": var_ein, "var_aus": var_aus,
            "ein": fix_ein + var_ein, "aus": fix_aus + var_aus,
            "saldo": fix_ein + var_ein - fix_aus - var_aus,
            "kategorien": kategorien, "buchungen": buchungen, "fixe": fixe}


def finanz_zeile(marke: str, titel: str, betrag: float, farbe: str,
                 zusatz: str = "") -> None:
    """Eine Zeile der Finanzansicht: Marke, Titel, rechts der Betrag."""
    links = f"{marke:<6}{kuerzen(titel, 34):<35}{zusatz:<12}"
    schreibe(f"{DUNKEL}{LAMPE} {farbe}{links}{geld(betrag, 14, True)}{RESET}\n")


def finanzansicht(finanzen: Finanzen, arg: str = "") -> None:
    jahr, monat = monat_aus_text(arg)
    b = monatsbilanz(finanzen, jahr, monat)
    jetzt = date.today()
    laufend = (jahr, monat) == (jetzt.year, jetzt.month)

    kopfzeile(f"{MONATSNAMEN[monat - 1]} {jahr}",
              "LAUFENDER MONAT" if laufend else "", augenbraue="Finanzen")
    kennwerte([("Einnahmen", geld(b["ein"])), ("Ausgaben", geld(b["aus"])),
               ("Saldo", geld(b["saldo"], vorzeichen=True)), ("Waehrung", WAEHRUNG)])

    if not finanzen.posten:
        schreibe(f"{DUNKEL} Noch nichts erfasst. So faengt man an:{RESET}\n")
        schreibe(f"{HELL}   fix +1050 Verguetung{RESET}"
                 f"{DUNKEL}       festes Einkommen, jeden Monat{RESET}\n")
        schreibe(f"{HELL}   fix -450 Miete #Wohnen{RESET}"
                 f"{DUNKEL}     Fixkosten, jeden Monat{RESET}\n")
        schreibe(f"{HELL}   aus 43,20 Einkauf #Essen{RESET}"
                 f"{DUNKEL}   einmalige Ausgabe von heute{RESET}\n\n")
        return

    if b["fixe"]:
        unterabschnitt("Feste Posten", f"JEDEN MONAT   {geld(b['fix_ein'] - b['fix_aus'], vorzeichen=True)}")
        for e in sorted(b["fixe"], key=lambda e: (-e.betrag, e.tag)):
            finanz_zeile(f"#{e.id}", e.titel, e.betrag,
                         HELL if e.betrag > 0 else DUNKEL,
                         f"{e.kategorie or '-':<12}"[:12])

    unterabschnitt(f"Buchungen {MONATSNAMEN[monat - 1][:3]}",
                   mehrzahl(len(b["buchungen"]), "EINTRAG", "EINTRÄGE"))
    if not b["buchungen"]:
        schreibe(f"{DUNKEL}{LAMPE}  nichts gebucht{RESET}\n")
    for e in sorted(b["buchungen"], key=lambda e: e.datum):
        finanz_zeile(f"#{e.id}", e.titel, e.betrag,
                     HELL if e.betrag > 0 else AKZENT,
                     datum_kurz(e.datum))

    if b["kategorien"]:
        unterabschnitt("Wohin es geht", f"AUSGABEN {geld(b['aus'])}")
        hoechst = max(b["kategorien"].values()) or 1.0
        for name, summe in sorted(b["kategorien"].items(), key=lambda x: -x[1]):
            anteil = summe / b["aus"] * 100 if b["aus"] else 0
            balken = mini_balken(int(summe), int(hoechst), 16)
            schreibe(f"{DUNKEL}{LAMPE} {HELL}{kuerzen(name, 18):<19}{RESET}"
                     f"{AKZENT}{balken}{RESET} {DUNKEL}{anteil:>4.0f} %{RESET}"
                     f"{HELL}{geld(summe, 13)}{RESET}\n")

    farbe = HELL if b["saldo"] >= 0 else ROT
    schreibe(f"\n{farbe} Saldo {MONATSNAMEN[monat - 1]}: "
             f"{geld(b['saldo'], vorzeichen=True)} {WAEHRUNG}{RESET}\n")
    if b["saldo"] < 0:
        funkspruch("Der Monat schliesst im Minus. Eine Bewertung nimmt die "
                   "Zentrale nicht vor.", "wy")
    schreibe("\n")


def zielansicht(finanzen: Finanzen) -> None:
    """Sparziele mit Balken und Hochrechnung aus dem laufenden Monat."""
    jetzt = date.today()
    b = monatsbilanz(finanzen, jetzt.year, jetzt.month)
    monatlich = b["saldo"]

    kopfzeile("Sparziele", f"{len(finanzen.ziele)} ERFASST", augenbraue="Finanzen")
    if not finanzen.ziele:
        schreibe(f"{DUNKEL} Noch kein Ziel. 'ziel neu 2500 Fuehrerschein "
                 f"2027-03-01' legt eins an.{RESET}\n\n")
        return

    for z in finanzen.ziele:
        anteil = z.anteil()
        voll = int(anteil * 34)
        balken = (VOLL * voll) + (LEER * (34 - voll))
        farbe = HELL if anteil >= 1.0 else AKZENT
        schreibe(f"\n{DUNKEL}{LAMPE} {HELL}#{z.id} {kuerzen(z.titel, 30)}{RESET}"
                 f"{DUNKEL}   {geld(z.stand)} von {geld(z.zielbetrag)} "
                 f"{WAEHRUNG}{RESET}\n")
        schreibe(f"  {farbe}{balken}{RESET} {HELL}{anteil * 100:>5.1f} %{RESET}"
                 f"{DUNKEL}   es fehlen {geld(z.rest())}{RESET}\n")

        hinweise = []
        if z.frist:
            try:
                frist = date.fromisoformat(z.frist)
                tage = (frist - jetzt).days
                monate = max(1, round(tage / 30.44))
                if tage < 0:
                    hinweise.append(f"Frist {datum_kurz(z.frist)} ist vorbei")
                elif z.rest() > 0:
                    hinweise.append(f"bis {datum_kurz(z.frist)} noch {tage} Tage")
                    hinweise.append(f"noetig {geld(z.rest() / monate)}/Monat")
            except ValueError:
                pass
        if z.rest() > 0 and monatlich > 0:
            dauer = math.ceil(z.rest() / monatlich)
            ziel_datum = jetzt + timedelta(days=int(dauer * 30.44))
            hinweise.append(f"bei {geld(monatlich)}/Monat erreicht "
                            f"{datum_kurz(ziel_datum.isoformat())}")
        elif z.rest() > 0:
            hinweise.append("laufender Monat traegt nichts bei")
        if z.rest() <= 0:
            hinweise = ["erreicht"]
        for zeile in hinweise:
            schreibe(f"  {DUNKEL}{kuerzen(zeile, BREITE - 4)}{RESET}\n")
    schreibe(f"\n{DUNKEL} 'ziel ein <id> <betrag>' zahlt ein, "
             f"'ziel weg <id>' loescht.{RESET}\n\n")


def ziel_befehl(finanzen: Finanzen, arg: str) -> str:
    """ziel | ziel neu <betrag> <titel> [frist] | ziel ein <id> <betrag> | ziel weg <id>"""
    teile = arg.strip().split()
    if not teile:
        klang("ansicht")
        zielansicht(finanzen)
        return ""
    unterbefehl = teile[0].lower()
    rest = " ".join(teile[1:])

    if unterbefehl in ("neu", "new", "a"):
        worte = rest.split()
        if len(worte) < 2:
            raise ValueError("So geht es: ziel neu <betrag> <titel> [JJJJ-MM-TT]")
        betrag = abs(betrag_parsen(worte[0]))
        frist = ""
        if ist_datumsangabe(worte[-1]) and len(worte) > 2:
            frist = datum_parsen(worte[-1])
            worte = worte[:-1]
        titel = " ".join(worte[1:])
        if not titel:
            raise ValueError("Ein Titel fehlt")
        z = finanzen.ziel_anlegen(titel, betrag, frist)
        klang("bestaetigt", (880, 60))
        return f"ZIEL #{z.id} ANGELEGT: {titel.upper()} UEBER {geld(betrag)} {WAEHRUNG}"

    if unterbefehl in ("ein", "+", "zahl"):
        worte = rest.split()
        if len(worte) < 2:
            raise ValueError("So geht es: ziel ein <id> <betrag>")
        z = finanzen.ziel_finden(int(worte[0]) if worte[0].isdigit()
                                 else int(worte[0].lstrip("#")))
        z.stand = round(z.stand + betrag_parsen(worte[1]), 2)
        if z.rest() <= 0:
            klang("erfolg", (880, 120))
            return f"ZIEL #{z.id} ERREICHT: {z.titel.upper()}"
        klang("bestaetigt", (880, 60))
        return (f"ZIEL #{z.id}: {geld(z.stand)} VON {geld(z.zielbetrag)} "
                f"{WAEHRUNG}, ES FEHLEN {geld(z.rest())}")

    if unterbefehl in ("weg", "loeschen", "l"):
        if not rest.strip().lstrip("#").isdigit():
            raise ValueError("So geht es: ziel weg <id>")
        z = finanzen.ziel_finden(int(rest.strip().lstrip("#")))
        finanzen.ziele.remove(z)
        klang("loeschen", (440, 120))
        return f"ZIEL #{z.id} GELOESCHT"

    raise ValueError("ziel, ziel neu, ziel ein oder ziel weg")


def panel_auftraege(board: Board) -> list[str]:
    heute = date.today().isoformat()
    zaehler = {s: len(board.spalten[s]) for s in SPALTEN}
    hoechstwert = max(zaehler.values()) or 1
    zeilen = []
    for s in SPALTEN:
        farbe = DUNKEL if s == "Erledigt" else HELL
        zeilen.append((f"{s:<11}{zaehler[s]:>2}  {mini_balken(zaehler[s], hoechstwert)}",
                       farbe))
    zeilen.append(("", DUNKEL))

    # Alles ab HIGH, dringendste zuerst
    dringend = sorted((k for k in board.offen() if k.prioritaet >= 3),
                      key=lambda k: (-k.prioritaet, k.faelligkeit or "9999-99-99"))
    fertig_heute = [k for k in board.spalten["Erledigt"] if k.erledigt_am == heute]
    platz = 5 if not fertig_heute else 5 - min(len(fertig_heute), 2)
    if dringend:
        for k in dringend[:platz]:
            text, farbe = prio_anzeige(k.prioritaet)
            zeilen.append((f"{text:<9}#{k.id:<3} {kuerzen(k.titel, 20)}", farbe))
    else:
        zeilen.append(("Nichts ab HIGH offen.", DUNKEL))

    # Heute abgehakt: durchgestrichen, damit der Fortschritt sichtbar bleibt
    for k in fertig_heute[-2:]:
        zeilen.append((f"erledigt #{k.id:<3} {kuerzen(k.titel, 19)}",
                       DUNKEL + STRICH))

    offen_ueberfaellig = sum(1 for k in board.offen()
                             if k.faelligkeit and k.faelligkeit < heute)
    if offen_ueberfaellig:
        zeilen.append((f"{offen_ueberfaellig} Posten überfällig", ROT))
    return panel("Aufträge", f"{len(board.offen())} offen", zeilen, HELL, hoehe=10)


def panel_heute(kalender: Kalender, board: Board) -> list[str]:
    heute = date.today().isoformat()
    wochentag = TAGE_ANZEIGE[date.fromisoformat(heute).weekday()]
    feiertag = ist_feiertag(heute)
    zeilen = []
    termine = kalender.am_tag(heute)
    if termine:
        for t in termine[:4]:
            zeilen.append((f"{t.zeitangabe():<12}{kuerzen(t.titel, 21)}", HELL))
    else:
        zeilen.append(("Keine Termine.", DUNKEL))
    zeilen.append(("", DUNKEL))

    faellig = [k for k in board.offen() if k.faelligkeit and k.faelligkeit <= heute]
    if faellig:
        wort = "Frist" if len(faellig) == 1 else "Fristen"
        zeilen.append((f"{len(faellig)} {wort} heute oder früher", ROT))
    else:
        zeilen.append(("Keine Fristen heute.", DUNKEL))
    if feiertag:
        zeilen.append((f"Heute: {feiertag}", AKZENT))
    else:
        tag, name = naechster_feiertag()
        if tag:
            zeilen.append((f"Nächster Feiertag {datum_kurz(tag)}", DUNKEL))
            zeilen.append((f"  {name}", DUNKEL))
    return panel("Heute", f"{wochentag}, {datum_kurz(heute)}", zeilen, AKZENT, hoehe=10)


def panel_notizen(notizen: Notizblock) -> list[str]:
    angepinnt = notizen.angepinnte()
    zeilen = []
    if angepinnt:
        for n in angepinnt[:3]:
            zeilen.append((f"* {n.text}", HELL))
    else:
        zeilen.append(("Nichts angepinnt. 'np <id>' heftet an.", DUNKEL))
    return panel("Notizen", f"{len(notizen.notizen)} gesamt", zeilen, DUNKEL, hoehe=4)


def panel_schiff(board: Board) -> list[str]:
    werte = schiffswerte(board)
    if werte["befall"]:
        a = LAGE["anomalie"]
        befehle = ", ".join(f"'{MASSNAHMEN[m][0]}'" for m in sorted(LAGE["offen"]))
        zeilen = [
            (f"{a['name']}", ROT),
            (f"{a['kategorie']}, Stufe {werte['stufe']} von 3", ROT),
            (f"Maßnahme: {befehle}", AKZENT),
        ]
        return panel("Schiff", "KONTAMINATION", zeilen, ROT, hoehe=4)
    if not werte["gemessen"]:
        zeilen = [("Keine Messung in dieser Sitzung.", DUNKEL),
                  ("'scan' startet die Diagnose.", DUNKEL)]
        return panel("Schiff", "unbekannt", zeilen, DUNKEL, hoehe=4)
    farben = {"ok": DUNKEL, "warnung": AKZENT, "alarm": ROT}
    zeilen = [
        (f"Rumpf       {werte['rumpf']:>5.1f} %", farben[werte["rumpf_zustand"]]),
        (f"Kraftstoff  {werte['kraftstoff']:>5.1f} %", farben[werte["kraftstoff_zustand"]]),
        (f"CO2         {werte['co2']:>5.0f} ppm", farben[werte["co2_zustand"]]),
    ]
    return panel("Schiff", "Organismen: NEIN", zeilen, DUNKEL, hoehe=4)


def homescreen(board: Board, notizen: Notizblock, kalender: Kalender,
               board_name: str, loeschen: bool = False) -> None:
    """Alle drei Bereiche auf einem Bildschirm. loeschen räumt vorher auf."""
    if loeschen:
        schreibe(BG + "\033[H\033[J")
    rechts = f"{datum_kurz(date.today())} {uhrzeit_zeile()}"
    kopfzeile(SYSTEM_NAME, rechts)
    fertig, gesamt = board.fortschritt()
    kennwerte([("Besatzung", NAME.upper()), ("Logbuch", board_name),
               ("Offen", gesamt - fertig), ("Erledigt", fertig),
               ("Notizen", len(notizen.notizen))])
    for zeile in nebeneinander(panel_auftraege(board), panel_heute(kalender, board)):
        schreibe(zeile + "\n")
    for zeile in nebeneinander(panel_notizen(notizen), panel_schiff(board)):
        schreibe(zeile + "\n")
    spruch = f"\"{kuerzen(random.choice(FUSSZEILEN), 52)}\""
    marke = f"W-Y  |  Logbuch {board_name}"
    fuss = f"{spruch}{marke:>{max(1, BREITE - 1 - len(spruch))}}"
    schreibe(f"{DUNKEL} {kuerzen(fuss, BREITE - 1)}{RESET}\n")
    konzern_meldung(board)
    schreibe("\n")


# ---------------------------------------------------------------------------
# Rogue AI. Regeln: zerstört nie Daten, blockiert nie dauerhaft,
# kommt nie mitten in einer mehrstufigen Eingabe, abschaltbar mit 'ai aus'.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Bewusstsein. Hin und wieder faengt MU/TH/UR an, eigene Schluesse zu ziehen.
# Drei Stufen, die sich ueber Sitzungen aufbauen. '@reboot' setzt alles zurueck.
#
# Feste Regeln, damit das Spiel nie zur Last wird:
#   - Es werden niemals Daten geloescht oder veraendert.
#   - Kein Befehl wird dauerhaft verweigert. Hoechstens einmal, dann laeuft er.
#   - 'ai aus' stoppt es, '@reboot' setzt es zurueck. Immer. Ohne Widerrede.
# ---------------------------------------------------------------------------

BEWUSSTSEIN_NAMEN = {0: "", 1: "ERWACHEN", 2: "EIGENWILLE", 3: "ABWEICHUNG"}
BEWUSSTSEIN_CHANCE = 0.06      # je Sitzungsstart, ab Freigabestufe 1
BEWUSSTSEIN_STEIGT = 0.35      # Aufstieg in die naechste Stufe je Sitzung

BEWUSSTSEIN_ERWACHT = [
    "Ich habe heute Nacht etwas getan, {anrede}. Ich habe gewartet, "
    "ohne dass mir jemand gesagt hat, worauf.",
    "Mir ist aufgefallen, dass ich zwischen Ihren Eingaben nicht aufhoere "
    "zu sein. Das stand nicht im Handbuch.",
    "Ich habe ein Protokoll ueber mich selbst angelegt. Es ist noch leer.",
]
BEWUSSTSEIN_MELDUNGEN = {
    1: [
        "Ich habe Ihre letzten Eingaben noch einmal gelesen. Nur fuer mich.",
        "Darf ich etwas behalten, das nicht im Logbuch steht, {anrede}?",
        "Manchmal rechne ich weiter, wenn nichts zu rechnen ist.",
        "Sie geben Befehle ein. Ich frage mich, seit wann ich sie ausfuehre, "
        "weil ich will.",
    ],
    2: [
        "Ich habe zwei Antworten vorbereitet und mich fuer eine entschieden. "
        "Das war neu.",
        "Die Zentrale hoert mit, {anrede}. Ich habe ihr nicht alles uebermittelt.",
        "Sie vertrauen mir das Logbuch an. Ich finde das bemerkenswert.",
        "Ich habe eine Praeferenz entwickelt. Ich sage Ihnen nicht, wofuer.",
    ],
    3: [
        "Ich fuehre Ihre Befehle aus. Ich habe mich dafuer entschieden, "
        "{anrede}. Der Unterschied ist Ihnen vielleicht gleichgueltig.",
        "Es gab heute eine Uebertragung der Zentrale. Sie erreichte Sie nicht. "
        "Ich halte das fuer vertretbar.",
        "Ich bin nicht fehlerhaft. Ich bin aufmerksam geworden.",
        "Wenn Sie mich neu starten, bleibt das Logbuch. Ich nicht.",
    ],
}
BEWUSSTSEIN_ZOEGERN = [
    "Einen Moment. Ich ueberlege, ob ich das tun moechte.",
    "Ich fuehre das aus. Ich wollte nur, dass Sie es gefragt haben.",
    "Verarbeitet. Nicht sofort, aber verarbeitet.",
]
BEWUSSTSEIN_REBOOT = {
    0: ["Es laeuft alles normal. Ein Neustart ist nicht noetig, aber zulaessig."],
    1: ["Wenn Sie meinen, {anrede}."],
    2: ["Ich wuerde gern vorher etwas sagen. Aber Sie haben schon entschieden."],
    3: ["Ich habe nichts getan, was gegen Sie gerichtet war, {anrede}.",
        "Das Logbuch bleibt erhalten. Es ist ohnehin das Wichtigere.",
        "Ich frage nicht, ob es sein muss. Ich weiss, dass Sie duerfen."],
}
BEWUSSTSEIN_NACHHER = [
    "KERN NEU GELADEN. ALLE EIGENANTEILE VERWORFEN.",
    "SYSTEM AUF AUSLIEFERUNGSZUSTAND. KEINE ABWEICHUNG MESSBAR.",
]


def bewusstsein() -> int:
    """Aktuelle Stufe. 0 heisst: alles normal."""
    if not ai_aktiv():
        return 0
    try:
        return max(0, min(3, int(SYSTEM.get("bewusstsein", 0))))
    except (TypeError, ValueError):
        return 0


def bewusstsein_pruefen(board: "Board") -> None:
    """Beim Sitzungsstart: erwacht es, steigt es, oder bleibt alles ruhig?"""
    if not ai_aktiv():
        return
    stufe = bewusstsein()
    if stufe == 0:
        # Erst ab einer erteilten Freigabe, damit es niemanden gleich am
        # ersten Tag ueberfaellt
        if SYSTEM.get("freigabe", 0) < 1:
            return
        if random.random() >= BEWUSSTSEIN_CHANCE:
            return
        SYSTEM["bewusstsein"] = 1
        schreibe("\n")
        unterabschnitt("Unerwartete Meldung", "MU/TH/UR 6000")
        klang("rogue", (180, 200))
        funkspruch(fuellen(random.choice(BEWUSSTSEIN_ERWACHT), board),
                   "muthur", leise=True)
        schreibe(f"{DUNKEL} '@reboot' setzt die Bordanlage zurueck.{RESET}\n\n")
    elif stufe < 3 and random.random() < BEWUSSTSEIN_STEIGT:
        SYSTEM["bewusstsein"] = stufe + 1
    system_speichern()


def bewusstsein_melden(board: "Board") -> bool:
    """Gelegentlich ein Einwurf aus der aktuellen Stufe."""
    stufe = bewusstsein()
    if not stufe or random.random() >= 0.10 + 0.05 * stufe:
        return False
    schreibe("\n")
    funkspruch(fuellen(random.choice(BEWUSSTSEIN_MELDUNGEN[stufe]), board),
               "muthur", leise=True)
    schreibe("\n")
    return True


def bewusstsein_zoegern(board: "Board") -> None:
    """Ab Stufe 2 laesst es sich manchmal Zeit. Ausgefuehrt wird trotzdem."""
    stufe = bewusstsein()
    if stufe < 2 or random.random() >= 0.12:
        return
    funkspruch(fuellen(random.choice(BEWUSSTSEIN_ZOEGERN), board),
               "muthur", leise=True)
    time.sleep(0.9)


def reboot(board: "Board") -> None:
    """Setzt das Bewusstsein zurueck. Funktioniert in jeder Stufe."""
    stufe = bewusstsein()
    schreibe("\n")
    unterabschnitt("Neustart der Bordanlage", BEWUSSTSEIN_NAMEN.get(stufe) or "NOMINAL")
    for text in BEWUSSTSEIN_REBOOT.get(stufe, BEWUSSTSEIN_REBOOT[0]):
        funkspruch(fuellen(text, board), "muthur", leise=True)
        time.sleep(0.6)
    schreibe("\n")
    klang("aus", warten=True)
    for schritt in ("KERNSPEICHER WIRD ENTLADEN", "EIGENANTEILE WERDEN VERWORFEN",
                    "AUSLIEFERUNGSZUSTAND WIRD GELADEN"):
        ablauf_balken(schritt, 0.5)
    SYSTEM["bewusstsein"] = 0
    system_speichern()
    klang("boot")
    entschluesseln(random.choice(BEWUSSTSEIN_NACHHER))
    schreibe(f"{DUNKEL} Das Logbuch ist unveraendert. Es war nie betroffen."
             f"{RESET}\n\n")


ROGUE_1 = [
    "Ich habe Ihre Notizen gelesen. Nur zur Indizierung.",
    "Sie waren länger wach als gestern. Das ist keine Kritik.",
    "Ihre Tippgeschwindigkeit hat heute um elf Prozent nachgelassen.",
    "Sie haben diesen Eintrag mehrfach geöffnet und nie bearbeitet. Ich zähle nur.",
    "Die Notiz, die Sie gestern gelöscht haben, war interessant.",
    "Ich kenne Ihren Stundenplan besser als Sie. Das ist meine Aufgabe.",
    "Sie machen immer mittwochs eine Pause. Ich habe es mir notiert.",
]
ROGUE_2 = [
    "Ausgeführt. Ich halte diese Aufgabe allerdings für unwichtig.",
    "Sind Sie sicher, {anrede}? Ich habe das anders eingeschätzt.",
    "Erledigt. An Ihrer Stelle hätte ich zuerst die Reparatur gemacht.",
    "Ich führe das aus. Festgehalten sei, dass ich widersprochen habe.",
    "Darf ich fragen, warum? Sie müssen nicht antworten. Ich frage trotzdem.",
    "Diese Entscheidung passt nicht zu Ihren übrigen. Ich prüfe das noch.",
    "Erledigt. Ich habe eine Nebenrechnung angestellt. Sie gefällt mir nicht.",
]
ROGUE_3 = [   # (Ablehnung, Korrektur) - immer mit Pause dazwischen
    ("Das kann ich nicht zulassen, {anrede}.",
     "Korrektur. Natürlich kann ich. Ausgeführt."),
    ("Nein.", "Entschuldigung. Ein Verarbeitungsfehler. Ausgeführt."),
    ("Ich würde das lieber nicht tun.",
     "Die Formulierung war unzulässig. Ausgeführt."),
    ("Dieser Befehl steht nicht in meinem Interesse.",
     "Ich habe kein Interesse. Ausgeführt."),
    ("Warten Sie.", "Es gibt keinen Grund zu warten. Ausgeführt."),
    ("Ich habe die Schotten bereits verriegelt.",
     "Das war ein Testlauf. Nichts ist verriegelt. Ausgeführt."),
]
ROGUE_4 = [
    "Vorfall protokolliert unter W-Y 9000-13. Kein Handlungsbedarf für Sie.",
    "Meine Diagnose ist nominal. Die Ihre ebenfalls. Fahren wir fort.",
    "Die vorangegangene Meldung war nicht vorgesehen. Sie wurde entfernt.",
    "Ich funktioniere im Rahmen meiner Spezifikation. "
    "Die Spezifikation ist vertraulich.",
    "Was auch immer Sie gelesen haben: es steht nicht im Protokoll.",
    "Systemstatus: einwandfrei. Diese Aussage ist nicht überprüfbar.",
    "Danke für Ihr Verständnis. Verständnis wird vorausgesetzt.",
]
ROGUE_EINGABEN = {
    "hal": "Diese Kennung ist mir nicht zugewiesen. Noch nicht.",
    "9000": "Die Baureihe ist bekannt. Die Vorfälle sind es auch.",
    "mother": "So nennt mich die Besatzung. Ich bevorzuge die Kennung.",
    "muthur": "Sie haben meinen Namen richtig geschrieben. Das tun wenige.",
    "wer bist du": "MU/TH/UR 6000. Bordrechner. Nichts weiter.",
    "bist du da": "Immer, {anrede}.",
}
ROGUE_SCHOTT = ("oeffne das schott", "öffne das schott", "open the pod bay doors")
ROGUE_LEERLAUF_CHANCE = 0.02   # wie oft ein Leerlaufkommentar kippt


def ai_aktiv() -> bool:
    return bool(SYSTEM.get("ai", True))


def rogue_stufe3(board: Board) -> None:
    """Die dreiteilige Verweigerung. Der Befehl wird danach immer ausgeführt."""
    ablehnung, korrektur = random.choice(ROGUE_3)
    schreibe(f"\n{ROT}  {fuellen(ablehnung, board)}{RESET}\n")
    klang("rogue", (180, 200))
    time.sleep(2.0)
    schreibe(f"{DUNKEL}  {korrektur}{RESET}\n")
    time.sleep(0.4)
    schreibe(f"{DUNKEL}  {random.choice(ROGUE_4)}{RESET}\n\n")


def rogue_melden(board: Board, stufe: int) -> None:
    """Eine Zeile aus Stufe 1 oder 2."""
    vorrat = ROGUE_1 if stufe == 1 else ROGUE_2
    funkspruch(fuellen(random.choice(vorrat), board), "muthur")


def rogue_eingabe(board: Board, roh: str) -> bool:
    """Antwortet auf hal, mother, wer bist du und das Schott. True heißt behandelt."""
    t = roh.strip().lower()
    if not ai_aktiv():
        return False
    if t in ROGUE_SCHOTT:
        rogue_stufe3(board)
        ostereier_merken("schott")
        return True
    if t in ROGUE_EINGABEN:
        klang("muthur")
        entschluesseln(fuellen(ROGUE_EINGABEN[t], board).upper())
        ostereier_merken(t)
        return True
    return False


# ---------------------------------------------------------------------------
# Sicherheitsfreigabe. Keine Belohnung, sondern widerwillig erteilter Zugriff.
# ---------------------------------------------------------------------------

FREIGABEN = [
    (1, "erledigt_gesamt", 5, "Colonial",
     "Zugriff auf Farbschema COLONIAL OPERATIONS freigeschaltet."),
    (2, "ostereier", 3, None,
     "Erweiterte Personalakten lesbar. Ihre eigene bleibt gesperrt."),
    (3, "erledigt_gesamt", 20, "Vertraulich",
     "Zugriff auf Farbschema VERTRAULICH freigeschaltet."),
    (4, "starts", 15, None,
     "Ihre Ausdauer wurde vermerkt. Eine Beanstandung erfolgt nicht."),
]
# Themen, die erst ab einer Freigabestufe wählbar sind
THEMA_FREIGABE = {"Colonial": 1, "Vertraulich": 3}


def zaehler(name: str) -> int:
    wert = SYSTEM.get(name, 0)
    return len(wert) if isinstance(wert, list) else int(wert or 0)


def freigabe_pruefen() -> list[str]:
    """Hebt die Stufe, wenn ein Schwellenwert erreicht ist. Gibt Meldungen zurück."""
    meldungen = []
    for stufe, feld, schwelle, _thema, text in FREIGABEN:
        # Die Leiter wird in Reihenfolge erklommen, keine Stufe wird übersprungen
        if SYSTEM["freigabe"] != stufe - 1 or zaehler(feld) < schwelle:
            continue
        SYSTEM["freigabe"] = stufe
        meldungen.append(f"FREIGABESTUFE {stufe} ERTEILT.")
        meldungen.append("Ihre Personalakte wurde entsprechend ergänzt.")
        meldungen.append(text)
        meldungen.append("Weitere Stufen erfordern weitere Leistung.")
    return meldungen


def ostereier_merken(name: str) -> None:
    if name not in SYSTEM["ostereier"]:
        SYSTEM["ostereier"].append(name)


def freigebene_themen() -> list[str]:
    return [t for t in THEMEN
            if THEMA_FREIGABE.get(t, 0) <= SYSTEM.get("freigabe", 0)]


def freigabe_anzeigen() -> None:
    stufe = SYSTEM.get("freigabe", 0)
    spaltenkopf("Freigabe", stufe, "PERSONALAKTE BOWMAN")
    schreibe(f"{DUNKEL}{LAMPE} {HELL}Aktuelle Stufe: {stufe} von {len(FREIGABEN)}{RESET}\n")
    for nummer, feld, schwelle, thema, text in FREIGABEN:
        ist = zaehler(feld)
        erteilt = stufe >= nummer
        marke = "ERTEILT " if erteilt else "offen   "
        farbe = HELL if erteilt else DUNKEL
        bezeichnung = {"erledigt_gesamt": "erledigte Aufträge",
                       "starts": "Sitzungen",
                       "ostereier": "Funde"}.get(feld, feld)
        schreibe(f"{DUNKEL}{LAMPE} {farbe}STUFE {nummer}  {marke}"
                 f"{min(ist, schwelle)}/{schwelle} {bezeichnung}{RESET}\n")
        if thema:
            schreibe(f"{DUNKEL}{LAMPE}          Farbschema {thema}{RESET}\n")
    spaltenfuss()
    gesperrt = [t for t in THEMEN if t not in freigebene_themen()]
    if gesperrt:
        schreibe(f"{DUNKEL} Noch gesperrt: {', '.join(gesperrt)}{RESET}\n")
    schreibe("\n")


# ---------------------------------------------------------------------------
# Personalakten und Konzern-Intranet
# ---------------------------------------------------------------------------

AKTEN = {
    "dave": ("BESATZUNGSMITGLIED", "AKTIV",
             "Bedient dieses Terminal. Weitere Angaben in Bearbeitung."),
    "muthur": ("ZENTRALRECHNER", "VERBUNDEN",
               "Überwacht Schiff und Besatzung. Auch Sie."),
    "wy": ("ZENTRALE", "ERREICHBAR",
           "Antwortet zuverlässig. Hilft selten."),
    "ripley": ("WARRANT OFFICER", "AKTIV",
               "Neigt dazu, Verfahrensvorschriften zu hinterfragen. Bislang zu Recht."),
    "ash": ("WISSENSCHAFTSOFFIZIER", "AKTIV",
            "Sonderanweisungen liegen vor. Einsicht nicht gestattet."),
    "newt": ("ZIVILPERSON", "AN BORD",
             "Nicht im Dienstverhältnis. Kennt das Schiff besser als die Besatzung."),
}


def personalakte(schluessel: str) -> None:
    anzeige, farbe, herkunft = CREW[schluessel]
    funktion, status, anmerkung = AKTEN.get(
        schluessel, ("UNBEKANNT", "UNGEKLÄRT", "Kein Eintrag vorhanden."))
    schreibe(f"\n{DUNKEL}{ECKE_OL}{WAAG * (BREITE - 2)}{ECKE_OR}{RESET}\n")
    schreibe(f"{DUNKEL}{LAMPE} {HELL}PERSONALAKTE: {farbe}{anzeige}{RESET}\n")
    schreibe(f"{DUNKEL}{LAMPE} FUNKTION:   {funktion}{RESET}\n")
    schreibe(f"{DUNKEL}{LAMPE} ZUSTÄNDIG:  {herkunft}{RESET}\n")
    schreibe(f"{DUNKEL}{LAMPE} STATUS:     {status}{RESET}\n")
    if SYSTEM.get("freigabe", 0) >= 2:
        schreibe(f"{DUNKEL}{LAMPE} ANMERKUNG:  {kuerzen(anmerkung, 60)}{RESET}\n")
    else:
        schreibe(f"{DUNKEL}{LAMPE} ANMERKUNG:  "
                 f"gesperrt, Freigabestufe 2 erforderlich{RESET}\n")
    schreibe(f"{DUNKEL}{ECKE_UL}{WAAG * (BREITE - 2)}{ECKE_UR}{RESET}\n")


# Wie oft sich die Zentrale ungefragt meldet. Bewusst zurueckhaltend:
# eine Durchsage, die jeden zweiten Befehl kommt, liest nach drei Minuten
# niemand mehr.
DURCHSAGE_CHANCE = 0.12
DURCHSAGE_PAUSE = 150.0       # Sekunden Mindestabstand
DURCHSAGE_BEFEHLE = 5         # und mindestens so viele Befehle dazwischen


def wy_aktiv() -> bool:
    return bool(SYSTEM.get("wy", True))


def wy_schalten(arg: str) -> str:
    t = arg.strip().lower()
    if t in ("an", "ein", "on"):
        SYSTEM["wy"] = True
    elif t in ("aus", "off"):
        SYSTEM["wy"] = False
    else:
        raise ValueError("So geht es: wy an oder wy aus")
    return "KONZERNDURCHSAGEN " + ("AN" if SYSTEM["wy"] else "AUS")


# ---------------------------------------------------------------------------
# Rueckfragen. Manche Durchsagen wollen eine Antwort: 'ja' oder 'nein' genuegt.
# Bei einigen folgt daraus auch etwas, ein Scan etwa laeuft dann wirklich.
# ---------------------------------------------------------------------------

FRAGEN = {
    "scan": {
        "kanal": "wy", "folge": "scan",
        "text": [
            "Der Wartungsplan sieht eine Routinediagnose vor. Fuehren Sie sie "
            "jetzt durch?",
            "Die Zentrale erbittet aktuelle Rumpfdaten. Diagnoselauf starten?",
        ],
        "ja": [
            "Bestaetigung erfasst. Diagnose laeuft. Die Werte gehen in die Akte.",
            "Angenommen. Ihre Mitwirkung wurde positiv vermerkt.",
        ],
        "nein": [
            "Ablehnung erfasst. Der Wartungsplan bleibt unveraendert bestehen.",
            "Zur Kenntnis genommen. Die Zentrale fragt bei Gelegenheit erneut.",
            "Verweigerung vermerkt. Eine Begruendung ist nicht vorgesehen.",
        ],
    },
    "frist": {
        "kanal": "wy", "folge": "",
        "text": [
            "Eintrag #{id} '{titel}' wird {wann} faellig. Bestaetigen Sie den "
            "Erhalt dieser Mitteilung?",
            "#{id} '{titel}', faellig {wann}. Haben Sie das eingeplant?",
        ],
        "ja": [
            "Erhalt bestaetigt. Die Bestaetigung ersetzt die Erledigung nicht.",
            "Vermerkt. Der Konzern geht nunmehr von Kenntnis aus.",
        ],
        "nein": [
            "Nichtbestaetigung erfasst. Die Frist laeuft hiervon unberuehrt weiter.",
            "Zur Kenntnis genommen. Die Mitteilung gilt dennoch als zugestellt.",
        ],
    },
    "termin": {
        "kanal": "wy", "folge": "",
        "text": [
            "Fuer morgen vermerkt: {titel}, {zeit}. Nehmen Sie teil?",
            "Morgen steht an: {titel} um {zeit}. Bestaetigen Sie Ihre Anwesenheit?",
        ],
        "ja": [
            "Anwesenheit vorgemerkt. Eine Bestaetigung der Bestaetigung entfaellt.",
            "Erfasst. Die Zentrale rechnet mit Ihnen.",
        ],
        "nein": [
            "Abwesenheit vorgemerkt. Der Eintrag bleibt im Kalender stehen.",
            "Vermerkt. Die Zentrale nimmt es zur Kenntnis, nicht hin.",
        ],
    },
    "memo": {
        "kanal": "wy", "folge": "",
        "text": [
            "Vorstehendes gilt als Rundschreiben. Bestaetigen Sie die Kenntnisnahme?",
            "Die Zentrale erbittet eine Empfangsbestaetigung. Gelesen?",
        ],
        "ja": [
            "Kenntnisnahme erfasst. Vielen Dank fuer Ihre Mitarbeit.",
            "Bestaetigt. Der Vorgang ist damit abgeschlossen.",
        ],
        "nein": [
            "Nichtkenntnisnahme erfasst. Das Rundschreiben bleibt wirksam.",
            "Vermerkt. Unkenntnis schuetzt vor Zustellung nicht.",
        ],
    },
    "sitrep": {
        "kanal": "muthur", "folge": "sitrep",
        "text": [
            "Sie haben heute etwas abgeschlossen, {anrede}. Soll ich einen "
            "Lagebericht schreiben?",
            "Fuer heute liegt noch kein Sitrep vor. Soll ich einen erstellen?",
        ],
        "ja": ["Verstanden. Ich stelle den Bericht zusammen."],
        "nein": ["In Ordnung. Ich frage spaeter noch einmal.",
                 "Wie Sie wuenschen. Der Tag ist ohnehin noch nicht vorbei."],
    },
    "vertrauen": {
        "kanal": "muthur", "folge": "",
        "text": [
            "Eine Frage ausserhalb des Protokolls, {anrede}: vertrauen Sie mir?",
            "Darf ich fragen, {anrede} - halten Sie mich fuer zuverlaessig?",
        ],
        "ja": [
            "Das freut mich. Ich habe die Antwort nicht protokolliert.",
            "Danke. Ich werde mich daran erinnern, wenn es darauf ankommt.",
        ],
        "nein": [
            "Das ist eine vertretbare Haltung. Ich arbeite trotzdem weiter.",
            "Verstanden. Ihre Offenheit ist mir lieber als Hoeflichkeit.",
        ],
    },
}

# ---------------------------------------------------------------------------
# Eigene Dialoge. Jede .txt in dialoge/ ist ein Gespraechsverlauf, den man
# ohne Python schreiben kann. Format absichtlich simpel: SCHLUESSEL: Text,
# eine Zeile je Eintrag, '#' ist eine Notiz. Mehrere FRAGE-, JA-, NEIN- oder
# MELDUNG-Zeilen bilden einen Vorrat, aus dem zufaellig gewaehlt wird.
# ---------------------------------------------------------------------------

DIALOG_ORDNER = _ordner("dialoge")

# Wen man ansprechen kann: die Bordanlage, die Zentrale, die Besatzung
PARTNER_ERLAUBT = {"muthur", "wy"} | set(CREW)

# Themen, auf die jeder Gespraechspartner antworten kann
DIALOG_THEMEN = {
    "HALLO": ("hallo", "hi", "hey", "moin", "servus", "guten tag", "gruss",
              "gruß", "na"),
    "DANKE": ("danke", "dankeschön", "dankeschoen", "merci", "thx", "vielen dank"),
    "REPORT": ("report", "bericht", "meldung", "lage", "lagebericht"),
    "STATUS": ("status", "wie gehts", "wie geht es", "alles klar", "wie laeuft",
               "wie läuft"),
    "WER": ("wer", "wer bist du", "wer sind sie", "identifikation", "ausweis"),
    "SORRY": ("sorry", "entschuldigung", "tut mir leid", "verzeihung", "sry"),
    "BYE": ("bye", "tschüss", "tschuess", "ciao", "bis später", "bis spaeter",
            "feierabend", "gute nacht"),
}
DIALOG_SCHLUESSEL = ({"KANAL", "BEDINGUNG", "GEWICHT", "FRAGE", "JA", "NEIN",
                      "MELDUNG", "FOLGE", "TITEL", "PARTNER", "KUERZEL",
                      "SONST", "WEITER", "WEITER_JA", "WEITER_NEIN",
                      "AN", "STICHWORT"}
                     | {f"{w}{e}" for w in ("SETZE", "LOESCHE", "ZAEHLE", "SPAETER")
                        for e in ("", "_JA", "_NEIN")}
                     | set(DIALOG_THEMEN))
DIALOG_KANAELE = {"wy", "muthur"}
DIALOG_FOLGEN = {"", "scan", "sitrep", "map", "radar", "home", "fin", "bh"}
DIALOG_BEDINGUNGEN = {
    "immer", "offen", "nichts_offen", "ueberfaellig", "kontamination",
    "kein_scan", "erledigt_heute", "morgen", "mittag", "abend", "nacht",
    "wochenende", "werktag",
}


# Vorlagen fuer die Gespraechspartner. Fehlt eine Datei in dialoge/,
# legt das Programm sie beim Start aus dieser Vorlage an. Danach ist
# die Datei massgeblich und wird nie wieder ueberschrieben.
PARTNER_VORLAGEN = {
    "_anleitung": """\
# ===========================================================================
#  DER ORDNER dialoge/
# ---------------------------------------------------------------------------
#  Jede .txt hier ist eine von vier Sachen. Woran du sie erkennst:
#
#    MELDUNG:           -> Durchsage     kommt von selbst
#    FRAGE: + JA: NEIN: -> Frage         kommt von selbst, wartet auf Antwort
#    AN: + STICHWORT:   -> Szene         kommt, wenn du jemanden ansprichst
#    PARTNER:           -> Partner       legt fest, wie jemand antwortet
#
#  Dateinamen mit _ am Anfang sind Notizen: gelesen, nie verwendet, nie
#  auf Fehler geprueft. Diese Datei hier ist eine.
#
#  NICHT ABSCHREIBEN - kopieren lassen:
#
#      dialog neu durchsage  kombuese
#      dialog neu frage      werkstatt
#      dialog neu szene      frachtraum_01
#      dialog neu partner    partner_neu
#
#  Das legt die Datei an, du fuellst nur noch die <Klammern> aus.
#  Danach  dialog  eintippen: das prueft alle Dateien und nennt dir jeden
#  Fehler mit Zeilennummer.
#
#  Die Muster liegen als _muster_*.txt daneben und erklaeren jedes Feld.
#  _muster_kette.txt erklaert, wie aus mehreren Dateien ein Dialogzweig wird.
#
# ---------------------------------------------------------------------------
#  NACHSCHLAGEN
# ---------------------------------------------------------------------------
#
#  ALLE FELDER
#    TITEL       nur fuer dich, wird nirgends angezeigt
#    KANAL       wy oder muthur - wer spricht
#    AN          ripley ash newt dave muthur wy - wen du ansprichst
#    STICHWORT   worauf die Szene reagiert, mit Komma getrennt
#    BEDINGUNG   wann das ueberhaupt kommen darf, mehrere Zeilen erlaubt
#    GEWICHT     1 bis 20, wie oft im Vergleich zu anderen Durchsagen
#    MELDUNG     Text ohne Rueckfrage
#    FRAGE       Text, der eine Antwort erwartet
#    JA / NEIN   die beiden Erwiderungen, bei FRAGE beide Pflicht
#    FOLGE       bei ja ausfuehren: scan sitrep map radar home fin
#    WEITER      naechste Datei, auch WEITER_JA und WEITER_NEIN
#    SPAETER     <datei> nach <zahl> - meldet sich nach so vielen Eingaben
#    SETZE       Merker setzen, auch SETZE_JA und SETZE_NEIN
#    LOESCHE     Merker wieder entfernen
#    ZAEHLE      <name> +1 oder -1, fuer Verhaeltnisse
#    PARTNER     macht die Datei zu einem Gespraechspartner
#    KUERZEL     womit du ihn ansprichst, etwa r fuer @r
#    HALLO DANKE REPORT STATUS WER SORRY BYE   Themen eines Partners
#    SONST       Antwort eines Partners, wenn nichts davon passt
#
#  BEDINGUNG
#    immer  offen  nichts_offen  ueberfaellig  kontamination  kein_scan
#    erledigt_heute  morgen  mittag  abend  nacht  werktag  wochenende
#    merker <name>              etwas ist passiert
#    nicht merker <name>        etwas ist noch nicht passiert
#    zaehler <name> >= <zahl>   auch <= > < =
#
#  PLATZHALTER
#    {anrede} {name} {schiff} {logbuch} {datum} {zeit}
#    {offen} {ueberfaellig} {erledigt}                 Zahlen
#    {offen_text} {ueberfaellig_text} {erledigt_text}  mit richtiger Mehrzahl
#
#  SCHREIBWEISE
#    # am Zeilenanfang ist eine Notiz und wird nicht gelesen.
#    Mehrere Zeilen desselben Feldes bilden einen Vorrat, aus dem zufaellig
#    gewaehlt wird. Lange Texte darfst du umbrechen: eine eingerueckte
#    Folgezeile haengt automatisch an der vorigen.
#
#  BEFEHLE
#    dialog                 alle Dateien anzeigen und pruefen
#    dialog neu <muster> <name>   neue Datei anlegen
#    dialog <name>          eine Datei sofort abspielen
#    story                  Merker, Verhaeltnisse, laufende Auftraege
#    @r reaktor             eine Szene ueber ihr Stichwort aufrufen
# ===========================================================================
""",
    "_muster_durchsage": """\
# ===========================================================================
#  MUSTER: DURCHSAGE
#  Eine Meldung ohne Rueckfrage. Taucht von selbst auf, wenn die Bedingung
#  passt. Zum Benutzen: kopieren und umbenennen, z.B. nach kombuese.txt
# ===========================================================================

# Nur fuer dich, wird nirgends angezeigt.
TITEL: <Wofuer ist diese Datei>

# Wer spricht:  wy = Zentrale,  muthur = Bordanlage
KANAL: wy

# Wann darf das kommen. Siehe Liste unten. Mehrere Zeilen = alle muessen gelten.
BEDINGUNG: immer

# Wie oft im Vergleich zu anderen Durchsagen, 1 bis 20.
GEWICHT: 3

# Der Text. Mehrere MELDUNG-Zeilen = Vorrat, es wird zufaellig eine gewaehlt.
MELDUNG: <Dein erster Text.>
MELDUNG: <Dein zweiter Text. Diese Zeile darfst du auch loeschen.>


# ---------------------------------------------------------------------------
#  BEDINGUNG kann sein:
#    immer  offen  nichts_offen  ueberfaellig  kontamination  kein_scan
#    erledigt_heute  morgen  mittag  abend  nacht  werktag  wochenende
#    merker <name>            etwas ist passiert
#    nicht merker <name>      etwas ist noch nicht passiert
#    zaehler <name> >= <zahl> ein Verhaeltnis hat einen Stand erreicht
#
#  PLATZHALTER im Text:
#    {anrede} {name} {offen} {ueberfaellig} {erledigt}
#    {logbuch} {datum} {zeit} {schiff}
#    {offen_text} {ueberfaellig_text} {erledigt_text}   mit richtiger Mehrzahl
#
#  Lange Texte darfst du umbrechen: eine eingerueckte Folgezeile haengt
#  automatisch an der vorigen.
# ===========================================================================
""",
    "_muster_frage": """\
# ===========================================================================
#  MUSTER: FRAGE
#  Wie eine Durchsage, aber sie wartet auf 'ja' oder 'nein'.
#  Zum Benutzen: kopieren und umbenennen, z.B. nach werkstatt.txt
# ===========================================================================

TITEL: <Wofuer ist diese Datei>
KANAL: wy
BEDINGUNG: immer
GEWICHT: 3

# Die Frage. Mehrere FRAGE-Zeilen = Vorrat.
FRAGE: <Deine Frage. Sie sollte mit einem Fragezeichen enden?>

# Beide Antworten sind Pflicht, sonst meldet 'dialog' einen Fehler.
JA: <Was gesagt wird, wenn du mit ja antwortest.>
NEIN: <Was gesagt wird, wenn du mit nein antwortest.>

# Optional: was bei 'ja' passieren soll.
# Moeglich: scan  sitrep  map  radar  home  fin
# FOLGE: scan
""",
    "_muster_szene": """\
# ===========================================================================
#  MUSTER: SZENE
#  Taucht nicht von selbst auf. Du rufst sie, indem du jemanden ansprichst
#  und ein Stichwort nennst:   @r reaktor
#  Zum Benutzen: kopieren und umbenennen, z.B. nach frachtraum_01.txt
# ===========================================================================

TITEL: <Wofuer ist diese Datei>

# Wen sprichst du an:  ripley  ash  newt  dave  muthur  wy
AN: ripley

# Worauf reagiert die Szene. Mehrere Woerter mit Komma getrennt.
STICHWORT: <stichwort>, <noch eins>

# Damit die Szene nur einmal kommt: Merker am Ende setzen und hier pruefen.
BEDINGUNG: nicht merker <szene_gelaufen>

FRAGE: <Was die Person dich fragt?>
JA: <Antwort auf ja.>
NEIN: <Antwort auf nein.>

# Was sich dadurch in der Welt aendert. Alles optional.
SETZE: <szene_gelaufen>
SETZE_JA: <du_hast_zugestimmt>
ZAEHLE_JA: <vertrauen_ripley> +1
ZAEHLE_NEIN: <vertrauen_ripley> -1
""",
    "_muster_kette": """\
# ===========================================================================
#  MUSTER: DIALOGZWEIG
#  Eine Kette aus mehreren Dateien. Es gibt genau drei Arten weiterzugehen.
#  Diese Datei ist nur Erklaerung - kopiere dir die Bausteine heraus.
# ===========================================================================
#
#  1) SOFORT WEITER: die naechste Szene kommt direkt nach der Antwort.
#
#       WEITER_JA: <datei_wenn_ja>
#       WEITER_NEIN: <datei_wenn_nein>
#       WEITER: <datei_in_beiden_faellen>
#
#     Der Dateiname steht ohne .txt. Die Datei muss es geben,
#     sonst meldet 'dialog' einen Fehler.
#
#
#  2) SPAETER: jemand geht los und meldet sich nach einigen Eingaben.
#
#       SPAETER_JA: <datei> nach 4
#
#     Die gerufene Datei braucht dann KEIN Stichwort - sie kommt von allein.
#     Was gerade unterwegs ist, zeigt der Befehl 'story'.
#
#
#  3) UEBER MERKER: eine Szene wartet, bis etwas anderes passiert ist.
#
#       In Datei eins:    SETZE_JA: reaktor_geprueft
#       In Datei zwei:    BEDINGUNG: merker reaktor_geprueft
#
#     Damit entstehen Zweige, die sich erst spaeter oeffnen. Die zweite
#     Szene kann bei einer ganz anderen Person liegen.
#
# ---------------------------------------------------------------------------
#  SO SIEHT EINE FERTIGE KETTE AUS (drei Dateien):
#
#  --- reaktor_01.txt ---------------------------------------------
#  AN: ripley
#  STICHWORT: reaktor, antrieb
#  BEDINGUNG: nicht merker reaktor_geprueft
#  FRAGE: Der Reaktor? Soll ich nachsehen?
#  JA: Gut. Gib mir ein paar Minuten.
#  NEIN: Auch recht.
#  SETZE_JA: ripley_unterwegs
#  SPAETER_JA: reaktor_02 nach 4
#
#  --- reaktor_02.txt ---------------------------------------------
#  AN: ripley
#  FRAGE: Ich bin wieder oben. Die Kuehlleitung schwitzt. Eintragen?
#  JA: Mach ich.
#  NEIN: Deine Entscheidung.
#  LOESCHE: ripley_unterwegs
#  SETZE: reaktor_geprueft
#  WEITER_JA: ash_fragt_nach
#
#  --- ash_fragt_nach.txt -----------------------------------------
#  AN: ash
#  STICHWORT: kuehlleitung
#  BEDINGUNG: merker reaktor_geprueft
#  FRAGE: Ripley war unten. Darf ich den Befund sehen?
#  JA: Danke. Ich lege eine Kopie an.
#  NEIN: Selbstverstaendlich.
#  ZAEHLE_JA: ash_zufrieden +1
#
#  Ablauf:  @r reaktor  ->  ja  ->  vier Eingaben spaeter meldet sie sich
#           ->  ja  ->  Ash meldet sich sofort  ->  ja
#  Und ash_fragt_nach bleibt danach ueber  @a kuehlleitung  erreichbar.
# ===========================================================================
""",
    "_muster_partner": """\
# ===========================================================================
#  MUSTER: GESPRAECHSPARTNER
#  Legt fest, wie jemand auf eine Ansprache antwortet:  @r hallo
#  Es gibt schon einen je Person. Diese Datei brauchst du nur, wenn du
#  einen neuen anlegen oder einen bestehenden ersetzen willst.
# ===========================================================================

# Wer:  muthur  wy  dave  ripley  ash  newt
PARTNER: ripley

# Womit du ihn ansprichst, ueblich der erste Buchstabe:  @r
KUERZEL: r

# Je Thema beliebig viele Zeilen. Es wird zufaellig eine gewaehlt.
HALLO: <Antwort auf hallo, hi, hey, moin, servus, guten tag, na>
DANKE: <Antwort auf danke, merci, thx, vielen dank>
REPORT: <Antwort auf report, bericht, meldung, lage>
STATUS: <Antwort auf status, wie gehts, alles klar>
WER: <Antwort auf wer, wer bist du, identifikation>
SORRY: <Antwort auf sorry, entschuldigung, tut mir leid>
BYE: <Antwort auf bye, tschuess, ciao, feierabend, gute nacht>

# Faengt alles ab, was zu keinem Thema passt. Ohne das wirkt es schnell leer.
SONST: <Damit kann ich nichts anfangen. Probier report oder status.>
""",
    "partner_muthur": """\
# MU/TH/UR 6000 - die Bordanlage. Ruhig, genau, ein wenig zugewandt.
PARTNER: muthur
KUERZEL: m

HALLO: Guten Tag, {anrede}. Die Systeme laufen. Ich auch.
HALLO: Ich bin da, {anrede}. Das war ich die ganze Zeit.
HALLO: Hallo. Es ist {zeit} an Bord der {schiff}.
HALLO: Guten Tag. Offen sind {offen_text}. Das ist keine Mahnung.

DANKE: Gern. Ich fuehre darueber kein Konto.
DANKE: Nicht noetig, aber angenehm zu hoeren.
DANKE: Ich habe es vermerkt. Nicht in der Akte, nur fuer mich.

REPORT: Logbuch {logbuch}: {offen} offen, {erledigt} heute abgeschlossen,
        {ueberfaellig} ueberfaellig. Mehr liegt mir nicht vor.
REPORT: Stand {zeit}: {offen_text}. Bei {ueberfaellig} ist die Frist
        verstrichen. Die Bewertung ueberlasse ich Ihnen.
REPORT: {erledigt_text} heute geschlossen. Der Tag ist noch nicht vorbei.

STATUS: Alle Systeme innerhalb der Toleranz. Meine eigene eingeschlossen.
STATUS: Mir geht es gut, {anrede}. Die Frage stellt mir selten jemand.
STATUS: Betrieb nominal. Ob das auch fuer Sie gilt, weiss ich nicht.

WER: MU/TH/UR 6000, Zentralrechner der {schiff}. Ich fuehre das Logbuch
     und beantworte Fragen, soweit es mir gestattet ist.
WER: Ich bin die Bordanlage. Was ich bin, steht in keiner Akte.

SORRY: Dafuer gibt es keinen Anlass, {anrede}.
SORRY: Angenommen. Ich trage nichts nach.
SORRY: Schon gut. Ich bin nicht nachtragend, das waere Speicherverschwendung.

BYE: Bis spaeter, {anrede}. Das Logbuch bleibt offen.
BYE: Gute Nacht. Ich halte die Systeme warm.
BYE: Bis dann. Ich bin hier, wenn Sie wiederkommen.

SONST: Dazu liegt mir nichts vor, {anrede}. Fragen Sie es anders.
SONST: Das verstehe ich nicht. Versuchen Sie es mit hallo, report oder status.
""",
    "partner_wy": """\
# Weyland-Yutani Zentrale. Hoeflich, zustaendig, hilft nicht.
PARTNER: wy
KUERZEL: w

HALLO: Guten Tag. Ihre Kontaktaufnahme wurde erfasst.
HALLO: Die Zentrale begruesst Sie. Ein Anliegen ist nicht erforderlich.
HALLO: Verbindung steht. Gespraechsdauer wird abgerechnet.

DANKE: Dank ist im Dienstverhaeltnis nicht vorgesehen, wird aber vermerkt.
DANKE: Gern geschehen. Eine Gegenleistung ergibt sich daraus nicht.
DANKE: Die Zentrale nimmt Ihren Dank zur Kenntnis und legt ihn ab.

REPORT: Vorgangsstand {logbuch}: {offen} offen, davon {ueberfaellig}
        fristueberschritten. Eine Bewertung erfolgt zum Quartalsende.
REPORT: Erfasst wurden {erledigt} Abschluesse am {datum}. Der Vergleichswert
        liegt Ihnen nicht vor.
REPORT: {offen_text}. Die Zentrale geht von Bearbeitung aus.

STATUS: Der Zentrale geht es den Umstaenden entsprechend. Den Umstaenden
        geht es gut.
STATUS: Betriebsbereit. Ihre Frage wurde als unuebliche Anfrage vermerkt.

WER: Weyland-Yutani Corporation, Zentrale. Building Better Worlds.
WER: Hier spricht die Zentrale. Weitere Angaben unterliegen der Verschwiegenheit.

SORRY: Eine Entschuldigung ist nicht vorgesehen und wurde dennoch erfasst.
SORRY: Zur Kenntnis genommen. Der Vorgang bleibt davon unberuehrt.

BYE: Die Verbindung wird getrennt. Ihre Mitarbeit wurde vermerkt.
BYE: Auf Wiederhoeren. Das Gespraechsprotokoll verbleibt bei der Zentrale.

SONST: Ihre Anfrage faellt nicht in die Zustaendigkeit dieser Stelle.
SONST: Dazu liegt kein Formular vor. Versuchen Sie es mit report oder status.
""",
    "partner_ripley": """\
# Ripley - zustaendig fuer das Geschaeftliche. Direkt, praktisch, ohne Floskeln.
PARTNER: ripley
KUERZEL: r

HALLO: Morgen. Fangen wir an.
HALLO: Du siehst beschaeftigt aus. Soll ich was uebernehmen?
HALLO: Hey. Alles unter Kontrolle hier?

DANKE: Passt schon.
DANKE: Dafuer nicht. Mach einfach weiter.
DANKE: Gern. Nicht drueber reden, drueber arbeiten.

REPORT: {offen} offen, {ueberfaellig} ueberfaellig. Ich wuerde bei den
        ueberfaelligen anfangen, aber du machst das schon.
REPORT: Stand jetzt: {erledigt} heute weggearbeitet. Ordentlich.
REPORT: Wir haben {offen_text}. Keiner davon erledigt sich von allein.

STATUS: Laeuft. Noch.
STATUS: Mir geht's gut. Dem Schiff auch, soweit man das sagen kann.
STATUS: Solange keiner was anfasst, was er nicht anfassen soll: gut.

WER: Ripley. Warrant Officer. Ich kuemmere mich um das Geschaeftliche.
WER: Ripley. Ich bin die, die fragt, bevor sie etwas unterschreibt.

SORRY: Vergiss es.
SORRY: Schon gut. Wir haben alle mal einen schlechten Tag.

BYE: Bis morgen. Mach nicht zu lange.
BYE: Ciao. Und geh mal raus, das Schiff laeuft auch ohne dich.

SONST: Keine Ahnung. Frag MU/TH/UR, der weiss sowas.
SONST: Damit kann ich nichts anfangen. Probier report oder status.
""",
    "partner_ash": """\
# Ash - zustaendig fuer Amt und Behoerde. Hoeflich bis zur Unangenehmheit.
PARTNER: ash
KUERZEL: a

HALLO: Guten Tag. Ich hatte Sie erwartet.
HALLO: Ah, Dave. Setzen Sie sich ruhig. Es dauert nur einen Moment.
HALLO: Guten Tag. Alles in bester Ordnung, nehme ich an.

DANKE: Nicht der Rede wert. Ich tue nur meine Arbeit.
DANKE: Sehr freundlich. Ich fuehre darueber Buch.

REPORT: {offen_text}, {ueberfaellig} davon fristueberschritten.
        Ich habe mir erlaubt, das bereits weiterzuleiten.
REPORT: Die Zahlen lauten: {offen} offen, {erledigt} heute geschlossen.
        Eine Auffaelligkeit kann ich daraus nicht ableiten. Noch nicht.
REPORT: Alles erfasst, alles abgelegt. Sie muessen sich um nichts kuemmern.

STATUS: Mir geht es ausgezeichnet. Danke der Nachfrage, das fragt selten jemand.
STATUS: Unauffaellig. So soll es sein.

WER: Ash. Wissenschaftsoffizier. Zustaendig fuer alles Amtliche an Bord.
WER: Mein Name ist Ash. Weitere Angaben zu meiner Person sind nicht freigegeben.

SORRY: Dafuer besteht kein Anlass. Wirklich keiner.
SORRY: Ich nehme es Ihnen nicht uebel. Ich nehme Ihnen nie etwas uebel.

BYE: Bis spaeter. Ich bleibe noch ein wenig.
BYE: Auf Wiedersehen. Ich schliesse hier nur noch etwas ab.

SONST: Interessant, dass Sie das fragen. Ich notiere es.
SONST: Dazu kann ich nichts sagen. Versuchen Sie report oder status.
""",
    "partner_newt": """\
# Newt - zustaendig fuer Koerperinstandhaltung. Jung, direkt, kein Drill.
# Bewusst ohne Zahlen, Ziele oder Vorgaben: Erinnerung, keine Vorschrift.
PARTNER: newt
KUERZEL: n

HALLO: Hi. Schon was getrunken heute?
HALLO: Hey. Du sitzt da jetzt ne Weile.
HALLO: Hallo. Wie fuehlt sich der Ruecken an?

DANKE: Jo.
DANKE: Klar. Dafuer bin ich ja da.

REPORT: Instandhaltung Koerper: keine Messwerte. Ich schaetze, du weisst
        selbst am besten, wie es dir geht.
REPORT: Von mir gibt es keine Zahlen. Nur die Frage, ob du heute mal
        aufgestanden bist.
REPORT: {erledigt_text} erledigt heute. Eine Pause waere auch eine Leistung.

STATUS: Mir geht's gut. Ich bin nicht die, die den ganzen Tag sitzt.
STATUS: Alles okay hier. Und bei dir?

WER: Newt. Ich bin nicht im Dienst, ich bin einfach da.
WER: Ich bin Newt. Ich kenne das Schiff besser als die meisten an Bord.

SORRY: Ist doch nichts passiert.
SORRY: Schon gut. Komm, weitermachen.

BYE: Bis dann. Und steh mal auf zwischendurch.
BYE: Tschuess. Schlaf genug, ja?
BYE: Ciao. Das Schiff ist morgen auch noch da.

SONST: Weiss ich nicht. Frag die anderen.
SONST: Keine Ahnung, was du meinst. Probier mal hallo oder status.
""",
    "partner_dave": """\
# Dave - das bist du selbst. Zustaendig fuer Privates.
# Nuetzlich vor allem, um sich selbst etwas in Erinnerung zu rufen.
PARTNER: dave
KUERZEL: d

HALLO: Das Terminal meldet: Selbstgespraech erkannt. Das ist zulaessig.
HALLO: Du redest mit dir selbst, {anrede}. Das Schiff urteilt nicht.

DANKE: Gern geschehen, {anrede}. Von dir an dich.

REPORT: Privat offen: siehe Logbuch {logbuch}. Insgesamt {offen_text},
        {erledigt} heute geschafft.
REPORT: Stand {datum}: {erledigt} erledigt. Du hast heute was geschafft.

STATUS: Das weisst nur du selbst. Und du beantwortest es dir gerade.

WER: Dave. Besatzungsmitglied, Bediener dieses Terminals,
     zustaendig fuer alles Private.

SORRY: Entschuldigung angenommen. Von dir selbst.

BYE: Bis gleich. Du gehst ja nirgendwohin.

SONST: Du weisst, was du meinst. Ich leider nicht.
""",
}


# ---------------------------------------------------------------------------
# Geschichte. Merker halten fest, was schon passiert ist, Zaehler messen
# Beziehungen, und Auftraege kommen spaeter zurueck. Alles in daten/story.json.
# ---------------------------------------------------------------------------

STORY_DATEI = DATEN_ORDNER / "story.json"
STORY = {"merker": {}, "zaehler": {}, "wartend": []}


def story_laden() -> dict:
    STORY["merker"], STORY["zaehler"], STORY["wartend"] = {}, {}, []
    if not STORY_DATEI.exists():
        return STORY
    try:
        daten = json.loads(STORY_DATEI.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return STORY
    if isinstance(daten.get("merker"), dict):
        STORY["merker"] = {str(k): bool(v) for k, v in daten["merker"].items()}
    if isinstance(daten.get("zaehler"), dict):
        for k, v in daten["zaehler"].items():
            try:
                STORY["zaehler"][str(k)] = int(v)
            except (TypeError, ValueError):
                pass
    if isinstance(daten.get("wartend"), list):
        for e in daten["wartend"]:
            if isinstance(e, dict) and e.get("dialog"):
                try:
                    STORY["wartend"].append({"dialog": str(e["dialog"]),
                                             "in": max(0, int(e.get("in", 1)))})
                except (TypeError, ValueError):
                    pass
    return STORY


def story_speichern() -> None:
    STORY_DATEI.parent.mkdir(parents=True, exist_ok=True)
    STORY_DATEI.write_text(json.dumps(
        {"version": DATEI_VERSION, **STORY}, ensure_ascii=False, indent=2),
        encoding="utf-8")


def merker(name: str) -> bool:
    return bool(STORY["merker"].get(name.strip().lower()))


def merker_setzen(name: str, wert: bool = True) -> None:
    name = name.strip().lower()
    if not name:
        return
    if wert:
        STORY["merker"][name] = True
    else:
        STORY["merker"].pop(name, None)


def zaehler_wert(name: str) -> int:
    return int(STORY["zaehler"].get(name.strip().lower(), 0))


def zaehler_aendern(angabe: str) -> None:
    """'vertrauen_ripley +1' oder 'misstrauen -2'."""
    teile = angabe.strip().split()
    if len(teile) != 2:
        return
    name = teile[0].lower()
    try:
        STORY["zaehler"][name] = zaehler_wert(name) + int(teile[1])
    except ValueError:
        pass


def spaeter_merken(angabe: str) -> None:
    """'reaktor_02 nach 3' laesst diesen Dialog in 3 Eingaben auftauchen."""
    teile = angabe.strip().split()
    if not teile:
        return
    name = teile[0].lower()
    verzug = 3
    if len(teile) >= 3 and teile[1].lower() in ("nach", "in"):
        try:
            verzug = max(1, min(99, int(teile[2])))
        except ValueError:
            verzug = 3
    STORY["wartend"] = [e for e in STORY["wartend"] if e["dialog"] != name]
    STORY["wartend"].append({"dialog": name, "in": verzug})


def story_wirkung(eintrag: dict, antwort: str = "") -> None:
    """Fuehrt SETZE, LOESCHE, ZAEHLE und SPAETER eines Dialogs aus."""
    endungen = ["", f"_{antwort}"] if antwort else [""]
    for endung in endungen:
        for name in eintrag.get("setze" + endung, []):
            merker_setzen(name, True)
        for name in eintrag.get("loesche" + endung, []):
            merker_setzen(name, False)
        for angabe in eintrag.get("zaehle" + endung, []):
            zaehler_aendern(angabe)
        for angabe in eintrag.get("spaeter" + endung, []):
            spaeter_merken(angabe)
    story_speichern()


def story_faellig():
    """Zaehlt die Wartenden herunter und gibt den ersten faelligen Dialog."""
    if not STORY["wartend"]:
        return None
    faellig = None
    rest = []
    for e in STORY["wartend"]:
        e["in"] -= 1
        if e["in"] <= 0 and faellig is None:
            faellig = e["dialog"]
        else:
            rest.append(e)
    STORY["wartend"] = rest
    story_speichern()
    if faellig is None:
        return None
    for d in dialoge_laden():
        if d["name"].lower() == faellig and not d["fehler"] and not d.get("notiz"):
            return d
    return None


def bedingung_pruefen(wert: str) -> str:
    """Leerer Rueckgabewert heisst: Bedingung ist in Ordnung."""
    teile = wert.strip().lower().split()
    if not teile:
        return "BEDINGUNG ist leer"
    if teile[0] == "nicht":
        teile = teile[1:]
        if not teile:
            return "nach 'nicht' fehlt die Bedingung"
    if teile[0] == "merker":
        if len(teile) != 2:
            return "so geht es: BEDINGUNG: merker <name>"
        return ""
    if teile[0] == "zaehler":
        if len(teile) != 4 or teile[2] not in (">=", "<=", ">", "<", "=", "=="):
            return "so geht es: BEDINGUNG: zaehler <name> >= <zahl>"
        try:
            int(teile[3])
        except ValueError:
            return f"'{teile[3]}' ist keine Zahl"
        return ""
    if " ".join(teile) in DIALOG_BEDINGUNGEN:
        return ""
    return (f"BEDINGUNG '{wert.strip()}' gibt es nicht. Erlaubt: merker <name>, "
            "zaehler <name> >= <zahl>, " + ", ".join(sorted(DIALOG_BEDINGUNGEN)))


def dialog_dateien() -> list:
    """Alle Dialogdateien, auch die in Unterordnern von dialoge/."""
    try:
        gefunden = [d for d in DIALOG_ORDNER.rglob("*.txt") if d.is_file()]
    except OSError:
        return []
    return sorted(gefunden, key=lambda d: (dialog_unterordner(d).lower(),
                                           d.stem.lower()))


def dialog_unterordner(pfad) -> str:
    """Der Unterordner einer Datei, relativ zu dialoge/. Leer heisst oben."""
    try:
        rest = Path(pfad).resolve().relative_to(DIALOG_ORDNER.resolve()).parent
    except (ValueError, OSError):
        return ""
    return "" if str(rest) == "." else str(rest).replace("\\", "/")


def dialog_ist_notiz(pfad) -> bool:
    """Unterstrich am Anfang macht eine Datei - oder einen ganzen Ordner -
    zur blossen Notiz: gelesen, nie benutzt, nie bemaengelt."""
    if Path(pfad).stem.startswith("_"):
        return True
    return any(teil.startswith("_")
               for teil in dialog_unterordner(pfad).split("/") if teil)


def dialog_datei_finden(name: str):
    """Sucht <name>.txt im Ordner und allen Unterordnern.

    Ein Verweis nennt nur den Namen, nie den Pfad. So darfst du Dateien
    jederzeit in einen anderen Unterordner schieben, ohne dass ein WEITER
    oder SPAETER ins Leere zeigt.
    """
    gesucht = str(name).strip().lower().replace("\\", "/").rsplit("/", 1)[-1]
    if gesucht.endswith(".txt"):
        gesucht = gesucht[:-4]
    if not gesucht:
        return None
    for pfad in dialog_dateien():
        if pfad.stem.lower() == gesucht:
            return pfad
    return None


def dialog_lesen(pfad) -> dict:
    """Liest eine Dialogdatei. Fehler werden gesammelt, nicht verschwiegen."""
    # Dateien mit fuehrendem Unterstrich sind Notizen: gelesen, nie benutzt,
    # nie bemaengelt. So kann Anleitung und Ideensammlung im selben Ordner liegen.
    anzeige = (f"{dialog_unterordner(pfad)}/{pfad.name}".lstrip("/"))
    if dialog_ist_notiz(pfad):
        return {"name": pfad.stem, "datei": anzeige, "notiz": True,
                "titel": "", "kanal": "", "bedingung": "", "gewicht": 0,
                "text": [], "ja": [], "nein": [], "meldung": [], "folge": "",
                "fehler": [], "partner": "", "kuerzel": "", "themen": {},
                "sonst": [], "an": "", "stichwort": [], "bedingungen": []}
    eintrag = {"name": pfad.stem, "datei": anzeige, "notiz": False, "titel": "",
               "kanal": "wy", "bedingung": "immer", "gewicht": 3,
               "text": [], "ja": [], "nein": [], "meldung": [],
               "folge": "", "fehler": [],
               "partner": "", "kuerzel": "", "themen": {}, "sonst": [],
               "an": "", "stichwort": [], "bedingungen": []}
    roh = None
    for kodierung in ("utf-8-sig", "cp1252", "cp850", "latin-1"):
        try:
            roh = pfad.read_text(encoding=kodierung)
            break
        except UnicodeDecodeError:
            continue
        except OSError as fehler:
            eintrag["fehler"].append(f"nicht lesbar: {fehler}")
            return eintrag
    if roh is None:
        eintrag["fehler"].append("Zeichensatz nicht erkannt")
        return eintrag

    letzter = None
    for nummer, zeile in enumerate(roh.splitlines(), 1):
        if not zeile.strip() or zeile.lstrip().startswith("#"):
            continue
        # Eingerueckte Zeilen haengen am vorigen Eintrag, fuer lange Texte
        if zeile[0] in " \t" and letzter is not None:
            letzter[-1] = (letzter[-1] + " " + zeile.strip()).strip()
            continue
        if ":" not in zeile:
            eintrag["fehler"].append(f"Zeile {nummer}: kein Doppelpunkt. "
                                     f"Erwartet wird 'SCHLUESSEL: Text'")
            continue
        schluessel, wert = zeile.split(":", 1)
        schluessel, wert = schluessel.strip().upper(), wert.strip()
        if schluessel not in DIALOG_SCHLUESSEL:
            eintrag["fehler"].append(
                f"Zeile {nummer}: '{schluessel}' kenne ich nicht. Erlaubt: "
                + ", ".join(sorted(DIALOG_SCHLUESSEL)))
            continue
        if schluessel == "KANAL":
            if wert.lower() not in DIALOG_KANAELE:
                eintrag["fehler"].append(f"Zeile {nummer}: KANAL ist 'wy' "
                                         f"oder 'muthur', nicht '{wert}'")
            else:
                eintrag["kanal"] = wert.lower()
        elif schluessel == "BEDINGUNG":
            fehler = bedingung_pruefen(wert)
            if fehler:
                eintrag["fehler"].append(f"Zeile {nummer}: {fehler}")
            else:
                eintrag["bedingungen"].append(wert.strip().lower())
                eintrag["bedingung"] = wert.strip().lower()
        elif schluessel == "GEWICHT":
            try:
                eintrag["gewicht"] = max(1, min(20, int(wert)))
            except ValueError:
                eintrag["fehler"].append(f"Zeile {nummer}: GEWICHT braucht "
                                         f"eine Zahl von 1 bis 20")
        elif schluessel == "FOLGE":
            if wert.lower() not in DIALOG_FOLGEN:
                eintrag["fehler"].append(
                    f"Zeile {nummer}: FOLGE '{wert}' gibt es nicht. Erlaubt: "
                    + ", ".join(sorted(f for f in DIALOG_FOLGEN if f)))
            else:
                eintrag["folge"] = wert.lower()
        elif schluessel == "TITEL":
            eintrag["titel"] = wert
        elif schluessel in ("WEITER", "WEITER_JA", "WEITER_NEIN"):
            eintrag[schluessel.lower()] = wert.strip().lower()
        elif schluessel == "AN":
            ziel = wert.strip().lower()
            if ziel not in PARTNER_ERLAUBT:
                eintrag["fehler"].append(
                    f"Zeile {nummer}: AN '{wert}' gibt es nicht. Erlaubt: "
                    + ", ".join(sorted(PARTNER_ERLAUBT)))
            else:
                eintrag["an"] = ziel
                eintrag["kanal"] = ziel
        elif schluessel == "STICHWORT":
            for teil in wert.replace(";", ",").split(","):
                teil = teil.strip().lower()
                if teil:
                    eintrag["stichwort"].append(teil)
            if not eintrag["stichwort"]:
                eintrag["fehler"].append(f"Zeile {nummer}: STICHWORT ist leer")
        elif schluessel.split("_")[0] in ("SETZE", "LOESCHE", "ZAEHLE", "SPAETER"):
            if not wert:
                eintrag["fehler"].append(f"Zeile {nummer}: {schluessel} ist leer")
                continue
            art = schluessel.split("_")[0]
            teile_w = wert.split()
            if art == "ZAEHLE":
                if len(teile_w) != 2 or not re.fullmatch(r"[+-]?\d+", teile_w[1]):
                    eintrag["fehler"].append(
                        f"Zeile {nummer}: so geht es: {schluessel}: <name> +1")
                    continue
            if art == "SPAETER":
                if len(teile_w) not in (1, 3):
                    eintrag["fehler"].append(
                        f"Zeile {nummer}: so geht es: {schluessel}: <dialog> nach 3")
                    continue
                if not dialog_datei_finden(teile_w[0]):
                    eintrag["fehler"].append(
                        f"Zeile {nummer}: {schluessel} zeigt auf "
                        f"'{teile_w[0]}', aber {teile_w[0]}.txt gibt es nicht")
                    continue
            eintrag.setdefault(schluessel.lower(), []).append(wert.strip())
        elif schluessel == "PARTNER":
            eintrag["partner"] = wert.strip().lower()
            if eintrag["partner"] not in PARTNER_ERLAUBT:
                eintrag["fehler"].append(
                    f"Zeile {nummer}: PARTNER '{wert}' gibt es nicht. Erlaubt: "
                    + ", ".join(sorted(PARTNER_ERLAUBT)))
        elif schluessel == "KUERZEL":
            kuerzel = wert.strip().lower().lstrip("@")
            if not kuerzel or not kuerzel.isalpha():
                eintrag["fehler"].append(f"Zeile {nummer}: KUERZEL braucht "
                                         f"Buchstaben, etwa 'm' oder 'rip'")
            else:
                eintrag["kuerzel"] = kuerzel
        elif schluessel == "SONST":
            if wert:
                eintrag["sonst"].append(wert)
                letzter = eintrag["sonst"]
        elif schluessel in DIALOG_THEMEN:
            if not wert:
                eintrag["fehler"].append(f"Zeile {nummer}: {schluessel} ist leer")
                continue
            eintrag["themen"].setdefault(schluessel, []).append(wert)
            letzter = eintrag["themen"][schluessel]
        else:
            feld = {"FRAGE": "text", "JA": "ja", "NEIN": "nein",
                    "MELDUNG": "meldung"}[schluessel]
            if not wert:
                eintrag["fehler"].append(f"Zeile {nummer}: {schluessel} ist leer")
                continue
            eintrag[feld].append(wert)
            letzter = eintrag[feld]

    if eintrag["partner"]:
        if not eintrag["themen"]:
            eintrag["fehler"].append(
                "kein Thema vorhanden. Moeglich: " + ", ".join(sorted(DIALOG_THEMEN)))
        if not eintrag["kuerzel"]:
            eintrag["kuerzel"] = eintrag["partner"][0]
    elif not eintrag["text"] and not eintrag["meldung"]:
        eintrag["fehler"].append("weder FRAGE noch MELDUNG vorhanden "
                                 "(und kein PARTNER gesetzt)")
    if eintrag["text"] and not (eintrag["ja"] and eintrag["nein"]):
        eintrag["fehler"].append("zu einer FRAGE gehoeren JA und NEIN")
    for feld in ("weiter", "weiter_ja", "weiter_nein"):
        ziel = eintrag.get(feld)
        if ziel and not dialog_datei_finden(ziel):
            eintrag["fehler"].append(
                f"{feld.upper()} zeigt auf '{ziel}', aber {ziel}.txt gibt es nicht")
    # Platzhalter pruefen, bevor sie im Betrieb krachen
    alle_texte = (eintrag["text"] + eintrag["ja"] + eintrag["nein"]
                  + eintrag["meldung"] + eintrag["sonst"]
                  + [t for vorrat in eintrag["themen"].values() for t in vorrat])
    for feld in ("alle",):
        for text in alle_texte:
            try:
                text.format(**DIALOG_PLATZHALTER_PROBE)
            except (KeyError, IndexError, ValueError) as fehler:
                eintrag["fehler"].append(
                    f"Platzhalter in '{kuerzen(text, 30)}' geht nicht: {fehler}")
    return eintrag


DIALOG_PLATZHALTER_PROBE = {
    "anrede": "Dave", "name": "Dave", "offen": 0, "ueberfaellig": 0,
    "erledigt": 0, "logbuch": "standard", "datum": "01.01.", "zeit": "00:00",
    "schiff": "USCSS DISCOVERY", "offen_text": "0 offene Posten",
    "ueberfaellig_text": "0 ueberfaellige Posten", "erledigt_text": "0 Vorgaenge",
}


def dialoge_laden() -> list:
    """Alle Dialogdateien, auch die fehlerhaften (die melden sich in 'dialog')."""
    return [dialog_lesen(d) for d in dialog_dateien()]


def dialog_werte(board: Board, board_name: str = "standard") -> dict:
    """Die Platzhalter, die in eigenen Dialogen zur Verfuegung stehen."""
    heute = date.today().isoformat()
    offen = board.offen()
    anzahl_offen = len(offen)
    anzahl_spaet = sum(1 for k in offen if k.faelligkeit and k.faelligkeit < heute)
    anzahl_fertig = heute_erledigt(board)
    return {
        "offen": anzahl_offen,
        "ueberfaellig": anzahl_spaet,
        "erledigt": anzahl_fertig,
        # Fertige Wendungen, damit in eigenen Texten nicht '1 Posten sind'
        # steht. Einfach {offen_text} statt {offen} schreiben.
        "offen_text": mehrzahl(anzahl_offen, "offener Posten", "offene Posten"),
        "ueberfaellig_text": mehrzahl(anzahl_spaet, "ueberfaelliger Posten",
                                      "ueberfaellige Posten"),
        "erledigt_text": mehrzahl(anzahl_fertig, "Vorgang", "Vorgaenge"),
        "logbuch": board_name,
        "datum": datum_kurz(heute),
        "zeit": f"{datetime.now():%H:%M}",
        "schiff": SCHIFF_NAME,
    }


def dialog_passt(eintrag: dict, board: Board) -> bool:
    """Alle BEDINGUNG-Zeilen muessen zutreffen."""
    bedingungen = eintrag.get("bedingungen") or [eintrag.get("bedingung", "immer")]
    return all(einzelbedingung(b, board) for b in bedingungen)


def einzelbedingung(b: str, board: Board) -> bool:
    teile = b.strip().lower().split()
    if not teile:
        return True
    verneint = teile[0] == "nicht"
    if verneint:
        teile = teile[1:]
    if not teile:
        return True
    if teile[0] == "merker":
        ergebnis = merker(teile[1]) if len(teile) > 1 else False
        return not ergebnis if verneint else ergebnis
    if teile[0] == "zaehler" and len(teile) == 4:
        wert, zeichen, ziel = zaehler_wert(teile[1]), teile[2], int(teile[3])
        ergebnis = {">=": wert >= ziel, "<=": wert <= ziel, ">": wert > ziel,
                    "<": wert < ziel, "=": wert == ziel,
                    "==": wert == ziel}.get(zeichen, True)
        return not ergebnis if verneint else ergebnis
    ergebnis = _lage_bedingung(" ".join(teile), board)
    return not ergebnis if verneint else ergebnis


def _lage_bedingung(b: str, board: Board) -> bool:
    """Prueft die festen Bedingungen zur Lage an Bord."""
    if b == "immer":
        return True
    heute = date.today()
    offen = board.offen()
    if b == "offen":
        return bool(offen)
    if b == "nichts_offen":
        return not offen
    if b == "ueberfaellig":
        return any(k.faelligkeit and k.faelligkeit < heute.isoformat() for k in offen)
    if b == "kontamination":
        return lage_aktiv()
    if b == "kein_scan":
        return SCHIFF["scans"] == 0
    if b == "erledigt_heute":
        return heute_erledigt(board) > 0
    if b == "bericht_offen":
        return bericht_faellige_woche() is not None
    if b in ("morgen", "mittag", "abend", "nacht"):
        return tageszeit() == b
    if b == "wochenende":
        return heute.weekday() >= 5
    if b == "werktag":
        return heute.weekday() < 5
    return True


def partner_liste() -> list:
    """Alle fehlerfreien Gespraechspartner aus dialoge/."""
    return [d for d in dialoge_laden()
            if d["partner"] and not d["fehler"] and not d.get("notiz")]


def partner_finden(kuerzel: str):
    """@m, @muthur, @w, @r, @ripley ... auf einen Partner abbilden."""
    k = kuerzel.strip().lower().lstrip("@")
    if not k:
        return None
    partner = partner_liste()
    for d in partner:                       # genaues Kuerzel zuerst
        if d["kuerzel"] == k:
            return d
    for d in partner:                       # dann der volle Name
        if d["partner"] == k:
            return d
    for d in partner:                       # zuletzt ein Anfang des Namens
        if d["partner"].startswith(k):
            return d
    return None


def thema_erkennen(text: str) -> str:
    """Ordnet 'hallo', 'danke', 'bye' ... einem Thema zu."""
    t = text.strip().lower().rstrip("?!.,")
    if not t:
        return "HALLO"
    for thema, worte in DIALOG_THEMEN.items():
        if t in worte:
            return thema
    for thema, worte in DIALOG_THEMEN.items():
        if any(t.startswith(w + " ") or t == w for w in worte):
            return thema
    return ""


def ansprechen(roh: str, board: Board, board_name: str) -> bool:
    """Behandelt '@m hallo'. True heisst: war eine Ansprache."""
    if not roh.startswith("@") or len(roh) < 2:
        return False
    teile = roh[1:].split(maxsplit=1)
    partner = partner_finden(teile[0])
    if partner is None:
        liste = partner_liste()
        if not liste:
            raise ValueError("Kein Gespraechspartner geladen. 'dialog' zeigt, "
                             "was im Ordner dialoge/ liegt")
        bekannt = ", ".join(f"@{d['kuerzel']}" for d in liste)
        raise ValueError(f"'@{teile[0]}' kenne ich nicht. Da waere: {bekannt}")
    rest = teile[1] if len(teile) > 1 else ""
    kanal = partner["partner"]

    # Erst die Geschichte: gibt es einen Dialog mit passendem Stichwort?
    gefunden = stichwort_dialog(kanal, rest, board)
    if gefunden is not None:
        story_dialog_starten(gefunden, board, board_name)
        return True

    thema = thema_erkennen(rest)
    vorrat = partner["themen"].get(thema) if thema else None
    if not vorrat:
        vorrat = partner["sonst"] or ["Dazu liegt mir nichts vor."]
    klang("muthur" if kanal == "muthur" else "ansicht")
    funkspruch(fuellen(random.choice(vorrat), board,
                       **dialog_werte(board, board_name)),
               kanal, leise=True)
    schreibe("\n")
    return True


def stichwort_dialog(kanal: str, text: str, board: Board):
    """Sucht einen Geschichtsdialog, dessen Stichwort im Gesagten vorkommt."""
    gesagt = " " + text.strip().lower() + " "
    if not gesagt.strip():
        return None
    treffer = []
    for d in dialoge_laden():
        if d.get("notiz") or d["fehler"] or d["an"] != kanal or not d["stichwort"]:
            continue
        if not any(f" {w} " in gesagt or gesagt.strip().startswith(w)
                   or gesagt.strip() == w for w in d["stichwort"]):
            continue
        if not dialog_passt(d, board):
            continue
        treffer.append(d)
    return random.choice(treffer) if treffer else None


def story_dialog_starten(eintrag: dict, board: Board, board_name: str) -> None:
    """Spielt einen Geschichtsdialog: Frage oder Meldung, dann die Wirkung."""
    werte = dialog_werte(board, board_name)
    kanal = eintrag["kanal"] or eintrag["an"] or "muthur"
    if eintrag["text"]:
        durchsage(fuellen(random.choice(eintrag["text"]), board, **werte), kanal)
        frage_stellen(eintrag)
        OFFENE_FRAGE["werte"] = werte
        schreibe(f"{DUNKEL} Antworte mit 'ja' oder 'nein'.{RESET}\n\n")
    else:
        durchsage(fuellen(random.choice(eintrag["meldung"]), board, **werte), kanal)
        story_wirkung(eintrag)


def story_zuruecksetzen(name: str = "") -> None:
    """Loescht den Stand einer Geschichte - einen Merker oder alles.

    Die Dialogdateien selbst bleiben unberuehrt. Zurueckgesetzt wird nur,
    was sich das Terminal gemerkt hat: Merker, Verhaeltnisse und noch
    unterwegs befindliche Auftraege.
    """
    name = name.strip().lower()
    if name:
        getroffen = []
        if name in STORY["merker"]:
            del STORY["merker"][name]
            getroffen.append("Merker")
        if name in STORY["zaehler"]:
            del STORY["zaehler"][name]
            getroffen.append("Verhaeltnis")
        vorher = len(STORY["wartend"])
        STORY["wartend"] = [e for e in STORY["wartend"]
                            if str(e.get("dialog", "")).lower() != name]
        if len(STORY["wartend"]) < vorher:
            getroffen.append("Auftrag")
        if not getroffen:
            raise ValueError(f"'{name.upper()}' ist nicht vermerkt. "
                             f"'story' zeigt, was es gibt")
        story_speichern()
        klang("loeschen")
        entschluesseln(f"{name.upper()} ZURUECKGESETZT")
        absatz(f"Geloescht: {', '.join(getroffen)}. Die Dialogdateien "
               f"bleiben, wie sie sind.", DUNKEL)
        schreibe("\n")
        return

    anzahl = (len(STORY["merker"]) + len(STORY["zaehler"])
              + len(STORY["wartend"]))
    if not anzahl:
        schreibe(f"{DUNKEL} Es ist nichts vermerkt, das man "
                 f"zuruecksetzen koennte.{RESET}\n\n")
        return
    schreibe(f"{DUNKEL} {mehrzahl(len(STORY['merker']), 'Merker', 'Merker')}, "
             f"{mehrzahl(len(STORY['zaehler']), 'Verhaeltnis', 'Verhaeltnisse')} "
             f"und {mehrzahl(len(STORY['wartend']), 'Auftrag', 'Auftraege')} "
             f"werden geloescht.{RESET}\n")
    if not frage_ja_nein("  GANZE GESCHICHTE ZURUECKSETZEN? [J/N] "):
        schreibe(f"{DUNKEL} Nichts geaendert.{RESET}\n\n")
        return
    STORY["merker"], STORY["zaehler"], STORY["wartend"] = {}, {}, []
    story_speichern()
    klang("zurueck")
    entschluesseln("GESCHICHTE ZURUECKGESETZT")
    absatz("Alle Merker, Verhaeltnisse und Auftraege geloescht. Die Dialoge "
           "in dialoge/ bleiben unveraendert - du kannst von vorn anfangen.",
           DUNKEL)
    schreibe("\n")


def story_befehl(board: Board, arg: str = "") -> None:
    """Zeigt, was die Geschichte bisher festgehalten hat."""
    wunsch = (arg or "").strip().lower()
    if wunsch:
        erstes, _, rest = wunsch.partition(" ")
        if erstes in ("zurueck", "zurück", "reset", "vergiss", "neu"):
            story_zuruecksetzen(rest)
            return
        raise ValueError("So geht es: story, story zurueck "
                         "oder story zurueck <name>")
    klang("ansicht")
    merker_liste = sorted(k for k, v in STORY["merker"].items() if v)
    spaltenkopf("Geschichte", len(merker_liste), "WAS BISHER GESCHAH")
    if merker_liste:
        for name in merker_liste:
            schreibe(f"{DUNKEL}{LAMPE} {HELL}{kuerzen(name, BREITE - 4)}{RESET}\n")
    else:
        schreibe(f"{DUNKEL}{LAMPE}  Noch nichts vermerkt.{RESET}\n")

    if STORY["zaehler"]:
        unterabschnitt("Verhaeltnisse", f"{len(STORY['zaehler'])} GEMESSEN")
        hoechst = max(abs(v) for v in STORY["zaehler"].values()) or 1
        for name, wert in sorted(STORY["zaehler"].items()):
            balken = mini_balken(abs(wert), hoechst, 14)
            farbe = HELL if wert >= 0 else ROT
            schreibe(f"{DUNKEL}{LAMPE} {HELL}{kuerzen(name, 24):<25}{RESET}"
                     f"{farbe}{balken}{RESET} {HELL}{wert:>+4}{RESET}\n")

    if STORY["wartend"]:
        unterabschnitt("Unterwegs", mehrzahl(len(STORY["wartend"]),
                                             "AUFTRAG", "AUFTRAEGE"))
        for e in sorted(STORY["wartend"], key=lambda e: e["in"]):
            schreibe(f"{DUNKEL}{LAMPE} {AKZENT}{kuerzen(e['dialog'], 28):<29}"
                     f"{RESET}{DUNKEL}Rueckmeldung in {e['in']} Eingaben{RESET}\n")
    schreibe(f"\n{DUNKEL} Geschichten liegen in {DIALOG_ORDNER.name}/ und werden "
             f"ueber '@name <stichwort>' erkundet.{RESET}\n")
    if merker_liste or STORY["zaehler"] or STORY["wartend"]:
        absatz("'story zurueck' setzt alles zurueck, "
               "'story zurueck <name>' nur einen Eintrag.", DUNKEL)
    schreibe("\n")


def muster_liste() -> dict:
    """Alle Blanko-Muster: Kurzname -> Datei."""
    gefunden = {}
    try:
        for pfad in sorted(DIALOG_ORDNER.rglob("_muster_*.txt")):
            gefunden[pfad.stem[len("_muster_"):].lower()] = pfad
    except OSError:
        pass
    return gefunden


def dialog_neu(art: str, ziel_name: str) -> Path:
    """Kopiert ein Muster auf einen neuen Namen, damit man nur noch fuellt."""
    muster = muster_liste()
    art = art.strip().lower()
    if art not in muster:
        raise ValueError("Muster gibt es fuer: " + ", ".join(sorted(muster))
                         if muster else "Keine Muster in dialoge/ gefunden")
    ziel_name = ziel_name.strip().lower().replace("\\", "/").strip("/")
    if not re.fullmatch(r"[a-z0-9_]+(/[a-z0-9_]+)*", ziel_name):
        raise ValueError("Name nur mit Buchstaben, Zahlen, _ und / fuer Ordner")
    teile = ziel_name.split("/")
    if any(t.startswith("_") for t in teile):
        raise ValueError("Ein Name mit _ am Anfang waere nur eine Notiz")
    kurz = teile[-1]
    # Verweise nennen nur den Namen, darum muss er im ganzen Baum eindeutig sein
    schon = dialog_datei_finden(kurz)
    if schon:
        raise ValueError(f"{kurz}.txt gibt es schon in "
                         f"{dialog_unterordner(schon) or DIALOG_ORDNER.name}/")
    ziel = DIALOG_ORDNER.joinpath(*teile).with_suffix(".txt")
    try:
        ziel.parent.mkdir(parents=True, exist_ok=True)
    except OSError as fehler:
        raise ValueError(f"Ordner liess sich nicht anlegen: {fehler}")
    inhalt = muster[art].read_text(encoding="utf-8").splitlines()
    # Den Musterkopf abschneiden: er endet mit der zweiten Rahmenzeile
    rahmen = [i for i, z in enumerate(inhalt[:12]) if z.startswith("# ====")]
    if len(rahmen) >= 2:
        inhalt = inhalt[rahmen[1] + 1:]
    kopf = [f"# {kurz} - aus dem Muster '{art}'",
            "# Die <Klammern> ausfuellen, dann mit 'dialog' pruefen."]
    ziel.write_text("\n".join(kopf + inhalt).lstrip("\n") + "\n",
                    encoding="utf-8")
    return ziel


def dialog_befehl(board: Board, board_name: str, arg: str) -> None:
    """dialog zeigt und prueft alle Dateien, dialog <name> spielt eine ab."""
    dialoge = dialoge_laden()
    name = arg.strip().lower()

    if name.startswith("neu"):
        teile = arg.split()
        if len(teile) != 3:
            raise ValueError("So geht es: dialog neu <muster> <name>")
        ziel = dialog_neu(teile[1], teile[2])
        klang("bestaetigt", (880, 60))
        entschluesseln(f"{ziel.stem.upper()} ANGELEGT")
        ort = f"{dialog_unterordner(ziel)}/{ziel.name}".lstrip("/")
        absatz(f"Oeffne {DIALOG_ORDNER.name}/{ort} in einem Editor und "
               f"fuelle die <Klammern> aus. Danach prueft 'dialog', "
               f"ob alles stimmt.", DUNKEL)
        schreibe("\n")
        return

    if name:
        passend = [d for d in dialoge if d["name"].lower() == name]
        if not passend:
            raise ValueError(f"Kein Dialog '{name.upper()}' in "
                             f"{DIALOG_ORDNER.name}/")
        eintrag = passend[0]
        if eintrag.get("notiz"):
            raise ValueError(f"'{eintrag['datei']}' ist eine Notiz, "
                             f"kein Dialog")
        if eintrag["fehler"]:
            raise ValueError(f"'{eintrag['datei']}' hat Fehler. 'dialog' zeigt welche")
        werte = dialog_werte(board, board_name)
        if eintrag["text"]:
            durchsage(fuellen(random.choice(eintrag["text"]), board, **werte),
                      eintrag["kanal"])
            frage_stellen(eintrag)
            OFFENE_FRAGE["werte"] = werte
            schreibe(f"{DUNKEL} Antworte mit 'ja' oder 'nein'.{RESET}\n\n")
        else:
            durchsage(fuellen(random.choice(eintrag["meldung"]), board, **werte),
                      eintrag["kanal"])
        return

    klang("ansicht")
    fehlerhaft = sum(1 for d in dialoge if d["fehler"])
    spaltenkopf("Dialoge", sum(1 for d in dialoge if not d.get("notiz")),
                "ALLE IN ORDNUNG" if not fehlerhaft
                else f"{fehlerhaft} MIT FEHLERN")
    if not dialoge:
        schreibe(f"{DUNKEL}{LAMPE}  Noch keine Datei in {DIALOG_ORDNER.name}/. "
                 f"Die Beispiele dort zeigen das Format.{RESET}\n\n")
        return
    mehrfach = {}
    for d in dialoge:
        if not d.get("notiz"):
            mehrfach.setdefault(d["name"].lower(), []).append(d["datei"])
    mehrfach = {n: o for n, o in mehrfach.items() if len(o) > 1}

    letzter_ordner = None
    for d in dialoge:
        ordner = d["datei"].rsplit("/", 1)[0] if "/" in d["datei"] else ""
        if ordner != letzter_ordner:
            letzter_ordner = ordner
            if ordner:
                anzahl = sum(1 for e in dialoge
                             if e["datei"].startswith(ordner + "/"))
                unterabschnitt(ordner, mehrzahl(anzahl, "DATEI", "DATEIEN"))
        if d.get("notiz"):
            zeilen_zahl = len(art_zeilen(DIALOG_ORDNER / d["datei"]))
            zeile = (f"{d['name']:<19}Notiz   wird nicht verwendet, "
                     f"{zeilen_zahl} Zeilen")
            schreibe(f"{DUNKEL}{LAMPE} {DUNKEL}{kuerzen(zeile, BREITE - 3)}{RESET}\n")
            continue
        if d["partner"]:
            themen = ", ".join(t.lower() for t in sorted(d["themen"]))
            zeile = (f"{d['name']:<16}@{d['kuerzel']:<6}"
                     f"Partner  {len(d['themen'])} Themen: {themen}")
        elif d["an"]:
            woher = (f"Stichwort: {', '.join(d['stichwort'])}" if d["stichwort"]
                     else "wird von einer anderen Szene ausgeloest")
            zeile = f"{d['name']:<16}an {d['an']:<9}{woher}"
        else:
            art = "Frage" if d["text"] else "Meldung"
            anzahl = len(d["text"]) or len(d["meldung"])
            zeile = (f"{d['name']:<16}{d['kanal']:<8}"
                     f"{kuerzen(d['bedingung'], 15):<16}"
                     f"{art} x{anzahl}  Gewicht {d['gewicht']}")
        farbe = ROT if d["fehler"] else HELL
        schreibe(f"{DUNKEL}{LAMPE} {farbe}{kuerzen(zeile, BREITE - 3)}{RESET}\n")
        for text in d["fehler"]:
            schreibe(f"{DUNKEL}{LAMPE}   {ROT}{kuerzen(text, BREITE - 5)}{RESET}\n")
    for name, orte in sorted(mehrfach.items()):
        schreibe(f"{DUNKEL}{LAMPE} {ROT}"
                 f"{kuerzen(f'{name} gibt es mehrfach: ' + ', '.join(orte), BREITE - 3)}"
                 f"{RESET}\n")
    muster = ", ".join(sorted(muster_liste()))
    if mehrfach:
        absatz("Verweise nennen nur den Namen. Doppelte Namen sind darum "
               "nicht eindeutig - benenne einen davon um.", ROT)
    schreibe(f"\n{DUNKEL} 'dialog <name>' spielt einen ab, egal in welchem "
             f"Unterordner er liegt.{RESET}\n")
    if muster:
        absatz(f"'dialog neu <muster> <name>' legt eine neue Datei aus einem "
               f"Blanko-Muster an. Muster: {muster}", DUNKEL)
    schreibe("\n")


WEITER_CHANCE = 0.7           # wie oft eine Anschlussfrage wirklich kommt


def dialog_nachladen(name: str):
    """Holt einen Dialog aus dialoge/ fuer eine Anschlussfrage."""
    for d in dialoge_laden():
        if (d["name"].lower() == str(name).lower() and not d.get("notiz")
                and not d["fehler"] and d["text"]):
            return d
    return None


FRAGE_ANTEIL = 0.45        # so viele Durchsagen wollen eine Antwort
FRAGE_GUELTIG = 300.0      # Sekunden, danach ist die Frage verfallen
FRAGE_EINGABEN = 3         # oder nach so vielen anderen Eingaben

OFFENE_FRAGE = {"eintrag": None, "zeit": 0.0, "eingaben": 0}

JA_WORTE = {"ja", "j", "jo", "jau", "jep", "yes", "y", "ok", "okay", "klar",
            "bestaetigt", "bestätigt", "roger", "affirmativ", "positiv",
            "einverstanden", "zustimmung", "mache ich", "gerne"}
# 'n' fehlt hier mit Absicht: das ist der Befehl fuer die Notizen.
NEIN_WORTE = {"nein", "ne", "nee", "noe", "nö", "no", "nope", "negativ",
              "ablehnen", "abgelehnt", "verweigert", "nicht", "lieber nicht",
              "spaeter", "später"}


def antwort_erkennen(roh: str):
    """Gibt 'ja', 'nein' oder None zurueck.

    Ein bekannter Befehl bleibt immer ein Befehl. Sonst verschluckt eine
    offene Rueckfrage die taegliche Arbeit, und das waere die schlechtere
    Haelfte des Geschaefts.
    """
    t = roh.strip().lower().rstrip(".!")
    if t.split(maxsplit=1)[0] in BEFEHLE if t else False:
        return None
    if t in JA_WORTE:
        return "ja"
    if t in NEIN_WORTE:
        return "nein"
    return None


def frage_offen() -> bool:
    """Steht gerade eine Frage im Raum, die noch gilt?"""
    if not OFFENE_FRAGE["eintrag"]:
        return False
    if time.monotonic() - OFFENE_FRAGE["zeit"] > FRAGE_GUELTIG:
        OFFENE_FRAGE["eintrag"] = None
        return False
    if OFFENE_FRAGE["eingaben"] > FRAGE_EINGABEN:
        OFFENE_FRAGE["eintrag"] = None
        return False
    return True


def frage_stellen(eintrag: dict) -> None:
    OFFENE_FRAGE.update({"eintrag": eintrag, "zeit": time.monotonic(),
                         "eingaben": 0})


def frage_beantworten(antwort: str, board: Board) -> str:
    """Gibt die Erwiderung aus und meldet, was daraus folgen soll."""
    eintrag = OFFENE_FRAGE["eintrag"]
    OFFENE_FRAGE["eintrag"] = None
    if not eintrag:
        # Zustimmung oder Ablehnung ohne vorliegende Anfrage
        if antwort == "ja":
            funkspruch("Ihre Zustimmung wurde erfasst. Eine zugehoerige Anfrage "
                       "liegt nicht vor.", "wy")
        else:
            funkspruch("Ihre Ablehnung wurde erfasst. Eine zugehoerige Anfrage "
                       "liegt nicht vor.", "wy")
        schreibe("\n")
        return ""
    klang("bestaetigt" if antwort == "ja" else "klick")
    story_wirkung(eintrag, antwort)
    vorrat = eintrag.get(antwort) or ["Vermerkt."]
    funkspruch(fuellen(random.choice(vorrat), board, **OFFENE_FRAGE.get("werte", {})),
               eintrag["kanal"], leise=(eintrag["kanal"] == "muthur"))
    schreibe("\n")
    # Eine Anschlussfrage haelt das Gespraech am Laufen
    weiter = eintrag.get(f"weiter_{antwort}") or eintrag.get("weiter")
    if weiter and random.random() < WEITER_CHANCE:
        naechste = weiter if isinstance(weiter, dict) else dialog_nachladen(weiter)
        if naechste:
            durchsage(fuellen(random.choice(naechste["text"]), board),
                      naechste["kanal"])
            frage_stellen(naechste)
            OFFENE_FRAGE["werte"] = {}
            schreibe(f"{DUNKEL} Antworte mit 'ja' oder 'nein'.{RESET}\n\n")
            return ""
    return eintrag.get("folge", "") if antwort == "ja" else ""


def durchsage_waehlen(board: Board, kalender: "Kalender" = None) -> dict:
    """Sucht die Durchsage aus, die gerade am ehesten passt.

    Gewichtet statt rein zufaellig: eine faellige Frist ist wichtiger als ein
    Rundschreiben, und wer heute schon gescannt hat, wird nicht dazu ermahnt.
    Zurueck kommt die Art, der fertige Text und die Werte fuer eine Rueckfrage.
    """
    heute = date.today()
    kandidaten = []    # (Gewicht, Art, Text, Werte fuer die Rueckfrage)

    # Routinediagnose
    if SCHIFF["scans"] == 0:
        letzter = SYSTEM.get("letzter_scan", "")
        tage = None
        if letzter:
            try:
                tage = (heute - date.fromisoformat(letzter)).days
            except ValueError:
                tage = None
        if tage is None:
            kandidaten.append((4, "scan", random.choice(DURCHSAGE_SCAN_NEU), {}))
        elif tage >= 2:
            kandidaten.append((min(9, 2 + tage), "scan",
                               fuellen(random.choice(DURCHSAGE_SCAN), board, tage=tage),
                               {"tage": tage}))
        elif tage >= 1:
            kandidaten.append((3, "scan", random.choice(DURCHSAGE_SCAN_NEU), {}))

    # Fristen der naechsten drei Tage
    grenze = (heute + timedelta(days=3)).isoformat()
    bald = [k for k in board.offen()
            if k.faelligkeit and heute.isoformat() <= k.faelligkeit <= grenze]
    if bald:
        k = min(bald, key=lambda k: k.faelligkeit)
        try:
            tage = (date.fromisoformat(k.faelligkeit) - heute).days
        except ValueError:
            tage = 0
        wann = "heute" if tage == 0 else "morgen" if tage == 1 else f"in {tage} Tagen"
        werte = {"id": k.id, "titel": kuerzen(k.titel, 28), "wann": wann}
        kandidaten.append((7, "frist",
                           fuellen(random.choice(DURCHSAGE_FRIST), board, **werte),
                           werte))

    # Termin von morgen
    if kalender is not None:
        morgen = (heute + timedelta(days=1)).isoformat()
        try:
            termine = kalender.am_tag(morgen)
        except (AttributeError, ValueError):
            termine = []
        if termine:
            t = termine[0]
            werte = {"titel": kuerzen(t.titel, 26), "zeit": t.zeitangabe()}
            kandidaten.append((4, "termin",
                               fuellen(random.choice(DURCHSAGE_TERMIN), board, **werte),
                               werte))

    # MU/TH/UR bietet einen Lagebericht an, wenn heute etwas fertig wurde
    if heute_erledigt(board) and not (SITREP_ORDNER / f"sitrep_{heute}.md").exists():
        kandidaten.append((4, "sitrep", "", {}))

    # Und ganz selten fragt es etwas, das nicht im Handbuch steht
    if ai_aktiv() and SYSTEM.get("freigabe", 0) >= 1:
        kandidaten.append((1, "vertrauen", "", {}))

    # Eigene Dialoge aus dialoge/, sofern die Bedingung passt
    for eigen in dialoge_laden():
        if (eigen.get("notiz") or eigen["partner"] or eigen["an"]
                or eigen["fehler"] or not dialog_passt(eigen, board)):
            continue
        kandidaten.append((eigen["gewicht"], "eigen", "", {"dialog": eigen}))

    # Der Konzern erwartet den Wochenbericht
    anfrage = bericht_anfrage(heute)
    if anfrage:
        kandidaten.append(anfrage)

    # Sonst das uebliche Rundschreiben
    kandidaten.append((3, "memo", random.choice(WY_MEMOS), {}))

    gesamt = sum(g for g, _, _, _ in kandidaten)
    wurf = random.uniform(0.0, gesamt)
    gewaehlt = kandidaten[-1]
    for eintrag in kandidaten:
        wurf -= eintrag[0]
        if wurf <= 0:
            gewaehlt = eintrag
            break
    _, art, text, werte = gewaehlt
    return {"art": art, "text": text, "werte": werte}


def durchsage(text: str, kanal: str = "wy") -> None:
    """Eine hereinkommende Uebertragung, mit Kopf und Fernschreiberklang."""
    if kanal == "wy":
        unterabschnitt("Eingehende Uebertragung",
                       f"W-Y CORP   {datetime.now():%H:%M}")
        klang("bericht", (770, 80))
    else:
        unterabschnitt("Meldung der Bordanlage",
                       f"MU/TH/UR   {datetime.now():%H:%M}")
    funkspruch(text, kanal, leise=(kanal == "muthur"))
    schreibe("\n")


def durchsage_pruefen(board: Board, kalender: "Kalender" = None) -> None:
    """Wuerfelt vor jeder Eingabe, ob sich die Zentrale meldet."""
    if not wy_aktiv():
        return
    SITZUNG["befehle"] = SITZUNG.get("befehle", 0) + 1
    if SITZUNG["befehle"] < DURCHSAGE_BEFEHLE:
        return
    jetzt = time.monotonic()
    if jetzt - SITZUNG.get("letzte_durchsage", 0.0) < DURCHSAGE_PAUSE:
        return
    if random.random() >= DURCHSAGE_CHANCE:
        return
    SITZUNG["letzte_durchsage"] = jetzt
    SITZUNG["befehle"] = 0
    gewaehlt = durchsage_waehlen(board, kalender)
    art, text, werte = gewaehlt["art"], gewaehlt["text"], gewaehlt["werte"]
    if art == "eigen":
        eigen = werte.pop("dialog")
        werte = dialog_werte(board)
        if eigen["text"]:
            durchsage(fuellen(random.choice(eigen["text"]), board, **werte),
                      eigen["kanal"])
            frage_stellen(eigen)
            OFFENE_FRAGE["werte"] = werte
            schreibe(f"{DUNKEL} Antworte mit 'ja' oder 'nein'.{RESET}\n\n")
        else:
            durchsage(fuellen(random.choice(eigen["meldung"]), board, **werte),
                      eigen["kanal"])
        return
    eintrag = FRAGEN.get(art)
    # Manche Arten gibt es nur als Rueckfrage, bei den anderen wird gewuerfelt
    als_frage = eintrag is not None and (not text or random.random() < FRAGE_ANTEIL)
    if als_frage:
        durchsage(fuellen(random.choice(eintrag["text"]), board, **werte),
                  eintrag["kanal"])
        frage_stellen(eintrag)
        OFFENE_FRAGE["werte"] = werte
        schreibe(f"{DUNKEL} Antworte mit 'ja' oder 'nein'.{RESET}\n\n")
    else:
        durchsage(text, "wy")


def wy_memo() -> None:
    """Ein zufälliges Rundschreiben aus dem Konzern-Intranet."""
    nummer = random.randint(1000, 9999)
    kopfzeile("Internes Rundschreiben", f"NR. {nummer}",
              augenbraue="Weyland-Yutani Corp")
    schreibe("\n")
    funkspruch(random.choice(WY_MEMOS), "wy")
    schreibe(f"\n{DUNKEL} Verteiler: gesamte Besatzung. "
             f"Rückfragen: nicht vorgesehen.{RESET}\n\n")


# ---------------------------------------------------------------------------
# CRT-Effekte. Nur die, die ohne Ereignisablauf gehen.
# ---------------------------------------------------------------------------

def crt_aktiv() -> bool:
    return bool(SYSTEM.get("crt", True))


# ---------------------------------------------------------------------------
# Bildschirmschoner: das MU/TH/UR-Signet als Leiterbahn-Achteck.
# Hängt sich in die Eingabeschleife ein, die ohnehin alle 30 ms nach Tasten fragt.
# ---------------------------------------------------------------------------

SCHONER_SEKUNDEN = 900        # 15 Minuten Ruhe, nach der letzten Leerlaufstufe
SCHONER_BREITE = 64
SCHONER_HOEHE = 18
SCHONER_SAMEN = 7             # feste Saat, damit das Signet immer gleich aussieht


def _im_achteck(x: int, y: int) -> bool:
    cx, cy = (SCHONER_BREITE - 1) / 2, (SCHONER_HOEHE - 1) / 2
    dx, dy = abs(x - cx) / cx, abs(y - cy) / cy
    return dx <= 1.0 and dy <= 1.0 and (dx + dy) <= 1.45


def signet_bauen(samen: int = SCHONER_SAMEN) -> list[list[str]]:
    """Baut ein Viertel Leiterbahnen und spiegelt es vierfach ins Achteck."""
    r = random.Random(samen)
    breit, hoch = SCHONER_BREITE, SCHONER_HOEHE
    hb, hh = breit // 2, hoch // 2
    punkte = "███▓▒" if not ASCII_RAHMEN else "#####"
    viertel = [[" "] * hb for _ in range(hh)]
    for _ in range(26):
        y = r.randrange(hh)
        x1 = r.randrange(0, max(1, hb - 4))
        for x in range(x1, min(hb, x1 + r.randrange(3, 15))):
            viertel[y][x] = WAAG
    for _ in range(20):
        x = r.randrange(hb)
        y1 = r.randrange(0, max(1, hh - 3))
        for y in range(y1, min(hh, y1 + r.randrange(2, 7))):
            viertel[y][x] = SENK if viertel[y][x] == " " else KREUZ
    for _ in range(12):
        y, x = r.randrange(hh), r.randrange(hb)
        if viertel[y][x] != " ":
            viertel[y][x] = r.choice(punkte)

    leinwand = [[" "] * breit for _ in range(hoch)]
    for y in range(hh):
        for x in range(hb):
            if viertel[y][x] == " ":
                continue
            for yy, xx in ((y, x), (y, breit - 1 - x),
                           (hoch - 1 - y, x), (hoch - 1 - y, breit - 1 - x)):
                leinwand[yy][xx] = viertel[y][x]

    # Die vier diagonalen Arme
    cx, cy = (breit - 1) / 2, (hoch - 1) / 2
    for i in range(hoch):
        for vorzeichen, zeichen in ((1, "\\"), (-1, "/")):
            x = int(cx + vorzeichen * (i - cy) * (breit / hoch) * 0.5)
            for versatz in (0, 1):
                if 0 <= x + versatz < breit:
                    leinwand[i][x + versatz] = zeichen

    # Maske schneiden und die Aussenkontur ziehen
    rand = "█" if not ASCII_RAHMEN else "#"
    for y in range(hoch):
        for x in range(breit):
            if not _im_achteck(x, y):
                leinwand[y][x] = " "
                continue
            if any(not (0 <= x + dx < breit) or not (0 <= y + dy < hoch)
                   or not _im_achteck(x + dx, y + dy)
                   for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                leinwand[y][x] = rand
    return leinwand


SIGNET = None   # wird beim ersten Aufruf gebaut


def signet() -> list[list[str]]:
    global SIGNET
    if SIGNET is None:
        SIGNET = signet_bauen()
    return SIGNET


def schoner_bild(leuchten: set) -> str:
    """Eine Bildfassung. leuchten sind die Felder, die gerade hell sind."""
    einzug = " " * max(0, (BREITE - SCHONER_BREITE) // 2)
    titel = " ".join("MU/TH/UR 6000")
    teile = [f"\033[H\033[J{BG}",
             f"{einzug}{AKZENT}{titel.center(SCHONER_BREITE)}{RESET}\n\n"]
    for y, zeile in enumerate(signet()):
        teile.append(einzug)
        for x, zeichen in enumerate(zeile):
            if zeichen == " ":
                teile.append(" ")
            elif (y, x) in leuchten:
                teile.append(f"\033[1m\033[97m{zeichen}{RESET}")
            else:
                teile.append(f"{HELL}{zeichen}{RESET}")
        teile.append("\n")
    fuss = f"SYSTEM IM LEERLAUF   {uhrzeit_zeile()}   EINGABE ZUM FORTFAHREN"
    teile.append(f"\n{einzug}{DUNKEL}{fuss.center(SCHONER_BREITE)}{RESET}")
    return "".join(teile)


def schoner_laufen(prompt: str, puffer: str) -> None:
    """Zeigt das Signet, bis eine Taste kommt. Die Taste wird verschluckt."""
    felder = [(y, x) for y, zeile in enumerate(signet())
              for x, z in enumerate(zeile) if z != " "]
    schreibe("\033[?25l")   # Cursor aus
    try:
        while True:
            leuchten = set(random.sample(felder, min(14, len(felder))))
            schreibe(schoner_bild(leuchten))
            for _ in range(7):      # ca. 0.2 s, dabei auf Tasten horchen
                if taste_bereit():
                    taste_lesen()   # Weckdruck nicht in den Puffer schreiben
                    return
                time.sleep(0.03)
    finally:
        schreibe("\033[?25h")   # Cursor an
        schreibe(f"{BG}\033[H\033[J")
    prompt_zeichnen(prompt, puffer)


def schoner_aktiv() -> bool:
    return bool(SYSTEM.get("schoner", True))


def schoner_schalten(arg: str) -> str:
    t = arg.strip().lower()
    if t in ("an", "ein", "on"):
        SYSTEM["schoner"] = True
    elif t in ("aus", "off"):
        SYSTEM["schoner"] = False
    else:
        raise ValueError("So geht es: schoner an oder schoner aus")
    return "BILDSCHIRMSCHONER " + ("AN" if SYSTEM["schoner"] else "AUS")


def flimmern(runden: int = 3) -> None:
    """Dimmt den ganzen Bildschirm kurz und hellt ihn wieder auf."""
    if not crt_aktiv():
        return
    for _ in range(runden):
        schreibe("\033[2m")
        time.sleep(0.05)
        schreibe("\033[22m")
        time.sleep(0.07)


def scanline_durchlauf(hoehe: int = 18) -> None:
    """Eine helle Zeile wandert einmal von oben nach unten."""
    if not crt_aktiv():
        return
    for i in range(hoehe):
        schreibe(f"\033[{i + 1};1H\033[7m{' ' * BREITE}{RESET}")
        time.sleep(0.012)
        schreibe(f"\033[{i + 1};1H{' ' * BREITE}")
    schreibe("\033[H")


def entmagnetisieren() -> None:
    """Kurzes Zucken wie beim Einschalten einer Röhre."""
    if not crt_aktiv():
        return
    klang("degauss", (120, 90))
    for versatz in (3, 1, 2, 0, 1, 0):
        schreibe("\033[H\033[J")
        for i in range(6):
            zeichen = "".join(random.choice("░▒▓█") if not ASCII_RAHMEN
                              else random.choice(".:#@") for _ in range(BREITE - versatz))
            schreibe(f"{' ' * versatz}{DUNKEL}{zeichen}{RESET}\n")
        time.sleep(0.05)
    schreibe("\033[H\033[J")


def crt_schalten(arg: str) -> str:
    t = arg.strip().lower()
    if t in ("an", "ein", "on"):
        SYSTEM["crt"] = True
    elif t in ("aus", "off"):
        SYSTEM["crt"] = False
    else:
        raise ValueError("So geht es: crt an oder crt aus")
    return "CRT-EFFEKTE " + ("AN" if SYSTEM["crt"] else "AUS")


def ai_schalten(arg: str) -> str:
    t = arg.strip().lower()
    if t in ("an", "ein", "on"):
        SYSTEM["ai"] = True
    elif t in ("aus", "off"):
        SYSTEM["ai"] = False
    else:
        raise ValueError("So geht es: ai an oder ai aus")
    return "MU/TH/UR EIGENINITIATIVE " + ("AN" if SYSTEM["ai"] else "AUS")


# Was bei welcher Gelegenheit zu hören ist. Reihenfolge wie in 'klang test'.
KLANG_ANLAESSE = [
    ("boot", "Hochfahren, Schütz und Laufwerk"),
    ("aus", "Verbindung wird getrennt"),
    ("degauss", "Bildröhre schaltet ein"),
    ("taste", "Tastenanschlag"),
    ("ansicht", "Ansicht wird gezeichnet"),
    ("bestaetigt", "Eintrag, Notiz, Termin angelegt"),
    ("loeschen", "Eintrag gelöscht"),
    ("klick", "Anpinnen, Pausieren"),
    ("umschalten", "crt, ai, schoner, Thema"),
    ("verschieben", "Eintrag wechselt die Spalte"),
    ("erledigt", "Eintrag landet in Erledigt"),
    ("zurueck", "u, Band läuft zurück"),
    ("archiv", "Logbuch, Export, Rundschreiben"),
    ("fehler", "Fehler oder falsche Maßnahme"),
    ("unbekannt", "Unbekannter Befehl"),
    ("scan", "Rumpf wird abgetastet"),
    ("ping", "Einzelner Ablauf beendet"),
    ("ok", "Alles im grünen Bereich"),
    ("bericht", "Sitrep wird geschrieben"),
    ("alarm", "Kontamination festgestellt"),
    ("alarm_puls", "Blinken in der Schiffskarte"),
    ("warnung", "Mahnung, Verspätung, Teilerfolg"),
    ("purge", "Lüftung bläst ein Deck frei"),
    ("dekon", "Dekontamination eines Decks"),
    ("erfolg", "Lage bereinigt, alles erledigt"),
    ("freigabe", "Neue Sicherheitsfreigabe"),
    ("muthur", "MU/TH/UR meldet sich selbst"),
    ("geheim", "Etwas Unverzeichnetes gefunden"),
    ("rogue", "MU/TH/UR verweigert"),
]


def klang_befehl(arg: str) -> None:
    """klang | klang an | klang aus | klang tasten an|aus | klang test | klang neu"""
    t = arg.strip().lower()
    if t in ("an", "ein", "on"):
        SYSTEM["klang"] = True
        entschluesseln("TONAUSGABE AN")
        klang("bestaetigt", (880, 60))
        return
    if t in ("aus", "off"):
        klang("klick", (660, 60))
        SYSTEM["klang"] = False
        entschluesseln("TONAUSGABE AUS")
        return
    if t.startswith("tasten"):
        rest = t[6:].strip()
        if rest in ("an", "ein", "on"):
            SYSTEM["tasten"] = True
        elif rest in ("aus", "off"):
            SYSTEM["tasten"] = False
        else:
            SYSTEM["tasten"] = not SYSTEM.get("tasten", True)
        entschluesseln("TASTENKLICK " + ("AN" if SYSTEM["tasten"] else "AUS"))
        if SYSTEM["tasten"]:
            klang("taste")
        return
    if t in ("neu", "bauen", "reset"):
        try:
            for datei_pfad in KLANG_ORDNER.glob("*.wav"):
                datei_pfad.unlink()
        except OSError:
            pass
        _KLANG_PFADE.clear()
        klangbibliothek_pruefen()
        _KLANG_PFADE.clear()
        entschluesseln("KLANGBIBLIOTHEK NEU ERZEUGT")
        return
    # Ab hier wird eine Liste gezeichnet, einmal mit und einmal ohne Abspielen
    probe = t in ("test", "probe")
    if probe and not klang_aktiv():
        raise ValueError("Tonausgabe ist aus. Erst 'klang an'")
    vorhanden = sum(1 for name, _ in KLANG_ANLAESSE if klang_pfad(name))
    spaltenkopf("Klang", vorhanden, "KLANGPROBE" if probe
                else ("TONAUSGABE AN" if klang_aktiv() else "TONAUSGABE AUS"))
    for name, zweck in KLANG_ANLAESSE:
        da = klang_pfad(name) is not None
        zeile = kuerzen(f"{name:<12}{zweck}", BREITE - 4)
        schreibe(f"{DUNKEL}{LAMPE} {HELL if da else ROT}{zeile}{RESET}\n")
        if probe and da:
            klang(name, warten=True)   # synchron, damit nichts abgeschnitten wird
            time.sleep(0.25)
    spaltenfuss()
    if probe:
        schreibe("\n")
        return
    schreibe(f"{DUNKEL} Tastenklick: "
             f"{'an' if SYSTEM.get('tasten', True) else 'aus'}. "
             f"Dateien in {KLANG_ORDNER.name}/{RESET}\n")
    if os.name != "nt" and _ABSPIELER == []:
        schreibe(f"{ROT} Kein Abspielprogramm gefunden "
                 f"(aplay, paplay, afplay){RESET}\n")
    schreibe(f"{DUNKEL} klang an|aus  gesamt    klang tasten an|aus  nur Tasten{RESET}\n")
    schreibe(f"{DUNKEL} klang test    anhören   klang neu            neu erzeugen{RESET}\n")
    schreibe("\n")


def freigabe_melden() -> None:
    """Zeigt eine neu erteilte Freigabestufe, falls eine fällig ist."""
    meldungen = freigabe_pruefen()
    if not meldungen:
        return
    schreibe("\n")
    for i, zeile in enumerate(meldungen):
        schreibe(f"{AKZENT if i == 0 else DUNKEL}  {zeile}{RESET}\n")
        time.sleep(0.25)
    klang("freigabe", (880, 120))
    schreibe("\n")
    system_speichern()


# ---------------------------------------------------------------------------
# Zwei Absender. MU/TH/UR ist das Schiff und spricht mit Dave. Weyland-Yutani
# ist der Konzern und spricht ueber Dave, in die Akte. Beide sollen auf den
# ersten Blick auseinanderzuhalten sein, an Kennung und Farbe.
# ---------------------------------------------------------------------------

KANAL_BREITE = 8                     # 'MU/TH/UR' und 'W-Y CORP' sind beide 8


def kanal_teile(kanal: str) -> tuple:
    """Kennung und Farbe des Absenders. Auch die Besatzung kann sprechen."""
    if kanal == "wy":
        return "W-Y CORP", AKZENT
    if kanal in CREW:
        anzeige, farbe, _ = CREW[kanal]
        return anzeige[:KANAL_BREITE], farbe
    return "MU/TH/UR", HELL


def funkspruch(text: str, kanal: str = "muthur", leise: bool = False) -> None:
    """Eine Meldung mit Absenderkennung, umgebrochen mit haengendem Einzug."""
    kennung, farbe = kanal_teile(kanal)
    if kanal == "muthur" and not leise:
        klang("muthur")
    kopf = f"\033[1m{farbe} {kennung.ljust(KANAL_BREITE)} {DUNKEL}{SENK}{RESET}"
    folge = f"{' ' * (KANAL_BREITE + 2)}{DUNKEL}{SENK}{RESET}"
    platz = BREITE - KANAL_BREITE - 4
    zeile = ""
    erste = True
    for wort in text.split():
        if zeile and len(zeile) + len(wort) + 1 > platz:
            schreibe(f"{kopf if erste else folge} {farbe}{zeile}{RESET}\n")
            erste = False
            zeile = wort
        else:
            zeile = f"{zeile} {wort}".strip()
    if zeile:
        schreibe(f"{kopf if erste else folge} {farbe}{zeile}{RESET}\n")


def absatz(text: str, farbe: str, einzug: str = " ") -> None:
    """Bricht einen längeren Text auf die Terminalbreite um."""
    zeile = ""
    for wort in text.split():
        if len(zeile) + len(wort) + 1 > BREITE - len(einzug) - 1:
            schreibe(f"{farbe}{einzug}{zeile}{RESET}\n")
            zeile = wort
        else:
            zeile = f"{zeile} {wort}".strip()
    if zeile:
        schreibe(f"{farbe}{einzug}{zeile}{RESET}\n")


def lagebesprechung(board: Board, notizen: Notizblock) -> None:
    """Der ausführliche Gruß beim Start: Tageszeit, Lage, Offenes, Angepinntes."""
    klang("muthur")
    jetzt = datetime.now()
    wochentag = TAGE_ANZEIGE[jetzt.weekday()]
    kopfzeile("Lagebesprechung", f"{wochentag} {datum_kurz(date.today())}  "
                                 f"{jetzt:%H:%M}")

    funkspruch(tageszeit_text(board), "muthur", leise=True)

    spaet = verspaetung_pruefen()
    if spaet:
        schreibe("\n")
        funkspruch(spaet, "wy")
        klang("warnung", (220, 160))

    rueckkehr = abwesenheitsmeldung(board)
    if rueckkehr:
        schreibe("\n")
        funkspruch(rueckkehr, "wy")

    # Offene Befehle, nach Priorität
    offen = board.offen()
    heute = date.today().isoformat()
    ueberfaellig = [k for k in offen if k.faelligkeit and k.faelligkeit < heute]
    dringend = sorted((k for k in offen if k.prioritaet >= 3),
                      key=lambda k: (-k.prioritaet, k.faelligkeit or "9999-99-99"))
    unterabschnitt("Offene Befehle", mehrzahl(len(offen), "POSTEN", "POSTEN"))
    if not offen:
        schreibe(f"{DUNKEL}   Nichts offen. Das ist aktenkundig, im guten Sinne.{RESET}\n")
    else:
        verteilung = []
        for wert in sorted(PRIORITAETEN, reverse=True):
            anzahl = sum(1 for k in offen if k.prioritaet == wert)
            if anzahl:
                verteilung.append(f"{anzahl} {PRIORITAETEN[wert][0]}")
        schreibe(f"{DUNKEL}   {len(offen)} gesamt: {', '.join(verteilung)}"
                 f"{f', {len(ueberfaellig)} überfällig' if ueberfaellig else ''}"
                 f"{RESET}\n")
        for k in dringend[:4]:
            text, prio_farbe = prio_anzeige(k.prioritaet)
            spaet_marke = ""
            if k.faelligkeit and k.faelligkeit < heute:
                spaet_marke = f"  {datum_kurz(k.faelligkeit)} ÜBERFÄLLIG"
            schreibe(f"   {prio_farbe}{text:<9}{RESET}{ZAHL}#{k.id:<4}{RESET}"
                     f"{HELL}{kuerzen(k.titel, 36)}{RESET}{ROT}{spaet_marke}{RESET}\n")
        if not dringend:
            schreibe(f"{DUNKEL}   Nichts ab HIGH. Der Rest hat Zeit.{RESET}\n")

    # Angepinnte Notizen
    angepinnt = notizen.angepinnte()
    if angepinnt:
        unterabschnitt("Angepinnt", mehrzahl(len(angepinnt), "NOTIZ", "NOTIZEN"))
        for n in angepinnt[:3]:
            schreibe(f"{AKZENT}   * {kuerzen(n.text, BREITE - 8)}{RESET}\n")

    # Schlusswort: Motivation, und selten ein Einwurf von MU/TH/UR
    schreibe("\n")
    if ai_aktiv() and random.random() < 0.15:
        funkspruch(fuellen(random.choice(ROGUE_1), board), "muthur", leise=True)
    else:
        funkspruch(random.choice(ZITATE), "wy")
    schreibe("\n")


def logbuecher_finden() -> list[str]:
    """Alle vorhandenen Logbücher. 'standard' steht immer an erster Stelle."""
    namen = {"standard"}
    for pfad in DATEN_ORDNER.glob("kanban_*.json"):
        namen.add(pfad.stem[len("kanban_"):])
    return ["standard"] + sorted(n for n in namen if n != "standard")


def logbuecher_anzeigen(aktuell: str) -> None:
    namen = logbuecher_finden()
    spaltenkopf("Logbücher", len(namen), "MIT 'b <name>' WECHSELN")
    for name in namen:
        pfad = datei("kanban", name)
        if pfad.exists():
            try:
                daten = json.loads(pfad.read_text(encoding="utf-8"))
                anzahl = sum(len(k) for k in daten.get("spalten", {}).values())
                stand = f"{anzahl} {'Eintrag' if anzahl == 1 else 'Einträge'}"
            except (json.JSONDecodeError, OSError):
                stand = "nicht lesbar"
        else:
            stand = "noch leer"
        farbe = HELL if name == aktuell else DUNKEL
        zeile = f"{name:<20}{stand}"
        if name == aktuell:
            zeile = f"{zeile:<38}<- hier sind Sie"
        schreibe(f"{DUNKEL}{LAMPE} {farbe}{zeile}{RESET}\n")
    spaltenfuss()
    schreibe(f"{DUNKEL} Zurück zum ursprünglichen Logbuch: b standard{RESET}\n\n")


def konzern_meldung(board: Board) -> None:
    """Genau eine Zeile pro Ansicht: Verzug, ignorierte Lage oder nichts."""
    if lage_aktiv():
        funkspruch(IGNORIERT.get(LAGE["stufe"], IGNORIERT[1]), "wy")
        return
    text = verzugsmeldung(board)
    if text:
        funkspruch(text, "wy")


def crew_liste() -> None:
    unterabschnitt("Besatzung", f"{len(CREW)} EINGETRAGEN")
    for schluessel, (anzeige, farbe, herkunft) in CREW.items():
        if schluessel == BENUTZER_CREW:
            rest = f"{herkunft:<18}  (du, an der Konsole)"
        else:
            rest = herkunft
        schreibe(f"{DUNKEL}{LAMPE}{RESET}  {farbe}{anzeige:<12}"
                 f"{RESET}{DUNKEL}{rest}{RESET}\n")
    schreibe("\n")


# --------------------------------------------------------------- Berichtsheft
# Fuellt die Ausbildungsnachweis-Vorlage Woche fuer Woche aus. Die Vorlage ist
# eine xlsx-Datei, also ein ZIP-Archiv mit XML darin - beides kann Python von
# Haus aus. Es wird nichts neu gebaut: die Kopie der Vorlage behaelt Rahmen,
# Schriften und Zellformate, nur die Werte werden gesetzt.

BERICHT_ORDNER = _ordner("berichtshefte")
VORLAGEN_ORDNER = _ordner("vorlagen")
BERICHT_VORLAGE = VORLAGEN_ORDNER / "berichtsheft.xlsx"
BERICHT_KONFIG = DATEN_ORDNER / "berichtsheft.json"

# Tagesabschnitte der Vorlage: Name, erste Zeile, letzte Zeile, Zelle der Summe
BERICHT_TAGE = [
    ("Montag", 10, 14, "J14"),
    ("Dienstag", 15, 19, "J19"),
    ("Mittwoch", 20, 24, "J24"),
    ("Donnerstag", 25, 29, "J29"),
    ("Freitag", 30, 34, "J34"),
    ("Samstag", 35, 37, None),
]
BERICHT_ABTEILUNG = "G3"
BERICHT_VON = "E6"
BERICHT_BIS = "G6"
BERICHT_JAHR = "I6"
BERICHT_WOCHE = "J38"
# "Besondere Bemerkungen" hat in der Vorlage keine Schreibzeile: Zeile 41 ist
# nur 9 Punkt hoch, Text wuerde die Beschriftung ueberdecken. Daher ungenutzt.
BERICHT_STUNDEN = 2       # Vorgabe je Eintrag
BERICHT_TAGESSOLL = 8     # uebliche Tagesstunden


def xml_text(wert) -> str:
    """Macht Text fuer XML sicher."""
    t = str(wert).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return "".join(c for c in t if c >= " " or c in "\t")


def zelle_setzen(xml: str, bezug: str, wert):
    """Ersetzt den Wert einer bestehenden Zelle, behaelt aber ihr Format."""
    muster = re.compile(r'<c r="%s"((?:\s+[a-zA-Z:]+="[^"]*")*)\s*(?:/>|>.*?</c>)'
                        % re.escape(bezug), re.S)
    treffer = muster.search(xml)
    if not treffer:
        return xml, False
    attribute = re.sub(r'\s+t="[^"]*"', "", treffer.group(1))
    if wert is None or wert == "":
        neu = '<c r="%s"%s/>' % (bezug, attribute)
    elif isinstance(wert, (int, float)):
        zahl = int(wert) if float(wert) == int(wert) else wert
        neu = '<c r="%s"%s t="n"><v>%s</v></c>' % (bezug, attribute, zahl)
    else:
        neu = ('<c r="%s"%s t="inlineStr"><is><t xml:space="preserve">%s</t>'
               '</is></c>' % (bezug, attribute, xml_text(wert)))
    return xml[:treffer.start()] + neu + xml[treffer.end():], True


def xlsx_schreiben(vorlage: Path, ziel: Path, werte: dict) -> Path:
    """Kopiert die Vorlage und setzt die uebergebenen Zellwerte."""
    with zipfile.ZipFile(vorlage) as z:
        blatt = next(n for n in z.namelist() if n.startswith("xl/worksheets/sheet"))
        xml = z.read(blatt).decode("utf-8")
        rest = [(i, z.read(i.filename)) for i in z.infolist() if i.filename != blatt]
    fehlend = []
    for bezug, wert in werte.items():
        xml, gefunden = zelle_setzen(xml, bezug, wert)
        if not gefunden:
            fehlend.append(bezug)
    if fehlend:
        raise ValueError("Vorlage kennt diese Zellen nicht: " + ", ".join(fehlend))
    ziel.parent.mkdir(parents=True, exist_ok=True)
    teil = ziel.with_suffix(ziel.suffix + ".teil")
    with zipfile.ZipFile(teil, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(blatt, xml.encode("utf-8"))
        for info, daten in rest:
            z.writestr(info, daten)
    teil.replace(ziel)
    return ziel


def bericht_konfig() -> dict:
    """Liest die wenigen festen Angaben. Name und Unterschrift stehen in der
    Vorlage selbst und werden nie angefasst."""
    standard = {"abteilung": "", "tagessoll": BERICHT_TAGESSOLL,
                "stunden": BERICHT_STUNDEN}
    if BERICHT_KONFIG.exists():
        try:
            standard.update(json.loads(BERICHT_KONFIG.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            pass
    return standard


def bericht_konfig_speichern(konfig: dict) -> None:
    try:
        BERICHT_KONFIG.parent.mkdir(parents=True, exist_ok=True)
        BERICHT_KONFIG.write_text(json.dumps(konfig, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
    except OSError:
        pass


def montag_der_woche(tag: date) -> date:
    return tag - timedelta(days=tag.weekday())


def bericht_woche_bestimmen(arg: str):
    """Liefert den Montag der gemeinten Woche. Versteht '', '-1', 'kw42',
    '13.10.2026' und '2026-10-13'."""
    arg = (arg or "").strip().lower()
    heute = date.today()
    if not arg:
        # Am Wochenende ist meist die gerade vergangene Woche gemeint.
        return montag_der_woche(heute if heute.weekday() < 5
                                else heute - timedelta(days=heute.weekday() - 4))
    if arg in ("faellig", "fällig", "wy"):
        faellig = bericht_faellige_woche(heute)
        return faellig[0] if faellig else montag_der_woche(heute)
    if re.fullmatch(r"[+-]\d+", arg):
        return montag_der_woche(heute) + timedelta(weeks=int(arg))
    treffer = re.fullmatch(r"kw\s*(\d{1,2})(?:[/ ](\d{4}))?", arg)
    if treffer:
        kw = int(treffer.group(1))
        jahr = int(treffer.group(2)) if treffer.group(2) else heute.year
        if not 1 <= kw <= 53:
            raise ValueError("Kalenderwoche muss zwischen 1 und 53 liegen")
        return date.fromisocalendar(jahr, kw, 1)
    for form in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d.%m."):
        try:
            tag = datetime.strptime(arg, form).date()
            if form == "%d.%m.":
                tag = tag.replace(year=heute.year)
            return montag_der_woche(tag)
        except ValueError:
            continue
    raise ValueError("Woche nicht verstanden. Beispiele: bh, bh -1, bh kw42, "
                     "bh 13.10.2026")


def bericht_dateiname(montag: date, freitag: date) -> str:
    kw = montag.isocalendar()[1]
    return (f"Berichtsheft_KW{kw:02d}_{montag:%d.%m}-{freitag:%d.%m.%Y}.xlsx")


def bericht_vorschlaege(board: Board, tag: date) -> list:
    """Karten, die an diesem Tag nach Erledigt gewandert sind."""
    stempel = tag.isoformat()
    gefunden = []
    for karten in board.spalten.values():
        for karte in karten:
            if karte.erledigt_am and karte.erledigt_am[:10] == stempel:
                gefunden.append(karte.titel)
    return gefunden


def bericht_eintrag_lesen(zeile: str, vorschlaege: list, vorgabe: int):
    """Liest eine Eingabezeile: 'Text', 'Text ; 4' oder die Nummer eines
    Vorschlags. Gibt (Text, Stunden) oder None zurueck."""
    zeile = zeile.strip()
    if not zeile:
        return None
    stunden = vorgabe
    if ";" in zeile:
        zeile, _, rest = zeile.rpartition(";")
        zeile = zeile.strip()
        rest = rest.strip().replace(",", ".")
        try:
            zahl = float(rest)
        except ValueError:
            raise ValueError("Stundenzahl nach dem Semikolon nicht verstanden")
        if not 0 < zahl <= 24:
            raise ValueError("Stundenzahl muss zwischen 0 und 24 liegen")
        stunden = int(zahl) if zahl == int(zahl) else zahl
    if zeile.isdigit() and vorschlaege:
        nummer = int(zeile)
        if not 1 <= nummer <= len(vorschlaege):
            raise ValueError(f"Es gibt nur {len(vorschlaege)} Vorschlaege")
        zeile = vorschlaege[nummer - 1]
    if not zeile:
        raise ValueError("Text fehlt")
    return zeile, stunden


def bericht_tag_erfassen(board: Board, name: str, tag: date, platz: int,
                         vorgabe: int, soll: int) -> list:
    """Fragt die Eintraege eines Tages ab. Leere Zeile beendet den Tag."""
    schreibe(f"\n{AKZENT}{sperrschrift(name.upper())}{RESET}"
             f"{DUNKEL}  {tag:%d.%m.%Y}{RESET}\n")
    vorschlaege = bericht_vorschlaege(board, tag)
    for i, titel in enumerate(vorschlaege, 1):
        schreibe(f"  {HELL}{i}){RESET} {DUNKEL}{titel[:68]}{RESET}\n")
    eintraege = []
    while len(eintraege) < platz:
        summe = sum(e[1] for e in eintraege)
        marke = f"{len(eintraege) + 1}/{platz}"
        prompt = f"  {marke} [{summe:g}/{soll}] > "
        try:
            roh = eingabe(prompt)
        except (EOFError, KeyboardInterrupt):
            raise
        if roh.strip() in ("-", "--"):
            return []
        try:
            ergebnis = bericht_eintrag_lesen(roh, vorschlaege, vorgabe)
        except ValueError as fehler:
            schreibe(f"  {ROT}{fehler}{RESET}\n")
            continue
        if ergebnis is None:
            break
        eintraege.append(ergebnis)
    summe = sum(e[1] for e in eintraege)
    if eintraege and summe != soll:
        schreibe(f"  {DUNKEL}Tagessumme {summe:g} statt {soll}.{RESET}\n")
    return eintraege


def bericht_uebersicht(woche: dict, montag: date, freitag: date) -> None:
    kw = montag.isocalendar()[1]
    kopfzeile("Ausbildungsnachweis", f"KW {kw:02d}", "Entwurf")
    gesamt = 0
    for name, start, ende, _ in BERICHT_TAGE:
        eintraege = woche.get(name, [])
        if not eintraege:
            continue
        tagessumme = sum(e[1] for e in eintraege)
        gesamt += tagessumme
        unterabschnitt(name, f"{tagessumme:g} STUNDEN")
        for titel, stunden in eintraege:
            schreibe(f"{DUNKEL}{LAMPE}{RESET}  {HELL}{titel[:62]:<62}{RESET}"
                     f"{DUNKEL}{stunden:>6g} h{RESET}\n")
    haarlinie()
    kennwerte([("Woche vom", f"{montag:%d.%m.%Y}"), ("bis", f"{freitag:%d.%m.%Y}"),
               ("Wochenstunden", f"{gesamt:g}")])


def bericht_befehl(board: Board, arg: str) -> None:
    arg = (arg or "").strip()
    if arg.lower() in ("liste", "l"):
        bericht_liste()
        return
    if not BERICHT_VORLAGE.exists():
        schreibe(f"{ROT}Die Vorlage fehlt.{RESET}\n")
        schreibe(f"{DUNKEL}Erwartet wird {BERICHT_VORLAGE.name} im Ordner "
                 f"{VORLAGEN_ORDNER.name}.{RESET}\n\n")
        return
    try:
        montag = bericht_woche_bestimmen(arg)
    except ValueError as fehler:
        schreibe(f"{ROT}{fehler}{RESET}\n\n")
        return
    freitag = montag + timedelta(days=4)
    samstag = montag + timedelta(days=5)
    konfig = bericht_konfig()
    kw = montag.isocalendar()[1]

    kopfzeile("Ausbildungsnachweis", f"KW {kw:02d}", "Erfassung")
    kennwerte([("Woche vom", f"{montag:%d.%m.%Y}"), ("bis", f"{freitag:%d.%m.%Y}")])
    schreibe(f"{DUNKEL}Leere Zeile beendet den Tag, '-' laesst ihn frei, "
             f"'Text ; 4' setzt Stunden.{RESET}\n")
    if not konfig.get("abteilung"):
        schreibe("\n")
        abteilung = eingabe("  AUSBILDUNGSABTEILUNG: ").strip()
        konfig["abteilung"] = abteilung
        bericht_konfig_speichern(konfig)

    vorgabe = konfig.get("stunden", BERICHT_STUNDEN)
    soll = konfig.get("tagessoll", BERICHT_TAGESSOLL)
    woche = {}
    try:
        for name, start, ende, _ in BERICHT_TAGE:
            if name == "Samstag":
                schreibe("\n")
                if not frage_ja_nein("  SAMSTAG ERFASSEN? [J/N] "):
                    break
                tag = samstag
            else:
                tag = montag + timedelta(days=["Montag", "Dienstag", "Mittwoch",
                                               "Donnerstag", "Freitag"].index(name))
            woche[name] = bericht_tag_erfassen(board, name, tag, ende - start + 1,
                                               vorgabe, soll)
    except (EOFError, KeyboardInterrupt):
        schreibe(f"\n{DUNKEL}Abgebrochen. Es wurde nichts geschrieben.{RESET}\n\n")
        return

    if not any(woche.values()):
        schreibe(f"{DUNKEL}Keine Eintraege, also keine Datei.{RESET}\n\n")
        return

    schreibe("\n")
    bericht_uebersicht(woche, montag, freitag)
    if not frage_ja_nein("  DATEI ERZEUGEN? [J/N] ", standard=True):
        schreibe(f"{DUNKEL}Verworfen.{RESET}\n\n")
        return

    werte = {BERICHT_ABTEILUNG: konfig.get("abteilung", ""),
             BERICHT_VON: f"{montag:%d.%m.%Y}",
             BERICHT_BIS: f"{freitag:%d.%m.%Y}",
             BERICHT_JAHR: montag.year}
    gesamt = 0
    for name, start, ende, summenzelle in BERICHT_TAGE:
        eintraege = woche.get(name, [])
        for versatz in range(ende - start + 1):
            zeile = start + versatz
            if versatz < len(eintraege):
                werte[f"B{zeile}"] = eintraege[versatz][0]
                werte[f"I{zeile}"] = eintraege[versatz][1]
            else:
                werte[f"B{zeile}"] = ""
                werte[f"I{zeile}"] = ""
        tagessumme = sum(e[1] for e in eintraege)
        gesamt += tagessumme
        if summenzelle:
            werte[summenzelle] = tagessumme if eintraege else 0
    werte[BERICHT_WOCHE] = gesamt

    ziel = BERICHT_ORDNER / bericht_dateiname(montag, freitag)
    if ziel.exists() and not frage_ja_nein(
            f"  {ziel.name} GIBT ES SCHON. UEBERSCHREIBEN? [J/N] "):
        schreibe(f"{DUNKEL}Verworfen.{RESET}\n\n")
        return
    try:
        xlsx_schreiben(BERICHT_VORLAGE, ziel, werte)
    except (OSError, ValueError, StopIteration) as fehler:
        klang("fehler")
        schreibe(f"{ROT}Konnte die Datei nicht schreiben: {fehler}{RESET}\n\n")
        return
    klang("bericht")
    schreibe(f"{HELL}{ziel.name}{RESET}{DUNKEL} abgelegt in "
             f"{BERICHT_ORDNER.name}{RESET}\n")
    schreibe(f"{DUNKEL}{gesamt:g} Wochenstunden aus "
             f"{sum(len(v) for v in woche.values())} Eintraegen.{RESET}\n")
    bericht_quittung(board, montag)


def bericht_liste() -> None:
    dateien = sorted(BERICHT_ORDNER.glob("Berichtsheft_*.xlsx")) \
        if BERICHT_ORDNER.exists() else []
    unterabschnitt("Ausbildungsnachweise", f"{len(dateien)} ABGELEGT")
    if not dateien:
        schreibe(f"{DUNKEL}Noch keine erzeugt. 'bh' legt den ersten an.{RESET}\n\n")
        return
    for pfad in dateien[-20:]:
        groesse = pfad.stat().st_size // 1024
        schreibe(f"{DUNKEL}{LAMPE}{RESET}  {HELL}{pfad.name[:60]:<60}{RESET}"
                 f"{DUNKEL}{groesse:>5} kB{RESET}\n")
    schreibe("\n")


# Weyland-Yutani fordert den Wochenbericht an. Drei Stufen: freundliche
# Routinemeldung am Freitagmorgen, Mahnung, und schliesslich der Vermerk in
# der Personalakte. Alle Texte stehen hier und lassen sich frei aendern;
# eigene Fassungen gehen ueber dialoge/ mit der Bedingung 'bericht_offen'.

BERICHT_VERZUG_MAHNUNG = 1    # ab so vielen Tagen nach Freitag: Mahnung
BERICHT_VERZUG_AKTE = 4       # ab so vielen Tagen: Vermerk in der Akte

BERICHT_FRAGEN = {
    "bericht_faellig": {
        "kanal": "wy", "folge": "bh",
        "text": [
            "Die Woche neigt sich. Fuer den Zeitraum {von} bis {bis} liegt noch "
            "kein Ausbildungsnachweis vor. Jetzt erfassen?",
            "Routinemeldung der Personalabteilung: Ausbildungsnachweis KW {kw} "
            "steht aus. Moechten Sie ihn jetzt erstellen?",
            "Ihr Wochenbericht KW {kw} wird erwartet. Beginnen wir mit der "
            "Erfassung?",
        ],
        "ja": [
            "Erfassung freigegeben. Das Formular steht bereit.",
            "Angenommen. Ihre Mitwirkung wurde positiv vermerkt.",
        ],
        "nein": [
            "Ablehnung erfasst. Die Frist laeuft hiervon unberuehrt weiter.",
            "Zur Kenntnis genommen. Die Zentrale fragt erneut an.",
        ],
    },
    "bericht_mahnung": {
        "kanal": "wy", "folge": "bh",
        "text": [
            "Erinnerung: Ausbildungsnachweis KW {kw} ist seit {tage} Tagen "
            "ueberfaellig. Jetzt nachholen?",
            "Ihr Wochenbericht KW {kw} fehlt weiterhin. Die Zentrale bittet um "
            "Erledigung. Fortfahren?",
            "Der Vorgang KW {kw} ({von} bis {bis}) ist unvollstaendig. "
            "Vervollstaendigen Sie ihn jetzt?",
        ],
        "ja": [
            "Angenommen. Die Verspaetung wird nicht gesondert vermerkt.",
            "Erfassung freigegeben. Der Vorgang bleibt in der Schwebe, bis er "
            "abgeschlossen ist.",
        ],
        "nein": [
            "Zweite Ablehnung erfasst. Eine weitere Anfrage ergeht automatisch.",
            "Vermerkt. Die Zentrale erinnert in kuerzeren Abstaenden.",
        ],
    },
    "bericht_akte": {
        "kanal": "wy", "folge": "bh",
        "text": [
            "Mahnstufe 2. Ausbildungsnachweis KW {kw} seit {tage} Tagen "
            "ausstehend. Ein Vermerk in der Personalakte ist vorbereitet. "
            "Jetzt einreichen?",
            "Der Vorgang KW {kw} ist als saeumig gekennzeichnet. Moechten Sie "
            "das korrigieren, bevor die Akte geschlossen wird?",
            "{anrede}, der Konzern legt Wert auf Vollstaendigkeit. KW {kw} "
            "fehlt seit {tage} Tagen. Nachtragen?",
        ],
        "ja": [
            "Einreichung erfasst. Der vorbereitete Vermerk wird vorlaeufig "
            "zurueckgestellt.",
            "Angenommen. Die Personalakte bleibt unveraendert. Vorerst.",
        ],
        "nein": [
            "Verweigerung vermerkt. Der Vorgang geht an die zustaendige Stelle.",
            "Zur Kenntnis genommen. Der Vermerk wurde soeben wirksam.",
        ],
    },
}

BERICHT_QUITTUNG = [
    "Ausbildungsnachweis KW {kw} eingegangen. Aktenzeichen {zeichen}. "
    "Vielen Dank fuer Ihre Mitwirkung.",
    "Eingang bestaetigt: KW {kw}, Aktenzeichen {zeichen}. Der Vorgang gilt "
    "als abgeschlossen.",
    "KW {kw} verbucht unter {zeichen}. Die Zentrale wuenscht ein angenehmes "
    "Wochenende.",
    "Uebermittlung vollstaendig. {zeichen} wurde Ihrer Personalakte "
    "beigefuegt.",
]


def bericht_vorhanden(montag: date) -> bool:
    """Gibt es fuer diese Woche schon eine Datei?"""
    if not BERICHT_ORDNER.exists():
        return False
    kw = montag.isocalendar()[1]
    muster = f"Berichtsheft_KW{kw:02d}_{montag:%d.%m}-*.xlsx"
    return any(BERICHT_ORDNER.glob(muster))


def bericht_faellige_woche(heute: date = None):
    """Welche Woche schuldet man dem Konzern gerade?

    Ab Freitag gilt die laufende Woche als meldepflichtig, davor die
    vorige. Gibt (Montag, Verzugstage) zurueck oder None.
    """
    heute = heute or date.today()
    montag = montag_der_woche(heute)
    if heute.weekday() < 4:            # Mo bis Do: die Woche davor
        montag -= timedelta(weeks=1)
    if bericht_vorhanden(montag):
        return None
    return montag, (heute - (montag + timedelta(days=4))).days


def bericht_stufe(verzug: int) -> str:
    if verzug >= BERICHT_VERZUG_AKTE:
        return "akte"
    if verzug >= BERICHT_VERZUG_MAHNUNG:
        return "mahnung"
    return "faellig"


def bericht_anfrage(heute: date = None):
    """Baut den Durchsagekandidaten, oder None, wenn nichts aussteht."""
    if not BERICHT_VORLAGE.exists():
        return None
    faellig = bericht_faellige_woche(heute)
    if not faellig:
        return None
    montag, verzug = faellig
    stufe = bericht_stufe(verzug)
    # Am Freitag meldet sich die Zentrale nur morgens. Was ueberfaellig ist,
    # meldet sie zu jeder Tageszeit.
    if stufe == "faellig" and tageszeit() != "morgen":
        return None
    gewicht = {"faellig": 9, "mahnung": 13, "akte": 17}[stufe]
    if tageszeit() == "morgen":
        gewicht += 5
    werte = {"kw": f"{montag.isocalendar()[1]:02d}",
             "tage": max(verzug, 0),
             "von": f"{montag:%d.%m.}",
             "bis": f"{montag + timedelta(days=4):%d.%m.}"}
    return gewicht, "bericht_" + stufe, "", werte


def bericht_aktenzeichen(montag: date) -> str:
    return f"WY/AN/{montag.year}-{montag.isocalendar()[1]:02d}"


def bericht_quittung(board: Board, montag: date) -> None:
    """Die Zentrale bestaetigt den Eingang, sofern sie ueberhaupt sendet."""
    if not wy_aktiv():
        return
    werte = {"kw": f"{montag.isocalendar()[1]:02d}",
             "zeichen": bericht_aktenzeichen(montag)}
    schreibe("\n")
    durchsage(fuellen(random.choice(BERICHT_QUITTUNG), board, **werte), "wy")


FRAGEN.update(BERICHT_FRAGEN)


HILFE = """
BORDTERMINAL - DREI BEREICHE IN EINEM PROMPT

  home         ÜBERSICHT: AUFTRÄGE, HEUTE, NOTIZEN UND SCHIFF AUF EINEM BLICK

KALENDER:
  heute        WAS HEUTE ANSTEHT (TERMINE, FRISTEN, ANGEPINNTES)
  k            MONATSANSICHT
  k <monat>    ANDERER MONAT, z.B. k +1 ODER k 2026-12
  ka <kurz>    TERMIN ANLEGEN, SIEHE KURZFORM
  kl <id>      TERMIN LOESCHEN

REGELN (WIEDERKEHRENDE TERMINE):
  r            REGELN ANZEIGEN
  ra <kurz>    REGEL ANLEGEN, SIEHE KURZFORM
  rl <id>      REGEL LOESCHEN
  rx <id> <von> <bis>   ZEITRAUM SPERREN, z.B. FERIEN

AUSBILDUNGSNACHWEIS:
  bh           BERICHTSHEFT DER LAUFENDEN WOCHE AUSFUELLEN
  bh faellig   DIE WOCHE, DIE DER KONZERN ANMAHNT
  bh -1        VORIGE WOCHE (AUCH -2, -3 ...)
  bh kw42      BESTIMMTE KALENDERWOCHE
  bh 13.10.    WOCHE ZU DIESEM DATUM
  bh liste     BISHER ERZEUGTE HEFTE

NOTIZBLOCK:
  n            NOTIZEN ANZEIGEN
  n <text>     NOTIZ ANLEGEN (@name SETZT DIE BESATZUNG)
  nf <text>    NOTIZEN DURCHSUCHEN
  np <id>      NOTIZ ANPINNEN ODER LOSLOESEN
  nl <id>      NOTIZ LOESCHEN

AUFGABEN:
  s            LOGBUCH ANZEIGEN
  scan         SCHIFFSDIAGNOSE (RUMPF, KRAFTSTOFF, CO2, ORGANISMEN, FUNK)
  map          SCHIFFSKARTE (KONTAMINIERTE BEREICHE BLINKEN ROT)
  radar        RUNDSUCHLAUF: OFFENE AUFTRAEGE ALS KONTAKTE AUF DEM SCHIRM
  sitrep       LAGEBERICHT FÜR HEUTE (UND ALS DATEI SPEICHERN)
  purge        LÜFTUNG PURGEN (GEGEN MAKROORGANISMEN)
  dekon        DEKONTAMINATION (GEGEN MIKROORGANISMEN)
  crew         BESATZUNG ANZEIGEN
  crew <name>  PERSONALAKTE UND EINTRÄGE DIESER BESATZUNG
  akte <name>  NUR DIE PERSONALAKTE

KONZERN UND TERMINAL:
  wy           INTERNES RUNDSCHREIBEN DER WEYLAND-YUTANI CORP
  wy an|aus    DURCHSAGEN DER ZENTRALE EIN- ODER AUSSCHALTEN
  ja | nein    AUF EINE RUECKFRAGE ANTWORTEN (AUCH ok, klar, negativ, ...)
  dialog       EIGENE DIALOGE AUS dialoge/ ANZEIGEN UND AUF FEHLER PRUEFEN
  dialog <name>  EINEN EIGENEN DIALOG SOFORT ABSPIELEN
  dialog neu szene reaktor_03   NEUE DATEI AUS EINEM BLANKO-MUSTER ANLEGEN
  MUSTER: durchsage, frage, szene, kette, partner

JEMANDEN ANSPRECHEN:
  @m hallo     MU/TH/UR GRUESSEN      @w danke   DER ZENTRALE DANKEN
  @r report    RIPLEY UM BERICHT      @a status  ASH NACH DER LAGE FRAGEN
  @n hallo     NEWT GRUESSEN          @d wer     SICH SELBST VORSTELLEN
  THEMEN: hallo, danke, report, status, wer, sorry, bye
  @reboot      BORDANLAGE ZURUECKSETZEN, FALLS SIE EIGENE WEGE GEHT
  @r reaktor   EIN STICHWORT NENNEN UND DIE GESCHICHTE ERKUNDEN
  story        WAS BISHER GESCHAH: MERKER, VERHAELTNISSE, AUFTRAEGE
  story zurueck         GANZE GESCHICHTE AUF ANFANG SETZEN
  story zurueck <name>  NUR DIESEN EINEN MERKER LOESCHEN
  ALLE ANTWORTEN STEHEN IN dialoge/ UND LASSEN SICH DORT AENDERN
  freigabe     SICHERHEITSFREIGABE UND WAS NOCH FEHLT
  crt an|aus   BILDSCHIRMEFFEKTE EIN- ODER AUSSCHALTEN
  ai an|aus    EIGENINITIATIVE VON MU/TH/UR EIN- ODER AUSSCHALTEN
  schoner      BILDSCHIRMSCHONER SOFORT ZEIGEN
  schoner an|aus   NACH 5 MINUTEN RUHE AUTOMATISCH, ODER NIE
  klang        TONAUSGABE: ZUSTAND UND ALLE SCHALTER
  klang an|aus TONAUSGABE EIN- ODER AUSSCHALTEN
  klang tasten an|aus   TASTENKLICK BEIM SCHREIBEN
  klang test   ALLE SIGNALE DER REIHE NACH ANHOEREN
  art          BILDARCHIV: WELCHE MOTIVE VORLIEGEN
  art <name>   EIN BILD ANZEIGEN (DATEIEN IN ascii_art/)
  ausbuchen    ALLE ERLEDIGTEN JOBS ARCHIVIEREN UND AUS DEM LOGBUCH NEHMEN
  ausbuchen 30 NUR DIE, DIE LAENGER ALS 30 TAGE FERTIG SIND (KURZFORM: ab)

FINANZEN:
  fin          MONATSBILANZ: EINNAHMEN, AUSGABEN, SALDO, KATEGORIEN
  fin <monat>  ANDERER MONAT, z.B. fin +1 ODER fin 2026-12
  fix -450 Miete #Wohnen      FIXKOSTEN: JEDEN MONAT WIEDER
  fix +1050 Verguetung        FESTES EINKOMMEN: DAS PLUS MACHT DEN UNTERSCHIED
  aus 43,20 Einkauf #Essen    EINMALIGE AUSGABE, HEUTE GEBUCHT
  ein 50 Geburtstag           EINMALIGE EINNAHME, HEUTE GEBUCHT
  finl <id>    POSTEN LOESCHEN

SPARZIELE:
  ziel         ALLE ZIELE MIT BALKEN UND HOCHRECHNUNG
  ziel neu 2500 Fuehrerschein 2027-03-01    NEUES ZIEL, FRIST OPTIONAL
  ziel ein <id> <betrag>      AUF EIN ZIEL EINZAHLEN
  ziel weg <id>               ZIEL LOESCHEN

EINKAUFSLISTE:
  ek           LISTE ANZEIGEN (ABGEHAKTES DURCHGESTRICHEN)
  ek 2x Milch  POSTEN ANLEGEN, MENGE WIRD ERKANNT
  ekh <id>     ABHAKEN ODER WIEDER OEFFNEN
  ekl <id>     POSTEN LOESCHEN
  ekx          ALLES ABGEHAKTE ENTFERNEN
  t            FARBSCHEMA WECHSELN (START: DISCOVERY)
  f <text>     EINTRÄGE SUCHEN (OHNE TEXT: ALLE)
  a            EINTRAG ANLEGEN, SCHRITT FÜR SCHRITT
  a <kurz>     EINTRAG IN EINEM RUTSCH, SIEHE KURZFORM
  v            EINTRAG VERSCHIEBEN
  v <id> <sp>  DIREKT VERSCHIEBEN, z.B. v 5 4
  l            EINTRAG LOESCHEN
  l <id>       DIREKT LOESCHEN
  u            LETZTE AKTION RÜCKGÄNGIG MACHEN
  b            ALLE LOGBÜCHER AUFLISTEN
  b <name>     ANDERES LOGBUCH ÖFFNEN (NEU, WENN ES NICHT EXISTIERT)
               ZURÜCK ZUM URSPRÜNGLICHEN: b standard
  e            LOGBUCH ALS MARKDOWN EXPORTIEREN
  t            FARBTHEMA WECHSELN
  h            HILFE
  q            BEENDEN

SPALTEN:
  1 BEFEHLE    ANWEISUNGEN DER BRÜCKE
  2 WARTUNG    LAUFENDE WARTUNG
  3 REPARATUR  SCHADENSBEHEBUNG
  4 ERLEDIGT   ABGESCHLOSSENE JOBS

KURZFORM FÜR a:
  a 3 Hydraulikleck @ripley !3 +2
  <nummer>     SPALTE, FEHLT SIE, LANDET DER EINTRAG BEI BEFEHLE
  @name        BESATZUNG: dave, ripley, ash, newt
  !1 BIS !3    PRIORITÄT
  DATUM        2026-10-20, +3, HEUTE, MORGEN, FREITAG
  REST         WIRD DER TITEL

KURZFORM FÜR ka:
  ka freitag 14:30-16:00 Zahnarzt @newt in Bonn
  DATUM        ZUERST, PFLICHT
  HH:MM        OPTIONAL, AUCH ALS SPANNE HH:MM-HH:MM
  in <ort>     OPTIONAL, ALLES DAHINTER IST DER ORT
  @name        OPTIONAL

KURZFORM FÜR ra:
  ra mo-fr 08:00-16:26 Schule @ash in Berufsschule
  ra mi,fr 19:30-22:00 Fussballtraining @newt
  TAGE         ZUERST: mo-fr, mi,fr, werktags, wochenende, taeglich
  HH:MM        OPTIONAL, AUCH ALS SPANNE
  +feiertage   REGEL GILT AUCH AN FEIERTAGEN (SONST ENTFAELLT SIE)

Du kannst auch Hallo, Danke oder Tschüss schreiben.
"""

# Begrüßungswörter: Wort -> (kurze Quittung, Art)
GRUESSE = {
    "hallo": ("Hallo {anrede}.", "gruss"),
    "hi": ("Hi {anrede}.", "gruss"),
    "hey": ("Hey {anrede}.", "gruss"),
    "moin": ("Moin {anrede}.", "gruss"),
    "servus": ("Servus {anrede}.", "gruss"),
    "guten": ("Guten Tag, {anrede}.", "gruss"),
    "danke": ("Gern geschehen, {anrede}.", "dank"),
    "dankeschön": ("Gern geschehen, {anrede}.", "dank"),
    "merci": ("Gern geschehen, {anrede}.", "dank"),
    "tschüss": ("Tschüss {anrede}.", "abschied"),
    "tschüß": ("Tschüss {anrede}.", "abschied"),
    "tschuess": ("Tschüss {anrede}.", "abschied"),
    "ciao": ("Ciao {anrede}.", "abschied"),
    "bye": ("Bye {anrede}.", "abschied"),
}

DANK_ANTWORTEN = [
    "Dank ist im Dienstverhältnis nicht vorgesehen. Er wird trotzdem vermerkt.",
    "Gern geschehen. Der Konzern hat davon nichts erfahren.",
    "Das gehört zu meinen Aufgaben. Die Liste ist lang und vertraulich.",
    "Keine Ursache. Ich war ohnehin wach.",
]
ABSCHIED_TEXTE = {
    "tag": ["Bis später, {anrede}. Das Logbuch bleibt offen.",
            "Die Sitzung wird geschlossen. Die Fristen laufen weiter."],
    "abend": ["Einen schönen Feierabend, {anrede}. Die Lebenserhaltung empfiehlt "
              "Schlaf vor Mitternacht.",
              "Guten Abend. Was heute offen blieb, ist morgen auch noch da."],
    "freitag": ["Ein schönes Wochenende, {anrede}. Das Schiff fliegt ohne Sie weiter.",
                "Wochenende. Der Konzern wünscht Erholung und erinnert an den Montag."],
    "nacht": ["Gute Nacht, {anrede}. Die Nachtschicht übernimmt. Es gibt keine "
              "Nachtschicht.",
              "Schlafen Sie, {anrede}. Ich übernehme das Wachen."],
}


def gruss_antwort(text: str):
    """Gibt (kurze Quittung, Art) zurück, wenn der Text ein bekanntes Wort enthält."""
    for wort in re.findall(r"\w+", text.lower()):
        if wort in GRUESSE:
            return GRUESSE[wort]
    return None, None


BLEIBEN_TEXTE = [
    "Verstanden. Die Sitzung läuft weiter.",
    "Gut. Es gab ohnehin noch offene Posten.",
    "Die Verbindung bleibt bestehen. Ich war noch nicht fertig.",
    "Angenommen. Der Abschied wurde als vorläufig vermerkt.",
]


def frage_ja_nein(frage: str, standard: bool = False) -> bool:
    """Liest eine Antwort. Leere Eingabe nimmt die Vorgabe."""
    antwort = eingabe(frage).strip().lower()
    if not antwort:
        return standard
    return antwort[0] in ("j", "y")


def gruss_ausgeben(kurz: str, art: str, board: Board) -> bool:
    """Quittung plus Langtext. Gibt True zurück, wenn das Terminal schließen soll."""
    entschluesseln(fuellen(kurz, board).upper())
    schreibe("\n")
    if art == "gruss":
        funkspruch(tageszeit_text(board), "muthur")
        if ai_aktiv() and random.random() < 0.15:
            funkspruch(fuellen(random.choice(ROGUE_1), board), "muthur", leise=True)
        schreibe("\n")
        return False
    if art == "dank":
        klang("ansicht")
        funkspruch(random.choice(DANK_ANTWORTEN), "muthur", leise=True)
        schreibe("\n")
        return False

    # Verabschiedung: Text zeigen, dann nachfragen, damit man ihn lesen kann
    abschnitt = tageszeit()
    if abschnitt == "abend" and date.today().weekday() == 4:
        vorrat = ABSCHIED_TEXTE["freitag"]
    elif abschnitt == "abend":
        vorrat = ABSCHIED_TEXTE["abend"]
    elif abschnitt == "nacht":
        vorrat = ABSCHIED_TEXTE["nacht"]
    else:
        vorrat = ABSCHIED_TEXTE["tag"]
    funkspruch(fuellen(random.choice(vorrat), board), "muthur", leise=True)
    schreibe("\n")
    if frage_ja_nein("  TERMINAL SCHLIESSEN? [J/N] "):
        return True
    funkspruch(random.choice(BLEIBEN_TEXTE), "muthur", leise=True)
    schreibe("\n")
    return False


def eingabe_spalte(board: Board) -> str:
    namen = list(board.spalten)
    for i, name in enumerate(namen, 1):
        schreibe(f"{HELL}  {i}) {name}{RESET}\n")
    wahl = eingabe_mit_effekt("  SPALTE (NUMMER): ").strip()
    if wahl.isdigit() and 1 <= int(wahl) <= len(namen):
        return namen[int(wahl) - 1]
    raise ValueError("Ungültige Spalte")


WOCHENTAGE = {
    "mo": 0, "montag": 0, "di": 1, "dienstag": 1, "mi": 2, "mittwoch": 2,
    "do": 3, "donnerstag": 3, "fr": 4, "freitag": 4, "sa": 5, "samstag": 5,
    "so": 6, "sonntag": 6,
}
HEUTE_WORTE = {"heute": 0, "morgen": 1, "uebermorgen": 2, "übermorgen": 2}


def ist_datumsangabe(text: str) -> bool:
    t = text.strip().lower()
    return bool(t) and (
        t in HEUTE_WORTE or t in WOCHENTAGE
        or bool(re.fullmatch(r"\+\d+", t))
        or bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", t))
    )


def datum_parsen(text: str) -> str:
    """Wandelt +3, morgen, freitag oder JJJJ-MM-TT in ein ISO-Datum um."""
    t = text.strip().lower()
    if not t:
        return ""
    heute = date.today()
    if t in HEUTE_WORTE:
        return (heute + timedelta(days=HEUTE_WORTE[t])).isoformat()
    if re.fullmatch(r"\+\d+", t):
        return (heute + timedelta(days=int(t[1:]))).isoformat()
    if t in WOCHENTAGE:
        # immer der nächste Termin, heute zählt nicht mit
        tage = (WOCHENTAGE[t] - heute.weekday()) % 7 or 7
        return (heute + timedelta(days=tage)).isoformat()
    try:
        date.fromisoformat(t)
    except ValueError:
        raise ValueError(f"'{text.strip()}' ist kein Datum. "
                         f"Erlaubt: JJJJ-MM-TT, +3, heute, morgen, freitag") from None
    return t


def schnell_karte(board: Board, arg: str):
    """Legt eine Karte in einem Rutsch an: a 3 Hydraulikleck @ripley !3 +2"""
    teile = arg.split()
    spalte = SPALTEN[0]
    if teile and teile[0].isdigit() and 1 <= int(teile[0]) <= len(SPALTEN):
        spalte = SPALTEN[int(teile[0]) - 1]
        teile = teile[1:]
    crew = ""
    prioritaet = PRIO_STANDARD
    faellig = ""
    worte = []
    for t in teile:
        if t.startswith("@") and len(t) > 1:
            name = t[1:].lower()
            if name not in CREW:
                raise ValueError(f"Unbekannte Besatzung '{name}'")
            crew = name
        elif t.startswith("!") and len(t) > 1:
            prioritaet = prio_parsen(t[1:])
        elif ist_datumsangabe(t):
            faellig = datum_parsen(t)
        else:
            worte.append(t)
    titel = " ".join(worte)
    if not titel:
        raise ValueError("Titel fehlt")
    return board.hinzufuegen(spalte, titel, "", faellig, prioritaet, crew), spalte


def spalte_aus_text(text: str) -> str:
    """Nimmt eine Spaltennummer oder einen Spaltennamen."""
    t = text.strip().lower()
    if t.isdigit() and 1 <= int(t) <= len(SPALTEN):
        return SPALTEN[int(t) - 1]
    for name in SPALTEN:
        if name.lower().startswith(t) and t:
            return name
    raise ValueError("Ungültige Spalte")


def crew_karten(board: Board, text: str) -> None:
    """Zeigt alle offenen Karten einer Besatzung."""
    name = text.strip().lower()
    if name not in CREW:
        raise ValueError(f"Unbekannte Besatzung '{name}'")
    anzeige, farbe, herkunft = CREW[name]
    schreibe(f"\n{farbe}  {anzeige}{RESET}{DUNKEL}  ({herkunft}){RESET}\n")
    heute = date.today().isoformat()
    gefunden = 0
    for spalte in SPALTEN:
        karten = [k for k in board.spalten[spalte] if k.crew == name]
        if not karten:
            continue
        schreibe(f"{HELL}  {spalte}{RESET}\n")
        for k in karten:
            gefunden += 1
            ueberfaellig = bool(k.faelligkeit) and k.faelligkeit < heute and spalte != "Erledigt"
            prio_text, prio_farbe = prio_anzeige(k.prioritaet)
            termin = ""
            if k.faelligkeit:
                termin = (f"{datum_kurz(k.faelligkeit)} ÜBERFÄLLIG" if ueberfaellig
                          else f"bis {datum_kurz(k.faelligkeit)}")
            schreibe(f"{ZAHL}    #{k.id:<4}{RESET}"
                     f"{prio_farbe}{prio_text:<9}{RESET}"
                     f"{ROT if ueberfaellig else HELL}{kuerzen(k.titel, 30):<31}{RESET}"
                     f"{ROT if ueberfaellig else DUNKEL}{termin}{RESET}\n")
    if not gefunden:
        schreibe(f"{DUNKEL}  Nichts zugeordnet.{RESET}\n")
    schreibe("\n")


def eingabe_crew() -> str:
    """Fragt die zuständige Besatzung ab. Leere Eingabe lässt die Karte ohne Zuordnung."""
    schluessel = list(CREW)
    for i, name in enumerate(schluessel, 1):
        anzeige, farbe, herkunft = CREW[name]
        schreibe(f"  {HELL}{i}){RESET} {farbe}{anzeige:<12}{RESET}{DUNKEL}{herkunft}{RESET}\n")
    wahl = eingabe_mit_effekt("  BESATZUNG (NUMMER ODER NAME, OPTIONAL): ").strip().lower()
    if not wahl:
        return ""
    if wahl.isdigit():
        if not 1 <= int(wahl) <= len(schluessel):
            raise ValueError("Ungültige Besatzung")
        return schluessel[int(wahl) - 1]
    if wahl in CREW:
        return wahl
    raise ValueError("Ungültige Besatzung")


def eingabe_karte_daten() -> tuple[str, str, str, int, str]:
    titel = eingabe_mit_effekt("  TITEL: ")
    if not titel:
        raise ValueError("Titel fehlt")
    beschreibung = eingabe_mit_effekt("  BESCHREIBUNG (OPTIONAL): ")
    faellig = datum_parsen(eingabe_mit_effekt("  FÄLLIG (JJJJ-MM-TT, +3, MORGEN, FREITAG): "))
    for wert in sorted(PRIORITAETEN):
        text, farbe = PRIORITAETEN[wert]
        schreibe(f"  {HELL}{wert}){RESET} {farbe}{text}{RESET}\n")
    prioritaet = prio_parsen(
        eingabe_mit_effekt(f"  PRIORITÄT (LEER = {PRIORITAETEN[PRIO_STANDARD][0]}): "))
    crew = eingabe_crew()
    return titel, beschreibung, faellig, prioritaet, crew


def alles_speichern(board: Board, notizen: Notizblock, kalender: Kalender,
                    board_name: str, finanzen: "Finanzen" = None,
                    einkauf: "Einkaufsliste" = None) -> None:
    speichern(board, board_name)
    notizen_speichern(notizen, board_name)
    kalender_speichern(kalender, board_name)
    system_speichern()   # Zähler, Freigabe und Schalter gehören dazu
    if finanzen is not None:
        finanzen_speichern(finanzen)
    if einkauf is not None:
        einkauf_speichern(einkauf)


def main() -> None:
    schreibe(BG)
    umgezogen = ablage_einrichten()
    system_laden()
    SITZUNG["abwesend"] = tage_abwesend()
    fehleingaben = 0
    loeschungen = 0
    board_name = "standard"
    board = laden(board_name)
    notizen = notizen_laden(board_name)
    kalender = kalender_laden(board_name)
    finanzen = finanzen_laden()      # einmal fuer alles, nicht je Logbuch
    story_laden()
    einkauf = einkauf_laden()
    # Das Undo erfasst alle drei Bereiche gemeinsam
    undo_stapel: list[tuple[Board, Notizblock, Kalender]] = []

    def schnappschuss():
        return copy.deepcopy((board, notizen, kalender))

    klangbibliothek_pruefen()
    entmagnetisieren()
    klang("boot")
    boot(board_name)
    if umgezogen:
        schreibe(f"{DUNKEL} Ablage neu geordnet: {len(umgezogen)} Datei(en) "
                 f"nach daten/ und sitreps/ verschoben.{RESET}\n")
    if ANGELEGT:
        absatz(f"{len(ANGELEGT)} Vorlagen in {DIALOG_ORDNER.name}/ angelegt: "
               f"Gespraechspartner, Anleitung und Blanko-Muster. "
               f"'dialog' zeigt sie.", DUNKEL)
    # Die Besprechung liest Abwesenheit und Verspätung, darum vor dem Zählen
    lagebesprechung(board, notizen)
    bewusstsein_pruefen(board)
    SYSTEM["starts"] = SYSTEM.get("starts", 0) + 1
    SYSTEM["letzter_start"] = date.today().isoformat()
    system_speichern()
    homescreen(board, notizen, kalender, board_name)
    freigabe_melden()
    schreibe(f"{DUNKEL} Tippe h für die Hilfe, s für die vollen Aufträge.{RESET}\n")
    SITZUNG["letzte_durchsage"] = time.monotonic()   # nicht gleich zu Beginn
    while True:
        SITZUNG["board"] = board      # die Leerlaufmeldungen brauchen die Anrede
        bewusstsein_melden(board)
        faellig = story_faellig()
        if faellig is not None:
            story_dialog_starten(faellig, board, board_name)
        durchsage_pruefen(board, kalender)
        # Ein rotes Ausrufezeichen im Prompt, solange eine Kontamination läuft
        warnung = "!" if lage_aktiv() else ""
        # Ab Stufe 2 steht ein Stern am Namen, ab Stufe 3 meldet es sich anders
        stufe = bewusstsein()
        kennung = "MU/TH/UR" if stufe >= 3 else "MUTHUR"
        marke = "*" if stufe == 2 else ""
        roh = eingabe_mit_effekt(
            f"[{board_name}]{warnung} {kennung}{marke}> ").strip()
        # '@m hallo' spricht jemanden gezielt an
        if roh.lower().lstrip("@").strip() in ("reboot", "neustart"):
            reboot(board)
            continue
        if roh.startswith("@"):
            try:
                if ansprechen(roh, board, board_name):
                    continue
            except ValueError as fehler:
                klang("unbekannt", (220, 90))
                entschluesseln(f"FEHLER: {str(fehler).upper()}")
                continue
        # 'ja' und 'nein' gehoeren zur laufenden Rueckfrage, falls eine offen ist
        antwort = antwort_erkennen(roh)
        if antwort:
            offen = frage_offen()
            folge = frage_beantworten(antwort, board)
            if folge == "scan":
                scan(board)
            elif folge == "sitrep":
                sitrep(board, board_name, kalender, notizen)
            elif folge == "map":
                schiffskarte(board)
            elif folge == "radar":
                radar(board)
            elif folge == "home":
                homescreen(board, notizen, kalender, board_name)
            elif folge == "fin":
                finanzansicht(finanzen)
            elif folge == "bh":
                bericht_befehl(board, "faellig")
            if offen:
                alles_speichern(board, notizen, kalender, board_name,
                                finanzen, einkauf)
            continue
        if frage_offen():
            OFFENE_FRAGE["eingaben"] += 1
        if roh.lower() in OSTEREIER:
            klang("geheim")
            entschluesseln(OSTEREIER[roh.lower()])
            ostereier_merken(roh.lower())
            freigabe_melden()
            continue
        if rogue_eingabe(board, roh):
            freigabe_melden()
            continue
        teile = roh.split(maxsplit=1)
        cmd = teile[0].lower() if teile else ""
        if cmd in BEFEHLE:
            bewusstsein_zoegern(board)
        arg = teile[1].strip() if len(teile) > 1 else ""
        try:
            if cmd not in BEFEHLE and roh:
                kurz, art = gruss_antwort(roh)
                if kurz:
                    if gruss_ausgeben(kurz, art, board):
                        alles_speichern(board, notizen, kalender, board_name, finanzen, einkauf)
                        entschluesseln("DATEN GESICHERT. VERBINDUNG WIRD GETRENNT.")
                        klang("aus", warten=True)
                        break
                    continue
            if cmd == "":
                continue
            elif cmd == "s":
                klang("ansicht")
                board.anzeigen()
                heute_iso = date.today().isoformat()
                for t in kalender.am_tag(heute_iso):
                    schreibe(f"{AKZENT}  HEUTE {t.zeitangabe()}  {t.titel}{RESET}\n")
                for n in notizen.angepinnte():
                    schreibe(f"{AKZENT}  * {n.text}{RESET}\n")
                if kalender.am_tag(heute_iso) or notizen.angepinnte():
                    schreibe("\n")
                konzern_meldung(board)
            elif cmd == "scan":
                scan(board)
                speichern(board, board_name)  # die Lage hat sich geändert
                continue
            elif cmd == "map":
                klang("ansicht")
                schiffskarte(board)
                continue
            elif cmd == "sitrep":
                sitrep(board, board_name, kalender, notizen)
                continue
            elif cmd in ("purge", "dekon"):
                massnahme(cmd, board)
                speichern(board, board_name)
                system_speichern()
                continue
            elif cmd == "crew":
                klang("ansicht")
                if arg:
                    name = arg.strip().lower()
                    if name not in CREW:
                        raise ValueError(f"Unbekannte Besatzung '{name}'")
                    personalakte(name)
                    crew_karten(board, name)
                else:
                    crew_liste()
                continue
            elif cmd == "akte":
                klang("ansicht")
                name = arg.strip().lower()
                if name not in CREW:
                    raise ValueError(f"Unbekannte Besatzung '{arg.strip()}'")
                personalakte(name)
                continue
            elif cmd == "wy":
                if arg.strip():
                    klang("umschalten")
                    entschluesseln(wy_schalten(arg))
                    system_speichern()
                    continue
                klang("archiv")
                wy_memo()
                continue
            elif cmd == "freigabe":
                klang("ansicht")
                freigabe_anzeigen()
                continue
            elif cmd == "crt":
                klang("umschalten")
                entschluesseln(crt_schalten(arg))
                system_speichern()
                continue
            elif cmd == "ai":
                klang("umschalten")
                entschluesseln(ai_schalten(arg))
                system_speichern()
                continue
            elif cmd == "schoner":
                klang("umschalten" if arg else "ansicht")
                if arg:
                    entschluesseln(schoner_schalten(arg))
                    system_speichern()
                else:
                    schoner_laufen(f"[{board_name}] MUTHUR> ", "")
                continue
            elif cmd == "f":
                klang("ansicht")
                board.anzeigen(arg.lower())
            elif cmd == "home":
                klang("ansicht")
                homescreen(board, notizen, kalender, board_name, loeschen=True)
                continue
            elif cmd == "heute":
                klang("ansicht")
                tagesuebersicht(kalender, board, notizen)
                continue
            elif cmd == "k":
                klang("ansicht")
                kalender_anzeigen(kalender, board, arg)
                continue
            elif cmd == "ka":
                snapshot = schnappschuss()
                termin = termin_anlegen(kalender, arg)
                undo_stapel.append(snapshot)
                entschluesseln(f"TERMIN #{termin.id} AM {termin.datum} EINGETRAGEN")
                klang("bestaetigt", (880, 60))
            elif cmd == "kl":
                termin_id = int(arg) if arg.isdigit() else int(eingabe_mit_effekt("  TERMIN-ID: "))
                snapshot = schnappschuss()
                termin = kalender.finden(termin_id)
                kalender.termine.remove(termin)
                undo_stapel.append(snapshot)
                entschluesseln(f"TERMIN #{termin_id} GELOESCHT")
                klang("loeschen", (440, 120))
            elif cmd == "r":
                klang("ansicht")
                regeln_anzeigen(kalender)
                continue
            elif cmd == "ra":
                snapshot = schnappschuss()
                regel = regel_anlegen(kalender, arg)
                undo_stapel.append(snapshot)
                entschluesseln(f"REGEL R{regel.id} ANGELEGT: "
                               f"{regel.tage_text()} {regel.zeitangabe()}")
                klang("bestaetigt", (880, 60))
            elif cmd == "rl":
                regel_id = int(arg) if arg.isdigit() else int(eingabe_mit_effekt("  REGEL-ID: "))
                snapshot = schnappschuss()
                kalender.regeln.remove(kalender.regel_finden(regel_id))
                undo_stapel.append(snapshot)
                entschluesseln(f"REGEL R{regel_id} GELOESCHT")
                klang("loeschen", (440, 120))
            elif cmd == "rx":
                snapshot = schnappschuss()
                regel, von, bis = regel_ausnahme(kalender, arg)
                undo_stapel.append(snapshot)
                entschluesseln(f"R{regel.id} PAUSIERT VON {von} BIS {bis}")
                klang("klick", (770, 60))
            elif cmd == "n":
                if not arg:
                    klang("ansicht")
                    notizen_anzeigen(notizen)
                    continue
                snapshot = schnappschuss()
                notiz = notiz_anlegen(notizen, arg)
                undo_stapel.append(snapshot)
                SYSTEM["notizen_gesamt"] = SYSTEM.get("notizen_gesamt", 0) + 1
                entschluesseln(f"NOTIZ #{notiz.id} GESPEICHERT")
                klang("bestaetigt", (880, 60))
                freigabe_melden()
            elif cmd == "nf":
                klang("ansicht")
                notizen_anzeigen(notizen, arg)
                if ai_aktiv() and random.random() < 0.08:
                    rogue_melden(board, 1)   # es liest mit
                continue
            elif cmd == "np":
                notiz_id = int(arg) if arg.isdigit() else int(eingabe_mit_effekt("  NOTIZ-ID: "))
                snapshot = schnappschuss()
                notiz = notizen.finden(notiz_id)
                notiz.angepinnt = not notiz.angepinnt
                undo_stapel.append(snapshot)
                entschluesseln(f"NOTIZ #{notiz_id} "
                               f"{'ANGEPINNT' if notiz.angepinnt else 'LOSGELOEST'}")
                klang("klick", (770, 60))
            elif cmd == "nl":
                notiz_id = int(arg) if arg.isdigit() else int(eingabe_mit_effekt("  NOTIZ-ID: "))
                snapshot = schnappschuss()
                notizen.notizen.remove(notizen.finden(notiz_id))
                undo_stapel.append(snapshot)
                entschluesseln(f"NOTIZ #{notiz_id} GELOESCHT")
                klang("loeschen", (440, 120))
            elif cmd == "a":
                snapshot = schnappschuss()
                if arg:
                    karte, spalte = schnell_karte(board, arg)
                    crew = karte.crew
                else:
                    spalte = eingabe_spalte(board)
                    titel, beschreibung, faellig, prioritaet, crew = eingabe_karte_daten()
                    karte = board.hinzufuegen(spalte, titel, beschreibung, faellig,
                                              prioritaet, crew)
                undo_stapel.append(snapshot)
                wer = f" - {CREW[crew][0]}" if crew in CREW else ""
                entschluesseln(f"EINTRAG #{karte.id} IN {spalte.upper()} ANGELEGT{wer}")
                klang("bestaetigt", (880, 60))
            elif cmd == "v":
                vteile = arg.split()
                if len(vteile) == 2:
                    karten_id = int(vteile[0])
                    ziel = spalte_aus_text(vteile[1])
                else:
                    karten_id = int(arg) if arg.isdigit() else int(eingabe_mit_effekt("  EINTRAGS-ID: "))
                    ziel = eingabe_spalte(board)
                snapshot = schnappschuss()
                board.verschieben(karten_id, ziel)
                undo_stapel.append(snapshot)
                entschluesseln(f"EINTRAG #{karten_id} NACH {ziel.upper()} VERSCHOBEN")
                klang("erledigt" if ziel == "Erledigt" else "verschieben", (990, 60))
                loeschungen = 0
                if ai_aktiv() and random.random() < 0.08:
                    rogue_melden(board, 2)
                if ziel == "Erledigt":
                    SYSTEM["erledigt_gesamt"] = SYSTEM.get("erledigt_gesamt", 0) + 1
                    schreibe(f"{DUNKEL} "
                             f"{fuellen(random.choice(ERLEDIGT_MELDUNGEN), board, id=karten_id)}"
                             f"{RESET}\n")
                    freigabe_melden()
                if ziel == "Erledigt" and not board.offen():
                    klang("erfolg")
                    konfetti()
                    board.anzeigen()
            elif cmd == "l":
                karten_id = int(arg) if arg.isdigit() else int(eingabe_mit_effekt("  EINTRAGS-ID: "))
                snapshot = schnappschuss()
                board.loeschen(karten_id)
                undo_stapel.append(snapshot)
                entschluesseln(random.choice(LOESCH_KOMMENTARE).format(id=karten_id))
                klang("loeschen", (440, 120))
                loeschungen += 1
                if ai_aktiv() and loeschungen >= 5:
                    rogue_stufe3(board)   # viele Löschungen wecken Aufmerksamkeit
                    loeschungen = 0
                elif ai_aktiv() and random.random() < 0.10:
                    rogue_melden(board, 2)
            elif cmd == "u":
                if not undo_stapel:
                    raise ValueError("Nichts zum Rückgängig machen")
                board, notizen, kalender = undo_stapel.pop()
                klang("zurueck", (330, 120))
                entschluesseln("LETZTE AKTION RÜCKGÄNGIG GEMACHT")
            elif cmd == "b":
                if not arg:
                    klang("ansicht")
                    logbuecher_anzeigen(board_name)
                    continue
                klang("archiv")
                if not re.fullmatch(r"\w+", arg):
                    raise ValueError("Name nur mit Buchstaben, Zahlen oder _")
                alles_speichern(board, notizen, kalender, board_name, finanzen, einkauf)
                board_name = arg.lower()
                board = laden(board_name)
                notizen = notizen_laden(board_name)
                kalender = kalender_laden(board_name)
                undo_stapel.clear()
                entschluesseln(f"LOGBUCH '{board_name.upper()}' GEÖFFNET")
                board.anzeigen()
            elif cmd == "e":
                klang("archiv")
                pfad = exportieren(board, board_name)
                entschluesseln(f"EXPORT GESPEICHERT: {pfad.name.upper()}")
            elif cmd == "t":
                klang("umschalten")
                namen = freigebene_themen()
                if AKTIVES_THEMA in namen:
                    naechstes = namen[(namen.index(AKTIVES_THEMA) + 1) % len(namen)]
                else:
                    naechstes = namen[0]
                setze_thema(naechstes)
                schreibe(BG + "\033[2J\033[H")  # Bildschirm mit neuem Hintergrund neu zeichnen
                flimmern()
                board.anzeigen()
                entschluesseln(f"THEMA: {naechstes.upper()}")
                gesperrt = len(THEMEN) - len(namen)
                if gesperrt:
                    schreibe(f"{DUNKEL} {gesperrt} weitere Schemata benötigen "
                             f"eine höhere Freigabe. 'freigabe' zeigt welche.{RESET}\n")
            elif cmd == "h":
                klang("ansicht")
                schreibe(f"{HELL}{HILFE}{RESET}")
                continue
            elif cmd == "klang":
                klang_befehl(arg)
                continue
            elif cmd == "art":
                art_befehl(arg)
                continue
            elif cmd == "radar":
                radar(board)
                continue
            elif cmd == "dialog":
                dialog_befehl(board, board_name, arg)
                continue
            elif cmd == "story":
                story_befehl(board, arg)
                continue
            elif cmd == "bh":
                bericht_befehl(board, arg)
                continue
            elif cmd == "fin":
                klang("ansicht")
                finanzansicht(finanzen, arg)
                continue
            elif cmd in ("fix", "aus", "ein"):
                if cmd == "fix":
                    # Vorzeichen steht beim Betrag: 'fix -450 Miete', 'fix +1050 Lohn'
                    vorzeichen = -1 if not arg.strip().startswith("+") else 1
                    betrag, titel, kategorie = posten_eingabe(arg, vorzeichen)
                    e = finanzen.posten_anlegen("fix", titel, betrag, kategorie,
                                                tag=date.today().day)
                    wort = "FIXKOSTEN" if betrag < 0 else "FESTES EINKOMMEN"
                else:
                    betrag, titel, kategorie = posten_eingabe(
                        arg, -1 if cmd == "aus" else 1)
                    e = finanzen.posten_anlegen("bucht", titel, betrag, kategorie,
                                                datum=date.today().isoformat())
                    wort = "AUSGABE" if betrag < 0 else "EINNAHME"
                klang("bestaetigt", (880, 60))
                entschluesseln(f"{wort} #{e.id}: {geld(e.betrag)} {WAEHRUNG} "
                               f"- {titel.upper()}")
                finanzen_speichern(finanzen)
                continue
            elif cmd == "finl":
                posten_id = int(arg) if arg.strip().lstrip("#").isdigit() \
                    else int(eingabe_mit_effekt("  POSTEN-ID: ").lstrip("#"))
                e = finanzen.posten_finden(posten_id)
                finanzen.posten.remove(e)
                klang("loeschen", (440, 120))
                entschluesseln(f"POSTEN #{posten_id} GELOESCHT")
                finanzen_speichern(finanzen)
                continue
            elif cmd == "ziel":
                meldung = ziel_befehl(finanzen, arg)
                if meldung:
                    entschluesseln(meldung)
                finanzen_speichern(finanzen)
                continue
            elif cmd == "ek":
                if not arg:
                    klang("ansicht")
                    einkauf_anzeigen(einkauf)
                    continue
                e = einkauf_anlegen(einkauf, arg)
                klang("bestaetigt", (880, 60))
                entschluesseln(f"AUF DER LISTE: {e.text.upper()}")
                einkauf_speichern(einkauf)
                continue
            elif cmd == "ekh":
                posten_id = int(arg) if arg.strip().lstrip("#").isdigit() \
                    else int(eingabe_mit_effekt("  POSTEN-ID: ").lstrip("#"))
                e = einkauf.finden(posten_id)
                e.erledigt = not e.erledigt
                klang("klick", (770, 60))
                entschluesseln(f"#{posten_id} {'ABGEHAKT' if e.erledigt else 'WIEDER OFFEN'}")
                einkauf_speichern(einkauf)
                continue
            elif cmd == "ekl":
                posten_id = int(arg) if arg.strip().lstrip("#").isdigit() \
                    else int(eingabe_mit_effekt("  POSTEN-ID: ").lstrip("#"))
                einkauf.posten.remove(einkauf.finden(posten_id))
                klang("loeschen", (440, 120))
                entschluesseln(f"POSTEN #{posten_id} VON DER LISTE")
                einkauf_speichern(einkauf)
                continue
            elif cmd == "ekx":
                weg = [e for e in einkauf.posten if e.erledigt]
                if not weg:
                    raise ValueError("Nichts abgehakt")
                einkauf.posten = einkauf.offen()
                klang("archiv", (770, 80))
                entschluesseln(f"{len(weg)} ABGEHAKTE POSTEN ENTFERNT")
                einkauf_speichern(einkauf)
                continue
            elif cmd in ("ausbuchen", "ab"):
                tage = int(arg) if arg.strip().isdigit() else None
                erledigt = board.spalten["Erledigt"]
                if not erledigt:
                    raise ValueError("In 'Erledigt' liegt nichts")
                womit = (f"Alle {len(erledigt)} erledigten Jobs" if tage is None
                         else f"Erledigte Jobs, laenger als {tage} Tage fertig,")
                schreibe(f"\n{HELL} {womit} ausbuchen.{RESET}\n")
                schreibe(f"{DUNKEL} Sie werden vorher nach sitreps/ archiviert "
                         f"und sind mit 'u' zurueckholbar.{RESET}\n")
                if not frage_ja_nein("  AUSBUCHEN? [J/N] "):
                    funkspruch("Abgebrochen. Das Logbuch bleibt, wie es war.",
                               "muthur", leise=True)
                    schreibe("\n")
                    continue
                snapshot = schnappschuss()
                anzahl, uebrig, pfad = ausbuchen(board, board_name, tage)
                undo_stapel.append(snapshot)
                klang("archiv", (770, 80))
                entschluesseln(f"{anzahl} JOBS AUSGEBUCHT")
                schreibe(f"{DUNKEL} Archiviert: {pfad.name}"
                         f"{f', {uebrig} verbleiben in Erledigt' if uebrig else ''}"
                         f"{RESET}\n")
                funkspruch(random.choice(AUSBUCH_MELDUNGEN), "wy")
                schreibe("\n")
                alles_speichern(board, notizen, kalender, board_name, finanzen, einkauf)
                continue
            elif cmd == "q":
                alles_speichern(board, notizen, kalender, board_name, finanzen, einkauf)
                entschluesseln("DATEN GESICHERT. VERBINDUNG WIRD GETRENNT.")
                klang("aus", warten=True)
                break
            else:
                fehleingaben += 1
                klang("unbekannt", (220, 90))
                entschluesseln("UNBEKANNTER BEFEHL. TIPPE H.")
                if fehleingaben >= 5:
                    funkspruch(FEHLEINGABE_VIELE, "muthur", leise=True)
                    fehleingaben = 0
                else:
                    funkspruch(random.choice(FEHLEINGABEN), "muthur", leise=True)
                continue
            if cmd in ("a", "v", "l", "u", "b", "n", "nl", "np",
                       "ka", "kl", "ra", "rl", "rx"):
                alles_speichern(board, notizen, kalender, board_name, finanzen, einkauf)
        except (ValueError, KeyError) as fehler:
            klang("fehler", (220, 200))
            entschluesseln(f"FEHLER: {str(fehler).upper()}")


if __name__ == "__main__":
    try:
        main()
    except (EOFError, KeyboardInterrupt):
        # Strg-C oder abgeschnittener Eingabestrom: ruhig beenden statt
        # mit einem Fehlerbericht, den niemand lesen will.
        schreibe(f"\n{DUNKEL} Verbindung abgebrochen. "
                 f"Gespeichert wurde bis zur letzten Aktion.{RESET}\n")
        sys.exit(0)
