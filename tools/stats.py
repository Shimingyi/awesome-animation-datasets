"""Statistics over the registry: totals, hours by subject / motion type, licences. Used by tools/readme.py.

    python -m tools.stats            prints them (and writes docs/stats.json)

Counting rules (data/SCHEMA.md): only datasets above our quality bar (review verdict not `caution`) count; datasets with `derived_from` are listed and counted as datasets, but their hours and
clips are not added (the motion is already counted in their source); `variants` are never counted. Datasets without
published hours are counted as datasets and listed under "hours unknown".
"""
import json
import os

from . import config, registry


def _num(d, k):
    return (d.get('stats') or {}).get(k)


def compute(ds=None, tx=None):
    """everything is over the datasets above our quality bar; the `caution` ones are summarised apart"""
    tx = tx or registry.taxonomy()
    ds = ds if ds is not None else registry.datasets()
    caution = [d for d in ds if not registry.passes(d)]
    ds = [d for d in ds if registry.passes(d)]
    counted = [d for d in ds if registry.counted(d)]
    hours = sum(_num(d, 'hours') or 0 for d in counted)

    def group(key, ids):
        rows = []
        for t in ids:
            members = [d for d in ds if d.get(key) == t['id']]
            if not members:
                continue
            h = sum(_num(d, 'hours') or 0 for d in members if registry.counted(d))
            rows.append(dict(id=t['id'], name=t['name'], emoji=t.get('emoji', ''), datasets=len(members), hours=round(h, 2),
                             share=h / hours if hours else 0, ids=[d['id'] for d in members]))
        return rows

    def by_content():
        """hours split by each dataset's content shares; `datasets` counts those with at least 5 % of that type"""
        rows = []
        for t in tx['content']:
            h = sum((_num(d, 'hours') or 0) * registry.content_shares(d).get(t['id'], 0) for d in counted)
            n = [d['id'] for d in ds if registry.content_shares(d).get(t['id'], 0) >= 0.05]
            if h or n:
                rows.append(dict(id=t['id'], name=t['name'], datasets=len(n), hours=round(h, 2), share=h / hours if hours else 0, ids=n))
        return sorted(rows, key=lambda r: (r['id'] == 'general', -r['hours']))      # unclassified last
    lic = {'yes': 0, 'no': 0, 'unknown': 0}
    for d in ds:
        c = (d.get('license') or {}).get('commercial')
        lic['yes' if c is True else 'no' if c is False else 'unknown'] += 1
    access = {}
    for d in ds:
        access[d.get('access', '?')] = access.get(d.get('access', '?'), 0) + 1
    years = sorted(d['year'] for d in ds if isinstance(d.get('year'), int))
    return dict(
        datasets=len(ds), counted=len(counted), hours=round(hours, 1),
        caution=[d['id'] for d in caution], caution_hours=round(sum(_num(d, 'hours') or 0 for d in caution if registry.counted(d)), 1),
        clips=sum(_num(d, 'clips') or 0 for d in counted),
        no_hours=[d['id'] for d in ds if _num(d, 'hours') is None],
        derived=[d['id'] for d in ds if not registry.counted(d)],
        by_subject=group('subject', tx['subjects']), by_content=by_content(),
        commercial=lic, access=access, years=[years[0], years[-1]] if years else [],
    )


def main():
    s = compute()
    out = os.path.join(config.REPO, 'docs', 'stats.json')
    with open(out, 'w') as f:
        json.dump(s, f, indent=1)
    print(f"{s['datasets']} datasets ({s['counted']} counted), {s['hours']} h, {s['clips']} clips")
    for k in ('by_subject', 'by_content'):
        print(k)
        for r in s[k]:
            print(f"  {r['name']:24s} {r['datasets']:3d} datasets {r['hours']:9.1f} h {100 * r['share']:5.1f} %")
    print('commercial use:', s['commercial'], ' access:', s['access'])


if __name__ == '__main__':
    main()
