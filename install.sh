#!/bin/bash
# AWTRIX EQ - Installer fuer macOS
# Legt eine eigene Python-Umgebung an, fragt Uhr-IP, Tonquelle und Stil ab,
# schreibt die Konfiguration und richtet den Autostart beim Anmelden ein.
#
# Aufruf:   bash install.sh
# Ohne Rueckfragen (z.B. fuer Tests):
#   AWTRIX_EQ_IP=192.168.1.154 AWTRIX_EQ_DEVICE="eqMac" AWTRIX_EQ_STYLE=v2 bash install.sh
#   AWTRIX_EQ_NO_AUTOSTART=1   -> keinen Autostart einrichten
set -e

HERE="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$HOME/Library/Application Support/awtrix-eq"
VENV="$APP_DIR/venv"
CONFIG="$APP_DIR/config.json"
LABEL="de.awtrix-eq.analyzer"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

echo "AWTRIX EQ Installation"
echo "----------------------"

# 1. Python pruefen
PY=$(command -v python3 || true)
if [ -z "$PY" ]; then
  echo "python3 fehlt. Bitte installieren (https://www.python.org oder 'xcode-select --install') und erneut starten."; exit 1
fi
PYV=$($PY -c 'import sys; print("%d.%d" % sys.version_info[:2])')
echo "Python $PYV gefunden: $PY"

# 2. Umgebung und Abhaengigkeiten
mkdir -p "$APP_DIR"
if [ ! -x "$VENV/bin/python" ]; then
  echo "Lege Python-Umgebung an ..."
  "$PY" -m venv "$VENV"
fi
echo "Installiere Abhaengigkeiten (numpy, sounddevice) ..."
"$VENV/bin/pip" install --quiet --upgrade pip >/dev/null
"$VENV/bin/pip" install --quiet -r "$HERE/requirements.txt"
cp "$HERE/awtrix_eq.py" "$APP_DIR/awtrix_eq.py"

# 3. Uhr-IP
IP="${AWTRIX_EQ_IP:-}"
if [ -z "$IP" ]; then
  read -r -p "IP-Adresse der Uhr (steht in der AWTRIX Web-UI unter System): " IP
fi
if curl -s -m 4 "http://$IP/api/v1/version" | grep -q version; then
  echo "Uhr gefunden: $(curl -s -m 4 "http://$IP/api/v1/version")"
else
  echo "Warnung: Unter $IP antwortet keine AWTRIX-Uhr. Installation geht weiter, bitte IP spaeter in $CONFIG pruefen."
fi

# 4. Tonquelle
echo
echo "Verfuegbare Tonquellen:"
"$VENV/bin/python" "$APP_DIR/awtrix_eq.py" --list || true
echo
echo "Tipp: Fuer Musik vom Mac ein virtuelles Ausgabegeraet nehmen (BlackHole oder eqMac)."
echo "      Ein Mikrofon zeigt stattdessen den Raumschall."
DEVICE="${AWTRIX_EQ_DEVICE:-}"
if [ -z "$DEVICE" ]; then
  read -r -p "Tonquelle (Namensteil oder Nummer): " DEVICE
fi

# 5. Stil
STYLE="${AWTRIX_EQ_STYLE:-}"
if [ -z "$STYLE" ]; then
  echo
  echo "Darstellung:  v2 = Kurve mit Mittelwertlinie (empfohlen)   v1 = 52 weisse Balken"
  read -r -p "Stil [v2]: " STYLE
  STYLE="${STYLE:-v2}"
fi

# 6. Konfiguration schreiben
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
echo "Konfiguration gespeichert: $CONFIG"

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
  echo "Autostart eingerichtet und gestartet. Beim ersten Start fragt macOS einmal nach Mikrofon-Zugriff: bitte erlauben."
  echo "Protokoll: $APP_DIR/awtrix-eq.log"
else
  echo "Autostart uebersprungen. Manuell starten mit:"
  echo "  \"$VENV/bin/python\" \"$APP_DIR/awtrix_eq.py\""
fi

echo
echo "Fertig. Einstellungen aendern: $CONFIG bearbeiten, dann:"
echo "  launchctl kickstart -k gui/$(id -u)/$LABEL"
echo "Deinstallieren: bash uninstall.sh"
