# Quality review

The verdict is the maintainer's judgement, so **only record a verdict the user gave you** (or confirmed after you showed
them the evidence). You may prepare the evidence: open the dataset's examples in the viewer (capsules / mesh, on floor,
trajectory on) and note what you see.

```yaml
# data/datasets/<id>.yaml
review:
  verdict: caution                           # recommended | usable | caution   (data/taxonomy.yaml review_verdicts)
  issues: [jitter, foot-skating, penetration]   # data/taxonomy.yaml review_issues; add a new id there if none fits
  note: >-
    One or two sentences: what is wrong, how widespread, which part of the data.
  subsets:                                   # optional: part of the data differs (vault collection prefix)
    - match: idea400/
      verdict: usable
  date: 2026-10-19
```

Then `python -m tools.examples.bake --manifest-only` (the viewer reads verdicts from the manifest),
`python -m tools.readme`, `python -m tools.validate`.

Effects: `caution` → the dataset leaves its subject for the "Use with caution" category: its own README section with the
reason, `docs/categories/caution.md`, a viewer tab (not in "All"); totals and charts leave it out (headline mentions it).
`recommended` → ⭐. No review → listed normally as unreviewed.

## Quality red flags (numbers)

`python -m tools.quality [ids]` measures every human dataset's viewer examples (full length) for gravity tilt, jump
gravity, physics residual, floating, foot sliding, jitter, joint range and self-penetration, writes
`docs/assets/quality.json`, and `python -m tools.readme` renders the README's "Quality red flags" table from it. Run it
after adding a dataset or changing its examples. Flags are a prompt to look, not a verdict: the caution category stays
the maintainer's call. Known false alarms: in-place root motion, uneven terrain, keyframed animation, unseen chairs/beds.
