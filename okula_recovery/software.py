"""Software installieren (I-020) aus der Software-Bibliothek des Tools (Ä-041) – ohne GTK.

Ablage auf dem NAS im eigenen Ordner neben „Verteilen“ (gesichert, für alle Tool-Rechner gleich):
    Software-Bibliothek/<key>-<version>/      ein Eintrag (Name = Auswahl, z. B. „vlc-3.0.24“)
        .okula.json                           Beschreibung (Format „okula-software“ wie I-020)
        <Installer> bzw. Inhalt des geladenen Ordners
    Software-Bibliothek/.<…>.partial/         während des Ladens – ein Abbruch hinterlässt nichts Halbes
Einträge entstehen nur über „Ins Tool laden …“ (ein Installer, INSTALLER_EXT) bzw. „Ordner laden …“ (Installer, der seine Dateien
daneben braucht, z. B. YSUSB_V213_Win/setup.exe): Kopie in die Bibliothek, danach Erkennung. Gleicher Inhalt
(SHA-256) wird nicht doppelt abgelegt. Sammelordner (z. B. „System Tools“) lassen sich als „nur kopieren“ markieren:
der Ordner landet auf dem öffentlichen Desktop unter Software\\<Eintrag>, installiert wird nichts.

Der Ordner Verteilen/Software gehört nur noch zu *Ordner senden*; der Katalog liest und schreibt ihn nicht.
Die Beschreibungen „.<Name>.okula.json“, die I-020 dort angelegt hat, räumt cleanup_distribute weg.

Beschreibung: Programmname, Version, Hersteller, Installer-Typ, Parameter für die stille Installation, erwartete
Rückgabewerte, Art (installieren, nur kopieren, nur von Hand), Installer (relativ), Grösse und SHA-256 des
Installers, dazu SHA-256 des ganzen Inhalts (Doppel erkennen) und woher der Eintrag geladen wurde. Dazu ein freier
Text „info“ der Techniker (Ä-050, max. MAX_INFO Zeichen) – bleibt bei „Neu erkennen“, geht an die neue Version.

Erkennung ohne Ausführen (Ä-043; Leser in installerinfo.py, Typen in KINDS, Quellen in docs/TECHNIK.md):
- MSI/MSP (Compound File), MSU (Cabinet), MSIX/APPX (ZIP) – an Endung und Kopf
- Windows-Programme: Kennungen im Kopf, im Manifest und in den angehängten Daten (NSIS, Inno Setup, Qt Installer
  Framework, InstallShield, WiX Burn, Advanced Installer, InstallBuilder, SFX-Archive …)
- Name, Version, Hersteller: Versionsinfo, MSI-Tabelle Property, Qt-IFW-config.xml, AppxManifest, NSIS-Skript
- Squirrel installiert nur für den angemeldeten Benutzer → „nur von Hand“
- sonst „Parameter fehlt“ mit Hinweis (erkannter Typ bzw. unbekannt, was zu tun ist) – nicht wählbar, bis
  Parameter hinterlegt sind. „Neu erkennen“ (redetect) wendet die Erkennung auf schon geladene Einträge an.

Neue Version: gleicher Programmname (aus dem Datei-/Ordnernamen ohne Version und Architektur, z. B.
vlc-3.0.24-win64.exe ↔ vlc-3.0.23-win64.exe) → Parameter, Art, Rückgabewerte und Info der vorigen Version in der
Bibliothek werden übernommen (Hinweis in der Liste). Die alte Version bleibt, bis sie gelöscht wird.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import struct
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Callable

from okula_recovery import distribute, installerinfo

LIBRARY_DIR = "Software-Bibliothek"   # auf dem NAS neben „Verteilen“
LIB_META = ".okula.json"              # Beschreibung im Ordner des Eintrags
PARTIAL = ".partial"
SOFTWARE_DIR = "Software"             # Verteilen/Software – nur noch für Ordner senden (Aufräumen von I-020)
META_SUFFIX = ".okula.json"
META_FORMAT = "okula-software"
META_VERSION = 1
APPX_EXT = (".msix", ".msixbundle", ".appx", ".appxbundle")     # App-Pakete (Ä-043)
INSTALLER_EXT = (".exe", ".msi", ".msp", ".msu") + APPX_EXT
HEAD_BYTES = 8 * 1024 * 1024          # Kennungen stehen im Programmteil vor den gepackten Daten
MAX_ARGS = 1000
MAX_INFO = 2000                       # Zeichen im freien Text „Info“ (Ä-050)
DEFAULT_EXIT_CODES = (0, 3010)
MSI_EXIT_CODES = (0, 1641, 3010)      # Windows Installer: 1641/3010 = Neustart eingeleitet bzw. nötig
REBOOT_CODES = (3010, 1641)           # ERROR_SUCCESS_REBOOT_REQUIRED, ERROR_SUCCESS_REBOOT_INITIATED

# Art des Eintrags
INSTALL, COPY, MANUAL = "install", "copy", "manual"
MODES = (INSTALL, COPY, MANUAL)
# Status in der Liste (Texte wie in der Oberfläche)
READY, MISSING, HAND, COPY_ONLY = "bereit", "Parameter fehlt", "nur von Hand", "nur kopieren"

UNKNOWN_HINT = ("Installer-Typ unbekannt – Parameter für die stille Installation in der Herstellerdoku nachsehen "
                "(Stichwort „silent install“ bzw. „unattended“), an einer VM testen und hier eintragen")
SFX_HINT = ("selbstentpackendes Archiv – Inhalt prüfen (z. B. mit 7-Zip öffnen): liegt darin ein bekannter Installer, "
            "den entpackten Ordner mit „Ordner laden …“ laden")
VM_TEST = " – an einer VM testen und hier eintragen"
IFW_TARGET = "<Zielordner>"
IFW_ARGS = f'install --root "{IFW_TARGET}" --accept-licenses --accept-messages --default-answer --confirm-command'

# Installer-Typ → (Anzeige, Parameter für die stille Installation, erfolgreiche Rückgabewerte, Hinweis bei
# „Parameter fehlt“). Quellen: docs/TECHNIK.md („Software installieren“, Tabelle). „Quelle nicht abgerufen“ =
# Angabe aus dem Gedächtnis des Umsetzungs-Agenten (Ä-043, 18.11.2026), nicht neu in der Herstellerdoku
# nachgelesen. Typen ohne belegbare Parameter bleiben „Parameter fehlt“ und nennen den vermuteten Parameter im
# Hinweis – ein falscher Parameter liesse den Installer am Gerät auf eine Eingabe warten (Abbruch nach 60 min).
KINDS: dict[str, tuple[str, str, tuple[int, ...], str]] = {
    # Microsoft Learn „msiexec“, „Standard Installer Command-Line Options“ (Quelle nicht abgerufen)
    "msi": ("MSI (Windows Installer)", "/qn /norestart", MSI_EXIT_CODES, ""),
    "msp": ("MSP (Patch für Windows Installer)", "/qn /norestart", MSI_EXIT_CODES, ""),
    # Microsoft Learn „wusa.exe“; 2359302 = 0x240006 WU_S_ALREADY_INSTALLED (Quelle nicht abgerufen)
    "msu": ("MSU (Windows-Update-Paket)", "/quiet /norestart", (0, 3010, 2359302), ""),
    # Microsoft Learn „Add-AppxProvisionedPackage“ (Quelle nicht abgerufen)
    "msix": ("MSIX/APPX (App-Paket)", "-SkipLicense", (0,), ""),
    # NSIS-Handbuch 3.2.1 „Common Options“ / 4.12 „Silent Installers“ (Quelle nicht abgerufen)
    "nsis": ("NSIS", "/S", DEFAULT_EXIT_CODES, ""),
    # electron-builder „NSIS“: /allusers = für alle Benutzer, sonst nur für das Konto SYSTEM (Quelle nicht abgerufen)
    "electron": ("electron-builder (NSIS)", "/S /allusers", DEFAULT_EXIT_CODES, ""),
    # Inno-Setup-Hilfe „Setup Command Line Parameters“ (Quelle nicht abgerufen)
    "inno": ("Inno Setup", "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-", DEFAULT_EXIT_CODES, ""),
    # Revenera „Setup.exe and Update.exe Command-Line Parameters“ (Quelle nicht abgerufen)
    "installshield": ("InstallShield (MSI)", '/s /v"/qn /norestart"', MSI_EXIT_CODES, ""),
    "installscript": ("InstallShield (InstallScript)", "", DEFAULT_EXIT_CODES,
                      "InstallScript braucht eine Antwortdatei: an einer VM „setup.exe /r /f1\"C:\\setup.iss\"“ "
                      "ausführen und durchklicken, Installer und setup.iss zusammen als Ordner laden, Parameter "
                      "/s /f1\"{ordner}\\setup.iss\" eintragen"),
    # WiX Toolset „Burn Command Line“ (Quelle nicht abgerufen)
    "wix": ("WiX Burn", "/quiet /norestart", MSI_EXIT_CODES, ""),
    # Microsoft-Bootstrapper (VC++ Redistributable, .NET-Runtime) sind Burn-Pakete; 1638 = neuere Version schon da
    "msburn": ("Microsoft-Bootstrapper (Burn)", "/install /quiet /norestart", (0, 1638, 1641, 3010), ""),
    # I-041: virtio-win-guest-tools.exe (Fedora virtio-win, Red Hat) ist ein Burn-Paket: Treiber + qemu-ga;
    # 3010 = Neustart nötig (Treiber), 1638 = andere Version schon da (Quelle nicht abgerufen)
    "virtio": ("virtio-win-Gasttools (Burn)", "/install /quiet /norestart", (0, 1638, 1641, 3010), ""),
    "squirrel": ("Squirrel", "", DEFAULT_EXIT_CODES, ""),
    # Qt Installer Framework „Using Command Line Interface“ (ab 4.0; Quelle nicht abgerufen, an Araneo geprüft)
    "qtifw": ("Qt Installer Framework", IFW_ARGS, (0,),
              "Qt Installer Framework vor 4.0 kennt keine Befehle zum stillen Installieren – nur mit Steuerskript "
              "(--script <Datei>.qs); Installer und Skript zusammen als Ordner laden" + VM_TEST),
    # Advanced Installer „EXE setup file“: /exenoui = ohne Oberfläche, Rest geht an msiexec (Quelle nicht abgerufen)
    "advinst": ("Advanced Installer", "/exenoui /qn /norestart", MSI_EXIT_CODES, ""),
    # InstallAware „Command Line Parameters“ /s (Quelle nicht abgerufen)
    "installaware": ("InstallAware", "/s", DEFAULT_EXIT_CODES, ""),
    # Wise Installation System /s (Quelle nicht abgerufen)
    "wise": ("Wise Installation", "/s", DEFAULT_EXIT_CODES, ""),
    # InstallBuilder „Unattended Installations“ (BitRock, später VMware; Quelle nicht abgerufen)
    "installbuilder": ("InstallBuilder (BitRock/VMware)", "--mode unattended --unattendedmodeui none",
                       DEFAULT_EXIT_CODES, ""),
    "setupfactory": ("Setup Factory", "", DEFAULT_EXIT_CODES,
                     "Setup Factory: stille Installation laut Hersteller meist mit /S (je nach Version)" + VM_TEST),
    "clickteam": ("Clickteam Install Creator", "", DEFAULT_EXIT_CODES,
                  "Install Creator: /S nur bei der Pro-Version" + VM_TEST),
    "smartinstall": ("Smart Install Maker", "", DEFAULT_EXIT_CODES,
                     "Smart Install Maker: Parameter für die stille Installation (vermutlich /s) in der "
                     "Herstellerdoku nachsehen" + VM_TEST),
    "actual": ("Actual Installer", "", DEFAULT_EXIT_CODES,
               "Actual Installer: stille Installation vermutlich mit /S" + VM_TEST),
    "createinstall": ("CreateInstall", "", DEFAULT_EXIT_CODES,
                      "CreateInstall: Parameter für die stille Installation (vermutlich -silent) in der "
                      "Herstellerdoku nachsehen" + VM_TEST),
    "ghost": ("Ghost Installer", "", DEFAULT_EXIT_CODES,
              "Ghost Installer: Parameter für die stille Installation (vermutlich -s) in der Herstellerdoku "
              "nachsehen" + VM_TEST),
    "iexpress": ("IExpress (selbstentpackend)", "", DEFAULT_EXIT_CODES,
                 "IExpress-Paket: /Q entpackt still und startet das enthaltene Programm – still nur, wenn dieses "
                 "selbst still läuft; " + SFX_HINT),
    "7zsfx": ("7-Zip-SFX (selbstentpackend)", "", DEFAULT_EXIT_CODES, SFX_HINT),
    "winrar": ("WinRAR-SFX (selbstentpackend)", "", DEFAULT_EXIT_CODES, SFX_HINT),
    "": ("unbekannt", "", DEFAULT_EXIT_CODES, UNKNOWN_HINT),
}
# Typen mit sicherem Namen und Version aus der Datei selbst (gehen dem Datei-/Ordnernamen vor)
AUTHORITATIVE = ("msi", "msp", "msu", "msix", "qtifw")
SQUIRREL_NOTE = "Squirrel installiert nur für den angemeldeten Benutzer – von Hand installieren"
FOLDER_NOTE = "Installer im Ordner wählen"

# Wörter ohne Bedeutung für den Programmnamen (Version, Architektur, „Setup“ …)
NOISE = {"setup", "install", "installer", "installation", "win", "win32", "win64", "windows", "x64", "x86", "x32",
         "amd64", "arm64", "64bit", "32bit", "bit", "full", "offline", "online", "web", "release", "final", "stable",
         "v", "x", "msi", "exe", "x86_64", "64", "32", "msp", "msu", "msix", "appx", "msixbundle", "appxbundle"}


class SoftwareError(Exception):
    pass


# ---------- Erkennung ----------

def _pe_sections(data: bytes) -> list[str]:
    """Namen der PE-Abschnitte (leer, wenn keine Windows-Programmdatei)."""
    if len(data) < 64 or data[:2] != b"MZ":
        return []
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if pe + 24 > len(data) or data[pe:pe + 4] != b"PE\0\0":
        return []
    count, = struct.unpack_from("<H", data, pe + 6)
    opt_size, = struct.unpack_from("<H", data, pe + 20)
    start = pe + 24 + opt_size
    names = []
    for i in range(min(count, 96)):
        off = start + 40 * i
        if off + 40 > len(data):
            break
        names.append(data[off:off + 8].rstrip(b"\0").decode("latin-1"))
    return names


_has = installerinfo.has_text           # Kennung als ASCII oder UTF-16 enthalten?

VERSION_KEYS = ("ProductName", "ProductVersion", "FileVersion", "FileDescription", "CompanyName", "InternalName",
                "OriginalFilename")


def version_info(data: bytes) -> dict[str, str]:
    """Texte aus der Versionsinfo (VS_VERSIONINFO → StringFileInfo) durch Suchen im Kopf der Datei – nur noch für
    Programme ohne lesbares Ressourcenverzeichnis (sonst installerinfo.parse_version_resource).

    Aufbau je Eintrag: wLength, wValueLength (Zeichen inkl. Abschluss), wType=1, Schlüssel (UTF-16, mit 0),
    Auffüllen auf 32 Bit ab Beginn des Eintrags, Wert (UTF-16, mit 0)."""
    out: dict[str, str] = {}
    for key in VERSION_KEYS:
        pat = key.encode("utf-16-le") + b"\0\0"
        i = data.find(pat)
        while i >= 6 and key not in out:
            length, value_len, kind = struct.unpack_from("<HHH", data, i - 6)
            j = i + len(pat)
            if (j - (i - 6)) % 4:
                j += 2
            if kind == 1 and 0 < value_len < 260 and length >= j - (i - 6):
                raw = data[j:j + 2 * value_len]
                value = raw.decode("utf-16-le", errors="replace").split("\0", 1)[0].strip()
                if value and value.isprintable():
                    out[key] = value
                    break
            i = data.find(pat, i + 1)
    return out


def _result(kind: str = "", args: str | None = None, **extra) -> dict:
    """Ergebnis der Erkennung: {kind, args, exit_codes, mode, note, hint, program, version, publisher,
    authoritative}. args None = Parameter des Typs; hint nur, wenn keine Parameter (→ „Parameter fehlt“)."""
    label, default_args, codes, hint = KINDS[kind]
    args = default_args if args is None else args
    info = {"kind": kind, "args": args, "exit_codes": list(codes), "mode": INSTALL, "note": "",
            "hint": "" if args else hint, "program": "", "version": "", "publisher": "",
            "authoritative": kind in AUTHORITATIVE}
    if kind == "squirrel":
        info.update(mode=MANUAL, note=SQUIRREL_NOTE, hint="")
    info.update({k: v for k, v in extra.items() if v is not None})
    return info


VERSION_RE_STRICT = re.compile(r"\d+(?:\.\d+){1,3}(?:[-+][0-9A-Za-z.]+)?")
# Namen von Registry-Werten der Deinstallation – folgen im NSIS-Skript oft direkt aufeinander (kein Hersteller)
NSIS_NAMES = {"DisplayName", "DisplayVersion", "DisplayIcon", "Publisher", "UninstallString", "QuietUninstallString",
              "InstallLocation", "URLInfoAbout", "URLUpdateInfo", "HelpLink", "EstimatedSize", "NoModify", "NoRepair",
              "VersionMajor", "VersionMinor", "Comments", "Contact", "Readme"}


def _nsis_text(header: bytes, name: str) -> str:
    """Fester Wert eines Registry-Eintrags aus dem NSIS-Skript, nur wenn plausibel."""
    value = installerinfo.nsis_value(header, name)
    if not value or value in NSIS_NAMES or re.fullmatch(r"[A-Z][a-z]+[A-Z]\w*", value) or "\\" in value \
            or value.lower().startswith(("http", "www.")):
        return ""
    if name == "DisplayVersion" and not VERSION_RE_STRICT.fullmatch(value):
        return ""
    return value


def _pe_version(vi: dict[str, str]) -> str:
    for key in ("ProductVersion", "FileVersion", "#ProductVersion", "#FileVersion"):
        value = vi.get(key, "")
        if value and value != "0.0.0.0" and re.search(r"\d", value):
            return value
    return ""


def ifw_target(target: str, is64: bool = True) -> str:
    """Zielordner aus <TargetDir> von Qt IFW: @ApplicationsDirX64@ → C:\\Program Files usw.; „“, wenn eine andere
    Variable (z. B. @HomeDir@ – als SYSTEM sinnlos) übrig bleibt."""
    repl = {"@ApplicationsDirX64@": r"C:\Program Files", "@ApplicationsDirX86@": r"C:\Program Files (x86)",
            "@ApplicationsDir@": r"C:\Program Files" if is64 else r"C:\Program Files (x86)", "@RootDir@": "C:\\"}
    for k, v in repl.items():
        target = target.replace(k, v)
    target = re.sub(r"\\{2,}", r"\\", target.replace("/", "\\")).rstrip("\\")
    if "@" in target or '"' in target or not re.fullmatch(r"[A-Za-z]:\\[^\x00-\x1f]*", target):
        return ""
    return target


def _qt_ifw(blob: installerinfo.Blob, pe: installerinfo.PE, head: bytes, overlay: bytes) -> dict | None:
    """Qt Installer Framework: config.xml/Updates.xml aus den angehängten Qt-Ressourcen, Version des Frameworks aus
    dem Text „Built with Qt Installer Framework x.y.z“ (Kopf bzw. Abschnitt .rdata)."""
    files: dict[str, bytes] = {}
    if overlay[:4] == b"qres":
        data = blob.read(pe.image_end, 8 << 20)
        pos = 0
        for _ in range(8):
            i = data.find(b"qres", pos)
            if i < 0:
                break
            for k, v in installerinfo.rcc_files(data[i:], {"config.xml", "Updates.xml"}).items():
                files.setdefault(k, v)
            if len(files) == 2:
                break
            pos = i + 4
    config = files.get("config.xml", b"").decode("utf-8", errors="replace")
    updates = files.get("Updates.xml", b"").decode("utf-8", errors="replace")
    rx = re.compile(rb"Qt Installer Framework (\d+)\.(\d+)(?:\.(\d+))?")
    m = rx.search(head) or rx.search(installerinfo.section_bytes(blob, pe, ".rdata"))
    if "<Installer>" not in config and m is None:
        return None
    cfg = installerinfo.xml_tags(config, "Name", "Version", "Title", "Publisher", "TargetDir")
    upd = installerinfo.xml_tags(updates, "ApplicationName", "ApplicationVersion")
    program = cfg.get("Name") or upd.get("ApplicationName") or cfg.get("Title") or ""
    version = cfg.get("Version") or upd.get("ApplicationVersion") or ""
    framework = tuple(int(x) for x in m.groups() if x is not None) if m else ()
    target = ifw_target(cfg.get("TargetDir", ""), pe.is64)
    hint = ""
    if not framework:
        hint = ("Qt Installer Framework, Version des Frameworks nicht erkannt – ab 4.0: "
                + IFW_ARGS.replace(IFW_TARGET, target or "C:\\Program Files\\…") + VM_TEST)
    elif framework < (4, 0):
        hint = KINDS["qtifw"][3]
    elif not target:
        hint = (f"Qt Installer Framework: Zielordner „{cfg.get('TargetDir', '')}“ nicht eindeutig – Parameter "
                + IFW_ARGS + " mit dem Zielordner eintragen")
    args = IFW_ARGS.replace(IFW_TARGET, target) if not hint else ""
    note = f"Qt Installer Framework {'.'.join(map(str, framework))}" if framework else ""
    return _result("qtifw", args, hint=hint or None, note=note, program=program, version=version,
                   publisher=cfg.get("Publisher", ""))


def _detect_pe(blob: installerinfo.Blob, head: bytes, filename: str = "") -> dict:
    """Windows-Programm: Typ aus Abschnitten, Manifest, Kopf und angehängten Daten; Angaben aus der Versionsinfo."""
    pe = installerinfo.pe_info(blob)
    vi: dict[str, str] = {}
    manifest, overlay, sections = "", b"", []
    if pe is not None:
        res = installerinfo.resources(blob, pe, 16, limit=1)
        vi = installerinfo.parse_version_resource(res[0]) if res else {}
        manifest = installerinfo.manifest_text(blob, pe)
        overlay = blob.read(pe.image_end, 1 << 16) if pe.image_end else b""
        sections = pe.names
    if not any(k in vi for k in VERSION_KEYS):
        vi.update(version_info(head))            # ohne Ressourcenverzeichnis: Suche im Kopf (wie bis Ä-041)
    marks = head + b"\0" + manifest.encode("utf-8", errors="replace") + b"\0" + overlay
    meta = {"program": vi.get("ProductName") or vi.get("FileDescription") or "", "version": _pe_version(vi),
            "publisher": vi.get("CompanyName", "")}
    company = meta["publisher"].lower()
    original = (vi.get("OriginalFilename", "") + " " + vi.get("InternalName", "")).lower()

    if ".wixburn" in sections:
        # I-041: Gasttools für Test-VMs (Fedora virtio-win, Red Hat) – Burn-Paket mit Treibern und qemu-ga
        if "red hat" in company or "virtio-win" in (meta["program"] + " " + filename).lower():
            return _result("virtio", **meta)
        return _result("msburn" if "microsoft" in company else "wix", **meta)
    if pe is not None and (overlay[:4] == b"qres" or _has(head, "Qt Installer Framework")):
        ifw = _qt_ifw(blob, pe, head, overlay)
        if ifw is not None:
            for k, v in meta.items():
                ifw[k] = ifw[k] or v
            return ifw
    if _has(marks, "Inno Setup Setup Data", "JR.Inno.Setup", "Inno Setup"):
        return _result("inno", **meta)
    if _has(marks, "Nullsoft.NSIS", "NullsoftInst", "Nullsoft Install System"):
        header = installerinfo.nsis_header(blob, pe, head)
        if not meta["program"]:
            meta["program"] = re.sub(r"\s+v?\d+(?:\.\d+)+$", "", _nsis_text(header, "DisplayName"))
        meta["version"] = meta["version"] or _nsis_text(header, "DisplayVersion")
        meta["publisher"] = meta["publisher"] or _nsis_text(header, "Publisher")
        electron = _has(header, "app-64.7z", "app-32.7z", "app-arm64.7z")
        return _result("electron" if electron else "nsis", **meta)
    if _has(marks, "BitRock", "InstallBuilder"):
        return _result("installbuilder", **meta)
    if _has(marks, "InstallShield", "ISSetup.dll", "ISSetupStream"):
        # setup.inx = übersetztes InstallScript (InstallScript- bzw. InstallScript-MSI-Projekt) → Antwortdatei nötig
        script = _has(marks, "setup.inx", "Setup.inx", "SETUP.INX")
        return _result("installscript" if script else "installshield", **meta)
    simple = (("advinst", ("Caphyon", "Advanced Installer", "AI_SETUPEXEPATH")),
              ("installaware", ("InstallAware",)),
              ("wise", ("WiseMain", "Wise Installation", "Wise Solutions")),
              ("setupfactory", ("Setup Factory", "Indigo Rose", "irsetup.exe")),
              ("clickteam", ("Clickteam", "Install Creator")),
              ("smartinstall", ("Smart Install Maker",)),
              ("actual", ("Actual Installer",)),
              ("createinstall", ("CreateInstall",)),
              ("ghost", ("Ghost Installer", "GhostInstaller", "Ethalone")))
    for kind, texts in simple:
        if _has(marks, *texts):
            return _result(kind, **meta)
    if _has(marks, "Squirrel") or "SquirrelAwareVersion" in vi:
        return _result("squirrel", **meta)
    if original.startswith("wextract") or _has(marks, "IExpress"):
        return _result("iexpress", **meta)
    if b";!@Install@!UTF-8!" in overlay or overlay.startswith(b"7z\xbc\xaf\x27\x1c") \
            or _has(marks, "7-Zip Self-extracting", "7zS.sfx"):
        return _result("7zsfx", **meta)
    if b"Rar!\x1a\x07" in overlay[:4096] or _has(marks, "WinRAR SFX", "WinRAR self-extracting"):
        return _result("winrar", **meta)
    return _result("", **meta)


def _detect_blob(blob: installerinfo.Blob, filename: str) -> dict:
    lower = filename.lower()
    head = blob.read(0, HEAD_BYTES)
    if lower.endswith(".msp"):
        return _result("msp")
    if lower.endswith(".msu") or (head[:4] == b"MSCF" and not lower.endswith(".exe")):
        kb = re.search(r"kb(\d{6,8})", lower)
        return _result("msu", program="Windows-Update" if kb else None, version=f"KB{kb.group(1)}" if kb else None)
    if lower.endswith(APPX_EXT) or (head[:4] == b"PK\x03\x04" and not lower.endswith(".exe")):
        m = installerinfo.appx_manifest(blob)
        return _result("msix", program=m.get("DisplayName") or m.get("Name"), version=m.get("Version"),
                       publisher=m.get("PublisherDisplayName") or installerinfo.publisher_cn(m.get("Publisher", "")))
    if lower.endswith(".msi") or head[:8] == installerinfo.CFB_MAGIC:
        p = installerinfo.msi_properties(blob)
        return _result("msi", program=p.get("ProductName"), version=p.get("ProductVersion"),
                       publisher=p.get("Manufacturer"))
    if head[:2] != b"MZ":
        return _result("")
    return _detect_pe(blob, head, filename)


def detect_bytes(data: bytes, filename: str) -> dict:
    """Installer-Typ und Angaben aus den Bytes einer Datei (Tests, Proben) – siehe detect."""
    with installerinfo.Blob(data) as blob:
        return _detect_blob(blob, filename)


def detect(path: str | Path) -> dict:
    """Installer-Typ, Parameter, Rückgabewerte und Name/Version/Hersteller einer Datei – nur lesend, ohne sie
    auszuführen: {kind, args, exit_codes, mode, note, hint, program, version, publisher, authoritative}."""
    path = Path(path)
    try:
        with installerinfo.Blob(path) as blob:
            return _detect_blob(blob, path.name)
    except OSError:
        return _result("")


# ---------- Programmname und Version aus dem Namen ----------

VERSION_RE = re.compile(r"\d+(?:[._]\d+)+")
NUMBER_RE = re.compile(r"\d{3,}")


def split_name(name: str) -> tuple[str, str, str]:
    """Datei-/Ordnername → (Programmname, Version, Vergleichsschlüssel).

    „vlc-3.0.24-win64.exe“ → („vlc“, „3.0.24“, „vlc“); „AcroRdrDC2400221005_de_DE.exe“ →
    („AcroRdrDC“, „2400221005“, „acrordrdc-de-de“); „Firefox Setup 120.0.1.exe“ → („Firefox Setup“, „120.0.1“,
    „firefox“). Schlüssel ohne Version, Architektur und „Setup“ – leer bei Namen wie „setup.exe“."""
    stem = name
    ext = next((x for x in INSTALLER_EXT if stem.lower().endswith(x)), "")
    if ext:
        stem = stem[:-len(ext)]
    m = VERSION_RE.search(stem) or NUMBER_RE.search(stem)
    if m:
        before, version, after = stem[:m.start()], m.group(0).replace("_", "."), stem[m.end():]
    else:
        before, version, after = stem, "", ""
    program = re.sub(r"\s+v$", "", re.sub(r"[\s._-]+", " ", before).strip(), flags=re.IGNORECASE).strip() \
        or re.sub(r"[\s._-]+", " ", stem).strip()
    return clean_program(program), version, name_key(before + " " + after)


SETUP_WORDS_RE = re.compile(r"(?:[\s._-]+(?:setup|installer|install|installation))+$", re.IGNORECASE)
SETUP_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?:Setup|Installer|Install)$")


def clean_program(name: str) -> str:
    """Programmname ohne „Setup“/„Installer“ am Ende („AraneoInstaller“ → „Araneo“, „OBS Studio Installer“ →
    „OBS Studio“); bleibt nichts übrig, der Name wie er war."""
    text = name.strip()
    cleaned = SETUP_CAMEL_RE.sub("", SETUP_WORDS_RE.sub("", text)).strip(" ._-")
    return cleaned or text


def name_key(text: str) -> str:
    """Vergleichsschlüssel: Kleinbuchstaben, ohne Zahlen, Version, Architektur und Füllwörter."""
    tokens = [t for t in re.split(r"[^0-9a-z]+", text.lower()) if t]
    words = [t for t in tokens if t not in NOISE and not t.isdigit() and not re.fullmatch(r"v\d+", t)]
    return "-".join(words)


def _version_tuple(text: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", text or "")[:6])


# ---------- Beschreibung ----------

def library_dir(nas_root: str | Path) -> Path:
    """Software-Bibliothek auf dem NAS (bzw. im Demo-Speicher)."""
    return Path(nas_root) / LIBRARY_DIR


def ensure_library(nas_root: str | Path) -> Path:
    base = library_dir(nas_root)
    base.mkdir(parents=True, exist_ok=True)
    return base


def software_dir(nas_root: str | Path) -> Path:
    """Verteilen/Software – nur für Ordner senden; hier nur noch zum Aufräumen der I-020-Beschreibungen."""
    return distribute.root(nas_root) / SOFTWARE_DIR


def meta_path(entry: Path) -> Path:
    """Beschreibung eines Eintrags der Bibliothek (im Ordner des Eintrags)."""
    return entry / LIB_META


def _read_meta(path: Path) -> dict | None:
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return meta if isinstance(meta, dict) and meta.get("format") == META_FORMAT else None


def _write_meta(entry: Path, meta: dict) -> bool:
    """Speichern (atomar); False, wenn der Ordner nicht beschreibbar ist (Liste funktioniert trotzdem)."""
    target = meta_path(entry)
    tmp = target.with_name(target.name + ".tmp")
    try:
        tmp.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(target)
        return True
    except OSError:
        return False


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(4 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def parse_exit_codes(text: str) -> list[int]:
    """„0, 3010“ → [0, 3010]; Fehler bei anderem als Zahlen."""
    codes = []
    for part in re.split(r"[\s,;]+", text.strip()):
        if not part:
            continue
        if not re.fullmatch(r"-?\d{1,10}", part) or not -2**31 <= int(part) < 2**32:
            raise SoftwareError(f"Rückgabewert „{part}“ ist keine Zahl")
        codes.append(int(part))
    if not codes:
        raise SoftwareError("Mindestens einen Rückgabewert für „erfolgreich“ angeben (meist 0)")
    return list(dict.fromkeys(codes))


def check_args(args: str) -> str:
    args = args.strip()
    if len(args) > MAX_ARGS:
        raise SoftwareError(f"Parameter zu lang (max. {MAX_ARGS} Zeichen)")
    if any(ord(c) < 32 for c in args):
        raise SoftwareError("Parameter enthalten Steuerzeichen oder Zeilenumbrüche")
    return args


def check_info(text: str) -> str:
    """Freier Text „Info“ (Ä-050): Zeilenumbrüche vereinheitlichen, Steuerzeichen ausser Zeilenumbruch und Tab
    entfernen, Leerraum am Anfang und Ende weg; Fehler über MAX_INFO Zeichen."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(c for c in text if c in "\n\t" or ord(c) >= 32).strip()
    if len(text) > MAX_INFO:
        raise SoftwareError(f"Info zu lang ({len(text)} Zeichen, max. {MAX_INFO})")
    return text


def first_line(text: str) -> str:
    """Erste Zeile eines Textes, „ …“ angehängt, wenn weitere folgen (Spalte „Info“)."""
    lines = text.strip().split("\n")
    return lines[0].rstrip() + (" …" if len(lines) > 1 else "")


@dataclass
class Entry:
    """Ein Programm in der Software-Bibliothek (Ordner Software-Bibliothek/<name>)."""
    name: str                        # Ordnername in der Bibliothek = Auswahl
    is_dir: bool                     # als Ordner geladen (Installer wählbar, „nur kopieren“ möglich)
    path: Path                       # Ordner des Eintrags
    size: int                        # Bytes (alle Dateien ohne Beschreibung)
    meta: dict = field(default_factory=dict)
    candidates: list[str] = field(default_factory=list)   # mögliche Installer (relativ zum Eintrag)

    @property
    def program(self) -> str:
        return str(self.meta.get("program") or self.name)

    @property
    def version(self) -> str:
        return str(self.meta.get("program_version") or "")

    @property
    def publisher(self) -> str:
        """Hersteller (Ä-043) – aus Versionsinfo, MSI, Qt IFW, App-Paket oder von Hand."""
        return str(self.meta.get("publisher") or "")

    @property
    def info(self) -> str:
        """Freier Text der Techniker (Ä-050), z. B. „Lizenz im Tresor“ – nicht zu verwechseln mit note."""
        return str(self.meta.get("info") or "")

    @property
    def search_text(self) -> str:
        """Alles, worin das Suchfeld der Software-Bibliothek sucht (klein geschrieben)."""
        return " ".join((self.name, self.program, self.version, self.publisher, self.kind_label, self.args,
                         self.status, self.info)).lower()

    @property
    def kind(self) -> str:
        return str(self.meta.get("kind") or "")

    @property
    def detected_label(self) -> str:
        """Erkannter Typ (unabhängig von einer Änderung von Hand)."""
        return KINDS.get(str(self.meta.get("detected") or ""), KINDS[""])[0]

    @property
    def detected_args(self) -> str:
        """Parameter, die die Erkennung vorschlägt (bei Qt IFW mit Zielordner)."""
        return str(self.meta.get("detected_args") or KINDS.get(str(self.meta.get("detected") or ""), KINDS[""])[1])

    @property
    def hint(self) -> str:
        """Was bei „Parameter fehlt“ zu tun ist (Typ-Hinweis bzw. „unbekannt“) – leer, sobald Parameter da sind."""
        if self.mode != INSTALL or self.args.strip() or self.installer not in self.candidates:
            return ""
        return str(self.meta.get("hint") or KINDS.get(self.kind, KINDS[""])[3] or UNKNOWN_HINT)

    @property
    def kind_label(self) -> str:
        return KINDS.get(self.kind, KINDS[""])[0] if self.mode != COPY else "Ordner"

    @property
    def args(self) -> str:
        return str(self.meta.get("args") or "")

    @property
    def mode(self) -> str:
        mode = self.meta.get("mode")
        return mode if mode in MODES and (mode != COPY or self.is_dir) else INSTALL

    @property
    def installer(self) -> str:
        """Installer relativ zum Ordner des Eintrags („/“); bei einer geladenen Datei deren Name."""
        return str(self.meta.get("installer") or "")

    @property
    def loaded_from(self) -> str:
        return str(self.meta.get("loaded_from") or "")

    @property
    def content_sha256(self) -> str:
        return str(self.meta.get("content_sha256") or "")

    @property
    def exit_codes(self) -> list[int]:
        codes = self.meta.get("exit_codes")
        return [int(c) for c in codes] if isinstance(codes, list) and codes else list(DEFAULT_EXIT_CODES)

    @property
    def key(self) -> str:
        return str(self.meta.get("key") or "")

    @property
    def adopted_from(self) -> str:
        return str(self.meta.get("adopted_from") or "")

    @property
    def status(self) -> str:
        if self.mode == MANUAL:
            return HAND
        if self.mode == COPY:
            return COPY_ONLY
        if self.installer not in self.candidates:
            return MISSING
        return READY if self.args.strip() else MISSING

    @property
    def selectable(self) -> bool:
        return self.status in (READY, COPY_ONLY)

    @property
    def note(self) -> str:
        """Hinweis für die Liste (neue Version, Squirrel, Installer wählen, was bei „Parameter fehlt“ zu tun ist)."""
        notes = []
        if self.adopted_from:
            notes.append(f"Parameter von „{self.adopted_from}“ übernommen (neue Version)")
        if self.mode == INSTALL and self.installer not in self.candidates:
            notes.append(FOLDER_NOTE if self.candidates else "Kein Installer (.exe, .msi, .msix …) im Ordner")
        if self.meta.get("note"):
            notes.append(str(self.meta["note"]))
        if self.hint:
            notes.append(self.hint)
        return " · ".join(notes)

    @property
    def label(self) -> str:
        """„VLC media player 3.0.24“ – für Log, Verlauf und Skript."""
        version = self.version
        return f"{self.program} {version}" if version and version not in self.program else self.program


def _folder_info(path: Path) -> tuple[int, list[str], list[tuple[str, os.stat_result]]]:
    """Grösse, Installer-Kandidaten (INSTALLER_EXT, relativ) und alle Dateien eines Ordners (ohne Links)."""
    size, candidates, files = 0, [], []
    for dirpath, dirnames, filenames in os.walk(path):
        here = Path(dirpath)
        dirnames[:] = sorted(d for d in dirnames if not (here / d).is_symlink())
        for f in sorted(filenames):
            full = here / f
            try:
                st = full.lstat()
            except OSError:
                continue
            if not stat.S_ISREG(st.st_mode) or (f.startswith(".") and f.endswith(META_SUFFIX)) \
                    or (here == path and f.startswith(LIB_META)):
                continue
            rel = full.relative_to(path).as_posix()
            size += st.st_size
            files.append((rel, st))
            if f.lower().endswith(INSTALLER_EXT):
                candidates.append(rel)
    # Installer direkt im Ordner zuerst, dann nach Tiefe und Name
    candidates.sort(key=lambda r: (r.count("/"), r.lower()))
    return size, candidates, files


def pick_installer(candidates: list[str]) -> str:
    """Eindeutiger Installer eines Ordners (genau einer direkt im Ordner bzw. genau einer insgesamt), sonst „“."""
    top = [c for c in candidates if "/" not in c]
    return top[0] if len(top) == 1 else (candidates[0] if len(candidates) == 1 else "")


def _fresh_meta(folder: Path, source_name: str, is_dir: bool, candidates: list[str],
                installer: str | None = None) -> dict:
    """Neue Beschreibung: Name/Version aus dem Namen der geladenen Datei bzw. des Ordners, Installer-Typ aus der
    Datei. folder: Ordner, in dem die Dateien liegen (Eintrag bzw. .partial)."""
    program, version, key = split_name(source_name)
    meta = {"format": META_FORMAT, "version": META_VERSION, "program": program, "program_version": version,
            "publisher": "", "key": key, "kind": "", "detected": "", "args": "", "detected_args": "",
            "exit_codes": list(DEFAULT_EXIT_CODES), "mode": INSTALL, "installer": "", "note": "", "hint": "",
            "adopted_from": "", "edited": False, "info": "", "source": "folder" if is_dir else "file"}
    pick = installer if installer is not None else (pick_installer(candidates) if is_dir else source_name)
    meta["installer"] = pick if pick in candidates else ""
    if meta["installer"]:
        _apply_detection(meta, folder / meta["installer"])
    else:
        _stamp(meta, None)
    return meta


def _apply_detection(meta: dict, installer: Path) -> None:
    """Erkennung übernehmen: Typ, Parameter, Rückgabewerte, Art, Hinweise, Hersteller; Name aus der Datei geht dem
    Datei-/Ordnernamen vor. Version: aus dem Namen, ausser die Datei ist massgebend (MSI, Qt IFW, App-Paket, MSU)
    bzw. der Name hat nur eine Zahl ohne Punkt (z. B. Build „701“ statt 3.3.1)."""
    found = detect(installer)
    meta.update(kind=found["kind"], detected=found["kind"], args=found["args"], detected_args=found["args"],
                exit_codes=list(found["exit_codes"]), mode=found["mode"], note=found["note"], hint=found["hint"],
                publisher=found["publisher"][:120])
    program = clean_program(found["program"])
    if program and not re.fullmatch(r"[\d.\s]*", program):
        meta["program"] = program[:120]
    version, current = found["version"][:60], str(meta.get("program_version") or "")
    if version and (not current or found["authoritative"] or ("." not in current and "." in version)):
        meta["program_version"] = version
    _stamp(meta, installer)


def _stamp(meta: dict, installer: Path | None) -> None:
    """Grösse, Zeit und SHA-256 des Installers (bzw. leer)."""
    if installer is None or not installer.is_file():
        meta.update(size=0, mtime=0, sha256="")
        return
    st = installer.stat()
    if meta.get("size") == st.st_size and meta.get("mtime") == int(st.st_mtime) and meta.get("sha256"):
        return
    try:
        digest = sha256(installer)
    except OSError:
        digest = ""
    meta.update(size=st.st_size, mtime=int(st.st_mtime), sha256=digest)


ADOPT_FIELDS = ("kind", "args", "exit_codes", "mode", "note")   # „info“ eigens in _adopt (auch ohne Parameter)


def _adopt(meta: dict, name: str, others: dict[str, dict], candidates: list[str]) -> None:
    """Neue Version: Parameter der vorigen Beschreibung mit gleichem Programmnamen übernehmen. Die Info (Ä-050)
    kommt auch dann mit, wenn die vorige Version keine Parameter hat (von der neuesten mit Info)."""
    key = meta.get("key") or ""
    prog = name_key(str(meta.get("program") or ""))
    matches, with_info = [], []
    for other_name, other in others.items():
        if other_name == name:
            continue
        same = (key and other.get("key") == key) or (prog and name_key(str(other.get("program") or "")) == prog)
        useful = other.get("mode") in (COPY, MANUAL) or str(other.get("args") or "").strip()
        order = (_version_tuple(str(other.get("program_version") or "")), other_name, other)
        if same and useful:
            matches.append(order)
        if same and str(other.get("info") or "").strip():
            with_info.append(order)
    if with_info and not str(meta.get("info") or "").strip():
        # eigene Info (z. B. bei „Neu erkennen“) bleibt; sonst die der neuesten Version mit Info
        meta["info"] = max(with_info, key=lambda m: (m[0], m[1]))[2]["info"]
    if not matches:
        return
    _v, source_name, source = max(matches, key=lambda m: (m[0], m[1]))
    for f in ADOPT_FIELDS:
        if f in source:
            meta[f] = source[f]
    old_installer = str(source.get("installer") or "")
    if candidates and old_installer:
        # gleicher Dateiname im neuen Ordner, sonst der gleiche Name ohne Version
        same_name = [c for c in candidates if c == old_installer]
        same_key = [c for c in candidates if name_key(c) == name_key(old_installer) and name_key(c)]
        if same_name or same_key:
            meta["installer"] = (same_name or same_key)[0]
    meta["adopted_from"] = source_name


def scan(nas_root: str | Path, write: bool = True) -> list[Entry]:
    """Alle Programme der Software-Bibliothek. Nur die Bibliothek – Verteilen/Software wird nicht gelesen.

    Ein Ordner ohne Beschreibung (von Hand hineinkopiert) erhält eine neue, sofern write."""
    base = library_dir(nas_root)
    try:
        items = sorted(os.scandir(base), key=lambda e: e.name.lower())
    except OSError:
        return []
    entries = []
    for e in items:
        if e.name.startswith(".") or e.is_symlink() or not e.is_dir(follow_symlinks=False):
            continue                  # .partial (Laden läuft/abgebrochen), Dateien, Links
        path = base / e.name
        size, candidates, _files = _folder_info(path)
        meta = _read_meta(meta_path(path))
        if meta is None:
            meta = _fresh_meta(path, e.name, True, candidates)
            if write:
                _write_meta(path, meta)
        is_dir = meta.get("source") != "file"
        entries.append(Entry(e.name, is_dir, path, size, meta, candidates))
    entries.sort(key=lambda x: (x.program.lower(), _version_tuple(x.version), x.name.lower()))
    return entries


def find(entries: list[Entry], name: str) -> Entry | None:
    return next((e for e in entries if e.name == name), None)


def update(nas_root: str | Path, name: str, *, program: str | None = None, version: str | None = None,
           args: str | None = None, exit_codes: str | list[int] | None = None, mode: str | None = None,
           installer: str | None = None, publisher: str | None = None, info: str | None = None) -> Entry:
    """Beschreibung von Hand ändern (Extras → Software-Bibliothek …) und speichern. Nur die Info (Ä-050) gilt
    nicht als „von Hand geändert“ – „Neu erkennen“ behält sie ohnehin."""
    entries = scan(nas_root)
    entry = find(entries, name)
    if entry is None:
        raise SoftwareError(f"„{name}“ liegt nicht (mehr) in der Software-Bibliothek")
    meta = dict(entry.meta)
    if installer is not None and entry.is_dir:
        if installer and installer not in entry.candidates:
            raise SoftwareError(f"„{installer}“ ist kein Installer im Ordner")
        if installer != meta.get("installer"):
            meta["installer"] = installer
            if installer:
                keep = {k: meta[k] for k in ("program", "program_version")}
                _apply_detection(meta, entry.path / installer)
                meta.update(keep)
            else:
                _stamp(meta, None)
    if program is not None:
        if not program.strip():
            raise SoftwareError("Programmname fehlt")
        meta["program"] = program.strip()[:120]
    if version is not None:
        meta["program_version"] = version.strip()[:60]
    if publisher is not None:
        meta["publisher"] = publisher.strip()[:120]
    if args is not None:
        meta["args"] = check_args(args)
    if exit_codes is not None:
        meta["exit_codes"] = parse_exit_codes(exit_codes) if isinstance(exit_codes, str) else \
            parse_exit_codes(",".join(str(c) for c in exit_codes))
    if mode is not None:
        if mode not in MODES or (mode == COPY and not entry.is_dir):
            raise SoftwareError("Ungültige Art")
        meta["mode"] = mode
        if mode == INSTALL and meta.get("kind") == "squirrel":
            meta["note"] = ""
    if info is not None:
        meta["info"] = check_info(info)
    if any(v is not None for v in (program, version, args, exit_codes, mode, installer, publisher)):
        meta["edited"] = True
    if not _write_meta(entry.path, meta):
        raise SoftwareError("Beschreibung konnte nicht gespeichert werden (Ordner auf dem NAS schreibgeschützt?)")
    entry.meta = meta
    return entry


class EditedError(SoftwareError):
    """„Neu erkennen“ würde von Hand geänderte Angaben überschreiben – erst nach Rückfrage (overwrite_edited)."""


KEEP_ON_REDETECT = ("key", "source", "content_sha256", "loaded_from", "loaded", "info")


def redetect(nas_root: str | Path, name: str, overwrite_edited: bool = False) -> Entry:
    """„Neu erkennen“ (Ä-043): Erkennung erneut auf den Installer eines Eintrags anwenden – Typ, Parameter,
    Rückgabewerte, Art, Name, Version, Hersteller wie beim Laden. Ordner, Schlüssel (gespeicherte Auswahlen),
    Installer im Ordner und Herkunft bleiben. Von Hand geänderte Angaben („edited“) nur mit overwrite_edited,
    sonst EditedError. Findet die Erkennung keine Parameter, übernimmt der Eintrag sie wie beim Laden von einer
    anderen Version desselben Programms (_adopt)."""
    entries = scan(nas_root)
    entry = find(entries, name)
    if entry is None:
        raise SoftwareError(f"„{name}“ liegt nicht (mehr) in der Software-Bibliothek")
    if entry.meta.get("edited") and not overwrite_edited:
        raise EditedError(f"„{entry.label}“ wurde von Hand geändert")
    source_name = Path(entry.loaded_from).name if entry.loaded_from else \
        (entry.installer if not entry.is_dir and entry.installer else entry.name)
    installer = entry.installer if entry.installer in entry.candidates else None
    meta = _fresh_meta(entry.path, source_name, entry.is_dir, entry.candidates, installer)
    for k in KEEP_ON_REDETECT:
        if k in entry.meta:
            meta[k] = entry.meta[k]
    if meta.get("mode") == INSTALL and not str(meta.get("args") or "").strip():
        _adopt(meta, entry.name, {e.name: e.meta for e in entries}, entry.candidates)
    meta["redetected"] = time.strftime("%Y-%m-%d %H:%M:%S")
    if not _write_meta(entry.path, meta):
        raise SoftwareError("Beschreibung konnte nicht gespeichert werden (Ordner auf dem NAS schreibgeschützt?)")
    entry.meta = meta
    return entry


# ---------- Bibliothek: laden, löschen, aufräumen (Ä-041) ----------

COPY_CHUNK = 8 * 1024 * 1024
SPACE_RESERVE = 1024**3


@dataclass
class Source:
    """Was geladen werden soll – vor dem Kopieren ermittelt (Umfang, Installer im Ordner)."""
    path: Path
    is_dir: bool
    files: list[tuple[str, Path, int]] = field(default_factory=list)   # (relativ, Quelle, Grösse)
    bytes: int = 0
    candidates: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)                   # Links, Sonderdateien

    @property
    def installer(self) -> str:
        """Eindeutiger Installer (Datei: sie selbst), sonst „“ – dann fragt die Oberfläche nach."""
        return self.path.name if not self.is_dir else pick_installer(self.candidates)


@dataclass
class LoadResult:
    entry: Entry
    duplicate: bool = False          # gleicher Inhalt lag schon in der Bibliothek – nichts abgelegt


def inspect(source: str | Path, nas_root: str | Path | None = None) -> Source:
    """Datei (Installer, INSTALLER_EXT) oder Ordner prüfen, bevor etwas kopiert wird."""
    from okula_recovery import nasfiles
    src = Path(source)
    if src.is_symlink() or not src.exists():
        raise SoftwareError(f"„{src.name}“ ist keine normale Datei bzw. kein Ordner")
    if nas_root is not None:
        lib = library_dir(nas_root).resolve()
        if src.resolve() == lib or src.resolve().is_relative_to(lib):
            raise SoftwareError("Liegt schon in der Software-Bibliothek")
    if src.is_file():
        if not src.name.lower().endswith(INSTALLER_EXT):
            raise SoftwareError(f"„{src.name}“ ist kein Installer ({', '.join(INSTALLER_EXT)}) – Ordner mit "
                                "„Ordner laden …“ laden")
        size = src.stat().st_size
        return Source(src, False, [(src.name, src, size)], size, [src.name])
    if not src.is_dir():
        raise SoftwareError(f"„{src.name}“ ist keine normale Datei bzw. kein Ordner")
    out = Source(src, True)
    for dirpath, dirnames, filenames in os.walk(src):
        here = Path(dirpath)
        for name in dirnames + filenames:
            try:
                nasfiles.validate_name(name)
            except nasfiles.FileError as e:
                raise SoftwareError(f"{here / name}: {e} – auf dem NAS nicht möglich") from None
        dirnames[:] = sorted(d for d in dirnames if not (here / d).is_symlink())
        for f in sorted(filenames):
            full = here / f
            rel = full.relative_to(src).as_posix()
            try:
                st = full.lstat()
            except OSError:
                out.skipped.append(rel)
                continue
            if not stat.S_ISREG(st.st_mode) or rel.startswith(LIB_META):
                out.skipped.append(rel)
                continue
            out.files.append((rel, full, st.st_size))
            out.bytes += st.st_size
            if f.lower().endswith(INSTALLER_EXT):
                out.candidates.append(rel)
    out.candidates.sort(key=lambda r: (r.count("/"), r.lower()))
    if not out.files:
        raise SoftwareError(f"Ordner „{src.name}“ ist leer")
    return out


def _content_hash(digests: list[tuple[str, str]]) -> str:
    """SHA-256 des Inhalts: Datei → deren SHA-256; Ordner → über alle Pfade und deren SHA-256."""
    if len(digests) == 1 and "/" not in digests[0][0]:
        return digests[0][1]
    h = hashlib.sha256()
    for rel, digest in sorted(digests):
        h.update(f"{rel}\0{digest}\n".encode())
    return h.hexdigest()


def _entry_name(base: Path, meta: dict, source_name: str) -> str:
    """„<key>-<version>“ (z. B. „vlc-3.0.24“); belegt → „-2“, „-3“ … (bestehende Einträge bleiben)."""
    key = str(meta.get("key") or "") or name_key(str(meta.get("program") or "")) \
        or name_key(Path(source_name).stem) or "software"
    version = re.sub(r"[^0-9A-Za-z._-]+", "", str(meta.get("program_version") or ""))[:40].strip("._-")
    stem = (f"{key}-{version}" if version else key)[:100]
    name = stem
    for i in range(2, 1000):
        if not (base / name).exists() and not (base / name).is_symlink():
            return name
        name = f"{stem}-{i}"
    raise SoftwareError(f"Kein freier Name für „{stem}“")


def load(nas_root: str | Path, source: str | Path | Source, progress: Callable[[int, int, str], None] | None = None,
         cancel: threading.Event | None = None, installer: str | None = None) -> LoadResult:
    """Datei bzw. Ordner in die Bibliothek kopieren (zuerst als .partial – ein Abbruch hinterlässt nichts), dabei
    SHA-256 bilden. Gleicher Inhalt schon da → nichts ablegen (duplicate). Danach Erkennung wie I-020 und
    Übernahme der Parameter einer vorigen Version (_adopt). installer: im Ordner gewählter Installer."""
    src = source if isinstance(source, Source) else inspect(source, nas_root)
    progress = progress or (lambda *_a: None)
    cancel = cancel or threading.Event()
    base = ensure_library(nas_root)
    if installer is not None and installer and installer not in src.candidates:
        raise SoftwareError(f"„{installer}“ ist kein Installer im Ordner")
    free =shutil.disk_usage(base).free
    if free < src.bytes + SPACE_RESERVE:
        raise SoftwareError(f"Zu wenig Platz auf dem NAS: {free / 1000**3:.1f} GB frei, "
                            f"nötig {src.bytes / 1000**3:.1f} GB")
    partial = base / f".{uuid.uuid4().hex[:12]}{PARTIAL}"
    done, last = 0, 0.0
    digests: list[tuple[str, str]] = []
    try:
        partial.mkdir()
        for rel, full, _size in src.files:
            target = partial / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            h = hashlib.sha256()
            with open(full, "rb") as fin, open(target, "xb") as fout:
                while chunk := fin.read(COPY_CHUNK):
                    if cancel.is_set():
                        raise SoftwareError("Abgebrochen")
                    fout.write(chunk)
                    h.update(chunk)
                    done += len(chunk)
                    if time.monotonic() - last >= 0.3:
                        last = time.monotonic()
                        progress(done, src.bytes, rel)
                fout.flush()
                os.fsync(fout.fileno())
            st = full.stat()
            os.utime(target, (st.st_atime, st.st_mtime))
            digests.append((rel, h.hexdigest()))
        if cancel.is_set():
            raise SoftwareError("Abgebrochen")
        content = _content_hash(digests)
        existing = scan(nas_root, write=False)
        same = next((e for e in existing if e.content_sha256 == content), None)
        if same is not None:
            shutil.rmtree(partial, ignore_errors=True)
            progress(src.bytes, src.bytes, "")
            return LoadResult(same, duplicate=True)
        size, candidates, _files = _folder_info(partial)
        meta = _fresh_meta(partial, src.path.name, src.is_dir, candidates,
                           installer if src.is_dir else src.path.name)
        _adopt(meta, "", {e.name: e.meta for e in existing}, candidates)
        meta.update(content_sha256=content, loaded_from=str(src.path),
                    loaded=time.strftime("%Y-%m-%d %H:%M:%S"))
        name = _entry_name(base, meta, src.path.name)
        if not _write_meta(partial, meta):
            raise SoftwareError("Beschreibung konnte nicht gespeichert werden (Ordner auf dem NAS schreibgeschützt?)")
        partial.rename(base / name)
    except BaseException:
        shutil.rmtree(partial, ignore_errors=True)
        raise
    progress(src.bytes, src.bytes, "")
    path = base / name
    return LoadResult(Entry(name, src.is_dir, path, size, meta, candidates))


def delete(nas_root: str | Path, name: str) -> None:
    """Eintrag samt Dateien aus der Bibliothek löschen (erst umbenennen, dann löschen – nie halb sichtbar)."""
    base = library_dir(nas_root)
    p = PurePosixPath(name)
    if not name or len(p.parts) != 1 or name.startswith(".") or name in (".", ".."):
        raise SoftwareError(f"Ungültiger Eintrag: {name}")
    path = base / name
    if path.is_symlink() or not path.is_dir():
        raise SoftwareError(f"„{name}“ liegt nicht (mehr) in der Software-Bibliothek")
    trash = base / f".{uuid.uuid4().hex[:12]}.geloescht{PARTIAL}"
    path.rename(trash)
    shutil.rmtree(trash, ignore_errors=True)


def cleanup_partial(nas_root: str | Path, older_than: float = 24 * 3600) -> int:
    """Reste abgebrochener Ladevorgänge (Absturz, Stromausfall) nach einem Tag entfernen."""
    base = library_dir(nas_root)
    n = 0
    try:
        items = list(os.scandir(base))
    except OSError:
        return 0
    for e in items:
        if e.name.startswith(".") and e.name.endswith(PARTIAL) and e.is_dir(follow_symlinks=False):
            try:
                if time.time() - e.stat(follow_symlinks=False).st_mtime < older_than:
                    continue
            except OSError:
                continue
            shutil.rmtree(e.path, ignore_errors=True)
            n += 1
    return n


def cleanup_distribute(nas_root: str | Path) -> list[str]:
    """Ä-041: In Verteilen/Software die von I-020 angelegten Beschreibungen „.<Name>.okula.json“ (Format
    okula-software) löschen – nur diese, sonst nichts. Gibt die gelöschten Dateinamen zurück."""
    folder = software_dir(nas_root)
    removed = []
    try:
        items = sorted(os.scandir(folder), key=lambda e: e.name)
    except OSError:
        return removed
    for e in items:
        if not (e.name.startswith(".") and e.name.endswith(META_SUFFIX)) or not e.is_file(follow_symlinks=False):
            continue
        if _read_meta(Path(e.path)) is None:
            continue                  # fremde Datei mit ähnlichem Namen – bleibt
        try:
            os.unlink(e.path)
        except OSError:
            continue
        removed.append(e.name)
    return removed


# ---------- Auswahl → was aufs Gerät kommt ----------

@dataclass
class Plan:
    entries: list[Entry] = field(default_factory=list)
    files: list[tuple] = field(default_factory=list)   # (Typ "dir"/"file", Pfad relativ zur Ablage am Gerät,
    #                                                     Grösse, mtime, Quelle) – Aufbau wie distribute.Plan.entries
    bytes: int = 0
    missing: list[str] = field(default_factory=list)            # nicht mehr in der Bibliothek
    blocked: list[tuple[str, str]] = field(default_factory=list)   # (Name, Status) – nicht installierbar
    renamed: list[tuple[str, str]] = field(default_factory=list)   # (gespeichert, neue Version)

    @property
    def names(self) -> list[str]:
        return [e.name for e in self.entries]

    def lines(self) -> list[str]:
        """Für das Log des Auftrags."""
        out = [f"{e.label} – {'nur kopieren (Desktop)' if e.mode == COPY else e.kind_label}"
               f" ({_size(e.size)})" for e in self.entries]
        out += [f"{old} → {new} (neue Version)" for old, new in self.renamed]
        out += [f"{n}: fehlt in der Software-Bibliothek – übersprungen" for n in self.missing]
        out += [f"{n}: {s} – übersprungen" for n, s in self.blocked]
        return out


def _size(n: int) -> str:
    return f"{n / 1000**3:.1f} GB" if n >= 1000**3 else f"{n / 1000**2:.0f} MB" if n >= 1000**2 \
        else f"{n / 1000:.0f} kB"


def resolve(entries: list[Entry], names: list[str]) -> tuple[list[Entry], list[str], list[tuple[str, str]]]:
    """Gespeicherte Auswahl (z. B. Automatisierung) → Einträge. Fehlt ein Name, gilt die neueste Version mit
    gleichem Programmnamen (die alte Datei wurde durch eine neue ersetzt)."""
    chosen, missing, renamed = [], [], []
    by_name = {e.name: e for e in entries}
    for name in names:
        entry = by_name.get(name)
        if entry is None:
            key = split_name(name)[2]
            same = [e for e in entries if key and (e.key == key or e.adopted_from == name)]
            if same:
                entry = max(same, key=lambda e: (_version_tuple(e.version), e.name))
                renamed.append((name, entry.name))
        if entry is None:
            missing.append(name)
        elif entry not in chosen:
            chosen.append(entry)
    return chosen, missing, renamed


def plan(nas_root: str | Path, names: list[str], entries: list[Entry] | None = None) -> Plan:
    """Dateien der gewählten Programme (Links und Sonderdateien bleiben auf dem NAS)."""
    entries = scan(nas_root) if entries is None else entries
    chosen, missing, renamed = resolve(entries, names)
    p = Plan(missing=missing, renamed=renamed)
    for e in chosen:
        if not e.selectable:
            p.blocked.append((e.name, e.status))
            continue
        p.entries.append(e)
        p.files.append(("dir", e.name, 0, 0, None))       # Ordner des Eintrags (ohne Beschreibung)
        _size_, _cand, files = _folder_info(e.path)
        dirs = set()
        for rel, _st in files:
            dirs.update(str(d) for d in PurePosixPath(rel).parents if str(d) != ".")
        for d in sorted(dirs, key=lambda d: (d.count("/"), d)):
            p.files.append(("dir", f"{e.name}/{d}", 0, 0, None))
        for rel, st in files:
            p.files.append(("file", f"{e.name}/{rel}", st.st_size, int(st.st_mtime), e.path / rel))
            p.bytes += st.st_size
    return p


def total_size(entries: list[Entry]) -> int:
    return sum(e.size for e in entries)


def summary(entries: list[Entry]) -> str:
    """„VLC media player 3.0.24, Adobe Acrobat Reader“ – Verlauf, Auftragsliste."""
    return ", ".join(e.label for e in entries) or "nichts"


def history_text(entries: list[Entry]) -> str:
    return f"Software: {summary(entries)} (wird beim ersten Start installiert)"


# ---------- Installationsskript (PowerShell 5.1, läuft beim ersten Windows-Start als SYSTEM) ----------
#
# Startmechanismus wie „Windows anpassen“ (I-039): einmaliges Startskript der lokalen Gruppenrichtlinie
# (deploy.install_startup_script). Windows bricht Startskripte nach 10 Minuten ab (Richtlinie „Maximale Wartezeit
# für Gruppenrichtlinienskripts“, Standard 600 s). Darum installiert nicht das Startskript selbst, sondern eine
# einmalige geplante Aufgabe als SYSTEM, die es anlegt und startet (Ausführungszeit bis 12 h, läuft unabhängig vom
# Startskript weiter). Das Startskript wartet höchstens 9 min auf das Ende – kurze Installationen sind vor der
# Anmeldung fertig. Lässt sich die Aufgabe nicht anlegen, installiert das Startskript direkt (dann mit der 10-min-
# Grenze, steht im Protokoll).

TASK_NAME = "Okula Software installieren"
START_WAIT = 540            # s – unter den 600 s, nach denen Windows Startskripte abbricht
# B-019: Die 600 s (MaxGPOScriptWait) gelten für alle Startskripte zusammen. Steht danach noch ein anderes
# Okula-Startskript aus (Windows anpassen, ~90 s), wartet Software höchstens so lange – die Aufgabe läuft weiter.
SHARED_WAIT = 180
PROGRAM_TIMEOUT = 60        # min je Programm (wartet ein Installer auf eine Eingabe, hängt sonst alles)
REBOOT_DELAY = 60           # s nach dem letzten Programm, wenn eines 3010 meldet

SCRIPT = r"""# Okula Recovery Tool – Software installieren (I-020)
# Erstellt: __CREATED__ · Gerät: __DEVICE__ · __COUNT__ Programm(e)
# Einmaliges Startskript der lokalen Gruppenrichtlinie (als SYSTEM vor der Anmeldung); bei der Direktinstallation
# zusätzlich aus SetupComplete.cmd bzw. im Audit-Modus aufgerufen – was zuerst kommt, gewinnt (das Startskript
# löscht sich als Erstes). Ablauf:
#   -Mode Start    Skript nach ProgramData kopieren, Startskript und Gruppenrichtlinie zurückbauen, einmalige
#                  geplante Aufgabe (SYSTEM) anlegen und starten, höchstens __WAITMIN__ min auf das Ende warten.
#                  Windows bricht Startskripte nach 10 min ab – die Aufgabe läuft davon unabhängig weiter.
#   -Mode Install  (geplante Aufgabe) Programme nacheinander still installieren, Protokoll, Installer löschen,
#                  Aufgabe entfernen; Rückgabewert 3010 → nach dem letzten Programm ein Neustart.
# Protokoll: __LOG__
param([string]$Mode = 'Start', [int]$RebootDelay = __REBOOT__)
$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
$OkulaName = '__NAME__'
$OkulaLog = Join-Path $env:SystemRoot "Temp\$OkulaName.log"
$OkulaGp = Join-Path $env:SystemRoot 'System32\GroupPolicy'
$OkulaStartup = Join-Path $OkulaGp 'Machine\Scripts\Startup'
$OkulaDir = Join-Path $env:ProgramData 'Okula\Software'
$OkulaRunner = Join-Path $OkulaDir "$OkulaName.ps1"
$OkulaTask = '__TASK__'
$OkulaWait = __WAIT__
$OkulaTimeout = __TIMEOUT__
$OkulaPrograms = @(
__PROGRAMS__
)
$script:OkulaOk = 0
$script:OkulaFailed = 0
$script:OkulaReboot = $false

function Write-OkulaLog([string]$Text) {
    $line = '{0}  {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Text
    try { Add-Content -LiteralPath $OkulaLog -Value $line -Encoding UTF8 -ErrorAction Stop } catch { }
}

__RESTORE__

function Test-OkulaDone([string]$Name) {
    # B-028: steht für das Programm schon ein ok-Eintrag im Protokoll (früherer Aufruf derselben Installation)?
    if (-not (Test-Path -LiteralPath $OkulaLog)) { return $false }
    $needle = '  ok      {0}:' -f $Name
    return [bool](Select-String -LiteralPath $OkulaLog -SimpleMatch -Pattern $needle -Encoding UTF8 -Quiet `
        -ErrorAction SilentlyContinue)
}

function Install-OkulaProgram($P) {
    $ErrorActionPreference = 'Stop'
    $item = Join-Path $OkulaDir $P.Item
    if (-not (Test-Path -LiteralPath $item)) {
        # B-028: „schon erledigt“ nur mit ok-Eintrag im Protokoll (zweiter Aufruf), sonst fehlen die Installer
        if (Test-OkulaDone $P.Name) {
            Write-OkulaLog ('--      {0}: schon installiert (ok weiter oben im Protokoll) – übersprungen' -f $P.Name)
            return
        }
        $script:OkulaFailed++
        Write-OkulaLog ('FEHLER  {0}: Dateien fehlen ({1}) – nicht installiert' -f $P.Name, $item)
        return
    }
    $t0 = Get-Date
    try {
        if ($P.Kind -eq 'copy') {
            $desk = Join-Path ([Environment]::GetFolderPath('CommonDesktopDirectory')) 'Software'
            New-Item -ItemType Directory -Path $desk -Force | Out-Null
            $dest = Join-Path $desk $P.Item
            if (Test-Path -LiteralPath $dest) { Remove-Item -LiteralPath $dest -Recurse -Force }
            Copy-Item -LiteralPath $item -Destination $dest -Recurse -Force
            $script:OkulaOk++
            Write-OkulaLog ('ok      {0}: auf den Desktop kopiert ({1})' -f $P.Name, $dest)
            return
        }
        $file = Join-Path $OkulaDir $P.File
        $folder = Split-Path -Parent $file
        $arguments = $P.Args.Replace('{ordner}', $folder)
        if ($P.Kind -eq 'msix') {
            # App-Paket (MSIX/APPX, auch Bündel) für alle Benutzer bereitstellen – kein Prozess, kein Rückgabewert
            Write-OkulaLog ('Start   {0}: Add-AppxProvisionedPackage -Online -PackagePath "{1}" {2}' -f $P.Name, $file, $arguments)
            $provision = @{ Online = $true; PackagePath = $file; ErrorAction = 'Stop' }
            if ($arguments -match 'SkipLicense') { $provision.SkipLicense = $true }
            Add-AppxProvisionedPackage @provision | Out-Null
            $script:OkulaOk++
            Write-OkulaLog ('ok      {0}: für alle Benutzer bereitgestellt ({1} s)' -f $P.Name, [int]((Get-Date) - $t0).TotalSeconds)
            return
        }
        if ($P.Kind -eq 'msi') {
            $exe = Join-Path $env:SystemRoot 'System32\msiexec.exe'
            $arguments = ('/i "{0}" {1}' -f $file, $arguments).Trim()
        } elseif ($P.Kind -eq 'msp') {
            $exe = Join-Path $env:SystemRoot 'System32\msiexec.exe'
            $arguments = ('/p "{0}" {1}' -f $file, $arguments).Trim()
        } elseif ($P.Kind -eq 'msu') {
            $exe = Join-Path $env:SystemRoot 'System32\wusa.exe'
            $arguments = ('"{0}" {1}' -f $file, $arguments).Trim()
        } else {
            $exe = $file
        }
        Write-OkulaLog ('Start   {0}: {1} {2}' -f $P.Name, $exe, $arguments)
        $code = $null
        for ($try = 1; $try -le 10; $try++) {
            $start = @{ FilePath = $exe; WorkingDirectory = $folder; PassThru = $true; WindowStyle = 'Hidden' }
            if ($arguments) { $start.ArgumentList = $arguments }
            $proc = Start-Process @start
            $null = $proc.Handle
            if (-not $proc.WaitForExit($OkulaTimeout * 60000)) {
                try { $proc.Kill() } catch { }
                throw ('nach {0} min abgebrochen – wartet vermutlich auf eine Eingabe (Parameter prüfen)' -f $OkulaTimeout)
            }
            $proc.WaitForExit()
            $code = $proc.ExitCode
            if ($code -ne 1618) { break }
            Write-OkulaLog ('        {0}: eine andere Installation läuft (1618) – neuer Versuch in 30 s' -f $P.Name)
            Start-Sleep -Seconds 30
        }
        $took = [int]((Get-Date) - $t0).TotalSeconds
        if ($P.Ok -contains $code) {
            $script:OkulaOk++
            $note = ''
            if (@(3010, 1641) -contains $code) {
                $script:OkulaReboot = $true
                $note = ', Neustart nötig'
            }
            Write-OkulaLog ('ok      {0}: Rückgabewert {1}{2} ({3} s)' -f $P.Name, $code, $note, $took)
        } else {
            $script:OkulaFailed++
            Write-OkulaLog ('FEHLER  {0}: Rückgabewert {1} ({2} s)' -f $P.Name, $code, $took)
        }
    } catch {
        $script:OkulaFailed++
        Write-OkulaLog ('FEHLER  {0}: {1}' -f $P.Name, $_.Exception.Message)
    } finally {
        Remove-Item -LiteralPath $item -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Install-Okula {
    $mutex = New-Object System.Threading.Mutex($false, 'Global\OkulaSoftware')
    if (-not $mutex.WaitOne(0)) {
        Write-OkulaLog 'Installation läuft bereits – nichts zu tun'
        return
    }
    try {
        Write-OkulaLog ('----- Software installieren (Okula Recovery Tool): {0} Programm(e) -----' -f $OkulaPrograms.Count)
        foreach ($p in $OkulaPrograms) { Install-OkulaProgram $p }
        Write-OkulaLog ('----- Ende: {0} ok, {1} mit Fehler -----' -f $script:OkulaOk, $script:OkulaFailed)
    } finally {
        Remove-Item -LiteralPath $OkulaRunner -Force -ErrorAction SilentlyContinue
        foreach ($d in $OkulaDir, (Split-Path -Parent $OkulaDir)) {
            if ((Test-Path -LiteralPath $d) -and -not @(Get-ChildItem -LiteralPath $d -Force)) {
                Remove-Item -LiteralPath $d -Force -ErrorAction SilentlyContinue
            }
        }
        if ($script:OkulaReboot) {
            Write-OkulaLog ('Neustart in {0} s (Rückgabewert 3010: Neustart nötig)' -f $RebootDelay)
            & shutdown.exe /r /t $RebootDelay /c 'Okula Recovery Tool: Software installiert - Neustart' /d p:4:2 | Out-Null
        }
        $mutex.ReleaseMutex()
        # zuletzt: die Aufgabe entfernt sich selbst (läuft diese Instanz gerade darin, ist alles erledigt)
        Unregister-ScheduledTask -TaskName $OkulaTask -Confirm:$false -ErrorAction SilentlyContinue
    }
}

function Start-Okula {
    New-Item -ItemType Directory -Path $OkulaDir -Force | Out-Null
    if ($PSCommandPath -and ($PSCommandPath -ne $OkulaRunner)) {
        Copy-Item -LiteralPath $PSCommandPath -Destination $OkulaRunner -Force
    }
    # Startskript zuerst entfernen – so läuft es genau einmal, auch nach einem Fehler
    Remove-Item -LiteralPath (Join-Path $OkulaStartup "$OkulaName.ps1"), (Join-Path $OkulaStartup "$OkulaName.cmd") `
        -Force -ErrorAction SilentlyContinue
    # B-019: läuft danach noch ein Okula-Startskript (Windows anpassen), kürzer warten – Windows bricht alle
    # Startskripte zusammen nach 600 s ab (MaxGPOScriptWait)
    if (@(Get-ChildItem -LiteralPath $OkulaStartup -Filter 'okula-*.cmd' -Force -ErrorAction SilentlyContinue)) {
        $OkulaWait = [Math]::Min($OkulaWait, __SHAREDWAIT__)
    }
    try {
        $ErrorActionPreference = 'Stop'
        $note = Restore-OkulaStart
        if ($note) { Write-OkulaLog ('ok      Startskript und Gruppenrichtlinie aufgeräumt ({0})' -f $note) }
        else { Write-OkulaLog 'ok      Startskript und Gruppenrichtlinie aufgeräumt' }
    } catch {
        Write-OkulaLog ('FEHLER  Startskript und Gruppenrichtlinie aufräumen: {0}' -f $_.Exception.Message)
    }
    $ErrorActionPreference = 'Continue'
    if (-not (Test-Path -LiteralPath $OkulaRunner)) {
        Write-OkulaLog 'FEHLER  Skript liegt nicht in ProgramData – Installation direkt im Startskript'
        Install-Okula
        return
    }
    try {
        $ps = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
        $arg = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}" -Mode Install -RebootDelay {1}' -f `
            $OkulaRunner, $RebootDelay
        $action = New-ScheduledTaskAction -Execute $ps -Argument $arg
        $trigger = New-ScheduledTaskTrigger -AtStartup
        $principal = New-ScheduledTaskPrincipal -UserId 'S-1-5-18' -LogonType ServiceAccount -RunLevel Highest
        $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 12) -AllowStartIfOnBatteries `
            -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
        Register-ScheduledTask -TaskName $OkulaTask -Action $action -Trigger $trigger -Principal $principal `
            -Settings $settings -Force -ErrorAction Stop | Out-Null
        Start-ScheduledTask -TaskName $OkulaTask -ErrorAction Stop
        Write-OkulaLog ('ok      Geplante Aufgabe „{0}“ angelegt und gestartet (SYSTEM, ohne 10-Minuten-Grenze)' -f $OkulaTask)
    } catch {
        $why = 'FEHLER  Geplante Aufgabe nicht angelegt: {0} – Installation direkt im Startskript' -f $_.Exception.Message
        Write-OkulaLog ($why + ' (Windows bricht Startskripte nach 10 min ab)')
        Install-Okula
        return
    }
    $t0 = Get-Date
    while (((Get-Date) - $t0).TotalSeconds -lt $OkulaWait) {
        Start-Sleep -Seconds 5
        $task = Get-ScheduledTask -TaskName $OkulaTask -ErrorAction SilentlyContinue
        if (-not $task) { return }          # fertig – die Aufgabe entfernt sich am Ende selbst
        if ((@('Running', 'Queued') -notcontains [string]$task.State) -and ((Get-Date) - $t0).TotalSeconds -gt 30) {
            Write-OkulaLog ('FEHLER  Geplante Aufgabe läuft nicht (Zustand {0}) – neuer Versuch beim nächsten Start' -f `
                $task.State)
            return
        }
    }
    Write-OkulaLog 'Installation läuft als geplante Aufgabe weiter – die Anmeldung ist schon möglich'
}

if ($Mode -eq 'Install') { Install-Okula } else { Start-Okula }
"""


def _ps(text: str) -> str:
    from okula_recovery.wintweaks import ps_quote
    return ps_quote(text)


def script_kind(e: Entry) -> str:
    """Wie das Skript am Gerät installiert: copy, msi (msiexec /i), msp (msiexec /p), msu (wusa.exe),
    msix (Add-AppxProvisionedPackage) oder exe (Installer selbst starten)."""
    if e.mode == COPY:
        return "copy"
    low = e.installer.lower()
    if low.endswith(APPX_EXT):
        return "msix"
    for ext in ("msi", "msp", "msu"):
        if low.endswith("." + ext):
            return ext
    return "msi" if e.kind == "msi" else "exe"


def program_line(e: Entry) -> str:
    """Ein Eintrag der Liste $OkulaPrograms."""
    kind = script_kind(e)
    file = f"{e.name}/{e.installer}" if e.mode != COPY else e.name
    codes = ", ".join(str(c) for c in e.exit_codes)
    return (f"    [pscustomobject]@{{ Name = {_ps(e.label)}; Item = {_ps(e.name)}; "
            f"File = {_ps(file.replace('/', chr(92)))}; Kind = '{kind}'; Args = {_ps(e.args if kind != 'copy' else '')}; "
            f"Ok = @({codes}) }}")


def build_script(entries: list[Entry], device: str = "", created: float | None = None,
                 reboot_delay: int = REBOOT_DELAY) -> str:
    """PowerShell-Skript für die gewählten Programme (Reihenfolge wie gewählt)."""
    import time
    from okula_recovery import deploy, wintweaks
    if not entries:
        raise SoftwareError("Keine Software gewählt")
    bad = [e.name for e in entries if not e.selectable]
    if bad:
        raise SoftwareError(f"Nicht installierbar ({', '.join(bad)}) – Parameter in Extras → Software-Bibliothek "
                            "hinterlegen")
    stamp = time.strftime("%d.%m.%Y %H:%M", time.localtime(created if created is not None else time.time()))
    safe_device = re.sub(r"[^\w .-]", "", device)[:60] or "–"
    replace = {"__RESTORE__": wintweaks.RESTORE_START, "__AFTER__": deploy.TWEAK_AFTER, "__CREATED__": stamp,
               "__DEVICE__": safe_device, "__COUNT__": str(len(entries)), "__LOG__": deploy.SOFTWARE_LOG,
               "__NAME__": deploy.SOFTWARE_NAME, "__TASK__": TASK_NAME, "__WAIT__": str(START_WAIT),
               "__WAITMIN__": str(START_WAIT // 60), "__SHAREDWAIT__": str(SHARED_WAIT),
               "__TIMEOUT__": str(PROGRAM_TIMEOUT),
               "__REBOOT__": str(int(reboot_delay)),
               "__PROGRAMS__": ",\n".join(program_line(e) for e in entries)}
    text = SCRIPT
    for k, v in replace.items():   # Reihenfolge: __RESTORE__ zuerst (enthält __AFTER__)
        text = text.replace(k, v)
    return text


# ---------- Direktinstallation: Dateien auf der Setup-Partition ----------

SETUP_SOFTWARE = "okula/software"     # → C:\ProgramData\Okula\Software (install.cmd kopiert)
SETUP_GP = "okula/gp"                 # → C:\Windows\System32\GroupPolicy (Startskript)


BOM = "﻿"


def startup_files(scripts: list[tuple[str, str, str]]) -> dict[str, str]:
    """Startskripte für ein frisch aufgespieltes Windows (ohne lokale Gruppenrichtlinie) – Texte für die
    Setup-Partition (Agent schreibt UTF-8; scripts.ini/gpt.ini nur ASCII, .ps1 mit BOM für PowerShell 5.1).
    scripts: [(Name, Text der .cmd, PowerShell-Skript)] in dieser Reihenfolge in scripts.ini (Ä-046: Software vor
    Windows anpassen)."""
    from okula_recovery import deploy
    start = f"{SETUP_GP}/Machine/Scripts/Startup"
    files = {f"{SETUP_GP}/gpt.ini": deploy.gpt_edit("", 1, True)[0]}
    ini = ""
    for name, cmd_text, script in scripts:
        ini = deploy.scripts_ini_add(ini, name + ".cmd")
        files[f"{start}/{name}.cmd"] = cmd_text
        files[f"{start}/{name}.ps1"] = BOM + script.replace("\r\n", "\n").replace("\n", "\r\n")
    files[f"{SETUP_GP}/Machine/Scripts/scripts.ini"] = ini
    return files


def setup_files(script: str) -> dict[str, str]:
    """Startskript „Software installieren“ für die Setup-Partition (siehe startup_files)."""
    from okula_recovery import deploy
    return startup_files([(deploy.SOFTWARE_NAME, deploy.SOFTWARE_CMD_TEXT, script)])
