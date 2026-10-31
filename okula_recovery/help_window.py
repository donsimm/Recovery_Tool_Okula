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
•  Geräte ohne Stick starten (<b>Netzwerkstart</b>) und aus der Ferne einschalten (<b>Wake-on-LAN</b>).
•  <b>Inventar</b> jedes Geräts: Hardware, Disks mit Zustand, Windows-11-Tauglichkeit, Garantie.
    Export als Liste (CSV) oder PDF.
•  USB-Sticks erstellen (Agent-, Boot- und Restore-Stick), USB-Datenträger klonen und formatieren.
•  Ein <b>Demo-Gerät</b> zum Vorführen.

<b>Aufbau des Fensters:</b>
•  <b>Links</b> stehen alle Geräte (Computer). Ein grüner Punkt bedeutet: verbunden.
    Das Häkchen <i>Auto</i> schaltet die Automatisierung für ein Gerät ein oder aus.
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

<b>TPM und Secure Boot</b>
Sicherheitsfunktionen im Gerät. Windows 11 verlangt TPM 2.0 und Secure Boot.

<b>SMART</b>
Der Selbsttest einer Disk. Er zeigt, ob die Disk gesund ist.

<b>Inventar</b>
Alle Angaben zu einem Gerät: Hersteller, Modell, Seriennummer, Prozessor, Arbeitsspeicher, Disks.

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
Nach einem Update des Tools muss der Agent-Stick manchmal neu erstellt werden.
Das steht dann in den Hinweisen zum Update.

<b>3. Firewall</b>
Nur nötig, wenn auf dem Server eine Firewall läuft. Prüfen mit <tt>sudo nft list ruleset</tt>:
leer bedeutet, dass nichts zu tun ist. Sonst diese Ports für eingehende Verbindungen freigeben:
•  <b>Immer:</b> UDP 47811 – sonst findet das Tool die Geräte nicht.
•  <b>Nur für den Netzwerkstart:</b> UDP 67, UDP 69, UDP 4011 und TCP 47813."""),

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
Vor dem Neustart am Ende den Stick abziehen.

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
    Ordner senden, Inventar neu einlesen, Herunterfahren, Neu starten.
•  <i>Aufträge</i>: was gerade läuft, mit Fortschritt und Log.
•  <i>Übersicht</i>: Hersteller, Modell, Seriennummer, Starttasten, Windows 11, Garantie bis, Windows-Schlüssel.
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
•  Nach Windows-Updates kann die Startreihenfolge zurückgesetzt sein. <i>Prüfen</i> zeigt es an."""),

    ("Geräte verwalten", """<big><b>Geräte verwalten</b></big>

Alle Aktionen über Rechtsklick auf ein Gerät oder einen Ordner in der Geräteliste.
Die Aufträge für das gewählte Gerät stehen zusätzlich im Menü <i>Tools</i>.

<b>Gerät</b>
•  <i>Umbenennen …</i>: Der Gerätename wird bei Neuinstallation, Master-Image und Automatisierung
    der Computername. Windows erlaubt höchstens 15 Zeichen ohne Sonderzeichen.
•  <i>Nach „Neu / nicht einsortiert“</i>: Gerät aus seinem Ordner zurücknehmen.
•  <i>Zusammenführen mit …</i>: Steht ein Gerät doppelt in der Liste, die zwei Einträge vereinen.
•  <i>Aus der Liste löschen …</i>: nur möglich, wenn das Gerät nicht verbunden ist.
    Images und Backups auf dem NAS bleiben.
•  <i>Inventar neu einlesen</i>: Angaben zum Gerät neu holen (zum Beispiel nach einem Disk-Tausch).
•  <i>Herunterfahren</i> und <i>Neu starten</i>: nur wenn das Gerät verbunden ist
    (auch <i>Tools → Gerät herunterfahren</i>).
•  <i>Inventar exportieren …</i>: Liste zu diesem Gerät (Kapitel <i>Inventar, Garantie, Windows 11</i>).

<b>Ordner</b>
•  <i>Neuer Ordner …</i>, <i>Ordner umbenennen …</i>, <i>Ordner löschen (nur leer)</i>.
•  Höchstens 3 Ordnerebenen, zum Beispiel <i>Firma → Standort → Abteilung</i>.
•  Geräte und Ordner lassen sich mit der Maus verschieben (ziehen und loslassen)."""),

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
6.  Zur Bestätigung den Namen der Zieldisk eintippen (zum Beispiel „sda“ oder „nvme0n1“).
7.  Auf <i>Zurückspielen</i> klicken.

Am Ende den Stick abziehen und das Gerät neu starten.

<b>Zieldisk kleiner als das Image</b>
Zum Beispiel 256 statt 512 GB: Das Tool prüft, ob die Daten passen.
Dann <i>Für diese Disk anpassen</i> anhaken: Das Tool erstellt daraus ein neues, kleineres Image.
Das Original bleibt unverändert. Das dauert etwas länger.
Nicht möglich bei verschlüsselten Disks (BitLocker) – dort fehlt die Option.

<b>Gut zu wissen:</b>
•  Auch Images von Clonezilla funktionieren.
•  Nach einem Abbruch ist die Zieldisk unvollständig.
•  Bei einem Master-Image passt das Tool Windows danach an: Kapitel <i>Master-Image</i>."""),

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
    oder Rechtsklick → <i>Zurückspielen / herunterladen …</i>.
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
1.  Windows frisch installieren. Beim ersten Einrichtungsbildschirm <b>Ctrl+Shift+F3</b> drücken:
    Windows startet in den <b>Audit-Modus</b> (ohne Benutzer anzulegen).
2.  Updates, Treiber und Programme installieren. Kein Microsoft-Konto, keine Domäne.
3.  BitLocker ausschalten.
4.  Sysprep starten (als Administrator):
    <tt>C:\\Windows\\System32\\Sysprep\\sysprep.exe /generalize /oobe /shutdown</tt>
5.  Windows <b>nicht mehr starten</b>. Direkt mit dem Agent-Stick starten.
6.  <i>Disk-Image erstellen …</i>, Name zum Beispiel „Master-Win11-2026-10“.
Die ausführliche Anleitung steht im Projekt in <tt>docs/MASTER-IMAGE.md</tt>.

<b>Im Tool:</b>
1.  Rechts im Reiter <i>Images</i>: Rechtsklick auf das Image → <i>Als Master-Image markieren</i>.
    Es bekommt einen Stern ★.
2.  Beim Zurückspielen ist dann <i>Danach anpassen</i> eingeschaltet:
    Das Gerät bekommt seinen Namen aus dem Tool und den Windows-Schlüssel.
3.  Beim ersten Start richtet sich Windows damit selbst ein.

<b>Gut zu wissen:</b>
•  Den Windows-Schlüssel liest das Tool aus dem BIOS. Ein eigener Schlüssel lässt sich im Gerätefenster
    unter <i>Übersicht → Windows-Schlüssel</i> hinterlegen.
•  Ein Image eines UEFI-Geräts läuft nur auf UEFI-Geräten.
•  Ein normales Image (ohne Sysprep) wird nicht angepasst. Das Log sagt es."""),

    ("Automatisierung", """<big><b>Geräte automatisch neu aufsetzen</b></big>

Mit der Automatisierung setzt das Tool ein Gerät selbst neu auf, sobald es mit dem Agent startet.

<b>Einrichten (einmal pro Gerät):</b>
1.  Gerät öffnen → Reiter <i>Automatisierung</i>.
2.  <b>Backup</b> (Option): vorher sichern – nur Benutzerdaten (schnell) oder die ganze Disk als Disk-Image.
3.  <b>Image zurückspielen</b>: Master-Image oder ein eigenes Image wählen, dazu die Zieldisk.
    Ist die Zieldisk kleiner: <i>Image dafür anpassen</i> anhaken (Kapitel <i>Image zurückspielen</i>).
4.  <b>Anpassen</b> (läuft immer, nur bei Master-Images): Gerätename und Windows-Schlüssel,
    auf Wunsch <i>Region Schweiz</i> und ein <i>Lokales Konto</i> (Passwort beim ersten Anmelden setzen).
5.  <b>Ordner senden</b> (Option): Software, Test Files, Content-Projekte.
6.  <b>Abschluss</b>: Neustart, Herunterfahren oder nichts.
7.  Schalter <i>Automatisierung</i> einschalten – oder in der Liste das Häkchen <i>Auto</i> setzen.

<b>Achtung:</b> Ist das Gerät beim Einschalten des Schalters verbunden, beginnt der Countdown sofort.
Nach 30 Sekunden wird die Zieldisk überschrieben.

<b>Vorlagen</b>
•  <i>Als Vorlage speichern …</i>: Einstellungen unter einem Namen speichern (z. B. „Schulungs-PC“).
•  <i>Anwenden</i>: Vorlage bei einem anderen Gerät übernehmen. Die Zieldisk dort neu wählen.
•  <i>Löschen</i>: Geräte, die die Vorlage verwendet haben, behalten ihre Einstellungen.

<b>Ablauf am Gerät:</b>
1.  Das Gerät startet mit dem Agent (Stick oder Netzwerkstart).
2.  30 Sekunden Countdown – am Gerät bricht <b>Esc</b> ab, im Tool <i>Abbrechen</i>.
3.  Backup (wenn gewählt), Image zurückspielen, anpassen, Ordner senden.
4.  Abschluss. Vor dem Neustart den Agent-Stick abziehen, sonst startet wieder der Agent.
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
Die Inhalte lassen sich rechts im Reiter <i>Dateien</i> ändern.

<b>Ablauf:</b>
1.  Gerät mit dem Agent starten.
2.  Rechtsklick auf das Gerät → <i>Ordner senden</i> → <i>Software</i>, <i>Test Files</i> oder <i>Content …</i>
3.  Bei Content die Projekte anhaken und auf <i>Senden</i> klicken.

<b>Gut zu wissen:</b>
•  Gibt es den Ordner schon auf dem Desktop, wird er ersetzt.
•  Bricht etwas ab, bleibt der alte Ordner.
•  Windows muss ganz heruntergefahren sein (Shift-Taste gedrückt halten + „Herunterfahren“)."""),

    ("Inventar, Garantie, Windows 11", """<big><b>Inventar, Garantie und Windows 11</b></big>

Das Tool liest bei jedem Verbinden die Angaben des Geräts (Inventar).
Die Angaben stehen im Gerätefenster unter <i>Übersicht</i> und <i>Disks</i>.
<i>Inventar neu einlesen</i> holt sie neu, zum Beispiel nach einem Disk-Tausch.

<b>Windows 11</b> (<i>Übersicht → Windows 11</i>)
•  ✔ Das Gerät erfüllt die Anforderungen von Windows 11.
•  ✖ Nicht tauglich, zum Beispiel wegen TPM 1.2 oder einem zu alten Prozessor. Der Grund steht daneben.
•  ? Noch unbekannt: Agent-Stick neu erstellen und <i>Inventar neu einlesen</i>.

<b>Garantie</b> (<i>Übersicht → Garantie bis</i>)
•  <span foreground="#2e7d32">grün</span>: Die Garantie läuft noch.
•  <span background="#fff3b0">gelb</span>: Die Garantie läuft in den nächsten 90 Tagen ab.
•  <span background="#c62828" foreground="#ffffff">rot</span>: Die Garantie ist abgelaufen.
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
5.  Starten. Das Gerät startet danach neu und installiert selbständig.
    Am Gerät wird nichts gefragt. Was nicht ausgewählt ist, wird nicht installiert.

Der <b>Computername</b> ist immer der Gerätename im Tool. Für einen anderen Namen das Gerät umbenennen.
Windows erlaubt nur 15 Zeichen ohne Sonderzeichen. Der Dialog zeigt, wie der Name ankommt.

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
    Vor dem Neustart den Stick abziehen.

<b>Agent-Stick</b>
•  <i>Menü → Agent-USB-Stick erstellen …</i> (Kapitel <i>Erste Schritte</i>).

Bei allen Sticks gilt: Der Stick wird dabei gelöscht."""),

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
•  <i>Als Master-Image markieren</i> bzw. <i>Master-Markierung entfernen</i> (Stern ★).
•  <i>Restore-Stick aus Image …</i>: Kapitel <i>Sticks erstellen</i>.
•  <i>Umbenennen …</i> und <i>Löschen …</i>. Gelöschte Images sind endgültig weg (kein Papierkorb).

<b>ISO</b>
•  <i>Details und Prüfsummen …</i>: Version, Edition und Prüfsummen der ISO.
•  <i>Boot-Stick erstellen …</i> und <i>Auf Gerät installieren …</i>.
•  <i>ISO hinzufügen …</i>: neue ISO aufnehmen.

<b>Aktualisieren</b>
<i>Tools → Images aktualisieren</i> (F5) liest die Liste neu vom NAS,
zum Beispiel nachdem Dateien direkt auf das NAS kopiert wurden."""),

    ("Anzeigen im Fenster", """<big><b>Was die Anzeigen bedeuten</b></big>

<b>Oben rechts: Serverlast</b>
•  <b>CPU</b>: wie stark der Prozessor arbeitet.
•  <b>RAM</b>: wie viel Arbeitsspeicher belegt ist.
•  <b>LAN</b>: wie viel über das Netzwerk geht. ↓ empfangen, ↑ gesendet.
•  Die Kurve zeigt die letzte Minute. Über 90 % wird die Zahl rot.
•  Mit der Maus darüberfahren zeigt mehr Details.

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
•  <span foreground="#2e7d32">grün</span>: Der Auftrag läuft.
•  <span foreground="#c62828">rot</span>: Der Auftrag ist fehlgeschlagen. Daneben steht, bei wie viel Prozent.
    Den Grund zeigt das Gerätefenster unter <i>Aufträge</i>. Der rote Balken bleibt, bis der nächste Auftrag startet.

<b>Spalte „Auto“ und Status der Automatisierung</b>
•  Häkchen gesetzt: Die Automatisierung ist eingeschaltet.
•  Häkchen grau: Alles ist pausiert (Stopp-Knopf ■ ist rot).
•  <i>startet in 25 s</i>: Countdown läuft. Am Gerät bricht Esc ab.
•  <i>wartet (Platz 2)</i>: Es laufen schon so viele Geräte wie erlaubt. Das Gerät kommt gleich dran.
•  <i>Schritt 2/5: Image zurückspielen</i>: Die Automatisierung arbeitet.
•  <i>wieder aktiv in 2 Tagen 5 h</i>: Die Automatisierung ist fertig und schaltet sich nach 3 Tagen wieder ein.
•  <span foreground="#c62828">rot</span>: Es gab einen Fehler. Details im Gerätefenster.

<b>Stern ★ bei Images</b>
Das Image ist als Master-Image markiert.

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
Im NAS-Fenster gibt es <i>Exportieren …</i> und <i>Importieren …</i>.
Damit kommen nur die NAS-Einstellungen mit (ohne Passwort)."""),

    ("Probleme lösen", """<big><b>Wenn etwas nicht klappt</b></big>

<b>Das Gerät erscheint nicht im Tool</b>
•  Ist das Gerät am Netzwerkkabel? WLAN geht nicht.
•  Sind Gerät und Server im selben Netzwerk?
•  Firewall auf dem Server: Ports freigeben (Kapitel <i>Erste Schritte</i>).
•  Startet das Gerät wirklich vom Stick? Im Boot-Menü den USB-Stick wählen.

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
•  Der Agent-Stick steckt noch. Stick abziehen und neu starten.

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

<b>Ablauf:</b>
1.  <i>Extras → Demo-Gerät (Vorführung)</i> anhaken.
2.  Nach ein paar Sekunden steht links <i>DEMO-PC</i> mit grünem Punkt.
3.  Jetzt lässt sich alles zeigen: Image erstellen, zurückspielen, Backup, Ordner senden, Automatisierung …
    Ein Auftrag dauert knapp eine Minute.

<b>Einen Fehler zeigen:</b>
<i>Extras → Demo: nächster Auftrag mit Fehler</i>. Der nächste Auftrag bricht ab, der Balken wird rot.

<b>Gut zu wissen:</b>
•  Der DEMO-PC fasst nichts an. Es gibt keine echte Disk dahinter.
•  Andere Geräte im Netzwerk merken nichts davon.
•  Ein Image vom DEMO-PC lässt sich nur auf den DEMO-PC zurückspielen.
•  Zum Beenden das Häkchen wieder entfernen."""),
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
