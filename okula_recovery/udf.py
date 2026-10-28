"""Schlanker UDF-Leser (ECMA-167 / OSTA UDF) für ISO-Dateien – ohne Einhängen, ohne root.

Windows-ISOs tragen ihre Dateien nur im UDF-Dateisystem (der ISO9660-Teil enthält bloss
eine README). Gelesen werden Verzeichnisse und Dateien mit beliebigem Zugriff (seek), damit
z. B. die XML-Beschreibung am Ende einer 5 GB grossen install.wim direkt gelesen werden kann.

Unterstützt: Partitionskarten Typ 1, File Entry und Extended File Entry, short_ad/long_ad
und eingebettete Daten. Nicht unterstützt: Metadaten-Partition (UDF 2.50+ mit Typ-2-Karte).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import BinaryIO, Iterator

SECTOR = 2048

TAG_AVDP, TAG_PD, TAG_LVD, TAG_TD = 2, 5, 6, 8
TAG_FSD, TAG_FID, TAG_FE, TAG_EFE = 256, 257, 261, 266


class UdfError(Exception):
    pass


@dataclass
class Entry:
    name: str
    is_dir: bool
    size: int
    extents: list[tuple[int, int]] = field(default_factory=list)  # (Byte-Offset im ISO, Länge); Offset -1 = Nullen
    inline: bytes | None = None                                    # eingebettete Daten (kleine Dateien)


def _tag(data: bytes, expected: int | None = None) -> int:
    if len(data) < 16:
        raise UdfError("Deskriptor zu kurz")
    ident = struct.unpack_from("<H", data, 0)[0]
    if sum(data[0:4]) + sum(data[5:16]) & 0xFF != data[4]:
        raise UdfError(f"Prüfsumme des Deskriptors {ident} falsch")
    if expected is not None and ident != expected:
        raise UdfError(f"Deskriptor {expected} erwartet, {ident} gefunden")
    return ident


def _dstring(raw: bytes) -> str:
    if not raw:
        return ""
    comp, body = raw[0], raw[1:]
    if comp == 8:
        return body.decode("latin-1")
    if comp == 16:
        return body.decode("utf-16-be", errors="replace")
    raise UdfError(f"Unbekannte Zeichenkodierung {comp}")


class UdfImage:
    def __init__(self, fh: BinaryIO):
        self.fh = fh
        self.partitions: dict[int, int] = {}   # Partitionsnummer → Startsektor
        self.maps: list[int] = []              # Partitionsreferenz → Partitionsnummer
        self.block = SECTOR
        avdp = self._sector(256)
        _tag(avdp, TAG_AVDP)
        length, location = struct.unpack_from("<II", avdp, 16)
        fsd_ad = None
        for i in range(max(1, length // SECTOR)):
            d = self._sector(location + i)
            ident = _tag(d)
            if ident == TAG_PD:
                number = struct.unpack_from("<H", d, 22)[0]
                self.partitions[number] = struct.unpack_from("<I", d, 188)[0]
            elif ident == TAG_LVD:
                self.block = struct.unpack_from("<I", d, 212)[0]
                fsd_ad = d[248:264]
                count = struct.unpack_from("<I", d, 268)[0]
                pos = 440
                for _ in range(count):
                    kind, size = d[pos], d[pos + 1]
                    if kind != 1:
                        raise UdfError("UDF mit Metadaten-Partition wird nicht unterstützt")
                    self.maps.append(struct.unpack_from("<H", d, pos + 4)[0])
                    pos += size
            elif ident == TAG_TD:
                break
        if fsd_ad is None or not self.partitions or not self.maps or self.block != SECTOR:
            raise UdfError("Kein gültiges UDF-Dateisystem")
        _length, lbn, ref = struct.unpack_from("<IIH", fsd_ad, 0)
        fsd = self._read(self._pos(ref, lbn), SECTOR)
        _tag(fsd, TAG_FSD)
        root_len, root_lbn, root_ref = struct.unpack_from("<IIH", fsd, 400)
        self.root = self._entry("", root_ref, root_lbn)

    @classmethod
    def open(cls, path: str) -> "UdfImage":
        fh = open(path, "rb")
        try:
            return cls(fh)
        except BaseException:
            fh.close()
            raise

    def close(self) -> None:
        self.fh.close()

    def __enter__(self) -> "UdfImage":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    # ---------- Grundlagen ----------

    def _read(self, offset: int, size: int) -> bytes:
        self.fh.seek(offset)
        data = self.fh.read(size)
        if len(data) < size:
            raise UdfError("ISO ist abgeschnitten")
        return data

    def _sector(self, n: int) -> bytes:
        return self._read(n * SECTOR, SECTOR)

    def _pos(self, ref: int, lbn: int) -> int:
        try:
            start = self.partitions[self.maps[ref]]
        except (IndexError, KeyError):
            raise UdfError(f"Unbekannte Partitionsreferenz {ref}") from None
        return (start + lbn) * SECTOR

    def _entry(self, name: str, ref: int, lbn: int) -> Entry:
        fe = self._read(self._pos(ref, lbn), SECTOR)
        ident = _tag(fe)
        if ident == TAG_FE:
            l_ea, l_ad = struct.unpack_from("<II", fe, 168)
            start = 176 + l_ea
        elif ident == TAG_EFE:
            l_ea, l_ad = struct.unpack_from("<II", fe, 208)
            start = 216 + l_ea
        else:
            raise UdfError(f"File Entry erwartet, Deskriptor {ident} gefunden")
        file_type = fe[27]
        flags = struct.unpack_from("<H", fe, 34)[0] & 7
        size = struct.unpack_from("<Q", fe, 56)[0]
        ads = fe[start:start + l_ad]
        entry = Entry(name, file_type == 4, size)
        if flags == 3:
            entry.inline = ads[:size]
            return entry
        step = {0: 8, 1: 16}.get(flags)
        if step is None:
            raise UdfError("Erweiterte Allocation Descriptors werden nicht unterstützt")
        remaining = size
        for pos in range(0, len(ads) - step + 1, step):
            raw_len, ad_lbn = struct.unpack_from("<II", ads, pos)
            ad_ref = struct.unpack_from("<H", ads, pos + 8)[0] if step == 16 else ref
            length, kind = raw_len & 0x3FFFFFFF, raw_len >> 30
            if length == 0 or remaining <= 0:
                break
            if kind == 3:
                raise UdfError("Fortgesetzte Allocation Descriptors werden nicht unterstützt")
            length = min(length, remaining)
            entry.extents.append((self._pos(ad_ref, ad_lbn) if kind == 0 else -1, length))
            remaining -= length
        return entry

    # ---------- Verzeichnisse und Dateien ----------

    def listdir(self, d: Entry) -> list[Entry]:
        if not d.is_dir:
            raise UdfError(f"{d.name} ist kein Verzeichnis")
        data = self.read(d)
        result, pos = [], 0
        while pos + 38 <= len(data):
            ident = struct.unpack_from("<H", data, pos)[0]
            if ident != TAG_FID:
                break
            chars, l_fi = data[pos + 18], data[pos + 19]
            _icb_len, icb_lbn, icb_ref = struct.unpack_from("<IIH", data, pos + 20)
            l_iu = struct.unpack_from("<H", data, pos + 36)[0]
            name_raw = data[pos + 38 + l_iu:pos + 38 + l_iu + l_fi]
            pos += (38 + l_iu + l_fi + 3) & ~3
            if chars & 0x0C:  # gelöscht oder Elternverweis
                continue
            result.append(self._entry(_dstring(name_raw), icb_ref, icb_lbn))
        return result

    def lookup(self, path: str) -> Entry | None:
        """Pfad wie „/sources/install.wim“, Gross-/Kleinschreibung egal (Windows-Medien)."""
        entry = self.root
        for part in [p for p in path.split("/") if p]:
            if not entry.is_dir:
                return None
            match = [e for e in self.listdir(entry) if e.name.lower() == part.lower()]
            if not match:
                return None
            entry = match[0]
        return entry

    def walk(self, d: Entry | None = None, prefix: str = "") -> Iterator[tuple[str, Entry]]:
        """Alle Dateien und Verzeichnisse: (Pfad ohne führenden „/“, Eintrag)."""
        for e in self.listdir(d or self.root):
            path = f"{prefix}{e.name}"
            yield path, e
            if e.is_dir:
                yield from self.walk(e, path + "/")

    def read(self, e: Entry, offset: int = 0, size: int | None = None) -> bytes:
        size = e.size - offset if size is None else min(size, e.size - offset)
        return b"".join(self.chunks(e, offset, size))

    def chunks(self, e: Entry, offset: int = 0, size: int | None = None,
               chunk: int = 4 * 1024 * 1024) -> Iterator[bytes]:
        """Inhalt ab offset in Stücken – für grosse Dateien ohne alles in den Speicher zu laden."""
        remaining = e.size - offset if size is None else size
        if e.inline is not None:
            yield e.inline[offset:offset + remaining]
            return
        pos = 0
        for start, length in e.extents:
            if remaining <= 0:
                return
            if offset >= pos + length:
                pos += length
                continue
            skip = max(0, offset - pos)
            todo = min(length - skip, remaining)
            while todo > 0:
                n = min(chunk, todo)
                yield bytes(n) if start < 0 else self._read(start + skip, n)
                skip += n
                todo -= n
                remaining -= n
            pos += length
