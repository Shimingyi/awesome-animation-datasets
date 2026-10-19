"""Local mode of the viewer: browse every dataset of a motion vault (<vault>/processed/<dataset>/_catalog.json + npz).

    python -m tools.vault.server [--root <vault>] [--port 8765]        then open http://127.0.0.1:8765/

GET /                   the viewer (viewer/index.html of this repo; it finds api/catalog and switches to local mode)
GET /<file>             any other file under viewer/ (js, css, baked examples)
GET /api/catalog        {datasets: [{name, clips: [...]}]}
GET /api/clip?id=       skeleton + channel layout of one clip (JSON)
GET /api/motion?id=     float32 little-endian (frames, channels) in BVH units
GET /api/bvh?id=        the original BVH, rebuilt from the npz (byte-identical, sha256-checked)
GET /api/mesh?id=       SMPL clips: shaped template, skinning weights, faces (binary)
GET /api/npz?id=        the stored npz file as it is
Ids are '<dataset>/<clip id>' and are looked up in the catalog; nothing is ever joined into a path from the request.
"""
import argparse
import gzip
import csv
import json
import os
import mimetypes
import threading
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import numpy as np

from .. import config
from . import bvhcodec as codec
from . import smplmodel as sm

VIEWER = os.path.join(config.REPO, 'viewer')
ROOT = config.get('vault')
_lock = threading.Lock()
_catalog = {'mtime': None, 'data': None, 'index': {}}
_cache = OrderedDict()
def _descriptions(ds_dir):
    """100style ships Dataset_List.csv (style -> description); pick up any such file."""
    out = {}
    for dp, _, fn in os.walk(ds_dir):
        for f in fn:
            if f == 'Dataset_List.csv':
                try:
                    for r in csv.DictReader(open(os.path.join(dp, f), encoding='utf-8-sig')):
                        if r.get('Style Name'):
                            out[r['Style Name']] = r.get('Description', '')
                except Exception:
                    pass
    return out


def catalog():
    pdir = os.path.join(ROOT, 'processed')
    files = [os.path.join(pdir, d, '_catalog.json') for d in sorted(os.listdir(pdir))] if os.path.isdir(pdir) else []
    files = [f for f in files if os.path.exists(f)]
    mt = tuple(os.path.getmtime(f) for f in files)
    with _lock:
        if _catalog['mtime'] != mt:
            data, index = [], {}
            for f in files:
                c = json.load(open(f)); ds = c['dataset']
                desc = _descriptions(os.path.dirname(f))
                for k in c['clips']:
                    k['id'] = ds + '/' + k['id']
                    k['desc'] = k.get('desc') or desc.get(k['group'], '')
                    index[k['id']] = os.path.join(pdir, k['id'] + '.npz')
                data.append(dict(name=ds, clips=c['clips']))
            _catalog.update(mtime=mt, data=data, index=index)
        return _catalog['data'], _catalog['index']


def load(cid):
    _, index = catalog()
    p = index.get(cid)
    if not p:
        return None
    with _lock:
        if cid in _cache:
            _cache.move_to_end(cid); return _cache[cid]
    with np.load(p) as z:
        z = {k: z[k] for k in z.files}
    with _lock:
        _cache[cid] = z
        while len(_cache) > 24:
            _cache.popitem(last=False)
    return z


_smpl_cache = OrderedDict()
_payload = {'mt': None, 'raw': b'', 'gz': b''}
SLIM = ('id', 'kind', 'name', 'collection', 'group', 'frames', 'fps', 'duration', 'joints', 'src_bytes', 'desc')


def catalog_payload():
    """The catalog as the page needs it (a few fields per clip), JSON + gzip, cached until a _catalog.json changes."""
    data, _ = catalog()
    with _lock:
        if _payload['mt'] != _catalog['mtime']:
            slim = [dict(name=d['name'], clips=[{k: c.get(k, '') for k in SLIM} for c in d['clips']]) for d in data]
            raw = json.dumps(dict(root=ROOT, datasets=slim), separators=(',', ':')).encode()
            _payload.update(mt=_catalog['mtime'], raw=raw, gz=gzip.compress(raw, 6))
        return _payload['raw'], _payload['gz']


def is_smpl(z):
    return 'format' not in z and 'poses' in z


def smpl_info(cid, z):
    """-> kind, model, v_shaped, rest joints for one SMPL clip (cached)."""
    if cid in _smpl_cache:
        return _smpl_cache[cid]
    kind = sm.pose_layout(z['poses'].shape[1])
    g = str(z['gender'].item() if hasattr(z['gender'], 'item') else z['gender']) if 'gender' in z else 'neutral'
    g = g.strip("b'\" ").lower() if g else 'neutral'
    m = sm.model(kind, g if g in ('male', 'female') else 'neutral', ROOT)
    v, J = sm.shape(m, z['betas'])
    _smpl_cache[cid] = (kind, m, v, J)
    while len(_smpl_cache) > 8:
        _smpl_cache.popitem(last=False)
    return _smpl_cache[cid]


def smpl_fps(z):
    for k in ('mocap_framerate', 'mocap_frame_rate', 'fps'):
        if k in z:
            return float(z[k])
    return 30.0


def smpl_meta(cid, z):
    kind, m, v, J = smpl_info(cid, z)
    par = m['parents'].astype(int)
    off = J.copy(); off[1:] -= J[par[1:]]
    return dict(id=cid, kind='smpl', model=kind, joint_names=sm.NAMES[kind], parents=par.tolist(), offsets=off.tolist(), rest=J.tolist(),
                frame_time=1.0 / smpl_fps(z), frames=int(z['poses'].shape[0]), mode='smpl-npz')


def smpl_motion(cid, z):
    kind = smpl_info(cid, z)[0]
    return np.concatenate([np.asarray(z['trans'], np.float32).reshape(-1, 3), sm.to_model_pose(z['poses'], kind)], axis=1)


def smpl_mesh(cid, z, K=6):
    """binary: u32 header length, JSON header (space padded to a multiple of 4), v_shaped f32, idx u8 (padded), w f32, faces u32."""
    kind, m, v, J = smpl_info(cid, z)
    idx, w = sm.skin_weights(m, K)
    F = m['faces'].astype(np.uint32)
    h = json.dumps(dict(V=int(len(v)), K=K, F=int(len(F)), J=int(len(J)))).encode()
    h += b' ' * ((-(4 + len(h))) % 4)
    ib = idx.tobytes(); ib += b'\0' * ((-len(ib)) % 4)
    return len(h).to_bytes(4, 'little') + h + v.astype('<f4').tobytes() + ib + w.astype('<f4').tobytes() + F.tobytes()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _static(self, path):
        """a file under viewer/ (the page, its scripts, baked examples); the resolved path must stay inside viewer/"""
        rel = path.lstrip('/') or 'index.html'
        p = os.path.realpath(os.path.join(VIEWER, rel))
        if os.path.isdir(p):
            p = os.path.join(p, 'index.html')
        if not p.startswith(os.path.realpath(VIEWER) + os.sep) or not os.path.isfile(p):
            return self._send(404, b'not found', 'text/plain')
        ctype = mimetypes.guess_type(p)[0] or 'application/octet-stream'
        if ctype.startswith('text/') or ctype.endswith(('javascript', 'json')):
            ctype += '; charset=utf-8'
        with open(p, 'rb') as f:
            return self._send(200, f.read(), ctype)

    def _send(self, code, body, ctype, extra=None):
        self.send_response(code)
        self.send_header('Content-Type', ctype); self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-cache')
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        try:
            if not u.path.startswith('/api/'):
                return self._static(u.path)
            if u.path == '/api/catalog':
                raw, gz = catalog_payload()
                if 'gzip' in self.headers.get('Accept-Encoding', ''):
                    return self._send(200, gz, 'application/json', {'Content-Encoding': 'gzip'})
                return self._send(200, raw, 'application/json')
            if u.path in ('/api/clip', '/api/motion', '/api/bvh', '/api/mesh', '/api/npz'):
                cid = q.get('id', [''])[0]
                z = load(cid)
                if z is None:
                    return self._send(404, b'unknown clip', 'text/plain')
                if u.path == '/api/npz':
                    return self._send(200, open(_catalog['index'][cid], 'rb').read(), 'application/octet-stream',
                                      {'Content-Disposition': f'attachment; filename="{cid.split("/")[-1]}.npz"'})
                if 'mv_kind' in z and str(z['mv_kind']) == 'joints':                 # joint positions (HumanML3D, KIT, animationGPT)
                    pos = z['positions']
                    if u.path == '/api/clip':
                        meta = dict(id=cid, kind='joints', joint_names=z['joint_names'].tolist(), parents=z['parents'].tolist(), offsets=[],
                                    frame_time=1.0 / float(z['fps']), frames=int(pos.shape[0]), mode='joints-v1')
                        return self._send(200, json.dumps(meta).encode(), 'application/json')
                    if u.path == '/api/motion':
                        return self._send(200, np.ascontiguousarray(pos.reshape(len(pos), -1), '<f4').tobytes(), 'application/octet-stream')
                    return self._send(404, b'a joint-position clip has no BVH or mesh; use /api/npz', 'text/plain')
                if is_smpl(z):
                    if u.path == '/api/clip':
                        return self._send(200, json.dumps(smpl_meta(cid, z)).encode(), 'application/json')
                    if u.path == '/api/motion':
                        return self._send(200, np.ascontiguousarray(smpl_motion(cid, z), '<f4').tobytes(), 'application/octet-stream')
                    if u.path == '/api/mesh':
                        return self._send(200, smpl_mesh(cid, z), 'application/octet-stream')
                    return self._send(404, b'an SMPL clip has no BVH; use /api/npz', 'text/plain')
                if u.path == '/api/clip':
                    m = codec.motion_float(z)
                    meta = dict(id=cid, joint_names=z['joint_names'].tolist(), parents=z['parents'].tolist(),
                                offsets=z['offsets'].tolist(), channel_joint=z['channel_joint'].tolist(),
                                channel_name=z['channel_name'].tolist(), frame_time=float(z['frame_time']),
                                frames=int(m.shape[0]), mode=str(z['format']))
                    return self._send(200, json.dumps(meta).encode(), 'application/json')
                if u.path == '/api/motion':
                    return self._send(200, np.ascontiguousarray(codec.motion_float(z), '<f4').tobytes(), 'application/octet-stream')
                raw = codec.decode(z)
                name = cid.split('/')[-1] + '.bvh'
                return self._send(200, raw, 'application/octet-stream', {'Content-Disposition': f'attachment; filename="{name}"'})
            self._send(404, b'not found', 'text/plain')
        except BrokenPipeError:
            pass
        except Exception as e:
            self._send(500, f'{type(e).__name__}: {e}'.encode(), 'text/plain')


def main():
    global ROOT
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=ROOT); ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--host', default='127.0.0.1')
    a = ap.parse_args(); ROOT = a.root
    data, _ = catalog()
    print(f'{sum(len(d["clips"]) for d in data)} clips in {len(data)} dataset(s) from {ROOT}')
    print(f'http://{a.host}:{a.port}/')
    ThreadingHTTPServer((a.host, a.port), H).serve_forever()


if __name__ == '__main__':
    main()
