"""RoboMoCap (BitRobot/robomocap on the Hub) -> vault input, one file per performer and session.

    python -m tools.examples.robomocap <release dir: actions/<category>/<action>/session_*/> <out dir>        # SMPL-X npz
    python -m tools.examples.robomocap bvh <release dir> <out dir>                                            # NOKOV BVH

Fetch only the motion part of the 5 TB release (video, IMU and raw markers stay on the Hub):
    snapshot_download('BitRobot/robomocap', repo_type='dataset', allow_patterns=['*/meta.json', '*/annotations.json',
                      '*/motions/smplx.npz', '*/motions/smplx_body1.npz', '*/motions/skeleton_body1.npz',
                      'actions/*/*/*/raw/mocap/Body*.bvh'])

motions/smplx.npz is SMPL-X solved from the 53 NOKOV markers at 120 Hz (Z-up, metres, levelled per capture block):
global_orient, body_pose (21), left/right_hand_pose (15 each, absolute: the release's mean-hand frames hold the mean
pose itself), transl, betas (16), gender, and `valid` per frame. Out: poses (T,165) = root, body, jaw and eyes (zero),
left hand, right hand; every frame of the take is kept (the performers of a two-person take share its time base) and
frames not marked valid repeat the nearest valid pose.
smplx_body1.npz is the second performer of a two-person take (when the release solved one). The session's instruction
(annotations.json) goes to `text`. Also prints the per-person motion time over valid frames, the list's hours.

bvh: raw/mocap/Body<N>.bvh is NOKOV's own skeleton solve (23 body joints, no fingers; cm, Y-up, 120 Hz), one file per
performer, all of a take's files on the same frames. Unsolved frames are written as all zeros, and the frame before a
leading gap is a stale pose (the release's SMPL-X marks it invalid too), so solved runs under 3 frames count as
unsolved; those frames repeat the nearest solved line, the frame count stays. Out: <session>.bvh for Body0,
<session>_body<N>.bvh for the others, plus _instructions.json {clip id: "<action> · <instruction>"}.
286 of the 5,896 files have every bone offset 0 (rotations without a skeleton); they are passed through as they are.
"""
import argparse
import json
import os
from multiprocessing import Pool

import numpy as np


def convert(p):
    z = np.load(p, allow_pickle=False)
    v = z['valid'].astype(bool) & np.isfinite(z['transl']).all(1) & np.isfinite(z['global_orient']).all(1)
    if not v.any():
        return None, 0
    keep = np.maximum.accumulate(np.where(v, np.arange(len(v)), 0))          # index of the last valid frame
    keep[:np.flatnonzero(v)[0]] = np.flatnonzero(v)[0]                        # before the first: the first valid pose
    T = len(keep)                                                             # every frame kept: performers stay in sync
    poses = np.concatenate([z['global_orient'][keep], z['body_pose'][keep].reshape(T, 63), np.zeros((T, 9), np.float32),
                            z['left_hand_pose'][keep].reshape(T, 45), z['right_hand_pose'][keep].reshape(T, 45)], 1)
    d = dict(poses=np.nan_to_num(poses).astype(np.float32), trans=z['transl'][keep].astype(np.float32), betas=z['betas'].astype(np.float32),
             gender=np.array(str(z['gender'])), surface_model_type=np.array('smplx'), mocap_framerate=np.float64(120.0))
    return d, int(v.sum())


def clean_bvh(job):
    """(src, dst) -> solved frames; writes the BVH with unsolved frames filled"""
    src, dst = job
    raw = open(src, 'rb').read()
    nl = b'\r\n' if b'\r\n' in raw[:200] else b'\n'
    head, body = raw.split(b'MOTION', 1)
    lines = body.strip().split(nl)                                            # Frames:, Frame Time:, then one line per frame
    fr = lines[2:]
    v = np.array([any(float(t) != 0 for t in l.split()) for l in fr])
    e = np.flatnonzero(np.diff(np.r_[0, v.astype(np.int8), 0]))               # solved runs: [start, end) pairs
    for a, b in zip(e[::2], e[1::2]):
        if b - a < 3 and b - a < len(fr):                                    # a stray frame next to a gap
            v[a:b] = False
    if not v.any():
        return 0
    keep = np.maximum.accumulate(np.where(v, np.arange(len(v)), 0))
    keep[:np.flatnonzero(v)[0]] = np.flatnonzero(v)[0]
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst + '.part', 'wb') as f:
        f.write(head + b'MOTION' + nl + nl.join(lines[:2] + [fr[k] for k in keep]) + nl)
    os.replace(dst + '.part', dst)
    return int(v.sum())


def instruction(sd):
    p = os.path.join(sd, 'annotations.json')
    return ' '.join(str(json.load(open(p)).get('instruction', '')).split()) if os.path.exists(p) else ''


def bvh_main(release, out):
    root, jobs, cats, text = os.path.join(release, 'actions'), [], [], {}
    for cat in sorted(os.listdir(root)):
        for act in sorted(os.listdir(os.path.join(root, cat))):
            for ses in sorted(os.listdir(os.path.join(root, cat, act))):
                sd, t = os.path.join(root, cat, act, ses), None
                md = os.path.join(sd, 'raw', 'mocap')
                for f in sorted(os.listdir(md)) if os.path.isdir(md) else []:
                    if f.startswith('Body') and f.endswith('.bvh'):
                        n = f[4:-4]
                        cid = f'{cat}/{act}/{ses}' + ('' if n == '0' else f'_body{n}')
                        jobs.append((os.path.join(md, f), os.path.join(out, cid + '.bvh'))); cats.append(cat)
                        t = instruction(sd) if t is None else t
                        text[cid] = f'{act} · {t}' if t else act
    with Pool(8) as pool:
        nv = pool.map(clean_bvh, jobs, chunksize=8)
    json.dump(text, open(os.path.join(out, '_instructions.json'), 'w'), ensure_ascii=False, indent=0)
    by_cat = {}
    for c, v in zip(cats, nv):
        by_cat[c] = by_cat.get(c, 0) + v
    print(f'{sum(v > 0 for v in nv)} of {len(jobs)} performer files, {sum(nv) / 120 / 3600:.2f} h of solved per-person motion -> {out}')
    for c, v in sorted(by_cat.items(), key=lambda x: -x[1]):
        print(f'  {c}: {v / 120 / 3600:.2f} h')


def main():
    import sys
    if sys.argv[1:2] == ['bvh']:
        return bvh_main(*sys.argv[2:4])
    ap = argparse.ArgumentParser()
    ap.add_argument('release'); ap.add_argument('out')
    a = ap.parse_args()
    root = os.path.join(a.release, 'actions')
    n, valid, by_cat = 0, 0, {}
    for cat in sorted(os.listdir(root)):
        for act in sorted(os.listdir(os.path.join(root, cat))):
            for ses in sorted(os.listdir(os.path.join(root, cat, act))):
                sd = os.path.join(root, cat, act, ses)
                text = instruction(sd)
                for body, suffix in (('smplx.npz', ''), ('smplx_body1.npz', '_body1')):
                    p = os.path.join(sd, 'motions', body)
                    if not os.path.exists(p):
                        continue
                    d, nv = convert(p)
                    if d is None:
                        continue
                    d['text'] = np.array(f'{act} · {text}' if text else act)
                    o = os.path.join(a.out, cat, act, ses + suffix + '.npz')
                    os.makedirs(os.path.dirname(o), exist_ok=True)
                    np.savez(o, **d)
                    n += 1; valid += nv; by_cat[cat] = by_cat.get(cat, 0) + nv
    print(f'{n} clips, {valid / 120 / 3600:.2f} h of valid per-person motion -> {a.out}')
    for c, v in sorted(by_cat.items(), key=lambda x: -x[1]):
        print(f'  {c}: {v / 120 / 3600:.2f} h')


if __name__ == '__main__':
    main()
