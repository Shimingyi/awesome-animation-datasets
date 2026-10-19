"""Motion quality red flags: numbers that real, clean human motion almost never shows. A low value does not prove quality;
a high value means a person should look.

    python -m tools.quality [dataset id ...] [--n 100] [--out build/quality.json]

Each dataset is measured on N 10-second windows drawn (fixed seed) from its `quality:` pool in data/examples/<id>.yaml
(the full data; mirrored copies excluded), or from its viewer examples. Clips become 19 canonical joints in metres, Y-up,
30 fps (up axis and unit decided once per dataset; leading rest-pose frames dropped; faster sources low-passed at
13.5 Hz before decimation, slower ones spline-upsampled). The floor is tracked locally (4 s), so slow drift is not
mistaken for flight. Metrics, per window:

  gravity   G1 tilt       floor plane under the planted feet vs the up axis (deg; needs >= 1 m of spread both ways)
            G3 g_est      parabola fits to the COM over real jumps (m/s^2); information only: an unseen box or chair
                          looks like slow flight
  physics   residual      the smallest non-physical acceleration (in g) the motion needs: A1 the ground pulling down,
                          A2 force in free flight (>= 3 frames from any contact), A3 the zero-moment point outside the
                          support polygon, A4 leaving the friction cone (mu = 1)
  floor     drift         how far the ground under the body moves over the whole clip (P95 - P5, cm)
            pair gap      the floor difference between performers of one take (cm)
  contacts  #1 skate      ball-of-foot slide while planted and loaded, contact edges excluded (mm per frame at 30 fps)
            #2 float      share of resting steps that stand > 2 cm above the window's lowest ones (feet hovering)
            #3 penetrate  how far feet go below their local contact height, P99 (cm)
  signal    #4 jitter     share of acceleration energy in 8-12 Hz (of 0-12 Hz; n/a under 25 fps), mean jerk
            #5 pops       single-frame acceleration spikes per minute
  body      #6 range      share of frames with a knee bent backwards (hinge test) or the head bent > 70 deg off the spine
            #7 self-pen   share of frames with forearms deep in the torso or legs in each other (capsules sized by height)
"""
import argparse
import json
import os
import re

import numpy as np

from . import config, registry
from .examples import bake, spec
from .examples.joints2smpl import bvh_positions

G = 9.81
FPS = 30.0
CANON = ['pelvis', 'neck', 'head', 'l_hip', 'l_knee', 'l_ankle', 'l_toe', 'r_hip', 'r_knee', 'r_ankle', 'r_toe',
         'l_shoulder', 'l_elbow', 'l_wrist', 'r_shoulder', 'r_elbow', 'r_wrist', 'spine', 'chest']
SMPL_CANON = dict(pelvis='pelvis', neck='neck', head='head', l_hip='left_hip', l_knee='left_knee', l_ankle='left_ankle',
                  l_toe='left_foot', r_hip='right_hip', r_knee='right_knee', r_ankle='right_ankle', r_toe='right_foot',
                  l_shoulder='left_shoulder', l_elbow='left_elbow', l_wrist='left_wrist', r_shoulder='right_shoulder',
                  r_elbow='right_elbow', r_wrist='right_wrist', spine='spine1', chest='spine3')
# segment masses (fraction of body mass) and COM position along the segment (de Leva 1996)
SEGMENTS = [('pelvis', 'neck', 0.4346, 0.5), ('neck', 'head', 0.0694, 0.5),
            ('l_shoulder', 'l_elbow', 0.0271, 0.577), ('l_elbow', 'l_wrist', 0.0162, 0.457), ('l_wrist', 'l_wrist', 0.0061, 0.0),
            ('r_shoulder', 'r_elbow', 0.0271, 0.577), ('r_elbow', 'r_wrist', 0.0162, 0.457), ('r_wrist', 'r_wrist', 0.0061, 0.0),
            ('l_hip', 'l_knee', 0.1416, 0.41), ('l_knee', 'l_ankle', 0.0433, 0.44), ('l_ankle', 'l_toe', 0.0137, 0.44),
            ('r_hip', 'r_knee', 0.1416, 0.41), ('r_knee', 'r_ankle', 0.0433, 0.44), ('r_ankle', 'r_toe', 0.0137, 0.44)]
# anonymous joint layouts (joint_0 ...), by joint count: KIT-ML 21 (MMM: 11-15 right leg, 16-20 left, 5-7 right arm) and
# the first 22 SMPL joints (HumanML3D)
ORDERED = {21: dict(pelvis=0, spine=1, chest=2, neck=3, head=4, r_shoulder=5, r_elbow=6, r_wrist=7, l_shoulder=8, l_elbow=9, l_wrist=10,
                    r_hip=11, r_knee=12, r_ankle=13, r_toe=14, l_hip=16, l_knee=17, l_ankle=18, l_toe=19),
           22: dict(pelvis=0, l_hip=1, r_hip=2, spine=3, l_knee=4, r_knee=5, l_ankle=7, r_ankle=8, chest=9, l_toe=10, r_toe=11, neck=12,
                    head=15, l_shoulder=16, r_shoulder=17, l_elbow=18, r_elbow=19, l_wrist=20, r_wrist=21)}
FEET = ['l_ankle', 'l_toe', 'r_ankle', 'r_toe']
# how far a joint sits above the floor when that body part lies on it (joints are inside the body): contact margins (m)
MARGIN = dict(pelvis=0.25, spine=0.18, chest=0.18, neck=0.15, head=0.15, l_hip=0.15, r_hip=0.15, l_shoulder=0.12, r_shoulder=0.12,
              l_knee=0.10, r_knee=0.10, l_elbow=0.08, r_elbow=0.08, l_wrist=0.08, r_wrist=0.08)
I = {c: k for k, c in enumerate(CANON)}
UPS = {'+y': (0, 1, 0), '-y': (0, -1, 0), '+z': (0, 0, 1), '-z': (0, 0, -1), '+x': (1, 0, 0), '-x': (-1, 0, 0)}


# ---------------------------------------------------------------------------------------------------------------- loading
def _aa_to_mat(aa):
    a = np.linalg.norm(aa, axis=-1, keepdims=True); k = aa / np.maximum(a, 1e-12)
    K = np.zeros(aa.shape[:-1] + (3, 3))
    K[..., 0, 1], K[..., 0, 2], K[..., 1, 0], K[..., 1, 2], K[..., 2, 0], K[..., 2, 1] = -k[..., 2], k[..., 1], k[..., 2], -k[..., 0], -k[..., 1], k[..., 0]
    s, c = np.sin(a)[..., None], np.cos(a)[..., None]
    return np.eye(3) + s * K + (1 - c) * K @ K


def smpl_positions(meta, motion):
    """world joints of a body-model clip (motion = [trans, axis-angle per joint], see tools/vault/server.py)"""
    T, par, off = len(motion), meta['parents'], np.asarray(meta['offsets'], float)
    R = _aa_to_mat(motion[:, 3:].reshape(T, -1, 3).astype(np.float64))
    W, P = [None] * len(par), np.zeros((T, len(par), 3))
    for j, p in enumerate(par):
        if p < 0:
            W[j], P[:, j] = R[:, j], off[j] + motion[:, :3]
        else:
            W[j] = W[p] @ R[:, j]; P[:, j] = P[:, p] + np.einsum('tij,j->ti', W[p], off[j])
    return P


def parts_of(ds_id, item):
    """-> [(meta, motion)] one per performer, full length, as bake_item reads them"""
    if item.get('source', 'vault') == 'vault':
        clips = item['clip'] if isinstance(item['clip'], list) else [item['clip']]
        return [bake.read_vault(c)[:2] for c in clips]
    if item.get('smpl'):
        files = item['smpl'] if isinstance(item['smpl'], list) else [item['smpl']]
        return [bake.read_smpl(os.path.join(config.source(item['source']), f), f'{ds_id}/q/{k}')[:2] for k, f in enumerate(files)]
    root = config.source(item['source'])
    if item.get('scene'):
        bvhs = [os.path.join(bake.scene_to_clip(os.path.join(root, item['scene'])), 'character.bvh')]
    elif item.get('anim'):
        bvhs = [bake.anim_to_bvh(os.path.join(root, item['anim']), item.get('action'))]
    else:
        bvhs = [os.path.join(root, b) for b in (item['bvh'] if isinstance(item['bvh'], list) else [item['bvh']])]
    return [bake.read_bvh(b) for b in bvhs]


def positions(meta, motion):
    if meta['kind'] == 'smpl':
        return smpl_positions(meta, motion.astype(np.float64))
    if meta['kind'] == 'joints':
        return motion.reshape(len(motion), -1, 3).astype(np.float64)
    m = motion.astype(np.float64).copy(); bake.relative_positions(meta, m)
    return bvh_positions(meta, m)


def canon_map(meta):
    """canonical joint -> index in the clip, from SMPL names or name heuristics (None where not found)"""
    names = meta['joint_names']
    if all(re.fullmatch(r'joint_\d+', n) for n in names) and len(names) in ORDERED:
        return {c: ORDERED[len(names)].get(c) for c in CANON}
    if meta['kind'] == 'smpl' or 'left_hip' in names:
        return {c: names.index(n) if n in names else None for c, n in SMPL_CANON.items()}
    def split(raw):
        """-> (side 'l' / 'r' / None, core name without side, prefixes, numbering)"""
        n = re.sub(r'^(bip0?1[_ ]?|b_|j_|jnt_|def[-_])', '', re.sub(r'^.*:', '', raw.lower()))
        n = re.sub(r'(_bind_jnt|_jnt)$', '', n)
        m = re.match(r'^(left|right)(.*)$', n) or re.match(r'^(.*?)(left|right)$', n)
        if m:
            sd = 'l' if 'left' in m.group(0)[:5] or n.endswith('left') else 'r'
            core = n.replace('left', '').replace('right', '')
        else:
            m = (re.match(r'^([lr])[_ .]+(.*)$', n) or re.match(r'^(.*?)[_ .]+([lr])$', n)
                 or re.match(r'^([lr])(femur|tibia|fibula|foot|toes?|humerus|radius|ulna|hand|wrist|shoulder|clavicle|collar|thigh|shin|hip|knee|ankle|elbow|upleg|leg|arm|forearm)$', n))
            if m:
                sd = m.group(1) if len(m.group(1)) == 1 else m.group(2); core = m.group(2) if len(m.group(1)) == 1 else m.group(1)
            else:
                sd, core = None, n
        return sd, re.sub(r'[_ .]', '', re.sub(r'\d+$', '', core))
    fingers = re.compile(r'thumb|index|middle|ring|pinky|little|finger|carpal')
    cand = {c: [] for c in CANON}; clav = {'l': [], 'r': []}
    for j, raw in enumerate(names):
        if re.search(r'end$|_end|nub|site', raw.lower()):
            continue
        s, core = split(raw)
        if fingers.search(core) or 'twist' in core or 'roll' in core or 'eye' in core or 'jaw' in core:
            continue
        if s:
            if re.search(r'toe|ball', core): cand[s + '_toe'].append(j)
            elif re.search(r'foot|ankle', core): cand[s + '_ankle'].append(j)
            elif re.search(r'upleg|thigh|upperleg|legupper|hip|femur', core): cand[s + '_hip'].append(j)
            elif re.search(r'^leg$|knee|shin|calf|lowleg|lowerleg|leglower|tibia', core): cand[s + '_knee'].append(j)
            elif re.search(r'forearm|elbow|lowarm|lowerarm|armlower|radius', core): cand[s + '_elbow'].append(j)
            elif re.search(r'hand|wrist', core): cand[s + '_wrist'].append(j)
            elif re.search(r'^arm$|uparm|upperarm|armupper|humerus', core): cand[s + '_shoulder'].append(j)
            elif re.search(r'shoulder|collar|clavicle', core): clav[s].append(j)
        else:
            if re.search(r'^(hips?|pelvis)$', core) or core in ('cpelvis',): cand['pelvis'].append(j)
            elif 'head' in core and 'top' not in core: cand['head'].append(j)
            elif 'neck' in core: cand['neck'].append(j)
            elif re.search(r'chest|spine[23]|upperback', core): cand['chest'].append(j)
            elif re.search(r'spine|abdomen|back|torso|waist', core): cand['spine'].append(j)
    par = meta['parents']
    depth = lambda j: 0 if par[j] < 0 else 1 + depth(par[j])
    for sd in 'lr':
        if not cand[sd + '_shoulder'] and clav[sd]:                         # collar -> shoulder rigs: the shoulder is the upper arm
            cand[sd + '_shoulder'] = [max(clav[sd], key=depth)]
        if not cand[sd + '_hip'] and len(cand[sd + '_knee']) > 1:           # Leg = thigh, Shin = knee (BONES-SEED)
            ks = sorted(cand[sd + '_knee'], key=depth); cand[sd + '_hip'], cand[sd + '_knee'] = ks[:1], ks[1:]
        if not cand[sd + '_toe'] and len(cand[sd + '_ankle']) > 1:          # foot0001 / foot0002: the deeper one is the toe
            cand[sd + '_toe'] = [max(cand[sd + '_ankle'], key=depth)]
    out = {c: (min(js, key=depth) if js else None) for c, js in cand.items()}   # the first of a chain (before twist bones)
    if cand['neck']:                                    # Neck / Neck1 (CMU family): the upper one is the neck, the lower is mid-chest
        out['neck'] = max(cand['neck'], key=depth)
    if out.get('chest') is None and len(cand['spine']) > 1:
        out['chest'] = max(cand['spine'], key=depth)
    if out['pelvis'] is None:
        out['pelvis'] = 0
    if out['chest'] is None:
        out['chest'] = out['spine']
    if out['spine'] is None:
        out['spine'] = out['chest']
    return out


def up_rotation(up):
    """rotation taking the data's up axis to +Y"""
    v = np.asarray(UPS[up], float); y = np.array([0, 1.0, 0])
    if np.allclose(v, y): return np.eye(3)
    if np.allclose(v, -y): return np.diag([1.0, -1, -1])
    a = np.cross(v, y); s, c = np.linalg.norm(a), v @ y; a = a / s
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + s * K + (1 - c) * K @ K


def lead_teleports(P):
    """leading frames that jump into place (some releases start with a rest pose at the origin): how many to drop"""
    step = np.linalg.norm(np.diff(P, axis=0), axis=-1).max(1)
    if len(step) < 10:
        return 0
    lim, n = 4 * np.percentile(step, 99.5), 0
    while n < min(5, len(step)) and step[n] > lim:
        n += 1
    return n


def detect_up(P, cm):
    """the axis pelvis -> head points along most of the time (decide per dataset: lying clips fool it)"""
    v = np.median(P[:, cm['head']] - P[:, cm['pelvis']], 0); a = int(np.argmax(np.abs(v)))
    return ('+' if v[a] > 0 else '-') + 'xyz'[a]


UNITS = (1.0, 0.01, 0.0254, 0.001)


def clip_unit(Q):
    """the unit that makes the head joint stand 0.9-1.95 m above the feet (90th percentile over the clip), else the
    scale to a 1.55 m head height. A sitting / crouching clip can fool it: decide per dataset (dataset_unit)."""
    stature = np.percentile(Q[:, I['head'], 1] - Q[:, [I['l_ankle'], I['r_ankle'], I['l_toe'], I['r_toe']], 1].min(1), 90)
    return next((u for u in UNITS if 0.9 <= stature * u <= 1.95), 1.55 / max(stature, 1e-9))


def dataset_unit(loaded, up):
    """the most common standard unit over the clips (when most agree), else the median scale"""
    us = []
    for _, _, _, parts in loaded[:30]:
        meta, P, cm = parts[0]
        Q, _ = to_canon(P, cm, meta['frame_time'], up, unit=1.0)
        if Q is not None:
            us.append(clip_unit(Q))
    if not us:
        return None
    std = [u for u in us if u in UNITS]
    if len(std) >= 0.5 * len(us):
        return max(set(std), key=std.count)
    return float(np.median(us))


def to_canon(P, cm, ft, up=None, unit=None):
    """(T, J, 3) clip joints -> (T, 19, 3) canonical joints in metres, Y-up, 30 fps, and info; (None, reason) if unusable.
    up / unit: the dataset's (spec or majority); unit=None picks the unit that makes the head joint stand 0.9-1.95 m
    above the feet (children included), else scales the body to a 1.55 m head height (rigs in odd units, e.g. SnapMoGen).
    Faster sources are low-passed at 13.5 Hz before decimation (no aliasing); sources under 25 fps are spline-upsampled
    and flagged lowfps (they carry nothing above their Nyquist, so jitter is not measured)."""
    need = ['pelvis', 'head', 'l_hip', 'l_knee', 'l_ankle', 'r_hip', 'r_knee', 'r_ankle', 'l_shoulder', 'l_elbow', 'l_wrist',
            'r_shoulder', 'r_elbow', 'r_wrist']
    if any(cm.get(c) is None for c in need):
        return None, f'missing {[c for c in need if cm.get(c) is None]}'
    P = P[lead_teleports(P):]
    idx = {c: cm[c] for c in CANON if cm.get(c) is not None}
    Q = np.stack([P[:, idx[c]] if c in idx else np.full((len(P), 3), np.nan) for c in CANON], 1)
    no_toe = False
    for s in 'lr':                                       # no toe joint: the ankle stands in (foot sliding is then not measured)
        k = CANON.index(s + '_toe')
        if np.isnan(Q[0, k, 0]):
            Q[:, k] = Q[:, CANON.index(s + '_ankle')]; no_toe = True
    if np.isnan(Q[0, CANON.index('neck'), 0]):
        Q[:, CANON.index('neck')] = 0.5 * (Q[:, CANON.index('l_shoulder')] + Q[:, CANON.index('r_shoulder')])
    for c in ('spine', 'chest'):
        if np.isnan(Q[0, CANON.index(c), 0]):
            Q[:, CANON.index(c)] = 0.5 * (Q[:, CANON.index('pelvis')] + Q[:, CANON.index('neck')])
    up = up or detect_up(P, cm)
    Q = Q @ up_rotation(up).T
    unit = unit or clip_unit(Q)
    Q = Q * unit
    src = 1 / ft; T = len(Q); lowfps = src < 25
    if abs(src - FPS) > 0.5 and T > 3:
        t0 = np.arange(T) * ft; t1 = np.arange(0, t0[-1] + 1e-9, 1 / FPS)
        if src > FPS:
            from scipy.signal import butter, sosfiltfilt
            Q = sosfiltfilt(butter(4, 13.5, fs=src, output='sos'), Q, axis=0) if T > 30 else Q
            Q = np.stack([np.stack([np.interp(t1, t0, Q[:, j, a]) for a in range(3)], -1) for j in range(Q.shape[1])], 1)
        else:
            from scipy.interpolate import CubicSpline
            Q = CubicSpline(t0, Q, axis=0)(t1)
    return Q, dict(up=up, unit=round(float(unit), 5), fps=round(float(src), 2), lowfps=lowfps, no_toe=no_toe)


# ---------------------------------------------------------------------------------------------------------------- body


def com(Q):
    pts = np.stack([Q[:, I[a]] + f * (Q[:, I[b]] - Q[:, I[a]]) for a, b, m, f in SEGMENTS], 1)
    w = np.array([m for _, _, m, _ in SEGMENTS]); w = w / w.sum()
    return (pts * w[None, :, None]).sum(1), pts, w


def sg(x, deriv=0, k=7):
    """Savitzky-Golay (quadratic, k frames) at 30 fps: smoothed values or derivatives; the edges are fitted, not padded"""
    from scipy.signal import savgol_filter
    if len(x) < k:
        return np.gradient(x, 1 / FPS, axis=0) if deriv == 1 else np.zeros_like(x) if deriv else x
    return savgol_filter(x, k, 2, deriv=deriv, delta=1 / FPS, axis=0, mode='interp')


def rolling_pct(v, q, w):
    """the q-th percentile of v over a centred window of w frames"""
    if len(v) <= w:
        return np.full(len(v), np.percentile(v, q))
    h = w // 2; vp = np.concatenate([np.full(h, np.nan), v, np.full(w - h - 1, np.nan)])
    return np.nanpercentile(np.lib.stride_tricks.sliding_window_view(vp, w), q, axis=1)


def hull(pts):
    pts = sorted(set(map(tuple, np.round(pts, 4))))
    if len(pts) < 3: return np.array(pts)
    def cross(o, a, b): return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, hi = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0: lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(hi) >= 2 and cross(hi[-2], hi[-1], p) <= 0: hi.pop()
        hi.append(p)
    return np.array(lo[:-1] + hi[:-1])


def outside(p, H):
    """distance of point p outside the convex polygon H (0 inside)"""
    if len(H) == 0: return np.inf
    if len(H) == 1: return float(np.linalg.norm(p - H[0]))
    def seg(p, a, b):
        ab = b - a; t = np.clip((p - a) @ ab / max(ab @ ab, 1e-12), 0, 1); return np.linalg.norm(p - (a + t * ab))
    if len(H) == 2: return float(seg(p, H[0], H[1]))
    inside = all(((H[(k + 1) % len(H)] - H[k])[0] * (p - H[k])[1] - (H[(k + 1) % len(H)] - H[k])[1] * (p - H[k])[0]) >= 0 for k in range(len(H)))
    return 0.0 if inside else float(min(seg(p, H[k], H[(k + 1) % len(H)]) for k in range(len(H))))


def capsule_depth(a0, a1, b0, b1, ra, rb):
    """penetration depth of two capsules per frame (positive = overlapping), closest points of two segments"""
    d1, d2, r = a1 - a0, b1 - b0, a0 - b0
    A, E, F = (d1 * d1).sum(-1), (d2 * d2).sum(-1), (d2 * r).sum(-1)
    C, B = (d1 * r).sum(-1), (d1 * d2).sum(-1)
    den = np.maximum(A * E - B * B, 1e-12)
    s = np.clip((B * F - C * E) / den, 0, 1); t = np.clip((B * s + F) / np.maximum(E, 1e-12), 0, 1)
    s = np.clip((B * t - C) / np.maximum(A, 1e-12), 0, 1)
    d = np.linalg.norm(a0 + d1 * s[:, None] - (b0 + d2 * t[:, None]), axis=-1)
    return ra + rb - d


# ---------------------------------------------------------------------------------------------------------------- metrics
def floor_track(Q):
    """the ground under the body over time (4 s rolling, from the lowest foot joint; toe joints sit ~3 cm up)"""
    return rolling_pct(np.min(Q[:, [I[c] for c in FEET], 1], 1), 3, 120) - 0.03


def metrics(Q, lowfps=False, no_toe=False):
    T = len(Q); y = Q[..., 1]; feet = [I[c] for c in FEET]
    # floor, locally (4 s): each foot joint's resting height, and the ground under the body
    base = {j: rolling_pct(y[:, j], 3, 120) for j in feet}
    floor = floor_track(Q)
    fc = np.stack([y[:, j] < base[j] + 0.05 for j in feet], 1)                 # foot contacts
    mj = [I[c] for c in MARGIN]; mm = np.array(list(MARGIN.values()))
    body_c = y[:, mj] < floor[:, None] + mm                                    # body parts lying / kneeling / sitting on the floor
    contact = fc.any(1) | body_c.any(1)
    near = np.convolve(contact.astype(float), np.ones(7), 'same') > 0          # within 3 frames of a contact
    core_air = ~near                                                          # airborne, clear of take-off / landing
    edge = np.zeros(T, bool); edge[:3] = edge[-3:] = True
    out = dict(frames=T, seconds=round(T / FPS, 1))

    # G1: tilt of the plane under the planted feet (needs >= 1 m of spread along both principal axes)
    speed = np.linalg.norm(sg(Q, 1)[..., [0, 2]], axis=-1)
    sel = fc & (speed[:, feet] < 0.2)
    pts = np.concatenate([np.c_[Q[sel[:, k], j][:, [0, 2]], y[sel[:, k], j] - base[j][sel[:, k]]] for k, j in enumerate(feet)]) if sel.any() else np.zeros((0, 3))
    if len(pts) > 20:
        xy = pts[:, :2] - pts[:, :2].mean(0); ev, evec = np.linalg.eigh(xy.T @ xy / len(xy))
        span = np.ptp(xy @ evec, 0)
        if span.min() >= 1.0:
            A = np.c_[pts[:, :2], np.ones(len(pts))]; coef = np.linalg.lstsq(A, pts[:, 2], rcond=None)[0]
            out['G1_tilt_deg'] = round(float(np.degrees(np.arctan(np.linalg.norm(coef[:2])))), 2)

    # body: COM and its angular momentum (per kg of body mass)
    c, segp, w = com(Q)
    cs, a = sg(c), sg(c, 2)
    rel = segp - c[:, None]; vrel = sg(segp, 1) - sg(c, 1)[:, None]
    L = (w[None, :, None] * np.cross(rel, vrel)).sum(1); dL = sg(L, 1)

    # G3: gravity from parabolas fitted to the COM over real jumps (0.17-0.8 s, rising then falling, >= 2 cm of height)
    gs, gw, ang = [], [], []
    k = 0
    while k < T:
        if core_air[k] and not edge[k]:
            e = k
            while e < T and core_air[e] and not edge[e]: e += 1
            if 5 <= e - k <= 24:
                t = np.arange(e - k) / FPS; cy = c[k:e, 1]
                fy = np.polyfit(t, cy, 2); apex = -fy[1] / (2 * fy[0]) if fy[0] else -1
                v0, v1 = fy[1], 2 * fy[0] * t[-1] + fy[1]   # a jump leaves upwards and lands downwards
                if fy[0] < 0 and 0 < apex < t[-1] and np.ptp(cy) >= 0.02 and v0 > 0.25 and v1 < -0.25:
                    ah = [2 * np.polyfit(t, c[k:e, d], 2)[0] for d in (0, 2)]
                    gs.append(-2 * fy[0]); gw.append(e - k); ang.append(np.degrees(np.arctan2(np.hypot(*ah), -2 * fy[0])))
            k = e
        else:
            k += 1
    if gs:
        out['G3_g_est'] = round(float(np.average(gs, weights=gw)), 2); out['G3_g_angle_deg'] = round(float(np.average(ang, weights=gw)), 1)

    # physics residual (A1-A4), in g; flight frames only when clear of contacts, never the 3 edge frames
    fy = a[:, 1] + G
    res = np.full(T, np.nan)
    for t in range(T):
        if edge[t] or (not contact[t] and not core_air[t]):
            continue
        if core_air[t]:
            res[t] = np.linalg.norm(a[t] - [0, -G, 0]); continue
        r_v = max(0.0, -fy[t]); r_h = max(0.0, np.hypot(a[t, 0], a[t, 2]) - 1.0 * max(fy[t], 0))
        r_z = 0.0
        if fy[t] > 1.0:
            dy = floor[t] - cs[t, 1]
            p = np.array([cs[t, 0] + (dL[t, 2] + dy * a[t, 0]) / fy[t], cs[t, 2] + (dy * a[t, 2] - dL[t, 0]) / fy[t]])
            sup = [Q[t, j][[0, 2]] for k2, j in enumerate(feet) if fc[t, k2]] + [Q[t, j][[0, 2]] for k2, j in enumerate(mj) if body_c[t, k2]]
            d_out = max(0.0, outside(p, hull(np.array(sup))) - 0.08) if sup else 0.0
            r_z = d_out * fy[t] / max(cs[t, 1] - floor[t], 0.3)
        res[t] = np.sqrt(r_v ** 2 + r_h ** 2 + r_z ** 2)
    res = res / G; scored = ~np.isnan(res)
    out['phys_residual_g'] = round(float(np.nanmean(res)), 3) if scored.any() else None
    out['phys_bad_frac'] = round(float(np.nanmean(res > 0.25)), 3) if scored.any() else None
    out['A1_pull_frac'] = round(float(np.mean(contact & ~edge & (fy < -0.2 * G))), 3)

    # #1 skating: the ball of the foot (toe joint) slides while the foot is planted and loaded: toe within 2.5 cm of its
    # resting height (weight 2 - 2^(h/H)), nearly still vertically, the ankle down too (< 3 cm; in walking the swinging toe
    # passes only 1-2 cm above the floor), weighted by the foot's share of the body's load (the foot nearer the centre of
    # mass carries more; a shuffling, unloaded foot barely counts). Not measured without a toe.
    if not no_toe:
        sk, wt = 0.0, 0.0
        vy = sg(y, 1)
        dist = {sd: np.linalg.norm((Q[:, I[sd + '_toe']] + Q[:, I[sd + '_ankle']])[:, [0, 2]] / 2 - c[:, [0, 2]], axis=1) for sd in 'lr'}
        for sd in 'lr':
            j, ja = I[sd + '_toe'], I[sd + '_ankle']
            load = dist['r' if sd == 'l' else 'l'] / (dist['l'] + dist['r'] + 1e-9)
            planted = (y[:, j] - base[j] < 0.025) & (y[:, ja] - base[ja] < 0.03)
            inner = planted.copy()                      # not the 2 frames at each end of a contact: touchdown and lift-off
            for k2 in (1, 2):                           # (a running foot is still arriving at speed when it is that low)
                inner[k2:] &= planted[:-k2]; inner[:-k2] &= planted[k2:]
            wgt = (np.clip(2 - 2 ** (np.maximum(y[:, j] - base[j], 0) / 0.025), 0, 1) * (np.abs(vy[:, j]) < 0.1) * inner
                   * np.clip(2 * load - 0.5, 0, 1))
            sk += (speed[:, j] * wgt).sum(); wt += wgt.sum()
        out['skate_mm'] = round(float(sk / max(wt, 1e-9) * 1000 / FPS), 2)
    # #2 float: feet resting above the floor. In clean capture every resting foot stands at the floor; a step that rests
    # > 2 cm above the window's lowest resting steps (10th percentile) floats. Resting = toe still (vertical < 5 cm/s,
    # horizontal < 15 cm/s) for >= 5 frames; share of such steps, measured per window.
    rest = []
    for sd in 'lr':
        j = I[sd + '_toe']
        still = (np.abs(sg(y[:, j], 1)) < 0.05) & (speed[:, j] < 0.15)
        k = 0
        while k < T:
            if still[k]:
                e = k
                while e < T and still[e]: e += 1
                if e - k >= 5: rest.append(np.median(y[k:e, j]))
                k = e
            else:
                k += 1
    if len(rest) >= 3:
        rest = np.array(rest); out['float_frac'] = round(float(np.mean(rest > np.percentile(rest, 10) + 0.02)), 3)
    pen = np.max(np.stack([base[j] - y[:, j] for j in feet], 1), 1)
    out['penetrate_cm'] = round(float(max(0.0, np.percentile(pen, 99)) * 100), 2)

    # #4 jitter: share of acceleration energy above 10 Hz (true second difference; n/a for sources under 25 fps), jerk
    A = (Q[2:] - 2 * Q[1:-1] + Q[:-2]) * FPS ** 2
    out['jitter'] = round(float(np.linalg.norm(np.diff(A, axis=0) * FPS, axis=-1).mean()), 1)
    if not lowfps and len(A) > 30:                        # 8-12 Hz of 0-12 Hz: below the anti-alias filter, so fast and 30 fps sources compare
        f = np.fft.rfftfreq(len(A), 1 / FPS); S = (np.abs(np.fft.rfft(A - A.mean(0), axis=0)) ** 2).sum((1, 2))
        out['hf_ratio'] = round(float(S[(f > 8) & (f <= 12)].sum() / max(S[f <= 12].sum(), 1e-12)), 4)
    # #5 pops: a frame whose peak acceleration is > 100 m/s^2 and 6x the median of its +-3 neighbours (itself excluded)
    am = np.linalg.norm(A, axis=-1).max(1)
    if len(am) > 7:
        win = np.lib.stride_tricks.sliding_window_view(am, 7)
        nb = np.maximum(np.median(np.delete(win, 3, axis=1), 1), 1.0)
        out['pops_per_min'] = round(float(((win[:, 3] > 100) & (win[:, 3] > 6 * nb)).sum() / max(T / FPS / 60, 1e-9)), 2)

    # #6 range of motion: a knee bent backwards (hinge test: the knee's bending axis against the pelvis' left-right axis,
    # any body orientation; > 10 deg, only where the bend plane is well defined) and the head bent > 70 deg off the spine
    bad = np.zeros(T, bool)
    lat = Q[:, I['r_hip']] - Q[:, I['l_hip']]; lat /= np.maximum(np.linalg.norm(lat, axis=-1, keepdims=True), 1e-9)
    for sd in 'lr':
        th, sh = Q[:, I[sd + '_knee']] - Q[:, I[sd + '_hip']], Q[:, I[sd + '_ankle']] - Q[:, I[sd + '_knee']]
        n = np.cross(th, sh); nn = np.linalg.norm(n, axis=-1)
        ang = np.degrees(np.arcsin(np.clip(nn / np.maximum(np.linalg.norm(th, axis=-1) * np.linalg.norm(sh, axis=-1), 1e-9), 0, 1)))
        cos = (n * lat).sum(-1) / np.maximum(nn, 1e-9)       # normal flexion: the bend axis points to the body's left (< 0)
        bad |= (cos > 0.5) & (ang > 10)
    sp = Q[:, I['neck']] - Q[:, I['pelvis']]; hd = Q[:, I['head']] - Q[:, I['neck']]
    hang = np.degrees(np.arccos(np.clip((sp * hd).sum(-1) / np.maximum(np.linalg.norm(sp, axis=-1) * np.linalg.norm(hd, axis=-1), 1e-9), -1, 1)))
    bad |= hang > 70
    out['rom_bad_frac'] = round(float(bad.mean()), 3)

    # #7 self-penetration: capsules sized by standing height (head joint ~1.55 m), the torso in two parts; deep = axes
    # closer than half their radii sum
    h = float(np.percentile(y[:, I['head']] - floor, 90)) / 1.55
    caps = dict(lowt=('pelvis', 'chest', 0.12), upt=('chest', 'neck', 0.12), lfa=('l_elbow', 'l_wrist', 0.04), rfa=('r_elbow', 'r_wrist', 0.04),
                lth=('l_hip', 'l_knee', 0.075), lsh=('l_knee', 'l_ankle', 0.055), rth=('r_hip', 'r_knee', 0.075), rsh=('r_knee', 'r_ankle', 0.055))
    pairs = [('lfa', 'lowt'), ('lfa', 'upt'), ('rfa', 'lowt'), ('rfa', 'upt'), ('lth', 'rth'), ('lsh', 'rsh'), ('lth', 'rsh'), ('lsh', 'rth'), ('lfa', 'rfa')]
    deep = np.zeros(T, bool)
    for p1, p2 in pairs:
        (a0, a1, ra), (b0, b1, rb) = caps[p1], caps[p2]
        deep |= capsule_depth(Q[:, I[a0]], Q[:, I[a1]], Q[:, I[b0]], Q[:, I[b1]], ra * h, rb * h) > 0.5 * (ra + rb) * h
    out['selfpen_frac'] = round(float(deep.mean()), 3)
    out['floor_median'] = float(np.median(floor))                  # for the gap between performers of one take
    return out


# ---------------------------------------------------------------------------------------------------------------- run
# red-flag thresholds per window. Calibrated with LAFAN1 as the reference (visually the cleanest set: no metric may flag
# it), against the sets judged poor by eye (AIST++, Motion-X, MotionMillion, AnimationGPT); slide set by the maintainer
FLAGS = dict(phys_residual_g=0.05, float_frac=0.4, skate_mm=10.0, hf_ratio=0.12, floor_drift_cm=6.0, pair_floor_gap_cm=5.0,
             G1_tilt_deg=1.3, rom_bad_frac=0.03, selfpen_frac=0.01)


SHARE = 0.25          # a dataset is flagged on a metric when more than this share of its windows is over the threshold


def shares(rows):
    """per metric: the share of measured windows over its threshold"""
    out = {}
    for k, th in FLAGS.items():
        v = [r[k] for r in rows if r.get(k) is not None]
        if v:
            out[k] = round(float(np.mean(np.array(v) > th)), 3)
    return out


def flags(share):
    return [k for k, v in share.items() if v > SHARE]


KEYS = ['G1_tilt_deg', 'G3_g_est', 'G3_g_angle_deg', 'phys_residual_g', 'phys_bad_frac', 'A1_pull_frac', 'float_frac',
        'floor_drift_cm', 'pair_floor_gap_cm', 'skate_mm', 'penetrate_cm', 'jitter', 'hf_ratio', 'pops_per_min', 'rom_bad_frac',
        'selfpen_frac']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ids', nargs='*'); ap.add_argument('--out', default=os.path.join(config.REPO, 'build', 'quality.json'))
    ap.add_argument('--n', type=int, default=N_WINDOWS, help='windows per dataset')
    a = ap.parse_args()
    ids = a.ids or [d['id'] for d in registry.datasets() if d['subject'] == 'human-body' and spec.load(d['id'])]
    res = json.load(open(a.out)) if os.path.exists(a.out) else {}
    for i in ids:
        res[i] = sample(i, a.n)
        ok = [r for r in res[i] if 'error' not in r]
        print(f'{i:28s} n={len(ok):3d} flags: ' + ', '.join(flags(shares(ok))), flush=True)
        for r in res[i]:
            if 'error' in r:
                print(f'    ! {r["item"]}: {r["error"]}')
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(res, open(a.out, 'w'), indent=1, default=float)
    json.dump(summary(res), open(SUMMARY, 'w'), indent=1)          # tracked: the README's quality table is built from it


SUMMARY = os.path.join(config.REPO, 'docs', 'assets', 'quality.json')


def summary(res):
    """per dataset: clips measured, the median clip's value of each metric, and the red flags it raises"""
    import time
    out = dict(generated=time.strftime('%Y-%m-%d'), fps=FPS, windows=N_WINDOWS, thresholds=FLAGS, share=SHARE, datasets={})
    for d, rows in sorted(res.items()):
        ok = [r for r in rows if 'error' not in r]
        if not ok:
            continue
        med = {k: float(np.nanmedian(v)) for k in KEYS if (v := [r[k] for r in ok if r.get(k) is not None])}
        sh = shares(ok)
        out['datasets'][d] = dict(clips=len(ok), median={k: round(v, 4) for k, v in med.items()}, share=sh, flags=flags(sh))
    return out



# ---------------------------------------------------------------------------------------------------------------- pools
# Where a dataset's measured clips come from: `quality:` in data/examples/<id>.yaml, else its viewer examples.
#   quality:
#     up: auto                                                  # optional: the pool's own up axis / unit (auto: majority)
#     from:
#       - {reader: vault, glob: 'SnapMoGen/renamed_bvhs/*', exclude: ['/m_']}     # vault clip ids (fnmatch)
#       - {reader: interx, source: interx_raw, glob: 'motions/*'}                 # files / folders of a config source
# Readers turn one pool entry into its performers' (meta, motion). Mirrored copies are never measured.
N_WINDOWS, WINDOW_S = 100, 10.0
MIRROR = re.compile(r'mirror|/m_|_m$|(^|/)M\d|_mirrored', re.I)
_cache = {}


def _smpl(z, cid):
    return bake.read_smpl_dict(z, cid)[:2]


def _omomo(path):
    """all sequences of an OMOMO pickle, loaded once (arrays only, tools/examples/safepickle.py)"""
    if path not in _cache:
        from .examples.safepickle import load
        _cache[path] = {s['seq_name']: s for s in load(path).values()}
    return _cache[path]


def _read(reader, ref):
    import glob as G
    from .examples import aistpp, dd100, embody3d, finedance, interx
    if reader == 'vault':
        return [bake.read_vault(ref)[:2]]
    if reader == 'bvh':
        return [bake.read_bvh(ref)]
    if reader == 'smpl':
        return [bake.read_smpl(ref, 'q/' + os.path.basename(ref))[:2]]
    if reader == 'interx':
        return [_smpl(interx.person(os.path.join(ref, p + '.npz')), f'q/{p}') for p in ('P1', 'P2')]
    if reader == 'embody3d':
        return [_smpl(embody3d.person(d), 'q/' + os.path.basename(d.rstrip('/'))) for d in sorted(G.glob(os.path.join(ref, '*/')))]
    if reader == 'aistpp':
        return [_smpl(aistpp.convert(ref), 'q/aist')]
    if reader == 'finedance':
        root, cid = os.path.dirname(os.path.dirname(ref)), os.path.basename(ref)[:-4]
        return [_smpl(finedance.clip(root, cid), 'q/fd')]
    if reader == 'dd100':
        return [_smpl(dd100.dancer(ref), 'q/dd' + ref[-6:-4])]
    if reader == 'omomo':
        pk, seq = ref.split('::')
        from .examples import omomo
        return [_smpl(omomo.sequence(_omomo(pk)[seq]), 'q/omomo')]
    if reader == 'rpr272':
        from .vault import adapters
        return [_smpl(adapters.convert_rpr272(ref, 'q')[0], 'q/rpr')]
    if reader == 'joints22':                             # (T, >= 66): the 22 SMPL joint positions first (InterGen layout), 30 fps
        a = np.load(ref, allow_pickle=False); T = len(a)
        return [(dict(kind='joints', joint_names=[f'joint_{j}' for j in range(22)], parents=[-1] * 22, frame_time=1 / 30.0, frames=T),
                 a[:, :66].astype(np.float32))]
    if reader == 'scene':
        return [bake.read_bvh(os.path.join(bake.scene_to_clip(ref), 'character.bvh'))]
    raise ValueError(f'unknown reader {reader}')


def pool_refs(ds_id):
    """-> [(reader, ref, label)] of everything the dataset's `quality:` pool covers (None: use the viewer examples)"""
    import fnmatch
    import glob as G
    s = spec.load(ds_id) or {}
    q = s.get('quality')
    if not q:                                            # default: the vault collections the viewer examples come from
        clips = [c for it in s.get('items', []) if it.get('source', 'vault') == 'vault'
                 for c in (it['clip'] if isinstance(it['clip'], list) else [it['clip']])]
        if not clips or len(clips) < sum(len(it['clip']) if isinstance(it.get('clip'), list) else 1 for it in s.get('items', [])):
            return None
        top = {'/'.join(c.split('/')[:2]) if c.count('/') >= 2 else c.split('/')[0] for c in clips}    # folder / collection
        q = {'from': [dict(reader='vault', glob=g + '/*') for g in sorted(top)]}
    refs = []
    for e in q['from']:
        ex = [re.compile(re.escape(x), re.I) for x in e.get('exclude', [])]
        if e['reader'] == 'vault':
            folder = e['glob'].split('/')[0]
            cat = json.load(open(os.path.join(config.get('vault'), 'processed', folder, '_catalog.json')))['clips']
            ids = [f"{folder}/{c['id']}" for c in cat if fnmatch.fnmatch(f"{folder}/{c['id']}", e['glob'])]
        elif e['reader'] == 'omomo':
            pk = os.path.join(config.source(e['source']), e['glob'])
            ids = [f'{pk}::{s}' for s in _omomo(pk)]
        else:
            ids = sorted(G.glob(os.path.join(config.source(e['source']), e['glob'])))
        refs += [(e['reader'], i, os.path.basename(i.rstrip('/'))) for i in ids
                 if not MIRROR.search(i.split('::')[-1]) and not any(x.search(i) for x in ex)]
    seen = set()
    return [r for r in refs if not (r[1] in seen or seen.add(r[1]))]


def windows(Q, k):
    """k evenly spaced windows of WINDOW_S seconds (the whole clip when shorter)"""
    L = int(WINDOW_S * FPS)
    if len(Q) <= L:
        return [Q]
    starts = np.linspace(0, len(Q) - L, k + 2)[1:-1] if k > 1 else [(len(Q) - L) / 2]
    return [Q[int(s):int(s) + L] for s in starts]


def sample(ds_id, n=N_WINDOWS, seed=0):
    """-> rows of metrics for n windows: clips drawn at random from the pool (one window each), or several evenly spaced
    windows per clip when the pool has fewer than n clips; the viewer examples when the dataset has no pool. The up axis
    is the spec's or the majority over the first clips, the unit the spec's or picked per clip from the body height."""
    s = spec.load(ds_id) or {}
    refs = pool_refs(ds_id)
    if refs is None:
        items = s.get('items', [])
        per = max(1, -(-n // max(1, len(items))))
        jobs = [('item', it, it.get('label')) for it in items]
    else:
        rng = np.random.default_rng(seed + sum(map(ord, ds_id)))            # the same sample on every run
        per = max(1, -(-n // max(1, len(refs))))
        jobs = [refs[i] for i in rng.permutation(len(refs))[:n]] if len(refs) > n else refs
    qs = s.get('quality') or {}                           # the pool may differ from the examples (other files, other axes)
    up, unit = qs.get('up', s.get('up')), qs.get('unit', s.get('unit'))
    up = None if up == 'auto' else up
    loaded, rows = [], []
    for reader, ref, label in jobs:                       # load lazily; the up vote needs the first clips first
        if len(loaded) >= n and up:
            break
        try:
            parts = parts_of(ds_id, ref) if reader == 'item' else _read(reader, ref)
            parts = [(meta, positions(meta, motion), canon_map(meta)) for meta, motion in parts]
            loaded.append((reader, ref, label, parts))
        except Exception as e:  # noqa
            rows.append(dict(item=label, error=f'{type(e).__name__}: {e}'))
        if up is None and len(loaded) >= 10:
            up = majority_up(loaded)
    up = up or majority_up(loaded)
    unit = unit or dataset_unit(loaded, up)
    for reader, ref, label, parts in loaded:
        take = []
        for k, (meta, P, cm) in enumerate(parts):
            Q, info = to_canon(P, cm, meta['frame_time'], ref.get('up', up) if reader == 'item' else up, unit)
            if Q is None:
                rows.append(dict(item=label, error=info)); continue
            ft = floor_track(Q)                              # over the whole clip: how far the ground moves (a 10 s window hides it)
            drift = round(float(np.percentile(ft, 95) - np.percentile(ft, 5)) * 100, 2)
            for w, Qw in enumerate(windows(Q, per)):
                if len(Qw) >= 60:
                    take.append(dict(item=label, part=k, window=w, **info, **metrics(Qw, info['lowfps'], info['no_toe']), floor_drift_cm=drift))
        if len({r['part'] for r in take}) > 1:            # performers of one take stand on one floor
            for w in {r['window'] for r in take}:
                same = [r for r in take if r['window'] == w]
                gap = round((max(r['floor_median'] for r in same) - min(r['floor_median'] for r in same)) * 100, 2)
                for r in same:
                    r['pair_floor_gap_cm'] = gap
        rows += take
        if sum('error' not in r for r in rows) >= n:
            break
    return rows


def majority_up(loaded):
    votes = [detect_up(P, cm) for _, _, _, parts in loaded for _, P, cm in parts[:1]
             if cm.get('head') is not None and cm.get('pelvis') is not None]
    return max(set(votes), key=votes.count) if votes else '+y'


if __name__ == '__main__':
    main()
