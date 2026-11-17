"""Windows direkt auf ein Gerät installieren (Tool-Seite): Plan, Skripte, Antwortdateien.

Ablauf:
1. Der Agent legt auf der Zieldisk an (GPT): EFI (FAT32) · MSR · Windows (NTFS, Marker) · Setup (FAT32, am Ende).
2. Das Tool schickt die Dateien des Windows-Mediums (aus der ISO auf dem NAS) auf die Setup-Partition;
   eine install.wim über 4 GB teilt der Agent in install.swm-Teile.
3. Der Agent setzt per efibootmgr den einmaligen Start (BootNext) auf die Setup-Partition und startet neu.
4. Die Windows-Setup-Umgebung (signiert – Secure Boot geht) startet über autounattend.xml nur okula\\install.cmd:
   dism spielt die gewählte Edition auf, bcdboot richtet den Start ein, bcdedit setzt den Windows Boot Manager
   an die erste Stelle der Firmware-Startreihenfolge (B-015). Der Setup-Assistent läuft nicht,
   daher auch keine TPM-/Secure-Boot-Prüfung.
5. Erster Start: Anpassungen aus Panther\\unattend.xml; SetupComplete.cmd löscht die Setup-Partition
   und vergrössert C: auf die ganze Disk.
   Für ein Master-Image (I-038, audit_mode): Windows startet im Audit-Modus; im Durchgang auditUser laufen das
   Aufräumen (SetupComplete.cmd) und das Löschen von Panther\\unattend.xml.
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
WIN_LABEL = "OKULAWIN"                   # Bezeichnung der Windows-Partition (wininstall.WIN_LABEL, Agent)
PE_CMD = "X:\\Windows\\System32\\cmd.exe"  # Eingabeaufforderung in der Setup-Umgebung
DIR = "dir"   # cmd-Befehl; eigene Konstante, damit die Anrede-Prüfung (tests/test_help.py) ihn nicht meldet


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
    """Läuft in der Windows-Setup-Umgebung (cmd, nur ASCII). %1 = Laufwerk der Setup-Partition.

    Windows-Partition: Markierung okula-<id>.target, sonst genau ein Laufwerk mit Bezeichnung OKULAWIN (B-014) –
    nie ein Laufwerk auf Verdacht. Im Fehlerfall Laufwerksliste ins Protokoll und Hinweis oben im Editor (Ä-039)."""
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
set K=
set N=0
set LOG=%S%:\\okula\\install.log
echo Okula: Installation {install_id}, Setup-Partition %S%: > "%LOG%"
for %%L in ({LETTERS}) do if exist %%L:\\okula-{install_id}.target set W=%%L
if not "%W%"=="" echo Okula: Windows-Partition %W%: - Markierung okula-{install_id}.target >> "%LOG%"
if not "%W%"=="" goto gefunden
rem Markierung fehlt: nur ein einziges Laufwerk mit der Bezeichnung {WIN_LABEL} gilt als Windows-Partition
for %%L in ({LETTERS}) do call :bezeichnung %%L
echo Okula: Markierung okula-{install_id}.target fehlt, Laufwerke mit Bezeichnung {WIN_LABEL}: %N% >> "%LOG%"
if not "%N%"=="1" goto fehler
set W=%K%
echo Okula: Windows-Partition %W%: - Bezeichnung {WIN_LABEL} >> "%LOG%"
:gefunden
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
rem B-015: Windows Boot Manager zuerst - manche Firmware setzt einen eigenen Eintrag fuer die Setup-Partition
rem an die erste Stelle. Fehler hier nur protokollieren, bcdboot hat die Reihenfolge normalerweise schon gesetzt.
echo Okula: Firmware-Startreihenfolge vorher - bcdedit /enum firmware: >> "%LOG%"
bcdedit /enum firmware >> "%LOG%" 2>&1
bcdedit /set {{fwbootmgr}} displayorder {{bootmgr}} /addfirst >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo Okula: Windows Boot Manager an erste Stelle - Rueckgabe %RC% >> "%LOG%"
if not "%RC%"=="0" echo Okula: Startreihenfolge nicht gesetzt - Installation laeuft weiter >> "%LOG%"
echo Okula: Firmware-Startreihenfolge nachher - bcdedit /enum firmware: >> "%LOG%"
bcdedit /enum firmware >> "%LOG%" 2>&1
mkdir %W%:\\Windows\\Panther >nul 2>&1
copy /y "%S%:\\okula\\unattend.xml" %W%:\\Windows\\Panther\\unattend.xml >> "%LOG%" 2>&1
mkdir %W%:\\Windows\\Setup\\Scripts >nul 2>&1
copy /y "%S%:\\okula\\SetupComplete.cmd" %W%:\\Windows\\Setup\\Scripts\\SetupComplete.cmd >> "%LOG%" 2>&1
echo Okula: fertig >> "%LOG%"
wpeutil reboot
exit /b 0
:fehler
echo FEHLER - Protokoll: %LOG% >> "%LOG%"
echo. >> "%LOG%"
echo Laufwerke - diskpart list volume: >> "%LOG%"
> "%TEMP%\\okula-dp.txt" echo list volume
diskpart /s "%TEMP%\\okula-dp.txt" >> "%LOG%" 2>&1
set FEHLT=
for %%L in ({LETTERS}) do call :laufwerk %%L
echo. >> "%LOG%"
echo Nicht vorhanden:%FEHLT% >> "%LOG%"
> "%TEMP%\\okula-kopf.txt" (
  echo ==========================================================================
  echo  FEHLER bei der Windows-Installation - Okula Recovery Tool
  echo.
  echo  Nach dem Schliessen dieses Fensters schaltet sich das Geraet aus.
  echo  Fuer eine Eingabeaufforderung vorher Shift+F10 druecken. Ohne Wirkung:
  echo  Datei - Oeffnen, Dateityp "Alle Dateien", {PE_CMD}
  echo  mit der rechten Maustaste - Oeffnen.
  echo.
  echo  Unten: Ablauf, Laufwerksliste und je Laufwerk Bezeichnung, Inhalt
  echo  und Markierung okula-*.target. Protokoll: %LOG%
  echo ==========================================================================
  echo.
)
copy /y /b "%TEMP%\\okula-kopf.txt"+"%LOG%" "%TEMP%\\okula-install.log" >nul
copy /y /b "%TEMP%\\okula-install.log" "%LOG%" >nul
notepad "%LOG%"
wpeutil shutdown
exit /b 1

:bezeichnung
rem %1 = Laufwerksbuchstabe; zaehlt Laufwerke mit der Bezeichnung {WIN_LABEL} (genaues Wort)
if not exist %1:\\ goto :eof
for /f "tokens=*" %%z in ('vol %1: 2^>nul') do for %%t in (%%z) do if /i "%%t"=="{WIN_LABEL}" (set /a N+=1 & set K=%1)
goto :eof

:laufwerk
rem %1 = Laufwerksbuchstabe; Bezeichnung, Inhalt und Markierung ins Protokoll
if not exist %1:\\ (set FEHLT=%FEHLT% %1:& goto :eof)
echo. >> "%LOG%"
echo ----- Laufwerk %1: >> "%LOG%"
set M=nein
if exist %1:\\okula-*.target set M=ja
echo Markierung okula-*.target: %M% >> "%LOG%"
{DIR} /b %1:\\okula-*.target >> "%LOG%" 2>nul
{DIR} %1:\\ >> "%LOG%" 2>&1
goto :eof
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


# I-038: Ob SetupComplete.cmd auch beim Start in den Audit-Modus läuft, sagt Microsoft nicht eindeutig („After Windows
# is installed but before the logon screen appears“, Microsoft Learn „Add a Custom Script to Windows Setup“). Damit die
# Setup-Partition nicht im Master-Image landet, läuft dasselbe Skript im Audit-Fall zusätzlich im Durchgang auditUser
# (RunSynchronous, dort laut Microsoft gültig; auditSystem kennt kein RunSynchronous). Doppelt ist harmlos: Ohne
# Marker-Datei (Partition schon weg) tut das Skript nichts.
SETUPCOMPLETE = "%WINDIR%\\Setup\\Scripts\\SetupComplete.cmd"
AUDIT_CLEANUP = f'cmd /c "{SETUPCOMPLETE}"'


def system_unattend(opts: winunattend.WinOptions) -> str:
    """Panther\\unattend.xml für den ersten Start nach der Direktinstallation (specialize, oobeSystem bzw. auditUser)."""
    system_opts = winunattend.WinOptions(**{**opts.__dict__, "skip_network": True})
    return winunattend.build(system_opts, pe=False, system=True,
                             audit_commands=[AUDIT_CLEANUP] if opts.audit_mode else None)


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
    launcher = winunattend.build(opts, pe=True, system=False, launch=launch_command())
    extra = {
        # Setup sucht auf festen Disks in \sources des Mediums, auf Wechselmedien im Wurzelverzeichnis
        "sources/autounattend.xml": launcher,
        "autounattend.xml": launcher,
        "okula/install.cmd": install_cmd(install_id, index, wim[0], split, language),
        "okula/unattend.xml": system_unattend(opts),
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
