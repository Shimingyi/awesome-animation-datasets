"""Choose a dataset's viewer examples from the vault and write them into data/examples/<id>.yaml (`items`).

    python -m tools.examples.pick <id> [--vault-dir <dir>] [--collection <prefix>] [-n 10] [--replace]

Deterministic: the clips are spread over the dataset's groups (style, subject, take, ... whatever the vault's
catalog groups by), in catalog order, taking from each group the clip whose length is closest to the group's median;
clips shorter than MIN_SECONDS are skipped. Existing `items` are kept unless --replace (hand-picked items stay first).
"""
import argparse
import json
import os

from .. import config
from . import spec

MIN_SECONDS = 2.0


def candidates(vault_dir, collection=None, exclude=()):
    p = os.path.join(config.get('vault'), 'processed', vault_dir, '_catalog.json')
    with open(p) as f:
        cat = json.load(f)
    col = lambda c: str(c.get('collection', ''))  # noqa: E731
    return [c for c in cat['clips'] if c.get('ok', True) and c.get('duration', 0) >= MIN_SECONDS
            and (not collection or col(c) == collection or col(c).startswith(collection + '/'))
            and not any(x in c['id'] for x in exclude)]


def takes(clips):
    """clips of one collection shown together (the performers / hands of one take): one pseudo-clip per collection"""
    out = {}
    for c in clips:
        out.setdefault(c.get('collection', ''), []).append(c)
    return [dict(id=[c['id'] for c in cs], name=k or cs[0]['name'], collection='', group=k, duration=min(c['duration'] for c in cs))
            for k, cs in out.items()]


def choose(clips, n):
    groups = {}
    for c in clips:
        groups.setdefault((c.get('collection', ''), c.get('group', '')), []).append(c)
    keys = list(groups)
    if len(keys) >= n:                                    # n groups evenly spread over the catalog, one clip each
        keys = [keys[round(i * (len(keys) - 1) / max(1, n - 1))] for i in range(n)]
        take = {k: 1 for k in keys}
    else:                                                 # fewer groups than n: several clips per group
        take = {k: n // len(keys) + (1 if i < n % len(keys) else 0) for i, k in enumerate(keys)}
    out = []
    for k in keys:
        g = groups[k]
        med = sorted(c['duration'] for c in g)[len(g) // 2]
        ranked = sorted(g, key=lambda c: abs(c['duration'] - med))
        step = max(1, len(ranked) // max(1, take[k]))
        out += ranked[::step][:take[k]]
    return out[:n]


def label_of(c):
    return str(c['name']).replace('_', ' ')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('id')
    ap.add_argument('--vault-dir', help='vault dataset folder (default: pick.vault in the yaml)')
    ap.add_argument('--collection', help='only clips whose collection starts with this')
    ap.add_argument('-n', type=int, default=spec.N_EXAMPLES)
    ap.add_argument('--replace', action='store_true', help='drop the current items first')
    a = ap.parse_args()
    s = spec.load(a.id) or dict(dataset=a.id, items=[])
    pk = s.setdefault('pick', {})
    if a.vault_dir:
        pk['vault'] = a.vault_dir
    if a.collection is not None:
        pk['collection'] = a.collection
    pk.setdefault('n', a.n)
    if not pk.get('vault'):
        raise SystemExit('which vault folder? pass --vault-dir (it is remembered in the yaml)')
    items = [] if a.replace else list(s['items'])
    have = {str(i.get('clip')) for i in items}
    need = pk['n'] - len(items)
    if need > 0:
        cands = candidates(pk['vault'], pk.get('collection'), pk.get('exclude') or ())
        if pk.get('together'):
            cands = takes(cands)
        full = lambda cid: [f"{pk['vault']}/{x}" for x in cid] if isinstance(cid, list) else f"{pk['vault']}/{cid}"  # noqa: E731
        for c in choose([c for c in cands if str(full(c['id'])) not in have], need):
            items.append(dict(source='vault', clip=full(c['id']), label=label_of(c)))
    s['items'] = items
    spec.save(s)
    print(f'{a.id}: {len(items)} items -> {os.path.relpath(spec.path(a.id), config.REPO)}')
    for i in items:
        print('  ', i.get('clip') or i.get('bvh') or i.get('anim'))


if __name__ == '__main__':
    main()
