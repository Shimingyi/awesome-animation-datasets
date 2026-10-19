"""Datasets that are not BVH/AMASS-npz: each source file becomes one self-contained npz (lossless: nothing is dropped).

motionX   motion_data/smplx_322/<category>/<subset>/<name>.npy   (T, 322) SMPL-X per frame
          layout: root_orient 0:3, pose_body 3:66, pose_hand 66:156, jaw 156:159, face_expr 159:209, face_shape 209:309, trans 309:312, betas 312:322
          -> AMASS-style SMPL-X npz (poses (T,165) = root, body, jaw, eyes(0), left hand, right hand; trans; betas; mocap_framerate=30)
             plus face_expr / face_shape, so the 322 vector can be rebuilt exactly. The viewer treats it like any SMPL clip (mesh).
HumanML3D / KIT / animationGPT   new_joints/<id>.npy (T, J, 3) joint positions, new_joint_vecs/<id>.npy (features), texts/<id>.txt
          -> 'joints' clip: positions, vecs, text, parents, joint_names, fps. The viewer draws the skeleton (no mesh: these are positions, not SMPL parameters).
"""
import os
import re

import numpy as np

from . import smplmodel

T2M_PARENTS = [-1, 0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 9, 9, 12, 13, 14, 16, 17, 18, 19]       # SMPL 22-joint tree (HumanML3D order)
KIT_CHAINS = [[0, 11, 12, 13, 14, 15], [0, 16, 17, 18, 19, 20], [0, 1, 2, 3, 4], [3, 5, 6, 7], [3, 8, 9, 10]]
FPS = {'HumanML3D': 20.0, 'KIT': 12.5, 'animationGPT': 20.0}                                       # as published; animationGPT assumed like HumanML3D


def _rot6d_cols(x):
    """(..., 6) = the first two COLUMNS of a rotation matrix -> (..., 3, 3)"""
    b1 = x[..., :3] / np.linalg.norm(x[..., :3], axis=-1, keepdims=True)
    a2 = x[..., 3:]; b2 = a2 - (b1 * a2).sum(-1, keepdims=True) * b1; b2 /= np.linalg.norm(b2, axis=-1, keepdims=True)
    return np.stack([b1, b2, np.cross(b1, b2)], -1)


def _rot6d_rows(x):
    """(..., 6) = the first two ROWS of a rotation matrix -> (..., 3, 3)"""
    b1 = x[..., :3] / np.linalg.norm(x[..., :3], axis=-1, keepdims=True)
    a2 = x[..., 3:]; b2 = a2 - (b1 * a2).sum(-1, keepdims=True) * b1; b2 /= np.linalg.norm(b2, axis=-1, keepdims=True)
    return np.stack([b1, b2, np.cross(b1, b2)], -2)


def _matrix_to_axis_angle(R):
    """(N, 3, 3) -> (N, 3)"""
    tr = np.clip((np.trace(R, axis1=1, axis2=2) - 1) / 2, -1, 1); ang = np.arccos(tr)
    ax = np.stack([R[:, 2, 1] - R[:, 1, 2], R[:, 0, 2] - R[:, 2, 0], R[:, 1, 0] - R[:, 0, 1]], 1)
    s = np.linalg.norm(ax, axis=1, keepdims=True)
    out = np.where(s > 1e-8, ax / np.maximum(s, 1e-12) * ang[:, None], 0.0)
    near_pi = (s[:, 0] <= 1e-8) & (ang > 3.0)                 # half turns: the axis from the diagonal
    for i in np.flatnonzero(near_pi):
        d = np.sqrt(np.maximum((np.diag(R[i]) + 1) / 2, 0)); k = int(np.argmax(d)); v = R[i][:, k] + np.eye(3)[k]
        out[i] = v / np.linalg.norm(v) * np.pi
    return out


def recover_rpr272(a):
    """MotionStreamer / MotionMillion 272-dim features -> world joint positions (T, 22, 3), Y-up metres.
    [0:2] root xz velocity in the heading frame, [2:8] heading change (6D, columns), [8:74] the 22 SMPL joints in the
    heading frame, [74:140] their velocities, [140:272] 6D joint rotations. Heading and root are integrated; the
    convention was chosen by the least foot skating over sample clips."""
    T = len(a); P = a[:, 8:74].reshape(T, 22, 3); D = _rot6d_cols(a[:, 2:8])
    R, root, out = np.eye(3), np.zeros(3), np.zeros_like(P)
    for t in range(T):
        out[t] = P[t] @ R.T + root
        root = root + R @ np.array([a[t, 0], 0.0, a[t, 1]])
        R = R @ D[t]
    return out


def convert_rpr272(src, ds_name, fps=30.0):
    """MotionStreamer / MotionMillion 272-dim features -> AMASS-style SMPL-X npz. The 6D rotations ([140:272], rows) are
    SMPL-X body joint rotations relative to the parent (the root's relative to the heading): with the neutral SMPL-X
    skeleton they reproduce the stored joint positions. Heading and root are integrated (recover_rpr272); hands, jaw and
    eyes stay at rest; the shape is neutral (the format keeps none). The 272 vector is kept as `features`."""
    a = np.load(src, allow_pickle=False)
    if a.ndim != 2 or a.shape[1] != 272:
        raise ValueError(f'unexpected shape {a.shape}')
    a = a.astype(np.float64); T = len(a)
    world = recover_rpr272(a)
    D = _rot6d_cols(a[:, 2:8]); H = np.empty((T, 3, 3)); R = np.eye(3)
    for t in range(T):
        H[t] = R; R = R @ D[t]
    Rl = _rot6d_rows(a[:, 140:272].reshape(T, 22, 6))
    Rl[:, 0] = H @ Rl[:, 0]                                       # the root in world
    poses = np.zeros((T, 55, 3)); poses[:, :22] = _matrix_to_axis_angle(Rl.reshape(-1, 3, 3)).reshape(T, 22, 3)
    m = smplmodel.model('smplx', 'neutral', os.environ.get('AAD_VAULT') or _vault_root())
    _, J = smplmodel.shape(m, np.zeros(10))
    d = dict(poses=poses.reshape(T, 165).astype(np.float32), trans=(world[:, 0] - J[0]).astype(np.float32), betas=np.zeros(10, np.float32),
             gender=np.array('neutral'), surface_model_type=np.array('smplx'), mocap_framerate=np.float64(fps),
             mv_kind=np.array('smpl'), mv_source=np.array('rpr272'), features=a.astype(np.float32))
    return d, dict(frames=T, fps=fps, joints=55, channels=165, desc='', src_bytes=os.path.getsize(src))


def _vault_root():
    from .. import config
    return config.get('vault')


def kit_parents():
    par = [-1] * 21
    for ch in KIT_CHAINS:
        for a, b in zip(ch[:-1], ch[1:]):
            par[b] = a
    return par


def is_adapter_file(rel, mode='auto'):
    """does this source file get its own clip? mode: 'motionx' = every .npy, 'joints' = the ones in new_joints/ (their siblings are
    read together with them), 'auto' = decide from the path"""
    r = '/' + rel.replace('\\', '/')
    if not r.endswith('.npy'):
        return False
    return {'motionx': True, 'rpr272': True, 'joints': '/new_joints/' in r}.get(mode, '/new_joints/' in r or 'smplx_322' in r)


def kind_of(rel, mode='auto'):
    return mode if mode in ('motionx', 'joints', 'rpr272') else ('joints' if '/new_joints/' in '/' + rel.replace('\\', '/') else 'motionx')


def group_for(name):
    """bucket numbered clips by thousands: 000123 -> 000xxx"""
    m = re.match(r'^([A-Za-z]*)(\d+)$', name)
    return f'{m.group(1)}{m.group(2)[:-3]}xxx' if m and len(m.group(2)) > 3 else name


def _same(a, b):
    return a.shape == b.shape and a.dtype == b.dtype and bool(np.array_equal(a, b))


def convert_motionx(src, ds_name):
    x = np.load(src)
    if x.ndim != 2 or x.shape[1] != 322:
        raise ValueError(f'unexpected shape {x.shape}')
    T = len(x)
    ro, body, hand, jaw, expr, shape, trans, betas = (x[:, a:b] for a, b in ((0, 3), (3, 66), (66, 156), (156, 159), (159, 209), (209, 309), (309, 312), (312, 322)))
    poses = np.concatenate([ro, body, jaw, np.zeros((T, 6), x.dtype), hand], axis=1)
    d = dict(poses=poses, trans=trans, face_expr=expr, gender=np.array('neutral'), surface_model_type=np.array('smplx'),
             mocap_framerate=np.float64(30.0), mv_kind=np.array('smpl'), mv_source=np.array('motionx-smplx322'))
    d['betas'] = betas[0].copy() if (betas == betas[0]).all() else betas[0].copy()
    if not (betas == betas[0]).all():
        d['betas_t'] = betas
    d['face_shape'] = shape[0].copy() if (shape == shape[0]).all() else shape
    # exactness: the 322 vector must be rebuildable from what is stored
    b_full = d['betas_t'] if 'betas_t' in d else np.tile(d['betas'], (T, 1))
    s_full = d['face_shape'] if d['face_shape'].ndim == 2 else np.tile(d['face_shape'], (T, 1))
    back = np.concatenate([poses[:, 0:3], poses[:, 3:66], poses[:, 75:165], poses[:, 66:69], d['face_expr'], s_full, trans, b_full], axis=1)
    if not _same(back, x):
        raise ValueError('322-vector is not rebuildable from the stored fields')
    return d, dict(frames=T, fps=30.0, joints=55, channels=165, desc='')


def convert_joints(src, ds_name):
    pos = np.load(src)
    squeezed = pos.ndim == 2                                  # a one-frame clip saved without its time axis
    if squeezed:
        pos = pos[None]
    if pos.ndim != 3 or pos.shape[2] != 3:
        raise ValueError(f'unexpected shape {pos.shape}')
    J = pos.shape[1]
    base = os.path.basename(src)[:-4]; ddir = os.path.dirname(os.path.dirname(src))
    vecs_p, txt_p = os.path.join(ddir, 'new_joint_vecs', base + '.npy'), os.path.join(ddir, 'texts', base + '.txt')
    vecs = np.load(vecs_p) if os.path.exists(vecs_p) else None
    text = open(txt_p, encoding='utf-8', errors='replace').read() if os.path.exists(txt_p) else ''
    if J == 22:
        par, names = T2M_PARENTS, smplmodel.BODY
    elif J == 21:
        par, names = kit_parents(), [f'joint_{i}' for i in range(21)]
    else:
        raise ValueError(f'unsupported joint count {J}')
    fps = FPS.get(ds_name, 20.0)
    d = dict(mv_kind=np.array('joints'), positions=pos, parents=np.array(par, np.int32), joint_names=np.array(names), fps=np.float64(fps), text=np.array(text))
    if vecs is not None:
        d['vecs'] = vecs
    if squeezed:
        d['squeezed'] = np.bool_(True)
    cap = next((ln.split('#')[0].strip() for ln in text.splitlines() if ln.strip()), '')
    srcb = os.path.getsize(src) + (os.path.getsize(vecs_p) if vecs is not None else 0) + (os.path.getsize(txt_p) if text else 0)
    return d, dict(frames=len(pos), fps=fps, joints=J, channels=J * 3, desc=cap[:140], src_bytes=srcb)
