# Virtuelle Maschinen (VM) im Tool – Konzept (I-001)

Stand: **in Arbeit** – Konzept mit Dominik festgelegt am 06.11.2026, Umsetzung in 4 Aufträgen
(Prompts `docs/prompts/I-001-*.md`). Auftrag 1 „VM-Grundlage“ umgesetzt 06.11.2026 (noch ohne Oberfläche).

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
- **Nur Standard-Hardware** nachbilden (SATA/NVMe, Intel e1000e bzw. Realtek rtl8139), keine virtio-Treiber –
  sonst läuft ein Image aus der VM auf echten Geräten nicht. Übertragbar auf andere Hardware nur mit Sysprep.

## Profile (Vorlagen)

| VM | Nachgebildet | Firmware | Chipsatz | Disk | Netzwerk | CPU / RAM | Testet vor allem |
|---|---|---|---|---|---|---|---|
| **VM-Win11** | moderner Business-Laptop | UEFI + Secure Boot + TPM 2.0 | Q35 | NVMe 128 GB | Intel e1000e | 4 / 8 GB | Master bauen, Windows 11, Automatisierung |
| **VM-Legacy** | älteres Gerät | BIOS (Legacy, SeaBIOS) | i440FX | SATA-HDD 80 GB | Realtek rtl8139 | 2 / 4 GB | BIOS-Netzwerkstart, Windows 10, alte Hardware |
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
| `network`: Treiber (r8169) | ~ ähnliches Modell: Realtek → rtl8139, Intel → e1000e; **MAC nie übernehmen** |
| Disk-Inhalt | ✔ optional letztes Image des Geräts einspielen (Standard an) |
| `oem_key` | ✖ bewusst nicht (Lizenz gehört zum Gerät) |
| SMART, Akku, Grafik, WLAN, Sound, Hersteller-BIOS-Einstellungen | ✖ nicht nachbildbar |

Nicht nachbildbar sind auch Eigenheiten echter Hersteller-Firmware (z. B. B-004, HP-UEFI ohne Netzwerkstart).

## Umsetzung in 4 Aufträgen

| # | Auftrag | Inhalt | Prompt |
|---|---|---|---|
| 1 | **VM-Grundlage** ✔ 06.11. | `install.sh`: Pakete, Pool `okula`, Brücke `br0` (`okula-bridge`); `vm.py`: Hardware-Profil → libvirt-Konfiguration, Aktionen über virsh (als Benutzer, kein Root-Helfer nötig); Tests | `I-001-1-vm-grundlage.md` |
| 2 | **VMs im Tool** | Ordner „Virtuelle Maschinen“, „Neue VM …“ mit Profilen, Starten (Normal / Mit Agent / Von ISO), Herunterfahren, Bildschirm, Netzwerkstart-Freigabe | folgt |
| 3 | **Hardware vom Gerät** | „VM mit dieser Hardware erstellen …“, Identität abwandeln, letztes Image einspielen | folgt |
| 4 | **Snapshots** | Zustand sichern und zurückholen | folgt |

Kein neuer Agent-Stick nötig (Agent unverändert).

### Abweichungen und Grenzen aus Auftrag 1 (06.11.2026)

- **NVMe:** libvirt 11.3 (Debian 13) hat den Disk-Bus `nvme` erst ab 11.5. Lösung: SATA-Disk, per `qemu:override` zum
  QEMU-Gerät `nvme` umgebaut. Am realen Server noch nicht gestartet (Test in [TESTS.md](TESTS.md), Abschnitt 8).
  Klappt das nicht, Rückfall auf SATA für VM-Win11 oder warten auf libvirt ≥ 11.5.
- **Modellname der NVMe-Disk:** QEMU 10.0 kennt dafür keine Einstellung → bleibt „QEMU NVMe Ctrl“. SATA-Disks
  bekommen den Modellnamen (`<product>`).
- **CPU-Name:** per `-global host-x86_64-cpu.model-id` (`qemu:commandline`); in den drei Profilen leer = Server-CPU.
  Wird erst mit Auftrag 3 (Hardware vom Gerät) genutzt.
- **Gehäusetyp** (SMBIOS Typ 3, z. B. Notebook) lässt sich in libvirt/QEMU nicht setzen – steht nur im Profil.
- **Einmal-Start** „Netzwerkstart zuerst“ bzw. „Von ISO“: gilt für das Einschalten; ein Neustart *innerhalb* der laufenden
  VM behält die geänderte Reihenfolge (bei ISO z. B. erneut „Press any key to boot from CD“), erst nach dem Ausschalten
  ist sie wieder normal.
- Kein Root-Helfer `okula-vm`: Der Benutzer steuert libvirt über die Gruppe `libvirt` direkt.
