# AWTRIX EQ

Musik-Spektrum vom Mac live auf einer Ulanzi TC002 Pixeluhr mit AWTRIX NG Firmware.
Logarithmische Frequenzachse mit feiner Bass-Auflösung, bis zu 40 Bilder pro Sekunde,
Ruhe-Animation wenn keine Musik läuft, Autostart beim Anmelden.

**EQ 2** – weiche Live-Kurve mit Fläche und träger Mittelwertlinie:

![EQ 2](docs/eq_v2.png)

![EQ 2, zweiter Moment](docs/eq_v2_b.png)

**EQ 1** – 52 weiße Balken, Spitzen nach Pegel grün, orange, rot:

![EQ 1](docs/eq_v1.png)

## Voraussetzungen

- Mac mit macOS 12 oder neuer, Python 3.9 oder neuer
  (prüfen: Terminal öffnen, `python3 --version` eingeben; fehlt es, `xcode-select --install`).
- Ulanzi TC002 mit AWTRIX NG (Port von sanderdw, Version 1.1.1-tc002.5 oder neuer)
  im selben WLAN. Die IP-Adresse steht in der Web-Oberfläche der Uhr unter System.
- Für Musik vom Mac ein virtuelles Audiogerät, das die Wiedergabe mitliest:
  **BlackHole** (kostenlos, existential.audio/blackhole) oder **eqMac** (eqmac.app).
  Ohne so ein Gerät nimmt AWTRIX EQ ein Mikrofon und zeigt den Raumschall.

## Installation

1. ZIP entpacken, zum Beispiel in den Downloads-Ordner.
2. Terminal öffnen (Programme → Dienstprogramme → Terminal).
3. Eingeben, dabei den Pfad anpassen:

       bash ~/Downloads/awtrix-eq/install.sh

4. Der Installer fragt nacheinander:
   - die IP-Adresse der Uhr,
   - die Tonquelle (er zeigt eine Liste, es reicht ein Namensteil wie `BlackHole` oder `eqMac`),
   - den Stil: `v2` Kurve mit Mittelwertlinie (empfohlen) oder `v1` 52 weiße Balken.
5. Beim ersten Start fragt macOS nach dem Zugriff auf das Mikrofon. Bitte erlauben,
   das gilt auch für virtuelle Audiogeräte.

Danach läuft AWTRIX EQ im Hintergrund und startet bei jeder Anmeldung automatisch.
Die Uhr zeigt die App „spectrum“; sie verschwindet, wenn der Mac aus ist.

## Musik vom Mac einrichten (BlackHole)

1. BlackHole installieren.
2. Programme → Dienstprogramme → Audio-MIDI-Setup öffnen.
3. Unten links „+“ → „Multi-Output-Gerät“ anlegen, darin die Lautsprecher **und** BlackHole anhaken.
4. Dieses Multi-Output-Gerät in den Systemeinstellungen → Ton als Ausgabe wählen.
5. In AWTRIX EQ `BlackHole` als Tonquelle angeben.

Mit eqMac entfällt das: dort einfach `eqMac` als Tonquelle wählen.

## Einstellungen ändern

Die Datei `~/Library/Application Support/awtrix-eq/config.json` enthält alle Werte:

| Schlüssel | Bedeutung | Standard |
|---|---|---|
| `clock` | IP-Adresse der Uhr | |
| `device` | Tonquelle, Namensteil oder Nummer | |
| `style` | `v2` Kurve, `v1` Balken, `rainbow` bunte Balken | `v2` |
| `gain` | Empfindlichkeit, höher = höhere Balken | `1.5` |
| `tilt` | Höhenanhebung in dB pro Oktave, 0 = linear | `4.5` |
| `fps` | Ziel-Bildrate | `42` |
| `connections` | parallele Verbindungen zur Uhr | `3` |
| `idle_after` | Sekunden ohne Musik bis zur Ruhe-Animation | `15` |

Nach dem Ändern neu starten:

    launchctl kickstart -k gui/$(id -u)/de.awtrix-eq.analyzer

## Manuell starten, Fehler suchen

    "$HOME/Library/Application Support/awtrix-eq/venv/bin/python" "$HOME/Library/Application Support/awtrix-eq/awtrix_eq.py" --list
    "$HOME/Library/Application Support/awtrix-eq/venv/bin/python" "$HOME/Library/Application Support/awtrix-eq/awtrix_eq.py" --style v2

Alle fünf Sekunden erscheint eine Statuszeile mit Bildrate, Pegel und Modus.
Das Hintergrund-Protokoll liegt in `~/Library/Application Support/awtrix-eq/awtrix-eq.log`.

Häufige Ursachen:
- **Nichts auf der Uhr**: IP prüfen, Uhr und Mac im selben WLAN?
- **Balken reagieren nicht auf Musik**: Tonquelle ist ein Mikrofon statt BlackHole/eqMac.
- **Immer Ruhe-Animation**: Musik läuft über ein anderes Ausgabegerät als das gewählte.
- **Balken zu niedrig oder dauerhaft oben**: `gain` anpassen.

## Deinstallation

    bash ~/Downloads/awtrix-eq/uninstall.sh

## Technik

Der Mac liest das Audiosignal, rechnet eine Fourier-Transformation (Bass mit feinerem
Fenster) und schickt pro Bild eine kleine HTTP-Anfrage an die Uhr, die nur noch zeichnet.
Die Uhr selbst hört nichts. Verwendet werden ausschließlich die öffentliche HTTP-Schnittstelle
von AWTRIX NG sowie die Python-Bibliotheken numpy und sounddevice.
