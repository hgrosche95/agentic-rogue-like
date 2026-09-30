"""Cut recorded gameplay frames, text cards and effects into the trailer.

Usage: python3 compose.py timeline.py out.mp4 [--preview]
The timeline module defines SHOTS and TEXTS (see timeline.py).
"""
import json, sys, subprocess, math, importlib.util, os
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

W, H, FPS = 1920, 1080, 30
HERE = os.path.dirname(os.path.abspath(__file__))
FFMPEG = __import__('imageio_ffmpeg').get_ffmpeg_exe()

spec = importlib.util.spec_from_file_location('tl', sys.argv[1]); tl = importlib.util.module_from_spec(spec); spec.loader.exec_module(tl)
OUT = sys.argv[2]
PREVIEW = '--preview' in sys.argv
SCALE = 0.5 if PREVIEW else 1.0
OW, OH = int(W * SCALE), int(H * SCALE)


def font(name, size, weight='Black'):
    f = ImageFont.truetype(os.path.join(HERE, 'fonts', name), int(size * SCALE))
    try:
        f.set_variation_by_name(weight)
    except Exception:
        pass
    return f


ORB = lambda s, w='Black': font('Orbitron%5Bwght%5D.ttf', s, w)
MONO = lambda s, w='Bold': font('JetBrainsMono%5Bwght%5D.ttf', s, w)

# ------------------------------------------------------------------ sources
_rec_cache = {}


def rec(name):
    if name not in _rec_cache:
        fr = json.load(open(os.path.join(HERE, name, 'frames.json')))
        t0 = fr[0][1]
        ts = np.array([x[1] - t0 for x in fr])
        _rec_cache[name] = (fr, ts)
    return _rec_cache[name]


_img_cache = {}


def frame_at(name, t):
    fr, ts = rec(name)
    i = max(0, int(np.searchsorted(ts, t, side='right')) - 1)
    key = (name, i)
    if key not in _img_cache:
        if len(_img_cache) > 40:
            _img_cache.clear()
        im = Image.open(os.path.join(HERE, name, 'frames', fr[i][0])).convert('RGB')
        if im.size != (W, H):
            im = im.resize((W, H), Image.LANCZOS)
        _img_cache[key] = im
    return _img_cache[key]


def ease(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def kenburns(im, z, cx, cy):
    """Crop a W/z x H/z window centred near (cx, cy) (0..1) and scale to output."""
    cw, ch = W / z, H / z
    x0 = min(max(cx * W - cw / 2, 0), W - cw)
    y0 = min(max(cy * H - ch / 2, 0), H - ch)
    return im.resize((OW, OH), Image.BICUBIC, box=(x0, y0, x0 + cw, y0 + ch))


# ------------------------------------------------------------------ effects
_vig = None


def vignette():
    global _vig
    if _vig is None:
        y, x = np.mgrid[0:OH, 0:OW]
        d = np.sqrt(((x - OW / 2) / (OW / 2)) ** 2 + ((y - OH / 2) / (OH / 2)) ** 2)
        _vig = np.clip(1.15 - 0.45 * d ** 2, 0.35, 1.0)[..., None].astype(np.float32)
    return _vig


def glitch(arr, amount, seed):
    r = np.random.default_rng(seed)
    out = arr.copy()
    sh = int(18 * amount * SCALE) + 1
    out[..., 0] = np.roll(arr[..., 0], sh, axis=1)
    out[..., 2] = np.roll(arr[..., 2], -sh, axis=1)
    for _ in range(int(10 * amount)):
        y = r.integers(0, OH - 10); h = r.integers(4, int(60 * SCALE) + 5)
        out[y:y + h] = np.roll(out[y:y + h], r.integers(-80, 80) * SCALE, axis=1)
    return out


def glow_text(size, lines, fnt, color=(255, 255, 255), glow=(0, 229, 255), spacing=0, tracking=0, yc=0.5):
    """Render text lines with letter tracking and a coloured glow; returns RGBA."""
    img = Image.new('L', size, 0)
    d = ImageDraw.Draw(img)
    heights = [fnt.getbbox('Ag')[3] for _ in lines]
    total = sum(heights) + spacing * (len(lines) - 1)
    y = size[1] * yc - total / 2
    for ln, h in zip(lines, heights):
        widths = [fnt.getlength(c) + tracking for c in ln]
        x = (size[0] - (sum(widths) - tracking)) / 2
        for c, w in zip(ln, widths):
            d.text((x, y), c, font=fnt, fill=255)
            x += w
        y += h + spacing
    blur1 = img.filter(ImageFilter.GaussianBlur(14 * SCALE))
    blur2 = img.filter(ImageFilter.GaussianBlur(4 * SCALE))
    a = np.asarray(img, np.float32)[..., None] / 255
    g = np.clip(np.asarray(blur1, np.float32)[..., None] / 255 * 1.8 + np.asarray(blur2, np.float32)[..., None] / 255 * 0.8, 0, 1)
    rgb = np.array(color, np.float32) * a + np.array(glow, np.float32) * g * (1 - a)
    alpha = np.clip(a + g * 0.9, 0, 1)
    return np.concatenate([rgb, alpha * 255], -1)


_text_cache = {}


def text_layer(tx):
    key = id(tx)
    if key not in _text_cache:
        style = tx.get('style', 'title')
        lines = tx['lines']
        if style == 'title':
            f = ORB(tx.get('size', 84)); trk = int(tx.get('tracking', 10) * SCALE)
            col, gl = (255, 255, 255), tx.get('glow', (0, 229, 255))
        elif style == 'mono':
            f = MONO(tx.get('size', 40)); trk = int(4 * SCALE)
            col, gl = (230, 250, 255), tx.get('glow', (0, 229, 255))
        else:
            f = ORB(tx.get('size', 44), 'Bold'); trk = int(6 * SCALE)
            col, gl = (255, 255, 255), tx.get('glow', (255, 64, 190))
        _text_cache[key] = glow_text((OW, OH), lines, f, col, gl, int(tx.get('spacing', 18) * SCALE), trk, tx.get('y', 0.5))
    return _text_cache[key]


def over(base, rgba, alpha=1.0, dy=0.0):
    a = rgba[..., 3:4] / 255 * alpha
    src = rgba[..., :3]
    if dy:
        src = np.roll(src, int(dy), 0); a = np.roll(a, int(dy), 0)
    return base * (1 - a) + src * a


# ------------------------------------------------------------------ render
def render_frame(t):
    shot = None
    for s in tl.SHOTS:
        if s['at'] <= t < s['at'] + s['dur']:
            shot = s
    if shot is None:
        arr = np.zeros((OH, OW, 3), np.float32)
    else:
        local = t - shot['at']
        p = local / shot['dur']
        if shot.get('black'):
            arr = np.zeros((OH, OW, 3), np.float32)
        else:
            src_t = shot['src_t'] + local * shot.get('speed', 1.0)
            im = frame_at(shot['rec'], src_t)
            z0, z1 = shot.get('zoom', (1.0, 1.08))
            c0 = shot.get('c0', (0.5, 0.5)); c1 = shot.get('c1', c0)
            e = ease(p) if shot.get('ease', True) else p
            z = z0 + (z1 - z0) * e
            cx = c0[0] + (c1[0] - c0[0]) * e; cy = c0[1] + (c1[1] - c0[1]) * e
            arr = np.asarray(kenburns(im, z, cx, cy), np.float32)
            if shot.get('fade_bottom'):
                yy = np.linspace(0, 1, OH, dtype=np.float32)[:, None, None]
                arr *= np.clip(1 - (yy - shot['fade_bottom']) / 0.08, 0.0, 1)
            if shot.get('dim'):
                arr *= shot['dim']
        # fades
        fi, fo = shot.get('fade_in', 0), shot.get('fade_out', 0)
        k = 1.0
        if fi: k *= ease(local / fi)
        if fo: k *= ease((shot['dur'] - local) / fo)
        arr *= k
        # glitch at shot start
        gl = shot.get('glitch_in', 0.18)
        if gl and local < gl:
            arr = glitch(arr, 1.0 - local / gl, int(t * 1000))
    for tx in tl.TEXTS:
        if tx['at'] <= t < tx['at'] + tx['dur']:
            local = t - tx['at']
            a = ease(local / 0.25) * ease((tx['dur'] - local) / 0.3)
            dim = tx.get('backdrop', 0.45)
            if dim:
                arr = arr * (1 - dim * a)
            layer = text_layer(tx)
            dy = (1 - ease(local / 0.4)) * 20 * SCALE
            if local < 0.15 or (tx['dur'] - local) < 0.1:
                g = glitch(layer[..., :3], 0.8, int(t * 997))
                layer = np.concatenate([g, layer[..., 3:]], -1)
            arr = over(arr, layer, a, dy)
    for fl in getattr(tl, 'FLASHES', []):
        if fl['at'] <= t < fl['at'] + fl['dur']:
            k = 1 - (t - fl['at']) / fl['dur']
            col = np.array(fl.get('color', (255, 255, 255)), np.float32)
            arr = arr * (1 - k * fl.get('amt', 0.9)) + col * k * fl.get('amt', 0.9)
    arr = arr * vignette()
    bars = int(getattr(tl, 'LETTERBOX', 0) * SCALE)
    if bars:
        arr[:bars] = 0; arr[-bars:] = 0
    # film grain
    arr += np.random.default_rng(int(t * 30)).normal(0, 3.5, (OH, OW, 1)).astype(np.float32)
    return np.clip(arr, 0, 255).astype(np.uint8)


def main():
    dur = tl.DURATION
    nframes = int(dur * FPS)
    only = [a for a in sys.argv if a.startswith('--frames=')]
    if only:
        for tt in only[0][9:].split(','):
            Image.fromarray(render_frame(float(tt))).save(os.path.join(HERE, f'still_{tt}.jpg'), quality=90)
        return
    cmd = [FFMPEG, '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{OW}x{OH}', '-r', str(FPS), '-i', '-',
           '-i', os.path.join(HERE, tl.AUDIO), '-map', '0:v', '-map', '1:a', '-t', str(dur),
           '-c:v', 'libx264', '-preset', 'medium' if not PREVIEW else 'veryfast', '-crf', '17' if not PREVIEW else '26',
           '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '256k', '-movflags', '+faststart', OUT]
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    for i in range(nframes):
        pr.stdin.write(render_frame(i / FPS).tobytes())
        if i % 150 == 0:
            print(f'{i}/{nframes}', flush=True)
    pr.stdin.close(); pr.wait()
    print('done', OUT)


main()
