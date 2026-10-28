"""Test-ISOs: Windows-artig (UDF + echte WIM), Linux (ISO9660/Rock Ridge), hybrid."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

HAVE_TOOLS = all(shutil.which(t) for t in ("genisoimage", "wimlib-imagex", "xorriso"))

EDITIONS = (("Windows 11 Home", "Core"), ("Windows 11 Pro", "Professional"))


def make_wim(work: Path, out: Path, build: int = 26100, editions=EDITIONS, payload: int = 200_000) -> None:
    cap = work / "cap"
    cap.mkdir(parents=True, exist_ok=True)
    (cap / "Windows").mkdir(exist_ok=True)
    (cap / "Windows" / "data.bin").write_bytes(bytes(range(256)) * (payload // 256))
    out.parent.mkdir(parents=True, exist_ok=True)
    for i, (name, edition) in enumerate(editions, 1):
        cmd = "capture" if i == 1 else "append"
        subprocess.run(["wimlib-imagex", cmd, str(cap), str(out), name, "--compress=none"], check=True,
                       capture_output=True)
        subprocess.run(["wimlib-imagex", "info", str(out), str(i),
                        "--image-property", "WINDOWS/VERSION/MAJOR=10",
                        "--image-property", f"WINDOWS/VERSION/BUILD={build}",
                        "--image-property", f"WINDOWS/EDITIONID={edition}",
                        "--image-property", "WINDOWS/ARCH=9",
                        "--image-property", "WINDOWS/LANGUAGES/DEFAULT=de-DE",
                        "--image-property", f"DISPLAYNAME={name}"], check=True, capture_output=True)


def windows_iso(work: Path, name: str = "Win11_24H2_German_x64.iso", **kw) -> Path:
    src = work / "winsrc"
    (src / "sources").mkdir(parents=True, exist_ok=True)
    (src / "efi" / "boot").mkdir(parents=True, exist_ok=True)
    (src / "efi" / "microsoft" / "boot").mkdir(parents=True, exist_ok=True)
    (src / "boot").mkdir(exist_ok=True)
    make_wim(work, src / "sources" / "install.wim", **kw)
    (src / "sources" / "boot.wim").write_bytes(b"BOOTWIM" * 1000)
    (src / "bootmgr").write_bytes(b"BOOTMGR")
    (src / "bootmgr.efi").write_bytes(b"BOOTMGREFI")
    (src / "efi" / "boot" / "bootx64.efi").write_bytes(b"MZ-efi")
    (src / "efi" / "microsoft" / "boot" / "bcd").write_bytes(b"BCD")
    (src / "boot" / "bcd").write_bytes(b"BCD")
    (src / "setup.exe").write_bytes(b"MZ")
    out = work / name
    # wie die Microsoft-Medien: Inhalt im UDF-Teil
    subprocess.run(["genisoimage", "-quiet", "-udf", "-iso-level", "3", "-V", "CCCOMA_X64FRE_DE-DE_DV9",
                    "-o", str(out), str(src)], check=True)
    return out


def linux_iso(work: Path, name: str = "ubuntu-24.04.1-desktop-amd64.iso",
              info: str = 'Ubuntu 24.04.1 LTS "Noble Numbat" - Release amd64 (20240827)',
              kind: str = "casper", hybrid: bool = True) -> Path:
    src = work / f"src-{name}"
    (src / ".disk").mkdir(parents=True, exist_ok=True)
    (src / ".disk" / "info").write_text(info)
    (src / kind).mkdir(exist_ok=True)
    (src / kind / "vmlinuz").write_bytes(b"kernel" * 1000)
    (src / kind / "initrd").write_bytes(b"initrd" * 1000)
    (src / "EFI" / "boot").mkdir(parents=True, exist_ok=True)
    (src / "EFI" / "boot" / "bootx64.efi").write_bytes(b"MZ-shim")
    (src / "boot" / "grub").mkdir(parents=True, exist_ok=True)
    (src / "boot" / "grub" / "grub.cfg").write_text("menuentry x {}\n")
    out = work / name
    subprocess.run(["genisoimage", "-quiet", "-R", "-J", "-V", "Ubuntu 24.04.1 LTS amd64", "-o", str(out), str(src)],
                   check=True)
    if hybrid:  # MBR mit einer Partition im Systembereich, wie isohybrid
        with open(out, "r+b") as fh:
            fh.seek(446)
            fh.write(bytes([0x80, 0, 0, 0, 0x17, 0, 0, 0]) + (0).to_bytes(4, "little")
                     + (out.stat().st_size // 512).to_bytes(4, "little"))
            fh.seek(510)
            fh.write(b"\x55\xaa")
    return out
