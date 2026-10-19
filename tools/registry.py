"""The dataset registry: data/datasets/*.yaml checked against data/taxonomy.yaml (schema: data/SCHEMA.md).

    from tools import registry
    ds = registry.datasets()          # list of dicts, taxonomy order (subject, then hours, largest first)
    tx = registry.taxonomy()
"""
import glob
import os
import re

import yaml

from . import config

DATA = os.path.join(config.REPO, 'data')
REQUIRED = ('id', 'name', 'year', 'subject', 'content', 'capture', 'representation', 'license', 'access', 'links')
KNOWN = set(REQUIRED) | {'full_name', 'tags', 'skeleton', 'fps', 'stats', 'stats_note', 'annotations', 'paper', 'citation',
                         'variants', 'derived_from', 'notes', 'review', 'content_note', 'good_for', 'released'}


def taxonomy():
    with open(os.path.join(DATA, 'taxonomy.yaml')) as f:
        return yaml.safe_load(f)


def _ids(tx, key):
    return [x['id'] if isinstance(x, dict) else x for x in tx[key]]


def load_all():
    out = []
    for p in sorted(glob.glob(os.path.join(DATA, 'datasets', '*.yaml'))):
        with open(p) as f:
            d = yaml.safe_load(f) or {}
        d['_file'] = os.path.relpath(p, config.REPO)
        out.append(d)
    return out


def problems(ds=None, tx=None):
    """-> list of 'file: message' strings (empty = valid)."""
    tx = tx or taxonomy()
    ds = ds if ds is not None else load_all()
    allowed = {k: set(_ids(tx, k)) for k in ('subjects', 'content', 'capture', 'access')}
    tags = set(tx['motion_tags'])
    ids = {d.get('id') for d in ds}
    out = []
    for d in ds:
        f = d['_file']
        err = lambda m: out.append(f'{f}: {m}')  # noqa: E731
        for k in REQUIRED:
            if k not in d or d[k] in (None, '', []):
                err(f'missing `{k}`')
        for k in d:
            if k not in KNOWN and not k.startswith('_'):
                err(f'unknown field `{k}`')
        if d.get('id') != os.path.basename(f)[:-5]:
            err('`id` must equal the file name')
        if 'released' in d and not (re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', str(d['released'])) and str(d['released'])[:4] == str(d.get('year'))):
            err('`released` must be YYYY-MM within `year`')
        if d.get('id') and not re.fullmatch(r'[a-z0-9][a-z0-9-]*', str(d['id'])):
            err('`id`: lower case letters, digits and "-" only')
        for k, tk in (('subject', 'subjects'), ('capture', 'capture'), ('access', 'access')):
            if d.get(k) is not None and d[k] not in allowed[tk]:
                err(f'`{k}: {d[k]}` is not in data/taxonomy.yaml {tk}')
        c = d.get('content')
        if isinstance(c, dict):
            for k, v in c.items():
                if k not in allowed['content']:
                    err(f'`content.{k}` is not in data/taxonomy.yaml content')
                if not isinstance(v, (int, float)) or not 0 < v <= 1:
                    err(f'`content.{k}` must be a share in (0, 1]')
            if abs(sum(v for v in c.values() if isinstance(v, (int, float))) - 1) > 0.02:
                err('`content` shares must add up to 1')
        elif c is not None and c not in allowed['content']:
            err(f'`content: {c}` is not in data/taxonomy.yaml content')
        for t in d.get('tags') or []:
            if t not in tags:
                err(f'tag `{t}` is not in data/taxonomy.yaml motion_tags')
        lic = d.get('license') or {}
        if not isinstance(lic, dict) or not lic.get('name'):
            err('`license.name` is required')
        elif lic.get('commercial') not in (True, False, 'unknown', None):
            err('`license.commercial` must be true, false or unknown')
        if not isinstance(d.get('links'), dict) or not d['links'].get('homepage'):
            err('`links.homepage` is required')
        st = d.get('stats') or {}
        for k, v in st.items():
            if k not in ('hours', 'clips', 'subjects', 'frames'):
                err(f'unknown stats field `{k}`')
            elif not isinstance(v, (int, float)) or v < 0:
                err(f'`stats.{k}` must be a number')
        rv = d.get('review')
        if rv is not None:
            verdicts, issues = set(_ids(tx, 'review_verdicts')), set(_ids(tx, 'review_issues'))
            if not isinstance(rv, dict) or rv.get('verdict') not in verdicts:
                err(f'`review.verdict` must be one of {sorted(verdicts)}')
            else:
                for i in rv.get('issues') or []:
                    if i not in issues:
                        err(f'`review.issues`: `{i}` is not in data/taxonomy.yaml review_issues')
                for sub in rv.get('subsets') or []:
                    if not sub.get('match') or sub.get('verdict') not in verdicts:
                        err('`review.subsets`: each needs `match` (a collection prefix) and a valid `verdict`')
                for k in rv:
                    if k not in ('verdict', 'issues', 'note', 'subsets', 'date'):
                        err(f'unknown review field `{k}`')
        for r in d.get('derived_from') or []:
            if r not in ids:
                err(f'`derived_from: {r}` is not a dataset id')
    return out


def counted(d):
    """does this dataset's motion count towards the totals? (re-labelled / re-cut datasets do not)"""
    return not d.get('derived_from')


def content_shares(d):
    """{content id: share of the dataset's duration} (a single id = all of it)"""
    c = d.get('content') or 'general'
    if isinstance(c, dict):
        tot = sum(c.values()) or 1
        return {k: v / tot for k, v in c.items()}
    return {c: 1.0}


BODY_MODELS = {'smpl': 'SMPL', 'smplh': 'SMPL-H', 'smplx': 'SMPL-X'}


def body_models(d):
    """the SMPL-family body models a dataset ships parameters for (from `representation`), display names"""
    return [BODY_MODELS[r] for r in d.get('representation') or [] if r in BODY_MODELS]


def verdict(d):
    """our quality verdict: recommended / usable / caution, or None (not reviewed)"""
    return (d.get('review') or {}).get('verdict')


def passes(d):
    """above the quality bar (unreviewed datasets pass)"""
    return verdict(d) != 'caution'


def hours(d):
    return float((d.get('stats') or {}).get('hours') or 0)


def datasets():
    """valid entries, sorted by subject (taxonomy order), then hours (largest first), then name."""
    tx = taxonomy()
    order = {s: i for i, s in enumerate(_ids(tx, 'subjects'))}
    ds = load_all()
    return sorted(ds, key=lambda d: (order.get(d.get('subject'), 99), -hours(d), str(d.get('name', '')).lower()))


def by_id():
    return {d['id']: d for d in datasets()}
