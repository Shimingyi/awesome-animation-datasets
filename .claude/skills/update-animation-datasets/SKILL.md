---
name: update-animation-datasets
description: Maintain the awesome-animation-datasets repo — add or fix a dataset entry, regenerate the README statistics / charts / category pages, pick and bake the 10 viewer examples of a dataset (vault clips, BVH, rigged FBX/GLB meshes, SMPL), render thumbnails, preview the Motion Viewer locally and deploy it (Hugging Face Space myshi/motion-viewer, mirror playground.rubbly.cn/motion_viewer). Use for any request to add, update, remove, re-render or publish datasets or viewer examples in this repo.
---

# Updating awesome-animation-datasets

Everything is generated from yaml. Never hand-edit generated output (README blocks between `<!-- BEGIN/END -->`,
`docs/categories/*.md`, `docs/assets/charts/*`, `docs/assets/thumbs/*`, `viewer/examples/`).

```
data/datasets/<id>.yaml   one dataset (schema: data/SCHEMA.md, ids: data/taxonomy.yaml)      ← you edit
data/examples/<id>.yaml   its viewer examples (format: tools/examples/spec.py docstring)      ← you edit
tools/                    python -m tools.<cmd>   (run from the repo root)
viewer/                   static Motion Viewer; viewer/examples/ is baked, gitignored
config.local.yaml         machine paths: vault, sources, blender, chrome, deploy host       (gitignored)
```

## Hard rules

- Some local vault folders are private and must never appear anywhere in this repo (yaml, docs, code, commit
  messages). Only ever reference vault folders that a `data/examples/*.yaml` already uses or that the user names.
  Pick examples by allow-list (`pick.vault`), never by listing the vault.
- Statistics come from the dataset's paper / homepage / card. If you count yourself, say so in `stats_note`. Never guess;
  leave a number out instead.
- A dataset that re-labels / re-targets another one gets `derived_from` (listed, not added to the hours). Other releases
  of the same motion (retargets, re-solves, other rigs) go under `variants` of the original, not as new entries.
- One `subject` per dataset and a `content` composition (measured with `tools/composition.py` where possible), from `data/taxonomy.yaml`. If a new id is really needed, add it to the
  taxonomy in the same change and say so.
- Examples are short excerpts for research reference (non-commercial notice in the viewer footer); max 10 per dataset.

## Task recipes

| Task | Steps |
|---|---|
| Add / fix a dataset | [references/add-dataset.md](references/add-dataset.md) |
| Viewer examples: pick, bake, meshes, up axis, thumbnails | [references/examples.md](references/examples.md) |
| Quality review (recommended / usable / caution) | [references/review.md](references/review.md) |
| Preview locally, deploy the viewer (HF Space + mirror) | [references/deploy.md](references/deploy.md) |

## The loop (every change ends with this)

```bash
python -m tools.validate                 # registry + example specs + generated pages up to date
python -m tools.examples.bake <id>       # only if examples changed (add --thumbs to render the cards)
python -m tools.readme                   # README stats/tables, charts, docs/categories/*.md
python -m tools.banner                   # README header: new text + date over the saved tile wall (--background rebuilds it, --social the still card)
python -m tools.validate                 # must print "... ok" and "README and docs are up to date"
```

A new dataset gets an announcement issue once it is deployed: `python -m tools.announce <id>` drafts it
(build/announce/<id>.md: summary, numbers, verdict, its 10 previews), `--post` opens it with gh and adds the README
News line that links to it (then `python -m tools.readme`). Post only after the user has seen the draft.

Then look at the result: open `build/contact_sheet.png` (after `python -m tools.examples.thumbs --sheet`) for the
examples, and the README in a markdown preview. Report what changed, what numbers came from where, and anything you
could not verify.
