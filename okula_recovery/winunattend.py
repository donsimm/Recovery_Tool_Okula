"""autounattend.xml für Windows-Setup: Anpassungen wie bei Rufus, Vorgaben für die Schweiz.

Windows-Setup liest die Datei automatisch aus dem Wurzelverzeichnis des Sticks. Was gesetzt wird:
- Anforderungen von Windows 11 umgehen (TPM 2.0, Secure Boot, RAM, CPU, Speicher) über LabConfig
- lokales Konto statt Microsoft-Konto (BypassNRO), optional mit Passwort
- Datenschutz-Fragen überspringen, keine automatische BitLocker-Verschlüsselung
- Region Schweiz: Formate de-CH, Tastatur Schweiz (Deutsch), Zeitzone Zürich
Die Sprache von Windows selbst bleibt die des Mediums (ui_language).
"""

from __future__ import annotations

import base64
import dataclasses
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from okula_recovery import textnorm

NS = "urn:schemas-microsoft-com:unattend"
WCM = "http://schemas.microsoft.com/WMIConfig/2002/State"

SWISS_LOCALE = "de-CH"
SWISS_KEYBOARD = "0807:00000807"       # Deutsch (Schweiz)
SWISS_TIMEZONE = "W. Europe Standard Time"

LABCONFIG = ("BypassTPMCheck", "BypassSecureBootCheck", "BypassRAMCheck", "BypassStorageCheck", "BypassCPUCheck")


# Microsoft: Installation auf nicht unterstützter Hardware „nicht empfohlen“, kein Support, keine Update-Garantie,
# Schäden nicht von der Herstellergarantie gedeckt (support.microsoft.com, Artikel 0b2dc4a2…, Stand 12.12.2024)
UNSUPPORTED_WARNING = ("Microsoft rät davon ab: kein Support, Updates (auch Sicherheitsupdates) nicht garantiert, "
                       "Schäden durch Inkompatibilität nicht von der Herstellergarantie gedeckt, Wasserzeichen auf "
                       "dem Desktop.")


@dataclass
class WinOptions:
    bypass_requirements: bool = False  # LabConfig: Setup-Prüfung TPM/Secure Boot/RAM/CPU umgehen – nur von Hand
    local_account: str = "Okula"       # leer = Windows fragt selbst (B-012: nicht „Benutzer“, s. pruefe_kontoname)
    password: str = ""                 # leer = beim ersten Anmelden setzen
    skip_privacy: bool = True
    no_bitlocker: bool = True
    swiss_region: bool = True
    ui_language: str = "de-DE"         # Sprache des Mediums
    computer_name: str = ""            # leer = Windows wählt
    arch: str = "amd64"
    skip_network: bool = False         # Netzwerk-Seite im Willkommens-Assistenten überspringen
    product_key: str = ""              # nur Direktinstallation: wird beim ersten Start gesetzt
    unsupported_hardware: bool = False  # Direktinstallation: Windows 11 trotz „nicht tauglich“ (am Gerät vermerken)
    audit_mode: bool = False           # I-038: für ein Master-Image – startet im Audit-Modus, kein Konto/Name/Key


# I-038: Text für Dialog, Log und Verlauf
AUDIT_SUMMARY = "Startet im Audit-Modus für ein Master-Image (kein Konto, kein Computername, kein Schlüssel)"
AUDIT_NEXT_STEPS = ("Windows startet im Audit-Modus. Einrichten, dann Sysprep: "
                    "C:\\Windows\\System32\\Sysprep\\sysprep.exe /generalize /oobe /shutdown – danach Windows nicht "
                    "mehr starten, mit dem Agent-Stick „Disk-Image erstellen …“ und das Image als Master markieren.")

# I-038: Die Antwortdatei der Direktinstallation liegt als Windows\Panther\unattend.xml auf C:. Windows sucht bei jedem
# Durchgang implizit dort (Microsoft Learn, „Windows Setup Automation Overview“ → „Implicit Answer File Search Order“,
# Platz 3) und verlangt: „Before you deliver the computer to a customer, you must delete the cached answer file in the
# %WINDIR%\panther directory.“ Bliebe sie im Master-Image, könnte ein Gerät daraus wieder im Audit-Modus starten.
# Gelöscht wird im Durchgang auditUser (RunSynchronous ist laut Microsoft nur in auditUser und specialize gültig,
# nicht in auditSystem; auditUser läuft beim Eintritt in den Audit-Modus als eingebauter Administrator).
# Microsoft dokumentiert zudem, dass Setup die zwischengespeicherte Datei nach einem Durchgang annotiert („Windows Setup
# Annotates Configuration Passes“). Damit ein Zurückschreiben am Ende von auditUser die Löschung nicht aufhebt, löscht
# ein abgekoppelter Befehl die Datei nach zwei Minuten noch einmal. Mehrfaches Löschen ist harmlos.
PANTHER_UNATTEND = "%WINDIR%\\Panther\\unattend.xml"
AUDIT_DELETE_ANSWER_FILE = [
    f'cmd /c del /f /q "{PANTHER_UNATTEND}"',
    f'cmd /c start "Okula" /min cmd /c "ping -n 121 127.0.0.1 >nul & del /f /q {PANTHER_UNATTEND}"',
]


# B-012: Namen, die in Windows (deutsch/englisch) schon für eingebaute Gruppen oder Konten vergeben sind.
# Ein lokales Konto mit so einem Namen lässt sich nicht anlegen (0x80070563), die Einrichtung hängt danach in einer
# Neustart-Schleife. Vergleich ohne Gross-/Kleinschreibung.
RESERVED_ACCOUNT_NAMES = (
    "Benutzer", "Benutzerin", "Administrator", "Administratoren", "Administrator-Gruppe", "Administratoren-Gruppe",
    "Gast", "Gäste", "Jeder", "Users", "User", "Administrators", "Guest", "Guests", "Everyone", "System", "Network",
    "Local", "Default", "DefaultAccount", "WDAGUtilityAccount", "Konto",
    # weitere eingebaute Gruppen/Konten
    "Hauptbenutzer", "Power Users", "Sicherungs-Operatoren", "Backup Operators", "Remotedesktopbenutzer",
    "Remote Desktop Users", "Netzwerkkonfigurations-Operatoren", "Network Configuration Operators",
    "Leistungsüberwachungsbenutzer", "Performance Monitor Users", "Leistungsprotokollbenutzer",
    "Performance Log Users", "Ereignisprotokollleser", "Event Log Readers", "Replikations-Operator", "Replicator",
    "IIS_IUSRS", "Hyper-V-Administratoren", "Hyper-V Administrators", "Remoteverwaltungsbenutzer",
    "Remote Management Users", "Zugriffssteuerungsunterstützungsoperatoren", "Access Control Assistance Operators",
    "Kryptografie-Operatoren", "Cryptographic Operators", "Distributed COM-Benutzer", "Distributed COM Users",
    "Gerätebesitzer", "Device Owners", "Lokaler Dienst", "Local Service", "Netzwerkdienst", "Network Service",
    "Interaktiv", "Interactive", "Authentifizierte Benutzer", "Authenticated Users", "Anonymous Logon",
    "Batch", "Dialup", "Service", "Dienst", "Creator Owner", "Ersteller-Besitzer", "Creator Group",
    "Erstellergruppe", "Terminal Server User", "TrustedInstaller",
)
_RESERVED_LOWER = frozenset(n.casefold() for n in RESERVED_ACCOUNT_NAMES)
ACCOUNT_FORBIDDEN_CHARS = '"/\\[]:;|=,+*?<>'
ACCOUNT_MAX_LEN = 20


def pruefe_kontoname(name: str) -> str | None:
    """Meldung, wenn Windows ein lokales Konto mit diesem Namen nicht anlegen kann, sonst None.

    Leer ist erlaubt: Dann legt die Antwortdatei kein Konto an und Windows fragt beim ersten Start selbst nach
    einem Konto (Einrichtung hält dort an). Der Name wird nicht korrigiert – die Meldung nennt den Grund."""
    name = (name or "").strip()
    if not name:
        return None
    if name.casefold() in _RESERVED_LOWER:
        return (f"Der Name „{name}“ ist in Windows für eine Gruppe oder ein eingebautes Konto vergeben und lässt "
                "sich nicht als Konto verwenden. Anderen Benutzernamen eingeben.")
    if len(name) > ACCOUNT_MAX_LEN:
        return (f"Der Benutzername „{name}“ ist zu lang ({len(name)} Zeichen, Windows erlaubt höchstens "
                f"{ACCOUNT_MAX_LEN}). Kürzeren Benutzernamen eingeben.")
    if name.endswith("."):
        return f"Der Benutzername „{name}“ darf nicht auf einen Punkt enden. Anderen Benutzernamen eingeben."
    bad = "".join(dict.fromkeys(c for c in name if c in ACCOUNT_FORBIDDEN_CHARS))
    if bad:
        return (f"Der Benutzername „{name}“ enthält Zeichen, die Windows nicht erlaubt ({' '.join(bad)}). "
                "Anderen Benutzernamen eingeben.")
    return None


def encode_password(password: str, kind: str = "Password") -> str:
    """Wie Windows SIM: Base64 von UTF-16LE(Passwort + „Password“)."""
    return base64.b64encode((password + kind).encode("utf-16-le")).decode()


def computer_name(name: str) -> str:
    """Gültiger NetBIOS-Name: max. 15 Zeichen, nur A–Z, 0–9 und Bindestrich."""
    name = textnorm.to_ascii(name)          # ä→ae, ß→ss, é→e – auch in NFD-Form (vom Mac)
    cleaned = "".join(c if c.isascii() and (c.isalnum() or c == "-") else "-" for c in name.strip())
    cleaned = cleaned.strip("-")[:15].strip("-")
    return "" if cleaned.isdigit() else cleaned


class _Builder:
    def __init__(self, arch: str):
        ET.register_namespace("", NS)
        ET.register_namespace("wcm", WCM)
        self.arch = arch
        self.root = ET.Element(f"{{{NS}}}unattend")
        self.passes: dict[str, ET.Element] = {}

    def component(self, pass_name: str, name: str) -> ET.Element:
        if pass_name not in self.passes:
            self.passes[pass_name] = ET.SubElement(self.root, f"{{{NS}}}settings", {"pass": pass_name})
        return ET.SubElement(self.passes[pass_name], f"{{{NS}}}component", {
            "name": name, "processorArchitecture": self.arch, "publicKeyToken": "31bf3856ad364e35",
            "language": "neutral", "versionScope": "nonSxS"})

    @staticmethod
    def sub(parent: ET.Element, tag: str, text: str | None = None, **attrs) -> ET.Element:
        el = ET.SubElement(parent, f"{{{NS}}}{tag}", {f"{{{WCM}}}{k}": v for k, v in attrs.items()})
        if text is not None:
            el.text = text
        return el

    def commands(self, parent: ET.Element, container: str, item: str, cmds: list[str], key: str = "Path") -> None:
        box = self.sub(parent, container)
        for i, cmd in enumerate(cmds, 1):
            c = self.sub(box, item, action="add")
            self.sub(c, "Order", str(i))
            self.sub(c, key, cmd)

    def xml(self) -> str:
        ET.indent(self.root, "  ")
        return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(self.root, encoding="unicode") + "\n"


def _international(b: _Builder, pass_name: str, opts: WinOptions, winpe: bool) -> None:
    if not opts.ui_language and not opts.swiss_region:
        return  # Master-Image: Sprache und Formate bleiben wie im Image
    comp = b.component(pass_name, "Microsoft-Windows-International-Core" + ("-WinPE" if winpe else ""))
    if winpe:
        setup = b.sub(comp, "SetupUILanguage")
        b.sub(setup, "UILanguage", opts.ui_language)
    b.sub(comp, "InputLocale", SWISS_KEYBOARD if opts.swiss_region else opts.ui_language)
    b.sub(comp, "SystemLocale", SWISS_LOCALE if opts.swiss_region else opts.ui_language)
    if opts.ui_language:  # leer (Master-Image): Sprache von Windows bleibt die installierte
        b.sub(comp, "UILanguage", opts.ui_language)
    b.sub(comp, "UserLocale", SWISS_LOCALE if opts.swiss_region else opts.ui_language)


def _audit_opts(opts: WinOptions) -> WinOptions:
    """I-038: Audit-Modus hat Vorrang – kein Konto, kein Computername, kein Schlüssel (gehören ins Zurückspielen)."""
    if not opts.audit_mode:
        return opts
    return dataclasses.replace(opts, local_account="", password="", computer_name="", product_key="")


def build(opts: WinOptions, pe: bool = True, system: bool = True, launch: str | None = None,
          audit_commands: list[str] | None = None) -> str:
    """pe: Setup-Umgebung (windowsPE); system: erster Start (specialize, oobeSystem bzw. auditUser);
    launch: Befehl, der in der Setup-Umgebung statt des Setup-Assistenten läuft (Direktinstallation);
    audit_commands: nur bei audit_mode – Befehle, die im Durchgang auditUser vor dem Löschen der Antwortdatei laufen
    (Direktinstallation: Setup-Partition aufräumen)."""
    opts = _audit_opts(opts)
    b = _Builder(opts.arch)

    # --- windowsPE: Setup selbst ---
    if pe:
        _international(b, "windowsPE", opts, winpe=True)
        setup = b.component("windowsPE", "Microsoft-Windows-Setup")
        cmds = [f"reg add HKLM\\SYSTEM\\Setup\\LabConfig /v {v} /t REG_DWORD /d 1 /f"
                for v in LABCONFIG] if opts.bypass_requirements else []
        if launch:
            cmds.append(launch)
        if cmds:
            b.commands(setup, "RunSynchronous", "RunSynchronousCommand", cmds)
        # UserData ohne ProductKey bricht Setup ab („<ProductKey> kann nicht gelesen werden“);
        # ein leerer Schlüssel wie bei Rufus: Setup fragt Edition/Schlüssel wie gewohnt
        user = b.sub(setup, "UserData")
        b.sub(b.sub(user, "ProductKey"), "Key", "")
    if not system:
        return b.xml()

    # --- specialize: Name, Zeitzone, Registry ---
    shell = b.component("specialize", "Microsoft-Windows-Shell-Setup")
    name = computer_name(opts.computer_name)
    if name:
        b.sub(shell, "ComputerName", name)
    if opts.product_key:
        b.sub(shell, "ProductKey", opts.product_key)
    if opts.swiss_region:
        b.sub(shell, "TimeZone", SWISS_TIMEZONE)
    regs = []
    if opts.local_account:
        regs.append("reg add HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\OOBE /v BypassNRO "
                    "/t REG_DWORD /d 1 /f")
    if opts.no_bitlocker:
        regs.append("reg add HKLM\\SYSTEM\\CurrentControlSet\\Control\\BitLocker /v PreventDeviceEncryption "
                    "/t REG_DWORD /d 1 /f")
    if opts.skip_privacy:
        regs.append("reg add HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\OOBE /v DisablePrivacyExperience "
                    "/t REG_DWORD /d 1 /f")
    if regs:
        deploy = b.component("specialize", "Microsoft-Windows-Deployment")
        b.commands(deploy, "RunSynchronous", "RunSynchronousCommand", regs)

    if opts.audit_mode:
        # I-038: Reseal/Mode=Audit im oobeSystem – Windows startet nach der Installation im Audit-Modus (eingebauter
        # Administrator, kein Konto). Microsoft Learn, „Boot Windows to Audit Mode or OOBE“ und „Mode
        # (microsoft-windows-deployment-reseal-mode)“: oobeSystem + Audit (ForceShutdownNow nicht gesetzt) „ignores all
        # other settings in the oobeSystem configuration pass“ und startet auditSystem. Darum steht die Region hier
        # in specialize (International-Core ist dort gültig) und oobeSystem enthält nur Reseal.
        _international(b, "specialize", opts, winpe=False)
        cmds = list(audit_commands or []) + AUDIT_DELETE_ANSWER_FILE
        audit = b.component("auditUser", "Microsoft-Windows-Deployment")
        b.commands(audit, "RunSynchronous", "RunSynchronousCommand", cmds)
        reseal = b.sub(b.component("oobeSystem", "Microsoft-Windows-Deployment"), "Reseal")
        b.sub(reseal, "Mode", "Audit")
        return b.xml()

    # --- oobeSystem: Willkommens-Assistent ---
    _international(b, "oobeSystem", opts, winpe=False)
    shell = b.component("oobeSystem", "Microsoft-Windows-Shell-Setup")
    oobe = b.sub(shell, "OOBE")
    b.sub(oobe, "HideEULAPage", "true")
    if opts.local_account:
        b.sub(oobe, "HideOnlineAccountScreens", "true")
        b.sub(oobe, "HideLocalAccountScreen", "true")
    if opts.skip_network:
        b.sub(oobe, "HideWirelessSetupInOOBE", "true")
    if opts.skip_privacy:
        b.sub(oobe, "ProtectYourPC", "3")
    if opts.local_account:
        accounts = b.sub(b.sub(shell, "UserAccounts"), "LocalAccounts")
        acc = b.sub(accounts, "LocalAccount", action="add")
        b.sub(acc, "Name", opts.local_account)
        b.sub(acc, "DisplayName", opts.local_account)
        b.sub(acc, "Group", "Administrators")
        pw = b.sub(acc, "Password")
        b.sub(pw, "Value", encode_password(opts.password) if opts.password else "")
        b.sub(pw, "PlainText", "false" if opts.password else "true")
        if not opts.password:
            # ohne Passwort: einmal automatisch anmelden, dann muss ein Passwort gesetzt werden
            auto = b.sub(shell, "AutoLogon")
            apw = b.sub(auto, "Password")
            b.sub(apw, "Value", "")
            b.sub(apw, "PlainText", "true")
            b.sub(auto, "Enabled", "true")
            b.sub(auto, "LogonCount", "1")
            b.sub(auto, "Username", opts.local_account)
            b.commands(shell, "FirstLogonCommands", "SynchronousCommand",
                       [f'net user "{opts.local_account}" /logonpasswordchg:yes',
                        "net accounts /maxpwage:unlimited"], key="CommandLine")
    return b.xml()


def summary(opts: WinOptions) -> list[str]:
    """Was die Anpassung bewirkt – für Dialog und Log."""
    lines = [AUDIT_SUMMARY] if opts.audit_mode else []
    opts = _audit_opts(opts)
    if opts.bypass_requirements:
        lines.append("Anforderungen umgangen: TPM 2.0, Secure Boot, RAM, CPU – nicht unterstützt, Updates nicht "
                     "garantiert")
    if opts.unsupported_hardware:
        lines.append("Windows 11 auf nicht unterstützter Hardware – Updates nicht garantiert")
    if opts.local_account:
        lines.append(f"Lokales Konto „{opts.local_account}“"
                     + (" mit Passwort" if opts.password else " – Passwort beim ersten Anmelden setzen"))
    if opts.skip_privacy:
        lines.append("Datenschutz-Fragen übersprungen")
    if opts.no_bitlocker:
        lines.append("Keine automatische BitLocker-Verschlüsselung")
    if opts.swiss_region:
        lines.append("Region Schweiz: Formate de-CH, Tastatur Schweiz, Zeitzone Zürich")
    if computer_name(opts.computer_name):
        lines.append(f"Computername {computer_name(opts.computer_name)}")
    if opts.product_key:
        lines.append(f"Windows-Schlüssel …{opts.product_key[-5:]} (Aktivierung, sobald Internet da ist)")
    return lines


def master_unattend(computer: str, product_key: str = "", swiss_region: bool = True, account: str = "") -> str:
    """Antwortdatei für ein zurückgespieltes Master-Image (Sysprep): Windows/Panther/unattend.xml.

    Computername und Key immer; Region Schweiz und lokales Konto optional. Ohne Konto fragt Windows beim ersten
    Start nach einem Benutzer; mit Konto ohne Passwort wird das Passwort beim ersten Anmelden gesetzt (es wird
    nirgends gespeichert)."""
    opts = WinOptions(bypass_requirements=False, local_account=account, password="", skip_privacy=True,
                      no_bitlocker=True, swiss_region=swiss_region, ui_language="", computer_name=computer,
                      skip_network=bool(account), product_key=product_key)
    return build(opts, pe=False, system=True)
