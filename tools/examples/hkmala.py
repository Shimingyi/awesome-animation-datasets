"""HKMALA-Motion (the DirtyMoCap release, aLongZJU/HKMALA-Motion on the Hub) -> AMASS-style SMPL-H npz for the vault.

    python -m tools.examples.hkmala <release dir: data/*.npz + metadata.xlsx> <out dir>

Each recording: poses (T,156) SMPL-H axis-angle (root, body, left hand, right hand) fitted with flat_hand_mean=False,
transl (T,3), betas per frame (T,10), fps (60 or 120), Y-up metres, plus the raw markers. Out: the mean hand pose is
added into the hand rotations (so the clip reads as a plain flat-hand SMPL-H), one shape per clip (the median of the
per-frame betas: the viewer has no per-frame shape), gender neutral, the source fps; the clip is named by its public
id under its English style label, and its routine and style labels go to `text`. Markers are left out.
"""
import argparse
import os

import numpy as np

from ..vault import smplmodel


def labels(release):
    import openpyxl
    ws = openpyxl.load_workbook(os.path.join(release, 'metadata.xlsx'), read_only=True)['Sequences']
    rows = list(ws.iter_rows(values_only=True))
    head = rows[0]
    return {r[0]: dict(zip(head, r)) for r in rows[1:] if r and r[0]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('release'); ap.add_argument('out')
    a = ap.parse_args()
    lab, mean = labels(a.release), smplmodel.hands_mean()
    n, secs = 0, 0.0
    for f in sorted(os.listdir(os.path.join(a.release, 'data'))):
        if not f.endswith('.npz'):
            continue
        sid = f[:-4]
        with np.load(os.path.join(a.release, 'data', f), allow_pickle=False) as z:
            poses = z['poses'].astype(np.float32).copy(); poses[:, 66:156] += mean
            d = dict(poses=poses, trans=z['transl'].astype(np.float32), betas=np.median(z['betas'], 0).astype(np.float32),
                     gender=np.array('neutral'), surface_model_type=np.array('smplh'), mocap_framerate=np.float64(z['fps']))
        m = lab.get(sid, {})
        style = (m.get('style_en') or 'Unlabelled').strip()
        d['text'] = np.array(' · '.join(x for x in (m.get('routine'), m.get('style_en'), m.get('style_zh')) if x))
        o = os.path.join(a.out, style.replace('/', '-').replace(' ', '_'), sid + '.npz')
        os.makedirs(os.path.dirname(o), exist_ok=True)
        np.savez(o, **d); n += 1; secs += len(poses) / float(d['mocap_framerate'])
    print(f'{n} recordings, {secs / 3600:.2f} h -> {a.out}')


if __name__ == '__main__':
    main()
