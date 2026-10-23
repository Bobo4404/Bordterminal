"""Klangbibliothek für das Bordterminal.

Dieses Modul erzeugt alle Geräusche selbst und legt sie als WAV-Dateien ab.
Es braucht nichts ausser der Standardbibliothek, also kein numpy, kein pygame.

Klangliche Richtung: Technik von 1979, nicht von heute. Vorbilder sind die
Nostromo aus Alien, die Discovery aus 2001 und die Sevastopol aus Alien
Isolation. Das heisst in der Praxis:

  - Relais und Magnetschalter statt Pieptoene. Ein Befehl wird angenommen,
    weil ein Kontakt schliesst, nicht weil ein Akkord spielt.
  - Reine, weiche Sinustoene statt Rechteck-Arpeggien. 2001 hat keine
    Melodien, nur einzelne Toene.
  - Alles laeuft am Ende durch 'tonband': Bandbegrenzung bei etwa 4 kHz,
    leichtes Wow und Flutter, Saettigung und ein wenig Bandrauschen.
    Nichts klingt dadurch digital.
  - 50-Hz-Netzbrummen unter den langen Signalen, Motorlaufen fuer Laufwerke.
  - Die Sirene ist tief, langsam und durch einen Hornkoerper gefiltert.

Von Hand neu erzeugen (zum Beispiel nach Änderungen an den Rezepten):

    py klaenge.py

Das überschreibt den Ordner "klaenge" neben dieser Datei.
"""

import math
import random
import struct
import wave
from pathlib import Path

ABTASTRATE = 22050          # reicht für diese Bandbreite und spart Platz
ORDNER = Path(__file__).resolve().parent / "klaenge"


# ---------------------------------------------------------------- Bausteine

def _laenge(dauer: float) -> int:
    return max(1, int(ABTASTRATE * dauer))


def _wert(parameter, t: float, dauer: float):
    """Erlaubt feste Zahlen und Funktionen von t (Sekunden) oder vom Fortschritt."""
    if callable(parameter):
        return parameter(t)
    if isinstance(parameter, (tuple, list)) and len(parameter) == 2:
        von, bis = parameter
        anteil = min(1.0, t / dauer) if dauer else 0.0
        return von * (bis / von) ** anteil if von > 0 and bis > 0 else von + (bis - von) * anteil
    return parameter


def osz(dauer: float, frequenz, form: str = "sin", pegel: float = 1.0) -> list:
    """Ein Oszillator. frequenz darf eine Zahl, ein (von, bis)-Paar oder eine Funktion sein."""
    n = _laenge(dauer)
    ausgabe = [0.0] * n
    phase = 0.0
    schritt = 2.0 * math.pi / ABTASTRATE
    for i in range(n):
        t = i / ABTASTRATE
        phase += schritt * _wert(frequenz, t, dauer)
        if form == "sin":
            v = math.sin(phase)
        elif form == "sqr":
            v = 1.0 if math.sin(phase) >= 0.0 else -1.0
        elif form == "saw":
            v = 2.0 * ((phase / (2.0 * math.pi)) % 1.0) - 1.0
        elif form == "tri":
            anteil = (phase / (2.0 * math.pi)) % 1.0
            v = 4.0 * abs(anteil - 0.5) - 1.0
        else:
            raise ValueError("unbekannte Wellenform: " + form)
        ausgabe[i] = v * pegel
    return ausgabe


def rauschen(dauer: float, pegel: float = 1.0) -> list:
    return [random.uniform(-1.0, 1.0) * pegel for _ in range(_laenge(dauer))]


def tiefpass(signal: list, grenze) -> list:
    """Einpoliges Tiefpassfilter. grenze darf sich über die Zeit ändern."""
    ausgabe = []
    y = 0.0
    dauer = len(signal) / ABTASTRATE
    fest = not callable(grenze) and not isinstance(grenze, (tuple, list))
    if fest:
        a = math.exp(-2.0 * math.pi * max(20.0, min(ABTASTRATE / 2.5, grenze)) / ABTASTRATE)
    for i, x in enumerate(signal):
        if not fest:
            fc = max(20.0, min(ABTASTRATE / 2.5, _wert(grenze, i / ABTASTRATE, dauer)))
            a = math.exp(-2.0 * math.pi * fc / ABTASTRATE)
        y = (1.0 - a) * x + a * y
        ausgabe.append(y)
    return ausgabe


def hochpass(signal: list, grenze) -> list:
    tief = tiefpass(signal, grenze)
    return [x - y for x, y in zip(signal, tief)]


def resonanz(signal: list, grenze, guete: float = 4.0) -> list:
    """Schmalbandfilter (Chamberlin). Gut für Hoerner, Pfeifen und Sirenen."""
    ausgabe = []
    tief = band = 0.0
    dauer = len(signal) / ABTASTRATE
    dq = 1.0 / max(0.5, guete)
    for i, x in enumerate(signal):
        fc = max(20.0, min(ABTASTRATE / 4.2, _wert(grenze, i / ABTASTRATE, dauer)))
        f = 2.0 * math.sin(math.pi * fc / ABTASTRATE)
        tief += f * band
        hoch = x - tief - dq * band
        band += f * hoch
        ausgabe.append(band)
    return ausgabe


def huelle(signal: list, anstieg: float = 0.004, abfall: float = None,
           halten: float = 0.0, kurve: float = 2.2) -> list:
    """Legt eine Attack/Hold/Decay-Hülle über das Signal."""
    n = len(signal)
    dauer = n / ABTASTRATE
    if abfall is None:
        abfall = max(0.01, dauer - anstieg - halten)
    a = max(1, _laenge(anstieg))
    h = _laenge(halten) if halten else 0
    ausgabe = [0.0] * n
    for i, x in enumerate(signal):
        if i < a:
            g = i / a
        elif i < a + h:
            g = 1.0
        else:
            rest = (i - a - h) / max(1, _laenge(abfall))
            g = max(0.0, 1.0 - rest) ** kurve
        ausgabe[i] = x * g
    return ausgabe


def tremolo(signal: list, frequenz: float, tiefe: float = 0.5) -> list:
    return [x * (1.0 - tiefe + tiefe * (0.5 + 0.5 * math.sin(2.0 * math.pi * frequenz * i / ABTASTRATE)))
            for i, x in enumerate(signal)]


def mischen(ziel: list, quelle: list, start: float = 0.0, pegel: float = 1.0) -> list:
    i0 = _laenge(start) if start else 0
    fehlt = i0 + len(quelle) - len(ziel)
    if fehlt > 0:
        ziel.extend([0.0] * fehlt)
    for i, v in enumerate(quelle):
        ziel[i0 + i] += v * pegel
    return ziel


def raum(signal: list, abstaende=(0.031, 0.047, 0.071), daempfung: float = 0.33,
         schwanz: float = None) -> list:
    """Billiger, aber wirksamer Nachklang. Grosse Abstaende = grosser Maschinenraum."""
    ausgabe = list(signal) + [0.0] * _laenge(schwanz if schwanz is not None
                                             else max(abstaende) * 2.6)
    for stufe, abstand in enumerate(abstaende):
        versatz = _laenge(abstand)
        pegel = daempfung ** (stufe + 1)
        for i, v in enumerate(signal):
            if i + versatz < len(ausgabe):
                ausgabe[i + versatz] += v * pegel
    return ausgabe


# -------------------------------------------------- Analoge Eigenheiten

def flattern(signal: list, tiefe: float = 0.0035, rate: float = 1.1) -> list:
    """Wow und Flutter. Der Leseort wandert leicht, wie bei einem Tonband."""
    n = len(signal)
    if n < 8:
        return list(signal)
    ausgabe = []
    ort = 0.0
    phase = random.random() * 6.283
    for _ in range(n):
        t = len(ausgabe) / ABTASTRATE
        drift = (1.0
                 + tiefe * math.sin(2.0 * math.pi * rate * t + phase)
                 + tiefe * 0.35 * math.sin(2.0 * math.pi * rate * 6.3 * t))
        ort += drift
        if ort >= n - 2:
            break
        i0 = int(ort)
        rest = ort - i0
        ausgabe.append(signal[i0] * (1.0 - rest) + signal[i0 + 1] * rest)
    return ausgabe


def tonband(signal: list, grenze: float = 4200.0, rauschpegel: float = 0.012,
            saettigung: float = 1.7, flutter: bool = True) -> list:
    """Letzte Stufe für jeden Klang: Band, Bandbreite, Saettigung, Bandrauschen.

    Das ist der Griff, der alles nach 1979 klingen laesst. Die Bandbegrenzung
    nimmt den digitalen Glanz, die Saettigung rundet die Spitzen, und das
    Rauschen liegt nur dort, wo auch Signal ist, damit kurze Klaenge nicht
    mit einem Zischer anfangen.
    """
    s = flattern(signal) if flutter else list(signal)
    s = tiefpass(s, grenze)
    s = hochpass(s, 38.0)                    # kein Tiefbassmatsch
    norm = math.tanh(saettigung)
    s = [math.tanh(v * saettigung) / norm for v in s]
    if rauschpegel:
        kontur = tiefpass([abs(v) for v in s], 14.0)
        hoechst = max(kontur) or 1.0
        s = [v + random.uniform(-1.0, 1.0) * rauschpegel * (0.35 + 0.65 * k / hoechst)
             for v, k in zip(s, kontur)]
    return s


def netz(dauer: float, pegel: float = 0.25) -> list:
    """50-Hz-Netzbrummen mit Oberwellen. Liegt unter allem, was laenger dauert."""
    s = osz(dauer, 50.0, "sin", pegel)
    for oberwelle, anteil in ((100.0, 0.45), (150.0, 0.22), (250.0, 0.08)):
        mischen(s, osz(dauer, oberwelle, "sin", pegel * anteil))
    return s


def motor(dauer: float, frequenz=72.0, pegel: float = 0.5) -> list:
    """Laufwerk oder Servo: ein brummiger Saegezahn mit Luft darueber."""
    s = osz(dauer, frequenz, "saw", pegel)
    mischen(s, osz(dauer, lambda t: _wert(frequenz, t, dauer) * 2.02, "sin", pegel * 0.3))
    s = tiefpass(s, 900.0)
    luft = tiefpass(rauschen(dauer, pegel * 0.5), 1600.0)
    mischen(s, luft, 0.0, 0.6)
    return s


def relais(hart: float = 1.0, tief: float = 130.0, dauer: float = 0.055) -> list:
    """Ein Magnetschalter schliesst: trockener Schlag plus kurzes Nachschwingen."""
    s = huelle(tiefpass(rauschen(dauer * 0.5), 2600.0 * hart),
               anstieg=0.0004, abfall=dauer * 0.45, kurve=3.2)
    koerper = huelle(osz(dauer, tief, "sin", 0.9),
                     anstieg=0.0006, abfall=dauer * 0.9, kurve=2.8)
    mischen(s, koerper, 0.0, 0.85)
    return s


def klonk(frequenz: float = 180.0, dauer: float = 0.3, pegel: float = 0.9) -> list:
    """Metall auf Metall: ein Schlag mit zwei unharmonischen Teiltoenen."""
    s = [0.0] * _laenge(dauer)
    for anteil, staerke, laenge in ((1.0, 1.0, 1.0), (2.37, 0.4, 0.6), (3.91, 0.18, 0.35)):
        mischen(s, huelle(osz(dauer * laenge, frequenz * anteil, "sin", pegel * staerke),
                          anstieg=0.0008, abfall=dauer * laenge * 0.95, kurve=2.4))
    mischen(s, huelle(hochpass(rauschen(0.02), 1200.0), anstieg=0.0004, abfall=0.019), 0.0, 0.35)
    return s


def horn(signal: list) -> list:
    """Hornkoerper einer Schiffssirene: drei Resonanzen uebereinander."""
    s = [0.0] * len(signal)
    for frequenz, guete, pegel in ((236.0, 7.0, 1.0), (470.0, 5.0, 0.55), (705.0, 4.0, 0.22)):
        mischen(s, resonanz(signal, frequenz, guete), 0.0, pegel)
    return [a * 0.55 + b * 0.45 for a, b in zip(s, tiefpass(signal, 1400.0))]


# ---------------------------------------------------------------- Ausgabe

def schreiben(name: str, signal: list, pegel: float = 0.72) -> Path:
    """Normiert, blendet die Ränder weich und schreibt eine 16-Bit-Mono-WAV."""
    ORDNER.mkdir(parents=True, exist_ok=True)
    hoechst = max((abs(v) for v in signal), default=0.0) or 1.0
    faktor = pegel / hoechst
    # Einblenden nur so kurz, dass der Anschlag eines Klicks erhalten bleibt
    ein = min(_laenge(0.0008), len(signal) // 4)
    aus = min(_laenge(0.004), len(signal) // 2)
    rahmen = bytearray()
    for i, v in enumerate(signal):
        g = 1.0
        if i < ein:
            g = i / ein
        elif i >= len(signal) - aus:
            g = (len(signal) - i) / aus
        probe = v * faktor * g
        rahmen += struct.pack("<h", max(-32767, min(32767, int(probe * 32767))))
    pfad = ORDNER / (name + ".wav")
    with wave.open(str(pfad), "wb") as datei:
        datei.setnchannels(1)
        datei.setsampwidth(2)
        datei.setframerate(ABTASTRATE)
        datei.writeframes(bytes(rahmen))
    return pfad


# ---------------------------------------------------------------- Rezepte
# Jede Funktion gibt ein fertiges Signal zurück. Der Name ist der Dateiname.

# --- Betrieb ---------------------------------------------------------------

def _boot():
    """Nostromo faehrt hoch: Schuetz, Netz, Laufwerk, Speicherbaenke, Freigabe."""
    s = [0.0] * _laenge(2.6)
    # Der Hauptschuetz schliesst
    mischen(s, relais(1.0, 90.0, 0.12), 0.0, 1.0)
    mischen(s, klonk(104.0, 0.45, 0.7), 0.01, 0.8)
    # Netz kommt, baut sich auf
    mischen(s, huelle(netz(2.3, 0.3), anstieg=0.55, abfall=1.7, kurve=1.2), 0.08, 1.0)
    # Bandlaufwerk laeuft an und haelt die Drehzahl
    lauf = motor(1.9, lambda t: 26.0 + 58.0 * min(1.0, t / 0.9), 0.5)
    mischen(s, huelle(lauf, anstieg=0.35, halten=1.1, abfall=0.45, kurve=1.1), 0.12, 0.8)
    # Speicherbaenke melden sich: Relais, keine Melodie
    for i in range(5):
        mischen(s, relais(0.7, 150.0 + i * 22.0, 0.05), 0.62 + i * 0.17, 0.5)
    # Zugriff: ein einzelner reiner Ton, wie auf der Discovery
    freigabe = huelle(osz(0.75, 528.0, "sin", 0.85), anstieg=0.02, halten=0.22, abfall=0.5, kurve=1.7)
    mischen(s, raum(freigabe, (0.043, 0.067), 0.26), 1.62, 0.95)
    return tonband(s, 3900.0, 0.016)


def _aus():
    """Abschalten: Schuetz faellt ab, Netz und Laufwerk laufen aus."""
    s = [0.0] * _laenge(1.8)
    mischen(s, relais(0.8, 78.0, 0.1), 0.0, 0.9)
    auslauf = motor(1.2, lambda t: 84.0 * math.exp(-1.9 * t) + 12.0, 0.55)
    mischen(s, huelle(auslauf, anstieg=0.01, abfall=1.15, kurve=1.5), 0.02, 1.0)
    mischen(s, huelle(netz(1.0, 0.28), anstieg=0.01, abfall=0.95, kurve=1.9), 0.0, 0.9)
    # Die Hochspannung entlaedt sich: ein fallender Pfeifton
    pfeifen = osz(0.85, lambda t: 1180.0 * math.exp(-3.1 * t) + 70.0, "tri", 0.4)
    mischen(s, tiefpass(huelle(pfeifen, anstieg=0.008, abfall=0.82, kurve=1.6),
                        lambda t: 2400.0 * math.exp(-2.4 * t) + 140.0), 0.03, 0.8)
    mischen(s, klonk(72.0, 0.4, 0.5), 1.18, 0.6)
    return tonband(s, 3600.0, 0.014)


def _degauss():
    """Entmagnetisieren der Bildroehre: tiefes Brummen mit schnellem Flattern."""
    s = [0.0] * _laenge(0.55)
    schlag = huelle(osz(0.42, (118.0, 52.0), "sin", 1.0), anstieg=0.001, abfall=0.41, kurve=2.4)
    mischen(s, schlag, 0.0, 1.0)
    mischen(s, huelle(tiefpass(rauschen(0.07), 700.0), anstieg=0.001, abfall=0.068), 0.0, 0.5)
    brummen = huelle(netz(0.45, 0.6), anstieg=0.008, halten=0.08, abfall=0.35, kurve=1.5)
    mischen(s, tremolo(brummen, 46.0, 0.7), 0.01, 0.9)
    # Eine Mittenlage dazu, damit das Brummen auch auf kleinen Lautsprechern traegt
    mitte = huelle(osz(0.3, (360.0, 190.0), "tri", 0.3), anstieg=0.002, abfall=0.29, kurve=2.2)
    mischen(s, mitte, 0.0, 0.55)
    return tonband(s, 2600.0, 0.01, flutter=False)


# --- Eingabe ---------------------------------------------------------------

def _taste():
    """Mechanische Taste: trocken, dumpf, kein Ton. Sehr leise."""
    s = huelle(tiefpass(hochpass(rauschen(0.018), 700.0), 3200.0),
               anstieg=0.0004, abfall=0.016, kurve=3.4)
    mischen(s, huelle(osz(0.022, 255.0, "sin", 0.55), anstieg=0.0005, abfall=0.021, kurve=3.0), 0.0, 0.7)
    return tonband(s, 3400.0, 0.0, flutter=False)


def _klick():
    """Kippschalter: hin und zurueck, zwei Kontakte."""
    s = [0.0] * _laenge(0.14)
    mischen(s, relais(0.9, 210.0, 0.045), 0.0, 1.0)
    mischen(s, relais(0.6, 165.0, 0.04), 0.052, 0.55)
    return tonband(s, 3800.0, 0.006, flutter=False)


def _bestaetigt():
    """Angenommen: ein Kontakt schliesst, dann ein kurzer reiner Ton."""
    s = [0.0] * _laenge(0.3)
    mischen(s, relais(0.85, 190.0, 0.05), 0.0, 1.0)
    ton = huelle(osz(0.2, 704.0, "sin", 0.8), anstieg=0.006, halten=0.06, abfall=0.13, kurve=1.8)
    mischen(s, ton, 0.045, 0.85)
    return tonband(s, 3900.0, 0.008)


def _loeschen():
    """Geloescht: Kontakt faellt ab, der Ton geht nach unten."""
    s = [0.0] * _laenge(0.34)
    mischen(s, relais(0.7, 140.0, 0.06), 0.0, 1.0)
    ton = huelle(osz(0.24, (470.0, 250.0), "sin", 0.75), anstieg=0.006, halten=0.04, abfall=0.19, kurve=1.7)
    mischen(s, ton, 0.05, 0.8)
    return tonband(s, 3400.0, 0.008)


def _verschieben():
    """Servo faehrt kurz, dann rastet es ein."""
    s = [0.0] * _laenge(0.3)
    lauf = motor(0.17, lambda t: 96.0 + 150.0 * t / 0.17, 0.5)
    mischen(s, huelle(lauf, anstieg=0.012, halten=0.1, abfall=0.05, kurve=1.3), 0.0, 1.0)
    mischen(s, relais(0.8, 230.0, 0.05), 0.165, 0.8)
    return tonband(s, 3600.0, 0.008)


def _erledigt():
    """Wie eine Speicherstation: schwerer Riegel, Laufwerk, ein Quittungston."""
    s = [0.0] * _laenge(1.15)
    mischen(s, klonk(126.0, 0.5, 1.0), 0.0, 1.0)
    mischen(s, relais(1.0, 96.0, 0.09), 0.01, 0.7)
    lauf = motor(0.5, lambda t: 64.0 + 26.0 * math.sin(2 * math.pi * 2.4 * t), 0.45)
    mischen(s, huelle(lauf, anstieg=0.05, halten=0.3, abfall=0.15, kurve=1.2), 0.1, 0.65)
    quittung = huelle(osz(0.5, 528.0, "sin", 0.8), anstieg=0.01, halten=0.14, abfall=0.34, kurve=1.7)
    mischen(s, quittung, 0.58, 0.9)
    return tonband(raum(s, (0.037, 0.061), 0.24), 3800.0, 0.014)


def _fehler():
    """Relaissummer: trocken, tief, unangenehm. Kein digitaler Buzzer."""
    s = [0.0] * _laenge(0.5)
    traeger = osz(0.4, 103.0, "sqr", 0.9)
    prellen = [v * (0.6 + 0.4 * (1.0 if math.sin(2 * math.pi * 31.0 * i / ABTASTRATE) > 0 else -1.0))
               for i, v in enumerate(traeger)]
    gefiltert = resonanz(prellen, 420.0, 2.4)
    mischen(s, huelle(gefiltert, anstieg=0.002, halten=0.26, abfall=0.14, kurve=1.3), 0.0, 1.0)
    mischen(s, huelle(tiefpass(rauschen(0.08), 500.0), anstieg=0.001, abfall=0.078), 0.0, 0.3)
    return tonband(s, 2800.0, 0.012, flutter=False)


def _unbekannt():
    """Nicht verstanden: ein einzelner dumpfer Schlag, sonst nichts."""
    s = [0.0] * _laenge(0.3)
    mischen(s, klonk(118.0, 0.26, 0.8), 0.0, 1.0)
    mischen(s, huelle(resonanz(rauschen(0.07), 430.0, 2.0), anstieg=0.001, abfall=0.068), 0.0, 0.55)
    return tonband(s, 2600.0, 0.01, flutter=False)


# --- Ansicht und Mechanik --------------------------------------------------

def _ansicht():
    """Bild wird neu geschrieben: ein kurzer elektrostatischer Hauch. Leise."""
    s = [0.0] * _laenge(0.13)
    wisch = resonanz(rauschen(0.09), lambda t: 480.0 + 1250.0 * t / 0.09, 1.6)
    mischen(s, huelle(wisch, anstieg=0.004, abfall=0.085, kurve=1.8), 0.0, 1.0)
    mischen(s, huelle(netz(0.1, 0.5), anstieg=0.006, abfall=0.09, kurve=1.6), 0.0, 0.45)
    return tonband(s, 2800.0, 0.008, flutter=False)


def _umschalten():
    """Ein richtiger Schalter mit Rastung, fuer crt, ai, schoner, Thema."""
    s = [0.0] * _laenge(0.26)
    mischen(s, relais(1.0, 118.0, 0.08), 0.0, 1.0)
    mischen(s, klonk(205.0, 0.16, 0.5), 0.012, 0.6)
    mischen(s, relais(0.5, 260.0, 0.035), 0.085, 0.4)
    return tonband(s, 3600.0, 0.008, flutter=False)


def _zurueck():
    """Band laeuft zurueck: Spulengeraeusch, dann steht es."""
    s = [0.0] * _laenge(0.65)
    spulen = motor(0.48, lambda t: 300.0 - 215.0 * t / 0.48, 0.5)
    mischen(s, huelle(spulen, anstieg=0.02, halten=0.3, abfall=0.14, kurve=1.3), 0.0, 1.0)
    band = resonanz(rauschen(0.48), lambda t: 2300.0 - 1500.0 * t / 0.48, 1.2)
    mischen(s, huelle(band, anstieg=0.02, abfall=0.45, kurve=1.4), 0.0, 0.4)
    mischen(s, relais(0.7, 150.0, 0.06), 0.47, 0.7)
    return tonband(s, 3400.0, 0.016)


def _archiv():
    """Bandlaufwerk sucht und schreibt: Anlauf, Lauf, Einrasten."""
    s = [0.0] * _laenge(0.95)
    mischen(s, relais(0.8, 112.0, 0.07), 0.0, 0.9)
    lauf = motor(0.7, lambda t: 58.0 + 34.0 * (0.5 - 0.5 * math.cos(2 * math.pi * 1.6 * t)), 0.5)
    mischen(s, huelle(lauf, anstieg=0.08, halten=0.45, abfall=0.17, kurve=1.2), 0.05, 1.0)
    for i in range(3):
        mischen(s, relais(0.6, 190.0, 0.04), 0.2 + i * 0.17, 0.35)
    mischen(s, klonk(142.0, 0.3, 0.6), 0.76, 0.7)
    return tonband(s, 3600.0, 0.016)


def _geheim():
    """Etwas, das nicht im Handbuch steht: zwei weiche Toene in grossem Raum."""
    s = [0.0] * _laenge(1.3)
    for i, f in enumerate((349.0, 466.0)):
        ton = huelle(osz(0.7, f, "sin", 0.7), anstieg=0.05, halten=0.12, abfall=0.5, kurve=1.6)
        mischen(s, ton, i * 0.26, 0.85)
    mischen(s, huelle(netz(0.9, 0.3), anstieg=0.3, abfall=0.55, kurve=1.4), 0.1, 0.6)
    return tonband(raum(s, (0.071, 0.113, 0.157), 0.34), 3200.0, 0.014)


def _muthur():
    """MU/TH/UR meldet sich: zwei reine Toene, ruhig und ohne Eile."""
    s = [0.0] * _laenge(1.0)
    for i, f in enumerate((396.0, 594.0)):
        ton = huelle(osz(0.55, f, "sin", 0.75), anstieg=0.025, halten=0.14, abfall=0.37, kurve=1.7)
        mischen(s, ton, i * 0.22, 0.9)
    return tonband(raum(s, (0.047, 0.073), 0.26), 3800.0, 0.012)


# --- Diagnose --------------------------------------------------------------

def _scan():
    """Rumpfabtastung: dunkler Sweep, Laufwerk, dazu gedaempfte Pings."""
    s = [0.0] * _laenge(1.5)
    sweep = resonanz(rauschen(1.15), lambda t: 180.0 * math.exp(1.75 * t), 5.0)
    mischen(s, huelle(sweep, anstieg=0.07, abfall=1.05, kurve=1.2), 0.0, 1.0)
    lauf = motor(1.2, 68.0, 0.4)
    mischen(s, huelle(lauf, anstieg=0.12, halten=0.75, abfall=0.3, kurve=1.2), 0.0, 0.5)
    for i in range(4):
        ping = huelle(osz(0.2, 840.0 + i * 70.0, "sin", 0.45), anstieg=0.004, abfall=0.19, kurve=2.4)
        mischen(s, tiefpass(ping, 1900.0), 0.14 + i * 0.27, 0.6)
    return tonband(s, 3400.0, 0.018)


def _ping():
    """Bewegungsmelder: ein gedaempfter Ping mit kurzem Nachschlag."""
    s = huelle(osz(0.36, 896.0, "sin", 0.75), anstieg=0.003, abfall=0.34, kurve=2.5)
    mischen(s, huelle(osz(0.12, 1792.0, "sin", 0.12), anstieg=0.003, abfall=0.115), 0.0, 1.0)
    return tonband(raum(tiefpass(s, 2100.0), (0.039, 0.061), 0.32), 3000.0, 0.012)


def _ok():
    """Im gruenen Bereich: ein einzelner weicher Ton, leicht schwebend."""
    s = huelle(osz(0.42, lambda t: 466.0 * (1.0 + 0.006 * math.sin(2 * math.pi * 5.5 * t)),
                   "sin", 0.8), anstieg=0.012, halten=0.13, abfall=0.27, kurve=1.7)
    return tonband(raum(s, (0.041, 0.063), 0.22), 3600.0, 0.01)


def _bericht():
    """Zeilendrucker: Typenhaemmer, dann der Wagen laeuft zurueck."""
    s = [0.0] * _laenge(0.95)
    zeit = 0.0
    while zeit < 0.6:
        schlag = huelle(resonanz(rauschen(0.016), random.uniform(620.0, 1150.0), 2.6),
                        anstieg=0.0005, abfall=0.015, kurve=3.0)
        mischen(s, schlag, zeit, random.uniform(0.6, 1.0))
        mischen(s, huelle(osz(0.02, random.uniform(150.0, 220.0), "sin", 0.4),
                          anstieg=0.0005, abfall=0.019), zeit, 0.5)
        zeit += random.uniform(0.022, 0.038)
    wagen = motor(0.2, lambda t: 190.0 - 110.0 * t / 0.2, 0.45)
    mischen(s, huelle(wagen, anstieg=0.01, halten=0.12, abfall=0.07, kurve=1.3), 0.63, 0.8)
    mischen(s, relais(0.8, 160.0, 0.06), 0.83, 0.7)
    return tonband(s, 3300.0, 0.016, flutter=False)


# --- Alarm -----------------------------------------------------------------

def _alarm():
    """Schiffssirene: tief, langsam, durch einen Hornkoerper. Zwei Heuler."""
    s = [0.0] * _laenge(2.0)
    for runde in range(2):
        rohton = [0.0] * _laenge(0.85)
        for verstimmung in (1.0, 1.004, 0.994):
            stimme = osz(0.85, lambda t, v=verstimmung: (176.0 + 96.0 *
                         (0.5 - 0.5 * math.cos(2.0 * math.pi * 1.15 * t))) * v, "saw", 0.4)
            mischen(rohton, stimme)
        gehorn = horn(rohton)
        mischen(gehorn, tiefpass(rauschen(0.85, 0.18), 700.0), 0.0, 0.5)
        mischen(s, huelle(gehorn, anstieg=0.045, halten=0.6, abfall=0.2, kurve=1.2),
                runde * 0.93, 1.0)
    mischen(s, huelle(netz(1.9, 0.22), anstieg=0.1, abfall=1.6, kurve=1.3), 0.0, 0.7)
    return tonband(raum(s, (0.083, 0.127, 0.179), 0.3), 3000.0, 0.018)


def _alarm_puls():
    """Ein einzelner Heuler derselben Sirene, fuer das Blinken in der Karte."""
    s = [0.0] * _laenge(0.46)
    rohton = [0.0] * _laenge(0.38)
    for verstimmung in (1.0, 1.005):
        mischen(rohton, osz(0.38, (178.0, 268.0), "saw", 0.45 * verstimmung))
    mischen(s, huelle(horn(rohton), anstieg=0.025, halten=0.22, abfall=0.13, kurve=1.2), 0.0, 1.0)
    return tonband(raum(s, (0.067, 0.101), 0.26), 3000.0, 0.014)


def _warnung():
    """Ferne Mahnung: zwei tiefe Pulse, stark gedaempft."""
    s = [0.0] * _laenge(0.85)
    for i, f in enumerate((196.0, 147.0)):
        puls = huelle(osz(0.28, f, "saw", 0.7), anstieg=0.012, halten=0.1, abfall=0.16, kurve=1.4)
        mischen(s, tiefpass(puls, 950.0), i * 0.34, 1.0)
    mischen(s, huelle(netz(0.7, 0.2), anstieg=0.05, abfall=0.62, kurve=1.4), 0.0, 0.6)
    return tonband(raum(s, (0.073, 0.109), 0.24), 2400.0, 0.014)


def _purge():
    """Schott auf, Druck raus: Klang am Riegel, dann fallendes Rauschen."""
    s = [0.0] * _laenge(0.55)
    mischen(s, klonk(148.0, 0.2, 0.7), 0.0, 0.8)
    zischen = resonanz(rauschen(0.45), lambda t: 1450.0 * math.exp(-4.2 * t) + 150.0, 1.0)
    mischen(s, huelle(zischen, anstieg=0.006, halten=0.06, abfall=0.37, kurve=1.4), 0.015, 1.0)
    mischen(s, huelle(osz(0.22, (130.0, 48.0), "sin", 0.6), anstieg=0.003, abfall=0.21), 0.01, 0.6)
    return tonband(s, 2500.0, 0.016, flutter=False)


def _dekon():
    """Ventil oeffnet, Nebel stroemt, UV-Zyklus pulst darunter."""
    s = [0.0] * _laenge(0.5)
    mischen(s, relais(0.8, 170.0, 0.05), 0.0, 0.8)
    nebel = resonanz(rauschen(0.34), 980.0, 0.9)
    mischen(s, huelle(nebel, anstieg=0.012, halten=0.1, abfall=0.22, kurve=1.5), 0.03, 0.9)
    uv = tremolo(osz(0.4, 232.0, "saw", 0.45), 23.0, 0.75)
    mischen(s, tiefpass(huelle(uv, anstieg=0.02, halten=0.16, abfall=0.21), 1300.0), 0.05, 0.8)
    return tonband(s, 2300.0, 0.016, flutter=False)


def _erfolg():
    """Lage bereinigt: Riegel faellt, dazu zwei ruhige Toene in der Quinte."""
    s = [0.0] * _laenge(1.3)
    mischen(s, relais(0.9, 104.0, 0.09), 0.0, 0.8)
    for i, f in enumerate((349.0, 523.0)):
        ton = huelle(osz(0.75, f, "sin", 0.75), anstieg=0.02, halten=0.18, abfall=0.53, kurve=1.6)
        mischen(s, ton, 0.1 + i * 0.2, 0.9)
    return tonband(raum(s, (0.053, 0.079, 0.113), 0.3), 3600.0, 0.014)


def _freigabe():
    """Ausweisleser: Karte rastet ein, drei gleichmaessige Toene bestaetigen."""
    s = [0.0] * _laenge(1.7)
    mischen(s, klonk(136.0, 0.26, 0.7), 0.0, 0.8)
    mischen(s, relais(0.7, 180.0, 0.05), 0.14, 0.5)
    for i, f in enumerate((392.0, 523.0, 659.0)):
        ton = huelle(osz(0.6, f, "sin", 0.75), anstieg=0.016, halten=0.16, abfall=0.42, kurve=1.6)
        mischen(s, ton, 0.3 + i * 0.28, 0.9)
    return tonband(raum(s, (0.049, 0.077, 0.109), 0.3), 3700.0, 0.014)


def _rogue():
    """Wenn das Terminal eigene Plaene hat: tiefes Schweben, kein Wort dazu."""
    s = [0.0] * _laenge(2.2)
    for f in (41.2, 43.6, 61.7):
        drohne = osz(2.0, lambda t, g=f: g * (1.0 + 0.003 * math.sin(2 * math.pi * 0.5 * t)),
                     "saw", 0.4)
        mischen(s, tiefpass(huelle(drohne, anstieg=0.5, halten=0.8, abfall=0.7, kurve=1.2), 480.0))
    mischen(s, huelle(netz(1.8, 0.3), anstieg=0.6, abfall=1.1, kurve=1.3), 0.1, 0.8)
    schwebung = huelle(osz(1.5, 587.0, "sin", 0.1), anstieg=0.7, abfall=0.8, kurve=1.5)
    mischen(s, tremolo(schwebung, 2.3, 0.85), 0.35, 0.8)
    return tonband(raum(s, (0.097, 0.149), 0.3), 2600.0, 0.018)


REZEPTE = {
    # Betrieb
    "boot": (_boot, 0.74),
    "aus": (_aus, 0.70),
    "degauss": (_degauss, 0.64),
    # Eingabe
    "taste": (_taste, 0.13),
    "klick": (_klick, 0.40),
    "bestaetigt": (_bestaetigt, 0.54),
    "loeschen": (_loeschen, 0.52),
    "verschieben": (_verschieben, 0.52),
    "erledigt": (_erledigt, 0.68),
    "fehler": (_fehler, 0.62),
    "unbekannt": (_unbekannt, 0.52),
    # Ansicht und Mechanik
    "ansicht": (_ansicht, 0.26),
    "umschalten": (_umschalten, 0.48),
    "zurueck": (_zurueck, 0.52),
    "archiv": (_archiv, 0.56),
    "geheim": (_geheim, 0.60),
    "muthur": (_muthur, 0.56),
    # Diagnose
    "scan": (_scan, 0.62),
    "ping": (_ping, 0.48),
    "ok": (_ok, 0.52),
    "bericht": (_bericht, 0.52),
    # Alarm
    "alarm": (_alarm, 0.84),
    "alarm_puls": (_alarm_puls, 0.70),
    "warnung": (_warnung, 0.60),
    "purge": (_purge, 0.60),
    "dekon": (_dekon, 0.58),
    "erfolg": (_erfolg, 0.66),
    # Konzern
    "freigabe": (_freigabe, 0.70),
    "rogue": (_rogue, 0.76),
}


def fehlende() -> list:
    """Namen der Klaenge, die noch nicht als Datei vorliegen."""
    return [name for name in REZEPTE if not (ORDNER / (name + ".wav")).exists()]


def bauen(namen=None, melden=None) -> list:
    """Erzeugt die Klaenge. melden(name, nummer, gesamt) wird je Datei aufgerufen."""
    namen = list(namen if namen is not None else REZEPTE)
    fertig = []
    for i, name in enumerate(namen, 1):
        random.seed(hash(name) & 0xFFFF)   # gleiches Rezept, gleiches Ergebnis
        rezept, pegel = REZEPTE[name]
        if melden:
            melden(name, i, len(namen))
        fertig.append(schreiben(name, rezept(), pegel))
    return fertig


if __name__ == "__main__":
    def _melden(name, i, gesamt):
        print(f"[{i:2d}/{gesamt}] {name}")

    dateien = bauen(melden=_melden)
    gesamt = sum(p.stat().st_size for p in dateien)
    print(f"\n{len(dateien)} Dateien in {ORDNER} ({gesamt / 1024:.0f} KB)")
