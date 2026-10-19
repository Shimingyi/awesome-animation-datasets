"""Extract chosen members of a huge remote .zip with HTTP range requests (only those bytes are downloaded).

    python -m tools.examples.zip_select <url or file of urls> <out dir> [--skip-dir smplx_mesh_betas --head-dir smplx_mesh_betas] [--workers 8]

Members whose path contains a --skip-dir folder are not downloaded; with --head-dir, of such an .npy only the header and
the first row are kept (e.g. Embody 3D stores the same 300 shape coefficients on every frame: 65 % of its bytes).
Files land under <out dir> with their path inside the zip; existing files of the right size are skipped (resumable).
"""
import argparse
import io
import os
import zipfile
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from .hf_zip import HttpFile


def first_row(z, info):
    """header + first row of an uncompressed .npy member, without reading the rest"""
    with z.open(info) as f:
        head = f.read(4096)
    bio = io.BytesIO(head)
    ver = np.lib.format.read_magic(bio)
    shape, fortran, dtype = np.lib.format._read_array_header(bio, ver)
    row = int(np.prod(shape[1:])) * dtype.itemsize
    with z.open(info) as f:
        data = f.read(bio.tell() + row)
    return np.frombuffer(data[bio.tell():], dtype=dtype, count=int(np.prod(shape[1:]))).reshape((1,) + tuple(shape[1:]))


def run(url, out, skip_dirs, head_dirs, workers):
    probe = HttpFile(url, {})
    z = zipfile.ZipFile(io.BufferedReader(probe, buffer_size=1 << 16))
    todo = []
    for i in z.infolist():
        if i.is_dir():
            continue
        parts = i.filename.split('/')
        dst = os.path.join(out, *[p for p in parts if p not in ('..', '')])
        head = any(d in parts for d in head_dirs)
        if any(d in parts for d in skip_dirs) and not head:
            continue
        if os.path.exists(dst) and (head or os.path.getsize(dst) == i.file_size):
            continue
        todo.append((i, dst, head))
    print(f'{os.path.basename(url.split("?")[0])}: {len(todo)} members to fetch', flush=True)

    def one(job, local={}):
        import threading
        t = threading.get_ident()
        if t not in local:                                   # one HTTP connection + zip reader per thread
            local[t] = zipfile.ZipFile(io.BufferedReader(HttpFile(url, {}), buffer_size=1 << 16))
        zt = local[t]
        info, dst, head = job
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if head:
            np.save(dst, first_row(zt, zt.getinfo(info.filename)))
        else:
            with open(dst + '.part', 'wb') as f:
                f.write(zt.read(info.filename))
            os.replace(dst + '.part', dst)
        return dst
    n = 0
    with ThreadPoolExecutor(workers) as ex:
        for _ in ex.map(one, todo):
            n += 1
            if n % 500 == 0 or n == len(todo):
                print(f'  {n}/{len(todo)}', flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src', help='a URL, or a text file with one URL per line')
    ap.add_argument('out')
    ap.add_argument('--skip-dir', action='append', default=[])
    ap.add_argument('--head-dir', action='append', default=[])
    ap.add_argument('--workers', type=int, default=8)
    a = ap.parse_args()
    urls = [l.strip() for l in open(a.src) if l.strip()] if os.path.exists(a.src) else [a.src]
    for u in urls:
        run(u, a.out, a.skip_dir, a.head_dir, a.workers)


if __name__ == '__main__':
    main()
