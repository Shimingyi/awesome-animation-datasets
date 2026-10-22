"""Seamless Interaction (facebook/seamless-interaction on the Hub): fetch only the motion files out of the release's tars.

    python -m tools.examples.seamless fetch <out dir> <tar path> [<tar path> ...] [--ext npz json]
        e.g. improvised/dev/0000/0000.tar naturalistic/dev/0000/0000.tar
    python -m tools.examples.seamless convert <fetched dir> <out dir>     # -> AMASS-style SMPL-H npz, upright, in place

Every tar (~1 GB) holds, per participant, <file id>.mp4 / .wav / .json / .npz. Tars are uncompressed, so their headers
are read with HTTP range requests and only the wanted members are downloaded; the video and audio are skipped. The npz
has SMPL-H (smplh:body_pose, global_orient, left/right_hand_pose, translation, is_valid; 30 Hz, estimated from the
video), keypoints and the Imitator face / head features; the json has the transcript and annotations.
Output: <out>/<tar path without .tar>/<file id>.<ext>; files already there are skipped.

convert: the SMPL-H is in camera space (y down, z away from the camera) and its translation is monocular depth: the
root jumps 3-7 cm in depth per frame (median) and drifts metres within a clip, so it is not usable as world motion.
The poses are turned upright (180 degrees about x), the root is held in place (translation zero) and frames the release
marks invalid repeat the last valid pose. Neutral shape (no betas are released).
"""
import argparse
import os
import tarfile

import numpy as np
import requests

REPO = 'https://huggingface.co/datasets/facebook/seamless-interaction/resolve/main/'


def members(url, s):
    """-> [(name, data offset, size)] from the tar headers (pax headers skipped)"""
    out, off = [], 0
    while True:
        h = s.get(url, headers={'Range': f'bytes={off}-{off + 511}'}, timeout=60)
        h.raise_for_status()
        if h.status_code != 206:
            raise SystemExit(f'no range support for {url}')
        if h.content.strip(b'\0') == b'':
            return out
        ti = tarfile.TarInfo.frombuf(h.content, 'utf-8', 'surrogateescape')
        if ti.type not in (tarfile.XHDTYPE, tarfile.XGLTYPE):
            out.append((ti.name, off + 512, ti.size))
        off += 512 + (ti.size + 511) // 512 * 512


def fetch(out, tar, exts, s):
    url, dst = REPO + tar, os.path.join(out, tar[:-4])
    os.makedirs(dst, exist_ok=True)
    got = 0
    for name, off, size in members(url, s):
        p = os.path.join(dst, os.path.basename(name))
        if name.rsplit('.', 1)[-1] not in exts or (os.path.exists(p) and os.path.getsize(p) == size):
            continue
        r = s.get(url, headers={'Range': f'bytes={off}-{off + size - 1}'}, timeout=600)
        r.raise_for_status()
        if len(r.content) != size:
            raise SystemExit(f'short read: {tar}:{name}')
        with open(p + '.part', 'wb') as f:
            f.write(r.content)
        os.replace(p + '.part', p); got += size
    return got


def to_smplh(p):
    from scipy.spatial.transform import Rotation as R
    z = np.load(p)
    v = z['smplh:is_valid'].astype(bool)
    if not v.any():
        return None
    a, b = np.flatnonzero(v)[[0, -1]]
    keep = np.maximum.accumulate(np.where(v, np.arange(len(v)), 0))[a:b + 1]   # index of the last valid frame
    flip = R.from_euler('x', 180, degrees=True)
    root = (flip * R.from_rotvec(z['smplh:global_orient'][keep])).as_rotvec()
    poses = np.concatenate([root, z['smplh:body_pose'][keep].reshape(-1, 63), z['smplh:left_hand_pose'][keep].reshape(-1, 45),
                            z['smplh:right_hand_pose'][keep].reshape(-1, 45)], 1)
    return dict(poses=poses.astype(np.float32), trans=np.zeros((len(keep), 3), np.float32), betas=np.zeros(10, np.float32),
                gender=np.array('neutral'), surface_model_type=np.array('smplh'), mocap_framerate=np.float64(30.0))


def convert(src, out):
    n, secs = 0, 0.0
    for d, _, fs in os.walk(src):
        for f in sorted(fs):
            if not f.endswith('.npz'):
                continue
            c = to_smplh(os.path.join(d, f))
            if c is None:
                continue
            o = os.path.join(out, os.path.relpath(d, src).split('/')[0], f)   # <improvised|naturalistic>/<file id>.npz
            os.makedirs(os.path.dirname(o), exist_ok=True)
            np.savez(o, **c); n += 1; secs += len(c['poses']) / 30
    print(f'{n} clips, {secs / 3600:.2f} h -> {out}')


def main():
    import sys
    if sys.argv[1:2] == ['convert']:
        return convert(*sys.argv[2:4])
    if sys.argv[1:2] == ['fetch']:
        sys.argv.pop(1)
    ap = argparse.ArgumentParser()
    ap.add_argument('out'); ap.add_argument('tars', nargs='+')
    ap.add_argument('--ext', nargs='+', default=['npz', 'json'])
    a = ap.parse_args()
    s = requests.Session()
    for f in ('interactions.csv', 'participants.csv', 'relationships.csv'):   # who talks to whom, per interaction
        p = os.path.join(a.out, f)
        if not os.path.exists(p):
            os.makedirs(a.out, exist_ok=True)
            open(p, 'wb').write(s.get(REPO + f, timeout=120).content)
    for t in a.tars:
        print(f'{t}: {fetch(a.out, t, set(a.ext), s) / 1e6:.0f} MB', flush=True)


if __name__ == '__main__':
    main()
