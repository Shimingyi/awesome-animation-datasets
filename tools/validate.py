"""Check the repository: dataset entries, example specs, and whether the generated pages are up to date.

    python -m tools.validate            (CI runs this; exit 1 on any problem)
"""
import sys

from . import readme, registry
from .examples import spec


def main():
    probs = registry.problems()
    ids = {d['id'] for d in registry.load_all()}
    for e in spec.all_ids():
        s = spec.load(e)
        if e not in ids:
            probs.append(f'data/examples/{e}.yaml: no dataset `{e}` in data/datasets/')
        if len(s['items']) > spec.N_EXAMPLES:
            probs.append(f'data/examples/{e}.yaml: {len(s["items"])} items, at most {spec.N_EXAMPLES} are shown')
        if s.get('up') and str(s['up']).lstrip('+') not in ('y', 'z', '-z', 'x', '-x', '-y'):
            probs.append(f'data/examples/{e}.yaml: `up: {s["up"]}` must be one of +y, +z, -z, +x, -x, -y')
    if probs:
        print('\n'.join(probs)); sys.exit(1)
    print(f'{len(ids)} datasets, {len(spec.all_ids())} example specs: ok')
    sys.argv = [sys.argv[0], '--check']
    readme.main()


if __name__ == '__main__':
    main()
