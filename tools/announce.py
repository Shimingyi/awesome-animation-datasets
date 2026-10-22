"""One GitHub issue per new dataset: what it is, its numbers, our quality verdict and its 10 examples playing, so people
can discuss it; the README's News links to it.

    python -m tools.announce <dataset id>           # draft only: build/announce/<id>.md (look at it first)
    python -m tools.announce <dataset id> --post    # open the issue (gh, as the logged-in account) + a News entry

The previews are the viewer's animated thumbnails served by the Space (deploy first), each linking to its clip.
--post appends {date, dataset, issue, text} to data/news.yaml; run python -m tools.readme afterwards.
"""
import argparse
import datetime
import json
import os
import subprocess

import yaml

from . import config, readme, registry

REPO = 'Shimingyi/awesome-animation-datasets'
NEWS = os.path.join(registry.DATA, 'news.yaml')
COLS = 5
MODEL = dict(smpl='SMPL', smplh='SMPL-H', smplx='SMPL-X', bvh='BVH', fbx='FBX')


def news_text(d):
    page = readme.page_of(d)
    where = ', under Use with caution' if registry.verdict(d) == 'caution' else ''
    h = registry.hours(d)
    return (f"Added [{d['name']}](docs/categories/{page}.md#{d['id']}){where}"
            + (f": {readme.fmt_h(h)} h of {' / '.join(MODEL.get(r, r) for r in d.get('representation', []))}" if h else '')
            + f". {d['good_for'].rstrip('.')}.")


def body(d):
    man = json.load(open(os.path.join(config.REPO, 'viewer', 'examples', 'manifest.json')))
    ex = next((x['examples'] for x in man['datasets'] if x['id'] == d['id']), [])
    st, lic, links, rv = d.get('stats') or {}, d.get('license') or {}, d.get('links') or {}, d.get('review') or {}
    nums = [f"**{readme.fmt_h(st['hours'])} h**" if st.get('hours') else '', f"{st['clips']:,} clips" if st.get('clips') else '',
            f"{st['subjects']:,} subjects" if st.get('subjects') else '', f"{d['fps']} fps" if d.get('fps') else '']
    out = [f"## {d['name']}" + (f" — {d['paper']['venue']}" if d.get('paper', {}).get('venue') else ''), '',
           f"**{d['full_name']}**" if d.get('full_name') else '', '', d['good_for'], '',
           ' · '.join(n for n in nums if n) + f" · {d['capture']} · " + ', '.join(MODEL.get(r, r) for r in d.get('representation', [])), '']
    if d.get('stats_note'):
        out += [f"<sub>{' '.join(d['stats_note'].split())}</sub>", '']
    out += [f"**Licence:** [{lic.get('name', '?')}]({lic.get('url', '')})" + ('' if lic.get('commercial') else ' (non-commercial)')
            + f" · **Access:** {d.get('access', '?')}",
            '**Links:** ' + ' · '.join(f'[{k}]({u})' for k, u in links.items()), '']
    if rv:
        out += [f"**Our verdict: {rv['verdict']}** — {' '.join(rv.get('note', '').split())}", '']
    if ex:
        out += [f"### {len(ex)} examples — click one to play it in the [Motion Viewer]({readme.VIEWER_URL}#{ex[0]['id']})", '', '<table>']
        for i in range(0, len(ex), COLS):
            out.append('<tr>' + ''.join(f'<td align="center"><a href="{readme.VIEWER_URL}#{e["id"]}"><img src="{readme.VIEWER_URL}examples/{e["thumb"]}" width="150"><br><sub>{e["label"]}</sub></a></td>'
                                        for e in ex[i:i + COLS]) + '</tr>')
        out += ['</table>', '']
    out += [f"Full entry: [{d['name']} on the list](https://github.com/{REPO}/blob/main/docs/categories/{readme.page_of(d)}.md#{d['id']}). "
            'Comments welcome: what you use it for, problems you hit, better examples to show.', '']
    if d.get('citation'):
        out += ['<details><summary>BibTeX</summary>', '', '```bibtex', d['citation'].strip(), '```', '', '</details>', '']
    return '\n'.join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('id'); ap.add_argument('--post', action='store_true')
    a = ap.parse_args()
    d = registry.by_id()[a.id]
    title = f"New dataset: {d['name']}" + (' (Use with caution)' if registry.verdict(d) == 'caution' else '')
    os.makedirs(os.path.join(config.REPO, 'build', 'announce'), exist_ok=True)
    draft = os.path.join(config.REPO, 'build', 'announce', f'{a.id}.md')
    open(draft, 'w').write(body(d))
    print(f'{title}\n-> {os.path.relpath(draft, config.REPO)}')
    if not a.post:
        return
    url = subprocess.run(['gh', 'issue', 'create', '-R', REPO, '--title', title, '--body-file', draft],
                         check=True, capture_output=True, text=True).stdout.strip().splitlines()[-1]
    news = (yaml.safe_load(open(NEWS)) if os.path.exists(NEWS) else None) or []
    news.insert(0, dict(date=datetime.date.today().isoformat(), dataset=a.id, issue=url, text=news_text(d)))
    with open(NEWS, 'w') as f:
        f.write('# README "News": newest first, the latest NEWS_SHOWN are shown; tools/announce.py adds one per issue.\n')
        yaml.safe_dump(news, f, sort_keys=False, allow_unicode=True, width=120)
    print(url)


if __name__ == '__main__':
    main()
