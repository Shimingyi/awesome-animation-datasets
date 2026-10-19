# Viewer examples

The [Motion Viewer](https://huggingface.co/spaces/myshi/motion-viewer) shows up to 10 short clips per dataset. They are
*baked* from local copies of the data by the maintainers; contributors only need the dataset yaml.

## Configuration: `data/examples/<dataset id>.yaml`

```yaml
dataset: lafan1
up: +y                 # optional: which axis of the data points up (+y default, +z, -z, +x, -x, -y); also per item
max_seconds: 12        # optional: longer clips are cut to their middle part
note: rendered on the Geno character      # optional, shown with the examples
publish: false         # optional: bake for local preview only; tools.deploy_hf leaves these examples out
pick:                  # optional: how `python -m tools.examples.pick` chooses clips from the local vault
  vault: <vault folder>
  collection: bvh      # only this sub-folder
  exclude: [_mirror]   # skip ids containing these
  together: false      # one example per collection, its clips played together (two actors, two hands)
  n: 10
items:                 # what is baked, in order
  - source: vault                      # a clip of the local vault (BVH, SMPL / SMPL-X npz, joint positions)
    clip: <vault folder>/<clip id>     # a list = several performers of one take
    label: Aiming
  - source: codec_assets               # a folder named in config.local.yaml `sources`
    bvh: clips/geno-fight.bvh          # a list = several performers of one take
    mesh: meshes/a673559ab3a3.glb      # optional rigged GLB / FBX, driven by the clip (bones matched by name)
    label: Fight
    credit: "“Model” by Author (CC-BY), https://…"
  - source: demo_src
    anim: truebones/Horse/Horse.fbx    # an animated FBX / GLB: clip exported from its action, mesh from the same file
    action: Horse|run                  # optional: which action
  - source: humoto
    scene: x/x.glb                     # a character with animated objects (HUMOTO): the objects play along as props
```

## Commands

```bash
python -m tools.examples.pick <id> --vault-dir <folder>      # fill `items` from the vault
python -m tools.examples.bake [<id> ...] [--force]           # -> viewer/examples/ (gitignored) + docs/assets/examples.json
python -m tools.examples.thumbs [<id> ...] [--force] --sheet # card thumbnails + docs/assets/thumbs + build/contact_sheet.png
python -m tools.readme                                       # README / category pages pick up the new examples
```

Baking crops each clip to its middle `max_seconds`, resamples to at most 30 fps, skips a leading T-pose frame, makes
Blender-style absolute position channels relative, and writes per clip a JSON skeleton + float32 motion (+ the SMPL
body or a shared Draco GLB). Machine paths (vault, sources, Blender, Chrome) live in `config.local.yaml`
(see `config.example.yaml`).
