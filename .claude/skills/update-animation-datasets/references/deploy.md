# Preview and deploy the Motion Viewer

## Local preview

- Static (exactly what will be deployed): `python3 -m http.server 8781 --bind 127.0.0.1 --directory viewer` →
  <http://127.0.0.1:8781/> (`.claude/launch.json` has it as `viewer-static`). Never open `viewer/index.html` as a
  `file://` page: module imports and fetches fail there.
- Whole vault (local mode, every clip, download buttons): `python -m tools.vault.server --port 8766` → the same page finds
  `api/catalog` and switches to the vault tree. (Port 8765 may be taken by the Motion Vault app.)
- Debug from the browser console: `window.__viewer.players` (scale, floor, up axis, rig errors per clip).

## Deploy (only when the user asks)

The main home is a static Hugging Face Space (`hf_space` in `config.local.yaml`, login: `hf auth whoami`):

```bash
python -m tools.deploy_hf              # validate, stage viewer/ + Space card into build/hf_space/, upload, delete stale files
python -m tools.deploy_hf --dry-run    # stage only
```

Check <https://huggingface.co/spaces/myshi/motion-viewer> and the direct domain
<https://myshi-motion-viewer.static.hf.space/> (the README links there: the Spaces page iframe drops `#` deep links).

Mirror: `playground.rubbly.cn` is Caddy on the maintainer's server (ssh host and path: `deploy_host` / `deploy_path` in
`config.local.yaml`), one routing file per app in `/etc/caddy/apps/`. The viewer is static, so no service is needed:

```bash
tools/deploy.sh            # rsync viewer/ (with examples/) to <deploy_host>:<deploy_path>, then print the Caddy snippet status
```

First time only, on the VM: copy `deploy/motion_viewer.caddy` to `/etc/caddy/apps/motion_viewer.caddy` and
`sudo systemctl reload caddy`. Deploying publishes data: confirm with the user
first, and check the result at <https://playground.rubbly.cn/motion_viewer/>.
