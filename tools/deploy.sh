#!/usr/bin/env bash
# Publish the static Motion Viewer (viewer/ incl. the baked viewer/examples/) to the playground server.
#
#   tools/deploy.sh [--dry-run]
#
# Host and path come from config.local.yaml (deploy_host, deploy_path) or AAD_DEPLOY_HOST / AAD_DEPLOY_PATH.
# First deploy only: install deploy/motion_viewer.caddy as /etc/caddy/apps/motion_viewer.caddy on the server and
# `sudo systemctl reload caddy`.
set -euo pipefail
cd "$(dirname "$0")/.."
read -r HOST DEST < <(python3 -c "from tools import config; print(config.get('deploy_host') or '', config.get('deploy_path'))")
[ -n "$HOST" ] || { echo "set deploy_host in config.local.yaml"; exit 1; }
[ -f viewer/examples/manifest.json ] || { echo "no baked examples: run python -m tools.examples.bake --thumbs"; exit 1; }
python3 -m tools.validate
DRY=${1:-}
echo "== rsync viewer/ -> $HOST:$DEST"
ssh "$HOST" "mkdir -p '$DEST'"
rsync -az --delete ${DRY:+--dry-run} --exclude '.DS_Store' viewer/ "$HOST:$DEST/"
if ssh "$HOST" "test -f /etc/caddy/apps/motion_viewer.caddy"; then echo "caddy route: installed"
else echo "caddy route missing: scp deploy/motion_viewer.caddy $HOST:/tmp/ && ssh $HOST 'sudo mv /tmp/motion_viewer.caddy /etc/caddy/apps/ && sudo systemctl reload caddy'"; fi
echo "== https://playground.rubbly.cn/motion_viewer/"
