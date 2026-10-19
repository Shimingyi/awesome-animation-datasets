"""Embody 3D capture folders -> SMPL-X npz in the AMASS layout (one file per person), for `smpl:` example items.

    python -m tools.examples.embody3d <capture dir> ... --out build/embody3d/npz

A capture dir (as extracted by zip_select) holds one folder per participant with smplx_mesh_{global_orient, body_pose,
left_hand_pose, right_hand_pose, transl, betas} and `missing` (1 = good tracking) arrays, each <name>/<capture>.npy.
The release uses neutral SMPL-X, flat hand mean, 300 betas, Y-up, 30 fps (facebookresearch/embody-3d src/run.py).
The output keeps every frame; `valid` carries the tracking flag.
"""
import argparse
import glob
import os

import numpy as np

PARTS = ['global_orient', 'body_pose', 'jaw', 'leye', 'reye', 'left_hand_pose', 'right_hand_pose']   # SMPL-X 165 order


def person(d):
    cap = os.path.basename(os.path.dirname(d.rstrip('/')))
    a = {k: np.load(os.path.join(d, f'smplx_mesh_{k}', cap + '.npy'), allow_pickle=False)
         for k in ('global_orient', 'body_pose', 'left_hand_pose', 'right_hand_pose', 'transl', 'betas')}
    T = len(a['transl'])
    z = np.zeros((T, 3))
    poses = np.concatenate([a.get(k, z) if k not in ('jaw', 'leye', 'reye') else z for k in PARTS], axis=1)
    ok = os.path.join(d, 'missing', cap + '.npy')
    valid = np.load(ok, allow_pickle=False).reshape(-1) if os.path.exists(ok) else np.ones(T)
    return dict(poses=poses.astype(np.float32), trans=a['transl'].astype(np.float32), betas=a['betas'].reshape(-1).astype(np.float32),
                gender=np.array('neutral'), mocap_framerate=np.float64(30), valid=valid.astype(np.uint8))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('captures', nargs='+'); ap.add_argument('--out', required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for c in a.captures:
        for d in sorted(glob.glob(os.path.join(c, '*/'))):
            z = person(d)
            out = os.path.join(a.out, f'{os.path.basename(c.rstrip("/"))}__{os.path.basename(d.rstrip("/"))}.npz')
            np.savez_compressed(out, **z)
            print(f'{os.path.basename(out)}: {len(z["poses"])} frames, {100 * z["valid"].mean():.0f} % tracked')


if __name__ == '__main__':
    main()
