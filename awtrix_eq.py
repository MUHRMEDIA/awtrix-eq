#!/usr/bin/env python3
"""AWTRIX EQ - live music spectrum from your Mac on the Ulanzi TC002 running AWTRIX NG.

Captures audio from an input device (microphone, or BlackHole/eqMac for system sound),
computes a logarithmic spectrum and streams it to the clock as drawing commands.
Stop with Ctrl+C and the app disappears from the clock again.

Examples:
  python3 awtrix_eq.py                      # defaults from the config file
  python3 awtrix_eq.py --device BlackHole   # system sound (music); BlackHole must be the output device
  python3 awtrix_eq.py --style v1           # 52 white bars instead of the curve
  python3 awtrix_eq.py --list               # list input devices
  python3 awtrix_eq.py --demo               # test pattern without audio
"""
import argparse, colorsys, json, math, os, sys, time, urllib.request

CLOCK = "192.168.1.154"
APP = "spectrum"
BANDS = 52          # one band per pixel column; 52 pixels is the physical maximum
BAR_W = 1
HEIGHT = 16
RATE = 44100
BLOCK = 1024        # small block = fast response (23 ms)
STYLE = "white"     # "white"/v1: white bars with level-coloured peaks; "rainbow": hue gradient; v2 curve; v3 wide bars


import threading
_tls = threading.local()        # each sender thread owns its own connection
_errors = 0


def _request(path, body):
    """PUT over this thread's open connection; on error reconnect and drop the frame."""
    global _errors
    import http.client
    conn = getattr(_tls, "conn", None)
    try:
        if conn is None:
            conn = _tls.conn = http.client.HTTPConnection(CLOCK, 80, timeout=6.0)
        conn.request("PUT", path, body=body, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        resp.read()
        _errors = 0
        return True
    except Exception:
        _errors += 1
        try:
            conn.close()
        except Exception:
            pass
        _tls.conn = None
        if _errors in (5, 50, 500):
            print(f"Clock is not responding ({_errors} errors in a row), retrying", file=sys.stderr)
        return False


class Sender:
    """Sends frames over several parallel connections. The clock needs ~30-45 ms per request but
    serves connections concurrently; three connections were measured at ~70 frames/s.
    Every free thread takes the newest frame; older frames that were never sent are dropped."""

    def __init__(self, workers=3):
        self._lock = threading.Lock()
        self._event = threading.Event()
        self._frame = None
        self.sent = self.dropped = self.failed = 0
        self.last_ms = 0.0
        self._activated = False
        self._stop = False
        self._threads = [threading.Thread(target=self._run, daemon=True) for _ in range(workers)]
        for t in self._threads:
            t.start()

    def submit(self, draw):
        with self._lock:
            if self._frame is not None:
                self.dropped += 1
            self._frame = draw
        self._event.set()

    def _run(self):
        while not self._stop:
            self._event.wait(0.5)
            with self._lock:
                draw, self._frame = self._frame, None
                self._event.clear()
            if draw is None:
                continue
            body = json.dumps({"draw": draw, "durationMs": 0, "lifetimeMs": 30000}).encode()
            t = time.time()
            ok = _request(f"/api/v1/apps/pushed/{APP}", body)
            self.last_ms = (time.time() - t) * 1000
            if ok:
                self.sent += 1
                if not self._activated:
                    self._activated = bool(_request("/api/v1/apps/active",
                                                    json.dumps({"name": APP, "fast": True}).encode()))
            else:
                self.failed += 1

    def stop(self):
        self._stop = True
        self._event.set()
        for t in self._threads:
            t.join(timeout=2)

    def stats(self, seconds):
        s = f"{self.sent / seconds:.1f} frames/s sent, {self.dropped} dropped, {self.failed} errors, clock responds in {self.last_ms:.0f} ms"
        self.sent = self.dropped = self.failed = 0
        return s


def paced(fps, t0, seconds):
    """Pacer: yields ticks at a fixed interval regardless of how long the work took."""
    period = 1.0 / fps
    next_t = time.time()
    while not seconds or time.time() - t0 < seconds:
        yield
        next_t += period
        delay = next_t - time.time()
        if delay > 0:
            time.sleep(delay)
        else:
            next_t = time.time()      # too slow: resync instead of trying to catch up


def remove():
    try:
        req = urllib.request.Request(f"http://{CLOCK}/api/v1/apps/{APP}", method="DELETE")
        urllib.request.urlopen(req, timeout=2).read()
    except Exception:
        pass


def hexcol(h, s, v):
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return "#%02X%02X%02X" % (int(r * 255), int(g * 255), int(b * 255))


def peak_color(p):
    """Peak colour by level: quiet green, medium orange, loud red."""
    if p >= 12:
        return "#FF3030"
    if p >= 8:
        return "#FFA000"
    return "#30FF30"


def frame_v1(levels, peaks, hue_shift):
    """v1: 52 bars, white with level-coloured peaks (white) or hue gradient (rainbow)."""
    draw = []
    if STYLE in ("white", "v1"):
        bars, pk_g, pk_o, pk_r = [], [], [], []
        for i, (lv, pk) in enumerate(zip(levels, peaks)):
            h = int(round(lv))
            if h > 0:
                draw.append(["rectFill", i * BAR_W, HEIGHT - h, BAR_W, h, "#FFFFFF"])
            p = int(round(pk))
            if p > h and p > 0:
                col = peak_color(p)
                (pk_r if col == "#FF3030" else pk_o if col == "#FFA000" else pk_g).extend([i * BAR_W, HEIGHT - p])
        for col, pts in (("#30FF30", pk_g), ("#FFA000", pk_o), ("#FF3030", pk_r)):
            if pts:
                draw.append(["pixels", col] + pts)
    else:
        for i, (lv, pk) in enumerate(zip(levels, peaks)):
            x = i * BAR_W
            h = int(round(lv))
            hue = (i / BANDS * 0.75 + hue_shift) % 1.0          # red -> violet across the width
            if h > 0:
                draw.append(["rectFill", x, HEIGHT - h, BAR_W, h, hexcol(hue, 1.0, 1.0)])
            p = int(round(pk))
            if p > h and p > 0:
                draw.append(["rectFill", x, HEIGHT - p, BAR_W, 1, hexcol(hue, 0.3, 1.0)])
    if not draw:
        draw.append(["pixel", 0, 15, "#000000"])
    return draw


import colorsys as _cs

# ---------- v2: curve display, inspired by eqMac's analyser ----------
V2 = {"slow": None}
V2_FILL = "#0B3F47"      # dark teal fill below the live line
V2_LINE = "#FFFFFF"      # live line
V2_SLOW = "#FF8C00"      # slow average curve


def frame_v2(levels, peaks, t):
    """Smooth live curve (white) with a filled area below it and a slow average curve (orange)."""
    sm = [(levels[max(0, i - 1)] + 2 * levels[i] + levels[min(BANDS - 1, i + 1)]) / 4 for i in range(BANDS)]
    if V2["slow"] is None:
        V2["slow"] = sm[:]
    slow = V2["slow"]
    for i in range(BANDS):
        slow[i] = slow[i] * 0.93 + sm[i] * 0.07
    draw, line, avg = [], [], []
    for x in range(BANDS):
        h = int(round(sm[x]))
        if h >= 1:
            if h >= 2:
                draw.append(["rectFill", x, HEIGHT - h + 1, 1, h - 1, V2_FILL])
            line += [x, HEIGHT - h]
        sh = int(round(slow[x]))
        if sh >= 1:
            avg += [x, HEIGHT - sh]
    if avg:
        draw.append(["pixels", V2_SLOW] + avg)
    if line:
        draw.append(["pixels", V2_LINE] + line)
    if not draw:
        draw.append(["pixel", 0, 15, "#000000"])
    return draw


# ---------- v3: 13 wide bars with gradient and falling peak caps ----------
V3_BARS = 13
V3 = {"peak": [0.0] * V3_BARS, "vel": [0.0] * V3_BARS, "hold": [0] * V3_BARS}
# gradient from bottom (green) through yellow to top (red), one colour per row
V3_ROWS = ["#%02X%02X%02X" % tuple(int(c * 255) for c in _cs.hsv_to_rgb(0.33 * (1 - r / (HEIGHT - 1)), 1.0, 1.0))
           for r in range(HEIGHT)]


def frame_v3(levels, peaks, t):
    """13 bars of 3 pixels each, colour by height, white peak caps that hold briefly and then fall with gravity."""
    bars = [max(levels[4 * i:4 * i + 4]) for i in range(V3_BARS)]
    pk, vel, hold = V3["peak"], V3["vel"], V3["hold"]
    for i in range(V3_BARS):
        if bars[i] >= pk[i]:
            pk[i], vel[i], hold[i] = bars[i], 0.0, 10          # hold ~0.25 s
        elif hold[i] > 0:
            hold[i] -= 1
        else:
            vel[i] += 0.06                                    # gravity
            pk[i] = max(bars[i], pk[i] - vel[i])
    draw = []
    for r in range(HEIGHT):                                   # r = 0 unten
        pts = []
        for i, h in enumerate(bars):
            if h >= r + 1:
                x = i * 4
                pts += [x, HEIGHT - 1 - r, x + 1, HEIGHT - 1 - r, x + 2, HEIGHT - 1 - r]
        if pts:
            draw.append(["pixels", V3_ROWS[r]] + pts)
    caps = []
    for i in range(V3_BARS):
        p = int(round(pk[i]))
        if p >= 1 and p > int(round(bars[i])):
            x = i * 4
            caps += [x, HEIGHT - p, x + 1, HEIGHT - p, x + 2, HEIGHT - p]
    if caps:
        draw.append(["pixels", "#FFFFFF"] + caps)
    if not draw:
        draw.append(["pixel", 0, 15, "#000000"])
    return draw


def frame(levels, peaks, t):
    if STYLE == "v2":
        return frame_v2(levels, peaks, t)
    if STYLE == "v3":
        return frame_v3(levels, peaks, t)
    return frame_v1(levels, peaks, t)


def update_levels(targets, levels, peaks, decay):
    """Ballistics per style: how fast the display rises and falls."""
    for i in range(BANDS):
        tg = targets[i]
        if STYLE == "v2":                                     # soft like eqMac: quick rise, gentle fall
            levels[i] = levels[i] + (tg - levels[i]) * 0.65 if tg > levels[i] else levels[i] * 0.86 + tg * 0.14
        elif STYLE == "v3":                                   # instant rise, brisk fall; peaks are handled in frame_v3
            levels[i] = max(tg, levels[i] * 0.72)
        else:
            levels[i] = max(tg, levels[i] * decay[i])
            peaks[i] = max(levels[i], peaks[i] - 0.5)


BASS_BLOCK = 4096   # longer window for the bass: 10.8 Hz resolution instead of 43 Hz
BASS_SPLIT = 320.0  # below this frequency the value comes from the fine bass spectrum

# column layout: the bass gets most bands, the treble the fewest.
SEGMENTS = [
    (30.0, 120.0, 16),      # sub and kick bass: 16 bands, ~5 Hz steps
    (120.0, 320.0, 12),     # bass / low mids
    (320.0, 2000.0, 14),    # mids
    (2000.0, 14000.0, 10),  # treble, coarse
]


def idle_wave(t):
    """Idle animation: two travelling waves that overlap, like a breathing EQ curve."""
    lv = []
    for i in range(BANDS):
        x = i / BANDS
        v = 5.5 + 3.2 * math.sin(2 * math.pi * (x * 1.3 - t * 0.35)) \
                + 2.2 * math.sin(2 * math.pi * (x * 2.9 + t * 0.21)) \
                + 1.2 * math.sin(2 * math.pi * (x * 0.5 + t * 0.09))
        lv.append(max(1.0, min(15.0, v)))
    return lv


LAYOUT = "bass"     # "bass": many bands in the bass; "log": uniform logarithmic 20 Hz - 20 kHz


def band_edges():
    if LAYOUT == "log":
        return [20.0 * (20000.0 / 20.0) ** (i / BANDS) for i in range(BANDS + 1)]
    edges = []
    for lo, hi, n in SEGMENTS:
        edges += [lo * (hi / lo) ** (i / n) for i in range(n)]
    edges.append(SEGMENTS[-1][1])
    assert len(edges) == BANDS + 1, f"segments yield {len(edges) - 1} bands, expected {BANDS}"
    return edges


def main():
    global CLOCK, STYLE, LAYOUT, APP
    ap = argparse.ArgumentParser(description="AWTRIX EQ: live music spectrum from your Mac on the Ulanzi TC002 / AWTRIX NG clock")
    cfg_path = os.environ.get("AWTRIX_EQ_CONFIG") or os.path.expanduser("~/Library/Application Support/awtrix-eq/config.json")
    cfg = {}
    if os.path.exists(cfg_path):
        try:
            cfg = {k.replace("-", "_"): v for k, v in json.load(open(cfg_path)).items()}
        except Exception as e:
            print("Cannot read config file:", cfg_path, e, file=sys.stderr)
    ap.add_argument("--device", default="eqMac", help="input device: index or part of its name (BlackHole / eqMac = the Mac's system sound)")
    ap.add_argument("--fps", type=float, default=42)
    ap.add_argument("--connections", type=int, default=3, help="parallel connections to the clock (3 allows ~70 frames/s)")
    ap.add_argument("--gain", type=float, default=1.0, help="sensitivity, e.g. 2 for quiet sources")
    ap.add_argument("--style", choices=["v1", "v2", "v3", "white", "rainbow"], default="v1",
                    help="v1 = 52 white bars, v2 = smooth curve with average line, v3 = 13 wide gradient bars, rainbow = colourful v1")
    ap.add_argument("--bands", choices=["bass", "log"], default=None, help="band layout; default: log for v2, bass-weighted otherwise")
    ap.add_argument("--tilt", type=float, default=4.5,
                    help="treble boost in dB per octave above 200 Hz (0 = flat, 4.5 = snares and claps stand out)")
    ap.add_argument("--idle-motion", type=float, default=0.55,
                    help="average bar movement (pixels per frame) below which the input counts as silent (0 = no idle animation)")
    ap.add_argument("--idle-after", type=float, default=15.0, help="seconds of silence before the idle animation starts")
    ap.add_argument("--clock", default=CLOCK)
    ap.add_argument("--channel", type=int, default=1, help="channel of the input device, 1 = first (RODECaster multitrack: 1/2 = main mix)")
    ap.add_argument("--app", default=APP, help="app name on the clock (e.g. eq_v1 and eq_v2 to run two displays side by side)")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--demo", action="store_true", help="test pattern without audio")
    ap.add_argument("--seconds", type=float, default=0, help="stop after n seconds (0 = run forever)")
    ap.set_defaults(**{k: v for k, v in cfg.items() if k in {x.dest for x in ap._actions}})
    a = ap.parse_args()
    CLOCK = a.clock
    APP = a.app
    STYLE = a.style
    LAYOUT = a.bands or ("log" if a.style == "v2" else "bass")

    levels = [0.0] * BANDS
    peaks = [0.0] * BANDS
    t0 = time.time()
    first = True

    sender = Sender(workers=max(1, a.connections))
    last_stats = time.time()

    if a.demo:
        try:
            for _ in paced(a.fps, t0, a.seconds):
                t = time.time() - t0
                levels = [8 + 7 * math.sin(t * 4 + i * 0.4) for i in range(BANDS)]
                peaks = [min(16, l + 2) for l in levels]
                sender.submit(frame(levels, peaks, t * 0.05))
                if time.time() - last_stats >= 5:
                    print(sender.stats(time.time() - last_stats)); last_stats = time.time()
        except KeyboardInterrupt:
            pass
        finally:
            sender.stop()
            remove()
        return

    import numpy as np
    import sounddevice as sd

    if a.list:
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0:
                print(i, d["name"])
        return

    dev = None
    if a.device.isdigit():
        dev = int(a.device)
    else:
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0 and a.device.lower() in d["name"].lower():
                dev = i; break
    if dev is None:
        print("Input device not found; --list shows the available devices", file=sys.stderr); sys.exit(1)
    print("Input:", sd.query_devices(dev)["name"], "| clock:", CLOCK, "| Ctrl+C stops")

    edges = band_edges()
    centers = [math.sqrt(edges[i] * edges[i + 1]) for i in range(BANDS)]
    freqs_hi = np.fft.rfftfreq(BLOCK, 1 / RATE)
    freqs_lo = np.fft.rfftfreq(BASS_BLOCK, 1 / RATE)
    use_lo = [c < BASS_SPLIT for c in centers]
    idx = []
    for i in range(BANDS):
        f = freqs_lo if use_lo[i] else freqs_hi
        idx.append(np.where((f >= edges[i]) & (f < edges[i + 1]))[0])
    win_hi = np.hanning(BLOCK)
    win_lo = np.hanning(BASS_BLOCK)
    # treble boost: music carries far more energy in the bass; without compensation snares and claps stay small.
    boost_db = [min(18.0, max(0.0, a.tilt * math.log2(c / 200.0))) for c in centers]
    # treble decays faster than bass so hits flash instead of smearing
    decay = [0.6 if c < 320 else 0.45 for c in centers]
    ring = np.zeros(BASS_BLOCK, dtype=np.float32)      # ring buffer for the long bass window
    latest = {"buf": None, "ring": ring}

    def cb(indata, frames, t, status):
        mono = indata[:, chan - 1].copy()
        latest["buf"] = mono
        latest["ring"] = np.concatenate((latest["ring"][len(mono):], mono))

    quiet_since = None      # moment since which the input has been quiet
    idle = False

    chan = max(1, a.channel)
    maxch = int(sd.query_devices(dev)["max_input_channels"])
    if chan > maxch:
        print(f"Kanal {chan} gibt es nicht, das Geraet hat {maxch}" if "en" == "de" else f"channel {chan} does not exist, the device has {maxch}", file=sys.stderr); sys.exit(1)
    with sd.InputStream(device=dev, channels=chan, samplerate=RATE, blocksize=BLOCK, callback=cb):
        try:
            rms_db = -99.0
            peak_px = 0.0
            prev_targets = None
            motion_ema = 9.0        # starts "moving" so the idle animation does not kick in immediately
            for _ in paced(a.fps, t0, a.seconds):
                buf = latest["buf"]
                targets = None
                if buf is not None:
                    rms_db = 20 * math.log10(float(np.sqrt(np.mean(buf * buf))) * a.gain + 1e-9)
                    spec_hi = np.abs(np.fft.rfft(buf * win_hi)) / BLOCK
                    spec_lo = np.abs(np.fft.rfft(latest["ring"] * win_lo)) / BASS_BLOCK
                    targets = []
                    for i in range(BANDS):
                        spec, freqs = (spec_lo, freqs_lo) if use_lo[i] else (spec_hi, freqs_hi)
                        if len(idx[i]):
                            mag = spec[idx[i]].max()
                        else:                                    # narrow band without its own FFT bin: interpolate
                            mag = float(np.interp(centers[i], freqs, spec))
                        db = 20 * math.log10(mag * a.gain + 1e-9) + boost_db[i]
                        targets.append(max(0.0, min(16.0, (db + 60) / 60 * 16)))   # -60 dB .. 0 dB -> 0..16 px
                    # detect silence via motion: music changes the spectrum constantly,
                    # noise and hum stand still. Averaged over about one second.
                    peak_px = max(targets)
                    if prev_targets is not None:
                        motion = sum(abs(t - p) for t, p in zip(targets, prev_targets)) / BANDS
                        motion_ema = motion_ema * 0.95 + motion * 0.05
                    prev_targets = targets
                    now = time.time()
                    # hysteresis: enter on little motion, leave only on clearly more (music), so it does not flicker
                    if idle:
                        if motion_ema > a.idle_motion * 1.6 or peak_px >= 14:
                            idle = False
                            quiet_since = None
                    elif motion_ema < a.idle_motion and peak_px < 14:
                        quiet_since = quiet_since or now
                        if now - quiet_since > a.idle_after:
                            idle = True
                    else:
                        quiet_since = None
                if idle:
                    lv = idle_wave(time.time() - t0)
                    for i in range(BANDS):
                        levels[i] = lv[i]
                        peaks[i] = max(lv[i] + 1, peaks[i] - 0.3)
                elif targets is not None:
                    update_levels(targets, levels, peaks, decay)
                sender.submit(frame(levels, peaks, (time.time() - t0) * 0.02))
                if time.time() - last_stats >= 5:
                    pegel = f"level {rms_db:.0f} dBFS, tallest bar {peak_px:.1f} px, motion {motion_ema:.2f}" if buf is not None else "no audio"
                    print(sender.stats(time.time() - last_stats), "|", pegel, "| idle animation" if idle else "| music")
                    last_stats = time.time()
        except KeyboardInterrupt:
            pass
        finally:
            sender.stop()
            remove()


if __name__ == "__main__":
    main()
