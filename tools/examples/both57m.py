"""BOTH57M (BOTH2Hands) release -> AMASS-style SMPL-H npz, one per clip, grouped by the release's split.

    python -m tools.examples.both57m <raw dir: full_motion/<id>/data.npz + train|val|test.txt> <out dir>

The release stores each clip as root_orient (T,3), body_pose (T,21,3), hand_pose (T,30,3: left then right hand, SMPL-H
order), trans (T,3), seq_len, framerate (30) and its text: full_annot (whole-body descriptions) and, for 1,815 clips,
hand_annot. No betas or gender are given, so the clips use the neutral shape. Output: poses (T,156) = root, body,
left hand, right hand; trans; betas (zeros); gender neutral; mocap_framerate; text and hand_text (one description per
line). Y-up, metres, as released.
"""
import argparse
import os

import numpy as np


def convert(p):
    z = np.load(p, allow_pickle=False)
    T = int(z['seq_len'])
    poses = np.concatenate([z['root_orient'][:T].reshape(T, 3), z['body_pose'][:T].reshape(T, 63), z['hand_pose'][:T].reshape(T, 90)], 1)
    lines = lambda a: '\n'.join(str(s) for s in np.asarray(a).ravel())   # noqa: E731
    return dict(poses=poses.astype(np.float32), trans=z['trans'][:T].astype(np.float32), betas=np.zeros(10, np.float32),
                gender=np.array('neutral'), surface_model_type=np.array('smplh'), mocap_framerate=np.float64(z['framerate']),
                text=np.array(lines(z['full_annot'])), hand_text=np.array(lines(z['hand_annot'])))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('raw'); ap.add_argument('out')
    a = ap.parse_args()
    split = {}
    for s in ('train', 'val', 'test'):
        with open(os.path.join(a.raw, f'{s}.txt')) as f:
            split.update({ln.strip(): s for ln in f if ln.strip()})
    n, secs = 0, 0.0
    src = os.path.join(a.raw, 'full_motion')
    for cid in sorted(os.listdir(src), key=lambda c: (len(c), c)):
        p = os.path.join(src, cid, 'data.npz')
        if not os.path.exists(p):
            continue
        d = convert(p)
        os.makedirs(os.path.join(a.out, split.get(cid, 'other')), exist_ok=True)
        np.savez(os.path.join(a.out, split.get(cid, 'other'), f'{int(cid):04d}.npz'), **d)
        n += 1; secs += len(d['poses']) / float(d['mocap_framerate'])
    print(f'{n} clips, {secs / 3600:.2f} h -> {a.out}')


if __name__ == '__main__':
    main()
