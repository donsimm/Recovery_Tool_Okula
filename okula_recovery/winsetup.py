"""Windows direkt auf ein Gerät installieren (Tool-Seite): Plan, Skripte, Antwortdateien.

Ablauf:
1. Der Agent legt auf der Zieldisk an (GPT): EFI (FAT32) · MSR · Windows (NTFS, Marker) · Setup (FAT32, am Ende).
2. Das Tool schickt die Dateien des Windows-Mediums (aus der ISO auf dem NAS) auf die Setup-Partition;
   eine install.wim über 4 GB teilt der Agent in install.swm-Teile.
3. Der Agent setzt per efibootmgr den einmaligen Start (BootNext) auf die Setup-Partition und startet neu.
4. Die Windows-Setup-Umgebung (signiert – Secure Boot geht) startet über autounattend.xml nur okula\\install.cmd:
   dism spielt die gewählte Edition auf, bcdboot richtet den Start ein. Der Setup-Assistent läuft nicht,
   daher auch keine TPM-/Secure-Boot-Prüfung.
5. Erster Start: Anpassungen aus Panther\\unattend.xml; SetupComplete.cmd löscht die Setup-Partition
   und vergrössert C: auf die ganze Disk.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from pathlib import Path

from okula_recovery import udf, winunattend

FAT32_MAX = 4 * 1024**3 - 1
SPLIT_MB = 3800
SETUP_RESERVE = 512 * 1024 * 1024        # FAT32-Verwaltung, Skripte, Rundung
MIN_DISK = 40 * 1000**3                  # Windows 10/11 + Setup-Partition
LETTERS = "C D E F G H I J K L M N O P Q R S T U V W Y Z"
BOOT_LABEL = "Okula Windows-Installation"


class WinSetupError(Exception):
    pass


@dataclass
class Plan:
    install_id: str
    files: list[tuple[str, udf.Entry]]               # (Pfad auf der Setup-Partition, Eintrag in der ISO)
    wim_path: str                                    # z. B. sources/install.wim
    split: bool
    extra: dict[str, str] = field(default_factory=dict)  # weitere Dateien (Text)
    setup_size: int = 0

    @property
    def target_marker(self) -> str:
        return f"okula-{self.install_id}.target"

    def request(self, disk: str) -> dict:
        return {"cmd": "install", "disk": disk,
                "files": [{"path": p, "size": e.size} for p, e in self.files],
                "split": {"path": self.wim_path, "mb": SPLIT_MB} if self.split else None,
                "extra": self.extra, "setup_size": self.setup_size, "target_marker": self.target_marker,
                "boot_label": BOOT_LABEL, "min_disk": MIN_DISK, "reboot": True}


def _crlf(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\n", "\r\n")


def install_cmd(install_id: str, index: int, wim_path: str, split: bool, language: str) -> str:
    """Läuft in der Windows-Setup-Umgebung (cmd, nur ASCII). %1 = Laufwerk der Setup-Partition."""
    win_path = wim_path.replace("/", "\\")
    if split:
        image = '/ImageFile:"%S%:\\sources\\install.swm" /SWMFile:"%S%:\\sources\\install*.swm"'
    else:
        image = f'/ImageFile:"%S%:\\{win_path}"'
    return _crlf(f"""@echo off
rem Okula Recovery Tool - Windows-Direktinstallation ({install_id})
title Okula Recovery Tool - Windows wird installiert
set S=%1
set W=
set LOG=%S%:\\okula\\install.log
for %%L in ({LETTERS}) do if exist %%L:\\okula-{install_id}.target set W=%%L
echo Okula: Setup-Partition %S%:, Windows-Partition %W%: > "%LOG%"
if "%W%"=="" goto fehler
echo.
echo  Okula Recovery Tool: Windows wird auf %W%: installiert - bitte nicht ausschalten.
echo.
format %W%: /fs:ntfs /q /y /v:Windows >> "%LOG%" 2>&1
if errorlevel 1 goto fehler
dism /Apply-Image {image} /Index:{index} /ApplyDir:%W%:\\ >> "%LOG%" 2>&1
if errorlevel 1 goto fehler
mountvol Z: /s >> "%LOG%" 2>&1
bcdboot %W%:\\Windows /s Z: /f UEFI /l {language} >> "%LOG%" 2>&1
if errorlevel 1 goto fehler
mountvol Z: /d >> "%LOG%" 2>&1
mkdir %W%:\\Windows\\Panther >nul 2>&1
copy /y "%S%:\\okula\\unattend.xml" %W%:\\Windows\\Panther\\unattend.xml >> "%LOG%" 2>&1
mkdir %W%:\\Windows\\Setup\\Scripts >nul 2>&1
copy /y "%S%:\\okula\\SetupComplete.cmd" %W%:\\Windows\\Setup\\Scripts\\SetupComplete.cmd >> "%LOG%" 2>&1
echo Okula: fertig >> "%LOG%"
wpeutil reboot
exit /b 0
:fehler
echo FEHLER - Protokoll: %LOG% >> "%LOG%"
notepad "%LOG%"
wpeutil shutdown
""")


def setupcomplete_cmd(install_id: str) -> str:
    """Läuft am Ende der Einrichtung im installierten Windows (als SYSTEM): Setup-Partition weg, C: vergrössern."""
    return _crlf(f"""@echo off
rem Okula Recovery Tool - Aufraeumen nach der Direktinstallation ({install_id})
set S=
for %%L in ({LETTERS.replace("C ", "")}) do if exist %%L:\\okula\\{install_id}.setup set S=%%L
if "%S%"=="" goto ende
> "%TEMP%\\okula-dp.txt" (
  echo select volume %S%
  echo delete partition override
  echo select volume C
  echo extend
)
diskpart /s "%TEMP%\\okula-dp.txt" > "%WINDIR%\\Temp\\okula-aufraeumen.log" 2>&1
del "%TEMP%\\okula-dp.txt"
:ende
""")


def launch_command() -> str:
    """RunSynchronous in der Setup-Umgebung: install.cmd auf der Setup-Partition suchen und starten."""
    return (f"cmd /c for %i in ({LETTERS}) do @if exist %i:\\okula\\install.cmd "
            f"call %i:\\okula\\install.cmd %i")


def plan(iso_path: str | Path, index: int, opts: winunattend.WinOptions) -> Plan:
    """Was auf die Setup-Partition kommt – Dateien aus der ISO plus Skripte und Antwortdateien."""
    install_id = secrets.token_hex(4)
    with udf.UdfImage.open(str(iso_path)) as img:
        entries = [(p, e) for p, e in img.walk() if not e.is_dir]
    wim = next(((p, e) for p, e in entries if p.lower() in ("sources/install.wim", "sources/install.esd")), None)
    if wim is None:
        raise WinSetupError("Keine install.wim/esd im Medium – ist es eine Windows-Installations-ISO?")
    too_big = [p for p, e in entries if e.size > FAT32_MAX and e is not wim[1]]
    if too_big:
        raise WinSetupError(f"Datei grösser als 4 GB: {too_big[0]}")
    split = wim[1].size > FAT32_MAX
    if split and wim[0].lower().endswith(".esd"):
        raise WinSetupError("install.esd über 4 GB kann nicht geteilt werden")
    # eigene Antwortdatei statt einer evtl. mitgelieferten
    files = [(p, e) for p, e in entries if p.lower() not in ("autounattend.xml", "sources/autounattend.xml")]
    language = opts.ui_language or "de-DE"
    system_opts = winunattend.WinOptions(**{**opts.__dict__, "skip_network": True})
    launcher = winunattend.build(opts, pe=True, system=False, launch=launch_command())
    extra = {
        # Setup sucht auf festen Disks in \sources des Mediums, auf Wechselmedien im Wurzelverzeichnis
        "sources/autounattend.xml": launcher,
        "autounattend.xml": launcher,
        "okula/install.cmd": install_cmd(install_id, index, wim[0], split, language),
        "okula/unattend.xml": winunattend.build(system_opts, pe=False, system=True),
        "okula/SetupComplete.cmd": setupcomplete_cmd(install_id),
        f"okula/{install_id}.setup": install_id,
    }
    size = sum(e.size for _p, e in files) + sum(len(t.encode()) for t in extra.values()) + SETUP_RESERVE
    return Plan(install_id, files, wim[0], split, extra, size)


def describe(plan: Plan) -> list[str]:
    total = sum(e.size for _p, e in plan.files)
    lines = [f"{len(plan.files)} Dateien, {total / 1000**3:.1f} GB auf die Setup-Partition "
             f"({plan.setup_size / 1000**3:.1f} GB)"]
    if plan.split:
        lines.append("install.wim über 4 GB – der Agent teilt sie in install.swm-Teile")
    return lines
