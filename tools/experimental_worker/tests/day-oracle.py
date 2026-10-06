"""Synthetic, in-memory v9 day oracle. Never reads or writes a game save."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--engine', required=True)
args = parser.parse_args()
path = Path(args.engine).resolve()
sys.path.insert(0, str(path.parent))
spec = importlib.util.spec_from_file_location('day_oracle_engine', path)
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)


def normalized(value):
    return json.loads(json.dumps(value, ensure_ascii=False))


def state(seed=0, day=1):
    result = e.new_state(seed)
    result['revision'] = 1
    result['day'] = day
    result['stats']['days_traded'] = day - 1
    result['walkins'] = e._make_walkins(e._rng(result), day)
    if day > 7:
        result['first_week_result'] = 'missed'
    return result


def item(row, number, condition=80, collected=True):
    return {
        'catalog_id': row[0], 'name': row[1], 'rarity': row[2], 'kind': row[3],
        'base_value': row[4], 'condition': condition, 'description': row[5],
        'origin': e.SUPPLIERS['curated']['name'], 'collected': collected,
        'repairs': 0, 'last_sale_day': 0, 'last_repair_day': 0,
        'id': f'I{number:03d}', 'price': 100,
    }


def collection(s, identities, condition=80):
    s['collection'] = [item(row, index + 1, condition) for index, row in enumerate(identities)]
    s['next_item'] = len(s['collection']) + 1
    s['stats']['crates_opened'] = len(s['collection'])
    s['discovered'] = [row['catalog_id'] for row in s['collection']]


def run(label, s, commands, private_only=False):
    e._validate_state(s)
    initial = normalized(s)
    steps = []
    for command in commands:
        candidate = copy.deepcopy(s)
        try:
            e.apply_command(candidate, command, [])
            candidate['revision'] += 1
            e._validate_state(candidate)
            s, error = candidate, None
        except e.GameError as exc:
            error = str(exc)
        steps.append({
            'command': command, 'error': error, 'state': normalized(s),
            'observation': None if private_only else e.observation(s),
        })
    return {
        'label': label, 'initial': initial, 'private_only': private_only,
        'initial_observation': None if private_only else e.observation(initial), 'steps': steps,
    }


cases = []
# Longer sequences cross the first-week pause, repeated-continue rejection,
# repeated RNG state boundaries, event exclusions, and daily budget derivation.
for seed in list(range(32)) + [42, 2**53 - 1, 2**128 + 17]:
    s = state(seed)
    s['credits'] = 10000
    s['upgrades']['display'] = seed % 4
    s['upgrades']['shelf'] = (seed // 4) % 4
    cases.append(run(f'sequence-seed-{seed}', s,
                     ['continue'] + ['endday'] * 7 + ['endday', 'continue', 'continue'] + ['endday'] * 23))

# All outgoing events, shelf/display tiers, and ordinary quality-independent
# collection perks. Preserve unrelated shelf/cabinet/crate data across days.
for event_index, daily_event in enumerate(e.EVENTS):
    for level in range(4):
        s = state(2000 + 10 * event_index + level, 8)
        s['credits'] = 2400
        s['daily_event'] = copy.deepcopy(daily_event)
        s['energy'] = 0
        s['upgrades'] = {'workbench': level, 'shelf': level, 'display': level}
        collection(s, [row for row in e.CATALOG if row[3] in {'plant', 'bot', 'signal'}], 5)
        s['supplier_stock'] = {'salvage': 0, 'curated': 0}
        s['visitors'][0]['status'] = 'left'
        s['visitors'][1]['status'] = 'bought'
        shelf_item = item(e.CATALOG[0], s['next_item'], 66, False)
        shelf_item.update(last_sale_day=8, last_repair_day=8, repairs=1)
        s['inventory'] = [shelf_item]
        s['next_item'] += 1
        s['stats']['crates_opened'] += 1
        s['discovered'].append(shelf_item['catalog_id'])
        cargo = item(e.CATALOG[1], 999, 54, False)
        del cargo['id'], cargo['price']
        s['crates'] = [{'id': 'C001', 'supplier': 'curated', 'name': '夜航封存箱', 'cargo': cargo}]
        s['next_crate'] = 2
        cases.append(run(f'event-{daily_event["id"]}-tier-{level}-low-quality-sets', s, ['endday'] * 5))

# First-week cash and quality thresholds, computed after the outgoing fee.
for credits, conditions in [(663, [70, 70]), (664, [70, 70]), (665, [70, 70]),
                            (664, [69, 100]), (664, [70]), (14, []), (13, []),
                            (2000, [100, 100, 100, 100, 100])]:
    s = state(3100 + credits, 7)
    s['credits'] = credits
    collection(s, e.CATALOG[:len(conditions)])
    for row, condition in zip(s['collection'], conditions):
        row['condition'] = condition
    cases.append(run(f'week-cash-{credits}-quality-{conditions}', s,
                     ['continue', 'endday', 'endday', 'continue', 'continue', 'endday']))

# A complete collection can earn several milestones in one wrapper call.
s = state(4000, 7)
s['credits'] = 50000
s['reputation'] = 99
s['upgrades'] = {'workbench': 3, 'shelf': 3, 'display': 3}
collection(s, e.CATALOG, 100)
cases.append(run('week-multi-milestone-and-voyages', s,
                 ['endday', 'continue'] + ['endday'] * 12))

# Exact maintenance affordability and loss for every event, with/without plants.
for daily_event in e.EVENTS:
    for plants in [False, True]:
        for delta in [-1, 0]:
            s = state(5000 + len(cases), 8)
            s['daily_event'] = copy.deepcopy(daily_event)
            s['energy'] = 0
            if plants:
                collection(s, [row for row in e.CATALOG if row[3] == 'plant'][:3], 5)
            s['credits'] = e._operating_cost(s) + delta
            cases.append(run(f'affordability-{daily_event["id"]}-plants-{plants}-delta-{delta}', s,
                             ['endday', 'endday', 'continue']))

# The ongoing campaign has no artificial post-week cap. Stay within the
# engine's validated integer envelope (day <= 10**12).
for day in [8, 99, 9999, 2**32 - 1, 10**12 - 3]:
    s = state(6000 + day, day)
    s['credits'] = 10000
    s['log'] = [{'day': 1, 'text': f'synthetic retained log {index}'} for index in range(60)]
    cases.append(run(f'endless-day-{day}-log-trim', s, ['endday'] * 3))

# Closing actual synthetic pending trades is private-state parity only:
# the bounded public projection intentionally rejects any trade history.
def pending_state(day, named):
    for seed in range(7000, 7500):
        s = state(seed, day)
        visitor = s['visitors'][0] if named else None
        row = next(row for row in e.CATALOG if not named or row[3] == visitor['preferred_kind'])
        goods = item(row, 1, 100, False)
        s['inventory'], s['next_item'] = [goods], 2
        s['stats']['crates_opened'] = 1
        s['discovered'] = [goods['catalog_id']]
        public = e._sale_option(s, goods, visitor)
        goods['price'] = public['max_counter_ask']
        s['log'] = [{'day': 1, 'text': f'synthetic pending log {index}'} for index in range(60)]
        e.apply_command(s, 'sell', ['I001'] + ([visitor['id']] if named else []))
        s['revision'] += 1
        if s['negotiation'] is not None:
            e._validate_state(s)
            return s
    raise AssertionError('Could not generate synthetic pending negotiation')


private_cases = []
for named in [False, True]:
    for day in [1, 7, 123]:
        for lost in [False, True]:
            s = pending_state(day, named)
            s['credits'] = 0 if lost else 10000
            private_cases.append(run(f'pending-named-{named}-day-{day}-lost-{lost}', s,
                                     ['endday', 'continue', 'endday'], private_only=True))

print(json.dumps({
    'cases': cases, 'private_cases': private_cases,
    'case_count': len(cases), 'private_case_count': len(private_cases),
    'action_count': sum(len(case['steps']) for case in cases + private_cases),
}, ensure_ascii=False, separators=(',', ':')))
