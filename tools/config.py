"""Machine-specific paths, read from config.local.yaml at the repo root (gitignored; copy config.example.yaml).

Every key can be overridden by an environment variable AAD_<KEY> (e.g. AAD_VAULT=/data/vault).
"""
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULTS = {
    'vault': os.path.join(REPO, 'vault'),                                     # npz motion vault (tools/vault/ingest.py)
    'sources': {},                                                            # name -> folder, used by data/examples/*.yaml
    'smpl_models': None,                                                      # folder with SMPL_*.pkl / SMPLX_*.npz
    'blender': '/Applications/Blender.app/Contents/MacOS/Blender',
    'chrome': '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    'hf_space': None,                                                         # Hugging Face Space of the viewer (user/name)
    'deploy_host': None,                                                      # ssh host of the playground server (mirror)
    'deploy_path': '/srv/playground/motion_viewer',
}
_cache = None


def load():
    global _cache
    if _cache is None:
        cfg = dict(DEFAULTS)
        p = os.path.join(REPO, 'config.local.yaml')
        if os.path.exists(p):
            import yaml
            with open(p) as f:
                cfg.update({k: v for k, v in (yaml.safe_load(f) or {}).items() if v is not None})
        for k in DEFAULTS:
            env = os.environ.get('AAD_' + k.upper())
            if env and not isinstance(DEFAULTS[k], dict):
                cfg[k] = env
        _cache = cfg
    return _cache


def get(key):
    return load().get(key)


def source(name):
    """Folder of a named example source (config.local.yaml `sources`). 'vault' is the vault itself."""
    if name == 'vault':
        return get('vault')
    s = load()['sources'].get(name)
    if not s:
        raise KeyError(f'example source "{name}" is not configured: add it under `sources:` in config.local.yaml')
    return os.path.expanduser(s)
