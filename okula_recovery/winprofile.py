"""Agent-Seite (Ä-040): Einstellungen des Administrators aus dem Audit-Modus fürs Standardprofil übernehmen.

CopyProfile (in der Antwortdatei, winunattend) kopiert das Profil des eingebauten Administrators beim ersten Start
ins Standardprofil – laut Microsoft aber **nicht** die an die Taskleiste angehefteten Symbole. Diese liest das Tool
hier aus dem eingehängten (generalisierten) Windows und schreibt sie als LayoutModification.xml ins Standardprofil:

- Quellprofil: Users\\Administrator (sonst das einzige Profil mit angehefteten Symbolen; nie Default/Public).
- Pins: AppData\\Roaming\\Microsoft\\Internet Explorer\\Quick Launch\\User Pinned\\TaskBar\\*.lnk; Reihenfolge und
  Store-Apps aus dem Registrierungswert Taskband\\Favorites in NTUSER.DAT (nur gelesen, eigener kleiner Leser – kein
  Hive wird geschrieben). Ist die Registrierung nicht lesbar: Reihenfolge nach Datum der Verknüpfungen.
- Explorer → DesktopApplicationID „Microsoft.Windows.Explorer“, Edge → „MSEdge“, Store-Apps → AppUserModelID,
  übrige Programme → Verknüpfung im Startmenü für alle Benutzer (vorhandene, sonst Kopie unter Programs\\Okula).
- Ziel: Users\\Default\\AppData\\Local\\Microsoft\\Windows\\Shell\\LayoutModification.xml (und dieselbe Datei im
  Quellprofil, damit CopyProfile sie nicht mit dem Stand des Administrators überschreibt). Ein vorhandenes
  Startlayout in der Datei bleibt, nur die Taskleiste wird ersetzt.
Kein GTK, nur Standardbibliothek (läuft auf dem Agent).
"""

from __future__ import annotations

import re
import shutil
import struct
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath
from xml.sax.saxutils import escape, quoteattr

# ---------- Pfade ----------

TASKBAR_DIR = "AppData/Roaming/Microsoft/Internet Explorer/Quick Launch/User Pinned/TaskBar"
SHELL_DIR = "AppData/Local/Microsoft/Windows/Shell"
LAYOUT_FILE = "LayoutModification.xml"
START_MENU = "ProgramData/Microsoft/Windows/Start Menu/Programs"
START_MENU_ENV = "%ALLUSERSPROFILE%\\Microsoft\\Windows\\Start Menu\\Programs"
OWN_FOLDER = "Okula"                       # Kopien von Verknüpfungen ohne Eintrag im Startmenü
TASKBAND_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Taskband"
SKIP_PROFILES = {"default", "default user", "public", "all users", "defaultapppool", "wdagutilityaccount"}
BACKUP_SUFFIX = ".okula-vorher"            # ungültige vorhandene Datei bleibt daneben erhalten

EXPLORER_ID = "Microsoft.Windows.Explorer"
EDGE_ID = "MSEdge"

# ---------- XML ----------

NS_LAYOUT = "http://schemas.microsoft.com/Start/2014/LayoutModification"
NS_DEFAULT = "http://schemas.microsoft.com/Start/2014/FullDefaultLayout"
NS_START = "http://schemas.microsoft.com/Start/2014/StartLayout"
NS_TASKBAR = "http://schemas.microsoft.com/Start/2014/TaskbarLayout"
# Reihenfolge der Kinder von LayoutModificationTemplate laut Microsoft (XSD); CustomTaskbarLayoutCollection ist Nr. 7
CHILD_ORDER = ("LayoutOptions", "DefaultLayoutOverride", "RequiredStartGroupsCollection", "AppendDownloadOfficeTile",
               "AppendOfficeSuite", "AppendOfficeSuiteChoice", "TopMFUApps", "CustomTaskbarLayoutCollection",
               "InkWorkspaceTopApps", "StartLayoutCollection")

# Store-Apps: PackageFamilyName (Name_13 Zeichen Herausgeber-ID) + „!“ + App-ID, z. B.
# Microsoft.WindowsStore_8wekyb3d8bbwe!App
AUMID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9.\-]{1,}_[a-z0-9]{13}![A-Za-z0-9.\-_]+")
KNOWN_APPS = {
    "microsoft.windowsstore_8wekyb3d8bbwe!app": "Microsoft Store",
    "microsoft.windowscommunicationsapps_8wekyb3d8bbwe!microsoft.windowslive.mail": "Mail",
    "microsoft.microsoftedge_8wekyb3d8bbwe!microsoftedge": "Microsoft Edge",
}


class ProfileError(Exception):
    pass


# ---------- Registrierung (NTUSER.DAT) nur lesen ----------

class Hive:
    """Minimaler, nur lesender Leser für Registrierungsdateien (regf): Schlüssel finden, Wert lesen.

    Aufbau (öffentlich dokumentiert, z. B. libyal „Windows NT Registry File format“): Kopfblock 4096 Bytes
    („regf“, Offset 0x24 = Wurzelschlüssel), danach Zellen (int32 Grösse, negativ = belegt). nk = Schlüssel,
    vk = Wert, lf/lh/li/ri = Unterschlüssel-Listen, db = grosse Daten in Segmenten."""

    BASE = 4096

    def __init__(self, data: bytes):
        if len(data) < self.BASE + 8 or data[:4] != b"regf":
            raise ProfileError("keine Registrierungsdatei")
        self.data = data
        self.root = struct.unpack_from("<I", data, 0x24)[0]

    def _cell(self, off: int) -> bytes:
        pos = self.BASE + off
        if off == 0xFFFFFFFF or pos + 4 > len(self.data):
            raise ProfileError("Verweis ausserhalb der Datei")
        size = abs(struct.unpack_from("<i", self.data, pos)[0])
        if size < 8 or pos + size > len(self.data):
            raise ProfileError("ungültige Zelle")
        return self.data[pos + 4:pos + size]

    def _key_name(self, nk: bytes) -> str:
        flags = struct.unpack_from("<H", nk, 2)[0]
        length = struct.unpack_from("<H", nk, 72)[0]
        raw = nk[76:76 + length]
        return raw.decode("latin-1") if flags & 0x20 else raw.decode("utf-16-le", errors="replace")

    def _subkeys(self, nk: bytes) -> list[int]:
        count, list_off = struct.unpack_from("<I", nk, 20)[0], struct.unpack_from("<I", nk, 28)[0]
        return self._list(list_off) if count else []

    def _list(self, off: int, depth: int = 0) -> list[int]:
        cell = self._cell(off)
        sig, count = cell[:2], struct.unpack_from("<H", cell, 2)[0]
        if sig in (b"lf", b"lh"):
            return [struct.unpack_from("<I", cell, 4 + 8 * i)[0] for i in range(count)]
        if sig == b"li":
            return [struct.unpack_from("<I", cell, 4 + 4 * i)[0] for i in range(count)]
        if sig == b"ri" and depth < 4:
            out = []
            for i in range(count):
                out += self._list(struct.unpack_from("<I", cell, 4 + 4 * i)[0], depth + 1)
            return out
        raise ProfileError("unbekannte Unterschlüssel-Liste")

    def find_key(self, path: str) -> bytes | None:
        nk = self._cell(self.root)
        for part in [p for p in path.split("\\") if p]:
            for off in self._subkeys(nk):
                child = self._cell(off)
                if child[:2] == b"nk" and self._key_name(child).lower() == part.lower():
                    nk = child
                    break
            else:
                return None
        return nk

    def value(self, path: str, name: str) -> tuple[int, bytes] | None:
        """(Typ, Daten) des Werts – None, wenn Schlüssel oder Wert fehlt."""
        for vname, kind, data in self.values(path) or []:
            if vname.lower() == name.lower():
                return kind, data
        return None

    def values(self, path: str) -> list[tuple[str, int, bytes]] | None:
        """Alle Werte eines Schlüssels als (Name, Typ, Daten) – None, wenn der Schlüssel fehlt (B-019)."""
        nk = self.find_key(path)
        if nk is None:
            return None
        count, list_off = struct.unpack_from("<I", nk, 36)[0], struct.unpack_from("<I", nk, 40)[0]
        if not count:
            return []
        offsets = self._cell(list_off)
        out = []
        for i in range(count):
            vk = self._cell(struct.unpack_from("<I", offsets, 4 * i)[0])
            if vk[:2] != b"vk":
                continue
            length, size, data_off, kind, flags = struct.unpack_from("<HIIIH", vk, 2)
            raw = vk[20:20 + length]
            vname = raw.decode("latin-1") if flags & 1 else raw.decode("utf-16-le", errors="replace")
            if size & 0x80000000:                      # Daten direkt im Feld (höchstens 4 Bytes)
                out.append((vname, kind, struct.pack("<I", data_off)[:size & 0x7FFFFFFF]))
                continue
            data = self._cell(data_off)
            if data[:2] == b"db" and size > 16344:     # grosse Daten in Segmenten
                segs, seg_list = struct.unpack_from("<H", data, 2)[0], struct.unpack_from("<I", data, 4)[0]
                offs = self._cell(seg_list)
                data = b"".join(self._cell(struct.unpack_from("<I", offs, 4 * j)[0])[:16344] for j in range(segs))
            out.append((vname, kind, data[:size]))
        return out

    def clean(self) -> bool:
        """Kopf sauber geschrieben? Primäre und sekundäre Sequenznummer (Offset 4 und 8) gleich – sonst stehen
        Änderungen noch in den Protokolldateien (.LOG1/.LOG2), und ein Schreiben von aussen wäre unsicher."""
        return struct.unpack_from("<I", self.data, 4)[0] == struct.unpack_from("<I", self.data, 8)[0]


def read_favorites(ntuser: Path) -> bytes | None:
    """Taskband\\Favorites (Reihenfolge der angehefteten Symbole) – None, wenn nicht lesbar."""
    try:
        found = Hive(ntuser.read_bytes()).value(TASKBAND_KEY, "Favorites")
    except (OSError, ProfileError, struct.error):
        return None
    return found[1] if found else None


def _utf16_positions(blob: bytes) -> list[tuple[int, str]]:
    """Text des Blobs als UTF-16 (beide Ausrichtungen) mit Byte-Position des Anfangs."""
    out = []
    for align in (0, 1):
        out.append((align, blob[align:].decode("utf-16-le", errors="replace")))
    return out


def find_position(blob: bytes, name: str) -> int | None:
    """Erste Byte-Position von name (UTF-16, ohne Gross-/Kleinschreibung) im Blob."""
    best = None
    for align, text in _utf16_positions(blob):
        i = text.lower().find(name.lower())
        if i >= 0:
            pos = align + 2 * i
            best = pos if best is None else min(best, pos)
    return best


def find_store_apps(blob: bytes) -> list[tuple[int, str]]:
    """(Position, AppUserModelID) der Store-Apps im Favorites-Blob, ohne Doppel."""
    seen: dict[str, tuple[int, str]] = {}
    for align, text in _utf16_positions(blob):
        for m in AUMID_RE.finditer(text):
            pos, key = align + 2 * m.start(), m.group(0).lower()
            if key not in seen or pos < seen[key][0]:
                seen[key] = (pos, m.group(0))
    return sorted(seen.values())


# ---------- Verknüpfungen (.lnk) ----------

def lnk_target(data: bytes) -> str:
    """Ziel einer Windows-Verknüpfung (MS-SHLLINK): Umgebungsvariablen-Block, sonst LinkInfo – leer, wenn unbekannt."""
    try:
        if len(data) < 0x4C or struct.unpack_from("<I", data, 0)[0] != 0x4C:
            return ""
        flags = struct.unpack_from("<I", data, 0x14)[0]
        pos = 0x4C
        if flags & 0x1:                                 # HasLinkTargetIDList
            pos += 2 + struct.unpack_from("<H", data, pos)[0]
        local = ""
        if flags & 0x2:                                 # HasLinkInfo
            size, header, li_flags = struct.unpack_from("<III", data, pos)
            if li_flags & 1:
                base_off, suffix_off = struct.unpack_from("<I", data, pos + 16)[0], \
                    struct.unpack_from("<I", data, pos + 24)[0]
                if header >= 0x24:
                    uoff = struct.unpack_from("<I", data, pos + 28)[0]
                    if uoff:
                        end = pos + uoff
                        while end + 1 < pos + size and data[end:end + 2] != b"\0\0":
                            end += 2
                        local = data[pos + uoff:end].decode("utf-16-le", errors="replace")
                if not local:
                    local = data[pos + base_off:data.index(b"\0", pos + base_off)].decode("cp1252", "replace")
                    local += data[pos + suffix_off:data.index(b"\0", pos + suffix_off)].decode("cp1252", "replace")
            pos += size
        unicode = bool(flags & 0x80)
        for bit in (0x4, 0x8, 0x10, 0x20, 0x40):        # Name, relativer Pfad, Arbeitsordner, Argumente, Symbol
            if flags & bit:
                n = struct.unpack_from("<H", data, pos)[0]
                pos += 2 + n * (2 if unicode else 1)
        while pos + 8 <= len(data):                     # ExtraData
            size, sig = struct.unpack_from("<II", data, pos)
            if size < 8:
                break
            if sig == 0xA0000001 and size >= 0x314:     # EnvironmentVariableDataBlock
                wide = data[pos + 268:pos + 268 + 520].decode("utf-16-le", errors="replace").split("\0")[0]
                ansi = data[pos + 8:pos + 268].split(b"\0")[0].decode("cp1252", "replace")
                if wide or ansi:
                    return wide or ansi
            pos += size
        return local
    except (struct.error, ValueError):
        return ""


def _norm(path: str) -> str:
    p = path.strip().strip('"').replace("/", "\\").lower()
    for env, real in (("%programfiles(x86)%", "c:\\program files (x86)"), ("%programfiles%", "c:\\program files"),
                      ("%programw6432%", "c:\\program files"), ("%systemroot%", "c:\\windows"),
                      ("%windir%", "c:\\windows"), ("%systemdrive%", "c:"), ("%programdata%", "c:\\programdata"),
                      ("%allusersprofile%", "c:\\programdata")):
        p = p.replace(env, real)
    return p


def classify(data: bytes) -> tuple[str, str]:
    """(Art, Wert): ("id", DesktopApplicationID) für Explorer/Edge, sonst ("lnk", Ziel)."""
    target = _norm(lnk_target(data))
    exe = target.rsplit("\\", 1)[-1]
    if exe == "explorer.exe":
        return "id", EXPLORER_ID
    if exe == "msedge.exe":
        return "id", EDGE_ID
    if not target:   # Ziel nur als Shell-Element: am Programmnamen in der Verknüpfung erkennen
        low = data.lower()
        if b"\\explorer.exe" in low or "\\explorer.exe".encode("utf-16-le") in low:
            return "id", EXPLORER_ID
        if b"msedge.exe" in low or "msedge.exe".encode("utf-16-le") in low:
            return "id", EDGE_ID
    return "lnk", target


# ---------- Dateisystem ----------

def find_ci(root: Path, rel: str) -> Path | None:
    """Pfad ohne Rücksicht auf Gross-/Kleinschreibung (NTFS über ntfs-3g unterscheidet sie)."""
    cur = root
    for part in PurePosixPath(rel).parts:
        if (cur / part).exists():
            cur = cur / part
            continue
        try:
            match = next((p for p in cur.iterdir() if p.name.lower() == part.lower()), None)
        except OSError:
            return None
        if match is None:
            return None
        cur = match
    return cur


def _ensure_dir(root: Path, rel: str) -> Path:
    cur = root
    for part in PurePosixPath(rel).parts:
        nxt = find_ci(cur, part) or cur / part
        if nxt.is_symlink():
            raise ProfileError(f"{nxt.name} ist ein Link – nicht geschrieben")
        nxt.mkdir(exist_ok=True)
        cur = nxt
    return cur


def _pins_dir(profile: Path) -> Path | None:
    d = find_ci(profile, TASKBAR_DIR)
    return d if d is not None and d.is_dir() and not d.is_symlink() else None


def _lnk_files(profile: Path) -> list[Path]:
    d = _pins_dir(profile)
    if d is None:
        return []
    return sorted((p for p in d.iterdir() if p.suffix.lower() == ".lnk" and p.is_file() and not p.is_symlink()),
                  key=lambda p: p.name.lower())


def profiles(root: Path) -> list[Path]:
    """Benutzerprofile mit NTUSER.DAT – ohne Default, Public und Links."""
    users = find_ci(root, "Users")
    if users is None or not users.is_dir():
        return []
    out = []
    for p in sorted(users.iterdir(), key=lambda p: p.name.lower()):
        if p.is_symlink() or not p.is_dir() or p.name.lower() in SKIP_PROFILES:
            continue
        if find_ci(p, "NTUSER.DAT") is not None:
            out.append(p)
    return out


def source_profile(root: Path) -> tuple[Path | None, str]:
    """Profil, in dem im Audit-Modus eingerichtet wurde: Administrator, sonst das einzige mit angehefteten Symbolen.
    (Profil, Grund) – Profil None mit Grund, wenn keins eindeutig ist."""
    found = [p for p in profiles(root) if _lnk_files(p)]
    admin = [p for p in found if p.name.lower() == "administrator"] or \
        [p for p in found if p.name.lower().startswith("administrator.")]
    if admin:
        return admin[0], ""
    if len(found) == 1:
        return found[0], ""
    if not found:
        return None, "keine angehefteten Symbole gefunden"
    return None, ("mehrere Profile mit angehefteten Symbolen (" + ", ".join(p.name for p in found) +
                  ") – nicht eindeutig")


def _start_menu_links(root: Path) -> list[Path]:
    menu = find_ci(root, START_MENU)
    if menu is None or not menu.is_dir():
        return []
    out = []
    for p in menu.rglob("*"):
        if p.suffix.lower() == ".lnk" and p.is_file() and not p.is_symlink():
            out.append(p)
    return sorted(out, key=lambda p: str(p).lower())


def _menu_path(menu: Path, link: Path) -> str:
    return START_MENU_ENV + "\\" + "\\".join(link.relative_to(menu).parts)


# ---------- Pins bestimmen ----------

def collect_pins(root: Path, profile: Path) -> dict:
    """Angeheftete Symbole des Profils in Taskleisten-Reihenfolge.

    Ergebnis: {"pins": [{"name", "kind" (id|link|app), "value", "lnk" (Quelle), "copy" (bool)}], "order":
    "registry" | "date"}. Für „link“ ist value der Pfad für DesktopApplicationLinkPath."""
    blob = None
    ntuser = find_ci(profile, "NTUSER.DAT")
    if ntuser is not None:
        blob = read_favorites(ntuser)
    menu = find_ci(root, START_MENU)
    menu_links = _start_menu_links(root)
    targets = {}
    for link in menu_links:
        try:
            targets.setdefault(_norm(lnk_target(link.read_bytes()[:65536])), link)
        except OSError:
            continue
    items = []                         # (Sortierschlüssel, Pin)
    for i, lnk in enumerate(_lnk_files(profile)):
        try:
            data = lnk.read_bytes()[:1024 * 1024]
        except OSError:
            continue
        kind, value = classify(data)
        name = lnk.stem
        pin = {"name": name, "lnk": str(lnk), "copy": False}
        if kind == "id":
            pin.update(kind="id", value=value, name="Explorer" if value == EXPLORER_ID else
                       ("Microsoft Edge" if value == EDGE_ID else name))
        else:
            same = targets.get(value) if value else None
            if same is None:
                same = next((m for m in menu_links if m.name.lower() == lnk.name.lower()), None)
            if same is not None and menu is not None:
                pin.update(kind="link", value=_menu_path(menu, same))
            else:
                pin.update(kind="link", value=f"{START_MENU_ENV}\\{OWN_FOLDER}\\{lnk.name}", copy=True)
        pos = find_position(blob, lnk.name) if blob else None
        if pos is None and blob:
            pos = find_position(blob, name)
        try:
            mtime = lnk.stat().st_mtime
        except OSError:
            mtime = 0.0
        items.append(((0 if pos is not None else 1, pos if pos is not None else mtime, i), pin, data))
    if blob:
        for pos, aumid in find_store_apps(blob):
            # gehört die App-ID zu einer schon erfassten Verknüpfung (Desktop-App mit App-ID)? Dann nicht doppelt
            needle = aumid.lower().encode("utf-16-le")
            if any(needle in d.lower() for _k, _p, d in items):
                continue
            label = KNOWN_APPS.get(aumid.lower()) or aumid.split("_", 1)[0].split(".")[-1]
            items.append(((0, pos, 0), {"name": label, "kind": "app", "value": aumid, "lnk": "", "copy": False},
                          b""))
    items.sort(key=lambda x: x[0])
    return {"pins": [p for _k, p, _d in items], "order": "registry" if blob else "date"}


# ---------- LayoutModification.xml ----------

def taskbar_element(pins: list[dict]) -> ET.Element:
    coll = ET.Element(f"{{{NS_LAYOUT}}}CustomTaskbarLayoutCollection", {"PinListPlacement": "Replace"})
    layout = ET.SubElement(coll, f"{{{NS_DEFAULT}}}TaskbarLayout")
    plist = ET.SubElement(layout, f"{{{NS_TASKBAR}}}TaskbarPinList")
    for pin in pins:
        if pin["kind"] == "app":
            ET.SubElement(plist, f"{{{NS_TASKBAR}}}UWA", {"AppUserModelID": pin["value"]})
        elif pin["kind"] == "id":
            ET.SubElement(plist, f"{{{NS_TASKBAR}}}DesktopApp", {"DesktopApplicationID": pin["value"]})
        else:
            ET.SubElement(plist, f"{{{NS_TASKBAR}}}DesktopApp", {"DesktopApplicationLinkPath": pin["value"]})
    return coll


def _serialize(root: ET.Element) -> str:
    """Eigene Ausgabe mit den Präfixen wie bei Microsoft (ElementTree kennt nur globale Präfixe, und der leere
    Präfix ist dort schon für die Antwortdatei vergeben)."""
    prefixes = {NS_LAYOUT: "", NS_DEFAULT: "defaultlayout", NS_START: "start", NS_TASKBAR: "taskbar"}
    used = dict(prefixes)

    def qname(tag: str) -> str:
        if not tag.startswith("{"):
            return tag
        uri, local = tag[1:].split("}", 1)
        if uri not in used:
            used[uri] = f"ns{len(used) - len(prefixes) + 1}"
        return f"{used[uri]}:{local}" if used[uri] else local

    def element(el: ET.Element, depth: int) -> list[str]:
        pad = "  " * depth
        attrs = "".join(f" {qname(k)}={quoteattr(v)}" for k, v in el.attrib.items())
        if depth == 0:
            attrs = "{ns}" + attrs
        text = (el.text or "").strip()
        children = list(el)
        if not children and not text:
            return [f"{pad}<{qname(el.tag)}{attrs} />"]
        if not children:
            return [f"{pad}<{qname(el.tag)}{attrs}>{escape(text)}</{qname(el.tag)}>"]
        lines = [f"{pad}<{qname(el.tag)}{attrs}>"]
        for child in children:
            lines += element(child, depth + 1)
        return lines + [f"{pad}</{qname(el.tag)}>"]

    body = "\n".join(element(root, 0))
    decl = "".join(f" xmlns={quoteattr(uri)}" if not p else f" xmlns:{p}={quoteattr(uri)}"
                   for uri, p in used.items())
    return '<?xml version="1.0" encoding="utf-8"?>\n' + body.replace("{ns}", decl, 1) + "\n"


def _usable(existing: str) -> ET.Element | None:
    """Vorhandene Datei als Baum, wenn sie ein gültiges LayoutModificationTemplate ist – sonst None."""
    if not existing.strip():
        return None
    try:
        root = ET.fromstring(existing)
    except ET.ParseError:
        return None
    if root.tag != f"{{{NS_LAYOUT}}}LayoutModificationTemplate" or \
            any(not el.tag.startswith("{") for el in root.iter()):
        return None
    return root


def layout_xml(pins: list[dict], existing: str = "") -> str:
    """LayoutModification.xml mit der Taskleiste; ein vorhandenes (gültiges) Startlayout bleibt erhalten."""
    root = _usable(existing)
    if root is None:
        root = ET.Element(f"{{{NS_LAYOUT}}}LayoutModificationTemplate", {"Version": "1"})
    for old in [c for c in root if c.tag == f"{{{NS_LAYOUT}}}CustomTaskbarLayoutCollection"]:
        root.remove(old)
    rank = CHILD_ORDER.index("CustomTaskbarLayoutCollection")

    def order(el: ET.Element) -> int:
        local = el.tag.rsplit("}", 1)[-1]
        return CHILD_ORDER.index(local) if local in CHILD_ORDER else len(CHILD_ORDER)

    at = next((i for i, c in enumerate(root) if order(c) > rank), len(root))
    root.insert(at, taskbar_element(pins))
    return _serialize(root)


def _write_layout(profile: Path, pins: list[dict]) -> Path:
    shell = _ensure_dir(profile, SHELL_DIR)
    target = find_ci(shell, LAYOUT_FILE) or shell / LAYOUT_FILE
    if target.is_symlink():
        raise ProfileError(f"{target.name} ist ein Link – nicht geschrieben")
    existing = ""
    if target.is_file():
        raw = target.read_bytes()
        existing = raw.decode("utf-16", errors="replace") if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else \
            raw.decode("utf-8-sig", errors="replace")
        if existing.strip() and _usable(existing) is None:   # unbrauchbar: daneben aufbewahren, neu schreiben
            shutil.copy2(target, target.with_name(target.name + BACKUP_SUFFIX))
            existing = ""
    tmp = shell / f".{LAYOUT_FILE}.okula-tmp"
    tmp.write_text(layout_xml(pins, existing), encoding="utf-8")
    tmp.replace(target)
    return target


def adopt_taskbar(root: Path) -> dict:
    """Taskleiste des Quellprofils ins Standardprofil übernehmen (root = eingehängte Windows-Partition).

    Ergebnis: {"profile", "pins" (Namen), "order", "written" (Pfade relativ zu root), "copied", "reason"}.
    Keine Pins → nichts geschrieben, reason gesetzt."""
    result = {"profile": "", "pins": [], "order": "", "written": [], "copied": [], "reason": ""}
    profile, reason = source_profile(root)
    if profile is None:
        result["reason"] = reason
        return result
    result["profile"] = profile.name
    found = collect_pins(root, profile)
    pins = found["pins"]
    if not pins:
        result["reason"] = "keine angehefteten Symbole gefunden"
        return result
    default = find_ci(root, "Users/Default")
    if default is None or not default.is_dir() or default.is_symlink():
        result["reason"] = "Standardprofil (Users\\Default) fehlt"
        return result
    copies = [p for p in pins if p.get("copy")]
    if copies:
        own = _ensure_dir(root, f"{START_MENU}/{OWN_FOLDER}")
        for pin in copies:
            src = Path(pin["lnk"])
            dest = find_ci(own, src.name) or own / src.name
            if dest.is_symlink():
                raise ProfileError(f"{dest.name} ist ein Link – nicht geschrieben")
            shutil.copyfile(src, dest)
            result["copied"].append(str(dest.relative_to(root)))
    for prof in (default, profile):
        result["written"].append(str(_write_layout(prof, pins).relative_to(root)))
    result.update(pins=[p["name"] for p in pins], order=found["order"])
    return result
