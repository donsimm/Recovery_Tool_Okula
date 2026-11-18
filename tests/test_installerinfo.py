"""Ä-043: Installer-Typen erkennen – Probe-Dateien mit den Kennungen jedes Typs, Versionsinfo aus einer
konstruierten Ressource, MSI-Tabelle Property aus einer erzeugten Compound-Datei, Qt Installer Framework mit
config.xml/Updates.xml, NSIS-Kopf (deflate und LZMA), MSIX/MSU/MSP im Installationsskript, „Neu erkennen“."""

import io
import json
import lzma
import struct
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path
from unittest import mock

from okula_recovery import installerinfo, software


# ---------- Probe-Dateien bauen ----------

def _align(n: int, a: int) -> int:
    return (n + a - 1) // a * a


def vs_node(key: str, value: bytes, typ: int, children: bytes = b"") -> bytes:
    """Ein Knoten aus VS_VERSIONINFO: wLength, wValueLength, wType, Schlüssel, Auffüllen, Wert, Kinder."""
    k = key.encode("utf-16-le") + b"\0\0"
    pad1 = b"\0" * ((-(6 + len(k))) % 4)
    pad2 = b"\0" * ((-len(value)) % 4)
    body = k + pad1 + value + pad2 + children
    vlen = len(value) // 2 if typ == 1 else len(value)
    return struct.pack("<HHH", 6 + len(body), vlen, typ) + body


def version_resource(strings: dict[str, str], fixed=(1, 2, 3, 4)) -> bytes:
    nodes = b"".join(vs_node(k, (v + "\0").encode("utf-16-le"), 1) for k, v in strings.items())
    table = vs_node("040904b0", b"", 1, nodes)
    ms, ls = (fixed[0] << 16) | fixed[1], (fixed[2] << 16) | fixed[3]
    ffi = struct.pack("<13I", 0xFEEF04BD, 0x10000, ms, ls, ms, ls, 0x3F, 0, 0x40004, 1, 0, 0, 0)
    var = vs_node("VarFileInfo", b"", 1, vs_node("Translation", struct.pack("<HH", 0x409, 1200), 0))
    return vs_node("VS_VERSION_INFO", ffi, 0, vs_node("StringFileInfo", b"", 1, table) + var)


def rsrc_section(resources: dict[int, bytes], va: int) -> bytes:
    """Ressourcenverzeichnis: Typ → ID 1 → Sprache 0x409 → Datenblock."""
    types = sorted(resources)
    pos = 16 + 8 * len(types)
    layout = []
    for t in types:
        layout.append((t, pos, pos + 24, pos + 48))
        pos += 64
    data_pos = []
    for t in types:
        data_pos.append(pos)
        pos = _align(pos + len(resources[t]), 4)
    buf = bytearray(pos)

    def head(at: int, n: int) -> None:
        struct.pack_into("<IIHHHH", buf, at, 0, 0, 0, 0, 0, n)

    head(0, len(types))
    for i, (t, name_dir, lang_dir, data_entry) in enumerate(layout):
        struct.pack_into("<II", buf, 16 + 8 * i, t, 0x80000000 | name_dir)
        head(name_dir, 1)
        struct.pack_into("<II", buf, name_dir + 16, 1, 0x80000000 | lang_dir)
        head(lang_dir, 1)
        struct.pack_into("<II", buf, lang_dir + 16, 0x409, data_entry)
        struct.pack_into("<IIII", buf, data_entry, va + data_pos[i], len(resources[t]), 0, 0)
        buf[data_pos[i]:data_pos[i] + len(resources[t])] = resources[t]
    return bytes(buf)


def pe_file(body: bytes = b"", resources: dict[int, bytes] | None = None, overlay: bytes = b"",
            sections: tuple = (".text",), extra: dict[str, bytes] | None = None, is64: bool = True) -> bytes:
    """Windows-Programm mit optionalem Kopf, Abschnitten (erster mit body, extra: weitere mit Inhalt), Ressourcen
    (.rsrc) und angehängten Daten."""
    contents = [(name, body if i == 0 else b"\0" * 16) for i, name in enumerate(sections)]
    contents += list((extra or {}).items())
    opt_size = 240 if is64 else 224
    count = len(contents) + (1 if resources else 0)
    raw = _align(0x80 + 24 + opt_size + 40 * count, 0x200)
    va = 0x1000
    table, data, dirs = b"", b"", [(0, 0)] * 16
    for name, content in contents + ([(".rsrc", None)] if resources else []):
        if content is None:
            content = rsrc_section(resources, va)
            dirs[2] = (va, len(content))
        size = _align(max(len(content), 1), 0x200)
        table += name.encode().ljust(8, b"\0") + struct.pack("<IIII", len(content), va, size, raw + len(data)) \
            + bytes(16)
        data += content.ljust(size, b"\0")
        va += _align(size, 0x1000)
    opt = bytearray(opt_size)
    struct.pack_into("<H", opt, 0, 0x20B if is64 else 0x10B)
    num_at, dirs_at = (108, 112) if is64 else (92, 96)
    struct.pack_into("<I", opt, num_at, 16)
    for i, (a, s) in enumerate(dirs):
        struct.pack_into("<II", opt, dirs_at + 8 * i, a, s)
    head = bytearray(0x80)
    head[:2] = b"MZ"
    struct.pack_into("<I", head, 0x3C, 0x80)
    coff = b"PE\0\0" + struct.pack("<HHIIIHH", 0x8664 if is64 else 0x14C, count, 0, 0, 0, opt_size, 0x22)
    out = bytes(head) + coff + bytes(opt) + table
    return out.ljust(raw, b"\0") + data + overlay


def manifest(description: str = "", name: str = "Probe.Setup") -> bytes:
    return (f'<?xml version="1.0"?><assembly><assemblyIdentity name="{name}"/>'
            f"<description>{description}</description></assembly>").encode()


def rcc(tree: dict, compress: tuple = ()) -> bytes:
    """Qt-Ressourcen (Version 1): tree = {"config": {"config.xml": b"…"}, "Updates.xml": b"…"}."""
    names, data, nodes = bytearray(), bytearray(), []

    def name(n: str) -> int:
        off = len(names)
        names.extend(struct.pack(">HI", len(n), 0) + n.encode("utf-16-be"))
        return off

    def add_dir(children: dict) -> tuple[int, int]:
        """Kinder einer Ebene hintereinander anlegen, danach deren Unterverzeichnisse."""
        first = len(nodes)
        items = list(children.items())
        nodes.extend([None] * len(items))
        for i, (n, c) in enumerate(items):
            if isinstance(c, dict):
                nodes[first + i] = ("dir", name(n), c)
            else:
                flag = 1 if n in compress else 0
                content = struct.pack(">I", len(c)) + zlib.compress(c) if flag else c
                nodes[first + i] = ("file", name(n), flag, len(data))
                data.extend(struct.pack(">I", len(content)) + content)
        for i, node in enumerate(nodes[first:first + len(items)]):
            if node[0] == "dir":
                child_first, count = add_dir(node[2])
                nodes[first + i] = ("dirdone", node[1], count, child_first)
        return first, len(items)

    nodes.append(("root",))
    first, count = add_dir(tree)
    tree_bytes = struct.pack(">IHII", 0, 2, count, first)
    for node in nodes[1:]:
        if node[0] == "dirdone":
            tree_bytes += struct.pack(">IHII", node[1], 2, node[2], node[3])
        else:
            tree_bytes += struct.pack(">IHHHI", node[1], node[2], 0, 0, node[3])
    data_start = 20
    names_start = data_start + len(data)
    tree_start = names_start + len(names)
    return b"qres" + struct.pack(">IIII", 1, tree_start, data_start, names_start) + bytes(data) + bytes(names) \
        + tree_bytes


IFW_CONFIG = b"""<?xml version='1.0' encoding='UTF-8'?>
<Installer>
    <Name>Araneo</Name>
    <Version>1.10.2</Version>
    <Title>Araneo</Title>
    <Publisher>Luminex Network Intelligence</Publisher>
    <TargetDir>@ApplicationsDirX64@/Araneo</TargetDir>
</Installer>
"""
IFW_UPDATES = b"""<Updates>
 <ApplicationName>Araneo</ApplicationName>
 <ApplicationVersion>1.10.2</ApplicationVersion>
 <PackageUpdate><Name>Araneo</Name><Version>1.10.2</Version><Default>true</Default></PackageUpdate>
</Updates>
"""


def qt_ifw(framework: str = "4.6.1", config: bytes = IFW_CONFIG, in_rdata: bool = False) -> bytes:
    marker = f"Built with Qt Installer Framework {framework}".encode()
    return pe_file(body=b"" if in_rdata else marker, sections=(".text",),
                   extra={".rdata": marker} if in_rdata else None,
                   overlay=rcc({"config": {"config.xml": config}, "Updates.xml": IFW_UPDATES},
                               compress=("config.xml",)))


def nsis(header: bytes, solid_lzma: bool = False, vi: dict | None = None) -> bytes:
    """NSIS-Installer: Programmteil mit Manifest, danach firstheader und gepackter Kopf."""
    if solid_lzma:
        filters = [{"id": lzma.FILTER_LZMA1, "dict_size": 1 << 16, "lc": 3, "lp": 0, "pb": 2}]
        packed = bytes([0x5D]) + struct.pack("<I", 1 << 16) + \
            lzma.compress(struct.pack("<I", len(header)) + header, format=lzma.FORMAT_RAW, filters=filters)
    else:
        deflate = zlib.compressobj(9, zlib.DEFLATED, -15)
        raw = deflate.compress(header) + deflate.flush()
        packed = struct.pack("<I", len(raw) | 0x80000000) + raw
    first = struct.pack("<I", 0) + installerinfo.NSIS_SIG + struct.pack("<II", len(header), len(packed) + 28)
    resources = {24: manifest("Nullsoft Install System v3.10", "Nullsoft.NSIS.exehead")}
    if vi:
        resources[16] = version_resource(vi)
    return pe_file(sections=(".text", ".ndata"), resources=resources, overlay=first + packed)


def nsis_strings(*texts: str) -> bytes:
    return b"".join(t.encode("utf-16-le") + b"\0\0" for t in texts)


ENDOFCHAIN, FREESECT, FATSECT = 0xFFFFFFFE, 0xFFFFFFFF, 0xFFFFFFFD


def cfb(streams: dict[str, bytes]) -> bytes:
    """Compound File (Version 3, 512-Byte-Sektoren): Datenströme unter 4096 Byte im Mini-Stream, sonst in Sektoren."""
    sector = 512
    mini_data, mini_fat, big = bytearray(), [], []
    entries = [("Root Entry", 5, 0, 0)]                       # Name, Typ, Start, Grösse (Start der Wurzel später)
    for name, content in streams.items():
        if len(content) < 4096:
            start = len(mini_data) // 64
            n = max(1, _align(len(content), 64) // 64)
            mini_fat += [start + i + 1 for i in range(n - 1)] + [ENDOFCHAIN]
            mini_data += content.ljust(n * 64, b"\0")
            entries.append((name, 2, start, len(content)))
        else:
            big.append((len(entries), content))
            entries.append((name, 2, None, len(content)))
    sectors: list[bytes] = []
    fat: list[int] = [FATSECT]                                 # Sektor 0 = FAT

    def put(blob: bytes) -> int:
        start = len(sectors) + 1
        n = max(1, _align(len(blob), sector) // sector)
        for i in range(n):
            sectors.append(blob[i * sector:(i + 1) * sector].ljust(sector, b"\0"))
            fat.append(start + i + 1 if i < n - 1 else ENDOFCHAIN)
        return start

    for index, content in big:
        e = entries[index]
        entries[index] = (e[0], e[1], put(content), e[3])
    mini_start = put(bytes(mini_data)) if mini_data else ENDOFCHAIN
    minifat_start = put(struct.pack(f"<{len(mini_fat)}I", *mini_fat)) if mini_fat else ENDOFCHAIN
    entries[0] = ("Root Entry", 5, mini_start, len(mini_data))
    dirs = bytearray()
    for i, (name, typ, start, size) in enumerate(entries):
        raw_name = name.encode("utf-16-le") + b"\0\0"
        e = bytearray(128)
        e[:len(raw_name)] = raw_name
        right = i + 1 if 0 < i < len(entries) - 1 else FREESECT
        child = 1 if i == 0 and len(entries) > 1 else FREESECT
        struct.pack_into("<HBBIII", e, 64, len(raw_name), typ, 1, FREESECT, right, child)
        struct.pack_into("<IQ", e, 116, start, size)
        dirs += e
    dir_start = put(bytes(dirs))
    fat_sector = struct.pack(f"<{len(fat)}I", *fat).ljust(sector, b"\xff")
    header = bytearray(512)
    header[:8] = installerinfo.CFB_MAGIC
    struct.pack_into("<HHHHH", header, 0x18, 0x3E, 3, 0xFFFE, 9, 6)
    struct.pack_into("<IIIIIIII", header, 0x2C, 1, dir_start, 0, 4096, minifat_start,
                     1 if mini_fat else 0, ENDOFCHAIN, 0)
    difat = [0] + [FREESECT] * 108
    struct.pack_into("<109I", header, 0x4C, *difat)
    return bytes(header) + fat_sector + b"".join(sectors)


def msi(props: dict[str, str], codepage: int = 65001) -> bytes:
    """MSI mit String-Pool und Tabelle Property (2-Byte-Verweise)."""
    strings = list(dict.fromkeys(list(props) + list(props.values())))
    enc = "utf-8" if codepage == 65001 else f"cp{codepage}"
    raw = [s.encode(enc) for s in strings]
    pool = struct.pack("<HH", codepage & 0xFFFF, codepage >> 16) + b"".join(struct.pack("<HH", len(r), 1)
                                                                           for r in raw)
    ids = {s: i + 1 for i, s in enumerate(strings)}
    table = b"".join(struct.pack("<H", ids[k]) for k in props) + b"".join(struct.pack("<H", ids[v])
                                                                         for v in props.values())
    name = installerinfo.msi_stream_name
    return cfb({name("!_StringPool"): pool, name("!_StringData"): b"".join(raw), name("!Property"): table,
                "\x05SummaryInformation": b"\0" * 48})


def appx(identity: dict, display: str = "", publisher_display: str = "", bundle: bool = False) -> bytes:
    attrs = " ".join(f'{k}="{v}"' for k, v in identity.items())
    props = (f"<Properties><DisplayName>{display}</DisplayName>"
             f"<PublisherDisplayName>{publisher_display}</PublisherDisplayName></Properties>") if display else ""
    xml = f'<?xml version="1.0"?><Package xmlns="x"><Identity {attrs} />{props}</Package>'
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("AppxMetadata/AppxBundleManifest.xml" if bundle else "AppxManifest.xml", xml)
        z.writestr("[Content_Types].xml", "<Types/>")
    return out.getvalue()


# ---------- Tests ----------

class ReaderTest(unittest.TestCase):
    def test_version_resource_constructed(self):
        res = version_resource({"ProductName": "Probe Studio", "ProductVersion": "2.5.1", "CompanyName": "Okula AG",
                                "OriginalFilename": "probe-setup.exe"}, fixed=(2, 5, 1, 7))
        vi = installerinfo.parse_version_resource(res)
        self.assertEqual((vi["ProductName"], vi["ProductVersion"], vi["CompanyName"], vi["#FileVersion"]),
                         ("Probe Studio", "2.5.1", "Okula AG", "2.5.1.7"))
        data = pe_file(resources={16: res, 24: manifest("Probe")}, overlay=b"ANGEHAENGT")
        with installerinfo.Blob(data) as blob:
            pe = installerinfo.pe_info(blob)
            self.assertTrue(pe.is64)
            self.assertEqual(blob.read(pe.image_end, 10), b"ANGEHAENGT")       # Overlay = nach den Abschnitten
            self.assertEqual(installerinfo.resources(blob, pe, 16), [res])
            self.assertIn("<description>Probe</description>", installerinfo.manifest_text(blob, pe))
        found = software.detect_bytes(data, "probe-setup.exe")
        self.assertEqual((found["program"], found["version"], found["publisher"]),
                         ("Probe Studio", "2.5.1", "Okula AG"))

    def test_broken_files_never_raise(self):
        for data in (b"", b"MZ", b"MZ" + bytes(100), pe_file()[:300], installerinfo.CFB_MAGIC + bytes(600),
                     b"PK\x03\x04kaputt", b"qres" + bytes(30), pe_file(overlay=b"qres" + b"\xff" * 40)):
            with self.subTest(data=data[:12]):
                for name in ("x.exe", "x.msi", "x.msix", "x.msu", "x.msp"):
                    self.assertIn("kind", software.detect_bytes(data, name))
        self.assertEqual(installerinfo.parse_version_resource(b"\xff" * 40), {})
        self.assertEqual(installerinfo.rcc_files(b"qres" + b"\0" * 16, {"config.xml"}), {})
        with installerinfo.Blob(b"MZ" + bytes(100)) as blob:
            self.assertEqual(installerinfo.msi_properties(blob), {})

    def test_msi_stream_names(self):
        self.assertEqual(installerinfo.msi_stream_name("!Property")[0], "\u4840")
        self.assertEqual(len(installerinfo.msi_stream_name("!_StringPool")), 1 + 6)     # 11 Zeichen → 6
        self.assertEqual(installerinfo.msi_stream_name("Ab"), chr(0x3800 + 10 + (37 << 6)))


class MsiTest(unittest.TestCase):
    PROPS = {"ProductName": "Probe Programm", "ProductVersion": "2.5.1", "Manufacturer": "Okula Probe AG, Zürich",
             "ALLUSERS": "1"}

    def test_properties_from_constructed_msi(self):
        data = msi(self.PROPS)
        with installerinfo.Blob(data) as blob:
            self.assertEqual(installerinfo.msi_properties(blob),
                             {k: v for k, v in self.PROPS.items() if k != "ALLUSERS"})
        found = software.detect_bytes(data, "probe.msi")
        self.assertEqual((found["kind"], found["args"], found["exit_codes"]),
                         ("msi", "/qn /norestart", [0, 1641, 3010]))
        self.assertEqual((found["program"], found["version"], found["publisher"]),
                         ("Probe Programm", "2.5.1", "Okula Probe AG, Zürich"))

    def test_big_stream_and_codepage(self):
        props = dict(self.PROPS, Description="x" * 5000)       # _StringData über 4096 Byte → normale Sektoren
        data = msi(props, codepage=1252)
        with installerinfo.Blob(data) as blob:
            p = installerinfo.msi_properties(blob, ("Manufacturer", "Description"))
        self.assertEqual((p["Manufacturer"], len(p["Description"])), ("Okula Probe AG, Zürich", 5000))

    def test_loaded_msi_name_version_publisher(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "quelle" / "probe_setup_x64.msi"
            src.parent.mkdir()
            src.write_bytes(msi(self.PROPS))
            e = software.load(Path(tmp) / "nas", src).entry
            self.assertEqual((e.program, e.version, e.publisher, e.status), ("Probe Programm", "2.5.1",
                                                                             "Okula Probe AG, Zürich", software.READY))
            self.assertEqual(json.loads((e.path / ".okula.json").read_text())["publisher"], "Okula Probe AG, Zürich")


class QtIfwTest(unittest.TestCase):
    def test_araneo_like(self):
        found = software.detect_bytes(qt_ifw(), "AraneoInstaller.exe")
        self.assertEqual(found["kind"], "qtifw")
        self.assertEqual(found["args"], 'install --root "C:\\Program Files\\Araneo" --accept-licenses '
                                        "--accept-messages --default-answer --confirm-command")
        self.assertEqual((found["program"], found["version"], found["publisher"], found["hint"]),
                         ("Araneo", "1.10.2", "Luminex Network Intelligence", ""))
        self.assertIn("4.6.1", found["note"])

    def test_framework_version_in_rdata(self):
        with mock.patch.object(software, "HEAD_BYTES", 256):     # Kennung nicht im Kopf, sondern in .rdata
            found = software.detect_bytes(qt_ifw(in_rdata=True), "AraneoInstaller.exe")
        self.assertEqual((found["kind"], bool(found["args"])), ("qtifw", True))

    def test_old_framework_and_unclear_target(self):
        old = software.detect_bytes(qt_ifw("3.2.2"), "x.exe")
        self.assertEqual((old["kind"], old["args"]), ("qtifw", ""))
        self.assertIn("vor 4.0", old["hint"])
        home = software.detect_bytes(qt_ifw(config=IFW_CONFIG.replace(b"@ApplicationsDirX64@", b"@HomeDir@")),
                                     "x.exe")
        self.assertEqual(home["args"], "")
        self.assertIn("@HomeDir@", home["hint"])

    def test_target_dirs(self):
        self.assertEqual(software.ifw_target("@ApplicationsDir@/Firma/App", is64=False),
                         "C:\\Program Files (x86)\\Firma\\App")
        self.assertEqual(software.ifw_target("@RootDir@/Tools/"), "C:\\Tools")
        self.assertEqual(software.ifw_target("@HomeDir@/App"), "")
        self.assertEqual(software.ifw_target("relativ/App"), "")

    def test_loaded_entry_and_redetect_respects_edited(self):
        """Araneo-Fall: Eintrag aus der Zeit vor Ä-043 → „Neu erkennen“; von Hand geändert → nur mit Rückfrage."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "nas"
            src = Path(tmp) / "quelle" / "AraneoInstaller.exe"
            src.parent.mkdir()
            src.write_bytes(qt_ifw())
            e = software.load(root, src).entry
            self.assertEqual((e.program, e.version, e.publisher, e.status), ("Araneo", "1.10.2",
                                                                             "Luminex Network Intelligence",
                                                                             software.READY))
            # Beschreibung wie vor Ä-043 (nicht erkannt)
            old = dict(e.meta, kind="", detected="", args="", program="AraneoInstaller", program_version="",
                       publisher="", hint="", detected_args="", exit_codes=[0, 3010])
            (e.path / ".okula.json").write_text(json.dumps(old))
            before = software.find(software.scan(root), e.name)
            self.assertEqual((before.status, before.hint), (software.MISSING, software.UNKNOWN_HINT))
            again = software.redetect(root, e.name)
            self.assertEqual((again.name, again.kind_label, again.program, again.version, again.publisher,
                              again.status, again.key, again.meta["edited"]),
                             (e.name, "Qt Installer Framework", "Araneo", "1.10.2", "Luminex Network Intelligence",
                              software.READY, e.key, False))
            self.assertEqual(again.loaded_from, str(src))
            # von Hand geändert → ohne Rückfrage nichts überschrieben
            software.update(root, e.name, args="install --root \"D:\\Araneo\" --confirm-command")
            with self.assertRaises(software.EditedError):
                software.redetect(root, e.name)
            self.assertIn("D:\\Araneo", software.find(software.scan(root), e.name).args)
            forced = software.redetect(root, e.name, overwrite_edited=True)
            self.assertIn("C:\\Program Files\\Araneo", forced.args)
            self.assertFalse(forced.meta["edited"])
            with self.assertRaises(software.SoftwareError):
                software.redetect(root, "gibtsnicht")


class NsisTest(unittest.TestCase):
    def test_electron_builder_gets_allusers(self):
        header = nsis_strings("DisplayVersion", "1.3.1", "Publisher", "Alteka Solutions", "\\app-64.7z",
                              "allusers", "currentuser")
        for solid in (False, True):
            with self.subTest(solid=solid):
                found = software.detect_bytes(nsis(header, solid_lzma=solid), "Kards-1.3.1-windows-x64.exe")
                self.assertEqual((found["kind"], found["args"]), ("electron", "/S /allusers"))
                self.assertEqual((found["version"], found["publisher"]), ("1.3.1", "Alteka Solutions"))

    def test_plain_nsis_values_checked(self):
        # Werte aus dem Skript nur, wenn plausibel: „NoModify“ ist kein Hersteller, „URLInfoAbout“ keine Version
        header = b"DisplayName\0WinDirStat 1.1.2\0DisplayVersion\0URLInfoAbout\0Publisher\0NoModify\0"
        found = software.detect_bytes(nsis(header), "windirstat1_1_2_setup.exe")
        self.assertEqual((found["kind"], found["args"]), ("nsis", "/S"))
        self.assertEqual((found["program"], found["version"], found["publisher"]), ("WinDirStat", "", ""))
        vi = software.detect_bytes(nsis(b"Publisher\0Andere GmbH\0", vi={"CompanyName": "Twoloox GmbH"}), "pb.exe")
        self.assertEqual(vi["publisher"], "Twoloox GmbH")          # Versionsinfo geht vor
        latin = software.detect_bytes(nsis(b"DisplayVersion\x0010.0.0-beta.128\x00Publisher\x00\xfd\x80\x00"),
                                      "pb.exe")
        self.assertEqual((latin["version"], latin["publisher"]), ("10.0.0-beta.128", ""))   # Variable → leer


class KindsTest(unittest.TestCase):
    """Probe-Dateien mit den Kennungen jedes Typs (Text im Programm, Manifest, Abschnitt, angehängte Daten)."""

    def detect(self, data: bytes, name: str = "setup.exe") -> dict:
        return software.detect_bytes(data, name)

    def test_marker_kinds(self):
        cases = {
            "advinst": pe_file(body="Caphyon Advanced Installer".encode("utf-16-le")),
            "installaware": pe_file(body=b"InstallAware Software"),
            "wise": pe_file(body=b"WiseMain"),
            "installbuilder": pe_file(resources={24: manifest("BitRock Installer")}),
            "setupfactory": pe_file(body=b"irsetup.exe Setup Factory"),
            "clickteam": pe_file(body=b"Clickteam Install Creator"),
            "smartinstall": pe_file(body=b"Smart Install Maker"),
            "actual": pe_file(body=b"Actual Installer"),
            "createinstall": pe_file(body=b"CreateInstall"),
            "ghost": pe_file(body=b"Ghost Installer"),
            "installshield": pe_file(body="InstallShield (R)".encode("utf-16-le")),
            "installscript": pe_file(body=b"InstData\\ISSetup.dll\0InstData\\setup.inx\0"),
            "wix": pe_file(sections=(".text", ".wixburn")),
            "msburn": pe_file(sections=(".text", ".wixburn"),
                              resources={16: version_resource({"CompanyName": "Microsoft Corporation"})}),
            "squirrel": pe_file(resources={16: version_resource({"SquirrelAwareVersion": "1"})}),
            "iexpress": pe_file(resources={16: version_resource({"OriginalFilename": "WEXTRACT.EXE .MUI"})}),
            "7zsfx": pe_file(overlay=b";!@Install@!UTF-8!\nTitle=\"Firefox\"\n"),
            "winrar": pe_file(overlay=b"Rar!\x1a\x07\x00" + bytes(50)),
            "inno": pe_file(resources={24: manifest("Inno Setup", "JR.Inno.Setup")}),
            "": pe_file(body=b"irgendein Programm"),
        }
        for kind, data in cases.items():
            with self.subTest(kind=kind):
                found = self.detect(data)
                self.assertEqual(found["kind"], kind)
                label, args, codes, hint = software.KINDS[kind]
                self.assertEqual((found["args"], found["exit_codes"]), (args, list(codes)))
                if args or kind == "squirrel":
                    self.assertEqual(found["hint"], "")
                else:                      # „Parameter fehlt“ immer mit Hinweis, was zu tun ist
                    self.assertTrue(found["hint"])

    def test_every_kind_has_label_and_either_args_or_hint(self):
        for kind, (label, args, codes, hint) in software.KINDS.items():
            with self.subTest(kind=kind):
                self.assertTrue(label)
                self.assertTrue(codes and 0 in codes)
                self.assertTrue(args or hint or kind == "squirrel")
                self.assertNotIn("\n", hint)

    def test_microsoft_burn_parameters(self):
        found = self.detect(pe_file(sections=(".text", ".wixburn"), resources={16: version_resource(
            {"CompanyName": "Microsoft Corporation", "ProductName": "Microsoft Visual C++ 2015-2022 Redistributable",
             "ProductVersion": "14.40.33810.0"})}), "VC_redist.x64.exe")
        self.assertEqual((found["args"], found["exit_codes"]), ("/install /quiet /norestart", [0, 1638, 1641, 3010]))
        self.assertEqual(found["program"], "Microsoft Visual C++ 2015-2022 Redistributable")

    def test_msu_msp_msix(self):
        msu = self.detect(b"MSCF" + bytes(60), "windows10.0-kb5034441-x64_abc.msu")
        self.assertEqual((msu["kind"], msu["args"], msu["exit_codes"], msu["program"], msu["version"]),
                         ("msu", "/quiet /norestart", [0, 3010, 2359302], "Windows-Update", "KB5034441"))
        msp = self.detect(installerinfo.CFB_MAGIC + bytes(600), "patch.msp")
        self.assertEqual((msp["kind"], msp["args"]), ("msp", "/qn /norestart"))
        pkg = self.detect(appx({"Name": "Okula.Probe", "Version": "1.2.3.0", "Publisher": "CN=Okula AG, C=CH"},
                               "Okula Probe", "Okula AG"), "probe.msix")
        self.assertEqual((pkg["kind"], pkg["args"], pkg["program"], pkg["version"], pkg["publisher"]),
                         ("msix", "-SkipLicense", "Okula Probe", "1.2.3.0", "Okula AG"))
        bundle = self.detect(appx({"Name": "Okula.Bundle", "Version": "2.0.0.0", "Publisher": "CN=Okula AG, C=CH"},
                                  bundle=True), "probe.msixbundle")
        self.assertEqual((bundle["program"], bundle["version"], bundle["publisher"]),
                         ("Okula.Bundle", "2.0.0.0", "Okula AG"))

    def test_program_names_without_setup(self):
        self.assertEqual(software.clean_program("AraneoInstaller"), "Araneo")
        self.assertEqual(software.clean_program("OBS Studio Installer"), "OBS Studio")
        self.assertEqual(software.clean_program("ChromeSetup"), "Chrome")
        self.assertEqual(software.clean_program("Setup"), "Setup")
        self.assertEqual(software.clean_program("Reinstall"), "Reinstall")
        found = self.detect(pe_file(resources={16: version_resource({"FileDescription": "Probe Tool Setup"})}))
        self.assertEqual(found["program"], "Probe Tool Setup")       # roh – beim Laden bereinigt
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "q" / "ProbeSetup.exe"
            src.parent.mkdir()
            src.write_bytes(pe_file(body=b"irgendwas", resources={16: version_resource(
                {"FileDescription": "Probe Tool Setup", "ProductVersion": "3.3.1"})}))
            e = software.load(Path(tmp) / "nas", src).entry
            self.assertEqual((e.program, e.version, e.status), ("Probe Tool", "3.3.1", software.MISSING))
            self.assertIn("unbekannt", e.note)                       # Hinweis in der Liste (Tooltip)
            software.update(Path(tmp) / "nas", e.name, args="/quiet")
            ready = software.find(software.scan(Path(tmp) / "nas"), e.name)
            self.assertEqual((ready.status, ready.hint), (software.READY, ""))   # Hinweis weg, sobald Parameter da

    def test_build_number_in_name_replaced_by_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "q" / "companion-satellite-x64-701-effd351.exe"
            src.parent.mkdir()
            src.write_bytes(nsis(nsis_strings("\\app-64.7z"),
                                 vi={"ProductName": "Companion Satellite", "ProductVersion": "3.3.1"}))
            e = software.load(Path(tmp) / "nas", src).entry
            self.assertEqual((e.program, e.version, e.kind, e.args), ("Companion Satellite", "3.3.1", "electron",
                                                                      "/S /allusers"))


class NewKindsScriptTest(unittest.TestCase):
    """MSIX, MSU und MSP: laden und im Installationsskript am Gerät."""

    def test_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, src = Path(tmp) / "nas", Path(tmp) / "q"
            src.mkdir()
            files = {"Probe App 1.2.msix": appx({"Name": "Okula.Probe", "Version": "1.2.0.0",
                                                 "Publisher": "CN=Okula AG"}, "Probe App", "Okula AG"),
                     "windows10.0-kb5034441-x64.msu": b"MSCF" + bytes(60),
                     "probe-patch-1.1.msp": installerinfo.CFB_MAGIC + bytes(600)}
            names = []
            for fname, data in files.items():
                (src / fname).write_bytes(data)
                names.append(software.load(root, src / fname).entry.name)
            entries = software.plan(root, names).entries
            self.assertEqual([software.script_kind(e) for e in entries], ["msix", "msu", "msp"])
            self.assertEqual([e.status for e in entries], [software.READY] * 3)
            s = software.build_script(entries, "PC-1", created=0)
            self.assertIn("Kind = 'msix'; Args = '-SkipLicense'; Ok = @(0)", s)
            self.assertIn("Kind = 'msu'; Args = '/quiet /norestart'; Ok = @(0, 3010, 2359302)", s)
            self.assertIn("Kind = 'msp'; Args = '/qn /norestart'; Ok = @(0, 1641, 3010)", s)
            self.assertIn("Add-AppxProvisionedPackage @provision", s)
            self.assertIn("$provision.SkipLicense = $true", s)
            self.assertIn("'System32\\wusa.exe'", s)
            self.assertIn("('/p \"{0}\" {1}' -f $file, $arguments)", s)
            self.assertEqual(s.count("{"), s.count("}"))
            self.assertEqual(s.count("("), s.count(")"))
            body = s[s.index("function Install-OkulaProgram"):s.index("function Install-Okula {")]
            # App-Paket in try (Fehler → FEHLER im Protokoll), Installer danach im finally gelöscht
            self.assertLess(body.index("try {"), body.index("Add-AppxProvisionedPackage"))
            self.assertLess(body.index("Add-AppxProvisionedPackage"), body.index("} finally {"))

    def test_inspect_accepts_new_extensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("a.msix", "a.APPXBUNDLE", "a.msu", "a.msp", "a.appx", "a.msixbundle"):
                p = Path(tmp) / name
                p.write_bytes(b"x")
                self.assertEqual(software.inspect(p).candidates, [name])
            (Path(tmp) / "a.zip").write_bytes(b"x")
            with self.assertRaisesRegex(software.SoftwareError, "kein Installer"):
                software.inspect(Path(tmp) / "a.zip")


def _software_ui():
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        from okula_recovery import software_ui
        return software_ui
    except (ImportError, ValueError):
        return None


def _gtk() -> bool:
    from tests.test_wintweaks import gtk_available
    return gtk_available()


@unittest.skipUnless(_software_ui(), "braucht PyGObject")
class DetailTest(unittest.TestCase):
    def test_detail_line_markup_and_hint(self):
        from gi.repository import Pango
        ui = _software_ui()
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "q" / "Tool <1> & Co.exe"
            src.parent.mkdir()
            src.write_bytes(pe_file(body=b"InstData\\ISSetup.dll setup.inx", resources={16: version_resource(
                {"ProductName": "Epson <Probe>", "CompanyName": "SEIKO EPSON & Co"})}))
            e = software.load(Path(tmp) / "nas", src).entry
            text = ui.detail_markup(e)
            Pango.parse_markup(text, -1, "\0")                       # gültiges Markup trotz < > &
            self.assertIn("InstallShield (InstallScript)", text)
            self.assertIn("SEIKO EPSON &amp; Co", text)
            self.assertIn("Was tun:", text)
            self.assertIn("setup.iss", text)


@unittest.skipUnless(_gtk(), "braucht GTK mit Bildschirm")
class RedetectWindowTest(unittest.TestCase):
    def test_redetect_button_asks_only_when_edited(self):
        import time
        from gi.repository import GLib
        ui = _software_ui()

        def wait(cond):
            for _ in range(1000):
                if cond():
                    return
                GLib.MainContext.default().iteration(False)
                time.sleep(0.01)
            self.fail("Zeitüberschreitung")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "nas"
            src = Path(tmp) / "q" / "AraneoInstaller.exe"
            src.parent.mkdir()
            src.write_bytes(qt_ifw())
            e = software.load(root, src).entry
            old = dict(e.meta, kind="", detected="", args="", program="AraneoInstaller", publisher="")
            (e.path / ".okula.json").write_text(json.dumps(old))
            win = ui.SoftwareLibraryWindow(None, str(root))
            wait(lambda: len(win.store) == 1 and "Einträge" in win.status.get_text())
            win._select(e.name)
            self.assertIn("Was tun:", win.detail.get_label())      # „Parameter fehlt“ mit Hinweis
            asked = []
            with mock.patch.object(ui, "confirm", lambda *a, **k: asked.append(a) or True):
                win.on_redetect()
                wait(lambda: any(r[win.C_PROG] == "Araneo" for r in win.store))
                self.assertEqual(asked, [])                          # nicht von Hand geändert → keine Rückfrage
                row = next(r for r in win.store if r[win.C_NAME] == e.name)
                self.assertEqual((row[win.C_PUB], row[win.C_TYPE], row[win.C_STATUS]),
                                 ("Luminex Network Intelligence", "Qt Installer Framework", software.READY))
                self.assertIn("neu erkannt", win.status.get_text())
                software.update(root, e.name, args="/anders")
                win.reload(select=e.name)
                wait(lambda: any(r[win.C_ARGS] == "/anders" for r in win.store))
                win._select(e.name)
                win.on_redetect()
                wait(lambda: any(r[win.C_ARGS].startswith("install --root") for r in win.store))
                self.assertEqual(len(asked), 1)                      # von Hand geändert → Rückfrage
            win.destroy()


if __name__ == "__main__":
    unittest.main()
