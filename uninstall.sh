#!/bin/bash
# AWTRIX EQ - Deinstallation: Autostart entfernen, Programm und Einstellungen loeschen.
LABEL="de.awtrix-eq.analyzer"
APP_DIR="$HOME/Library/Application Support/awtrix-eq"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
rm -f "$PLIST"
rm -rf "$APP_DIR"
echo "AWTRIX EQ entfernt."
