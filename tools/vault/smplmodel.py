"""SMPL / SMPL-X body models, reduced to what the viewer needs (no torch, no chumpy).

Sources (not shipped, they carry the MPI licence): SMPLX_{NEUTRAL,MALE,FEMALE}.npz and SMPL_{NEUTRAL,MALE,FEMALE}.pkl.
The first time a model is used it is cut down to <root>/models/<kind>_<gender>.npz:
    v_template (V,3)  shapedirs (V,3,16)  J_regressor (J,V)  weights (V,J)  parents (J,)  faces (F,3)
Look-up: the directory $SMPL_MODELS, else config.local.yaml `smpl_models` (see SEARCH).
Pose correctives (posedirs) are not applied: the mesh is shape + linear blend skinning only, which is what the
viewer needs to judge a motion.
"""
import os
import pickle

import numpy as np

SEARCH = {                                   # {d} = $SMPL_MODELS or config.local.yaml `smpl_models`
    'smplx': ['{d}/SMPLX_{G}.npz', '{d}/smplx/SMPLX_{G}.npz'],
    'smpl': ['{d}/SMPL_{G}.pkl', '{d}/smpl/SMPL_{G}.pkl', '{d}/smpl/smpl/SMPL_{G}.pkl'],
}
NB = 16
BODY = ['pelvis', 'left_hip', 'right_hip', 'spine1', 'left_knee', 'right_knee', 'spine2', 'left_ankle', 'right_ankle', 'spine3',
        'left_foot', 'right_foot', 'neck', 'left_collar', 'right_collar', 'head', 'left_shoulder', 'right_shoulder', 'left_elbow',
        'right_elbow', 'left_wrist', 'right_wrist']
FINGERS = [f'{f}{i}' for f in ('index', 'middle', 'pinky', 'ring', 'thumb') for i in (1, 2, 3)]
NAMES = {'smpl': BODY + ['left_hand', 'right_hand'],
         'smplx': BODY + ['jaw', 'left_eye', 'right_eye'] + ['left_' + f for f in FINGERS] + ['right_' + f for f in FINGERS]}


class _Stub:                                   # stands in for chumpy.Ch while unpickling the official SMPL .pkl
    def __init__(self, *a, **k):
        pass

    def __setstate__(self, st):
        self.__dict__.update(st if isinstance(st, dict) else {'x': st})


class _Unpickler(pickle.Unpickler):
    def find_class(self, module, name):
        return _Stub if module.startswith('chumpy') else super().find_class(module, name)


def _arr(v):
    v = getattr(v, 'x', v)
    if hasattr(v, 'toarray'):
        v = v.toarray()
    return np.asarray(v)


def _find(kind, gender):
    from .. import config
    d = os.environ.get('SMPL_MODELS') or config.get('smpl_models') or '/nonexistent'
    for g in (gender.upper(), 'NEUTRAL'):
        for pat in SEARCH[kind]:
            p = pat.format(d=d, G=g)
            if os.path.exists(p):
                return p, g.lower()
    raise FileNotFoundError(f'no {kind} model found (put {kind.upper()}_NEUTRAL.* under $SMPL_MODELS)')


def _build(kind, gender):
    src, g = _find(kind, gender)
    if src.endswith('.npz'):
        z = np.load(src, allow_pickle=True)
        d = {k: z[k] for k in ('v_template', 'shapedirs', 'J_regressor', 'weights', 'kintree_table', 'f')}
    else:
        d = _Unpickler(open(src, 'rb'), encoding='latin1').load()
        d = {k: _arr(d[k]) for k in ('v_template', 'shapedirs', 'J_regressor', 'weights', 'kintree_table', 'f')}
    par = d['kintree_table'][0].astype(np.int64); par[0] = -1
    return g, dict(v_template=d['v_template'].astype(np.float32), shapedirs=d['shapedirs'][:, :, :NB].astype(np.float32),
                   J_regressor=d['J_regressor'].astype(np.float32), weights=d['weights'].astype(np.float32),
                   parents=par.astype(np.int32), faces=d['f'].astype(np.int32))


def hands_mean():
    """SMPL-X mean hand pose (90,) axis-angle, left then right: what a clip saved with flat_hand_mean=False is relative to"""
    if 'hands_mean' not in _mem:
        src, _ = _find('smplx', 'neutral')
        if src.endswith('.npz'):
            z = np.load(src, allow_pickle=True)
            d = {k: z[k] for k in ('hands_meanl', 'hands_meanr')}
        else:
            d = _Unpickler(open(src, 'rb'), encoding='latin1').load()
        _mem['hands_mean'] = np.concatenate([_arr(d['hands_meanl']), _arr(d['hands_meanr'])]).astype(np.float32)
    return _mem['hands_mean']


_mem = {}


def model(kind, gender, cache_dir):
    """-> dict (see module doc) for kind 'smpl'|'smplx' and gender 'neutral'|'male'|'female' (falls back to neutral)."""
    gender = str(gender).lower()
    key = (kind, gender)
    if key in _mem:
        return _mem[key]
    path = os.path.join(cache_dir, 'models', f'{kind}_{gender}.npz')
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        g, m = _build(kind, gender)
        path = os.path.join(cache_dir, 'models', f'{kind}_{g}.npz')
        if not os.path.exists(path):
            np.savez_compressed(path, **m)
    with np.load(path) as z:
        m = {k: z[k] for k in z.files}
    _mem[key] = m
    return m


def shape(m, betas):
    """-> v_shaped (V,3) float32, rest joints (J,3) float32 for the given betas."""
    k = m['shapedirs'].shape[2]
    b = np.zeros(k, np.float32); bb = np.asarray(betas, np.float32).reshape(-1)[:k]; b[:len(bb)] = bb
    v = m['v_template'] + m['shapedirs'] @ b
    return v.astype(np.float32), (m['J_regressor'] @ v).astype(np.float32)


def skin_weights(m, K=6):
    """Sparse top-K skinning weights -> (idx uint8 (V,K), w float32 (V,K)), rows renormalised."""
    W = m['weights']
    idx = np.argsort(-W, axis=1)[:, :K]
    w = np.take_along_axis(W, idx, axis=1)
    w = w / np.maximum(w.sum(1, keepdims=True), 1e-9)
    return idx.astype(np.uint8), w.astype(np.float32)


def pose_layout(width):
    """-> (kind, pose array mapping) for an AMASS-style `poses` width: 72 SMPL, 165 SMPL-X, 156 SMPL-H (-> SMPL-X)."""
    if width == 72:
        return 'smpl'
    if width in (165, 156):
        return 'smplx'
    raise ValueError(f'unsupported pose width {width}')


def to_model_pose(poses, kind):
    """(T,W) axis-angle -> (T, 3*J) in the model's joint order."""
    poses = np.asarray(poses, np.float32)
    if kind == 'smplx' and poses.shape[1] == 156:                       # SMPL-H: insert jaw + eyes (zeros)
        return np.concatenate([poses[:, :66], np.zeros((len(poses), 9), np.float32), poses[:, 66:]], axis=1)
    return poses
