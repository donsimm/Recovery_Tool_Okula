# Virtuelle Maschinen (VM) im Tool – Konzept (I-001)

Stand: **umgesetzt** – Konzept mit Dominik festgelegt am 06.11.2026, Umsetzung in 4 Aufträgen
(Prompts `docs/prompts/I-001-*.md`). Auftrag 1 „VM-Grundlage“ umgesetzt 06.11.2026, Nacharbeit 1b am selben Tag,
Auftrag 2 „VMs im Tool“ (Oberfläche) ebenfalls am 06.11.2026, Auftrag 3 „Digitaler Zwilling“ (mit Ä-036) am 06.11.2026,
Auftrag 4 „Snapshots“ am 06.11.2026.

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
| **VM-Win11** | moderner Business-Laptop | UEFI + Secure Boot + TPM 2.0 | Q35 | NVMe 256 GB (bis 10.11.2026: 128 GB, Ä-037) | Intel e1000e | 4 / 8 GB | Master bauen, Windows 11, Automatisierung |
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
| 4 | **Snapshots** ✔ 06.11. | Zustand der Disk einfrieren und zurückholen, automatisch vor Zurückspielen/OS installieren/Automatisierung | `I-001-4-snapshots.md` |

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

## Snapshots (Auftrag 4, 06.11.2026)

**Entscheide (Dominik, 06.11.):** von Hand nur bei ausgeschalteter VM, nur die Disk (kein Arbeitsspeicher);
automatisch vor Zurückspielen, OS installieren und Automatisierung (Häkchen „Vorher Snapshot“, Standard an);
unbegrenzt viele, Warnung unter 50 GB frei. Projektleitung: der automatische Snapshot darf bei laufender VM entstehen,
weil dann der Agent läuft und die Disk unbenutzt ist – bei laufendem Windows nie.

### Technik-Entscheid: externe Overlays, vom Tool verwaltet

Am Server mit libvirt 11.3 / QEMU 10.0 geprüft:

| Weg | Ergebnis |
|---|---|
| Interne Snapshots (`snapshot-create-as` ohne `--disk-only`) | bei ausgeschalteten VMs angenommen, auch UEFI – aber bei laufender VM (automatischer Snapshot mit Agent) mit pflash-NVRAM nicht möglich, und ein Disk-Snapshot einer laufenden VM geht nur extern. Für alle Fälle gleich: **extern** |
| libvirt-Snapshots extern (`--disk-only`) anlegen und zurücksetzen | geht (Zurücksetzen seit libvirt 9.9: neues Overlay auf der Snapshot-Datei) |
| libvirt-Snapshot **löschen** (`snapshot-delete`) | **scheitert** – ausgeschaltet wie laufend: „block-commit: Could not open …qcow2: Permission denied“. Ursache: virt-aa-helper schreibt für jede Backing-Datei `deny "<Datei>" w,` ins AppArmor-Profil der VM; block-commit muss aber in die Backing-Datei schreiben, und eine deny-Regel lässt sich in AppArmor nicht übersteuern |
| block-stream (`blockpull`) | geht: schreibt nur in die **oberste** Datei, die übernimmt die Daten ihrer Backing-Dateien |

Darum verwaltet das Tool die Snapshots selbst (`vm.py`, ohne libvirt-Snapshot-Metadaten):

- **Dateien** im Pool-Verzeichnis (AppArmor-Freigabe wie bei der Disk, Lehre aus 1b): `<Name>.qcow2` (ursprüngliche
  Disk) und `<Name>.snap-<n>.qcow2` (Overlays). Ein Snapshot friert die bisherige Disk-Datei ein, die VM schreibt in
  ein neues Overlay darüber (`vol-create-as … --backing-vol`, Sekunden). Für alle drei Firmware-Arten gleich.
- **Liste** als JSON in den Metadaten der VM (eigener Namensraum `https://okula.ch/recovery/vm-snapshots/1`, neben dem
  Profil): Titel, Zeit, automatisch, eingefrorene Datei, Eltern-Snapshot, aktueller Stand, Inventar-Stand fürs Tool.
- **Zurück:** neues Overlay auf der Datei des Snapshots, das bisherige Overlay wird gelöscht. Spätere Snapshots bleiben
  gültig (ihre Dateien ändern sich nie) – auch zu ihnen lässt sich wieder springen.
- **Löschen:** Jede Datei, die direkt auf dem Snapshot aufbaut (folgender Snapshot bzw. aktuelles Overlay), übernimmt
  per `blockpull --base <Eltern-Datei>` seine Daten – in einer **angehaltenen Hilfs-VM** `okula-merge-<Name>` (nur
  diese Disk, kein Netzwerk, `virsh create --paused`, läuft nie). Danach wird die Datei gelöscht. Erst nach geprüftem
  Ergebnis (neue Backing-Datei laut libvirt), sonst bleibt der Snapshot. Dauer: so viele Daten wie der Snapshot selbst
  enthält – beim ältesten (die ganze bisherige Disk) bis zu einigen Minuten.
- **Automatisch bei laufendem Agent:** `snapshot-create-as --no-metadata --disk-only --atomic --diskspec
  sda,snapshot=external,file=…` – libvirt stellt die laufende VM und die gespeicherte Konfiguration auf das neue
  Overlay um; die Liste schreibt `virsh metadata --live --config`.
- Neu-Definieren der VM (Start mit Agent bzw. von ISO, Hardware ändern) übernimmt Disk-Datei und Liste.

**NVRAM (`*_VARS.fd`) und TPM-Zustand werden nicht mitkopiert** – beim Zurückspringen bleiben sie, wie sie sind:
- Secure Boot hängt an den Schlüsseln im NVRAM (PK/KEK/db aus der Vorlage `OVMF_VARS_4M.ms.fd`); die Disk ändert sie
  nicht. Am Server geprüft: VM-Win11-Probe nach dem Zurückspringen im UEFI-Menü „Current Secure Boot State
  **Enabled**“.
- Boot-Einträge im NVRAM, die auf eine nicht mehr vorhandene Partition zeigen (z. B. Zurück auf einen Stand vor der
  Installation), überspringt OVMF; Windows startet über `\EFI\BOOT\BOOTX64.EFI` und legt seinen Eintrag neu an.
- TPM: Schlüssel, die Windows im TPM ablegt (BitLocker, Windows Hello), hängen am Speicher-Stammschlüssel des TPM. Der
  bleibt, solange das TPM nicht gelöscht wird – ein älterer Disk-Stand passt also weiter. Ausnahme: Wurde das TPM nach
  dem Snapshot gelöscht oder änderte ein Windows-Update die Secure-Boot-Sperrliste (dbx im NVRAM) und ist BitLocker
  aktiv, verlangt Windows nach dem Zurückspringen den Wiederherstellungsschlüssel. Für Master-VMs BitLocker darum aus
  lassen (beim Master ohnehin Standard; „OS installieren“ setzt „Keine automatische BitLocker-Verschlüsselung“).
- NVRAM und TPM-Zustand liegen ausserhalb des Pools (`/var/lib/libvirt/qemu/nvram`, `/var/lib/libvirt/swtpm`, nur
  root); Mitkopieren bräuchte einen Root-Helfer (bewusst keiner seit Auftrag 1) – für den Zweck nicht nötig.

### Zusammenspiel

- **VM löschen …** löscht alle Overlays und die Disk (`undefine --remove-all-storage` entfernt nur die oberste Datei;
  den Rest löscht das Tool, auch liegengebliebene `<Name>.snap-*.qcow2`). Am Server geprüft: Pool danach ohne Datei der VM.
- **Hardware ändern …:** Disk vergrössern bei vorhandenen Snapshots gesperrt („zuerst Snapshots löschen“); RAM, Kerne
  und Netzwerkkarte gehen (das Tool definiert die VM neu, libvirt kennt die Snapshots nicht) – am Server geprüft.
  Zurück zu einem Snapshot setzt nur die Disk zurück, nicht die Hardware.
- **Vor-Inventar / Ä-036:** Jeder Snapshot speichert Disks und Systeme aus dem Inventar des Geräteeintrags und ob die
  Disk „leer“ war. Beim Zurückspringen gilt wieder dieser Stand; der Verlaufseintrag trägt `snapshot_blank`, die Prüfung
  „Disk leer“ wertet nur den Verlauf danach aus.
- **Zwillinge** wie jede VM. Das Einspielen des letzten Images beim Erstellen eines Zwillings macht keinen Snapshot
  (die Disk ist dort neu und leer).

### Abweichungen und Grenzen aus Auftrag 4 (06.11.2026)

- **Nicht über libvirts Snapshot-Verwaltung** (siehe Technik-Entscheid): `virsh snapshot-list` zeigt die Snapshots
  des Tools nicht.
- **Löschen nur bei ausgeschalteter VM** (im Prompt nur für Erstellen/Zurück verlangt): Beim Zusammenführen ändert sich
  eine Datei der Kette, die eine laufende VM liest. Während des Löschens ist die VM gesperrt (Einschalten ausgegraut).
- **Grösse je Snapshot** = belegter Platz seiner eingefrorenen Datei (die Änderungen bis zu diesem Snapshot; beim
  ersten die ganze bisherige Disk); unter der Liste die Änderungen seit dem aktuellen Snapshot und die Summe.
- Am Server geprüft (ohne Oberfläche, echter Code, Probe-VMs mit Profil VM-Legacy und VM-Win11, Disk-Inhalt per
  hochgeladenen qcow2-Dateien gesetzt und über die heruntergeladene Kette gelesen): Snapshot → ändern → Start mit Kette
  (AppArmor) → automatischer Snapshot bei laufender VM → ändern → zurück zu A (alter Inhalt) → zurück zum späteren
  Snapshot → RAM ändern (geht), Disk vergrössern (gesperrt) → ältesten und letzten Snapshot löschen (Inhalt bleibt,
  Datei weg) → Start → VM löschen: keine Datei übrig, keine Hilfs-VM. Den Ablauf im Tool prüft Dominik
  ([TESTS.md](TESTS.md) Abschnitt 11).

## VM-Disk beim Zurückspielen vergrössern (Ä-037, 10.11.2026)

Viele Images (Lenovo L15 256/512 GB, Samsung 970 EVO 1 TB) passen nicht auf eine VM mit 128 GB. Ist die Disk der VM
kleiner als die Quelldisk des Images, bietet *Image zurückspielen …* zwei Wege an (Entscheid Dominik 10.11.):

- **VM-Disk auf <N> GB vergrössern und zurückspielen** (Standard): N = Grösse der Quelldisk, aufgerundet auf ganze GB.
  Ein Auftrag: VM herunterfahren (ACPI, nach 60 s hart) → Disk vergrössern (wie *Hardware ändern …*, `vol-resize`) →
  Einschalten und Agent starten → ggf. „Vorher Snapshot“ (erst jetzt – ein Snapshot vorher würde das Vergrössern
  sperren) → Zurückspielen. Das Image bleibt 1:1, kein Umbau.
- **Image an die kleinere Disk anpassen** (Ä-002, [KLEINERE-DISK.md](KLEINERE-DISK.md)), wenn die Daten passen.

Vergrössern geht nicht mit Snapshots oder wenn im Pool `okula` weniger frei ist als die belegten Daten des Images plus
10 % Reserve (mind. 10 GB). Die qcow2-Datei ist dünn: Vergrössern selbst belegt nichts, erst das Zurückspielen
schreibt. Bricht der Auftrag vor dem Zurückspielen ab, bleibt die Disk vergrössert (Daten unverändert); verkleinern
lässt sie sich nicht. Kein Vergrössern im laufenden Betrieb (`blockresize`), keine Änderung am Agent.

Profil **VM-Win11 seit Ä-037 mit 256 GB** („Okula NVMe SSD 256GB“); bestehende VMs behalten ihre Grösse.
Technik: [TECHNIK.md](TECHNIK.md), Abschnitt „VM-Disk beim Zurückspielen vergrössern“. Prüfung: [TESTS.md](TESTS.md)
Abschnitt 13.

### Abweichungen und Grenzen (Ä-037)

- **Grösse der Zieldisk nach dem Vergrössern** wird gegen N GB geprüft (nicht gegen die genaue Quelldisk) – N ist
  aufgerundet und damit mindestens so gross.
- **Fehler beim „Vorher Snapshot“** (nach dem Vergrössern): Auftrag rot, nichts zurückgespielt; der Text lautet wie
  beim normalen Zurückspielen „Snapshot vorher fehlgeschlagen – Auftrag nicht gestartet: …“.
- **Platzprüfung** nutzt die belegten Daten aus dem partclone-Kopf jeder Partition (wie Ä-002); bei Rohkopien die
  ganze Partition. Gelesen wird nur der Kopf, im Hintergrund des Dialogs.
- Die Zahl im Verlauf („von 128 GB auf 513 GB“) ist die aufgerundete Quelldisk, z. B. 513 GB für eine 512-GB-SSD
  (512,1 GB).
