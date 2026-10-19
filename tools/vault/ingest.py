"""Convert a dataset folder to npz (BVH) + verbatim copies (everything else).

    python -m tools.vault.ingest <source folder> <name> [--root <vault>]      (vault: config.local.yaml `vault`, or $AAD_VAULT)

Output: <root>/processed/<name>/<same relative tree>.npz and <root>/processed/<name>/_catalog.json.
Every npz is re-opened from disk and decoded; the result must equal the source bytes or the file is reported as failed.
"""
import argparse
import json
import os
import shutil
import sys
import time
from multiprocessing import Pool

import numpy as np

from .. import config
from . import adapters
from . import bvhcodec as codec

DEFAULT_ROOT = config.get('vault')


GENERIC_STEMS = {'motion_actor'}                       # HiPHI: every clip is <frame>/<lu>/<motion_id>/motion_actor.bvh


def _naming(rel):
    """-> (name, collection, group) for a source-relative path."""
    name = os.path.basename(rel)[:-4]; parent = os.path.dirname(rel)
    if name in GENERIC_STEMS and parent:                # name the clip after its folder, group by the folder above
        parts = parent.split('/')
        return parts[-1], '/'.join(parts[:-2]), parts[-2] if len(parts) >= 2 else ''
    style = name.split('_')[0]
    return name, (os.path.dirname(parent) if os.path.basename(parent) == style else parent), style


def _same(a, b):
    return bool(np.array_equal(a, b, equal_nan=True)) if a.dtype.kind in 'fc' and b.dtype.kind in 'fc' else bool(np.array_equal(a, b))


def _smpl(src, dst, rel):
    """AMASS-style npz (poses, trans, betas, ...). Kept as npz with the same keys, recompressed (LZMA); float64 arrays that are
    exactly float32-representable are stored as float32. Verified array-by-array after writing. -> catalog row, or None if
    this npz is not SMPL-like."""
    z = np.load(src, allow_pickle=True)
    if not {'poses', 'trans', 'betas'} <= set(z.files):
        return None
    d = {}
    for k in z.files:
        a = z[k]
        if a.dtype == object:
            a = np.array(str(a.item())) if a.shape == () else a
        if a.dtype == np.float64 and _same(a.astype(np.float32).astype(np.float64), a):
            a = a.astype(np.float32)
        d[k] = a
    d['mv_kind'] = np.array('smpl')
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    codec.save(dst, d)
    ok = True
    with np.load(dst) as y:
        for k in z.files:
            ok &= _same(y[k].astype(np.float64) if y[k].dtype.kind == 'f' else y[k],
                        z[k].astype(np.float64) if z[k].dtype.kind == 'f' else z[k])
    fps = next((float(z[k]) for k in ('mocap_framerate', 'mocap_frame_rate', 'fps') if k in z.files), 30.0)
    T = int(z['poses'].shape[0]); W = int(z['poses'].shape[1])
    name, coll, group = _naming(rel)
    return dict(id=rel[:-4], kind='smpl', name=name, collection=coll, group=group, frames=T, fps=fps, duration=round(T / fps, 3),
                joints=W // 3, channels=W, src_bytes=os.path.getsize(src), npz_bytes=os.path.getsize(dst), mode='smpl-npz',
                ok=bool(ok), sha256='')


def _adapt(src, dst, rel, ds, mode='auto'):
    """motionX / HumanML3D-style .npy -> npz (see adapters.py); verified by reloading what was written"""
    kind = adapters.kind_of(rel, mode)
    d, extra = {'motionx': adapters.convert_motionx, 'rpr272': adapters.convert_rpr272}.get(kind, adapters.convert_joints)(src, ds)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    codec.save(dst, d)
    ok = True
    with np.load(dst) as z:
        for k, v in d.items():
            ok &= _same(np.asarray(z[k]), np.asarray(v))
    parts = rel.replace('\\', '/').split('/')
    name = parts[-1][:-4]
    if kind == 'joints' and 'new_joints' in parts:
        i = parts.index('new_joints')
        coll, group = '/'.join(parts[:i]), adapters.group_for(name)
    else:
        name, coll, group = _naming(rel)
    row = dict(id=rel[:-4], kind='smpl' if kind in ('motionx', 'rpr272') else 'joints', name=name, collection=coll, group=group,
               duration=round(extra['frames'] / extra['fps'], 3), src_bytes=extra.pop('src_bytes', os.path.getsize(src)),
               npz_bytes=os.path.getsize(dst), mode='smpl-npz' if kind in ('motionx', 'rpr272') else 'joints-v1', ok=bool(ok), sha256='', **extra)
    return row


def _one(args):
    src, dst, rel = args[:3]
    if rel.lower().endswith('.npy'):
        return _adapt(src, dst, rel, args[3], args[4])
    if rel.lower().endswith('.npz'):
        return _smpl(src, dst, rel)
    raw = open(src, 'rb').read()
    d = codec.encode(raw)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    codec.save(dst, d)
    with np.load(dst) as z:                      # verify the artifact on disk, not the one in memory
        ok = codec.decode(z) == raw
    frames = int(d['motion'].shape[0]) if 'motion' in d else -1
    ft = float(d['frame_time']) if 'frame_time' in d else 0.0
    if frames < 0:                               # text fallback: the counts come from the header (no number parsing needed)
        import re
        txt = raw[:raw.find(b'Frame Time:') + 60].decode('latin-1'); m = re.search(r'Frames:\s*(\d+)', txt); t = re.search(r'Frame Time:\s*([0-9.eE+-]+)', txt)
        frames = int(m.group(1)) if m else 0; ft = float(t.group(1)) if t else 0.0
    name, coll, group = _naming(rel)
    return dict(id=rel[:-4], kind='bvh', name=name, collection=coll, group=group, frames=frames,
                fps=round(1 / ft, 3) if ft else 0, duration=round(frames * ft, 3),
                joints=int(len(d['joint_names'])) if 'joint_names' in d else 0,
                channels=int(len(d['channel_name'])) if 'channel_name' in d else 0,
                src_bytes=len(raw), npz_bytes=os.path.getsize(dst), mode=str(d['format']),
                ok=bool(ok), sha256=str(d['sha256']))


def _safe(args):
    """One file, never raises: a failure comes back as {'error':...} so a batch run keeps going."""
    try:
        return _one(args)
    except Exception as e:                       # noqa: BLE001 - report and move on
        return dict(id=args[2], error=f'{type(e).__name__}: {e}')


def _pool_run(pool_jobs, workers, done, label, total0, t0):
    n = 0
    if not pool_jobs:
        return
    with Pool(workers) as p:
        for r in p.imap_unordered(_safe, pool_jobs, chunksize=1 if workers <= 4 else 4):
            n += 1
            done(r)
            if n % 200 == 0 or n == len(pool_jobs):
                print(f'  [{label}] {n}/{len(pool_jobs)}  {time.time() - t0:.0f}s', flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src'); ap.add_argument('name'); ap.add_argument('--root', default=DEFAULT_ROOT)
    ap.add_argument('--jobs', type=int, default=os.cpu_count())
    ap.add_argument('--big-mb', type=float, default=64, help='files above this size use the small pool (they need ~20x their size in RAM)')
    ap.add_argument('--big-jobs', type=int, default=3)
    ap.add_argument('--max-copy-kb', type=float, default=1024, help='other files are copied only up to this size; bigger ones are listed, not copied')
    ap.add_argument('--no-resume', action='store_true')
    ap.add_argument('--adapter', default='auto', choices=['auto', 'motionx', 'joints', 'rpr272'], help='how to read .npy files: motionx = (T,322) SMPL-X, joints = new_joints/ (HumanML3D style), rpr272 = MotionStreamer / MotionMillion 272-dim features')
    ap.add_argument('--no-copy', action='store_true', help='copy no other files (for datasets whose siblings are folded into the clip npz)')
    a = ap.parse_args()
    out = os.path.join(a.root, 'processed', a.name)
    part = os.path.join(out, '_catalog.partial.jsonl')
    jobs, copies, skipped = [], [], {}
    for dp, dn, fn in os.walk(a.src):
        dn[:] = [x for x in dn if not x.startswith('.')]
        for f in fn:
            if f.startswith('.'):
                continue
            s_ = os.path.join(dp, f); rel = os.path.relpath(s_, a.src)
            if f.lower().endswith(('.bvh', '.npz')) or adapters.is_adapter_file(rel, a.adapter):
                jobs.append((s_, os.path.join(out, rel[:-4] + '.npz'), rel, a.name, a.adapter))
            elif a.no_copy:
                continue
            else:
                sz = os.path.getsize(s_)
                if sz <= a.max_copy_kb * 1024:
                    copies.append((s_, os.path.join(out, rel)))
                else:
                    e = os.path.splitext(f)[1].lower() or '(none)'
                    k = skipped.setdefault(e, [0, 0]); k[0] += 1; k[1] += sz
    clips, failed, seen = [], [], set()
    cat_path = os.path.join(out, '_catalog.json')
    if not a.no_resume and os.path.exists(cat_path):
        for r in json.load(open(cat_path))['clips']:
            if os.path.exists(os.path.join(out, r['id'] + '.npz')):
                clips.append(r); seen.add(r['id'])
    if not a.no_resume and os.path.exists(part):
        for ln in open(part):
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if r['id'] not in seen and os.path.exists(os.path.join(out, r['id'] + '.npz')):
                clips.append(r); seen.add(r['id'])
    if seen:
        print(f'{len(seen)} clips already in the vault (kept)', flush=True)
    todo = [j for j in jobs if j[2][:-4] not in seen]
    print(f'{a.name}: {len(jobs)} bvh/npz ({len(todo)} to do), {len(copies)} small files copied, '
          f'{sum(v[0] for v in skipped.values())} large non-motion files left out', flush=True)
    os.makedirs(out, exist_ok=True)
    for s_, d in copies:
        if not os.path.exists(d):
            os.makedirs(os.path.dirname(d), exist_ok=True); shutil.copy2(s_, d)
    pf = open(part, 'a')

    def done(r):
        if r is None:                              # an npz that is not SMPL-like: kept verbatim below (if small)
            return
        if 'error' in r:
            failed.append(r); print('  ERROR', r['id'], r['error'], flush=True); return
        clips.append(r); pf.write(json.dumps(r) + '\n'); pf.flush()

    t0 = time.time()
    big = [j for j in todo if os.path.getsize(j[0]) > a.big_mb * 1e6]
    small = [j for j in todo if os.path.getsize(j[0]) <= a.big_mb * 1e6]
    _pool_run(small, a.jobs, done, 'small', len(todo), t0)
    _pool_run(big, a.big_jobs, done, 'big', len(todo), t0)
    pf.close()
    for src, dst, rel, *_ in jobs:                 # non-SMPL npz files: copy them as they are (if small)
        if rel.lower().endswith('.npz') and not adapters.is_adapter_file(rel, a.adapter) and not os.path.exists(dst) and os.path.getsize(src) <= a.max_copy_kb * 1024:
            os.makedirs(os.path.dirname(dst), exist_ok=True); shutil.copy2(src, dst)
    clips.sort(key=lambda c: c['id'])
    json.dump(dict(dataset=a.name, source=a.src, clips=clips), open(cat_path, 'w'))
    if not failed:
        os.remove(part)
    json.dump(dict(skipped={k: dict(files=v[0], bytes=v[1]) for k, v in sorted(skipped.items(), key=lambda kv: -kv[1][1])}, failed=failed),
              open(os.path.join(out, '_ingest_report.json'), 'w'), indent=1)
    sb = sum(c['src_bytes'] for c in clips); nb = sum(c['npz_bytes'] for c in clips)
    bad = [c['id'] for c in clips if not c['ok']]
    fb = sum(c['mode'] not in ('bvh-fixed6-v1', 'smpl-npz') for c in clips)
    hrs = sum(c['duration'] for c in clips) / 3600
    print(f'done {a.name}: {len(clips)} clips  {hrs:.1f} h  {sb / 1e9:.2f} GB -> {nb / 1e9:.2f} GB  ({sb / max(nb, 1):.2f}x)  '
          f'text-fallback {fb}  verify-failed {len(bad)}  errors {len(failed)}  ({time.time() - t0:.0f}s)', flush=True)
    if bad or failed:
        print('FAILED:', (bad + [f["id"] for f in failed])[:20]); sys.exit(1)


if __name__ == '__main__':
    main()
