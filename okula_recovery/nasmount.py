"""Root-Helfer: NAS-Freigabe ein- und aushängen (per sudo über /usr/local/sbin/okula-nas-mount).

Das Passwort kommt über stdin und landet nur in CRED_FILE (root, 0600).
Ausgabe: eine Zeile „OK <Text>“ oder „ERROR <Text>“.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

from okula_recovery.nas import CRED_FILE, mount_error_hint

MOUNT_ROOT = Path("/mnt")
HOST_RE = re.compile(r"^[A-Za-z0-9.-]{1,253}$")
SMB_SHARE_RE = re.compile(r"^[A-Za-z0-9 _.$-]{1,80}(/[A-Za-z0-9 _.-]{1,80})*$")
NFS_EXPORT_RE = re.compile(r"^/[A-Za-z0-9 _./-]{1,200}$")
USER_RE = re.compile(r"^[A-Za-z0-9 _.@\\-]{1,64}$")


class MountError(Exception):
    pass


def check_mount_point(path: str) -> Path:
    """Nur Verzeichnisse unter /mnt, damit die sudo-Regel nichts anderes überdecken kann."""
    p = Path(path)
    if not p.is_absolute() or ".." in p.parts:
        raise MountError(f"Ungültiger Einhängepunkt: {path}")
    if p.parent != MOUNT_ROOT:
        raise MountError(f"Einhängepunkt muss direkt unter {MOUNT_ROOT} liegen, z. B. /mnt/okula-nas")
    return p


def read_cred_user() -> str:
    try:
        for line in CRED_FILE.read_text().splitlines():
            if line.startswith("username="):
                return line.split("=", 1)[1]
    except OSError:
        pass
    return ""


def write_cred(user: str, password: str) -> None:
    if not password or "\n" in password or "\r" in password:
        raise MountError("Ungültiges Passwort")
    CRED_FILE.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    fd = os.open(CRED_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(f"username={user}\npassword={password}\n")
    os.chmod(CRED_FILE, 0o600)


def smb_options(uid: int, gid: int) -> str:
    return (f"credentials={CRED_FILE},uid={uid},gid={gid},iocharset=utf8,"
            "file_mode=0664,dir_mode=0775,nosuid,nodev,noexec")


def _run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        msg = (r.stderr or r.stdout).strip() or f"Exit-Code {r.returncode}"
        hint = mount_error_hint(msg)
        raise MountError(f"{msg} – {hint}" if hint else msg)


def do_mount(protocol: str, host: str, share: str, mount_point: str, user: str, password: str | None,
             uid: int, gid: int) -> str:
    if not HOST_RE.match(host):
        raise MountError(f"Ungültiger Host: {host}")
    mp = check_mount_point(mount_point)

    # Erst alles prüfen, dann am System etwas ändern
    if protocol == "smb":
        if not SMB_SHARE_RE.match(share):
            raise MountError(f"Ungültige Freigabe: {share}")
        if not USER_RE.match(user):
            raise MountError("Benutzername fehlt oder ist ungültig")
        if not password and read_cred_user() != user:
            raise MountError("Passwort eingeben (für diesen Benutzer ist keines gespeichert)")
        cmd = ["mount", "-t", "cifs", f"//{host}/{share}", str(mp), "-o", smb_options(uid, gid)]
    elif protocol == "nfs":
        if not NFS_EXPORT_RE.match(share):
            raise MountError(f"Ungültiger NFS-Pfad: {share} (z. B. /volume1/recovery)")
        cmd = ["mount", "-t", "nfs", f"{host}:{share}", str(mp), "-o", "rw,nosuid,nodev,noexec"]
    else:
        raise MountError(f"Unbekanntes Protokoll: {protocol}")

    mp.mkdir(mode=0o755, exist_ok=True)
    if os.path.ismount(mp):
        _run(["umount", str(mp)])
    if not (protocol == "smb" and password):
        _run(cmd)
        return f"{mp} eingehängt"

    # Neue Zugangsdaten nur behalten, wenn der Mount damit klappt
    try:
        previous = CRED_FILE.read_bytes()
    except OSError:
        previous = None
    write_cred(user, password)
    try:
        _run(cmd)
    except MountError:
        if previous is None:
            CRED_FILE.unlink(missing_ok=True)
        else:
            CRED_FILE.write_bytes(previous)
        raise
    return f"{mp} eingehängt"


def do_umount(mount_point: str) -> str:
    mp = check_mount_point(mount_point)
    if not os.path.ismount(mp):
        return f"{mp} war nicht eingehängt"
    _run(["umount", str(mp)])
    return f"{mp} ausgehängt"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NAS-Freigabe für das Okula Recovery Tool ein-/aushängen")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("mount")
    m.add_argument("--protocol", choices=("smb", "nfs"), required=True)
    m.add_argument("--host", required=True)
    m.add_argument("--share", required=True)
    m.add_argument("--mount-point", required=True)
    m.add_argument("--user", default="")
    m.add_argument("--password-stdin", action="store_true")
    u = sub.add_parser("umount")
    u.add_argument("--mount-point", required=True)
    args = ap.parse_args(argv)

    if os.geteuid() != 0:
        print("ERROR Muss als root laufen", flush=True)
        return 1
    try:
        if args.cmd == "mount":
            password = sys.stdin.readline().rstrip("\n") if args.password_stdin else None
            uid = int(os.environ.get("SUDO_UID", "0"))
            gid = int(os.environ.get("SUDO_GID", "0"))
            msg = do_mount(args.protocol, args.host, args.share, args.mount_point, args.user, password, uid, gid)
        else:
            msg = do_umount(args.mount_point)
    except (MountError, OSError, subprocess.TimeoutExpired) as e:
        print(f"ERROR {e}", flush=True)
        return 1
    print(f"OK {msg}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
