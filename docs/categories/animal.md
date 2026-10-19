# 🐾 Animals

<sub>Generated from `data/datasets/*.yaml` by `python -m tools.readme` — edit the yaml, not this page.</sub>

Quadrupeds, birds, insects, fish and other creatures, captured or keyframed.

| Dataset | Hours | Clips | Data | Links | Viewer | Preview |
|---|--:|--:|---|---|:-:|---|
| [**Truebones Zoo**](../categories/animal.md#truebones-zoo)<br><sub>Dozens of animal species with rigs and meshes: any-skeleton and animal motion research.</sub> | 1.4 | 1.2k | fbx<br>bvh | [home](https://truebones.gumroad.com/l/skZMC) | [▶](https://myshi-motion-viewer.static.hf.space/#truebones-zoo/elephant-walk) | <a href="https://myshi-motion-viewer.static.hf.space/#truebones-zoo/elephant-walk"><img src="../assets/thumbs/truebones-zoo.webp" width="607" height="200" alt="Truebones Zoo examples"></a> |
| [**MANN Dog**](../categories/animal.md#mann-dog)<br><sub>Quadruped (dog) gaits and transitions: quadruped character control.</sub> | 0.50 | 51 | bvh | [home](https://github.com/sebastianstarke/AI4Animation)<br>[data](https://starke-consult.de/AI4Animation/SIGGRAPH_2018/MotionCapture.zip)<br>[code](https://github.com/sebastianstarke/AI4Animation/tree/master/AI4Animation/SIGGRAPH_2018)<br>[paper](https://github.com/sebastianstarke/AI4Animation/blob/master/Media/SIGGRAPH_2018/Paper.pdf) | [▶](https://myshi-motion-viewer.static.hf.space/#mann-dog/d1-010-kan01-004) | <a href="https://myshi-motion-viewer.static.hf.space/#mann-dog/d1-010-kan01-004"><img src="../assets/thumbs/mann-dog.webp" width="607" height="200" alt="MANN Dog examples"></a> |

## Truebones Zoo

<a href="https://myshi-motion-viewer.static.hf.space/#truebones-zoo/elephant-walk"><img src="../assets/thumbs/truebones-zoo.webp" width="486" height="160" alt="Truebones Zoo examples"></a>

**Truebones FBX/BVH Zoo** (2022)

*Good for:* Dozens of animal species with rigs and meshes: any-skeleton and animal motion research.

| | |
|---|---|
| Size | 1.4 h · 1,219 clips · 70 subjects |
| Motion | Unclassified · tags: locomotion, gait |
| Capture | mixed |
| Data | fbx, bvh |
| Annotations | – |
| Licence | ✅ [Truebones royalty-free licence (no resale)](https://truebones.gumroad.com/l/skZMC) · access: paid |
| Links | [homepage](https://truebones.gumroad.com/l/skZMC) |
| Viewer | [10 examples](https://myshi-motion-viewer.static.hf.space/#truebones-zoo/elephant-walk) |

<sub>Size: Truebones lists over 75 animals; the clip, frame and skeleton counts are those reported by AnyTop (Gat et al. 2025) for its copy of the Zoo; hours are those 147,178 frames at the 30 fps of the Truebones files. DATA.md counts 3,488 clips (2.1 h) across several Truebones packs.</sub>

Commercial library of rigged, textured animals (mammals, birds, insects, reptiles, fish, dinosaurs and other creatures), each with a set of animation clips. It was offered as a free download for some time and is now sold on Gumroad, at USD 99 at the time of writing.

## MANN Dog

<a href="https://myshi-motion-viewer.static.hf.space/#mann-dog/d1-010-kan01-004"><img src="../assets/thumbs/mann-dog.webp" width="486" height="160" alt="MANN Dog examples"></a>

**Mode-Adaptive Neural Networks quadruped (dog) motion capture** (2018)

*Good for:* Quadruped (dog) gaits and transitions: quadruped character control.

| | |
|---|---|
| Size | 0.50 h · 51 clips |
| Motion | Locomotion (gaits (walk, pace, trot, canter) with some sitting, standing and lying (not measured)) · tags: locomotion, gait, idle, sitting |
| Capture | optical-mocap |
| Data | bvh · 21 joints · MANN dog skeleton · 60 fps |
| Annotations | – |
| Licence | ❌ [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) · access: open |
| Links | [homepage](https://github.com/sebastianstarke/AI4Animation) · [download](https://starke-consult.de/AI4Animation/SIGGRAPH_2018/MotionCapture.zip) · [code](https://github.com/sebastianstarke/AI4Animation/tree/master/AI4Animation/SIGGRAPH_2018) · [paper](https://github.com/sebastianstarke/AI4Animation/blob/master/Media/SIGGRAPH_2018/Paper.pdf) |
| Paper | Mode-Adaptive Neural Networks for Quadruped Motion Control (SIGGRAPH 2018) |
| Viewer | [10 examples](https://myshi-motion-viewer.static.hf.space/#mann-dog/d1-010-kan01-004) |

<sub>Size: About 30 minutes of unstructured dog capture per the paper; 51 BVH takes in MotionCapture.zip, counted from the release.</sub>

Unstructured capture of a dog on flat ground: walk, pace, trot and canter plus sitting, standing, idling, lying and jumping. The raw BVH carries no labels; the paper's motion labels are assigned in the AI4Animation Unity tools.

<details><summary>BibTeX</summary>

```bibtex
@article{zhang2018mann,
  author = {Zhang, He and Starke, Sebastian and Komura, Taku and Saito, Jun},
  title = {Mode-Adaptive Neural Networks for Quadruped Motion Control},
  journal = {ACM Transactions on Graphics},
  volume = {37},
  number = {4},
  pages = {145},
  year = {2018}
}
```

</details>
