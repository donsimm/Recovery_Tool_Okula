"""Hilfe → „So funktioniert das Tool“: Anleitung in einfacher Sprache, Kapitel links, Text rechts."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk  # noqa: E402

from okula_recovery import helpsearch  # noqa: E402
from okula_recovery.uikit import scrolled  # noqa: E402

# (Kapitel, Text in Pango-Markup). Handbuch-Stil: keine Anrede (weder „du“ noch „Sie“), Schritte im Infinitiv,
# kurze Sätze, Fachwörter in „Wichtige Begriffe“ erklärt. Begriffe wie in der Oberfläche: Disk, Zieldisk,
# Datenträger (USB), Windows-Schlüssel, Agent-Stick. Schritte nummeriert, Hinweise mit •, Folgezeilen 4 Leerzeichen.
# Farbwörter als Farbfeld mit fester Schriftfarbe (lesbar im hellen und im dunklen Design).
CHAPTERS: list[tuple[str, str]] = [
    ("Überblick", """<big><b>Was macht das Tool?</b></big>

Das Okula Recovery Tool sichert Computer und stellt sie wieder her.
Alles läuft über das Netzwerk. Die Sicherungen liegen auf dem <b>NAS</b>.

<b>Funktionen:</b>
•  Eine ganze Disk sichern (<b>Disk-Image</b>) und später zurückspielen – auch auf eine kleinere Disk.
•  Nur Dateien sichern (<b>Datei-Backup</b>), zum Beispiel Dokumente und Bilder.
•  Ein <b>Master-Image</b> auf viele Geräte verteilen – jedes Gerät bekommt seinen eigenen Namen.
•  Geräte <b>automatisch</b> neu aufsetzen, sobald sie starten (<b>Automatisierung</b>).
•  Windows oder Linux direkt auf ein Gerät installieren.
•  Ordner wie <i>Software</i> oder Projekte auf den Desktop eines Geräts senden.
•  Programme still installieren lassen – aus der <b>Software-Bibliothek</b> des Tools.
•  Geräte ohne Stick starten (<b>Netzwerkstart</b>) und aus der Ferne einschalten (<b>Wake-on-LAN</b>).
•  <b>Inventar</b> jedes Geräts: Hardware, Disks mit Zustand, Windows-11-Tauglichkeit, Garantie.
    Export als Liste (CSV) oder PDF.
•  USB-Sticks erstellen (Agent-, Boot- und Restore-Stick), USB-Datenträger klonen und formatieren.
•  <b>Virtuelle Maschinen</b> auf dem Server: Master-Image bauen und Images testen ohne echtes Gerät.
•  Ein <b>Demo-Gerät</b> zum Vorführen.
•  Eine <b>Projektübersicht</b> im Browser: offene Tests, Bugs, Änderungen und Ideen mit Rückmeldungen.

<b>Aufbau des Fensters:</b>
•  <b>Links</b> stehen alle Geräte (Computer). Ein grüner Punkt bedeutet: verbunden.
    Das Häkchen <i>Auto</i> schaltet die Automatisierung für ein Gerät ein (mit Rückfrage) oder aus.
•  <b>Rechts</b> steht das NAS mit den Reitern <i>Images</i>, <i>Dateien</i> und <i>Backups</i>.
•  <b>Oben rechts</b> steht, wie stark der Server gerade arbeitet (CPU, RAM, LAN).
•  <b>Oben</b> ist die Menüleiste: <i>Menü</i>, <i>Tools</i>, <i>Extras</i> und <i>Hilfe</i>.

Wichtig: Auf den Geräten wird <b>nichts installiert</b>.
Die Geräte starten nur kurz vom <b>Agent-Stick</b> oder über das Netzwerk (Netzwerkstart).

<b>In dieser Anleitung suchen:</b> Wort oben links ins Suchfeld eingeben (oder <b>Ctrl+F</b>).
Die Liste zeigt dann nur Kapitel mit diesem Wort, die Treffer sind gelb markiert."""),

    ("Wichtige Begriffe", """<big><b>Wichtige Begriffe einfach erklärt</b></big>

<b>Server</b>
Der Computer, auf dem dieses Tool läuft (der RecoveryPC).

<b>NAS</b>
Ein Netzwerk-Speicher. Dort liegen alle Sicherungen und ISO-Dateien.

<b>Einhängen</b>
Das NAS mit dem Server verbinden, damit das Tool darauf lesen und schreiben kann.

<b>Gerät</b>
Ein Computer, der gesichert, wiederhergestellt oder neu aufgesetzt wird.

<b>Agent und Agent-Stick</b>
Der Agent ist ein kleines Programm. Es startet vom Agent-Stick (USB) oder über das Netzwerk.
Dann kann das Tool mit dem Gerät reden. Der Agent läuft nur im Arbeitsspeicher und ändert nichts am Gerät.

<b>Disk und Zieldisk</b>
Disk ist die Festplatte oder SSD im Gerät. Die Zieldisk ist die Disk, auf die geschrieben wird.
Alles auf der Zieldisk wird dabei überschrieben.

<b>Datenträger</b>
USB-Stick oder externe Festplatte, die am Server steckt.

<b>Partition</b>
Ein Bereich auf einer Disk. Eine Disk kann mehrere Partitionen haben.

<b>Disk-Image</b>
Eine Kopie der ganzen Disk, mit Windows, Programmen und Dateien.
Damit lässt sich ein Gerät genau so wiederherstellen, wie es war.

<b>Datei-Backup</b>
Eine Kopie von ausgewählten Dateien und Ordnern, zum Beispiel „Dokumente“.

<b>Master-Image</b>
Ein vorbereitetes Windows für viele Geräte (mit Sysprep). Beim Zurückspielen bekommt jedes Gerät
seinen eigenen Namen und seinen Windows-Schlüssel. In der Liste hat es einen Stern ★.

<b>Sysprep</b>
Ein Werkzeug von Windows. Es macht ein eingerichtetes Windows „neutral“ (ohne Namen und Kennung),
damit es auf viele Geräte passt. Siehe Kapitel <i>Master-Image</i>.

<b>Automatisierung</b>
Das Tool setzt ein Gerät selbst neu auf, sobald es mit dem Agent startet – ohne Klick.

<b>Gerätename</b>
Der Name im Tool. Er wird auch der Computername bei einer Neuinstallation.

<b>Windows-Schlüssel</b>
Der Produktschlüssel (Lizenz) von Windows. Viele Geräte haben ihn im BIOS gespeichert.

<b>ISO</b>
Eine Datei mit einem Betriebssystem, zum Beispiel Windows 11 oder Ubuntu.

<b>BIOS / UEFI</b>
Die Grundeinstellungen des Geräts, noch vor Windows. UEFI ist die moderne Form.
Dort werden zum Beispiel die Startreihenfolge und Wake-on-LAN eingestellt.

<b>Boot-Menü</b>
Eine Auswahl beim Einschalten: von welchem Datenträger das Gerät startet (Disk, USB-Stick, Netzwerk).

<b>Netzwerkstart (PXE)</b>
Das Gerät startet den Agent über das Netzwerkkabel statt vom USB-Stick.

<b>Wake-on-LAN</b>
Ein ausgeschaltetes Gerät über das Netzwerk einschalten.

<b>Virtuelle Maschine (VM)</b>
Ein nachgebildeter Computer, der auf dem Server läuft – mit eigener Disk (eine Datei auf dem Server),
Netzwerkkarte und Bildschirm im eigenen Fenster. Im Tool ist sie ein Gerät wie jedes andere.
Siehe Kapitel <i>Virtuelle Maschinen</i>.

<b>TPM und Secure Boot</b>
Sicherheitsfunktionen im Gerät. Windows 11 verlangt TPM 2.0 und Secure Boot.

<b>SMART</b>
Der Selbsttest einer Disk. Er zeigt, ob die Disk gesund ist.

<b>Inventar</b>
Alle Angaben zu einem Gerät: Hersteller, Modell, Seriennummer, Prozessor, Arbeitsspeicher, Grafikkarte, Disks.

<b>CSV</b>
Eine einfache Tabellendatei, lässt sich mit Excel öffnen.

<b>Formatieren</b>
Einen Datenträger leer machen und für ein bestimmtes System vorbereiten. Dabei gehen alle Daten verloren.

<b>Klonen</b>
Einen Datenträger 1:1 auf einen anderen kopieren.

<b>Firewall und Port</b>
Eine Firewall lässt nur erlaubte Verbindungen durch. Ein Port ist die „Türnummer“ einer Verbindung."""),

    ("Erste Schritte", """<big><b>Erste Schritte (nur einmal nötig)</b></big>

<b>1. NAS verbinden</b>
1.  <i>Menü → NAS-Verbindung …</i> öffnen (oder Ctrl+N).
2.  Adresse des NAS, Benutzer und Passwort eingeben.
3.  Auf <i>Freigaben suchen</i> klicken und die Freigabe wählen.
4.  Auf <i>Einhängen</i> klicken.
Rechts steht dann „● NAS verbunden“ in Grün.
•  <i>NAS-Webseite öffnen</i> (oder das kleine Symbol neben dem Zahnrad) öffnet die Seite des NAS im Browser,
    zum Beispiel um dort Speicher oder Benutzer zu prüfen.

<b>2. Agent-Stick erstellen</b>
1.  Einen leeren USB-Stick einstecken (mindestens 4 GB).
2.  <i>Menü → Agent-USB-Stick erstellen …</i> öffnen.
3.  Den Stick wählen. Fehlt die Debian-Live-ISO, auf <i>Herunterladen</i> klicken.
4.  Auf <i>Stick vorbereiten</i> klicken. Achtung: Der Stick wird gelöscht.
5.  Warten, bis das Fenster <i>Agent-Stick fertig</i> erscheint („Der Stick kann jetzt abgezogen werden.“),
    dann auf <i>OK</i> klicken und den Stick abziehen. <b>Stick erst abziehen, wenn „Stick fertig“ erscheint.</b>
Zum Schluss prüft das Tool die Dateien auf dem Stick (Agent-Teil vorhanden und gültig, Live-System vollständig,
Kernel und initrd vorhanden). Wurde der Stick zu früh abgezogen oder fehlt etwas, erscheint rot
<i>Stick nicht fertig</i> mit dem Grund (z. B. „Stick wurde während des Schreibens abgezogen – Stick neu
erstellen.“). Diesen Stick nicht verwenden, sondern neu erstellen.
Nach einem Update des Tools muss der Agent-Stick manchmal neu erstellt werden.
Das steht dann in den Hinweisen zum Update.

<b>3. Firewall</b>
Nur nötig, wenn auf dem Server eine Firewall läuft. Prüfen mit <tt>sudo nft list ruleset</tt>:
leer bedeutet, dass nichts zu tun ist. Sonst diese Ports für eingehende Verbindungen freigeben:
•  <b>Immer:</b> UDP 47811 – sonst findet das Tool die Geräte nicht.
•  <b>Nur für den Netzwerkstart:</b> UDP 67, UDP 69, UDP 4011 und TCP 47813.

<b>4. Bandbreite begrenzen (bei Bedarf)</b>
Aufträge nutzen sonst das Netzwerk voll aus. Damit das Netz tagsüber nicht ausgelastet ist:
1.  <i>Menü → Einstellungen …</i> öffnen. Ganz oben steht der Rahmen <i>Bandbreite</i>.
2.  <i>Bandbreite begrenzen</i> anhaken und den Höchstwert in Mbit/s wählen (daneben umgerechnet in MB/s).
3.  Auf Wunsch <i>Nur in diesem Zeitfenster</i> anhaken, von/bis und die Tage wählen (Standard Mo–Fr
    07:00–18:00). Helle Tage sind begrenzt, dunkle unbegrenzt. Ausserhalb gilt keine Grenze,
    ohne Zeitfenster gilt sie immer.
4.  <i>Speichern</i>. Die Grenze wirkt sofort, auch auf laufende Aufträge.
•  Die Grenze gilt für alle Aufträge zusammen und wird gerecht verteilt: Disk-Image, Zurückspielen,
    Datei-Backup, Ordner senden, OS installieren, Image anpassen auf dem Gerät – auch für das Demo-Gerät.
•  Zugriffe des Servers auf das NAS (Reiter <i>Dateien</i>, <i>Image prüfen …</i>) bleiben unbegrenzt.
•  Im Log jedes Auftrags steht zu Beginn „Bandbreite begrenzt auf … Mbit/s“."""),

    ("Typischer Ablauf", """<big><b>Typischer Ablauf von A bis Z</b></big>

Ein neues Gerät erfassen, sichern und später automatisch neu aufsetzen.

<b>1. Gerät erfassen</b>
Gerät mit dem Agent-Stick starten (Kapitel <i>Gerät verbinden</i>).
Es erscheint links unter „Neu / nicht einsortiert“.
Rechtsklick → <i>Umbenennen …</i>: Der Name wird später der Computername.
Danach das Gerät in einen Ordner ziehen, zum Beispiel nach Standort oder Abteilung.

<b>2. Zustand sichern</b>
<i>Disk-Image erstellen …</i> – so lässt sich der alte Zustand jederzeit wiederherstellen.

<b>3. Master-Image bereitstellen</b>
Ein vorbereitetes Windows (Kapitel <i>Master-Image</i>) im Reiter <i>Images</i> mit ★ markieren.

<b>4. Automatisierung einrichten</b>
Gerät öffnen → Reiter <i>Automatisierung</i>: Master-Image und Zieldisk wählen,
vorher Backup ja oder nein, am Ende Neustart. Schalter einschalten.
Achtung: Ist das Gerät gerade verbunden, beginnt der Countdown sofort (30 Sekunden).

<b>5. Gerät neu aufsetzen</b>
Gerät mit dem Agent-Stick oder per Netzwerkstart starten. Der Rest läuft von selbst.
Den Stick nie abziehen, solange der Agent läuft – erst wenn das Gerät aus ist bzw. beim Neustart
der Bildschirm dunkel wird.

<b>6. Inventar festhalten</b>
<i>Menü → Inventar exportieren (CSV/PDF) …</i> – zum Beispiel als Liste für die Übergabe."""),

    ("Gerät verbinden", """<big><b>Ein Gerät verbinden</b></big>

<b>Ablauf:</b>
1.  Agent-Stick in das Gerät stecken.
2.  Gerät starten und das Boot-Menü öffnen: gleich nach dem Einschalten die Taste mehrmals antippen.
    <b>Boot-Menü-Taste je Hersteller</b> (BIOS-Taste in Klammern):
    HP <b>F9</b> (F10) · Dell <b>F12</b> (F2) · Lenovo ThinkPad <b>F12</b> (F1) · Lenovo IdeaPad <b>F12</b> (F2)
    Asus Notebook <b>Esc</b> (F2) · Asus Desktop <b>F8</b> (Entf) · Acer <b>F12</b> (F2) · MSI <b>F11</b> (Entf)
    Gigabyte <b>F12</b> (Entf) · Fujitsu <b>F12</b> (F2) · Medion <b>F10</b> (F2) · Toshiba/Dynabook <b>F12</b> (F2)
    Surface: <b>Lautstärke leiser</b> halten + Ein-Knopf · Mac (Intel): <b>Option/Alt</b> halten
    •  Acer: Das F12-Menü muss zuerst im BIOS eingeschaltet werden.
    •  Lenovo IdeaPad: Klappt keine Taste, hilft der kleine Novo-Knopf (Büroklammer).
    •  Ist das Gerät schon im Tool, steht seine Taste im Gerätefenster unter <i>Übersicht → Starttasten</i>.
3.  Den USB-Stick wählen.
4.  Nach etwa einer Minute erscheint das Gerät links im Tool, mit grünem Punkt.

Neue Geräte stehen zuerst unter <i>„Neu / nicht einsortiert“</i>.
Einsortieren und umbenennen: Kapitel <i>Geräte verwalten</i>.

<b>Die Punkte bedeuten:</b>
•  <span foreground="#2e7d32">●</span> grün: Gerät ist verbunden und bereit.
•  <span foreground="#c62828">●</span> rot: Gerät ist nicht verbunden (ausgeschaltet oder ohne Agent).

<b>Gerätefenster</b>
Doppelklick auf ein Gerät öffnet sein Fenster:
•  Oben die Knöpfe: Disk-Image erstellen, Image zurückspielen, OS installieren, Backup erstellen,
    Ordner senden, Windows anpassen (Kapitel <i>Windows anpassen</i>), Inventar neu einlesen; rechts die Symbole <i>Neu starten</i> (Pfeil im Ein/Aus-Zeichen)
    und <i>Herunterfahren</i> (Ein/Aus-Zeichen).
•  Oben rechts <i>VM mit dieser Hardware erstellen …</i>: virtuelle Maschine mit der Hardware des Geräts
    (Kapitel <i>Virtuelle Maschinen</i>, Abschnitt „Digitaler Zwilling“).
•  <i>Aufträge</i>: was gerade läuft, mit Fortschritt und Log.
•  <i>Übersicht</i>: Hersteller, Modell, Seriennummer, Starttasten, Prozessor, Arbeitsspeicher, Grafikkarte,
    Windows 11, Garantie bis, Windows-Schlüssel.
    <i>Grafikkarte</i>: Hersteller und Modell, z. B. „NVIDIA GeForce GT 740 (GK107)“, dahinter die PCI-Adresse.
    Bei mehreren Karten (z. B. Video-Server) steht jede einzeln als <i>Grafikkarte 1</i>, <i>Grafikkarte 2</i> …
    nach PCI-Adresse – so lassen sich gleiche Modelle unterscheiden. Der Tooltip zeigt IDs, Hersteller der Karte
    und Treiber. Fehlt die Zeile, stammt das Inventar von einem älteren Agent-Stick: Stick neu erstellen und
    <i>Inventar neu einlesen</i>.
•  <i>Disks</i>: die Disks und ihr Zustand (SMART).
•  <i>Images</i> und <i>Backups</i>: alle Sicherungen dieses Geräts.
•  <i>Netzwerk</i>: Netzwerkstart, Einschalten aus der Ferne (Wake-on-LAN).
•  <i>Automatisierung</i>: das Gerät automatisch neu aufsetzen.
•  <i>Verlauf</i> und <i>Notizen</i>.

Das Tool erkennt ein Gerät beim nächsten Mal wieder, auch nach Monaten."""),

    ("Netzwerkstart", """<big><b>Gerät ohne Stick verbinden (Netzwerkstart)</b></big>

Ein Gerät, das schon einmal mit dem Agent-Stick lief, kann den Agent auch <b>über das Netzwerk</b> starten.
Der Stick ist dann nicht mehr nötig.

<b>Einmal einrichten:</b>
1.  <i>Tools → Netzwerkstart (PXE) …</i> öffnen.
2.  Server-IP prüfen und die Debian-Live-ISO wählen. Fehlt sie, auf <i>Herunterladen</i> klicken.
3.  Auf <i>Vorbereiten</i> klicken. Das dauert einige Minuten.
4.  Geräte freischalten: Haken setzen. Oder im Gerätefenster unter <i>Netzwerk</i> den Schalter
    „Netzwerkstart“ einschalten. Das Zahnrad daneben öffnet die Einstellungen.
5.  Auf <i>Einschalten</i> klicken.
Läuft auf dem Server eine Firewall: Ports im Kapitel <i>Erste Schritte</i> freigeben.

<b>Am Gerät:</b>
1.  Netzwerkkabel einstecken.
2.  Beim Start das Boot-Menü öffnen (Taste je Hersteller: Kapitel <i>Gerät verbinden</i>)
    und „Netzwerk“, „LAN“ oder „PXE“ wählen.
3.  Das Gerät erscheint im Tool mit grünem Punkt – wie mit dem Stick.

<b>Sicher für die anderen Rechner:</b>
•  Nur freigeschaltete Geräte bekommen eine Antwort. Alle anderen Rechner merken nichts.
•  Das Tool verteilt keine IP-Adressen. Das macht weiterhin der Router bzw. DHCP-Server.
•  Neue Geräte sind nie automatisch freigeschaltet.

<b>Ganz aus der Ferne (Reiter „Netzwerk“ im Gerätefenster):</b>
•  <i>Einschalten</i>: schaltet ein ausgeschaltetes Gerät über das Netzwerk ein (Wake-on-LAN).
    Im BIOS des Geräts muss Wake-on-LAN eingeschaltet sein.
•  <i>Netzwerkstart zuerst</i>: Das Gerät fragt bei jedem Start zuerst das Tool.
    Ohne Auftrag startet es nach 1–2 Sekunden ganz normal (z. B. Windows).
    Einschalten geht, während das Gerät mit dem Agent verbunden ist.
•  <i>Beim nächsten Start den Agent laden</i>: Beim nächsten Start kommt der Agent statt Windows. Nur einmal.
•  <i>Einschalten und Agent starten</i>: beides zusammen. Das Gerät erscheint danach im Tool,
    ohne dass jemand vor Ort sein muss.
•  Nach Windows-Updates kann die Startreihenfolge zurückgesetzt sein. <i>Prüfen</i> zeigt es an.
•  <i>Netzwerkstart-Protokoll</i> (unten im Reiter <i>Netzwerk</i>): was der Server in den letzten 6 Stunden
    von diesem Gerät gesehen hat – Anfrage (BIOS oder UEFI), Antwort, Bootlader, Kernel, Live-System,
    Agent. Grün = geklappt, rot = Fehler mit Grund. Aktualisiert sich alle 5 Sekunden, solange der
    Reiter offen ist.
•  <b>Gerät im BIOS-Modus (Legacy)</b>: Das Tool kann die Startreihenfolge nicht ändern. Im BIOS-Setup
    (Taste je Hersteller, z. B. HP: F10) „Netzwerk“ bzw. „PXE“ an die erste Stelle setzen, danach den
    Schalter <i>Netzwerkstart zuerst</i> einschalten – das Tool vermerkt es nur. <i>Beim nächsten Start den
    Agent laden</i> und <i>Einschalten und Agent starten</i> gehen dann wie bei UEFI.
•  In der Liste <i>Netzwerkkarten</i> taugen nur Kabel-Karten mit fester MAC für Netzwerkstart und
    Wake-on-LAN – nicht WLAN, Mobilfunk-Modems und zufällige MACs."""),

    ("Geräte verwalten", """<big><b>Geräte verwalten</b></big>

Alle Aktionen über Rechtsklick auf ein Gerät oder einen Ordner in der Geräteliste.
Die Aufträge für das gewählte Gerät stehen zusätzlich im Menü <i>Tools</i>.

<b>Gerät</b>
•  <i>Umbenennen …</i>: Der Gerätename wird bei Neuinstallation, Master-Image und Automatisierung
    der Computername. Windows erlaubt höchstens 15 Zeichen ohne Sonderzeichen.
•  <i>Nach „Neu / nicht einsortiert“</i>: Gerät aus seinem Ordner zurücknehmen.
•  <i>Zusammenführen mit …</i>: Steht ein Gerät doppelt in der Liste, die zwei Einträge vereinen.
•  Baugleiche Geräte (gleiche Kennung ab Werk, z. B. leere oder gleiche Board-UUID) bleiben getrennt:
    Sind zwei gleichzeitig verbunden, führt das Tool sie als zwei Geräte, das zweite mit „(2)“ im Namen.
    Wurden sie früher vereint, trennt das Tool sie, sobald beide zugleich verbunden sind.
•  <i>Aus der Liste löschen …</i>: nur möglich, wenn das Gerät nicht verbunden ist.
    Images und Backups auf dem NAS bleiben.
•  <i>Inventar neu einlesen</i>: Angaben zum Gerät neu holen (zum Beispiel nach einem Disk-Tausch).
•  <i>Netzwerkstart → Einschalten</i> bzw. <i>Einschalten und Agent starten</i>: Gerät aus der Ferne
    einschalten (Wake-on-LAN, wie im Reiter <i>Netzwerk</i>). Ausgegraut, wenn es nicht geht – der Grund
    steht im Tooltip (z. B. schon verbunden, keine Kabel-Netzwerkkarte, „Netzwerkstart zuerst“ fehlt).
•  <i>Neu starten</i> und <i>Herunterfahren</i>: Symbole rechts unter der Geräteliste und im Gerätefenster
    (Name als Tooltip), mit Rückfrage; nur wenn das Gerät verbunden ist und kein Auftrag läuft.
    Bei virtuellen Maschinen auch ohne Agent (Kapitel <i>Virtuelle Maschinen</i>).
•  <i>Inventar exportieren …</i>: Liste zu diesem Gerät (Kapitel <i>Inventar, Garantie, Windows 11</i>).

<b>Ordner</b>
•  <i>Neuer Ordner …</i>, <i>Ordner umbenennen …</i>, <i>Ordner löschen (nur leer)</i>.
•  Höchstens 3 Ordnerebenen, zum Beispiel <i>Firma → Standort → Abteilung</i>.
•  Geräte und Ordner lassen sich mit der Maus verschieben (ziehen und loslassen).
•  Der Ordner <i>Virtuelle Maschinen</i> ist fest: keine Unterordner, nicht umbenennbar, VMs bleiben darin
    und echte Geräte kommen nicht hinein."""),

    ("Disk-Image", """<big><b>Ganze Disk sichern (Disk-Image)</b></big>

Ein Disk-Image ist eine komplette Kopie der Disk.
Sinnvoll zum Beispiel vor einer Reparatur oder vor einem Disk-Tausch.

<b>Ablauf:</b>
1.  Gerät mit dem Agent starten (grüner Punkt).
2.  Gerät wählen und auf <i>Disk-Image erstellen …</i> klicken.
3.  Die <b>Disk</b> wählen und unter <i>Name im Archiv</i> einen Namen eingeben.
    <i>Ziel</i> zeigt, wo das Image auf dem NAS gespeichert wird.
4.  Auf Wunsch: <i>Maschine danach herunterfahren</i> anhaken.
5.  Auf <i>Image erstellen</i> klicken.

Der Fortschritt steht links in der Geräteliste und im Gerätefenster.
In der Zwischenzeit lässt sich mit anderen Geräten weiterarbeiten.

<b>Wichtig bei Windows:</b>
Windows vorher <b>ganz</b> herunterfahren: Shift-Taste gedrückt halten und auf „Herunterfahren“ klicken.
Sonst ist die Disk im Zustand „Schnellstart“ und lässt sich nicht sauber sichern.

Das fertige Image steht rechts im Reiter <i>Images</i> unter „Nicht einsortiert“.
Einsortieren: Kapitel <i>Images verwalten</i>."""),

    ("Image zurückspielen", """<big><b>Disk wiederherstellen (Image zurückspielen)</b></big>

Damit kommt ein Gerät auf den Stand des Images zurück.
<b>Achtung:</b> Alles auf der Zieldisk wird überschrieben.

<b>Ablauf:</b>
1.  Gerät mit dem Agent starten.
2.  Auf <i>Image zurückspielen …</i> klicken.
3.  Image wählen. Darunter steht, von welchem Gerät es ist.
4.  Zieldisk wählen.
5.  Optionen prüfen:
    •  <i>Image vor dem Schreiben vollständig prüfen</i> (empfohlen, Standard an).
    •  <i>Maschine danach herunterfahren</i>: danach den Stick abziehen und das Gerät einschalten.
    •  Nur bei VMs: <i>Vorher Snapshot</i> (Standard an) – direkt vor dem Zurückspielen entsteht ein Snapshot
        der Disk, damit lässt sich der Stand davor in Sekunden zurückholen (Kapitel <i>Virtuelle Maschinen</i>).
        Schlägt der Snapshot fehl, startet das Zurückspielen nicht. Wird die VM-Disk vorher vergrössert,
        entsteht der Snapshot erst danach (Abschnitt „Disk der VM zu klein“ unten).
6.  Zur Bestätigung den Namen der Zieldisk eintippen (zum Beispiel „sda“ oder „nvme0n1“).
7.  Auf <i>Zurückspielen</i> klicken.

Am Ende das Gerät herunterfahren (Symbol <i>Herunterfahren</i> oder Häkchen oben), dann den Stick abziehen
und das Gerät einschalten. Den Stick nie abziehen, solange der Agent läuft: Er läuft vom Stick.

<b>Zieldisk kleiner als das Image</b>
Zum Beispiel 256 statt 512 GB: Das Tool prüft, ob die Daten passen.
Dann <i>Für diese Disk anpassen</i> anhaken: Das Tool erstellt daraus ein neues, kleineres Image.
Das Original bleibt unverändert. Das dauert etwas länger.
Nicht möglich bei verschlüsselten Disks (BitLocker) – dort fehlt die Option.

<b>Disk der VM zu klein</b>
Bei einer virtuellen Maschine gibt es zwei Wege, als Optionsfelder unter dem Prüftext:
•  <i>VM-Disk auf … GB vergrössern und zurückspielen</i> (vorgewählt): Die Disk der VM wird auf die Grösse der
    Quelldisk des Images gebracht (auf ganze GB aufgerundet), das Image danach unverändert zurückgespielt.
    Alles läuft als ein Auftrag im Reiter <i>Aufträge</i>: VM wird heruntergefahren (1/4), Disk wird vergrössert
    (2/4), Agent wird gestartet (3/4), Zurückspielen (4/4). <i>Vorher Snapshot</i> entsteht dabei erst nach dem
    Vergrössern. Im Verlauf steht z. B. „VM-Disk von 128 GB auf 512 GB vergrössert“.
•  <i>Image an die kleinere Disk anpassen</i>: wie oben bei <b>Zieldisk kleiner als das Image</b> – nur wählbar,
    wenn die Daten passen.
Ausgegraut ist ein Weg mit Grund im Prüftext und im Tooltip. Vergrössern geht nicht, solange die VM
Snapshots hat (zuerst im Reiter <i>Snapshots</i> löschen) oder wenn auf dem Server zu wenig Platz frei ist
(belegte Daten des Images plus 10 % Reserve, mindestens 10 GB). Die Disk-Datei der VM ist dünn: Vergrössern
belegt erst Platz, wenn geschrieben wird. Bricht der Auftrag vor dem Zurückspielen ab, bleibt die Disk
vergrössert, die Daten darauf sind unverändert. Gehen beide Wege nicht, bleibt <i>Zurückspielen</i> gesperrt.

<b>Gut zu wissen:</b>
•  Zeigte die letzte Prüfung „beschädigt“, steht im Dialog ein roter Hinweis. Zurückspielen geht trotzdem.
•  Auch Images von Clonezilla funktionieren.
•  Nach einem Abbruch ist die Zieldisk unvollständig.
•  Bei einem Master-Image passt das Tool Windows danach an (Name, Schlüssel, auf Wunsch Einstellungen des
    Administrators): Kapitel <i>Master-Image</i>.
•  Unter <i>Danach anpassen</i> steht die Liste <i>Software installieren</i>: Die gewählten Programme werden beim
    ersten Start nach der Ersteinrichtung still installiert (Kapitel <i>Software installieren</i>)."""),

    ("Datei-Backup", """<big><b>Nur Dateien sichern (Datei-Backup)</b></big>

Ein Datei-Backup sichert nur das Ausgewählte. Es ist kleiner und schneller als ein Image.
Ideal vor einer Neuinstallation: Dateien sichern, neu installieren, Dateien zurückspielen.

<b>Backup erstellen:</b>
1.  Gerät mit dem Agent starten.
2.  Auf <i>Backup erstellen …</i> klicken.
3.  Wählen, was gesichert wird:
    •  <i>Benutzerdaten</i>: Desktop, Dokumente, Bilder, Lesezeichen … pro Benutzer.
    •  <i>Ganze Partitionen</i>: alles auf einem Laufwerk.
    •  <i>Eigene Ordner</i>: Ordner selbst auswählen.
4.  <i>Ablage</i> wählen: <i>Normale Dateien</i> (im Reiter „Dateien“ durchsuchbar)
    oder <i>Archiv tar.zst</i> (kompakt, schneller).
5.  Auf Wunsch eine Notiz eingeben (zum Beispiel „vor Neuinstallation“).
6.  Auf <i>Backup erstellen</i> klicken.

<b>Zurückspielen oder herunterladen:</b>
1.  Rechts im Reiter <i>Backups</i> (oder im Gerätefenster) das Backup doppelklicken
    oder Rechtsklick → <i>Zurückspielen / herunterladen …</i>
    Für das gewählte Gerät auch: <i>Tools → Backup zurückspielen …</i>
2.  Ziel wählen:
    •  <i>Ins installierte System</i>: Dateien zurück auf das Gerät. Alte Benutzer lassen sich neuen zuordnen.
    •  <i>Herunterladen in einen Ordner</i>: Dateien auf den Server oder einen USB-Stick kopieren.
3.  <i>Vorhandene Dateien überschreiben</i>: Ist das Häkchen aus (Standard), bleibt die vorhandene Datei.
    Die gesicherte Datei heisst dann „Name (wiederhergestellt)“.

Windows vor dem Zurückspielen <b>ganz</b> herunterfahren (Shift-Taste gedrückt halten + „Herunterfahren“).

Mit <i>Notiz …</i> lässt sich die Notiz ändern. <i>Löschen …</i> entfernt ein Backup vom NAS."""),

    ("Master-Image", """<big><b>Master-Image: ein Windows für viele Geräte</b></big>

Ein Master-Image ist ein vorbereitetes Windows. Beim Zurückspielen bekommt jedes Gerät
seinen eigenen Namen, seinen Windows-Schlüssel und auf Wunsch Region Schweiz und ein lokales Konto.

<b>Master-Image vorbereiten (am Referenzgerät):</b>
1.  Windows frisch installieren, sodass es im <b>Audit-Modus</b> startet (eingebauter Administrator,
    kein Benutzer):
    •  Am einfachsten: Agent starten → <i>OS installieren …</i> mit Häkchen
        <i>Für Master-Image (Audit-Modus)</i> (Kapitel <i>Windows / Linux installieren</i>). Kein Konto,
        kein Computername, kein Schlüssel – das kommt beim Zurückspielen dazu.
    •  Oder von Hand (Boot-Stick): beim ersten Einrichtungsbildschirm <b>Ctrl+Shift+F3</b> drücken.
2.  Updates, Treiber und Programme installieren. Kein Microsoft-Konto, keine Domäne.
    Bei einer VM vorher einen Snapshot erstellen (Reiter <i>Snapshots</i> → <i>Snapshot erstellen …</i>,
    z. B. „vor Sysprep“) – so lässt sich der Stand vor Sysprep jederzeit zurückholen.
    Desktop-Symbole anordnen, Programme an die Taskleiste heften, Explorer-Ansicht und Hintergrund einstellen –
    einfach am Administrator im Audit-Modus, ohne Skripte. Das Tool übernimmt das beim Zurückspielen für alle
    Benutzer (Häkchen <i>Einstellungen des Administrators übernehmen (Master)</i>). Kein weiteres Konto anlegen.
3.  BitLocker ausschalten.
4.  Sysprep starten (als Administrator):
    <tt>C:\\Windows\\System32\\Sysprep\\sysprep.exe /generalize /oobe /shutdown</tt>
5.  Windows <b>nicht mehr starten</b>. Direkt mit dem Agent-Stick starten.
6.  <i>Disk-Image erstellen …</i>, Name zum Beispiel „Master-Win11-2026-10“.
Die ausführliche Anleitung steht im Projekt in <tt>docs/MASTER-IMAGE.md</tt>.
Ohne Referenzgerät geht das auch in einer virtuellen Maschine (Profil <i>VM-Win11</i>,
Kapitel <i>Virtuelle Maschinen</i>).

<b>Im Tool:</b>
1.  Rechts im Reiter <i>Images</i>: Rechtsklick auf das Image → <i>Als Master-Image markieren</i>.
    Es bekommt einen Stern ★.
2.  Beim Zurückspielen ist dann <i>Danach anpassen</i> eingeschaltet:
    Das Gerät bekommt seinen Namen aus dem Tool und den Windows-Schlüssel.
    Darunter <i>Einstellungen des Administrators übernehmen (Master)</i> (Standard an): Was im Audit-Modus am
    Administrator eingerichtet wurde, wird Standard für jeden neuen Benutzer.
3.  Beim ersten Start richtet sich Windows damit selbst ein.

<b>Einstellungen des Administrators übernehmen</b>
•  Windows kopiert beim ersten Start das Profil des Administrators ins Standardprofil (<tt>CopyProfile</tt>):
    Anordnung der Desktop-Symbole, Explorer-Ansicht, Hintergrund und weitere Benutzereinstellungen.
•  Die an die Taskleiste angehefteten Programme kopiert Windows dabei nicht. Das Tool liest sie aus dem Profil
    des Administrators (gleiche Reihenfolge) und legt sie als Vorgabe für neue Benutzer ab. Das Log nennt sie:
    „Einstellungen des Administrators werden übernommen – Taskleiste: VLC media player, Explorer …“.
•  Gilt für jeden neuen Benutzer, also auch für ein zweites Konto. Ein normales Image (ohne Sysprep) bleibt
    unverändert.
•  Nicht übernommen: Kacheln im Startmenü und die Standard-Apps (welches Programm welche Dateien öffnet).
    Unter Windows 11 die Taskleiste am Gerät prüfen.
•  Für die Taskleiste ist ein aktueller Agent-Stick nötig; ein alter meldet im Log „Agent zu alt“.

<b>Gut zu wissen:</b>
•  Den Windows-Schlüssel liest das Tool aus dem BIOS. Ein eigener Schlüssel lässt sich im Gerätefenster
    unter <i>Übersicht → Windows-Schlüssel</i> hinterlegen.
•  Ein Image eines UEFI-Geräts läuft nur auf UEFI-Geräten.
•  Ein normales Image (ohne Sysprep) wird nicht angepasst. Das Log sagt es."""),

    ("Virtuelle Maschinen", """<big><b>Virtuelle Maschinen (VM) auf dem Server</b></big>

Eine virtuelle Maschine ist ein nachgebildeter Computer, der auf dem Server läuft. Die VM ist im LAN sichtbar wie
ein echter PC und startet den Agent über den Netzwerkstart – ohne Stick. Wozu:
•  <b>Master-Image bauen</b> ohne Referenzgerät: ISO installieren → einrichten → Sysprep → Disk-Image
    (Kapitel <i>Master-Image</i>).
•  <b>Images testen</b>, bevor sie auf echte Geräte gehen: zurückspielen, starten, prüfen.
•  <b>Ausprobieren</b> von Agent, Netzwerkstart und Automatisierung, bevor ein echtes Gerät dran ist.

<b>Drei Profile (Vorlagen)</b>
•  <b>VM-Win11</b>: moderner Business-Laptop – UEFI mit Secure Boot und TPM 2.0, NVMe 256 GB, Intel e1000e,
    4 Kerne, 8 GB RAM. Für Master-Image, Windows 11, Automatisierung. (VMs, die vor dieser Version mit
    128 GB angelegt wurden, behalten ihre Grösse.)
•  <b>VM-Legacy</b>: älteres Gerät – BIOS (Legacy), SATA-HDD 80 GB, Intel e1000, 2 Kerne, 4 GB RAM.
    Für BIOS-Netzwerkstart, Windows 10, alte Hardware.
•  <b>VM-Klein</b>: Gerät mit kleiner Disk – UEFI ohne Secure Boot, SATA-SSD 64 GB, Intel e1000e, 2 Kerne,
    4 GB RAM. Für Zurückspielen auf eine kleinere Disk und Linux.

<b>Anlegen</b>
1.  <i>Extras → Neue virtuelle Maschine …</i> oder Rechtsklick auf den Ordner <i>Virtuelle Maschinen</i>.
2.  Profil wählen. Der Name ist vorgeschlagen und lässt sich ändern.
3.  Unten steht, wie viel Platz und Arbeitsspeicher auf dem Server frei sind. Rot = geht nicht.
4.  <i>Erstellen</i>. Die VM steht danach im Ordner <i>Virtuelle Maschinen</i>, ist für den Netzwerkstart
    freigeschaltet und hat ein vorläufiges Inventar aus dem Profil. Beim ersten Start mit Agent kommt das echte.
Die Disk ist eine Datei auf der SSD des Servers und wächst mit dem belegten Platz.

<b>Starten und Bedienen</b> – Rechtsklick auf die VM oder Knöpfe im Gerätefenster (Zeile <i>Virtuelle Maschine</i>):
•  <i>Einschalten</i>: Die VM startet von ihrer Disk (z. B. Windows). Hatte die Disk noch nie ein System
    (keine Partitionen, im Verlauf keine Installation und kein Zurückspielen), kommt zuerst eine Rückfrage:
    ohne System startet die VM ins UEFI-Menü bzw. meldet „kein Betriebssystem“. Die Knöpfe:
    <i>Einschalten und Agent starten</i> (Image zurückspielen oder OS installieren), <i>Von ISO starten …</i>
    oder <i>Trotzdem einschalten</i>. Das UEFI-Menü bei leerer Disk ist normal und kein Fehler: VM mit
    <i>Ausschalten …</i> ausschalten und mit Agent oder von ISO neu starten.
•  <i>Einschalten und Agent starten</i>: Agent vormerken und einschalten. Die VM startet den Agent über den
    Netzwerkstart und erscheint mit grünem Punkt. Danach geht alles wie bei echten Geräten: Disk-Image,
    Image zurückspielen, Backup, Automatisierung. Dafür muss der Netzwerkstart eingeschaltet sein
    (<i>Tools → Netzwerkstart (PXE) …</i>, Kapitel <i>Netzwerkstart</i>).
•  <i>Von ISO starten …</i>: einmal von einer ISO aus der ISO-Bibliothek auf dem NAS starten, zum Beispiel
    um Windows 11 zu installieren. Nach dem Ausschalten startet die VM wieder normal.
    Tipp: zuerst <i>Bildschirm</i> öffnen (das Fenster wartet auf die VM) – Windows-ISOs verlangen beim Start
    innert weniger Sekunden einen Tastendruck („Press any key to boot from CD“).
•  <i>Bildschirm</i>: zeigt den Bildschirm der VM in einem eigenen Fenster; es wartet, bis die VM läuft.
    Nochmals klicken öffnet das Fenster neu. Maus und Tastatur gehen in die VM, Ctrl+Alt gibt sie wieder frei.
•  <i>Herunterfahren</i> und <i>Neu starten</i>: mit Agent über den Agent, sonst bekommt das Betriebssystem
    in der VM das Signal wie beim kurzen Druck auf den Einschaltknopf.
•  <i>Ausschalten …</i>: hart ausschalten wie Stecker ziehen, mit Rückfrage.
•  <i>Hardware ändern …</i> (nur ausgeschaltet): Arbeitsspeicher, Kerne, Disk vergrössern (nie verkleinern),
    Netzwerkkarte. Firmware und Disk-Anschluss nur mit Warnung – ein installiertes System startet danach
    evtl. nicht mehr. Hat die VM Snapshots, ist <i>Disk</i> gesperrt: zuerst die Snapshots löschen.
    Ist die Disk für ein Image zu klein, vergrössert <i>Image zurückspielen …</i> sie auf Wunsch selbst
    (Kapitel <i>Image zurückspielen</i>, Abschnitt „Disk der VM zu klein“).
•  <i>VM löschen …</i> (nur ausgeschaltet): VM, Disk, alle Snapshots und Geräteeintrag werden gelöscht;
    Images und Backups auf dem NAS bleiben.
In der Geräteliste steht der Zustand: <i>aus</i>, <i>läuft</i> oder <i>läuft – Agent verbunden</i>
(alle 5 Sekunden neu). Die Startreihenfolge stellt das Tool selbst ein: normal startet die VM von der Disk,
nach <i>Einschalten und Agent starten</i> einmal über das Netzwerk. Sobald der Agent verbunden ist, gilt wieder
die Disk – ein Neustart danach (z. B. nach dem Zurückspielen) startet das System auf der Disk. Im Gerätefenster,
Reiter <i>Netzwerk</i>, lässt sich der Agent auch für den nächsten Neustart einer laufenden VM vormerken.
Wake-on-LAN und „Netzwerkstart zuerst“ gibt es bei VMs nicht.

<b>Snapshots – Stand der Disk einfrieren und zurückholen</b>
Wozu: einen Stand festhalten, z. B. „frisch installiert“ oder „vor Sysprep“, und in Sekunden dorthin
zurückkehren. So lassen sich Master-Bau und Tests beliebig wiederholen, ohne neu zu installieren.
Gerätefenster der VM → Reiter <i>Snapshots</i>: Liste mit Titel, Datum, <i>Automatisch</i> ja/nein und Grösse;
<i>◀ aktueller Stand</i> markiert den Snapshot, auf dem der jetzige Stand aufbaut.
•  <i>Snapshot erstellen …</i> (nur ausgeschaltet): Titel eingeben (Vorgabe „Snapshot TT.MM. HH:MM“).
    Gesichert wird nur die Disk, ohne Arbeitsspeicher; das dauert Sekunden.
•  <i>Zurück zu diesem Snapshot …</i> (nur ausgeschaltet, auch per Doppelklick): Die Disk ist danach wieder
    so wie beim Snapshot. <b>Alle Änderungen seit diesem Snapshot gehen verloren.</b> Die anderen Snapshots
    bleiben – auch spätere, zu denen sich wieder zurückspringen lässt. Das Inventar im Tool gilt wieder wie
    zum Zeitpunkt des Snapshots (eine damals leere Disk gilt wieder als leer).
•  <i>Löschen …</i> (nur ausgeschaltet): Der aktuelle Stand und die anderen Snapshots bleiben. Die Daten des
    Snapshots werden dafür in die folgende Datei übernommen – je nach Grösse dauert das bis zu einigen
    Minuten (Balken im Reiter); so lange bleibt die VM gesperrt.
•  <b>Automatisch vor Aktionen:</b> Bei <i>Image zurückspielen …</i>, <i>OS installieren …</i> und in der
    Automatisierung gibt es bei VMs das Häkchen <i>Vorher Snapshot</i> (Standard an). Der Snapshot entsteht direkt
    vor dem Auftrag, bei laufendem Agent (die Disk ist dann unbenutzt), Titel z. B. „vor Zurückspielen 06.11. 14:05“.
    Schlägt er fehl, startet der Auftrag nicht. Bei laufendem Windows gibt es nie einen Snapshot.
•  <b>Platz:</b> Snapshots sind unbegrenzt möglich. Jeder belegt so viel, wie sich seither auf der Disk geändert
    hat; der erste enthält die ganze bisherige Disk. Unter 50 GB frei auf der Server-SSD erscheint unter der
    Liste eine Warnung – dann nicht mehr benötigte Snapshots löschen.
•  Zurückgesetzt wird nur die Disk: Hardware (RAM, Kerne …), UEFI-Einstellungen mit Secure Boot und der
    TPM-Zustand bleiben wie sie sind. Im Verlauf stehen „Snapshot ‚…‘ erstellt / zurückgesetzt / gelöscht“.
Beispiel Master-Image: Windows in der VM installieren und einrichten → VM herunterfahren → Snapshot
„vor Sysprep“ → Sysprep → Disk-Image. Für die nächste Version zurück zu „vor Sysprep“, ändern, wieder Sysprep.

<b>Digitaler Zwilling – VM mit der Hardware eines Geräts</b>
Wozu: ein Image auf „derselben“ Hardware testen, ohne das echte Gerät anzufassen.
1.  Gerätefenster eines echten Geräts → <i>VM mit dieser Hardware erstellen …</i> (oben rechts), oder
    Rechtsklick auf das Gerät. Ausgegraut, solange das Gerät noch kein Inventar hat (einmal mit dem Agent
    verbinden). Nicht für VMs und das Demo-Gerät.
2.  Die Vorschau zeigt <i>Gerät → VM</i>: <b>✔</b> genau übernommen, <b>~</b> angepasst, <b>✖</b> nicht
    übernommen, darunter jede Abweichung als Hinweis. Der Name (<i>VM-</i> + Gerätename) lässt sich ändern.
3.  <i>Letztes Image des Geräts einspielen</i> ist angehakt, das neueste Image vorgewählt (Master-Images
    mit ★). Gibt es keins: „Kein Image dieses Geräts auf dem NAS“. Dafür muss der Netzwerkstart laufen.
4.  <i>Erstellen</i>. Die VM steht im Ordner <i>Virtuelle Maschinen</i>. Mit Image läuft im Gerätefenster der
    VM ein Auftrag (Reiter <i>Aufträge</i>): einschalten und Agent starten (höchstens 5 Minuten warten),
    Image zurückspielen (vorher geprüft, ohne Anpassen), danach herunterfahren. Danach startet
    <i>Einschalten</i> das System des Images. Bei einem Fehler bleibt die VM bestehen.
Übernommen werden Hersteller, Modell, Version, SKU, Familie, Mainboard, BIOS (Hersteller, Version, Datum),
Prozessor-Name und Anzahl Kerne, Arbeitsspeicher, Disk (Grösse, Anschluss SATA/NVMe, Modellname bei SATA),
Firmware (Partitionstabelle GPT → UEFI, MBR → BIOS), Secure Boot und TPM. Angepasst: Kerne höchstens
Server-Kerne − 2, Arbeitsspeicher höchstens freier RAM des Servers − 4 GB, Netzwerkkarte immer Intel (Treiber
in Windows), Gehäusetyp nur im Profil, NVMe-Modellname bleibt „QEMU NVMe Ctrl“. Die Leistung ist die der
Server-CPU. Nicht übernommen: Windows-Schlüssel (Windows bleibt „nicht aktiviert“), Akku, WLAN, Grafik, Sound,
SMART und Einstellungen des Hersteller-BIOS. Die Grafikkarte des Geräts steht nur als Hinweis in der Vorschau;
die VM behält ihre Standard-Grafik.
<b>Abgewandelte Identität:</b> Seriennummern bekommen <i>VM-</i> vorne (z. B. VM-5CG1234XYZ), die System-UUID
beginnt mit <i>0c1a</i>, die Disk-Seriennummer mit <i>VM</i>, die MAC ist eigene. So hält das Tool Zwilling und
Gerät auseinander und führt sie nie zusammen. In der Übersicht der VM steht <i>Zwilling von</i> mit dem Gerät
(anklickbar); im Verlauf beider steht der Eintrag. Ein neues Image aktualisiert den Zwilling nicht von selbst.

<b>Grenzen</b>
•  Kein echtes Hersteller-BIOS: Eigenheiten echter Geräte (z. B. Einstellungen im HP- oder Lenovo-BIOS)
    lassen sich nicht nachbilden. Der Reiter <i>BIOS</i> zeigt nur das einfache BIOS der VM.
•  Windows in der VM bleibt „nicht aktiviert“. Der Windows-Schlüssel eines Geräts wird nie übernommen.
•  Ein Image aus der VM läuft auf echten Geräten nur mit Sysprep (Kapitel <i>Master-Image</i>).
    Die VM nutzt dafür nur Standard-Hardware (SATA/NVMe, Intel-Netzwerkkarte).
•  Die VMs laufen auf dem Server weiter, auch wenn das Tool geschlossen ist."""),

    ("Automatisierung", """<big><b>Geräte automatisch neu aufsetzen</b></big>

Mit der Automatisierung setzt das Tool ein Gerät selbst neu auf, sobald es mit dem Agent startet.

<b>Einrichten (einmal pro Gerät):</b>
1.  Gerät öffnen → Reiter <i>Automatisierung</i>.
2.  <b>Backup</b> (Option): vorher sichern – nur Benutzerdaten (schnell) oder die ganze Disk als Disk-Image.
3.  <b>Image zurückspielen</b>: Master-Image oder ein eigenes Image wählen, dazu die Zieldisk.
    Ist die Zieldisk kleiner: <i>Image dafür anpassen</i> anhaken (Kapitel <i>Image zurückspielen</i>).
4.  <b>Anpassen</b> (läuft immer, nur bei Master-Images): Gerätename und Windows-Schlüssel,
    auf Wunsch <i>Region Schweiz</i> und ein <i>Lokales Konto</i> (Passwort beim ersten Anmelden setzen).
    <i>Einstellungen des Administrators übernehmen (Master)</i> (Standard an): Desktop, Explorer-Ansicht und
    Taskleiste aus dem Audit-Modus für alle Benutzer (Kapitel <i>Master-Image</i>).
    Liste <i>Software installieren</i>: angekreuzte Programme werden beim ersten Start still installiert
    (Kapitel <i>Software installieren</i>).
5.  <b>Ordner senden</b> (Option): Software, Test Files, Content-Projekte.
6.  <b>Abschluss</b>: Neustart, Herunterfahren oder nichts.
    Nur bei VMs: <i>Vorher Snapshot</i> (oben, Standard an) – direkt vor dem Start entsteht ein Snapshot der Disk
    (Kapitel <i>Virtuelle Maschinen</i>). Schlägt er fehl, startet die Automatisierung nicht.
7.  Schalter <i>Automatisierung</i> einschalten – oder in der Liste das Häkchen <i>Auto</i> setzen.
8.  Rückfrage prüfen: Rot steht dort, was passiert – Disk, die gelöscht wird, Image, Gerätename danach,
    Backup, bei VMs Snapshot, Abschluss und ob sie sich nach 3 Tagen wieder einschaltet.
    Mit <i>Einschalten</i> bzw. <i>Löschen und neu aufsetzen</i> bestätigen. <i>Abbrechen</i> lässt alles aus.
    Fehlt noch etwas (Image, Zieldisk, NAS), erscheint statt der Rückfrage eine Meldung, was fehlt.

<b>Achtung:</b> Ist das Gerät beim Einschalten verbunden, heisst der Knopf <i>Löschen und neu aufsetzen</i>:
Nach der Bestätigung beginnt der Countdown sofort, nach 30 Sekunden wird die Zieldisk überschrieben.
Ist es nicht verbunden, heisst er <i>Einschalten</i> – gelöscht wird beim nächsten Verbinden.
Ausschalten, das Wieder-Einschalten nach 3 Tagen und der Stopp-Knopf ■ fragen nicht nach.

<b>Vorlagen</b>
•  <i>Als Vorlage speichern …</i>: Einstellungen unter einem Namen speichern (z. B. „Schulungs-PC“).
•  <i>Anwenden</i>: Vorlage bei einem anderen Gerät übernehmen. Die Zieldisk dort neu wählen.
•  <i>Löschen</i>: Geräte, die die Vorlage verwendet haben, behalten ihre Einstellungen.

<b>Ablauf am Gerät:</b>
1.  Das Gerät startet mit dem Agent (Stick oder Netzwerkstart).
2.  30 Sekunden Countdown – am Gerät bricht <b>Esc</b> ab, im Tool <i>Abbrechen</i>.
3.  Backup (wenn gewählt), Image zurückspielen, anpassen, Ordner senden.
4.  Abschluss. Bei Neustart den Agent-Stick erst abziehen, wenn der Bildschirm dunkel wird – sonst
    startet wieder der Agent. Mit Stick einfacher: Abschluss <i>Herunterfahren</i>, dann Stick abziehen.
5.  Danach schaltet sich die Automatisierung aus und nach 3 Tagen wieder ein.
    Das lässt sich mit dem Häkchen <i>Nach 3 Tagen wieder einschalten</i> abschalten.

<b>Gut zu wissen:</b>
•  Steckt eine andere Disk im Gerät, bricht das Tool ab. Es wird nichts gelöscht.
•  Bei einem Fehler steht das in der Liste (rot), im Gerätefenster und am Bildschirm des Geräts.
    Für einen neuen Versuch das Gerät neu starten.
•  Es laufen höchstens 2 Geräte gleichzeitig (ändern: <i>Menü → Einstellungen …</i>). Die anderen warten.
•  Alles anhalten: oben über der Geräteliste der Stopp-Knopf ■. Pausiert ist er rot. Nochmals klicken = weiter."""),

    ("Ordner senden", """<big><b>Ordner an ein Gerät senden</b></big>

Legt Ordner vom NAS auf den Desktop eines Geräts – für alle Benutzer.

<b>Wo die Ordner liegen:</b> auf dem NAS im Ordner <i>Verteilen</i>:
•  <i>Software</i> und <i>Test Files</i>: werden immer ganz gesendet.
•  <i>Content</i>: darin liegen Projekte. Gesendet werden nur die gewählten Projekte.
Die Inhalte lassen sich rechts im Reiter <i>Dateien</i> ändern. <i>Verteilen\\Software</i> ist ein Werkzeug-Ordner
für Geräte unterwegs – Programme zum stillen Installieren kommen aus der Software-Bibliothek
(Kapitel <i>Software installieren</i>).

<b>Ablauf:</b>
1.  Gerät mit dem Agent starten.
2.  Rechtsklick auf das Gerät → <i>Ordner senden</i> → <i>Software</i>, <i>Test Files</i> oder <i>Content …</i>
3.  Bei Content die Projekte anhaken und auf <i>Senden</i> klicken.

<b>Gut zu wissen:</b>
•  Gibt es den Ordner schon auf dem Desktop, wird er ersetzt.
•  Bricht etwas ab, bleibt der alte Ordner.
•  Windows muss ganz heruntergefahren sein (Shift-Taste gedrückt halten + „Herunterfahren“)."""),

    ("Windows anpassen", """<big><b>Windows anpassen</b></big>

Stellt an einem Gerät mit Windows per Häkchen Einstellungen um – zum Beispiel Store-Apps entfernen,
Windows Update aus, Energie für Dauerbetrieb, automatische Anmeldung. Windows setzt die Einstellungen
beim <b>nächsten Start selbst</b> um, vor der Anmeldung. Geht nach einer Installation oder jederzeit.

<b>Ablauf:</b>
1.  Gerät mit dem Agent starten (Agent-Stick oder Netzwerkstart). Windows muss ganz heruntergefahren sein.
2.  Rechtsklick auf das Gerät → <i>Windows anpassen …</i> (auch <i>Tools → Windows anpassen …</i> oder
    der Knopf <i>Windows anpassen …</i> im Gerätefenster).
3.  Oben eine <b>Vorlage</b> wählen oder die Häkchen einzeln setzen.
4.  Auf <i>Senden</i> klicken. Der Auftrag steht in der Auftragsliste, der Verlauf des Geräts nennt die Auswahl.
5.  Gerät neu starten (Agent-Stick abziehen). Beim Start von Windows werden die Einstellungen umgesetzt.

<b>Vorlagen</b> (setzen die Häkchen; danach lässt sich jedes Häkchen ändern – dann steht
„Vorlage: Player (geändert)“):
•  <b>Player</b>: alles an ausser <i>Kamera</i> und <i>Druckwarteschlange</i>, mit automatischer Anmeldung.
•  <b>Laptop</b>: Store-Apps ausser <i>Kamera</i> und <i>Microsoft Store</i> (auch Kurznotizen, Audiorecorder,
    Schnellhilfe), Nachlauf, Wiederinstallation sperren, Cortana aus; Updates bleiben; Betrieb nur Schnellstart,
    Tipps und Einrastfunktion aus; Datenschutz und Explorer alles (mit Startmenü); Dienste nur Xbox-Dienste und
    Remote-Registrierung; keine automatische Anmeldung.
•  <b>Clean</b>: Windows 11 ohne Werbung – alle Häkchen unter <i>Apps</i> ausser <i>Kamera</i> und
    <i>Microsoft Store</i> (beide bleiben installiert, lassen sich aber dazu wählen), <i>Startmenü: Werbe-Kacheln
    entfernen</i>, Tipps aus, Telemetrie minimal, Werbe-ID, Fehlerberichte und Bing-Suche aus. Updates, Energie,
    Explorer-Ansicht, Dienste und Anmeldung bleiben, wie sie sind.
•  <b>Keine</b>: alle Häkchen weg.

<b>Die Einstellungen:</b>
•  <b>Apps</b>: Store-Apps entfernen (Xbox, Bing (Wetter, News, Bing Search …), Groove/Filme &amp; TV, Solitaire,
    Kontakte, Smartphone-Link, Kamera, Office/Office-Hub, 3D-Viewer/Paint 3D/Mixed Reality, Feedback-Hub/Tipps/Hilfe,
    Microsoft Store, Outlook (neu)/Mail und Kalender, Teams, Clipchamp, Audiorecorder, Kurznotizen, To Do, Journal,
    Karten, Uhr (Wecker), Family, Schnellhilfe, Power Automate, Dev Home, Copilot, Widgets, Werbe-Apps (WhatsApp,
    LinkedIn, Spotify …)) – für alle Benutzer und auch für später angelegte Konten. <b>Nie entfernt</b> werden
    Rechner, Editor, Paint, Fotos, Snipping Tool, Terminal, Edge, Windows-Sicherheit, App-Installer, Codecs,
    Treiber-Apps (NVIDIA, Realtek, Intel, AMD, Dolby …) und Bausteine, die andere Apps brauchen. Dazu: Später
    nachgeladene Apps nochmals entfernen (nach der Anmeldung), Wiederinstallation von Werbe-Apps sperren, OneDrive
    entfernen, Cortana aus.
•  <b>Updates</b>: Windows Update aus, keine Treiber über Windows Update, keine automatischen App-Updates.
•  <b>Betrieb</b>: Energieplan Höchstleistung, Bildschirm und Standby nie ausschalten, Ruhezustand aus,
    Schnellstart aus, Sperrbildschirm aus, Tipps, Vorschläge und Benachrichtigungen aus, Einrastfunktion und
    Anschlagverzögerung aus.
•  <b>Datenschutz</b>: Telemetrie minimal (bei Windows Pro wirkt das wie „Erforderliche Diagnosedaten“),
    Werbe-ID aus, Standort aus, Fehlerberichte aus, Bing-Suche im Startmenü aus.
•  <b>Explorer und Desktop</b>: Dateiendungen anzeigen, versteckte Dateien anzeigen, Explorer öffnet
    „Dieser PC“, Symbole „Dieser PC“ und „Netzwerk“ auf dem Desktop, Suchfeld und Taskansicht aus der Taskleiste,
    Startmenü: Werbe-Kacheln entfernen (Windows 11).
•  <b>Dienste</b>: Windows Search, Xbox-Dienste, SysMain, Remote-Registrierung, Druckwarteschlange – je Häkchen
    gestoppt und auf „Deaktiviert“ gestellt.
•  <b>Anmeldung</b>: <i>Automatische Anmeldung</i> mit Benutzername und Passwort. Ohne beide Angaben lässt sich
    nicht senden. Das Konto muss auf dem Gerät schon vorhanden sein, sonst wird nichts gesetzt (Eintrag im
    Protokoll).
Einstellungen für Benutzer gelten für alle vorhandenen Konten und für neue Konten.

<b>Startmenü von Windows 11 – warum Werbe-Kacheln trotz entfernter Apps:</b> WhatsApp, LinkedIn, Clipchamp,
Adobe Express, Spotify &amp; Co. sind im Startmenü oft nur <b>Platzhalter</b>: Die App ist noch gar nicht
installiert, Windows lädt sie erst beim Klick oder später im Hintergrund. Darum hilft Entfernen allein nicht.
•  <i>Startmenü: Werbe-Kacheln entfernen (Windows 11)</i> ersetzt die angehefteten Kacheln durch Edge, Explorer,
    Einstellungen, Rechner, Editor, Fotos, Paint, Snipping Tool und Terminal (fehlt eine davon, erscheint ihre
    Kachel erst nach der Installation). Wirkt bei der nächsten Anmeldung – für bestehende und neue Benutzer, auch
    bei Windows Pro. Ab Windows 11 24H2 mit dem Update KB5062660 wird die Liste nur einmal gesetzt, danach lässt
    sich wieder selbst anheften; bei älteren Windows 11 setzt Windows sie bei jeder Anmeldung neu. Windows 10:
    ohne Wirkung.
•  <i>Später nachgeladene Apps nochmals entfernen (nach der Anmeldung)</i> legt eine geplante Aufgabe an: 30 min
    nach der ersten Anmeldung werden die gewählten Store-Apps ein zweites Mal entfernt, danach löscht sich die
    Aufgabe selbst (Protokoll wie unten, Abschnitt „Nachlauf“).
•  <i>Wiederinstallation von Werbe-Apps sperren</i>: Die Richtlinie dazu wirkt laut Microsoft nur bei Windows
    Enterprise und Education. Bei Pro und Home wirken die Werte für die stille App-Installation (alle Benutzer)
    und die beiden Häkchen oben. Das Protokoll nennt die Edition.

<b>Passwort:</b> Das Passwort der automatischen Anmeldung liegt danach – wie bei Windows üblich – im
<b>Klartext in der Registrierung</b> (Winlogon). Bis zum nächsten Start steht es im Startskript auf der Disk;
das Skript löscht sich beim Start als Erstes. Im Protokoll, im Log des Auftrags und im Verlauf steht es nie.

<b>Protokoll am Gerät:</b> <tt>C:\\Windows\\Temp\\okula-windows-anpassen.log</tt> – je Einstellung „ok“ oder
„FEHLER“ mit Grund. Ein Fehler hält die übrigen Einstellungen nicht auf.

<b>Gut zu wissen:</b>
•  Das Startskript läuft genau einmal und entfernt sich danach vollständig. Eine vorhandene lokale
    Gruppenrichtlinie bleibt erhalten.
•  Erneut senden vor dem nächsten Start ersetzt die noch nicht umgesetzte Auswahl.
•  Meldung „Ruhezustand bzw. Schnellstart“: Windows starten und mit Shift + „Herunterfahren“ ganz
    herunterfahren, dann erneut senden.
•  Kein Windows auf der Disk (oder BitLocker): Es wird nichts gesendet.
•  Frisch zurückgespieltes Master-Image (Ersteinrichtung steht noch aus): Die Einstellungen greifen erst nach
    der Ersteinrichtung bei einem Windows-Start.
•  Die automatische Anmeldung kann erst beim zweiten Start greifen, wenn sich Windows beim ersten Start schon
    vor dem Ende des Skripts anmeldet.
•  Rückgängig macht das Tool nichts: Apps lassen sich aus dem Microsoft Store neu installieren, Einstellungen
    in Windows zurückstellen.
•  Neuer Agent nötig: Agent-Stick bzw. Netzwerkstart nach dem Update neu erstellen (sonst „Agent zu alt“)."""),

    ("Software installieren", """<big><b>Software installieren</b></big>

Programme aus der <b>Software-Bibliothek</b> des Tools werden auf dem Gerät <b>still und ohne Klicks</b>
installiert – beim ersten Windows-Start, als SYSTEM. Die Liste <i>Software installieren</i> (Häkchen, Suchfeld,
Spalten Programm, Version, Grösse, Status, darunter die Gesamtgrösse) zeigt nur die Bibliothek und steht an drei
Stellen:
•  <i>OS installieren …</i> (Windows) – auch mit <i>Für Master-Image (Audit-Modus)</i>: dann wird im Audit-Modus
    installiert, die Programme landen im Master-Image (Kapitel <i>Windows / Linux installieren</i>).
•  <i>Image zurückspielen …</i> unter <i>Danach anpassen</i> (Kapitel <i>Image zurückspielen</i>).
•  Reiter <i>Automatisierung</i>, Schritt <b>Anpassen</b> – die Auswahl wird mit den übrigen Einstellungen und in
    Vorlagen gespeichert (Kapitel <i>Automatisierung</i>).

<b>Die Software-Bibliothek</b> (<i>Extras → Software-Bibliothek …</i>)
Oben wird geladen, darunter steht direkt die Liste mit Programm, Version, Hersteller, Typ, Parameter,
Rückgabewerte, Status und Grösse (Suchfeld oben rechts). Unter der Liste stehen Typ, Hersteller, Installer und
Status des markierten Eintrags, bei „Parameter fehlt“ zusätzlich <b>Was tun</b>.
•  <i>Ins Tool laden …</i>: einen Installer wählen (<tt>.exe</tt>, <tt>.msi</tt>, <tt>.msp</tt>, <tt>.msu</tt>,
    <tt>.msix</tt>, <tt>.appx</tt>, <tt>.msixbundle</tt>, <tt>.appxbundle</tt>) – von der Server-Disk, einem
    USB-Datenträger oder dem NAS (auch aus <i>Verteilen\\Software</i>). Er wird in die Bibliothek kopiert.
•  <i>Ordner laden …</i>: für Installer, die ihre Dateien daneben brauchen (z. B. <tt>YSUSB_V213_Win</tt> mit
    <tt>setup.exe</tt>). Der ganze Ordner wird kopiert und kommt mit aufs Gerät. Liegen mehrere Installer im
    Ordner, fragt das Tool, welcher es ist.
•  Oder Dateien und Ordner aus dem Dateimanager ins Fenster ziehen.
•  Ein Balken zeigt das Kopieren; <i>Abbrechen</i> lässt nichts Halbes in der Bibliothek zurück.
•  Danach erkennt das Tool den Installer-Typ und trägt Parameter, Rückgabewerte, Programmname, Version und
    Hersteller ein (Abschnitt <i>Erkannte Installer-Typen</i>). Liegt derselbe Inhalt schon in der Bibliothek
    (gleiche SHA-256-Prüfsumme), wird nichts doppelt abgelegt – die Meldung nennt den Eintrag.
•  Sammelordner mit vielen kleinen Werkzeugen (z. B. „System Tools“): als Ordner laden, Art <i>Nur kopieren</i> –
    der Ordner landet auf dem Desktop für alle Benutzer unter <i>Software</i>, installiert wird nichts.
•  <i>Neu erkennen</i> (Knopf unter der Liste oder Rechtsklick auf die Zeile): Erkennung erneut auf den Installer
    anwenden – z. B. für Einträge, die vor einer neueren Version des Tools geladen wurden. Wurden Angaben von Hand
    geändert, fragt das Tool vorher, ob sie überschrieben werden sollen.
•  <i>Löschen</i> (oder Taste Entf): Eintrag mit allen Dateien nach Rückfrage entfernen.
Läuft das Demo-Gerät, zeigt das Fenster die Bibliothek im Demo-Speicher (Kapitel <i>Demo-Gerät</i>).

<b>Status</b>
•  <b>bereit</b>: Installer-Typ erkannt bzw. Parameter hinterlegt – lässt sich ankreuzen.
•  <b>Parameter fehlt</b>: Typ unbekannt oder ohne sicheren stillen Weg (oder bei einem Ordner kein Installer
    gewählt) – nicht wählbar. Unter der Liste steht, was zu tun ist.
•  <b>nur von Hand</b>: lässt sich nicht still installieren (z. B. Programme, die nur für den angemeldeten Benutzer
    installieren) – nicht wählbar.
•  <b>nur kopieren</b>: Ordner auf den Desktop (siehe oben).

<b>Erkannte Installer-Typen</b> (ohne die Datei auszuführen – das Tool liest nur)
•  MSI: <tt>msiexec /i … /qn /norestart</tt>, Name, Version und Hersteller aus der MSI-Datei
•  MSP (Patch): <tt>msiexec /p … /qn /norestart</tt> · MSU (Windows-Update): <tt>wusa.exe … /quiet
    /norestart</tt>, Rückgabewert 2359302 = schon installiert
•  MSIX/APPX und Bündel: für alle Benutzer bereitgestellt (<tt>Add-AppxProvisionedPackage -SkipLicense</tt>);
    nötige Frameworks (z. B. VCLibs) als eigene Einträge davor wählen
•  NSIS: <tt>/S</tt> · electron-builder (NSIS): <tt>/S /allusers</tt> – für alle Benutzer statt nur für SYSTEM
•  Inno Setup: <tt>/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-</tt>
•  InstallShield (MSI): <tt>/s /v"/qn /norestart"</tt>
•  WiX Burn: <tt>/quiet /norestart</tt> · Microsoft-Bootstrapper (VC++ Redistributable, .NET-Runtime):
    <tt>/install /quiet /norestart</tt>, Rückgabewert 1638 = neuere Version schon da
•  Qt Installer Framework ab 4.0 (z. B. Luminex Araneo): <tt>install --root "&lt;Zielordner&gt;"
    --accept-licenses --accept-messages --default-answer --confirm-command</tt>, Zielordner aus dem Installer
    (<tt>C:\\Program Files\\…</tt>)
•  Advanced Installer: <tt>/exenoui /qn /norestart</tt> · InstallAware: <tt>/s</tt> · Wise: <tt>/s</tt>
•  InstallBuilder (BitRock/VMware, z. B. Barco Event Master Toolset): <tt>--mode unattended
    --unattendedmodeui none</tt>
•  Nur erkannt, Parameter fehlt (mit Hinweis): InstallShield mit InstallScript (Antwortdatei nötig), Qt Installer
    Framework vor 4.0, Setup Factory, Clickteam Install Creator, Smart Install Maker, Actual Installer,
    CreateInstall, Ghost Installer, selbstentpackende Archive (IExpress, 7-Zip-SFX, WinRAR-SFX)
•  Squirrel: nur von Hand
Name, Version und Hersteller kommen aus der Versionsinfo des Installers, aus der MSI-Datei, aus den Angaben des
Qt Installer Framework bzw. des App-Pakets, sonst aus dem Dateinamen (ohne „Setup“, „Installer“).

<b>Parameter fehlt – was tun</b>
1.  Eintrag markieren: unter der Liste stehen der erkannte Typ und <i>Was tun</i>.
2.  Bei einem bekannten Typ den genannten Parameter prüfen, sonst in der Herstellerdoku nach „silent install“
    bzw. „unattended“ suchen.
3.  An einer VM testen (Installer mit den Parametern in einer Eingabeaufforderung als Administrator starten – es
    darf kein Fenster erscheinen), dann die Parameter in der Liste eintragen.
4.  Selbstentpackende Archive mit 7-Zip öffnen: liegt darin ein bekannter Installer, den entpackten Ordner mit
    <i>Ordner laden …</i> laden.

<b>Parameter hinterlegen</b>
1.  <i>Extras → Software-Bibliothek …</i> öffnen.
2.  Zeile markieren und in die Zelle <i>Programm</i>, <i>Version</i>, <i>Hersteller</i>, <i>Parameter</i> oder
    <i>Rückgabewerte</i> klicken, Wert eintragen, Enter – gespeichert wird sofort. <i>Parameter</i> sind die Angaben für die stille
    Installation (z. B. <tt>/S</tt>), <i>Rückgabewerte</i> die Werte für „erfolgreich“ (Standard „0, 3010“;
    3010 = Neustart nötig).
3.  <i>Art</i> (still installieren, nur kopieren, nur von Hand) und bei Ordnern den <i>Installer</i>: Zeile markieren,
    <i>Bearbeiten …</i>, <i>Speichern</i>.
Bei MSI ergänzt das Tool <tt>msiexec /i</tt> und den Dateinamen. <tt>{ordner}</tt> steht für den Ordner des
Installers, z. B. für eine Antwortdatei.

<b>Neue Version</b>
Gleicher Programmname, andere Version (z. B. <tt>vlc-3.0.24-win64.exe</tt> nach <tt>vlc-3.0.23-win64.exe</tt>):
Die neu geladene Version übernimmt Parameter, Art und Rückgabewerte der vorigen; der Hinweis steht in der Liste
(Maus über der Zeile). Die alte Version bleibt in der Bibliothek, bis sie gelöscht wird. Eine gespeicherte Auswahl
(Automatisierung, Vorlagen) nimmt nach dem Löschen der alten Version die neueste; gibt es das Programm gar nicht
mehr, steht es in der Liste als „fehlt in der Bibliothek“ und wird beim Auftrag übersprungen (Eintrag im Log).

<b>Ablage</b>
Auf dem NAS im Ordner <i>Software-Bibliothek</i> neben <i>Verteilen</i> – gilt für alle Tool-Rechner gleich.
Je Programm ein Unterordner (z. B. <tt>vlc-3.0.24</tt>) mit dem Installer bzw. dem geladenen Ordner und einer
versteckten Beschreibung. Dort nichts von Hand ändern – laden und löschen nur über das Fenster.
Der Ordner <i>Verteilen\\Software</i> gehört nur zu <i>Ordner senden</i> und wird für <i>Software installieren</i>
weder gelesen noch beschrieben. Die versteckten Beschreibungen <tt>.…okula.json</tt>, die frühere Versionen dort
angelegt hatten, entfernt das Tool beim Verbinden mit dem NAS (Meldung in der Statuszeile); sonst bleibt dort alles,
wie es ist.

<b>Ablauf am Gerät</b>
1.  Die gewählten Programme kommen mit auf die Disk (<tt>C:\\ProgramData\\Okula\\Software</tt>), dazu ein
    einmaliges Startskript wie bei <i>Windows anpassen</i>.
2.  Beim ersten Windows-Start (bei einem Master-Image nach der Ersteinrichtung) legt das Startskript eine
    einmalige geplante Aufgabe an. Diese installiert die Programme nacheinander still als SYSTEM – auch lange
    Installationen werden nicht abgebrochen. Kurze Installationen sind fertig, bevor die Anmeldung erscheint.
3.  Danach werden die Installer gelöscht. Meldet ein Programm „Neustart nötig“ (3010), startet das Gerät nach
    dem letzten Programm <b>einmal</b> neu.
Ein Fehler bei einem Programm hält die übrigen nicht auf.

<b>Protokoll am Gerät:</b> <tt>C:\\Windows\\Temp\\okula-software.log</tt> – je Programm Start, Ende,
Rückgabewert und „ok“ oder „FEHLER“. Im Tool nennt das Log des Auftrags die gewählten Programme, der Verlauf des
Geräts z. B. „Software: VLC media player 3.0.24, … (wird beim ersten Start installiert)“. Ob die Installation am
Gerät geklappt hat, zeigt nur das Protokoll am Gerät.

<b>Gut zu wissen:</b>
•  Ein Installer, der trotz Parametern auf eine Eingabe wartet, wird nach 60 Minuten beendet (Eintrag im
    Protokoll) – Parameter prüfen.
•  Erneut zurückspielen bzw. senden vor dem ersten Start ersetzt die noch nicht installierte Auswahl.
•  Direktinstallation: Dateien über 4 GB gehen nicht (Setup-Partition FAT32).
•  Neuer Agent nötig: Agent-Stick bzw. Netzwerkstart nach dem Update neu erstellen (sonst „Agent zu alt“)."""),

    ("Inventar, Garantie, Windows 11", """<big><b>Inventar, Garantie und Windows 11</b></big>

Das Tool liest bei jedem Verbinden die Angaben des Geräts (Inventar).
Die Angaben stehen im Gerätefenster unter <i>Übersicht</i> und <i>Disks</i>.
<i>Inventar neu einlesen</i> holt sie neu, zum Beispiel nach einem Disk-Tausch.

<b>Windows 11</b> (<i>Übersicht → Windows 11</i>)
•  ✔ Das Gerät erfüllt die Anforderungen von Windows 11.
•  ✖ Nicht tauglich, zum Beispiel wegen TPM 1.2 oder einem zu alten Prozessor. Der Grund steht daneben.
•  ? Noch unbekannt: Agent-Stick neu erstellen und <i>Inventar neu einlesen</i>.

<b>Garantie</b> (<i>Übersicht → Garantie bis</i>)
•  <span background="#2e7d32" foreground="#ffffff"> grün </span>: Die Garantie läuft noch.
•  <span background="#fff3b0" foreground="#6d5200"> gelb </span>: Die Garantie läuft in den nächsten 90 Tagen ab.
•  <span background="#c62828" foreground="#ffffff"> rot </span>: Die Garantie ist abgelaufen.
<i>Beim Hersteller abfragen</i> holt das Datum über die Seriennummer. Das geht bei Dell, HP und Lenovo.
Für Dell und HP braucht es einen Schlüssel vom Hersteller: <i>Menü → Einstellungen … → Garantie-Abfrage</i>.
Ohne Schlüssel, ohne Internet oder bei einem anderen Hersteller: mit <i>Von Hand …</i> das Datum eintragen.

<b>Inventar exportieren</b>
<i>Menü → Inventar exportieren (CSV/PDF) …</i> oder Rechtsklick auf einen Ordner bzw. ein Gerät
→ <i>Inventar exportieren …</i>
1.  Umfang wählen: alle Geräte, einen Ordner (mit Unterordnern) oder einzelne Geräte (Häkchen setzen).
2.  Format wählen: CSV (für Excel) und/oder PDF.
    Beim PDF: <i>je Ordner eine Datei</i> oder <i>alle Geräte in einer Datei</i>.
3.  Speicherort wählen und auf <i>Exportieren</i> klicken.
Der Windows-Schlüssel kommt standardmässig nicht mit. Auf Wunsch nur verdeckt (XXXXX-…-ABCDE)."""),

    ("BIOS", """<big><b>BIOS-Einstellungen lesen, vergleichen und ändern</b></big>

Reiter <i>BIOS</i> im Gerätefenster. Das Gerät muss mit dem Agent verbunden sein (neuer Agent-Stick bzw.
Netzwerkstart mit dem aktuellen Tool).

<b>Lesen</b>
1.  Gerätefenster öffnen, Reiter <i>BIOS</i> wählen. Beim ersten Mal liest das Tool von selbst.
2.  Später: <i>BIOS lesen</i>. Der Stand wird beim Gerät gespeichert und bleibt sichtbar, auch wenn das
    Gerät aus ist.
•  <b>Grundangaben</b> gibt es bei jedem Gerät: BIOS-Version, Boot-Modus (UEFI oder BIOS-Modus), Secure Boot,
    TPM, BIOS-Passwort gesetzt ja/nein, UEFI-Startreihenfolge.
•  <b>Einstellungen</b> (z. B. „PXE Internal IPV4 NIC boot“, „Fast Boot“, „Wake On LAN“) gibt es nur bei
    Modellen, die sie an Linux melden: HP, Dell und Lenovo Business-Geräte. Sonst steht „nur Grundangaben“.
•  Ältere Modelle (z. B. HP EliteBook 850 G1) melden die Schnittstelle zwar, liefern aber unlesbare
    Einträge. Diese blendet das Tool aus; unter <i>Schnittstelle</i> steht dann „liefert unlesbare Daten“.
    Die Grundangaben (z. B. BIOS-Version) lassen sich trotzdem vergleichen.

<b>Vergleichen</b> – zum Beispiel ein Gerät, das funktioniert, mit einem, das nicht funktioniert
1.  Bei beiden Geräten einmal <i>BIOS lesen</i>.
2.  Beim zweiten Gerät unter <i>Vergleichen mit</i> das erste wählen.
3.  <i>Nur Unterschiede</i> zeigt nur, was verschieden ist – rot. Wichtige Einstellungen für Start,
    Netzwerk und Secure Boot stehen oben und fett.
•  <i>Einstellung suchen</i> filtert nach Namen und Werten.
•  <i>Als CSV speichern …</i> speichert die Liste für Excel (bzw. den Vergleich).

<b>Ändern</b>
1.  Einstellung doppelklicken (oder wählen und <i>Ändern …</i>).
2.  Neuen Wert wählen, falls im BIOS ein Passwort gesetzt ist, das BIOS-Admin-Passwort eingeben.
3.  <i>Setzen</i>. Die Änderung gilt nach dem nächsten Neustart; die Grundangaben zeigen „warten auf Neustart“.
•  Das Passwort geht verschlüsselt an den Agent und wird nie gespeichert.
•  Vorsicht beim Boot-Modus: Ein Windows im BIOS-Modus startet im UEFI-Modus nicht mehr (und umgekehrt).
    Secure Boot verlangt bei HP beim nächsten Start eine Bestätigung am Gerät.
•  Jede Änderung steht im Verlauf des Geräts."""),

    ("Hardware-Test", """<big><b>Hardware prüfen (Hardware-Test)</b></big>

Reiter <i>Hardware-Test</i> im Gerätefenster. Das Gerät muss mit dem Agent verbunden sein (neuer Agent-Stick bzw.
Netzwerkstart mit dem aktuellen Tool). Geprüft wird nur lesend: Daten, Windows und BIOS bleiben unverändert.

<b>Test starten</b>
1.  Unter <i>Disks</i> die zu prüfenden Disks anhaken (alle internen sind vorgewählt, USB-Sticks nicht).
2.  <i>Schnelltest (≈ 5 min)</i>: Akku, Temperaturen, SMART-Selbsttest kurz, Arbeitsspeicher (Teil),
    1 Minute CPU-Last, Netzwerk-Durchsatz zum Server.
3.  <i>Gründlich (≈ 1–3 h)</i>: zusätzlich SMART-Selbsttest lang, jeden Sektor der Disk lesen,
    15 Minuten CPU-Last, grösserer Arbeitsspeicher-Test.
4.  Der Fortschritt steht im Reiter <i>Aufträge</i> und am Bildschirm des Geräts. Abbrechen geht dort jederzeit.
•  Während des Tests sind die gewählten Disks für andere Aufträge gesperrt.

<b>Ergebnis</b>
•  Je Bereich <span foreground="#2e7d32">✔ in Ordnung</span>, <span foreground="#b26a00">⚠ Achtung</span>,
    <span foreground="#c62828">✖ Fehler</span> oder – nicht geprüft (z. B. kein Akku, Disk ohne Selbsttest).
•  Pfeil bzw. Doppelklick zeigt die Einzelheiten (z. B. Betriebsstunden, Abnutzung, Temperatur, Takt).
•  <i>Test vom</i> wählt einen früheren Test (die letzten 10 bleiben gespeichert). Jeder Test steht im Verlauf.
•  <i>Protokoll als PDF …</i>: Prüfprotokoll mit Gerät, Seriennummer, Ergebnissen und Unterschriftsfeld,
    zum Beispiel für die Übergabe oder den Verkauf eines Geräts.

<b>Was die Bereiche bedeuten</b>
•  <i>Akku</i>: heutige Kapazität im Vergleich zu neu – unter 80 % Achtung, unter 60 % Fehler.
•  <i>Disk</i>: Selbsttest der Disk und wichtige Werte (umgeschriebene oder unlesbare Sektoren, Abnutzung).
•  <i>Oberfläche</i>: Jeder Sektor wird gelesen; Lesefehler bedeuten: Disk ersetzen.
•  <i>Arbeitsspeicher</i>: Teilprüfung im laufenden System. Ein Test ohne Befund schliesst Defekte nicht ganz aus.
•  <i>CPU unter Last</i>: Temperatur, Takt und Drosselung – drosselt das Gerät, Lüfter und Wärmeleitpaste prüfen.
    Dazu Hardware-Fehler des Prozessors (Machine Check) aus dem Kernel-Protokoll, zusammengefasst nach CPU und Bank:
    gelb, wenn seit dem Start des Geräts Hardware-Fehler gemeldet wurden; rot, wenn während der Last neue dazukommen
    oder ein Fehler nicht korrigiert wurde. Abhilfe: BIOS-Update, sonst Prozessor bzw. Mainboard prüfen.
•  <i>Netzwerk</i>: tatsächlicher Durchsatz zum Server (ohne Bandbreitengrenze) und Verbindungsgeschwindigkeit."""),

    ("Windows / Linux installieren", """<big><b>Betriebssystem installieren</b></big>

<b>1. ISO-Datei hinzufügen (einmal pro Version)</b>
•  <i>Tools → ISO hinzufügen …</i> oder die Datei rechts in den Reiter <i>Images</i> ziehen.
•  Das Tool erkennt, was in der ISO steckt, und sortiert sie unter <i>Betriebssysteme</i> ein.

<b>2. Direkt auf ein Gerät installieren</b>
1.  Gerät mit dem Agent starten.
2.  Auf <i>OS installieren …</i> klicken.
3.  ISO und Zieldisk wählen.
4.  Einstellungen wählen: Benutzer, Passwort, bei Windows die Edition.
    Bei Linux auch die Software: zum Beispiel Desktop, SSH-Server (Fernzugriff) oder weitere Pakete.
    Bei Debian gibt es die ganze Auswahl wie im Debian-Installer.
    Bei Windows unter <i>Windows-Anpassung</i> die Liste <i>Software installieren</i>: Programme aus der
    Software-Bibliothek ankreuzen – sie werden beim ersten Start still installiert, mit
    <i>Für Master-Image (Audit-Modus)</i> im Audit-Modus, damit sie im Master-Image landen
    (Kapitel <i>Software installieren</i>).
5.  Starten. Das Gerät startet danach neu und installiert selbständig.
    Am Gerät wird nichts gefragt. Was nicht ausgewählt ist, wird nicht installiert.
    Nur bei VMs: <i>Vorher Snapshot</i> (Standard an) – direkt vor der Installation entsteht ein Snapshot der
    Disk (Kapitel <i>Virtuelle Maschinen</i>). Schlägt er fehl, startet die Installation nicht.

Der <b>Computername</b> ist immer der Gerätename im Tool. Für einen anderen Namen das Gerät umbenennen.
Windows erlaubt nur 15 Zeichen ohne Sonderzeichen. Der Dialog zeigt, wie der Name ankommt.

<b>Windows-Konto</b> (<i>Lokales Konto statt Microsoft-Konto</i>, Feld <i>Benutzername</i>, vorbelegt mit „Okula“)
•  Namen, die Windows schon für Gruppen oder eingebaute Konten verwendet, gehen nicht – zum Beispiel
    „Benutzer“, „Administrator“, „Gast“, „Jeder“, „Users“ oder „System“. Das Tool zeigt dann eine Meldung
    und startet nicht. Ebenso: mehr als 20 Zeichen, Punkt am Ende, Zeichen wie / \\ [ ] : ; | = , + * ? &lt; &gt; "
•  Benutzername leer: Windows fragt beim ersten Start selbst nach einem Konto (die Einrichtung hält dort an).
•  Gilt auch für den Boot-Stick (Kapitel <i>Sticks erstellen</i>).

<b>Für Master-Image (Audit-Modus)</b> (Häkchen, nur bei Windows, Standard aus)
•  Windows wird genauso ohne Eingriff installiert, startet danach aber im <b>Audit-Modus</b>
    (eingebauter Administrator). Kein Konto, kein Computername, kein Windows-Schlüssel – diese Felder sind
    ausgegraut. Region Schweiz, Datenschutz-Fragen und BitLocker wirken weiterhin.
•  Beim ersten Start im Audit-Modus entfernt Windows die Setup-Partition, vergrössert C: und löscht die
    Antwortdatei des Tools (<tt>C:\\Windows\\Panther\\unattend.xml</tt>), damit sie nicht ins Image kommt.
•  Danach: einrichten (Updates, Treiber, Programme), dann Sysprep:
    <tt>C:\\Windows\\System32\\Sysprep\\sysprep.exe /generalize /oobe /shutdown</tt>
    Windows nicht mehr starten, mit dem Agent-Stick <i>Disk-Image erstellen …</i> und das Image als Master
    markieren (Kapitel <i>Master-Image</i>). Das Log des Auftrags nennt diese Schritte ebenfalls.
•  Bei einer VM vor Sysprep im Reiter <i>Snapshots</i> einen Snapshot erstellen (<i>Snapshot erstellen …</i>).

<b>Fehler am Gerät</b> (Windows)
•  Vor dem Neustart löscht der Agent alte Daten auf den neuen Partitionen (Anfang und Ende) und prüft die
    Windows-Partition direkt auf der Disk. Kommt das Geschriebene dort nicht an, bricht der Auftrag ab mit
    „Schreiben auf die Disk wird nicht übernommen – Disk prüfen“. Das Gerät startet dann nicht neu.
•  Die Setup-Umgebung sucht die Windows-Partition über eine Markierungsdatei, sonst über die Bezeichnung
    „OKULAWIN“ (nur wenn genau ein Laufwerk sie trägt). Ein Laufwerk mit einem alten Windows wird nie formatiert.
•  Wird keine gefunden, öffnet sich der Editor mit dem Protokoll <tt>okula\\install.log</tt> auf der Setup-Partition
    „OKULASETUP“: oben ein Hinweis, darunter der Ablauf, die Laufwerksliste (<tt>diskpart</tt>) und je Laufwerk
    Bezeichnung, Inhalt und ob eine Markierung <tt>okula-….target</tt> darauf liegt.
•  Editor nicht gleich schliessen: Danach schaltet sich das Gerät aus. Für eine Eingabeaufforderung vorher
    Shift+F10 drücken; ohne Wirkung im Editor <i>Datei → Öffnen</i>, Dateityp „Alle Dateien“,
    <tt>X:\\Windows\\System32\\cmd.exe</tt> mit der rechten Maustaste öffnen.
•  Für die Fehlersuche das Protokoll fotografieren oder später von der Setup-Partition kopieren.

Direkt installieren geht mit Windows 10/11, Ubuntu Desktop ab 24.04, Debian und Fedora/Rocky/Alma.
Bei anderen Systemen zeigt das Tool den Grund. Dann hilft ein Boot-Stick (Kapitel <i>Sticks erstellen</i>).

<b>Windows-Schlüssel</b>
•  Viele Geräte haben den Schlüssel im BIOS. Das Tool liest ihn automatisch.
•  Ein eigener Schlüssel lässt sich im Gerätefenster unter <i>Übersicht → Windows-Schlüssel</i> hinterlegen.
•  Bei der Installation wird dieser Schlüssel verwendet."""),

    ("Sticks erstellen", """<big><b>USB-Sticks erstellen</b></big>

<b>Boot-Stick aus ISO</b> (wie das Programm „Rufus“)
•  Rechts eine ISO wählen und auf <i>Boot-Stick aus ISO …</i> klicken.
•  Mit dem Stick lässt sich Windows oder Linux an jedem Computer installieren.
•  Bei Windows gibt es Einstellungen: lokales Konto statt Microsoft-Konto, Region Schweiz.
    Für den <i>Benutzernamen</i> gelten dieselben Regeln wie beim Installieren
    (Kapitel <i>Windows / Linux installieren</i>, „Benutzer“ oder „Administrator“ gehen nicht).
•  Altes Gerät, das Windows 11 nicht erfüllt? Microsoft rät ab (keine Updates garantiert).
    Wer es trotzdem will: Häkchen <i>Trotzdem installieren</i> bzw. beim Stick
    <i>Auch für nicht unterstützte Hardware</i>. Das Gerät bekommt dann einen Vermerk.
•  Das Tool kann den Stick vorher testen. So fallen gefälschte Sticks auf.

<b>Restore-Stick aus Image</b>
Der Stick enthält ein Image und stellt ein Gerät auch <b>ohne Netzwerk</b> wieder her.
1.  Rechts ein Image wählen und auf <i>Restore-Stick aus Image …</i> klicken.
2.  Am Gerät vom Stick starten (Boot-Menü, Kapitel <i>Gerät verbinden</i>).
3.  Auf dem Bildschirm die Zieldisk wählen und zur Bestätigung ihren Namen eintippen.
4.  Der Stick prüft das Image, spielt es zurück und fragt am Ende: neu starten oder herunterfahren.
    Den Stick erst abziehen, wenn das Gerät aus ist (bzw. beim Neustart der Bildschirm dunkel).

<b>Agent-Stick</b>
•  <i>Menü → Agent-USB-Stick erstellen …</i> (Kapitel <i>Erste Schritte</i>).

Bei allen Sticks gilt: Der Stick wird dabei gelöscht.
<b>Stick erst abziehen, wenn „Stick fertig“ erscheint.</b> Am Ende erscheint ein Fenster
<i>Agent-Stick fertig</i>, <i>Restore-Stick fertig</i> bzw. <i>Boot-Stick fertig</i> („Der Stick kann jetzt
abgezogen werden.“). Agent- und Restore-Stick werden vorher geprüft, beim Restore-Stick auch das Image auf der
Datenpartition. Ging etwas schief (z. B. Stick zu früh abgezogen), erscheint rot <i>Stick nicht fertig</i> mit
dem Grund: Stick nicht verwenden – neu erstellen."""),

    ("USB klonen", """<big><b>USB-Stick oder externe Festplatte klonen</b></big>

Klonen bedeutet: Ein Datenträger wird komplett auf einen anderen kopiert.
Mit allen Partitionen, Dateien und – falls vorhanden – mit der Startfähigkeit.

<b>Ablauf:</b>
1.  Beide Datenträger am Server einstecken.
2.  <i>Extras → USB klonen …</i> öffnen.
3.  <b>Quelle</b> wählen: Von hier wird kopiert. Die Quelle wird nur gelesen.
4.  <b>Ziel</b> wählen: Hierhin wird kopiert. <b>Alles auf dem Ziel wird gelöscht.</b>
5.  Art wählen:
    •  <i>Nur belegte Bereiche</i>: schneller. Empfohlen.
        Das Ziel darf sogar kleiner sein, wenn alle Partitionen darauf Platz haben.
    •  <i>Alles 1:1</i>: kopiert jeden Sektor. Für verschlüsselte oder unbekannte Datenträger.
        Danach ist auch ein Vergleich möglich.
6.  Auf <i>Klonen</i> klicken und bestätigen.

Das Tool zeigt, ob das Ziel gross genug ist, wie schnell es kopiert und wie lange es noch dauert.
<i>Abbrechen</i> stoppt den Vorgang. Das Ziel ist dann aber unvollständig.

<b>Gut zu wissen:</b>
•  Nach dem Klonen haben beide Datenträger dieselben Kennungen.
    Nicht gleichzeitig am selben Windows-PC anschliessen.
•  Ist das Ziel grösser, bleibt der Rest frei und lässt sich später nutzen."""),

    ("USB formatieren", """<big><b>USB-Stick oder externe Festplatte formatieren</b></big>

<b>Ablauf:</b>
1.  Datenträger am Server einstecken.
2.  <i>Extras → USB formatieren …</i> öffnen.
3.  Datenträger wählen. Darunter steht, was jetzt darauf ist.
4.  Dateisystem wählen (siehe unten). Das Tool schlägt eines vor.
5.  Auf Wunsch einen Namen eingeben.
6.  Auf <i>Formatieren</i> klicken und bestätigen. <b>Alle Daten gehen verloren.</b>

<b>Welches Dateisystem wofür?</b>
•  <b>FAT32</b>: läuft fast überall (Windows, Mac, Linux, TV, Auto). Dateien höchstens 4 GB.
•  <b>exFAT</b>: für grosse Dateien. Windows, Mac, Linux und viele TVs. Gut zum Austauschen.
•  <b>NTFS</b>: Windows-Standard. Der Mac kann nur lesen.
•  <b>ext4</b>, <b>Btrfs</b>, <b>XFS</b>, <b>F2FS</b>, <b>ext3</b>, <b>ext2</b>: für Linux.
•  <b>HFS+</b>: für ältere Macs.
•  <b>UDF</b>: für grosse Dateien, Windows, Mac und Linux.
•  <b>FAT16</b>: für sehr alte Geräte, nur bis 4 GB.
•  <b>Kein Dateisystem</b>: macht den Datenträger nur leer.

Im Zweifel: bis 32 GB <b>FAT32</b>, darüber <b>exFAT</b>.

<b>Partitionsschema</b>
•  <b>MBR</b>: passt überall. Für Datenträger bis 2 TB.
•  <b>GPT</b>: für Datenträger über 2 TB und moderne Computer.

<b>Vorher</b> (Option)
•  <i>Schnelltest</i>: erkennt gefälschte Sticks, die mehr Platz vortäuschen.
•  <i>Mit Nullen überschreiben</i>: alte Daten sind danach sicher weg. Dauert lange.
•  <i>Vollständiger Test</i>: prüft jeden Block. Dauert sehr lange."""),

    ("Images verwalten", """<big><b>Images und ISOs verwalten (Reiter „Images“)</b></big>

Neue Disk-Images landen unter „Nicht einsortiert“. ISOs stehen unter „Betriebssysteme“.
Alle Aktionen über Rechtsklick.

<b>Ordner</b>
•  <i>Neuer Ordner …</i>, <i>Umbenennen …</i>, <i>Löschen (nur leer)</i>. Höchstens 3 Ebenen.
•  Images mit der Maus in einen Ordner ziehen. <i>Nach „Nicht einsortiert“</i> nimmt sie zurück.

<b>Disk-Image</b>
•  <i>Image prüfen …</i>: liest das Image auf dem NAS und vergleicht die Prüfsummen. Nichts wird verändert,
    kein Gerät nötig. Ordner: <i>Alle Images im Ordner prüfen …</i> (mit Unterordnern, auch „Nicht einsortiert“).
    Fortschritt und Restzeit stehen in einem eigenen Fenster, <i>Abbrechen</i> beendet die Prüfung.
    Spalte <i>Geprüft</i>: <span background="#2e7d32" foreground="#ffffff"> ✔ Datum </span> in Ordnung,
    <span background="#c62828" foreground="#ffffff"> ✖ beschädigt </span> (Maus darüber: welche Datei), leer = nie geprüft.
    Ein beschädigtes Image lässt sich trotzdem zurückspielen; vorher wird nochmals geprüft.
•  <i>Als Master-Image markieren</i> bzw. <i>Master-Markierung entfernen</i> (Stern ★).
•  <i>Restore-Stick aus Image …</i>: Kapitel <i>Sticks erstellen</i>.
•  <i>Umbenennen …</i> und <i>Löschen …</i> Gelöschte Images sind endgültig weg (kein Papierkorb).

<b>ISO</b>
•  <i>Details und Prüfsummen …</i>: Version, Edition und Prüfsummen der ISO.
•  <i>Boot-Stick erstellen …</i> und <i>Auf Gerät installieren …</i>
•  <i>ISO hinzufügen …</i>: neue ISO aufnehmen.

<b>Aktualisieren</b>
<i>Tools → Images aktualisieren</i> (F5) liest die Liste neu vom NAS,
zum Beispiel nachdem Dateien direkt auf das NAS kopiert wurden."""),

    ("Anzeigen im Fenster", """<big><b>Was die Anzeigen bedeuten</b></big>

<b>Oben rechts: Serverlast</b>
•  <b>CPU</b>: wie stark der Prozessor arbeitet.
•  <b>RAM</b>: wie viel Arbeitsspeicher belegt ist.
•  <b>LAN</b>: wie viel über das Netzwerk geht. ↓ empfangen, ↑ gesendet.
    Steht in der LAN-Kurve „begrenzt: 300 Mbit/s“, ist die Bandbreite gerade begrenzt
    (Kapitel <i>Erste Schritte</i>, Abschnitt 4). Die Restzeit der Aufträge richtet sich danach.
•  Die Kurve zeigt die letzte Minute. Über 90 % wird die Zahl rot.
•  Mit der Maus darüberfahren zeigt mehr Details.

<b>Spalten in den Listen</b>
•  In <i>Geräte</i>, <i>Images</i>, <i>Dateien</i>, <i>Backups</i> und in den Tabellen des Gerätefensters
    (Aufträge, Disks, Images, Backups, Netzwerk, Verlauf) lässt sich jede Spalte am rechten Rand ihres Titels
    mit der Maus breiter oder schmaler ziehen.
•  Das Tool merkt sich die Breiten je Liste, auch nach einem Neustart. Nicht verstellte Spalten passen sich
    dem Inhalt an.

<b>NAS-Zeile</b>
•  <span foreground="#2e7d32">●</span> grün: NAS ist verbunden. Daneben steht der freie Speicher.
•  <span foreground="#c62828">●</span> rot: NAS ist nicht verbunden. Auf das Zahnrad klicken.

<b>Reiter rechts</b>
•  <i>Images</i>: alle Disk-Images und ISO-Dateien, in Ordnern sortiert (Kapitel <i>Images verwalten</i>).
•  <i>Dateien</i>: die Dateien auf dem NAS, wie in einem Datei-Manager.
    Dateien und Ordner lassen sich aus dem Datei-Manager hineinziehen. Dann werden sie auf das NAS kopiert.
    So kommen zum Beispiel Clonezilla-Images von einer externen Festplatte auf das NAS.
•  <i>Backups</i>: alle Datei-Backups, nach Gerät sortiert, mit Suche.

<b>Fortschritt</b>
In der Geräteliste steht bei jedem Gerät ein Balken mit Prozent und Restzeit.
•  <span background="#2e7d32" foreground="#ffffff"> grün </span>: Der Auftrag läuft.
•  <span background="#c62828" foreground="#ffffff"> rot </span>: Der Auftrag ist fehlgeschlagen. Daneben steht, bei wie viel Prozent.
    Den Grund zeigt das Gerätefenster unter <i>Aufträge</i>. Der rote Balken bleibt, bis der nächste Auftrag startet.

<b>Spalte „Auto“ und Status der Automatisierung</b>
•  Häkchen gesetzt: Die Automatisierung ist eingeschaltet. Beim Setzen erscheint zuerst eine Rückfrage
    mit allem, was gelöscht und aufgesetzt wird (Kapitel <i>Automatisierung</i>).
•  Häkchen grau: Alles ist pausiert (Stopp-Knopf ■ ist rot).
•  <i>startet in 25 s</i>: Countdown läuft. Am Gerät bricht Esc ab.
•  <i>wartet (Platz 2)</i>: Es laufen schon so viele Geräte wie erlaubt. Das Gerät kommt gleich dran.
•  <i>Schritt 2/5: Image zurückspielen</i>: Die Automatisierung arbeitet.
•  <i>wieder aktiv in 2 Tagen 5 h</i>: Die Automatisierung ist fertig und schaltet sich nach 3 Tagen wieder ein.
•  <span background="#c62828" foreground="#ffffff"> rot </span>: Es gab einen Fehler. Details im Gerätefenster.

<b>Stern ★ bei Images</b>
Das Image ist als Master-Image markiert.

<b>Ordner „Virtuelle Maschinen“ in der Geräteliste</b>
Die VMs auf dem Server. Statt „nicht verbunden“ steht der Zustand der VM: <i>aus</i>, <i>läuft</i> oder
<i>läuft – Agent verbunden</i> (Kapitel <i>Virtuelle Maschinen</i>).

<b>Bereich „Demo (lokal, nicht auf dem NAS)“</b>
Erscheint nur bei eingeschaltetem Demo-Gerät: Images des DEMO-PC im Demo-Speicher (Kapitel <i>Demo-Gerät</i>).

<b>Spalte „Geprüft“ bei Images</b>
•  ✔ mit Datum: Bei der letzten Prüfung war das Image in Ordnung.
•  ✖ beschädigt: Eine Datei stimmt nicht. Die Maus über der Zeile zeigt, welche.
•  leer: noch nie geprüft. Rechtsklick → <i>Image prüfen …</i> (Kapitel <i>Images verwalten</i>).

<b>Windows 11 und Garantie</b>
Kapitel <i>Inventar, Garantie, Windows 11</i>."""),

    ("Neuer Rechner", """<big><b>Das Tool auf einen neuen Rechner umziehen</b></big>

Alles, was das Tool weiss, lässt sich in <b>eine Datei</b> speichern.
So muss auf einem neuen Rechner nichts von vorne eingerichtet werden.

<b>Auf dem alten Rechner:</b>
1.  <i>Menü → Einstellungen exportieren …</i> öffnen.
2.  Auswählen, was mitkommen soll. Empfohlen: alles.
    •  NAS-Verbindung und Einstellungen
    •  Geräte mit Ordnern, Verlauf, Notizen und Windows-Schlüsseln
    •  Agent-Schlüssel: Dann funktionieren alle bisherigen Agent- und Restore-Sticks weiter.
    Die Vorlagen der Automatisierung kommen mit den Einstellungen mit.
3.  Auf <i>Exportieren …</i> klicken und die Datei speichern, zum Beispiel auf einem USB-Stick.

<b>Auf dem neuen Rechner:</b>
1.  Das Tool installieren (<tt>sudo ./install.sh</tt>).
2.  <i>Menü → Einstellungen importieren …</i> öffnen und die Datei wählen.
3.  Prüfen, was übernommen wird, und auf <i>Importieren</i> klicken. Das Tool startet neu.
4.  <i>Menü → NAS-Verbindung …</i>: einmal das <b>Passwort</b> eingeben und auf <i>Einhängen</i> klicken.
5.  Für die Garantie-Abfrage die Schlüssel neu eingeben (<i>Menü → Einstellungen …</i>).

<b>Gut zu wissen:</b>
•  NAS-Passwort und Garantie-Schlüssel sind aus Sicherheitsgründen nicht in der Datei.
•  Images, Backups und ISOs liegen auf dem NAS und sind sofort wieder da.
•  Die Datei sicher aufbewahren wie ein Passwort, denn sie enthält Schlüssel.
•  Vorhandene Daten auf dem neuen Rechner werden vor dem Import gesichert.

<b>Nur die NAS-Verbindung</b>
Im NAS-Fenster gibt es <i>Exportieren …</i> und <i>Importieren …</i>
Damit kommen nur die NAS-Einstellungen mit (ohne Passwort)."""),

    ("Probleme lösen", """<big><b>Wenn etwas nicht klappt</b></big>

<b>Das Gerät erscheint nicht im Tool</b>
•  Ist das Gerät am Netzwerkkabel? WLAN geht nicht.
•  Sind Gerät und Server im selben Netzwerk?
•  Firewall auf dem Server: Ports freigeben (Kapitel <i>Erste Schritte</i>).
•  Startet das Gerät wirklich vom Stick? Im Boot-Menü den USB-Stick wählen.

<b>Aufträge sind langsam</b>
•  Bandbreite in <i>Menü → Einstellungen …</i> prüfen: Ist <i>Bandbreite begrenzen</i> angehakt, teilen sich
    alle laufenden Aufträge diesen Wert. Zeigt die LAN-Kurve „begrenzt: …“, gilt die Grenze gerade.
•  Mehrere Aufträge gleichzeitig teilen sich auch ohne Grenze das Netzwerk und das NAS.

<b>Netzwerkstart klappt nicht</b>
•  Gerätefenster → <i>Netzwerk</i> → <i>Netzwerkstart-Protokoll</i> zeigt, bis wohin der Start kam.
•  „keine Netzwerkstart-Anfrage“: im BIOS den Netzwerkstart (PXE) einschalten, Kabel prüfen, beim Start
    „Netzwerk“ wählen.
•  „nicht freigeschaltet“: oben im Reiter den Schalter <i>Netzwerkstart</i> einschalten.
•  „Übertragung abgebrochen“: oft lehnt Secure Boot die Datei ab – Netzwerkstart neu vorbereiten
    (<i>Tools → Netzwerkstart (PXE) …</i>), sonst Secure Boot im BIOS prüfen.

<b>Das NAS ist rot</b>
•  Ist das NAS eingeschaltet?
•  Stimmen Benutzer und Passwort? <i>Menü → NAS-Verbindung … → Verbindung testen</i>.

<b>Windows lässt sich nicht sichern oder zurückspielen</b>
•  Meldung „Ruhezustand bzw. Schnellstart“: Windows starten und ganz herunterfahren
    (Shift-Taste gedrückt halten + „Herunterfahren“).
•  Mit BitLocker verschlüsselte Disks kann das Tool nur 1:1 sichern, nicht die Dateien lesen.

<b>Zieldisk zu klein</b>
•  Beim Zurückspielen <i>Für diese Disk anpassen</i> anhaken (Kapitel <i>Image zurückspielen</i>).
•  Passen die Daten nicht, nennt das Tool die Zahlen. Dann ist eine grössere Disk nötig.

<b>Nach dem Zurückspielen startet wieder der Agent statt Windows</b>
•  Der Agent-Stick steckt noch. Gerät herunterfahren, Stick abziehen, einschalten.

<b>Wake-on-LAN schaltet das Gerät nicht ein</b>
•  Im BIOS Wake-on-LAN einschalten. Bei Notebooks muss das Netzteil angeschlossen sein.
•  Das Netzwerkkabel muss stecken. Nach einem Stromausfall klappt es oft erst nach einmal Einschalten von Hand.

<b>Windows 11 zeigt „?“</b>
•  Agent-Stick neu erstellen und <i>Inventar neu einlesen</i>.

<b>Garantie-Abfrage klappt nicht</b>
•  Dell und HP: Ist der Schlüssel unter <i>Menü → Einstellungen … → Garantie-Abfrage</i> eingetragen?
•  Hat der Server Internet?
•  Meldung zum Hilfsprogramm: einmal <tt>sudo ./install.sh</tt> ausführen.
•  Sonst das Datum mit <i>Von Hand …</i> eintragen.

<b>Ein USB-Stick wird nicht angezeigt</b>
•  Neu einstecken und auf ⟳ (neu suchen) klicken.
•  Die Disk des Servers wird nie angezeigt. Das ist ein Schutz.

<b>Ein Stick ist plötzlich zu klein oder macht Fehler</b>
•  Beim Formatieren den <i>Schnelltest</i> wählen. Er erkennt gefälschte Sticks.

<b>Die Automatisierung startet nicht</b>
•  Steht in der Liste <i>Einstellungen unvollständig</i>? Im Reiter <i>Automatisierung</i> steht, was fehlt.
•  Steht <i>pausiert</i>? Oben über der Geräteliste auf den roten Stopp-Knopf ■ klicken.
•  Steht <i>wieder aktiv in …</i>? Die Automatisierung lief schon. Häkchen <i>Auto</i> neu setzen, wenn sie sofort laufen soll.
•  Nach einem Fehler oder Esc: Gerät neu starten, dann startet sie neu.
•  Meldung „Agent zu alt“: Agent-Stick neu erstellen bzw. Netzwerkstart neu vorbereiten.

<b>Name oder Windows-Schlüssel wurden nicht gesetzt</b>
•  Das geht nur bei einem Master-Image, das mit Sysprep vorbereitet wurde. Das Log sagt es.

<b>Fehlermeldung „Hilfsprogramm … sudo-Regel“</b>
•  Auf dem Server einmal <tt>sudo ./install.sh</tt> im Tool-Ordner ausführen."""),

    ("Projektübersicht", """<big><b>Projektstand ansehen und Rückmeldungen geben (Projektübersicht)</b></big>

Die Projektübersicht zeigt den ganzen Stand der Weiterentwicklung an einem Ort:
offene Tests am realen System, Bugs, Änderungen, Ideen, die offenen Punkte der letzten Übergabe
und die Aufträge (Prompts) mit ihrem Status. Zu jedem Eintrag lässt sich direkt eine Rückmeldung geben.

<b>Öffnen:</b>
1.  <i>Extras → Projektübersicht …</i> wählen.
2.  Der Browser (Firefox) öffnet die Seite <i>Projektübersicht – Okula Recovery Tool</i>.
    Ein weiterer Aufruf öffnet dieselbe Seite erneut.

<b>Was die Seite zeigt:</b>
•  <b>Oben</b> eine Übersicht mit Zählern: offene Tests je Abschnitt (offen, ✔ ok, ✖ Fehler),
    offene Bugs, Änderungen und Ideen, neue Rückmeldungen, „Als Nächstes“ und die Prompts mit Status.
•  Die Bereiche <i>Tests am realen System</i>, <i>Bugs</i>, <i>Änderungen</i>, <i>Ideen</i>,
    <i>Offene Punkte (Übergabe)</i>, <i>Prompts</i>, <i>Meine neuen Notizen</i> und
    <i>Rückmeldungen ohne Eintrag</i>. Jeder Bereich lässt sich einklappen.
•  Suchfeld und Filter (Art, Priorität, nur mit eigener Rückmeldung, nur neue, erledigte Tests ausblenden).

<b>Rückmeldungen geben</b> (werden sofort gespeichert, kurz erscheint „gespeichert“):
•  Tests: <i>✔ ok</i> oder <i>✖ Fehler</i> anklicken (nochmals klicken = leer) und einen Kommentar schreiben.
•  Bugs, Änderungen, Ideen: Kommentar, Wunsch-Priorität (🔴 🟡 ⚪) und Wunsch-Status
    (<i>als Nächstes</i>, <i>zurückstellen</i>, <i>streichen</i>, <i>erledigt</i>).
    Neben dem Eintrag steht der Wunsch zum Ist-Stand, zum Beispiel „Prio 🟡 → Wunsch 🔴“.
•  Offene Punkte und Prompts: Kommentar.
•  <i>Neue Notiz</i>: Art (Bug, Änderung, Idee, Frage) wählen, Text eingeben, auf <i>Neue Notiz</i> klicken.
    Notizen lassen sich ändern und löschen, solange sie nicht übernommen sind.

<b>Woher die Daten kommen:</b>
Die Seite liest bei jedem Laden die Doku im Projektordner (Repo), Ordner <tt>docs</tt>:
<tt>TESTS.md</tt>, <tt>AENDERUNGEN.md</tt>, <tt>UEBERGABE.md</tt> und <tt>prompts</tt>.
Standard ist <tt>~/recovery_tool_okula</tt>; ändern unter <i>Menü → Einstellungen … → Projektordner (Repo)</i>.
Nach <tt>git pull</tt> genügt auf der Seite der Knopf <i>Neu laden</i> – ohne Neustart des Tools.
Fehlt der Ordner, steht oben auf der Seite ein Hinweis.

<b>Wo die Rückmeldungen liegen:</b>
In <tt>~/.local/share/okula-recovery/projekt-rueckmeldungen.json</tt> (nicht im Repo, nur für den Benutzer lesbar).
Die Seite ändert <b>nie</b> die Doku. Erst die Projektleitung überträgt die Rückmeldungen in die Doku und
markiert sie als übernommen; sie erscheinen dann grau mit „übernommen TT.MM.“.
Eine neue Änderung daran macht sie wieder neu.
Ändert sich der Text eines Eintrags in der Doku, steht die alte Rückmeldung unter
<i>Rückmeldungen ohne Eintrag</i> – es geht nichts verloren.

<b>Sicherheit:</b>
Die Seite ist <b>nur auf diesem Rechner</b> erreichbar (127.0.0.1), nicht aus dem LAN.
Die Adresse enthält einen zufälligen Schlüssel, der bei jedem Start des Tools neu ist.
Nach einem Neustart des Tools die Seite daher über <i>Extras → Projektübersicht …</i> neu öffnen."""),

    ("Tastenkürzel", """<big><b>Tastenkürzel</b></big>

<tt>F1        </tt>  Diese Anleitung
<tt>Ctrl+F    </tt>  In der Anleitung suchen
<tt>Esc       </tt>  Suche leeren, sonst Anleitung bzw. Dialog schliessen
<tt>Ctrl+N    </tt>  NAS-Verbindung
<tt>Ctrl+O    </tt>  Gewähltes Gerät öffnen
<tt>F5        </tt>  Images aktualisieren
<tt>F11       </tt>  Vollbild ein / aus
<tt>Ctrl+Q    </tt>  Beenden

<b>Im Reiter „Dateien“</b>
<tt>Doppelklick</tt>  Ordner öffnen
<tt>Backspace </tt>  Eine Ebene zurück
<tt>F2        </tt>  Umbenennen
<tt>Entf      </tt>  Löschen"""),

    ("Demo-Gerät", """<big><b>Das Tool vorführen (Demo-Gerät)</b></big>

Zum Vorführen gibt es ein Gerät, das es gar nicht gibt: den <b>DEMO-PC</b>.
Die Vorführung braucht <b>kein NAS</b>. Alle Demo-Daten liegen lokal auf dem Server im
<b>Demo-Speicher</b> – das NAS wird weder gelesen noch beschrieben, auch wenn es verbunden ist.

<b>Ablauf:</b>
1.  <i>Extras → Demo-Gerät (Vorführung)</i> anhaken.
2.  Nach ein paar Sekunden steht links <i>DEMO-PC</i> mit grünem Punkt.
    Rechts im Reiter <i>Images</i> erscheint der Bereich <i>Demo (lokal, nicht auf dem NAS)</i> –
    auch wenn „NAS nicht verbunden“ steht. Das ist bei der Vorführung normal.
3.  Jetzt lässt sich alles zeigen: Disk-Image erstellen, Image prüfen, zurückspielen, Automatisierung,
    Backup erstellen und zurückspielen, Ordner senden, Windows anpassen, Inventar exportieren.
    Ein Auftrag dauert knapp eine Minute (<i>Windows anpassen</i> nur ein paar Sekunden; am DEMO-PC wird
    nichts abgelegt).

<b>Fertige Demo-Images</b> (im Bereich <i>Demo</i>):
•  <i>DEMO-Master-Win11</i>: als Master-Image markiert (★). <i>Image prüfen …</i> ergibt ✔.
    Damit lassen sich Zurückspielen und die Automatisierung vorführen.
•  <i>DEMO-Image-beschaedigt</i>: absichtlich beschädigt. <i>Image prüfen …</i> ergibt ✖ und nennt die Datei.
•  Rechtsklick auf <i>Demo (lokal, nicht auf dem NAS)</i> → <i>Alle Images im Ordner prüfen …</i>
    zeigt die Zusammenfassung, zum Beispiel „3 Images geprüft: 2 ✔, 1 ✖“.
•  Für den Ordner <i>Ordner senden</i> gibt es Beispielordner (Software, Test Files, drei Projekte).
•  Für <i>Software installieren</i> liegen drei erfundene Beispiel-Installer in der Software-Bibliothek des
    Demo-Speichers (zwei „bereit“, einer „Parameter fehlt“). <i>Extras → Software-Bibliothek …</i> zeigt bei
    laufendem Demo-Gerät diese Bibliothek – laden, bearbeiten und löschen verändern das NAS nicht. Auswahl und
    Auftrag lassen sich zeigen; am DEMO-PC wird nichts installiert, der Auftrag meldet „fertig“.

<b>Einen Fehler zeigen:</b>
<i>Extras → Demo: nächster Auftrag mit Fehler</i>. Der nächste Auftrag bricht ab, der Balken wird rot.

<b>Demo-Daten zurücksetzen</b>
<i>Extras → Demo-Daten zurücksetzen …</i> löscht den Demo-Speicher (nach Rückfrage).
Beim nächsten Einschalten entsteht der Ausgangszustand mit den zwei fertigen Demo-Images neu.

<b>Gut zu wissen:</b>
•  Der DEMO-PC fasst nichts an. Es gibt keine echte Disk dahinter.
•  Andere Geräte im Netzwerk merken nichts davon.
•  Demo-Images lassen sich nur auf den DEMO-PC zurückspielen, echte Images nie auf den DEMO-PC.
    Ebenso bei den Backups.
•  Zum Beenden das Häkchen wieder entfernen. Der Bereich <i>Demo</i> verschwindet,
    die Demo-Daten bleiben für die nächste Vorführung.
•  Liegen noch alte Demo-Images auf dem NAS (von früher), sind sie ausgeblendet.
    Rechtsklick auf den Hinweis → <i>Alte Demo-Images vom NAS löschen …</i>"""),
]


class HelpWindow(Gtk.Window):
    """Kapitel links (mit Suchfeld darüber), Text rechts. HelpWindow(parent, chapter="…") öffnet ein Kapitel."""

    def __init__(self, parent: Gtk.Window, chapter: str | None = None):
        super().__init__(title="So funktioniert das Tool")
        self.set_transient_for(parent)
        self.set_default_size(980, 720)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.labels: dict[str, Gtk.Label] = {}
        self.pages: dict[str, Gtk.Widget] = {}
        for title, text in CHAPTERS:
            label = Gtk.Label(xalign=0, yalign=0, wrap=True, selectable=True, max_width_chars=90,
                              margin=24, margin_top=18)
            label.set_markup(text)
            label.set_line_wrap(True)
            page = scrolled(label)
            self.stack.add_titled(page, title, title)
            self.labels[title], self.pages[title] = label, page
        none = Gtk.Label(label="Keine Treffer. Ein anderes Wort versuchen.", margin=24, xalign=0, yalign=0)
        none.get_style_context().add_class("status-idle")
        self.stack.add_named(none, "__keine_treffer__")
        self.search = Gtk.SearchEntry(placeholder_text="Suchen (Ctrl+F)", margin=6)
        self.search.connect("search-changed", lambda _e: self.apply_search())
        self.search.connect("activate", lambda _e: self._show_first())
        sidebar = Gtk.StackSidebar(stack=self.stack, vexpand=True)
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        side.set_size_request(240, -1)
        side.pack_start(self.search, False, False, 0)
        side.pack_start(sidebar, True, True, 0)
        box = Gtk.Box()
        box.pack_start(side, False, False, 0)
        box.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 0)
        box.pack_start(self.stack, True, True, 0)
        self.add(box)
        self.connect("key-press-event", self._on_key)
        self.show_all()
        if chapter:
            self.stack.set_visible_child_name(chapter)

    def apply_search(self) -> list[str]:
        """Kapitelliste filtern, Treffer hervorheben, erstes Treffer-Kapitel zeigen. Gibt die Treffer zurück."""
        query = self.search.get_text()
        found = helpsearch.find(query, CHAPTERS)
        for title, text in CHAPTERS:
            self.pages[title].set_visible(title in found)
            self.labels[title].set_markup(helpsearch.highlight(text, query) if title in found else text)
        if not query.strip():
            if self.stack.get_visible_child_name() == "__keine_treffer__":
                self.stack.set_visible_child_name(CHAPTERS[0][0])
            return found
        self._show_first(found)
        return found

    def _show_first(self, found: list[str] | None = None) -> None:
        found = helpsearch.find(self.search.get_text(), CHAPTERS) if found is None else found
        if found:
            self.stack.set_visible_child_name(found[0])    # erstes Treffer-Kapitel
        else:
            self.stack.set_visible_child_name("__keine_treffer__")

    def _on_key(self, _w, event) -> bool:
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
        if ctrl and event.keyval in (Gdk.KEY_f, Gdk.KEY_F):
            self.search.grab_focus()
            return True
        if event.keyval == Gdk.KEY_Escape:
            if self.search.get_text():
                self.search.set_text("")
                return True
            self.destroy()
            return True
        return False
