# I-001 Auftrag 1b – Nacharbeit VM-Grundlage (Bildschirm, Disk-Zugriff, Netzwerkkarte)

Status: umgesetzt (Commit 2ecc04f) · erstellt 06.11.2026 von der Projektleitung · Freigabe: Dominik 06.11.

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, `docs/VM.md`, `docs/prompts/I-001-1-vm-grundlage.md`
(Auftrag 1, Commit 8d1e851), `okula_recovery/vm.py`, `tests/test_vm.py`. Arbeitsbranch
`claude/blissful-goldberg-mo3xda`; vorher `git pull`. Die Sitzung läuft auf dem Server; `install.sh` ist dort
installiert (libvirt 11.3.0, QEMU 10.0, Brücke `br0` aktiv, Benutzer kann `virsh -c qemu:///system` ohne sudo).
`sudo` gibt es nur mit Passwort – `install.sh` führt Dominik aus.

## Ziel

Die Probe-VMs aus `docs/TESTS.md` Abschnitt 8 laufen mit dem unveränderten Code von `vm.py` nicht. Die
Projektleitung hat am 06.11. am Server die Ursachen gefunden und mit Testkopien der VM-Beschreibung bestätigt.
Diese drei Punkte beheben, damit `Virsh.create()` + `start()` für alle drei Profile ohne Handarbeit funktioniert.

## Befunde der Abnahme (am Server geprüft, 06.11.2026)

1. **Kein SPICE:** `virsh define` → „unsupported configuration: spice graphics are not supported with this QEMU“.
   Ursache: Paket `qemu-system-modules-spice` fehlt (nur „Empfiehlt“ von `qemu-system-x86`, `install.sh` nutzt
   `--no-install-recommends`).
2. **Disk nicht lesbar:** `virsh start` → „Could not open '/var/lib/libvirt/images/okula/<name>.qcow2': Permission
   denied“. Ursache: Disk als `<disk type="volume">` + `<source pool=… volume=…>`; für solche Disks legt
   virt-aa-helper keine AppArmor-Freigabe der Datei an (keine `libvirt-<uuid>.files`). **Bestätigt:** mit
   `<disk type="file">` + `<source file="/var/lib/libvirt/images/okula/<name>.qcow2"/>` starten alle drei Profile.
3. **Netzwerkkarte VM-Legacy:** `rtl8139` hat in Windows 10/11 keinen mitgelieferten Treiber → Windows in VM-Legacy
   ohne Netzwerk.

**Funktioniert bereits (mit Testkopie geprüft, so lassen):** `<product>` bei SATA-Disks (Modellname kommt an),
NVMe per `qemu:override` (UEFI zeigt „UEFI QEMU NVMe Ctrl <Seriennummer>“), Secure Boot (`OVMF_CODE_4M.ms.fd`),
TPM 2.0 `tpm-crb`, SMBIOS Typ 0–3, Brücke `br0` (VM-Legacy bekommt per DHCP eine LAN-Adresse), Netzwerkstart-
Versuch ohne Freigabe ohne Antwort.

## Anforderungen

1. `install.sh`: `qemu-system-modules-spice` zu den VM-Paketen. (virt-viewer und die SPICE-Client-Bibliotheken
   sind schon installiert.)
2. `vm.py`: Disk als Datei im Pool-Verzeichnis (`type="file"`, Pfad `POOL_DIR/<volume_name>`), Anlegen weiterhin
   mit `vol-create-as` im Pool `okula` (Rechte und Grösse verwaltet libvirt). Alle Stellen anpassen, die das
   Volume ansprechen (`delete`, `set_profile`/`vol-resize`); `alias ua-disk0` bleibt (NVMe-Override).
3. Profil **VM-Legacy: Netzwerkkarte `e1000`** (Intel 82540EM, Treiber in Windows enthalten). `NIC_MODELS` um
   `e1000` erweitern; `rtl8139` bleibt erlaubt (nur für Linux sinnvoll – Kommentar im Code).
4. Tests anpassen/ergänzen (`tests/test_vm.py`): Disk-Element `type="file"` mit richtigem Pfad, kein `pool=`
   im XML, VM-Legacy mit `e1000`, `install.sh` enthält `qemu-system-modules-spice`.
5. **Am Server prüfen** (geht ohne sudo): für alle drei Profile `Virsh().create()` → `start()` → Zustand `running`
   → `virsh -c qemu:///system screenshot` zeigt UEFI bzw. SeaBIOS → `poweroff()` → `delete()` → Pool leer. Weil
   SPICE erst nach Dominiks `sudo ./install.sh` geht: für diesen Test die erzeugte XML vor dem `define` in einer
   Testkopie auf VNC umstellen (nicht im Code!) oder den Test nach der Installation wiederholen; im Bericht sagen,
   was wie geprüft wurde. Hinterher keine VMs und keine Volumes zurücklassen.

## Nicht Teil dieses Auftrags

- Oberfläche (Auftrag 2), Hardware vom Gerät (Auftrag 3), Snapshots (Auftrag 4).
- Die 4 bekannten roten Tests (`test_imaging` ×3, `test_jobs` ×1).

## Hinweise zum Code

- `vm.py`: `domain_xml()` (Disk-Block), `Virsh.create/delete/set_profile`, `PROFILES`, `NIC_MODELS`.
- Agent betroffen? **Nein.** Hilfe (F1): keine Änderung (noch keine Oberfläche).

## Abnahmekriterien

- [ ] Alle Tests: nicht mehr als die 4 bekannten roten.
- [ ] Prüfung am Server laut Anforderung 5 für alle drei Profile bestanden.
- [ ] `docs/VM.md`: Profil-Tabelle VM-Legacy → Intel e1000; „Abweichungen und Grenzen“ um Disk als Datei
      (AppArmor) und SPICE-Paket ergänzen; Entscheid „VM-Legacy e1000 statt rtl8139 (Windows-Treiber)“.
- [ ] `docs/TESTS.md` Abschnitt 8: Probe-VM-Schritte auf den neuen Stand (VM-Legacy: Intel-Karte); ein Schritt
      „nach `sudo ./install.sh`: `virt-viewer -c qemu:///system <name>` öffnet den Bildschirm“.
- [ ] `docs/AENDERUNGEN.md`: im „✅ Erledigt“-Protokoll „I-001 Auftrag 1b“ mit Datum.

## Abschluss

1. Commit mit Titel `I-001 (1b/4): VM-Nacharbeit – SPICE-Paket, Disk als Datei, e1000 für VM-Legacy`; pushen.
2. In dieser Datei oben `Status: umgesetzt (Commit <hash>)` setzen.
3. Abschlussmeldung: Änderungen, Testergebnis, Prüfung am Server, Schritte für Dominik
   (`cd ~/recovery_tool_okula && git pull && sudo ./install.sh` – diesmal ohne Netzwerk-Unterbruch, die Brücke steht schon).
