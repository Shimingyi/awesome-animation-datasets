"""RoboMoCap (BitRobot/robomocap on the Hub) -> AMASS-style SMPL-X npz for the vault, one per performer and session.

    python -m tools.examples.robomocap <release dir: actions/<category>/<action>/session_*/> <out dir>

Fetch only the motion part of the 5 TB release (video, IMU and raw mocap stay on the Hub):
    snapshot_download('BitRobot/robomocap', repo_type='dataset', allow_patterns=['*/meta.json', '*/annotations.json',
                      '*/motions/smplx.npz', '*/motions/smplx_body1.npz', '*/motions/skeleton_body1.npz'])

motions/smplx.npz is SMPL-X solved from the 53 NOKOV markers at 120 Hz (Z-up, metres, levelled per capture block):
global_orient, body_pose (21), left/right_hand_pose (15 each, absolute: the release's mean-hand frames hold the mean
pose itself), transl, betas (16), gender, and `valid` per frame. Out: poses (T,165) = root, body, jaw and eyes (zero),
left hand, right hand; every frame of the take is kept (the performers of a two-person take share its time base) and
frames not marked valid repeat the nearest valid pose.
smplx_body1.npz is the second performer of a two-person take (when the release solved one). The session's instruction
(annotations.json) goes to `text`. Also prints the per-person motion time over valid frames, the list's hours.
"""
import argparse
import json
import os

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('release'); ap.add_argument('out')
    a = ap.parse_args()
    root = os.path.join(a.release, 'actions')
    n, valid, by_cat = 0, 0, {}
    for cat in sorted(os.listdir(root)):
        for act in sorted(os.listdir(os.path.join(root, cat))):
            for ses in sorted(os.listdir(os.path.join(root, cat, act))):
                sd = os.path.join(root, cat, act, ses)
                text = ''
                if os.path.exists(os.path.join(sd, 'annotations.json')):
                    text = ' '.join(str(json.load(open(os.path.join(sd, 'annotations.json'))).get('instruction', '')).split())
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
