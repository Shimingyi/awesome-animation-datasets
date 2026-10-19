"""Animated card thumbnails: each example rendered by the viewer itself (viewer/index.html?thumb=<id>, no UI) in headless
Chrome, frame by frame, saved as an animated WebP. Also writes the README's per-dataset previews and a contact sheet.

    python -m tools.examples.thumbs [ids ...] [--force] [--sheet]

viewer/examples/thumbs/<dataset>/<example>.webp     card thumbnails (SIZE px, PREVIEW_S seconds at PREVIEW_FPS)
docs/assets/thumbs/<dataset>.webp                   the first N_DOC examples side by side (README tables); <dataset>-1.webp the first alone
build/contact_sheet.png                             (--sheet) first frame of every example, to eyeball them all at once
"""
import argparse
import asyncio
import base64
import functools
import http.server
import io
import json
import os
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request

from PIL import Image

from .. import config
from . import spec

VIEWER = os.path.join(config.REPO, 'viewer')
EXAMPLES = os.path.join(VIEWER, 'examples')
DOC_THUMBS = os.path.join(config.REPO, 'docs', 'assets', 'thumbs')
SIZE = 240
DOC_SIZE = 220
N_DOC = 3                 # README previews per dataset
PREVIEW_S = 3.0
PREVIEW_FPS = 10


def _free_port():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); p = s.getsockname()[1]; s.close(); return p


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve_viewer():
    """a static server on viewer/ (the page must be loaded over http for its module imports and fetches)"""
    port = _free_port()
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', port), functools.partial(_Quiet, directory=VIEWER))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f'http://127.0.0.1:{port}'


class Chrome:
    """one headless Chrome with a DevTools port"""
    def __init__(self):
        self.port = _free_port()
        self.dir = tempfile.mkdtemp(prefix='aad_thumbs_')
        self.proc = subprocess.Popen([config.get('chrome'), '--headless=new', '--use-angle=swiftshader', '--enable-unsafe-swiftshader',
                                      '--hide-scrollbars', f'--remote-debugging-port={self.port}', f'--user-data-dir={self.dir}', 'about:blank'],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                tabs = json.load(urllib.request.urlopen(f'http://127.0.0.1:{self.port}/json'))
                self.ws = [t for t in tabs if t['type'] == 'page'][0]['webSocketDebuggerUrl']
                return
            except Exception:  # noqa: BLE001
                time.sleep(0.1)
        raise RuntimeError('headless Chrome did not start (set `chrome:` in config.local.yaml)')

    def close(self):
        self.proc.terminate()


async def _render(ws_url, base, jobs, size):
    """jobs: [(example id, out path)] -> rendered sequentially in one tab"""
    import websockets
    async with websockets.connect(ws_url, max_size=2 ** 27) as ws:
        n = 0

        async def send(m, p=None):
            nonlocal n; n += 1; my = n
            await ws.send(json.dumps({'id': my, 'method': m, 'params': p or {}}))
            while True:
                r = json.loads(await ws.recv())
                if r.get('id') == my:
                    return r

        async def ev(expr):
            r = await send('Runtime.evaluate', {'expression': expr, 'returnByValue': True, 'awaitPromise': True})
            return r['result']['result'].get('value')
        await send('Emulation.setDeviceMetricsOverride', {'width': size, 'height': size, 'deviceScaleFactor': 1, 'mobile': False})
        for ex_id, out in jobs:
            await send('Page.navigate', {'url': f'{base}/index.html?thumb={ex_id}&theme=light'})
            ok = False
            for _ in range(400):
                await asyncio.sleep(0.05)
                if await ev('window.__ready === true'):
                    ok = True; break
            if not ok:
                print(f'  ! {ex_id}: viewer not ready (timeout)'); continue
            info = await ev('window.__info')
            dur = min(PREVIEW_S, info['duration'])
            times = [i / PREVIEW_FPS for i in range(max(1, int(dur * PREVIEW_FPS)))]
            imgs = []
            for tt in times:
                await ev(f'window.__frame({tt})')
                r = await send('Page.captureScreenshot', {'format': 'png'})
                imgs.append(Image.open(io.BytesIO(base64.b64decode(r['result']['data']))).convert('RGB'))
            os.makedirs(os.path.dirname(out), exist_ok=True)
            imgs[0].save(out, save_all=True, append_images=imgs[1:], duration=int(1000 / PREVIEW_FPS), loop=0, quality=72, method=4)
            print(f'  {ex_id}: {len(imgs)} frames', flush=True)


def doc_thumb(src, dst, size=DOC_SIZE):
    """a smaller copy of an animated WebP"""
    im = Image.open(src); frames, durs = [], []
    try:
        while True:
            frames.append(im.convert('RGB').resize((size, size), Image.LANCZOS)); durs.append(im.info.get('duration', 80)); im.seek(im.tell() + 1)
    except EOFError:
        pass
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    frames[0].save(dst, save_all=True, append_images=frames[1:], duration=durs, loop=0, quality=65, method=6)


def frames_of(path, size):
    im = Image.open(path); out, durs = [], []
    try:
        while True:
            out.append(im.convert('RGB').resize((size, size), Image.LANCZOS)); durs.append(im.info.get('duration', 100)); im.seek(im.tell() + 1)
    except EOFError:
        pass
    return out, durs


def doc_strip(srcs, dst, size=DOC_SIZE, gap=4):
    """several animated thumbnails side by side in one animated WebP (a README table cell cannot keep separate images on
    one line); shorter clips hold their last frame"""
    seqs = [frames_of(p, size) for p in srcs]
    n = max(len(f) for f, _ in seqs)
    w = len(seqs) * size + (len(seqs) - 1) * gap
    out = []
    for i in range(n):
        im = Image.new('RGB', (w, size), 'white')
        for k, (fr, _) in enumerate(seqs):
            im.paste(fr[min(i, len(fr) - 1)], (k * (size + gap), 0))
        out.append(im)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    out[0].save(dst, save_all=True, append_images=out[1:], duration=seqs[0][1][0] if seqs[0][1] else 100, loop=0, quality=65, method=6)


def contact_sheet(man, out, cell=120):
    rows = [d for d in man['datasets'] if d['examples']]
    sheet = Image.new('RGB', (cell * 10 + 220, cell * len(rows)), 'white')
    from PIL import ImageDraw
    dr = ImageDraw.Draw(sheet)
    for r, d in enumerate(rows):
        dr.text((6, r * cell + cell // 2), d['id'], fill='black')
        for c, e in enumerate(d['examples'][:10]):
            p = os.path.join(EXAMPLES, e['thumb'])
            if os.path.exists(p):
                im = Image.open(p)
                im.seek(getattr(im, 'n_frames', 1) // 2)                     # the middle frame: the clip in motion
                sheet.paste(im.convert('RGB').resize((cell, cell)), (220 + c * cell, r * cell))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sheet.save(out)
    return out


def render_all(ids=None, force=False, sheet=False, workers=4):
    with open(os.path.join(EXAMPLES, 'manifest.json')) as f:
        man = json.load(f)
    jobs = []
    for d in man['datasets']:
        if ids and d['id'] not in ids:
            continue
        for e in d['examples']:
            out = os.path.join(EXAMPLES, e['thumb'])
            if force or not os.path.exists(out):
                jobs.append((e['id'], out))
    if jobs:                                            # software WebGL is slow: several Chromes, one share of the jobs each
        srv, base = serve_viewer()
        chromes = [Chrome() for _ in range(max(1, min(workers, len(jobs))))]

        async def run_all():
            await asyncio.gather(*(_render(c.ws, base, jobs[i::len(chromes)], SIZE) for i, c in enumerate(chromes)))
        try:
            asyncio.run(run_all())
        finally:
            for c in chromes:
                c.close()
            srv.shutdown()
    used = {os.path.normpath(os.path.join(EXAMPLES, e['thumb'])) for d in man['datasets'] for e in d['examples']}
    for dp, _, fs in os.walk(os.path.join(EXAMPLES, 'thumbs')):      # cards of examples that are gone
        for f in fs:
            if os.path.normpath(os.path.join(dp, f)) not in used:
                os.unlink(os.path.join(dp, f))
    docs_used = {f"{d['id']}{suf}.webp" for d in man['datasets'] if d['examples'] and spec.published(d['id']) for suf in ('', '-1')}
    for f in os.listdir(DOC_THUMBS) if os.path.isdir(DOC_THUMBS) else []:
        if f not in docs_used:
            os.unlink(os.path.join(DOC_THUMBS, f))
    for d in man['datasets']:                           # README: a strip of the first N_DOC examples + the first one alone
        if (not ids or d['id'] in ids) and spec.published(d['id']):
            srcs = [p for p in (os.path.join(EXAMPLES, e['thumb']) for e in d['examples'][:N_DOC]) if os.path.exists(p)]
            if srcs:
                doc_strip(srcs, os.path.join(DOC_THUMBS, f"{d['id']}.webp"))
                doc_thumb(srcs[0], os.path.join(DOC_THUMBS, f"{d['id']}-1.webp"))
    if sheet:
        print('contact sheet:', contact_sheet(man, os.path.join(config.REPO, 'build', 'contact_sheet.png')))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ids', nargs='*')
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--sheet', action='store_true', help='also write build/contact_sheet.png')
    ap.add_argument('--workers', type=int, default=max(1, min(6, (os.cpu_count() or 4) // 2)), help='parallel headless Chromes')
    a = ap.parse_args()
    render_all(a.ids or None, a.force, a.sheet, a.workers)


if __name__ == '__main__':
    main()
