# Prüfung der Hilfe (F1, „So funktioniert das Tool“)

Stand: 31.10.2026, geprüft gegen Code und README (Commit 9d60ee7). Datei: `okula_recovery/help_window.py`.
**Status:** H1–H22 umgesetzt am 31.10.2026 (Ä-024). H23–H25 erledigt (Ä-025). Offen: Sichtprüfung.

## A – Falsch oder veraltet

| Nr | Kapitel | Problem | Vorschlag |
|---|---|---|---|
| H1 | Probleme lösen | „Menü → NAS-Verbindung … → **Testen**“ – der Knopf heisst **„Verbindung testen“** | Text anpassen |
| H2 | Erste Schritte, Probleme lösen | Firewall: nur UDP 47811 genannt. Netzwerkstart braucht zusätzlich eingehend **UDP 67, 69, 4011** (Proxy-DHCP, TFTP) und **TCP 47813** (HTTP, `pxe.HTTP_PORT`) | Ports ergänzen, getrennt: „immer“ und „nur bei Netzwerkstart“ |
| H3 | Netzwerkstart | „Boot-Menü öffnen (meist F12)“ widerspricht der neuen Tabelle. Schritt 2 erwähnt den Knopf *Herunterladen* (ISO) nicht | Auf die Tabelle in „Gerät verbinden“ verweisen; Schritt 2: „Debian-Live-ISO wählen bzw. *Herunterladen*, dann *Vorbereiten*“ |
| H4 | Image zurückspielen | „Das Tool prüft zuerst, ob das Image in Ordnung ist“ – das ist ein Häkchen („…vollständig prüfen (empfohlen)“, Standard an). Die Option „Maschine danach herunterfahren“ fehlt | Beides als Option beschreiben |
| H5 | Datei-Backup | „Vorhandene Dateien werden nicht überschrieben“ – es gibt die Option **„Vorhandene Dateien überschreiben“**. Die Wahlen heissen „Ins **installierte** System …“ und „**Herunterladen** in einen Ordner“ | Texte an die Oberfläche angleichen, Option erklären |
| H6 | Disk-Image | Der Dialog hat die Felder **Disk, Name im Archiv, Ziel** (Ordner) und „Maschine danach herunterfahren“. Die Hilfe nennt nur Festplatte und Name. „Steht unter Nicht einsortiert“ gilt nur ohne Ziel | Schritte ergänzen |
| H7 | Anzeigen im Fenster | Menüpunkt heisst „Inventar exportieren **(CSV/PDF)** …“. Rechtsklick auf ein **Gerät** → „Inventar exportieren …“ fehlt | Text anpassen |
| H8 | Gerät verbinden → Gerätefenster | Liste der Reiter ohne die neuen Zeilen in *Übersicht*: Starttasten, Windows 11, Garantie bis, Windows-Schlüssel | Ergänzen |

## B – Fehlt

| Nr | Kapitel | Problem | Vorschlag |
|---|---|---|---|
| H9 | Überblick | Neue Funktionen fehlen: Netzwerkstart/Wake-on-LAN, Inventar-Export, Garantie, Windows 11, Restore auf kleinere Disk, Demo | Aufzählung ergänzen (je eine Zeile) |
| H10 | Automatisierung | Fehlt: Option „Image dafür anpassen“ (kleinere Disk), Abschnitt *Anpassen* (Region Schweiz, lokales Konto), Vorlage anwenden/löschen, „Nach 3 Tagen wieder einschalten“ ist abschaltbar, **Warnung:** Schalter ein bei verbundenem Gerät = Start in 30 s, Disk wird gelöscht; vor dem Neustart Stick abziehen | Ergänzen |
| H11 | neu: **Geräte verwalten** | Kein Kapitel für: Umbenennen (= Computername), Ordner anlegen/umbenennen/löschen, verschieben, „Aus der Liste löschen“ (nur wenn nicht verbunden), Herunterfahren/Neu starten, Inventar neu einlesen | Neues Kapitel |
| H12 | neu: **Images verwalten** | Kein Kapitel für: Ordner im Reiter *Images*, einsortieren, „Nach Nicht einsortiert“, Löschen, Details und Prüfsummen, F5 | Neues Kapitel |
| H13 | neu: **Typischer Ablauf** | Kein roter Faden für Neulinge | Kapitel „Von A bis Z“: Gerät erfassen → Image sichern → Master-Image → Automatisierung → Inventar exportieren |
| H14 | neu: **Inventar, Garantie, Windows 11** | Stehen heute versteckt unter „Anzeigen im Fenster“ | Eigenes Kapitel; in „Anzeigen“ nur die Farben/Symbole |
| H15 | Master-Image | Steckt im Kapitel „Image zurückspielen“; „Anleitung im Ordner docs“ – ein Laie findet docs nicht | Eigenes Kapitel mit Kurzfassung von MASTER-IMAGE.md (Audit-Modus, Sysprep, Stick, markieren) |
| H16 | Probleme lösen | Fehlt: Zieldisk zu klein; Garantie-Abfrage scheitert (Schlüssel, Internet, `install.sh`); Gerät startet nach dem Neustart wieder den Agent (Stick steckt); Wake-on-LAN geht nicht (BIOS, Netzteil, Kabel); Meldung „Ruhezustand bzw. Schnellstart“; Windows 11 zeigt „?“ | Ergänzen |
| H17 | Sticks erstellen | Restore-Stick: wie man ihn am Gerät benutzt (starten, was passiert, Dauer) fehlt | 3–4 Schritte ergänzen |
| H18 | Tastenkürzel | Esc (schliesst Hilfe und Fenster) fehlt | Ergänzen |

## C – Sprache und Begriffe

| Nr | Problem | Vorschlag |
|---|---|---|
| H19 | Dieselbe Sache, verschiedene Wörter: Festplatte / Disk / Ziel-Festplatte / **Zieldisk** / Datenträger; Windows-Schlüssel / Windows-Key / Produktschlüssel; Agent / Agent-Stick | Wie in der Oberfläche: „Disk“ (einmal erklärt als Festplatte/SSD), „Zieldisk“, „Windows-Schlüssel“; Datenträger nur für USB |
| H20 | Fachwörter nicht erklärt: Sysprep, BIOS/UEFI, Wake-on-LAN, TPM, Secure Boot, PXE, SMART, Firewall/Port, CSV, Einhängen, Inventar | In „Wichtige Begriffe“ je 1–2 Sätze |
| H21 | Uneinheitliche Form: Einrückungen 3 bzw. 5 Leerzeichen, „Shift + Herunterfahren“ / „Shift-Taste halten …“, Nummern und Punkte gemischt | Einheitlich: Schritte nummeriert, Hinweise mit •, eine Schreibweise für Tasten |
| H22 | **Handbuch-Stil ohne Anrede (Wunsch Dominik, 31.10.)** – weder „du“ noch „Sie“, überall: Hilfe (55 Zeilen mit „du“, 16 Befehle wie „Klicke“), Oberfläche (Gerätefenster „…starten Sie…“, `usbtools.py` „damit du …“), Fortschrittstexte in Ich-Form („Prüfe Stick …“, „Starte …“, ~20 Stellen) | Schritte im Infinitiv („Gerät mit dem Agent-Stick starten.“), Beschreibungen sachlich („Links stehen alle Geräte.“, „Das Gerät lässt sich … verschieben.“), Fortschritt als Vorgang („Stick wird geprüft …“). Regel in CLAUDE.md aufnehmen |

## D – Aufbau

| Nr | Problem | Vorschlag |
|---|---|---|
| H23 | Reihenfolge folgt nicht dem Arbeitsablauf | Überblick → Begriffe → Erste Schritte → **Typischer Ablauf** → Gerät verbinden → Netzwerkstart → **Geräte verwalten** → Disk-Image → Image zurückspielen → Datei-Backup → **Master-Image** → Automatisierung → Ordner senden → **Inventar, Garantie, Windows 11** → OS installieren → Sticks → USB klonen → USB formatieren → **Images verwalten** → Anzeigen → Neuer Rechner → Probleme lösen → Tastenkürzel → Demo |
| H24 | Hilfe hat keine Suche | Suchfeld über der Kapitelliste (filtert Kapitel nach Wort) |
| H25 | Hilfe veraltet leicht | Regel in CLAUDE.md: neue/geänderte Funktion → passendes Kapitel mitändern; Test, der prüft, dass alle Menüeinträge in der Hilfe vorkommen |
