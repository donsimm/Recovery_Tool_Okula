"""Windows anpassen (I-039): Optionen, Vorlagen und das PowerShell-Skript – ohne GTK.

Das Tool erzeugt hier ein Skript für Windows PowerShell 5.1 (Windows 10 22H2, Windows 11) und schickt es an den
Agent; der legt es als einmaliges Startskript der lokalen Gruppenrichtlinie ab (deploy.install_startup_script).
Beim nächsten Windows-Start läuft es als SYSTEM vor der Anmeldung:
1. Skript löschen, Startmechanismus zurückbauen (gpt.ini/scripts.ini von vorher, Einträge unter
   HKLM\\…\\Group Policy\\Scripts) – so läuft es nie ein zweites Mal, auch nicht nach einem Fehler.
2. Jede gewählte Option als eigener Baustein (try/catch): Fehler wird protokolliert, der nächste Baustein läuft.
   Store-Apps zuletzt (dauert am längsten), danach ggf. der Nachlauf (Ä-042: geplante Aufgabe, die nach der ersten
   Anmeldung nachgeladene Apps nochmals entfernt und sich danach selbst löscht).
Protokoll: C:\\Windows\\Temp\\okula-windows-anpassen.log – das Passwort der automatischen Anmeldung steht nie darin.
"""

from __future__ import annotations

import base64
import json
import re
import time
from dataclasses import dataclass

from okula_recovery.deploy import TWEAK_AFTER, TWEAK_LOG, TWEAK_NAME

LOG_PATH = TWEAK_LOG
GROUPS = ("Apps", "Windows-Programme", "Updates", "Betrieb", "Datenschutz", "Explorer und Desktop", "Dienste",
          "Anmeldung")
WIN_GROUP = "Windows-Programme"
WIN_HEADING = "Entfernen (Standard aus, in keiner Vorlage):"
AUTOLOGON = "autologon"
LATER = "later_cleanup"           # Nachlauf (Ä-042) – Baustein entsteht in build_script aus den gewählten Apps
START_CLEAN = "start_clean"
APPS_HEADING = "Store-Apps entfernen:"
SERVICES_HEADING = "Abschalten (stoppen, Starttyp „Deaktiviert“):"
PASSWORD_HINT = ("Das Passwort liegt nach dem Umsetzen im Klartext in der Registrierung (Winlogon) – wie bei der "
                 "automatischen Anmeldung von Windows üblich.")

# Nachlauf (Ä-042): geplante Aufgabe und Skript – nur ASCII (Aufgabenname, Pfad, Befehlszeile)
LATER_TASK = "Okula Windows anpassen Nachlauf"
LATER_FILE = "okula-windows-anpassen-nachlauf.ps1"     # unter %ProgramData%\Okula
LATER_DELAY_MIN = 30                                    # Minuten nach der Anmeldung
LATER_DAYS = 30                                         # läuft bis dahin nie → Windows löscht die Aufgabe

# Pakete, die keine Option je entfernt – auch nicht die Gruppe „Windows-Programme“: Edge, Einstellungen, Suche,
# Sicherheit, App-Installer, Shell, Frameworks, Treiber-Apps. Im Skript $OkulaKeepAlways (-like).
PROTECTED_ALWAYS = (
    "Microsoft.MicrosoftEdge*", "windows.immersivecontrolpanel", "Microsoft.Windows.Search", "Microsoft.Windows.Cortana",
    "Microsoft.SecHealthUI", "Microsoft.DesktopAppInstaller", "Microsoft.Windows.ShellExperienceHost",
    "Microsoft.Windows.StartMenuExperienceHost", "MicrosoftWindows.Client.CBS", "MicrosoftWindows.Client.Core",
    "*VCLibs*", "*NET.Native*", "Microsoft.NET.*", "*UI.Xaml*", "*WindowsAppRuntime*",
    "*NVIDIA*", "*Realtek*", "*Intel*", "AdvancedMicroDevices*", "*Dolby*", "*Synaptics*", "*Waves*",
)
# Windows-Programme (Ergänzung Ä-042): nur über die ausdrücklichen Häkchen der Gruppe „Windows-Programme“
# entfernbar, nie über andere Optionen oder Vorlagen
PROTECTED_WINDOWS = (
    "Microsoft.WindowsCalculator", "Microsoft.WindowsNotepad", "Microsoft.Paint", "Microsoft.Windows.Photos",
    "Microsoft.ScreenSketch", "Microsoft.WindowsTerminal", "Microsoft.ZuneMusic", "Microsoft.*Extension*",
)
PROTECTED = PROTECTED_ALWAYS + PROTECTED_WINDOWS          # im Skript $OkulaKeep

# Startmenü Windows 11 (Ä-042, B-017): Richtlinie ConfigureStartPins – Kacheln in dieser Reihenfolge; fehlt eine App,
# zeigt Windows die Kachel erst, wenn sie installiert ist (Microsoft Learn, „Customize the Start layout“).
# IDs Edge, Explorer, Einstellungen, Fotos, Paint, Terminal aus dem Beispiel von Microsoft Learn. Schreibweise
# „packagedAppId“ wie in den JSON-Beispielen von Microsoft Learn und in der Ausgabe von Export-StartLayout (die
# Tabellen dort schreiben „packagedAppID“).
# Ab Windows 11 24H2 (Build 26100, KB5062660) als Gruppenrichtlinie laut StartMenu.admx: ConfigureStartPins = 1
# (DWORD) und ConfigureStartPinsJSON = Pfad zur JSON-Datei (REG_EXPAND_SZ). Die Datei bleibt liegen (Nachlauf und
# Software installieren löschen %ProgramData%\Okula nur, wenn der Ordner leer ist).
START_PINS_FILE = "StartPins.json"                      # unter %ProgramData%\Okula, UTF-8 ohne BOM
START_GPO_BUILD = 26100
START_PINS = (
    ("Edge", {"desktopAppLink": "%ALLUSERSPROFILE%\\Microsoft\\Windows\\Start Menu\\Programs\\Microsoft Edge.lnk"}),
    ("Explorer", {"desktopAppLink": "%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\File Explorer.lnk"}),
    ("Einstellungen", {"packagedAppId": "windows.immersivecontrolpanel_cw5n1h2txyewy!microsoft.windows."
                                        "immersivecontrolpanel"}),
    ("Rechner", {"packagedAppId": "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"}),
    ("Editor", {"packagedAppId": "Microsoft.WindowsNotepad_8wekyb3d8bbwe!App"}),
    ("Fotos", {"packagedAppId": "Microsoft.Windows.Photos_8wekyb3d8bbwe!App"}),
    ("Paint", {"packagedAppId": "Microsoft.Paint_8wekyb3d8bbwe!App"}),
    ("Snipping Tool", {"packagedAppId": "Microsoft.ScreenSketch_8wekyb3d8bbwe!App"}),
    ("Terminal", {"packagedAppId": "Microsoft.WindowsTerminal_8wekyb3d8bbwe!App"}),
)


def start_pins_json() -> str:
    """LayoutModification.json für ConfigureStartPins (eine Zeile, nur ASCII). applyOnce: Windows 11 24H2 mit KB5062660
    setzt die Liste nur einmal, danach heften Benutzer selbst an; ältere Windows 11 ignorieren es (Liste bei jeder
    Anmeldung)."""
    return json.dumps({"applyOnce": True, "pinnedList": [pin for _n, pin in START_PINS]}, separators=(",", ":"))


@dataclass(frozen=True)
class Option:
    key: str
    group: str
    label: str
    body: str = ""          # PowerShell-Baustein (läuft in Invoke-OkulaStep, Fehler = Ausnahme)
    sub: str = ""           # Unterüberschrift im Dialog (Store-Apps, Dienste)
    patterns: tuple[str, ...] = ()   # Store-Apps: Name-Muster (Get-AppxPackage -like)
    tooltip: str = ""
    capabilities: tuple[str, ...] = ()   # Windows-Funktionen: Name-Muster (Get-WindowsCapability -like)


def _apps(*patterns: str, explicit: bool = False) -> str:
    return "Remove-OkulaApps @(" + ", ".join(f"'{p}'" for p in patterns) + ")" + (" -Explicit" if explicit else "")


def _app(key: str, label: str, *patterns: str) -> Option:
    return Option(key, "Apps", label, _apps(*patterns), APPS_HEADING, patterns)


def _win(key: str, label: str, apps: tuple[str, ...] = (), caps: tuple[str, ...] = (), tooltip: str = "") -> Option:
    """Windows-Programm (Ergänzung Ä-042): Store-App(s) mit -Explicit (nur $OkulaKeepAlways gilt) und/oder
    Windows-Funktion(en) per Remove-WindowsCapability."""
    lines = []
    if apps:
        lines.append(f"$a = {_apps(*apps, explicit=True)}")
    if caps:
        lines.append("$c = Remove-OkulaCapabilities @(" + ", ".join(f"'{c}'" for c in caps) + ")")
    lines.append("(@(" + ", ".join(v for v, on in (("$a", apps), ("$c", caps)) if on) + ") -join '; ')")
    return Option(key, WIN_GROUP, label, "\n".join(lines), WIN_HEADING, apps, tooltip, caps)


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
    # Apps – Store-Apps je Gruppe (Name-Muster); Frameworks, NonRemovable, PROTECTED und Treiber-Apps nie
    _app("apps_xbox", "Xbox", "Microsoft.Xbox*", "Microsoft.GamingApp"),
    _app("apps_bing", "Bing (Wetter, News, Bing Search …)", "Microsoft.Bing*"),
    # Microsoft.ZuneMusic (Groove-Musik bzw. Medienwiedergabe) nur noch unter „Windows-Programme“ (keine Doppelung)
    _app("apps_zune", "Filme & TV", "Microsoft.ZuneVideo"),
    _app("apps_solitaire", "Solitaire", "Microsoft.MicrosoftSolitaireCollection"),
    _app("apps_people", "Kontakte", "Microsoft.People"),
    _app("apps_phone", "Smartphone-Link", "Microsoft.YourPhone"),
    _app("apps_camera", "Kamera", "Microsoft.WindowsCamera"),
    _app("apps_office", "Office/Office-Hub", "Microsoft.MicrosoftOfficeHub", "Microsoft.Office.OneNote",
         "Microsoft.Office.Sway"),
    _app("apps_3d", "3D-Viewer/Paint 3D/Mixed Reality", "Microsoft.Microsoft3DViewer", "Microsoft.MSPaint",
         "Microsoft.Print3D", "Microsoft.MixedReality.Portal"),
    _app("apps_help", "Feedback-Hub/Tipps/Hilfe", "Microsoft.WindowsFeedbackHub", "Microsoft.Getstarted",
         "Microsoft.GetHelp"),
    _app("apps_store", "Microsoft Store", "Microsoft.WindowsStore", "Microsoft.StorePurchaseApp"),
    # Ä-042: weitere Apps (Windows 11)
    _app("apps_outlook", "Outlook (neu)/Mail und Kalender", "Microsoft.OutlookForWindows",
         "microsoft.windowscommunicationsapps"),
    _app("apps_teams", "Teams", "MSTeams", "MicrosoftTeams"),
    _app("apps_clipchamp", "Clipchamp", "Clipchamp.Clipchamp"),
    _app("apps_recorder", "Audiorecorder", "Microsoft.WindowsSoundRecorder"),
    _app("apps_notes", "Kurznotizen", "Microsoft.MicrosoftStickyNotes"),
    _app("apps_todo", "To Do", "Microsoft.Todos"),
    _app("apps_journal", "Journal", "Microsoft.MicrosoftJournal"),
    _app("apps_maps", "Karten", "Microsoft.WindowsMaps"),
    _app("apps_alarms", "Uhr (Wecker)", "Microsoft.WindowsAlarms"),
    _app("apps_family", "Family", "MicrosoftCorporationII.MicrosoftFamily"),
    _app("apps_quickassist", "Schnellhilfe", "MicrosoftCorporationII.QuickAssist"),
    _app("apps_powerautomate", "Power Automate", "Microsoft.PowerAutomateDesktop"),
    _app("apps_devhome", "Dev Home", "Microsoft.Windows.DevHome"),
    _app("apps_copilot", "Copilot", "Microsoft.Copilot", "Microsoft.Windows.Ai.Copilot.Provider"),
    # B-017: zusätzlich Richtlinie „Widgets zulassen“ = 0 (Policy CSP NewsAndInterests/AllowNewsAndInterests, Pro ab
    # Windows 11 21H2) – Wetter und Widgets verschwinden aus der Taskleiste, auch wenn das Paket bleibt
    Option("apps_widgets", "Apps", "Widgets", f"""
Set-OkulaReg '{POL}\\Dsh' 'AllowNewsAndInterests' 0
try {{ $r = {_apps("MicrosoftWindows.Client.WebExperience")} }}
catch {{ throw ('Richtlinie „Widgets zulassen“ aus; ' + $_.Exception.Message) }}
'Richtlinie „Widgets zulassen“ aus; ' + $r""", APPS_HEADING, ("MicrosoftWindows.Client.WebExperience",),
           tooltip="Entfernt die App Widgets und setzt die Richtlinie „Widgets zulassen“ auf aus – damit "
                   "verschwindet auch das Wetter aus der Taskleiste."),
    # nachgeladene Werbe-Apps (Platzhalter im Startmenü von Windows 11, später still installiert)
    _app("apps_ads", "Werbe-Apps (WhatsApp, LinkedIn, Spotify …)", "5319275A.WhatsAppDesktop",
         "7EE7776C.LinkedInforWindows", "AdobeSystemsIncorporated.Adobe*Express*", "SpotifyAB.SpotifyMusic",
         "Disney.37853FC22B2CE", "Facebook.*", "BytedancePte.Ltd.TikTok", "AmazonVideo.PrimeVideo",
         "4DF9E0F8.Netflix", "king.com.*"),
    Option(LATER, "Apps", "Später nachgeladene Apps nochmals entfernen (nach der Anmeldung)",
           tooltip=f"Geplante Aufgabe: {LATER_DELAY_MIN} min nach der ersten Anmeldung werden die gewählten "
                   "Store-Apps ein zweites Mal entfernt (Windows lädt Werbe-Apps erst nach der Anmeldung nach). "
                   "Die Aufgabe entfernt sich danach selbst."),
    Option("no_reinstall", "Apps", "Wiederinstallation von Werbe-Apps sperren", f"""
Set-OkulaReg '{POL}\\Windows\\CloudContent' 'DisableWindowsConsumerFeatures' 1
$users = Invoke-OkulaAllUsers {{
    param($Root)
    foreach ($n in 'SilentInstalledAppsEnabled', 'PreInstalledAppsEnabled', 'PreInstalledAppsEverEnabled',
                   'OemPreInstalledAppsEnabled') {{
        Set-OkulaReg "$Root\\{CDM}" $n 0
    }}
}}
$edition = [string](Get-ItemProperty -LiteralPath 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion' `
    -ErrorAction SilentlyContinue).EditionID
if ($edition -match 'Enterprise|Education') {{ "Richtlinie und stille Installation aus: $users" }}
else {{ "stille Installation aus: $users; Richtlinie wirkt bei $edition nicht (nur Enterprise/Education)" }}""",
           tooltip="Die Richtlinie „Microsoft-Benutzererfahrungen deaktivieren“ wirkt nur bei Windows Enterprise "
                   "und Education. Bei Pro und Home wirken die Werte für die stille App-Installation (alle "
                   "Benutzer) sowie „Startmenü: Werbe-Kacheln entfernen“ und „Später nachgeladene Apps nochmals "
                   "entfernen“."),
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
    # Windows-Programme (Ergänzung Ä-042) – Standard aus, in keiner Vorlage. Store-Apps und Windows-Funktionen
    # (Features on Demand, Microsoft Learn „Available features on demand“); unter Windows 10 sind Editor, Paint und
    # Snipping Tool teils noch Windows-Funktionen statt Store-Apps
    _win("win_calc", "Rechner", ("Microsoft.WindowsCalculator",)),
    _win("win_notepad", "Editor", ("Microsoft.WindowsNotepad",),
         ("Microsoft.Windows.Notepad~~~~*", "Microsoft.Windows.Notepad.System~~~~*")),
    _win("win_paint", "Paint", ("Microsoft.Paint",), ("Microsoft.Windows.MSPaint~~~~*",)),
    _win("win_photos", "Fotos", ("Microsoft.Windows.Photos",)),
    _win("win_snip", "Snipping Tool", ("Microsoft.ScreenSketch",), ("Microsoft.Windows.SnippingTool~~~~*",)),
    _win("win_terminal", "Terminal", ("Microsoft.WindowsTerminal",)),
    _win("win_media", "Medienwiedergabe (Groove-Musik)", ("Microsoft.ZuneMusic",),
         tooltip="App „Medienwiedergabe“ (Windows 11) bzw. „Groove-Musik“ (Windows 10). „Filme & TV“ ist ein "
                 "eigenes Häkchen unter Apps."),
    _win("win_codecs", "Medien-Erweiterungen (HEVC, HEIF, WebP, VP9, AV1, RAW …)",
         ("Microsoft.*VideoExtension*", "Microsoft.*ImageExtension", "Microsoft.WebMediaExtensions"),
         tooltip="Achtung: Fotos, Medienwiedergabe, Explorer-Vorschaubilder und andere Programme brauchen diese "
                 "Codecs u. U. – danach lassen sich z. B. HEIC-Fotos oder HEVC-Videos nicht mehr öffnen."),
    _win("win_wordpad", "WordPad", caps=("Microsoft.Windows.WordPad~~~~*",),
         tooltip="Windows-Funktion. Ab Windows 11 24H2 gibt es WordPad nicht mehr (dann „nicht vorhanden“)."),
    _win("win_steps", "Schrittaufzeichnung", caps=("App.StepsRecorder~~~~*",),
         tooltip="Windows-Funktion „Steps Recorder“ (psr.exe), von Microsoft abgekündigt."),
    _win("win_wmp", "Windows Media Player (klassisch)", caps=("Media.WindowsMediaPlayer~~~~*",),
         tooltip="Windows-Funktion „Windows Media Player Legacy“. Die App „Medienwiedergabe“ ist ein eigenes Häkchen."),
    _win("win_ie", "Internet Explorer 11 (auch IE-Modus in Edge)", caps=("Browser.InternetExplorer~~~~*",),
         tooltip="Windows-Funktion Internet Explorer 11. Danach funktioniert der IE-Modus in Edge nicht mehr "
                 "(Microsoft: Voraussetzung „Internet Explorer 11 enabled in Windows Features“)."),
    _win("win_math", "Math-Eingabe (Math Recognizer)", caps=("MathRecognizer~~~~*",),
         tooltip="Windows-Funktion für die Erkennung handgeschriebener Formeln (Stift); unter Windows 10 bis 2004 "
                 "auch der Mathematik-Eingabebereich."),
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
    Option(START_CLEAN, "Explorer und Desktop", "Startmenü: Werbe-Kacheln entfernen (Windows 11)", f"""
if ([Environment]::OSVersion.Version.Build -lt 22000) {{
    return 'Windows 10 – ohne Wirkung (gilt nur für Windows 11)'
}}
$json = '{start_pins_json()}'
if ([Environment]::OSVersion.Version.Build -ge {START_GPO_BUILD}) {{
    # Windows 11 24H2: Gruppenrichtlinie „Configure Start Pins“ wie in StartMenu.admx – Schalter (DWORD 1) und Pfad
    # zur JSON-Datei (REG_EXPAND_SZ); die Datei bleibt in %ProgramData%\\Okula liegen
    $folder = Join-Path $env:ProgramData 'Okula'
    New-Item -ItemType Directory -Path $folder -Force | Out-Null
    $file = Join-Path $folder '{START_PINS_FILE}'
    [IO.File]::WriteAllText($file, $json, (New-Object Text.UTF8Encoding $false))
    $key = '{POL}\\Windows\\Explorer'
    # bisheriger falscher Wert (Ä-042: JSON-Text als REG_SZ) wird ersetzt
    Remove-ItemProperty -LiteralPath $key -Name 'ConfigureStartPins' -ErrorAction SilentlyContinue
    Set-OkulaReg $key 'ConfigureStartPins' 1
    Set-OkulaReg $key 'ConfigureStartPinsJSON' $file 'ExpandString'
    return ('Gruppenrichtlinie ConfigureStartPins gesetzt (Datei {{0}}); wirkt bei der nächsten Anmeldung, auch ' +
            'für bestehende Benutzer') -f $file
}}
try {{
    # Windows 11 vor 24H2: nur Policy CSP Start/ConfigureStartPins über die MDM-Bridge (WMI, als SYSTEM)
    $ns = 'root\\cimv2\\mdm\\dmmap'
    $cls = 'MDM_Policy_Config01_Start02'
    $obj = Get-CimInstance -Namespace $ns -ClassName $cls `
        -Filter "ParentID='./Vendor/MSFT/Policy/Config' and InstanceID='Start'" -ErrorAction SilentlyContinue
    if ($obj) {{
        $obj.ConfigureStartPins = $json
        Set-CimInstance -CimInstance $obj -ErrorAction Stop
    }} else {{
        New-CimInstance -Namespace $ns -ClassName $cls -Property @{{ ParentID = './Vendor/MSFT/Policy/Config';
            InstanceID = 'Start'; ConfigureStartPins = $json }} -ErrorAction Stop | Out-Null
    }}
}} catch {{
    throw ('Windows 11 vor 24H2: Startmenü nur mit Geräteverwaltung (Policy CSP: {{0}})' -f $_.Exception.Message)
}}
'Richtlinie ConfigureStartPins gesetzt (Policy CSP); wirkt bei der nächsten Anmeldung, auch für bestehende Benutzer'""",
           tooltip="Ersetzt die angehefteten Kacheln im Startmenü von Windows 11 (auch die Platzhalter für "
                   "WhatsApp, LinkedIn, Clipchamp …, die Windows erst beim Klick installiert) durch Edge, Explorer, "
                   "Einstellungen, Rechner, Editor, Fotos, Paint, Snipping Tool und Terminal. Ab Windows 11 24H2 "
                   "über die Gruppenrichtlinie (Liste in C:\\ProgramData\\Okula\\StartPins.json), nur einmal – "
                   "danach lässt sich wieder selbst anheften. Ältere Windows 11 nur, wenn die Geräteverwaltung die "
                   "Richtlinie annimmt (sonst Fehler im Protokoll). Windows 10: ohne Wirkung."),
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
WIN_KEYS = tuple(o.key for o in OPTIONS if o.group == WIN_GROUP)      # Standard aus, in keiner Vorlage

# Vorlagen fest im Code (keine eigenen Vorlagen); „Keine“ = nichts gewählt
TEMPLATES: dict[str, frozenset[str]] = {
    "Player": frozenset(KEYS) - {"apps_camera", "svc_spooler"} - set(WIN_KEYS),
    "Laptop": frozenset(set(APP_KEYS) - {"apps_camera", "apps_store"}
                        | {"no_reinstall", "cortana",
                           "fastboot_off", "tips_off", "sticky_off",
                           "telemetry", "adid_off", "location_off", "wer_off", "bing_search_off",
                           "show_ext", "show_hidden", "explorer_thispc", "desktop_icons", "taskbar_clean",
                           START_CLEAN, LATER, "svc_xbox", "svc_remotereg"}),
    # Ä-042: Windows 11 ohne Werbung – Store und Kamera bleiben (lassen sich dazu wählen), Updates, Betrieb (ausser
    # Tipps), Explorer-Ansicht, Dienste und Anmeldung bleiben unverändert
    "Clean": frozenset(set(APP_KEYS) - {"apps_camera", "apps_store"}
                       | {LATER, "no_reinstall", "onedrive", "cortana", START_CLEAN, "tips_off",
                          "telemetry", "adid_off", "wer_off", "bing_search_off"}),
}
assert not any(set(WIN_KEYS) & keys for keys in TEMPLATES.values()), "Windows-Programme nie in Vorlagen"
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
        heading = {"Apps": "Store-Apps entfernen: ", WIN_GROUP: "entfernen: ", "Dienste": "abschalten: "}.get(group, "")
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


# Rückbau des Startmechanismus – gemeinsam mit „Software installieren“ (I-020, software.py). Stehen mehrere
# Okula-Startskripte gleichzeitig aus, laufen sie beim selben Start nacheinander; erst das letzte (keine andere
# okula-*.cmd mehr im Startup-Ordner) legt gpt.ini/scripts.ini von vorher zurück.
RESTORE_START = r"""function Restore-OkulaStart {
    # Weitere Okula-Startskripte noch offen (z. B. Software installieren): das letzte stellt den Stand her.
    # Rückgabe: Hinweis fürs Protokoll (oder nichts). Fehler nur, wenn scripts.ini bzw. die Registrierung des
    # Startskripts bleibt – lässt sich ein leerer, von Windows gerade verwendeter Ordner nicht löschen, ist das nur
    # ein Hinweis (B-017).
    $notes = @()
    $others = @(Get-ChildItem -LiteralPath $OkulaStartup -Filter 'okula-*.cmd' -Force -ErrorAction SilentlyContinue |
                Where-Object { $_.BaseName -ne $OkulaName })
    if (-not $others) {
        # gpt.ini und scripts.ini: Stand von vorher (Version erhöht) bzw. löschen, wenn es sie vorher nicht gab
        foreach ($file in (Join-Path $OkulaGp 'Machine\Scripts\scripts.ini'), (Join-Path $OkulaGp 'gpt.ini')) {
            $saved = $file + '__AFTER__'
            if (Test-Path -LiteralPath $file) { Remove-Item -LiteralPath $file -Force -ErrorAction Stop }
            if (Test-Path -LiteralPath $saved) { Move-Item -LiteralPath $saved -Destination $file -Force -ErrorAction Stop }
        }
        $ini = Join-Path $OkulaGp 'Machine\Scripts\scripts.ini'
        if ((Test-Path -LiteralPath $ini) -and
            ((Get-Content -LiteralPath $ini -Raw -ErrorAction SilentlyContinue) -like "*$OkulaName*")) {
            throw ('scripts.ini nennt das Startskript noch: {0}' -f $ini)
        }
        foreach ($sub in 'Machine\Scripts\Startup', 'Machine\Scripts', 'Machine') {
            $folder = Join-Path $OkulaGp $sub
            if ((Test-Path -LiteralPath $folder) -and -not @(Get-ChildItem -LiteralPath $folder -Force)) {
                try { Remove-Item -LiteralPath $folder -Force -ErrorAction Stop }
                catch { $notes += ('leerer Ordner {0} bleibt (wird gerade verwendet, ohne Wirkung)' -f $sub) }
            }
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
    if ($notes) { return ($notes -join '; ') }
}"""

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
__COMMON__

# Zuerst: Skript (enthält ggf. das Passwort der automatischen Anmeldung) und Startskript löschen
Remove-Item -LiteralPath (Join-Path $OkulaStartup "$OkulaName.ps1"), (Join-Path $OkulaStartup "$OkulaName.cmd") `
    -Force -ErrorAction SilentlyContinue

__RESTORE__

__FUNCTIONS__
Write-OkulaLog '----- Windows anpassen (Okula Recovery Tool): Start – Vorlage __TEMPLATE__ -----'
Invoke-OkulaStep 'Startskript und Gruppenrichtlinie aufräumen' {
    Restore-OkulaStart
}
"""

# Gemeinsam mit dem Nachlauf: Schutzliste, Zähler, Protokoll
COMMON = r"""$OkulaKeep = @(__KEEP__)
$OkulaKeepAlways = @(__KEEPALWAYS__)
$script:OkulaOk = 0
$script:OkulaFailed = 0

function Write-OkulaLog([string]$Text) {
    $line = '{0}  {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Text
    try { Add-Content -LiteralPath $OkulaLog -Value $line -Encoding UTF8 -ErrorAction Stop } catch { }
}"""

# Bausteine – gemeinsam mit dem Nachlauf
FUNCTIONS = r"""function Invoke-OkulaStep([string]$Label, [scriptblock]$Action) {
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

function Test-OkulaKeep([string]$Name, [bool]$Explicit = $false) {
    # $OkulaKeepAlways gilt immer; Rechner, Editor, Paint … ($OkulaKeep) nur ausdrücklich (Gruppe Windows-Programme)
    $list = if ($Explicit) { $OkulaKeepAlways } else { $OkulaKeep }
    foreach ($k in $list) { if ($Name -like $k) { return $true } }
    return $false
}

function Get-OkulaPackages([string]$Type) {
    # Liste einmal lesen (ein Aufruf je Muster kostet bei 40 Mustern Minuten – Startskripte haben 10 min)
    if (-not $script:OkulaPkgs) { $script:OkulaPkgs = @{} }
    if (-not $script:OkulaPkgs.ContainsKey($Type)) {
        if ($Type -eq 'Provisioned') {
            $script:OkulaPkgs[$Type] = @(Get-AppxProvisionedPackage -Online -ErrorAction Stop)
        } else {
            $script:OkulaPkgs[$Type] = @(Get-AppxPackage -AllUsers -PackageTypeFilter $Type -ErrorAction Stop)
        }
    }
    return $script:OkulaPkgs[$Type]
}

function Test-OkulaNotFound($ErrorRecord) {
    # 0x80070002 / 0x80070003 (Datei bzw. Pfad nicht gefunden): das Paket ist schon weg
    $e = $ErrorRecord.Exception
    while ($e) {
        if ($e.HResult -eq -2147024894 -or $e.HResult -eq -2147024893) { return $true }
        $e = $e.InnerException
    }
    return ([string]$ErrorRecord.Exception.Message -match '0x8007000[23]')
}

function Get-OkulaResult([string[]]$Removed, [string[]]$Errors, [string]$Suffix, [string]$None) {
    # Protokollzeile: entfernte Pakete stehen immer drin, auch wenn es daneben echte Fehler gibt
    $names = @($Removed | Where-Object { $_ } | Sort-Object -Unique)
    $text = if ($names) { ($names -join ', ') + $Suffix } else { '' }
    if ($Errors) {
        if ($text) { throw ('{0}; Fehler: {1}' -f $text, ($Errors -join '; ')) }
        throw ($Errors -join '; ')
    }
    if ($text) { return $text }
    return $None
}

function Remove-OkulaApps([string[]]$Patterns, [switch]$Explicit) {
    # installierte Pakete (alle Benutzer) und vorinstallierte (sonst kommen sie bei neuen Konten wieder und ein
    # späteres Sysprep bricht ab); Frameworks, NonRemovable, Schutzliste und Treiber-Apps nie
    if (-not $script:OkulaGone) { $script:OkulaGone = @{} }
    $removed = @()
    $errors = @()
    foreach ($pat in $Patterns) {
        foreach ($type in 'Bundle', 'Main') {
            foreach ($p in @(Get-OkulaPackages $type | Where-Object { $_.Name -like $pat })) {
                if ($p.NonRemovable -or (Test-OkulaKeep $p.Name $Explicit.IsPresent) -or
                    $script:OkulaGone.ContainsKey($p.Name)) { continue }
                try {
                    Remove-AppxPackage -Package $p.PackageFullName -AllUsers -ErrorAction Stop
                    $script:OkulaGone[$p.Name] = $true
                    $removed += $p.Name
                    # Windows 11 24H2: -AllUsers entfernt auch die Bereitstellung – Liste vor dem nächsten Schritt
                    # neu lesen (B-017)
                    $script:OkulaPkgs.Remove('Provisioned')
                } catch {
                    $errors += '{0}: {1}' -f $p.Name, $_.Exception.Message
                }
            }
        }
        foreach ($p in @(Get-OkulaPackages 'Provisioned' | Where-Object { $_.DisplayName -like $pat })) {
            if ((Test-OkulaKeep $p.DisplayName $Explicit.IsPresent) -or $script:OkulaGone.ContainsKey($p.PackageName)) {
                continue
            }
            try {
                Remove-AppxProvisionedPackage -Online -PackageName $p.PackageName -ErrorAction Stop | Out-Null
                $script:OkulaGone[$p.PackageName] = $true
                $removed += $p.DisplayName
            } catch {
                if (Test-OkulaNotFound $_) {
                    # schon entfernt (z. B. durch Remove-AppxPackage -AllUsers) – kein Fehler
                    $script:OkulaGone[$p.PackageName] = $true
                    $removed += $p.DisplayName
                } else {
                    $errors += '{0} (vorinstalliert): {1}' -f $p.DisplayName, $_.Exception.Message
                }
            }
        }
    }
    return (Get-OkulaResult $removed $errors ' entfernt' 'nicht vorhanden')
}

function Remove-OkulaCapabilities([string[]]$Patterns) {
    # Windows-Funktionen (Features on Demand): nur installierte, Liste einmal lesen
    if ($null -eq $script:OkulaCaps) { $script:OkulaCaps = @(Get-WindowsCapability -Online -ErrorAction Stop) }
    $removed = @()
    $errors = @()
    $restart = $false
    foreach ($pat in $Patterns) {
        foreach ($c in @($script:OkulaCaps | Where-Object { $_.Name -like $pat -and [string]$_.State -eq 'Installed' })) {
            try {
                $r = Remove-WindowsCapability -Online -Name $c.Name -ErrorAction Stop
                if ($r.RestartNeeded) { $restart = $true }
                $removed += ($c.Name -split '~')[0]
            } catch {
                $errors += '{0}: {1}' -f $c.Name, $_.Exception.Message
            }
        }
    }
    $suffix = if ($restart) { ' entfernt (wirkt nach einem Neustart)' } else { ' entfernt' }
    $text = Get-OkulaResult $removed $errors $suffix 'nicht vorhanden'
    return 'Windows-Funktion ' + $text
}
"""

# Nachlauf (Ä-042): eigenes Skript unter %ProgramData%\Okula, läuft als geplante Aufgabe (SYSTEM) nach der ersten
# Anmeldung, entfernt die gewählten Store-Apps nochmals und danach Aufgabe und Datei – auch nach einem Fehler.
LATER_HEADER = r"""# Okula Recovery Tool – Windows anpassen, Nachlauf (Ä-042)
# Erstellt: __CREATED__ · Gerät: __DEVICE__
# Läuft einmal als geplante Aufgabe (SYSTEM) __DELAY__ min nach der ersten Anmeldung: entfernt Store-Apps, die
# Windows erst nach der Anmeldung nachlädt, danach die Aufgabe und sich selbst. Protokoll: __LOG__
$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
$OkulaName = '__NAME__'
$OkulaLog = Join-Path $env:SystemRoot "Temp\$OkulaName.log"
$OkulaTask = '__TASK__'
__COMMON__

__FUNCTIONS__
try {
    Write-OkulaLog '----- Windows anpassen – Nachlauf nach der Anmeldung: Start -----'
"""

LATER_FOOTER = r"""} finally {
    Write-OkulaLog ('----- Nachlauf Ende: {0} ok, {1} mit Fehler -----' -f $script:OkulaOk, $script:OkulaFailed)
    if ($PSCommandPath) { Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue }
    # nur einen leeren Ordner löschen – StartPins.json (Startmenü-Richtlinie, B-017) bleibt
    $folder = Join-Path $env:ProgramData 'Okula'
    if ((Test-Path -LiteralPath $folder) -and -not @(Get-ChildItem -LiteralPath $folder -Force)) {
        Remove-Item -LiteralPath $folder -Force -ErrorAction SilentlyContinue
    }
    # zuletzt: die Aufgabe entfernt sich selbst
    Unregister-ScheduledTask -TaskName $OkulaTask -Confirm:$false -ErrorAction SilentlyContinue
}
"""

# Baustein im Startskript: Nachlauf-Skript ablegen und Aufgabe anlegen
LATER_BODY = r"""$folder = Join-Path $env:ProgramData 'Okula'
New-Item -ItemType Directory -Path $folder -Force | Out-Null
$file = Join-Path $folder '__FILE__'
$text = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__B64__'))
[IO.File]::WriteAllText($file, $text, (New-Object Text.UTF8Encoding $true))
$ps = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$action = New-ScheduledTaskAction -Execute $ps -Argument ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}"' -f $file)
$trigger = New-ScheduledTaskTrigger -AtLogOn
$trigger.Delay = 'PT__DELAY__M'
$trigger.EndBoundary = (Get-Date).AddDays(__DAYS__).ToString('s')
$principal = New-ScheduledTaskPrincipal -UserId 'S-1-5-18' -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 2) -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew `
    -DeleteExpiredTaskAfter (New-TimeSpan -Days 1)
Register-ScheduledTask -TaskName '__TASK__' -Action $action -Trigger $trigger -Principal $principal `
    -Settings $settings -Force -ErrorAction Stop | Out-Null
'Aufgabe „__TASK__“ angelegt: __DELAY__ min nach der ersten Anmeldung, __COUNT__ App-Gruppe(n)'"""

FOOTER = r"""
Write-OkulaLog ('----- Ende: {0} ok, {1} mit Fehler -----' -f $script:OkulaOk, $script:OkulaFailed)
"""


def _indent(code: str) -> str:
    return "\n".join(("    " + line) if line.strip() else "" for line in code.strip("\n").splitlines())


def _keep_list(items=PROTECTED) -> str:
    return ", ".join(f"'{k}'" for k in items)


def _fill(text: str, **values: str) -> str:
    # gemeinsame Teile zuerst (enthalten selbst Platzhalter)
    text = (text.replace("__COMMON__", COMMON).replace("__FUNCTIONS__", FUNCTIONS)
            .replace("__KEEPALWAYS__", _keep_list(PROTECTED_ALWAYS)).replace("__KEEP__", _keep_list()))
    for k, v in values.items():
        text = text.replace(f"__{k}__", v)
    return text


def _step(o: Option, body: str) -> str:
    label = f"Store-Apps entfernen: {o.label}" if o.key in APP_KEYS else \
        f"Windows-Programm entfernen: {o.label}" if o.group == WIN_GROUP else \
        f"Dienst abschalten: {o.label}" if o.group == "Dienste" else o.label
    return f"Invoke-OkulaStep {ps_quote(label)} {{\n{_indent(body)}\n}}"


def app_patterns(selected) -> list[str]:
    """Name-Muster aller gewählten Store-App-Gruppen (Reihenfolge wie im Dialog)."""
    return [p for o in OPTIONS if o.key in selected and o.key in APP_KEYS for p in o.patterns]


def build_later_script(selected, device: str = "", created: float | None = None) -> str:
    """Nachlauf-Skript (Ä-042): die gewählten Store-Apps nochmals entfernen, danach Aufgabe und Datei löschen."""
    stamp = time.strftime("%d.%m.%Y %H:%M", time.localtime(created if created is not None else time.time()))
    safe_device = re.sub(r"[^\w .-]", "", device)[:60] or "–"
    head = _fill(LATER_HEADER, CREATED=stamp, DEVICE=safe_device, DELAY=str(LATER_DELAY_MIN), LOG=LOG_PATH,
                 NAME=TWEAK_NAME, TASK=LATER_TASK)
    steps = [_step(o, o.body) for o in OPTIONS if o.key in selected and o.key in APP_KEYS]
    return head + _indent("\n".join(steps)) + "\n" + LATER_FOOTER


def later_body(selected, device: str = "", created: float | None = None) -> str:
    """Baustein im Startskript: Nachlauf-Skript nach %ProgramData%\\Okula schreiben, Aufgabe anlegen."""
    count = sum(1 for k in APP_KEYS if k in selected)
    if not count:
        return "'keine Store-Apps gewählt – kein Nachlauf nötig'"
    return _fill(LATER_BODY, FILE=LATER_FILE, B64=_b64(build_later_script(selected, device, created)),
                 DELAY=str(LATER_DELAY_MIN), DAYS=str(LATER_DAYS), TASK=LATER_TASK, COUNT=str(count))


def build_script(selected, user: str = "", password: str = "", device: str = "", template: str = NO_TEMPLATE,
                 created: float | None = None) -> str:
    """PowerShell-Skript für die gewählten Optionen. Reihenfolge: wie im Dialog, Store-Apps zuletzt, danach der
    Nachlauf (geplante Aufgabe)."""
    selected = set(selected)
    problem = check(selected, user, password)
    if problem:
        raise TweakError(problem)
    stamp = time.strftime("%d.%m.%Y %H:%M", time.localtime(created if created is not None else time.time()))
    safe_device = re.sub(r"[^\w .-]", "", device)[:60] or "–"
    head = _fill(HEADER.replace("__RESTORE__", RESTORE_START), CREATED=stamp, DEVICE=safe_device,
                 TEMPLATE=template_label(template, selected), LOG=LOG_PATH, NAME=TWEAK_NAME, AFTER=TWEAK_AFTER)
    chosen = [o for o in OPTIONS if o.key in selected]
    removal = set(APP_KEYS) | set(WIN_KEYS)
    order = [o for o in chosen if o.key not in removal and o.key != LATER] + \
            [o for o in chosen if o.key in APP_KEYS] + [o for o in chosen if o.key in WIN_KEYS] + \
            [o for o in chosen if o.key == LATER]
    steps = []
    for o in order:
        body = autologon_body(user, password) if o.key == AUTOLOGON else \
            later_body(selected, device, created) if o.key == LATER else o.body
        steps.append(_step(o, body))
    return head + "\n" + "\n".join(steps) + "\n" + FOOTER
