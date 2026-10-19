"""Bake the viewer's examples: data/examples/<id>.yaml -> viewer/examples/ (static files the viewer reads without a server).

    python -m tools.examples.bake [ids ...] [--thumbs] [--force]

viewer/examples/
  manifest.json                     the registry (data/datasets) + every baked example, read by the viewer at start-up
  <dataset>/<example>.json          one clip: skeleton + channel layout, same fields as the local server's /api/clip
  <dataset>/<example>.bin           its motion, float32 little-endian (frames, channels), same as /api/motion
  <dataset>/<example>.smpl.bin      SMPL / SMPL-X clips: shaped template + skin weights + faces, same as /api/mesh
  <dataset>/<example>.props.bin     `scene:` items: per frame a column-major 4x4 per prop (meta.props: mesh GLB, names)
  <dataset>/<example>.p2.json/.bin  further performers of a multi-person take (the first one is <example>.json)
  meshes/<sha12>.glb                rigged meshes (shared by every example of that rig)
  thumbs/<dataset>/<example>.webp   animated card thumbnails (--thumbs, rendered by tools/examples/thumbs.py)

Clips longer than max_seconds are cut to their middle part and resampled to at most MAX_FPS, which keeps a baked
example to a few hundred kB.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import time

import numpy as np

from .. import config, registry
from ..vault import bvhcodec, server as vault
from . import spec

OUT = os.path.join(config.REPO, 'viewer', 'examples')
MAX_FPS = 30.0
INDEX = os.path.join(config.REPO, 'docs', 'assets', 'examples.json')
BLENDER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'blender')
MESH_VERSION = 'fbx2glb-1'     # bump when blender/fbx2glb.py changes what it writes


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', str(s).lower()).strip('-')[:60] or 'clip'


# ---------------------------------------------------------------------------------------------------------------- readers
def read_bvh(path):
    """-> (meta, motion float32 (T, C)) for a BVH file; meta has the fields of the server's /api/clip."""
    with open(path, 'rb') as f:
        raw = f.read()
    i = raw.find(b'Frame Time:')
    head = raw[:raw.find(b'\n', i) + 1].decode('latin-1')
    names, parents, offsets, cj, cn, ft = bvhcodec.parse_header(head)
    vals = np.array(raw[len(head.encode('latin-1')):].split(), dtype=np.float64)
    C = len(cn)
    motion = vals[:len(vals) // C * C].reshape(-1, C).astype(np.float32)
    meta = dict(kind='bvh', joint_names=names.tolist(), parents=parents.tolist(), offsets=offsets.tolist(),
                channel_joint=cj.tolist(), channel_name=cn.tolist(), frame_time=float(ft), frames=len(motion))
    return meta, motion


def relative_positions(meta, motion):
    """Blender-style exports write the FULL local translation (OFFSET included) into every joint's position channels, where
    the BVH convention adds the channels to OFFSET: read as is, every bone would be twice its length. When most non-root
    position channels of the first frame equal their OFFSETs, the channels are made relative to OFFSET (in place)."""
    idx = {n: i for i, n in enumerate(meta['joint_names'])}
    cols = {}
    for k, (c, j) in enumerate(zip(meta['channel_name'], meta['channel_joint'])):
        if c.endswith('position'):
            cols.setdefault(idx[j], [None] * 3)['XYZ'.index(c[0])] = k
    child = [(j, ks) for j, ks in cols.items() if meta['parents'][j] >= 0 and None not in ks]
    if not child or not len(motion):
        return False
    off = meta['offsets']
    # close to OFFSET (within 10 % of the bone; exporters round or re-solve them, e.g. HiPHI to a few cm), not close to 0
    rel = [np.linalg.norm([motion[0, k] - off[j][a] for a, k in enumerate(ks)]) / max(np.linalg.norm(off[j]), 1e-9) for j, ks in child]
    if np.median(rel) >= 0.1:
        return False
    for j, ks in cols.items():
        for a, k in enumerate(ks):
            if k is not None:
                motion[:, k] -= off[j][a]
    return True


def read_vault(cid):
    """-> (meta, motion (T, C), smpl mesh bytes or None, extra catalog fields) for '<vault dir>/<clip id>'."""
    vault.ROOT = config.get('vault')
    p = os.path.join(vault.ROOT, 'processed', cid + '.npz')
    if not os.path.exists(p):
        raise FileNotFoundError(f'vault clip not found: {p}')
    with np.load(p) as z:
        z = {k: z[k] for k in z.files}
    if 'mv_kind' in z and str(z['mv_kind']) == 'joints':
        pos = z['positions']
        meta = dict(kind='joints', joint_names=z['joint_names'].tolist(), parents=z['parents'].tolist(), offsets=[],
                    frame_time=1.0 / float(z['fps']), frames=int(pos.shape[0]))
        text = str(z['text']) if 'text' in z else ''
        cap = next((ln.split('#')[0].strip() for ln in text.splitlines() if ln.strip()), '')
        return meta, np.ascontiguousarray(pos.reshape(len(pos), -1), np.float32), None, dict(desc=cap)
    if vault.is_smpl(z):
        meta = vault.smpl_meta(cid, z)
        return meta, vault.smpl_motion(cid, z).astype(np.float32), vault.smpl_mesh(cid, z), {}
    m = bvhcodec.motion_float(z)
    meta = dict(kind='bvh', joint_names=z['joint_names'].tolist(), parents=z['parents'].tolist(), offsets=z['offsets'].tolist(),
                channel_joint=z['channel_joint'].tolist(), channel_name=z['channel_name'].tolist(),
                frame_time=float(z['frame_time']), frames=int(m.shape[0]))
    return meta, m, None, {}


def lead_rest_frames(meta, motion):
    """frames at the start whose rotations are all zero (a T-pose some converters prepend): skipped"""
    if meta['kind'] != 'bvh' or len(motion) < 3:
        return 0
    rot = [k for k, c in enumerate(meta['channel_name']) if c.endswith('rotation')]
    n = 0
    while n < len(motion) - 2 and not np.abs(motion[n, rot]).max() > 1e-6:
        n += 1
    return n


def read_smpl(path, cid):
    """an AMASS-style SMPL / SMPL-H / SMPL-X npz (poses, trans, betas, gender, mocap frame rate) -> like read_vault"""
    vault.ROOT = config.get('vault')                       # the cut-down body models are cached in <vault>/models/
    with np.load(path, allow_pickle=False) as z:
        z = {k: z[k] for k in z.files if k != 'markers_latent_vids'}   # AMASS SMPL-X: the one pickled (object) field, not needed
    return read_smpl_dict(z, cid, path)


def read_smpl_dict(z, cid, what=''):
    """the same, for an AMASS-layout dict already in memory (converted on the fly)"""
    vault.ROOT = config.get('vault')
    if not vault.is_smpl(z):
        raise ValueError(f'{what or cid}: no poses / trans / betas')
    if 'flat_hand_mean' in z and not bool(z['flat_hand_mean']) and z['poses'].shape[1] == 165:   # hands stored relative to the mean pose
        from ..vault import smplmodel
        z['poses'] = z['poses'].copy(); z['poses'][:, 75:165] += smplmodel.hands_mean()
    return vault.smpl_meta(cid, z), vault.smpl_motion(cid, z).astype(np.float32), vault.smpl_mesh(cid, z)


def window(T, ft, max_seconds):
    """-> (first frame, frame count, stride): the middle max_seconds, at most MAX_FPS"""
    stride = max(1, int(round((1 / ft) / MAX_FPS))) if ft > 0 and 1 / ft > MAX_FPS * 1.25 else 1
    keep = min(T, max(2, int(round(max_seconds / ft))) if ft > 0 else T)
    return (T - keep) // 2, keep, stride


def crop(meta, motion, a, n, stride):
    m = motion[a:a + n:stride]
    meta = dict(meta, frames=int(len(m)), frame_time=float(meta['frame_time']) * stride)
    return meta, np.ascontiguousarray(m, '<f4')


# ---------------------------------------------------------------------------------------------------------------- meshes
def mesh_file(src):
    """GLB/GLTF are copied, FBX is converted with Blender (blender/fbx2glb.py). -> path relative to viewer/examples/"""
    with open(src, 'rb') as f:
        h = hashlib.sha1(f.read() + MESH_VERSION.encode()).hexdigest()[:12]
    rel = f'meshes/{h}.glb'
    dst = os.path.join(OUT, rel)
    if not os.path.exists(dst):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if src.lower().endswith('.glb'):
            shutil.copyfile(src, dst)
        else:
            r = subprocess.run([config.get('blender'), '-b', '--factory-startup', '--python', os.path.join(BLENDER_DIR, 'fbx2glb.py'),
                                '--', src, dst], capture_output=True, text=True, timeout=900)
            if r.returncode != 0 or not os.path.exists(dst):
                raise RuntimeError(f'fbx2glb failed for {src}: {(r.stdout + r.stderr)[-1200:]}')
    return rel


def anim_to_bvh(src, action=None):
    """an FBX / glTF animation exported to BVH by Blender (blender/anim2bvh.py), cached next to the examples"""
    with open(src, 'rb') as f:
        h = hashlib.sha1(f.read() + b'anim2bvh' + (action or '').encode()).hexdigest()[:12]
    dst = os.path.join(config.REPO, 'build', 'anim2bvh', f'{h}.bvh')
    if not os.path.exists(dst):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        r = subprocess.run([config.get('blender'), '-b', '--factory-startup', '--python', os.path.join(BLENDER_DIR, 'anim2bvh.py'),
                            '--', src, dst] + ([action] if action else []), capture_output=True, text=True, timeout=900)
        if r.returncode != 0 or not os.path.exists(dst):
            raise RuntimeError(f'anim2bvh failed for {src}: {(r.stdout + r.stderr)[-1200:]}')
    return dst


def scene_to_clip(src):
    """a character + animated objects file (blender/props2clip.py) -> folder with character.bvh / .glb, props.glb / .npz"""
    with open(src, 'rb') as f:
        h = hashlib.sha1(f.read() + b'props2clip-3').hexdigest()[:12]
    dst = os.path.join(config.REPO, 'build', 'props2clip', h)
    if not os.path.exists(os.path.join(dst, 'props.npz')):
        r = subprocess.run([config.get('blender'), '-b', '--factory-startup', '--python', os.path.join(BLENDER_DIR, 'props2clip.py'),
                            '--', src, dst], capture_output=True, text=True, timeout=900)
        if r.returncode != 0 or not os.path.exists(os.path.join(dst, 'props.npz')):
            raise RuntimeError(f'props2clip failed for {src}: {(r.stdout + r.stderr)[-1200:]}')
    return dst


# ---------------------------------------------------------------------------------------------------------------- one item
def write_part(base, meta, motion, smpl_mesh):
    os.makedirs(os.path.dirname(base), exist_ok=True)
    with open(base + '.json', 'w') as f:
        json.dump(meta, f, separators=(',', ':'))
    with open(base + '.bin', 'wb') as f:
        f.write(motion.tobytes())
    if smpl_mesh is not None:
        with open(base + '.smpl.bin', 'wb') as f:
            f.write(smpl_mesh)


def bake_item(ds_id, item, ex_id, max_seconds, up=None):
    """-> manifest row for one example"""
    extra, credit, mesh, props = {}, item.get('credit'), None, None
    if item.get('source', 'vault') == 'vault':
        clips = item['clip'] if isinstance(item['clip'], list) else [item['clip']]
        parts = []
        for cid in clips:
            meta, motion, smpl, ex = read_vault(cid)
            parts.append((meta, motion, smpl)); extra = extra or ex
        default_label = clips[0].split('/')[-1]
    elif item.get('smpl'):                                       # SMPL-family npz from a named source folder (a list: one take)
        files = item['smpl'] if isinstance(item['smpl'], list) else [item['smpl']]
        parts = [read_smpl(os.path.join(config.source(item['source']), f), f'{ds_id}/{ex_id}/{k}') for k, f in enumerate(files)]
        default_label = os.path.splitext(os.path.basename(files[0]))[0]
    else:
        root = config.source(item['source'])
        if item.get('scene'):                                    # character + animated objects: the objects become props
            d = scene_to_clip(os.path.join(root, item['scene']))
            bvhs = [os.path.join(d, 'character.bvh')]
            with np.load(os.path.join(d, 'props.npz'), allow_pickle=False) as z:
                props = dict(names=[str(n) for n in z['names']], mats=z['mats'], mesh=mesh_file(os.path.join(d, 'props.glb')))
            mesh = mesh_file(os.path.join(d, 'character.glb'))
        elif item.get('anim'):                                   # an animated FBX / GLB: clip from its action, mesh from the file
            src = os.path.join(root, item['anim'])
            bvhs = [anim_to_bvh(src, item.get('action'))]
            item = dict(item, mesh=item.get('mesh') or item['anim'])
        else:
            bvhs = [os.path.join(root, b) for b in (item['bvh'] if isinstance(item['bvh'], list) else [item['bvh']])]
        parts = [read_bvh(b) + (None,) for b in bvhs]
        default_label = os.path.splitext(os.path.basename(bvhs[0]))[0]
    if item.get('mesh'):                                         # any item may name a mesh, from its own or another source folder
        mesh = mesh_file(os.path.join(config.source(item.get('mesh_source') or item['source']), item['mesh']))
    for meta, motion, _ in parts:
        if meta['kind'] == 'bvh':
            relative_positions(meta, motion)
    skip = max(lead_rest_frames(m, mo) for m, mo, _ in parts)
    parts = [(m, mo[skip:], sm) for m, mo, sm in parts]
    T = min(len(mo) for _, mo, _ in parts)
    a, n, stride = window(T, parts[0][0]['frame_time'], max_seconds)
    files = []
    for k, (meta, motion, smpl) in enumerate(parts):
        meta, motion = crop(meta, motion[:T], a, n, stride)
        rel = f'{ds_id}/{ex_id}' + (f'.p{k + 1}' if k else '')
        meta.update(id=rel, mesh=mesh)
        if item.get('bone_map'):                                 # clip joint -> mesh bone, for a mesh with its own skeleton
            meta['bone_map'] = item['bone_map']
        if item.get('up', up):                                   # 'z': a Z-up clip the viewer cannot tell by itself
            meta['up'] = item.get('up', up)
        if props and not k:                                      # props ride on the first performer, cropped like its clip
            pm = props['mats'][skip:][:T][a:a + n:stride]
            os.makedirs(os.path.dirname(os.path.join(OUT, rel)), exist_ok=True)
            with open(os.path.join(OUT, rel + '.props.bin'), 'wb') as f:
                f.write(np.ascontiguousarray(pm.transpose(0, 1, 3, 2), '<f4').tobytes())   # column-major, as THREE.Matrix4
            meta['props'] = dict(mesh=props['mesh'], names=props['names'], frames=int(len(pm)))
        write_part(os.path.join(OUT, rel), meta, motion, smpl)
        files.append(rel)
    m0 = json.load(open(os.path.join(OUT, files[0] + '.json')))
    fps = 1 / m0['frame_time']
    return dict(id=f'{ds_id}/{ex_id}', label=item.get('label') or default_label.replace('_', ' '), kind=m0['kind'], parts=files,
                frames=m0['frames'], fps=round(fps, 2), duration=round(m0['frames'] / fps, 2),
                joints=sum(1 for nme in m0['joint_names'] if not nme.endswith('_End')) * len(files),
                mesh=mesh or ('smpl' if m0['kind'] == 'smpl' else None), credit=credit, desc=extra.get('desc') or item.get('desc', ''),
                source=item.get('clip') or item.get('smpl') or item.get('scene') or item.get('anim') or item.get('bvh'),
                thumb=f'thumbs/{ds_id}/{ex_id}.webp')


# ---------------------------------------------------------------------------------------------------------------- manifest
DS_FIELDS = ('id', 'name', 'full_name', 'good_for', 'year', 'subject', 'content', 'content_note', 'tags', 'capture', 'representation', 'skeleton', 'fps',
             'stats', 'stats_note', 'annotations', 'license', 'access', 'links', 'paper', 'notes', 'derived_from', 'variants', 'review')


def write_manifest(examples):
    tx = registry.taxonomy()
    ds = []
    for d in registry.datasets():
        row = {k: d[k] for k in DS_FIELDS if k in d}
        row['examples'] = examples.get(d['id'], [])
        note = (spec.load(d['id']) or {}).get('note')
        if note:
            row['examples_note'] = note
        ds.append(row)
    start = next((d['examples'][0]['id'] for d in ds if d['examples'] and (spec.load(d['id']) or {}).get('default')), None)  # opening clip
    man = dict(generated=time.strftime('%Y-%m-%d'), start=start, subjects=tx['subjects'], content=tx['content'],
               review_verdicts=tx['review_verdicts'], review_issues=tx['review_issues'], datasets=ds)
    os.makedirs(OUT, exist_ok=True)
    tmp = os.path.join(OUT, 'manifest.json.tmp')                  # written whole, then swapped in: the viewer never sees half
    with open(tmp, 'w') as f:
        json.dump(man, f, separators=(',', ':'), ensure_ascii=False, default=str)      # default=str: yaml dates
    os.replace(tmp, os.path.join(OUT, 'manifest.json'))
    # the example ids per dataset, committed (docs/ is in git, viewer/examples/ is not): the README links to them
    with open(INDEX, 'w') as f:
        json.dump({d['id']: [e['id'] for e in d['examples']] for d in ds if d['examples'] and spec.published(d['id'])}, f, indent=1)
        f.write('\n')
    return man


def existing_examples():
    p = os.path.join(OUT, 'manifest.json')
    if not os.path.exists(p):
        return {}
    try:
        with open(p) as f:
            return {d['id']: d.get('examples', []) for d in json.load(f)['datasets']}
    except ValueError:                                  # unreadable: rebuilt from scratch by a full bake
        return {}


def bake(ids, force=False):
    examples = existing_examples()
    for ds_id in ids:
        s = spec.load(ds_id)
        if not s or not s['items']:
            print(f'{ds_id:28s} no items (run: python -m tools.examples.pick {ds_id})'); continue
        if force and os.path.isdir(os.path.join(OUT, ds_id)):
            shutil.rmtree(os.path.join(OUT, ds_id))
        rows, used = [], set()
        for item in s['items'][:spec.N_EXAMPLES]:
            first = lambda v: v[0] if isinstance(v, list) else v  # noqa: E731
            ex = slug(item.get('label') or str(first(item.get('clip', ''))).split('/')[-1] or os.path.basename(str(first(item.get('bvh') or item.get('smpl') or item.get('scene') or item.get('anim')))))
            while ex in used:
                ex += '-2'
            used.add(ex)
            try:
                rows.append(bake_item(ds_id, item, ex, s.get('max_seconds', spec.MAX_SECONDS), s.get('up')))
            except Exception as e:  # noqa: BLE001 - report and keep going
                print(f'  ! {ds_id}/{ex}: {type(e).__name__}: {str(e)[:300]}')
        examples[ds_id] = rows
        size = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(os.path.join(OUT, ds_id)) for f in fs)
        print(f'{ds_id:28s} {len(rows):2d} examples  {size / 1e6:6.1f} MB', flush=True)
    known = set(registry.by_id())
    examples = {k: v for k, v in examples.items() if k in known}
    return write_manifest(examples)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ids', nargs='*', help='dataset ids (default: every data/examples/*.yaml)')
    ap.add_argument('--force', action='store_true', help='delete and rebuild the examples of these datasets')
    ap.add_argument('--thumbs', action='store_true', help='also render the card thumbnails (headless Chrome)')
    ap.add_argument('--manifest-only', action='store_true', help='only rewrite manifest.json from data/datasets')
    a = ap.parse_args()
    ids = a.ids or spec.all_ids()
    man = write_manifest(existing_examples()) if a.manifest_only else bake(ids, a.force)
    if a.thumbs:
        from . import thumbs
        thumbs.render_all(ids, force=a.force)
    n = sum(len(d['examples']) for d in man['datasets'])
    print(f'manifest: {len(man["datasets"])} datasets, {n} examples -> {os.path.relpath(OUT, config.REPO)}/manifest.json')


if __name__ == '__main__':
    main()
