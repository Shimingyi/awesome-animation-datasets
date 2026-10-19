"""Fit SMPL pose parameters to HumanML3D-style joint positions (the first 22 SMPL joints, Y-up), so such clips can be
shown as SMPL bodies. Analytic, no optimisation, a few ms per frame:

  - a joint with several children (pelvis, spine3) gets the rotation that best aligns all its rest child bones with the
    current ones (Kabsch): the full rotation, twist included;
  - a joint with one child gets the smallest rotation that turns its rest bone (carried by the parent) onto the current
    bone: the swing; its twist follows the parent, so forearm / head roll is approximate;
  - head, wrists and feet (no child among the 22) keep their parent's rotation; the hands (22, 23) stay at rest.

    python -m tools.examples.joints2smpl <vault clip id> ... --out <dir>      -> <dir>/<clip name>.npz (AMASS layout)
    python -m tools.examples.joints2smpl <vault BVH clip id> ... --out <dir> --map snapmogen [--unit 0.01]

Joint-position clips (HumanML3D layout) are used as they are. A BVH clip needs a joint map (MAPS: its joint for each of
the 22 SMPL joints); its forward kinematics give the positions (times --unit, to metres).

The result is shape-neutral SMPL (betas 0); the joint positions it reproduces are reported (mean error, cm).
"""
import argparse
import os

import numpy as np

from .. import config
from ..vault import smplmodel


def _kabsch(A, B):
    """rotation R minimising |R a - b| over the rows of A, B"""
    H = A.T @ B
    U, _, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    return Vt.T @ np.diag([1, 1, d]) @ U.T


def _from_to(a, b):
    """smallest rotation taking direction a onto direction b"""
    a, b = a / (np.linalg.norm(a) + 1e-12), b / (np.linalg.norm(b) + 1e-12)
    v, c = np.cross(a, b), float(np.dot(a, b))
    if c < -0.999999:                                    # opposite: half turn about any axis perpendicular to a
        ax = np.cross(a, [1, 0, 0] if abs(a[0]) < 0.9 else [0, 1, 0]); ax /= np.linalg.norm(ax)
        return 2 * np.outer(ax, ax) - np.eye(3)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx / (1 + c)


def _axis_angle(R):
    q = np.empty(4)                                      # matrix -> quaternion (w, x, y, z), robust branch choice
    t = np.trace(R)
    if t > 0:
        s = np.sqrt(t + 1) * 2; q[:] = [0.25 * s, (R[2, 1] - R[1, 2]) / s, (R[0, 2] - R[2, 0]) / s, (R[1, 0] - R[0, 1]) / s]
    else:
        i = int(np.argmax(np.diag(R))); j, k = (i + 1) % 3, (i + 2) % 3
        s = np.sqrt(1 + R[i, i] - R[j, j] - R[k, k]) * 2
        q[0] = (R[k, j] - R[j, k]) / s; q[1 + i] = 0.25 * s; q[1 + j] = (R[j, i] + R[i, j]) / s; q[1 + k] = (R[k, i] + R[i, k]) / s
    if q[0] < 0:
        q = -q
    ang = 2 * np.arctan2(np.linalg.norm(q[1:]), q[0])
    n = np.linalg.norm(q[1:])
    return q[1:] / n * ang if n > 1e-12 else np.zeros(3)


def fit(P, model):
    """P (T, 22, 3) joint positions -> poses (T, 72) axis-angle, trans (T, 3), mean joint error (m)"""
    par = model['parents'].astype(int)
    _, J = smplmodel.shape(model, np.zeros(10))
    kids = {j: [c for c in range(1, 22) if par[c] == j] for j in range(22)}
    T = len(P)
    poses = np.zeros((T, 24, 3)); trans = P[:, 0] - J[0]
    for f in range(T):
        W = [None] * 24
        for j in range(22):
            ks = kids[j]
            if len(ks) >= 2:
                W[j] = _kabsch(np.stack([J[c] - J[j] for c in ks]), np.stack([P[f, c] - P[f, j] for c in ks]))
            elif len(ks) == 1:
                Wp = W[par[j]] if j else np.eye(3)
                W[j] = _from_to(Wp @ (J[ks[0]] - J[j]), P[f, ks[0]] - P[f, j]) @ Wp
            else:
                W[j] = W[par[j]]
            poses[f, j] = _axis_angle(W[j] if j == 0 else W[par[j]].T @ W[j])
    # check: forward kinematics of the fit against the input
    err = []
    for f in range(0, T, max(1, T // 50)):
        G, X = [None] * 22, np.zeros((22, 3))
        for j in range(22):
            a = poses[f, j]; t = np.linalg.norm(a)
            k = a / t if t > 1e-12 else np.zeros(3)
            K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
            Rl = np.eye(3) + np.sin(t) * K + (1 - np.cos(t)) * K @ K
            if j == 0:
                G[0], X[0] = Rl, J[0] + trans[f]
            else:
                G[j] = G[par[j]] @ Rl; X[j] = X[par[j]] + G[par[j]] @ (J[j] - J[par[j]])
        err.append(np.linalg.norm(X - P[f], axis=1).mean())
    return poses.reshape(T, 72), trans, float(np.mean(err))


SMPL22 = ['pelvis', 'left_hip', 'right_hip', 'spine1', 'left_knee', 'right_knee', 'spine2', 'left_ankle', 'right_ankle', 'spine3',
          'left_foot', 'right_foot', 'neck', 'left_collar', 'right_collar', 'head', 'left_shoulder', 'right_shoulder', 'left_elbow',
          'right_elbow', 'left_wrist', 'right_wrist']
MAPS = {   # BVH joint per SMPL joint (in SMPL22 order)
    'snapmogen': ['C_pelvis0001_bind_JNT', 'L_legUpper0001_bind_JNT', 'R_legUpper0001_bind_JNT', 'C_spine0001_bind_JNT',
                  'L_legLower0001_bind_JNT', 'R_legLower0001_bind_JNT', 'C_spine0002_bind_JNT', 'L_foot0001_bind_JNT', 'R_foot0001_bind_JNT',
                  'C_spine0003_bind_JNT', 'L_foot0002_bind_JNT', 'R_foot0002_bind_JNT', 'C_neck0001_bind_JNT', 'L_clavicle_bind_JNT',
                  'R_clavicle_bind_JNT', 'C_head_bind_JNT', 'L_armUpper0001_bind_JNT', 'R_armUpper0001_bind_JNT', 'L_armLower0001_bind_JNT',
                  'R_armLower0001_bind_JNT', 'L_hand0001_bind_JNT', 'R_hand0001_bind_JNT'],
}


def _euler(axis, deg):
    a = np.radians(deg); c, s = np.cos(a), np.sin(a); o, z = np.ones_like(a), np.zeros_like(a)
    R = {'X': [[o, z, z], [z, c, -s], [z, s, c]], 'Y': [[c, z, s], [z, o, z], [-s, z, c]], 'Z': [[c, -s, z], [s, c, z], [z, z, o]]}[axis]
    return np.moveaxis(np.array(R), [0, 1], [-2, -1])


def bvh_positions(meta, motion):
    """world joint positions (T, J, 3) of a BVH clip (vault / server meta + float motion)"""
    T, names = len(motion), meta['joint_names']
    idx = {n: i for i, n in enumerate(names)}; ch = {}
    for k, (j, c) in enumerate(zip(meta['channel_joint'], meta['channel_name'])):
        ch.setdefault(idx[j], []).append((c, k))
    G = [None] * len(names); P = np.zeros((T, len(names), 3))
    for j, par in enumerate(meta['parents']):
        t = np.tile(np.asarray(meta['offsets'][j], float), (T, 1)); R = np.tile(np.eye(3), (T, 1, 1))
        for c, k in ch.get(j, []):
            if c.endswith('position'):
                t[:, 'XYZ'.index(c[0])] += motion[:, k]
            else:
                R = R @ _euler(c[0], motion[:, k])
        if par < 0:
            G[j], P[:, j] = R, t
        else:
            G[j] = G[par] @ R; P[:, j] = P[:, par] + np.einsum('tij,tj->ti', G[par], t)
    return P


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('clips', nargs='+', help='vault clip ids of HumanML3D-style joint clips (<vault dir>/<clip id>)')
    ap.add_argument('--out', required=True)
    ap.add_argument('--map', choices=sorted(MAPS), help='BVH clips: which joint map')
    ap.add_argument('--unit', type=float, default=0, help='BVH units to metres (0: scale to SMPL bone lengths)')
    a = ap.parse_args()
    model = smplmodel.model('smpl', 'neutral', config.get('vault'))
    os.makedirs(a.out, exist_ok=True)
    for cid in a.clips:
        if a.map:
            from .bake import read_vault
            meta, motion, _, _ = read_vault(cid)
            W = bvh_positions(meta, motion.astype(np.float64))
            idx = {n: i for i, n in enumerate(meta['joint_names'])}
            P, fps = W[:, [idx[n] for n in MAPS[a.map]]], 1.0 / meta['frame_time']
            unit = a.unit
            if not unit:                                     # the median ratio of SMPL to clip bone lengths
                par = model['parents'].astype(int); _, J = smplmodel.shape(model, np.zeros(10))
                unit = float(np.median([np.linalg.norm(J[c] - J[par[c]]) / max(1e-9, np.linalg.norm(P[0, c] - P[0, par[c]])) for c in range(1, 22)]))
            P = P * unit
        else:
            with np.load(os.path.join(config.get('vault'), 'processed', cid + '.npz'), allow_pickle=False) as z:
                P, fps = z['positions'].astype(np.float64)[:, :22], float(z['fps'])
        poses, trans, err = fit(P, model)
        out = os.path.join(a.out, os.path.basename(cid) + '.npz')
        np.savez_compressed(out, poses=poses.astype(np.float32), trans=trans.astype(np.float32), betas=np.zeros(10, np.float32),
                            gender=np.array('neutral'), mocap_framerate=np.float64(fps), fitted_from=np.array(cid))
        print(f'{cid}: {len(P)} frames, mean joint error {100 * err:.1f} cm -> {out}')


if __name__ == '__main__':
    main()
