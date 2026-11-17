"""Windows anpassen (I-039): Optionen, Vorlagen und das PowerShell-Skript – ohne GTK.

Das Tool erzeugt hier ein Skript für Windows PowerShell 5.1 (Windows 10 22H2, Windows 11) und schickt es an den
Agent; der legt es als einmaliges Startskript der lokalen Gruppenrichtlinie ab (deploy.install_startup_script).
Beim nächsten Windows-Start läuft es als SYSTEM vor der Anmeldung:
1. Skript löschen, Startmechanismus zurückbauen (gpt.ini/scripts.ini von vorher, Einträge unter
   HKLM\\…\\Group Policy\\Scripts) – so läuft es nie ein zweites Mal, auch nicht nach einem Fehler.
2. Jede gewählte Option als eigener Baustein (try/catch): Fehler wird protokolliert, der nächste Baustein läuft.
   Store-Apps zuletzt (dauert am längsten).
Protokoll: C:\\Windows\\Temp\\okula-windows-anpassen.log – das Passwort der automatischen Anmeldung steht nie darin.
"""

from __future__ import annotations

import base64
import re
import time
from dataclasses import dataclass

from okula_recovery.deploy import TWEAK_AFTER, TWEAK_LOG, TWEAK_NAME

LOG_PATH = TWEAK_LOG
GROUPS = ("Apps", "Updates", "Betrieb", "Datenschutz", "Explorer und Desktop", "Dienste", "Anmeldung")
AUTOLOGON = "autologon"
APPS_HEADING = "Store-Apps entfernen:"
SERVICES_HEADING = "Abschalten (stoppen, Starttyp „Deaktiviert“):"
PASSWORD_HINT = ("Das Passwort liegt nach dem Umsetzen im Klartext in der Registrierung (Winlogon) – wie bei der "
                 "automatischen Anmeldung von Windows üblich.")


@dataclass(frozen=True)
class Option:
    key: str
    group: str
    label: str
    body: str = ""          # PowerShell-Baustein (läuft in Invoke-OkulaStep, Fehler = Ausnahme)
    sub: str = ""           # Unterüberschrift im Dialog (Store-Apps, Dienste)


def _apps(*patterns: str) -> str:
    return "Remove-OkulaApps @(" + ", ".join(f"'{p}'" for p in patterns) + ")"


def _services(*names: str) -> str:
    return "Disable-OkulaServices @(" + ", ".join(f"'{n}'" for n in names) + ")"


POL = "HKLM:\\SOFTWARE\\Policies\\Microsoft"
CDM = "Software\\Microsoft\\Windows\\CurrentVersion\\ContentDeliveryManager"
ADV = "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced"
SEARCH = "Software\\Microsoft\\Windows\\CurrentVersion\\Search"
TIPS_IDS = ("310093", "314559", "314563", "338387", "338388", "338389", "338393", "353694", "353696", "353698",
            "88000326")
HIGH_PERFORMANCE = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
THIS_PC = "{20D04FE0-3AEA-1069-A2D8-08002B30309D}"
NETWORK = "{F02C1A0D-BE21-4350-88B0-7367FC96EF3C}"

OPTIONS: tuple[Option, ...] = (
    # Apps – Store-Apps je Gruppe (Name-Muster); Frameworks, NonRemovable und Treiber-Apps nie
    Option("apps_xbox", "Apps", "Xbox", _apps("Microsoft.Xbox*", "Microsoft.GamingApp"), APPS_HEADING),
    Option("apps_bing", "Apps", "Bing (Wetter, News …)", _apps("Microsoft.Bing*"), APPS_HEADING),
    Option("apps_zune", "Apps", "Groove/Filme & TV", _apps("Microsoft.ZuneMusic", "Microsoft.ZuneVideo"),
           APPS_HEADING),
    Option("apps_solitaire", "Apps", "Solitaire", _apps("Microsoft.MicrosoftSolitaireCollection"), APPS_HEADING),
    Option("apps_people", "Apps", "Kontakte", _apps("Microsoft.People"), APPS_HEADING),
    Option("apps_phone", "Apps", "Smartphone-Link", _apps("Microsoft.YourPhone"), APPS_HEADING),
    Option("apps_camera", "Apps", "Kamera", _apps("Microsoft.WindowsCamera"), APPS_HEADING),
    Option("apps_office", "Apps", "Office/Office-Hub",
           _apps("Microsoft.MicrosoftOfficeHub", "Microsoft.Office.OneNote", "Microsoft.Office.Sway"), APPS_HEADING),
    Option("apps_3d", "Apps", "3D-Viewer/Paint 3D/Mixed Reality",
           _apps("Microsoft.Microsoft3DViewer", "Microsoft.MSPaint", "Microsoft.Print3D",
                 "Microsoft.MixedReality.Portal"), APPS_HEADING),
    Option("apps_help", "Apps", "Feedback-Hub/Tipps/Hilfe",
           _apps("Microsoft.WindowsFeedbackHub", "Microsoft.Getstarted", "Microsoft.GetHelp"), APPS_HEADING),
    Option("apps_store", "Apps", "Microsoft Store", _apps("Microsoft.WindowsStore", "Microsoft.StorePurchaseApp"),
           APPS_HEADING),
    Option("no_reinstall", "Apps", "Wiederinstallation von Werbe-Apps sperren", f"""
Set-OkulaReg '{POL}\\Windows\\CloudContent' 'DisableWindowsConsumerFeatures' 1
Invoke-OkulaAllUsers {{
    param($Root)
    foreach ($n in 'SilentInstalledAppsEnabled', 'PreInstalledAppsEnabled', 'PreInstalledAppsEverEnabled',
                   'OemPreInstalledAppsEnabled') {{
        Set-OkulaReg "$Root\\{CDM}" $n 0
    }}
}}"""),
    Option("onedrive", "Apps", "OneDrive entfernen", f"""
Get-Process -Name 'OneDrive' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
$notes = @()
foreach ($exe in "$env:SystemRoot\\System32\\OneDriveSetup.exe", "$env:SystemRoot\\SysWOW64\\OneDriveSetup.exe") {{
    if (Test-Path -LiteralPath $exe) {{
        $p = Start-Process -FilePath $exe -ArgumentList '/uninstall' -Wait -PassThru -WindowStyle Hidden
        $notes += "OneDriveSetup /uninstall: $($p.ExitCode)"
    }}
}}
Set-OkulaReg '{POL}\\Windows\\OneDrive' 'DisableFileSyncNGSC' 1
$users = Invoke-OkulaAllUsers {{
    param($Root)
    Remove-ItemProperty -LiteralPath "$Root\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" `
        -Name 'OneDriveSetup', 'OneDrive' -ErrorAction SilentlyContinue
}}
(@($notes) + "Autostart entfernt: $users") -join ', '"""),
    Option("cortana", "Apps", "Cortana aus", f"Set-OkulaReg '{POL}\\Windows\\Windows Search' 'AllowCortana' 0"),
    # Updates
    Option("wu_off", "Updates", "Windows Update aus",
           f"Set-OkulaReg '{POL}\\Windows\\WindowsUpdate\\AU' 'NoAutoUpdate' 1"),
    Option("wu_drivers", "Updates", "Keine Treiber über Windows Update", f"""
Set-OkulaReg '{POL}\\Windows\\WindowsUpdate' 'ExcludeWUDriversInQualityUpdate' 1
Set-OkulaReg 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\DriverSearching' 'SearchOrderConfig' 0"""),
    Option("store_updates", "Updates", "Keine automatischen App-Updates",
           f"Set-OkulaReg '{POL}\\WindowsStore' 'AutoDownload' 2"),
    # Betrieb
    Option("power_high", "Betrieb", "Energieplan Höchstleistung", f"""
$hp = '{HIGH_PERFORMANCE}'
if ((Invoke-OkulaNative 'powercfg.exe' @('/list')) -match $hp) {{
    Invoke-OkulaNative 'powercfg.exe' @('/setactive', $hp) | Out-Null
    'vorhanden'
}} else {{
    $out = Invoke-OkulaNative 'powercfg.exe' @('/duplicatescheme', $hp)
    $guid = [regex]::Match($out, '[0-9a-fA-F]{{8}}-([0-9a-fA-F]{{4}}-){{3}}[0-9a-fA-F]{{12}}').Value
    if (-not $guid) {{ throw "Energieplan nicht angelegt: $out" }}
    Invoke-OkulaNative 'powercfg.exe' @('/setactive', $guid) | Out-Null
    'aus Vorlage angelegt'
}}"""),
    Option("power_never", "Betrieb", "Bildschirm und Standby nie ausschalten", """
foreach ($a in 'monitor-timeout-ac', 'monitor-timeout-dc', 'standby-timeout-ac', 'standby-timeout-dc') {
    Invoke-OkulaNative 'powercfg.exe' @('/change', $a, '0') | Out-Null
}"""),
    Option("hibernate_off", "Betrieb", "Ruhezustand aus",
           "Invoke-OkulaNative 'powercfg.exe' @('/hibernate', 'off') | Out-Null"),
    Option("fastboot_off", "Betrieb", "Schnellstart aus",
           "Set-OkulaReg 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Power' 'HiberbootEnabled' 0"),
    Option("lockscreen_off", "Betrieb", "Sperrbildschirm aus",
           f"Set-OkulaReg '{POL}\\Windows\\Personalization' 'NoLockScreen' 1"),
    Option("tips_off", "Betrieb", "Tipps, Vorschläge und Benachrichtigungen aus", f"""
Invoke-OkulaAllUsers {{
    param($Root)
    $k = "$Root\\{CDM}"
    $names = @({", ".join(f"'SubscribedContent-{i}Enabled'" for i in TIPS_IDS)})
    if (Test-Path -LiteralPath $k) {{
        $names += @((Get-Item -LiteralPath $k).Property | Where-Object {{ $_ -like 'SubscribedContent-*Enabled' }})
    }}
    foreach ($n in ($names | Sort-Object -Unique)) {{ Set-OkulaReg $k $n 0 }}
    Set-OkulaReg $k 'SystemPaneSuggestionsEnabled' 0
    Set-OkulaReg $k 'SoftLandingEnabled' 0
    Set-OkulaReg "$Root\\Software\\Microsoft\\Windows\\CurrentVersion\\PushNotifications" 'ToastEnabled' 0
}}"""),
    Option("sticky_off", "Betrieb", "Einrastfunktion und Anschlagverzögerung aus", """
Invoke-OkulaAllUsers {
    param($Root)
    Set-OkulaReg "$Root\\Control Panel\\Accessibility\\StickyKeys" 'Flags' '506' 'String'
    Set-OkulaReg "$Root\\Control Panel\\Accessibility\\Keyboard Response" 'Flags' '122' 'String'
}"""),
    # Datenschutz
    Option("telemetry", "Datenschutz", "Telemetrie minimal", f"""
Set-OkulaReg '{POL}\\Windows\\DataCollection' 'AllowTelemetry' 0
Disable-OkulaServices @('DiagTrack')"""),
    Option("adid_off", "Datenschutz", "Werbe-ID aus",
           f"Set-OkulaReg '{POL}\\Windows\\AdvertisingInfo' 'DisabledByGroupPolicy' 1"),
    Option("location_off", "Datenschutz", "Standort aus",
           f"Set-OkulaReg '{POL}\\Windows\\LocationAndSensors' 'DisableLocation' 1"),
    Option("wer_off", "Datenschutz", "Fehlerberichte aus",
           f"Set-OkulaReg '{POL}\\Windows\\Windows Error Reporting' 'Disabled' 1"),
    Option("bing_search_off", "Datenschutz", "Bing-Suche im Startmenü aus", f"""
Set-OkulaReg '{POL}\\Windows\\Windows Search' 'DisableWebSearch' 1
Set-OkulaReg '{POL}\\Windows\\Windows Search' 'ConnectedSearchUseWeb' 0
Invoke-OkulaAllUsers {{
    param($Root)
    Set-OkulaReg "$Root\\{SEARCH}" 'BingSearchEnabled' 0
    Set-OkulaReg "$Root\\Software\\Policies\\Microsoft\\Windows\\Explorer" 'DisableSearchBoxSuggestions' 1
}}"""),
    # Explorer und Desktop – alle Benutzer und Standardprofil
    Option("show_ext", "Explorer und Desktop", "Dateiendungen anzeigen",
           f"Invoke-OkulaAllUsers {{ param($Root) Set-OkulaReg \"$Root\\{ADV}\" 'HideFileExt' 0 }}"),
    Option("show_hidden", "Explorer und Desktop", "Versteckte Dateien anzeigen",
           f"Invoke-OkulaAllUsers {{ param($Root) Set-OkulaReg \"$Root\\{ADV}\" 'Hidden' 1 }}"),
    Option("explorer_thispc", "Explorer und Desktop", "Explorer öffnet „Dieser PC“",
           f"Invoke-OkulaAllUsers {{ param($Root) Set-OkulaReg \"$Root\\{ADV}\" 'LaunchTo' 1 }}"),
    Option("desktop_icons", "Explorer und Desktop", "Symbole „Dieser PC“ und „Netzwerk“ auf dem Desktop", f"""
Invoke-OkulaAllUsers {{
    param($Root)
    $k = "$Root\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\HideDesktopIcons\\NewStartPanel"
    Set-OkulaReg $k '{THIS_PC}' 0
    Set-OkulaReg $k '{NETWORK}' 0
}}"""),
    Option("taskbar_clean", "Explorer und Desktop", "Suchfeld und Taskansicht aus der Taskleiste", f"""
Invoke-OkulaAllUsers {{
    param($Root)
    Set-OkulaReg "$Root\\{SEARCH}" 'SearchboxTaskbarMode' 0
    Set-OkulaReg "$Root\\{ADV}" 'ShowTaskViewButton' 0
}}"""),
    # Dienste – je Häkchen stoppen und Starttyp „Deaktiviert“
    Option("svc_search", "Dienste", "Windows Search", _services("WSearch"), SERVICES_HEADING),
    Option("svc_xbox", "Dienste", "Xbox-Dienste",
           _services("XblAuthManager", "XblGameSave", "XboxNetApiSvc", "XboxGipSvc"), SERVICES_HEADING),
    Option("svc_sysmain", "Dienste", "SysMain", _services("SysMain"), SERVICES_HEADING),
    Option("svc_remotereg", "Dienste", "Remote-Registrierung", _services("RemoteRegistry"), SERVICES_HEADING),
    Option("svc_spooler", "Dienste", "Druckwarteschlange", _services("Spooler"), SERVICES_HEADING),
    # Anmeldung – Baustein mit Benutzername/Passwort entsteht in build_script
    Option(AUTOLOGON, "Anmeldung", "Automatische Anmeldung"),
)
BY_KEY = {o.key: o for o in OPTIONS}
KEYS = tuple(BY_KEY)
APP_KEYS = tuple(o.key for o in OPTIONS if o.key.startswith("apps_"))

# Vorlagen fest im Code (keine eigenen Vorlagen); „Keine“ = nichts gewählt
TEMPLATES: dict[str, frozenset[str]] = {
    "Player": frozenset(KEYS) - {"apps_camera", "svc_spooler"},
    "Laptop": frozenset(set(APP_KEYS) - {"apps_camera", "apps_store"}
                        | {"no_reinstall", "cortana",
                           "fastboot_off", "tips_off", "sticky_off",
                           "telemetry", "adid_off", "location_off", "wer_off", "bing_search_off",
                           "show_ext", "show_hidden", "explorer_thispc", "desktop_icons", "taskbar_clean",
                           "svc_xbox", "svc_remotereg"}),
}
NO_TEMPLATE = "Keine"
TEMPLATE_NAMES = (*TEMPLATES, NO_TEMPLATE)


class TweakError(ValueError):
    pass


def template_keys(name: str) -> frozenset[str]:
    return TEMPLATES.get(name, frozenset())


def template_label(name: str, selected) -> str:
    """„Player“, „Player (geändert)“ oder „keine“ – für „Vorlage: …“ im Dialog und im Verlauf."""
    if name in TEMPLATES:
        return name + ("" if frozenset(selected) == TEMPLATES[name] else " (geändert)")
    return "keine"


def by_group(selected=None) -> dict[str, list[Option]]:
    """Optionen nach Gruppe (Reihenfolge wie im Dialog); selected = nur die gewählten."""
    out: dict[str, list[Option]] = {g: [] for g in GROUPS}
    for o in OPTIONS:
        if selected is None or o.key in selected:
            out[o.group].append(o)
    return out


def check(selected, user: str = "", password: str = "") -> str | None:
    """Meldung, warum sich (noch) nicht senden lässt – oder None."""
    unknown = set(selected) - set(KEYS)
    if unknown:
        return f"Unbekannte Einstellung: {', '.join(sorted(unknown))}"
    if not selected:
        return "Keine Einstellung gewählt."
    if AUTOLOGON in selected:
        if not user.strip() or not password:
            return "Für die automatische Anmeldung Benutzername und Passwort eintragen."
        if any(ord(c) < 32 for c in user + password):
            return "Benutzername oder Passwort enthält Steuerzeichen."
        if len(user.strip()) > 104 or len(password) > 256:
            return "Benutzername oder Passwort zu lang."
    return None


def summary(selected, template: str = NO_TEMPLATE, user: str = "") -> str:
    """Kurzform für Verlauf und Auftragsliste, z. B. „Vorlage Player (geändert): Apps (12), Updates (3), …“."""
    parts = []
    for group, opts in by_group(selected).items():
        if group == "Anmeldung":
            if opts:
                parts.append(f"automatische Anmeldung ({user.strip()})" if user.strip() else "automatische Anmeldung")
        elif opts:
            parts.append(f"{group} ({len(opts)})")
    return f"Vorlage {template_label(template, selected)}: " + ", ".join(parts)


def describe_lines(selected, user: str = "") -> list[str]:
    """Gewählte Optionen je Gruppe fürs Log des Auftrags (ohne Passwort)."""
    lines = []
    for group, opts in by_group(selected).items():
        if not opts:
            continue
        if group == "Anmeldung":
            lines.append(f"  Anmeldung: automatisch als „{user.strip()}“ (Passwort wird nicht protokolliert)")
            continue
        names = [o.label for o in opts]
        heading = {"Apps": "Store-Apps entfernen: ", "Dienste": "abschalten: "}.get(group, "")
        apps = [n for o, n in zip(opts, names) if o.sub]
        rest = [n for o, n in zip(opts, names) if not o.sub]
        text = ((heading + ", ".join(apps)) if apps else "")
        text = "; ".join(t for t in (text, ", ".join(rest)) if t)
        lines.append(f"  {group}: {text}")
    return lines


def ps_quote(text: str) -> str:
    """Einfache Anführungszeichen für PowerShell (auch typografische ‘ ’ ‚ ‛ gelten dort als Anführungszeichen)."""
    return "'" + re.sub("(['\u2018\u2019\u201a\u201b])", r"\1\1", text) + "'"


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def autologon_body(user: str, password: str) -> str:
    """Winlogon: AutoAdminLogon, DefaultUserName/-Password/-DomainName. Konto fehlt → Fehler, nichts gesetzt.
    Benutzername und Passwort als Base64 (keine Anführungszeichen-Probleme); das Passwort kommt nie ins Protokoll."""
    return f"""
$user = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{_b64(user.strip())}'))
$secret = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{_b64(password)}'))
if (-not @(Get-LocalUser | Where-Object {{ $_.Name -eq $user }})) {{
    throw ('Konto „{{0}}“ ist auf diesem Gerät nicht vorhanden – nichts gesetzt' -f $user)
}}
$wl = 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon'
Set-OkulaReg $wl 'DefaultUserName' $user 'String'
Set-OkulaReg $wl 'DefaultPassword' $secret 'String'
Set-OkulaReg $wl 'DefaultDomainName' $env:COMPUTERNAME 'String'
Remove-ItemProperty -LiteralPath $wl -Name 'AutoLogonCount' -ErrorAction SilentlyContinue
Set-OkulaReg $wl 'AutoAdminLogon' '1' 'String'
$secret = $null
'Konto ' + $user
"""


HEADER = r"""# Okula Recovery Tool – Windows anpassen (I-039)
# Erstellt: __CREATED__ · Gerät: __DEVICE__ · Vorlage: __TEMPLATE__
# Einmaliges Startskript der lokalen Gruppenrichtlinie (läuft als SYSTEM vor der Anmeldung). Zuerst werden das
# Skript und der Startmechanismus entfernt, dann folgen die Einstellungen – jede für sich: ein Fehler wird
# protokolliert, die nächste Einstellung läuft weiter. Protokoll: __LOG__
$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
$OkulaName = '__NAME__'
$OkulaLog = Join-Path $env:SystemRoot "Temp\$OkulaName.log"
$OkulaGp = Join-Path $env:SystemRoot 'System32\GroupPolicy'
$OkulaStartup = Join-Path $OkulaGp 'Machine\Scripts\Startup'
$OkulaKeep = @('*VCLibs*', '*NET.Native*', '*UI.Xaml*', '*NVIDIA*', '*Realtek*', '*Intel*')
$script:OkulaOk = 0
$script:OkulaFailed = 0

function Write-OkulaLog([string]$Text) {
    $line = '{0}  {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Text
    try { Add-Content -LiteralPath $OkulaLog -Value $line -Encoding UTF8 -ErrorAction Stop } catch { }
}

# Zuerst: Skript (enthält ggf. das Passwort der automatischen Anmeldung) und Startskript löschen
Remove-Item -LiteralPath (Join-Path $OkulaStartup "$OkulaName.ps1"), (Join-Path $OkulaStartup "$OkulaName.cmd") `
    -Force -ErrorAction SilentlyContinue

function Restore-OkulaStart {
    # gpt.ini und scripts.ini: Stand von vorher (Version erhöht) bzw. löschen, wenn es sie vorher nicht gab
    foreach ($file in (Join-Path $OkulaGp 'Machine\Scripts\scripts.ini'), (Join-Path $OkulaGp 'gpt.ini')) {
        $saved = $file + '__AFTER__'
        if (Test-Path -LiteralPath $file) { Remove-Item -LiteralPath $file -Force }
        if (Test-Path -LiteralPath $saved) { Move-Item -LiteralPath $saved -Destination $file -Force }
    }
    foreach ($sub in 'Machine\Scripts\Startup', 'Machine\Scripts', 'Machine') {
        $folder = Join-Path $OkulaGp $sub
        if ((Test-Path -LiteralPath $folder) -and -not @(Get-ChildItem -LiteralPath $folder -Force)) {
            Remove-Item -LiteralPath $folder -Force
        }
    }
    # Einträge, die Windows beim Verarbeiten der Richtlinie für dieses Startskript angelegt hat
    $base = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Group Policy'
    foreach ($list in "$base\Scripts\Startup", "$base\State\Machine\Scripts\Startup") {
        if (-not (Test-Path -LiteralPath $list)) { continue }
        foreach ($gpo in @(Get-ChildItem -LiteralPath $list)) {
            foreach ($entry in @(Get-ChildItem -LiteralPath $gpo.PSPath)) {
                $s = [string](Get-ItemProperty -LiteralPath $entry.PSPath -ErrorAction SilentlyContinue).Script
                if ($s -like "*$OkulaName*") { Remove-Item -LiteralPath $entry.PSPath -Recurse -Force }
            }
            if (-not @(Get-ChildItem -LiteralPath $gpo.PSPath)) { Remove-Item -LiteralPath $gpo.PSPath -Recurse -Force }
        }
    }
}

function Invoke-OkulaStep([string]$Label, [scriptblock]$Action) {
    try {
        $ErrorActionPreference = 'Stop'
        $note = @(& $Action) | Where-Object { $_ -is [string] -and $_ } | Select-Object -Last 1
        $script:OkulaOk++
        if ($note) { Write-OkulaLog "ok      $Label ($note)" } else { Write-OkulaLog "ok      $Label" }
    } catch {
        $script:OkulaFailed++
        Write-OkulaLog "FEHLER  ${Label}: $($_.Exception.Message)"
    }
}

function Invoke-OkulaNative([string]$File, [string[]]$Arguments) {
    $ErrorActionPreference = 'Continue'
    $out = (& $File @Arguments 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw ('{0} {1}: Rückgabewert {2} {3}' -f $File, ($Arguments -join ' '), $LASTEXITCODE, $out)
    }
    return $out
}

function Set-OkulaReg([string]$Path, [string]$Name, $Value, [string]$Type = 'DWord') {
    if (-not (Test-Path -LiteralPath $Path)) { New-Item -Path $Path -Force | Out-Null }
    New-ItemProperty -LiteralPath $Path -Name $Name -Value $Value -PropertyType $Type -Force | Out-Null
}

function Get-OkulaUserHives {
    # alle lokalen Profile (HKU\<SID> bzw. NTUSER.DAT) und das Standardprofil für später angelegte Konten
    $list = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList'
    $hives = @()
    foreach ($k in @(Get-ChildItem -LiteralPath $list)) {
        if ($k.PSChildName -notmatch '^S-1-5-21-[\d-]+$') { continue }
        $path = [string](Get-ItemProperty -LiteralPath $k.PSPath -ErrorAction SilentlyContinue).ProfileImagePath
        if (-not $path) { continue }
        $path = [Environment]::ExpandEnvironmentVariables($path)
        $hives += [pscustomobject]@{ Name = (Split-Path -Leaf $path); Sid = $k.PSChildName;
                                     File = (Join-Path $path 'NTUSER.DAT') }
    }
    $default = [string](Get-ItemProperty -LiteralPath $list -ErrorAction SilentlyContinue).Default
    if (-not $default) { $default = Join-Path $env:SystemDrive 'Users\Default' }
    $default = [Environment]::ExpandEnvironmentVariables($default)
    $hives += [pscustomobject]@{ Name = 'Standardprofil'; Sid = ''; File = (Join-Path $default 'NTUSER.DAT') }
    return $hives
}

function Invoke-OkulaAllUsers([scriptblock]$Action) {
    $done = 0
    $errors = @()
    foreach ($h in @(Get-OkulaUserHives)) {
        $mounted = $false
        try {
            if ($h.Sid -and (Test-Path -LiteralPath "Registry::HKEY_USERS\$($h.Sid)")) {
                $root = "Registry::HKEY_USERS\$($h.Sid)"
            } elseif (Test-Path -LiteralPath $h.File) {
                Invoke-OkulaNative 'reg.exe' @('load', 'HKU\OkulaAnpassen', $h.File) | Out-Null
                $mounted = $true
                $root = 'Registry::HKEY_USERS\OkulaAnpassen'
            } else {
                continue
            }
            & $Action $root | Out-Null
            $done++
        } catch {
            $errors += '{0}: {1}' -f $h.Name, $_.Exception.Message
        } finally {
            if ($mounted) {
                [gc]::Collect()
                [gc]::WaitForPendingFinalizers()
                for ($i = 0; $i -lt 10; $i++) {
                    try { Invoke-OkulaNative 'reg.exe' @('unload', 'HKU\OkulaAnpassen') | Out-Null; break }
                    catch { Start-Sleep -Milliseconds 500 }
                }
            }
        }
    }
    if ($errors) { throw ($errors -join '; ') }
    return "$done Profile"
}

function Disable-OkulaServices([string[]]$Names) {
    $done = @()
    $errors = @()
    foreach ($n in $Names) {
        $svc = Get-Service -Name $n -ErrorAction SilentlyContinue
        if (-not $svc) { continue }
        try {
            if ($svc.Status -ne 'Stopped') { Stop-Service -Name $n -Force -ErrorAction Stop }
            Set-Service -Name $n -StartupType Disabled -ErrorAction Stop
            $done += $n
        } catch {
            $errors += '{0}: {1}' -f $n, $_.Exception.Message
        }
    }
    if ($errors) { throw ($errors -join '; ') }
    if ($done) { return ($done -join ', ') + ' deaktiviert' }
    return 'nicht vorhanden'
}

function Test-OkulaKeep([string]$Name) {
    foreach ($k in $OkulaKeep) { if ($Name -like $k) { return $true } }
    return $false
}

function Remove-OkulaApps([string[]]$Patterns) {
    # installierte Pakete (alle Benutzer) und vorinstallierte (sonst kommen sie bei neuen Konten wieder und ein
    # späteres Sysprep bricht ab); Frameworks, NonRemovable und Treiber-Apps (NVIDIA, Realtek, Intel) nie
    $removed = @()
    $errors = @()
    foreach ($pat in $Patterns) {
        foreach ($type in 'Bundle', 'Main') {
            foreach ($p in @(Get-AppxPackage -AllUsers -PackageTypeFilter $type -Name $pat -ErrorAction SilentlyContinue)) {
                if ($p.NonRemovable -or (Test-OkulaKeep $p.Name) -or ($removed -contains $p.Name)) { continue }
                try {
                    Remove-AppxPackage -Package $p.PackageFullName -AllUsers -ErrorAction Stop
                    $removed += $p.Name
                } catch {
                    $errors += '{0}: {1}' -f $p.Name, $_.Exception.Message
                }
            }
        }
        foreach ($p in @(Get-AppxProvisionedPackage -Online | Where-Object { $_.DisplayName -like $pat })) {
            if (Test-OkulaKeep $p.DisplayName) { continue }
            try {
                Remove-AppxProvisionedPackage -Online -PackageName $p.PackageName -ErrorAction Stop | Out-Null
                $removed += $p.DisplayName
            } catch {
                $errors += '{0} (vorinstalliert): {1}' -f $p.DisplayName, $_.Exception.Message
            }
        }
    }
    if ($errors) { throw ($errors -join '; ') }
    $names = @($removed | Sort-Object -Unique)
    if ($names) { return ($names -join ', ') + ' entfernt' }
    return 'nicht vorhanden'
}

Write-OkulaLog '----- Windows anpassen (Okula Recovery Tool): Start – Vorlage __TEMPLATE__ -----'
Invoke-OkulaStep 'Startskript und Gruppenrichtlinie aufräumen' {
    Restore-OkulaStart
}
"""

FOOTER = r"""
Write-OkulaLog ('----- Ende: {0} ok, {1} mit Fehler -----' -f $script:OkulaOk, $script:OkulaFailed)
"""


def _indent(code: str) -> str:
    return "\n".join(("    " + line) if line.strip() else "" for line in code.strip("\n").splitlines())


def build_script(selected, user: str = "", password: str = "", device: str = "", template: str = NO_TEMPLATE,
                 created: float | None = None) -> str:
    """PowerShell-Skript für die gewählten Optionen. Reihenfolge: wie im Dialog, Store-Apps zuletzt."""
    selected = set(selected)
    problem = check(selected, user, password)
    if problem:
        raise TweakError(problem)
    stamp = time.strftime("%d.%m.%Y %H:%M", time.localtime(created if created is not None else time.time()))
    safe_device = re.sub(r"[^\w .-]", "", device)[:60] or "–"
    head = (HEADER.replace("__CREATED__", stamp).replace("__DEVICE__", safe_device)
            .replace("__TEMPLATE__", template_label(template, selected)).replace("__LOG__", LOG_PATH)
            .replace("__NAME__", TWEAK_NAME).replace("__AFTER__", TWEAK_AFTER))
    order = [o for o in OPTIONS if o.key in selected and o.key not in APP_KEYS] + \
            [o for o in OPTIONS if o.key in selected and o.key in APP_KEYS]
    steps = []
    for o in order:
        body = autologon_body(user, password) if o.key == AUTOLOGON else o.body
        label = f"Store-Apps entfernen: {o.label}" if o.key in APP_KEYS else \
            f"Dienst abschalten: {o.label}" if o.group == "Dienste" else o.label
        steps.append(f"Invoke-OkulaStep {ps_quote(label)} {{\n{_indent(body)}\n}}")
    return head + "\n" + "\n".join(steps) + "\n" + FOOTER
