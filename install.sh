#!/bin/sh
# Installiert das Okula Recovery Tool auf Debian 13 (Xfce).
#   sudo ./install.sh            Tool + Abhängigkeiten installieren
#   sudo ./install.sh --autostart  zusätzlich nach dem Login automatisch starten
#   sudo ./install.sh --no-bridge  ohne Netzwerkbrücke br0 (VMs dann ohne Netzwerk im LAN)
# Am Server selbst ausführen, nicht aus der Ferne: Beim Einrichten der Brücke ist der Server kurz offline.
set -eu

[ "$(id -u)" -eq 0 ] || exec sudo "$0" "$@"

APP_DIR=/opt/okula-recovery
SRC_DIR=$(cd "$(dirname "$0")" && pwd)
TARGET_USER=${SUDO_USER:-}
AUTOSTART=0
BRIDGE=1
for arg in "$@"; do
    case "$arg" in
        --autostart) AUTOSTART=1 ;;
        --no-bridge) BRIDGE=0 ;;
        *) echo "Unbekannte Option: $arg (erlaubt: --autostart, --no-bridge)" >&2; exit 1 ;;
    esac
done

if [ -z "$TARGET_USER" ] || [ "$TARGET_USER" = root ]; then
    echo "Bitte als normaler Benutzer mit sudo starten: sudo ./install.sh" >&2
    exit 1
fi

echo "==> Pakete installieren"
apt-get update
apt-get install -y --no-install-recommends \
    python3 python3-gi python3-gi-cairo gir1.2-gtk-3.0 librsvg2-common \
    cifs-utils nfs-common smbclient iputils-ping iproute2 \
    util-linux dosfstools grub-pc-bin grub2-common squashfs-tools \
    partclone zstd pigz lz4 lzop bzip2 xz-utils \
    xorriso wimtools e2fsprogs exfatprogs ntfs-3g dnsmasq-base \
    python3-reportlab

# Virtuelle Maschinen (I-001): QEMU/KVM, libvirt, UEFI-Firmware, TPM-Emulator, Bildschirmfenster
# (qemu-system-modules-spice ist nur „Empfiehlt“ von qemu-system-x86 – ohne es kein SPICE-Bildschirm)
echo "==> Pakete für virtuelle Maschinen"
apt-get install -y --no-install-recommends \
    qemu-system-x86 qemu-system-modules-spice qemu-utils libvirt-daemon-system libvirt-clients \
    ovmf swtpm swtpm-tools virt-viewer

# Formatieren: weitere Dateisysteme. Sichtbar installieren (Btrfs/XFS bauen das initramfs neu, das dauert);
# fehlt ein Paket in den Quellen, einzeln weiter – das bricht die Installation nicht ab.
echo "==> Zusatzpakete zum Formatieren (Btrfs, XFS, F2FS, HFS+, UDF) – kann 1–2 Minuten dauern"
OPTIONAL="btrfs-progs xfsprogs f2fs-tools hfsprogs udftools"
APT_OPTS="-y --no-install-recommends -o DPkg::Lock::Timeout=120"
# shellcheck disable=SC2086
if ! DEBIAN_FRONTEND=noninteractive apt-get install $APT_OPTS $OPTIONAL; then
    for pkg in $OPTIONAL; do
        # shellcheck disable=SC2086
        DEBIAN_FRONTEND=noninteractive apt-get install $APT_OPTS "$pkg" \
            || echo "Hinweis: Paket $pkg nicht installiert – dieses Dateisystem fehlt beim Formatieren"
    done
fi

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

echo "==> Root-Helfer (Agent-Stick, NAS einhängen, Garantie-Abfrage)"
install -m 0755 "$APP_DIR/packaging/okula-make-stick" /usr/local/sbin/okula-make-stick
install -m 0755 "$APP_DIR/packaging/okula-nas-mount" /usr/local/sbin/okula-nas-mount
install -m 0755 "$APP_DIR/packaging/okula-warranty" /usr/local/sbin/okula-warranty
SUDOERS=/etc/sudoers.d/okula-recovery
echo "$TARGET_USER ALL=(root) NOPASSWD: /usr/local/sbin/okula-make-stick, /usr/local/sbin/okula-nas-mount, /usr/local/sbin/okula-warranty" > "$SUDOERS.tmp"
chmod 0440 "$SUDOERS.tmp"
visudo -cf "$SUDOERS.tmp" >/dev/null
mv "$SUDOERS.tmp" "$SUDOERS"

echo "==> Virtuelle Maschinen (libvirt)"
install -m 0755 "$APP_DIR/packaging/okula-bridge" /usr/local/sbin/okula-bridge
VIRSH="virsh -c qemu:///system"
systemctl enable --now libvirtd.service >/dev/null 2>&1 || true
if ! id -nG "$TARGET_USER" | tr ' ' '\n' | grep -qx libvirt; then
    usermod -aG libvirt "$TARGET_USER"
    LIBVIRT_NEW=1
fi
# Speicherpool für die virtuellen Disks (qcow2 auf der Server-SSD)
if ! $VIRSH pool-info okula >/dev/null 2>&1; then
    $VIRSH pool-define-as okula dir --target /var/lib/libvirt/images/okula >/dev/null \
        && $VIRSH pool-build okula >/dev/null \
        || echo "Hinweis: Speicherpool okula nicht angelegt – virtuelle Maschinen nicht möglich"
fi
$VIRSH pool-start okula >/dev/null 2>&1 || true
$VIRSH pool-autostart okula >/dev/null 2>&1 || true
# libvirt-Standardnetz (NAT, virbr0) nicht verwenden: VMs hängen über br0 im LAN
if $VIRSH net-info default >/dev/null 2>&1; then
    $VIRSH net-autostart default --disable >/dev/null 2>&1 || true
    $VIRSH net-destroy default >/dev/null 2>&1 || true
fi

echo "==> Netzwerkbrücke für virtuelle Maschinen"
if [ "$BRIDGE" -eq 1 ]; then
    /usr/local/sbin/okula-bridge setup || echo "Hinweis: Netzwerkbrücke nicht eingerichtet – Installation läuft weiter (VMs ohne Netzwerk im LAN)."
else
    echo "Übersprungen (--no-bridge)."
fi

echo "==> Netzwerkstart-Dienste (laufen nur, wenn im Tool eingeschaltet)"
install -m 0644 "$APP_DIR/packaging/okula-pxe.service" /etc/systemd/system/okula-pxe.service
install -m 0644 "$APP_DIR/packaging/okula-pxe-http.service" /etc/systemd/system/okula-pxe-http.service
systemctl daemon-reload
if systemctl is-enabled --quiet okula-pxe.service 2>/dev/null; then
    systemctl restart okula-pxe.service okula-pxe-http.service || true
fi

echo "==> Startmenü-Eintrag"
install -D -m 0644 "$APP_DIR/okula_recovery/assets/okula-emblem.svg" \
    /usr/share/icons/hicolor/scalable/apps/okula-recovery.svg
gtk-update-icon-cache -q /usr/share/icons/hicolor 2>/dev/null || true
# Dateiname = Programm-ID des Tools, damit Alt+Tab und Dock Name und Logo zeigen (früher okula-recovery.desktop)
DESKTOP=ch.okula.RecoveryTool.desktop
rm -f /usr/share/applications/okula-recovery.desktop
install -m 0644 "$APP_DIR/packaging/$DESKTOP" "/usr/share/applications/$DESKTOP"
update-desktop-database -q /usr/share/applications 2>/dev/null || true
HOME_DIR=$(getent passwd "$TARGET_USER" | cut -d: -f6)
if [ "$AUTOSTART" -eq 1 ] || [ -f "$HOME_DIR/.config/autostart/okula-recovery.desktop" ]; then
    rm -f "$HOME_DIR/.config/autostart/okula-recovery.desktop"
    install -d -o "$TARGET_USER" -g "$TARGET_USER" "$HOME_DIR/.config/autostart"
    install -m 0644 -o "$TARGET_USER" -g "$TARGET_USER" \
        "$APP_DIR/packaging/$DESKTOP" "$HOME_DIR/.config/autostart/$DESKTOP"
fi

mkdir -p /mnt/okula-nas

echo
echo "Fertig. Starten: Menü → System → Okula Recovery Tool"
echo "         oder:   cd $APP_DIR && python3 -m okula_recovery"
echo "Firewall aktiv? UDP 47811 eingehend freigeben (USB-Agent-Erkennung)."
if [ "${LIBVIRT_NEW:-0}" -eq 1 ]; then
    echo
    echo "Hinweis: $TARGET_USER wurde in die Gruppe libvirt aufgenommen – für virtuelle Maschinen einmal ab- und"
    echo "         wieder anmelden."
fi
