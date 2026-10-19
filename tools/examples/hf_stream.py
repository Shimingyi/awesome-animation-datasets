"""Pull a few example clips out of a huge .tar.gz on the Hugging Face Hub without downloading all of it.

    python -m tools.examples.hf_stream bones-studio/seed soma_uniform.tar.gz <out dir> --n 10 --budget-mb 800 \
        [--meta metadata/seed_metadata_v004.csv --key filename --group category --skip-col is_mirror]

The archive is read as a stream (gzip has no random access) until --n clips are kept or --budget-mb compressed bytes
have been read; then the connection is closed. Only members ending in --ext (default .bvh) are kept, written under
<out dir> as their archive path with '/' -> '__' (never as a path of their own). With --meta, a member is kept only if its row's --group value is new, so the
examples spread over the dataset's categories; rows whose --skip-col is "True" (mirrored copies) are skipped.
"""
import argparse
import csv
import json
import os
import tarfile


class _Counting:
    """file-like over the HTTP stream that stops after `budget` bytes"""
    def __init__(self, it, budget):
        self.it, self.buf, self.n, self.budget = it, b'', 0, budget

    def read(self, size=-1):
        while (size < 0 or len(self.buf) < size) and self.n < self.budget:
            chunk = next(self.it, b'')
            if not chunk:
                break
            self.n += len(chunk); self.buf += chunk
        out, self.buf = (self.buf, b'') if size < 0 else (self.buf[:size], self.buf[size:])
        return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('repo'); ap.add_argument('archive'); ap.add_argument('out')
    ap.add_argument('--n', type=int, default=10); ap.add_argument('--budget-mb', type=float, default=800)
    ap.add_argument('--meta'); ap.add_argument('--key', default='filename'); ap.add_argument('--group', default='category')
    ap.add_argument('--skip-col')
    ap.add_argument('--ext', default='.bvh')
    ap.add_argument('--skip', default='', help='skip members whose path contains this (e.g. mirror)')
    a = ap.parse_args()
    import httpx
    from huggingface_hub import get_token, hf_hub_download, hf_hub_url
    rows = {}
    if a.meta:
        with open(hf_hub_download(a.repo, a.meta, repo_type='dataset', local_dir=a.out)) as f:
            rows = {r[a.key]: r for r in csv.DictReader(f)}
    url = hf_hub_url(a.repo, a.archive, repo_type='dataset')
    headers = {'Authorization': f'Bearer {get_token()}'} if get_token() else {}
    os.makedirs(a.out, exist_ok=True)
    kept, groups = [], set()
    with httpx.stream('GET', url, headers=headers, follow_redirects=True, timeout=120) as r:
        r.raise_for_status()
        src = _Counting(r.iter_bytes(1 << 20), a.budget_mb * 1e6)
        try:
            with tarfile.open(fileobj=src, mode='r|gz') as tar:
                for m in tar:
                    if not m.isfile() or not m.name.endswith(a.ext) or (a.skip and a.skip.lower() in m.name.lower()):
                        continue
                    stem = os.path.basename(m.name)[:-len(a.ext)]
                    row = rows.get(stem, {})
                    if rows and (not row or (a.skip_col and row.get(a.skip_col) == 'True') or row.get(a.group) in groups):
                        continue
                    data = tar.extractfile(m).read()
                    name = os.path.basename(m.name) if rows else m.name.replace('..', '_').lstrip('./').replace('/', '__')
                    with open(os.path.join(a.out, name), 'wb') as f:
                        f.write(data)
                    groups.add(row.get(a.group)); kept.append(dict(file=name, group=row.get(a.group, ''),
                                                                   desc=row.get('content_short_description', '')))
                    print(f'  {len(kept):2d} {stem}  [{row.get(a.group, "")}]  {src.n / 1e6:.0f} MB read', flush=True)
                    if len(kept) >= a.n:
                        break
        except (tarfile.ReadError, EOFError):
            pass                                            # the byte budget ended the stream mid-archive
    p = os.path.join(a.out, 'picked.json')                  # appended to: several archives can feed one folder
    old = json.load(open(p)) if os.path.exists(p) else []
    with open(p, 'w') as f:
        json.dump(old + [k for k in kept if k['file'] not in {o['file'] for o in old}], f, indent=1)
    print(f'{len(kept)} clips, {src.n / 1e6:.0f} MB read -> {a.out}/picked.json')


if __name__ == '__main__':
    main()
