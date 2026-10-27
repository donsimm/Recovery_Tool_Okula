# Okula Recovery Tool

Backups und Disk-Images von Maschinen im LAN, gespeichert auf einem NAS.
Server: Debian 13 + Xfce, Python 3 + GTK 3.

![Oberfläche](docs/screenshot.png)

- **Links (NAS):** Verbindung testen (Namensauflösung, Port, Einhängepunkt, Lese-/Schreibrecht, freier Platz), gespeicherte Images (Roh-/partclone-Images, auch komprimiert, sowie Clonezilla-Ordner).
- **Rechts (Maschinen):** Maschinen, die vom USB-Stick gebootet wurden, erscheinen automatisch (Quelle *USB-Agent*). Dazu kommen der Ping-Scan des LAN und manuell erfasste Maschinen.

## Server-Installation (Debian 13)

```bash
sudo apt install python3-gi gir1.2-gtk-3.0 cifs-utils nfs-common iputils-ping iproute2
sudo git clone https://github.com/donsimm/recovery_tool_okula.git /opt/okula-recovery
cd /opt/okula-recovery && python3 -m okula_recovery
```

Autostart nach dem Login: `packaging/okula-recovery.desktop` nach `~/.config/autostart/` kopieren.

### NAS einhängen

Der Button „Einhängen“ ruft `mount <Einhängepunkt>` auf. Dafür braucht es einen Eintrag in `/etc/fstab` mit der Option `user`:

```fstab
# SMB
//nas.local/recovery  /mnt/okula-nas  cifs  user,noauto,credentials=/etc/okula-nas.cred,uid=1000,gid=1000,iocharset=utf8  0 0
# oder NFS
nas.local:/volume1/recovery  /mnt/okula-nas  nfs  user,noauto,_netdev  0 0
```

`/etc/okula-nas.cred` (Rechte `600`): `username=...` und `password=...`.

## USB-Stick (Zielmaschine)

Auf dem Stick läuft ein Live-Debian mit dem Agent (`python3 -m okula_recovery.agent`, systemd-Unit `packaging/okula-agent.service`). Der Agent sendet alle 3 s ein UDP-Broadcast-Beacon an **Port 47811**. Inhalt: Hostname, MAC, Hersteller/Modell und Disks (`lsblk`). Das Tool antwortet, und auf der Konsole der Zielmaschine erscheint „Verbunden“. Kommt 15 s lang kein Beacon, zeigt das Tool die Maschine als offline.

- **Voraussetzung:** Server und Zielmaschine sind im selben Subnetz (Broadcast). In einem anderen Subnetz startet der Agent mit `--server <IP>`.
- **Firewall auf dem Server:** UDP 47811 eingehend freigeben (z. B. `sudo ufw allow 47811/udp`).
- **Hinweis:** Die Beacons sind nicht authentifiziert. Die spätere Steuerverbindung zum Agent bekommt eine Authentifizierung.

Das Live-Image selbst (Debian live-build) ist der nächste Schritt.

## Tests

```bash
python3 -m unittest discover -s tests -t .
```
