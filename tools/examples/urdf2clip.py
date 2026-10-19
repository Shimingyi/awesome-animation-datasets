"""A robot (URDF + STL meshes) and its joint-angle trajectories (CSV: root xyz + quaternion xyzw, then one angle per
actuated joint in URDF order) -> what the viewer plays: one BVH per trajectory and one rigidly skinned GLB of the robot.

    python -m tools.examples.urdf2clip <robot.urdf> <out dir> <traj.csv> ... [--fps 30]

Every link becomes a joint. The BVH is written in world-aligned rest frames (the robot at zero angles, every joint frame
rotated to the world axes): OFFSET = the link's rest position relative to its parent, channels = the link's rotation
relative to its rest rotation. With that, zero channels = the GLB's bind pose, which the viewer's rig fit expects.
The GLB holds every link's visual STL in the rest pose, each vertex skinned 100 % to its link, turned Y-up as glTF
expects (the BVH keeps the URDF's Z-up; the viewer's rig fit finds the mapping); Blender then decimates it and
compresses it with Draco (<robot>.glb; the full mesh stays as <robot>_full.glb). Fixed joints are kept as links of their own.
"""
import argparse
import json
import math
import os
import struct
import xml.etree.ElementTree as ET

import numpy as np


# ---------------------------------------------------------------------------------------------------------------- maths
def rpy_matrix(r, p, y):
    cr, sr, cp, sp, cy, sy = math.cos(r), math.sin(r), math.cos(p), math.sin(p), math.cos(y), math.sin(y)
    return np.array([[cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
                     [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
                     [-sp, cp * sr, cp * cr]])


def axis_angle(ax, a):
    ax = np.asarray(ax, float); ax = ax / (np.linalg.norm(ax) + 1e-12)
    K = np.array([[0, -ax[2], ax[1]], [ax[2], 0, -ax[0]], [-ax[1], ax[0], 0]])
    return np.eye(3) + math.sin(a) * K + (1 - math.cos(a)) * K @ K


def quat_matrix(x, y, z, w):
    n = math.sqrt(x * x + y * y + z * z + w * w) or 1; x, y, z, w = x / n, y / n, z / n, w / n
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def euler_zyx(R):
    """R = Rz Ry Rx -> degrees (z, y, x), the BVH channel order 'Zrotation Yrotation Xrotation'"""
    sy = -R[2, 0]
    if abs(sy) < 0.999999:
        y = math.asin(sy); z = math.atan2(R[1, 0], R[0, 0]); x = math.atan2(R[2, 1], R[2, 2])
    else:
        y = math.copysign(math.pi / 2, sy); z = math.atan2(-R[0, 1], R[1, 1]); x = 0.0
    return [math.degrees(z), math.degrees(y), math.degrees(x)]


# ---------------------------------------------------------------------------------------------------------------- URDF
def parse_urdf(path):
    root = ET.parse(path).getroot()
    xyz = lambda e, k='xyz': [float(v) for v in (e.get(k) if e is not None and e.get(k) else '0 0 0').split()]  # noqa: E731
    links = {}
    for l in root.findall('link'):
        vis = []
        for v in l.findall('visual'):
            m = v.find('geometry/mesh')
            if m is not None:
                o = v.find('origin')
                vis.append(dict(file=m.get('filename'), xyz=xyz(o), rpy=xyz(o, 'rpy'), scale=xyz(m, 'scale') if m.get('scale') else [1, 1, 1]))
        links[l.get('name')] = vis
    joints = []
    for j in root.findall('joint'):
        o = j.find('origin'); ax = j.find('axis')
        joints.append(dict(name=j.get('name'), type=j.get('type'), parent=j.find('parent').get('link'), child=j.find('child').get('link'),
                           xyz=xyz(o), rpy=xyz(o, 'rpy'), axis=xyz(ax) if ax is not None else [1, 0, 0]))
    children = {j['child'] for j in joints}
    base = next(n for n in links if n not in children)
    return base, links, joints


def tree(base, joints):
    """links in depth-first order with (parent index, joint) and the actuated joints in URDF order"""
    order, info = [base], [(-1, None)]
    def walk(link, idx):
        for j in joints:
            if j['parent'] == link and j['type'] != 'floating':
                order.append(j['child']); info.append((idx, j)); walk(j['child'], len(order) - 1)
    walk(base, 0)
    actuated = [j['name'] for j in joints if j['type'] in ('revolute', 'continuous', 'prismatic')]
    return order, info, actuated


def fk(info, q, root_p, root_R):
    """world rotation / position of every link for joint values q (name -> value)"""
    n = len(info); R, P = [None] * n, [None] * n
    for i, (pi, j) in enumerate(info):
        if pi < 0:
            R[i], P[i] = root_R, root_p; continue
        L = rpy_matrix(*j['rpy'])
        if j['type'] in ('revolute', 'continuous'):
            L = L @ axis_angle(j['axis'], q.get(j['name'], 0.0))
        t = np.array(j['xyz'], float)
        if j['type'] == 'prismatic':
            t = t + rpy_matrix(*j['rpy']) @ (np.array(j['axis']) * q.get(j['name'], 0.0))
        R[i] = R[pi] @ L; P[i] = P[pi] + R[pi] @ t
    return R, P


# ---------------------------------------------------------------------------------------------------------------- BVH
def write_bvh(path, order, info, R0, P0, frames, fps):
    """frames: [(R list, P list)] per frame; world-aligned rest frames (see module doc)"""
    n = len(order); kids = {i: [k for k in range(n) if info[k][0] == i] for i in range(n)}
    lines = ['HIERARCHY']
    def node(i, d):
        pad = '\t' * d; pi = info[i][0]
        off = P0[i] - (P0[pi] if pi >= 0 else 0)
        lines.append(pad + ('ROOT ' if pi < 0 else 'JOINT ') + order[i]); lines.append(pad + '{')
        lines.append(pad + '\tOFFSET %.6f %.6f %.6f' % tuple(off if pi >= 0 else np.zeros(3)))
        lines.append(pad + ('\tCHANNELS 6 Xposition Yposition Zposition Zrotation Yrotation Xrotation' if pi < 0 else '\tCHANNELS 3 Zrotation Yrotation Xrotation'))
        for k in kids[i]:
            node(k, d + 1)
        if not kids[i]:
            lines.append(pad + '\tEnd Site'); lines.append(pad + '\t{'); lines.append(pad + '\t\tOFFSET 0.000000 0.000000 0.020000'); lines.append(pad + '\t}')
        lines.append(pad + '}')
    node(0, 0)
    lines += ['MOTION', f'Frames: {len(frames)}', 'Frame Time: %.6f' % (1 / fps)]
    for R, P in frames:
        A = [R[i] @ R0[i].T for i in range(n)]                      # world rotation relative to the rest
        row = list(P[0]) + euler_zyx(A[0])
        for i in range(1, n):
            row += euler_zyx(A[info[i][0]].T @ A[i])
        lines.append(' '.join('%.6f' % v for v in row))
    with open(path, 'w') as f:
        f.write('\n'.join(lines) + '\n')


# ---------------------------------------------------------------------------------------------------------------- GLB
ZUP_TO_YUP = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], float)


def read_stl(path):
    with open(path, 'rb') as f:
        data = f.read()
    if len(data) > 84 and 84 + 50 * struct.unpack('<I', data[80:84])[0] == len(data):        # binary
        n = struct.unpack('<I', data[80:84])[0]
        rec = np.frombuffer(data, dtype=np.dtype([('n', '<f4', 3), ('v', '<f4', (3, 3)), ('a', '<u2')]), count=n, offset=84)
        return rec['v'].reshape(-1, 3).astype(np.float64)
    vs = [list(map(float, l.split()[1:4])) for l in data.decode('latin-1').splitlines() if l.strip().startswith('vertex')]
    return np.array(vs, float)


def write_glb(path, order, info, R0, P0, links, mesh_dir):
    n = len(order); pos, nrm, jnt = [], [], []
    for i, name in enumerate(order):
        for v in links.get(name, []):
            f = os.path.join(mesh_dir, os.path.basename(v['file'].replace('package://', '')))
            if not os.path.exists(f):
                continue
            tri = read_stl(f) * np.array(v['scale'])
            tri = tri @ rpy_matrix(*v['rpy']).T + v['xyz']                 # visual origin, in the link frame
            tri = tri @ R0[i].T + P0[i]                                     # rest pose, world
            pos.append(tri); jnt.append(np.full(len(tri), i))
    pos = np.concatenate(pos) @ ZUP_TO_YUP.T; jnt = np.concatenate(jnt)
    tri = pos.reshape(-1, 3, 3)
    fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]); fn /= np.linalg.norm(fn, axis=1, keepdims=True) + 1e-12
    nrm = np.repeat(fn, 3, axis=0)
    pos32, nrm32 = pos.astype('<f4'), nrm.astype('<f4')
    joints = np.zeros((len(pos), 4), '<u2'); joints[:, 0] = jnt
    weights = np.zeros((len(pos), 4), '<f4'); weights[:, 0] = 1
    Py = P0 @ ZUP_TO_YUP.T                                                  # glTF is Y-up (the BVH stays in URDF Z-up; the viewer fits the axes)
    ibm = np.stack([np.eye(4) for _ in range(n)]).astype('<f4')
    for i in range(n):
        ibm[i, :3, 3] = -Py[i]                                              # world-aligned rest frames: bind = translation only
    ibm = np.ascontiguousarray(ibm.transpose(0, 2, 1))                      # column-major
    blobs, views, accs = [], [], []
    def add(arr, comp, ctype, typ, target=None, minmax=False):
        b = arr.tobytes(); off = sum(len(x) for x in blobs)
        blobs.append(b + b'\0' * ((-len(b)) % 4))
        views.append(dict(buffer=0, byteOffset=off, byteLength=len(b), **({'target': target} if target else {})))
        a = dict(bufferView=len(views) - 1, componentType=ctype, count=len(arr), type=typ)
        if minmax:
            a.update(min=arr.min(0).tolist(), max=arr.max(0).tolist())
        accs.append(a); return len(accs) - 1
    ap = add(pos32, 3, 5126, 'VEC3', 34962, True); an = add(nrm32, 3, 5126, 'VEC3', 34962)
    aj = add(joints, 4, 5123, 'VEC4', 34962); aw = add(weights, 4, 5126, 'VEC4', 34962); ai = add(ibm, 16, 5126, 'MAT4')
    nodes = []
    for i in range(n):
        pi = info[i][0]; t = Py[i] - (Py[pi] if pi >= 0 else 0)
        nodes.append(dict(name=order[i], translation=[float(x) for x in t], children=[k for k in range(n) if info[k][0] == i]))
    for nd in nodes:
        if not nd['children']:
            nd.pop('children')
    nodes.append(dict(name='robot_mesh', mesh=0, skin=0))
    gl = dict(asset=dict(version='2.0', generator='awesome-animation-datasets urdf2clip'), scene=0,
              scenes=[dict(nodes=[0, n])], nodes=nodes,
              meshes=[dict(primitives=[dict(attributes=dict(POSITION=ap, NORMAL=an, JOINTS_0=aj, WEIGHTS_0=aw), material=0)])],
              materials=[dict(name='robot', pbrMetallicRoughness=dict(baseColorFactor=[0.78, 0.79, 0.81, 1], metallicFactor=0.35, roughnessFactor=0.45))],
              skins=[dict(joints=list(range(n)), inverseBindMatrices=ai, skeleton=0)],
              accessors=accs, bufferViews=views, buffers=[dict(byteLength=sum(len(x) for x in blobs))])
    js = json.dumps(gl, separators=(',', ':')).encode(); js += b' ' * ((-len(js)) % 4)
    bin_ = b''.join(blobs)
    with open(path, 'wb') as f:
        f.write(struct.pack('<III', 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(bin_)))
        f.write(struct.pack('<II', len(js), 0x4E4F534A) + js + struct.pack('<II', len(bin_), 0x004E4942) + bin_)
    return len(pos) // 3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('urdf'); ap.add_argument('out'); ap.add_argument('csv', nargs='+'); ap.add_argument('--fps', type=float, default=30)
    a = ap.parse_args()
    base, links, joints = parse_urdf(a.urdf)
    order, info, actuated = tree(base, joints)
    R0, P0 = fk(info, {}, np.zeros(3), np.eye(3))
    os.makedirs(a.out, exist_ok=True)
    robot = os.path.splitext(os.path.basename(a.urdf))[0]
    raw = os.path.join(a.out, robot + '_full.glb')
    tris = write_glb(raw, order, info, R0, P0, links, os.path.join(os.path.dirname(a.urdf), 'meshes'))
    print(f'{robot}: {len(order)} links, {len(actuated)} actuated joints, mesh {tris} triangles')
    # Blender (blender/fbx2glb.py): decimate by edge collapse (skin weights kept) and Draco-compress -> <robot>.glb
    import subprocess
    from .. import config
    r = subprocess.run([config.get('blender'), '-b', '--factory-startup', '--python', os.path.join(os.path.dirname(__file__), 'blender', 'fbx2glb.py'),
                        '--', raw, os.path.join(a.out, robot + '.glb')], capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        raise SystemExit(r.stdout[-1500:] + r.stderr[-1500:])
    print(f'  -> {robot}.glb {os.path.getsize(os.path.join(a.out, robot + ".glb")) / 1e6:.1f} MB')
    for c in a.csv:
        rows = np.loadtxt(c, delimiter=',', ndmin=2)
        if rows.shape[1] != 7 + len(actuated):
            raise SystemExit(f'{c}: {rows.shape[1]} columns, expected 7 + {len(actuated)}')
        frames = []
        for r in rows:
            q = dict(zip(actuated, r[7:]))
            frames.append(fk(info, q, r[:3], quat_matrix(*r[3:7])))
        out = os.path.join(a.out, os.path.splitext(os.path.basename(c))[0] + '.bvh')
        write_bvh(out, order, info, R0, P0, frames, a.fps)
        print(f'  {os.path.basename(c)}: {len(rows)} frames -> {out}')


if __name__ == '__main__':
    main()
