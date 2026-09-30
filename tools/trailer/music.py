"""Procedural trailer score for Agentic Rogue, 120 BPM, A minor.

Timeline (seconds, one bar = 2 s):
  0-8    dark drone + heartbeat sub
  8      BRAAM (the rift opens)
  8-16   drone, ticking, typing glitches
  16-20  riser + snare roll, cut to silence at 19.75
  20-52  DROP: four-on-the-floor, bass, arp, chords
  52-56  breakdown (low-passed)
  56-60  riser 2
  60-68  final drop
  68     final BRAAM + tail
"""
import numpy as np
from scipy.signal import butter, sosfilt, fftconvolve
import wave, sys

SR = 48000
DUR = 78.0
N = int(SR * DUR)
BEAT = 0.5
rng = np.random.default_rng(7)

L = np.zeros(N); R = np.zeros(N)


def t_arr(d):
    return np.arange(int(SR * d)) / SR


def add(sig, at, gain=1.0, pan=0.0):
    i = int(at * SR)
    if i >= N:
        return
    s = sig[: N - i] * gain
    lg = np.cos((pan + 1) * np.pi / 4); rg = np.sin((pan + 1) * np.pi / 4)
    L[i:i + len(s)] += s * lg * 1.414
    R[i:i + len(s)] += s * rg * 1.414


def lp(x, f, order=2):
    return sosfilt(butter(order, f, 'low', fs=SR, output='sos'), x)


def hp(x, f, order=2):
    return sosfilt(butter(order, f, 'high', fs=SR, output='sos'), x)


def bp(x, lo, hi):
    return sosfilt(butter(2, [lo, hi], 'band', fs=SR, output='sos'), x)


def saw(f, t):
    ph = np.cumsum(np.broadcast_to(f, t.shape) / SR) if np.ndim(f) else f * t
    return 2 * (ph % 1) - 1


def env_adsr(n, a, d, s, r, sus_len=None):
    a, d, r = int(a * SR), int(d * SR), int(r * SR)
    sus = n - a - d - r if sus_len is None else int(sus_len * SR)
    sus = max(sus, 0)
    e = np.concatenate([np.linspace(0, 1, a, endpoint=False), np.linspace(1, s, d, endpoint=False),
                        np.full(sus, s), np.linspace(s, 0, r)])
    return np.pad(e, (0, max(0, n - len(e))))[:n]


def midi(m):
    return 440 * 2 ** ((m - 69) / 12)


# ---------------------------------------------------------------- instruments
def kick(g=1.0):
    t = t_arr(0.45)
    f = 45 + 110 * np.exp(-t * 28)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7)
    click = hp(rng.standard_normal(len(t)), 2000) * np.exp(-t * 300) * 0.3
    return np.tanh((s + click) * 1.6) * g


def snare():
    t = t_arr(0.35)
    body = np.sin(2 * np.pi * 190 * t) * np.exp(-t * 25)
    n = bp(rng.standard_normal(len(t)), 1500, 9000) * np.exp(-t * 14)
    return body * 0.5 + n * 0.8


def hat(open_=False):
    t = t_arr(0.25 if open_ else 0.06)
    return hp(rng.standard_normal(len(t)), 8000) * np.exp(-t * (12 if open_ else 70)) * 0.35


def clap():
    t = t_arr(0.3)
    n = bp(rng.standard_normal(len(t)), 900, 5000)
    e = np.zeros(len(t))
    for k in (0, 0.012, 0.024):
        e += np.exp(-np.clip(t - k, 0, None) * 60) * (t >= k)
    e += np.exp(-t * 12) * 0.5
    return n * e * 0.6


def braam(root=33, d=6.0):
    t = t_arr(d)
    sig = np.zeros(len(t))
    for m, g in [(root, 1.0), (root + 12, 0.7), (root + 19, 0.35), (root - 12, 0.9)]:
        for det in (-0.12, 0, 0.13):
            sig += saw(midi(m + det), t) * g
    cutoff_env = 200 + 2500 * np.exp(-t * 1.2)
    # time-varying lowpass via short blocks
    out = np.zeros_like(sig)
    blk = 2048
    zi = None
    for i in range(0, len(sig), blk):
        sos = butter(2, cutoff_env[i], 'low', fs=SR, output='sos')
        from scipy.signal import sosfilt_zi
        if zi is None:
            zi = np.zeros((sos.shape[0], 2))
        out[i:i + blk], zi = sosfilt(sos, sig[i:i + blk], zi=zi)
    e = np.minimum(t / 0.02, 1) * np.exp(-t * 0.55)
    sub = np.sin(2 * np.pi * midi(root - 12) * t) * np.exp(-t * 0.8)
    boom = kick(1.0)
    res = np.tanh(out * e * 0.35) + sub * 0.8
    res[:len(boom)] += boom * 1.2
    return res


def riser(d):
    t = t_arr(d)
    n = rng.standard_normal(len(t))
    out = np.zeros_like(n)
    blk = 1024
    zi = np.zeros((1, 2))
    for i in range(0, len(n), blk):
        fc = 300 * (40 ** (i / len(n)))
        sos = butter(2, [fc, min(fc * 1.6, 20000)], 'band', fs=SR, output='sos')
        if zi.shape[0] != sos.shape[0]:
            zi = np.zeros((sos.shape[0], 2))
        out[i:i + blk], zi = sosfilt(sos, n[i:i + blk], zi=zi)
    tone = saw(np.linspace(midi(45), midi(81), len(t)), t) * 0.15
    e = (t / d) ** 2
    return (out * 1.2 + lp(tone, 6000)) * e


def reverse_swell(d=2.0):
    t = t_arr(d)
    n = lp(rng.standard_normal(len(t)), 3000) * (t / d) ** 3
    return n * 0.6


def whoosh(d=0.6):
    t = t_arr(d)
    n = rng.standard_normal(len(t))
    e = np.sin(np.pi * t / d) ** 2
    return bp(n, 400, 4000) * e * 0.5


def glitch(d=0.25):
    t = t_arr(d)
    s = np.sign(np.sin(2 * np.pi * rng.uniform(200, 1400) * t)) * 0.3
    s *= (np.floor(t * 60) % 2)
    s += hp(rng.standard_normal(len(t)), 3000) * 0.3 * (np.floor(t * 90) % 3 == 0)
    return s * np.exp(-t * 6)


def type_click():
    t = t_arr(0.03)
    return hp(rng.standard_normal(len(t)), 2500) * np.exp(-t * 250) * 0.4


def pluck(m, d=0.35, bright=4000):
    t = t_arr(d)
    s = saw(midi(m), t) + saw(midi(m + 0.08), t) * 0.7
    s = lp(s, bright)
    return s * np.exp(-t * 9) * 0.25


def pad(ms, d, cutoff=1400):
    t = t_arr(d)
    s = np.zeros(len(t))
    for m in ms:
        for det in (-0.1, 0.1):
            s += saw(midi(m + det), t)
    s = lp(s, cutoff) / (len(ms) * 2)
    return s * env_adsr(len(t), 0.4, 0.2, 0.9, 0.8)


def bass_note(m, d):
    t = t_arr(d)
    s = saw(midi(m), t) * 0.6 + np.sin(2 * np.pi * midi(m) * t) * 0.8
    s = lp(s, 700)
    return np.tanh(s * 1.5) * env_adsr(len(t), 0.005, 0.1, 0.7, 0.05) * 0.5


# ---------------------------------------------------------------- arrangement
CHORDS = [  # A minor: Am F C G  -> darker: Am F Dm E
    (45, [57, 60, 64]), (41, [53, 57, 60]), (38, [50, 53, 57]), (40, [52, 56, 59]),
]

# Act 1: drone + heartbeat
drone_t = t_arr(20)
drone = np.zeros(len(drone_t))
for m in (33, 40, 45):
    for det in (-0.07, 0.07):
        drone += saw(midi(m + det), drone_t)
drone = lp(drone, 380) * 0.12
drone *= np.minimum(drone_t / 3, 1) * np.clip((19.75 - drone_t) / 0.1, 0, 1)
drone *= 1 + 0.25 * np.sin(2 * np.pi * 0.25 * drone_t)
add(drone, 0, 1.0)
for i in range(0, 8):  # heartbeat
    for off, g in ((0, 1.0), (0.22, 0.6)):
        add(lp(kick(0.9), 180), i * 2 + off + 0.5, g * 0.8)
add(reverse_swell(2.0), 6.0, 1.0)
add(braam(33, 7.0), 8.0, 0.9)
for i in range(16):  # clock ticks 8-16
    add(hat() * 0.8, 8 + i * 0.5 + 0.25, 0.7, pan=0.4 if i % 2 else -0.4)
for i in range(70):  # typing 11-15.5
    add(type_click(), 11.2 + i * 0.06 + rng.uniform(0, 0.03), 0.8, pan=rng.uniform(-0.3, 0.3))
add(glitch(0.4), 10.0, 0.7)
add(glitch(0.3), 14.0, 0.7)
# riser 16-19.75
add(riser(3.75), 16.0, 0.55)
for k in range(24):
    tt = 16 + 3.75 * (1 - (1 - k / 24) ** 1.6)
    add(snare(), tt, 0.25 + 0.5 * k / 24)
add(glitch(0.2), 19.55, 0.8)


def groove(start, bars, intensity=1.0, filt=None):
    seg_len = bars * 2.0
    n = int(seg_len * SR) + SR
    bufL = np.zeros(n)
    def put(sig, at, g=1.0):
        i = int(at * SR)
        s = sig[: n - i] * g
        bufL[i:i + len(s)] += s
    for b in range(bars):
        root, chord = CHORDS[(b // 1) % 4] if bars <= 2 else CHORDS[(b // 2) % 4]
        bt = b * 2.0
        for q in range(4):
            put(kick(), bt + q * BEAT, 0.9)
            put(bass_note(root, BEAT * 0.45), bt + q * BEAT + BEAT / 2, 0.8 * intensity)
            put(bass_note(root + 12, 0.1), bt + q * BEAT + BEAT * 0.75, 0.3 * intensity)
        for q in (1, 3):
            put(snare(), bt + q * BEAT, 0.55)
            put(clap(), bt + q * BEAT, 0.4)
        for s16 in range(16):
            put(hat(open_=(s16 % 4 == 2)), bt + s16 * BEAT / 4, (0.5 if s16 % 2 else 0.3) * intensity)
        arp = [chord[0], chord[1], chord[2], chord[1] + 12, chord[2] + 12, chord[1] + 12, chord[2], chord[1]]
        for s in range(16):
            put(pluck(arp[s % 8] + 12, 0.3, 3500 + 2000 * intensity), bt + s * BEAT / 4, 0.55)
        put(pad([c + 12 for c in chord], 2.0), bt, 0.35 * intensity)
    if filt:
        bufL = lp(bufL, filt, 4)
    # pseudo sidechain
    t = np.arange(n) / SR
    duck = 1 - 0.35 * np.exp(-((t % BEAT)) * 14)
    bufL *= duck
    add(bufL, start, 0.9)


groove(20, 16, 1.0)
# impacts every 8 s inside the drop
for tt in (20, 28, 36, 44):
    add(lp(braam(33, 3.0), 3000), tt, 0.35)
    add(reverse_swell(1.0), tt - 1.0, 0.5)
groove(52, 2, 0.6, filt=700)
add(pad([57, 60, 64], 4.0, 900), 52, 0.5)
add(riser(4.0), 56, 0.6)
for k in range(32):
    tt = 56 + 4.0 * (1 - (1 - k / 32) ** 1.5)
    add(snare(), tt, 0.2 + 0.5 * k / 32)
groove(60, 4, 1.15)
for tt in (60, 64):
    add(lp(braam(33, 3.0), 3500), tt, 0.4)
add(reverse_swell(1.5), 66.5, 0.8)
add(braam(33, 9.0), 68.0, 1.0)
add(glitch(0.5), 71.5, 0.5)

# ---------------------------------------------------------------- scene SFX (cut accents)
for tt in (22.0, 24.0, 26.0, 30.0, 32.0, 34.0, 38.0, 40.0, 42.0, 46.0, 48.0, 50.0, 62.0, 66.0):
    add(whoosh(0.5), tt - 0.3, 0.45, pan=rng.uniform(-0.5, 0.5))

# ---------------------------------------------------------------- reverb + master
def reverb(x, secs=2.2, mix=0.22):
    t = t_arr(secs)
    ir = rng.standard_normal(len(t)) * np.exp(-t * 3.2)
    ir = lp(ir, 5000)
    wet = fftconvolve(x, ir)[: len(x)]
    wet /= np.max(np.abs(wet)) + 1e-9
    return x + wet * mix * np.max(np.abs(x))

L = reverb(hp(L, 25)); R = reverb(hp(R, 25))
mx = max(np.max(np.abs(L)), np.max(np.abs(R)))
L, R = L / mx, R / mx
L = np.tanh(L * 1.6) / np.tanh(1.6) * 0.95
R = np.tanh(R * 1.6) / np.tanh(1.6) * 0.95
fade = np.clip((DUR - np.arange(N) / SR) / 3, 0, 1)
L *= fade; R *= fade
out = (np.stack([L, R], 1) * 32767).astype(np.int16)
with wave.open(sys.argv[1] if len(sys.argv) > 1 else 'score.wav', 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(out.tobytes())
print('ok')
