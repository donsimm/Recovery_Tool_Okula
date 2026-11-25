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
Ä-046 „Windows anpassen“: install.cmd setzt nach dism die Richtlinien vor der ersten Anmeldung offline (reg load), das
Skript läuft als Startskript bzw. zuletzt aus SetupComplete.cmd (nach der Software) – nicht beim Master (Audit-Modus).
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
    nas_files: list[tuple[str, int, Path]] = field(default_factory=list)  # I-020: (Pfad Setup-Partition, Grösse,
    #                                                                       Quelle auf dem NAS) – Software
    software: list = field(default_factory=list)                         # software.Entry – gewählte Programme
    tweak: dict | None = None                                           # Ä-046: Auswahl „Windows anpassen“

    @property
    def target_marker(self) -> str:
        return f"okula-{self.install_id}.target"

    def request(self, disk: str) -> dict:
        return {"cmd": "install", "disk": disk,
                "files": [{"path": p, "size": e.size} for p, e in self.files]
                + [{"path": p, "size": size} for p, size, _src in self.nas_files],
                "split": {"path": self.wim_path, "mb": SPLIT_MB} if self.split else None,
                "extra": self.extra, "setup_size": self.setup_size, "target_marker": self.target_marker,
                "boot_label": BOOT_LABEL, "min_disk": MIN_DISK, "reboot": True}


def _crlf(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\n", "\r\n")


SOFTWARE_COPY = """\
rem I-020: Software nach ProgramData kopieren
if not exist "%S%:\\okula\\software" goto ohnesoftware
echo Okula: Software wird nach %W%:\\ProgramData\\Okula\\Software kopiert >> "%LOG%"
xcopy "%S%:\\okula\\software" "%W%:\\ProgramData\\Okula\\Software\\" /e /i /h /k /y /q >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo Okula: Software kopiert - Rueckgabe %RC% >> "%LOG%"
rem B-028: Kopierfehler bricht ab - sonst loescht SetupComplete die Setup-Partition samt Installern
if not "%RC%"=="0" echo Okula: FEHLER - Software nicht vollstaendig kopiert >> "%LOG%"
if not "%RC%"=="0" goto fehler
:ohnesoftware
"""

# I-020, Ae-046: Startskripte (Software installieren, Windows anpassen) der lokalen Gruppenrichtlinie einrichten
STARTUP_COPY = """\
rem I-020/Ae-046: Startskripte der lokalen Gruppenrichtlinie einrichten (Software, Windows anpassen)
if not exist "%S%:\\okula\\gp" goto ohnestartskript
set OKGP=%W%:\\Windows\\System32\\GroupPolicy
set OKF=0
if exist "%OKGP%\\gpt.ini" copy /y "%OKGP%\\gpt.ini" "%OKGP%\\gpt.ini.okula-nachher" >> "%LOG%" 2>&1
if exist "%OKGP%\\Machine\\Scripts\\scripts.ini" copy /y "%OKGP%\\Machine\\Scripts\\scripts.ini" \
"%OKGP%\\Machine\\Scripts\\scripts.ini.okula-nachher" >> "%LOG%" 2>&1
if exist "%OKGP%\\gpt.ini" (echo Okula: lokale Gruppenrichtlinie im Image vorhanden - Startskripte laufen ueber \
SetupComplete >> "%LOG%") else (xcopy "%S%:\\okula\\gp" "%OKGP%\\" /e /i /h /k /y /q >> "%LOG%" 2>&1 || set OKF=1)
xcopy "%S%:\\okula\\gp\\Machine\\Scripts\\Startup" "%OKGP%\\Machine\\Scripts\\Startup\\" /e /i /h /k /y /q \
>> "%LOG%" 2>&1 || set OKF=1
echo Okula: Startskripte eingerichtet - Fehler %OKF% >> "%LOG%"
rem B-028: ohne Startskript wuerde weder Software installiert noch Windows angepasst - abbrechen
if not "%OKF%"=="0" echo Okula: FEHLER - Startskripte nicht vollstaendig kopiert >> "%LOG%"
if not "%OKF%"=="0" goto fehler
:ohnestartskript
"""

# ---------- Ae-046: Windows anpassen bei der Direktinstallation ----------
#
# Windows wartet bei der Anmeldung nicht auf Startskripte (B-020). Was vor der ersten Anmeldung wirken muss
# (Startmenü-Richtlinie + StartPins.json, Widgets, Sperrbildschirm, Microsoft-Benutzererfahrungen – dieselben Werte wie
# deploy.tweak_offline), setzt install.cmd darum gleich nach dism offline im Hive SOFTWARE des neuen Windows
# (reg load/add/unload, wie im Microsoft-Learn-Lab „Windows S mode deployment“ an einem aufgespielten Image). Windows
# ist dann noch nie gestartet: kein Benutzerprofil, also auch keine start2.bin, die umbenannt werden müsste – die Marke
# start-offline.ok (source=setup) sagt dem Skript, dass nichts zurückzusetzen ist. Gilt auch mit OEM-Schlüssel (B-013).
# Die übrigen Einstellungen setzt das Skript am Ende der Einrichtung aus SetupComplete.cmd (als SYSTEM, vor dem
# Anmeldebildschirm laut Microsoft Learn „Add a Custom Script to Windows Setup“), nach der Software: Store-Apps
# entfernen und Dienste abschalten sollen keine laufende Installation stören (z. B. Druckwarteschlange für
# Druckertreiber). Mit OEM-Schlüssel läuft SetupComplete.cmd nicht – dann das Startskript (Reihenfolge wie in
# scripts.ini: Software, danach Windows anpassen).

TWEAK_SETUP = "okula/tweak"                       # auf der Setup-Partition: StartPins.json
TWEAK_HIVE = "HKLM\\OKULASW"                      # Hive SOFTWARE des neuen Windows, nur während install.cmd
SOFTWARE_WAIT_MIN = 30                            # SetupComplete: so lange wartet Windows anpassen auf die Software
SOFTWARE_WAIT_STEP = 15                           # s zwischen zwei Abfragen der geplanten Aufgabe


def _reg_add(key: str, name: str, kind: str, data: str, flag: str = "TWF") -> str:
    return (f'reg add "{TWEAK_HIVE}\\{key}" /v {name} /t {kind} /d {data} /f >> "%LOG%" 2>&1\n'
            f"if errorlevel 1 set {flag}=1\n")


def tweak_offline_cmd(offline: dict) -> str:
    """Block für install.cmd (nur ASCII): Richtlinien aus wintweaks.offline_request offline setzen – Fehler nur im
    Protokoll (install.log und C:\\Windows\\Temp\\okula-windows-anpassen.log), die Installation läuft weiter; das Skript
    setzt dieselben Werte beim ersten Start nochmals."""
    from okula_recovery import deploy
    if not offline:
        return ""
    done = [what for key, what in (("widgets", "Widgets aus"), ("lock_screen_off", "kein Sperrbildschirm"),
                                   ("consumer_off", "Microsoft-Benutzererfahrungen aus")) if offline.get(key)]
    # B-022: gesetzt heisst nicht wirksam – ob die Gruppenrichtlinie greift, steht beim Baustein Startmenue des Skripts
    start_text = (", " if done else "") + ("Startmenue-Richtlinie mit festen Kacheln (Wirkung: siehe Zeile Startmenue "
                                           "beim ersten Start)")
    lines = [
        "rem Ae-046: Windows anpassen - Richtlinien vor dem ersten Start offline setzen (wie der Agent, B-020/B-021)",
        'set "TWLOG=%W%:\\Windows\\Temp\\okula-windows-anpassen.log"',
        'mkdir "%W%:\\Windows\\Temp" >nul 2>&1',
        "set TWF=0",
        "set TWB=0",
        'set "TWSM="' if done else 'set "TWSM=keine Richtlinie"',
        'echo Okula: Windows anpassen - Richtlinien vor dem ersten Start >> "%LOG%"',
        f'reg load {TWEAK_HIVE} "%W%:\\Windows\\System32\\config\\SOFTWARE" >> "%LOG%" 2>&1',
        "if errorlevel 1 goto twfehler",
        f'for /f "tokens=1,3" %%a in (\'reg query "{TWEAK_HIVE}\\Microsoft\\Windows NT\\CurrentVersion" '
        f'/v CurrentBuild 2^>nul\') do if /i "%%a"=="CurrentBuild" set TWB=%%b',
        'echo Okula: Windows-Build %TWB% >> "%LOG%"',
    ]
    text = "\n".join(lines) + "\n"
    if offline.get("start_pins"):
        okula = "%W%:\\ProgramData\\Okula"
        marker = f'"{okula}\\{deploy.START_MARKER}"'
        text += (f"if %TWB% LSS {deploy.START_GPO_BUILD} goto twaltstart\n"
                 "set TWS=0\n"
                 f'mkdir "{okula}" >nul 2>&1\n'
                 f'copy /y "%S%:\\{TWEAK_SETUP.replace("/", chr(92))}\\{deploy.START_PINS_FILE}" '
                 f'"{okula}\\{deploy.START_PINS_FILE}" >> "%LOG%" 2>&1\n'
                 "if errorlevel 1 set TWS=1\n"
                 + _reg_add(deploy.EXPLORER_KEY, "ConfigureStartPins", "REG_DWORD", "1", "TWS")
                 + _reg_add(deploy.EXPLORER_KEY, "ConfigureStartPinsJSON", "REG_EXPAND_SZ",
                            '"' + deploy.START_PINS_PATH.replace("%", "%%") + '"', "TWS")
                 + 'if not "%TWS%"=="0" set TWF=1\n'
                 'if not "%TWS%"=="0" goto twnachstart\n'
                 f"> {marker} echo stamp=setup\n"
                 f">> {marker} echo profiles=0\n"
                 f">> {marker} echo source=setup\n"
                 f'set "TWSM={start_text}"\n'
                 "goto twnachstart\n"
                 ":twaltstart\n"
                 '>>"%TWLOG%" echo %DATE% %TIME%  Startmenue: Windows-Build %TWB% vor 24H2 - setzt nur das Skript '
                 "beim ersten Start\n"
                 ":twnachstart\n")
    if offline.get("widgets"):
        text += _reg_add(deploy.DSH_KEY, "AllowNewsAndInterests", "REG_DWORD", "0")
    if offline.get("lock_screen_off"):
        text += _reg_add(deploy.LOCK_KEY, "NoLockScreen", "REG_DWORD", "1")
    if offline.get("consumer_off"):
        text += _reg_add(deploy.CLOUD_KEY, "DisableWindowsConsumerFeatures", "REG_DWORD", "1")
    text += "\n".join((
        f'reg unload {TWEAK_HIVE} >> "%LOG%" 2>&1',
        "if errorlevel 1 set TWF=1",
        'if not "%TWF%"=="0" goto twfehler',
        f'>>"%TWLOG%" echo %DATE% %TIME%  ok      Vor dem ersten Start gesetzt - Setup-Umgebung, Windows-Build %TWB%: '
        f"{', '.join(done)}%TWSM%",
        'echo Okula: Windows anpassen - Richtlinien gesetzt >> "%LOG%"',
        "goto twende",
        ":twfehler",
        f"reg unload {TWEAK_HIVE} >nul 2>&1",
        '>>"%TWLOG%" echo %DATE% %TIME%  Hinweis Richtlinien vor dem ersten Start nicht vollstaendig gesetzt - das '
        "Skript setzt sie beim ersten Start; Startmenue, Wetter bzw. Sperrbildschirm evtl. erst nach einem weiteren "
        "Neustart",
        'echo Okula: Windows anpassen - Richtlinien nicht vollstaendig gesetzt, Installation laeuft weiter >> "%LOG%"',
        ":twende",
        ""))
    return text


def install_cmd(install_id: str, index: int, wim_path: str, split: bool, language: str,
                software: bool = False, tweak: dict | None = None) -> str:
    """Läuft in der Windows-Setup-Umgebung (cmd, nur ASCII). %1 = Laufwerk der Setup-Partition.

    Windows-Partition: Markierung okula-<id>.target, sonst genau ein Laufwerk mit Bezeichnung OKULAWIN (B-014) –
    nie ein Laufwerk auf Verdacht. Im Fehlerfall Laufwerksliste ins Protokoll und Hinweis oben im Editor (Ä-039).
    software (I-020): Installer und Startskript von der Setup-Partition ins neue Windows kopieren.
    tweak (Ä-046): None = kein „Windows anpassen“; sonst der Teil vor der ersten Anmeldung (wintweaks.offline_request,
    evtl. leer) – Richtlinien offline setzen, Startskript mitkopieren."""
    win_path = wim_path.replace("/", "\\")
    software_copy = (SOFTWARE_COPY if software else "") + \
        (tweak_offline_cmd(tweak) if tweak else "") + \
        (STARTUP_COPY if software or tweak is not None else "")
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
if errorlevel 1 echo Okula: FEHLER - unattend.xml nicht kopiert >> "%LOG%"
if errorlevel 1 goto fehler
mkdir %W%:\\Windows\\Setup\\Scripts >nul 2>&1
copy /y "%S%:\\okula\\SetupComplete.cmd" %W%:\\Windows\\Setup\\Scripts\\SetupComplete.cmd >> "%LOG%" 2>&1
if errorlevel 1 echo Okula: FEHLER - SetupComplete.cmd nicht kopiert >> "%LOG%"
if errorlevel 1 goto fehler
{software_copy}echo Okula: fertig >> "%LOG%"
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


SOFTWARE_START = """\
rem I-020: Software installieren - falls das Startskript noch nicht gelaufen ist (laeuft nur einmal)
set "OKULA_SW=%WINDIR%\\System32\\GroupPolicy\\Machine\\Scripts\\Startup\\okula-software.cmd"
if exist "%OKULA_SW%" cmd /c "%OKULA_SW%"
"""


def tweak_start(software: bool) -> str:
    """SetupComplete.cmd (Ae-046): Startskript „Windows anpassen“ aufrufen – mit Software erst, wenn deren geplante
    Aufgabe fertig ist (höchstens SOFTWARE_WAIT_MIN). Warten mit ping (timeout braucht eine Konsole)."""
    from okula_recovery import deploy, software as sw
    rounds = SOFTWARE_WAIT_MIN * 60 // SOFTWARE_WAIT_STEP
    text = ("rem Ae-046: Windows anpassen - nach der Software, vor der ersten Anmeldung (laeuft nur einmal)\n"
            f'set "OKULA_TW=%WINDIR%\\System32\\GroupPolicy\\Machine\\Scripts\\Startup\\{deploy.TWEAK_CMD}"\n'
            'if not exist "%OKULA_TW%" goto ohneanpassen\n')
    if software:
        text += ("set N=0\n"
                 ":wartesoftware\n"
                 f'schtasks /query /tn "{sw.TASK_NAME}" >nul 2>&1\n'
                 "if errorlevel 1 goto anpassen\n"
                 f"if %N% GEQ {rounds} goto anpassen\n"
                 f'if %N%==0 >>"%WINDIR%\\Temp\\{deploy.TWEAK_NAME}.log" echo %DATE% %TIME%  Software wird noch '
                 f"installiert - Windows anpassen folgt danach, hoechstens {SOFTWARE_WAIT_MIN} min Wartezeit\n"
                 "set /a N+=1\n"
                 f"ping -n {SOFTWARE_WAIT_STEP + 1} 127.0.0.1 >nul\n"
                 "goto wartesoftware\n"
                 ":anpassen\n"
                 f'if %N% GEQ {rounds} >>"%WINDIR%\\Temp\\{deploy.TWEAK_NAME}.log" echo %DATE% %TIME%  Hinweis '
                 f"Software nach {SOFTWARE_WAIT_MIN} min noch nicht fertig - Windows anpassen laeuft trotzdem\n"
                 "rem Neustart der Software (Rueckgabewert 3010, in 60 s) zurueckstellen - er kaeme mitten in Windows\n"
                 "rem anpassen; ganz am Schluss wieder ausloesen (letzter Befehl, SetupComplete ist dann fertig)\n"
                 'set "OKULA_NEUSTART="\n'
                 "shutdown /a >nul 2>&1\n"
                 'if not errorlevel 1 set "OKULA_NEUSTART=1"\n'
                 "rem B-022: Zeile vor dem Skript schreiben - es gleicht beim ersten Schreiben alle Zeilen von cmd an\n"
                 "rem (Datum, UTF-8 mit BOM); eine Zeile danach bliebe im Format von cmd\n"
                 f'if defined OKULA_NEUSTART >>"%WINDIR%\\Temp\\{deploy.TWEAK_NAME}.log" echo %DATE% %TIME%  '
                 f"Neustart {sw.REBOOT_DELAY} s nach Windows anpassen - Software meldete Neustart noetig\n")
    text += 'cmd /c "%OKULA_TW%"\n'
    if software:
        text += ("if not defined OKULA_NEUSTART goto ohneanpassen\n"
                 f"shutdown /r /t {sw.REBOOT_DELAY} /c \"Okula Recovery Tool: Software installiert, Windows angepasst "
                 "- Neustart\" /d p:4:2 >nul 2>&1\n")
    return text + ":ohneanpassen\n"


def setupcomplete_cmd(install_id: str, software: bool = False, tweak: bool = False) -> str:
    """Läuft am Ende der Einrichtung im installierten Windows (als SYSTEM): Setup-Partition weg, C: vergrössern.
    software (I-020): danach das Startskript „Software installieren“ (SetupComplete läuft vor der ersten Anmeldung;
    mit OEM-Schlüssel nicht – dann übernimmt das Startskript der Gruppenrichtlinie, B-013).
    tweak (Ä-046): zuletzt das Startskript „Windows anpassen“ (nach der Software)."""
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
""" + (SOFTWARE_START if software else "") + (tweak_start(software) if tweak else ""))


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


TWEAK_AUDIT = ("Windows anpassen nicht beim Master-Image (Audit-Modus): Die Einstellungen landeten im Master (Store-Apps "
               "nur teilweise entfernt lassen Sysprep scheitern, Nachlauf und Startskript liefen erst beim Ausrollen). "
               "Beim Ausrollen über Image zurückspielen → Danach anpassen bzw. die Automatisierung mitgeben.")


def plan(iso_path: str | Path, index: int, opts: winunattend.WinOptions, software_plan=None,
         device: str = "", tweak: dict | None = None) -> Plan:
    """Was auf die Setup-Partition kommt – Dateien aus der ISO plus Skripte und Antwortdateien.
    software_plan (I-020, software.Plan): gewählte Programme vom NAS unter okula/software, Startskript unter okula/gp.
    tweak (Ä-046): Auswahl „Windows anpassen“ (wintweaks.choice) – Startskript unter okula/gp (nach der Software),
    Richtlinien vor dem ersten Start in install.cmd, Aufruf in SetupComplete.cmd."""
    from okula_recovery import deploy, software, wintweaks
    install_id = secrets.token_hex(4)
    nas_files: list[tuple[str, int, Path]] = []
    chosen = list(software_plan.entries) if software_plan is not None else []
    choice = wintweaks.clean_choice(tweak)
    if choice and opts.audit_mode:
        raise WinSetupError(TWEAK_AUDIT)
    soft_extra: dict[str, str] = {}
    startup: list[tuple[str, str, str]] = []
    if chosen:
        for kind, rel, size, _mtime, src in software_plan.files:
            if kind != "file":
                continue
            if size > FAT32_MAX:
                raise WinSetupError(f"Software-Datei grösser als 4 GB (Setup-Partition FAT32): {rel}")
            nas_files.append((f"{software.SETUP_SOFTWARE}/{rel}", size, Path(src)))
        startup.append((deploy.SOFTWARE_NAME, deploy.SOFTWARE_CMD_TEXT, software.build_script(chosen, device)))
    offline = None
    if choice:
        offline = wintweaks.choice_offline(choice)
        startup.append((deploy.TWEAK_NAME, deploy.TWEAK_CMD_TEXT, wintweaks.choice_script(choice, device)))
        if offline.get("start_pins"):
            soft_extra[f"{TWEAK_SETUP}/{deploy.START_PINS_FILE}"] = offline["start_pins"]
    if startup:
        soft_extra.update(software.startup_files(startup))
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
        "okula/install.cmd": install_cmd(install_id, index, wim[0], split, language, software=bool(chosen),
                                         tweak=offline),
        "okula/unattend.xml": system_unattend(opts),
        "okula/SetupComplete.cmd": setupcomplete_cmd(install_id, software=bool(chosen), tweak=choice is not None),
        f"okula/{install_id}.setup": install_id,
        **soft_extra,
    }
    size = sum(e.size for _p, e in files) + sum(len(t.encode()) for t in extra.values()) + SETUP_RESERVE \
        + sum(s for _p, s, _src in nas_files)
    return Plan(install_id, files, wim[0], split, extra, size, nas_files, chosen, choice)


def describe(plan: Plan) -> list[str]:
    total = sum(e.size for _p, e in plan.files)
    lines = [f"{len(plan.files)} Dateien, {total / 1000**3:.1f} GB auf die Setup-Partition "
             f"({plan.setup_size / 1000**3:.1f} GB)"]
    if plan.split:
        lines.append("install.wim über 4 GB – der Agent teilt sie in install.swm-Teile")
    if plan.software:
        soft = sum(s for _p, s, _src in plan.nas_files)
        lines.append(f"Software ({len(plan.nas_files)} Dateien, {soft / 1000**3:.2f} GB): "
                     + ", ".join(e.label for e in plan.software)
                     + " – wird beim ersten Start installiert")
    if plan.tweak:
        from okula_recovery import wintweaks
        lines.append(f"Windows anpassen ({wintweaks.choice_summary(plan.tweak)}) – vor der ersten Anmeldung"
                     + (", nach der Software" if plan.software else ""))
        if wintweaks.START_CLEAN in plan.tweak.get("keys", ()) and not wintweaks.start_pins_ppkg():
            lines.append("Hinweis Startmenü: " + wintweaks.START_GPO_HINT)          # B-022
    return lines
