"""OMOMO sequences -> SMPL-X npz in the AMASS layout (one file per sequence), for `smpl:` example items.

    python -m tools.examples.omomo data/{train,test}_diffusion_manip_seq_joints24.p --seq sub1_mop_021 ... --out build/omomo/npz

The two joblib pickles of the release (data.tar.gz) hold {index: {seq_name <subject>_<object>_<take>, betas (1,16),
gender, trans, root_orient, pose_body (T,63), rest_offsets, trans2joint, obj_trans (T,3,1), obj_rot (T,3,3),
obj_scale (T,), obj_com_pos, + obj_bottom_* for the two-part mop / vacuum}}. The official code
(lijiaman/omomo_release, run_smplx_model) feeds them to SMPL-X (male / female, 16 betas) with the hands at zero (flat),
30 fps, Z-up (floor_z), metres; `trans` is the model translation. They are loaded through safepickle (numpy arrays only).
The object pose is kept in the npz (obj_*: vertices = scale * R @ v + t, meshes in data/captured_objects/
<object>_cleaned_simplified[_top|_bottom].obj) for when the viewer can show objects.
"""
import argparse
import os

import numpy as np

from .safepickle import load

OBJ = ['obj_trans', 'obj_rot', 'obj_scale', 'obj_com_pos', 'obj_bottom_trans', 'obj_bottom_rot', 'obj_bottom_scale']


def sequence(s):
    T = len(s['trans'])
    poses = np.concatenate([s['root_orient'], s['pose_body'], np.zeros((T, 9 + 90))], axis=1)   # + jaw, eyes, hands (SMPL-X 165)
    z = dict(poses=poses.astype(np.float32), trans=np.asarray(s['trans'], np.float32), betas=np.asarray(s['betas'], np.float32).reshape(-1),
             gender=np.array(str(s['gender'])), mocap_framerate=np.float64(30), obj_name=np.array(s['seq_name'].split('_')[1]))
    for k in OBJ:
        if k in s:
            v = np.asarray(s[k], np.float32)
            z[k] = v.reshape(T, 3) if k.endswith('_trans') else v
    return z


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pickles', nargs='+'); ap.add_argument('--seq', nargs='*', help='sequence names (default: all)')
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    want, left = set(a.seq or []), set(a.seq or [])
    for p in a.pickles:
        for s in load(p).values():
            if want and s['seq_name'] not in want:
                continue
            z = sequence(s)
            np.savez_compressed(os.path.join(a.out, s['seq_name'] + '.npz'), **z)
            left.discard(s['seq_name'])
            print(f'{s["seq_name"]}.npz: {len(z["poses"])} frames, {z["gender"]}')
    if left:
        print('not found:', ' '.join(sorted(left)))


if __name__ == '__main__':
    main()
