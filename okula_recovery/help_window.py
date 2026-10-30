"""Hilfe → „So funktioniert das Tool“: Anleitung in einfacher Sprache, Kapitel links, Text rechts."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from okula_recovery.uikit import scrolled  # noqa: E402

# (Kapitel, Text in Pango-Markup). Einfache Sprache: kurze Sätze, ein Gedanke pro Satz, Fachwörter erklärt.
CHAPTERS: list[tuple[str, str]] = [
    ("Überblick", """<big><b>Was macht das Tool?</b></big>

Mit dem Okula Recovery Tool sicherst du Computer und stellst sie wieder her.
Alles läuft über das Netzwerk. Die Sicherungen liegen auf dem <b>NAS</b>.

<b>Das kannst du damit machen:</b>
•  Eine ganze Festplatte sichern (<b>Disk-Image</b>) und später zurückspielen.
•  Nur Dateien sichern (<b>Datei-Backup</b>), zum Beispiel Dokumente und Bilder.
•  Windows oder Linux neu auf einen Computer installieren.
•  USB-Sticks erstellen: zum Starten, zum Installieren oder zum Wiederherstellen.
•  USB-Sticks und externe Festplatten kopieren (klonen) und formatieren.
•  Ein <b>Master-Image</b> auf viele Geräte verteilen – jedes bekommt seinen eigenen Namen.
•  Ordner wie <i>Software</i> oder Projekte auf den Desktop eines Geräts senden.
•  Geräte <b>automatisch</b> neu aufsetzen, sobald sie starten (<b>Automatisierung</b>).

<b>So ist das Fenster aufgebaut:</b>
•  <b>Links</b> stehen alle Geräte (Computer). Ein grüner Punkt heisst: verbunden.
   Das Häkchen <i>Auto</i> schaltet die Automatisierung für ein Gerät ein oder aus.
•  <b>Rechts</b> siehst du das NAS mit den Reitern <i>Images</i>, <i>Dateien</i> und <i>Backups</i>.
•  <b>Oben rechts</b> siehst du, wie stark der Server gerade arbeitet (CPU, RAM, LAN).
•  <b>Oben</b> ist die Menüleiste: <i>Menü</i>, <i>Tools</i>, <i>Extras</i> und <i>Hilfe</i>.

Wichtig: Auf den Computern wird <b>nichts installiert</b>.
Sie starten nur kurz vom <b>Agent-Stick</b> oder über das Netzwerk (Netzwerkstart)."""),

    ("Wichtige Begriffe", """<big><b>Wichtige Begriffe einfach erklärt</b></big>

<b>Server</b>
Der Computer, auf dem dieses Tool läuft (der RecoveryPC).

<b>NAS</b>
Ein Netzwerk-Speicher. Dort liegen alle Sicherungen und ISO-Dateien.

<b>Gerät</b>
Ein Computer, den du sichern oder wiederherstellen willst.

<b>Agent-Stick</b>
Ein USB-Stick, von dem das Gerät startet. Dann kann das Tool mit dem Gerät reden.
Der Stick ändert nichts am Gerät. Er läuft nur im Arbeitsspeicher.

<b>Disk-Image</b>
Eine Kopie der ganzen Festplatte, mit Windows, Programmen und Dateien.
Damit stellst du den Computer genau so wieder her, wie er war.

<b>Datei-Backup</b>
Eine Kopie von ausgewählten Dateien und Ordnern, zum Beispiel „Dokumente“.

<b>ISO</b>
Eine Datei mit einem Betriebssystem, zum Beispiel Windows 11 oder Ubuntu.

<b>Partition</b>
Ein Bereich auf einer Festplatte. Eine Festplatte kann mehrere Partitionen haben.

<b>Formatieren</b>
Einen Datenträger leer machen und für ein bestimmtes System vorbereiten.
Dabei gehen alle Daten verloren.

<b>Klonen</b>
Einen Datenträger 1:1 auf einen anderen kopieren.

<b>Master-Image</b>
Ein vorbereitetes Windows für viele Geräte (mit Sysprep). Beim Zurückspielen bekommt jedes Gerät
seinen eigenen Namen und seinen Windows-Schlüssel. In der Liste hat es einen Stern ★.

<b>Automatisierung</b>
Das Tool setzt ein Gerät selbst neu auf, sobald es mit dem Agent startet – ohne Klick.

<b>Gerätename</b>
Der Name im Tool. Er wird auch der Computername bei einer Neuinstallation."""),

    ("Erste Schritte", """<big><b>Erste Schritte (nur einmal nötig)</b></big>

<b>1. NAS verbinden</b>
•  Öffne <i>Menü → NAS-Verbindung …</i> (oder Ctrl+N).
•  Gib die Adresse des NAS, den Benutzer und das Passwort ein.
•  Klicke auf <i>Freigaben suchen</i> und wähle die Freigabe.
•  Klicke auf <i>Einhängen</i>.
•  Rechts steht dann „● NAS verbunden“ in Grün.

<b>2. Agent-Stick erstellen</b>
•  Stecke einen leeren USB-Stick ein (mindestens 4 GB).
•  Öffne <i>Menü → Agent-USB-Stick erstellen …</i>.
•  Wähle den Stick und klicke auf <i>Herunterladen</i> (das System für den Stick).
•  Klicke auf <i>Stick vorbereiten</i>. Achtung: Der Stick wird gelöscht.

Nach einem Update des Tools musst du den Agent-Stick manchmal neu erstellen.
Das steht dann in den Hinweisen zum Update.

<b>3. Firewall</b>
Falls auf dem Server eine Firewall läuft: UDP-Port 47811 freigeben.
Sonst findet das Tool die Geräte nicht."""),

    ("Gerät verbinden", """<big><b>Ein Gerät verbinden</b></big>

<b>So gehts:</b>
1.  Stecke den Agent-Stick in das Gerät.
2.  Starte das Gerät und öffne das Boot-Menü.
     Die Taste ist meist F12, F11, F8 oder Esc (steht kurz beim Start auf dem Bildschirm).
3.  Wähle den USB-Stick.
4.  Nach etwa einer Minute erscheint das Gerät links im Tool, mit grünem Punkt.

Neue Geräte stehen zuerst unter <i>„Neu / nicht einsortiert“</i>.
Du kannst sie mit der Maus in eigene Ordner ziehen, zum Beispiel nach Kunde.
Steht ein Gerät doppelt in der Liste: Rechtsklick auf den doppelten Eintrag → <i>„Zusammenführen mit …“</i>.

<b>Die Punkte bedeuten:</b>
•  <span foreground="#2e7d32">●</span> grün: Gerät ist verbunden und bereit.
•  <span foreground="#c62828">●</span> rot: Gerät ist nicht verbunden (ausgeschaltet oder ohne Stick).

<b>Gerätefenster</b>
Doppelklick auf ein Gerät öffnet sein Fenster. Dort findest du:
•  Knöpfe für alle Aufgaben: Image, Zurückspielen, OS installieren, Backup.
•  <i>Aufträge</i>: was gerade läuft, mit Fortschritt.
•  <i>Übersicht</i> und <i>Disks</i>: Hersteller, Modell, Festplatten und deren Zustand.
•  <i>Images</i> und <i>Backups</i>: alle Sicherungen von diesem Gerät.
•  <i>Netzwerk</i>: Netzwerkstart, Einschalten aus der Ferne (Wake-on-LAN).
•  <i>Automatisierung</i>: das Gerät automatisch neu aufsetzen.
•  <i>Verlauf</i> und <i>Notizen</i>.
•  <i>Ordner senden …</i>: Ordner vom NAS auf den Desktop des Geräts.

Das Tool erkennt ein Gerät beim nächsten Mal wieder, auch nach Monaten."""),

    ("Netzwerkstart", """<big><b>Gerät ohne Stick verbinden (Netzwerkstart)</b></big>

Ein Gerät, das schon einmal mit dem Agent-Stick lief, kann den Agent auch <b>übers Netzwerk</b> starten.
Dann brauchst du den Stick nicht mehr.

<b>Einmal einrichten:</b>
1.  <i>Tools → Netzwerkstart (PXE) …</i> öffnen.
2.  Server-IP und Debian-Live-ISO wählen, dann <i>Vorbereiten</i>. Das dauert einige Minuten.
3.  Geräte freischalten: Haken setzen. Oder im Gerätefenster unter <i>Netzwerk</i> den Schalter
     „Netzwerkstart“ einschalten. Das Zahnrad daneben öffnet die Einstellungen.
4.  <i>Einschalten</i>.

<b>Am Gerät:</b>
1.  Netzwerkkabel einstecken.
2.  Beim Start das Boot-Menü öffnen (meist F12) und „Netzwerk“ oder „PXE“ wählen.
3.  Das Gerät erscheint im Tool mit grünem Punkt – wie mit dem Stick.

<b>Sicher für die anderen Rechner:</b>
•  Nur freigeschaltete Geräte bekommen eine Antwort. Alle anderen Rechner merken nichts.
•  Das Tool verteilt keine IP-Adressen. Das macht weiterhin euer Router bzw. DHCP-Server.
•  Neue Geräte sind nie automatisch freigeschaltet.

<b>Ganz aus der Ferne (Reiter „Netzwerk“ im Gerätefenster):</b>
•  <i>Einschalten</i>: schaltet ein ausgeschaltetes Gerät über das Netzwerk ein (Wake-on-LAN).
   Im BIOS des Geräts muss Wake-on-LAN eingeschaltet sein.
•  <i>Netzwerkstart zuerst</i>: Das Gerät fragt bei jedem Start zuerst das Tool.
   Ohne Auftrag startet es nach 1–2 Sekunden ganz normal (z. B. Windows).
   Einschalten geht, während das Gerät mit dem Agent verbunden ist.
•  <i>Beim nächsten Start den Agent laden</i>: Beim nächsten Start kommt der Agent statt Windows. Nur einmal.
•  <i>Einschalten und Agent starten</i>: beides zusammen. Das Gerät erscheint danach im Tool,
   ohne dass jemand hingehen muss.
•  Nach Windows-Updates kann die Startreihenfolge zurückgesetzt sein. Das Tool prüft das und zeigt es an."""),

    ("Disk-Image", """<big><b>Ganze Festplatte sichern (Disk-Image)</b></big>

Ein Disk-Image ist eine komplette Kopie der Festplatte.
Nimm es zum Beispiel vor einer Reparatur oder vor einem Festplattentausch.

<b>So gehts:</b>
1.  Gerät mit dem Agent-Stick starten (grüner Punkt).
2.  Gerät wählen und auf <i>Disk-Image erstellen …</i> klicken.
3.  Festplatte wählen und einen Namen eingeben.
4.  <i>Image erstellen</i> klicken.

Der Fortschritt steht links bei der Geräteliste und im Gerätefenster.
Du kannst in der Zeit andere Dinge machen, auch mit anderen Geräten.

<b>Tipp für Windows:</b>
Fahre Windows vorher <b>ganz</b> herunter: Shift-Taste halten und auf „Herunterfahren“ klicken.
Sonst ist die Festplatte im Zustand „Schnellstart“ und lässt sich nicht sauber sichern.

Das fertige Image steht rechts im Reiter <i>Images</i> unter „Nicht einsortiert“."""),

    ("Image zurückspielen", """<big><b>Festplatte wiederherstellen (Image zurückspielen)</b></big>

Damit bringst du ein Gerät auf den Stand des Images zurück.
<b>Achtung:</b> Alles auf der Ziel-Festplatte wird überschrieben.

<b>So gehts:</b>
1.  Gerät mit dem Agent-Stick starten.
2.  <i>Image zurückspielen …</i> klicken.
3.  Image wählen. Darunter siehst du, von welchem Gerät es ist.
4.  Ziel-Festplatte wählen.
5.  Zur Sicherheit den Namen der Festplatte eintippen (zum Beispiel „sda“).
6.  <i>Zurückspielen</i> klicken.

Das Tool prüft zuerst, ob das Image in Ordnung ist. Erst dann wird geschrieben.
Am Ende den Stick abziehen und das Gerät neu starten.

<b>Gut zu wissen:</b>
•  Die Ziel-Festplatte muss mindestens so gross sein wie die alte.
•  Auch Images von Clonezilla funktionieren.
•  Wenn du abbrichst, ist die Festplatte danach unvollständig.

<b>Master-Image</b>
Ein Master-Image ist ein vorbereitetes Windows für viele Geräte (mit Sysprep, Anleitung im Ordner docs).
•  Rechtsklick auf das Image → <i>Als Master-Image markieren</i>. Es bekommt einen Stern ★.
•  Beim Zurückspielen ist dann <i>Danach anpassen</i> eingeschaltet:
     Das Gerät bekommt seinen Namen aus dem Tool und den Windows-Schlüssel.
•  Beim ersten Start richtet sich Windows damit selbst ein."""),

    ("Ordner senden", """<big><b>Ordner an ein Gerät senden</b></big>

Damit legst du Ordner vom NAS auf den Desktop eines Geräts – für alle Benutzer.

<b>Wo die Ordner liegen:</b> auf dem NAS im Ordner <i>Verteilen</i>:
•  <i>Software</i> und <i>Test Files</i>: werden immer ganz gesendet.
•  <i>Content</i>: darin liegen Projekte. Du wählst, welche Projekte gesendet werden.
Die Inhalte änderst du rechts im Reiter <i>Dateien</i>.

<b>So gehts:</b>
1.  Gerät mit dem Agent-Stick starten.
2.  Rechtsklick auf das Gerät → <i>Ordner senden</i> → <i>Software</i>, <i>Test Files</i> oder <i>Content …</i>
3.  Bei Content die Projekte anhaken und <i>Senden</i> klicken.

<b>Gut zu wissen:</b>
•  Gibt es den Ordner schon auf dem Desktop, wird er ersetzt.
•  Bricht etwas ab, bleibt der alte Ordner.
•  Windows muss ganz heruntergefahren sein (Shift + Herunterfahren)."""),

    ("Automatisierung", """<big><b>Geräte automatisch neu aufsetzen</b></big>

Mit der Automatisierung setzt das Tool ein Gerät selbst neu auf, sobald es mit dem Agent startet.

<b>Einrichten (einmal pro Gerät):</b>
1.  Gerät öffnen → Reiter <i>Automatisierung</i>.
2.  Image wählen (Master-Image oder ein eigenes) und die Ziel-Festplatte.
3.  Wenn du willst: vorher Backup, Ordner senden, am Ende Neustart oder Herunterfahren.
4.  Schalter <i>Automatisierung</i> einschalten – oder in der Liste das Häkchen <i>Auto</i> setzen.
Tipp: Speichere die Einstellungen als <i>Vorlage</i> und verwende sie für andere Geräte.

<b>Was dann passiert:</b>
1.  Das Gerät startet mit dem Agent (Stick oder Netzwerkstart).
2.  30 Sekunden Countdown – am Gerät bricht <b>Esc</b> ab, im Tool <i>Abbrechen</i>.
3.  Backup (wenn gewählt), Image zurückspielen, Name und Windows-Schlüssel setzen, Ordner senden.
4.  Neustart. Danach schaltet sich die Automatisierung aus – und nach 24 Stunden wieder ein.

<b>Gut zu wissen:</b>
•  Steckt eine andere Festplatte im Gerät, bricht das Tool ab. Es wird nichts gelöscht.
•  Bei einem Fehler steht das in der Liste (rot), im Gerätefenster und am Bildschirm des Geräts.
     Für einen neuen Versuch das Gerät neu starten.
•  Es laufen höchstens 2 Geräte gleichzeitig (ändern: Menü → Einstellungen). Die anderen warten.
•  Alles anhalten: oben über der Geräteliste der rote Stopp-Knopf ■. Nochmals klicken = weiter."""),

    ("Datei-Backup", """<big><b>Nur Dateien sichern (Datei-Backup)</b></big>

Ein Datei-Backup sichert nur das, was du auswählst. Es ist kleiner und schneller als ein Image.
Ideal vor einer Neuinstallation: Dateien sichern, neu installieren, Dateien zurückspielen.

<b>Backup erstellen:</b>
1.  Gerät mit dem Agent-Stick starten.
2.  <i>Backup erstellen …</i> klicken.
3.  Wählen, was du sichern willst:
     •  <i>Benutzerdaten</i>: Desktop, Dokumente, Bilder, Lesezeichen … pro Benutzer.
     •  <i>Ganze Partitionen</i>: alles auf einem Laufwerk.
     •  <i>Eigene Ordner</i>: du wählst die Ordner selbst.
4.  Wählen, wie es gespeichert wird: als normale Dateien oder als ein Archiv.
5.  Eine Notiz eingeben, wenn du willst (zum Beispiel „vor Neuinstallation“).
6.  <i>Backup erstellen</i> klicken.

<b>Zurückspielen oder herunterladen:</b>
•  Rechts im Reiter <i>Backups</i> (oder im Gerätefenster) das Backup doppelklicken.
•  <i>Ins System</i>: Dateien zurück auf das Gerät. Alte Benutzer kannst du neuen zuordnen.
•  <i>In einen Ordner</i>: Dateien auf den Server oder einen USB-Stick kopieren.
•  Vorhandene Dateien werden nicht überschrieben. Die gesicherte Datei heisst dann „… (wiederhergestellt)“.

Windows vor dem Zurückspielen <b>ganz</b> herunterfahren (Shift + Herunterfahren).

Mit <i>Notiz …</i> änderst du die Notiz. Mit <i>Löschen …</i> entfernst du ein Backup vom NAS."""),

    ("Windows / Linux installieren", """<big><b>Betriebssystem installieren</b></big>

<b>1. ISO-Datei hinzufügen (einmal pro Version)</b>
•  <i>Tools → ISO hinzufügen …</i> oder die Datei rechts in den Reiter <i>Images</i> ziehen.
•  Das Tool erkennt, was in der ISO steckt, und sortiert sie unter <i>Betriebssysteme</i> ein.

<b>2. Direkt auf ein Gerät installieren</b>
1.  Gerät mit dem Agent-Stick starten.
2.  <i>OS installieren …</i> klicken.
3.  ISO und Ziel-Festplatte wählen.
4.  Einstellungen wählen: Benutzer, Passwort, bei Windows die Edition.
     Bei Linux auch die Software: zum Beispiel Desktop, SSH-Server (Fernzugriff) oder weitere Pakete.
     Bei Debian gibt es die ganze Auswahl wie im Debian-Installer.
5.  Starten. Das Gerät startet danach neu und installiert selbständig.
     An der Maschine wird nichts gefragt. Was du nicht auswählst, wird nicht installiert.

Der <b>Computername</b> ist immer der Gerätename im Tool. Willst du einen anderen, benenne das Gerät um.
Windows erlaubt nur 15 Zeichen ohne Sonderzeichen. Der Dialog zeigt dir, wie der Name ankommt.

Direkt installieren geht mit Windows 10/11, Ubuntu Desktop ab 24.04, Debian und Fedora.
Bei anderen Systemen zeigt das Tool den Grund. Dann hilft ein Boot-Stick (nächstes Kapitel).

<b>Windows-Produktschlüssel</b>
•  Viele Geräte haben den Schlüssel im BIOS. Das Tool liest ihn automatisch.
•  Einen eigenen Schlüssel kannst du im Gerätefenster unter <i>Übersicht</i> hinterlegen.
•  Bei der Installation wird der Schlüssel dann verwendet."""),

    ("Sticks erstellen", """<big><b>USB-Sticks erstellen</b></big>

<b>Boot-Stick aus ISO</b> (wie das Programm „Rufus“)
•  Rechts eine ISO wählen und <i>Boot-Stick aus ISO …</i> klicken.
•  Mit dem Stick kannst du Windows oder Linux an jedem Computer installieren.
•  Bei Windows kannst du Dinge einstellen: ohne Microsoft-Konto, ohne TPM-Prüfung, Region Schweiz.
•  Das Tool kann den Stick vorher testen. So erkennst du gefälschte Sticks.

<b>Restore-Stick aus Image</b>
•  Rechts ein Image wählen und <i>Restore-Stick aus Image …</i> klicken.
•  Der Stick enthält das Image. Er stellt ein Gerät auch <b>ohne Netzwerk</b> wieder her.

<b>Agent-Stick</b>
•  <i>Menü → Agent-USB-Stick erstellen …</i> (siehe „Erste Schritte“).

Bei allen Sticks gilt: Der Stick wird dabei gelöscht."""),

    ("USB klonen", """<big><b>USB-Stick oder externe Festplatte klonen</b></big>

Klonen heisst: Ein Datenträger wird komplett auf einen anderen kopiert.
Mit allen Partitionen, Dateien und – falls vorhanden – mit der Startfähigkeit.

<b>So gehts:</b>
1.  Beide Datenträger am Server einstecken.
2.  <i>Extras → USB klonen …</i> öffnen.
3.  <b>Quelle</b> wählen: Von hier wird kopiert. Die Quelle wird nur gelesen.
4.  <b>Ziel</b> wählen: Hierhin wird kopiert. <b>Alles auf dem Ziel wird gelöscht.</b>
5.  Art wählen:
     •  <i>Nur belegte Bereiche</i>: schneller. Empfohlen.
        Das Ziel darf sogar kleiner sein, wenn alle Partitionen darauf Platz haben.
     •  <i>Alles 1:1</i>: kopiert jeden Sektor. Für verschlüsselte oder unbekannte Datenträger.
        Hier kannst du danach auch vergleichen lassen.
6.  <i>Klonen</i> klicken und bestätigen.

Das Tool zeigt, ob das Ziel gross genug ist, wie schnell es kopiert und wie lange es noch dauert.
Mit <i>Abbrechen</i> stoppst du. Das Ziel ist dann aber unvollständig.

<b>Gut zu wissen:</b>
•  Nach dem Klonen haben beide Datenträger dieselben Kennungen.
   Schliesse sie nicht gleichzeitig am selben Windows-PC an.
•  Ist das Ziel grösser, bleibt der Rest frei. Du kannst ihn später nutzen."""),

    ("USB formatieren", """<big><b>USB-Stick oder externe Festplatte formatieren</b></big>

<b>So gehts:</b>
1.  Datenträger am Server einstecken.
2.  <i>Extras → USB formatieren …</i> öffnen.
3.  Datenträger wählen. Darunter siehst du, was jetzt darauf ist.
4.  Dateisystem wählen (siehe unten). Das Tool schlägt eines vor.
5.  Einen Namen eingeben, wenn du willst.
6.  <i>Formatieren</i> klicken und bestätigen. <b>Alle Daten gehen verloren.</b>

<b>Welches Dateisystem wofür?</b>
•  <b>FAT32</b>: läuft fast überall (Windows, Mac, Linux, TV, Auto). Dateien höchstens 4 GB.
•  <b>exFAT</b>: für grosse Dateien. Windows, Mac, Linux und viele TVs. Gut zum Austauschen.
•  <b>NTFS</b>: Windows-Standard. Der Mac kann nur lesen.
•  <b>ext4</b>, <b>Btrfs</b>, <b>XFS</b>, <b>F2FS</b>, <b>ext3</b>, <b>ext2</b>: für Linux.
•  <b>HFS+</b>: für ältere Macs.
•  <b>UDF</b>: für grosse Dateien, Windows, Mac und Linux.
•  <b>FAT16</b>: für sehr alte Geräte, nur bis 4 GB.
•  <b>Kein Dateisystem</b>: macht den Datenträger nur leer.

Wenn du unsicher bist: Bis 32 GB <b>FAT32</b>, darüber <b>exFAT</b>.

<b>Partitionsschema</b>
•  <b>MBR</b>: passt überall. Für Datenträger bis 2 TB.
•  <b>GPT</b>: für Festplatten über 2 TB und moderne Computer.

<b>Vorher</b> (optional)
•  <i>Schnelltest</i>: erkennt gefälschte Sticks, die mehr Platz vortäuschen.
•  <i>Mit Nullen überschreiben</i>: alte Daten sind danach sicher weg. Dauert lange.
•  <i>Vollständiger Test</i>: prüft jeden Block. Dauert sehr lange."""),

    ("Demo-Gerät", """<big><b>Das Tool vorführen (Demo-Gerät)</b></big>

Zum Zeigen gibt es ein Gerät, das es gar nicht gibt: den <b>DEMO-PC</b>.

<b>So gehts:</b>
1.  <i>Extras → Demo-Gerät (Vorführung)</i> anhaken.
2.  Nach ein paar Sekunden steht links <i>DEMO-PC</i> mit grünem Punkt.
3.  Jetzt kannst du alles zeigen: Image erstellen, zurückspielen, Backup, Ordner senden, Automatisierung …
     Ein Auftrag dauert etwa eine Minute.

<b>Einen Fehler zeigen:</b>
<i>Extras → Demo: nächster Auftrag mit Fehler</i>. Der nächste Auftrag bricht ab, der Balken wird rot.

<b>Gut zu wissen:</b>
•  Der DEMO-PC fasst nichts an. Es gibt keine echte Festplatte dahinter.
•  Andere Geräte im Netzwerk merken nichts davon.
•  Ein Image vom DEMO-PC kann nur auf den DEMO-PC zurückgespielt werden.
•  Zum Beenden das Häkchen wieder entfernen."""),

    ("Anzeigen im Fenster", """<big><b>Was die Anzeigen bedeuten</b></big>

<b>Oben rechts: Serverlast</b>
•  <b>CPU</b>: wie stark der Prozessor arbeitet.
•  <b>RAM</b>: wie viel Arbeitsspeicher belegt ist.
•  <b>LAN</b>: wie viel über das Netzwerk geht. ↓ empfangen, ↑ gesendet.
•  Die Kurve zeigt die letzte Minute. Über 90 % wird die Zahl rot.
•  Fahre mit der Maus darüber, dann siehst du mehr Details.

<b>NAS-Zeile</b>
•  <span foreground="#2e7d32">●</span> grün: NAS ist verbunden. Daneben steht der freie Speicher.
•  <span foreground="#c62828">●</span> rot: NAS ist nicht verbunden. Klicke auf das Zahnrad.

<b>Reiter rechts</b>
•  <i>Images</i>: alle Disk-Images und ISO-Dateien, in Ordnern sortiert.
•  <i>Dateien</i>: die Dateien auf dem NAS, wie in einem Datei-Manager.
   Dateien und Ordner kannst du aus dem Dateimanager hineinziehen. Dann werden sie auf das NAS kopiert.
   So kommen zum Beispiel Clonezilla-Images von einer externen Festplatte aufs NAS.
•  <i>Backups</i>: alle Datei-Backups, nach Gerät sortiert, mit Suche.

<b>Fortschritt</b>
In der Geräteliste siehst du bei jedem Gerät einen Balken mit Prozent und Restzeit.
•  <span foreground="#2e7d32">grün</span>: Der Auftrag läuft.
•  <span foreground="#c62828">rot</span>: Der Auftrag ist fehlgeschlagen. Daneben steht, bei wie viel Prozent.
   Den Grund findest du im Gerätefenster unter <i>Aufträge</i>. Der rote Balken bleibt, bis der nächste Auftrag startet.

<b>Spalte „Auto“ und Status der Automatisierung</b>
•  Häkchen gesetzt: Die Automatisierung ist eingeschaltet.
•  Häkchen grau: Alles ist pausiert (roter Stopp-Knopf ■ gedrückt).
•  <i>startet in 25 s</i>: Countdown läuft. Am Gerät bricht Esc ab.
•  <i>wartet (Platz 2)</i>: Es laufen schon so viele Geräte wie erlaubt. Das Gerät kommt gleich dran.
•  <i>Schritt 2/5: Image zurückspielen</i>: Die Automatisierung arbeitet.
•  <i>wieder aktiv in 5 h</i>: Sie ist fertig und schaltet sich nach 24 Stunden wieder ein.
•  <span foreground="#c62828">rot</span>: Es gab einen Fehler. Details im Gerätefenster.

<b>Stern ★ bei Images</b>
Das Image ist als Master-Image markiert."""),

    ("Neuer Rechner", """<big><b>Das Tool auf einen neuen Rechner umziehen</b></big>

Alles, was das Tool weiss, lässt sich in <b>eine Datei</b> speichern.
So musst du auf einem neuen Rechner nichts von vorne einrichten.

<b>Auf dem alten Rechner:</b>
1.  <i>Menü → Einstellungen exportieren …</i> öffnen.
2.  Auswählen, was mit soll. Am besten alles:
     •  NAS-Verbindung und Einstellungen
     •  Geräte mit Ordnern, Verlauf, Notizen und Windows-Schlüsseln
     •  Agent-Schlüssel: Dann funktionieren alle bisherigen Agent- und Restore-Sticks weiter.
     Die Vorlagen der Automatisierung kommen mit den Einstellungen mit.
3.  <i>Exportieren …</i> klicken und die Datei speichern, zum Beispiel auf einem USB-Stick.

<b>Auf dem neuen Rechner:</b>
1.  Das Tool installieren (<tt>sudo ./install.sh</tt>).
2.  <i>Menü → Einstellungen importieren …</i> öffnen und die Datei wählen.
3.  Prüfen, was übernommen wird, und <i>Importieren</i> klicken. Das Tool startet neu.
4.  <i>Menü → NAS-Verbindung …</i>: einmal das <b>Passwort</b> eingeben und <i>Einhängen</i> klicken.

<b>Gut zu wissen:</b>
•  Das NAS-Passwort ist aus Sicherheitsgründen nicht in der Datei.
•  Images, Backups und ISOs liegen auf dem NAS. Sie sind sofort wieder da.
•  Bewahre die Datei sicher auf, wie ein Passwort. Sie enthält Schlüssel.
•  Vorhandene Daten auf dem neuen Rechner werden vor dem Import gesichert.

<b>Nur die NAS-Verbindung</b>
Im NAS-Fenster gibt es <i>Exportieren …</i> und <i>Importieren …</i>.
Damit nimmst du nur die NAS-Einstellungen mit (ohne Passwort)."""),

    ("Probleme lösen", """<big><b>Wenn etwas nicht klappt</b></big>

<b>Das Gerät erscheint nicht im Tool</b>
•  Ist das Gerät am Netzwerkkabel? WLAN geht nicht.
•  Sind Gerät und Server im selben Netzwerk?
•  Firewall auf dem Server: UDP-Port 47811 freigeben.
•  Startet das Gerät wirklich vom Stick? Im Boot-Menü den USB-Stick wählen.

<b>Das NAS ist rot</b>
•  Ist das NAS eingeschaltet?
•  Stimmen Benutzer und Passwort? <i>Menü → NAS-Verbindung … → Testen</i>.

<b>Windows lässt sich nicht sichern oder zurückspielen</b>
•  Windows ganz herunterfahren: Shift halten und „Herunterfahren“ klicken.
•  Mit BitLocker verschlüsselte Laufwerke kann das Tool nur 1:1 sichern, nicht die Dateien lesen.

<b>Ein USB-Stick wird nicht angezeigt</b>
•  Neu einstecken und auf ⟳ (neu suchen) klicken.
•  Die Festplatte des Servers wird nie angezeigt. Das ist ein Schutz.

<b>Ein Stick ist plötzlich zu klein oder macht Fehler</b>
•  Beim Formatieren den <i>Schnelltest</i> wählen. Er erkennt gefälschte Sticks.

<b>Die Automatisierung startet nicht</b>
•  Steht in der Liste <i>Einstellungen unvollständig</i>? Im Reiter <i>Automatisierung</i> steht, was fehlt.
•  Steht <i>pausiert</i>? Oben über der Geräteliste den roten Stopp-Knopf ■ nochmals klicken.
•  Steht <i>wieder aktiv in …</i>? Sie lief schon. Häkchen <i>Auto</i> neu setzen, wenn sie sofort laufen soll.
•  Nach einem Fehler oder Esc: Gerät neu starten, dann versucht sie es wieder.
•  Meldung „Agent zu alt“: Agent-Stick neu erstellen bzw. Netzwerkstart neu vorbereiten.

<b>Name oder Windows-Schlüssel wurden nicht gesetzt</b>
•  Das geht nur bei einem Master-Image, das mit Sysprep vorbereitet wurde. Das Protokoll sagt es.

<b>Fehlermeldung „Hilfsprogramm … sudo-Regel“</b>
•  Auf dem Server einmal <tt>sudo ./install.sh</tt> im Tool-Ordner ausführen."""),

    ("Tastenkürzel", """<big><b>Tastenkürzel</b></big>

<tt>F1        </tt>  Diese Anleitung
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
]


class HelpWindow(Gtk.Window):
    def __init__(self, parent: Gtk.Window, chapter: str | None = None):
        super().__init__(title="So funktioniert das Tool")
        self.set_transient_for(parent)
        self.set_default_size(980, 720)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        for title, text in CHAPTERS:
            label = Gtk.Label(xalign=0, yalign=0, wrap=True, selectable=True, max_width_chars=90,
                              margin=24, margin_top=18)
            label.set_markup(text)
            label.set_line_wrap(True)
            self.stack.add_titled(scrolled(label), title, title)
        sidebar = Gtk.StackSidebar(stack=self.stack)
        sidebar.set_size_request(220, -1)
        box = Gtk.Box()
        box.pack_start(sidebar, False, False, 0)
        box.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 0)
        box.pack_start(self.stack, True, True, 0)
        self.add(box)
        self.connect("key-press-event", self._on_key)
        self.show_all()
        if chapter:
            self.stack.set_visible_child_name(chapter)

    def _on_key(self, _w, event) -> bool:
        from gi.repository import Gdk
        if event.keyval == Gdk.KEY_Escape:
            self.destroy()
            return True
        return False
