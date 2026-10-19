"""data/examples/<dataset>.yaml: which clips the online viewer shows for a dataset (see docs/EXAMPLES.md).

    dataset: lafan1
    max_seconds: 12                 # optional, default MAX_SECONDS: longer clips are cut to their middle part
    up: +z                          # optional: which data axis points up (+y default, +z, -z, +x, -x, -y; also per item)
    note: rendered on Geno          # optional, shown with the examples
    default: true                   # optional: the viewer opens on this dataset (one dataset only)
    publish: false                  # optional: baked for local preview, held back by tools.deploy_hf
    pick:                           # optional: how `python -m tools.examples.pick` fills `items` from the vault
      vault: <vault dataset dir>    #   processed/<dir>/_catalog.json
      collection: bvh               #   only clips of this collection (or below it), optional
      exclude: [__mirror]           #   skip clip ids containing any of these, optional
      together: false               #   true: one example per collection, its clips shown together (both hands, both actors)
      n: 10
    items:                          # what is baked, in order (at most N_EXAMPLES)
      - source: vault               # a clip of the vault (BVH npz, SMPL npz or joint positions)
        clip: <vault dir>/<clip id>   #   or a list of clip ids = performers of one take, shown together
        label: Aiming 1             # optional, default: the clip name
      - source: hf_motionpersona    # an SMPL / SMPL-H / SMPL-X npz (AMASS layout: poses, trans, betas, gender, frame rate)
        smpl: smpl_skeleton/smpl/p03/p03_neutral_fw.npz
      - source: codec_assets        # a named folder from config.local.yaml `sources`
        bvh: clips/geno-fight.bvh   #   one BVH, or a list = the performers of one take (shown together)
        mesh: meshes/a673559ab3a3.glb   # optional rigged GLB (or FBX, converted with Blender) driven by the clip
        mesh_source: local_assets   # optional: the mesh lives in another source folder
        bone_map: {Hips: Becken}    # optional: clip joint -> mesh bone when the mesh has its own skeleton (aim retarget)
        label: Fight
        credit: "“Model” by Author (CC-BY), https://..."   # optional, shown under the viewer
      - source: humoto              # a character + animated objects (glTF / FBX): blender/props2clip.py splits it into the
        scene: x/x.glb              #   character (BVH + rigged GLB) and props (meshes + a 4x4 per frame, moved with the take)
"""
import glob
import os

import yaml

from .. import config

EXAMPLES_DIR = os.path.join(config.REPO, 'data', 'examples')
N_EXAMPLES = 10
MAX_SECONDS = 12.0


def path(ds_id):
    return os.path.join(EXAMPLES_DIR, f'{ds_id}.yaml')


def load(ds_id):
    p = path(ds_id)
    if not os.path.exists(p):
        return None
    with open(p) as f:
        s = yaml.safe_load(f) or {}
    s.setdefault('dataset', ds_id)
    s.setdefault('items', [])
    s.setdefault('note', '')
    return s


def published(ds_id):
    """False when the spec says `publish: false`: baked for local preview, kept out of the Space and the README"""
    s = load(ds_id)
    return not s or s.get('publish', True) is not False


def save(spec):
    with open(path(spec['dataset']), 'w') as f:
        yaml.safe_dump(spec, f, sort_keys=False, allow_unicode=True, width=120)


def all_ids():
    return sorted(os.path.basename(p)[:-5] for p in glob.glob(os.path.join(EXAMPLES_DIR, '*.yaml')))
