# Add or fix a dataset entry

1. **Find the facts** (web search; read the paper, the homepage / GitHub README / Hugging Face card, the licence file):
   full name, first public release year, paper title + venue + link, homepage / download / code links, licence name +
   URL + whether commercial use is allowed, access (open / registration / gated / paid), capture method, native fps,
   skeleton (joint count, rig / body model), size (hours, clips, subjects), annotations (text, audio, music, labels ...).
   Copy the official BibTeX verbatim when there is one.
2. **Write `data/datasets/<id>.yaml`** — field order and style as in `data/datasets/lafan1.yaml`; schema in
   `data/SCHEMA.md`. `id` = file name, lower case + digits + `-`.
   - `stats`: the dataset's own numbers. Our own count → say so in `stats_note` ("counted from the HF release").
   - `subject` (who moves) from `data/taxonomy.yaml`; `content` (what the motion is): if the data is in the vault, add a
     RULE to `tools/composition.py` and run `python -m tools.composition <id> --write` (shares measured from clip
     labels, weighted by duration); otherwise one id + a `content_note` saying where it comes from. Style, emotion and
     persona are `tags`, never a content type (stylized walking is locomotion).
   - SMPL support = `smpl` / `smplh` / `smplx` in `representation` (listed first in the README's Data column, a badge in the viewer).
   - Re-labelled / re-targeted data → `derived_from: [<source id>]`. Retargets of an existing entry → `variants:` there.
   - `good_for`: one line, "what is it good for" (shown under the name in every table).
   - `notes`: 1–2 neutral sentences: what it is, what makes it useful, caveats.
3. `python -m tools.validate` → fix every message.
4. `python -m tools.readme` → regenerates README tables/stats, charts and `docs/categories/<subject>.md`.
5. Optional: viewer examples ([examples.md](examples.md)).
6. Report a table: id | hours | clips | licence | commercial | stats source, plus every uncertainty.

Removing a dataset: delete `data/datasets/<id>.yaml` and `data/examples/<id>.yaml`, then
`rm -rf viewer/examples/<id> viewer/examples/thumbs/<id> docs/assets/thumbs/<id>.webp`, `python -m tools.examples.bake --manifest-only`,
`python -m tools.readme`.

Many datasets at once: split them over parallel agents (5–10 each), each writing only its own files, then run the
validator once and review the reports for conflicts (two agents must never own the same id).
