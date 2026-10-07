#!/bin/bash
# AWTRIX EQ - installer for macOS
# Creates a private Python environment, asks for the clock's IP, the audio source and the style,
# writes the configuration and sets up automatic start at login.
#
# Usage:   bash install.sh
# Without prompts (e.g. for testing):
#   AWTRIX_EQ_IP=192.168.1.154 AWTRIX_EQ_DEVICE="BlackHole" AWTRIX_EQ_STYLE=v2 bash install.sh
#   AWTRIX_EQ_NO_AUTOSTART=1   -> do not set up autostart
set -e

HERE="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$HOME/Library/Application Support/awtrix-eq"
VENV="$APP_DIR/venv"
CONFIG="$APP_DIR/config.json"
LABEL="de.awtrix-eq.analyzer"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

echo "AWTRIX EQ installation"
echo "----------------------"

# 1. Python
PY=$(command -v python3 || true)
if [ -z "$PY" ]; then
  echo "python3 is missing. Install it (https://www.python.org or 'xcode-select --install') and run this again."; exit 1
fi
PYV=$($PY -c 'import sys; print("%d.%d" % sys.version_info[:2])')
echo "Found Python $PYV: $PY"

# 2. Environment and dependencies
mkdir -p "$APP_DIR"
if [ ! -x "$VENV/bin/python" ]; then
  echo "Creating Python environment ..."
  "$PY" -m venv "$VENV"
fi
echo "Installing dependencies (numpy, sounddevice) ..."
"$VENV/bin/pip" install --quiet --upgrade pip >/dev/null
"$VENV/bin/pip" install --quiet -r "$HERE/requirements.txt"
cp "$HERE/awtrix_eq.py" "$APP_DIR/awtrix_eq.py"

# 3. Clock IP
IP="${AWTRIX_EQ_IP:-}"
if [ -z "$IP" ]; then
  read -r -p "IP address of the clock (shown in the AWTRIX web UI under System): " IP
fi
if curl -s -m 4 "http://$IP/api/v1/version" | grep -q version; then
  echo "Clock found: $(curl -s -m 4 "http://$IP/api/v1/version")"
else
  echo "Warning: no AWTRIX clock answers at $IP. Continuing; please check the IP later in $CONFIG."
fi

# 4. Audio source
echo
echo "Available audio sources:"
"$VENV/bin/python" "$APP_DIR/awtrix_eq.py" --list || true
echo
echo "Tip: to visualise music from the Mac, pick a virtual output device (BlackHole or eqMac)."
echo "     A microphone shows the sound in the room instead."
DEVICE="${AWTRIX_EQ_DEVICE:-}"
if [ -z "$DEVICE" ]; then
  read -r -p "Audio source (part of the name or the number): " DEVICE
fi

# 5. Style
STYLE="${AWTRIX_EQ_STYLE:-}"
if [ -z "$STYLE" ]; then
  echo
  echo "Style:  v2 = curve with average line (recommended)   v1 = 52 white bars"
  read -r -p "Style [v2]: " STYLE
  STYLE="${STYLE:-v2}"
fi

# 6. Write configuration
cat > "$CONFIG" <<EOF
{
  "clock": "$IP",
  "device": "$DEVICE",
  "style": "$STYLE",
  "gain": 1.5,
  "tilt": 4.5,
  "fps": 42,
  "connections": 3,
  "idle_after": 15
}
EOF
echo "Configuration saved: $CONFIG"

# 7. Autostart
if [ -z "${AWTRIX_EQ_NO_AUTOSTART:-}" ]; then
  mkdir -p "$HOME/Library/LaunchAgents"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array>
    <string>$VENV/bin/python</string>
    <string>-u</string>
    <string>$APP_DIR/awtrix_eq.py</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>$APP_DIR/awtrix-eq.log</string>
  <key>StandardErrorPath</key><string>$APP_DIR/awtrix-eq.log</string>
</dict></plist>
EOF
  launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/$(id -u)" "$PLIST"
  echo "Autostart set up and started."
  echo "macOS will ask once for microphone access and once for local network access (\"Python wants to find devices\"): allow both."
  echo "If the clock stays dark, open System Settings > Privacy & Security > Local Network and enable Python."
  echo "Log: $APP_DIR/awtrix-eq.log"
else
  echo "Autostart skipped. Start manually with:"
  echo "  \"$VENV/bin/python\" \"$APP_DIR/awtrix_eq.py\""
fi

echo
echo "Done. To change settings edit $CONFIG, then run:"
echo "  launchctl kickstart -k gui/$(id -u)/$LABEL"
echo "To uninstall: bash uninstall.sh"
