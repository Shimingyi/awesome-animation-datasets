"""FineDance motion -> SMPL-H npz in the AMASS layout, for `smpl:` example items.

    python -m tools.examples.finedance <finedance dir> 052 058 ... --out build/finedance/npz

<finedance dir>/motion/<id>.npy is (T, 315): root translation + 52 SMPL-H joint rotations as 6D (the first two rows of
each matrix, pytorch3d matrix_to_rotation_6d), label_json/<id>.json gives the song name and genre. The release is
Y-up, 30 fps, and is posed on neutral SMPL-X with zero betas and flat hand mean (li-ronghui/FineDance
data/code/pre_motion.py), so the output is (T,156) axis-angle, betas 0, gender neutral.
"""
import argparse
import json
import os

import numpy as np

from tools.vault.adapters import _matrix_to_axis_angle, _rot6d_rows


def clip(root, cid):
    a = np.load(os.path.join(root, 'motion', cid + '.npy'), allow_pickle=False).astype(np.float64)
    T = len(a)
    poses = _matrix_to_axis_angle(_rot6d_rows(a[:, 3:].reshape(T * 52, 6))).reshape(T, 156)
    return dict(poses=poses.astype(np.float32), trans=a[:, :3].astype(np.float32), betas=np.zeros(10, np.float32),
                gender=np.array('neutral'), mocap_framerate=np.float64(30))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('root'); ap.add_argument('ids', nargs='+'); ap.add_argument('--out', required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for cid in a.ids:
        z = clip(a.root, cid)
        np.savez_compressed(os.path.join(a.out, cid + '.npz'), **z)
        lab = json.load(open(os.path.join(a.root, 'label_json', cid + '.json')))
        print(f'{cid}.npz: {len(z["poses"])} frames, {lab["style1"]} / {lab["style2"]}, song {lab["name"]!r}')


if __name__ == '__main__':
    main()
