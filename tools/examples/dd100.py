"""DD100 (Duolando) duet takes -> SMPL-X npz in the AMASS layout (one file per dancer), for `smpl:` example items.

    python3 -I tools/examples/dd100.py <data/motion/smplx/all> Waltz_001_004 Tango_002_029 ... --out build/dd100/npz

Each take is <GENRE>_<CHOREO>_<TAKE>_00.npy (follower, female) + _01.npy (leader, male): a pickled dict with poses
(T,165) SMPL-X axis-angle, global_orient, transl, betas (T,16) and meta.gender. The release is Z-up, 30 fps, flat hand
mean (lisiyao21/Duolando _prepare_motion_data.py, datasets/dd100lf_all2.py), so poses are copied as they are.
The output is named <take>_{leader,follower}.npz by meta.gender: 12 Tango / Waltz takes (one couple) store the man in _00.
The dicts are read through a pickle.Unpickler that only lets numpy arrays through (the files are untrusted downloads).
"""
import argparse
import os
import pickle

import numpy as np
from numpy.lib import format as npf

SAFE = {('numpy.core.multiarray', '_reconstruct'), ('numpy._core.multiarray', '_reconstruct'), ('numpy', 'ndarray'),
        ('numpy', 'dtype'), ('numpy.core.multiarray', 'scalar'), ('numpy._core.multiarray', 'scalar'),
        ('collections', 'OrderedDict'), ('builtins', 'dict'), ('builtins', 'list')}
ROLE = {'male': 'leader', 'female': 'follower'}   # the man leads in every DD100 genre


class _Unpickler(pickle.Unpickler):
    def find_class(self, module, name):
        if (module, name) in SAFE:
            return super().find_class(module, name)
        raise pickle.UnpicklingError(f'refusing {module}.{name}')


def load_dict(path):
    """np.load(path, allow_pickle=True).item() without running arbitrary pickled code"""
    with open(path, 'rb') as f:
        npf._read_array_header(f, npf.read_magic(f))
        a = _Unpickler(f, encoding='latin1').load()
    return a.item() if isinstance(a, np.ndarray) else a


def dancer(path):
    d = load_dict(path)
    return dict(poses=np.asarray(d['poses'], np.float32), trans=np.asarray(d['transl'], np.float32),
                betas=np.asarray(d['betas'], np.float32)[0], gender=np.array(str(d['meta']['gender'])),
                mocap_framerate=np.float64(30))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('root'); ap.add_argument('takes', nargs='+'); ap.add_argument('--out', required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for t in a.takes:
        for s in ('00', '01'):
            z = dancer(os.path.join(a.root, f'{t}_{s}.npy'))
            out = os.path.join(a.out, f'{t}_{ROLE[str(z["gender"])]}.npz')
            np.savez_compressed(out, **z)
            print(f'{os.path.basename(out)}: {len(z["poses"])} frames, {z["gender"]}')


if __name__ == '__main__':
    main()
