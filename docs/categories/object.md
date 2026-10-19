# 🧸 Objects & creatures

<sub>Generated from `data/datasets/*.yaml` by `python -m tools.readme` — edit the yaml, not this page.</sub>

Rigged and animated 3D assets of any kind (props, toys, plants, fantasy creatures, vehicles).

| Dataset | Hours | Clips | Data | Links | Viewer | Preview |
|---|--:|--:|---|---|:-:|---|
| [**Objaverse-XL Rigged & Animated**](../categories/object.md#objaverse-xl-rigged-animated)<br><sub>Thousands of rigged, animated 3D assets of any shape: rigging and any-skeleton motion.</sub> | 21.0 | 16k | glb | [home](https://huggingface.co/datasets/Linzhan/Objaverse-XL-Rigged-Animated)<br>[code](https://github.com/Friedrich-M/UniMate/tree/main/data_process)<br>[paper](https://arxiv.org/abs/2609.05415) | [▶](https://myshi-motion-viewer.static.hf.space/#objaverse-xl-rigged-animated/hummingbird-hover) | <a href="https://myshi-motion-viewer.static.hf.space/#objaverse-xl-rigged-animated/hummingbird-hover"><img src="../assets/thumbs/objaverse-xl-rigged-animated.webp" width="607" height="200" alt="Objaverse-XL Rigged & Animated examples"></a> |

## Objaverse-XL Rigged & Animated

<a href="https://myshi-motion-viewer.static.hf.space/#objaverse-xl-rigged-animated/hummingbird-hover"><img src="../assets/thumbs/objaverse-xl-rigged-animated.webp" width="486" height="160" alt="Objaverse-XL Rigged & Animated examples"></a>

**Objaverse-XL Rigged & Animated Subset** (2026)

*Good for:* Thousands of rigged, animated 3D assets of any shape: rigging and any-skeleton motion.

| | |
|---|---|
| Size | 21.0 h · 16,190 clips · 7373 subjects |
| Motion | Unclassified |
| Capture | mixed |
| Data | glb · per-asset glTF skins (3 to 344 joints, median 44) |
| Annotations | – |
| Licence | ❔ [Per-asset upstream licences (metadata ODC-BY 1.0)](https://huggingface.co/datasets/Linzhan/Objaverse-XL-Rigged-Animated/blob/main/NOTICE.md) · access: open |
| Links | [homepage](https://huggingface.co/datasets/Linzhan/Objaverse-XL-Rigged-Animated) · [code](https://github.com/Friedrich-M/UniMate/tree/main/data_process) · [paper](https://arxiv.org/abs/2609.05415) |
| Paper | UniMate: One Unified Model to Animate Diverse Skeletons (SIGGRAPH Asia 2026) |
| Viewer | [10 examples](https://myshi-motion-viewer.static.hf.space/#objaverse-xl-rigged-animated/hummingbird-hover) |

<sub>Size: 7,373 assets with 16,190 animation clips (about 21.0 h); 5,615 clips animate only non-joint nodes</sub>

Every Objaverse / Objaverse-XL asset that carries both a skin with joints and at least one animation clip, shipped unmodified as GLB with per-asset and per-clip metadata tables. Characters and articulated objects are mixed; the processed, text-captioned release built from it is UniML3D.

<details><summary>BibTeX</summary>

```bibtex
@article{mou2026unimate,
  title   = {UniMate: One Unified Model to Animate Diverse Skeletons},
  author  = {Mou, Linzhan and Lei, Jiahui and Dou, Zhiyang and Cai, Chenyue and Song, Chaoyue and Finkelstein, Adam and Rusinkiewicz, Szymon},
  journal = {arXiv preprint arXiv:2609.05415},
  year    = {2026}
}
```

</details>
