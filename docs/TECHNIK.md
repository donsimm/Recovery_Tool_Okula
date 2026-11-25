# Okula Recovery Tool – Technik und Details

Kurzfassung: [README](../README.md). Bedienung Schritt für Schritt: Hilfe im Tool (F1).

Backups und Disk-Images von Maschinen im LAN, gespeichert auf einem NAS.
Server: Debian 13 + Xfce, Python 3 + GTK 3.
Bugs, Änderungen, Ideen und Entscheidungen: [docs/AENDERUNGEN.md](AENDERUNGEN.md) · spontane Notizen: [docs/EINGANG.md](EINGANG.md).

![Oberfläche](screenshot.png)

Schreibweise in README, Hilfe und Oberfläche: Handbuch-Stil ohne Anrede, Schritte im Infinitiv; Begriffe wie in der
Oberfläche (Disk, Zieldisk, Datenträger für USB, Windows-Schlüssel, Agent-Stick).

- **Menüleiste** (Beschriftungen zentral in `MENU_LABELS`, `okula_recovery/ui.py`):
  - **Menü:** NAS-Verbindung … (Ctrl+N), Einstellungen … (Bandbreite, Automatisierung, Garantie-Abfrage), Agent-USB-Stick erstellen …, Inventar exportieren (CSV/PDF) …, Einstellungen exportieren / importieren …, Beenden
  - **Tools:** Gerät öffnen (Ctrl+O), Disk-Image erstellen, Image zurückspielen, OS installieren, Backup erstellen, Backup zurückspielen, Ordner senden, Inventar neu einlesen, Restore-Stick aus Image, ISO hinzufügen, Boot-Stick aus ISO, Netzwerkstart (PXE), Images aktualisieren (F5)
  - **Extras:** USB klonen, USB formatieren, Demo-Gerät (Vorführung), Demo: nächster Auftrag mit Fehler, Demo-Daten zurücksetzen
  - **Hilfe:** **So funktioniert das Tool** (F1, siehe [Hilfe](#hilfe-f1-und-tastenkürzel)), Tastenkürzel, Über
- **Links (Geräte):** Alle Geräte, die je mit dem Agent-Stick gebootet wurden, in einer Ordnerstruktur. ● grün = verbunden, ● rot = nicht verbunden (Erklärung auch unter Hilfe → So funktioniert das Tool); dazu Status, Betriebssystem, zuletzt verbunden und IP. Details siehe [Geräte](#geräte).
- **Rechts (NAS):**
  - **Statuszeile:** ● grün = NAS verbunden, ● rot = nicht verbunden bzw. nicht eingerichtet. Daneben der freie Speicher: grün, wenn genug frei ist; rot, wenn weniger als 100 GB frei sind. Das Tool prüft den Status beim Start und danach alle 30 s.
  - **Reiter:** *Images* (Ordnerbaum, siehe unten), *Dateien* (Dateiverwaltung) und *Backups* (alle Datei-Backups).
- **NAS-Verbindung einrichten:** Menü → NAS-Verbindung … oder das Zahnrad in der Statuszeile. Das Fenster enthält Protokoll, Host, Freigabe (mit „Freigaben suchen“), Benutzer, Passwort, Einhängepunkt, die Knöpfe Verbindung testen, Einhängen, Aushängen und Speichern sowie die Prüfdetails.

## Server-Installation (Debian 13)

```bash
sudo apt install git
git clone https://github.com/donsimm/Recovery_Tool_Okula.git recovery_tool_okula
cd recovery_tool_okula
git checkout claude/blissful-goldberg-mo3xda   # bis zum Merge
sudo ./install.sh --autostart
```

`install.sh` installiert die Pakete, kopiert das Tool nach `/opt/okula-recovery` (gehört root), legt die Root-Helfer (`okula-make-stick`, `okula-nas-mount`, `okula-warranty` in `/usr/local/sbin`) samt sudo-Regel für den angemeldeten Benutzer an, erstellt den Menüeintrag und mit `--autostart` den Start nach dem Login. Dazu kommen die Grundlage für virtuelle Maschinen und die Netzwerkbrücke `br0` (siehe [Virtuelle Maschinen – Grundlage](#virtuelle-maschinen--grundlage)).

**`install.sh` am Server selbst ausführen**, nicht aus der Ferne (SSH): Beim Einrichten der Netzwerkbrücke ist der Server einige Sekunden offline; misslingt sie, stellt das Skript die alte Verbindung nach 45 s wieder her. `sudo ./install.sh --no-bridge` überspringt die Brücke (VMs haben dann kein Netzwerk im LAN). Nach der ersten Installation mit VM-Paketen einmal ab- und wieder anmelden (Gruppe `libvirt`).

Starten: Menü → System → *Okula Recovery Tool* oder `cd /opt/okula-recovery && python3 -m okula_recovery`.
Update: im Repo `git pull`, dann wieder `sudo ./install.sh`.

### Firewall

Nur nötig, wenn auf dem Server eine Firewall läuft. Prüfen mit `sudo nft list ruleset` (leer = nichts zu tun).
Eingehend freigeben:

| Wann | Port | Wofür |
|---|---|---|
| immer | UDP 47811 | Beacons der Agents – sonst findet das Tool die Geräte nicht |
| nur Netzwerkstart | UDP 67, 69, 4011 | Proxy-DHCP und TFTP |
| nur Netzwerkstart | TCP 47813 | HTTP-Dienst für den Agent-Teil |

Beispiel mit ufw: `sudo ufw allow 47811/udp`, für den Netzwerkstart zusätzlich `sudo ufw allow 67,69,4011/udp && sudo ufw allow 47813/tcp`.
Die Steuer- und Datenverbindung zum Agent (TCP 47812, TLS 1.3 mit PSK) baut der Server selbst auf – dafür ist eingehend nichts nötig.

### NAS einrichten (z. B. Synology)

Im NAS (Synology DSM: Systemsteuerung):
1. **Freigegebener Ordner** anlegen, z. B. `recovery`.
2. Eigenen **Benutzer** anlegen (nicht den Admin) und ihm Lese-/Schreibrecht nur auf diese Freigabe geben.
3. **Dateidienste → SMB** aktivieren, Mindestversion SMB2 (Standard in DSM 7).

Im Tool unter Menü → NAS-Verbindung …:
1. Host (IP des NAS), Benutzer und Passwort eingeben.
2. **Freigaben suchen**, dann die Freigabe aus der Liste wählen.
3. **Einhängen**. Bei Erfolg zeigt die Statuszeile rechts „● NAS verbunden“, und das Tool listet die Images.

Das Passwort speichert nur der Root-Helfer, in `/etc/okula-recovery/nas.cred` (root, `0600`). Es steht nie in der Konfiguration oder in Prozess-Argumenten. Nach dem nächsten Start hängt das Tool das NAS automatisch wieder ein. Fehlermeldungen von `mount` und `smbclient` werden als Hinweis angezeigt, etwa bei einem falschen Passwort, einer fehlenden Freigabe oder einer unpassenden SMB-Version.

Für NFS als Freigabe den Exportpfad angeben (z. B. `/volume1/recovery`) und im NAS die IP des Servers erlauben.

**NAS-Webseite öffnen:** Knopf im Fenster NAS-Verbindung (neben „Verbindung testen“) und kleines Symbol in der NAS-Statuszeile. Öffnet die Weboberfläche des NAS im Browser, z. B. Synology DSM unter `https://<Host>:5001`. Protokoll und Port stehen im NAS-Fenster (Zeile „NAS-Webseite“: https 5001 oder http 5000). Ohne Host ist der Knopf ausgegraut. Der Browser startet immer als normaler Benutzer.

### Images in Ordner einsortieren

Der Reiter *Images* zeigt einen aufklappbaren Baum:
- **Nicht einsortiert** steht ganz oben, neueste zuerst. Hier landen neue Images und alle, die noch in keinem Ordner liegen, auch bestehende Clonezilla-Images.
- **Eigene Ordner** mit bis zu **3 Ebenen**, z. B. *Standort › Abteilung › Gerät*. Anlegen, Umbenennen und Löschen über die Knöpfe oder per Rechtsklick. Ein Ordner lässt sich nur löschen, wenn er leer ist.
- **Icons:** OKULA-Emblem = mit diesem Tool erstelltes Image, orange Disk = Clonezilla-Image, Datei-Symbol = sonstiges Image (einzelne Image-Datei `.img`, `.dd` …). Eine Legende steht unter dem Baum (Okula-Image, Clonezilla, Sonstiges Image, Windows-ISO, Linux-ISO, Sonstige ISO).
- **Restore-Stick aus Image …:** Der Knopf steht unter dem Baum und ist aktiv, sobald ein Okula- oder Clonezilla-Image gewählt ist.
- **Einsortieren per Maus:** Ein Image auf einen Ordner ziehen oder zurück auf „Nicht einsortiert“. Ganze Ordner lassen sich ebenfalls in einen anderen Ordner ziehen, ohne die 3 Ebenen zu überschreiten. Rechtsklick → „Nach ‚Nicht einsortiert‘“ geht auch.

Die Ordner sind echte Ordner auf dem NAS unter `Archiv/`, z. B. `Archiv/Zürich/Buchhaltung/PC-Buchhaltung/<Image>`. Verschieben ist ein Umbenennen auf derselben Freigabe und geht auch bei grossen Images sofort. Nicht einsortierte Images liegen unter `images/` (bzw. bei Clonezilla dort, wo sie abgelegt wurden).

### Dateien auf dem NAS verwalten

Rechts gibt es zwei Reiter:
- **Images:** Alle gefundenen Images. **Löschen** entfernt das gewählte Image.
- **Dateien:** Dateiverwaltung der Freigabe. Doppelklick öffnet einen Ordner, ↑ oder Backspace führt eine Ebene zurück. Dazu kommen **Neuer Ordner**, **Umbenennen** (F2) und **Löschen** (Entf, mit Mehrfachauswahl).
- **Auf das NAS kopieren:** Dateien und ganze Ordner – z. B. **Clonezilla-Images** von einer externen Platte – aus dem Dateimanager in den Reiter *Dateien* ziehen (auf einen Ordner = dorthin, sonst in den offenen Ordner) oder über den Knopf **Hochladen** (Dateien … / Ordner …). Kopiert wird im Hintergrund mit Fortschritt, Tempo, Restzeit und Abbrechen; vorher prüft das Tool Platz und Namen (SMB-taugliche Zeichen). Bestehendes wird nie überschrieben („Name (2)“). Jeder Eintrag entsteht zuerst als versteckter `.Name.partial` und wird erst vollständig umbenannt – ein Abbruch hinterlässt nichts Halbes. Links werden übersprungen. Ein kopiertes Clonezilla-Image erkennt das Tool und zeigt es im Reiter *Images*.

Vor dem Löschen zeigt das Tool Anzahl und Grösse der Dateien und fragt nach. Das Tool hat keinen Papierkorb, gelöschte Daten sind weg. Falls im NAS ein Papierkorb für die Freigabe aktiv ist, greift dieser. Alle Aktionen bleiben innerhalb des Einhängepunkts: `..` und Links nach draussen werden abgewiesen, Links werden nie verfolgt.

Das Tool startet maximiert. **F11** schaltet auf Vollbild ohne Titelleiste und wieder zurück.

**Serverlast:** Oben rechts zeigt das Tool die Auslastung des Servers – CPU, RAM (ohne Cache) und LAN (↓ empfangen, ↑ gesendet) mit Verlauf der letzten Minute, gemessen jede Sekunde aus `/proc`. Maus darüber: Kerne und Last, Swap, Netzwerkkarte und Verbindungsgeschwindigkeit. Ab 90 % wird der Wert rot. Für die Kurven braucht es `python3-gi-cairo` (installiert `install.sh`).

**Spaltenbreiten (Ä-032):** In Geräte, Images, Dateien, Backups und in den Tabellen des Gerätefensters (Aufträge, Disks, Images, Backups, Netzwerk, Verlauf – Breiten für alle Geräte gemeinsam) sind alle Spalten mit der Maus verstellbar; keine Spalte dehnt sich (eine leere Spalte am Ende nimmt den Rest), frühere Mindestbreiten sind weg. Gemerkt werden nur verstellte Spalten (`uikit.remember_columns`, GTK setzt beim Ziehen `fixed-width`) in `~/.config/okula-recovery/spalten.json` (`colstate.py`) – je Rechner, nicht im Export.

**Bandbreite begrenzen (I-030):** Menü → **Einstellungen …** → Rahmen *Bandbreite* (ganz oben): Schalter, Höchstwert 10–10'000 Mbit/s (Standard 300, daneben in MB/s), optional nur im Zeitfenster von/bis mit Tagen (Standard Mo–Fr 07:00–18:00; über Mitternacht zählt der Morgen zum Starttag, von = bis = ganzer Tag). Standard: aus (unbegrenzt). Umsetzung nur im Tool (`bandwidth.py`): ein gemeinsamer Token-Bucket für alle Aufträge, eingehängt in `wire.send_data`/`wire.recv_frame` (nur Daten-Frames) über `wire.set_limiter` – der Agent bleibt unverändert, kein neuer Agent-Stick; beim Empfangen bremst das verzögerte Lesen den Absender über TCP. Portionen von 128 KiB werden der Reihe nach reserviert, dadurch teilen sich parallele Aufträge die Grenze gerecht. Die Grenze wird bei jeder Portion neu gelesen (Änderungen und Zeitfenster wirken sofort). Gilt auch für das Demo-Gerät; NAS-Zugriffe des Servers (Reiter Dateien, Image prüfen) bleiben unbegrenzt. Anzeige: „begrenzt: 300 Mbit/s“ klein in der LAN-Kurve (plus Tooltip), Zeile „Bandbreite begrenzt auf …“ zu Beginn jedes Auftrags-Logs; ändert sich die Grenze, rechnet die Restzeit ab da neu. Gespeichert in `config.json` (`bandwidth`, mit Grenzen beim Laden), im Export enthalten.

## Typischer Ablauf

1. **Gerät erfassen:** Gerät mit dem Agent-Stick starten; es erscheint unter „Neu / nicht einsortiert“. Umbenennen (Name = späterer Computername) und in einen Ordner ziehen.
2. **Zustand sichern:** *Disk-Image erstellen …*.
3. **Master-Image bereitstellen:** vorbereitetes Windows sichern und im Reiter *Images* mit ★ markieren ([Master-Image](#master-image-sysprep)).
4. **Automatisierung einrichten:** Gerätefenster → Reiter *Automatisierung* (Master-Image, Zieldisk, Backup ja/nein, Abschluss), Schalter einschalten. Achtung: Ist das Gerät verbunden, beginnt der Countdown sofort (30 s).
5. **Neu aufsetzen:** Gerät mit Agent-Stick oder Netzwerkstart starten; Stick nie abziehen, solange der Agent läuft (er läuft vom Stick) – erst wenn das Gerät aus ist bzw. beim Neustart der Bildschirm dunkel wird.
6. **Inventar festhalten:** *Menü → Inventar exportieren (CSV/PDF) …*.

## Umzug auf einen neuen Rechner

**Menü → Einstellungen exportieren …** speichert alles in eine Datei (`okula-recovery-<Rechner>-<Datum>.okula.zip`, nur für den Benutzer lesbar):
- `config.json`: NAS-Verbindung und Einstellungen
- `geraete/…`: Geräteverzeichnis mit Ordnern, Verlauf, Notizen und Windows-Schlüsseln
- `agent.key`: Schlüssel der Agent- und Restore-Sticks (empfohlen – sonst alle Sticks neu erstellen)

Nicht enthalten: Images, Backups und ISOs (bleiben auf dem NAS) sowie das **NAS-Passwort** und die **Garantie-Schlüssel** (Dell/HP) – sie liegen nur für root lesbar in `/etc/okula-recovery/nas.cred` bzw. `warranty.cred`. Das NAS-Passwort nach dem Import einmal im NAS-Fenster eingeben, die Garantie-Schlüssel unter Menü → Einstellungen. Die Datei enthält Schlüssel: wie ein Passwort aufbewahren.

Der Export enthält auch die Vorlagen der Automatisierung und die Einstellung „höchstens gleichzeitig“.

**Menü → Einstellungen importieren …** auf dem neuen Rechner (nach `sudo ./install.sh`): zeigt den Inhalt, Teile einzeln wählbar. Vorher sichert das Tool alles, was überschrieben werden könnte, nach `~/.config/okula-recovery/import-sicherung/<Datum>/`. Geräte werden zusammengeführt (gleiche ID: das zuletzt gesehene gewinnt, Ordner aus dem Export; gleiche Hardware mit anderer ID wird zu einem Eintrag vereint). Danach startet das Tool neu. Während Aufträge laufen, ist der Import gesperrt. Manipulierte Dateien (Pfade ausserhalb, falsche IDs, neuere Formatversion) werden abgewiesen.

**Nur NAS:** Im NAS-Fenster gibt es **Exportieren …** (JSON ohne Passwort) und **Importieren …** (liest auch den Gesamt-Export). Der Import füllt das Formular; danach Passwort eingeben und „Einhängen“.

## Agent-USB-Stick

Menü → **Agent-USB-Stick erstellen …**:

**Boot-Menü-Taste je Hersteller** (Tabelle auch im Stick-Dialog und in der Hilfe; Quellen in `okula_recovery/bootkeys.py`):

| Hersteller | Boot-Menü | BIOS | Hinweis |
|---|---|---|---|
| HP | F9 (oder Esc → F9) | F10 | teils mit Fn |
| Dell | F12 | F2 | |
| Lenovo ThinkPad/ThinkCentre | F12 (oder Enter → F12) | F1 | |
| Lenovo IdeaPad/Yoga/Legion | F12 bzw. Fn+F12 | F2 | sonst Novo-Knopf |
| Asus Notebook / Desktop | Esc / F8 | F2 / Entf | |
| Acer | F12 | F2 | F12-Menü erst im BIOS einschalten |
| MSI | F11 | Entf | |
| Gigabyte | F12 | Entf | |
| Fujitsu | F12 | F2 | |
| Medion | F10 (teils F8/F11) | F2 | |
| Toshiba/Dynabook | F12 | F2 | |
| Microsoft Surface | Lautstärke leiser + Ein | Lautstärke lauter + Ein | |
| Apple Mac (Intel) | Option/Alt halten | – | T2: Start von externen Medien erlauben |

Bei erfassten Geräten zeigt das Gerätefenster (Übersicht → **Starttasten**) die passende Taste aus den Inventardaten (DMI-Hersteller und -Modell).


1. Stick einstecken und auswählen. Angeboten werden nur USB- und Wechseldatenträger, nie die Systemdisk.
2. Debian-Live-ISO wählen oder **Herunterladen** klicken. Das Tool lädt das aktuelle `debian-live-…-amd64-standard.iso` von cdimage.debian.org und prüft es gegen `SHA512SUMS`. Die Datei liegt danach unter `~/.cache/okula-recovery/iso`. Ein anderer Mirror lässt sich über die Umgebungsvariable `OKULA_DEBIAN_LIVE_URL` setzen.
3. **Stick vorbereiten**. Der Stick wird gelöscht und so aufgebaut:
   - MBR mit einer FAT32-Partition (Label `OKULAAGENT`), darauf der Inhalt des Live-ISO
   - eigene `grub.cfg`; gebootet wird per UEFI über den GRUB des ISO und per BIOS über `grub-install`
   - Agent als zusätzliches Image `/live/okula-agent.squashfs`. live-boot legt es über das Live-System, so sind Agent, systemd-Dienst und Banner beim Booten direkt aktiv. Auf der Zielmaschine wird nichts installiert, alles läuft im RAM.
   - Tastatur `ch`, Locale `de_CH.UTF-8`, Zeitzone `Europe/Zurich`
4. **Prüfung am Schluss** (Ä-038, `stick.check_written` → `stick.verify_stick`): Nach `sync` und dem Aushängen hängt
   der Helfer die FAT-Partition (beim Restore-Stick auch die Datenpartition) erneut schreibgeschützt ein, damit vom
   Stick gelesen wird und nicht aus dem Zwischenspeicher. Geprüft wird: `live/okula-agent.squashfs` vorhanden,
   > 0 Byte, beginnt mit dem Squashfs-Kopf `hsqs`; `live/filesystem.squashfs` so gross wie im ISO; Kernel und initrd
   vorhanden; beim Restore-Stick das Image (`image/` auf der Datenpartition) vorhanden und > 0 Byte. Schlägt etwas
   fehl, endet der Helfer mit `ERROR Prüfung am Schluss fehlgeschlagen: …` statt `DONE`. Verschwindet das Gerät
   während des Baus oder kommt ein E/A-Fehler (EIO/ENODEV/ENXIO bzw. „Input/output error“ in der Ausgabe eines
   Befehls), lautet die Meldung „Stick wurde während des Schreibens abgezogen – Stick neu erstellen.“
   (`stick.explain_unplugged`). Anlass: B-010 (Stick nach 24 s abgezogen, Agent-Teil 0 Byte).
5. **Meldung am Ende** (`stick_dialog.show_stick_result`): Fenster „Agent-Stick fertig“ bzw. „Restore-Stick fertig“
   („Der Stick kann jetzt abgezogen werden.“, Knopf „OK“) oder rot „Stick nicht fertig“ mit dem Grund und
   „Stick nicht verwenden – neu erstellen.“ (Knopf „Schliessen“, `uikit.confirm_error(…, red=True)`). Während des
   Baus steht unter dem Balken „Stick erst abziehen, wenn „Stick fertig“ erscheint.“ Der Boot-Stick aus ISO zeigt
   am Ende dasselbe Fenster („Boot-Stick fertig“), ohne die Datei-Prüfung.

![Boot-Menü des Agent-Sticks](grub-menu.png)

**Ablauf an der Zielmaschine:** vom Stick booten (Boot-Menü-Taste siehe Tabelle oben). Der Agent sendet alle 3 s ein Beacon auf **UDP 47811**, und zwar per Broadcast und zusätzlich direkt an die Server-IP aus dem Dialog. Das Tool antwortet, die Konsole zeigt „Verbunden“, und das Gerät erscheint links mit grüner LED (neu: unter „Neu / nicht einsortiert“, siehe [Geräte](#geräte)).

- **Unbekannte IP:** Die IP muss niemand kennen. Die Zielmaschine bekommt im Live-System per DHCP eine neue IP, die alte Netzwerkeinstellung des installierten Systems spielt keine Rolle. Gibt es kein DHCP, setzt der Agent nach etwa 25 s eine feste Link-Local-Adresse `169.254.x.y` (aus der MAC) und meldet sich per Broadcast an `255.255.255.255`. Das Tool antwortet dann ebenfalls per Broadcast.
- **Firewall auf dem Server:** UDP 47811 eingehend freigeben (siehe [Firewall](#firewall)).
- **Secure Boot:** Der Stick nutzt die signierte Boot-Kette des Debian-ISO.
- **Hinweis:** Die Beacons sind nicht authentifiziert. Die spätere Steuerverbindung zum Agent bekommt eine Authentifizierung.

## Netzwerkstart (PXE) – Agent ohne Stick

Registrierte Geräte können den Agent **übers Netzwerk** starten (am Gerät Boot-Menü → Netzwerk/PXE, Taste siehe [Agent-USB-Stick](#agent-usb-stick)), statt vom Agent-Stick. **Nur** Geräte, die schon einmal mit dem Agent-Stick liefen **und** einzeln freigeschaltet sind, bekommen eine Antwort; alle anderen Rechner im Netz bleiben unberührt.

**Einrichten (Tools → Netzwerkstart (PXE) …):**
1. Server-IP wählen (Netz der Geräte) und das Debian-Live-ISO (wie beim Agent-Stick, ggf. **Herunterladen**).
2. **Vorbereiten:** legt Live-System, Agent-Teil (mit Schlüssel, partclone usw.) und die signierten Bootlader bereit (`/var/lib/okula-recovery/pxe`). Nach einem Tool-Update oder neuer Server-IP erneut vorbereiten.
3. Geräte freischalten: Haken in der Liste oder im Gerätefenster (Reiter *Netzwerk*, Zeile *Netzwerkstart*: Schalter Ein/Aus, daneben das Zahnrad zu den PXE-Einstellungen). Der Schalter ist ausgegraut, solange der Netzwerkstart nicht eingerichtet und eingeschaltet ist oder keine Kabel-Netzwerkkarte bekannt ist. Neu erfasste Geräte sind nie freigeschaltet.
4. **Einschalten.** Der Dienst läuft danach auch nach einem Neustart des Servers, bis er ausgeschaltet wird.

**Wie es abgesichert ist:**
- Das Tool vergibt **keine IP-Adressen** und macht kein DNS: `dnsmasq` läuft nur als *Proxy-DHCP* (`dhcp-range=…,proxy`, `port=0`). Der normale DHCP-Server bleibt zuständig.
- Proxy-DHCP und TFTP antworten nur MAC-Adressen in der Freigabeliste (`dhcp-hostsfile` mit Merkmal `okula`, `dhcp-ignore=tag:!okula`); es werden nur kabelgebundene Netzwerkkarten freigeschaltet. Fremde Rechner, die per Netzwerk starten, bekommen keine Antwort (getestet in QEMU).
- Den Agent-Teil (enthält den Agent-Schlüssel) liefert ein eigener HTTP-Dienst (Port 47813) nur aus, wenn die MAC der anfragenden IP (ARP-Tabelle) freigeschaltet ist; er kennt nur zwei feste Dateien. Der Schlüssel liegt nur für root lesbar auf dem Server.
- Bootlader: `shim`, `grub` (signiert – **Secure Boot** darf an bleiben) und `pxelinux` (BIOS) kommen aus den Paketquellen des Servers. Das Tool lädt sie nur herunter und packt sie aus, ohne sie zu installieren – der Bootlader des Servers bleibt unberührt.

**Technik:** UEFI: shim → grub → Kernel/initrd per TFTP; BIOS: pxelinux. Das initrd ist das des Live-ISO plus ein kleines Skript, das live-boot anweist, neben `filesystem.squashfs` auch den Agent-Teil per HTTP zu laden – danach läuft alles wie mit dem Stick. Dienste: `okula-pxe.service` (dnsmasq), `okula-pxe-http.service`; gesteuert über den bestehenden Root-Helfer (`okula-make-stick pxe …`).

**Firewall auf dem Server:** eingehend UDP 67, 69 und 4011 (Proxy-DHCP, TFTP) sowie TCP 47813 (HTTP) freigeben (siehe [Firewall](#firewall)).

**Voraussetzungen am Gerät:** Netzwerkkabel (kein WLAN), Netzwerkstart im BIOS aktiv. Liegen Router/VLANs zwischen Gerät und Server, braucht es eine DHCP-Weiterleitung (IP-Helper) zum Server. Die Geräte brauchen genug RAM für das Live-System (wie beim Stick, ca. 2 GB).

### Fernsteuerung: Wake-on-LAN und „Netzwerkstart zuerst“

Im Gerätefenster, Reiter **Netzwerk** (dort auch Netzwerkstart-Schalter und Netzwerkkarten):

- **Einschalten (Wake-on-LAN):** sendet ein Magic Packet an die Kabel-Netzwerkkarten (Broadcast in die Netze des Servers und an 255.255.255.255, UDP 9 und 7). Am Gerät muss Wake-on-LAN im BIOS/UEFI aktiv sein; das Gerät muss im selben Netz sein (Router leiten Broadcasts nicht weiter).
- **Netzwerkstart zuerst:** Während das Gerät mit dem Agent verbunden ist, setzt der Agent den Netzwerkstart (PXE IPv4) an die erste Stelle der UEFI-Startreihenfolge (`efibootmgr`); die bisherige Reihenfolge merkt sich das Tool zum Zurückstellen. Danach fragt das Gerät bei jedem Start zuerst das Tool:
  - ohne Auftrag (**Startart lokal**): grub bzw. pxelinux starten sofort von der Festplatte weiter (UEFI: zurück an die Firmware → nächster Starteintrag, z. B. Windows),
  - mit **„Beim nächsten Start den Agent laden“** (**einmal Agent**): der Agent startet; sobald er seinen Agent-Teil geladen hat, steht das Gerät wieder auf „lokal“.
  - **Einschalten und Agent starten** = Agent vormerken + Wake-on-LAN – das Gerät meldet sich danach im Tool, ohne dass jemand hingeht.
- Nur UEFI (BIOS-Geräte: Reihenfolge im BIOS-Setup). Windows-Updates können die Reihenfolge zurücksetzen – das Tool prüft sie bei jeder Verbindung (Knopf **Prüfen**) und meldet, wenn das Netzwerk nicht mehr vorne steht. Ist der Server aus, wartet das Gerät kurz aufs Netzwerk und startet dann normal.
- Die Startart pro Gerät setzt der Netzwerkstart-Dienst über je eine kleine Datei pro MAC (grub: `source /okula/mode/<MAC>`, pxelinux: `pxelinux.cfg/01-<MAC>`); getestet in QEMU mit UEFI/Secure Boot und BIOS.

> Für „Netzwerkstart zuerst“ braucht der Agent die neue Funktion: **Agent-Stick neu erstellen** und unter Tools → Netzwerkstart **neu vorbereiten**.

**Neustart in Windows / Neustart in den Agent (Ä-045):** zwei Knöpfe statt „Neu starten“ (Geräteliste, Gerätefenster,
Rechtsklick; nach *Windows anpassen* / *Software installieren* die Frage „Jetzt in Windows neu starten?“). Regeln und
Texte: `neustart.py`; Ablauf: `ui.reboot_to` → `_reboot_go`.
- **VM:** `virsh.set_boot_runtime` je Knopf (Windows: Disk zuerst, „einmal Agent“ abbestellt; Agent: Netzwerk zuerst,
  Netzwerkstart erlaubt, „einmal Agent“ angefordert), dann Neustart über den Agent bzw. ACPI. Was vorher vorgemerkt war,
  zählt nicht mehr.
- **Echtes Gerät (Agent verbunden):** Agent-Befehl `bootnext` (`wininstall.set_boot_next`, `efibootmgr --bootnext`):
  Windows = Eintrag „Windows Boot Manager“ bzw. Pfad `\EFI\Microsoft\Boot\bootmgfw.efi` (bcdboot legt ihn in NVRAM an,
  Microsoft Learn „BCDBoot Command-Line Options“); Agent = `BootCurrent` (Stick oder Netzwerk), sonst der Netzwerk-
  Eintrag. BootNext gilt laut UEFI-Spezifikation (3.1.2) einmal und vor BootOrder; BootOrder bleibt unverändert.
  Mit Netzwerkstart setzt bzw. löscht das Tool zusätzlich „einmal Agent“, sodass grub/pxelinux zum Ziel passt.
- **Nicht steuerbar** (BIOS-Modus, alter Agent ohne `bootnext`, kein passender Eintrag): Rückfrage „Startziel nicht
  festgelegt“ mit Hinweis – Windows: „Stick abziehen, sobald der Bildschirm dunkel wird“ (bzw. Netzwerkstart „lokal“);
  Agent: Stick stecken lassen, sonst im Startmenü der Firmware wählen. Grenzen: Firmware, die BootNext übergeht, oder
  ein USB-Eintrag, den die Firmware nur vorübergehend anlegt (dann Netzwerk-Eintrag bzw. Hinweis).

**Netzwerkstart-Protokoll (Ä-034):** Gerätefenster → Netzwerk zeigt, was die Dienste je Gerät gesehen haben (letzte 6 Stunden, alle 5 s neu, solange der Reiter offen ist): Anfrage mit Firmware-Art (BIOS/UEFI aus `PXEClient:Arch`), Antwort bzw. „nicht freigeschaltet“ (`proxy-ignored`), TFTP-Dateien (shim, grub, grub.cfg, Startart, Kernel, initrd bzw. pxelinux), HTTP (Live-System, Agent-Teil) und Fehler. Das Journal liest der Root-Helfer (`okula-make-stick pxe log`, gleiche sudo-Regel), übersetzt wird in `pxelog.py`. TFTP kennt nur IPs – die MAC kommt aus Dateinamen mit MAC (`okula/mode/<mac>`, `pxelinux.cfg/01-<mac>`), der Anfrage auf Port 4011, der HTTP-Meldung (mit MAC) oder der ARP-Tabelle. Geprüft mit echten Abläufen im Labor (dnsmasq 2.91, OVMF + shim/grub, SeaBIOS/iPXE + pxelinux); die Aufzeichnungen liegen in `tests/data/pxelog/`.

**BIOS-Modus (Legacy, B-003):** keine EFI-Variablen – „Netzwerkstart zuerst“ stellt man im BIOS-Setup von Hand ein (Netzwerk/PXE an erste Stelle); der Schalter vermerkt es nur (`devices.bios_mode`: Inventar `platform.uefi`, sonst letzte Prüfung). „Agent beim nächsten Start“ und „Einschalten und Agent starten“ laufen danach über die PXE-Antwort des Tools wie bei UEFI. Netzwerkkarten: nur Kabel mit fester MAC zählen für PXE/WoL (`devices.nic_kind`, `real_mac`); WLAN, Mobilfunk (`ww…`) und zufällige MACs nicht; früher gesehene Karten nur mit fester MAC.

## Virtuelle Maschinen – Grundlage

Konzept, Entscheide und Profile: [VM.md](VM.md) (I-001). Auftrag 1 legt das Fundament; die Oberfläche steht unter [Virtuelle Maschinen im Tool](#virtuelle-maschinen-im-tool-i-001-auftrag-2).

**Pakete** (`install.sh`): `qemu-system-x86 qemu-utils libvirt-daemon-system libvirt-clients ovmf swtpm swtpm-tools virt-viewer`.
Der angemeldete Benutzer kommt in die Gruppe `libvirt` (wirksam nach Ab- und Anmelden) und steuert die VMs ohne sudo
über `virsh -c qemu:///system`. Die VMs laufen im libvirt-Dienst weiter, auch wenn das Tool geschlossen ist.

**Speicherpool** `okula` (Typ dir, `/var/lib/libvirt/images/okula`, Autostart): eine qcow2-Datei je VM
(`<Name>.qcow2`), wächst mit dem belegten Platz. Das libvirt-Standardnetz `default` (NAT, `virbr0`) wird
ausgeschaltet – es würde sonst als eigenes Netz in der Netzwerk-Erkennung auftauchen.

**Netzwerkbrücke `br0`** (`/usr/local/sbin/okula-bridge setup | status | remove`, `okula_recovery/bridge.py`, nur root,
aus `install.sh`): nur mit NetworkManager (sonst Hinweis, nichts geändert). Die Kabel-Schnittstelle der Standardroute
(nie WLAN, z. B. `eno2`) wird Port der Bridge-Verbindung `okula-br0` (ifname `br0`, STP aus, forward-delay 0). `br0`
erhält **dieselbe MAC** wie die Schnittstelle (der DHCP-Server vergibt dieselbe IP) und die IPv4/IPv6-Einstellungen der
bisherigen Verbindung; diese bleibt bestehen, startet aber nicht mehr automatisch. **Rückfall:** Hat `br0` nach 45 s keine
IPv4-Adresse, wird die alte Verbindung wieder aktiviert, die neuen gelöscht und deutlich gemeldet; die Installation
läuft weiter. Idempotent (läuft `br0` schon, passiert nichts). `remove` stellt den alten Zustand her (Angaben in
`/etc/okula-recovery/bridge.json`).

**Netzwerkstart mit `br0`:** Die Server-IP hängt danach an `br0`. `okula-pxe.service` führt vor jedem Start
`python3 -m okula_recovery.pxe refresh` aus und schreibt die dnsmasq-Konfiguration neu, wenn die Schnittstelle nicht mehr
stimmt (`interface=eno2` → `interface=br0`); `install.sh` startet den Dienst neu, wenn er eingeschaltet ist. Beacons
(UDP 47811, an alle Schnittstellen gebunden) und Ping-Scan (über die IP-Adressen) sind nicht an einen
Schnittstellennamen gebunden.

**Modul `okula_recovery/vm.py`** (ohne GTK):
- `VmProfile` mit Firmware (`uefi-sb` | `uefi` | `bios`), TPM, Chipsatz (`q35` | `i440fx`), Disk (`nvme` | `sata`,
  Grösse in GB = 10⁹ Byte, Modellname, Seriennummer, Drehzahl), Netzwerkkarte (`e1000e` | `rtl8139`, MAC), CPU (Kerne,
  Threads, Name), RAM und SMBIOS Typ 0/1/2/3. `PROFILES`: VM-Win11, VM-Legacy, VM-Klein (Tabelle in [VM.md](VM.md)).
- `domain_xml(profile)`: libvirt-XML. UEFI über die Firmware-Auswahl von libvirt (`<os firmware='efi'>`, Merkmale
  `secure-boot`/`enrolled-keys`, bei Secure Boot SMM an), BIOS = SeaBIOS; TPM 2.0 `tpm-crb` mit swtpm; Netzwerk
  `bridge br0`; Start Disk → Netzwerk; Grafik SPICE (nur 127.0.0.1, für virt-viewer) mit Standard-VGA; USB-Tablet;
  kein Memory-Balloon – **kein virtio-Gerät** (einzige Ausnahme auf Wunsch: Gastagent in Test-VMs, I-041,
  [unten](#test-vms-mit-gastagent-i-041)). SMBIOS per `<sysinfo type='smbios'>` + `<smbios mode='sysinfo'/>`, die
  UUID der VM = SMBIOS-UUID. Das Profil steht als JSON in den Metadaten der VM (`profile_from_xml`).
- **NVMe:** libvirt 11.3 (Debian 13) kennt den Disk-Bus `nvme` erst ab 11.5. Die Disk wird darum als SATA-Disk
  definiert (libvirt verwaltet Datei, Rechte, AppArmor) und per `<qemu:override>` zum QEMU-Gerät `nvme` umgebaut
  (auf `pcie.0`, Steckplatz `0x1b`). QEMU 10.0 hat bei NVMe **keinen Modellnamen** – Windows zeigt „QEMU NVMe Ctrl“.
- **Modellname** der SATA-Disk über `<product>` (libvirt ≥ 11.1), Drehzahl über `rotation_rate` (1 = SSD).
  **CPU-Name** (falls gesetzt) per `-global host-x86_64-cpu.model-id` in `<qemu:commandline>`; sonst der Name der
  Server-CPU. **Gehäusetyp** (SMBIOS Typ 3) lässt sich weder in libvirt noch in QEMU setzen – steht nur im Profil.
  libvirt markiert VMs mit `qemu:override`/`qemu:commandline` als „tainted“ (nur ein Hinweis im Log).
- MAC: `52:54:00:xx:xx:xx`, zufällig, eindeutig gegenüber allen VMs (auch fremden). Seriennummer `VM-…`, UUID zufällig.
- `Virsh`: `create` (Volume per `vol-create-as` qcow2, `define`), `list` (nur VMs des Tools), `state`, `states`
  (alle VMs mit einem `virsh list --all`), `start(name, mode)` mit `normal` (Disk → Netzwerk) | `agent` (einmal
  Netzwerk zuerst) | `iso` (ISO als CD, einmal zuerst) – dafür wird die Startreihenfolge nur für diesen Start
  definiert und gleich wieder zurückgesetzt; ein Neustart in der laufenden VM behält sie, bis `set_boot_runtime` sie
  umstellt –, `shutdown`/`reboot` (ACPI), `poweroff`, `delete` (mit Disk, NVRAM, TPM-Zustand), `set_profile` (nur
  ausgeschaltet; Disk nur vergrössern; UUID und MAC bleiben). Fehler als `VmError` mit deutschem Text.

## Virtuelle Maschinen im Tool (I-001 Auftrag 2)

**Geräteliste:** fester Ordner **„Virtuelle Maschinen“** (`devices.VM_FOLDER`), sichtbar sobald es eine VM gibt oder
libvirt installiert ist. Keine Unterordner, nicht umbenennbar/löschbar/verschiebbar, VMs nicht herausziehbar, echte
Geräte nicht hinein (`DeviceStore` lehnt ab, die Oberfläche zeigt die Meldung). Zeile einer VM: LED wie bei Geräten,
Status statt „nicht verbunden“ der Zustand der VM (`aus`, `läuft`, `läuft – Agent verbunden`), alle 5 s über einen
`virsh list --all` im Hintergrund (`MainWindow.vm_poll`).

**Geräteeintrag** (`DeviceStore.register_vm`, beim Erstellen): Name = VM-Name, `vm = {"name", "profile"}`,
Identität `uuid:<SMBIOS-UUID>` und dieselbe UUID als Agent-ID – der Agent meldet beim ersten Start genau diese
Board-UUID, `match()` findet den Eintrag schon über den Beacon, es entsteht kein zweites Gerät. **Vor-Inventar**
(`vm.pre_inventory`, Feld `provisional`): dmi (Okula, Profilname, Seriennummer, UUID, Gehäuse), cpu, memory, Disk
(Name `sda`/`nvme0n1`, Grösse, Anschluss, Modell, Seriennummer), eine **Kabel**-Karte mit der VM-MAC und platform
(uefi/secure_boot/tpm); der erste Agent-Bericht ersetzt es. Die Kabel-Karte ist nötig: `52:54:00:…` ist lokal
vergeben (`real_mac` = falsch), `netboot_macs` nimmt solche MACs nur aus dem Inventar. Netzwerkstart ist sofort
frei (`netboot = True`, Freigabeliste wird gleich geschrieben), `netfirst = True` (Startart `local`/`once`).

**Startreihenfolge:** Gespeichert ist **Disk → Netzwerk**. „Einschalten und Agent starten“ merkt den Agent vor
(`boot_request`, Startart `once`), schreibt die Freigabeliste und startet erst danach mit `mode="agent"` (einmal
Netzwerk zuerst). Sobald der Agent verbunden ist, stellt das Tool die **laufende** VM auf Disk zuerst um
(`Virsh.set_boot_runtime`: QMP `qom-set` auf `bootindex` von `ua-disk0`/`ua-net0`, QEMU liest die Reihenfolge bei
jedem Neustart neu) – ein Neustart danach (Automatisierung nach dem Zurückspielen) startet das System auf der Disk.
Umgekehrt stellt das Häkchen „Beim nächsten Start den Agent laden“ eine laufende VM auf Netzwerk zuerst.
*Warum nicht fest Netzwerk → Disk wie „Netzwerkstart zuerst“:* Am Server geprüft (06.11.2026) – nach der Startart
„lokal“ beendet sich grub mit `exit` (Erfolg); OVMF startet dann laut UEFI-Regel nicht den nächsten Eintrag, sondern
zeigt das Setup-Menü (auch mit `exit 1`). Ohne Antwort des Netzwerkstarts braucht OVMF über eine Minute (IPv4, danach
IPv6). SeaBIOS startet nach „lokal“ korrekt von der Disk.

**Aktionen** (Rechtsklick auf die VM, Knöpfe im Gerätefenster, gemeinsam aus `MainWindow.vm_actions`; ausgegraut mit
Grund im Tooltip): Einschalten, Einschalten und Agent starten, Von ISO starten … (ISO aus der ISO-Bibliothek; CD mit
`<seclabel model='dac' relabel='no'/>`, damit libvirt die Datei auf dem CIFS-NAS nicht umbesitzt – am Server mit
Debian-Netinst in VM-Win11 und VM-Legacy geprüft), Bildschirm (`virt-viewer -c qemu:///system --wait --reconnect
<Name>`; unter Wayland lässt sich ein fremdes Fenster nicht nach vorne holen, ein offenes Fenster derselben VM wird
darum geschlossen und neu geöffnet), Herunterfahren/Neu starten (mit Agent über den Agent, sonst ACPI), Ausschalten
(hart, Rückfrage), Hardware ändern … (`set_profile`, nur aus; Firmware und Disk-Anschluss mit Warnung; Geräteeintrag
bleibt, Änderung im Verlauf), VM löschen … (rote Rückfrage, nur aus; VM, Disk und Geräteeintrag; Images/Backups auf
dem NAS bleiben). Wake-on-LAN (`wake_device`, Reiter Netzwerk, Rechtsklick) schaltet VMs über libvirt ein; im Reiter
Netzwerk sind Wake-on-LAN und „Netzwerkstart zuerst“ bei VMs ausgeblendet. Alle virsh-Aufrufe laufen im Hintergrund,
`VmError` erscheint als Meldung. Dialoge: `okula_recovery/vm_dialogs.py` (Neue VM mit Prüfung von freiem Platz und
RAM, Hardware ändern, ISO wählen). Das Demo-Gerät bleibt unberührt.

**Leere Disk (Ä-036):** „Einschalten“ einer VM, deren Disk noch nie ein System hatte, fragt zuerst nach
(`vm.blank_disk`: keine Disk im Inventar mit Partitionen oder Partitionstabelle **und** im Verlauf kein erfolgreiches
`install`/`linux`/`restore`/`auto` und kein „VM von ISO gestartet“ – von ISO lässt sich in der VM von Hand
installieren). Knöpfe *Einschalten und Agent starten*, *Von ISO starten …*, *Trotzdem einschalten*
(`vm_dialogs.ask_blank_disk`); gilt für alle VMs.

### Test-VMs mit Gastagent (I-041)

Zweck: Die Projektleitung (am Server, mit sudo) führt in einer Test-VM unter Windows Befehle aus und liest die Ausgabe
– ohne Netzwerk, Passwort oder Bildschirm: `virsh qemu-agent-command <VM> '{"execute":"guest-exec","arguments":
{"path":"powershell.exe","arg":[…],"capture-output":true}}'`, danach `guest-exec-status` mit der `pid`. Befehle aus
dem Tool heraus gibt es bewusst nicht.

- **Profil:** `VmProfile.guest_agent` (Standard `False`; ältere Profile ohne das Feld = aus). Oberfläche: Häkchen
  *Gastagent (nur Test-VMs)* in *Neue virtuelle Maschine* und *Hardware ändern …* (`vm_dialogs.guest_agent_check`,
  Tooltip `vm.GUEST_AGENT_TIP` mit dem Grund). Ändern wie jede Hardware nur bei ausgeschalteter VM (`set_profile`),
  Verlauf „Hardware geändert: Gastagent aus → an“ (`vm.profile_changes`). Zwillinge (`profile_from_inventory`) und
  die drei Vorlagen immer ohne.
- **XML** (`domain_xml`): eingeschaltet zusätzlich `<controller type='virtio-serial' index='0'/>` und
  `<channel type='unix'><target type='virtio' name='org.qemu.guest_agent.0'/></channel>` – ohne `<source path>`, den
  Socket legt libvirt selbst an (unter `/var/lib/libvirt/qemu/channel/target/…`, AppArmor-Freigabe über
  virt-aa-helper). Ausgeschaltet fehlen beide; sonst ist das XML gleich (Test `test_vm_guest_agent`). Disk-Datei,
  Snapshot-Liste, Startreihenfolge (`start` definiert zweimal neu), Snapshot einer laufenden VM
  (`snapshot-create-as --disk-only` ohne `--quiesce`) und die Hilfs-VM zum Zusammenführen (nie ein Kanal) bleiben
  unverändert. Herunterfahren/Neu starten bleiben ausdrücklich ACPI (`--mode acpi`) – libvirt nähme sonst den
  Gastagent, sobald er antwortet.
- **Kennzeichen:** Der Geräteeintrag merkt sich `vm.guest_agent = true` (`MainWindow._vm_guest_flag` nach Erstellen
  bzw. *Hardware ändern …*), damit die Liste ohne virsh-Aufruf zeichnen kann: Zustand „aus · Gastagent“ bzw. „läuft –
  Agent verbunden · Gastagent“, im Gerätefenster in der Zeile *Virtuelle Maschine* „Gastagent: antwortet / keine
  Antwort / VM nicht eingeschaltet“ und in der Übersicht. Die Antwort holt `Virsh.guest_ping`
  (`virsh qemu-agent-command <VM> --timeout 3 '{"execute":"guest-ping"}'`) im Hintergrund – beim Öffnen, bei
  Änderungen höchstens alle 10 s und sonst alle 30 s, nur solange das Fenster offen ist und die VM läuft.
- **Warnung beim Master** (`MainWindow.warn_guest_agent_master`, Rückfrage mit *Trotzdem fortfahren*, sperrt nicht):
  *Disk-Image erstellen …* einer VM mit Gastagent, *Als Master-Image markieren* eines Images, dessen Quelle laut
  Metadaten (`source.device_id` bzw. `agent_id`) eine solche VM ist, und *OS installieren …* mit *Für Master-Image
  (Audit-Modus)* (bei *Abbrechen* bleibt der Dialog offen, „Nicht gestartet: abgebrochen (VM mit Gastagent)“). Text:
  „VM mit Gastagent – virtio-Treiber und qemu-ga sind im Image. Für Master-Images ohne Gastagent arbeiten.“ Sysprep
  selbst läuft in der VM von Hand – das Tool sieht ihn nicht.
- **Gasttools in Windows** über die Software-Bibliothek, kein eigener Download-Code: Quelle Fedora virtio-win, stabile
  Version (`virtio-win.iso` bzw. die Direkt-Downloads unter `fedorapeople.org/groups/virt/virtio-win/` ¹). Im
  Hauptordner der ISO `virtio-win-guest-tools.exe` (WiX-Burn-Paket von Red Hat: Treiber-Paket
  `virtio-win-gt-x64.msi` und qemu-ga, je nach Version weitere Werkzeuge ¹) bzw. die Einzelpakete
  `virtio-win-gt-x64.msi` und `guest-agent/qemu-ga-x86_64.msi`. Erkennung: Burn mit CompanyName „Red Hat“ bzw.
  „virtio-win“ im Programm- oder Dateinamen → Typ `virtio` „virtio-win-Gasttools (Burn)“, `/install /quiet /norestart`
  (0, 1638, 1641, 3010); die MSI wie jedes MSI `/qn /norestart` (0, 1641, 3010). qemu-ga läuft danach als Dienst
  „QEMU Guest Agent“ (`QEMU-GA` ¹) und braucht den VirtIO-Serial-Treiber aus dem Treiber-Paket. **Entfernen:** in
  Windows unter *Einstellungen → Apps* deinstallieren (bzw. zurück zu einem Snapshot) und die Option ausschalten.
- **Agent:** unverändert – kein neuer Agent-Stick.

¹ Aus dem Gedächtnis des Umsetzungs-Agenten (I-041, 19.11.2026), nicht nachgelesen (kein Internetzugriff im
Auftrag): Ablage der Downloads, Inhalt des Burn-Pakets und Dienstname am Server prüfen ([TESTS.md](TESTS.md)
Abschnitt 27).

## Digitaler Zwilling (I-001 Auftrag 3)

**„VM mit dieser Hardware erstellen …“** – Knopf oben rechts im Gerätefenster und Rechtsklick auf ein Gerät; nicht für
VMs und den DEMO-PC, ohne Inventar (dmi + Disks) ausgegraut mit Grund (`MainWindow.twin_why`).

**Profil** (`vm.profile_from_inventory(inv, ServerInfo, Gerätename) -> (VmProfile, Hinweise)`, rein, Tests in
`tests/test_vm_twin.py`): Systemdisk = Disk aus `systems[].disk`, sonst die erste. Firmware aus deren `pttype`
(`gpt` → UEFI/Q35, `dos` → BIOS/i440FX, leer → `platform.uefi`), Secure Boot aus `platform.secure_boot`, TPM 2.0 wenn
`platform.tpm` gesetzt (1.2 → 2.0 mit Hinweis). Disk: Grösse auf ganze GB aufgerundet, `nvme` → NVMe, sonst SATA,
Modell ≤ 40 Zeichen (bei NVMe bleibt „QEMU NVMe Ctrl“), Drehzahl nur aus `rpm`/`rotation_rate` (das Inventar kennt sie
heute nicht → SSD). CPU-Name per `model-id`, Kerne/Threads wie im Gerät, gesamt höchstens Server-Kerne − 2. RAM: das
Inventar meldet `MemTotal` ohne Firmware-Reservat (4 GB → 3,77 GB) – darum auf ganze GB aufgerundet, höchstens
MemAvailable − 4 GB (auf 512 MB, mindestens 1 GB). Netzwerkkarte immer Intel (`e1000e` bei Q35, `e1000` bei i440FX).
SMBIOS Typ 0/1/2/3 genau aus `dmi`, fehlende Werte leer (keine „Okula“-Vorgaben); Gehäusetyp nur im Profil.
BIOS-Datum nur im Format MM/TT/JJ(JJ) (sonst lehnt libvirt ab). **Identität:** Seriennummern (System, Board, Gehäuse
– neues Feld `Smbios.chassis_serial`) → `VM-` + Original (≤ 64 Zeichen), UUID → erste 8 Stellen `0c1a0000` (beim
zweiten Zwilling `0c1a0001` …), Disk-Seriennummer → `VM` + letzte 18 Zeichen, MAC neu; Platzhalter ab Werk
(`devices.placeholder_*`) → neu wie bei neuen VMs. Name `VM-<Gerätename>` (ASCII, `NAME_RE`, eindeutig).
`vm.twin_rows` liefert die Vorschau *Gerät → VM* mit ✔/~/✖.

**Ablauf** (`MainWindow.vm_twin` → `TwinDialog` → `Virsh.create` → `_twin_created`): Geräteeintrag im Ordner
„Virtuelle Maschinen“ mit `vm.twin_of = <Geräte-ID>`, Verlauf beim Original „Zwilling <VM> erstellt“, bei der VM
„Zwilling von <Gerät> (Image …)“, Netzwerkstart frei. Images des Geräts: `device_window.device_images` (gemeinsam mit
dem Reiter Images, neuestes zuerst), Grösse der Quelldisk aus den Image-Metadaten (grösser als die VM-Disk → Fehler im
Dialog). Mit Häkchen: **ein Auftrag** `restore` auf der VM (`_twin_restore`): Agent vormerken, Freigabeliste schreiben,
`Virsh.start(mode="agent")`, bis 300 s auf den Agent warten (Fortschritt „Agent starten (1/3)“), Zieldisk über
`get_info` (Pfad `/dev/sda` bzw. `/dev/nvme0n1`), `jobs.restore_work` mit Prüfung, ohne Anpassen, danach über
`_after_job` herunterfahren (Agent). Fehler: Meldung und Verlauf, VM bleibt. Übersicht der VM: Zeile „Zwilling von“
(Link öffnet das Gerätefenster des Originals).


## Snapshots der VMs (I-001 Auftrag 4)

Begründung und Prüfung am Server: [VM.md](VM.md), Abschnitt „Snapshots“. Kurz: **externe qcow2-Overlays** im
Pool-Verzeichnis, vom Tool verwaltet; libvirts `snapshot-delete` scheitert an AppArmor (`deny … w` für Backing-Dateien),
darum Löschen per block-stream.

**`vm.py`** (ohne GTK):
- `Snapshot` (id, Titel, Zeit, automatisch, eingefrorene Datei, Eltern-ID, `info`; gelesen: Grösse, aktuell) und
  `SnapState` (laufende Nummer, aktueller Snapshot, Liste) – als JSON im Element `okulasnap:snapshots` der
  VM-Metadaten (Namensraum `https://okula.ch/recovery/vm-snapshots/1`). `domain_xml(p, disk_file=…, snapshots=…)`
  schreibt aktuelle Disk-Datei und Liste mit; `Virsh._rebuild` holt beides beim Neu-Definieren (`start` mit Agent/ISO,
  `set_profile`) aus der gespeicherten VM.
- `Virsh.snapshots(name)` (älteste zuerst, Grösse = `vol-info --bytes` Allocation), `snapshot_changes(name)`
  (Änderungen seit dem aktuellen Snapshot), `snapshot_create(name, title, auto=False, info=None, running_ok=False)`,
  `snapshot_revert(name, id)`, `snapshot_delete(name, id, progress)`. Fehler als `VmError` (deutsch).
- Erstellen ausgeschaltet: `vol-create-as <Name>.snap-<n>.qcow2 <Kapazität der Disk> --backing-vol <bisherige Disk>`,
  dann `define`. Laufend (nur `running_ok`, Agent): `snapshot-create-as --no-metadata --disk-only --atomic --diskspec
  sda,snapshot=external,file=…` + `virsh metadata --live --config`. Vor Pool-Abfragen `pool-refresh` (libvirt legt das
  Overlay der laufenden VM ausserhalb des Pools an).
- Zurück: neues Overlay auf der Datei des Snapshots, `define`, bisheriges Overlay `vol-delete`.
- Löschen: für jede Datei, die auf dem Snapshot aufbaut, Hilfs-VM `okula-merge-<Name>` (`helper_xml`: 64 MiB, i440FX,
  nur Disk `hda`, kein Netzwerk) mit `virsh create --paused`, `blockpull hda [--base <Eltern-Datei>]`, Fortschritt aus
  `blockjob --raw` (`cur=`/`end=`), `destroy`; Ergebnis über `vol-dumpxml` (neue Backing-Datei) geprüft, sonst
  `VmError` und der Snapshot bleibt. Danach Liste anpassen, `define`, Datei löschen.
- `delete`: nach `undefine --remove-all-storage` alle Dateien der Liste, die ursprüngliche Disk und übrige
  `<Name>.snap-*.qcow2` löschen (oberste zuerst). `set_profile`: Disk vergrössern mit Snapshots → `VmError`, ohne
  Snapshots wird die oberste Datei vergrössert.
- Texte: `snapshot_title()` („Snapshot TT.MM. HH:MM“), `auto_title(Aktion)` („vor Zurückspielen TT.MM. HH:MM“),
  `history_text()` („Snapshot ‚…‘ erstellt / zurückgesetzt / gelöscht“), `low_space_text()` (unter `LOW_SPACE_GB` = 50).
- `blank_disk` (Ä-036): Verlaufseintrag mit `snapshot_blank` (Zurücksetzen) beendet die Suche – davor gilt der Stand des
  Snapshots. `DeviceStore.add_history(…, **extra)` speichert solche Zusatzfelder.

**Oberfläche:** Reiter **„Snapshots“** im Gerätefenster einer VM (`snapshot_tab.py`): Liste (Titel, Datum,
Automatisch, Grösse, „◀ aktueller Stand“), Zeile „Aktueller Stand: ‚…‘ plus … Änderungen“, Platzwarnung, Fortschritt
beim Löschen; Knöpfe *Snapshot erstellen …*, *Zurück zu diesem Snapshot …* (auch Doppelklick), *Löschen …* – nur bei
ausgeschalteter VM ohne laufenden Auftrag (`MainWindow.vm_why(dev, "snapshot")`), während des Löschens ist die VM
gesperrt (`vm_snap_busy`). Steuerung in `ui.py` (`vm_snapshot_create/revert/delete`, im Hintergrund über `_vm_task`).
Beim Snapshot speichert das Tool in `info` die Disks und Systeme des Inventars und `blank` (Ä-036); beim Zurücksetzen
kommen sie zurück in den Geräteeintrag.

**„Vorher Snapshot“** (nur VMs, Standard an): in *Image zurückspielen* (`RestoreDialog`), *OS installieren*
(`InstallDialog`) und in der Automatisierung (`automation.Settings.snapshot`, Häkchen im Reiter). `ui.vm_auto_snapshot`
macht den Snapshot direkt vor `jobs.start` (bei laufendem Agent, `running_ok`); ein Fehler bricht ab, bevor ein Auftrag
startet: im Dialog „Nicht gestartet: …“, in der Automatisierung Schritt „Vorher Snapshot“ als Fehler (Verlauf, Meldung
am Gerät). `automation.Engine(…, snapshot=…)` ruft ihn im Thread der Automatisierung auf.

## VM-Disk beim Zurückspielen vergrössern (Ä-037)

Ist die Disk einer VM kleiner als die Quelldisk des Images, bietet *Image zurückspielen …* zwei Wege an:
VM-Disk vergrössern (Standard, Image 1:1) oder Image anpassen (Ä-002). Echte Geräte: unverändert (Häkchen
„Für diese Disk anpassen“).

**Entscheidung (`vm.py`, ohne GTK):** `restore_ways(need, grow_info, adapt)` → `RestoreWays` (`grow_gb`, `grow_why`,
`adapt_why`, `adapt_lines`, `default()`, `allowed(way)`, `pending`). `grow_size_gb(need)` = Quelldisk aufgerundet auf
ganze GB (dezimal wie `DiskSpec.size_gb`). `grow_why(snapshots, pool_free, image_used)`: Snapshots →
`SNAPSHOTS_BLOCK_GROW`; frei < belegte Daten + `grow_reserve` (10 %, mind. `GROW_RESERVE_MIN` = 10 GB) → Meldung mit
Zahlen. Die qcow2-Datei ist dünn – Platz braucht nur, was das Zurückspielen schreibt.

**Belegte Daten** (`shrink.used_bytes(image, source_disk)`): partclone-Kopf (belegte Blöcke), Rohkopie (`dd`) = ganze
Partition laut Metadaten, sonst Grösse der Image-Datei; Swap zählt nicht; Kopfbereich dazu. Liest je Partition nur den
Kopf (wie Ä-002), läuft im Hintergrund des Dialogs.

**Virsh:** `pool_free()` (`pool-info okula --bytes` → Available, sonst `free_disk()`), `snapshot_count(name)`,
`power_down(name, timeout=60)` (ACPI-`shutdown`, alle 2 s `domstate`, nach `SHUTDOWN_TIMEOUT` `destroy`; Rückgabe
off/clean/hard, Abbruch → `VmError`), `grow_disk(name, size_gb)` (Profil mit neuer `disk.size_gb` über `set_profile`,
Modellname, Seriennummer, MAC und UUID bleiben; schon gross genug → nichts).

**Dialog (`RestoreDialog`):** neuer Parameter `vm_info` (nur VMs; `ui.start_restore` übergibt
`{"snapshots": snapshot_count, "pool_free": pool_free}`). Bei `disk["size"] < need` startet `_vm_smaller` zwei Prüfungen
im Hintergrund – Ä-002 (`_shrink_state`, wie bisher) und `_grow_state` (vm_info + `used_bytes`) – und zeigt die
Optionsfelder `way_grow`/`way_adapt` (ausgegraut mit Grund im Tooltip, Prüftext mit beiden Wegen). Vorwahl einmal pro
Image/Disk, sobald beide Prüfungen fertig sind (`RestoreWays.default()`). `start_job(…, grow_gb=N)` bzw. `adapt` wie
bisher.

**Auftrag (`jobs.grow_restore_work`, ohne GTK):** ein Auftrag `restore` „VM-Disk vergrössern und zurückspielen
<Image> → <Disk>“ mit den Schritten `vm.GROW_STEPS`: 1. `power_down` – 2. `grow_disk` (Rückruf `grown` → Verlauf
„VM-Disk von 128 GB auf 513 GB vergrössert“) – 3. `start(name, "agent")`, warten bis `TWIN_AGENT_TIMEOUT` auf einen Agent
mit `last_seen` nach dem Einschalten (der alte Agent bleibt bis `AGENT_TIMEOUT` in der Liste), Zieldisk per `get_info`
muss ≥ `grow_gb` GB sein – „Vorher Snapshot“ (`vm_auto_snapshot`) erst jetzt, sonst sperrt er das Vergrössern –
4. `jobs.restore_work` mit dem neuen Agent (Fortschritt über `_StepProgress` als „Zurückspielen (4/4) · …“, Verlauf über
`_after_job` wie beim normalen Zurückspielen). Fehler in 1–3: `failed` → Verlauf „… fehlgeschlagen: … – nichts
zurückgespielt“, Log erwähnt die vergrösserte Disk. `ui._grow_restore` merkt den Agent vor (`boot_request`, wie
`_twin_restore`) und startet den Auftrag erst nach `sync_netboot`.

**Profil VM-Win11:** 256 GB, Modell „Okula NVMe SSD 256GB“ (bestehende VMs bleiben).

## Geräte

Bootet ein Gerät vom Agent-Stick, sammelt der Agent einmal das **Inventar** und das Tool legt das Gerät an bzw. erkennt es wieder.

- **Inventar:** Hersteller, Modell, Seriennummer, System-UUID, Gehäuse, Mainboard, BIOS, Prozessor, RAM, Grafikkarten (siehe [Grafikkarte](#grafikkarte-i-037)), Akku (Zustand in %), Netzwerkkarten (MAC), Disks mit Seriennummer und SMART (Zustand, Betriebsstunden, Temperatur), BitLocker-Partitionen und das **installierte Betriebssystem** (Windows-Version und Computername aus der Registry, Linux aus `os-release`). Dafür hängt der Agent die Partitionen **nur lesend** ein (ext4 `noload`, NTFS `ro`, kein Journal-Replay); auf der Disk wird nichts verändert.
- **Wiedererkennung:** über die System-UUID, sonst Hersteller + Seriennummer, sonst MAC. Nach einem Board-Tausch hilft die Disk-Seriennummer. Eine MAC allein verbindet keine zwei Geräte mit verschiedener UUID (geteilter USB-Netzwerkadapter).
- **Doppelt erfasst?** Einträge mit gleicher System-UUID (z. B. nach einem Import, wenn das Gerät auf dem neuen Server schon vorher gestartet wurde) führt das Tool beim Start und beim Import automatisch zusammen. Von Hand: Rechtsklick auf den doppelten Eintrag → **„Zusammenführen mit …“** → Gerät wählen. Name und Ordner des gewählten Geräts bleiben, Verlauf, Netzwerkkarten, Disks und Notizen werden übernommen, das Inventar kommt vom zuletzt verbundenen Eintrag. **Baugleiche Geräte (B-001):** Platzhalter ab Werk (z. B. UUID `03000200-0400-0500-0006-000700080009`, nur 0 bzw. F; Seriennummern wie „Default string“, „To be filled by O.E.M.“, Disk-Seriennummern aus Nullen) zählen nie als Identität, lokal vergebene MACs (zufällig, Tethering) nicht beim Wiedererkennen. Ist ein passender Eintrag gerade über einen anderen Agent verbunden, entsteht ein eigenes Gerät („Name (2)“); die gemeinsamen Kennungen stehen danach in `geraete/mehrdeutig.ids` und gelten nie mehr als eindeutig. Ein früher vereinter Eintrag wird dabei getrennt (MACs, Agent-ID, Disk des zweiten Geräts entfernt, Inventar neu geholt). Gleiche Agent-ID mit anderer Beacon-MAC führt das Tool als „ID@MAC“ – kein neuer Agent-Stick nötig.
- **Name:** Windows-Computername bzw. Linux-Hostname, sonst Hersteller + Modell. Umbenennen per Stift-Knopf, Rechtsklick oder im Gerätefenster.
- **Ordner:** wie bei den Images, max. 3 Ebenen, per Maus ziehen. Neue Geräte landen oben unter **„Neu / nicht einsortiert“**.
- **Ablage:** lokal auf dem Server unter `~/.local/share/okula-recovery/geraete/` – eine JSON-Datei pro Gerät, Ordner = Ordnerstruktur. Gehört in die Datensicherung des Servers.
- **Getrennt:** Kommt 15 s kein Beacon, wird die LED rot. Das Gerät bleibt in der Liste mit „zuletzt verbunden“. Löschen geht nur bei nicht verbundenen Geräten.

![Gerätefenster mit laufendem Auftrag](geraet.png)

**Gerätefenster** (Doppelklick): Kopf mit LED, Name und Status, Aktionen *Disk-Image erstellen*, *Image zurückspielen*, *Inventar neu einlesen*, die Symbole *Neu starten* und *Herunterfahren* und die Reiter

- **Aufträge:** alle Aufträge dieser Sitzung mit Fortschrittsbalken, Log des gewählten Auftrags und *Auftrag abbrechen*
- **Übersicht**, **Disks** (inkl. SMART), **Images** (Images dieses Geräts auf dem NAS; Doppelklick = zurückspielen), **Verlauf** (erfasst, verbunden/getrennt, Images, Restores, Herunterfahren – mit Ergebnis) und **Notizen**

**Mehrere Aufträge parallel:** Aufträge laufen im Hintergrund, auch auf mehreren Geräten gleichzeitig und auf verschiedenen Disks desselben Geräts. Pro Disk ist nur ein Auftrag möglich. Die Geräteliste zeigt pro Gerät einen Fortschrittsbalken mit Prozent, Auftrag und geschätzter Restzeit (z. B. „▬▬▭ **48 %** Disk-Image · noch 7 min“; bei mehreren Aufträgen „2 Aufträge“ mit Mittelwert und längster Restzeit). Die Restzeit erscheint nach etwa 10 s Laufzeit. Beim Beenden warnt das Tool, solange Aufträge laufen.

> Nach dem Update den **Agent-Stick neu erstellen** – ältere Sticks liefern kein Inventar und können nur einen Auftrag gleichzeitig.

## Inventar, Garantie, Windows 11

Das Tool liest bei jedem Verbinden das Inventar des Geräts (siehe [Geräte](#geräte)). Die Angaben stehen im Gerätefenster unter *Übersicht* und *Disks*; *Inventar neu einlesen* holt sie neu.

### Grafikkarte (I-037)

Der Agent erfasst die Grafikgeräte (PCI-Klasse `03xx`: VGA, 3D, Display) im Inventar unter `gpus` – je Gerät
PCI-Adresse (`slot`), Klasse, Hersteller- und Geräte-ID (`vendor`, `device`, hex), Namen (`vendor_name`,
`device_name`), Subsystem (`subsystem_vendor`/`_device`, `subsystem_vendor_name`, `subsystem_name` = Hersteller bzw.
Modell der Karte) und den gebundenen Kernel-Treiber (`driver`). Quelle ist `lspci -vmm -nn -D -k` (Paket `pciutils`
auf dem Agent-Stick, Datenbank `pci.ids` kommt über `libpci3` mit); fehlt `lspci`, liest der Agent
`/sys/bus/pci/devices/*/{class,vendor,device,subsystem_vendor,subsystem_device}` und die Namen aus
`/usr/share/misc/pci.ids` bzw. `/usr/share/hwdata/pci.ids` – ohne Datenbank nur die IDs. Zusatzfunktionen derselben
Karte (HDMI-Audio, Klasse `04xx`) zählen nicht. Kein Grafikspeicher (VRAM): ohne Treiber nicht zuverlässig lesbar.

Übersicht im Gerätefenster: Zeile **„Grafikkarte“** (mehrere: „Grafikkarte 1“, „Grafikkarte 2“ … nach PCI-Adresse),
z. B. „NVIDIA GeForce GT 740 (GK107)  (0000:01:00.0)“. Hersteller als Kurzname (NVIDIA, AMD, Intel, Matrox, ASPEED …
nach Hersteller-ID), Modell aus „Chip [Verkaufsname]“ → „Verkaufsname (Chip)“ (`inventory.gpu_text`, `gpu_rows`).
Tooltip: PCI-Adresse, IDs, Hersteller der Karte, Treiber. Altes Inventar ohne `gpus` → keine Zeile; leere Liste → „–“.
Nur Anzeige – keine Treiber-Empfehlung. Digitaler Zwilling: Grafikkarte nur als Hinweis und Zeile in der Vorschau
(✖), die VM behält ihre Standard-Grafik.

### Windows 11

Zeile **„Windows 11“** im Gerätefenster (Übersicht): ✔ tauglich, ✖ nicht tauglich mit Grund (z. B. „✖ TPM 1.2 (2.0 nötig)“), ? unbekannt; auch im Inventar-Export. Nicht in der Geräteliste (bewusst, übersichtlicher). Der Agent erfasst TPM-Version, UEFI/BIOS-Start und Secure Boot; das Tool prüft TPM 2.0, UEFI, RAM ≥ 4 GB, Disk ≥ 64 GB und den Prozessor gegen Microsofts Listen (`okula_recovery/data/win11_cpus.txt`, abgeglichen am 31.10.2026 mit den offiziellen Listen Original/24H2/25H2 für Intel, AMD und Qualcomm; tauglich = Serie steht in einer dieser Listen, Quellen im Kopf der Datei). Ältere Inventare zeigen „?“ – Agent-Stick neu erstellen und Inventar neu einlesen.

Windows 11 auf nicht unterstützter Hardware: siehe [Betriebssystem direkt installieren](#betriebssystem-direkt-auf-ein-gerät-installieren).

### Garantie

Zeile **„Garantie bis“** im Gerätefenster (Übersicht). Grün = gültig, **gelb** = läuft in höchstens 90 Tagen ab, **rot** = abgelaufen. Knopf **„Beim Hersteller abfragen“** fragt per Seriennummer nach: **Dell** (TechDirect Warranty API) und **HP** (HP Warranty API) brauchen einen Schlüssel, einzutragen unter **Menü → Einstellungen → Garantie-Abfrage**; **Lenovo** über die öffentliche Support-Seite, ohne Schlüssel. Ohne Schlüssel, ohne Internet oder bei anderen Herstellern: **„Von Hand …“** (TT.MM.JJJJ). Abgefragt wird nur auf Knopfdruck und einmal automatisch nach dem ersten Erfassen – kein Dauer-Polling. Das Ergebnis bleibt am Gerät gespeichert (gilt 30 Tage als aktuell, danach Hinweis „älter als 30 Tage“); schlägt eine Abfrage fehl, bleibt das alte Datum und der Fehler steht darunter. Die Schlüssel speichert nur der Root-Helfer `/usr/local/sbin/okula-warranty` in `/etc/okula-recovery/warranty.cred` (root, `0600`); er fragt Dell/HP selbst ab und gibt nur das Ergebnis zurück. Die Schlüssel stehen nie in der Konfiguration, im Repo oder im Export und werden im Tool nie angezeigt. Zugang: Dell über TechDirect (APIs → Warranty, Freigabe durch Dell), HP über developers.hp.com (Freigabe durch HP, Schlüssel 90 Tage gültig).

### BIOS (I-032)
Reiter **BIOS** im Gerätefenster. Agent (`biosread.py`, nur stdlib): Grundangaben (DMI `bios_*`, `inventory.platform`, UEFI-Startreihenfolge per efibootmgr) und Einstellungen über die Linux-Schnittstelle `firmware-attributes` (`/sys/class/firmware-attributes/<Treiber>/attributes/<Name>/{type,current_value,display_name,possible_values,…}`; Treiber `hp-bioscfg`, `dell-wmi-sysman`, `think-lmi`, werden per `modprobe` geladen). Befehle `bios` (lesen) und `bios_set` (Wert setzen; Passwort nur für den Aufruf in `authentication/<Rolle>/current_password`, danach gelöscht, nie gespeichert oder protokolliert; erlaubte Werte geprüft). Tool (`biosinfo.py`, `bios_tab.py`): Stand je Gerät in `Device.bios`, Vergleich mit einem anderen Gerät (nur Unterschiede, wichtige Einstellungen zuerst), Suche, CSV, Warnung vor riskanten Änderungen (Boot-Modus, Secure Boot, TPM). Neuer Agent-Stick nötig; ältere Agents melden „Agent zu alt“. Das Demo-Gerät hat ein simuliertes HP-BIOS.

### Hardware-Test (I-023)
Reiter **Hardware-Test** im Gerätefenster, nur lesend. Agent (`hwtest.py`, stdlib + smartctl): Akku (`power_supply`: Kapazität gegen neu, Zyklen), Temperaturen (hwmon/thermal), SMART-Selbsttest kurz/lang (`smartctl -t`, ATA und NVMe, Werte 5/197/198/199 bzw. NVMe Abnutzung/Reserve/Medienfehler), Oberfläche (jeden Sektor lesen, `posix_fadvise` gegen Zwischenspeicher, Lesefehler übersprungen), Arbeitsspeicher (Muster 0x00/FF/55/AA im freien Speicher, Schnell 15 %/max. 1 GiB, Gründlich 60 %/max. 16 GiB), CPU-Last (je Kern ein Prozess, Temperatur, Takt, `thermal_throttle`, Kernel-Meldungen zu Machine Checks), Netzwerk (Daten an das Tool, ohne Bandbreitengrenze). Befehl `hwtest`: Ereignisse step_start/progress/step, Durchsatz über Daten-Frames mit Bestätigung, Abbrechen per `cancel`; die gewählten Disks sind gesperrt. Tool: Auftrag „Hardware-Test“ (`jobs.hwtest_work`), Bericht in `Device.hwtests` (letzte 10), Verlauf, PDF-Prüfprotokoll (`hwreport.py`, reportlab). Neuer Agent-Stick nötig. Folgt: vollständiger RAM-Test mit memtest86+ (I-033).

**Prozessor-Fehler (Machine Check, B-011):** Der Agent liest das Kernel-Protokoll seit dem Start vor und nach der Last
(`journalctl -k -b -o short-monotonic --no-pager`, liefert es nichts oder einen Fehler: `dmesg`) – bewusst **ohne
`journalctl -g`** (braucht PCRE2 zur Laufzeit; Fehler fielen früher als „0 Fehler“ durch). Gefiltert wird in Python
(„mce“, „machine check“, „hardware error“, Gross-/Kleinschreibung egal); Rückgabewert, Zeitlimit (60 s) und fehlende
Programme werden geprüft. Ein Ereignis ist die Zeile `CPU n: Machine Check: … Bank b: <Status>` (PROCESSOR-, TSC-,
ADDR-Zeilen zählen nicht), `Machine check events logged` zählt „ohne Zuordnung“; Status-Bit 61 (UC) unterscheidet
korrigiert/nicht korrigiert. Gruppen nach CPU, Bank und Art mit Anzahl und höchstens 3 Beispielzeilen (gekürzt). Neu
während der Last = Zeilen, die zwischen den beiden Lesungen dazukamen (Zeitstempel unterscheiden gleichlautende
Meldungen). Bewertung: neue während der Last oder nicht korrigiert → rot; nur vor dem Test → gelb („Hardware-Fehler
seit dem Start gemeldet (CPU 3, Bank 0: 12 Mal) – BIOS-Update bzw. Prozessor prüfen“); Temperatur/Drosselung wie
bisher, der schlechtere Status gilt. Kernel-Protokoll nicht lesbar → Detail „Hardware-Fehler nicht prüfbar“, Status
unverändert. `values`: `mce` (neu während der Last), `mce_boot` (seit Start), `mce_groups` (`cpu`, `bank`, `count`,
`kind` = corrected/uncorrected/leer, `during`). Funktionen `mce_events`/`mce_groups`/`new_lines` rein (Tests mit den
Zeilen vom Foto SRV-002), `_mce_lines` für Tests austauschbar.

### Inventar exportieren (CSV/PDF)

**Menü → Inventar exportieren (CSV/PDF) …** oder **Rechtsklick auf einen Ordner** (bzw. „Neu / nicht einsortiert“ oder ein Gerät) → **„Inventar exportieren …“**.

- **Welche Geräte:** alle, ein Ordner (mit Unterordnern) oder markierte Geräte (Häkchen in der Liste).
- **CSV:** eine Datei mit allen gewählten Geräten, UTF-8 mit BOM und Semikolon – öffnet sich in Excel direkt richtig. Mehrere Disks sind mit „ | “ getrennt.
- **PDF:** wahlweise **je Ordner eine Datei** (Titel = Ordnername wie in der Geräteliste, Unterordner bekommen eine eigene Datei, im Kopf steht der volle Ort, z. B. „Zürich › Buchhaltung“) oder **alle gewählten Geräte in einer Datei**. A4 quer, Kopf mit Ordnername und Datum, Tabelle, Seitenzahl; Garantie gelb/rot wie im Tool. Braucht `python3-reportlab` (installiert `install.sh`).
- **Spalten:** Name, Ordner, Hersteller, Modell, Seriennummer, CPU, RAM, Disks (Modell, Grösse, SMART), OS, Win-11-tauglich, Garantie bis, zuletzt verbunden, letztes Image, letztes Backup. Letztes Image/Backup nur, wenn das NAS verbunden ist.
- **Windows-Schlüssel:** „Windows-Schlüssel nicht exportieren“ ist standardmässig an. Ausgeschaltet kommt er nur **maskiert** (`XXXXX-XXXXX-XXXXX-XXXXX-ABCDE`) mit, nie vollständig. Passwörter und Schlüssel des Tools (NAS, Garantie, Agent) sind nie im Inventar.
- Dateinamen: `Inventar_<Ordner>_<Datum>.csv/.pdf` (bei Unterordnern mit vollem Pfad, z. B. `Inventar_Zürich_Buchhaltung_…`), Ziel frei wählbar (Standard: Dokumente).

## Disk-Image erstellen

Links das verbundene Gerät wählen (grüne LED) bzw. im Gerätefenster **„Disk-Image erstellen …“**. Im Dialog Disk und Archivname (vorgeschlagen: Gerätename) wählen und auf **„Image erstellen“** klicken. Der Auftrag läuft im Hintergrund weiter, Fortschritt und Log stehen im Gerätefenster unter *Aufträge*.

- **Disk-Image oder Backup:** Das Disk-Image sichert die ganze Disk: Partitionstabelle, Bootloader und alle Partitionen. Zurückgespielt ist die Maschine wieder genau wie vorher. Ein [Datei-Backup](#datei-backup) sichert nur ausgewählte Ordner.
- **Ablage:** `NAS/images/<Name>/<Datum_Zeit>_<disk>/` mit
  - `okula-image.json` (Metadaten, SHA256 je Datei)
  - `<disk>.sfdisk` (Partitionstabelle) sowie `-head.img` und `-tail.img` (erstes und letztes MiB, also MBR/GPT und Bootloader)
  - pro Partition `<part>.<fs>.pcl.zst` (partclone, nur belegte Blöcke, zstd-komprimiert) oder `<part>.dd.img.zst` für unbekannte und verschlüsselte Partitionen (BitLocker, LUKS): Rohkopie aller Blöcke
  - Swap wird nicht gesichert.
- **Datenfluss:** Der Agent liest die Disk nur und streamt über **TCP 47812** (TLS 1.3 mit PSK) zum Tool. Das Tool prüft die SHA256-Summen und schreibt aufs eingehängte NAS. Der Agent bekommt keine NAS-Zugangsdaten.
- **Abbruch und Fehler:** Während der Arbeit heisst der Ordner `….partial`. Bei Abbruch oder Fehler löscht das Tool ihn wieder, und in der Image-Liste erscheinen nur vollständige Images.
- **Schlüssel:** Das Tool erzeugt beim ersten Stick `~/.config/okula-recovery/agent.key` und bettet ihn in jeden Stick ein. Ein Stick von einem anderen Tool wird abgewiesen. Wer den Stick hat, hat auch den Schlüssel, deshalb die Sticks wie Admin-Werkzeug aufbewahren.
- **Werkzeugsuche:** sfdisk, partclone, wipefs … liegen in `/usr/sbin`, das bei Debian nicht im PATH normaler Benutzer steht. `okula_recovery/systools.py` (`find_tool`, `resolve`) sucht deshalb zuerst im PATH und danach in `/usr/local/sbin`, `/usr/sbin` und `/sbin`; Imaging und Clonezilla-Prüfung starten die Programme mit vollem Pfad (B-009).
- **partclone auf dem Stick:** `partclone` und `zstd` fehlen im Debian-Live-Image. Das Tool lädt sie beim Erstellen des Sticks mit `apt-get download` aus den Paketquellen des Servers (gleiche Debian-Version) und legt nur die fehlenden Pakete in den Agent-Layer. Dafür braucht der Server Internetzugang.

Tipp für Windows: Vorher vollständig herunterfahren (Shift-Taste gedrückt halten + „Herunterfahren“), sonst meldet partclone ein „inkonsistentes“ NTFS (Schnellstart/Ruhezustand).

## Image zurückspielen

Das Zielgerät vom Agent-Stick booten und links auswählen (oder im Gerätefenster), dann **„Image zurückspielen“**. Ist rechts im Reiter *Images* ein Image markiert, ist es im Dialog schon vorgewählt.

1. **Image wählen:** Der Dialog zeigt die Quelle, also Maschine, Disk, Grösse und Partitionen.
2. **Zieldisk wählen:** Darunter steht, was auf ihr **vollständig überschrieben** wird.
3. **Bestätigen:** Den Disk-Namen (z. B. `sda`) eintippen, erst dann wird **Zurückspielen** aktiv.

**Ablauf:**
1. **Image prüfen (empfohlen, Standard):** Das Tool liest alle Dateien vom NAS und vergleicht die SHA256-Summen. Ein beschädigtes Image wird erkannt, bevor etwas auf die Zieldisk geschrieben wird.
2. **Zieldisk prüfen:** Der Agent kontrolliert, dass die Zieldisk mindestens so gross ist wie die Quelldisk, dass keine Partition eingehängt ist und dass es nicht der Boot-Stick ist.
3. **Tabelle und Bootcode:** Alte Signaturen werden entfernt. Dann schreibt der Agent die Partitionstabelle (`sfdisk`), den MBR-Bootcode und die Bootloader-Lücke vor der ersten Partition. Bei einer grösseren Zieldisk wird die GPT-Backup-Tabelle ans neue Disk-Ende gesetzt.
4. **Partitionen:** `zstd -d | partclone.<fs> -r` schreibt jede Partition zurück, Rohkopien gehen per `dd`. Der Agent prüft dabei nochmals die Prüfsumme jeder Datei.
5. **Swap:** Swap wird mit der gleichen UUID und dem gleichen Label neu angelegt.

**Abschluss:** Gerät herunterfahren, dann den Stick abziehen und einschalten (nie abziehen, solange der Agent läuft).

**Einschränkungen:**
- **Kleinere Zieldisk (Ä-002):** Ist die Zieldisk kleiner (z. B. 512-GB-Image auf 256-GB-SSD), prüft der Dialog sofort, ob die belegten Daten passen, und bietet **„Für diese Disk anpassen“** an. Das Tool erstellt auf dem Server ein **neues Image** daneben (`…_für_256GB`): die grosse Partition (NTFS oder ext2/3/4) wird verkleinert, Partitionen dahinter (z. B. Recovery) rücken ans Ende. Das Original bleibt unverändert, ein angepasstes Image wird wiederverwendet. Zwischenspeicher: Server-SSD (`/var/tmp/okula-recovery`), sonst NAS. Nicht möglich bei BitLocker/Rohkopien, Btrfs/XFS, LVM und MBR mit logischen Partitionen – dann kommt der Grund mit Zahlen. Windows prüft das Laufwerk danach evtl. einmal beim Start. Belegte Daten kommen aus dem partclone-Kopf (`shrink.parse_pcl_header`): Format 0002 schreibt bei grossen Images `usedblocks = 0`, dann gilt das Feld danach (`used_bitmap`, ≤ `totalblock`); sind beide 0 oder unplausibel, lehnt die Prüfung ab („Belegter Platz im Image nicht lesbar – Anpassen nicht möglich“, B-007). Details: [docs/KLEINERE-DISK.md](KLEINERE-DISK.md).
- **Grössere Zieldisk:** Der zusätzliche Platz bleibt unpartitioniert. Unter Windows lässt sich die Partition danach in der Datenträgerverwaltung erweitern.
- **Abbruch:** Ein Abbruch während des Schreibens hinterlässt eine unvollständige Zieldisk; brauchbar ist sie erst nach einem vollständigen Durchlauf.
- **Gleiche Hardware:** Am besten zurück auf dieselbe oder baugleiche Hardware. Bei anderer Hardware braucht Windows unter Umständen andere Treiber.

### Clonezilla-Images zurückspielen

Bestehende Clonezilla-Images (Modus „savedisk“) erkennt das Tool automatisch und zeigt sie rechts in der Image-Liste und im Dialog „Image zurückspielen“ – mit der Kennzeichnung **[Clonezilla]**, bei mehreren gesicherten Disks mit einem Eintrag pro Disk. Den Image-Ordner einfach auf die NAS-Freigabe kopieren, Unterordner sind erlaubt.

- **Unterstützt:** partclone-Images aller Dateisysteme (`sda1.ntfs-ptcl-img.gz.aa …`) mit der Kompression gzip, zstd, bzip2, xz, lz4 oder lzop, gesplittet (`.aa`/`.ab`, `.aaa` …) oder nicht. Dazu Rohkopien (`dd-ptcl-img`), Swap (UUID/Label aus `swappt-*.info`), Partitionstabelle (`*-pt.sf`), MBR und die „hidden data“ nach dem MBR.
- **Prüfung vor dem Schreiben:** Clonezilla speichert keine Prüfsummen. Das Tool entpackt deshalb jedes Partitions-Image auf dem Server und prüft es mit `partclone.chkimg` (interne Prüfsummen von partclone), Rohkopien über die CRC der Kompression. Ein beschädigtes Image wird erkannt, bevor die Zieldisk angefasst wird.
- **Grösse:** Die Zieldisk muss mindestens so gross sein wie die Quelldisk (aus `*-pt.parted`).
- **Nicht unterstützt** (wird im Dialog mit Grund gemeldet): LVM, sehr alte Images mit ntfsclone/partimage (`*.ntfs-img`), Images einzelner Partitionen (Modus „saveparts“).
- **Agent-Stick:** Für gzip-, lz4- und lzop-Images liefert der Stick `pigz`, `lz4` und `lzop` mit, falls sie im Live-System fehlen. Dafür den Stick einmal mit dem aktuellen Tool neu erstellen.

### Fortschritt am Agent und Herunterfahren

- **Am Bildschirm der Zielmaschine:** Während Disk-Image oder Zurückspielen zeigt der Agent einen Fortschrittsbalken mit Prozent, Partition, Geschwindigkeit und Restzeit, danach eine Abschlussmeldung:
  ```
    Image wird auf /dev/sda zurückgespielt – Maschine nicht ausschalten
    [==============>               ]  47 %  sda3  98 MB/s  noch ca. 6 min
  ```
- **Image-Prüfung im Tool:** Beim Zurückspielen zeigt der Agent schon während der Prüfung einen Balken („Image wird im Tool geprüft … – gleich wird zurückgespielt“). Schlägt die Prüfung fehl, erscheint das auch am Agent-Bildschirm.
- **Status-Spalte im Tool:** Die Geräteliste zeigt pro Gerät, was gerade läuft, etwa „Image prüfen 37 %“, „Zurückspielen 52 %“, „Disk-Image 10 %“, „Inventar wird gelesen …“, „bereit“ oder „nicht verbunden“.
- **Danach herunterfahren:** In beiden Dialogen gibt es das Häkchen „Maschine danach herunterfahren“. Es greift nur, wenn der Auftrag erfolgreich war.
- **Symbole „Neu starten“ und „Herunterfahren“:** rechts unter der Geräteliste und im Gerätefenster (Systemsymbole `system-reboot`/`system-shutdown`, Name als Tooltip), mit Rückfrage. Im Menü Tools gibt es dafür keinen Eintrag mehr. Nach dem Auftrag wird nur heruntergefahren, wenn auf dem Gerät kein weiterer Auftrag läuft. Während ein Auftrag läuft, lehnt der Agent das Herunterfahren ab. Auf seinem Bildschirm meldet er „Maschine wird in 5 s heruntergefahren“.

## Master-Image (Sysprep)

Ein Master-Image ist ein vorbereitetes Windows für viele Geräte. Beim Zurückspielen bekommt jedes Gerät seinen eigenen Namen, seinen Windows-Schlüssel und auf Wunsch Region Schweiz und ein lokales Konto. Ausführliche Anleitung: [docs/MASTER-IMAGE.md](MASTER-IMAGE.md).

**Vorbereiten (am Referenzgerät):**
1. Windows frisch installieren, sodass es im **Audit-Modus** startet (ohne Benutzer): im Tool *OS installieren …* mit Häkchen **„Für Master-Image (Audit-Modus)“** (I-038, siehe „Betriebssystem direkt auf ein Gerät installieren“) oder von Hand beim ersten Einrichtungsbildschirm **Ctrl+Shift+F3**. Bei einer VM vor Sysprep einen Snapshot erstellen (Reiter *Snapshots*).
2. Updates, Treiber und Programme installieren. Kein Microsoft-Konto, keine Domäne. BitLocker ausschalten. Desktop-Symbole, Taskleiste, Explorer-Ansicht usw. direkt am eingebauten Administrator einrichten – das Tool übernimmt sie (Ä-040, unten). Kein weiteres lokales Konto anlegen.
3. Sysprep als Administrator starten: `C:\Windows\System32\Sysprep\sysprep.exe /generalize /oobe /shutdown`
4. Windows **nicht mehr starten**, direkt mit dem Agent-Stick starten und *Disk-Image erstellen …* (Name z. B. „Master-Win11-2026-10“).

**Im Tool:**
- **Markieren:** Rechtsklick auf das Image → **„Als Master-Image markieren“** (bzw. „Master-Markierung entfernen“). Die Liste zeigt „★ Master“. Die Markierung ist die Datei `okula-master.json` im Image-Ordner (Okula- und Clonezilla-Images).
- **Anpassen:** Im Dialog „Image zurückspielen“ ist bei einem Master-Image **„Danach anpassen“** vorgewählt: Gerätename (aus dem Tool), Windows-Schlüssel (hinterlegt oder aus dem BIOS), optional Region Schweiz und ein lokales Konto (Passwort beim ersten Anmelden – wird nirgends gespeichert), dazu „Einstellungen des Administrators übernehmen (Master)“ (Standard an, Ä-040, unten).
- **Wie:** Nach dem Zurückspielen hängt der Agent die Windows-Partition ein und legt `Windows\Panther\unattend.xml` ab. Windows richtet sich beim ersten Start damit ohne Fragen ein. Ob das Image generalisiert ist, erkennt der Agent an `Windows\Setup\State\State.ini` (`IMAGE_STATE_GENERALIZE_RESEAL_TO_OOBE`). Ein nicht generalisiertes Windows wird **nicht** verändert (Hinweis im Log). Linux bekommt den Hostnamen (`/etc/hostname`, `/etc/hosts`).
- Ein Image eines UEFI-Geräts läuft nur auf UEFI-Geräten.

### Einstellungen des Administrators übernehmen (Ä-040)

Sysprep `/generalize` lässt das Profil des eingebauten Administrators liegen, neue Benutzer bekommen aber das
Standardprofil (`Users\Default`). Ohne weiteres fehlen ihnen Anordnung der Desktop-Symbole, Explorer-Ansicht und
Taskleiste aus dem Audit-Modus (Befund Master CompactPlayer 17.11.2026). Das Tool löst das ohne Skripte im Master:

- **Option:** Häkchen **„Einstellungen des Administrators übernehmen (Master)“** im Dialog *Image zurückspielen*
  unter *Danach anpassen* (Standard an, nicht gespeichert – wie Region/Konto) und in der Automatisierung, Schritt
  *Anpassen* (`automation.Settings.copy_profile`, Standard an, auch in Vorlagen). Texte in
  `winunattend.COPY_PROFILE_LABEL/TOOLTIP`.
- **CopyProfile:** `winunattend.master_unattend(…, copy_profile=True)` schreibt in **specialize**
  `Microsoft-Windows-Shell-Setup/CopyProfile = true` (nach `ComputerName`, Reihenfolge wie Windows SIM). Nie bei der
  Direktinstallation im Audit-Modus (`_audit_opts`). Ohne Option ist die Antwortdatei unverändert.
- **Taskleiste (Agent, `winprofile.py`, Befehl `customize` mit `copy_profile`):** nur bei generalisiertem Windows,
  nachdem `Panther\unattend.xml` geschrieben ist.
  1. Quellprofil: `Users\Administrator` (bzw. `Administrator.*`), sonst das **einzige** Profil mit angehefteten
     Symbolen; nie Default, Public, All Users. Mehrere Kandidaten ohne Administrator → nichts, Grund im Log.
  2. Pins: `AppData\Roaming\Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar\*.lnk`. **Reihenfolge** aus
     `NTUSER.DAT` → `Software\Microsoft\Windows\CurrentVersion\Explorer\Taskband\Favorites` (REG_BINARY; Position des
     Dateinamens in UTF-16). Eigener, rein lesender regf-Leser (`winprofile.Hive`, nk/vk/lf/lh/li/ri/db) – kein
     Werkzeug nötig, kein Hive wird geschrieben. Store-Apps ohne `.lnk` (z. B. Microsoft Store, Mail) werden über ihre
     AppUserModelID im selben Blob erkannt (`Name_<13 Zeichen>!App`, heuristisch; doppelt mit einer Verknüpfung, die
     dieselbe ID trägt → nur die Verknüpfung). Ist die Registrierung nicht lesbar: Reihenfolge nach Datum der
     `.lnk`, ohne Store-Apps (Hinweis im Log).
  3. Zuordnung: Ziel `explorer.exe` → `DesktopApplicationID="Microsoft.Windows.Explorer"`, `msedge.exe` → `"MSEdge"`
     (IDs aus den Microsoft-Beispielen), Store-App → `taskbar:UWA AppUserModelID`, übrige → `DesktopApplicationLinkPath`
     auf eine Verknüpfung im Startmenü für alle (`%ALLUSERSPROFILE%\Microsoft\Windows\Start Menu\Programs\…`): zuerst
     eine vorhandene mit gleichem Ziel (LinkInfo bzw. EnvironmentVariableDataBlock der `.lnk`), dann gleicher
     Dateiname, sonst Kopie nach `…\Programs\Okula\` (Microsoft: Verknüpfungen für Drittprogramme müssen vor dem
     ersten Start in einem Startmenü-Ordner liegen).
  4. Datei `LayoutModification.xml` (`CustomTaskbarLayoutCollection PinListPlacement="Replace"`, Reihenfolge wie beim
     Administrator) nach `Users\Default\AppData\Local\Microsoft\Windows\Shell\` **und** in denselben Ordner des
     Quellprofils – CopyProfile ersetzt das Standardprofil durch das des Administrators, so ist die Datei in beiden
     Fällen da. Ein vorhandenes gültiges Startlayout in der Datei bleibt (nur die Taskleiste wird ersetzt, Position nach
     XSD-Reihenfolge); eine ungültige Datei bleibt als `LayoutModification.xml.okula-vorher` daneben.
  5. Keine Pins oder Option aus → nichts geschrieben. Fehler beim Schreiben brechen das Anpassen nicht ab (Name und
     Key sind gesetzt), sie stehen im Log.
- **Log:** „Einstellungen des Administrators werden übernommen – Taskleiste: VLC media player, Explorer …“
  (`winunattend.taskbar_log`), bei altem Agent „… Agent zu alt“. Nicht generalisiertes Windows: wie bisher nur
  „nicht mit Sysprep vorbereitet“, nichts geändert.
- **Agent betroffen:** neues Modul `winprofile.py` in `stick.AGENT_MODULES` → **neuer Agent-Stick** bzw. Netzwerkstart
  neu vorbereiten.

**Belegt (Microsoft Learn, abgerufen 17.11.2026):**
- „CopyProfile“ (Unattend-Referenz): *„CopyProfile runs during the specialize configuration pass. It should be used
  after customize the built-in administrator profile.“* Gültiger Durchgang nur **specialize**. *„On the reference
  computer, use only the built-in administrator account. Creating multiple accounts might cause you to copy the wrong
  user profile“*; keine Domänenkonten; *„some customizations to the default user profile are not copied, such as items
  that are pinned to the task bar“*; Standard-Apps (Hash pro Benutzer) werden nicht unterstützt.
- „Customize the default user profile by using CopyProfile“: im Audit-Modus am eingebauten Administrator einrichten;
  *„Using CopyProfile to customize the Start menu isn't supported“* (Windows 10: `LayoutModification.xml`); Ablauf
  mit `sysprep /generalize /oobe /unattend:…`; Troubleshooting: CopyProfile nur einmal setzen, keine weiteren Konten.
- „Configure the Windows Taskbar Pinned Apps“ / „Customize the Taskbar“: Format `LayoutModificationTemplate`,
  `PinListPlacement="Replace"` entfernt die Standard-Pins, Reihenfolge der Liste = Reihenfolge auf der Taskleiste,
  Explorer als `DesktopApplicationID="Microsoft.Windows.Explorer"`, Edge als `"MSEdge"`.
- „Customize the Start layout for managed Windows devices“: `.lnk` für Drittprogramme vor dem ersten Start in einen
  Startmenü-Ordner (`%ALLUSERSPROFILE%\Microsoft\Windows\Start Menu\Programs\`), Umgebungsvariablen erlaubt.

**Nicht belegt / offen (am Gerät prüfen, [TESTS.md](TESTS.md) Abschnitt 22):**
- Format von `Taskband\Favorites` ist nicht dokumentiert; Reihenfolge und Store-Apps werden nur über die Position der
  Namen im Blob bestimmt.
- Die Antwortdatei des Tools wird **nach** `/generalize` abgelegt (Microsoft beschreibt `/unattend` beim Sysprep-Aufruf).
  Da CopyProfile in specialize läuft und Setup dort `Panther\unattend.xml` liest (wie bisher Name und Key), sollte es
  wirken – Microsoft belegt diese Variante nicht ausdrücklich.
- Ablageort `Users\Default\…\Shell\LayoutModification.xml` für die Taskleiste: üblicher Ort (dorthin schreibt auch
  `Import-StartLayout`), in den OEM-Seiten verweist Microsoft für die Taskleiste auf `LayoutXMLPath` (Registrierung im
  Image, vor specialize) – das würde ein Schreiben in den Hive `SOFTWARE` verlangen und ist bewusst nicht umgesetzt.
- **Windows 11:** gleiche Datei wird geschrieben (schadet nicht); ob Windows 11 sie für die Taskleiste liest, ist zu
  prüfen. Startmenü von Windows 11 (`LayoutModification.json`, nur über Richtlinie bzw. ab 24H2) ist hier nicht
  umgesetzt – Werbe-Kacheln entfernt *Windows anpassen* (Ä-042, Richtlinie ConfigureStartPins, siehe dort).
- **Startmenü-Kacheln (Windows 10)** werden nicht übernommen: Das Layout liegt pro Benutzer in einer binären
  Datenbank (CloudStore/TileDataLayer) und lässt sich aus dem Profil nicht zuverlässig ableiten; CopyProfile
  unterstützt das Startmenü laut Microsoft nicht.
- Microsoft empfiehlt nach CopyProfile, im Standardprofil `…\Shell\Associations\FileAssociationsUpdateVersion`,
  `…\Shell\Associations\UrlAssociations` und `…\Explorer\FileExts` zu löschen, sonst setzt Windows Standard-Apps evtl.
  zurück (Meldung „App-Standardeinstellung wurde zurückgesetzt“). Das passiert erst nach CopyProfile beim ersten
  Start und ist nicht umgesetzt (bräuchte einen Befehl nach CopyProfile vor der ersten Anmeldung).

## Betriebssysteme (ISOs) und Boot-Sticks

Rechts im Reiter *Images* steht der Ast **„Betriebssysteme“**. Das Tool legt dafür auf dem NAS `OS/Windows`, `OS/Linux` und `OS/Sonstige` an; darunter sind eigene Ordner möglich (insgesamt max. 3 Ebenen).

- **ISO hinzufügen …** (Knopf, Rechtsklick oder Tools-Menü) oder ISO-Dateien aus dem Dateimanager auf den Baum ziehen. Das Tool kopiert sie aufs NAS, berechnet dabei die SHA-256-Summe und ordnet sie nach Windows / Linux / Sonstige ein. Auf einen Ordner gezogen landen sie dort. Auch Disk-Abbilder (`.img`, `.img.xz/.gz/.zst/.bz2`) gehen.
- **Erkennung** ohne Einhängen: Windows-ISOs über das UDF-Dateisystem und die Beschreibung der `install.wim/esd` (Produkt, Version wie 24H2, Sprache, alle Editionen), Linux über `.disk/info` bzw. `.treeinfo` (Ubuntu, Debian, Fedora …). Ob eine ISO per UEFI, BIOS oder als Hybrid (DD) startet, steht in den Details.
- **Details und Prüfsummen** (Doppelklick): Editionen, Boot-Arten, MD5/SHA-1/SHA-256/SHA-512 und ein Feld zum Vergleichen mit der Prüfsumme von der Herstellerseite (grün/rot).
- Verschieben per Maus zwischen OS-Ordnern, Umbenennen, Löschen wie bei den Images.

![Betriebssysteme im Image-Baum](betriebssysteme.png)

**Boot-Stick aus ISO …** (Funktionen wie Rufus):

![Boot-Stick-Dialog](bootstick.png)

| Schreibart | Für | Ablauf |
|---|---|---|
| Windows-Installation | Windows 10/11 | MBR (UEFI + BIOS) oder GPT (nur UEFI), FAT32. Eine `install.wim` über 4 GB wird in `install.swm`-Teile gesplittet (von Windows-Setup unterstützt). UEFI startet den signierten Microsoft-Bootloader – **Secure Boot funktioniert**. BIOS startet über GRUB → bootmgr. |
| Abbild 1:1 (DD) | Linux-Hybrid-ISOs, Disk-Abbilder | Schreibt das Abbild direkt (auch komprimiert), löscht alte Partitionstabellen inkl. GPT-Kopie am Ende, danach **Lesevergleich** (SHA-256). |
| Dateien kopieren | UEFI-ISOs ohne Hybrid-Bootsektor | FAT32, nur UEFI. |

- **Stick prüfen** vor dem Schreiben: *Schnelltest* (Standard, Sekunden) erkennt **gefälschte Sticks**, die mehr Kapazität melden als vorhanden; *Vollständig* schreibt und liest alle Blöcke (badblocks, dauert lange).
- **Windows-Anpassung** (`autounattend.xml` auf dem Stick): optional **„Auch für nicht unterstützte Hardware“** (TPM 2.0, Secure Boot, RAM, CPU nicht prüfen – standardmässig **aus**, Einschalten nur nach Bestätigung der Microsoft-Hinweise), lokales Konto statt Microsoft-Konto (Name, vorbelegt „Okula“, Prüfung wie beim Direktinstallieren – siehe
„Windows-Konto (B-012)“ unten; optional Passwort – sonst beim ersten Anmelden setzen), Datenschutz-Fragen überspringen, keine automatische BitLocker-Verschlüsselung, **Region Schweiz** (Formate de-CH, Tastatur Schweiz-Deutsch, Zeitzone Zürich), optional Computername. Die Windows-Sprache bleibt die des Mediums.
- Der Stick wird über den bestehenden Root-Helfer geschrieben (`sudo okula-make-stick iso-stick …`); ISOs werden nur vom eingehängten NAS (`/mnt/…`) akzeptiert.
- Nicht übernommen von Rufus: ReFS/MS-DOS (unter Linux nicht erstellbar), FFU-Abbilder (nur mit Microsoft DISM), Windows To Go, Download von Windows-ISOs (ISOs selbst hochladen).

### Betriebssystem direkt auf ein Gerät installieren

Gerät mit dem Agent-Stick starten, dann im Gerätefenster (oder Rechtsklick auf das Gerät bzw. auf eine ISO → „Auf Gerät installieren …“) **„OS installieren …“**. Im Dialog Betriebssystem, Zieldisk und Einstellungen wählen, Disk-Namen zur Bestätigung eintippen. **Computername = Gerätename im Tool** (fest; ändern: Gerät umbenennen). Der Dialog zeigt, wie der Name auf dem Gerät ankommt – Windows erlaubt max. 15 Zeichen und nur A–Z, 0–9 und `-` (aus „DoNs_EliteBook_1“ wird „DoNs-EliteBook“), Linux nur Kleinbuchstaben, Ziffern und `-`. Direkt installierbar: **Windows 10/11** (x64), **Ubuntu ab 24.04**, **Debian**, **Fedora** sowie andere Systeme mit Anaconda-Installer (Rocky, Alma – DVD-ISO). Der Dialog zeigt alle ISOs; nicht direkt installierbare sind mit „nur Boot-Stick“ markiert und nennen den Grund (z. B. Nobara/Fedora Live mit Calamares bzw. Live-Installer, Zorin/Kubuntu ohne Autoinstall, 32-Bit-Windows). Das Gerät muss im **UEFI-Modus** laufen; Secure Boot darf eingeschaltet bleiben. Der **Agent-Stick bleibt stecken**: Der Agent setzt BootNext, das Gerät startet 15 s nach „vorbereitet“ einmalig von der Disk; den Stick abziehen, sobald die Installation läuft (vorher nicht – der Agent läuft vom Stick, ohne ihn klappt der Neustart nicht).

![OS installieren](windows-installieren.png)

**Windows**
1. Der Agent legt auf der Zieldisk an (GPT): EFI (FAT32) · MSR · Windows · **Setup-Partition** (FAT32, am Ende).
2. Das Tool liest die Setup-Dateien direkt aus der ISO auf dem NAS und überträgt sie verschlüsselt (SHA-256 je Datei). Eine `install.wim` über 4 GB teilt der Agent in `install.swm`-Teile.
3. Der Agent setzt per `efibootmgr` den **einmaligen** Start (BootNext) auf die Setup-Partition und startet neu.
4. Die Windows-Setup-Umgebung (von Microsoft signiert) startet über `sources\autounattend.xml` nur `okula\install.cmd`: `dism` spielt die gewählte Edition auf, `bcdboot` richtet den Start ein, `bcdedit` setzt den Windows Boot Manager an die erste Stelle der Firmware-Startreihenfolge (B-015). Der Setup-Assistent läuft nicht (keine Klicks). Bei einem Fehler öffnet sich das Protokoll `okula\install.log` (mit Laufwerksliste, siehe unten).
5. Erster Start: Windows richtet sich mit den Anpassungen ein (Konto, Region Schweiz, Computername, Windows-Schlüssel). Danach löscht `SetupComplete.cmd` die Setup-Partition und vergrössert C:.

**Windows-Partition: alte Daten löschen, Prüfung, Suche in der Setup-Umgebung (B-014, Ä-039)**

Ablauf im Agent (`wininstall.install`):
1. Nach `sfdisk`: auf **allen vier** neuen Partitionen `wipefs -a` und Anfang (16 MiB) und Ende (letztes 1 MiB, darin
   der NTFS-Backup-Bootsektor im letzten Sektor) mit Nullen überschreiben (`zero_ends`: `O_DIRECT`, danach `fsync`;
   wo `O_DIRECT` nicht geht, gepuffert mit `fsync`). Kleine Partitionen (MSR, 16 MiB) ganz. Log „Alte Daten auf den
   neuen Partitionen werden gelöscht …“. Kein Discard als Mittel.
2. Zwischenablage für eine grosse `install.wim` (`_mkstage`, ext4) jetzt mit `-E nodiscard`: kein TRIM über die ganze
   Windows-Partition (~105 GB am CompactPlayer) direkt vor dem Schreiben.
3. Bei geteilter `install.wim`: vor `mkntfs` die Windows-Partition noch einmal löschen (ext4-Superblock weg).
4. `mkntfs -Q -F -L OKULAWIN`, Markierung `okula-<id>.target` über ntfs-3g, `sync`.
5. **Prüfung** (`check_windows_partition`, Log „Windows-Partition wird geprüft …“): `sync`, `blockdev --flushbufs`,
   `drop_caches`, dann `blkid -p` (liest direkt vom Gerät): Typ `ntfs` und Bezeichnung „OKULAWIN“; danach nur lesend
   einhängen (`ntfs-3g -o ro`) und Markierung suchen. Fehlt etwas → Auftrag bricht ab mit „Schreiben auf die Disk wird
   nicht übernommen – Disk prüfen (Windows-Partition …: gefunden …)“; **kein BootNext, kein Neustart**.

`install.cmd` (Setup-Umgebung, `winsetup.install_cmd`):
- Windows-Partition = Laufwerk mit `okula-<id>.target`; sonst **genau ein** Laufwerk, dessen `vol`-Ausgabe das Wort
  „OKULAWIN“ enthält (genauer Wortvergleich, Sprache der Setup-Umgebung egal). Kein Treffer oder mehrere → Fehler. Ein
  Laufwerk mit altem Windows (Bezeichnung „Windows“ von `format /v:Windows`) wird nie auf Verdacht formatiert.
- Protokoll `okula\install.log`: Installations-ID, Setup-Partition, wie die Windows-Partition gefunden wurde
  (Markierung/Bezeichnung, Anzahl Treffer).
- **Fehlerfall (Ä-039):** zusätzlich `diskpart` → `list volume` (Skriptdatei in `%TEMP%`), je Laufwerk C–Z (ohne X:)
  „Markierung okula-*.target: ja/nein“, die gefundenen Markierungen und `dir` des Wurzelverzeichnisses (Bezeichnung,
  Ordner mit Datum, freier Platz), dann die Liste der nicht vorhandenen Laufwerke. Oben im Protokoll ein Kasten:
  „Nach dem Schliessen dieses Fensters schaltet sich das Geraet aus. Fuer eine Eingabeaufforderung vorher Shift+F10
  druecken.“ und als Ausweichweg *Datei → Öffnen*, Dateityp „Alle Dateien“, `X:\Windows\System32\cmd.exe` mit
  Rechtsklick → Öffnen. Dann Editor, danach `wpeutil shutdown`. Ob Shift+F10 in diesem Zustand (RunSynchronous im
  Durchgang windowsPE, Editor offen) eine Eingabeaufforderung öffnet, ist hier nicht prüfbar – Microsoft nennt
  Shift+F10 für die Setup-Oberfläche; daher beide Wege ([TESTS.md](TESTS.md) Abschnitt 20).

Ursache (Stand 17.11.2026, CompactPlayer 1, Kingston SH103S3 120 GB, SandForce-Controller):
- **Belegt:** In Windows PE war C: (sda3) das **alte** Volume: Bezeichnung „Windows“ (vergibt nur `install.cmd`),
  Ordner aus dem Win10-Image, keine Markierung – obwohl der Agent ohne Fehler `mkntfs` und die Markierung
  geschrieben und sauber neu gestartet hatte; die Setup-Partition (gleicher Auftrag, früher geschrieben) war neu.
  Gleiche Startsektoren wie beim Vorversuch; der 1. Versuch (Disk vorher anders aufgeteilt) lief durch.
  `sfdisk` löscht im Skriptbetrieb keine Signaturen in neuen Partitionen (`--wipe-partitions` Standard `auto` = nur
  interaktiv). `mkntfs -Q` überschreibt das Volume nicht („skip both zeroing of the volume and bad sector
  checking“) – alte Strukturen mitten in der Partition (z. B. das alte `$MFT`) bleiben liegen. `mkntfs` schreibt den
  Backup-Bootsektor in den letzten Sektor der Partition (Test `WipeTest` mit Probe-Datei).
- **Vermutet** (nicht geprüft, in dieser Reihenfolge): (1) Das Geschriebene kam nicht bzw. nicht dauerhaft auf der SSD
  an – Windows PE las den alten Bootsektor und damit das alte `$MFT`. Begünstigt durch das TRIM von `mkfs.ext4` über
  die ganze Partition kurz vorher (SandForce verarbeitet TRIM verzögert; Lesen nach TRIM ist nur mit „Deterministic
  read ZEROs after TRIM“/RZAT garantiert null). Passt zu „103 GB frei“ trotz alter Ordner: die Daten der alten
  Zuordnungstabelle (`$Bitmap`) waren überschrieben bzw. getrimmt, das alte Verzeichnis nicht. Dagegen spricht: Der
  1. Versuch lief mit demselben Ablauf (inkl. TRIM) durch – der Verlust müsste also nur zeitweise auftreten (z. B.
  abhängig vom Zustand der SSD nach dem Vorversuch). (2) Windows nahm statt
  des neuen einen alten Bootsektor (Kopie am Partitionsende) – nur möglich, wenn der neue nicht gelesen werden konnte,
  da `mkntfs` die Kopie am Ende ebenfalls neu schreibt. (3) Wiederholung des Journals (`$LogFile`) des hart
  ausgeschalteten alten Windows – unwahrscheinlich, da `mkntfs` ein neues `$LogFile` anlegt.
  Nicht erklärt: Ordner `Windows` mit Datum 17.11. 09:37.
- **Wirkung der Korrektur:** Ohne alten Bootsektor (Anfang und Ende genullt) gibt es keinen Weg mehr zum alten
  Volume; kein grosses TRIM mehr direkt davor. Kommt das Geschriebene trotzdem nicht an, meldet das die Prüfung
  im Agent (Abbruch vor dem Neustart). Sieht Windows PE trotz bestandener Prüfung etwas anderes, zeigt das Protokoll
  der Setup-Umgebung den Zustand aller Laufwerke – dann liegt es an der SSD (Firmware, Disk-Test) und nicht am Ablauf.

Quellen: mkntfs(8) (ntfs-3g, Option `-Q`), mke2fs(8) (`-E discard/nodiscard`, Discard ist Standard), sfdisk(8)
(`--wipe-partitions`), wipefs(8) (löscht nur Signaturen, nicht die Daten), hdparm(8) / ATA ACS-2 DATA SET MANAGEMENT
(DRAT/RZAT), Microsoft Learn „How NTFS Works“ (Kopie des Bootsektors am Volumeende), Microsoft Learn „Windows
Setup Command-Line Options“/„WinPE: Use a command prompt“ (Shift+F10 in der Setup-Oberfläche). Agent betroffen → neuer
Agent-Stick bzw. Netzwerkstart neu vorbereiten.

**Startreihenfolge nach der Installation (B-015)**

Befund (CompactPlayer 1, AMI-Firmware 2014, 17.11.2026): Nach `dism`/`bcdboot` und `wpeutil reboot` startete das Gerät
wieder die Setup-Partition, `install.cmd` lief ein zweites Mal. `bcdedit /enum firmware` zeigte in `{fwbootmgr}`
`displayorder` zuerst „UEFI OS“ (Setup-Partition, `\EFI\BOOT\BOOTX64.EFI`), erst danach `{bootmgr}`. Den Eintrag „UEFI OS“
legt die Firmware selbst für den Wechseldatenträger-Pfad auf einer FAT-Partition an – nicht der Agent (dessen Eintrag
„Okula Windows-Installation“ gilt nur als BootNext).

`install.cmd` setzt darum nach erfolgreichem `bcdboot` (und `mountvol Z: /d`):
`bcdedit /set {fwbootmgr} displayorder {bootmgr} /addfirst`. Ins `install.log` kommen `bcdedit /enum firmware` vorher und
nachher sowie „Windows Boot Manager an erste Stelle - Rueckgabe <Code>“. Schlägt `bcdedit` fehl, wird das nur
protokolliert („Startreihenfolge nicht gesetzt - Installation laeuft weiter“), kein Abbruch. Am CompactPlayer 1 hat
genau dieser Befehl von Hand in Windows PE geholfen. Ab dem ersten Windows-Start (SetupComplete bzw. auditUser, I-038)
ist die Setup-Partition gelöscht, der Firmware-Eintrag dann gegenstandslos.

- **Keine zusätzliche `bcdboot`-Option:** Laut Microsoft Learn („BCDBoot Command-Line Options“) legt `bcdboot` den
  Firmware-Eintrag des Windows Boot Managers ohnehin zuerst an; `/addlast` setzt ihn ans Ende, `/p` behält eine
  bestehende Position, `/d` betrifft nur den Standardeintrag im `{bootmgr}`. Eine Option, die die Reihenfolge
  zuverlässiger setzt, gibt es nicht – die Firmware hat ihren Eintrag trotzdem davorgestellt. (Stand der Doku aus dem
  Wissen des Umsetzungs-Agenten, am 17.11. nicht neu abgerufen.)
- **Einträge der Setup-Partition werden nicht entfernt** (Anforderung 3 bewusst weggelassen): Die Ausgabe von
  `bcdedit /enum firmware` ist in der Sprache der Setup-Umgebung (z. B. „Bezeichner“ statt „identifier“) und in
  mehrzeiligen Blöcken – in `cmd` nicht sicher auszuwerten. Der Agent-Stick („UEFI: USB“) nutzt denselben Pfad
  `\EFI\BOOT\BOOTX64.EFI`; ein Fehlgriff träfe den falschen Eintrag. Zudem kann die Firmware solche Einträge bei jedem
  Start neu anlegen (vermutet). Mit `{bootmgr}` an erster Stelle ist das Entfernen nicht nötig.
- Agent nicht betroffen (`install.cmd` erzeugt das Tool) – kein neuer Agent-Stick. Prüfung: [TESTS.md](TESTS.md)
  Abschnitt 20.

**Für Master-Image (Audit-Modus) (I-038):** Häkchen im Dialog *OS installieren …* (nur Windows, Standard aus;
`WinOptions.audit_mode`). Konto, Benutzername, Passwort, Windows-Schlüssel und der Computername sind ausgegraut und
werden ignoriert (`winunattend._audit_opts` – Audit hat Vorrang, auch wenn Werte gesetzt sind); keine Prüfung des
Kontonamens (B-012). Region Schweiz, Datenschutz und BitLocker-Verhinderung bleiben wählbar. `winsetup.system_unattend`
erzeugt `okula/unattend.xml` (→ `C:\Windows\Panther\unattend.xml`):
- **specialize** wie bisher (Zeitzone, BitLocker, Datenschutz – ohne `BypassNRO`, ohne `ComputerName`/`ProductKey`),
  dazu `Microsoft-Windows-International-Core` (Region): Reseal/Audit im oobeSystem ignoriert laut Microsoft alle
  anderen oobeSystem-Einstellungen, die Region steht darum in specialize.
- **auditUser** (`Microsoft-Windows-Deployment/RunSynchronous`, läuft als eingebauter Administrator beim Eintritt in den
  Audit-Modus; RunSynchronous ist laut Microsoft nur in auditUser und specialize gültig, nicht in auditSystem):
  1. `cmd /c "%WINDIR%\Setup\Scripts\SetupComplete.cmd"` – Setup-Partition löschen, C: vergrössern. Ob
     `SetupComplete.cmd` beim Start in den Audit-Modus von selbst läuft, belegt Microsoft nicht; doppelt ist harmlos
     (ohne Marker-Datei tut das Skript nichts).
  2. `del /f /q "%WINDIR%\Panther\unattend.xml"` – die Antwortdatei darf nicht ins Master-Image (implizite Suche in
     `%WINDIR%\Panther`, Microsoft: „you must delete the cached answer file in the %WINDIR%\panther directory“).
  3. Dasselbe Löschen noch einmal nach zwei Minuten, abgekoppelt (`start … ping -n 121 …`): Setup annotiert die
     zwischengespeicherte Antwortdatei nach einem Durchgang; so bleibt sie auch dann weg, wenn Setup sie am Ende von
     auditUser zurückschreibt.
- **oobeSystem** nur `Microsoft-Windows-Deployment/Reseal/Mode=Audit` (ohne `ForceShutdownNow`).

Log des Auftrags: Zusammenfassung „Startet im Audit-Modus für ein Master-Image …“ und nach dem Vorbereiten die nächsten
Schritte (`winunattend.AUDIT_NEXT_STEPS`: einrichten, Sysprep `/generalize /oobe /shutdown`, Windows nicht mehr
starten, *Disk-Image erstellen …*, als Master markieren). Verlauf: „Windows-Installation <Edition> für Master-Image
(Audit-Modus) → <Disk>: vorbereitet …“. Beim Zurückspielen des Masters legt der Agent wie bisher seine eigene
`Windows\Panther\unattend.xml` ab (`master_unattend`, unverändert, ohne Reseal). Agent unverändert – kein neuer
Agent-Stick. Quellen: Microsoft Learn „Boot Windows to Audit Mode or OOBE“, „Mode (microsoft-windows-deployment-
reseal-mode)“, „RunSynchronousCommand (microsoft-windows-deployment-…)“, „Windows Setup Automation Overview“,
„Add a Custom Script to Windows Setup“.

**Windows-Konto (B-012):** Mit „Lokales Konto statt Microsoft-Konto“ legt die `autounattend.xml` ein lokales Konto
(Gruppe `Administrators`) an; ohne Passwort meldet es sich einmal automatisch an und verlangt dann ein neues
(`net user "<Name>" /logonpasswordchg:yes`). Vorbelegt ist **„Okula“** (`WinOptions.local_account`). Der frühere
Standard „Benutzer“ ist in deutschem Windows der Name der eingebauten Gruppe Builtin\Users: Das Anlegen scheitert
(`0x80070563`, `Windows\Panther\UnattendGC\setuperr.log`), danach hängt die Einrichtung in einer Neustart-Schleife
(oobeldr `0x8030000b`/`0x8030000c`). Darum prüft `winunattend.pruefe_kontoname(name)` (Meldung oder `None`) vor dem
Start – im Dialog „OS installieren …“ (Meldung in der Prüfliste, *Installieren* gesperrt, zusätzlich beim
Bestätigen) und beim Boot-Stick (Fehlerfenster beim Start, Stick wird nicht gelöscht):
- reservierte Namen von Gruppen und eingebauten Konten, deutsch und englisch (`RESERVED_ACCOUNT_NAMES`: Benutzer,
  Administrator(en), Gast, Gäste, Jeder, Users, User, Guest(s), Everyone, System, Network, Local, Default,
  DefaultAccount, WDAGUtilityAccount, Konto, Hauptbenutzer, Remotedesktopbenutzer, Netzwerkdienst …), nach
  `strip()` und ohne Gross-/Kleinschreibung;
- mehr als 20 Zeichen, Punkt am Ende, eines der Zeichen `" / \ [ ] : ; | = , + * ? < >`.

Der Name wird nie still korrigiert. **Leer** ist erlaubt: Dann enthält die Antwortdatei kein Konto (auch kein
`BypassNRO`), Windows fragt beim ersten Start selbst nach einem Konto – die Einrichtung hält dort an (Dialog zeigt
einen Hinweis). Die Prüfung läuft nur auf dem Server (kein neuer Agent-Stick). Das Konto im Master-Ablauf
(`master_unattend`, Automatisierung) ist davon nicht betroffen (Standard dort leer).

**Windows 11 auf nicht unterstützter Hardware:** Ist das Gerät laut Inventar nicht Windows-11-tauglich (z. B. TPM 1.2, Prozessor vor 8. Generation), zeigt der Dialog den Grund und die Hinweise von Microsoft (kein Support, Updates – auch Sicherheitsupdates – nicht garantiert, Schäden nicht von der Herstellergarantie gedeckt, Wasserzeichen). „Installieren“ geht erst mit dem Häkchen **„Trotzdem installieren – nicht unterstützt“**. Nach erfolgreicher Vorbereitung steht am Gerät ein Vermerk (Gerätefenster → Übersicht → Windows 11, Verlauf, Inventar-Export). Nie in der Automatisierung. Empfehlung: lieber Gerät ersetzen, Windows 10 mit ESU oder Linux. Quelle: [Microsoft](https://support.microsoft.com/en-us/windows/installing-windows-11-on-devices-that-don-t-meet-minimum-system-requirements-0b2dc4a2-5933-4ad4-9c09-ef0a331518f1).

Neuere Intel-Laptops mit **VMD/RST** zeigen die Disk in der Setup-Umgebung evtl. nicht – dann im BIOS auf AHCI stellen oder den Boot-Stick verwenden.

![Linux installieren](linux-installieren.png)

**Ubuntu Desktop (ab 24.04)**
- EFI-Partition mit den signierten Bootdateien der ISO (shim/grub), die ISO als Datei auf einer Setup-Partition am Disk-Ende, Antworten für den Installer auf einer kleinen Partition `CIDATA`.
- GRUB startet die ISO per Loopback, der offizielle Installer läuft per **Autoinstall** in den freien Platz (`use_gap`): Benutzer, Passwort, Computername, Tastatur Schweiz, Zeitzone Zürich, optional SSH-Server.
- Beim ersten Start entfernt der Dienst `okula-cleanup` die Setup-Partitionen und vergrössert die Systempartition.

**Debian**
- EFI-Partition mit den Bootdateien der ISO und dem **Debian-Netzwerk-Installer** (Kernel/initrd lädt der Server einmal von deb.debian.org, geprüft gegen `SHA256SUMS`, Zwischenspeicher `~/.cache/okula-recovery/netboot`).
- **Preseed** (im zweiten initrd): Partitionierung im freien Platz, Benutzer, Passwort, Computername, Region Schweiz. **Das Gerät braucht Internet**, die Pakete kommen von deb.debian.org.
- **Softwareauswahl wie im Debian-Installer:** Desktop (keiner/Server, GNOME, KDE Plasma, Xfce, Cinnamon, MATE, LXDE, LXQt), Standard-Systemwerkzeuge, SSH-Server, Webserver (Apache). Optional ein **Root-Passwort** (sonst kein Root-Konto, der Benutzer arbeitet mit sudo; mit Root-Konto bleibt er trotzdem in sudo).

**Fedora / Anaconda** (Fedora Everything/Server, Rocky, Alma …)
- Kernel/initrd der ISO auf der EFI-Partition, die ISO als Datei auf einer Setup-Partition am Disk-Ende (`inst.repo`/`inst.stage2=hd:LABEL=OKULASETUP:/fedora.iso`), Kickstart (`inst.ks`).
- Kickstart: Benutzer (Administrator), Passwort, Computername, Region Schweiz, `autopart` im freien Platz, wahlweise Desktop (Workstation/GNOME), optional SSH-Server (sshd aktiv, Firewall offen für SSH).
- DVD-ISO ohne Desktop installiert offline von der ISO; Fedora-Netzwerk-ISO oder Desktop laden die Pakete aus dem Internet.
- Beim ersten Start entfernt `okula-cleanup` die Setup-Partition und vergrössert das System (ext4, btrfs, xfs).

**Zusätzliche Pakete** (alle Linux): im Dialog durch Leerzeichen getrennt, z. B. `htop curl vim`. Der Installer holt sie am Schluss aus dem Internet; unbekannte Namen werden übersprungen, damit ein Tippfehler die automatische Installation nicht anhält (Fedora: `%packages --ignoremissing`).

An der Maschine wird während der Installation nichts gefragt – alles, was nicht im Dialog gewählt ist, wird nicht installiert.

Im Tool ist der Auftrag fertig, sobald das Gerät neu startet; den Rest erledigt der Installer am Gerät. Der Verlauf des Geräts vermerkt die Installation.

### Windows-Schlüssel

- **OEM-Schlüssel aus dem BIOS:** Der Agent liest ihn beim Erfassen aus (ACPI-Tabelle `MSDM`, bei den meisten Geräten ab Windows 8). Nach dem Update den Agent-Stick neu erstellen und *Inventar neu einlesen*.
- **Von Hand:** Gerätefenster → *Übersicht* → *Windows-Schlüssel* → „Hinterlegen …“ (Retail/Volumen; hat Vorrang vor dem OEM-Schlüssel). Angezeigt wird er maskiert, „Anzeigen“ und „Kopieren“ auf Wunsch. Gespeichert lokal auf dem Server bei den Gerätedaten.
- **Bei der Installation** setzt das Tool den Schlüssel ein; Windows aktiviert sich, sobald Internet da ist. Vorgewählt wird die Edition, die zuletzt auf dem Gerät lief – bei einer anderen Edition warnt der Dialog (z. B. Home-Schlüssel und Pro).
- Geräte mit **digitaler Lizenz** (z. B. Gratis-Upgrade auf 10/11) brauchen keinen Schlüssel: die gleiche Edition aktiviert sich nach der Neuinstallation von selbst.

## Datei-Backup

Im Gerätefenster **„Backup erstellen …“** (auch Rechtsklick auf das Gerät oder Tools-Menü). Partitionen werden nur **lesend** eingehängt – am Gerät ändert sich nichts.

**Was sichern** (Reiter im Dialog):
- **Benutzerdaten:** Benutzer pro Windows-/Linux-Partition anhaken. Windows-Kategorien wählbar: Desktop, Dokumente, Bilder, Musik, Videos, Downloads, Favoriten/Links, OneDrive (lokale Kopie), Outlook-PST, Browser-Lesezeichen (Chrome, Edge, Firefox). Linux: ganzer persönlicher Ordner.
- **Ganze Partitionen:** alle Dateien einer Partition.
- **Eigene Ordner:** Dateibaum des Geräts (lädt beim Aufklappen), Ordner/Dateien anhaken.

Immer übersprungen: Auslagerungs-/Ruhezustandsdatei, Papierkorb, *System Volume Information*, Temp-Ordner, Browser-/Programm-Caches, Office-Sperrdateien. BitLocker-Partitionen nur mit Wiederherstellungsschlüssel, nur lesend (Abschnitt [BitLocker entsperren](#bitlocker-entsperren-i-012)). **„Grösse berechnen“** zählt vorher Dateien und Grösse und vergleicht mit dem freien NAS-Platz.

**Ablage** auf dem NAS unter `Backups/<Gerät>/<Datum_Zeit>/`:
- **Normale Dateien** (`Dateien/<Partition>/…`) – im Reiter *Dateien* durchsuchbar, einzelne Dateien direkt herausholbar.
- **Archiv** `backup.tar.zst` – kompakt, schneller bei vielen kleinen Dateien.
Dazu `okula-backup.json` (Gerät, Auswahl, übersprungene Dateien mit Grund) und `dateien.tsv` (SHA-256, Grösse, Zeit je Datei). Jede Datei wird bei der Übertragung per SHA-256 geprüft; nicht lesbare Dateien (z. B. defekte Sektoren) werden vermerkt, das Backup läuft weiter.

**Übersicht aller Backups:** rechts Reiter **Backups** (neben *Images* und *Dateien*) – nach Gerät gruppiert, mit Notiz, Inhalt und Grösse, Suche nach Gerät oder Notiz.

**Zurückspielen / herunterladen** (Reiter *Backups* im Gerätefenster oder rechts; Doppelklick oder Rechtsklick):
- Auswahl, was zurück soll (pro Benutzerordner bzw. Partition).
- **Ins installierte System:** Zielpartition wählen, Benutzer zuordnen (z. B. alter Benutzer „Anna“ → neuer Benutzer „Neu“ nach einer Neuinstallation), sonst nach `Okula-Wiederherstellung/…`. Vorhandene Dateien bleiben, die zurückgespielte Datei kommt mit Zusatz „(wiederhergestellt)“ – ausser „überschreiben“ ist gewählt. Windows muss **vollständig heruntergefahren** sein (Shift-Taste gedrückt halten + „Herunterfahren“, ohne Schnellstart); Linux: Besitzer wird der zugeordnete Benutzer.
- **Herunterladen in einen Ordner** auf dem Server oder einem eingesteckten Laufwerk (auch aus dem Archiv).

**Notiz und Löschen:** Beim Erstellen optional eine Notiz eingeben (z. B. „vor Neuinstallation“, Ticketnummer); später ändern über **„Notiz …“** (Reiter *Backups* im Gerätefenster oder rechts, auch per Rechtsklick). Die Notiz steht in `okula-backup.json` auf dem NAS und erscheint in der Liste. **„Löschen …“** entfernt das Backup nach Rückfrage endgültig vom NAS; solange es zurückgespielt oder heruntergeladen wird, ist Löschen gesperrt.

### BitLocker entsperren (I-012)

Mit dem **Wiederherstellungsschlüssel** (48 Ziffern, 8 Blöcke à 6) öffnet der Agent eine BitLocker-Partition **nur
lesend** – für Datei-Backups (Benutzerdaten, ganze Partitionen, eigene Ordner, Durchsuchen, Grösse berechnen).
Entscheide Dominik 25.11.2026 ([AENDERUNGEN.md](AENDERUNGEN.md) „📌 Entscheidungen“): kein Disk-Image aus belegten
Blöcken (bleibt Rohkopie, sonst lägen Kundendaten unverschlüsselt auf dem NAS – erst mit Ä-003), nie schreiben, kein
Benutzerpasswort.

**Ablauf am Agent** (`filebackup.Mounts`): Die Anfragen `profiles`, `browse`, `estimate` und `backup` tragen optional
`bitlocker: {"<partition>": "<schlüssel>"}`. Für eine Partition mit Dateisystem `BitLocker` und Schlüssel:
1. Format prüfen (`filebackup.recovery_key`), sonst „… ungültig – 48 Ziffern …“; fehlt `dislocker` → „Agent-Stick zu
   alt für BitLocker – neuen Stick erstellen“.
2. `dislocker -r -V <dev> -p<schlüssel> -- <WORK>/<name>-bitlocker-…` (FUSE, **`-r` = nur lesend**). Fehler mit
   „decryption mean“/VMK/Passwort → „Wiederherstellungsschlüssel passt nicht zu <Partition>“, sonst die letzte Zeile
   von dislocker – immer ohne Schlüssel (`filebackup.scrub`, entfernt auch jeden 48-Ziffern-Block).
3. `<fuse>/dislocker-file` mit den Schreibschutz-Optionen plus `loop` einhängen (`inventory._mount_ro(…, loop=True)`,
   NTFS: `ntfs3`/`ntfs-3g` `ro,loop`).
4. Aufräumen in umgekehrter Reihenfolge, auch bei Fehlern: `umount` des Dateisystems, dann `fusermount3 -u`
   (Rückfall `fusermount -u`, `umount`) und Ordner löschen.
`profiles` meldet BitLocker-Partitionen mit `bitlocker: true`; ohne Schlüssel `error: "BitLocker – nicht lesbar"`, mit
passendem Schlüssel Benutzer wie bei NTFS und `unlocked: true`. Schreibende Wege bleiben gesperrt:
`Mounts(write=True)` → „… nicht beschreibbar“ auch mit Schlüssel, `deploy._candidates` unverändert. Fehlermeldungen
und Agent-Log (`run_job`) werden vom Schlüssel gesäubert; die Anfrage selbst wird nie geloggt.

**Speicher im Tool** (`bitlocker_keys.py`): Standard = Schlüssel beim Auftrag eingeben; mit Häkchen „Für dieses Gerät
speichern“ (nur wenn er passt) pro Gerät unter `/etc/okula-recovery/bitlocker/<Geräte-ID>.json` (Ordner 0700, Datei
0600, root) als `{"keys": {"/dev/nvme0n1p3": "…"}}`. Geschrieben atomar (temporäre Datei 0600 mit `O_EXCL`, `fsync`,
`os.replace`, Ordner-`fsync`); gelesen nur, wenn Ordner und Datei root gehören und für niemanden sonst zugänglich sind
(sonst Fehler „Rechte … falsch“). Das Tool läuft als Benutzer und fragt den Root-Helfer `/usr/local/sbin/okula-bitlocker`
per `sudo -n` (`has`, `get`, `set --stdin`, `delete`; Schlüssel nur über stdin, Antwort „OK …“/„ERROR …“) – eingerichtet
von `install.sh` (sudoers wie bei `okula-warranty`). Prüfung beim Eingeben: 48 Ziffern, jeder 6er-Block durch 11
teilbar und kleiner als 11 · 65536 = 720896 (Block = 11 × 16-Bit-Wert, letzte Ziffer = Prüfziffer; Quelle:
dislocker `src/accesses/rp/recovery_password.c`, `valid_block` – am realen System bestätigen). Ist nur ein Schlüssel
gespeichert, gilt er auch für eine anders benannte Partition (`for_partitions`, z. B. andere Disk-Reihenfolge).
**Nie** in Geräte-JSON, Inventar, Inventar-Export, Einstellungs-Export/-Übertragung, Logs oder Verlauf (Verlauf nur
„BitLocker-Schlüssel für <Partition> hinterlegt/entfernt“). Hinweis: Wer das Tool-Konto bedient, kann über den
Helfer die Schlüssel lesen – das Tool braucht sie im Klartext für die Anfrage an den Agent.

**Oberfläche:** *Backup erstellen …* zeigt bei gesperrter BitLocker-Partition den Rahmen *BitLocker* (Partition,
Feld *Wiederherstellungsschlüssel* verdeckt mit *Anzeigen*, Häkchen *Für dieses Gerät speichern*, Knopf
*Entsperren*); ein gespeicherter Schlüssel wird beim Öffnen von selbst verwendet, danach werden die Profile neu
abgefragt. Gerätefenster → *Übersicht*: Zeile *BitLocker-Schlüssel hinterlegt* (ja/nein, Stand vom Root-Helfer im
Hintergrund) mit *Schlüssel hinterlegen …* und *Entfernen* – nur sichtbar, wenn das Inventar eine BitLocker-Partition
zeigt (Dateisystem oder System „verschlüsselt (BitLocker)“) oder ein Schlüssel hinterlegt ist. Gerät bzw. VM löschen
löscht die Schlüssel mit (`MainWindow.forget_bitlocker`). Nicht übernommen beim Zusammenführen von Geräten.

**Automatisierung:** Backup „Benutzerdaten“ fragt die Profile, holt bei gesperrter BitLocker-Partition den
gespeicherten Schlüssel, fragt erneut mit Schlüssel und sichert dann wie gewohnt (`run_backup(…, bitlocker=…)`).
Ohne Schlüssel bzw. mit falschem Schlüssel Abbruch wie B-025, nichts gelöscht.

**Agent-Stick / Netzwerkstart:** `dislocker` und `fuse3` in `stick.BUNDLED_PACKAGES` (Abhängigkeiten
`libdislocker0.7t64`, `libfuse3-4`, `libruby3.3` kommen über `apt-cache depends` mit) – **neuer Agent-Stick bzw.
Netzwerkstart neu vorbereiten nötig**.

## Ordner an Geräte senden

Vordefinierte Ordner vom NAS per Mausklick auf den **Desktop für alle Benutzer** (`C:\Users\Public\Desktop`) eines Geräts legen.

```
NAS/Verteilen/Software/            fix – wird als ganzer Ordner gesendet
NAS/Verteilen/Test Files/          fix – wird als ganzer Ordner gesendet
NAS/Verteilen/Content/<Projekt>/   Auswahl – gewählte Projekte landen unter Content\<Projekt>
```

- Die Ordner legt das Tool beim Verbinden mit dem NAS an; die Inhalte lassen sich im Reiter **Dateien** pflegen (Drag & Drop).
- `Verteilen/Software` ist ein Werkzeug-Ordner für Geräte unterwegs; *Software installieren* nutzt seit Ä-041 die
  eigene Software-Bibliothek (`NAS/Software-Bibliothek/`, Abschnitt „Software installieren“).
- **Senden:** Rechtsklick auf das Gerät → **Ordner senden ▸ Software / Test Files / Content …**, oder im Gerätefenster bzw. Tools → „Ordner senden …“ (Auswahl mit Häkchen, auch mehrere Projekte).
- **Erneut senden ersetzt** den Ordner auf dem Desktop. Der Agent schreibt zuerst in einen versteckten Zwischenordner und tauscht erst um, wenn alles angekommen ist – bei einem Abbruch bleibt der alte Stand. Andere Projekte unter `Content\` bleiben.
- **Voraussetzungen:** Gerät läuft mit dem Agent (Stick oder Netzwerkstart), Windows vollständig heruntergefahren (kein Schnellstart/Ruhezustand), keine BitLocker-Verschlüsselung. Links auf dem NAS werden nicht mitgesendet.

## Windows anpassen (I-039)

Einstellungen an einem Gerät mit Windows per Häkchen umstellen; Windows setzt sie beim **nächsten Start selbst** um
(als SYSTEM, vor der Anmeldung). Bedienung wie *Ordner senden*: Rechtsklick auf das Gerät, *Tools* oder Knopf im
Gerätefenster → **„Windows anpassen …“** → Vorlage/Häkchen → *Senden*. Module: `wintweaks.py` (Optionen, Vorlagen,
Skript – ohne GTK), `automation_tab.WindowsTweakDialog`, `jobs.tweak_work`, `agentclient.tweak`, Agent-Befehl `tweak`
in `deploy.tweak`/`deploy.install_startup_script`; Demo-Agent nimmt den Befehl an und meldet „fertig“.

**Ablauf:** Das Tool prüft wie bei *Ordner senden*, ob laut Inventar ein Windows (ohne BitLocker) da ist, sonst Meldung
und nichts gesendet. Es erzeugt das PowerShell-Skript (`wintweaks.build_script`) und schickt es verschlüsselt an den
Agent (Befehl `tweak`, älterer Agent → „Agent zu alt …“). Der Agent hängt die NTFS-Partitionen schreibend ein
(ntfs-3g; Ruhezustand/Schnellstart → „Windows ist im Ruhezustand bzw. Schnellstart …“), sucht genau ein Windows
(keins → „Kein Windows auf … gefunden – nichts geändert“, mehrere → nicht eindeutig) und legt das Startskript ab.
Auftrag in der Auftragsliste, Log mit den gewählten Optionen, Verlauf „Windows anpassen (Vorlage Player (geändert):
Apps (12), …, automatische Anmeldung (Okula)): Startskript abgelegt, wird beim nächsten Windows-Start umgesetzt“.

**Startmechanismus: Startskript der lokalen Gruppenrichtlinie.** Begründung: dokumentierter Weg, ein Skript beim
Start **als SYSTEM vor der Anmeldung** laufen zu lassen, auf Windows 10 Pro und 11 Pro gleich; zur Laufzeit sind alle
Dienste da (AppX-Bereitstellung für `Remove-AppxPackage`, Dienststeuerung, powercfg); offline nur mit Dateien
einzurichten (kein Hive-Schreiben nötig; seit B-020 schreibt der Agent zusätzlich Startmenü- und Widgets-Richtlinie
offline in den Hive, siehe „Vor der ersten Anmeldung: offline beim Senden“). Verworfen: `RunOnce` (läuft erst bei einer Anmeldung), Dienst im
SYSTEM-Hive (`cmd`/PowerShell ist kein Dienst – die Dienststeuerung bricht nach 30 s ab), geplante Aufgabe offline
(binäre, nicht dokumentierte Einträge unter `TaskCache`), `SetupComplete.cmd` (nur nach einer Windows-Installation),
`HKLM\SYSTEM\Setup\CmdLine` (nicht dokumentiert, läuft vor den Diensten).

Ablage durch den Agent (alles unter `Windows\System32\GroupPolicy`, Gross/Klein wie vorhanden):

| Datei | Inhalt |
|---|---|
| `Machine\Scripts\Startup\okula-windows-anpassen.ps1` | Skript vom Tool (UTF-8 mit BOM, CRLF – Windows PowerShell 5.1) |
| `Machine\Scripts\Startup\okula-windows-anpassen.cmd` | ruft `powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File …` auf; nur ASCII |
| `Machine\Scripts\scripts.ini` | `[Startup]` um `NCmdLine=okula-windows-anpassen.cmd` ergänzt (nächste freie Nummer, andere Skripte bleiben; Kodierung wie vorhanden, neu UTF-16 wie gpedit) |
| `gpt.ini` | `gPCMachineExtensionNames` um `[{42B5FAAE-6536-11D2-AE5A-0000F87571E3}{40B6664F-4972-11D1-A7CA-0000F87571E3}]` (Scripts) ergänzt, nach GUID sortiert; `Version` Computer-Teil (untere 16 Bit) +1, damit Windows die Richtlinie neu verarbeitet; neu: `gPCFunctionalityVersion=2` |
| `gpt.ini.okula-nachher`, `Machine\Scripts\scripts.ini.okula-nachher` | Stand nach dem Lauf: Original (gpt.ini mit Version +2); fehlt die Datei, gab es das Original nicht |

Erneut senden vor dem Start (Eintrag in `scripts.ini` und Scripts-Erweiterung in `gpt.ini` vorhanden) ersetzt nur das
Skript; Originale und Version bleiben. Links (Symlinks) im Pfad werden abgelehnt.

**Bestehende Einstellungen bleiben:** Eine vorhandene lokale Gruppenrichtlinie (Registry.pol, eigene Start-/
Herunterfahrskripte, Benutzerteil) wird nur ergänzt. Das Skript legt beim Start als Erstes die `*.okula-nachher`-
Dateien zurück bzw. löscht `gpt.ini`/`scripts.ini`, wenn es sie vorher nicht gab, entfernt leere Ordner des
Startskripts und seine Einträge unter `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Group Policy\Scripts\Startup`
und `…\State\Machine\Scripts\Startup`. Die erhöhte Version sorgt dafür, dass Windows die Richtlinie beim nächsten Start
wieder im Originalzustand verarbeitet.

**Genau einmal, keine Schleife:** Erste Anweisung des Skripts: `.ps1` und `.cmd` löschen (PowerShell hat das Skript da
schon ganz gelesen), dann der Rückbau – erst danach die Einstellungen. Startet PowerShell das Skript nicht (z. B.
Ausführungsrichtlinie per Domänen-Richtlinie erzwungen, Syntaxfehler), läuft der Rest der `.cmd`: Skript löschen,
„FEHLER PowerShell-Skript nicht gestartet“ ins Protokoll, `gpt.ini`/`scripts.ini` zurücklegen, sich selbst löschen.

**Windows wartet nicht auf Startskripte (Befund B-020, 24.11.2026).** Gesamttest an VM-Win11-clean ab „frisch“ mit
B-019 und neuem Agent: `SyncForegroundPolicy` = 1 war offline gesetzt (geprüft, sauberer Hive, hivexsh-Weg
funktioniert), die Gruppenrichtlinie war um 10:31:59 vor der Anmeldung fertig (Ereignis 8000), die Anmeldung kam um
10:32:01 – das Okula-Skript startete trotzdem erst um 10:32:06. **Windows wartet bei der Anmeldung nicht auf
Startskripte; auf `SyncForegroundPolicy` ist kein Verlass.** Darum (B-020) setzt der Agent die Richtlinie nicht mehr;
was vor der ersten Anmeldung wirken muss, schreibt er offline beim Senden (siehe „Vor der ersten Anmeldung: offline
beim Senden“). Zweiter Befund: `okula-windows-anpassen` und `okula-software` starteten beide um 10:32:06–08 und
räumten **gleichzeitig** auf (falscher FEHLER „… `Startup\0\0` nicht vorhanden“ im Software-Protokoll) – darum das
Aufräumen unter einer Sperre (siehe „Gleichzeitige Okula-Startskripte“).

*Vorgeschichte – Anmeldung wartet auf das Startskript (B-019, zurückgebaut mit B-020).* Befund 24.11.2026 (VM-Win11-clean, Windows 11 Pro 25H2): Ereignis 5016
„Scripts-Erweiterung abgeschlossen in 140 ms“ und die interaktive Anmeldung (4624, Typ 2) um 09:25:28, das Okula-Skript
begann erst um 09:25:43 – die Startskripte liefen **asynchron**, parallel zur Anmeldung. Folgen: Die laufende Shell
schrieb `start2.bin` mit dem alten Layout neu (Startmenü-Richtlinie ohne Wirkung), das Wetter blieb (Richtlinie und Paket
erst nach dem Start von Explorer), die Nachlauf-Aufgabe (Auslöser *Bei Anmeldung*) entstand nach der Anmeldung und lief
nie. Ursache laut Microsoft Learn (Policy CSP *ADMX_Logon/SyncForegroundPolicy* bzw. Logon.admx „Always wait for the
network at computer startup and logon“, deutsch „Beim Neustart des Computers und bei der Anmeldung immer auf das
Netzwerk warten“): Auf Clients verarbeitet Windows die Gruppenrichtlinie beim Start standardmässig **nicht synchron**
(„Schnelle Anmeldung“); mit der Richtlinie wartet der Computer beim Start auf das Netzwerk und verarbeitet die
Richtlinie im Vordergrund – die Anmeldung erscheint erst, wenn die Startskripte fertig sind. Grenze: *Maximale Wartezeit
für Gruppenrichtlinienskripts* (`MaxGPOScriptWait`, Standard 600 s) gilt für **alle** Skripte zusammen, danach bricht
Windows sie ab. Quellen aus dem Gedächtnis, im Auftrag nicht abgerufen (kein Internet); die Wirkung prüft
[TESTS.md](TESTS.md) Abschnitt 26 „Korrektur B-019“ (5016 vor 4624).

B-019 setzte darum die Richtlinie offline und stellte sie im letzten Startskript wieder her; der Gesamttest B-020 zeigte,
dass sie nicht wirkt (oben).

- **Altlast SyncForegroundPolicy (seit B-020):** Der Agent setzt den Wert nicht mehr (`deploy.tweak`/`software` ohne
  Hive-Schreiben dafür). Liegt von einem Agent mit B-019 noch `GroupPolicy\SyncForegroundPolicy.okula-nachher`
  (`fehlt` bzw. `dword:<Zahl>`), stellt das letzte Okula-Startskript den Stand her (`dword:<n>` → Wert zurück,
  `fehlt` → Wert entfernen), Protokoll „SyncForegroundPolicy entfernt wie vorher“; Notfall im `.cmd` (PowerShell nicht
  gestartet): `set /p`, `reg add … /t REG_DWORD` bzw. `reg delete`. Ist die Sicherung beim Fehler schon weg (anderes
  Skript war schneller), ist das kein Fehler; FEHLER nur, wenn sie danach noch liegt.
- **Registrierung offline schreiben (`deploy.set_hive_values`, aus B-019 verallgemeinert):** `{Schlüssel: [(Name, Typ,
  Daten)]}` im Hive `Windows\System32\config\<Hive>` (Standard `SOFTWARE`). Ablauf: Hive mit dem eigenen Leser
  (`winprofile.Hive`) lesen; sind alle Werte schon so → nichts schreiben; Kopf nicht sauber (primäre ≠ sekundäre
  Sequenznummer, Änderungen stehen noch in `.LOG1/.LOG2`) → nicht schreiben; Kopie `<Hive>.okula-tmp` neben dem Original,
  **ein** `hivexsh -w`-Lauf (libhivex-bin, auf dem Agent-Stick): je Schlüssel `cd \…`, `add`/`cd` für fehlende Teile
  (von einem früheren Block im selben Lauf angelegte Teile nicht nochmals), **ein** `setval` mit allen Werten, am Schluss
  ein `commit`; Kopie prüfen (neue Werte da, alle übrigen Werte der Schlüssel und die Stichprobe `CurrentBuild` gleich,
  Kopf sauber); erst dann in dieselbe Datei zurückschreiben (Rechte bleiben), Inhalt vergleichen, bei einem Fehler das
  Original zurückschreiben. Da `setval` **alle** Werte des Schlüssels ersetzt, werden die übrigen unverändert als
  `hex:<Typ>:<Bytes>` mitgeschrieben; Namen ausserhalb von druckbarem ASCII oder ein fehlendes `hivexsh` → nicht
  schreiben (`HiveError`, Hive unverändert). Ein vorhandener Wert gleichen Namens wird ersetzt (auch anderer Typ, z. B.
  der REG_SZ aus Ä-042).
- **Dauer:** *Windows anpassen* braucht heute ~90 s (Gesamtlauf 24.11.); `MaxGPOScriptWait` (Standard 600 s) gilt für
  alle Startskripte zusammen. *Software installieren* wartet höchstens 540 s auf die geplante Aufgabe (I-020); steht
  danach noch ein anderes Okula-Startskript aus, höchstens `software.SHARED_WAIT` = 180 s. Die Aufgabe installiert
  danach weiter.
- **Nachlauf bei schon angemeldetem Benutzer (B-019, bleibt):** Läuft das Skript nach einer Anmeldung, bekommt die
  Nachlauf-Aufgabe zusätzlich einen einmaligen Auslöser „jetzt + 30 min“ (mit `EndBoundary`, nötig für
  `DeleteExpiredTaskAfter`); erkannt an laufenden `explorer.exe`-Prozessen (`Win32_Process`, auch Remote-Sitzungen).
- **Direktinstallation** (`software.setup_files`, Startskript von der Setup-Partition): der Agent schreibt dort keinen
  Hive (Windows entsteht erst beim Setup); dort ruft zusätzlich `SetupComplete.cmd` auf (Ä-046 offen).

**Vor der ersten Anmeldung: offline beim Senden (B-020).** `wintweaks.offline_request(selected)` schickt mit dem
Skript nur für die gewählten Optionen `{"start_pins": <JSON>}` (*Startmenü: Werbe-Kacheln entfernen*) bzw.
`{"widgets": true}` (*Widgets*). Der Agent (`deploy.tweak_offline`, nach `install_startup_script`, Windows aus) liest
`CurrentBuild` aus dem Hive `SOFTWARE` und schreibt:

| Option | offline |
|---|---|
| Startmenü, ab Build 26100 | `%ProgramData%\Okula\StartPins.json` (Inhalt wie im Skript, UTF-8 ohne BOM); `Policies\Microsoft\Windows\Explorer`: `ConfigureStartPins` = 1 (DWORD), `ConfigureStartPinsJSON` = `%ProgramData%\Okula\StartPins.json` (REG_EXPAND_SZ); danach in **allen** Profilen `Users\*\` + `START_LAYOUT_DIR` die Dateien `start2.bin`/`start.bin` → `<Name>.okula-<JJJJMMTT-hhmmss>` (Verknüpfungen wie „All Users“ übersprungen); Marke `%ProgramData%\Okula\start-offline.ok` (`stamp=…`, `profiles=N`) |
| Startmenü vor Build 26100 | nichts (MDM-Bridge nur zur Laufzeit), Antwort `start: old` |
| Widgets | `Policies\Microsoft\Dsh\AllowNewsAndInterests` = 0 (DWORD) |

Beide Schlüssel in einem hivexsh-Lauf (`set_hive_values`). Umbenannt und markiert wird nur, wenn die Werte gesetzt sind
(bzw. schon so waren) – sonst würde die erste Anmeldung ohne Richtlinie eine neue `start2.bin` anlegen. Eine alte Marke
wird bei jedem *Windows anpassen* zuerst gelöscht. Fehler (Hive unsauber, `CurrentBuild` nicht lesbar, hivexsh …) →
Antwort `offline_error`, Hive unverändert, nichts umbenannt, keine Marke; Log des Auftrags „Hinweis: Einstellungen
vor dem Windows-Start nicht gesetzt (…)“ (`jobs.offline_lines`, Text seit B-021). Liess sich eine Datei nicht umbenennen: Hinweis, keine
Marke (das Startskript versucht es nochmals). Ein Agent vor B-020 ignoriert den Auftrag → „Hinweis: Agent zu alt …“.
Das Startskript setzt Richtlinien und JSON **trotzdem** wie bisher (doppelt schadet nicht, wirkt, falls offline nicht
ging). Mit Marke überspringt es nur das Umbenennen – und damit auch das Nachholen im Nachlauf (`-StartSids`); die Marke
wird gelesen und gelöscht, Protokoll „… Startmenü schon beim Senden vor dem Windows-Start zurückgesetzt (Agent: …
N Profil(e) …)“. Ohne Marke wie B-018/B-019.

**Rest vor der ersten Anmeldung (B-021, 24.11.2026).** Befund Gesamttest B-020 (VM-Win11-clean, Windows 11 Pro Build
26200): Sperrbildschirm beim ersten Start noch da, im Startmenü zusätzlich WhatsApp, Adobe Express, LinkedIn, Zeitstempel
des Agents 1 h vor. Zusätzlich zur Tabelle oben schreibt der Agent im selben hivexsh-Lauf:

| Option | offline (Hive `SOFTWARE`) | Wirkung laut Microsoft Learn |
|---|---|---|
| *Sperrbildschirm aus* (`lock_screen_off`) | `Policies\Microsoft\Windows\Personalization\NoLockScreen` = 1 (DWORD) | Policy CSP `ADMX_ControlPanelDisplay/CPL_Personalization_NoLockScreen` („Do not display the lock screen“, ControlPanelDisplay.admx): Pro, Enterprise, Education, IoT Enterprise ab Windows 11 21H2 bzw. Windows 10 2004/20H2/21H1 mit KB5005101 – Home nicht aufgeführt |
| *Wiederinstallation von Werbe-Apps sperren* (`consumer_off`) | `Policies\Microsoft\Windows\CloudContent\DisableWindowsConsumerFeatures` = 1 (DWORD) | Policy CSP `Experience/AllowWindowsConsumerFeatures` („Turn off Microsoft consumer experiences“: Start suggestions, Post-OOBE app install and redirect tiles): **nur Enterprise, Education, IoT Enterprise** – nicht Pro |

Die Antwort nennt zusätzlich `edition` (`EditionID` aus `Microsoft\Windows NT\CurrentVersion`, `deploy.windows_edition`,
nur ASCII-Buchstaben/Ziffern). `jobs.offline_lines` meldet damit ehrlich: Sperrbildschirm bei Home (`Core*`) „laut
Microsoft nicht unterstützt, wirkt evtl. nicht“; Benutzererfahrungen bei allem ausser Enterprise/Education „wirkt bei
Windows <Edition> nicht“ samt Hinweis zu den Platzhaltern; bei *Startmenü* ohne Enterprise/Education eigener Hinweis.
Fehlt in der Antwort eines Agents von B-020 ein angeforderter Wert → „Hinweis: Agent zu alt für Sperrbildschirm bzw.
Werbe-Richtlinie …“. Das Startskript setzt beide Werte weiterhin selbst; die Startmenü-Zeile im Protokoll endet bei
Pro/Home mit dem Hinweis zu den Platzhaltern (`$adsNote`), *Sperrbildschirm aus* nennt die Edition.

*Werbe-Platzhalter (WhatsApp, Adobe Express, LinkedIn):* Microsoft Learn „Customize the Windows 11 Start menu“
(OEM): „The items in this section are a combination of Microsoft-defined apps, dynamically delivered apps, and
OEM-configured items.“ Die Richtlinie `ConfigureStartPins` ersetzt laut „Customize the Start layout“ die Liste, nennt
die nachgelieferten Apps aber nicht. Abschalten lassen sie sich laut Policy CSP nur über
`AllowWindowsConsumerFeatures` („redirect tiles“) bzw. `Experience/DisableCloudOptimizedContent` – beide **nicht für
Pro**. Für Pro/Home gibt es keinen belegten Weg (auch nicht über das Standardprofil `Users\Default\NTUSER.DAT`); die
Werte unter `ContentDeliveryManager` (*Tipps*, *Wiederinstallation sperren*) sind bei Microsoft nicht dokumentiert und
werden nicht als Lösung genannt. Darum ehrlicher Hinweis (Tooltip, Protokoll, Log, Hilfe): von Hand „Von Start lösen“;
mit `applyOnce: true` überschreibt die Richtlinie das danach nicht.

*Weitere Werte geprüft (nur Maschinen-Werte im Hive `SOFTWARE`):* offline umgesetzt nur, was beim ersten Start bzw. bei
der ersten Anmeldung schon wirken muss und ohne Seiteneffekt geschrieben werden kann (oben). Bewusst nicht offline:
Cortana, Bing-Suche (wirken erst bei der Benutzung, Bing zusätzlich Benutzerwerte), Telemetrie, Werbe-ID, Standort,
Fehlerberichte (kein Bezug zur ersten Anmeldung; Telemetrie braucht zusätzlich den Dienst), Windows Update, Treiber,
App-Updates (Skript läuft beim Start ohnehin vor den meisten Downloads – nicht belegt, dass offline nötig wäre),
OneDrive `DisableFileSyncNGSC` (Einrichtung je Benutzer über den Run-Eintrag im Benutzer-Hive; Wirkung der
Richtlinie auf die Ersteinrichtung nicht belegt), automatische Anmeldung (Winlogon liegt zwar in `SOFTWARE`, aber
Passwort offline im Klartext und keine Kontoprüfung ohne SAM), Copilot (Richtlinie nur Benutzer), Schnellstart (Hive
`SYSTEM`), Tipps/Explorer/Taskleiste/Einrastfunktion (Benutzer-Hives).

**Uhr des Agents (B-021).** Ursache: Windows führt die Hardware-Uhr (RTC) in Ortszeit; der Kernel des Live-Systems
liest sie beim Start als UTC, die Zeitzone `Europe/Zurich` (Startparameter `timezone=`, live-config) rechnet dann
nochmals +1 h (Winter) bzw. +2 h (Sommer) dazu – daher `start2.bin.okula-…` 17:02 statt 16:02, Windows-Dateizeiten
stimmen. Einen Zeitserver nutzt der Agent nicht. Lösung ohne Annahme über die RTC (Geräte mit Linux führen sie in UTC):
Jede Anfrage des Tools (JSON mit `cmd`) trägt `now` = Uhrzeit des Servers in Sekunden UTC (`wire.send_json`, nur auf
der Tool-Seite – der Agent sendet nur `type`). `agent.handle_connection` ruft vor jedem Befehl `agent.sync_clock(now)`:
weicht die Systemuhr mehr als 5 s ab, setzt sie `time.clock_settime(CLOCK_REALTIME)` (Log „Uhr nach dem Server gestellt
(ging N s vor; Hardware-Uhr unverändert)“); ungültige Werte (vor 2023, nach 2100, kein Zahlwert) und Fehler (kein
root) nur ins Protokoll. Die RTC bleibt unverändert: kein `hwclock --systohc`; der Kernel schreibt die RTC nur bei
NTP-Synchronisation zurück (`clock_settime` setzt den Status „unsynchronisiert“ – aus dem Gedächtnis, Kernel
`ntp_clear`). Zeitstempel vor der ersten Verbindung (Startmeldungen im Journal) können noch abweichen. Alter Agent mit
neuem Tool: `now` wird ignoriert; neuer Agent mit altem Tool: kein `now`, Uhr wie bisher. Neuer Agent-Stick nötig.

**Gleichzeitige Okula-Startskripte (B-020).** `Restore-OkulaStart` (gemeinsam für *Windows anpassen* und *Software
installieren*) läuft unter einem benannten Mutex `Global\OkulaStartRestore` (`wintweaks.RESTORE_LOCK`, Wartezeit
höchstens 120 s; danach bzw. ohne Mutex Hinweis „ohne Sperre aufgeräumt“; abgebrochener Halter
(`AbandonedMutexException`) → Sperre gilt als erhalten). Jedes Skript löscht seine `.ps1`/`.cmd`, **bevor** es die
Sperre anfordert; die Entscheidung „letztes Skript“ (kein anderes `okula-*.cmd` mehr) fällt unter der Sperre – das
zweite sieht das erste also erst als fertig, wenn dessen `.cmd` wirklich weg ist. Nur das letzte stellt
`gpt.ini`/`scripts.ini` und Altlasten her. Ist dort nichts mehr zurückzulegen (kein `*.okula-nachher`, `scripts.ini`
ohne `okula-*.cmd`), hat das andere Skript schon aufgeräumt → nichts löschen, Hinweis „Gruppenrichtlinie war schon
zurückgelegt“. Registrierung: scheitert das Entfernen eines Eintrags, zählt `Get-OkulaGpLeft` die verbliebenen
Okula-Einträge – Hinweis nur, wenn noch einer da ist. Der Notfall-Teil im `.cmd` bleibt ohne Sperre.

**Bausteine** (`wintweaks.OPTIONS`, je Option ein `Invoke-OkulaStep` mit try/catch; Fehler → `FEHLER <Option>: <Grund>`
im Protokoll, der nächste Baustein läuft; Store-Apps zuletzt, weil am langsamsten):

| Gruppe | Option | Umsetzung |
|---|---|---|
| Apps | Store-Apps: Xbox · Bing … · Filme & TV (`Microsoft.ZuneVideo`; `Microsoft.ZuneMusic` seit der Ergänzung nur unter Windows-Programme) · Solitaire · Kontakte · Smartphone-Link · Kamera · Office/Office-Hub · 3D-Viewer/Paint 3D/Mixed Reality · Feedback-Hub/Tipps/Hilfe · Microsoft Store | je Gruppe Name-Muster (z. B. `Microsoft.Xbox*`, `Microsoft.Bing*`, `Microsoft.MSPaint` = Paint 3D); `Remove-AppxPackage -AllUsers` (erst Bundle, dann Main) **und** `Remove-AppxProvisionedPackage -Online`; nie: `NonRemovable`, `*VCLibs*`, `*NET.Native*`, `*UI.Xaml*`, `*NVIDIA*`, `*Realtek*`, `*Intel*` |
| Apps (Ä-042) | Outlook (neu)/Mail und Kalender · Teams · Clipchamp · Audiorecorder · Kurznotizen · To Do · Journal · Karten · Uhr (Wecker) · Family · Schnellhilfe · Power Automate · Dev Home · Copilot · Widgets · Werbe-Apps | `Microsoft.OutlookForWindows`, `microsoft.windowscommunicationsapps` · `MSTeams`, `MicrosoftTeams` · `Clipchamp.Clipchamp` · `Microsoft.WindowsSoundRecorder` · `Microsoft.MicrosoftStickyNotes` · `Microsoft.Todos` · `Microsoft.MicrosoftJournal` · `Microsoft.WindowsMaps` · `Microsoft.WindowsAlarms` · `MicrosoftCorporationII.MicrosoftFamily` · `MicrosoftCorporationII.QuickAssist` · `Microsoft.PowerAutomateDesktop` · `Microsoft.Windows.DevHome` · `Microsoft.Copilot`, `Microsoft.Windows.Ai.Copilot.Provider` · `MicrosoftWindows.Client.WebExperience` und (B-017) Richtlinie `HKLM\SOFTWARE\Policies\Microsoft\Dsh\AllowNewsAndInterests=0` („Widgets zulassen“ aus, Policy CSP *NewsAndInterests/AllowNewsAndInterests*, Pro ab Windows 11 21H2 – nimmt Widgets samt Wetter aus der Taskleiste, auch wenn das Paket bleibt; wird vor dem Entfernen gesetzt) · `5319275A.WhatsAppDesktop`, `7EE7776C.LinkedInforWindows`, `AdobeSystemsIncorporated.Adobe*Express*`, `SpotifyAB.SpotifyMusic`, `Disney.37853FC22B2CE`, `Facebook.*` (Facebook, Instagram, Messenger), `BytedancePte.Ltd.TikTok`, `AmazonVideo.PrimeVideo`, `4DF9E0F8.Netflix`, `king.com.*` (Candy Crush). „Bing (Wetter, News, Bing Search …)“ = `Microsoft.Bing*` (auch `Microsoft.BingSearch`) |
| Apps (Ä-042) | Später nachgeladene Apps nochmals entfernen (nach der Anmeldung) | Nachlauf, siehe unten |
| Apps | Wiederinstallation von Werbe-Apps sperren | `Policies\…\CloudContent\DisableWindowsConsumerFeatures=1` (wirkt laut Policy CSP *Experience/AllowWindowsConsumerFeatures* **nur Enterprise/Education**, nicht Pro – Protokoll nennt die Edition, Tooltip im Dialog); ContentDeliveryManager `SilentInstalledAppsEnabled`, `PreInstalledAppsEnabled`, `PreInstalledAppsEverEnabled`, `OemPreInstalledAppsEnabled` = 0 (alle Benutzer, wirkt auch bei Pro) |
| Apps | OneDrive entfernen | Prozess beenden, `OneDriveSetup.exe /uninstall` (System32/SysWOW64), `DisableFileSyncNGSC=1`, Run-Werte `OneDriveSetup`/`OneDrive` weg (alle Benutzer) |
| Apps | Cortana aus | `Windows Search\AllowCortana=0` |
| Updates | Windows Update aus · Keine Treiber · Keine App-Updates | `WindowsUpdate\AU\NoAutoUpdate=1` · `ExcludeWUDriversInQualityUpdate=1`, `DriverSearching\SearchOrderConfig=0` · `WindowsStore\AutoDownload=2` |
| Betrieb | Energieplan Höchstleistung | `powercfg /setactive 8c5e7fda-…`; fehlt der Plan: `/duplicatescheme` und den neuen aktivieren |
| Betrieb | Bildschirm und Standby nie · Ruhezustand aus · Schnellstart aus · Sperrbildschirm aus | `powercfg /change monitor-/standby-timeout-ac/-dc 0` · `powercfg /hibernate off` · `HiberbootEnabled=0` · `Personalization\NoLockScreen=1` |
| Betrieb | Tipps, Vorschläge und Benachrichtigungen aus | ContentDeliveryManager `SubscribedContent-*Enabled` (bekannte und vorhandene), `SystemPaneSuggestionsEnabled`, `SoftLandingEnabled` = 0; `PushNotifications\ToastEnabled=0` (alle Benutzer) |
| Betrieb | Einrastfunktion und Anschlagverzögerung aus | `Control Panel\Accessibility\StickyKeys\Flags="506"`, `Keyboard Response\Flags="122"` (alle Benutzer) |
| Datenschutz | Telemetrie minimal · Werbe-ID · Standort · Fehlerberichte | `DataCollection\AllowTelemetry=0` (Pro: wirkt wie 1) + Dienst DiagTrack deaktiviert · `AdvertisingInfo\DisabledByGroupPolicy=1` · `LocationAndSensors\DisableLocation=1` · `Windows Error Reporting\Disabled=1` |
| Datenschutz | Bing-Suche im Startmenü aus | `DisableWebSearch=1`, `ConnectedSearchUseWeb=0`; Benutzer `BingSearchEnabled=0`, `Policies\…\Explorer\DisableSearchBoxSuggestions=1` (Windows 11) |
| Explorer und Desktop | Dateiendungen · versteckte Dateien · „Dieser PC“ · Desktop-Symbole · Taskleiste | `HideFileExt=0` · `Hidden=1` · `LaunchTo=1` · `HideDesktopIcons\NewStartPanel` `{20D04FE0-…}`/`{F02C1A0D-…}` = 0 · `SearchboxTaskbarMode=0`, `ShowTaskViewButton=0` (alle Benutzer) |
| Explorer und Desktop (Ä-042) | Startmenü: Werbe-Kacheln entfernen (Windows 11) | Richtlinie Start/ConfigureStartPins, siehe unten |
| Dienste | Windows Search · Xbox-Dienste · SysMain · Remote-Registrierung · Druckwarteschlange | `WSearch` · `XblAuthManager`, `XblGameSave`, `XboxNetApiSvc`, `XboxGipSvc` · `SysMain` · `RemoteRegistry` · `Spooler`: stoppen, Starttyp *Deaktiviert*; fehlt der Dienst: „nicht vorhanden“ |
| Anmeldung | Automatische Anmeldung | Konto fehlt (`Get-LocalUser`) → Fehler, nichts gesetzt; sonst Winlogon `DefaultUserName`, `DefaultPassword`, `DefaultDomainName` = Computername, `AutoLogonCount` weg, `AutoAdminLogon="1"` |

Richtlinien-Werte stehen direkt unter `HKLM\SOFTWARE\Policies` (nicht in Registry.pol) – die Verarbeitung der lokalen
Richtlinie entfernt nur Werte, die sie selbst gesetzt hat. **„Alle Benutzer“** (`Invoke-OkulaAllUsers`): jedes Profil
mit SID `S-1-5-21-…` aus `ProfileList` (geladen: `HKU\<SID>`, sonst `NTUSER.DAT` mit `reg load HKU\OkulaAnpassen`
laden und wieder entladen) und das Standardprofil (`ProfileList\Default`, sonst `%SystemDrive%\Users\Default`).

**Vorlagen** (fest, `wintweaks.TEMPLATES`): *Player* = alles ausser Kamera, Druckwarteschlange und Windows-Programme,
mit automatischer Anmeldung; *Laptop* = Store-Apps ausser Kamera/Store (auch Kurznotizen, Audiorecorder, Schnellhilfe), Nachlauf,
Wiederinstallation sperren, Cortana aus, Betrieb nur Schnellstart/Tipps/Einrastfunktion, Datenschutz und Explorer alles
(mit Startmenü), Dienste Xbox und Remote-Registrierung; *Clean* (Ä-042) = alle Häkchen der Gruppe Apps ausser Kamera
und Store, Startmenü, Tipps aus, Telemetrie, Werbe-ID, Fehlerberichte, Bing-Suche – Updates, Betrieb, Explorer-Ansicht,
Dienste und Anmeldung unverändert; *Keine* = nichts. Danach einzeln änderbar, Anzeige „Vorlage: Player (geändert)“.
Keine eigenen Vorlagen.

**Schutzliste** in zwei Stufen (Vergleich mit `-like`; dazu wie bisher `NonRemovable`):
- **Immer** (`wintweaks.PROTECTED_ALWAYS`, im Skript `$OkulaKeepAlways`): Edge `Microsoft.MicrosoftEdge*`, Einstellungen
  `windows.immersivecontrolpanel`, Suche `Microsoft.Windows.Search`/`Microsoft.Windows.Cortana` (Windows-10-Suche, nicht
  die Cortana-App), Sicherheit `Microsoft.SecHealthUI`, App-Installer `Microsoft.DesktopAppInstaller`, Shell-Pakete
  (`ShellExperienceHost`, `StartMenuExperienceHost`, `MicrosoftWindows.Client.CBS`/`.Core`), Frameworks (`*VCLibs*`,
  `*NET.Native*`, `Microsoft.NET.*`, `*UI.Xaml*`, `*WindowsAppRuntime*`), Treiber-Apps (`*NVIDIA*`, `*Realtek*`,
  `*Intel*`, `AdvancedMicroDevices*`, `*Dolby*`, `*Synaptics*`, `*Waves*`).
- **Nur ausdrücklich** (`wintweaks.PROTECTED_WINDOWS`; im Skript zusammen mit der ersten Stufe `$OkulaKeep`): Rechner
  `Microsoft.WindowsCalculator`, Editor `Microsoft.WindowsNotepad`, Paint `Microsoft.Paint` (nicht Paint 3D
  `Microsoft.MSPaint`), Fotos `Microsoft.Windows.Photos`, Snipping Tool `Microsoft.ScreenSketch`, Terminal
  `Microsoft.WindowsTerminal`, Medienwiedergabe `Microsoft.ZuneMusic`, Codecs `Microsoft.*Extension*`. Nur die Häkchen
  der Gruppe *Windows-Programme* rufen `Remove-OkulaApps … -Explicit` auf; dann gilt nur `$OkulaKeepAlways`.
Der Store hat sein eigenes Häkchen. `tests/test_wintweaks.py` prüft: kein Muster trifft ein Paket der ersten Stufe;
Pakete der zweiten Stufe trifft genau ihr eigenes Häkchen; nur die Gruppe *Windows-Programme* nutzt `-Explicit`; keine
Vorlage enthält ein Häkchen dieser Gruppe.

**Windows-Programme (Ergänzung Ä-042, Entscheid Dominik 18.11.2026)** – Gruppe zwischen *Apps* und *Updates*, Standard
aus, in keiner Vorlage (`wintweaks.WIN_KEYS`, Prüfung beim Laden des Moduls). Bausteine laufen nach den Store-Apps und
vor dem Nachlauf; der Nachlauf entfernt sie nicht nochmals.

| Häkchen | Store-App (`Remove-OkulaApps -Explicit`) | Windows-Funktion (`Remove-WindowsCapability -Online`) |
|---|---|---|
| Rechner | `Microsoft.WindowsCalculator` | – |
| Editor | `Microsoft.WindowsNotepad` | `Microsoft.Windows.Notepad~~~~*` (Windows 10 2004), `Microsoft.Windows.Notepad.System~~~~*` (klassischer Editor neben der App) |
| Paint | `Microsoft.Paint` | `Microsoft.Windows.MSPaint~~~~*` (klassisches Paint, Windows 10 2004) |
| Fotos | `Microsoft.Windows.Photos` | – |
| Snipping Tool | `Microsoft.ScreenSketch` | `Microsoft.Windows.SnippingTool~~~~*` (wo die App nicht vorinstalliert ist) |
| Terminal | `Microsoft.WindowsTerminal` | – |
| Medienwiedergabe (Groove-Musik) | `Microsoft.ZuneMusic` (Windows 11 „Medienwiedergabe“, Windows 10 „Groove-Musik“); „Filme & TV“ `Microsoft.ZuneVideo` bleibt unter Apps – keine Doppelung | – |
| Medien-Erweiterungen | `Microsoft.*VideoExtension*` (HEVC, VP9, AV1, MPEG-2 …), `Microsoft.*ImageExtension` (HEIF, WebP, RAW), `Microsoft.WebMediaExtensions`; Tooltip warnt | – |
| WordPad | – | `Microsoft.Windows.WordPad~~~~*` (ab Windows 11 24H2 entfernt → „nicht vorhanden“) |
| Schrittaufzeichnung | – | `App.StepsRecorder~~~~*` |
| Windows Media Player (klassisch) | – | `Media.WindowsMediaPlayer~~~~*` |
| Internet Explorer 11 (auch IE-Modus in Edge) | – | `Browser.InternetExplorer~~~~*` |
| Math-Eingabe (Math Recognizer) | – | `MathRecognizer~~~~*` |

`Remove-OkulaCapabilities`: `Get-WindowsCapability -Online` einmal lesen, nur `State = Installed` entfernen; meldet
`RestartNeeded` („wirkt nach einem Neustart“); keine passende Funktion → „Windows-Funktion nicht vorhanden“. Bewusst
**nicht**: `Disable-WindowsOptionalFeature` (optionale Features), Legacy-Konsole, VBScript, WMIC, PowerShell ISE,
Windows-Fax und -Scan (nicht verlangt). Microsoft rät OEMs, die vorinstallierten FODs nicht aus dem Abbild zu entfernen
(„Don't remove these FODs from the Windows image“) – darum Standard aus.

Quellen Ergänzung (abgerufen 18.11.2026): Microsoft Learn „Available features on demand“ (Capability-Namen WordPad,
Steps Recorder, Internet Explorer, Math Recognizer, Notepad, Notepad (system), Paint, Snipping Tool mit Verfügbarkeit),
„Deprecated features in the Windows client“ (WordPad ab Windows 11 24H2 entfernt, Steps Recorder abgekündigt), „What is
Internet Explorer mode?“ (Voraussetzung „Internet Explorer 11 enabled in Windows Features“); `Media.WindowsMediaPlayer`
nur in Microsoft Q&A (learn.microsoft.com/answers, `dism /online /remove-capability
/capabilityname:Media.WindowsMediaPlayer~~~~0.0.12.0`), nicht in der offiziellen FOD-Liste – darum Wildcard ab `~~~~`.
Paketnamen der Medien-Erweiterungen und `Microsoft.ZuneMusic` aus dem Gedächtnis (Wildcards). Die Paketlisten
(`Get-AppxPackage -AllUsers` je Bundle/Main, `Get-AppxProvisionedPackage -Online`) werden einmal gelesen und
zwischengespeichert – ein Aufruf je Muster dauerte bei rund 45 Mustern mehrere Minuten (10-Minuten-Grenze).

**Entfernen und Protokoll (B-017).** Befund 19.11.2026 (Windows 11 Pro 24H2, Build 26100.8036): 19× „FEHLER … (vorinstalliert):
Das System kann die angegebene Datei nicht finden“, obwohl die Apps weg waren – `Remove-AppxPackage -AllUsers` entfernt
bei 24H2 offenbar auch die Bereitstellung, die zwischengespeicherte Liste von `Get-AppxProvisionedPackage` war danach
veraltet; weil `Remove-OkulaApps` bei Fehlern nur die Fehler meldete, fehlten die entfernten Pakete im Protokoll. Jetzt:
- Nach jedem erfolgreichen `Remove-AppxPackage` wird die Bereitstellungsliste verworfen und vor dem nächsten Schritt neu
  gelesen (`$script:OkulaPkgs.Remove('Provisioned')`; höchstens ein Lesen je App-Gruppe mit entferntem Paket).
- Meldet `Remove-AppxProvisionedPackage` trotzdem 0x80070002/0x80070003 (`HResult` der Ausnahme oder einer inneren
  Ausnahme bzw. Code im Text, `Test-OkulaNotFound`), gilt das Paket als schon entfernt – kein Fehler.
- Protokollzeile über `Get-OkulaResult`: entfernte Pakete stehen immer drin, auch neben echten Fehlern
  („X, Y entfernt; Fehler: Z: …“, dann als FEHLER-Zeile). Gilt ebenso für `Remove-OkulaCapabilities` und – weil es die
  gleichen Funktionen sind – für den Nachlauf.

**Aufräumen des Startskripts (B-017).** `Restore-OkulaStart` (gemeinsam mit *Software installieren*): Lässt sich ein
leerer Ordner (`Machine\Scripts\Startup`, `Machine\Scripts`, `Machine`) nicht löschen, weil Windows ihn gerade verwendet,
wird das als Hinweis zurückgegeben („ok … (leerer Ordner … bleibt …)“) und der Rückbau der Registrierung läuft trotzdem
weiter (vorher brach er an dieser Stelle ab). Ein echter Fehler bleibt: `scripts.ini`/`gpt.ini` lassen sich nicht
löschen bzw. zurücklegen, `scripts.ini` nennt danach noch das Startskript, oder die Einträge unter
`…\Group Policy\Scripts\Startup` bzw. `…\State\Machine\Scripts\Startup` lassen sich nicht entfernen.

**Startmenü Windows 11 (Ä-042).** Befund 18.11.2026 (Win11-VM, alles angehakt): WhatsApp, LinkedIn, Adobe Express,
Clipchamp, Audiorecorder, Kurznotizen, Teams standen im Startmenü, `Get-AppxPackage -AllUsers` kannte sie nicht – es sind
**Platzhalter** im Standard-Startlayout, die Windows erst beim Klick bzw. später im Hintergrund installiert. Lösung:
Richtlinie **ConfigureStartPins** ersetzt die ganze Liste der angehefteten Kacheln (`wintweaks.START_PINS`, JSON
`wintweaks.start_pins_json()`): Edge (`desktopAppLink` `%ALLUSERSPROFILE%\…\Microsoft Edge.lnk`), Explorer
(`%APPDATA%\…\File Explorer.lnk`), Einstellungen (`windows.immersivecontrolpanel_cw5n1h2txyewy!…`), Rechner
(`Microsoft.WindowsCalculator_8wekyb3d8bbwe!App`), Editor (`Microsoft.WindowsNotepad_…!App`), Fotos
(`Microsoft.Windows.Photos_…!App`), Paint (`Microsoft.Paint_…!App`), Snipping Tool (`Microsoft.ScreenSketch_…!App`),
Terminal (`Microsoft.WindowsTerminal_…!App`); `"applyOnce":true`. Schlüssel `packagedAppId` wie in den JSON-Beispielen
von Microsoft Learn und in der Ausgabe von `Export-StartLayout` (die Tabellen auf Learn schreiben `packagedAppID`).
- **Ab Build 26100 (Windows 11 24H2, B-017):** Gruppenrichtlinie „Configure Start Pins“ genau wie in
  `C:\Windows\PolicyDefinitions\StartMenu.admx` (an der VM geprüft: `valueName="ConfigureStartPins"`, enabled = 1,
  Element `text` mit `valueName="ConfigureStartPinsJSON"`, `expandable="true"`; Learn GPO-Tabelle: Wert = „Path to the
  JSON file“). Das Skript schreibt die JSON-Datei `%ProgramData%\Okula\StartPins.json` (UTF-8 ohne BOM,
  `wintweaks.START_PINS_FILE`) und setzt unter `HKLM\SOFTWARE\Policies\Microsoft\Windows\Explorer`
  `ConfigureStartPins` = 1 (REG_DWORD) und `ConfigureStartPinsJSON` = voller Pfad der Datei (REG_EXPAND_SZ). Der
  falsche REG_SZ-Wert aus Ä-042 (JSON-Text in `ConfigureStartPins`) wird vorher gelöscht – ein erneuter Lauf auf schon
  angepassten Geräten repariert ihn. Die Datei muss bleiben: Nachlauf und *Software installieren* löschen
  `%ProgramData%\Okula` nur, wenn der Ordner leer ist. Keine MDM-Bridge mehr ab 24H2 (Befund 19.11.: „Ungültige
  Eigenschaft "ConfigureStartPins"“ am unverwalteten Pro).
- **Build 22000–26099 (Windows 11 vor 24H2):** nur Policy CSP `./Device/Vendor/MSFT/Policy/Config/Start/ConfigureStartPins`
  über die **MDM-Bridge** (WMI `root\cimv2\mdm\dmmap`, Klasse `MDM_Policy_Config01_Start02`, `ParentID='./Vendor/MSFT/Policy/Config'`,
  `InstanceID='Start'`, Eigenschaft `ConfigureStartPins` = JSON; Instanz anlegen bzw. ändern; das Startskript läuft als
  SYSTEM, wie die Bridge es verlangt). Klappt das nicht: FEHLER „Windows 11 vor 24H2: Startmenü nur mit
  Geräteverwaltung (Policy CSP: …)“ – die Gruppenrichtlinie gibt es dort nicht.
- Nicht geprüft wird, ob KB5062660 installiert ist (Build 26100 ohne das Update ignoriert die Richtlinie still).
- Build < 22000 (Windows 10): nichts gesetzt, Protokoll „Windows 10 – ohne Wirkung“. Windows 10 hat das alte
  Kachel-Startmenü (I-039 unverändert, Ä-040 bewusst ohne Startmenü-Kacheln); Option bleibt sichtbar, Beschriftung
  „(Windows 11)“.
- **Bestehende und neue Benutzer:** Geräte-Richtlinie, gilt laut Microsoft bei der nächsten Anmeldung jedes Benutzers.
  `applyOnce` ab Windows 11 24H2 mit KB5062660: Liste nur einmal, danach heften Benutzer selbst an; ältere Windows 11
  ignorieren `applyOnce` und setzen die Liste bei jeder Anmeldung neu (Benutzer können anheften, es bleibt aber nicht).
- **Bestehende Profile ab Build 26100 (B-018):** Befund 24.11.2026 (VM-Win11-clean, Windows 11 Pro 25H2): neues Konto
  bekam die 9 Kacheln sofort, das bestehende erst, nachdem seine `start2.bin` umbenannt war – die gespeicherte Datei
  hat Vorrang vor der Richtlinie. Darum benennt der Baustein nach dem Setzen der Richtlinie für jedes Profil aus
  `Win32_UserProfile` (nicht `Special`, `LocalPath` unter `%SystemDrive%\Users`) die Dateien `start2.bin` und – falls
  vorhanden – `start.bin` in `<Profil>\` + `wintweaks.START_LAYOUT_DIR`
  (`AppData\Local\Packages\Microsoft.Windows.StartMenuExperienceHost_cw5n1h2txyewy\LocalState`) in
  `<Name>.okula-<JJJJMMTT-hhmmss>` um (Sicherung; Windows legt bei der nächsten Anmeldung eine neue an). Das Startskript
  läuft vor der Anmeldung, also sollte nichts gesperrt sein; klappt das Umbenennen trotzdem nicht (oder lässt sich die
  Profilliste nicht lesen), steht ein Hinweis in der ok-Zeile, kein FEHLER. Protokoll: „… gilt für neue Konten und –
  einmalig zurückgesetzt – für bestehende: Startmenü von N Profil(en) zurückgesetzt (start2.bin gesichert als …);
  eigene Anheftungen der Benutzer gehen dabei verloren“. Bewusst nur im Startskript: der Nachlauf benennt nichts um,
  damit Benutzer danach selbst anheften können. Vor 24H2 (MDM-Bridge) unverändert. `start2.bin` wird nur umbenannt,
  nie geschrieben (Format nicht dokumentiert, siehe „Verworfen“).
- **Profil geladen (B-019):** Ist ein Profil beim Lauf geladen (`Win32_UserProfile.Loaded`, Benutzer angemeldet),
  würde die laufende Shell `start2.bin` mit dem alten Layout wieder schreiben (Befund 24.11.: umbenannt 09:25:54, neu
  geschrieben 09:26:58). Darum wird dort **nicht** umbenannt; die SID kommt nach `$script:OkulaStartLater`, die
  Protokollzeile nennt „<Konto> beim Lauf angemeldet – Startmenü dort nicht zurückgesetzt, greift erst nach erneutem
  Lauf / Neustart (der Nachlauf – falls gewählt – holt es einmalig nach …)“. Der Nachlauf bekommt die SIDs als
  `-StartSids "S-1-5-21-…,…"` und benennt einmalig um – nur für diese Profile und nur, wenn das Profil dann nicht
  geladen ist, sonst Hinweis „angemeldet – nicht nachgeholt“. Ohne Nachlauf (Option nicht gewählt oder keine
  Store-Apps) bleibt es beim Hinweis. Seit B-020 benennt der Agent schon offline beim Senden um (Marke
  `start-offline.ok`); dann entfällt dieser Teil im Startskript ganz – er greift nur noch ohne Marke (Agent vor B-020,
  offline nicht geklappt).
- **Zusammenspiel Ä-040:** Die Richtlinie betrifft nur die Startmenü-Kacheln; `LayoutModification.xml` der Taskleiste
  (`winprofile.py`) bleibt unberührt, es wird keine Datei im Standardprofil geschrieben.
- Verworfen: `LayoutModification.json` im Standardprofil (OEM-Weg – nur `primaryOEMPins`/`secondaryOEMPins` mit je
  höchstens 4 Kacheln **zusätzlich** zu den Microsoft-Kacheln, „dynamically delivered apps“ bleiben; nur neue Benutzer),
  `start2.bin` (binär, nicht dokumentiert), `HideRecommendedSection` (nimmt auch zuletzt geöffnete Dateien weg).

**Startmenü auf neu installiertem Windows (B-022).** Befund 25.11.2026 (Okuli, VM-Win11-clean, Direktinstallation mit
Ä-046, Windows 11 Pro 25H2 26200.8037): Richtlinie und JSON vor dem ersten Start gesetzt (Setup-Umgebung), Datei
lesbar, Gruppenrichtlinie vor der Anmeldung fertig, neues Profil ohne `start2.bin` – trotzdem Standard-Layout, auch
nach erneuter Anmeldung mit umbenannter `start2.bin` und ohne `applyOnce`. Am 24.11. wirkte dieselbe Richtlinie auf
der länger betriebenen VM (ab „frisch“); einmal (erster Lauf 24.11.) auch dort nicht.
- **Ursache – belegt:** Die GPO-Variante gibt es erst „starting with Windows 11, version 24H2 with KB5062660“
  (Microsoft Learn, „Customize the Start layout“, Reiter GPO). Der Support-Artikel zu KB5062660 (22.07.2025, Build
  26100.4770) führt die Neuerung „Start menu“ („Boolean option to the Configure Start Pins policy … apply Start menu
  pins once“) unter **„Gradual rollout“**: „users receive the updates at different times, and it might not be
  immediately available to all users“. Er nennt dabei nur die CSP („optionally applied through the existing
  configuration Service Provider (CSP)“), keine Gruppenrichtlinie. – **Belegt, dass es nicht daran liegt:** Edition
  (Policy CSP *ConfigureStartPins*: Pro ab 21H2) und „temporary enterprise feature control“ (Liste auf Learn,
  „Enterprise feature control in Windows 11“, enthält das Startmenü nicht).
- **Plausibel:** Die Gruppenrichtlinie hängt an derselben stufenweisen Freischaltung wie die Neuerung aus KB5062660;
  ein frisch installiertes Gerät hat die Freischaltung noch nicht (sie kommt online und mit der Zeit), ein länger
  betriebenes schon – das erklärt beide Befunde (24.11. wirkte, 25.11. nicht; erster Lauf 24.11. ebenfalls nicht).
- **Vermutung (nicht belegt):** Wann bzw. wodurch die Freischaltung kommt (Online-Konfiguration, Zeit seit
  Installation, kumulatives Update). Microsoft dokumentiert dafür keinen Schalter.
- **Weg 1 – Bereitstellungspaket (PPKG), gewählt:** Learn („Customize the Start layout“, Reiter PPKG):
  `Policies/Start/ConfigureStartPins`, Wert = JSON in einer Zeile. Provisioning setzt die Policy CSP ohne
  Geräteverwaltung („Quickly configure … devices … without a mobile device management (MDM) infrastructure“,
  „Provisioning packages overview“) – also nicht über die Gruppenrichtlinie und damit (plausibel) ohne deren
  Freischaltung. *Erzeugen:* nur mit Windows Configuration Designer (Store-App oder ADK, `icd.exe
  /Build-ProvisioningPackage /CustomizationXML:… /PackagePath:…`); das Format (.ppkg) ist nicht dokumentiert, unter
  Linux also nicht erzeugbar. Signieren ist nicht nötig (unsigniert: Zustimmung bei interaktiver Installation,
  `-QuietInstall` „without any customer interaction“). Darum einmal erzeugen und ins Repo legen:
  `okula_recovery/assets/startpins/customizations.xml` (Vorlage, `wintweaks.start_pins_customizations_xml()`, Test
  prüft Gleichheit; feste Paket-ID `wintweaks.START_PPKG_ID`, OwnerType ITAdmin) → daraus `StartPins.ppkg` und
  daneben `StartPins.ppkg.json` = Inhalt von `StartPins.json` beim Erzeugen. Das Tool gibt das Paket nur mit, wenn
  beide Dateien da sind und die Liste noch stimmt (`wintweaks.start_pins_ppkg()`); ändert sich `START_PINS`, Paket neu
  erzeugen. *Anwenden:* Der Baustein schreibt es als Base64 aus dem Skript nach `%ProgramData%\Okula\StartPins.ppkg` und
  ruft `Install-ProvisioningPackage -QuietInstall -ForceInstall -LogsDirectoryPath %WINDIR%\Temp\okula-startpins-ppkg`
  (Learn: nur Windows 11 Client; Admin-Rechte – das Skript läuft als SYSTEM). Das gilt für alle drei Wege von *Windows
  anpassen*: Direktinstallation (aus `SetupComplete.cmd`, vor der ersten Anmeldung), Agent offline + Startskript
  (B-020; das Startskript kann parallel zur ersten Anmeldung laufen – dann greift das Paket evtl. erst bei der nächsten
  Anmeldung) und Startskript allein. Vor 24H2 ersetzt ein installiertes Paket die MDM-Bridge. Fehler beim Paket: kein
  Abbruch, Grund in der Zeile, Gruppenrichtlinie läuft wie bisher. Die Gruppenrichtlinie (offline und im Skript) bleibt
  zusätzlich gesetzt (wirkt, wo freigeschaltet). *Nicht gewählt:* Paket in `C:\Recovery\Customizations` legen – laut
  Learn („How provisioning works“) wendet Windows Pakete dort bei OOBE immer an, auch unsigniert, aber nur bei OOBE
  (nicht bei schon eingerichteten Geräten des Agent-Wegs) und der Ordner gehört zu „Reset this PC“; über das Skript ist
  es für alle Wege gleich. *Offen:* Ob `applyOnce` über die CSP greift (der KB-Artikel nennt die CSP, aber unter
  „Gradual rollout“) – sonst setzt Windows die Liste bei jeder Anmeldung neu. Ob das Paket als SYSTEM aus
  `SetupComplete.cmd` installiert, prüft Okuli an der VM ([TESTS.md](TESTS.md) „B-022“).
- **Weg 2 – `LayoutModification.json` im Standardprofil (OEM):** bleibt verworfen (siehe oben: nur 4 + 4 Kacheln
  **zusätzlich**, Microsoft-Kacheln bleiben, nur neue Benutzer).
- **Weg 3 – Gruppenrichtlinie allein:** bleibt, solange kein Paket beiliegt – mit **ehrlichem Hinweis**
  (`wintweaks.START_GPO_HINT`): Protokoll am Gerät mit Status **„Hinweis“** statt „ok“ („Wirkung nicht sicher – …“,
  `Invoke-OkulaStep` wertet einen Rückgabetext „Hinweis: …“ so aus, Zähler „mit Hinweis“ in der Schlusszeile), Log des
  Auftrags („Hinweis Startmenü: …“ nach „Vor dem Windows-Start gesetzt …“), Vorschau der Direktinstallation, Tooltip,
  Hilfe. `install.cmd` schreibt „Startmenue-Richtlinie … (Wirkung: siehe Zeile Startmenue beim ersten Start)“.
- **Nicht gemacht:** Wirkung am Gerät erkennen (z. B. `start2.bin` nach der Anmeldung auswerten) – Format nicht
  dokumentiert, nicht belegbar. WMI-Bridge: `MDM_Policy_Config01_Start02` hat bei Pro ohne MDM-Anmeldung keine
  Eigenschaft `ConfigureStartPins` (Befund Okuli) – bleibt nur vor 24H2 als Versuch.

Quellen B-022 (abgerufen 25.11.2026): Microsoft Learn „Customize the Start layout for managed Windows devices“
(Stand 15.07.2026; Reiter CSP/GPO/PPKG, `applyOnce`), „Start Policy CSP“ (Stand 23.11.2026; *ConfigureStartPins*
Pro ab 21H2, GPO-Zuordnung StartMenu.admx), „Enterprise feature control in Windows 11“, „Provisioning packages
overview“, „How provisioning works in Windows“, „Apply a provisioning package“, „Windows Configuration Designer
command line interface“, „Create a provisioning package with multivariant settings“ (Aufbau `customizations.xml`),
PowerShell „Install-ProvisioningPackage“; support.microsoft.com „July 22, 2025—KB5062660 (OS Build 26100.4770)
Preview“ (Abschnitt „Gradual rollout“ → „Start menu“).

**Protokoll der Direktinstallation (B-022):** `install.cmd` und `SetupComplete.cmd` legen
`okula-windows-anpassen.log` mit cmd an – ohne BOM und mit `%DATE% %TIME%` („25.11.2026  8:28:45,79“). Das Skript
gleicht beim ersten Schreiben (`Initialize-OkulaLog` in `Write-OkulaLog`, auch im Nachlauf) einmalig an: Datei ohne
BOM → lesen, Zeilen mit Datum von cmd (`wintweaks.LOG_DATE_DE` Tag.Monat.Jahr, `LOG_DATE_US` „Tue 11/25/2026“) ins
Format `yyyy-MM-dd HH:mm:ss`, andere Zeilen unverändert, über eine Zwischendatei als UTF-8 mit BOM zurückschreiben;
danach hängt `Add-Content -Encoding UTF8` an (ohne zweiten BOM). Fehler dabei: still, das Protokoll läuft weiter. Die
Neustart-Zeile der Software schreibt `SetupComplete.cmd` jetzt vor dem Skript („Neustart 60 s nach Windows anpassen
…“) – nach dem Skript schreibt cmd nichts mehr hinein. Nicht angeglichen wird, wenn das Skript gar nicht läuft (dann
bleiben die Zeilen von cmd, wie sie sind). Zeit in cmd zerlegen wurde verworfen: `%DATE%` hängt von der Sprache der
Setup-Umgebung ab, `wmic` fehlt in neuen Versionen.

**Nachlauf (Ä-042)** – Option „Später nachgeladene Apps nochmals entfernen (nach der Anmeldung)“: Werbe-Apps lädt
Windows erst nach der ersten Anmeldung bzw. nach Store-Updates. Der Baustein (immer als letzter) schreibt
`%ProgramData%\Okula\okula-windows-anpassen-nachlauf.ps1` (UTF-8 mit BOM, Inhalt Base64 im Startskript, enthält nur die
App-Bausteine – nie das Passwort) und legt die geplante Aufgabe **„Okula Windows anpassen Nachlauf“** an: SYSTEM,
Auslöser *Bei Anmeldung* (jeder Benutzer) mit 30 min Verzögerung, Ablauf nach 30 Tagen
(`EndBoundary` + `DeleteExpiredTaskAfter` 1 Tag – läuft sie nie, löscht Windows sie), höchstens 2 h, auch im
Akkubetrieb. Das Skript entfernt die gewählten Store-Apps nochmals (gleiche Muster und Schutzliste), protokolliert ins
gleiche Protokoll („Nachlauf … Start/Ende“) und löscht im `finally` sich selbst, den leeren Ordner und zuletzt die
Aufgabe – auch nach einem Fehler, also genau ein Lauf. Ohne gewählte Store-Apps: „kein Nachlauf nötig“. Aufgabenname,
Pfad und Befehlszeile nur ASCII. B-019: Ist beim Anlegen schon jemand angemeldet, zusätzlich ein einmaliger Auslöser
„jetzt + 30 min“ (siehe „Windows wartet nicht auf Startskripte“); mit *Startmenü: Werbe-Kacheln entfernen* holt der
Nachlauf zuerst das Startmenü angemeldeter Profile nach (`-StartSids`, siehe Startmenü – entfällt, wenn der Agent
offline umbenannt hat, B-020).

**Bing Search blieb (Befund 18.11.):** Das Muster `Microsoft.Bing*` trifft `Microsoft.BingSearch`. Das Protokoll der VM
lag nicht vor. Vermutung (nicht belegt): Die App wurde erst nach dem Startskript über den Store nachgeladen bzw.
aktualisiert – dann stand im Protokoll „nicht vorhanden“ bzw. nur andere Bing-Apps; bei einem Fehler stünde
„FEHLER … Microsoft.BingSearch: <Grund>“. Behoben durch den Nachlauf (entfernt nachgeladene Pakete nochmals); Klärung
über das Protokoll in [TESTS.md](TESTS.md) Abschnitt 26.

Quellen Ä-042 (Microsoft Learn, abgerufen 18.11.2026): „Start Policy CSP“ (*ConfigureStartPins*: Device/User, **Pro**,
Enterprise, Education ab Windows 11 21H2 [10.0.22000]; GPO-Zuordnung `Software\Policies\Microsoft\Windows\Explorer`,
Wert `ConfigureStartPins`, StartMenu.admx; *HideRecommendedSection* Pro ab 22H2), „Customize the Start layout for
managed Windows devices“ (JSON-Format, `applyOnce` ab 24H2 mit KB5062660, „you overwrite the entire layout“, Pins
nicht installierter Apps erscheinen erst nach der Installation, IDs für Edge, Einstellungen, Explorer, Terminal, Paint,
Fotos), „Start policy settings“ (GPO *Configure Start Pins* erst ab 24H2 mit KB5062660), „Experience Policy CSP“
(*AllowWindowsConsumerFeatures* = GPO *Turn off Microsoft consumer experiences*, `DisableWindowsConsumerFeatures`:
**❌ Pro**, nur Enterprise/Education/IoT; „Start suggestions, … Post-OOBE app install and redirect tiles“), „Customize
the Windows 11 Start menu“ (OEM: `LayoutModification.json` in `Users\Default\AppData\Local\Microsoft\Windows\Shell`,
höchstens 4 + 4 Kacheln, „dynamically delivered apps“), „Using PowerShell scripting with the WMI Bridge Provider“
(Geräte-Richtlinien als Local System, `New-CimInstance`/`Set-CimInstance` mit `ParentID`/`InstanceID`),
„MDM_Policy_Config01_Start02 class“ (Klasse vorhanden; die Seite von 2018 listet `ConfigureStartPins` noch nicht – die
Eigenschaft kommt mit Windows 11, darum Weg 2 und Test am Gerät). support.microsoft.com: KB5062660 (22.07.2025, Build
26100.4770): „Boolean option to the Configure Start Pins policy to allow admins to apply Start menu pins once“. Nicht
abgerufen, aus dem Gedächtnis: Paketnamen der Werbe-Apps (WhatsApp, LinkedIn, Adobe Express, Spotify, Disney+, TikTok,
Prime Video, Netflix, Candy Crush, Facebook/Instagram), Journal, Family, Schnellhilfe, Copilot, Widgets und die
AUMIDs von Rechner, Editor, Snipping Tool.

Quellen B-017 (Microsoft Learn, abgerufen 19.11.2026): „Customize the Start layout for managed Windows devices“
(GPO-Tabelle *Configure Start Pins* = „Path to the JSON file“, nur ab 24H2 mit KB5062660; CSP/Intune = Inhalt der
Datei; Schlüsseltabelle `packagedAppID`, JSON-Beispiel `packagedAppId`), „Start Policy CSP“ (*ConfigureStartPins*
Pro ab 21H2, GPO-Wert `ConfigureStartPins`, StartMenu.admx; *HideRecommendedSection* Device/User, **Pro** ab 22H2,
`Policies\Microsoft\Windows\Explorer\HideRecommendedSection`), „NewsAndInterests Policy CSP“ (*AllowNewsAndInterests*:
Device, **Pro**, ab Windows 11 21H2, 0 = nicht zulassen, „applies to the entire widgets experience, including content
on the taskbar“, GPO *Allow widgets*, `SOFTWARE\Policies\Microsoft\Dsh`, NewsAndInterests.admx), „Customize the
Windows 11 Start menu“ (OEM, ebenfalls Tabelle `packagedAppID`, Beispiel `packagedAppId`). Am Gerät: `StartMenu.admx`
der VM-Win11-test (Okuli, 19.11.). HResult 0x80070002/0x80070003 = Win32-Fehler 2/3 (Datei/Pfad nicht gefunden).

**Protokoll:** `C:\Windows\Temp\okula-windows-anpassen.log` (UTF-8 mit BOM, Zeitstempel, „ok“/„Hinweis“/„FEHLER“ je
Baustein mit Kurzinfo, z. B. entfernte Apps; am Ende „Ende: N ok, H mit Hinweis, M mit Fehler“ – „Hinweis“ seit B-022
für gelaufene Bausteine mit unsicherer Wirkung, Zeilen der Direktinstallation siehe „Protokoll der Direktinstallation“).

**Sicherheit Passwort (automatische Anmeldung):** nie im Protokoll am Gerät, im Log des Auftrags, im Verlauf, in
Vorlagen oder im Agent-Log (der Agent protokolliert den Skriptinhalt nicht). Im Skript steht es Base64-kodiert (gegen
Anführungszeichen-Probleme, **kein** Schutz) – Übertragung Tool → Agent über TLS. Auf der Disk liegt es nur bis zum
nächsten Start (die Datei bekommt von ntfs-3g keine Windows-Rechte; Windows läuft in der Zeit nicht); das Skript löscht
sich als Erstes. Danach steht es – wie bei der automatischen Anmeldung von Windows üblich – im **Klartext** in Winlogon
(`DefaultPassword`); Hinweis im Dialog und in der Hilfe.

**Grenzen:** Startskripte haben eine Wartezeit von 10 Minuten (Richtlinie „Maximale Wartezeit für
Gruppenrichtlinienskripts“, Standard 600 s) – dauert die App-Entfernung länger, bricht Windows ab (das Aufräumen ist
dann schon erledigt, Protokoll ohne „Ende“). Ist die Anmeldung schneller als das Skript (asynchrone Verarbeitung beim
Start), greift die automatische Anmeldung erst beim nächsten Start. Bei einem frisch zurückgespielten,
generalisierten Master-Image (Ersteinrichtung offen) wirkt es erst nach der Ersteinrichtung (Hinweis im Log). Wird
die lokale Richtlinie per Domäne abgeschaltet, läuft das Skript nicht. Rückgängig macht das Tool nichts.
Kombination mit *Danach anpassen*, Direktinstallation und Automatisierung folgt später.

**Agent:** neuer Befehl → **neuer Agent-Stick bzw. Netzwerkstart neu vorbereiten**. Für das Startskript sind keine
neuen Pakete nötig (nur Dateien über ntfs-3g; `libhivex-bin` ist ohnehin auf dem Stick).

Quellen (Microsoft Learn): „Use Startup, Shutdown, Logon, and Logoff Scripts“ / „Assign computer startup scripts“
(Group Policy: Startskripte laufen als Local System beim Start), „[MS-GPSCR]: Group Policy: Scripts Extension Encoding“
(`scripts.ini`, GUIDs der Scripts-Erweiterung), „[MS-GPOL]: Group Policy: Core Protocol“ (`gpt.ini`, `Version` mit
Benutzer-/Computer-Teil, `gPCMachineExtensionNames`), Richtlinie „Specify maximum wait time for Group Policy scripts“
(`MaxGPOScriptWait`), „Turn on automatic logon in Windows“ (Winlogon `AutoAdminLogon`/`DefaultPassword`, Klartext),
„Remove-AppxPackage“ und „Remove-AppxProvisionedPackage“, „Sysprep fails after you remove or update Microsoft Store
apps that include built-in Windows images“ (warum auch die vorinstallierten Pakete entfernt werden).

**Zusammen mit „Software installieren“ (I-020):** Stehen beide Startskripte gleichzeitig aus, ergänzt das zweite nur
seinen Eintrag in `scripts.ini` (Originale und Version bleiben, Ergebnis `shared`). Beim Start laufen beide
nacheinander; der Rückbau (`wintweaks.RESTORE_START`, auch im Notfall-Teil der `.cmd`) legt `gpt.ini`/`scripts.ini`
erst zurück, wenn keine andere `okula-*.cmd` mehr im Startup-Ordner liegt.

**Registrierung des Startskripts (B-018).** Windows legt beim Verarbeiten der Richtlinie Einträge unter
`HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Group Policy\Scripts\Startup\<GPO>\<Nr>` und
`…\Group Policy\State\Machine\Scripts\Startup\<GPO>\<Nr>` an (Wert `Script` = Skriptname, u. a. `ExecTime` als
REG_QWORD mit 16 Byte). `Get-ItemProperty` wandelt alle Werte um und wirft daran `InvalidCastException`, auch mit
`-ErrorAction SilentlyContinue` (Befund 24.11.2026) – darum liest `Restore-OkulaStart` nur `$entry.GetValue('Script')`.
Entfernt werden Einträge des eigenen Skripts (`$OkulaName`) und Altlasten: `Script` endet auf `okula-*.cmd`, die
Datei liegt aber nicht mehr im Startup-Ordner (Reste von Läufen vor B-018; ein noch wartendes anderes Okula-Skript liegt
dort und bleibt). Wird eine GPO-Liste leer, wird sie gelöscht; sonst nummeriert `Update-OkulaGpNumbers` die übrigen
Einträge lückenlos `0, 1, …` nach (Reihenfolge bleibt), danach die GPO-Liste selbst. **Ungeprüft:** ob Windows Lücken
in der Nummerierung verträgt, ist in keiner gefundenen Quelle belegt – lückenlos entspricht dem, was Windows selbst
anlegt. Fehler in diesem Teil sind nur ein Hinweis („Registrierung … nicht ganz aufgeräumt (ohne Wirkung)“), die
Zeile bleibt ok; ohne `scripts.ini` haben die Einträge keine Wirkung. Die Zahl entfernter Einträge steht als Hinweis
in der Zeile „Startskript und Gruppenrichtlinie aufräumen“ (beide Startskripte).

### Beim Aufsetzen mitgeben (Ä-046)

Häkchen **Windows anpassen** mit *Vorlage* und *Einstellungen …* (`automation_tab.TweakChooser`; *Einstellungen …*
öffnet `WindowsTweakDialog(choose=True)` mit Knopf *Übernehmen* – gleiche Optionen und Tooltips, kein Nachbau) in
*OS installieren …*, *Image zurückspielen* → *Danach anpassen* und im Reiter *Automatisierung* (Feld
`Settings.tweak`, auch in Vorlagen). Auswahl als `{"template", "keys"}` (`wintweaks.choice`/`clean_choice`:
unbekannte Optionen fallen weg). **Ohne automatische Anmeldung** (`EMBED_EXCLUDED`): sie braucht ein Passwort, das
beim Aufsetzen mitgegeben bzw. in Einstellungen und Vorlagen gespeichert würde (Entscheid „Passwörter werden nicht
gespeichert“) – dafür bleibt *Windows anpassen …* am Gerät; „Player“ ohne Anmeldung gilt als unverändert
(`choice_label`). Ohne Häkchen ändert sich nichts am Ablauf (Tests `PlanTest.test_without_choice_unchanged`).

**Zurückspielen und Automatisierung:** Nach dem Zurückspielen (und nach der Software) `jobs.send_tweak_choice` →
derselbe Weg wie *Windows anpassen …*: Agent-Befehl `tweak` legt das Startskript ab (zweites Startskript nur als
Eintrag in `scripts.ini`, Software steht davor) und schreibt den Teil vor der ersten Anmeldung offline
(`deploy.tweak_offline`, B-020/B-021). Fehler → „Zurückgespielt, aber Windows anpassen nicht übertragen: …“ (wie
bei der Software). Bei einem generalisierten Master greift das Skript nach der Ersteinrichtung.

**Direktinstallation – Weg und Belege.** Beim Senden gibt es noch kein Windows und keinen Hive; Windows wartet bei der
Anmeldung nicht auf Startskripte (B-020). Darum zwei Teile:
1. **Richtlinien vor dem ersten Start** (Startmenü-Richtlinie + `StartPins.json` ab Build 26100, Widgets,
   `NoLockScreen`, `DisableWindowsConsumerFeatures` – dieselben Werte wie `deploy.tweak_offline`): `install.cmd`
   lädt gleich nach `dism /Apply-Image` den Hive `W:\Windows\System32\config\SOFTWARE` (`reg load HKLM\OKULASW`),
   liest `CurrentBuild`, setzt die Werte mit `reg add` und entlädt ihn (`winsetup.tweak_offline_cmd`). Vorbild:
   Microsoft Learn, „Windows S mode deployment lab“ (Abschnitt „Add the manufacturing registry key“: `reg load` des
   Hives eines aufgespielten Images, `reg add`, `reg unload`); `reg load`/`reg add`/`reg unload` aus der
   Befehlsreferenz „reg load“ (Rückgabe 0/1). Windows ist dann noch nie gestartet – **kein Benutzerprofil, keine
   `start2.bin`**, Umbenennen entfällt; die Marke `start-offline.ok` mit `source=setup` sagt dem Skript, dass nichts
   zurückzusetzen ist (Protokoll „schon bei der Installation vor dem ersten Start gesetzt …“). Dieser Teil hängt nicht
   an `SetupComplete.cmd` und wirkt darum **auch mit OEM-Schlüssel**. Fehler brechen die Installation nicht ab (nur
   `install.log` und Zeile „Hinweis …“ im Protokoll `okula-windows-anpassen.log`), das Skript setzt die Werte
   ohnehin nochmals. Gewählt statt `RunSynchronous` in specialize: einfacher (kein XML mit Bedingungen für den Build),
   früher (vor jedem Start) und gleich wie beim Agent.
2. **Übrige Einstellungen:** Das Skript liegt als Startskript (`okula/gp`, `software.startup_files`, Reihenfolge in
   `scripts.ini`: Software, dann Windows anpassen) und wird zuletzt aus `SetupComplete.cmd` aufgerufen
   (`winsetup.tweak_start`). Microsoft Learn, „Add a Custom Script to Windows Setup“ (abgerufen 24.11.2026): „After
   Windows is installed but before the logon screen appears, Windows Setup searches for the SetupComplete.cmd file …
   runs the script“, „runs with local system permissions“, „disabled when using OEM product keys, except on
   Enterprise editions“. **Widerspruch auf derselben Seite:** in der Übersicht steht „starts immediately after the
   user sees the desktop“ – die Reihenfolge der Schritte sagt „before the logon screen“. Darum hängt das, was vor der
   ersten Anmeldung wirken muss, nicht an SetupComplete (Teil 1); am Gerät prüfen ([TESTS.md](TESTS.md), Abschnitt
   „Ä-046 Neue Maschine in einem Durchgang“: Zeitstempel Protokoll vs. Anmeldung 4624). Die Seite warnt: kein
   Neustart innerhalb von SetupComplete.

**Reihenfolge mit der Software: erst Software, dann Anpassen.** *Dienste* schaltet z. B. die Druckwarteschlange ab
(Druckertreiber-Installer brauchen sie), *Store-Apps entfernen* soll den fertigen Stand treffen (auch was ein
Installer evtl. mitbringt); Bausteine, die Software braucht (VCLibs, .NET Native, WindowsAppRuntime, App-Installer),
schützt `PROTECTED_ALWAYS` ohnehin. In `SetupComplete.cmd` wartet *Windows anpassen*, bis die geplante Aufgabe „Okula
Software installieren“ weg ist (`schtasks /query`, alle 15 s per `ping` – `timeout` braucht eine Konsole), höchstens
`SOFTWARE_WAIT_MIN` = 30 min, danach trotzdem (Hinweis im Protokoll). Meldet ein Programm 3010, plant die Software
nach 60 s einen Neustart – der käme mitten in *Windows anpassen*: `shutdown /a` stellt ihn zurück, als **letzter**
Befehl von `SetupComplete.cmd` folgt `shutdown /r /t 60` (die Seite verbietet einen Neustart, nach dem SetupComplete
weiterlaufen müsste – hier ist SetupComplete dann fertig). Restrisiko: Läuft die Software länger als 30 min und
meldet danach 3010, kann der Neustart ein noch laufendes *Windows anpassen* abbrechen (Skript schon gelöscht, Rest
fehlt; Nachlauf entfernt die Store-Apps trotzdem). Als Startskript (OEM-Fall, Zurückspielen, Automatisierung) gibt es
kein Warten – beide Skripte starten beim Start (Reihenfolge `scripts.ini`), Software installiert in der geplanten
Aufgabe weiter (wie bisher bei *Software installieren* + *Windows anpassen*, Ä-044).

**OEM-Schlüssel (B-013):** SetupComplete läuft dann nicht. Teil 1 wirkt trotzdem; die übrigen Einstellungen setzt das
Startskript beim ersten Start – evtl. parallel zur ersten Anmeldung (B-020), Store-Apps spätestens im Nachlauf nach
30 min. Ehrlich gemeldet: Log des Auftrags (`jobs.TWEAK_SETUP_OEM`, sobald ein Windows-Schlüssel gesetzt ist – ob
er OEM ist, weiss das Tool nicht sicher) und Hilfe. Kein zusätzlicher Weg über `FirstLogonCommands` (läuft als
Benutzer bei der Anmeldung) oder specialize (vor der Software).

**Master-Image (Audit-Modus, I-038): nicht angeboten** (Häkchen ausgegraut, `winsetup.TWEAK_AUDIT`, `plan` lehnt ab).
Gründe: Die Einstellungen landeten im Master; nur für einzelne Benutzer entfernte Store-Apps lassen Sysprep
scheitern; Startskript und Nachlauf-Aufgabe liefen im Audit-Modus bzw. kämen ins Image. Beim Ausrollen über *Image
zurückspielen* → *Danach anpassen* bzw. Automatisierung mitgeben. Software bleibt beim Master erlaubt (I-020).

## Software installieren (I-020, Software-Bibliothek Ä-041)

Programme aus der **Software-Bibliothek** des Tools werden auf dem Gerät **still und ohne Klicks** installiert – beim
ersten Windows-Start als SYSTEM. Quelle sind feste, getestete Versionen (bewusst nicht winget, Entscheid 17.11.).
Bis Ä-041 (18.11.) war die Quelle `NAS/Verteilen/Software`; dieser Ordner gehört jetzt nur noch zu *Ordner senden*
(Werkzeug-Ordner für Geräte unterwegs) und wird vom Katalog weder gelesen noch beschrieben.
Module: `software.py` (Bibliothek, Erkennung, Skript – ohne GTK), `installerinfo.py` (Leser für PE, Versionsinfo,
Qt-Ressourcen, NSIS-Kopf, Compound File/MSI, MSIX – Ä-043), `software_ui.py` (Liste *Software installieren*,
Fenster *Software-Bibliothek*), Agent-Befehl `software` (`deploy.software`), `jobs.send_software`/`software_plan`,
Direktinstallation in `winsetup.py`.

**Ablage** (`software.library_dir`): `NAS/Software-Bibliothek/` neben `Verteilen` (wird beim Öffnen des Fensters bzw.
beim ersten Laden angelegt; im Demo-Speicher entsprechend `…/demo/Software-Bibliothek/`). Je Eintrag ein Ordner
`<key>-<version>` (z. B. `vlc-3.0.24`, ohne Version nur `<key>`; belegt → `-2`, `-3` …) mit dem Installer bzw. dem
Inhalt des geladenen Ordners und der Beschreibung `.okula.json` (`format: okula-software`, Felder wie I-020):
Programmname, Version, Schlüssel für neue Versionen, erkannter und gewählter Installer-Typ, Parameter, erfolgreiche
Rückgabewerte (je Typ, sonst 0, 3010), Art (`install`/`copy`/`manual`), Installer relativ zum Eintrag, Grösse, Zeit und
SHA-256 des Installers; seit Ä-043 `publisher` (Hersteller), `detected_args` (Vorschlag der Erkennung), `hint`
(Hinweis bei „Parameter fehlt“), `redetected` (Zeit von *Neu erkennen*); neu `source` (`file`/`folder`), `content_sha256` (Datei: deren SHA-256; Ordner: SHA-256 über
alle relativen Pfade und deren SHA-256), `loaded_from`, `loaded`. Der Name des Eintrags ist die Auswahl (gespeichert in
Automatisierung/Vorlagen) und der Ordnername am Gerät. Ein von Hand hineinkopierter Ordner ohne Beschreibung erhält
beim Lesen eine neue (als Ordner-Eintrag). Ordner `.…partial` und Links werden übersprungen.

**Laden** (`software.inspect` → `software.load`): Datei (`software.INSTALLER_EXT`: `.exe`, `.msi`, seit Ä-043 auch
`.msp`, `.msu`, `.msix`, `.msixbundle`, `.appx`, `.appxbundle`) oder Ordner prüfen (Umfang, Namen wie beim
Hochladen in den Reiter *Dateien*, Installer-Kandidaten; Links/Sonderdateien übersprungen; nichts aus der Bibliothek
selbst), freien Platz prüfen (Reserve 1 GB), dann nach `Software-Bibliothek/.<zufällig>.partial/` kopieren – Fortschritt
je 8 MB, Abbruch jederzeit, SHA-256 beim Kopieren. Gleicher `content_sha256` schon in der Bibliothek → Kopie löschen,
Meldung „schon in der Bibliothek (als …)“, kein zweiter Eintrag. Sonst Erkennung wie I-020 (`_fresh_meta` →
`detect`), Übernahme einer vorigen Version (`_adopt`), Beschreibung schreiben und `.partial` erst ganz am Schluss in den
Eintrag umbenennen – ein Abbruch oder Fehler hinterlässt nichts (Reste nach Absturz entfernt `cleanup_partial` beim
nächsten Verbinden, wenn älter als ein Tag). Ordner: genau ein Installer direkt im Ordner (bzw. genau einer insgesamt)
gilt als Installer; sonst fragt das Fenster vor dem Kopieren nach (oder „keiner – später festlegen“).
**Löschen** (`software.delete`): Eintrag zuerst in einen versteckten Namen umbenennen, dann löschen.

**Aufräumen von `Verteilen\Software`** (`software.cleanup_distribute`, Ä-041): bei jedem Wechsel auf „NAS verbunden“
(`ui.cleanup_software_folder`, im Hintergrund) werden in `Verteilen/Software` – nur direkt im Ordner – die Dateien
`.<Name>.okula.json` gelöscht, deren Inhalt `"format": "okula-software"` hat (von I-020 angelegt). Andere Dateien,
Links, fremde oder kaputte `.okula.json` und Unterordner bleiben. Ergebnis in der Statuszeile und auf stderr. Nichts
wird automatisch in die Bibliothek übernommen.

**Fenster** *Extras → Software-Bibliothek …* (`SoftwareLibraryWindow`): oben *Ins Tool laden …* (Dateiwahl mit Filter
.exe/.msi, mehrere möglich), *Ordner laden …* und Ziehen und Ablegen aufs Fenster (Warteschlange, nacheinander);
Fortschritt mit *Abbrechen* (Schliessen während des Ladens = Abbrechen; das Hauptfenster fragt beim Beenden wie bei
Kopien aufs NAS). Darunter die Liste (Programm, Version, Hersteller, Typ, Parameter, Rückgabewerte, Status, Grösse;
sortierbar, Suchfeld): Programm, Version, Hersteller, Parameter und Rückgabewerte direkt in der Zelle
(`software.update`), Art und Installer über *Bearbeiten …* (`SoftwareEditDialog` von I-020, mit Hersteller und dem
erkannten Typ samt Vorschlag), *Neu erkennen* (Knopf und Rechtsklick-Menü, Ä-043), *Löschen*/Entf mit Rückfrage.
Unter der Liste die Angaben des markierten Eintrags (`software_ui.detail_markup`: Typ, Hersteller, Installer, Status,
bei „Parameter fehlt“ „Was tun: …“). Der frühere Knopf *Software …* im
Reiter *Dateien* ist entfallen. Läuft das Demo-Gerät, öffnet das Fenster die Bibliothek im Demo-Speicher.

**Sammelordner** („System Tools“): als Ordner geladen ist er ein Eintrag. Für Ordner mit vielen kleinen Werkzeugen
gibt es die Art **„nur kopieren“**: der Ordner landet auf dem öffentlichen Desktop unter `Software\<Eintrag>`.
Begründung: eine Zeile je Ordner hält die Liste kurz, Werkzeuge sind meist portabel bzw. werden nur bei Bedarf
installiert. Einzelne Dateien eines Sammelordners zu wählen, wurde verworfen (Baumansicht in drei Dialogen, unklare
Reihenfolge).

**Erkennung ohne Ausführen** (Ä-043; `software.detect` → `_detect_blob`, Typen in `software.KINDS`, Leser in
`installerinfo.py`, ohne neue Abhängigkeit). Gelesen werden nur Teile der Datei (`installerinfo.Blob`): die ersten
8 MB, der PE-Kopf mit Abschnitten und Datenverzeichnissen, die Ressourcen Versionsinfo (RT_VERSION) und Manifest
(RT_MANIFEST) – auch wenn sie hinter 8 MB liegen –, die ersten 64 kB der **angehängten Daten** (Overlay = hinter dem
letzten Abschnitt, ohne Authenticode-Signatur) und je nach Typ gezielt mehr (Qt-Ressourcen bis 8 MB, Abschnitt
`.rdata`, entpackter NSIS-Kopf bis 4 MB, MSI-Tabellen bis 16 MB). Kaputte Dateien ergeben „unbekannt“, nie einen
Fehler. Reihenfolge: Endung/Kopf (MSP, MSU, MSIX/APPX, MSI) → `.wixburn` → Qt IFW → Inno → NSIS → InstallBuilder →
InstallShield → übrige Kennungen → Squirrel → SFX-Archive → unbekannt.

| Typ | Kennung | Parameter (Rückgabewerte „ok“) | Quelle |
|---|---|---|---|
| MSI | Endung `.msi` bzw. Compound-Kopf `D0 CF 11 E0 A1 B1 1A E1` | `msiexec /i "<Datei>" /qn /norestart` (0, 1641, 3010) | Microsoft Learn „msiexec“, „Standard Installer Command-Line Options“ ¹ |
| MSP (Patch) | Endung `.msp` | `msiexec /p "<Datei>" /qn /norestart` (0, 1641, 3010) | Microsoft Learn „msiexec“ ¹ |
| MSU (Windows-Update) | Endung `.msu` bzw. Cabinet-Kopf `MSCF` | `wusa.exe "<Datei>" /quiet /norestart` (0, 3010, 2359302 = 0x240006 schon installiert) | Microsoft Learn „wusa.exe“ ¹ |
| MSIX/APPX, Bündel | Endung `.msix`/`.appx`/`.msixbundle`/`.appxbundle` bzw. ZIP mit `AppxManifest.xml` / `AppxMetadata/AppxBundleManifest.xml` | `Add-AppxProvisionedPackage -Online -PackagePath "<Datei>" -SkipLicense` (kein Rückgabewert; Fehler = Ausnahme) | Microsoft Learn „Add-AppxProvisionedPackage“ ¹ |
| NSIS | Manifest „Nullsoft.NSIS.exehead“, „NullsoftInst“ am Anfang der angehängten Daten | `/S` (0, 3010) | NSIS-Handbuch 3.2.1 „Common Options“ / 4.12 „Silent Installers“ ¹ |
| electron-builder (NSIS) | NSIS, im entpackten Skript `app-64.7z`/`app-32.7z`/`app-arm64.7z` | `/S /allusers` – sonst nur für das Konto SYSTEM installiert (0, 3010) | electron-builder „NSIS“ (per-machine, `/allusers`) ¹; an Companion, Kards, Reolink geprüft |
| Inno Setup | Manifest „JR.Inno.Setup“, „Inno Setup Setup Data“, „Inno Setup“ | `/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-` (0, 3010) | Inno-Setup-Hilfe „Setup Command Line Parameters“ ¹ |
| InstallShield (MSI) | „InstallShield“, „ISSetup.dll“, „ISSetupStream“ ohne `setup.inx` | `/s /v"/qn /norestart"` (0, 1641, 3010) | Revenera „Setup.exe and Update.exe Command-Line Parameters“ ¹ |
| InstallShield (InstallScript) | wie oben, dazu `setup.inx` (übersetztes InstallScript) | – Parameter fehlt: Antwortdatei an einer VM aufzeichnen (`setup.exe /r /f1"C:\setup.iss"`), Installer und `setup.iss` als Ordner laden, `/s /f1"{ordner}\setup.iss"` | Revenera (wie oben) ¹; an `epson665751eu.exe` geprüft |
| WiX Burn | PE-Abschnitt `.wixburn` | `/quiet /norestart` (0, 1641, 3010) | WiX Toolset „Burn Command Line“ ¹ |
| Microsoft-Bootstrapper | `.wixburn` und CompanyName „Microsoft …“ (VC++ Redistributable, .NET-Runtime) | `/install /quiet /norestart` (0, 1638 = neuere Version da, 1641, 3010) | Microsoft Learn „Visual C++ Redistributable“ (Befehlszeile) ¹ |
| virtio-win-Gasttools (I-041) | `.wixburn` und CompanyName „Red Hat …“ bzw. „virtio-win“ im Programm- oder Dateinamen (`virtio-win-guest-tools.exe`) | `/install /quiet /norestart` (0, 1638, 1641, 3010) | WiX Toolset „Burn Command Line“ ¹ (I-041, nur für Test-VMs mit Gastagent) |
| Qt Installer Framework | angehängte Qt-Ressourcen („qres“) mit `config.xml` (`<Installer>`) bzw. „Built with Qt Installer Framework x.y.z“ (Kopf oder `.rdata`) | ab 4.0: `install --root "<TargetDir>" --accept-licenses --accept-messages --default-answer --confirm-command` (0); `<TargetDir>`: `@ApplicationsDirX64@` → `C:\Program Files`, `@ApplicationsDirX86@` → `C:\Program Files (x86)`, `@ApplicationsDir@` je nach 32/64 Bit, `@RootDir@` → `C:\`; andere Variablen (z. B. `@HomeDir@`) bzw. vor 4.0 (nur mit Steuerskript `--script`) → Parameter fehlt | Qt-IFW-Doku „Using Command Line Interface“, „Configuration File“ ¹; an `AraneoInstaller.exe` (IFW 4.6.1) geprüft |
| Advanced Installer | „Caphyon“, „Advanced Installer“, „AI_SETUPEXEPATH“ | `/exenoui /qn /norestart` (0, 1641, 3010) | Advanced Installer „EXE setup file command line“ ¹ |
| InstallAware | „InstallAware“ | `/s` (0, 3010) | InstallAware „Command Line Parameters“ ¹ |
| Wise Installation | „WiseMain“, „Wise Installation“, „Wise Solutions“ | `/s` (0, 3010) | Wise-Handbuch ¹ |
| InstallBuilder (BitRock/VMware) | Manifest „BitRock Installer“, „InstallBuilder“ | `--mode unattended --unattendedmodeui none` (0, 3010) | InstallBuilder-Handbuch „Unattended Installations“ ¹; an Barco Event Master Toolset geprüft |
| Setup Factory | „Setup Factory“, „Indigo Rose“, „irsetup.exe“ | – Parameter fehlt, Hinweis „meist /S“ | ¹ (Parameter je nach Version unsicher) |
| Clickteam Install Creator | „Clickteam“, „Install Creator“ | – Parameter fehlt, Hinweis „/S nur Pro-Version“ | ¹ |
| Smart Install Maker | „Smart Install Maker“ | – Parameter fehlt, Hinweis „vermutlich /s“ | ¹ |
| Actual Installer | „Actual Installer“ | – Parameter fehlt, Hinweis „vermutlich /S“ | ¹ |
| CreateInstall | „CreateInstall“ | – Parameter fehlt, Hinweis „vermutlich -silent“ | ¹ |
| Ghost Installer | „Ghost Installer“, „GhostInstaller“, „Ethalone“ | – Parameter fehlt, Hinweis „vermutlich -s“ | ¹ |
| Squirrel | „Squirrel“ bzw. Versionsinfo `SquirrelAwareVersion` | – „nur von Hand“ | Squirrel.Windows: installiert nach `%LocalAppData%` des angemeldeten Benutzers – als SYSTEM nutzlos |
| IExpress | Versionsinfo `OriginalFilename`/`InternalName` „WEXTRACT“, „IExpress“ | – Parameter fehlt, Hinweis `/Q` (still nur, wenn das enthaltene Programm still läuft) | ¹ |
| 7-Zip-SFX | angehängte Daten mit `;!@Install@!UTF-8!` bzw. `7z BC AF 27 1C`, Manifest „7-Zip Self-extracting“ | – Parameter fehlt: Inhalt prüfen, entpackten Ordner laden | ¹; an `Firefox Installer.exe` geprüft |
| WinRAR-SFX | `Rar!\x1a\x07` in den angehängten Daten, „WinRAR SFX“ | – Parameter fehlt (wie 7-Zip-SFX) | ¹ |
| unbekannt | – | – Parameter fehlt: Herstellerdoku („silent install“, „unattended“), an einer VM testen | – |

¹ **Quelle nicht abgerufen:** Angabe aus dem Gedächtnis des Umsetzungs-Agenten (Ä-043, 18.11.2026), nicht neu in der
Herstellerdoku nachgelesen (kein Internetzugriff im Auftrag). Darum bleiben Typen, deren Parameter nicht sicher
belegbar sind, „Parameter fehlt“ und nennen den vermuteten Parameter nur im Hinweis – ein falscher Parameter liesse
den Installer am Gerät auf eine Eingabe warten (Abbruch erst nach 60 min). Die Kennungen und das Ergebnis sind an den
37 Installern in `NAS/Verteilen/Software` geprüft (Stand 18.11.2026).

**Name, Version, Hersteller** (`publisher`, neu in der Beschreibung): Windows-Programme aus der Versionsinfo
(VS_VERSIONINFO über das Ressourcenverzeichnis, `installerinfo.parse_version_resource`: `ProductName` bzw.
`FileDescription`, `ProductVersion` bzw. `FileVersion` bzw. die Zahlen aus VS_FIXEDFILEINFO, `CompanyName`); ohne
Ressourcenverzeichnis wie bisher Suche im Kopf. NSIS ohne Versionsinfo: feste Texte nach `DisplayName`,
`DisplayVersion`, `Publisher` im entpackten Skript (Registry der Deinstallation; nur plausible Werte – kein
Registry-Name wie „NoModify“, Version mit Punkt, keine Variablen). MSI: Tabelle `Property` (`ProductName`,
`ProductVersion`, `Manufacturer`) mit eigenem Leser für Compound Files ([MS-CFB]: Header, DIFAT, FAT, Mini-FAT,
Verzeichnis) und MSI-Tabellen (Namen der Datenströme kodiert, `_StringPool`/`_StringData`, Codepage, 2- bzw.
3-Byte-Verweise, Spalten hintereinander; Aufbau wie Wine `msi/table.c`, `msi/string.c` ¹) – `msiinfo`/`msidump` werden
nicht gebraucht. Qt IFW: `config.xml` (`Name`, `Version`, `Publisher`, `TargetDir`) und `Updates.xml`
(`ApplicationName`, `ApplicationVersion`) aus den angehängten Qt-Ressourcen (rcc Version 1–3, zlib-gepackte Einträge
entpackt; zstd nicht). MSIX/APPX: `Identity` (`Name`, `Version`, `Publisher` → CN/O) und `Properties`
(`DisplayName`, `PublisherDisplayName`). MSU: „Windows-Update“ und KB-Nummer aus dem Dateinamen. Vorrang: Name aus der
Datei vor dem Datei-/Ordnernamen; Version aus dem Dateinamen, ausser bei MSI, MSP, MSU, MSIX und Qt IFW (Datei
massgebend) oder wenn der Dateiname nur eine Zahl ohne Punkt hat (`companion-satellite-x64-701-…` → 3.3.1 statt 701).
„Setup“/„Installer“ am Ende des Namens fallen weg (`AraneoInstaller` → `Araneo`, `OBS Studio Installer` → `OBS Studio`,
`clean_program`); der Schlüssel für neue Versionen (`key`) bleibt unverändert.

**Hinweis bei „Parameter fehlt“** (`hint` in der Beschreibung, `Entry.hint`): je Typ aus `KINDS` bzw. bei Qt IFW
genauer (Version des Frameworks, Zielordner); bei „unbekannt“ der Verweis auf Herstellerdoku und VM-Test. Er steht
im Fenster unter der Liste („Was tun:“), im Tooltip der Zeile und im Dialog *Bearbeiten …* und verschwindet, sobald
Parameter eingetragen sind. Ältere Einträge ohne `hint` erhalten den Hinweis ihres Typs.

**Neu erkennen** (`software.redetect`, Knopf und Kontextmenü im Fenster): wendet die Erkennung erneut auf den Installer
eines Eintrags an – wie beim Laden (`_fresh_meta`), mit dem ursprünglichen Datei-/Ordnernamen aus `loaded_from`.
Ordnername, Schlüssel (`key`, gespeicherte Auswahlen), Installer im Ordner, `content_sha256`, Herkunft bleiben;
`redetected` hält die Zeit fest. Findet die Erkennung keine Parameter, übernimmt der Eintrag sie wie beim Laden von
einer anderen Version (`_adopt`). Wurde der Eintrag von Hand geändert (`edited`), wirft `redetect` `EditedError`; das
Fenster fragt dann („… neu erkennen?“, *Überschreiben*) und ruft mit `overwrite_edited=True` auf – danach ist
`edited` wieder `false`.

**Neue Version** (`split_name`, `_adopt`): Schlüssel = Datei-/Ordnername ohne Version, Architektur und Füllwörter
(`vlc-3.0.24-win64.exe` → `vlc`, `AcroRdrDC2400221005_de_DE.exe` → `acrordrdc-de-de`), zusätzlich der Programmname.
Wird ein Eintrag geladen und gibt es in der Bibliothek einen mit gleichem Schlüssel bzw. Programmnamen und mit
Parametern (oder Art „nur kopieren“/„nur von Hand“), werden Typ, Parameter, Rückgabewerte, Art und – bei gleichem
Namen – der Installer im Ordner übernommen (`adopted_from` = Name des Eintrags, Hinweis in der Liste). Bei mehreren gilt
die höchste Version. Die alte Version bleibt, bis sie gelöscht wird. Eine gespeicherte Auswahl (Automatisierung,
Vorlagen) mit einem nicht mehr vorhandenen Namen nimmt die neueste Version gleichen Schlüssels (`software.resolve`,
Log „alt → neu (neue Version)“) – das gilt auch für Namen aus der Zeit von `Verteilen\Software`
(`vlc-3.0.24-win64.exe` → `vlc-3.0.24`, `System Tools` → `system-tools`). Gibt es nichts Passendes, steht der Name
als „fehlt in der Bibliothek“ in der Liste und im Log „… fehlt in der Software-Bibliothek – übersprungen“. Leere
Schlüssel (`setup.exe`) übernehmen nie etwas.

**Ablage auf dem Gerät:** `C:\ProgramData\Okula\Software\<Eintrag>\…` (seit Ä-041 immer ein Ordner je Eintrag, auch
bei einer einzelnen Datei; die Beschreibung bleibt auf dem NAS) und das Startskript
`System32\GroupPolicy\Machine\Scripts\Startup\okula-software.cmd/.ps1` (Mechanismus von I-039,
`deploy.install_startup_script(root, script, "okula-software", SOFTWARE_CMD_TEXT)`).
- *Image zurückspielen* (*Danach anpassen*) und Automatisierung (Schritt *Anpassen*, nach dem Anpassen): Agent-Befehl
  `software` – das Tool liest den NAS und überträgt wie *Ordner senden* (SHA-256 je Datei); der Agent sucht genau ein
  Windows (generalisiert oder installiert), schreibt in einen Zwischenordner und tauscht erst am Ende; eine noch nicht
  installierte Auswahl von vorher wird ersetzt. Alter Agent → „Agent zu alt“, Log „Zurückgespielt, aber Software
  nicht übertragen …“.
- *Software installieren …* an einem Gerät mit Windows (Ä-044): derselbe Agent-Befehl `software` auf ein schon
  eingerichtetes Windows – siehe unten „An einem Gerät mit Windows“.
- Direktinstallation: die Dateien kommen auf die Setup-Partition (`okula/software`, Dateien über 4 GB → Fehler,
  FAT32), das Startskript nach `okula/gp`. `install.cmd` kopiert nach `dism`/`bcdboot` mit `xcopy` nach
  `ProgramData\Okula\Software` und richtet das Startskript ein (hat das Image schon eine lokale Richtlinie, werden
  `gpt.ini`/`scripts.ini` nur als `*.okula-nachher` gesichert und nicht verändert – dann startet die Installation nur
  über SetupComplete). `SetupComplete.cmd` ruft danach `okula-software.cmd` auf, falls es noch da ist (läuft vor der
  ersten Anmeldung; nicht bei OEM-Schlüssel, B-013 – dann das Startskript). Agent für die Direktinstallation
  unverändert (die Dateien laufen über den bestehenden Befehl `install`).

**Ablauf am Gerät** (`software.SCRIPT`, PowerShell 5.1, UTF-8 mit BOM):
1. `-Mode Start` (Startskript, SetupComplete, Audit-Modus): Skript nach `ProgramData\Okula\Software` kopieren,
   Startskript löschen und Gruppenrichtlinie zurückbauen (wie I-039, gemeinsam mit *Windows anpassen*), dann eine
   **einmalige geplante Aufgabe** „Okula Software installieren“ anlegen (`Register-ScheduledTask`, Konto SYSTEM
   `S-1-5-18`, höchste Rechte, Auslöser beim Start, Ausführungszeit 12 h) und starten. Das Startskript wartet
   höchstens **9 min** (`START_WAIT` 540 s) auf das Ende – kurze Installationen sind vor der Anmeldung fertig.
   Lässt sich die Aufgabe nicht anlegen, installiert das Startskript direkt (Protokoll nennt die 10-min-Grenze).
2. `-Mode Install` (Aufgabe): Mutex `Global\OkulaSoftware`; Programme in der gewählten Reihenfolge,
   `Start-Process -WindowStyle Hidden -PassThru`, Arbeitsordner = Ordner des Installers, MSI über `msiexec /i`,
   MSP über `msiexec /p`, MSU über `System32\wusa.exe "<Datei>"` (Ä-043; `software.script_kind` nach der Endung);
   MSIX/APPX ohne Prozess über `Add-AppxProvisionedPackage -Online -PackagePath … [-SkipLicense]` (für alle Benutzer,
   auch künftige; Fehler = Ausnahme → „FEHLER“, Abhängigkeiten wie VCLibs nicht automatisch – als eigene Einträge davor);
   1618 (andere Installation läuft) → bis 10 Versuche im Abstand von 30 s; nach **60 min** je Programm wird der Prozess
   beendet („wartet vermutlich auf eine Eingabe“). Erfolgreich = Rückgabewert in der Liste der Beschreibung; 3010/1641
   merken. Jedes Programm in eigenem try/catch – ein Fehler stoppt die übrigen nicht; danach den Eintrag löschen.
   „Nur kopieren“ → `CommonDesktopDirectory\Software\<Ordner>` (ersetzt).
3. Am Ende: Skript und leere Ordner löschen, bei 3010 **ein** Neustart (`shutdown /r /t 60`), dann die Aufgabe
   entfernen. Wird das Gerät mitten drin neu gestartet, setzt die Aufgabe beim nächsten Start fort (erledigte
   Einträge sind gelöscht).
Protokoll `C:\Windows\Temp\okula-software.log`: je Programm `Start`, `ok`/`FEHLER` mit Rückgabewert und Dauer, am Ende
„Ende: N ok, M mit Fehler“.

**10-Minuten-Grenze:** Windows wartet auf Gruppenrichtlinien-Skripte höchstens die Zeit der Richtlinie „Maximale
Wartezeit für Gruppenrichtlinienskripts“ (`MaxGPOScriptWait`, Standard 600 s) und beendet die Skriptverarbeitung dann
(Microsoft Learn, Richtlinie „Specify maximum wait time for Group Policy scripts“). Gewählt: Installation in einer
geplanten Aufgabe, die das Startskript anlegt – sie läuft im Aufgabenplanungsdienst, unabhängig vom Startskript, mit
eigener Ausführungszeit (Microsoft Learn „New-ScheduledTaskSettingsSet -ExecutionTimeLimit“, Standard 72 h, hier 12 h;
„Register-ScheduledTask“, „New-ScheduledTaskPrincipal“). Verworfen: Wartezeit-Richtlinie für den Lauf setzen
(Registry.pol bzw. Richtlinienwert, den das Skript selbst zurücknehmen müsste; verzögert zudem die Anmeldung beliebig
lang), `SetupComplete.cmd` allein (läuft bei OEM-Schlüssel nicht, B-013; nicht nach dem Zurückspielen), eigener
Prozess mit `Start-Process` aus dem Startskript (Prozesse des Skripts beendet Windows beim Ablauf mit, nicht belegt).

**Master (Audit-Modus, I-038):** Mit *Für Master-Image (Audit-Modus)* läuft die Installation beim ersten Start im
Audit-Modus: Im Durchgang auditUser ruft die erste RunSynchronous-Anweisung `SetupComplete.cmd` auf – erst Setup-
Partition weg und C: vergrössern, dann Software (bis 9 min warten, Rest in der Aufgabe) – und erst danach wird
`Panther\unattend.xml` gelöscht (sofort und nach 2 min). Läuft das Startskript der Gruppenrichtlinie schon vorher
(Start in den Audit-Modus), installiert es, und der Aufruf aus SetupComplete findet nichts mehr. Ein Neustart nach
3010 kann die nachgelagerte Löschung (2 min) verhindern; dann liegt die Antwortdatei noch da, der nächste Start im
Audit-Modus läuft auditUser erneut und löscht sie (die Software ist dann schon erledigt) – am Gerät prüfen
([TESTS.md](TESTS.md) Abschnitt 23).

**Generalisiertes Image mit *Danach anpassen*:** Antwortdatei (Name, Key, CopyProfile, Ä-040) und Software sind
unabhängig: CopyProfile wirkt in specialize, die Software installiert das Startskript als SYSTEM – bei einem frisch
zurückgespielten Master erst, wenn Windows die Startskripte verarbeitet (nach bzw. während der Ersteinrichtung; wann
genau, ist am Gerät zu prüfen). Per-Benutzer-Einstellungen der Programme landen damit nicht im Standardprofil.
Windows anpassen (I-039) kann gleichzeitig ausstehen (siehe oben).

**Im Tool:** Liste *Software installieren* (Häkchen, Suchfeld, Programm, Version, Grösse, Status; Gesamtgrösse) in
*OS installieren …* (nur Windows), *Image zurückspielen* unter *Danach anpassen* und im Reiter *Automatisierung*
(Schritt *Anpassen*, `Settings.install_software`, auch in Vorlagen; Rückfrage nennt die Anzahl). Wählbar sind nur
„bereit“ und „nur kopieren“; die Liste zeigt nur die Software-Bibliothek. Pflege in *Extras → Software-Bibliothek …*
(siehe oben). Log des Auftrags nennt die Programme, Verlauf des Geräts „Software: … (wird beim
ersten Start installiert)“. Das Ergebnis am Gerät liest das Tool nicht zurück. Demo-Gerät: drei erfundene
Beispiel-Installer in der Bibliothek des Demo-Speichers (`demostore.ensure_software`, nur solange sie leer ist; frühere
Beispiele in `demo/Verteilen/Software` werden entfernt), der Demo-Agent nimmt den Befehl an und meldet „fertig“.

**Agent:** neuer Befehl `software` (I-020) → **neuer Agent-Stick bzw. Netzwerkstart neu vorbereiten**. Ä-041 und Ä-043
ändern am Agent nichts (kein neuer Stick): Erkennung und Installationsskript entstehen im Tool, der Agent überträgt
nur Dateien und prüft keine Endungen.

### An einem Gerät mit Windows (Ä-044)

Eintrag **„Software installieren …“** im Rechtsklick-Menü des Geräts (unter „Windows anpassen …“), unter *Tools*
(`Soft_ware installieren …`) und als Knopf im Gerätefenster (`ui.on_install_software`). Aufbau wie *Windows anpassen*
(`on_tweak_windows`): Agent verbunden und aktuell (`_ready_agent`), Windows laut Inventar ohne BitLocker
(`devices.windows_disk`, aus `ui.windows_disk` herausgelöst, damit ohne GTK prüfbar) – sonst Meldung „kein Windows
erkannt (oder … BitLocker) – nichts gesendet“; Ablage `root_for(dev)` (NAS bzw. beim Demo-Gerät der Demo-Speicher),
ohne NAS Meldung wie beim Fenster *Software-Bibliothek*. Dialog `software_ui.SoftwareInstallDialog` mit der
bestehenden Liste `SoftwareChooser` (nur „bereit“/„nur kopieren“ wählbar, übrige ausgegraut mit Grund im Tooltip,
Reihenfolge wie in der Bibliothek; Text „beim nächsten Windows-Start“). *Senden* erst mit Auswahl.

Auftrag `jobs.software_work` (Art `software`, Name „Software installieren“, Netzwerk-Auftrag wie *Ordner senden*):
ruft `jobs.send_software` mit der Disk aus dem Inventar und der Auswahl – also denselben Weg wie *Danach anpassen*
(Plan, `software.build_script`, Agent-Befehl `software`, Installer nach `ProgramData\Okula\Software`, Startskript der
lokalen Gruppenrichtlinie). Log mit Programmen und „Wird beim nächsten Windows-Start … installiert“ (`SOFTWARE_NEXT`
statt `SOFTWARE_LATER`); antwortet der Agent `shared`, steht im Log, dass ein *Windows anpassen* noch aussteht.
Verlauf: „Software installieren (VLC media player 3.0.24, …) – wird beim nächsten Start installiert“
(`jobs.software_history`, Programmnamen aus dem Plan). Am Agent wartet es wie *Windows anpassen* auf den nächsten
Start – das Tool startet nicht neu (gleiches Verhalten wie *Windows anpassen*: Hinweis „Gerät neu starten,
Agent-Stick abziehen“ im Dialog und in der Hilfe).

**Zusammen mit *Windows anpassen*:** beide Reihenfolgen gehen über `deploy.install_startup_script`. Das zuerst
abgelegte Skript sichert die Originale (`*.okula-nachher`) und erhöht die Version; das zweite trägt sich nur in
`scripts.ini` ein (`shared`). Erneutes Senden desselben Skripts ersetzt nur Skript bzw. Installer. Beim Start
löscht jedes Skript zuerst sich selbst; `RESTORE_START` (in beiden Skripten) stellt `gpt.ini`/`scripts.ini` erst her,
wenn kein anderes `okula-*.cmd` mehr im Startup-Ordner liegt – das zuletzt laufende räumt auf. Getestet in
`tests/test_software_device.py` (beide Reihenfolgen auf einem Probe-Verzeichnis).

**Agent:** unverändert – der Befehl `software` gibt es seit I-020 und sucht schon jetzt „genau ein Windows
(generalisiert oder installiert)“. **Kein neuer Agent-Stick.**

## Automatisierung

Erfasste Geräte mit eingeschalteter Automatisierung werden **neu aufgesetzt, sobald sie im LAN auftauchen** (Agent-Stick oder Netzwerkstart). Plan und Entscheide: [docs/AUTOMATISIERUNG.md](AUTOMATISIERUNG.md).

- **Ein/aus:** Häkchen in der Spalte **„Auto“** der Geräteliste oder im Gerätefenster, Reiter **„Automatisierung“**. Ist noch nicht alles eingestellt, öffnet das Häkchen den Reiter und sagt, was fehlt.
- **Ablauf:** 30 s Countdown (im Tool und am Bildschirm des Geräts – **Esc** bricht ab, im Tool „Abbrechen“) → Warteschlange → 1 Backup (Option: Benutzerdaten **oder ganze Disk als Disk-Image**) → 2 Image zurückspielen (**Master-Image** aus den markierten oder **eigenes Image**; vorher vollständige Prüfung) → 3 Anpassen (Gerätename, Windows-Schlüssel, Region Schweiz, Konto – läuft immer) → 4 Ordner senden (Option) → 5 Abschluss (Neustart / Herunterfahren / nichts).
- **Kleinere Zieldisk:** Option in Schritt 2 „Image dafür anpassen“ (Standard ein) – sonst bricht die Automatisierung ab, bevor etwas gelöscht wird.
- **Zieldisk** über die Seriennummer: Steckt eine andere Disk im Gerät, bricht die Automatisierung ab, bevor etwas gelöscht wird.
- **Einmal in 3 Tagen:** Nach erfolgreichem Durchlauf schaltet sich das Häkchen aus und 3 Tage später wieder ein (Option „Nach 3 Tagen wieder einschalten“, Standard ein). Die Liste zeigt z. B. „wieder aktiv in 2 Tagen 5 h“.
- **Fehler:** sofort abbrechen, das Gerät bleibt im normalen Agent-Betrieb. Der Fehler steht in der Liste (rot), im Gerätefenster, im Verlauf und am Bildschirm des Geräts („Automatisierung fehlgeschlagen … Gerät neu starten bzw. neu anschliessen“). Kein automatischer neuer Versuch – erst wenn das Gerät neu angeschlossen wird.
- **Gleichzeitig:** höchstens N Geräte (Menü → **Einstellungen …**, Standard 2); weitere warten („wartet, Platz 2 in der Warteschlange“). **Hauptschalter:** **Stopp-Knopf ■** oben über der Geräteliste, rechts neben den Symbolen – im Normalbetrieb wie die anderen Symbole, **rot solange pausiert** (nochmals klicken = weiter; auch in den Einstellungen). Solange pausiert ist, sind die Häkchen „Auto“ und der Schalter im Reiter ausgegraut.
- **Vorlagen:** Im Reiter Einstellungen als Vorlage speichern (z. B. „Schulungs-PC“) und bei anderen Geräten anwenden. Vorlagen enthalten keine Zieldisk (pro Gerät).
- **Protokoll:** Jeder Schritt steht im Log des Auftrags und im Verlauf des Geräts.

> Agent-Stick bzw. Netzwerkstart nach dem Update **einmal neu erstellen bzw. „Vorbereiten“** – Anpassen, Ordner senden und Countdown brauchen den neuen Agent.

## Demo-Gerät (Vorführung)

**Extras → Demo-Gerät (Vorführung)** startet auf dem Server einen simulierten Agent. In der Liste erscheint **DEMO-PC** (Okula Demo-PC, Windows 11 Pro, 512-GB-SSD, Akku, Netzwerkkarten) wie ein echtes, verbundenes Gerät. Alles lässt sich vorführen: Disk-Image, Zurückspielen, Backup, OS installieren, Ordner senden, Windows anpassen (meldet nach wenigen Sekunden „fertig“, legt nichts ab), Anpassen, Netzwerkstart zuerst, Neustart/Herunterfahren (das Gerät ist dann kurz weg) und die Automatisierung mit Countdown. Ein Auftrag dauert etwa 45 s.

- **Fehler vorführen:** Extras → „Demo: nächster Auftrag mit Fehler“ – der nächste Auftrag bricht bei etwa 40 % ab (roter Balken, Meldung im Log).
- **Sicher:** Der Demo-Agent ersetzt alles, was Disks anfasst, durch Attrappen, läuft als normaler Benutzer und ist nur über 127.0.0.1 erreichbar – andere Geräte im Netz sehen nichts. Die Disk `/dev/demo-nvme0n1` gibt es nicht.
- **Ohne NAS:** Alle Daten des DEMO-PC liegen im lokalen Demo-Speicher `~/.config/okula-recovery/demo/` (images/, Backups/, Verteilen/ mit Beispielprojekten) – auch wenn das NAS verbunden ist, wird dort nichts gelesen oder geschrieben. Reiter Images und Backups zeigen ihn als Bereich **„Demo (lokal, nicht auf dem NAS)“**.
- **Fertige Demo-Images:** „DEMO-Master-Win11“ (★ Master, „Image prüfen …“ ergibt ✔) und „DEMO-Image-beschaedigt“ (ein Byte absichtlich verändert, ergibt ✖).
- **Demo-Image:** Ein Disk-Image vom DEMO-PC ist nur wenige MB gross und als Demo markiert. Es lässt sich nur auf den DEMO-PC zurückspielen; ein echtes Gerät und ein Restore-Stick werden verweigert. Umgekehrt stehen echte Images und Backups beim DEMO-PC nicht zur Auswahl. Alte Demo-Images auf dem NAS (vor Ä-027) werden ausgeblendet und per Rechtsklick zum Löschen angeboten.
- **Zurücksetzen:** Extras → „Demo-Daten zurücksetzen …“ löscht den Demo-Speicher (mit Rückfrage); danach sind nur noch die zwei fertigen Images da.
- **Beenden:** Häkchen wieder entfernen (auch beim Schliessen des Tools). Der DEMO-PC bleibt als „nicht verbunden“ in der Liste und lässt sich löschen. Protokoll: `~/.config/okula-recovery/demo-geraet.log`.

## USB klonen und formatieren

Beide unter **Extras**, für USB-Sticks und externe Festplatten am Server. Angeboten werden nur USB- und Wechseldatenträger, nie die Systemdisk. Beides läuft über den Root-Helfer (`okula-make-stick usb-clone` / `usb-format`), zeigt Fortschritt mit Geschwindigkeit und Restzeit und lässt sich abbrechen.

**USB klonen …** – Quelle (wird nur gelesen) auf Ziel (wird gelöscht):
- **Nur belegte Bereiche (empfohlen):** Partitionstabelle mit gleichen IDs, MBR-Bootcode und Bootloader-Lücke werden übernommen, danach pro Partition nur die belegten Blöcke (`partclone -b`, Gerät → Gerät) für FAT, exFAT, NTFS, ext2/3/4, Btrfs, XFS, HFS+ und F2FS. Andere Partitionen (ohne Dateisystem, verschlüsselt) gehen 1:1. Das Ziel darf kleiner sein, solange alle Partitionen passen; logische MBR-Partitionen gehen auch. Boot-Sticks aus Hybrid-ISOs und Datenträger ohne Partitionstabelle kopiert das Tool automatisch 1:1.
- **Alles 1:1:** jeder Sektor, für verschlüsselte oder unbekannte Datenträger; optional danach Vergleich (Quelle und Ziel ganz lesen).
- GPT auf grösserem Ziel: Reserve-Tabelle ans Ende; der restliche Platz bleibt frei. Unterschiedliche Sektorgrössen (512/4096) werden abgewiesen.
- Danach tragen beide dieselben Kennungen – nicht gleichzeitig am selben Windows-PC anschliessen.

**USB formatieren …**:
- **Dateisysteme:** FAT32, exFAT, NTFS (Schnellformat), ext4, Btrfs, XFS, F2FS, ext3, ext2, HFS+, UDF, FAT16 (bis 4 GB) oder nur leeren. Zu jedem steht im Dialog, wofür es passt. Vorschlag: bis 32 GB FAT32, darüber exFAT. Fehlt ein Programm, ist der Eintrag mit dem Paketnamen ausgegraut.
- **Partitionsschema:** MBR (bis 2 TB), GPT oder ohne Partitionstabelle. Über 2 TB schlägt das Tool GPT vor.
- **Name:** wird nach den Regeln des Dateisystems angepasst (FAT: 11 Zeichen, Grossbuchstaben).
- **Vorher:** nichts, Schnelltest auf gefälschte Kapazität, mit Nullen überschreiben oder vollständiger Test (badblocks).
- Bei Linux-Dateisystemen gehört der oberste Ordner danach dem angemeldeten Benutzer (ohne root beschreibbar).

`install.sh` installiert dafür `exfatprogs` und `ntfs-3g` sowie – falls verfügbar – `btrfs-progs`, `xfsprogs`, `f2fs-tools`, `hfsprogs` und `udftools`.

## Restore-Stick (ein Image, ohne Netzwerk)

Rechts im Reiter *Images* (oder Tools → Restore-Stick aus Image …) ein Okula- oder Clonezilla-Image wählen, auch in Ordnern und **„Restore-Stick …“** klicken. Dann Stick und Debian-Live-ISO wählen und **Stick vorbereiten**. Der Dialog zeigt, wie gross der Stick mindestens sein muss: Image plus etwa 2 GB. Zu kleine Sticks sind markiert.

- **Aufbau:** Partition 1 ist FAT32 (`OKULA-REST`) mit Live-System, Boot-Menü „Okula Restore-Stick“ und Restore-Programm. Partition 2 ist ext4 (`OKULADATA`) mit dem Image unter `image/` und der Beschreibung `okula-restore.json`. ext4, weil Partitions-Images oft grösser als 4 GB sind.
- **An der Zielmaschine:** vom Stick booten. Die Bildschirmführung zeigt das Image und alle Disks der Maschine, mit Modell, Grösse, Partitionen und dem Hinweis, ob eine Disk zu klein ist.
  1. Zieldisk per Nummer wählen.
  2. Zur Bestätigung **den Disk-Namen eintippen**. Ohne Bestätigung wird nichts geändert.
  3. Der Stick prüft das Image (SHA256 bzw. `partclone.chkimg`) und spielt es mit Fortschrittsbalken zurück.
  4. Danach: Enter = herunterfahren, `n` = neu starten, `s` = Kommandozeile.
- **Fehler:** Bei einem Fehler (Lesefehler, beschädigtes Image) zeigt der Stick die Meldung und geht zurück zur Disk-Auswahl.
- **Sicherheit:** Der Stick selbst wird nie als Ziel angeboten. Zu kleine oder eingehängte Disks werden abgelehnt. Es gibt bewusst keinen Automatikmodus.

## Projektübersicht

*Extras → Projektübersicht …* (I-034) zeigt den Projektstand als lokale Webseite in Firefox und sammelt
Rückmeldungen. Module: `projekt.py` (Einlesen, Rückmeldungen-Datei, ohne GTK), `projekt_server.py` (HTTP),
Seite in `okula_recovery/assets/projekt/` (`index.html`, `style.css`, `app.js` – keine externen Dateien/CDNs).

**Datenquelle (nur lesen, bei jedem Laden neu):** `<Projektordner>/docs` – Standard `~/recovery_tool_okula` des
aufrufenden Benutzers (unter sudo: Home von `SUDO_USER`), änderbar unter *Menü → Einstellungen … → Projektordner
(Repo)* (`config.json`: `project_dir`, leer = Standard).
- `TESTS.md`: „## Vorbereitung am neuen Server“ und jede `### …`-Gruppe unter „## Offen – am realen System testen“;
  Zeilen `- [ ]`/`- [x]` samt eingerückter Folgezeilen sind Testpunkte, übrige Absätze/Hinweise Gruppentext.
- `AENDERUNGEN.md`: Tabellen 🐞/🔧/💡 (alle Spalten; Zeilen mit mehr Zellen als der Kopf → „Gemeldet“), Kurzübersicht
  (Zähler, „Als Nächstes“, „Vorschlag Reihenfolge“), „📌 Entscheidungen“ (eingeklappt, nur lesen).
- `UEBERGABE.md`: nummerierte Punkte unter „## Offen und als Nächstes“; `prompts/*.md` ohne `VORLAGE.md`: Titel und `Status:`.
- Inline-Markdown (fett, kursiv, `code`, Links) wird nach dem HTML-Escapen umgesetzt; nur `http(s)`-Links werden
  klickbar. Unbekannte Strukturen werden übersprungen, Lesefehler je Datei oben auf der Seite gemeldet.
- Stand: Zeit des Einlesens und `git log -1` des Projektordners.

**Schlüssel:** Bugs/Änderungen/Ideen = ID (`B-004`); Tests `test:<Abschnittsnummer bzw. vorbereitung>:<sha1>`,
Übergabe `uebergabe:offen:<sha1>` – SHA-1 (16 Zeichen) der ersten 200 Zeichen des Texts ohne Markdown, Leerraum und
Gross/Klein; ein angehängter Vermerk „– ✔ …“ zählt nicht. Prompts `prompt:<Datei>`. Rückmeldungen, deren Schlüssel
nicht mehr vorkommt, zeigt die Seite unter „Rückmeldungen ohne Eintrag“ (gespeicherte Textkopie) – nichts geht verloren.

**Datei:** `~/.local/share/okula-recovery/projekt-rueckmeldungen.json` (ausserhalb von Git, Rechte 0600, unter sudo
Besitzer `SUDO_USER`), atomar geschrieben (Temp-Datei + `os.replace`), bei jedem Zugriff neu gelesen. Defekte Datei →
`projekt-rueckmeldungen.defekt-<zeit>.json`, Neubeginn mit Hinweis auf der Seite. Aufbau:
`{"version": 1, "eintraege": {"<schlüssel>": {"art", "bezug", "text", "haken", "kommentar", "prio_wunsch",
"status_wunsch", "geaendert", "uebernommen"}}, "notizen": [{"id", "art", "text", "erstellt", "geaendert",
"uebernommen"}]}`. `haken`: `ok`/`fehler`/`null`; `status_wunsch`: `als Nächstes`, `zurückstellen`, `streichen`,
`erledigt`. Alle Felder leer → Eintrag entfernt. `uebernommen` setzt nur die Projektleitung (Datum, z. B.
`2026-11-10`); jede Änderung setzt es auf `null`. Übernommene Notizen lassen sich nicht mehr ändern/löschen.

**Sicherheit:** `ThreadingHTTPServer` im Tool-Prozess (Daemon-Thread, endet mit dem Tool), nur `127.0.0.1`, freier
Port; Token `secrets.token_urlsafe(24)` pro Tool-Start als erster Pfadteil, sonst 403. Zusätzlich 403 bei fremdem
`Host`-Header (DNS-Rebinding) und fremder Absenderadresse. Schreiben nur per `POST` mit `Content-Type:
application/json` (≤ 256 KB) auf `api/rueckmeldung` bzw. `api/notiz`; Antworten mit CSP `default-src 'self'`,
`no-store`, `Referrer-Policy: no-referrer`. Keine Schreibzugriffe auf Markdown, kein git-Schreiben. Filter- und
Klappzustand nur im `localStorage` des Browsers.

## Hilfe (F1) und Tastenkürzel

**Hilfe → So funktioniert das Tool** (F1): Anleitung im Handbuch-Stil mit Kapiteln in der Reihenfolge des Arbeitsablaufs – Überblick, Wichtige Begriffe, Erste Schritte, Typischer Ablauf, Gerät verbinden, Netzwerkstart, Geräte verwalten, Disk-Image, Image zurückspielen, Datei-Backup, Master-Image, Automatisierung, Ordner senden, Windows anpassen, Inventar/Garantie/Windows 11, Windows/Linux installieren, Sticks, USB klonen/formatieren, Images verwalten, Anzeigen, Neuer Rechner, Probleme lösen, Tastenkürzel, Demo-Gerät. **Suchfeld** oben links (oder **Ctrl+F**): zeigt nur Kapitel mit dem Wort und markiert die Treffer gelb; **Esc** leert die Suche.

| Taste | Wirkung |
|---|---|
| F1 | Hilfe |
| Ctrl+F | In der Hilfe suchen |
| Esc | Suche leeren, sonst Hilfe bzw. Dialog schliessen |
| Ctrl+N | NAS-Verbindung |
| Ctrl+O | Gewähltes Gerät öffnen |
| F5 | Images aktualisieren |
| F11 | Vollbild ein/aus |
| Ctrl+Q | Beenden |
| F2 / Entf / Backspace | Reiter *Dateien*: umbenennen / löschen / eine Ebene zurück |

Neue oder geänderte Funktionen bekommen im selben Commit das passende Kapitel in `okula_recovery/help_window.py`; `tests/test_help.py` prüft Markup, Menüeinträge, Querverweise und dass Hilfe und Oberfläche ohne Anrede auskommen.

## Tests

```bash
python3 -m unittest discover -s tests -t .
```

Die Tests laufen auch als normaler Benutzer ohne `/usr/sbin` im PATH; Tests mit Loop-Devices oder echtem partclone
(Log fest in `/var/log/partclone.log`) brauchen root und werden sonst mit Grund übersprungen.
