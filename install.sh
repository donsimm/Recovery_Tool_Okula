#!/bin/sh
# Installiert das Okula Recovery Tool auf Debian 13 (Xfce).
#   sudo ./install.sh            Tool + Abhängigkeiten installieren
#   sudo ./install.sh --autostart  zusätzlich nach dem Login automatisch starten
set -eu

[ "$(id -u)" -eq 0 ] || exec sudo "$0" "$@"

APP_DIR=/opt/okula-recovery
SRC_DIR=$(cd "$(dirname "$0")" && pwd)
TARGET_USER=${SUDO_USER:-}
AUTOSTART=0
[ "${1:-}" = "--autostart" ] && AUTOSTART=1

if [ -z "$TARGET_USER" ] || [ "$TARGET_USER" = root ]; then
    echo "Bitte als normaler Benutzer mit sudo starten: sudo ./install.sh" >&2
    exit 1
fi

echo "==> Pakete installieren"
apt-get update
apt-get install -y --no-install-recommends \
    python3 python3-gi gir1.2-gtk-3.0 librsvg2-common \
    cifs-utils nfs-common smbclient iputils-ping iproute2 \
    util-linux dosfstools grub-pc-bin grub2-common squashfs-tools \
    partclone zstd pigz lz4 lzop bzip2 xz-utils \
    xorriso wimtools e2fsprogs

echo "==> Programm nach $APP_DIR kopieren"
if [ "$SRC_DIR" != "$APP_DIR" ]; then
    rm -rf "$APP_DIR"
    mkdir -p "$APP_DIR"
    cp -r "$SRC_DIR/okula_recovery" "$SRC_DIR/packaging" "$APP_DIR/"
fi
# Der Root-Helfer läuft per sudo: Code darf nur root gehören
chown -R root:root "$APP_DIR"
chmod -R go-w "$APP_DIR"
find "$APP_DIR" -name __pycache__ -prune -exec rm -rf {} +

echo "==> Root-Helfer (Agent-Stick, NAS einhängen)"
install -m 0755 "$APP_DIR/packaging/okula-make-stick" /usr/local/sbin/okula-make-stick
install -m 0755 "$APP_DIR/packaging/okula-nas-mount" /usr/local/sbin/okula-nas-mount
SUDOERS=/etc/sudoers.d/okula-recovery
echo "$TARGET_USER ALL=(root) NOPASSWD: /usr/local/sbin/okula-make-stick, /usr/local/sbin/okula-nas-mount" > "$SUDOERS.tmp"
chmod 0440 "$SUDOERS.tmp"
visudo -cf "$SUDOERS.tmp" >/dev/null
mv "$SUDOERS.tmp" "$SUDOERS"

echo "==> Startmenü-Eintrag"
install -D -m 0644 "$APP_DIR/okula_recovery/assets/okula-emblem.svg" \
    /usr/share/icons/hicolor/scalable/apps/okula-recovery.svg
gtk-update-icon-cache -q /usr/share/icons/hicolor 2>/dev/null || true
install -m 0644 "$APP_DIR/packaging/okula-recovery.desktop" /usr/share/applications/okula-recovery.desktop
if [ "$AUTOSTART" -eq 1 ]; then
    HOME_DIR=$(getent passwd "$TARGET_USER" | cut -d: -f6)
    install -d -o "$TARGET_USER" -g "$TARGET_USER" "$HOME_DIR/.config/autostart"
    install -m 0644 -o "$TARGET_USER" -g "$TARGET_USER" \
        "$APP_DIR/packaging/okula-recovery.desktop" "$HOME_DIR/.config/autostart/okula-recovery.desktop"
fi

mkdir -p /mnt/okula-nas

echo
echo "Fertig. Starten: Menü → System → Okula Recovery Tool"
echo "         oder:   cd $APP_DIR && python3 -m okula_recovery"
echo "Firewall aktiv? UDP 47811 eingehend freigeben (USB-Agent-Erkennung)."
