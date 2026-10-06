#!/bin/bash
# AWTRIX EQ - uninstall: remove autostart, program and settings.
LABEL="de.awtrix-eq.analyzer"
APP_DIR="$HOME/Library/Application Support/awtrix-eq"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
rm -f "$PLIST"
rm -rf "$APP_DIR"
echo "AWTRIX EQ removed."
