# Virtuelle Maschinen (VM) im Tool – Konzept (I-001)

Stand: **in Arbeit** – Konzept mit Dominik festgelegt am 06.11.2026, Umsetzung in 4 Aufträgen
(Prompts `docs/prompts/I-001-*.md`). Auftrag 1 „VM-Grundlage“ umgesetzt 06.11.2026, Nacharbeit 1b am selben Tag,
Auftrag 2 „VMs im Tool“ (Oberfläche) ebenfalls am 06.11.2026, Auftrag 3 „Digitaler Zwilling“ (mit Ä-036) am 06.11.2026.

## Ziel

2–3 virtuelle Maschinen auf dem Server, in der Geräteliste im eigenen Ordner **„Virtuelle Maschinen“**. Zweck:

1. **Master-Image bauen** ohne Referenzgerät: ISO installieren → einrichten → Sysprep → Disk-Image → Master
   ([MASTER-IMAGE.md](MASTER-IMAGE.md)).
2. **Images testen**, bevor sie auf echte Geräte gehen: zurückspielen, starten, prüfen.
3. **Testlabor** für neue Funktionen (Agent, Netzwerkstart, Automatisierung) – zuerst an der VM, dann am echten Gerät.

## Entscheide (Dominik, 06.11.2026)

- **Netzwerk:** VMs sind **im LAN sichtbar** wie echte PCs (Netzwerkbrücke `br0` auf der Netzwerkkarte des Servers).
- **Bildschirm** der VM in einem **eigenen Fenster** (virt-viewer), nicht eingebettet.
- **Windows „nicht aktiviert“** genügt; kein Key in den VMs, der OEM-Key eines Geräts wird nie übernommen.
- **Drei Profile** als Vorlage (unten); zusätzlich **Hardware eines echten Geräts übernehmen** („bestücken“).
- **Identität der Zwillings-VM:** Seriennummer und UUID vom Original **mit Kennzeichen abgewandelt**
  (z. B. `VM-5CG4…`, UUID mit geänderten Stellen); MAC immer eigene. Sonst würde das Tool VM und Gerät
  automatisch zusammenführen (Entscheid „Zusammenführen nur bei sicherer Identität“).
- **Beim Bestücken** das letzte Image des Geräts einspielen – Häkchen, Standard an („digitaler Zwilling“).
- **Brücke `br0`** legt `install.sh` an; diese Installation am Server selbst ausführen (bei einem Fehler ist der
  Server kurz offline).
- **VM-Legacy mit Intel e1000 statt Realtek rtl8139** (Auftrag 1b, 06.11.2026): Für rtl8139 bringt Windows 10/11
  keinen Treiber mit, die VM wäre unter Windows ohne Netzwerk. e1000 (Intel 82540EM) hat einen Treiber in Windows
  und wird auch vom iPXE der SeaBIOS-Firmware unterstützt. rtl8139 bleibt wählbar (nur für Linux sinnvoll).

## Server (Stand 06.11.2026)

Intel i7-9700K (8 Kerne, VT-x, `/dev/kvm` vorhanden) · 31 GB RAM · NVMe 1 TB, 830 GB frei · Netzwerk `eno2` per
DHCP, verwaltet von NetworkManager („Wired connection 1“). QEMU/libvirt noch nicht installiert.
→ 2 VMs gleichzeitig problemlos, 3 gleichzeitig mit kleinen Profilen.

## Technik

- **QEMU/KVM mit libvirt** (`qemu-system-x86`, `libvirt-daemon-system`, `ovmf`, `swtpm`, `virt-viewer`).
  VMs laufen als Systemdienst weiter, auch wenn das Tool geschlossen ist (verträgt sich mit Ä-001 im Papierkorb:
  Aufträge laufen weiterhin im Tool, nur die VM selbst im Dienst).
- Virtuelle Disk = qcow2-Datei auf der Server-SSD (wächst mit dem belegten Platz), nicht auf dem NAS.
- **Agent in der VM über Netzwerkstart** (kein Stick, keine Agent-ISO): Das Tool schaltet die MAC jeder VM
  automatisch frei. Danach ist die VM ein Gerät wie jedes andere (Gerätefenster, Images, Backup, Automatisierung).
- Neustart/Herunterfahren/Einschalten über libvirt statt Wake-on-LAN.
- **Nur Standard-Hardware** nachbilden (SATA/NVMe, Intel e1000e/e1000, Realtek rtl8139 nur für Linux), keine virtio-Treiber –
  sonst läuft ein Image aus der VM auf echten Geräten nicht. Übertragbar auf andere Hardware nur mit Sysprep.

## Profile (Vorlagen)

| VM | Nachgebildet | Firmware | Chipsatz | Disk | Netzwerk | CPU / RAM | Testet vor allem |
|---|---|---|---|---|---|---|---|
| **VM-Win11** | moderner Business-Laptop | UEFI + Secure Boot + TPM 2.0 | Q35 | NVMe 128 GB | Intel e1000e | 4 / 8 GB | Master bauen, Windows 11, Automatisierung |
| **VM-Legacy** | älteres Gerät | BIOS (Legacy, SeaBIOS) | i440FX | SATA-HDD 80 GB | Intel e1000 | 2 / 4 GB | BIOS-Netzwerkstart, Windows 10, alte Hardware |
| **VM-Klein** | Gerät mit kleiner Disk | UEFI ohne Secure Boot | Q35 | SATA-SSD 64 GB | Intel e1000e | 2 / 4 GB | Zurückspielen auf kleinere Disk (Ä-002), Linux |

Jede VM lässt sich nachträglich ändern; weitere VMs mit eigenem Profil sind möglich.

## Hardware von einem Gerät übernehmen

Gerätefenster → **„VM mit dieser Hardware erstellen …“**. Quelle: das gespeicherte Inventar des Geräts
(Beispiel aus einem echten Inventar in Klammern).

| Inventar | Übernahme in die VM |
|---|---|
| `dmi`: Hersteller, Modell, Version, SKU, Familie, Board, BIOS-Hersteller/-Version/-Datum, Gehäusetyp (OEM SHARKBAY, AMI 4.6.5) | ✔ genau (SMBIOS Typ 0/1/2/3) |
| Seriennummern, `product_uuid` | ⚠ abgewandelt mit Kennzeichen (siehe Entscheide) |
| `cpu`: Name, Kerne, Threads (i5-4200U, 2/4) | ✔ Name und Anzahl (begrenzt auf den Server); Leistung = Server-CPU |
| `memory` (4 GB) | ✔, begrenzt durch freien RAM des Servers |
| `disks`: Grösse, `transport` sata/nvme, Modell (120 GB SATA KINGSTON SH103S3120G) | ✔ Grösse genau, Anschluss genau, Modellname soweit QEMU es erlaubt |
| Partitionstabelle `pttype` des Systemdisks (`dos`) | ✔ bestimmt die Firmware: `dos` → BIOS (Legacy), `gpt` → UEFI |
| `platform`: TPM, Secure Boot | ✔ TPM 2.0 / Secure Boot, wenn das Gerät sie hat |
| `network`: Treiber (r8169) | ~ immer Intel (Q35 → e1000e, i440FX → e1000), auch bei Realtek – rtl8139 hat in Windows keinen Treiber; **MAC nie übernehmen** |
| Disk-Inhalt | ✔ optional letztes Image des Geräts einspielen (Standard an) |
| `oem_key` | ✖ bewusst nicht (Lizenz gehört zum Gerät) |
| SMART, Akku, Grafik, WLAN, Sound, Hersteller-BIOS-Einstellungen | ✖ nicht nachbildbar |

Nicht nachbildbar sind auch Eigenheiten echter Hersteller-Firmware (z. B. B-004, HP-UEFI ohne Netzwerkstart).

## Umsetzung in 4 Aufträgen

| # | Auftrag | Inhalt | Prompt |
|---|---|---|---|
| 1 | **VM-Grundlage** ✔ 06.11. (Nacharbeit 1b ✔ 06.11.) | `install.sh`: Pakete, Pool `okula`, Brücke `br0` (`okula-bridge`); `vm.py`: Hardware-Profil → libvirt-Konfiguration, Aktionen über virsh (als Benutzer, kein Root-Helfer nötig); Tests | `I-001-1-vm-grundlage.md`, `I-001-1b-vm-nacharbeit.md` |
| 2 | **VMs im Tool** ✔ 06.11. | Ordner „Virtuelle Maschinen“, „Neue VM …“ mit Profilen, Starten (Normal / Mit Agent / Von ISO), Herunterfahren, Bildschirm, Netzwerkstart-Freigabe, Hardware ändern | `I-001-2-vms-im-tool.md` |
| 3 | **Hardware vom Gerät** ✔ 06.11. | „VM mit dieser Hardware erstellen …“, Identität abwandeln, letztes Image einspielen; Ä-036 leere Disk | `I-001-3-digitaler-zwilling.md` |
| 4 | **Snapshots** | Zustand sichern und zurückholen | folgt |

Kein neuer Agent-Stick nötig (Agent unverändert).

### Abweichungen und Grenzen aus Auftrag 1 (06.11.2026)

- **NVMe:** libvirt 11.3 (Debian 13) hat den Disk-Bus `nvme` erst ab 11.5. Lösung: SATA-Disk, per `qemu:override` zum
  QEMU-Gerät `nvme` umgebaut. Am Server geprüft (06.11.): UEFI zeigt „UEFI QEMU NVMe Ctrl <Seriennummer>“.
- **Modellname der NVMe-Disk:** QEMU 10.0 kennt dafür keine Einstellung → bleibt „QEMU NVMe Ctrl“. SATA-Disks
  bekommen den Modellnamen (`<product>`).
- **CPU-Name:** per `-global host-x86_64-cpu.model-id` (`qemu:commandline`); in den drei Profilen leer = Server-CPU.
  Wird erst mit Auftrag 3 (Hardware vom Gerät) genutzt.
- **Gehäusetyp** (SMBIOS Typ 3, z. B. Notebook) lässt sich in libvirt/QEMU nicht setzen – steht nur im Profil.
- **Einmal-Start** „Netzwerkstart zuerst“ bzw. „Von ISO“: gilt für das Einschalten; ein Neustart *innerhalb* der laufenden
  VM behält die geänderte Reihenfolge (bei ISO z. B. erneut „Press any key to boot from CD“), erst nach dem Ausschalten
  ist sie wieder normal.
- Kein Root-Helfer `okula-vm`: Der Benutzer steuert libvirt über die Gruppe `libvirt` direkt.

### Abweichungen und Grenzen aus Auftrag 1b (06.11.2026)

- **Disk als Datei statt Pool-Volume:** In der VM steht die Disk als `<disk type="file">` mit
  `/var/lib/libvirt/images/okula/<Name>.qcow2`. Bei `<disk type="volume">` legt virt-aa-helper keine AppArmor-Freigabe
  für die Datei an – der Start bricht mit „Could not open …: Permission denied“ ab. Angelegt, vergrössert und gelöscht
  wird die Datei weiterhin über den Pool `okula` (`vol-create-as`, `vol-resize`, `vol-delete`), Rechte und Grösse
  verwaltet libvirt.
- **SPICE-Bildschirm braucht `qemu-system-modules-spice`:** Das Paket ist nur „Empfiehlt“ von `qemu-system-x86`;
  `install.sh` installiert ohne Empfehlungen und nennt es darum ausdrücklich. Ohne es meldet `virsh define`
  „spice graphics are not supported with this QEMU“ (im Tool: „Bildschirm (SPICE) fehlt – sudo ./install.sh …“).
- **Netzwerkkarte VM-Legacy:** Intel e1000 statt Realtek rtl8139 (siehe Entscheide).

### Abweichungen und Grenzen aus Auftrag 2 (06.11.2026)

- **Startreihenfolge Disk → Netzwerk statt fest Netzwerk → Disk** (Entscheid Projektleitung im Prompt): Am Server
  geprüft – nach der Startart „lokal“ beendet sich grub mit `exit`; OVMF (UEFI) startet dann nicht den nächsten
  Eintrag, sondern zeigt das Setup-Menü (auch mit `exit 1`). Ohne Antwort braucht OVMF über eine Minute. SeaBIOS
  startet nach „lokal“ korrekt von der Disk. Lösung ohne Änderung am Netzwerkstart: gespeichert ist Disk → Netzwerk;
  „Einschalten und Agent starten“ startet einmal mit Netzwerk zuerst; sobald der Agent verbunden ist, stellt das Tool
  die laufende VM per QEMU (`qom-set bootindex`) auf Disk zuerst um. Das Ziel des Entscheids bleibt erfüllt: Ein
  Neustart nach dem Zurückspielen (Automatisierung) startet Windows, nicht wieder den Agent. Bei laufender VM stellt
  „Beim nächsten Start den Agent laden“ auf Netzwerk zuerst. Grenze: Ist das Tool geschlossen, während der Agent
  startet, bleibt die laufende VM auf Netzwerk zuerst (UEFI: ein Neustart endet im Setup-Menü; Ausschalten hilft).
- **Bildschirm nach vorne holen:** unter Wayland nicht möglich – ein offenes virt-viewer-Fenster derselben VM wird
  geschlossen und neu geöffnet.
- **Geräteeintrag Umbenennen** ändert nur den Namen im Tool, nicht den libvirt-Namen der VM.

### Abweichungen und Grenzen aus Auftrag 3 (06.11.2026)

- **RAM auf ganze GB aufgerundet** statt „auf MB“: Das Inventar meldet `MemTotal` ohne das Reservat der Firmware
  (SHARKBAY mit 4 GB meldet 3,77 GB). Aufgerundet entspricht der Zwilling dem eingebauten Speicher.
- **Gehäuse-Seriennummer** (`chassis_serial`) als eigenes Profilfeld; bisher übernahm die VM dafür die
  System-Seriennummer (bleibt so, wenn leer).
- **Zweiter Zwilling desselben Geräts:** UUID `0c1a0001-…`, `0c1a0002-…` (sonst lehnen libvirt und die Geräteliste die
  doppelte UUID ab); Name `VM-<Gerät>-2`.
- **Disk-Seriennummer** `VM` + die letzten 18 Zeichen des Originals (QEMU: höchstens 20).
- **Ä-036 – leer:** zusätzlich gilt ein „VM von ISO gestartet“ im Verlauf als mögliche Installation (von ISO lässt
  sich in der VM von Hand installieren, ohne dass das Tool es sieht).
- **Image einspielen** braucht den eingeschalteten Netzwerkstart; sonst ist das Häkchen aus und ausgegraut mit Grund.
- Am Server geprüft (ohne Oberfläche, mit `virsh`): Zwillinge aus den echten Inventaren von CompactPlayer 2
  (SHARKBAY, BIOS/SATA) und IOVERSAL-1 (UEFI/NVMe) angelegt und gestartet – SMBIOS zeigt Hersteller/Modell des
  Originals, Seriennummern `VM-…`, UUID `0c1a0000-…`, Disk-Seriennummer im QEMU-Gerät; `match()` findet das Original
  nicht; danach gelöscht. Den ganzen Ablauf mit Image prüft Dominik im Tool ([TESTS.md](TESTS.md) Abschnitt 10) –
  das Tool lief während der Umsetzung, eine zweite Instanz hätte mit Beacons und Netzwerkstart kollidiert.
