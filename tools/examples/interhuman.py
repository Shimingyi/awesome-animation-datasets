"""InterHuman raw motions (motions/<id>.pkl) -> SMPL npz in the AMASS layout (one file per person), for `smpl:` items.

    python -m tools.examples.interhuman <motions/<id>.pkl> ... --out build/interhuman/npz   -> <id>_person{1,2}.npz

A pkl is {person1, person2: {trans, root_orient, pose_body (T,63), betas (10,), gender 'neutral'}, mocap_framerate 59.94,
frames}, Z-up, metres. The release does not name the body model: SMPL-neutral forward kinematics reproduces the bone
lengths of the released motions_processed joints within ~0.6 cm (SMPL-X neutral: ~2.5 cm), so it is written as SMPL
(T,72) with the two hand joints at rest. The pkls are loaded through safepickle (numpy arrays only).
"""
import argparse
import os

import numpy as np

from .safepickle import load


def person(p, fps):
    T = len(p['trans'])
    poses = np.concatenate([p['root_orient'], p['pose_body'], np.zeros((T, 6))], axis=1)
    g = str(p.get('gender', 'neutral'))
    return dict(poses=poses.astype(np.float32), trans=np.asarray(p['trans'], np.float32), betas=np.asarray(p['betas'], np.float32).reshape(-1),
                gender=np.array(g if g in ('male', 'female') else 'neutral'), mocap_framerate=np.float64(fps))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pkls', nargs='+'); ap.add_argument('--out', required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for f in a.pkls:
        d, cid = load(f), os.path.splitext(os.path.basename(f))[0]
        for k in ('person1', 'person2'):
            z = person(d[k], float(d['mocap_framerate']))
            out = os.path.join(a.out, f'{cid}_{k}.npz')
            np.savez_compressed(out, **z)
            print(f'{os.path.basename(out)}: {len(z["poses"])} frames at {float(z["mocap_framerate"]):g} fps')


if __name__ == '__main__':
    main()
