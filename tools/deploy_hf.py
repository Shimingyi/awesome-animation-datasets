"""Publish the Motion Viewer (viewer/ incl. the baked examples) as a static Hugging Face Space — the main public link.

    python -m tools.deploy_hf [--space user/name] [--dry-run]

The Space id comes from --space, config.local.yaml `hf_space` or $AAD_HF_SPACE; the login from `hf auth login`.
viewer/ is staged into build/hf_space/ with the Space card (README.md) and uploaded in one go; files that no longer
exist locally are deleted from the Space. playground.rubbly.cn/motion_viewer is the mirror (tools/deploy.sh).
"""
import argparse
import os
import shutil

from . import config, registry, stats

STAGE = os.path.join(config.REPO, 'build', 'hf_space')
GITHUB = 'https://github.com/Shimingyi/awesome-animation-datasets'


def space_url(space):
    """the Space's own domain (the huggingface.co/spaces page wraps it in an iframe, which drops #deep-links)"""
    user, name = space.split('/')
    return f"https://{user.lower()}-{name.lower().replace('_', '-').replace('.', '-')}.static.hf.space/"


def hub_datasets(check=True):
    """the registry's datasets that live on the Hub: listed in the card, the Space then shows on their pages"""
    import re
    ids = sorted({m for d in registry.datasets() for m in re.findall(r'huggingface\.co/datasets/([\w.-]+/[\w.-]+)', str(d))})
    if not check:
        return ids
    from huggingface_hub import HfApi
    api, ok = HfApi(), []
    for i in ids:                                            # a moved or deleted repo would only be a dead link
        try:
            api.dataset_info(i); ok.append(i)
        except Exception:
            print('not on the Hub, left out of the card:', i)
    return ok


def readme_parts():
    """the intro paragraph and the BibTeX, taken from the README so the card follows its wording"""
    import re
    t = open(os.path.join(config.REPO, 'README.md')).read()
    head = t[:t.index('<!-- BEGIN HERO -->')]
    intro = next(p.strip() for p in head.split('\n\n') if p.strip() and not p.lstrip().startswith(('<', '**')))
    return intro, re.search(r'```bibtex\n.*?```', t, re.S).group(0)


def card(space, datasets=()):
    s, (intro, bib) = stats.compute(), readme_parts()
    user, name = space.split('/')
    raw = GITHUB.replace('github.com', 'raw.githubusercontent.com') + '/main/docs/assets'
    hub = ''.join(f'\n  - {d}' for d in datasets)
    return f"""---
title: Awesome Animation Datasets
emoji: 🕺
colorFrom: blue
colorTo: gray
sdk: static
app_file: index.html
pinned: true
license: mit
short_description: 3D previews of {s['datasets']} motion datasets, quality-checked
thumbnail: https://huggingface.co/spaces/{space}/resolve/main/thumbnail.png
tags:
  - motion-capture
  - human-motion
  - animation
  - character-animation
  - motion-generation
  - smpl
  - smpl-x
  - bvh
  - mocap
  - 3d
  - threejs
  - awesome-list
datasets:{hub}
---

<img src="{raw}/banner.webp" width="100%" alt="Awesome Animation Datasets">

{intro}

**[▶ Open the viewer full screen]({space_url(space)})** · **[The list on GitHub]({GITHUB})**

- **{s['datasets']} datasets, {s['hours']:,.0f} hours of motion**: human bodies, hands, two-person interaction, animals, rigged
  objects and robots.
- **10 example clips per dataset**, played in the browser as skeletons, SMPL / SMPL-X bodies or textured rigged meshes.
  No download, no conversion, no Blender.
- **Numbers and quality checks**: hours, clips and formats per dataset (from the paper or measured), and quality red
  flags (physics, floating, foot sliding, jitter, self-penetration) measured on the data itself, on
  [GitHub]({GITHUB}#quality-red-flags).
- Deep links: `{space_url(space)}#<dataset>/<example>`.

The examples are a few seconds of a handful of clips per dataset, shown for non-commercial research and reference only.
Every dataset remains under its own licence — get it from its source (links in the viewer and on GitHub). Dataset owners
who want their examples removed: please open an issue on [GitHub]({GITHUB}).

## Citation

{bib}
"""


def stage(space, datasets=()):
    src = os.path.join(config.REPO, 'viewer')
    if not os.path.exists(os.path.join(src, 'examples', 'manifest.json')):
        raise SystemExit('no baked examples: run python -m tools.examples.bake --thumbs first')
    if os.path.isdir(STAGE):
        shutil.rmtree(STAGE)
    shutil.copytree(src, STAGE, ignore=shutil.ignore_patterns('.DS_Store', '*.tmp'))
    with open(os.path.join(STAGE, 'README.md'), 'w') as f:
        f.write(card(space, datasets))
    shutil.copy(os.path.join(config.REPO, 'docs', 'assets', 'social.png'), os.path.join(STAGE, 'thumbnail.png'))
    url, og = space_url(space), os.path.join(STAGE, 'index.html')   # link previews (X, Slack, ...) for the direct domain
    t = open(og).read()
    meta = (f'<meta property="og:title" content="Awesome Animation Datasets · Motion Viewer">\n'
            f'<meta property="og:description" content="3D previews of every motion dataset worth knowing, with hours and quality red flags.">\n'
            f'<meta property="og:image" content="{url}thumbnail.png">\n<meta property="og:url" content="{url}">\n'
            f'<meta name="twitter:card" content="summary_large_image">\n')
    if '<meta name="viewport"' not in t:
        raise SystemExit('cannot add link-preview tags to index.html')
    open(og, 'w').write(t.replace('<meta name="viewport"', meta + '<meta name="viewport"', 1))
    from .examples import spec
    held = {d['id'] for d in registry.datasets() if not spec.published(d['id'])}
    if held:                                                 # baked for local preview only (`publish: false` in the spec)
        import json
        mp = os.path.join(STAGE, 'examples', 'manifest.json')
        man = json.load(open(mp))
        for d in man['datasets']:
            if d['id'] in held:
                d['examples'] = []
        json.dump(man, open(mp, 'w'), separators=(',', ':'), ensure_ascii=False, default=str)
        for i in held:                                       # its clips and its card thumbnails
            shutil.rmtree(os.path.join(STAGE, 'examples', i), ignore_errors=True)
            shutil.rmtree(os.path.join(STAGE, 'examples', 'thumbs', i), ignore_errors=True)
        print('held back (publish: false):', ', '.join(sorted(held)))
    # version-stamp the scripts so browsers never mix a cached old module with a new page
    import hashlib
    v = hashlib.sha1(b''.join(open(os.path.join(STAGE, 'js', n), 'rb').read() for n in sorted(os.listdir(os.path.join(STAGE, 'js'))))).hexdigest()[:8]
    for rel, a, b in (('index.html', 'js/app.js"', f'js/app.js?v={v}"'), ('index.html', 'css/viewer.css"', f'css/viewer.css?v={v}"'),
                      ('js/app.js', "from './rig.js'", f"from './rig.js?v={v}'")):
        p = os.path.join(STAGE, rel)
        with open(p) as f:
            t = f.read()
        if a not in t:
            raise SystemExit(f'cannot version {rel}: {a} not found')
        with open(p, 'w') as f:
            f.write(t.replace(a, b))
    n = sum(len(fs) for _, _, fs in os.walk(STAGE))
    size = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(STAGE) for f in fs)
    return n, size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--space', default=config.get('hf_space'))
    ap.add_argument('--dry-run', action='store_true', help='stage build/hf_space/ only, upload nothing')
    a = ap.parse_args()
    if not a.space or '/' not in a.space:
        raise SystemExit('which Space? pass --space user/name or set hf_space in config.local.yaml')
    from . import validate
    import sys
    argv, sys.argv = sys.argv, [sys.argv[0]]
    validate.main()                                          # the registry must be valid and the pages current
    sys.argv = argv
    n, size = stage(a.space, hub_datasets(check=not a.dry_run))
    print(f'staged {n} files, {size / 1e6:.1f} MB -> {os.path.relpath(STAGE, config.REPO)}')
    if a.dry_run:
        return
    from huggingface_hub import HfApi
    api = HfApi()
    api.create_repo(a.space, repo_type='space', space_sdk='static', exist_ok=True)
    api.upload_folder(repo_id=a.space, repo_type='space', folder_path=STAGE, delete_patterns='*',
                      commit_message='Update the Motion Viewer from awesome-animation-datasets')
    print(f'https://huggingface.co/spaces/{a.space}\n{space_url(a.space)}')


if __name__ == '__main__':
    main()
