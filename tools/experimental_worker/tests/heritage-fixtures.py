"""Synthetic native-v8 -> official migrate_v8 -> canonical-v9 validation corpus.

Reads trusted public Python sources only. No GameStore, saves, real observation,
network, file output, or guessed production state. Enriched boundary fixtures
are explicitly separate from the genuine-command campaigns in heritage-campaign.py.
"""
import argparse
import copy
import hashlib
import importlib
import importlib.util
import json
import random
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--engine', required=True)
source = Path(parser.parse_args().engine).resolve()
sys.path.insert(0, str(source.parent))
spec = importlib.util.spec_from_file_location('heritage_fixture_engine', source)
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)
old = importlib.import_module('_legacy_v8')


def normalized(value):
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False).encode()


states, migrations, mutations, older_chains = {}, [], [], []


def snapshot(label, state):
    engine._validate_state(state)
    states[label] = normalized(state)
    return state


def migrate(label, original):
    old._validate_state(original)
    before = normalized(original)
    state = engine.migrate_v8(encoded(original))
    assert normalized(original) == before
    # Exactly the official copy-only fields may differ. Revision/day/RNG,
    # every item/repair/quality/milestone, and old roll history must be retained.
    expected = copy.deepcopy(before)
    expected['version'] = 9
    expected['budget_upgrade'] = {'from_version': 8, 'source_day': original['day'],
        'source_phase': original['phase'], 'source_roll_seq': original['roll_seq']}
    if expected['negotiation'] is not None:
        expected['negotiation']['rules_version'] = 9
    for key in ['event_seq', 'last_event', 'log']:
        expected[key] = normalized(state[key])
    assert normalized(state) == expected, 'unexpected migration field change'
    assert state['event_seq'] == original['event_seq'] + 1
    assert old._public_collection_progress(original) == engine._public_collection_progress(state)
    assert old._public_campaign(original) == engine._public_campaign(state)
    migrations.append({'label': label, 'source': before})
    return snapshot(label, state)


def fixture(seed=123, day=1):
    state = old.new_state(123)
    state.update(revision=37, day=day, energy=10, credits=12000, rng=random.Random(seed).getstate())
    state['walkins'].update(day=day, budget=100)
    state['demand'] = {'kind': 'tool', 'multiplier': 1.25, 'label': '工具收藏热 · +25%'}
    if day >= 8:
        state['first_week_result'] = 'missed'
    return state


def add(state, catalog='coffee', collected=False, **patch):
    row = old.CATALOG_BY_ID[catalog]
    item = {'catalog_id': row[0], 'name': row[1], 'rarity': row[2], 'kind': row[3],
        'base_value': row[4], 'condition': 75, 'description': row[5],
        'origin': old.SUPPLIERS['salvage']['name'], 'collected': collected,
        'repairs': 0, 'last_sale_day': 0, 'last_repair_day': 0,
        'id': f"I{state['next_item']:03d}", 'price': 90}
    item.update(patch)
    state['next_item'] += 1
    state['stats']['crates_opened'] += 1
    state['collection' if collected else 'inventory'].append(item)
    if catalog not in state['discovered']:
        state['discovered'].append(catalog)
    return item


for seed in range(24):
    migrate(f'fresh-{seed}', old.new_state(seed))

s = fixture(day=30)
s['upgrades'] = {'workbench': 3, 'shelf': 3, 'display': 3}
for index, row in enumerate(old.CATALOG):
    add(s, row[0], collected=True, condition=[69, 70, 74, 75, 79, 80, 84, 85, 89, 90, 100][index % 11],
        repairs=index % 3, last_repair_day=30 if index % 2 else 0)
s['milestones'] = [{'id': row['id'], 'title': row['title'], 'day': 7 + index}
                   for index, row in enumerate(old.MILESTONES)]
s['milestones'].append({'id': 'voyage_1', 'title': '星海长航 · 第1章', 'day': 20})
migrate('quality-and-voyage', s)
for phase in ['active', 'week_summary', 'lost']:
    for result in ['won', 'missed']:
        s = fixture(day=7)
        s.update(phase=phase, first_week_result=result)
        migrate(f'phase-{phase}-{result}', s)

first_seeds, final_seeds = {}, {}
for seed in range(20000):
    rng = random.Random(seed)
    first = rng.randint(0, 9) * 10 + rng.randint(0, 9) or 100
    final = rng.randint(0, 9) * 10 + rng.randint(0, 9) or 100
    first_seeds.setdefault(first, seed)
    if 60 <= first <= 99:
        final_seeds.setdefault(final, seed)
    if len(first_seeds) == len(final_seeds) == 100:
        break
assert len(first_seeds) == len(final_seeds) == 100
for roll, seed in sorted(first_seeds.items()):
    s = fixture(seed)
    add(s)
    old.apply_command(s, 'sell', ['I001'])
    migrate(f'old-initial-{roll}', s)
for roll, seed in sorted(final_seeds.items()):
    s = fixture(seed)
    add(s)
    old.apply_command(s, 'sell', ['I001'])
    assert s['negotiation']
    migrated = migrate(f'pending-before-final-{roll}', s)
    engine.apply_command(migrated, 'offer', ['I001', '70'])
    snapshot(f'cross-final-{roll}', migrated)
    old.apply_command(s, 'offer', ['I001', '70'])
    migrate(f'old-final-{roll}', s)

for profile in old.CUSTOMERS:
    s = fixture(first_seeds[99])
    person = {'id': profile[0], 'name': profile[1], 'role': profile[2], 'preferred_kind': profile[3],
        'preference_label': f'偏爱{old.KINDS[profile[3]]}，品相{profile[4]}%以上更喜欢',
        'min_condition': profile[4], 'budget_range': [profile[5], profile[6]], 'premium': 1.25,
        'status': 'waiting', 'budget': profile[5]}
    s['visitors'] = [person] + [v for v in s['visitors'] if v['id'] != profile[0]][:2]
    catalog = next(row[0] for row in old.CATALOG if row[3] == profile[3])
    item = add(s, catalog, condition=100, price=100)
    old.apply_command(s, 'sell', [item['id'], profile[0]])
    assert s['negotiation']
    migrated = migrate(f'named-pending-{profile[0]}', s)
    for command in ['accept', 'decline', 'offer', 'endday']:
        candidate = copy.deepcopy(migrated)
        args = [] if command == 'endday' else [item['id']]
        if command == 'offer':
            args.append(str(candidate['negotiation']['counter_offer'] + 1))
        engine.apply_command(candidate, command, args)
        snapshot(f'named-{command}-{profile[0]}', candidate)

# A new initial after migration must use9 and establish pending origin9.
s = migrate('before-new-pending', fixture(first_seeds[99]))
add(s)
engine.apply_command(s, 'sell', ['I001'])
assert s['negotiation']['origin_rules_version'] == 9
snapshot('new-pending-after-cutoff', s)

# Old over-budget 1% initial is NOT recalculated under smooth-budget v9 rules.
s = fixture(first_seeds[99])
s['walkins']['budget'] = 60
add(s, price=90)
old.apply_command(s, 'sell', ['I001'])
assert s['negotiation'] and s['roll_history'][-1]['threshold'] == 1
migrated = migrate('old-budget-cliff-pending', s)
assert engine._initial_chance(migrated['negotiation']['context'], 90, 9) > 1

# A v9 final may lead a retained window only after its v6 initial is evicted.
s = fixture(final_seeds[50], day=8)
add(s)
old.apply_command(s, 'sell', ['I001'])
s = migrate('ring-cutoff-pending', s)
engine.apply_command(s, 'offer', ['I001', '70'])
snapshot('ring-cross-final', s)
for index in range(63):
    engine.apply_command(s, 'endday', [])
    s['inventory'] = []  # Explicit fixture enrichment, not a replay campaign.
    item = add(s, price=1)
    engine.apply_command(s, 'sell', [item['id']])
    if s['roll_seq'] in [59, 60, 61, 62, 64, 65]:
        snapshot(f'ring-{s["roll_seq"]}', s)
assert states['ring-61']['roll_history'][0]['stage'] == 'final'
assert all(row['rules_version'] == 9 for row in states['ring-62']['roll_history'])

# Lawful official older->v8->v9 chains are valid Python saves but out of scope.
for version in range(1, 7):
    previous = importlib.import_module(f'_legacy_v{version}').new_state(123)
    through_v8 = getattr(old, f'migrate_v{version}')(encoded(previous))
    upgraded = engine.migrate_v8(encoded(through_v8))
    engine._validate_state(upgraded)
    older_chains.append({'from_version': version, 'state': normalized(upgraded)})


def set_value(path, value):
    return {'op': 'set', 'path': path.split('.') if path else [], 'value': value}


def remove(path):
    return {'op': 'delete', 'path': path.split('.')}


def apply(state, operations):
    for operation in operations:
        parts = operation['path']
        if not parts:
            state = copy.deepcopy(operation['value'])
            continue
        parent = state
        for part in parts[:-1]:
            parent = parent[int(part)] if isinstance(parent, list) else parent[part]
        key = int(parts[-1]) if isinstance(parent, list) else parts[-1]
        if operation['op'] == 'delete':
            parent.pop(key, None)
        else:
            parent[key] = copy.deepcopy(operation['value'])
    return state


def mutate(label, base, *operations, expected=False, gate=None):
    candidate = apply(copy.deepcopy(states[base]), operations)
    try:
        engine._validate_state(candidate)
        accepted = True
    except (engine.GameError, TypeError, ValueError, KeyError, IndexError, OverflowError):
        accepted = False
    assert accepted == expected, (label, 'unexpected Python validation result', accepted)
    mutations.append({'label': label, 'base': base, 'operations': operations,
        'python_accept': accepted, 'gate_accept': accepted if gate is None else gate})


for key in ['migration', 'engine_upgrade', 'management_upgrade', 'collection_upgrade', 'budget_upgrade']:
    mutate(f'missing-{key}', 'fresh-0', remove(key), expected=False, gate=False)
for key in ['from_version', 'source_day', 'source_phase', 'source_roll_seq']:
    mutate(f'missing-boundary-{key}', 'fresh-0', remove(f'budget_upgrade.{key}'))
for value in [None, [], False, 8, 'state']:
    mutate(f'root-{value!r}', 'fresh-0', set_value('', value))
for key, values in {
    'budget_upgrade': [None, {}, []],
    'budget_upgrade.from_version': [1, 2, 3, 4, 5, 6, 7, 9, True, '8'],
    'budget_upgrade.source_day': [0, 2, True, '1', 1.25],
    'budget_upgrade.source_phase': ['won', None, True],
    'budget_upgrade.source_roll_seq': [-1, 1, True, '0', 0.25],
    'budget_upgrade.extra': [1],
}.items():
    for value in values:
        # Without any older provenance and no history, Python permits null;
        # this heritage-only gate deliberately requires the v8 marker.
        accepted = key == 'budget_upgrade' and value is None
        mutate(f'boundary-{key}-{value!r}', 'fresh-0', set_value(key, value), expected=accepted, gate=False)
for key in ['migration', 'engine_upgrade', 'management_upgrade', 'collection_upgrade']:
    mutate(f'unsupported-{key}', 'fresh-0', set_value(key, {}))
for key, value in [('source_day', 7), ('source_roll_seq', 0), ('source_roll_seq', 2)]:
    mutate(f'cutoff-{key}-{value}', 'ring-cross-final', set_value(f'budget_upgrade.{key}', value))
mutate('old-roll-after-source-day', 'ring-cross-final', set_value('roll_history.0.day', 9),
       set_value('day', 9), set_value('walkins.day', 9), set_value('walkins.used', 0), remove('last_event.roll'))
mutate('new-roll-before-source-day', 'ring-cross-final', set_value('roll_history.1.day', 7), remove('last_event.roll'))
for version in [3, 4, 5, 9, True]:
    mutate(f'wrong-old-rule-{version}', 'old-initial-99', set_value('roll_history.0.rules_version', version), remove('last_event.roll'))
for version in [3, 4, 5, 6, True]:
    mutate(f'wrong-new-rule-{version}', 'cross-final-50', set_value('roll_history.1.rules_version', version), remove('last_event.roll'))
for key, value in [('rules_version', 6), ('origin_rules_version', 9), ('origin_rules_version', 5),
    ('initial_roll_id', 0), ('original_price', 91), ('counter_offer', 89), ('context.budget', 99),
    ('context.reference', 0), ('context.modifier', 5), ('context.modifiers', [{'label': 'wrong', 'value': 1}])]:
    mutate(f'pending-{key}-{value!r}', 'old-initial-99', set_value(f'negotiation.{key}', value))
mutate('new-pending-wrong-origin6', 'new-pending-after-cutoff', set_value('negotiation.origin_rules_version', 6))
mutate('new-pending-wrong-history6', 'new-pending-after-cutoff', set_value('roll_history.0.rules_version', 6), remove('last_event.roll'))
cliff = states['old-budget-cliff-pending']
new_threshold = engine._initial_chance(cliff['negotiation']['context'], 90, 9)
mutate('rejudged-old-budget-cliff', 'old-budget-cliff-pending',
       set_value('roll_history.0.threshold', new_threshold), set_value('roll_history.0.probability', new_threshold / 100))
for key, value in [('roll', 100), ('probability', 0.99), ('counter_offer', 70), ('modifiers', []),
    ('base_chance', 60), ('premium', 0.1), ('price', 90), ('customer_name', 'changed')]:
    mutate(f'cross-final-{key}', 'cross-final-50', set_value(f'roll_history.1.{key}', value), remove('last_event.roll'),
           expected=(key == 'modifiers'))
mutate('stale-event-roll', 'cross-final-50', set_value('last_event.roll.id', 999))
mutate('walkin-used-erased', 'old-initial-99', set_value('walkins.used', 0))
mutate('retained-final-not-first', 'ring-61', set_value('roll_history.1', dict(states['ring-61']['roll_history'][0], id=3)), remove('last_event.roll'))
bad = copy.deepcopy(states['ring-61']['roll_history'])
for row in bad:
    row['id'] -= 1
mutate('unpaired-final-before-truncation', 'ring-61', set_value('roll_seq', 60), set_value('roll_history', bad), remove('last_event.roll'))
for key, value in [('revision', True), ('rng.1.624', 625), ('collection.0.condition', 101),
                   ('collection.0.repairs', 3), ('milestones.0.day', 6)]:
    mutate(f'common-{key}', 'quality-and-voyage', set_value(key, value))
mutate('native-safe-integer-stats', 'fresh-0', set_value('stats.sales_count', 2**53), expected=True, gate=False)
mutate('native-rng-v3-only', 'fresh-0', set_value('rng.0', 2), expected=True, gate=False)
mutate('allowed-marker-phase-historical', 'fresh-0', set_value('budget_upgrade.source_phase', 'lost'), expected=True)
mutate('allowed-boundary-evicted', 'ring-65', set_value('budget_upgrade.source_roll_seq', 2), expected=True)
mutate('allowed-frozen-bonus-after-upgrade', 'old-initial-99', set_value('upgrades.display', 3), set_value('reputation', 99), expected=True)

print(json.dumps({'states': states, 'migrations': migrations, 'mutations': mutations, 'older_chains': older_chains,
    'state_count': len(states), 'mutation_count': len(mutations),
    'engine_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
    'legacy_v8_sha256': hashlib.sha256(Path(old.__file__).read_bytes()).hexdigest()},
    ensure_ascii=False, allow_nan=False, separators=(',', ':')))
