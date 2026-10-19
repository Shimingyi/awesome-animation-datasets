"""Pull a few files out of a huge .zip on the Hugging Face Hub with HTTP range requests (a zip's directory is at its end,
so only that directory and the chosen members are downloaded).

    python -m tools.examples.hf_zip Ericguo5513/SnapMoGen renamed_bvhs.zip <out dir> --n 10 --ext .bvh [--skip M]

Members are spread over the archive's name groups (the part before the first '_'); names starting with --skip
(mirrored copies, case-insensitive) are left out. Files are written under <out dir> by their base name.
"""
import argparse
import io
import json
import os
import zipfile


class HttpFile(io.RawIOBase):
    """a seekable, read-only file over HTTP range requests"""
    def __init__(self, url, headers):
        import httpx
        self.c = httpx.Client(headers=headers, follow_redirects=True, timeout=120)
        r = self.c.head(url)
        self.url, self.size, self.pos, self.got = str(r.url), int(r.headers['content-length']), 0, 0

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else self.pos + off if whence == 1 else self.size + off
        return self.pos

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.size - self.pos
        if n == 0 or self.pos >= self.size:
            return b''
        end = min(self.size, self.pos + n) - 1
        for attempt in range(6):                         # servers drop long keep-alive connections now and then
            try:
                b = self.c.get(self.url, headers={'Range': f'bytes={self.pos}-{end}'}).content
                break
            except Exception:  # noqa: BLE001
                if attempt == 5:
                    raise
                import time
                time.sleep(2 * (attempt + 1))
        self.pos += len(b); self.got += len(b)
        return b

    def readinto(self, buf):
        b = self.read(len(buf)); buf[:len(b)] = b
        return len(b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('repo'); ap.add_argument('archive'); ap.add_argument('out')
    ap.add_argument('--n', type=int, default=10); ap.add_argument('--ext', default='.bvh'); ap.add_argument('--skip', default='')
    a = ap.parse_args()
    from huggingface_hub import get_token, hf_hub_url
    f = HttpFile(hf_hub_url(a.repo, a.archive, repo_type='dataset'), {'Authorization': f'Bearer {get_token()}'} if get_token() else {})
    z = zipfile.ZipFile(io.BufferedReader(f, buffer_size=1 << 16))
    names = [n for n in z.namelist() if n.endswith(a.ext) and not (a.skip and os.path.basename(n).lower().startswith(a.skip.lower()))]
    groups = {}
    for n in sorted(names):
        groups.setdefault(os.path.basename(n).split('_')[0], []).append(n)
    keys, pick, r = sorted(groups), [], 0                 # round robin over the groups, from the middle of each
    while len(pick) < min(a.n, len(names)):
        for k in keys:
            g = groups[k]; i = len(g) // 2 + r * (len(g) // 3 + 1)
            if len(pick) < a.n and r * (len(g) // 3 + 1) < len(g):
                pick.append(g[i % len(g)])
        r += 1
    os.makedirs(a.out, exist_ok=True)
    kept = []
    for n in pick:
        with open(os.path.join(a.out, os.path.basename(n)), 'wb') as fo:
            fo.write(z.read(n))
        kept.append(dict(file=os.path.basename(n), group=os.path.basename(n).split('_')[0]))
        print(f'  {os.path.basename(n)}  ({f.got / 1e6:.1f} MB read)', flush=True)
    with open(os.path.join(a.out, 'picked.json'), 'w') as fo:
        json.dump(kept, fo, indent=1)
    print(f'{len(kept)} of {len(names)} files from {len(keys)} groups, {f.got / 1e6:.1f} MB read -> {a.out}')


if __name__ == '__main__':
    main()
