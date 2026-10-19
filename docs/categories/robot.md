# 🤖 Robots

<sub>Generated from `data/datasets/*.yaml` by `python -m tools.readme` — edit the yaml, not this page.</sub>

Motion on robot kinematics (humanoids, quadrupeds), usually retargeted from human or animal data.

| Dataset | Hours | Clips | Data | Links | Viewer | Preview |
|---|--:|--:|---|---|:-:|---|
| [**MotionDecode**](../categories/robot.md#motiondecode)<br><sub>Nearly 1,000 h of optical mocap retargeted to the Unitree G1, in 480 labelled everyday, work, social and sports tasks: humanoid imitation learning.</sub> | 973 | 91k | csv | [home](https://chingmudata.github.io/MotionDecode/)<br>[data](https://huggingface.co/datasets/CMRobot/MotionDecode) | [▶](https://myshi-motion-viewer.static.hf.space/#motiondecode/g1-basic-gait-normal-walking) | <a href="https://myshi-motion-viewer.static.hf.space/#motiondecode/g1-basic-gait-normal-walking"><img src="../assets/thumbs/motiondecode.webp" width="607" height="200" alt="MotionDecode examples"></a> |
| [**Unitree LAFAN1 Retargeting**](../categories/robot.md#unitree-lafan1-retarget)<br><sub>Human motion retargeted to Unitree humanoids: robot imitation learning.</sub> | 2.5¹ | 40 | csv | [home](https://huggingface.co/datasets/unitreerobotics/LAFAN1_Retargeting_Dataset) | [▶](https://myshi-motion-viewer.static.hf.space/#unitree-lafan1-retarget/g1-dance1-s2) | <a href="https://myshi-motion-viewer.static.hf.space/#unitree-lafan1-retarget/g1-dance1-s2"><img src="../assets/thumbs/unitree-lafan1-retarget.webp" width="607" height="200" alt="Unitree LAFAN1 Retargeting examples"></a> |

## MotionDecode

<a href="https://myshi-motion-viewer.static.hf.space/#motiondecode/g1-basic-gait-normal-walking"><img src="../assets/thumbs/motiondecode.webp" width="486" height="160" alt="MotionDecode examples"></a>

**ChingMu MotionDecode 1000-Hour Embodied Motion Dataset (Unitree G1 release)** (2026)

*Good for:* Nearly 1,000 h of optical mocap retargeted to the Unitree G1, in 480 labelled everyday, work, social and sports tasks: humanoid imitation learning.

| | |
|---|---|
| Size | 973 h · 91,198 clips |
| Motion | daily activities & objects 58 %, gesture & speech 16 %, locomotion 9 %, interaction 8 %, sports & exercise 5 %, dance 4 %, combat & action 0 % (our count of the hours per folder of the release taxonomy: daily life, household, occupational, assistive and object-handling tasks as daily-activity; emotional expression and greetings as gesture; gait, crawling, stairs and terrain as locomotion; object passing and cooperative carrying or moving as interaction; jumps, throws, balance, parkour and ball games as sports; boxing, fencing and martial arts as combat) · tags: daily-activity, object-manipulation, gesture, emotion, interaction, locomotion, crawling, sitting, sports, acrobatics, dance, combat, retargeted |
| Capture | optical-mocap |
| Data | csv · 29 joints · Unitree G1 (29 DoF), root position (m, Z-up) and quaternion (wxyz) plus joint angles (rad) in URDF order · 120 fps |
| Annotations | action-labels |
| Licence | ❌ [ChingMu Dataset Access Terms (non-commercial)](https://huggingface.co/datasets/CMRobot/MotionDecode/blob/main/LICENSE.md) · access: open |
| Links | [homepage](https://chingmudata.github.io/MotionDecode/) · [download](https://huggingface.co/datasets/CMRobot/MotionDecode) |
| Quality |  Usable — ground or self penetration, retargeting artifacts. Foot contact is as steady as the Unitree LAFAN1 retarget, but the feet sit about 2 cm below z = 0 throughout. The pop-dance part (5.Dance, about 11 h) has frequent single-frame flips of the shoulder pitch and yaw angles; the other folders rarely do. |
| Viewer | [10 examples](https://myshi-motion-viewer.static.hf.space/#motiondecode/g1-basic-gait-normal-walking) |

<sub>Size: our count of the full Hugging Face release (September 2026): 92,560 G1 CSVs (138 GB on disk) under the 480 task labels of metadata/index.csv, of which 1,362 are byte-identical copies of other files; the remaining 91,198 takes hold 420,336,456 frames, 973.0 h at 120 fps. Official: "1000+ hours @ 120 Hz" of optical mocap, 15+ scenarios, 500+ tasks, 200+ tracked objects; the number of performers is not given. The card also lists BVH, object 6D pose, video and NPZ, but only the retargeted G1 CSVs are released.</sub>

Optical motion capture by ChingMu (a Chinese mocap-system maker), released as Unitree G1 trajectories only: one CSV per take with the root pose and the 29 joint angles at 120 fps, filed in a four-level folder taxonomy (basic movement, gait, daily life, occupational and assistive tasks, social interaction, emotional expression, dance, parkour, ball games, combat). The partner of a two-person task is not released, and the release adds no text descriptions.

## Unitree LAFAN1 Retargeting

<a href="https://myshi-motion-viewer.static.hf.space/#unitree-lafan1-retarget/g1-dance1-s2"><img src="../assets/thumbs/unitree-lafan1-retarget.webp" width="486" height="160" alt="Unitree LAFAN1 Retargeting examples"></a>

**LAFAN1 Retargeting Dataset (Unitree G1, H1, H1_2)** (2025)

*Good for:* Human motion retargeted to Unitree humanoids: robot imitation learning.

| | |
|---|---|
| Size | 2.5 h · 40 clips · 3 subjects |
| Motion | locomotion 54 %, combat & action 28 %, dance 9 %, unclassified 9 % (LAFAN1 takes retargeted, so their composition (measured from the take names)) · tags: locomotion, dance, combat, sports, falling, retargeted |
| Capture | retargeted |
| Data | csv · Unitree G1 (29 joints), H1_2 (27 joints) and H1 (19 joints), each with a floating base · 30 fps |
| Annotations | – |
| Licence | ❌ [CC BY-NC-ND 4.0 (LAFAN1 data; code BSD-3-Clause)](https://creativecommons.org/licenses/by-nc-nd/4.0/) · access: open |
| Links | [homepage](https://huggingface.co/datasets/unitreerobotics/LAFAN1_Retargeting_Dataset) |
| Derived from | [LAFAN1](human-body.md#lafan1) |
| Viewer | [10 examples](https://myshi-motion-viewer.static.hf.space/#unitree-lafan1-retarget/g1-dance1-s2) |

<sub>Size: 40 LAFAN1 takes retargeted to each of 3 robots (G1, H1, H1_2), counted from the release; hours are our count of the G1 trajectories (264,705 frames at 30 fps), the same motion on each robot, so counted once</sub>

LAFAN1 takes retargeted to Unitree humanoids with Interaction Mesh and IK optimisation under kinematic constraints only, stored as per-frame root pose and joint angles. The official Hugging Face repository was not publicly reachable in October 2026; copies exist under other accounts.
