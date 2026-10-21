"""Regenerate everything derived from the registry: the README's generated blocks, docs/categories/*.md and the charts.

    python -m tools.readme            write them
    python -m tools.readme --check    exit 1 if any of them is out of date (CI)

Generated blocks in README.md sit between <!-- BEGIN <name> --> and <!-- END <name> --> markers; everything outside the
markers is hand-written and kept as is.
"""
import argparse
import os
import re
import sys

from . import charts, config, registry, stats
from .examples import spec

VIEWER_URL = 'https://myshi-motion-viewer.static.hf.space/'           # the Space's own domain: keeps #deep-links
VIEWER_SPACE = 'https://huggingface.co/spaces/myshi/motion-viewer'
README = os.path.join(config.REPO, 'README.md')
DOCS = os.path.join(config.REPO, 'docs')
COMMERCIAL = {True: '✅', False: '❌'}


def esc(s):
    return str(s).replace('|', '\\|').replace('\n', ' ')


def fmt_n(n):
    return '–' if n is None else f'{n:,}'


def fmt_short(n):
    return '–' if n is None else f'{n / 1000:.0f}k' if n >= 10000 else f'{n / 1000:.1f}k' if n >= 1000 else str(n)


def fmt_h(h):
    return '–' if h is None else f'{h:,.0f}' if h >= 100 else f'{h:,.1f}' if h >= 1 else f'{h:.2f}'


def viewer_link(d, prefix=''):
    ex = examples_of(d['id'])
    return f'[▶]({VIEWER_URL}#{ex[0]})' if ex else ''


_ex_cache = {}


def examples_of(ds_id):
    """ids of the dataset's baked examples (docs/assets/examples.json, written by tools/examples/bake.py)"""
    if not _ex_cache:
        import json
        p = os.path.join(DOCS, 'assets', 'examples.json')
        _ex_cache.update(json.load(open(p)) if os.path.exists(p) else {})
        _ex_cache.setdefault('__loaded__', [])
    return _ex_cache.get(ds_id, [])


def thumb(d, rel, size=96):
    p = os.path.join(DOCS, 'assets', 'thumbs', f"{d['id']}.webp")
    return f'<img src="{rel}assets/thumbs/{d["id"]}.webp" width="{size}" height="{size}" alt="{esc(d["name"])}">' if os.path.exists(p) else ''


def licence_cell(d):
    lic = d.get('license') or {}
    name = esc(lic.get('name', '?'))
    name = f'[{name}]({lic["url"]})' if lic.get('url') else name
    return f"{COMMERCIAL.get(lic.get('commercial'), '❔')} {name}"


CAUTION = dict(id='caution', name='Use with caution', emoji='', description=(
    'Datasets whose motion quality fell short when we inspected it (jitter, foot skating, penetration ...). They are '
    'still large and useful for some purposes; read the reason before you use them.'))


def page_of(d):
    """the category page a dataset is described on: its subject, or the caution page"""
    return d['subject'] if registry.passes(d) else 'caution'


def content_text(d):
    names = {t['id']: t['name'] for t in registry.taxonomy()['content']}
    sh = registry.content_shares(d)
    txt = names.get(next(iter(sh)), '') if len(sh) == 1 else ', '.join(f"{names.get(k, k).lower()} {100 * v:.0f} %" for k, v in sh.items())
    return txt + (f" ({d['content_note']})" if d.get('content_note') else '')


def reason(d):
    rv, tx = d.get('review') or {}, registry.taxonomy()
    iss = [next((x['name'] for x in tx['review_issues'] if x['id'] == i), i) for i in rv.get('issues') or []]
    return ', '.join(iss).lower().capitalize() + (f". {' '.join(str(rv['note']).split())}" if rv.get('note') else '')


LINK_LABELS = {'homepage': 'home', 'paper': 'paper', 'code': 'code', 'download': 'data'}
N_PREVIEW = 3


def links_cell(d):
    return '<br>'.join(f"[{LINK_LABELS.get(k, k)}]({u})" for k, u in (d.get('links') or {}).items())


def data_cell(d):
    """body models first (SMPL support at a glance), then the other formats"""
    bm = registry.body_models(d)
    rest = [r for r in d.get('representation') or [] if r not in registry.BODY_MODELS]
    return '<br>'.join(bm + [esc(r) for r in rest])


def previews(d, rel, size):
    """the strip of the first N_PREVIEW animated thumbnails (one image: a table cell would wrap separate ones), opening
    the viewer; `size` is the height of one thumbnail"""
    ex, p = examples_of(d['id']), os.path.join(DOCS, 'assets', 'thumbs', f"{d['id']}.webp")
    if not ex or not os.path.exists(p):
        return ''
    from PIL import Image
    w, h = Image.open(p).size
    return f'<a href="{VIEWER_URL}#{ex[0]}"><img src="{rel}assets/thumbs/{d["id"]}.webp" width="{round(size * w / h)}" height="{size}" alt="{esc(d["name"])} examples"></a>'


def dataset_table(ds, rel, preview=200):
    """markdown table of datasets; rel = path prefix from the page to docs/. Previews open their example in the viewer."""
    rows = ['| Dataset | Hours | Clips | Data | Links | Viewer | Preview |', '|---|--:|--:|---|---|:-:|---|']
    for d in ds:
        st = d.get('stats') or {}
        mk = ' ⭐' if registry.verdict(d) == 'recommended' else ''
        name = f"[**{esc(d['name'])}**]({rel}categories/{page_of(d)}.md#{d['id']}){mk}"
        hours = fmt_h(st.get('hours')) + ('¹' if d.get('derived_from') else '')
        name += f"<br><sub>{esc(d['good_for'])}</sub>" if d.get('good_for') else ''
        rows.append(f"| {name} | {hours} | {fmt_short(st.get('clips'))} | {data_cell(d)} | {links_cell(d)} | {viewer_link(d)} | "
                    f"{previews(d, rel, preview)} |")
    return '\n'.join(rows)


def picture(name, rel, alt, width='49%'):
    return (f'<picture><source media="(prefers-color-scheme: dark)" srcset="{rel}assets/charts/{name}-dark.svg">'
            f'<img src="{rel}assets/charts/{name}-light.svg" alt="{alt}" width="{width}"></picture>')


# ------------------------------------------------------------------------------------------------------ README blocks
def block_stats(s):
    lines = [
        f"**{s['datasets']} datasets · {s['hours']:,.0f} hours of motion · {s['clips']:,} clips** — human bodies, hands, "
        f"interactions, animals, rigged objects and robots, {s['years'][0]}–{s['years'][1]}."
        + (f" {len(s['caution'])} more ({fmt_h(s['caution_hours'])} h) {'is' if len(s['caution']) == 1 else 'are'} listed under [Use with caution](#use-with-caution)." if s['caution'] else ''),
        '',
        '<p>',
        picture('subject', 'docs/', 'Hours of motion by subject'),
        picture('content', 'docs/', 'Hours of motion by motion type'),
        '<br>',
        picture('trend', 'docs/', 'Hours of motion over time', width='98.5%'),
        '</p>',
        '',
        '<details><summary>The numbers as tables</summary>',
        '',
        '| Subject | Datasets | Hours | Share |',
        '|---|--:|--:|--:|',
    ]
    for r in s['by_subject']:
        lines.append(f"| {r['emoji']} [{r['name']}](docs/categories/{r['id']}.md) | {r['datasets']} | {fmt_h(r['hours'] or None)} | {charts.fmt_pct(r['share']) or '–'} |")
    lines.append(f"| **Total** | **{s['datasets']}** | **{fmt_h(s['hours'])}** | |")
    lines += ['', '| Motion type | Datasets | Hours | Share |', '|---|--:|--:|--:|']
    for r in s['by_content']:
        lines.append(f"| {r['name']} | {r['datasets']} | {fmt_h(r['hours'] or None)} | {charts.fmt_pct(r['share']) or '–'} |")
    lines += ['', '</details>', '', f"Hours count each recording once: {len(s['derived'])} datasets that re-label or re-target another "
              f"one are listed but not added¹, and {len(s['no_hours'])} datasets publish no duration. Numbers come from each dataset's paper "
              f"or homepage, or are measured from the data (see [the schema](data/SCHEMA.md))."]
    return '\n'.join(lines)


def block_hero():
    """the viewer link under the banner (the banner itself is the preview wall: tools/banner.py)"""
    return f'<p><a href="{VIEWER_SPACE}"><img src="docs/assets/viewer-button.svg" height="56" alt="Online Dataset Viewer"></a></p>'


def block_datasets(ds, tx):
    out = []
    for subj in tx['subjects']:
        members = [d for d in ds if d['subject'] == subj['id'] and registry.passes(d)]
        if not members:
            continue
        out += [f"### {subj.get('emoji', '')} {subj['name']}", '', f"{subj['description']} → [details](docs/categories/{subj['id']}.md)", '',
                dataset_table(members, 'docs/'), '']
    bad = [d for d in ds if not registry.passes(d)]
    if bad:
        out += ['### Use with caution', '', f"{CAUTION['description']} → [details](docs/categories/caution.md)", '', dataset_table(bad, 'docs/'), '']
        out += [f"- **{esc(d['name'])}**: {reason(d)}" for d in bad] + ['']
    s = stats.compute(ds, tx)
    out += [f"**Licences.** {s['commercial']['yes']} of these datasets allow commercial use, {s['commercial']['no']} do not and "
            f"{s['commercial']['unknown']} leave it unclear; each category page gives the licence and its link. Always read the "
            f"dataset's own terms.", '']
    out.append('¹ re-labels or re-targets another dataset: listed, but its hours are not added to the totals. '
               '⭐ recommended. Quality notes are our judgement from inspecting the data, not the authors\' claims.')
    return '\n'.join(out)


QUALITY_COLS = [('phys_residual_g', 'Residual g', '{:.2f}'), ('float_frac', 'Float', '{:.0%}'), ('skate_mm', 'Slide mm', '{:.1f}'),
                ('hf_ratio', 'Jitter', '{:.2f}'), ('floor_drift_cm', 'Drift cm', '{:.1f}'), ('pair_floor_gap_cm', 'Pair gap', '{:.1f}'),
                ('G1_tilt_deg', 'Tilt °', '{:.2f}'), ('rom_bad_frac', 'ROM', '{:.0%}'), ('selfpen_frac', 'Self-pen', '{:.0%}')]
FLAG_NAMES = dict(G1_tilt_deg='tilted floor', phys_residual_g='physics', float_frac='floating', skate_mm='foot sliding',
                  hf_ratio='jitter', floor_drift_cm='floor drift', pair_floor_gap_cm='performers on different floors',
                  rom_bad_frac='joint range', selfpen_frac='self-penetration')


def quality_rows(ds):
    """-> (summary, [(id, row)] most flagged first, severity(row, key)) from docs/assets/quality.json, or None.
    severity = share of windows over the threshold / the flag share (> 1: flagged)"""
    import json
    p = os.path.join(DOCS, 'assets', 'quality.json')
    if not os.path.exists(p):
        return None
    q = json.load(open(p)); lim = q.get('share', 0.25)
    by_id = {d['id']: d for d in ds}
    def severity(r, k):
        v = r.get('share', {}).get(k)
        return None if v is None else v / lim
    rows = [(i, r) for i, r in q['datasets'].items() if i in by_id]
    rows.sort(key=lambda x: (-len(x[1]['flags']), -sum(min(3, severity(x[1], k) or 0) for k, _, _ in QUALITY_COLS), by_id[x[0]]['name'].lower()))
    return q, rows, severity


def quality_chart(ds, theme):
    got = quality_rows(ds)
    if not got:
        return None
    q, rows, severity = got
    by_id = {d['id']: d for d in ds}; th = q['thresholds']
    cols = [(n, f'> {th[k]:g}°' if k == 'G1_tilt_deg' else f'> {th[k]:.0%}' if f.endswith('%}') else f'> {th[k]:g}') for k, n, f in QUALITY_COLS]
    body = [(by_id[i]['name'], [((f'{r["share"][k]:.0%}' if r.get('share', {}).get(k) is not None else '–'), severity(r, k)) for k, _, _ in QUALITY_COLS])
            for i, r in rows]
    return charts.quality_card(body, cols, 'Quality red flags', f'share of {q.get("windows", 100)} ten-second windows over each threshold · '
                               f'flagged above {q.get("share", 0.25):.0%} · {q["generated"]} · tools/quality.py', theme)


def block_quality(ds):
    """red flags per dataset from docs/assets/quality.json (python -m tools.quality)"""
    got = quality_rows(ds)
    if not got:
        return '_Run `python -m tools.quality` to measure the datasets._\n'
    q, rows, _ = got; th = q['thresholds']; lim = q.get('share', 0.25)
    by_id = {d['id']: d for d in ds}
    def cell(i, r, k, fmt):                                     # median window · share of windows over the threshold
        v, sh = r['median'].get(k), r.get('share', {}).get(k)
        if v is None or sh is None:
            return '–'
        txt = f'{fmt.format(v)} · {sh:.0%}'
        return f'**{txt}**' if sh > lim else txt
    out = [f'Each of {len(rows)} human datasets is measured on {q.get("windows", 100)} ten-second windows drawn at random from its full '
           f'release (mirrored copies excluded; {q["generated"]}, `python -m tools.quality`): each window becomes world joints in '
           'metres at 30 fps on a body-segment mass model. Each metric has a per-window threshold, and the chart shows the share of '
           f'windows over it: a dataset is flagged when more than {lim:.0%} of its windows are, so problems in part of a release '
           'show even when the typical clip is fine. These are red flags: values clean motion capture practically never shows. '
           'A flag means look closer, no flag does not prove quality.', '',
           f'- **Residual**: the smallest non-physical acceleration the motion needs (flag > {th["phys_residual_g"]} g): the centre '
           'of mass falling faster than gravity, force while clear of the ground, the zero-moment point outside the feet, '
           f'leaving the friction cone. **Float**: feet resting above the floor — steps that stand > 2 cm above the lowest ones (flag > {th["float_frac"]:.0%} of steps).',
           f'- **Slide**: the planted, weight-bearing ball of the foot sliding, mm per frame (flag > {th["skate_mm"]}). **Jitter**: share of '
           f'acceleration energy at 8–12 Hz, above what muscles produce (flag > {th["hf_ratio"]}; not measured under 25 fps).',
           f'- **Drift**: how far the ground under the body moves within a clip (flag > {th["floor_drift_cm"]} cm). '
           f'**Pair gap**: performers of one take standing on different floors (flag > {th["pair_floor_gap_cm"]} cm). '
           f'**Tilt**: the floor under the planted feet against gravity (flag > {th["G1_tilt_deg"]}°).',
           f'- **ROM**: frames with a knee bent backwards or the head bent off the spine (flag > {th["rom_bad_frac"]:.0%}). '
           f'**Self-pen**: frames with limbs deep inside the body (flag > {th["selfpen_frac"]:.0%}).', '',
           'Known false alarms: feet that slide on purpose (dance pivots, shuffling or drunk gaits), releases with the root '
           'motion removed (feet slide), stairs and uneven terrain, keyframed animation, and supports we do not see (chairs, '
           'beds, boxes).', '',
           '<picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/charts/quality-dark.svg">'
           '<img src="docs/assets/charts/quality-light.svg" alt="Quality red flags per dataset and metric" width="100%"></picture>', '',
           '<details><summary>The numbers as a table (median window · share of windows over the threshold)</summary>', '',
           '| Dataset | Windows | ' + ' | '.join(c[1] for c in QUALITY_COLS) + ' | Red flags |',
           '|---|--:|' + '--:|' * len(QUALITY_COLS) + '---|']
    for i, r in rows:
        d = by_id[i]
        out.append(f'| [{d["name"]}](docs/categories/{page_of(d)}.md#{d['id']}) | {r["clips"]} | ' + ' | '.join(cell(i, r, k, f) for k, _, f in QUALITY_COLS)
                   + ' | ' + (', '.join(FLAG_NAMES.get(f, f) for f in r['flags']) or '–') + ' |')
    out += ['', '</details>']
    return '\n'.join(out) + '\n'


def replace_block(text, name, body):
    pat = re.compile(rf'(<!-- BEGIN {name} -->\n)(?:.*?\n)?(<!-- END {name} -->)', re.S)
    if not pat.search(text):
        raise SystemExit(f'README.md has no <!-- BEGIN {name} --> ... <!-- END {name} --> block')
    return pat.sub(lambda m: m.group(1) + body.rstrip('\n') + '\n' + m.group(2), text)


# ------------------------------------------------------------------------------------------------------ category pages
def category_page(subj, members, ds_by_id):
    lines = [f"# {subj.get('emoji', '')} {subj['name']}", '', f"<sub>Generated from `data/datasets/*.yaml` by `python -m tools.readme` — edit the yaml, not this page.</sub>",
             '', subj['description'], '', dataset_table(members, '../'), '']
    for d in members:
        st, L = d.get('stats') or {}, d.get('links') or {}
        lines += [f"## {d['name']}", '']
        im = previews(d, '../', 160)
        if im:
            lines += [im, '']
        if d.get('full_name'):
            lines += [f"**{d['full_name']}** ({d.get('year', '')})", '']
        if d.get('good_for'):
            lines += [f"*Good for:* {d['good_for']}", '']
        facts = [
            ('Size', ' · '.join(x for x in [f"{fmt_h(st['hours'])} h" if st.get('hours') is not None else '',
                                            f"{fmt_n(st['clips'])} clips" if st.get('clips') is not None else '',
                                            f"{st['subjects']} subjects" if st.get('subjects') else ''] if x) or '–'),
            ('Motion', content_text(d) + (f" · tags: {', '.join(d['tags'])}" if d.get('tags') else '')),
            ('Capture', d.get('capture', '')),
            ('Data', ', '.join(d.get('representation', [])) + (f" · {d['skeleton']['joints']} joints" if (d.get('skeleton') or {}).get('joints') else '')
             + (f" · {d['skeleton']['rig']}" if (d.get('skeleton') or {}).get('rig') else '') + (f" · {d['fps']} fps" if d.get('fps') else '')),
            ('Annotations', ', '.join(d.get('annotations') or []) or '–'),
            ('Licence', licence_cell(d) + f" · access: {d.get('access', '?')}"),
            ('Links', ' · '.join(f'[{k}]({v})' for k, v in L.items())),
        ]
        if d.get('paper'):
            facts.append(('Paper', f"{d['paper'].get('title', '')}" + (f" ({d['paper']['venue']})" if d['paper'].get('venue') else '')))
        if d.get('review'):
            rv, tx = d['review'], registry.taxonomy()
            v = next((x for x in tx['review_verdicts'] if x['id'] == rv['verdict']), {})
            iss = [next((x['name'] for x in tx['review_issues'] if x['id'] == i), i) for i in rv.get('issues') or []]
            facts.append(('Quality', f"{v.get('mark', '')} {v.get('name', rv['verdict'])}" + (f" — {', '.join(iss).lower()}" if iss else '')
                          + (f". {' '.join(str(rv['note']).split())}" if rv.get('note') else '')))
        if d.get('derived_from'):
            facts.append(('Derived from', ', '.join(f"[{ds_by_id[x]['name']}]({page_of(ds_by_id[x])}.md#{x})" if x in ds_by_id else x for x in d['derived_from'])))
        if examples_of(d['id']):
            facts.append(('Viewer', f"[{len(examples_of(d['id']))} examples]({VIEWER_URL}#{examples_of(d['id'])[0]})"))
        lines += ['| | |', '|---|---|'] + [f'| {k} | {esc(v)} |' for k, v in facts] + ['']
        if d.get('stats_note'):
            lines += [f"<sub>Size: {esc(d['stats_note'])}</sub>", '']
        if d.get('notes'):
            lines += [str(d['notes']).strip(), '']
        if d.get('variants'):
            lines += ['Other releases of the same motion:', '']
            lines += [f"- [{v['name']}]({v['url']})" + (f" — {v['note']}" if v.get('note') else '') if v.get('url') else f"- {v['name']}" + (f" — {v['note']}" if v.get('note') else '') for v in d['variants']]
            lines.append('')
        if d.get('citation'):
            lines += ['<details><summary>BibTeX</summary>', '', '```bibtex', str(d['citation']).strip(), '```', '', '</details>', '']
    return '\n'.join(lines)


TREND_START = 2018                                              # the trend starts here, with everything before it


def trend(ds, theme):
    """cumulative hours of the counted datasets by release month (`released`), labels on the steps of >= 10 h"""
    import collections
    ds = [d for d in ds if registry.passes(d) and registry.counted(d) and stats._num(d, 'hours')]
    tm = lambda d: int(str(d.get('released', d['year']))[:4]) + (int(str(d['released'])[5:7]) - 1) / 12 if d.get('released') else d['year'] + 0.5   # noqa: E731
    before = sum(stats._num(d, 'hours') for d in ds if tm(d) < TREND_START)
    by = collections.defaultdict(list)
    for d in ds:
        if tm(d) >= TREND_START:
            by[tm(d)].append((stats._num(d, 'hours'), d['name']))
    pts, cum, notes = [(TREND_START, before)], before, {}
    for t in sorted(by):
        add = sum(h for h, _ in by[t]); cum += add; pts.append((t, cum))
        if add >= 10:
            notes[t] = (' + '.join(n for h, n in sorted(by[t], reverse=True) if h >= 0.3 * add)[:40], add)
    return charts.trend_card(pts, notes, 'Hours of motion over time',
                             f'cumulative hours in this list by release month · {len(ds)} datasets · {cum:,.0f} h', TREND_START, theme)


SUBJECT_SLOTS = ['human-body', 'animal', 'object', 'robot', 'hands']   # donut colour per subject, in the order they first had data


def chart(name, rows, s, theme):
    sub = f"{s['datasets']} datasets above our quality bar"
    if name == 'subject':
        return charts.donut_card([(r['name'], r['hours']) for r in rows], 'Hours of motion by subject', sub, f"{s['hours']:,.0f}", theme,
                                 slots=[SUBJECT_SLOTS.index(r['id']) for r in rows])
    return charts.bars_card([(r['name'], r['hours']) for r in rows], 'Hours of motion by type', sub + ' · split by measured content', theme)


# ------------------------------------------------------------------------------------------------------ main
def render():
    """-> {path: content} of every generated file"""
    tx, ds = registry.taxonomy(), registry.datasets()
    probs = registry.problems()
    if probs:
        raise SystemExit('fix the registry first:\n  ' + '\n  '.join(probs))
    s = stats.compute(ds, tx)
    files = {}
    for name, rows in (('subject', s['by_subject']), ('content', s['by_content'])):
        for theme in ('light', 'dark'):
            files[os.path.join(DOCS, 'assets', 'charts', f'{name}-{theme}.svg')] = chart(name, rows, s, theme)
    for theme in ('light', 'dark'):
        files[os.path.join(DOCS, 'assets', 'charts', f'trend-{theme}.svg')] = trend(ds, theme)
    by_id = {d['id']: d for d in ds}
    import json
    qp = os.path.join(DOCS, 'assets', 'quality.json')
    new_quality = os.path.exists(qp) and 'windows' in json.load(open(qp))       # older summaries: leave that section alone
    for theme in ('light', 'dark') if new_quality else ():
        svg = quality_chart(ds, theme)
        if svg:
            files[os.path.join(DOCS, 'assets', 'charts', f'quality-{theme}.svg')] = svg
    for subj in tx['subjects'] + [CAUTION]:
        members = [d for d in ds if page_of(d) == subj['id']]
        if members:
            files[os.path.join(DOCS, 'categories', f"{subj['id']}.md")] = category_page(subj, members, by_id)
    with open(README) as f:
        text = f.read()
    text = replace_block(text, 'HERO', block_hero())
    text = replace_block(text, 'STATS', block_stats(s))
    text = replace_block(text, 'DATASETS', block_datasets(ds, tx))
    if new_quality:
        text = replace_block(text, 'QUALITY', block_quality(ds))
    files[README] = text
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()
    files = render()
    stale = []
    for p, content in files.items():
        old = open(p).read() if os.path.exists(p) else None
        if old != content:
            stale.append(os.path.relpath(p, config.REPO))
            if not a.check:
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, 'w') as f:
                    f.write(content)
    if a.check:
        if stale:
            print('out of date (run python -m tools.readme):\n  ' + '\n  '.join(stale)); sys.exit(1)
        print('README and docs are up to date')
    else:
        print(f'{len(stale)} file(s) updated' + (': ' + ', '.join(stale) if stale else ''))


if __name__ == '__main__':
    main()
