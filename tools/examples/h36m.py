"""Human3.6M D3_Angles (CDF, from the official download) -> BVH, one per take, with each subject's own bone lengths.

    python -m tools.examples.h36m <raw dir: S*/MyPoseFeatures/D3_Angles|D3_Positions/*.cdf> <metadata.xml> <out dir>

The skeleton is the official `skel_angles` tree of metadata.xml (32 joints, rotation order zxy, the angle columns of
each joint in `rotInd`; the release's toolbox, also shipped by github.com/anibali/h36m-fetch). The template OFFSETs give
each bone's direction; its length is the subject's, measured from that subject's D3_Positions (median over takes).
`Pose` of D3_Angles is (T, 78): root position (mm, Z-up) and 25 x 3 Euler angles (degrees). With channels
Zrotation Xrotation Yrotation taking the rotInd columns [2], [0], [1], forward kinematics reproduces D3_Positions to
0.0 mm. 50 fps, millimetres, Z-up.
"""
import argparse
import glob
import os
import re
import xml.etree.ElementTree as ET

import numpy as np

FPS = 50.0


def skeleton(metadata):
    tree = list(ET.parse(metadata).getroot().find('skel_angles').find('tree'))
    num = lambda s: [float(v) for v in re.findall(r'-?\d+\.?\d*(?:e-?\d+)?', s or '')]   # noqa: E731
    J = []
    for k, it in enumerate(tree):
        d = {c.tag: (c.text or '').strip() for c in it}
        rot = [int(v) - 1 for v in num(d['rotInd'])]
        J.append(dict(name=d['name'], parent=int(d['parent']) - 1 if k else -1, dir=np.array(num(d['offset'])),
                      cols=[rot[2], rot[0], rot[1]] if rot else []))   # Z, X, Y rotation columns
    return J


def bone_lengths(J, files):
    import cdflib
    L = []
    for f in files:
        X = np.asarray(cdflib.CDF(f).varget('Pose'), np.float64).reshape(-1, 32, 3)
        L.append(np.median(np.linalg.norm(X - X[:, [max(j['parent'], 0) for j in J]], axis=-1), 0))
    return np.median(L, 0)


def write_bvh(path, J, L, A):
    kids = {k: [c for c, j in enumerate(J) if j['parent'] == k] for k in range(len(J))}
    names, lines, cols = {}, ['HIERARCHY'], []
    def off(k):
        n = np.linalg.norm(J[k]['dir'])
        return J[k]['dir'] / n * L[k] if n > 1e-9 and k else np.zeros(3)
    def emit(k, depth):
        t = '\t' * depth; j = J[k]
        if not j['cols']:                                    # a site: End Site of its parent
            lines.append(f'{t}End Site'); lines.append(f'{t}{{')
            lines.append(f'{t}\tOFFSET ' + ' '.join(f'{v:.4f}' for v in off(k))); lines.append(f'{t}}}'); return
        name = j['name'] if j['name'] not in names else f"{j['name']}_{k}"; names[name] = k
        lines.append(f'{t}{"ROOT" if j["parent"] < 0 else "JOINT"} {name}'); lines.append(f'{t}{{')
        lines.append(f'{t}\tOFFSET ' + ' '.join(f'{v:.4f}' for v in off(k)))
        if j['parent'] < 0:
            lines.append(f'{t}\tCHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation'); cols.extend([0, 1, 2])
        else:
            lines.append(f'{t}\tCHANNELS 3 Zrotation Xrotation Yrotation')
        cols.extend(j['cols'])
        for c in kids[k]:
            emit(c, depth + 1)
        lines.append(f'{t}}}')
    emit(0, 0)
    lines += ['MOTION', f'Frames: {len(A)}', f'Frame Time: {1 / FPS:.6f}']
    lines += [' '.join(f'{v:.4f}' for v in row) for row in A[:, cols]]
    with open(path, 'w') as f:
        f.write('\n'.join(lines) + '\n')


def main():
    import cdflib
    ap = argparse.ArgumentParser()
    ap.add_argument('raw'); ap.add_argument('metadata'); ap.add_argument('out')
    a = ap.parse_args()
    J = skeleton(a.metadata)
    n = 0
    for sd in sorted(glob.glob(os.path.join(a.raw, 'S*'))):
        subj = os.path.basename(sd)
        L = bone_lengths(J, sorted(glob.glob(os.path.join(sd, 'MyPoseFeatures', 'D3_Positions', '*.cdf'))))
        os.makedirs(os.path.join(a.out, subj), exist_ok=True)
        for f in sorted(glob.glob(os.path.join(sd, 'MyPoseFeatures', 'D3_Angles', '*.cdf'))):
            A = np.asarray(cdflib.CDF(f).varget('Pose'), np.float64).reshape(-1, 78)
            write_bvh(os.path.join(a.out, subj, os.path.splitext(os.path.basename(f))[0].replace(' ', '_') + '.bvh'), J, L, A)
            n += 1
    print(f'{n} BVH -> {a.out}')


if __name__ == '__main__':
    main()
