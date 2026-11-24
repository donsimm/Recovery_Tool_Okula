"""Ä-045: Zwei eindeutige Neustart-Knöpfe – „Neustart in Windows“ und „Neustart in den Agent“.

Ohne GTK (testbar). Die Oberfläche (ui.py) holt hier Beschriftungen, Gründe fürs Ausgrauen und die ehrlichen
Hinweise, wenn sich das Startziel am Gerät nicht festlegen lässt.

Wie gesteuert wird:
- VM: Startreihenfolge in QEMU (Disk zuerst bzw. Netzwerk zuerst mit „Agent angefordert“), dann Neustart über den
  Agent oder ACPI – unabhängig davon, was vorher vorgemerkt war.
- Echtes Gerät mit Agent (UEFI): der Agent setzt BootNext (einmalig) auf den Windows-Boot-Manager bzw. auf die
  Startquelle des Agents (Stick oder Netzwerk); beim Netzwerkstart wird zusätzlich „Agent beim nächsten Start“
  gesetzt bzw. abbestellt.
- BIOS-Modus, alter Agent, kein passender Eintrag: nicht steuerbar → Hinweis mit Rückfrage.
"""

from __future__ import annotations

WINDOWS, AGENT = "windows", "agent"
LABELS = {WINDOWS: "Neustart in Windows", AGENT: "Neustart in den Agent"}
TIPS = {WINDOWS: "Startet von der Disk – abgelegte Aufträge (Windows anpassen, Software installieren) laufen dort",
        AGENT: "Startet wieder den Agent (Netzwerkstart bzw. Agent-Stick)"}
# Abfrage nach dem Senden (Windows anpassen, Software installieren)
AFTER_SEND_TITLE = "Jetzt in Windows neu starten?"
LATER = "Später"
AFTER_SEND_KINDS = ("tweak", "software")


def vm_network_first(target: str) -> bool:
    """VM: Netzwerk zuerst nur für den Agent; Windows startet von der Disk."""
    if target not in LABELS:
        raise ValueError(f"Unbekanntes Startziel: {target}")
    return target == AGENT


def why_not(target: str, *, selected: bool = True, is_vm: bool = False, online: bool = False,
            vm_stop_why: str = "", netboot_why: str = "") -> str:
    """Grund, warum der Knopf gerade nicht geht ("" = möglich). vm_stop_why: Grund von vm_why(dev, "stop");
    netboot_why: Grund, warum der Netzwerkstart nicht bereit ist (nur für VMs ohne Agent-Stick wichtig)."""
    if not selected:
        return "Zuerst links ein Gerät wählen"
    if is_vm:
        if not online and vm_stop_why:
            return vm_stop_why
        if target == AGENT and netboot_why:
            return f"{netboot_why} – die VM startet den Agent über den Netzwerkstart"
        return ""
    if not online:
        return "Gerät ist nicht mit dem Agent verbunden – ein laufendes Windows lässt sich nicht aus der Ferne " \
               "neu starten"
    return ""


def confirm_text(target: str, name: str, hardware: str = "", is_vm: bool = False, netboot: bool = False) -> tuple:
    """(Titel, Text, Knopf) der Rückfrage vor dem Neustart."""
    title = f"„{name}“ in Windows neu starten?" if target == WINDOWS else f"„{name}“ in den Agent neu starten?"
    if target == WINDOWS:
        body = ("Das Gerät startet von der Disk. Abgelegte Aufträge (Windows anpassen, Software installieren) laufen "
                "beim Windows-Start.")
        if is_vm:
            body += " Die VM wird dafür auf „Disk zuerst“ gestellt."
    else:
        body = "Das Gerät startet wieder den Agent und verbindet sich danach mit dem Tool."
        if is_vm:
            body += " Die VM wird dafür auf „Netzwerk zuerst“ gestellt, der Agent ist angefordert."
        elif netboot:
            body += " Beim Netzwerkstart ist der Agent angefordert."
    if hardware:
        body = f"{hardware}\n\n{body}"
    return title, body, LABELS[target]


def fallback_text(target: str, message: str, netboot_first: bool = False) -> str:
    """Ehrlicher Hinweis, wenn der Agent das Startziel nicht setzen konnte (BIOS-Modus, alter Agent, kein Eintrag)."""
    lines = [f"Das Startziel lässt sich nicht festlegen: {message.rstrip('.')}."]
    if target == WINDOWS:
        if netboot_first:
            lines.append("Netzwerkstart zuerst: Ohne Auftrag startet das Gerät nach etwa 2 Sekunden von der Disk.")
        lines.append("Läuft der Agent vom Agent-Stick: Stick abziehen, sobald der Bildschirm dunkel wird – dann "
                     "startet Windows.")
    else:
        if netboot_first:
            lines.append("Netzwerkstart zuerst: Der Agent ist angefordert und startet über das Netzwerk.")
        lines.append("Agent-Stick stecken lassen. Startet trotzdem Windows, im Startmenü der Firmware (z. B. F9 "
                     "oder F12) den Stick wählen.")
    return "\n\n".join(lines)


def done_text(target: str, result: dict | None) -> str:
    """Zeile für Verlauf und Statuszeile nach dem Neustart."""
    what = "Neustart in Windows" if target == WINDOWS else "Neustart in den Agent"
    if result and result.get("set"):
        return f"{what} (vom Tool, einmalig über {result.get('label') or 'Boot' + str(result['set'])})"
    if result is not None and result.get("vm"):
        return f"{what} (vom Tool, VM: {'Netzwerk' if target == AGENT else 'Disk'} zuerst)"
    return f"{what} (vom Tool, Startziel nicht festgelegt)"
