#!/bin/sh
# Script to dynamically create the "Install System" shortcut on the live user desktop

# Exit immediately if we are not in the live ISO environment
if [ ! -d /mnt/cdrom ] && [ ! -f /etc/gentoo-release ]; then
    exit 0
fi

# Wait a few seconds for the user session and xdg directories to initialize
sleep 2

# Query the localized Desktop folder name (e.g. ~/Ambiente de Trabalho)
DESKTOP=$(xdg-user-dir DESKTOP 2>/dev/null)
if [ -z "$DESKTOP" ]; then
    DESKTOP="$HOME/Desktop"
fi

# Ensure the directory exists
mkdir -p "$DESKTOP"

LAUNCHER_SRC="/usr/share/applications/install.desktop"
LAUNCHER_DEST="$DESKTOP/install.desktop"

if [ -f "$LAUNCHER_SRC" ]; then
    cp "$LAUNCHER_SRC" "$LAUNCHER_DEST"
    chmod +x "$LAUNCHER_DEST"

    # Set launcher as trusted under XFCE/Gnome to avoid execution warnings
    if command -v gio >/dev/null 2>&1; then
        gio set --type=string "$LAUNCHER_DEST" metadata::trusted true 2>/dev/null
        gio set --type=string "$LAUNCHER_DEST" metadata::xfce-exe-checksum "$(sha256sum "$LAUNCHER_DEST" | cut -f1 -d' ')" 2>/dev/null
    fi
    touch "$LAUNCHER_DEST"
fi
