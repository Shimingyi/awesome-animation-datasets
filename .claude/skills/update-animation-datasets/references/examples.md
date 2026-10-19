# Viewer examples: pick, bake, render

Full format and options: `docs/EXAMPLES.md` and the docstring of `tools/examples/spec.py`.

## Where clips come from

- **The vault** (`config.local.yaml` → `vault`): every dataset the maintainer ingested as npz
  (`<vault>/processed/<folder>/_catalog.json`). BVH, SMPL/SMPL-X npz (mesh shown via the body model) and
  HumanML3D-style joint positions all work. New raw data → `python -m tools.vault.ingest <src> <folder> --root <vault>`.
- **Named folders** (`config.local.yaml` → `sources`), e.g. `codec_assets` = the Animation Codec demo's cropped BVHs +
  fitted rigged GLBs (Truebones animals, Objaverse objects, Unitree robots, the Geno character).
- **Rigged FBX/GLB with their own animation**: an item with `anim: <file>` (+ optional `action:`) is exported to BVH by
  Blender (`tools/examples/blender/anim2bvh.py`) and its mesh converted to a Draco GLB with textures
  (`blender/fbx2glb.py`).

## Steps

```bash
# 1. choose clips (deterministic spread over the dataset's groups; hand-picked items stay first)
python -m tools.examples.pick <id> --vault-dir <vault folder> [--collection <sub folder>]
#    or write items by hand in data/examples/<id>.yaml (bvh / mesh / anim / label / credit)
# 2. bake: crop to the middle 12 s, resample to <= 30 fps, write viewer/examples/<id>/ + manifest.json
python -m tools.examples.bake <id> --force
# 3. thumbnails (headless Chrome renders the viewer itself) + contact sheet of all examples
python -m tools.examples.thumbs <id> --force --sheet      # -> build/contact_sheet.png
```

More sources:

- **SMPL / SMPL-H / SMPL-X npz** (AMASS layout): `smpl: <file>` (a list = performers of one take). Prefer the dataset's
  own body-model files over a BVH conversion whenever the release has them.
- **Joint positions only** (HumanML3D-style 22 SMPL joints): fit SMPL with
  `python -m tools.examples.joints2smpl <vault clip ids> --out build/fitted/<id>` and use `smpl:` items from the
  `fitted` source; say "SMPL fitted to the released joints" in the spec's `note` (the dataset does not ship SMPL).
- **Huge archives on the Hub**: `python -m tools.examples.hf_stream <repo> <archive.tar.gz> <out> --n 10 --meta <csv>`
  streams only until 10 clips (one per category) are found.
- **A mesh with its own skeleton** (e.g. the AI4Animation wolf for the MANN dog): `mesh:` + `mesh_source:` +
  `bone_map: {clip joint: mesh bone}`; the viewer aims each mapped bone along its clip bone (`rig.js` prepareAimRig).

Multi-performer takes (two actors, two hands): `clip:` / `bvh:` as a list, or `pick.together: true` (one example per
vault collection). They share one scale and floor and are shown together.

## Checking them (always look)

Open `build/contact_sheet.png` (one row per dataset, middle frame of each example). Then fix:

| Symptom | Fix |
|---|---|
| lying down / upside down / palms sideways | `up: +z` (or `-z`, `+x`, `-x`, `-y`) at the top of `data/examples/<id>.yaml` (or per item), re-bake. Try the viewer's **up** selector first to find the right value. |
| a long stray bone from the origin | the root stays put while a child carries the motion: the viewer hides such roots automatically; if not, check the BVH |
| bones twice as long | Blender-style absolute position channels; `bake.relative_positions` fixes them — check it triggered |
| a T-pose first frame | leading rest frames are skipped automatically (`bake.lead_rest_frames`) |
| mesh missing ("mesh not shown: ...") | the GLB's bone names / bind pose do not match the clip (`viewer/js/rig.js prepareRig`): export the clip from the same FBX (`anim:` item) |
| floating / sinking | the **on floor** toggle puts the clip's lowest point (capsules / mesh included) on the floor; it is on by default |

Thumbnails are rendered by `viewer/index.html?thumb=<example id>` (window.__ready / __frame) — a viewer change shows up
in the cards only after `thumbs --force`.
