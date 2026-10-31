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
    local_account: str = "Benutzer"    # leer = Windows fragt selbst
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


def build(opts: WinOptions, pe: bool = True, system: bool = True, launch: str | None = None) -> str:
    """pe: Setup-Umgebung (windowsPE); system: erster Start (specialize, oobeSystem);
    launch: Befehl, der in der Setup-Umgebung statt des Setup-Assistenten läuft (Direktinstallation)."""
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
    lines = []
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
