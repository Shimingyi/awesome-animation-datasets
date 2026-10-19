"""AIST++ motions/<sequence>.pkl -> SMPL npz in the AMASS layout.

    python -m tools.examples.aistpp <motions dir> <sequence> ... --out build/aistpp/npz

Each pickle holds smpl_poses (T, 72), smpl_trans (T, 3) and smpl_scaling (1,); as in the official API
(google/aistplusplus_api), the SMPL translation is smpl_trans / smpl_scaling (the scaling turns metres into the
centimetre-sized capture space). No shape is released (betas 0, neutral), 60 fps, Y-up. Read with safepickle (arrays only).
"""
import argparse
import os

import numpy as np

from .safepickle import Unpickler


def convert(path):
    with open(path, 'rb') as f:
        d = Unpickler(f).load()
    s = float(np.asarray(d['smpl_scaling']).reshape(-1)[0])
    return dict(poses=np.asarray(d['smpl_poses'], np.float32), trans=(np.asarray(d['smpl_trans']) / s).astype(np.float32),
                betas=np.zeros(10, np.float32), gender=np.array('neutral'), mocap_framerate=np.float64(60))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('motions'); ap.add_argument('seqs', nargs='+'); ap.add_argument('--out', required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for s in a.seqs:
        z = convert(os.path.join(a.motions, s + '.pkl'))
        np.savez_compressed(os.path.join(a.out, s + '.npz'), **z)
        print(f'{s}: {len(z["poses"])} frames')


if __name__ == '__main__':
    main()
