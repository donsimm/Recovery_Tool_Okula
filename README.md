# Okula Recovery Tool

Backups und Disk-Images von Maschinen im LAN, gespeichert auf einem NAS.
Server: Debian 13 + Xfce, Python 3 + GTK 3.

![Oberfläche](docs/screenshot.png)

- **Links (NAS):** Verbindung testen (Namensauflösung, Port, Einhängepunkt, Lese-/Schreibrecht, freier Platz), gespeicherte Images (Roh-/partclone-Images, auch komprimiert, sowie Clonezilla-Ordner).
- **Rechts (Maschinen):** Maschinen, die vom USB-Stick gebootet wurden, erscheinen automatisch (Quelle *USB-Agent*). Dazu kommen der Ping-Scan des LAN und manuell erfasste Maschinen.

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

### NAS einhängen

Der Button „Einhängen“ ruft `mount <Einhängepunkt>` auf. Dafür braucht es einen Eintrag in `/etc/fstab` mit der Option `user`:

```fstab
# SMB
//nas.local/recovery  /mnt/okula-nas  cifs  user,noauto,credentials=/etc/okula-nas.cred,uid=1000,gid=1000,iocharset=utf8  0 0
# oder NFS
nas.local:/volume1/recovery  /mnt/okula-nas  nfs  user,noauto,_netdev  0 0
```

`/etc/okula-nas.cred` (Rechte `600`): `username=...` und `password=...`.

## Agent-USB-Stick

Button **„Agent-USB-Stick erstellen …“** oben rechts:

1. Stick einstecken und auswählen. Angeboten werden nur USB- und Wechseldatenträger, nie die Systemdisk.
2. Debian-Live-ISO wählen oder **Herunterladen** klicken. Das Tool lädt das aktuelle `debian-live-…-amd64-standard.iso` von cdimage.debian.org und prüft es gegen `SHA512SUMS`. Die Datei liegt danach unter `~/.cache/okula-recovery/iso`. Einen anderen Mirror setzt du über die Umgebungsvariable `OKULA_DEBIAN_LIVE_URL`.
3. **Stick vorbereiten**. Der Stick wird gelöscht und so aufgebaut:
   - MBR mit einer FAT32-Partition (Label `OKULAAGENT`), darauf der Inhalt des Live-ISO
   - eigene `grub.cfg`; gebootet wird per UEFI über den GRUB des ISO und per BIOS über `grub-install`
   - Agent unter `/live/okula`; ein live-config-Hook (`live-config.hooks=medium`) startet ihn beim Booten als Dienst
   - Tastatur `ch`, Locale `de_CH.UTF-8`, Zeitzone `Europe/Zurich`

**Ablauf an der Zielmaschine:** vom Stick booten (Boot-Menü, meist F12/F11/F8). Der Agent sendet alle 3 s ein Beacon auf **UDP 47811**, und zwar per Broadcast und zusätzlich direkt an die Server-IP aus dem Dialog. Das Tool antwortet, die Konsole zeigt „Verbunden“, und die Maschine erscheint rechts mit Hostname `okula-<MAC-Ende>`, Hersteller/Modell und Disks. Kommt 15 s lang kein Beacon, zeigt das Tool die Maschine als offline.

- **Firewall auf dem Server:** UDP 47811 eingehend freigeben (z. B. `sudo ufw allow 47811/udp`).
- **Secure Boot:** Der Stick nutzt die signierte Boot-Kette des Debian-ISO.
- **Hinweis:** Die Beacons sind nicht authentifiziert. Die spätere Steuerverbindung zum Agent bekommt eine Authentifizierung.

## Tests

```bash
python3 -m unittest discover -s tests -t .
```
