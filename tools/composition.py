"""Measure what a dataset's motion IS (data/taxonomy.yaml `content`) from the labels of its clips in the local vault.

    python -m tools.composition [ids ...]           print the measured shares
    python -m tools.composition [ids ...] --write   and store them as `content:` + `content_note:` in data/datasets/<id>.yaml

Every clip of the release is labelled from its text — a category folder, the action word in its file name, or its text
caption — and weighted by its duration. Mirrored copies are skipped (same content). Clips no rule recognises count as
`general` (unclassified), so the shares never claim more than the labels say. Datasets without a RULE keep the single
type written by hand in their yaml.
"""
import argparse
import json
import os
import re

from . import config, registry

# keyword classes, tried in this order (sports before combat: "kicks a ball"; combat before locomotion: "runs and punches")
KEYWORDS = [
    ('dance', r'danc|salsa|waltz|ballet|hip ?hop|tango|\bplie|choreo|twerk|jazz|charleston|krump|popping|locking'),
    ('sports', r'golf|basketball|soccer|football|baseball|tennis|volleyball|badminton|swim|cartwheel|\bflip|somersault|'
               r'handstand|sit-?ups?\b|push-?ups?\b|jumping jacks?|stretch|yoga|exercis|workout|tai ?chi|lunge|plank|'
               r'warm(ing)?[ -]?up|goalkeeper|batter|\bball\b|bowling|\bski|skat|dumbbell|squat|fitness|gym|pilates'),
    ('combat', r'punch|kick|fight|boxing|\bbox\b|martial|karate|kung ?fu|sword|katana|\bblock|strike|attack|stab|slash|'
               r'shaolin|\bjab|\baim|gun|rifle|pistol|grenade|zombie|\bbite|\bhit\b|\bfall|stumble|dodg|defen[cs]|weapon'),
    ('gesture', r'wav(e|es|ing)\b|gestur|\bclap|\bpoint|talk|speak|speech|salute|\bbow(s|ing)?\b|\bnod|shrug|beckon|'
                r'conduct|applau|cheer|celebrat|greet'),
    ('locomotion', r'walk|\bruns?\b|running|\bjog|sprint|\bsteps?\b|stepping|stride|march|\bhop|\bskip|crawl|climb|stair|'
                   r'jump|\bleap|\bturns?\b|turning|sidestep|shuffl|sashay|strut|limp|stagger|obstacle|patrol|\bdash|'
                   r'circl|\bpac(e|es|ing)\b|wander|tiptoe|sneak|locomotion'),
    ('daily-activity', r'\bsit|stand|\blie\b|lying|\blay|pick|lift|carr(y|ies)|place|\bput|\btake|grab|drink|\beat|open|'
                       r'close|wipe|clean|pour|\bhold|reach|bend|kneel|\bidle|wait|look|phone|wash|brush|cook|typ(e|ing)|'
                       r'read|writ|throw|catch|crouch|get(s|ting)? up|\brise|scratch|touch|stretch|rais(e|es|ing)|'
                       r'\barms?\b|\bhands?\b|pretend|move|push|pull|drag'),
]
_KW = [(k, re.compile(p)) for k, p in KEYWORDS]


def classify(text, default='general'):
    t = re.sub(r'([a-z])([A-Z])', r'\1 \2', text).replace('_', ' ').replace('-', ' ').lower()      # camelCase / snake_case
    for k, rx in _KW:
        if rx.search(t):
            return k
    return default


def locomotion_codes(name):
    """100STYLE / MotionPersona take codes: BR BW FR FW SR SW TR = backwards/forwards/sideways/turning run or walk, ID = idle"""
    return 'daily-activity' if re.search(r'_id$', name.lower()) else 'locomotion'


HIPHI = {   # HiPHI's FrameNet-style category folders
    'locomotion': ['Self_motion', 'Change_direction', 'Motion_directional', 'Patrolling'],
    'combat': ['Dodging'],
    'gesture': ['Gesture'],
}

# dataset id -> how to read its clips. vault: folder under <vault>/processed; collection: prefix; label: how to get the text
RULES = {
    'hiphi': dict(vault='HiPHI', skip='__mirror', label=lambda c: next((k for k, v in HIPHI.items() if c['collection'] in v), 'daily-activity'),
                  note="measured from the release's action-category folders, weighted by duration"),
    'amass': dict(vault='HumanML3D', skip_group='M', label=lambda c: classify(c.get('desc', '')),
                  note='measured from the HumanML3D text captions of the AMASS clips, weighted by duration'),
    'kit-ml': dict(vault='KIT', skip_group='M', label=lambda c: classify(c.get('desc', '')),
                   note='measured from the first text caption of each clip, weighted by duration'),
    'bandai-namco': dict(vault='Bandai-Namco-Research-Motiondataset', label=lambda c: classify(re.sub(r'^dataset-\d_|_[^_]+_\d+$', '', c['name'])),
                         note='measured from the action in each file name, weighted by duration'),
    'lafan1': dict(vault='ubisoft-laforge-animation-dataset', collection='lafan1/lafan1',
                   label=lambda c: classify(re.sub(r'\d+_subject\d+$', '', c['name'])),
                   note='measured from the take names (walk, run, fight, dance, jumps, ...), weighted by duration'),
    'adult2child': dict(vault='kid', label=lambda c: classify(re.sub(r'^POSE-(adult|child)\d+-', '', c['name']), 'daily-activity'),
                        note='measured from the action in each file name, weighted by duration'),
    'multi-subject': dict(vault='multi-subject-human-motion-dataset', collection='train', label=lambda c: 'locomotion',
                          note='every take is a walking / running / jumping pattern (W, R, JB, JL, ZW ... in the file names)'),
    '100style': dict(vault='100style', collection='100STYLE_raw', label=lambda c: locomotion_codes(c['name']),
                     note='every style is performed as forward / backward / sideways / turning walks and runs plus an idle take'),
    'motionpersona': dict(vault='MotionPersona', label=lambda c: locomotion_codes(c['name']),
                          note='every persona is captured walking, running and turning, plus idle takes'),
    'motion-x': dict(vault='motionX', label=lambda c: classify(c['collection'] + ' ' + c['name']),
                     note='measured from the sub-dataset and clip names, weighted by duration'),
}
BONES_CATEGORY = {  # BONES-SEED metadata `category` -> content (Baseline / Other: from `content_type_of_movement`)
    'locomotion': ['Basic Locomotion Neutral', 'Basic Locomotion Styles', 'Advanced Locomotion', 'Unusual Locomotion', 'Environments'],
    'daily-activity': ['Object Interaction', 'Object Manipulation', 'Consuming', 'Household', 'Complex Actions'],
    'gesture': ['Gestures', 'Communication', 'Looking and Pointing'],
    'dance': ['Dancing'], 'sports': ['Sports'], 'combat': ['Stunts', 'Martial Arts'],
}


def bones_seed_clips():
    """(label, duration) per original move, from the release's metadata table (no motion files needed)"""
    import csv
    p = os.path.join(config.source('hf_bones_seed'), 'metadata', 'seed_metadata_v004.csv')
    with open(p) as f:
        for r in csv.DictReader(f):
            if r['is_mirror'] == 'True':
                continue
            k = next((c for c, cats in BONES_CATEGORY.items() if r['category'] in cats), None)
            yield k or classify(r['content_type_of_movement'] + ' ' + r['content_short_description']), float(r['move_duration_frames'] or 0)


RULES['bones-seed'] = dict(clips=bones_seed_clips, note="measured from the release's metadata (move category and movement type), weighted by duration")
RULES['unitree-lafan1-retarget'] = dict(RULES['lafan1'], note='LAFAN1 takes retargeted, so their composition (measured from the take names)')


def measure(ds_id):
    r = RULES[ds_id]
    if r.get('clips'):                                  # a rule with its own (label, weight) source
        tot = {}
        for k, w in r['clips']():
            tot[k] = tot.get(k, 0) + w
        return _shares(tot)
    with open(os.path.join(config.get('vault'), 'processed', r['vault'], '_catalog.json')) as f:
        clips = json.load(f)['clips']
    col = r.get('collection')
    tot = {}
    for c in clips:
        cc = str(c.get('collection', ''))
        if col and not (cc == col or cc.startswith(col + '/')):
            continue
        if r.get('skip') and r['skip'] in c['id'] or r.get('skip_group') and str(c.get('group', '')).startswith(r['skip_group']):
            continue
        k = r['label'](c)
        tot[k] = tot.get(k, 0) + float(c.get('duration') or 0)
    return _shares(tot)


def _shares(tot):
    s = sum(tot.values()) or 1
    shares = {k: v / s for k, v in sorted(tot.items(), key=lambda kv: -kv[1])}
    keep = {k: round(v, 2) for k, v in shares.items() if v >= 0.01}          # < 1 %: folded into general
    keep['general'] = round(keep.get('general', 0) + 1 - sum(keep.values()), 2)
    if keep['general'] <= 0:
        keep.pop('general')
    return keep, shares


def write(ds_id, shares, note):
    p = os.path.join(registry.DATA, 'datasets', f'{ds_id}.yaml')
    with open(p) as f:
        text = f.read()
    block = 'content:\n' + ''.join(f'  {k}: {v}\n' for k, v in shares.items()) + f'content_note: {note}\n'
    text = re.sub(r'^content_note:.*\n', '', text, flags=re.M)
    text, n = re.subn(r'^content:(?: \S+\n|\n(?:  .*\n)+)', block, text, count=1, flags=re.M)
    if not n:
        raise SystemExit(f'{p}: no `content:` to replace')
    with open(p, 'w') as f:
        f.write(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ids', nargs='*')
    ap.add_argument('--write', action='store_true')
    a = ap.parse_args()
    for ds_id in a.ids or sorted(RULES):
        if ds_id not in RULES:
            print(f'{ds_id}: no rule (keeps its hand-written content)'); continue
        try:
            keep, shares = measure(ds_id)
        except FileNotFoundError as e:
            print(f'{ds_id}: vault data missing ({e.filename}), skipped'); continue
        print(f'{ds_id:24s} ' + '  '.join(f'{k} {100 * v:.0f}%' for k, v in keep.items()))
        if a.write:
            write(ds_id, keep, RULES[ds_id]['note'])


if __name__ == '__main__':
    main()
