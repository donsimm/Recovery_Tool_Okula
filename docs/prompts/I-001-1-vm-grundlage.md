# I-001 Auftrag 1 – VM-Grundlage (Pakete, Netzwerkbrücke, VM-Modul)

Status: umgesetzt (Commit siehe `git log --grep 'I-001 (1/4)'`) · erstellt 06.11.2026 von der Projektleitung · Freigabe: Dominik 06.11.

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, **`docs/VM.md` (Konzept und Entscheide – verbindlich)**,
Eintrag I-001 in `docs/AENDERUNGEN.md`, Abschnitt „Server-Installation“ und „Netzwerkstart“ in `docs/TECHNIK.md`.
Arbeitsbranch `claude/blissful-goldberg-mo3xda`; vorher `git pull`. Die Sitzung läuft direkt auf dem Server
(`~/recovery_tool_okula`); `sudo` ist dort nicht ohne Passwort möglich – `install.sh` führt Dominik selbst aus.

## Ziel

Fundament für die virtuellen Maschinen, noch **ohne Oberfläche**: Nach `sudo ./install.sh` sind QEMU/KVM und libvirt
installiert, der Server hängt über die Netzwerkbrücke `br0` im LAN, und ein Python-Modul kann aus einem
Hardware-Profil eine libvirt-VM erstellen, starten, stoppen und löschen. Auftrag 2 baut darauf die Bedienung im Tool.

## Entscheide aus dem Brainstorming (Dominik, 06.11.2026)

- VMs im LAN sichtbar → Brücke `br0`, angelegt von `install.sh`.
- Agent in der VM über den bestehenden **Netzwerkstart** (kein Stick, keine Agent-ISO).
- Nur Standard-Hardware: SATA/NVMe, Intel e1000e bzw. Realtek rtl8139 – **keine virtio-Geräte**.
- Drei Profile laut Tabelle in `docs/VM.md` (VM-Win11, VM-Legacy, VM-Klein).
- Windows „nicht aktiviert“; kein Key in VMs.

## Anforderungen

1. **Pakete** in `install.sh`: `qemu-system-x86 qemu-utils libvirt-daemon-system libvirt-clients ovmf swtpm
   swtpm-tools virt-viewer`. Den Benutzer (`$TARGET_USER`) in die Gruppe `libvirt` aufnehmen (Hinweis ausgeben,
   dass dafür einmal ab- und wieder angemeldet werden muss). libvirt-Speicherpool `okula` (Typ dir,
   `/var/lib/libvirt/images/okula`, Autostart) anlegen, falls nicht vorhanden. libvirt-Standardnetz `default`
   (NAT) nicht verwenden.
2. **Netzwerkbrücke** als eigenes Skript `packaging/okula-bridge` (`setup` | `status` | `remove`), aufgerufen von
   `install.sh`; Option `sudo ./install.sh --no-bridge` überspringt sie.
   - Nur mit NetworkManager (auf dem Server aktiv; Verbindung „Wired connection 1“ auf `eno2`, IPv4 per DHCP).
     Ohne NetworkManager: Hinweis, nichts ändern.
   - Kabel-Schnittstelle der Standardroute ermitteln (nie WLAN), Bridge-Verbindung `okula-br0` (ifname `br0`,
     STP aus, forward-delay 0) mit **derselben MAC wie die Schnittstelle** (damit DHCP dieselbe IP vergibt) und den
     IPv4/IPv6-Einstellungen der bisherigen Verbindung; Schnittstelle als Port zuordnen; umschalten.
   - **Rückfall:** Hat `br0` nach 45 s keine IPv4-Adresse, alte Verbindung wieder aktivieren, neue Verbindungen
     löschen, deutlich melden – die Installation läuft weiter (ohne VM-Netz).
   - Idempotent: läuft `br0` schon, nichts tun. `remove` stellt den alten Zustand her.
   - Meldungen im Stil von `install.sh` („==> Netzwerkbrücke für virtuelle Maschinen“), Vorgang statt Ich-Form.
3. **Netzwerkstart und Erkennung mit `br0` prüfen:** `pxe.interface_for()` ermittelt die Schnittstelle aus der
   Server-IP – nach dem Umbau ist das `br0`. Sicherstellen, dass eine bereits geschriebene dnsmasq-Konfiguration
   mit `interface=eno2` beim nächsten Start bzw. nach `install.sh` neu erzeugt wird und der Netzwerkstart danach
   funktioniert. Beacons (UDP 47811) und Ping-Scan (`network.local_interfaces`) mit `br0` prüfen.
4. **Modul `okula_recovery/vm.py`** (ohne GTK, gut testbar):
   - `VmProfile` (Dataclass): Name, Firmware (`uefi-sb` | `uefi` | `bios`), TPM, Chipsatz (`q35` | `i440fx`),
     Disk (Bus `nvme` | `sata`, Grösse, Modellname, Seriennummer, Drehzahl für HDD), Netzwerkkarte
     (`e1000e` | `rtl8139`, MAC), CPU (Kerne, Threads, Name), RAM, SMBIOS-Werte (Typ 0/1/2/3: Hersteller, Modell,
     Version, SKU, Familie, Seriennummer, UUID, Board, BIOS-Hersteller/-Version/-Datum, Gehäusetyp).
   - `PROFILES`: die drei Profile aus `docs/VM.md` (Werte genau so). SMBIOS-Hersteller dort „Okula“, Modell = Profilname.
   - `domain_xml(profile) -> str`: libvirt-XML. Firmware über libvirts Auswahl (`<os firmware='efi'>` mit
     `secure-boot`/`enrolled-keys`; `bios` = SeaBIOS), TPM 2.0 `tpm-crb` mit Emulator, Netzwerk `bridge br0`,
     Startreihenfolge Disk → Netzwerk, Grafik SPICE (für virt-viewer, Auftrag 2), `<sysinfo type='smbios'>` +
     `<smbios mode='sysinfo'/>`. CPU-Name und Disk-Modellname: wo libvirt kein Element hat, über
     `<qemu:commandline>`/`<qemu:override>` – falls das mit der installierten libvirt-Version nicht sauber geht,
     weglassen und im Abschlussbericht nennen. Gegen die libvirt-Version von Debian 13 prüfen (NVMe-Bus!).
   - Neue MAC: `52:54:00:xx:xx:xx`, zufällig, eindeutig gegenüber allen bestehenden VMs.
   - Aktionen über `virsh -c qemu:///system` (als Benutzer, Gruppe libvirt): `create` (Volume im Pool `okula`
     per `vol-create-as` qcow2, `define`), `list`, `state`, `start(mode)` mit `normal` | `pxe` (einmal
     Netzwerkstart zuerst) | `iso` (ISO-Pfad als CD-ROM, einmal zuerst), `shutdown` (ACPI), `poweroff`, `delete`
     (mit Disk, Rückfrage ist Sache der Oberfläche), `set_profile` (Änderung bei ausgeschalteter VM).
     Fehler als verständliche Meldungen (Ausnahme mit deutschem Text), nie Traceback nach oben.
5. **Keine Oberfläche** in diesem Auftrag (kein Menü, kein Ordner, kein Fenster).

## Nicht Teil dieses Auftrags

- Ordner „Virtuelle Maschinen“, Knöpfe, Bildschirmfenster, Netzwerkstart-Freigabe der VM-MACs (Auftrag 2).
- Hardware vom Gerät übernehmen, Image einspielen (Auftrag 3). Snapshots (Auftrag 4).
- Die 4 bereits roten Tests (siehe unten) – nicht reparieren, nur nicht verschlimmern.

## Hinweise zum Code

- Root-Helfer-Muster: `packaging/okula-warranty`, `packaging/okula-make-stick` (sh-Wrapper → `python3 -m …`),
  Installation und sudo-Regel in `install.sh`. `okula-bridge` läuft nur aus `install.sh` (root), keine sudo-Regel nötig.
- Netzwerkstart: `okula_recovery/pxe.py` (`interface_for`, dnsmasq-Konfiguration mit `interface=`/`bind-interfaces`).
- Agent betroffen? **Nein** – kein neuer Agent-Stick.
- Ausgangslage Tests (06.11., unveränderter Stand): 378 Tests, **4 rot** – `test_imaging` ConsoleAndPowerTest.
  test_image_shows_progress_on_console, EndToEndTest.test_full_image, EndToEndTest.test_failure_leaves_no_partial,
  `test_jobs` ParallelJobsTest.test_two_disks_in_parallel_same_disk_refused.

## Oberfläche und Texte

- Keine Oberfläche. Meldungen von `install.sh`/`okula-bridge` deutsch, Handbuch-Stil ohne Anrede.
- Hilfe (F1): in diesem Auftrag **keine** Änderung (keine sichtbare Funktion); folgt mit Auftrag 2.

## Abnahmekriterien

- [ ] `tests/test_vm.py`: XML jedes Profils mit ElementTree geprüft (Firmware/Secure Boot/TPM, Chipsatz, Disk-Bus
      und Grösse, NIC-Modell und MAC, Bridge `br0`, SMBIOS-Werte, kein virtio), MAC-Eindeutigkeit, Aktionen mit
      nachgebildetem `virsh` (keine echte libvirt nötig).
- [ ] Tests für `okula-bridge` mit nachgebildetem `nmcli` (Setup, schon vorhanden, Rückfall, `remove`, kein NetworkManager).
- [ ] Test, dass die PXE-Konfiguration bei geänderter Schnittstelle neu erzeugt wird.
- [ ] Alle Tests: nicht mehr als die 4 bekannten roten; `python3 -m unittest discover -s tests -t .`
- [ ] `docs/TECHNIK.md`: Abschnitt „Virtuelle Maschinen – Grundlage“ (Pakete, Brücke, Pool, `vm.py`), bei
      Server-Installation `--no-bridge` und Hinweis „am Server ausführen“.
- [ ] `docs/TESTS.md` unter „Offen“: Schritte für Dominik – `sudo ./install.sh` **am Server** → `br0` hat dieselbe IP
      (`ip -br a`), Internet/NAS/Tool laufen, abmelden/anmelden, `virsh -c qemu:///system list --all` ohne sudo,
      Netzwerkstart eines echten Geräts funktioniert noch; Probe-VM per kurzem Python-Aufruf erstellen, starten
      (`virt-viewer -c qemu:///system <name>`), löschen – genauen Befehl angeben.
- [ ] `docs/VM.md`: Auftrag 1 als umgesetzt markieren, Abweichungen (z. B. CPU-/Disk-Modellname) vermerken.
- [ ] `docs/AENDERUNGEN.md`: I-001 bleibt „in Arbeit“; im „✅ Erledigt“-Protokoll Eintrag „I-001 Auftrag 1“ mit Datum.

## Abschluss

1. Commit(s) mit Titel `I-001 (1/4): VM-Grundlage – Pakete, Netzwerkbrücke, VM-Modul`; pushen auf
   `claude/blissful-goldberg-mo3xda`.
2. In dieser Datei oben `Status: umgesetzt (Commit <hash>)` setzen (im selben Commit).
3. Abschlussmeldung im Chat: was geändert wurde, Testergebnis, Abweichungen vom Prompt, und die Schritte für
   Dominik am Server (`git pull && sudo ./install.sh` – am Server, nicht aus der Ferne; danach ab- und anmelden).
