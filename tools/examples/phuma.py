"""PHUMA (DAVIAN-Robotics/PHUMA on the Hub) -> joint-angle CSVs for tools/examples/urdf2clip.py.

    python -m tools.examples.phuma <out dir> <member prefix> ... [--robot g1]

A member prefix is a clip path inside data.zip without its _chunk_NNNN.npy suffix, e.g. humanml/014501. The release
cuts every clip into ~4 s chunks that do not join up (they are separate training windows), so one chunk is taken (the
middle one, or --chunk N), fetched with HTTP range requests (tools/examples/hf_zip.py) and written as <out dir>/<name>.csv
(root xyz, root quaternion xyzw, then dof_pos in the robot's URDF joint order). fps is kept in <out dir>/fps.json.

Each .npy holds a pickled dict {root_trans, root_ori, dof_pos, fps}; it is read with an unpickler that only rebuilds
numpy arrays and plain dicts (never np.load(allow_pickle=True)).
"""
import argparse
import io
import json
import os
import pickle
import re
import zipfile

import numpy as np

ALLOWED = {('numpy.core.multiarray', '_reconstruct'), ('numpy._core.multiarray', '_reconstruct'), ('numpy', 'ndarray'),
           ('numpy', 'dtype'), ('numpy.core.multiarray', 'scalar'), ('numpy._core.multiarray', 'scalar'),
           ('builtins', 'dict'), ('collections', 'OrderedDict')}


class _Unpickler(pickle.Unpickler):
    def find_class(self, module, name):
        if (module, name) not in ALLOWED:
            raise pickle.UnpicklingError(f'blocked {module}.{name}')
        return super().find_class(module, name)


def load_npy_dict(data):
    """bytes of an .npy holding a 0-d object array (a pickled dict) -> the dict"""
    f = io.BytesIO(data)
    ver = np.lib.format.read_magic(f)
    np.lib.format._read_array_header(f, ver)
    obj = _Unpickler(f).load()
    return obj.item() if isinstance(obj, np.ndarray) else obj


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out'); ap.add_argument('clips', nargs='+'); ap.add_argument('--robot', default='g1')
    ap.add_argument('--chunk', type=int, help='chunk index (default: the middle one)')
    a = ap.parse_args()
    from huggingface_hub import get_token, hf_hub_url
    from .hf_zip import HttpFile
    t = get_token()
    z = zipfile.ZipFile(HttpFile(hf_hub_url('DAVIAN-Robotics/PHUMA', 'data.zip', repo_type='dataset'),
                                 {'Authorization': f'Bearer {t}'} if t else {}))
    names = [n for n in z.namelist() if n.startswith(f'data/{a.robot}/') and n.endswith('.npy')]
    os.makedirs(a.out, exist_ok=True)
    fps_path = os.path.join(a.out, 'fps.json')
    fps = json.load(open(fps_path)) if os.path.exists(fps_path) else {}
    for clip in a.clips:
        pre = f'data/{a.robot}/{clip}_chunk_'
        chunks = sorted(n for n in names if n.startswith(pre) and re.fullmatch(r'\d+\.npy', n[len(pre):]))
        if not chunks:
            print(f'{clip}: no chunks'); continue
        p = load_npy_dict(z.read(chunks[len(chunks) // 2 if a.chunk is None else a.chunk]))
        rows = np.concatenate([np.asarray(p['root_trans']), np.asarray(p['root_ori']), np.asarray(p['dof_pos'])], 1)
        name = clip.replace('/', '__')
        np.savetxt(os.path.join(a.out, name + '.csv'), rows, delimiter=',', fmt='%.6f')
        fps[name] = float(np.asarray(p['fps']))
        print(f'{clip}: chunk of {len(chunks)}, {len(rows)} frames at {fps[name]:g} fps, {rows.shape[1] - 7} dof')
    json.dump(fps, open(fps_path, 'w'), indent=1)


if __name__ == '__main__':
    main()
