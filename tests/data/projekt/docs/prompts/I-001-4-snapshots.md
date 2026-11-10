# I-001 Auftrag 4 – Snapshots der VMs

Status: abgenommen 06.11. (Commit 2dadd10) – Ablauf im Tool noch zu testen (TESTS.md Abschnitt 11) · erstellt 06.11.2026 von der Projektleitung · Freigabe: Dominik 06.11.

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, **`docs/VM.md` (verbindlich, inkl. aller Abweichungen aus
Auftrag 1–3)**, `okula_recovery/vm.py`, `okula_recovery/vm_dialogs.py`, in `ui.py` die VM-Funktionen (`vm_*`,
`start_restore`, `start_install`) und die Automatisierung (`automation.py`, `Engine._execute`). Arbeitsbranch
`claude/blissful-goldberg-mo3xda`; vorher `git pull`. Die Sitzung läuft auf dem Server (libvirt 11.3, QEMU 10.0,
`virsh -c qemu:///system` ohne sudo; `sudo` nur mit Passwort). **Das Tool läuft eventuell parallel** – keine zweite
