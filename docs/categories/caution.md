#  Use with caution

<sub>Generated from `data/datasets/*.yaml` by `python -m tools.readme` — edit the yaml, not this page.</sub>

Datasets whose motion quality fell short when we inspected it (jitter, foot skating, penetration ...). They are still large and useful for some purposes; read the reason before you use them.

| Dataset | Hours | Clips | Data | Links | Viewer | Preview |
|---|--:|--:|---|---|:-:|---|
| [**MotionMillion**](../categories/caution.md#motionmillion)<br><sub>Very large text-annotated motion corpus for zero-shot text-to-motion; quality varies (video mocap).</sub> | 988 | 685k | features | [home](https://huggingface.co/datasets/InternRobotics/MotionMillion)<br>[data](https://huggingface.co/datasets/InternRobotics/MotionMillion) | [▶](https://myshi-motion-viewer.static.hf.space/#motionmillion/motiongv-folder1-061406) | <a href="https://myshi-motion-viewer.static.hf.space/#motionmillion/motiongv-folder1-061406"><img src="../assets/thumbs/motionmillion.webp" width="607" height="200" alt="MotionMillion examples"></a> |
| [**Motion-X**](../categories/caution.md#motion-x)<br><sub>Very large whole-body SMPL-X with text, mostly from video: coverage over quality.</sub> | 144 | 81k | SMPL-X | [home](https://motion-x-dataset.github.io)<br>[code](https://github.com/IDEA-Research/Motion-X)<br>[paper](https://arxiv.org/abs/2307.00818) | [▶](https://myshi-motion-viewer.static.hf.space/#motion-x/badminton-underswing-clip-1) | <a href="https://myshi-motion-viewer.static.hf.space/#motion-x/badminton-underswing-clip-1"><img src="../assets/thumbs/motion-x.webp" width="607" height="200" alt="Motion-X examples"></a> |
| [**AnimationGPT**](../categories/caution.md#animationgpt)<br><sub>Game-style combat moves with text: text-to-motion for fighting and action games.</sub> | 26.4 | 15k | joints<br>features | [home](https://github.com/fyyakaxyy/AnimationGPT)<br>[data](https://drive.google.com/file/d/148AwoovJrnh4F0q_HbU83WCWwFooLSZj/view?usp=drive_link)<br>[code](https://github.com/fyyakaxyy/AnimationGPT) | [▶](https://myshi-motion-viewer.static.hf.space/#animationgpt/cmp000081) | <a href="https://myshi-motion-viewer.static.hf.space/#animationgpt/cmp000081"><img src="../assets/thumbs/animationgpt.webp" width="607" height="200" alt="AnimationGPT examples"></a> |
| [**AIST++**](../categories/caution.md#aistpp)<br><sub>Street-dance motion paired with music in 10 genres: the standard benchmark for music-to-dance generation.</sub> | 5.2 | 1.4k | SMPL<br>keypoints<br>pkl | [home](https://google.github.io/aistplusplus_dataset/)<br>[data](https://github.com/google/aistplusplus_dataset/releases/tag/v1.0)<br>[code](https://github.com/google/aistplusplus_api)<br>[paper](https://arxiv.org/abs/2101.08779) | [▶](https://myshi-motion-viewer.static.hf.space/#aistpp/breaking-choreography) | <a href="https://myshi-motion-viewer.static.hf.space/#aistpp/breaking-choreography"><img src="../assets/thumbs/aistpp.webp" width="607" height="200" alt="AIST++ examples"></a> |
| [**PHUMA**](../categories/caution.md#phuma)<br><sub>Large physics-filtered human motion retargeted to Unitree G1 and H1-2: humanoid imitation learning.</sub> | 73.0¹ | 76k | npy | [home](https://davian-robotics.github.io/PHUMA/)<br>[data](https://huggingface.co/datasets/DAVIAN-Robotics/PHUMA)<br>[code](https://github.com/DAVIAN-Robotics/PHUMA)<br>[paper](https://arxiv.org/abs/2510.26236) | [▶](https://myshi-motion-viewer.static.hf.space/#phuma/g1-amass-humanml3d-014612) | <a href="https://myshi-motion-viewer.static.hf.space/#phuma/g1-amass-humanml3d-014612"><img src="../assets/thumbs/phuma.webp" width="607" height="200" alt="PHUMA examples"></a> |

## MotionMillion

<a href="https://myshi-motion-viewer.static.hf.space/#motionmillion/motiongv-folder1-061406"><img src="../assets/thumbs/motionmillion.webp" width="486" height="160" alt="MotionMillion examples"></a>

*Good for:* Very large text-annotated motion corpus for zero-shot text-to-motion; quality varies (video mocap).

| | |
|---|---|
| Size | 988 h · 684,580 clips |
| Motion | sports & exercise 29 %, combat & action 24 %, dance 15 %, unclassified 32 % (from the dataset card's category shares (fitness and sports, martial arts, dance; performance, non-human and the rest unclassified)) · tags: text-annotated, martial-arts, sports, dance |
| Capture | video |
| Data | features · 22 joints · SMPL body joints (272-dim MotionStreamer features) · 30 fps |
| Annotations | text, age, body-characteristics, style, emotion, environment |
| Licence | ❌ [CC BY-NC-SA 4.0 (MotionMillion community licence, gated)](https://creativecommons.org/licenses/by-nc-sa/4.0/) · access: gated |
| Links | [homepage](https://huggingface.co/datasets/InternRobotics/MotionMillion) · [download](https://huggingface.co/datasets/InternRobotics/MotionMillion) |
| Quality |  Use with caution — foot skating, unnatural body angles. Reconstructed from web video (video mocap): foot skating and motion that does not look physically real in the examples we inspected. |
| Viewer | [10 examples](https://myshi-motion-viewer.static.hf.space/#motionmillion/motiongv-folder1-061406) |

<sub>Size: our count of the released non-mirrored archives (684,580 clips, 987.8 h at 30 fps); the card's "over 2000 hours" includes the mirrored copy, and BABEL, AIST and HumanML3D are not redistributed (processing scripts only)</sub>

Motion recovered from web video (the card says over 2000 hours), plus several existing sets re-processed into one 272-dim representation (root velocity and heading, 22 joint positions, velocities and 6D rotations), each motion with 20+ annotations (age, body, style, emotion, environment).

## Motion-X

<a href="https://myshi-motion-viewer.static.hf.space/#motion-x/badminton-underswing-clip-1"><img src="../assets/thumbs/motion-x.webp" width="486" height="160" alt="Motion-X examples"></a>

**Motion-X: A Large-scale 3D Expressive Whole-body Human Motion Dataset** (2023)

*Good for:* Very large whole-body SMPL-X with text, mostly from video: coverage over quality.

| | |
|---|---|
| Size | 144 h · 81,084 clips |
| Motion | sports & exercise 40 %, daily activities & objects 19 %, unclassified 15 %, locomotion 10 %, combat & action 8 %, dance 7 %, gesture & speech 1 % (measured from the sub-dataset and clip names, weighted by duration) · tags: daily-activity, dance, sports, martial-arts, text-annotated, action-labels |
| Capture | mixed |
| Data | smplx · 55 joints · SMPL-X · 30 fps |
| Annotations | text, pose-text, facial-expression |
| Licence | ❌ [Motion-X License (non-commercial; subsets also under their source licenses)](https://motion-x-dataset.github.io/static/license/Motion-X%20License.pdf) · access: gated |
| Links | [homepage](https://motion-x-dataset.github.io) · [code](https://github.com/IDEA-Research/Motion-X) · [paper](https://arxiv.org/abs/2307.00818) |
| Paper | Motion-X: A Large-scale 3D Expressive Whole-body Human Motion Dataset (NeurIPS 2023) |
| Quality |  Use with caution — jitter / high-frequency noise, foot skating, ground or self penetration. Most of the motion is reconstructed from monocular video: strong jitter, foot skating and ground / self penetration across the examples we inspected. |
| Viewer | [10 examples](https://myshi-motion-viewer.static.hf.space/#motion-x/badminton-underswing-clip-1) |

<sub>Size: 81,084 sequences, 144.2 h and 15.6M whole-body poses at 30 fps (official, Table 1 of the paper). The data distributed by the authors, without the AMASS, GRAB and EgoBody subsets, is 52,464 clips (86.7 h) in the BVH release used by DATA.md</sub>

Whole-body SMPL-X motion (body, hands, face) with sequence- and frame-level text, unified from online videos, the self-recorded IDEA400 set and eight existing datasets. The AMASS, GRAB and EgoBody motion is not redistributed and must be obtained from those datasets; Motion-X provides text and face labels for them.

Other releases of the same motion:

- [Motion-X++](https://huggingface.co/datasets/YuhongZhang/Motion-Xplusplus) — extended re-release (120.5K sequences, 19.5M poses) with re-annotated SMPL-X, video, audio and text (arXiv:2501.05098)

<details><summary>BibTeX</summary>

```bibtex
@article{lin2023motionx,
  title={Motion-X: A Large-scale 3D Expressive Whole-body Human Motion Dataset},
  author={Lin, Jing and Zeng, Ailing and Lu, Shunlin and Cai, Yuanhao and Zhang, Ruimao and Wang, Haoqian and Zhang, Lei},
  journal={Advances in Neural Information Processing Systems},
  year={2023}
}
```

</details>

## AnimationGPT

<a href="https://myshi-motion-viewer.static.hf.space/#animationgpt/cmp000081"><img src="../assets/thumbs/animationgpt.webp" width="486" height="160" alt="AnimationGPT examples"></a>

**AnimationGPT CombatMotion dataset** (2024)

*Good for:* Game-style combat moves with text: text-to-motion for fighting and action games.

| | |
|---|---|
| Size | 26.4 h · 14,883 clips |
| Motion | Combat & action · tags: combat, martial-arts, text-annotated |
| Capture | retargeted |
| Data | joints, features · 22 joints · SMPL body joints (HumanML3D format) |
| Annotations | text |
| Licence | ❔ [Not specified (repository MIT)](https://github.com/fyyakaxyy/AnimationGPT/blob/main/LICENSE) · access: open |
| Links | [homepage](https://github.com/fyyakaxyy/AnimationGPT) · [download](https://drive.google.com/file/d/148AwoovJrnh4F0q_HbU83WCWwFooLSZj/view?usp=drive_link) · [code](https://github.com/fyyakaxyy/AnimationGPT) |
| Quality |  Use with caution — jitter / high-frequency noise, unnatural body angles. Jittery motion that does not look real in the examples we inspected. |
| Viewer | [10 examples](https://myshi-motion-viewer.static.hf.space/#animationgpt/cmp000081) |

<sub>Size: CombatMotionRaw (CMR) holds 14,883 animations with one text annotation each; CombatMotionProcessed (CMP) is a curated subset of 8,700 animations with three annotations each. Hours are counted from the 14,762 CMR clips converted to BVH in DATA.md.</sub>

Combat animations taken from game assets (FBX), retargeted to SMPL and annotated with action, weapon, attack, direction, power and speed terms combined into sentences by GPT-4. Released in HumanML3D format for text-to-motion training.

<details><summary>BibTeX</summary>

```bibtex
@misc{CombatMotion,
  title={AnimationGPT:An AIGC tool for generating game combat motion assets},
  author={Yihao Liao, Yiyu Fu, Ziming Cheng, Jiangfeiyang Wang},
  year={2024},
  howpublished={\url{https://github.com/fyyakaxyy/AnimationGPT}}
}
```

</details>

## AIST++

<a href="https://myshi-motion-viewer.static.hf.space/#aistpp/breaking-choreography"><img src="../assets/thumbs/aistpp.webp" width="486" height="160" alt="AIST++ examples"></a>

**AIST++: 3D dance motion with music, reconstructed from the AIST Dance Video Database** (2021)

*Good for:* Street-dance motion paired with music in 10 genres: the standard benchmark for music-to-dance generation.

| | |
|---|---|
| Size | 5.2 h · 1,408 clips · 30 subjects |
| Motion | Dance (all dance: 10 street / jazz genres (breaking, popping, locking, middle and LA-style hip-hop, house, waack, krump, street jazz, ballet jazz)) · tags: dance, music |
| Capture | video |
| Data | smpl, keypoints, pkl · 24 joints · SMPL (no shape released) and 17 COCO 3D keypoints · 60 fps |
| Annotations | music |
| Licence | ✅ [CC BY 4.0 (annotations); videos and music under the AIST Dance Video Database terms](https://google.github.io/aistplusplus_dataset/factsfigures.html) · access: open |
| Links | [homepage](https://google.github.io/aistplusplus_dataset/) · [download](https://github.com/google/aistplusplus_dataset/releases/tag/v1.0) · [code](https://github.com/google/aistplusplus_api) · [paper](https://arxiv.org/abs/2101.08779) |
| Paper | AI Choreographer: Music Conditioned 3D Dance Generation with AIST++ (ICCV 2021) |
| Quality |  Use with caution — foot skating, unnatural body angles. Reconstructed from video (no markers): foot sliding throughout, and some sequences are broken (the official ignore list marks 46 poor reconstructions, and more fail in the examples we inspected). |
| Viewer | [10 examples](https://myshi-motion-viewer.static.hf.space/#aistpp/breaking-choreography) |

<sub>Size: our count of the release: 1,408 solo sequences of 3D keypoints, 5.2 h at 60 fps (4.99 h without the 46 sequences on the official ignore list of poor reconstructions), 30 dancers, matching the paper. The GitHub v1.0 re-release ships SMPL fits for only 411 of them (1.27 h); the original Cloud Storage full set is no longer public.</sub>

Reconstructed without markers from the 9-camera videos of the AIST Dance Video Database: 2D keypoints triangulated and fitted with SMPL. Basic (sBM) and advanced choreography (sFM) sequences of 10 genres by 30 professional dancers, each with the music it was danced to; the official ignore list marks sequences with poor reconstructions.

<details><summary>BibTeX</summary>

```bibtex
@inproceedings{li2021aichoreographer,
  title={AI Choreographer: Music Conditioned 3D Dance Generation with AIST++},
  author={Li, Ruilong and Yang, Shan and Ross, David A. and Kanazawa, Angjoo},
  booktitle={ICCV},
  year={2021}
}
```

</details>

## PHUMA

<a href="https://myshi-motion-viewer.static.hf.space/#phuma/g1-amass-humanml3d-014612"><img src="../assets/thumbs/phuma.webp" width="486" height="160" alt="PHUMA examples"></a>

**PHUMA: Physically-Grounded Humanoid Locomotion Dataset** (2025)

*Good for:* Large physics-filtered human motion retargeted to Unitree G1 and H1-2: humanoid imitation learning.

| | |
|---|---|
| Size | 73.0 h · 76,010 clips |
| Motion | Unclassified (mixed human motion (Motion-X video, AMASS, IDEA400, LAFAN1, AIST ...), not broken down by motion type) · tags: locomotion, dance, sports, retargeted |
| Capture | retargeted |
| Data | npy · Unitree G1 (29 DoF) and H1-2 (21 DoF without wrists), root position and quaternion plus joint angles · 30 fps |
| Annotations | – |
| Licence | ❔ [Apache-2.0 (Hugging Face card; source motions keep their own licences)](https://huggingface.co/datasets/DAVIAN-Robotics/PHUMA) · access: open |
| Links | [homepage](https://davian-robotics.github.io/PHUMA/) · [download](https://huggingface.co/datasets/DAVIAN-Robotics/PHUMA) · [code](https://github.com/DAVIAN-Robotics/PHUMA) · [paper](https://arxiv.org/abs/2510.26236) |
| Paper | PHUMA: Physically-Grounded Humanoid Locomotion Dataset (CoRL 2026) |
| Quality |  Use with caution — root drift / floating, foot skating, unnatural body angles. In the examples we inspected the feet float above the floor and slide, and the motion looks unnatural; part of the source motion is reconstructed from web video (Motion-X). |
| Derived from | [AMASS](human-body.md#amass), [Motion-X](caution.md#motion-x), [LAFAN1](human-body.md#lafan1) |
| Viewer | [10 examples](https://myshi-motion-viewer.static.hf.space/#phuma/g1-amass-humanml3d-014612) |

<sub>Size: official: 72.96 h in 76.01K 4-second clips (7.88M frames) per robot. Sources: Motion-X video 31.98 h, AMASS 20.86 h, IDEA400 9.10 h, LAFAN1 2.40 h, EgoBody 2.19 h, GRAB 1.88 h, AIST 1.66 h, HAA500 1.01 h, LocoMuJoCo 0.86 h, own video 0.56 h, HuMMan 0.47 h. The Hugging Face release leaves out the LAFAN1 and LocoMuJoCo parts, which the GitHub script rebuilds.</sub>

Human motion from Humanoid-X sources (Motion-X video, AMASS, ...), LAFAN1 and LocoMuJoCo, filtered for physical plausibility (foot contact, floating, penetration) and retargeted with PhySINK, a physics-constrained IK with joint limits and ground contact, to Unitree G1 and H1-2. Each clip stores root translation, root quaternion and joint positions at 30 fps; the same motions exist for both robots.

<details><summary>BibTeX</summary>

```bibtex
@article{lee2025phuma,
  title={PHUMA: Physically-Grounded Humanoid Locomotion Dataset},
  author={Kyungmin Lee and Sibeen Kim and Youngdo Lee and Minho Park and Hyunseung Kim and Dongyoon Hwang and Donghu Kim and Hojoon Lee and Jaegul Choo},
  journal={arXiv preprint arXiv:2510.26236},
  year={2025}
}
```

</details>
