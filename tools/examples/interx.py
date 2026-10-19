"""Inter-X takes (motions/<GgggTtttAaaaRrrr>/P1.npz, P2.npz) -> SMPL-X npz in the AMASS layout, one per person.

    python -m tools.examples.interx <motions dir> <take> ... --out build/inter-x/npz

Each person holds root_orient (T,3), pose_body (T,21,3), pose_lhand / pose_rhand (T,15,3), trans (T,3), betas (1,10) and
gender; the official viewer (aitviewer SMPLLayer) uses SMPL-X with full hand poses and flat_hand_mean=True, at 120 fps.
"""
import argparse
import os

import numpy as np


def person(path):
    with np.load(path, allow_pickle=False) as z:
        T = len(z['trans'])
        poses = np.concatenate([z['root_orient'].reshape(T, 3), z['pose_body'].reshape(T, 63), np.zeros((T, 9), np.float32),
                                z['pose_lhand'].reshape(T, 45), z['pose_rhand'].reshape(T, 45)], axis=1)
        return dict(poses=poses.astype(np.float32), trans=z['trans'].astype(np.float32), betas=z['betas'].reshape(-1).astype(np.float32),
                    gender=np.array(str(z['gender'])), mocap_framerate=np.float64(120))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('motions'); ap.add_argument('takes', nargs='+'); ap.add_argument('--out', required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for take in a.takes:
        for p in ('P1', 'P2'):
            z = person(os.path.join(a.motions, take, p + '.npz'))
            np.savez_compressed(os.path.join(a.out, f'{take}_{p}.npz'), **z)
        print(f'{take}: {len(z["poses"])} frames, {z["gender"]}')


if __name__ == '__main__':
    main()
