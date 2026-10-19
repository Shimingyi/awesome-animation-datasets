"""ChingMu MotionDecode (CMRobot/MotionDecode on the Hub) -> joint-angle CSVs for tools/examples/urdf2clip.py.

    python -m tools.examples.motiondecode <out dir> <release csv> ... [--step 4]

Each release CSV is one take of the Unitree G1 (29 DoF) at 120 fps with a header: root_pos_x/y/z (m, Z-up),
root_rot_w/x/y/z, then dof_<joint>(rad) in the URDF's actuated order. urdf2clip wants no header and the quaternion as
xyzw, so the columns are reordered; every --step-th frame is kept (120 -> 30 fps by default: the bake resamples to
<= 30 fps anyway and the BVH stays small). Written as <out dir>/<file name>.csv; fps in <out dir>/fps.json.
"""
import argparse
import json
import os

import numpy as np

G1 = ['left_hip_pitch', 'left_hip_roll', 'left_hip_yaw', 'left_knee', 'left_ankle_pitch', 'left_ankle_roll',
      'right_hip_pitch', 'right_hip_roll', 'right_hip_yaw', 'right_knee', 'right_ankle_pitch', 'right_ankle_roll',
      'waist_yaw', 'waist_roll', 'waist_pitch',
      'left_shoulder_pitch', 'left_shoulder_roll', 'left_shoulder_yaw', 'left_elbow', 'left_wrist_roll', 'left_wrist_pitch', 'left_wrist_yaw',
      'right_shoulder_pitch', 'right_shoulder_roll', 'right_shoulder_yaw', 'right_elbow', 'right_wrist_roll', 'right_wrist_pitch', 'right_wrist_yaw']
HEADER = ([f'root_pos_{a}(m)' for a in 'xyz'] + [f'root_rot_{a}' for a in 'wxyz'] + [f'dof_{j}_joint(rad)' for j in G1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out'); ap.add_argument('csv', nargs='+'); ap.add_argument('--step', type=int, default=4)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    fps_path = os.path.join(a.out, 'fps.json')
    fps = json.load(open(fps_path)) if os.path.exists(fps_path) else {}
    for c in a.csv:
        with open(c) as f:
            head = f.readline().strip().split(',')
        if head != HEADER:                       # the column order is all we rely on: refuse anything else
            print(f'{c}: unexpected header, skipped'); continue
        r = np.loadtxt(c, delimiter=',', skiprows=1, ndmin=2)[::a.step]
        rows = np.concatenate([r[:, :3], r[:, 4:7], r[:, 3:4], r[:, 7:]], 1)       # quaternion wxyz -> xyzw
        name = os.path.splitext(os.path.basename(c))[0]
        np.savetxt(os.path.join(a.out, name + '.csv'), rows, delimiter=',', fmt='%.6f')
        fps[name] = 120 / a.step
        print(f'{name}: {len(rows)} frames at {fps[name]:g} fps')
    json.dump(fps, open(fps_path, 'w'), indent=1)


if __name__ == '__main__':
    main()
