==============================================================================
 
BORDTERMINAL - DER BEFEHL "h" (HILFE), NEU GEORDNET
 
Stand: 02.11.2026, nach dem Aufraeumen des Hilfetexts in bordterminal.py
==============================================================================
WAS "h" SELBST TUT
------------------------------------------------------------------------------
Eingabe: h   (auch H). Argumente werden ignoriert, es gibt keine Aliase
wie "hilfe", "help" oder "?".
  1. 
Spielt den Klang "ansicht".
  2. 
Gibt den Text der Konstante HILFE in der hellen Farbe des aktiven
     
Farbthemas aus.
  3. 
Zeichnet das Logbuch danach nicht neu und speichert nichts.
Ab Bewusstseinsstufe 2 kann MU/TH/UR vor jedem Befehl (also auch vor "h")
gelegentlich kurz zoegern und einen leisen Funkspruch einwerfen.
Was beim Aufraeumen geaendert wurde:
  - 
"t" steht nur noch einmal drin (unter TERMINAL-EINSTELLUNGEN).
  - 
Die Logbuch-Befehle haben eine eigene Ueberschrift und stehen vorne.
  - 
Jede Kurzform steht direkt unter ihrem Bereich (a, ka, ra).
  - 
Schiff, Konzern, Ansprechen, Geschichte, Einstellungen und Klang sind
    
getrennte Abschnitte.
  - 
Es ist kein Befehl weggefallen und keiner dazugekommen.
  - 
Sicherung des alten Stands: sicherung/bordterminal_vor_hilfe_aufraeumen.py
Schreibweise: <...> = Angabe, die du einsetzt. "|" = eins von beiden.
1. 
GRUNDLAGEN
------------------------------------------------------------------------------
  
home            Startbildschirm: offene Auftraege, Heute, Notizen und
                  
Schiffszustand auf einen Blick.
  
h               Diese Hilfe.
  
u               Letzte Aktion rueckgaengig machen.
  
q               Alles speichern und beenden.
  
ja | nein       Auf eine Rueckfrage antworten (auch ok, klar, negativ ...).
  
Hallo / Danke / Tschuess
                  
Das Terminal antwortet; bei Tschuess folgt ein Abschied
                  
passend zur Tageszeit und das Terminal kann beenden.
2. 
LOGBUCH (AUFTRAEGE)
------------------------------------------------------------------------------
  
s               Logbuch (Kanban-Board) anzeigen, darunter heutige Termine
                  
und angepinnte Notizen.
  
a               Eintrag anlegen, Schritt fuer Schritt abgefragt.
  
a <kurz>        Eintrag in einem Rutsch (Kurzform unten).
  
v               Eintrag verschieben (mit Abfrage).
  
v <id> <spalte> Direkt verschieben, z.B. v 5 4 = Eintrag 5 nach ERLEDIGT.
  
l               Eintrag loeschen (mit Abfrage).
  
l <id>          Direkt loeschen.
  
f <text>        Eintraege suchen; ohne Text alle zeigen.
  
ausbuchen       Alle erledigten Jobs archivieren und aus dem Logbuch
                  
nehmen.
  
ausbuchen 30    Nur Jobs, die laenger als 30 Tage erledigt sind.
                  
Kurzform: ab
  
e               Logbuch als Markdown-Datei exportieren.
  
MEHRERE LOGBUECHER
  
b               Alle Logbuecher auflisten.
  
b <name>        Anderes Logbuch oeffnen; existiert es nicht, wird es
                  
neu angelegt.
  
b standard      Zurueck zum urspruenglichen Logbuch.
  
SPALTEN
  
1 BEFEHLE       Anweisungen der Bruecke (Eingang / To-do)
  
2 WARTUNG       Laufende Wartung (in Arbeit)
  
3 REPARATUR     Schadensbehebung (dringend / Stoerung)
  
4 ERLEDIGT      Abgeschlossene Jobs
  
KURZFORM FUER a
  
Beispiel:  a 3 Hydraulikleck @ripley !3 +2
  
<nummer>   Spalte 1-4; fehlt sie, landet der Eintrag in BEFEHLE.
  
@name      Besatzung: dave, ripley, ash, newt
  
!1 bis !3  Prioritaet
  
Datum      2026-10-20, +3 (in 3 Tagen), heute, morgen, freitag ...
  
Rest       Wird der Titel.
  
-> Spalte REPARATUR, Titel "Hydraulikleck", Ripley, Prioritaet 3,
     
faellig in 2 Tagen.
3. 
KALENDER
------------------------------------------------------------------------------
  
heute           Was heute ansteht: Termine, Fristen, Angepinntes.
  
k               Monatsansicht.
  
k <monat>       Anderer Monat: k +1, k -1 oder k 2026-12.
  
ka <kurz>       Termin anlegen (Kurzform unten).
  
kl <id>         Termin loeschen.
  
KURZFORM FUER ka
  
Beispiel:  ka freitag 14:30-16:00 Zahnarzt @newt in Bonn
  
Datum      Kommt zuerst, Pflicht.
  
HH:MM      Optional, auch als Spanne HH:MM-HH:MM.
  
in <ort>   Optional; alles hinter "in" ist der Ort.
  
@name      Optional.
4. 
WIEDERKEHRENDE TERMINE (REGELN)
------------------------------------------------------------------------------
  
r               Regeln anzeigen.
  
ra <kurz>       Regel anlegen (Kurzform unten).
  
rl <id>         Regel loeschen.
  
rx <id> <von> <bis>
                  
Zeitraum sperren, z.B. Ferien: dort entfaellt die Regel.
  
KURZFORM FUER ra
  
Beispiele: ra mo-fr 08:00-16:26 Schule @ash in Berufsschule
             
ra mi,fr 19:30-22:00 Fussballtraining @newt
  
Tage       Zuerst: mo-fr, mi,fr, werktags, wochenende, taeglich
  
HH:MM      Optional, auch als Spanne.
  
+feiertage Regel gilt auch an Feiertagen (sonst entfaellt sie dort).
5. 
NOTIZBLOCK
------------------------------------------------------------------------------
  
n               Notizen anzeigen.
  
n <text>        Notiz anlegen; @name ordnet sie jemandem zu.
  
nf <text>       Notizen durchsuchen.
  
np <id>         Anpinnen oder loesen (Angepinntes erscheint bei s,
                  
heute und home).
  
nl <id>         Notiz loeschen.
6. 
BERICHTSHEFT (AUSBILDUNGSNACHWEIS)
------------------------------------------------------------------------------
  
bh              Heft der laufenden Woche ausfuellen.
  
bh faellig      Die Woche, die der Konzern anmahnt.
  
bh -1           Vorige Woche (auch -2, -3 ...).
  
bh kw42         Bestimmte Kalenderwoche.
  
bh 13.10.       Woche, in der dieses Datum liegt.
  
bh liste        Bisher erzeugte Hefte (Ordner berichtshefte/).
7. 
FINANZEN
------------------------------------------------------------------------------
  
fin             Monatsbilanz: Einnahmen, Ausgaben, Saldo, Kategorien.
  
fin <monat>     Anderer Monat: fin +1 oder fin 2026-12.
  
fix -450 Miete #Wohnen
                  
Fixkosten, jeden Monat wieder. #Wort = Kategorie.
  
fix +1050 Verguetung
                  
Festes Einkommen. Nur das "+" macht es zur Einnahme.
  
aus 43,20 Einkauf #Essen
                  
Einmalige Ausgabe, heute gebucht.
  
ein 50 Geburtstag
                  
Einmalige Einnahme, heute gebucht.
  
finl <id>       Posten loeschen.
8. 
SPARZIELE
------------------------------------------------------------------------------
  
ziel            Alle Ziele mit Balken und Hochrechnung.
  
ziel neu 2500 Fuehrerschein 2027-03-01
                  
Neues Ziel: Betrag, Name, Frist (optional).
  
ziel ein <id> <betrag>   Einzahlen.
  
ziel weg <id>   Ziel loeschen.
9. 
EINKAUFSLISTE
------------------------------------------------------------------------------
  
ek              Liste anzeigen (Abgehaktes durchgestrichen).
  
ek 2x Milch     Posten anlegen, Menge wird erkannt.
  
ekh <id>        Abhaken oder wieder oeffnen.
  
ekl <id>        Posten loeschen.
  
ekx             Alles Abgehakte entfernen.
10. 
SCHIFF UND BESATZUNG
------------------------------------------------------------------------------
  
scan            Schiffsdiagnose: Rumpf, Kraftstoff, CO2, Organismen, Funk.
  
map             Schiffskarte; kontaminierte Bereiche blinken rot.
  
radar           Rundsuchlauf: offene Auftraege als Kontakte auf dem Schirm.
  
sitrep          Lagebericht fuer heute, auch als Datei in sitreps/.
  
purge           Lueftung purgen (gegen Makroorganismen).
  
dekon           Dekontamination (gegen Mikroorganismen).
  
crew            Besatzungsliste.
  
crew <name>     Personalakte plus alle Eintraege dieser Person.
  
akte <name>     Nur die Personalakte.
11. 
KONZERN
------------------------------------------------------------------------------
  
wy              Internes Rundschreiben der Weyland-Yutani Corp.
  
wy an|aus       Durchsagen der Zentrale ein- oder ausschalten.
  
freigabe        Deine Sicherheitsfreigabe und was noch fehlt (schaltet
                  
u.a. weitere Farbthemen frei).
12. 
JEMANDEN ANSPRECHEN
------------------------------------------------------------------------------
  
@<kuerzel> <thema>
                  
@m = MU/TH/UR   @w = Zentrale   @r = Ripley
                  
@a = Ash        @n = Newt       @d = Dave (du selbst)
                  
Themen: hallo, danke, report, status, wer, sorry, bye
                  
Beispiele: @m hallo, @r report, @a status, @d wer
  
@r reaktor      Statt eines Themas ein Stichwort nennen und die
                  
Geschichte erkunden.
  
@reboot         Bordanlage zuruecksetzen, falls MU/TH/UR eigene Wege geht
                  
(Bewusstseinsstufe zurueck auf 0; auch "neustart").
13. 
GESCHICHTE UND DIALOGE
------------------------------------------------------------------------------
  
story           Was bisher geschah: Merker, Verhaeltnisse, Auftraege.
  
story zurueck   Ganze Geschichte auf Anfang setzen.
  
story zurueck <name>   Nur diesen Merker loeschen.
  
dialog          Eigene Dialoge aus dialoge/ anzeigen und pruefen.
  
dialog <name>   Einen Dialog sofort abspielen.
  
dialog neu <muster> <name>
                  
Neue Datei aus Blanko-Muster, z.B. dialog neu szene
                  
reaktor_03. Muster: durchsage, frage, szene, kette,
                  
partner.
  
Alle Antworten der Figuren stehen in dialoge/ und sind dort aenderbar.
14. 
TERMINAL-EINSTELLUNGEN
------------------------------------------------------------------------------
  
t               Farbthema wechseln (Start: DISCOVERY), reihum durch alle
                  
freigeschalteten Themen.
  
crt an|aus      Roehrenmonitor-Effekte an/aus.
  
ai an|aus       Eigeninitiative von MU/TH/UR an/aus.
  
schoner         Bildschirmschoner sofort zeigen.
  
schoner an|aus  Automatisch nach 5 Minuten Ruhe, oder nie.
15. 
KLANG UND BILDER
------------------------------------------------------------------------------
  
klang           Tonausgabe: Zustand und alle Schalter.
  
klang an|aus    Ton ein/aus.
  
klang tasten an|aus   Tastenklick beim Schreiben ein/aus.
  
klang test      Alle Signale nacheinander anhoeren.
  
art             Bildarchiv: welche ASCII-Motive vorliegen.
  
art <name>      Ein Bild anzeigen (Dateien in ASCII_Art/).
==============================================================================
