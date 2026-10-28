# Okula Recovery Tool

Backups und Disk-Images von Maschinen im LAN, gespeichert auf einem NAS.
Server: Debian 13 + Xfce, Python 3 + GTK 3.

![Oberfläche](docs/screenshot.png)

- **Menüleiste:**
  - **Menü:** NAS-Verbindung … (Ctrl+N), Agent-USB-Stick erstellen …, Beenden
  - **Tools:** Gerät öffnen (Ctrl+O), Disk-Image erstellen, Image zurückspielen, Inventar neu einlesen, Gerät herunterfahren, Restore-Stick aus Image, Images aktualisieren (F5)
  - **Hilfe:** Tastenkürzel (F1), Über
- **Links (Geräte):** Alle Geräte, die je mit dem Agent-Stick gebootet wurden, in einer Ordnerstruktur. ● grün = verbunden, ● rot = nicht verbunden; dazu Status, Betriebssystem, zuletzt verbunden und IP. Details siehe [Geräte](#geräte).
- **Rechts (NAS):**
  - **Statuszeile:** ● grün = NAS verbunden, ● rot = nicht verbunden bzw. nicht eingerichtet. Daneben der freie Speicher: grün, wenn genug frei ist; rot, wenn weniger als 100 GB frei sind. Das Tool prüft den Status beim Start und danach alle 30 s.
  - **Reiter:** *Images* (Ordnerbaum, siehe unten) und *Dateien* (Dateiverwaltung).
- **NAS-Verbindung einrichten:** Menü → NAS-Verbindung … oder das Zahnrad in der Statuszeile. Das Fenster enthält Protokoll, Host, Freigabe (mit „Freigaben suchen“), Benutzer, Passwort, Einhängepunkt, die Buttons Testen, Einhängen, Aushängen und Speichern sowie die Prüfdetails.

## Server-Installation (Debian 13)

```bash
sudo apt install git
git clone https://github.com/donsimm/recovery_tool_okula.git
cd recovery_tool_okula
git checkout claude/blissful-goldberg-mo3xda   # bis zum Merge
sudo ./install.sh --autostart
```

`install.sh` installiert die Pakete, kopiert das Tool nach `/opt/okula-recovery` (gehört root), legt den Root-Helfer `/usr/local/sbin/okula-make-stick` samt sudo-Regel für deinen Benutzer an, erstellt den Menüeintrag und mit `--autostart` den Start nach dem Login.

Starten: Menü → System → *Okula Recovery Tool* oder `cd /opt/okula-recovery && python3 -m okula_recovery`.
Update: im Repo `git pull`, dann wieder `sudo ./install.sh`.

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

Für NFS gibst du als Freigabe den Exportpfad an (z. B. `/volume1/recovery`) und erlaubst im NAS die IP des Servers.

### Images in Ordner einsortieren

Der Reiter *Images* zeigt einen aufklappbaren Baum:
- **Nicht einsortiert** steht ganz oben, neueste zuerst. Hier landen neue Images und alle, die noch in keinem Ordner liegen, auch bestehende Clonezilla-Images.
- **Eigene Ordner** mit bis zu **3 Ebenen**, z. B. *Kunde › Standort › Gerät*. Anlegen, Umbenennen und Löschen über die Knöpfe oder per Rechtsklick. Ein Ordner lässt sich nur löschen, wenn er leer ist.
- **Icons:** OKULA-Emblem = mit diesem Tool erstelltes Image, orange Disk = Clonezilla-Image, Datei-Symbol = einzelne Image-Datei (`.img`, `.dd` …). Eine Legende steht unter dem Baum.
- **Restore-Stick aus Image …:** Der Knopf steht unter dem Baum und ist aktiv, sobald ein Okula- oder Clonezilla-Image gewählt ist.
- **Einsortieren per Maus:** Ein Image auf einen Ordner ziehen oder zurück auf „Nicht einsortiert“. Ganze Ordner lassen sich ebenfalls in einen anderen Ordner ziehen, ohne die 3 Ebenen zu überschreiten. Rechtsklick → „Nach ‚Nicht einsortiert‘“ geht auch.

Die Ordner sind echte Ordner auf dem NAS unter `Archiv/`, z. B. `Archiv/Kunde A/Standort Zürich/PC-Buchhaltung/<Image>`. Verschieben ist ein Umbenennen auf derselben Freigabe und geht auch bei grossen Images sofort. Nicht einsortierte Images liegen unter `images/` (bzw. bei Clonezilla dort, wo sie abgelegt wurden).

### Dateien auf dem NAS verwalten

Rechts gibt es zwei Reiter:
- **Images:** Alle gefundenen Images. Ein gewähltes Image löschst du mit **Löschen**.
- **Dateien:** Dateiverwaltung der Freigabe. Ordner öffnest du per Doppelklick, ↑ oder Backspace führt eine Ebene zurück. Dazu kommen **Neuer Ordner**, **Umbenennen** (F2) und **Löschen** (Entf, mit Mehrfachauswahl).

Vor dem Löschen zeigt das Tool Anzahl und Grösse der Dateien und fragt nach. Das Tool hat keinen Papierkorb, gelöschte Daten sind weg. Falls im NAS ein Papierkorb für die Freigabe aktiv ist, greift dieser. Alle Aktionen bleiben innerhalb des Einhängepunkts: `..` und Links nach draussen werden abgewiesen, Links werden nie verfolgt.

Das Tool startet maximiert. **F11** schaltet auf Vollbild ohne Titelleiste und wieder zurück.

## Agent-USB-Stick

Menü → **Agent-USB-Stick erstellen …**:

1. Stick einstecken und auswählen. Angeboten werden nur USB- und Wechseldatenträger, nie die Systemdisk.
2. Debian-Live-ISO wählen oder **Herunterladen** klicken. Das Tool lädt das aktuelle `debian-live-…-amd64-standard.iso` von cdimage.debian.org und prüft es gegen `SHA512SUMS`. Die Datei liegt danach unter `~/.cache/okula-recovery/iso`. Einen anderen Mirror setzt du über die Umgebungsvariable `OKULA_DEBIAN_LIVE_URL`.
3. **Stick vorbereiten**. Der Stick wird gelöscht und so aufgebaut:
   - MBR mit einer FAT32-Partition (Label `OKULAAGENT`), darauf der Inhalt des Live-ISO
   - eigene `grub.cfg`; gebootet wird per UEFI über den GRUB des ISO und per BIOS über `grub-install`
   - Agent als zusätzliches Image `/live/okula-agent.squashfs`. live-boot legt es über das Live-System, so sind Agent, systemd-Dienst und Banner beim Booten direkt aktiv. Auf der Zielmaschine wird nichts installiert, alles läuft im RAM.
   - Tastatur `ch`, Locale `de_CH.UTF-8`, Zeitzone `Europe/Zurich`

![Boot-Menü des Agent-Sticks](docs/grub-menu.png)

**Ablauf an der Zielmaschine:** vom Stick booten (Boot-Menü, meist F12/F11/F8). Der Agent sendet alle 3 s ein Beacon auf **UDP 47811**, und zwar per Broadcast und zusätzlich direkt an die Server-IP aus dem Dialog. Das Tool antwortet, die Konsole zeigt „Verbunden“, und das Gerät erscheint links mit grüner LED (neu: unter „Neu / nicht einsortiert“, siehe [Geräte](#geräte)).

- **Unbekannte IP:** Die IP muss niemand kennen. Die Zielmaschine bekommt im Live-System per DHCP eine neue IP, die alte Netzwerkeinstellung des installierten Systems spielt keine Rolle. Gibt es kein DHCP, setzt der Agent nach etwa 25 s eine feste Link-Local-Adresse `169.254.x.y` (aus der MAC) und meldet sich per Broadcast an `255.255.255.255`. Das Tool antwortet dann ebenfalls per Broadcast.
- **Firewall auf dem Server:** UDP 47811 eingehend freigeben (z. B. `sudo ufw allow 47811/udp`).
- **Secure Boot:** Der Stick nutzt die signierte Boot-Kette des Debian-ISO.
- **Hinweis:** Die Beacons sind nicht authentifiziert. Die spätere Steuerverbindung zum Agent bekommt eine Authentifizierung.

## Geräte

Bootet ein Gerät vom Agent-Stick, sammelt der Agent einmal das **Inventar** und das Tool legt das Gerät an bzw. erkennt es wieder.

- **Inventar:** Hersteller, Modell, Seriennummer, System-UUID, Gehäuse, Mainboard, BIOS, Prozessor, RAM, Akku (Zustand in %), Netzwerkkarten (MAC), Disks mit Seriennummer und SMART (Zustand, Betriebsstunden, Temperatur), BitLocker-Partitionen und das **installierte Betriebssystem** (Windows-Version und Computername aus der Registry, Linux aus `os-release`). Dafür hängt der Agent die Partitionen **nur lesend** ein (ext4 `noload`, NTFS `ro`, kein Journal-Replay); auf der Disk wird nichts verändert.
- **Wiedererkennung:** über die System-UUID, sonst Hersteller + Seriennummer, sonst MAC. Nach einem Board-Tausch hilft die Disk-Seriennummer. Eine MAC allein verbindet keine zwei Geräte mit verschiedener UUID (geteilter USB-Netzwerkadapter).
- **Name:** Windows-Computername bzw. Linux-Hostname, sonst Hersteller + Modell. Umbenennen per Stift-Knopf, Rechtsklick oder im Gerätefenster.
- **Ordner:** wie bei den Images, max. 3 Ebenen, per Maus ziehen. Neue Geräte landen oben unter **„Neu / nicht einsortiert“**.
- **Ablage:** lokal auf dem Server unter `~/.local/share/okula-recovery/geraete/` – eine JSON-Datei pro Gerät, Ordner = Ordnerstruktur. Gehört in die Datensicherung des Servers.
- **Getrennt:** Kommt 15 s kein Beacon, wird die LED rot. Das Gerät bleibt in der Liste mit „zuletzt verbunden“. Löschen geht nur bei nicht verbundenen Geräten.

![Gerätefenster mit laufendem Auftrag](docs/geraet.png)

**Gerätefenster** (Doppelklick): Kopf mit LED, Name und Status, Aktionen *Disk-Image erstellen*, *Image zurückspielen*, *Inventar neu einlesen*, *Herunterfahren*, *Neu starten* und die Reiter

- **Aufträge:** alle Aufträge dieser Sitzung mit Fortschrittsbalken, Log des gewählten Auftrags und *Auftrag abbrechen*
- **Übersicht**, **Disks** (inkl. SMART), **Images** (Images dieses Geräts auf dem NAS; Doppelklick = zurückspielen), **Verlauf** (erfasst, verbunden/getrennt, Images, Restores, Herunterfahren – mit Ergebnis) und **Notizen**

**Mehrere Aufträge parallel:** Aufträge laufen im Hintergrund, auch auf mehreren Geräten gleichzeitig und auf verschiedenen Disks desselben Geräts. Pro Disk ist nur ein Auftrag möglich. Die Geräteliste zeigt pro Gerät einen Fortschrittsbalken mit Prozent, Auftrag und geschätzter Restzeit (z. B. „▬▬▭ **48 %** Disk-Image · noch 7 min“; bei mehreren Aufträgen „2 Aufträge“ mit Mittelwert und längster Restzeit). Die Restzeit erscheint nach etwa 10 s Laufzeit. Beim Beenden warnt das Tool, solange Aufträge laufen.

> Nach dem Update den **Agent-Stick neu erstellen** – ältere Sticks liefern kein Inventar und können nur einen Auftrag gleichzeitig.

## Disk-Image erstellen

Links das verbundene Gerät wählen (grüne LED) bzw. im Gerätefenster **„Disk-Image erstellen …“**. Im Dialog Disk und Archivname (vorgeschlagen: Gerätename) wählen und auf **„Image erstellen“** klicken. Der Auftrag läuft im Hintergrund weiter, Fortschritt und Log stehen im Gerätefenster unter *Aufträge*.

- **Disk-Image oder Backup:** Das Disk-Image sichert die ganze Disk: Partitionstabelle, Bootloader und alle Partitionen. Zurückgespielt ist die Maschine wieder genau wie vorher. Ein Datei-Backup (folgt) sichert nur ausgewählte Ordner.
- **Ablage:** `NAS/images/<Name>/<Datum_Zeit>_<disk>/` mit
  - `okula-image.json` (Metadaten, SHA256 je Datei)
  - `<disk>.sfdisk` (Partitionstabelle) sowie `-head.img` und `-tail.img` (erstes und letztes MiB, also MBR/GPT und Bootloader)
  - pro Partition `<part>.<fs>.pcl.zst` (partclone, nur belegte Blöcke, zstd-komprimiert) oder `<part>.dd.img.zst` für unbekannte und verschlüsselte Partitionen (BitLocker, LUKS): Rohkopie aller Blöcke
  - Swap wird nicht gesichert.
- **Datenfluss:** Der Agent liest die Disk nur und streamt über **TCP 47812** (TLS 1.3 mit PSK) zum Tool. Das Tool prüft die SHA256-Summen und schreibt aufs eingehängte NAS. Der Agent bekommt keine NAS-Zugangsdaten.
- **Abbruch und Fehler:** Während der Arbeit heisst der Ordner `….partial`. Bei Abbruch oder Fehler löscht das Tool ihn wieder, und in der Image-Liste erscheinen nur vollständige Images.
- **Schlüssel:** Das Tool erzeugt beim ersten Stick `~/.config/okula-recovery/agent.key` und bettet ihn in jeden Stick ein. Ein Stick von einem anderen Tool wird abgewiesen. Wer den Stick hat, hat auch den Schlüssel, deshalb die Sticks wie Admin-Werkzeug aufbewahren.
- **partclone auf dem Stick:** `partclone` und `zstd` fehlen im Debian-Live-Image. Das Tool lädt sie beim Erstellen des Sticks mit `apt-get download` aus den Paketquellen des Servers (gleiche Debian-Version) und legt nur die fehlenden Pakete in den Agent-Layer. Dafür braucht der Server Internetzugang.

Tipp für Windows: Vorher vollständig herunterfahren (Shift + Herunterfahren), sonst meldet partclone ein „inkonsistentes“ NTFS (Schnellstart/Ruhezustand).

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

**Abschluss:** Danach den Stick abziehen und die Maschine neu starten.

**Einschränkungen:**
- **Grösse:** Die Zieldisk muss mindestens so gross sein wie die Quelldisk. Verkleinern geht nicht.
- **Grössere Zieldisk:** Der zusätzliche Platz bleibt unpartitioniert. Unter Windows kannst du die Partition danach in der Datenträgerverwaltung erweitern.
- **Abbruch:** Ein Abbruch während des Schreibens hinterlässt eine unvollständige Zieldisk. Sie ist erst nach einem vollständigen Durchlauf wieder brauchbar.
- **Gleiche Hardware:** Am besten zurück auf dieselbe oder baugleiche Hardware. Bei anderer Hardware braucht Windows unter Umständen andere Treiber.

### Clonezilla-Images zurückspielen

Bestehende Clonezilla-Images (Modus „savedisk“) erkennt das Tool automatisch. Sie stehen rechts in der Image-Liste und im Dialog „Image zurückspielen“ mit der Kennzeichnung **[Clonezilla]**, bei mehreren gesicherten Disks mit einem Eintrag pro Disk. Den Image-Ordner einfach auf die NAS-Freigabe kopieren, Unterordner sind erlaubt.

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
- **Knopf „Herunterfahren“:** Er steht unter der Geräteliste und im Gerätefenster bereit (dort auch „Neu starten“), mit Rückfrage. Nach dem Auftrag wird nur heruntergefahren, wenn auf dem Gerät kein weiterer Auftrag läuft. Während ein Auftrag läuft, lehnt der Agent das Herunterfahren ab. Auf seinem Bildschirm meldet er „Maschine wird in 5 s heruntergefahren“.

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

## Tests

```bash
python3 -m unittest discover -s tests -t .
```
