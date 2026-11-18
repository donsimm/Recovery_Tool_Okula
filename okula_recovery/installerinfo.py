"""Angaben aus Installer-Dateien lesen, ohne sie auszuführen (Ä-043) – nur Lesen, ohne GTK, ohne neue Abhängigkeit.

Leser für die Erkennung in software.py:
- Blob: Teile einer Datei (bzw. von Bytes) lesen, ohne alles zu laden – Installer sind oft mehrere 100 MB gross.
- PE (Windows-Programm, Microsoft „PE Format“): Abschnitte, Datenverzeichnisse, Ende des Abbilds (dahinter hängen
  NSIS, Qt IFW, SFX usw. ihre Daten an = „Overlay“), Ressourcen: Versionsinfo VS_VERSIONINFO (RT_VERSION 16) und
  Manifest (RT_MANIFEST 24).
- Qt-Ressourcen (rcc, Kopf „qres“): Qt Installer Framework hängt config.xml und Updates.xml so an.
- NSIS-Kopf (deflate oder LZMA): Texte des Installationsskripts (electron-builder, Registry-Werte der Deinstallation).
- Compound File Binary (CFB/OLE, [MS-CFB]) mit MSI-Tabellen (String-Pool, Tabelle Property).
- MSIX/APPX (ZIP): AppxManifest.xml bzw. AppxMetadata/AppxBundleManifest.xml.
Alle Leser sind gegen kaputte Dateien abgesichert: Fehler → leeres Ergebnis, nie eine Ausnahme nach aussen.
"""

from __future__ import annotations

import io
import lzma
import os
import re
import struct
import zipfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path

MAX_RESOURCE = 1 << 20          # Versionsinfo/Manifest: mehr ist nie nötig
MAX_STREAM = 16 << 20           # MSI-Tabellen, String-Pool
MAX_NSIS_OUT = 4 << 20          # entpackter NSIS-Kopf (Texte des Skripts)
MAX_SECTION_SCAN = 64 << 20     # Abschnitt nach einer Kennung durchsuchen (z. B. Qt IFW in .rdata)


class Blob:
    """Lesezugriff auf eine Datei oder auf Bytes (Tests) – immer nur Teile."""

    def __init__(self, source: bytes | bytearray | str | Path):
        self._file = None
        if isinstance(source, (bytes, bytearray)):
            self._data = bytes(source)
            self.size = len(self._data)
        else:
            self._data = None
            self._file = open(source, "rb")
            self.size = os.fstat(self._file.fileno()).st_size

    def read(self, offset: int, length: int) -> bytes:
        if offset < 0 or length <= 0 or offset >= self.size:
            return b""
        if self._data is not None:
            return self._data[offset:offset + length]
        self._file.seek(offset)
        return self._file.read(length)

    def fileobj(self):
        """Datei-Objekt für zipfile (MSIX)."""
        if self._data is not None:
            return io.BytesIO(self._data)
        self._file.seek(0)
        return self._file

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        self.close()


def _u16(b: bytes, off: int) -> int:
    return struct.unpack_from("<H", b, off)[0]


def _u32(b: bytes, off: int) -> int:
    return struct.unpack_from("<I", b, off)[0]


# ---------- PE ----------

@dataclass
class Section:
    name: str
    va: int
    vsize: int
    raw: int
    rawsize: int


@dataclass
class PE:
    is64: bool = False
    sections: list[Section] = field(default_factory=list)
    dirs: list[tuple[int, int]] = field(default_factory=list)   # Datenverzeichnisse (RVA bzw. Position, Grösse)
    image_end: int = 0                                          # Ende der Abschnitte in der Datei = Beginn Overlay

    @property
    def names(self) -> list[str]:
        return [s.name for s in self.sections]

    def dir(self, index: int) -> tuple[int, int]:
        return self.dirs[index] if index < len(self.dirs) else (0, 0)

    def rva_to_offset(self, rva: int) -> int | None:
        for s in self.sections:
            if s.va <= rva < s.va + max(s.vsize, s.rawsize) and rva - s.va < s.rawsize:
                return s.raw + rva - s.va
        return None

    def overlay_end(self, size: int) -> int:
        """Ende der angehängten Daten – ohne Authenticode-Signatur (Verzeichnis 4 = Dateiposition)."""
        off, length = self.dir(4)
        return off if off >= self.image_end and off + length <= size and off else size


def pe_info(blob: Blob) -> PE | None:
    """Kopf einer Windows-Programmdatei (None, wenn keine)."""
    try:
        head = blob.read(0, 64)
        if len(head) < 64 or head[:2] != b"MZ":
            return None
        pe_off = _u32(head, 0x3C)
        hdr = blob.read(pe_off, 24 + 0x100 + 40 * 96)
        if len(hdr) < 24 or hdr[:4] != b"PE\0\0":
            return None
        count, opt_size = _u16(hdr, 6), _u16(hdr, 20)
        info = PE()
        if opt_size >= 2:
            magic = _u16(hdr, 24)
            info.is64 = magic == 0x20B
            num_at, dirs_at = (24 + 108, 24 + 112) if info.is64 else (24 + 92, 24 + 96)
            if opt_size >= dirs_at - 24 and len(hdr) >= dirs_at:
                n = min(_u32(hdr, num_at), 16, (24 + opt_size - dirs_at) // 8)
                info.dirs = [struct.unpack_from("<II", hdr, dirs_at + 8 * i) for i in range(max(n, 0))]
        start = 24 + opt_size
        for i in range(min(count, 96)):
            off = start + 40 * i
            if off + 40 > len(hdr):
                break
            name = hdr[off:off + 8].rstrip(b"\0").decode("latin-1")
            vsize, va, rawsize, raw = struct.unpack_from("<IIII", hdr, off + 8)
            info.sections.append(Section(name, va, vsize, raw, rawsize))
            if rawsize:
                info.image_end = max(info.image_end, raw + rawsize)
        info.image_end = min(info.image_end, blob.size)
        return info
    except (struct.error, OSError):
        return None


def resources(blob: Blob, pe: PE, rtype: int, limit: int = 8) -> list[bytes]:
    """Daten aller Ressourcen eines Typs (z. B. 16 = Versionsinfo, 24 = Manifest), höchstens limit Stück."""
    rva, size = pe.dir(2)
    base = pe.rva_to_offset(rva) if rva else None
    if base is None or not size:
        return []
    out: list[bytes] = []

    def entries(off: int) -> list[tuple[int, int]]:
        head = blob.read(base + off, 16)
        if len(head) < 16:
            return []
        n = min(_u16(head, 12) + _u16(head, 14), 4096)
        raw = blob.read(base + off + 16, 8 * n)
        return [struct.unpack_from("<II", raw, 8 * i) for i in range(len(raw) // 8)]

    def leaf(off: int, depth: int) -> None:
        if len(out) >= limit or depth > 3:
            return
        for _name, target in entries(off):
            if target & 0x80000000:
                leaf(target & 0x7FFFFFFF, depth + 1)
            else:
                data_entry = blob.read(base + target, 16)
                if len(data_entry) < 8:
                    continue
                d_rva, d_size = struct.unpack_from("<II", data_entry, 0)
                pos = pe.rva_to_offset(d_rva)
                if pos is not None and 0 < d_size <= MAX_RESOURCE:
                    out.append(blob.read(pos, d_size))
            if len(out) >= limit:
                return

    try:
        for name, target in entries(0):
            if name == rtype and target & 0x80000000:
                leaf(target & 0x7FFFFFFF, 1)
    except (struct.error, OSError):
        pass
    return out


def _align4(n: int) -> int:
    return (n + 3) & ~3


def parse_version_resource(data: bytes) -> dict[str, str]:
    """VS_VERSIONINFO → Texte aus StringFileInfo (erste Sprache gewinnt) und die Zahlen aus VS_FIXEDFILEINFO
    („#FileVersion“, „#ProductVersion“). Aufbau je Knoten: wLength, wValueLength, wType, szKey (UTF-16 mit 0),
    Auffüllen auf 32 Bit, Wert, Auffüllen, Kinder (Microsoft Learn „VS_VERSIONINFO“, „String“, „StringTable“)."""
    out: dict[str, str] = {}

    def node(off: int, end: int, depth: int) -> int:
        if off + 6 > end or depth > 4:
            return end
        length, vlen, typ = struct.unpack_from("<HHH", data, off)
        stop = min(off + length, end) if length >= 6 else end
        k = off + 6
        while k + 1 < stop and data[k:k + 2] != b"\0\0":
            k += 2
        key = data[off + 6:k].decode("utf-16-le", errors="replace")
        pos = _align4(k + 2)
        if depth == 0 and key == "VS_VERSION_INFO" and vlen >= 52 and pos + 52 <= stop:
            sig, _sv, fms, fls, pms, pls = struct.unpack_from("<6I", data, pos)
            if sig == 0xFEEF04BD:
                out.setdefault("#FileVersion", f"{fms >> 16}.{fms & 0xFFFF}.{fls >> 16}.{fls & 0xFFFF}")
                out.setdefault("#ProductVersion", f"{pms >> 16}.{pms & 0xFFFF}.{pls >> 16}.{pls & 0xFFFF}")
        if depth == 3:                       # String: Wert bis zur ersten 0 (wValueLength ist nicht verlässlich)
            raw = data[pos:stop]
            text = raw[:len(raw) // 2 * 2].decode("utf-16-le", errors="replace").split("\0", 1)[0].strip()
            if key and text and text.isprintable():
                out.setdefault(key, text)
            return stop
        pos = _align4(pos + (vlen * 2 if typ == 1 else vlen))
        if depth == 1 and key != "StringFileInfo":
            return stop
        while pos + 6 <= stop:
            nxt = node(pos, stop, depth + 1)
            if nxt <= pos:
                break
            pos = _align4(nxt)
        return stop

    try:
        node(0, len(data), 0)
    except (struct.error, IndexError):
        pass
    return out


def manifest_text(blob: Blob, pe: PE) -> str:
    data = resources(blob, pe, 24, limit=2)
    return "\n".join(d.decode("utf-8", errors="replace") for d in data)


def section_bytes(blob: Blob, pe: PE, name: str) -> bytes:
    for s in pe.sections:
        if s.name == name and 0 < s.rawsize <= MAX_SECTION_SCAN:
            return blob.read(s.raw, s.rawsize)
    return b""


# ---------- Qt-Ressourcen (rcc) ----------

def rcc_files(data: bytes, wanted: set[str]) -> dict[str, bytes]:
    """Dateien mit diesen Namen aus einer Qt-Ressourcensammlung (Kopf „qres“, Version 1–3; zlib-gepackte Einträge
    werden entpackt, zstd nicht). Aufbau laut Qt-Quelltext rcc.cpp („Quelle nicht abgerufen“, aus dem Gedächtnis,
    an AraneoInstaller.exe geprüft)."""
    out: dict[str, bytes] = {}
    if data[:4] != b"qres" or len(data) < 20:
        return out
    try:
        version, tree, data_off, names = struct.unpack_from(">IIII", data, 4)
        node_size = 14 if version == 1 else 22

        def name_at(off: int) -> str:
            ln = struct.unpack_from(">H", data, names + off)[0]
            return data[names + off + 6:names + off + 6 + 2 * ln].decode("utf-16-be", errors="replace")

        seen = 0
        stack = [(0, 0)]
        while stack and seen < 20000:
            index, depth = stack.pop()
            seen += 1
            base = tree + index * node_size
            name_off, flags = struct.unpack_from(">IH", data, base)
            if flags & 2:
                if depth < 16:
                    count, first = struct.unpack_from(">II", data, base + 6)
                    stack += [(first + i, depth + 1) for i in range(min(count, 5000))]
                continue
            if index == 0:
                continue
            name = name_at(name_off)
            if name not in wanted or name in out:
                continue
            doff = struct.unpack_from(">I", data, base + 10)[0]
            size = struct.unpack_from(">I", data, data_off + doff)[0]
            content = data[data_off + doff + 4:data_off + doff + 4 + size]
            if flags & 4:
                continue                         # zstd – ohne Zusatzmodul nicht lesbar
            if flags & 1:
                content = zlib.decompressobj().decompress(content[4:], MAX_RESOURCE)
            out[name] = content
    except (struct.error, zlib.error, IndexError):
        pass
    return out


def xml_tags(text: str, *tags: str) -> dict[str, str]:
    """Einfache Tags <Tag>Wert</Tag> (erster Treffer) – ohne XML-Parser (keine Entitäten, keine Gefahr)."""
    out = {}
    for tag in tags:
        m = re.search(rf"<{tag}>\s*([^<]{{1,300}}?)\s*</{tag}>", text)
        if m:
            out[tag] = m.group(1).replace("&amp;", "&").strip()
    return out


# ---------- NSIS ----------

NSIS_SIG = b"\xef\xbe\xad\xdeNullsoftInst"


def _lzma_raw(raw: bytes, limit: int) -> bytes:
    props = raw[0]
    if props >= 9 * 5 * 5:
        return b""
    lc, props = props % 9, props // 9
    lp, pb = props % 5, props // 5
    dict_size = _u32(raw, 1)
    dec = lzma.LZMADecompressor(lzma.FORMAT_RAW, filters=[{"id": lzma.FILTER_LZMA1, "dict_size": max(dict_size, 4096),
                                                            "lc": lc, "lp": lp, "pb": pb}])
    return dec.decompress(raw[5:], max_length=limit)


def nsis_header(blob: Blob, pe: PE | None, head: bytes) -> bytes:
    """Entpackter Kopf eines NSIS-Installers (Skript mit allen Texten), leer bei Fehler. Kopf („firstheader“):
    Flags, 0xDEADBEEF, „NullsoftInst“, Länge Kopf, Länge Daten; danach deflate oder LZMA, als Ganzes („solid“) oder
    je Block mit Länge (Bit 31 = gepackt). NSIS-Quelltext fileform.h („Quelle nicht abgerufen“, an echten
    Installern geprüft)."""
    start = -1
    if pe is not None and pe.image_end:
        window = blob.read(pe.image_end, 1 << 16)
        i = window.find(NSIS_SIG)
        if i >= 0:
            start = pe.image_end + i
    if start < 0:
        i = head.find(NSIS_SIG)
        if i < 0:
            return b""
        start = i
    try:
        hdr = blob.read(start + 16, 8)
        head_len = _u32(hdr, 0)
        body = blob.read(start + 24, 8 << 20)
        limit = min(max(head_len, 0) + 4, MAX_NSIS_OUT)
        if body[:1] == b"\x5d":                                     # LZMA als Ganzes
            return _lzma_raw(body, limit)
        n = _u32(body, 0)
        if n & 0x80000000:                                          # gepackter Block
            blk = body[4:4 + (n & 0x7FFFFFFF)]
            if blk[:1] == b"\x5d":
                return _lzma_raw(blk, limit)
            return zlib.decompressobj(-15).decompress(blk, limit)
        try:                                                        # deflate als Ganzes
            return zlib.decompressobj(-15).decompress(body, limit)
        except zlib.error:
            return body[4:4 + min(n, limit)]                        # ungepackt
    except (lzma.LZMAError, zlib.error, struct.error, EOFError, OSError):
        return b""


def nsis_value(header: bytes, name: str) -> str:
    """Wert nach einem Registry-Namen im NSIS-Kopf („DisplayVersion“ → „10.0.0“), nur wenn fester Text
    (keine Variablen). NSIS legt Texte der Reihe nach ab – deshalb nur ein Vorschlag."""
    for enc, step in (("utf-16-le", 2), ("latin-1", 1)):
        nul = b"\0" * step
        i = header.find(name.encode(enc) + nul)
        if i < 0:
            continue
        j = k = i + len(name.encode(enc)) + step
        while k < len(header) and k - j < 400 and header[k:k + step] != nul:
            k += step
        raw = header[j:k]
        if enc == "latin-1" and any(b >= 0xFC for b in raw):          # NSIS-Codes (Variable, Sprache …)
            return ""
        text = raw.decode(enc, errors="replace").strip()
        return text if text and text.isprintable() and "$" not in text and len(text) <= 120 else ""
    return ""


def has_text(data: bytes, *texts: str) -> bool:
    """Text als ASCII oder UTF-16 enthalten?"""
    return any(t.encode() in data or t.encode("utf-16-le") in data for t in texts)


# ---------- Compound File (MSI, MSP) ----------

CFB_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_END = 0xFFFFFFFA                # ab hier: Sonderwerte (Kettenende, frei, FAT, DIFAT)


class Cfb:
    """Compound File Binary ([MS-CFB], „Quelle nicht abgerufen“, aus dem Gedächtnis; an echten MSI geprüft)."""

    def __init__(self, blob: Blob):
        h = blob.read(0, 512)
        if len(h) < 512 or h[:8] != CFB_MAGIC:
            raise ValueError("keine Compound-Datei")
        self.blob = blob
        self.ssize = 1 << _u16(h, 0x1E)
        self.msize = 1 << _u16(h, 0x20)
        if self.ssize not in (512, 4096) or self.msize != 64:
            raise ValueError("unbekannte Sektorgrösse")
        nfat, dir_start, self.cutoff = _u32(h, 0x2C), _u32(h, 0x30), _u32(h, 0x38)
        minifat_start, difat_start, ndifat = _u32(h, 0x3C), _u32(h, 0x44), _u32(h, 0x48)
        difat = list(struct.unpack_from("<109I", h, 0x4C))
        sec, n = difat_start, 0
        per = self.ssize // 4
        while sec < _END and n < min(ndifat, 4096):
            vals = struct.unpack(f"<{per}I", self._sector(sec).ljust(self.ssize, b"\xff"))
            difat += vals[:-1]
            sec, n = vals[-1], n + 1
        fat = bytearray()
        for s in difat[:min(nfat, 1 << 17)]:
            if s < _END:
                fat += self._sector(s)
        self.fat = struct.unpack(f"<{len(fat) // 4}I", bytes(fat[:len(fat) // 4 * 4]))
        dir_data = self._chain(dir_start, 1 << 22)
        self.entries = []
        for off in range(0, len(dir_data) - 127, 128):
            e = dir_data[off:off + 128]
            nlen = min(_u16(e, 64), 64)
            name = e[:max(nlen - 2, 0)].decode("utf-16-le", errors="replace")
            size = struct.unpack_from("<Q", e, 120)[0]
            if self.ssize == 512:
                size &= 0xFFFFFFFF
            self.entries.append((name, e[66], _u32(e, 116), size))
        root = self.entries[0] if self.entries else ("", 0, _END, 0)
        self.mini = self._chain(root[2], min(root[3], 1 << 26))
        minifat = self._chain(minifat_start, 1 << 22)
        self.minifat = struct.unpack(f"<{len(minifat) // 4}I", minifat[:len(minifat) // 4 * 4])

    def _sector(self, s: int) -> bytes:
        return self.blob.read((s + 1) * self.ssize, self.ssize)

    def _chain(self, start: int, limit: int) -> bytes:
        out, s, n = bytearray(), start, 0
        while s < _END and len(out) < limit and n < 1 << 20:
            out += self._sector(s)
            s = self.fat[s] if s < len(self.fat) else _END
            n += 1
        return bytes(out[:limit])

    def _mini_chain(self, start: int, size: int) -> bytes:
        out, s, n = bytearray(), start, 0
        while s < _END and len(out) < size and n < 1 << 20:
            out += self.mini[s * self.msize:(s + 1) * self.msize]
            s = self.minifat[s] if s < len(self.minifat) else _END
            n += 1
        return bytes(out[:size])

    def names(self) -> list[str]:
        return [e[0] for e in self.entries if e[1] == 2]

    def stream(self, name: str, limit: int = MAX_STREAM) -> bytes:
        for ename, etype, start, size in self.entries:
            if etype == 2 and ename == name:
                if size > limit:
                    return b""
                if size < self.cutoff:
                    return self._mini_chain(start, size)
                return self._chain(start, size)
        return b""


_MSI_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz._"


def msi_stream_name(name: str) -> str:
    """Name eines Datenstroms in der MSI-Kodierung: „Property“ als Tabelle → „\\u4840“ + je zwei Zeichen in einem
    (0x3800 + a + 64·b), Einzelzeichen 0x4800 + a (Wine msi/table.c, „Quelle nicht abgerufen“)."""
    out = []
    plain = name.lstrip("!")
    if name.startswith("!"):
        out.append("䡀")
    i = 0
    while i < len(plain):
        a = _MSI_CHARS.find(plain[i])
        if a < 0:
            out.append(plain[i])
            i += 1
            continue
        b = _MSI_CHARS.find(plain[i + 1]) if i + 1 < len(plain) else -1
        if b >= 0:
            out.append(chr(0x3800 + a + (b << 6)))
            i += 2
        else:
            out.append(chr(0x4800 + a))
            i += 1
    return "".join(out)


def msi_properties(blob: Blob, wanted: tuple[str, ...] = ("ProductName", "ProductVersion", "Manufacturer")) -> dict:
    """Werte aus der MSI-Tabelle Property. String-Pool: Kopf (Codepage, Bit 15 = 3-Byte-Verweise), danach je
    String Länge und Anzahl Verweise; Strings hintereinander in _StringData; Tabellen spaltenweise (Wine msi/string.c,
    „Quelle nicht abgerufen“, an echten MSI geprüft). Leer, wenn nicht lesbar."""
    try:
        cfb = Cfb(blob)
        pool = cfb.stream(msi_stream_name("!_StringPool"))
        sdata = cfb.stream(msi_stream_name("!_StringData"))
        prop = cfb.stream(msi_stream_name("!Property"))
        if len(pool) < 4 or not prop:
            return {}
        cp, flags = struct.unpack_from("<HH", pool, 0)
        refsize = 3 if flags & 0x8000 else 2
        codepage = cp | ((flags & 0x7FFF) << 16)
        enc = "utf-8" if codepage == 65001 else f"cp{codepage}" if codepage else "cp1252"
        try:
            "".encode(enc)
        except LookupError:
            enc = "cp1252"
        strings: dict[int, str] = {}
        count = len(pool) // 4
        i, sid, off = 1, 1, 0
        while i < count:
            ln, refs = struct.unpack_from("<HH", pool, i * 4)
            if ln == 0 and refs == 0:
                i, sid = i + 1, sid + 1
                continue
            if ln == 0:                                   # über 64 kB: Länge im nächsten Eintrag
                if i + 1 >= count:
                    break
                lo, hi = struct.unpack_from("<HH", pool, (i + 1) * 4)
                ln, i = (hi << 16) | lo, i + 2
            else:
                i += 1
            strings[sid] = sdata[off:off + ln].decode(enc, errors="replace")
            off, sid = off + ln, sid + 1
        rows = len(prop) // (2 * refsize)

        def ref(pos: int) -> int:
            return int.from_bytes(prop[pos:pos + refsize], "little")

        out = {}
        for r in range(rows):
            key = strings.get(ref(r * refsize), "")
            if key in wanted and key not in out:
                out[key] = strings.get(ref((rows + r) * refsize), "").strip()
        return out
    except (ValueError, struct.error, IndexError, OSError):
        return {}


# ---------- MSIX / APPX ----------

def appx_manifest(blob: Blob) -> dict[str, str]:
    """Name, Version, Hersteller aus einem App-Paket (.msix/.appx) bzw. Bündel (.msixbundle/.appxbundle):
    Identity Name/Version/Publisher (CN=…), Properties DisplayName/PublisherDisplayName (Microsoft Learn „Package
    manifest schema reference“, „Quelle nicht abgerufen“). Leer, wenn kein lesbares Paket."""
    try:
        with zipfile.ZipFile(blob.fileobj()) as z:
            names = set(z.namelist())
            bundle = "AppxMetadata/AppxBundleManifest.xml" in names
            member = "AppxMetadata/AppxBundleManifest.xml" if bundle else "AppxManifest.xml"
            if member not in names or z.getinfo(member).file_size > MAX_RESOURCE:
                return {}
            text = z.read(member).decode("utf-8", errors="replace")
    except (zipfile.BadZipFile, OSError, KeyError, ValueError, EOFError):
        return {}
    out = {"bundle": "1" if bundle else ""}
    m = re.search(r"<(?:\w+:)?Identity\b([^>]*)>", text)
    if m:
        for attr in ("Name", "Version", "Publisher"):
            a = re.search(rf'\b{attr}="([^"]*)"', m.group(1))
            if a:
                out[attr] = a.group(1)
    for tag in ("DisplayName", "PublisherDisplayName"):
        t = re.search(rf"<(?:\w+:)?{tag}>([^<]{{1,200}})</", text)
        if t and not t.group(1).startswith("ms-resource:"):
            out[tag] = t.group(1).strip()
    return out


def publisher_cn(publisher: str) -> str:
    """„CN=Contoso Ltd, O=Contoso, C=CH“ → „Contoso Ltd“."""
    m = re.search(r"(?:^|,\s*)(?:O|CN)=(\"[^\"]+\"|[^,]+)", publisher)
    return m.group(1).strip('" ') if m else publisher
