"""BVH <-> npz, byte-exact.

A BVH file is a text header (HIERARCHY ... Frame Time) followed by one line of numbers per frame. Almost every file in
our datasets prints those numbers with exactly 6 decimals, so they are stored as integers (value * 1e6): `-10.341831`
becomes `-10341831`. Decoding prints them back the same way, and `encode` refuses (returns the text-mode fallback)
unless decode(encode(x)) == x, so every npz reproduces its source file byte for byte.

npz layout, mode "fixed6" (the usual case):
    format          'bvh-fixed6-v1'
    header          str, original text up to and including the "Frame Time:" line (latin-1 view of the bytes)
    motion          int32 (frames, channels), value*1e6; stored as the difference to the previous frame (cumsum to undo)
    negzero         int64 flat indices of tokens printed as "-0.000000" (an int cannot carry that sign)
    crlf, trailing_space, final_newline, width, sep    line-format flags: a row is sep.join(tokens right-aligned to `width`) [+ ' '];
                    files written before `sep` existed have none, meaning ' '
    sha256          of the original file
    joint_names, parents, offsets          skeleton (End Sites appear as '<parent>_End'), parents[0] = -1
    channel_joint, channel_name            what each motion column is, e.g. ('Hips', 'Xposition')
    frame_time      seconds per frame
mode "text" (fallback, e.g. values printed with variable precision): `text` holds the whole file, plus the same
skeleton fields; `motion` is not stored.
"""
import hashlib
import re

import numpy as np

SCALE = 1_000_000


def parse_header(header: str):
    """-> names, parents, offsets, channel_joint, channel_name, frame_time, (frames) from the BVH header text."""
    names, parents, offsets, ch_joint, ch_name = [], [], [], [], []
    stack, pending_end = [], False
    toks = header.replace('{', ' { ').replace('}', ' } ').split()
    i = 0
    while i < len(toks):
        t = toks[i].upper()                                  # keywords are matched case-insensitively ("End site" exists in the wild)
        if t in ('ROOT', 'JOINT'):
            names.append(toks[i + 1]); parents.append(stack[-1] if stack else -1); offsets.append(None)
            stack.append(len(names) - 1); i += 2; continue
        if t == 'END' and toks[i + 1].upper() == 'SITE':
            names.append(names[stack[-1]] + '_End'); parents.append(stack[-1]); offsets.append(None)
            stack.append(len(names) - 1); i += 2; continue
        if t == 'OFFSET':
            offsets[stack[-1]] = [float(toks[i + 1]), float(toks[i + 2]), float(toks[i + 3])]; i += 4; continue
        if t == 'CHANNELS':
            n = int(toks[i + 1])
            for c in toks[i + 2:i + 2 + n]:
                ch_joint.append(names[stack[-1]]); ch_name.append(c)
            i += 2 + n; continue
        if t == '}':
            stack.pop()
        i += 1
    m = re.search(r'Frame Time:\s*([0-9.eE+-]+)', header)
    return (np.array(names), np.array(parents, np.int32), np.array(offsets, np.float64),
            np.array(ch_joint), np.array(ch_name), float(m.group(1)) if m else 0.0)


def _skeleton_fields(header):
    names, parents, offsets, cj, cn, ft = parse_header(header)
    return dict(joint_names=names, parents=parents, offsets=offsets, channel_joint=cj, channel_name=cn,
                frame_time=np.float64(ft))


def _split(raw: bytes):
    i = raw.find(b'Frame Time:')
    if i < 0:
        return None
    j = raw.find(b'\n', i) + 1
    return raw[:j], raw[j:]


def _render_body(A, negzero, crlf, trailing_space, final_newline, width=0, sep=' '):
    """int64 (frames, channels) fixed-point -> the motion lines as bytes.
    Row = sep.join(token right-aligned to `width`) [+ ' ']. '%.6f' of v/1e6 prints exactly the 6-digit decimal v came from."""
    T, n = A.shape
    x = np.ascontiguousarray(A, dtype=np.float64) / SCALE
    if len(negzero):
        x.reshape(-1)[negzero] = -0.0
    row = sep.join([('%' + (str(width) if width else '') + '.6f')] * n) + (' ' if trailing_space else '')
    nl = '\r\n' if crlf else '\n'
    body = nl.join([row % tuple(r) for r in x.tolist()]) + (nl if final_newline else '')
    return body.encode('latin-1')


def encode(raw: bytes) -> dict:
    """-> dict of arrays for save(). Always lossless: any file that does not round-trip is kept as text."""
    import re
    sha = np.array(hashlib.sha256(raw).hexdigest())
    sp = _split(raw)
    try:
        if sp is None:
            raise ValueError('no motion block')
        head, body = sp
        header = head.decode('latin-1')
        sk = _skeleton_fields(header)
        crlf = b'\r\n' in body
        b2 = body.replace(b'\r\n', b'\n') if crlf else body
        if b'\r' in b2:
            raise ValueError('mixed line endings')
        final_nl = b2.endswith(b'\n')
        lines = b2.split(b'\n')
        if final_nl:
            lines = lines[:-1]
        n = len(lines[0].split())
        x = np.fromstring(b2, dtype=np.float64, sep=' ')          # whitespace-separated numbers (newlines count)
        if x.size != n * len(lines):
            raise ValueError('ragged rows')
        A = np.rint(x * SCALE).astype(np.int64).reshape(len(lines), n)
        negzero = np.flatnonzero(np.signbit(x) & (x == 0)).astype(np.int64)
        if np.abs(A).max() >= 2 ** 31:
            raise ValueError('out of int32 range')
        # row layout: sep.join(token right-aligned to `width`) [+ ' ']; find it from the first row, then verify everything
        m = re.search(rb'\S(\s+)\S', lines[0])
        seps = [m.group(1).decode('latin-1')] if m else []
        if ' ' not in seps:
            seps.append(' ')
        row0, nz0, found = A[:1], negzero[negzero < n], None
        for sep in seps:
            for width in range(0, 20):
                for trailing in (False, True):
                    if _render_body(row0, nz0, False, trailing, False, width, sep) == lines[0]:
                        found = (sep, width, trailing); break
                if found:
                    break
            if found:
                break
        if not found:
            raise ValueError('unknown row layout')
        sep, width, trailing = found
        if head + _render_body(A, negzero, crlf, trailing, final_nl, width, sep) != raw:
            raise ValueError('not reproducible')
        D = np.diff(A, axis=0, prepend=0).astype(np.int32)
        return dict(format=np.array('bvh-fixed6-v1'), header=np.array(header), motion=D, negzero=negzero,
                    crlf=np.bool_(crlf), trailing_space=np.bool_(trailing), final_newline=np.bool_(final_nl),
                    width=np.int32(width), sep=np.array(sep), sha256=sha, **sk)
    except Exception:
        text = raw.decode('latin-1')
        header = text[:text.find('\n', text.find('Frame Time:')) + 1] if 'Frame Time:' in text else text
        try:
            sk = _skeleton_fields(header)
        except Exception:
            sk = {}
        return dict(format=np.array('bvh-text-v1'), text=np.array(text), sha256=sha, **sk)


def decode(z) -> bytes:
    """npz (NpzFile or dict) -> the original BVH bytes."""
    fmt = str(z['format'])
    if fmt == 'bvh-text-v1':
        raw = str(z['text']).encode('latin-1')
    else:
        A = np.cumsum(z['motion'].astype(np.int64), axis=0)
        raw = str(z['header']).encode('latin-1') + _render_body(
            A, z['negzero'], bool(z['crlf']), bool(z['trailing_space']), bool(z['final_newline']), int(z['width']),
            str(z['sep']) if 'sep' in z else ' ')
    if hashlib.sha256(raw).hexdigest() != str(z['sha256']):
        raise ValueError('sha256 mismatch after decode')
    return raw


def motion_float(z):
    """-> float32 (frames, channels) in BVH units (degrees / cm). Works for both modes."""
    if str(z['format']) == 'bvh-fixed6-v1':
        return (np.cumsum(z['motion'].astype(np.int64), axis=0) / SCALE).astype(np.float32)
    raw = str(z['text']).encode('latin-1').replace(b'\r', b'')
    i = raw.find(b'Frame Time:')
    body = raw[raw.find(b'\n', i) + 1:]
    toks = body.split()
    try:
        vals = np.array(toks, dtype=np.float64)
    except ValueError:                                  # junk such as '-nan(ind)' written by some exporters: show it as 0
        def f(t):
            try:
                v = float(t)
                return v if np.isfinite(v) else 0.0
            except ValueError:
                return 0.0
        vals = np.array([f(t) for t in toks], dtype=np.float64)
    nch = len(z['channel_name'])
    return vals.reshape(-1, nch).astype(np.float32)


def save(path, d: dict):
    """Write the arrays as a regular .npz (np.load reads it), bz2-compressed instead of np.savez_compressed's deflate (about 8% bigger than LZMA, 10x faster to write)."""
    import io
    import os
    import zipfile
    tmp = path + '.tmp'
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_BZIP2) as zf:
        for k, v in d.items():
            b = io.BytesIO()
            np.lib.format.write_array(b, np.asanyarray(v), allow_pickle=False)
            zf.writestr(k + '.npy', b.getvalue())
    os.replace(tmp, path)
