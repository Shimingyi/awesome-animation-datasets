# ✋ Hands

<sub>Generated from `data/datasets/*.yaml` by `python -m tools.readme` — edit the yaml, not this page.</sub>

Finger and hand motion (piano, manipulation, sign).

| Dataset | Hours | Clips | Data | Links | Viewer | Preview |
|---|--:|--:|---|---|:-:|---|
| [**FürElise**](../categories/hands.md#for-elise)<br><sub>Piano-playing hand motion with MIDI: music-to-hand-motion synthesis.</sub> | 10.0 | 153 | mano<br>joints<br>midi | [home](https://for-elise.github.io/)<br>[data](https://huggingface.co/datasets/rcwang/for_elise)<br>[paper](https://arxiv.org/abs/2410.05791) | [▶](https://myshi-motion-viewer.static.hf.space/#for-elise/000) | <a href="https://myshi-motion-viewer.static.hf.space/#for-elise/000"><img src="../assets/thumbs/for-elise.webp" width="427" height="140" alt="FürElise examples"></a> |

## FürElise

<a href="https://myshi-motion-viewer.static.hf.space/#for-elise/000"><img src="../assets/thumbs/for-elise.webp" width="488" height="160" alt="FürElise examples"></a>

**FürElise: piano performance hand motion dataset** (2024)

*Good for:* Piano-playing hand motion with MIDI: music-to-hand-motion synthesis.

| | |
|---|---|
| Size | 10.0 h · 153 clips · 15 subjects |
| Motion | Music performance · tags: music, piano |
| Capture | video |
| Data | mano, joints, midi · 21 joints · MANO (21 joints per hand, both hands) · 59.94 fps |
| Annotations | music, audio |
| Licence | ❌ [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) · access: open |
| Links | [homepage](https://for-elise.github.io/) · [download](https://huggingface.co/datasets/rcwang/for_elise) · [paper](https://arxiv.org/abs/2410.05791) |
| Paper | FürElise: Capturing and Physically Synthesizing Hand Motions of Piano Performance (SIGGRAPH Asia 2024) |
| Viewer | [10 examples](https://myshi-motion-viewer.static.hf.space/#for-elise/000) |

<sub>Size: 153 classical piano pieces played by 15 elite-level pianists, about 10 h, with synchronized MIDI key presses and audio synthesized from the MIDI.</sub>

Two-hand piano performance motion reconstructed markerlessly from multi-view video and refined with key-press data from a Disklavier piano. Each piece comes with MANO parameters, 3D joints, the recorded MIDI and audio.

<details><summary>BibTeX</summary>

```bibtex
@inproceedings{wang2024piano,
  title = {FürElise: Capturing and Physically Synthesizing Hand Motions of Piano Performance},
  author = {Ruocheng Wang and Pei Xu and Haochen Shi and Elizabeth Schumann and C. Karen Liu},
  booktitle = {SIGGRAPH Asia 2024},
  year = {2024}
}
```

</details>
