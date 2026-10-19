"""The README header: a wall of the viewer's example tiles, all playing, behind dark glass with the title, the list's
numbers and the update date. -> docs/assets/banner.webp (animated, 1800 x 600).

    python -m tools.banner [--updated "October 20, 2026"]     # new text over the saved background (needs Chrome)
    python -m tools.banner --background                       # also rebuild the background from the example thumbnails
    python -m tools.banner --social                           # also the still social card (Space thumbnail, link previews)

The background (the tile wall, no glass, no text) is kept in docs/assets/banner-bg.webp so the look stays fixed; an
update only re-renders the text layer. Tiles come from datasets above the quality bar, bodies and meshes first (3 of
every 4 tiles), no dataset twice in a row. The glass and the type are rendered by headless Chrome as one transparent
layer and laid over every frame. The date defaults to today, US style.
"""
import argparse
import datetime
import json
import os
import random
import subprocess
import tempfile

from PIL import Image, ImageEnhance

from . import config, registry, stats

W, H, TILE, GAP, FRAMES, MS = 1800, 600, 100, 3, 30, 100
OUT = os.path.join(config.REPO, 'docs', 'assets', 'banner.webp')
BG = os.path.join(config.REPO, 'docs', 'assets', 'banner-bg.webp')
SOCIAL = os.path.join(config.REPO, 'docs', 'assets', 'social.png')     # 1200 x 630, the og:image ratio
EXAMPLES = os.path.join(config.REPO, 'viewer', 'examples')

OVERLAY = '''<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;600;800&display=swap" rel="stylesheet">
<style>
  html,body{{margin:0;width:{w}px;height:{h}px;overflow:hidden;background:transparent}}
  .glass{{position:absolute;inset:0;background:
      linear-gradient(90deg, rgba(8,10,14,.96) 0%, rgba(8,10,14,.90) 38%, rgba(8,10,14,.70) 70%, rgba(8,10,14,.55) 100%),
      radial-gradient(120% 140% at 70% 50%, rgba(8,10,14,0) 40%, rgba(8,10,14,.75) 100%)}}
  .tint{{position:absolute;inset:0;background:linear-gradient(180deg, rgba(42,120,214,.10), rgba(42,120,214,0) 45%, rgba(0,0,0,.35))}}
  .text{{position:absolute;left:110px;top:{top}px;font-family:Inter,-apple-system,'SF Pro Display',Helvetica,sans-serif;color:#f4f6f8}}
  .kicker{{font-size:22px;font-weight:600;letter-spacing:.32em;text-transform:uppercase;color:#6aa8f0}}
  h1{{margin:22px 0 0;font-size:92px;font-weight:800;letter-spacing:-.035em;line-height:1}}
  .rule{{width:120px;height:3px;background:#3987e5;margin:34px 0 30px;border-radius:2px}}
  .stats{{font-size:28px;font-weight:300;color:#c9d1db}} .stats b{{font-weight:600;color:#fff}} .stats span{{color:#56606c;margin:0 16px}}
  .updated{{margin-top:22px;font-size:17px;font-weight:300;letter-spacing:.04em;color:#7d8794}}
</style></head><body><div class="glass"></div><div class="tint"></div>
<div class="text"><div class="kicker">Animation data, measured, verified and latest</div><h1>Awesome Animation Datasets</h1><div class="rule"></div>
<div class="stats"><b>{n}</b> datasets<span>·</span><b>{hours}</b> hours of motion<span>·</span><b>{clips}</b> clips</div>
<div class="updated">Last updated {updated}</div></div>
</body></html>'''


def tiles(n, seed=11):
    man = json.load(open(os.path.join(EXAMPLES, 'manifest.json')))
    ok = {d['id'] for d in registry.datasets() if registry.passes(d)}
    mesh, bare = [], []
    for d in man['datasets']:
        if d['id'] in ok:
            for e in d['examples']:
                p = os.path.join(EXAMPLES, e['thumb'])
                if os.path.exists(p):
                    (mesh if e.get('mesh') else bare).append((d['id'], p))
    rnd = random.Random(seed); rnd.shuffle(mesh); rnd.shuffle(bare)
    def spread(items):                                   # no dataset twice in a row
        out, pool = [], list(items)
        while pool:
            k = next((i for i, (d, _) in enumerate(pool) if not out or d != out[-1][0]), 0); out.append(pool.pop(k))
        return out
    mesh, bare = spread(mesh), spread(bare)
    return [(bare.pop() if k % 4 == 3 and bare else mesh.pop() if mesh else bare.pop())[1] for k in range(n) if mesh or bare]


def overlay(s, updated, w=W, h=H, top=150):
    clips = s['clips']
    html = OVERLAY.format(w=w, h=h, top=top, n=s['datasets'], hours=f"{s['hours']:,.0f}", updated=updated,
                          clips=f'{clips / 1000:,.0f}k' if clips >= 10000 else f'{clips:,}')
    d = tempfile.mkdtemp()
    open(os.path.join(d, 'o.html'), 'w').write(html)
    png = os.path.join(d, 'o.png')
    subprocess.run([config.get('chrome'), '--headless=new', '--disable-gpu', '--hide-scrollbars', f'--window-size={w},{h}',
                    '--default-background-color=00000000', '--virtual-time-budget=5000', f'--screenshot={png}',
                    'file://' + os.path.join(d, 'o.html')], capture_output=True, timeout=120)
    return Image.open(png).convert('RGBA')


def wall(h, ks):
    """the tile wall at frames ks, h px tall"""
    cols, rows = W // (TILE + GAP) + 2, h // (TILE + GAP) + 2
    seqs = []
    for p in tiles(cols * rows):                         # every tile's frames, desaturated a little
        im, fr = Image.open(p), []
        for k in ks:
            im.seek(min(k, getattr(im, 'n_frames', 1) - 1))
            fr.append(ImageEnhance.Color(im.convert('RGB').resize((TILE, TILE), Image.LANCZOS)).enhance(0.55))
        seqs.append(fr)
    frames = []
    for k in range(len(ks)):
        c = Image.new('RGB', (W, h), (12, 14, 18))
        for i, fr in enumerate(seqs):
            r, q = divmod(i, cols); c.paste(fr[k], (q * (TILE + GAP) - 20, r * (TILE + GAP) - 30))
        frames.append(c)
    return frames, len(seqs)


def background():
    """the tile wall, every frame, saved to BG (kept: later updates reuse it)"""
    frames, n = wall(H, range(FRAMES))
    frames[0].save(BG, save_all=True, append_images=frames[1:], duration=MS, loop=0, quality=90, method=6)
    print(f'{n} tiles -> {os.path.relpath(BG, config.REPO)} ({os.path.getsize(BG) / 1e6:.1f} MB)')


def social(s, updated):
    """one still at the link-preview ratio: the wall a little taller, the same glass and type, scaled to 1200 x 630"""
    h = round(W * 630 / 1200)
    im = Image.alpha_composite(wall(h, [15])[0][0].convert('RGBA'), overlay(s, updated, W, h, top=(h - 300) // 2))
    im.convert('RGB').resize((1200, 630), Image.LANCZOS).save(SOCIAL, optimize=True)
    print(f'-> {os.path.relpath(SOCIAL, config.REPO)} ({os.path.getsize(SOCIAL) / 1e6:.1f} MB)')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--background', action='store_true', help='rebuild the tile wall from the example thumbnails')
    ap.add_argument('--social', action='store_true', help='also render the still social card (needs the example thumbnails)')
    ap.add_argument('--updated', default=datetime.date.today().strftime('%B %-d, %Y'), help='the date shown, e.g. "October 20, 2026"')
    a = ap.parse_args()
    if a.background or not os.path.exists(BG):
        background()
    s = stats.compute()
    if a.social:
        social(s, a.updated)
    glass = overlay(s, a.updated)
    bg, frames = Image.open(BG), []
    for k in range(bg.n_frames):
        bg.seek(k); frames.append(Image.alpha_composite(bg.convert('RGBA'), glass).convert('RGB'))
    frames[0].save(OUT, save_all=True, append_images=frames[1:], duration=MS, loop=0, quality=72, method=6)
    print(f'{len(frames)} frames, updated {a.updated} -> {os.path.relpath(OUT, config.REPO)} ({os.path.getsize(OUT) / 1e6:.1f} MB)')


if __name__ == '__main__':
    main()
