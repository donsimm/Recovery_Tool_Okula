"""Ä-040: Einstellungen des Administrators im Master übernehmen – CopyProfile in der Antwortdatei, Taskleiste als
LayoutModification.xml im Standardprofil, Option im Dialog/in der Automatisierung. Läuft ohne root und ohne GTK."""

import os
import struct
import tempfile
import threading
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from okula_recovery import agentclient, automation, demo_agent, deploy, imagecheck, winprofile, winunattend as wu

N = {"u": wu.NS}
L = {"l": winprofile.NS_LAYOUT, "d": winprofile.NS_DEFAULT, "t": winprofile.NS_TASKBAR, "s": winprofile.NS_START}
STORE = "Microsoft.WindowsStore_8wekyb3d8bbwe!App"


# ---------- Hilfen: Registrierungsdatei und Verknüpfungen nachbauen ----------

class HiveWriter:
    """Kleine regf-Datei mit Schlüsseln (lf-Listen) und Werten – nur für Tests."""

    def __init__(self):
        self.buf = bytearray(b"hbin" + b"\0" * 28)      # Zellen-Offsets relativ zum Beginn der hbins (0x1000)

    def cell(self, data: bytes) -> int:
        off = len(self.buf)
        size = (4 + len(data) + 7) // 8 * 8
        self.buf += struct.pack("<i", -size) + data + b"\0" * (size - 4 - len(data))
        return off

    def value(self, name: str, kind: int, data: bytes) -> int:
        if len(data) <= 4:
            size, off = len(data) | 0x80000000, struct.unpack("<I", data.ljust(4, b"\0"))[0]
        elif len(data) > 16344:                          # grosse Daten in Segmenten („db“)
            segs = [self.cell(data[i:i + 16344]) for i in range(0, len(data), 16344)]
            seg_list = self.cell(b"".join(struct.pack("<I", s) for s in segs))
            size, off = len(data), self.cell(b"db" + struct.pack("<HI", len(segs), seg_list))
        else:
            size, off = len(data), self.cell(data)
        raw = name.encode("latin-1")
        return self.cell(b"vk" + struct.pack("<HIIIHH", len(raw), size, off, kind, 1, 0) + raw)

    def key(self, name: str, subkeys=(), values=()) -> int:
        lst = self.cell(b"lf" + struct.pack("<H", len(subkeys)) +
                        b"".join(struct.pack("<II", o, 0) for o in subkeys)) if subkeys else 0xFFFFFFFF
        vals = self.cell(b"".join(struct.pack("<I", o) for o in values)) if values else 0xFFFFFFFF
        raw = name.encode("latin-1")
        nk = bytearray(76)
        nk[0:2] = b"nk"
        struct.pack_into("<H", nk, 2, 0x20)
        struct.pack_into("<II", nk, 20, len(subkeys), 0)
        struct.pack_into("<I", nk, 28, lst)
        struct.pack_into("<II", nk, 36, len(values), vals)
        struct.pack_into("<H", nk, 72, len(raw))
        return self.cell(bytes(nk) + raw)

    def file(self, root: int) -> bytes:
        head = bytearray(4096)
        head[:4] = b"regf"
        struct.pack_into("<I", head, 0x24, root)
        return bytes(head) + bytes(self.buf)


def ntuser(favorites: bytes | None, extra_sibling: bool = True) -> bytes:
    """NTUSER.DAT mit Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Taskband\\Favorites."""
    h = HiveWriter()
    vals = [h.value("FavoritesVersion", 4, b"\3\0\0\0")]
    if favorites is not None:
        vals.append(h.value("Favorites", 3, favorites))
    node = h.key("Taskband", values=vals)
    for name in ("Explorer", "CurrentVersion", "Windows", "Microsoft"):
        children = [node]
        if extra_sibling:
            children.insert(0, h.key("Andere" + name))
        node = h.key(name, children)
    node = h.key("Software", [h.key("Classes"), node])
    return h.file(h.key("ROOT", [h.key("AppEvents"), node]))


def lnk(target: str = "", env: str = "", extra: bytes = b"") -> bytes:
    """Windows-Verknüpfung: Ziel über LinkInfo (target) bzw. EnvironmentVariableDataBlock (env)."""
    flags = 0x80 | (0x2 if target else 0) | (0x200 if env else 0)
    head = struct.pack("<I16sI", 0x4C, bytes.fromhex("0114020000000000c000000000000046"), flags).ljust(0x4C, b"\0")
    body = b""
    if target:
        volume = struct.pack("<IIII", 0x11, 3, 0x1234, 0x10) + b"\0"
        base = target.encode("cp1252") + b"\0"
        header = 0x1C
        local_off = header + len(volume)
        suffix_off = local_off + len(base)
        size = suffix_off + 1
        body += struct.pack("<IIIIIII", size, header, 1, header, local_off, 0, suffix_off) + volume + base + b"\0"
    if env:
        block = struct.pack("<II", 0x314, 0xA0000001) + env.encode("cp1252").ljust(260, b"\0") + \
            env.encode("utf-16-le").ljust(520, b"\0")
        body += block
    if extra:
        body += struct.pack("<II", 8 + len(extra), 0xA0000009) + extra
    return head + body + b"\0\0\0\0"


def u16(text: str) -> bytes:
    return text.encode("utf-16-le")


class Tree:
    """Eingehängte Windows-Partition nach dem Zurückspielen eines Master-Images (generalisiert)."""

    def __init__(self, base: Path):
        self.root = base
        for rel, data in {"Windows/System32/config/SYSTEM": b"regf",
                          "Windows/Setup/State/State.ini":
                              b"[State]\r\nImageState=IMAGE_STATE_GENERALIZE_RESEAL_TO_OOBE\r\n",
                          "Users/Default/NTUSER.DAT": b"regf",
                          "Users/Default/AppData/Local/Microsoft/Windows/Shell/DefaultLayouts.xml": b"<x/>",
                          "Users/Public/Desktop/desktop.ini": b""}.items():
            self.write(rel, data)

    def write(self, rel: str, data: bytes) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def pin(self, profile: str, name: str, data: bytes) -> Path:
        return self.write(f"Users/{profile}/{winprofile.TASKBAR_DIR}/{name}", data)

    def layout(self, profile: str = "Default") -> ET.Element:
        return ET.parse(self.root / f"Users/{profile}/{winprofile.SHELL_DIR}/LayoutModification.xml").getroot()


def pins_of(root: ET.Element) -> list[tuple[str, str]]:
    out = []
    for el in root.find("l:CustomTaskbarLayoutCollection/d:TaskbarLayout/t:TaskbarPinList", L):
        tag = el.tag.rsplit("}", 1)[1]
        out.append((tag, el.get("AppUserModelID") or el.get("DesktopApplicationID")
                    or el.get("DesktopApplicationLinkPath")))
    return out


# ---------- Antwortdatei ----------

class CopyProfileUnattendTest(unittest.TestCase):
    def component(self, xml: str, pass_name: str, name: str):
        root = ET.fromstring(xml)
        return next((c for s in root if s.get("pass") == pass_name for c in s if c.get("name") == name), None)

    def test_copy_profile_on(self):
        xml = wu.master_unattend("PC-1", "VK7JG-NPHTM-C97JM-9MPGT-3V66T", True, "Okula", copy_profile=True)
        shell = self.component(xml, "specialize", "Microsoft-Windows-Shell-Setup")
        self.assertEqual(shell.find("u:CopyProfile", N).text, "true")
        self.assertEqual(xml.count("CopyProfile"), 2)          # öffnendes und schliessendes Tag, nur einmal
        # nur specialize (laut Microsoft der einzige gültige Durchgang), Reihenfolge wie Windows SIM
        oobe = self.component(xml, "oobeSystem", "Microsoft-Windows-Shell-Setup")
        self.assertIsNone(oobe.find("u:CopyProfile", N))
        tags = [c.tag.rsplit("}", 1)[1] for c in shell]
        self.assertEqual(tags, ["ComputerName", "CopyProfile", "ProductKey", "TimeZone"])
        self.assertNotIn('pass="windowsPE"', xml)

    def test_copy_profile_off_unchanged(self):
        off = wu.master_unattend("PC-1", "", False, "")
        self.assertNotIn("CopyProfile", off)
        self.assertEqual(off, wu.master_unattend("PC-1", "", False, "", copy_profile=False))

    def test_never_in_audit_mode(self):
        xml = wu.build(wu.WinOptions(audit_mode=True, copy_profile=True), pe=False)
        self.assertNotIn("CopyProfile", xml)

    def test_log_texts(self):
        base = {"part": "/dev/sda3", "system": "windows", "action": "unattend"}
        self.assertIn("Agent zu alt", wu.taskbar_log(base))
        ok = wu.taskbar_log({**base, "taskbar": {"pins": ["VLC media player", "Explorer"], "order": "registry"}})
        self.assertEqual(ok, "Einstellungen des Administrators werden übernommen – Taskleiste: VLC media player, "
                             "Explorer")
        self.assertIn("nach Datum", wu.taskbar_log({**base, "taskbar": {"pins": ["A"], "order": "date"}}))
        self.assertIn("keine angehefteten Symbole gefunden, unverändert",
                      wu.taskbar_log({**base, "taskbar": {"pins": [], "reason": "keine angehefteten Symbole "
                                                                                "gefunden"}}))
        self.assertIn("nicht übernommen: kaputt", wu.taskbar_log({**base, "taskbar": {"error": "kaputt"}}))


# ---------- Registrierung und Verknüpfungen lesen ----------

class ReadTest(unittest.TestCase):
    def test_hive_value(self):
        blob = b"\x01\x02" + u16("abc")
        hive = winprofile.Hive(ntuser(blob))
        self.assertEqual(hive.value(winprofile.TASKBAND_KEY.upper(), "FAVORITES"), (3, blob))   # Gross/Klein egal
        self.assertEqual(hive.value(winprofile.TASKBAND_KEY, "FavoritesVersion"), (4, b"\3\0\0\0"))
        self.assertIsNone(hive.value(winprofile.TASKBAND_KEY, "Fehlt"))
        self.assertIsNone(hive.value(r"Software\Fehlt", "Favorites"))
        big = bytes(range(256)) * 100                         # > 16344 Bytes: Segmente
        self.assertEqual(winprofile.Hive(ntuser(big)).value(winprofile.TASKBAND_KEY, "Favorites")[1], big)
        with self.assertRaises(winprofile.ProfileError):
            winprofile.Hive(b"kein hive")

    def test_read_favorites_robust(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "NTUSER.DAT"
            p.write_bytes(b"regf" + b"\xff" * 5000)           # kaputt: keine Ausnahme, nur None
            self.assertIsNone(winprofile.read_favorites(p))
            p.write_bytes(ntuser(None))
            self.assertIsNone(winprofile.read_favorites(p))
            self.assertIsNone(winprofile.read_favorites(Path(tmp) / "fehlt"))

    def test_positions_both_alignments(self):
        blob = b"\0" + u16("B.lnk") + b"\0\0" + b"x" + u16(STORE) + b"\0\0" + u16("a.lnk")
        self.assertLess(winprofile.find_position(blob, "b.LNK"), winprofile.find_position(blob, "A.lnk"))
        self.assertIsNone(winprofile.find_position(blob, "c.lnk"))
        apps = winprofile.find_store_apps(blob + b"\0\0" + u16(STORE) + b"\0\0")
        self.assertEqual([a for _p, a in apps], [STORE])       # ohne Doppel

    def test_lnk_target_and_classify(self):
        self.assertEqual(winprofile.lnk_target(lnk(r"C:\Program Files\VideoLAN\VLC\vlc.exe")),
                         r"C:\Program Files\VideoLAN\VLC\vlc.exe")
        self.assertEqual(winprofile.lnk_target(lnk(env=r"%windir%\explorer.exe")), r"%windir%\explorer.exe")
        self.assertEqual(winprofile.lnk_target(b"kaputt"), "")
        self.assertEqual(winprofile.classify(lnk(env=r"%windir%\explorer.exe")), ("id", "Microsoft.Windows.Explorer"))
        self.assertEqual(winprofile.classify(lnk(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")),
                         ("id", "MSEdge"))
        self.assertEqual(winprofile.classify(lnk(r"C:\Program Files\VideoLAN\VLC\vlc.exe")),
                         ("lnk", r"c:\program files\videolan\vlc\vlc.exe"))
        # nur Shell-Element (kein lesbares Ziel): am Programmnamen erkannt
        self.assertEqual(winprofile.classify(b"L\0\0\0" + b"\0" * 0x48 + u16(r"C:\Windows\explorer.exe")),
                         ("id", "Microsoft.Windows.Explorer"))


# ---------- Taskleiste übernehmen ----------

class AdoptTaskbarTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.t = Tree(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def master(self, favorites: bool = True):
        t = self.t
        t.pin("Administrator", "VLC media player.lnk", lnk(r"C:\Program Files\VideoLAN\VLC\vlc.exe"))
        t.pin("Administrator", "File Explorer.lnk", lnk(env=r"%windir%\explorer.exe"))
        t.pin("Administrator", "Tool.lnk", lnk(r"C:\Tools\tool.exe"))
        t.pin("Administrator", "Microsoft Edge.lnk",
              lnk(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"))
        t.write("Users/Administrator/AppData/Roaming/Microsoft/Internet Explorer/Quick Launch/desktop.ini", b"")
        # Startmenü für alle Benutzer: VLC unter anderem Namen (Zuordnung über das Ziel)
        t.write("ProgramData/Microsoft/Windows/Start Menu/Programs/VideoLAN/VLC.lnk",
                lnk(r"C:\Program Files\VideoLAN\VLC\vlc.exe"))
        t.write("ProgramData/Microsoft/Windows/Start Menu/Programs/Zubehör/Rechner.lnk", lnk(r"C:\Windows\calc.exe"))
        blob = (b"\x0c\0" + u16("VLC media player.lnk") + b"\0" * 7 + u16(STORE) + b"\0" * 3
                + u16("File Explorer.lnk") + b"\0" * 4 + u16("TOOL.LNK") + b"\0" * 2 + u16("Microsoft Edge.lnk"))
        t.write("Users/Administrator/NTUSER.DAT", ntuser(blob if favorites else None))
        # Default und Public werden nie als Quelle genommen
        t.pin("Default", "Falsch.lnk", lnk(r"C:\falsch.exe"))
        t.pin("Public", "Falsch.lnk", lnk(r"C:\falsch.exe"))

    def test_order_paths_and_files(self):
        self.master()
        res = winprofile.adopt_taskbar(self.t.root)
        self.assertEqual(res["profile"], "Administrator")
        self.assertEqual(res["pins"], ["VLC media player", "Microsoft Store", "Explorer", "Tool", "Microsoft Edge"])
        self.assertEqual(res["order"], "registry")
        menu = winprofile.START_MENU_ENV
        expected = [("DesktopApp", menu + r"\VideoLAN\VLC.lnk"), ("UWA", STORE),
                    ("DesktopApp", "Microsoft.Windows.Explorer"), ("DesktopApp", menu + r"\Okula\Tool.lnk"),
                    ("DesktopApp", "MSEdge")]
        root = self.t.layout()
        self.assertEqual(root.tag, f"{{{winprofile.NS_LAYOUT}}}LayoutModificationTemplate")
        self.assertEqual(root.find("l:CustomTaskbarLayoutCollection", L).get("PinListPlacement"), "Replace")
        self.assertEqual(pins_of(root), expected)
        # gleiche Datei im Quellprofil (CopyProfile überschreibt das Standardprofil mit dem des Administrators)
        self.assertEqual(pins_of(self.t.layout("Administrator")), expected)
        self.assertEqual(sorted(res["written"]), sorted([
            f"Users/Default/{winprofile.SHELL_DIR}/LayoutModification.xml",
            f"Users/Administrator/{winprofile.SHELL_DIR}/LayoutModification.xml"]))
        # Verknüpfung ohne Eintrag im Startmenü: Kopie unter Programs\Okula
        copy = self.t.root / "ProgramData/Microsoft/Windows/Start Menu/Programs/Okula/Tool.lnk"
        self.assertEqual(copy.read_bytes(), lnk(r"C:\Tools\tool.exe"))
        self.assertEqual(res["copied"], [str(copy.relative_to(self.t.root))])
        text = (self.t.root / res["written"][0]).read_text(encoding="utf-8")
        self.assertTrue(text.startswith('<?xml version="1.0" encoding="utf-8"?>\n<LayoutModificationTemplate '))
        self.assertIn('xmlns:taskbar="http://schemas.microsoft.com/Start/2014/TaskbarLayout"', text)
        self.assertNotIn("ns0", text)
        self.assertNotIn("Falsch", text)
        # andere Dateien im Standardprofil bleiben
        self.assertTrue((self.t.root / f"Users/Default/{winprofile.SHELL_DIR}/DefaultLayouts.xml").is_file())

    def test_exact_xml(self):
        xml = winprofile.layout_xml([{"kind": "app", "value": STORE},
                                     {"kind": "id", "value": "Microsoft.Windows.Explorer"},
                                     {"kind": "link", "value": r"%ALLUSERSPROFILE%\A & B\Ä.lnk"}])
        self.assertEqual(xml, "\n".join((
            '<?xml version="1.0" encoding="utf-8"?>',
            '<LayoutModificationTemplate xmlns="http://schemas.microsoft.com/Start/2014/LayoutModification" '
            'xmlns:defaultlayout="http://schemas.microsoft.com/Start/2014/FullDefaultLayout" '
            'xmlns:start="http://schemas.microsoft.com/Start/2014/StartLayout" '
            'xmlns:taskbar="http://schemas.microsoft.com/Start/2014/TaskbarLayout" Version="1">',
            '  <CustomTaskbarLayoutCollection PinListPlacement="Replace">',
            '    <defaultlayout:TaskbarLayout>',
            '      <taskbar:TaskbarPinList>',
            f'        <taskbar:UWA AppUserModelID="{STORE}" />',
            '        <taskbar:DesktopApp DesktopApplicationID="Microsoft.Windows.Explorer" />',
            '        <taskbar:DesktopApp DesktopApplicationLinkPath="%ALLUSERSPROFILE%\\A &amp; B\\Ä.lnk" />',
            '      </taskbar:TaskbarPinList>',
            '    </defaultlayout:TaskbarLayout>',
            '  </CustomTaskbarLayoutCollection>',
            '</LayoutModificationTemplate>', "")))
        ET.fromstring(xml.split("\n", 1)[1])                       # gültiges XML

    def test_order_by_date_without_registry(self):
        self.master(favorites=False)
        taskbar = self.t.root / "Users/Administrator" / winprofile.TASKBAR_DIR
        for i, name in enumerate(("Tool.lnk", "Microsoft Edge.lnk", "File Explorer.lnk", "VLC media player.lnk")):
            os.utime(taskbar / name, (1_700_000_000 + i, 1_700_000_000 + i))
        res = winprofile.adopt_taskbar(self.t.root)
        self.assertEqual(res["order"], "date")
        self.assertEqual(res["pins"], ["Tool", "Microsoft Edge", "Explorer", "VLC media player"])   # ohne Store-App

    def test_no_pins_nothing_written(self):
        self.t.write("Users/Administrator/NTUSER.DAT", ntuser(b""))
        res = winprofile.adopt_taskbar(self.t.root)
        self.assertEqual((res["pins"], res["written"]), ([], []))
        self.assertEqual(res["reason"], "keine angehefteten Symbole gefunden")
        self.assertFalse((self.t.root / f"Users/Default/{winprofile.SHELL_DIR}/LayoutModification.xml").exists())

    def test_profile_choice(self):
        self.t.write("Users/Anna/NTUSER.DAT", b"regf")
        self.t.pin("Anna", "A.lnk", lnk(r"C:\a.exe"))
        self.assertEqual(winprofile.source_profile(self.t.root)[0].name, "Anna")     # einziges mit Pins
        self.t.write("Users/Beat/NTUSER.DAT", b"regf")
        self.t.pin("Beat", "B.lnk", lnk(r"C:\b.exe"))
        profile, reason = winprofile.source_profile(self.t.root)
        self.assertIsNone(profile)
        self.assertIn("nicht eindeutig", reason)
        self.assertEqual(winprofile.adopt_taskbar(self.t.root)["written"], [])
        self.t.write("Users/Administrator/NTUSER.DAT", b"regf")
        self.t.pin("Administrator", "C.lnk", lnk(r"C:\c.exe"))
        self.assertEqual(winprofile.source_profile(self.t.root)[0].name, "Administrator")   # hat Vorrang

    def test_existing_start_layout_kept(self):
        self.master()
        shell = self.t.root / f"Users/Default/{winprofile.SHELL_DIR}"
        (shell / "LayoutModification.xml").write_text(
            '<LayoutModificationTemplate xmlns="http://schemas.microsoft.com/Start/2014/LayoutModification" '
            'xmlns:defaultlayout="http://schemas.microsoft.com/Start/2014/FullDefaultLayout" '
            'xmlns:start="http://schemas.microsoft.com/Start/2014/StartLayout" '
            'xmlns:taskbar="http://schemas.microsoft.com/Start/2014/TaskbarLayout" Version="1">'
            '<LayoutOptions StartTileGroupCellWidth="6" />'
            '<DefaultLayoutOverride><StartLayoutCollection><defaultlayout:StartLayout GroupCellWidth="6">'
            '<start:Group Name="Okula"><start:Tile Size="2x2" Column="0" Row="0" AppUserModelID="X!App" />'
            '</start:Group></defaultlayout:StartLayout></StartLayoutCollection></DefaultLayoutOverride>'
            '<CustomTaskbarLayoutCollection><defaultlayout:TaskbarLayout><taskbar:TaskbarPinList>'
            '<taskbar:DesktopApp DesktopApplicationID="Alt" /></taskbar:TaskbarPinList></defaultlayout:TaskbarLayout>'
            '</CustomTaskbarLayoutCollection><InkWorkspaceTopApps /></LayoutModificationTemplate>', encoding="utf-8")
        winprofile.adopt_taskbar(self.t.root)
        root = self.t.layout()
        self.assertEqual([c.tag.rsplit("}", 1)[1] for c in root],
                         ["LayoutOptions", "DefaultLayoutOverride", "CustomTaskbarLayoutCollection",
                          "InkWorkspaceTopApps"])
        self.assertEqual(root.find(".//s:Tile", L).get("AppUserModelID"), "X!App")
        self.assertNotIn(("DesktopApp", "Alt"), pins_of(root))
        self.assertEqual(len(pins_of(root)), 5)

    def test_invalid_existing_file_kept_aside(self):
        self.master()
        shell = self.t.root / f"Users/Default/{winprofile.SHELL_DIR}"
        (shell / "LayoutModification.xml").write_text("<kaputt", encoding="utf-8")
        winprofile.adopt_taskbar(self.t.root)
        self.assertEqual((shell / "LayoutModification.xml.okula-vorher").read_text(), "<kaputt")
        self.assertEqual(len(pins_of(self.t.layout())), 5)


# ---------- Agent: Anpassen mit/ohne Option ----------

class CustomizeRootTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.t = Tree(Path(self.tmp.name))
        self.t.write("Users/Administrator/NTUSER.DAT", ntuser(u16("VLC.lnk")))
        self.t.pin("Administrator", "VLC.lnk", lnk(r"C:\vlc.exe"))
        self.layout = self.t.root / f"Users/Default/{winprofile.SHELL_DIR}/LayoutModification.xml"

    def tearDown(self):
        self.tmp.cleanup()

    def test_option_off_writes_nothing(self):
        res = deploy.customize_root(self.t.root, "<unattend/>", "", copy_profile=False)
        self.assertEqual(res, {"system": "windows", "action": "unattend"})
        self.assertFalse(self.layout.exists())
        self.assertTrue((self.t.root / "Windows/Panther/unattend.xml").is_file())

    def test_option_on(self):
        res = deploy.customize_root(self.t.root, "<unattend/>", "", copy_profile=True)
        self.assertEqual(res["taskbar"]["pins"], ["VLC"])
        self.assertTrue(self.layout.is_file())

    def test_not_generalized_untouched(self):
        self.t.write("Windows/Setup/State/State.ini", b"[State]\r\nImageState=IMAGE_STATE_COMPLETE\r\n")
        res = deploy.customize_root(self.t.root, "<unattend/>", "", copy_profile=True)
        self.assertEqual(res, {"system": "windows", "action": "not_generalized"})
        self.assertFalse(self.layout.exists())
        self.assertFalse((self.t.root / "Windows/Panther").exists())

    def test_error_reported_not_raised(self):
        with mock.patch.object(winprofile, "adopt_taskbar", side_effect=OSError("Disk voll")):
            res = deploy.customize_root(self.t.root, "<unattend/>", "", copy_profile=True)
        self.assertEqual(res["action"], "unattend")
        self.assertEqual(res["taskbar"]["error"], "Disk voll")

    def test_demo_agent(self):
        with mock.patch.object(demo_agent.time, "sleep", lambda s: None):
            on = demo_agent.customize({"copy_profile": True}, log=lambda *a: None)["results"][0]
            off = demo_agent.customize({}, log=lambda *a: None)["results"][0]
        self.assertIn("Explorer", on["taskbar"]["pins"])
        self.assertNotIn("taskbar", off)


# ---------- Automatisierung ----------

class AutomationOptionTest(unittest.TestCase):
    def test_default_on_and_saved(self):
        self.assertTrue(automation.Settings().copy_profile)
        self.assertTrue(automation.Settings.from_dict({"swiss": False}).copy_profile)   # alte Einstellungen
        s = automation.Settings.from_dict({"copy_profile": False})
        self.assertFalse(s.copy_profile)
        self.assertFalse(automation.Settings.from_dict(s.to_dict()).copy_profile)
        self.assertIn("copy_profile", automation.TEMPLATE_FIELDS)

    def run_work(self, copy_profile: bool) -> tuple[list, list]:
        calls, lines = [], []
        with tempfile.TemporaryDirectory() as nas:
            (Path(nas) / "images/Master").mkdir(parents=True)
            s = automation.Settings(image="images/Master", disk_key="S1", finish="none", copy_profile=copy_profile)
            dev = SimpleNamespace(id="d1", name="PC-1", windows_key=("", ""))

            def customize(ip, key, disk, xml, hostname, port, copy_profile=False):
                calls.append((xml, copy_profile))
                result = {"part": "/dev/sda3", "system": "windows", "action": "unattend"}
                if copy_profile:
                    result["taskbar"] = {"pins": ["VLC"], "order": "registry"}
                return [result]

            jm = SimpleNamespace(log=lambda job, line: lines.append(line), progress=lambda *a, **k: None)
            job = SimpleNamespace(cancel=threading.Event(), phase="läuft")
            patches = [mock.patch.object(agentclient, "get_info", lambda *a: {"disks": [
                           {"path": "/dev/sda", "serial": "S1", "model": "SSD", "size": 100}]}),
                       mock.patch.object(agentclient, "image_source", lambda *a: {"source": {"size": 50}}),
                       mock.patch.object(agentclient, "restore_image", lambda *a, **k: None),
                       mock.patch.object(agentclient, "customize", customize),
                       mock.patch.object(agentclient, "banner", lambda *a, **k: True),
                       mock.patch.object(imagecheck, "load", lambda *a: None),
                       mock.patch.object(imagecheck, "warning", lambda *a: "")]
            for p in patches:
                p.start()
            try:
                result = automation.automation_work("10.0.0.1", b"k" * 32, 1, dev, s, nas, {})(job, jm)
            finally:
                for p in patches:
                    p.stop()
        self.assertEqual(result, "Automatisierung fertig")
        return calls, lines

    def test_option_passed_to_agent(self):
        calls, lines = self.run_work(True)
        self.assertEqual(len(calls), 1)
        self.assertIn("<CopyProfile>true</CopyProfile>", calls[0][0])
        self.assertTrue(calls[0][1])
        self.assertIn("  /dev/sda3: Einstellungen des Administrators werden übernommen – Taskleiste: VLC", lines)
        self.assertTrue(any("Einstellungen des Administrators" in line and "Schritt 3/5" in line for line in lines))
        calls, lines = self.run_work(False)
        self.assertNotIn("CopyProfile", calls[0][0])
        self.assertFalse(calls[0][1])
        self.assertFalse(any("Einstellungen des Administrators" in line for line in lines))


if __name__ == "__main__":
    unittest.main()
