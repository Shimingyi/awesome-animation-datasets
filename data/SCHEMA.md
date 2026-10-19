# Dataset entry schema

One file per dataset: `data/datasets/<id>.yaml`. The file name (without `.yaml`) is the id. Everything in the README,
the category pages, the charts and the viewer is generated from these files. `python -m tools.validate` checks them.

```yaml
id: lafan1                       # = file name; lower case, digits, '-'
name: LAFAN1                     # short display name
full_name: Ubisoft La Forge Animation Dataset
good_for: "Long unedited takes with locomotion, fights and falls: in-betweening and motion matching."   # one line, shown in the tables
year: 2020                       # first public release
released: 2020-07                # optional: month of that release (arXiv month, Hugging Face repo, or venue)
subject: human-body              # data/taxonomy.yaml subjects   (exactly one)
content:                         # WHAT the motion is (data/taxonomy.yaml content): shares of the duration, or one id
  locomotion: 0.54               #   measured where clip labels allow: python -m tools.composition <id> --write
  combat: 0.28
  dance: 0.09
  general: 0.09                  #   general = unclassified
content_note: measured from the take names, weighted by duration   # where the shares come from
tags: [locomotion, combat, falling]   # data/taxonomy.yaml motion_tags (style, emotion, persona ... live here)
capture: optical-mocap           # data/taxonomy.yaml capture
representation: [bvh]            # what the files are: bvh, fbx, glb, smpl, smplh, smplx, joints, csv, c3d, npz, ...
skeleton:                        # optional
  joints: 22
  rig: Ubisoft LAFAN1            # free text: the rig / body model
fps: 30                          # native frame rate (number or list)
stats:                           # what the dataset contains (not what we converted)
  hours: 4.6
  clips: 77
  subjects: 5                    # performers / animals / assets, optional
stats_note: 77 takes of 5 actors  # optional, shown as a footnote
annotations: [action-labels]     # optional: text, audio, music, video, action-labels, style-labels, emotion, contacts, ...
license:
  name: CC BY-NC-ND 4.0
  url: https://creativecommons.org/licenses/by-nc-nd/4.0/
  commercial: false              # true / false / unknown
access: open                     # data/taxonomy.yaml access
links:
  homepage: https://...
  download: https://...          # optional
  code: https://...              # optional
  paper: https://...             # optional
paper:                           # optional
  title: Robust Motion In-betweening
  venue: SIGGRAPH 2020
citation: |                      # optional BibTeX
  @article{...}
variants:                        # optional: other releases of the SAME motion (retargets, re-solves, other rigs).
  - name: Geno LAFAN1            # Listed with the dataset, never counted twice in the statistics.
    url: https://theorangeduck.com/media/uploads/Geno/lafan1-resolved/bvh.zip
    note: re-solved onto Daniel Holden's Geno character
derived_from: [amass]            # optional: this dataset re-labels / re-cuts another one (its hours are not added
                                 # to the totals; the entry is still listed and counted as a dataset)
notes: >-                        # optional, one paragraph, shown on the category page
  ...
review:                          # optional: OUR quality judgement after inspecting the data (not the authors' claims)
  verdict: caution               # data/taxonomy.yaml review_verdicts: recommended | usable | caution
  issues: [jitter, foot-skating] # data/taxonomy.yaml review_issues
  note: >-                       # what we saw, one or two sentences
    ...
  subsets:                       # optional: a different verdict for part of the data (vault collection prefix)
    - match: HAA500/
      verdict: caution
  date: 2026-10-19
```

`caution` datasets leave their subject and form a category of their own, "Use with caution" (a README section with the
reason, `docs/categories/caution.md`, a viewer tab); the totals and charts count only the datasets above the bar.

Rules:

- **Statistics** come from the dataset's paper or homepage when they give them; otherwise from our own count of the
  release (say so in `stats_note`). Unknown numbers are left out, never guessed.
- `derived_from` datasets and `variants` are excluded from the hour/clip totals so nothing is counted twice.
- Viewer examples are configured separately in `data/examples/<id>.yaml` (see `docs/EXAMPLES.md`).
