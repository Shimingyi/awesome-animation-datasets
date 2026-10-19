# awesome-animation-datasets

A list of motion / animation datasets with generated statistics, and a static three.js Motion Viewer with 10 example
clips per dataset, published as the Hugging Face Space myshi/motion-viewer (mirror: playground.rubbly.cn/motion_viewer). For any change to datasets, examples, the README or the viewer deployment, use the
`update-animation-datasets` skill (`.claude/skills/update-animation-datasets/`).

- Source of truth: `data/datasets/*.yaml` (+ `data/taxonomy.yaml`, `data/examples/*.yaml`). Generated: README blocks,
  `docs/categories/`, `docs/assets/`, `viewer/examples/` (gitignored). Run `python -m tools.validate` before finishing.
- Machine paths are in `config.local.yaml` (gitignored); never write absolute local paths into tracked files.
- Some folders of the local motion vault are private: never list the vault or mention folders that no
  `data/examples/*.yaml` already uses.
- Viewer: `viewer/index.html` + `viewer/js/app.js` (players, UI) + `viewer/js/rig.js` (GLB rig fit). No build step;
  serve `viewer/` over http (`.claude/launch.json` → `viewer-static`), never as file://.
- Python style: compact, comments explain why; match the surrounding code.
