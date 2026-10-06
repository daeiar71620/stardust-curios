"""Fresh-v9 validation corpus from public source; in-memory synthetic data only.

No real saves/observations are opened, written, retained, or transmitted. The
oracle reports canonical Python validation and separately labelled native-only
restrictions. JSON integer-token/float-token importer parity is not claimed.
"""
import argparse
import copy
import importlib.util
import json
import random
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--engine', required=True)
source = Path(parser.parse_args().engine).resolve()
sys.path.insert(0, str(source.parent))
spec = importlib.util.spec_from_file_location('validation_engine', source)
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)


def normalize(value):
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


states = {}


def snapshot(label, state):
    engine._validate_state(state)
    states[label] = normalize(state)


def fresh(seed=123, day=1):
    state = engine.new_state(123)
    state.update(revision=1, day=day, energy=10, credits=10000,
                 rng=random.Random(seed).getstate())
    state['walkins'].update(day=day, budget=100)
    state['demand'] = {'kind': 'tool', 'multiplier': 1.25, 'label': '工具收藏热 · +25%'}
    if day >= 8:
        state['first_week_result'] = 'missed'
    return state


def add(state, catalog='coffee', collected=False, **patch):
    row = engine.CATALOG_BY_ID[catalog]
    item = {'catalog_id': row[0], 'name': row[1], 'rarity': row[2], 'kind': row[3],
            'base_value': row[4], 'condition': 75, 'description': row[5],
            'origin': engine.SUPPLIERS['salvage']['name'], 'collected': collected,
            'repairs': 0, 'last_sale_day': 0, 'last_repair_day': 0,
            'id': f"I{state['next_item']:03d}", 'price': 90}
    item.update(patch)
    state['next_item'] += 1
    state['stats']['crates_opened'] += 1
    state['collection' if collected else 'inventory'].append(item)
    if catalog not in state['discovered']:
        state['discovered'].append(catalog)
    return item


def visitor(state, key):
    row = next(row for row in engine.CUSTOMERS if row[0] == key)
    person = {'id': row[0], 'name': row[1], 'role': row[2], 'preferred_kind': row[3],
              'preference_label': f'偏爱{engine.KINDS[row[3]]}，品相{row[4]}%以上更喜欢',
              'min_condition': row[4], 'budget_range': [row[5], row[6]], 'premium': 1.25,
              'status': 'waiting', 'budget': row[5]}
    state['visitors'] = [person] + [v for v in state['visitors'] if v['id'] != key][:2]


for seed in range(24):
    snapshot(f'fresh-{seed}', engine.new_state(seed))

s = fresh(day=10**12)
s.update(credits=10**12, revision=10**12, next_crate=10**12, next_item=10**12, event_seq=10**12)
s['last_event']['seq'] = s['event_seq']
s['stats'] = {key: 2**53 - 1 for key in s['stats']}
snapshot('native-integer-upper-boundaries', s)
s = fresh()
s.update(credits=0, energy=0)
s['supplier_stock'] = {'salvage': 0, 'curated': 0}
snapshot('resource-lower-boundaries', s)
s = fresh()
s['upgrades']['display'] = 2
s['visitors'] = engine._make_visitors(random.Random(99), s)
snapshot('four-visitors', s)

s = fresh()
item = add(s)
cargo = copy.deepcopy(item)
del cargo['id']
del cargo['price']
s['crates'] = [{'id': 'C001', 'supplier': 'salvage', 'name': '漂流回收箱', 'cargo': cargo}]
s['next_crate'] = 2
add(s, 'wrench', collected=True)
snapshot('items', s)

s = fresh(day=8)
s['upgrades'] = {'workbench': 3, 'shelf': 3, 'display': 3}
s['daily_event'] = copy.deepcopy(engine.EVENTS[-1])
for index, row in enumerate(engine.CATALOG):
    add(s, row[0], collected=True, condition=5 if index % 2 else 100,
        base_value=1 if index % 2 else 10000, repairs=index % 3,
        last_repair_day=8 if index % 2 else 0, last_sale_day=8 if index % 2 else 0)
s['energy'] = 17
s['supplier_stock'] = {'salvage': 5, 'curated': 2}
snapshot('all-sets', s)

s = fresh(day=30)
s['milestones'] = [{'id': row['id'], 'title': row['title'], 'day': 7 + index}
                   for index, row in enumerate(engine.MILESTONES)]
s['milestones'] += [{'id': f'voyage_{index}', 'title': f'星海长航 · 第{index}章', 'day': 15 + index}
                    for index in range(1, 4)]
snapshot('voyages', s)
for phase in ['active', 'week_summary', 'lost']:
    for result in ['won', 'missed']:
        s = fresh(day=7)
        s.update(phase=phase, first_week_result=result)
        snapshot(f'phase-{phase}-{result}', s)

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
    s = fresh(seed)
    add(s)
    engine.apply_command(s, 'sell', ['I001'])
    snapshot(f'initial-{roll}', s)
for roll, seed in sorted(final_seeds.items()):
    s = fresh(seed)
    add(s)
    engine.apply_command(s, 'sell', ['I001'])
    assert s['negotiation']
    engine.apply_command(s, 'offer', ['I001', '70'])
    snapshot(f'final-{roll}', s)

for profile in engine.CUSTOMERS:
    s = fresh(first_seeds[99])
    visitor(s, profile[0])
    catalog = next(row[0] for row in engine.CATALOG if row[3] == profile[3])
    item = add(s, catalog, condition=100, price=100)
    engine.apply_command(s, 'sell', [item['id'], profile[0]])
    assert s['negotiation']
    snapshot(f'named-pending-{profile[0]}', s)
    for command in ['accept', 'decline', 'offer']:
        candidate = copy.deepcopy(s)
        args = [item['id']]
        if command == 'offer':
            args += [str(s['negotiation']['counter_offer'] + 1)]
        engine.apply_command(candidate, command, args)
        snapshot(f'named-{command}-{profile[0]}', candidate)

# Ring-buffer edge: row 1's initial must fall out before row 2's final may lead.
s = fresh(final_seeds[50], day=8)
add(s)
engine.apply_command(s, 'sell', ['I001'])
engine.apply_command(s, 'offer', ['I001', '70'])
for index in range(62):
    engine.apply_command(s, 'endday', [])
    s['inventory'] = []
    item = add(s, price=1)
    engine.apply_command(s, 'sell', [item['id']])
    if s['roll_seq'] in [59, 60, 61, 62, 64]:
        snapshot(f'history-{s["roll_seq"]}', s)
assert states['history-61']['roll_history'][0]['stage'] == 'final'

# Stateful legal transitions, with each intermediate state validated.
s = fresh(13)
commands = [('buy', ['salvage']), ('open', ['C001']), ('repair', ['I001']),
            ('price', ['I001', '80']), ('collect', ['I001']), ('upgrade', ['shelf'])]
for index, (command, args) in enumerate(commands):
    engine.apply_command(s, command, args)
    s['revision'] += 1
    snapshot(f'workflow-{index}-{command}', s)
for index in range(12):
    if s['phase'] == 'week_summary':
        engine.apply_command(s, 'continue', [])
    else:
        engine.apply_command(s, 'endday', [])
    s['revision'] += 1
    snapshot(f'workflow-day-{index}', s)

mutations = []


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
            del parent[key]
        else:
            parent[key] = copy.deepcopy(operation['value'])
    return state


def mutate(label, base, *operations, expected=False, native=None):
    candidate = apply(copy.deepcopy(states[base]), operations)
    try:
        engine._validate_state(candidate)
        accepted = True
    except (engine.GameError, TypeError, ValueError, KeyError, IndexError, OverflowError):
        accepted = False
    assert accepted == expected, (label, 'unexpected Python validation result', accepted)
    mutations.append({'label': label, 'base': base, 'operations': operations,
                      'python_accept': accepted, 'native_accept': accepted if native is None else native})


for value in [None, [], False, 9, 'state']:
    mutate(f'root-{value!r}', 'fresh-0', set_value('', value))
for key in states['fresh-0']:
    mutate(f'missing-root-{key}', 'fresh-0', remove(key))
for key, low, high in [('revision', 0, 10**12), ('day', 1, 10**12), ('credits', 0, 10**12),
                      ('energy', 0, 17), ('reputation', 0, 99), ('next_crate', 1, 10**12),
                      ('next_item', 1, 10**12), ('event_seq', 1, 10**12)]:
    for value in [None, True, '1', 1.25, low - 1, high + 1]:
        mutate(f'integer-{key}-{value!r}', 'fresh-0', set_value(key, value))
for key in ['migration', 'engine_upgrade', 'management_upgrade', 'collection_upgrade', 'budget_upgrade']:
    mutate(f'provenance-object-{key}', 'fresh-0', set_value(key, {}))
for version in [1, 2, 3, 4, 5, 6, 8, 10, True, '9']:
    mutate(f'version-{version}', 'fresh-0', set_value('version', version))
for key, value in [
    ('phase', 'won'), ('upgrades', []), ('upgrades.shelf', True), ('upgrades.display', 4),
    ('upgrades.extra', 0), ('daily_event.title', 'changed'), ('daily_event.extra', 0),
    ('daily_event.energy_delta', 3), ('first_week_result', 'unknown'), ('day', 8),
    ('phase', 'week_summary'), ('first_week_result', 'won'), ('discovered', ['coffee', 'coffee']),
    ('discovered', ['fake']), ('discovered', [1]), ('visitors', []), ('visitors.0.id', 'missing'),
    ('visitors.0.budget', 0), ('visitors.0.budget', True), ('visitors.0.status', 'unknown'),
    ('visitors.0.name', 'changed'), ('visitors.0.budget_range', [1, 2]),
    ('visitors.0.preferred_kind', 'unknown'), ('visitors.0.premium', 1.5),
    ('visitors.0.min_condition', True), ('visitors.0.status', 'negotiating'),
    ('stats.extra', 0), ('stats.sales_count', -1), ('stats.days_traded', True),
    ('stats.gross_earnings', 1.5), ('supplier_stock.salvage', 5), ('supplier_stock.curated', 3),
    ('supplier_stock.salvage', True), ('supplier_stock.extra', 0), ('energy', 13),
    ('demand.kind', 'unknown'), ('demand.multiplier', 1.3), ('demand.label', 7),
    ('inventory', {}), ('crates', None), ('collection', False), ('log', {}),
    ('log.0.day', 0), ('log.0.text', None), ('last_event', None), ('last_event.seq', 2),
    ('last_event.type', 'unknown'), ('last_event.title', 1), ('last_event.text', False),
    ('walkins.day', 2), ('walkins.used', 1), ('walkins.budget', 59), ('walkins.budget', 121),
    ('walkins.extra', 1), ('roll_seq', True), ('roll_seq', -1), ('roll_seq', 1),
    ('negotiation', {}), ('rng', []), ('rng.0', 1), ('rng.1.1', -1),
    ('rng.1.2', 0.5), ('rng.1.624', 625), ('rng.1.624', -1),
]:
    mutate(f'field-{key}-{value!r}', 'fresh-0', set_value(key, value))
mutate('duplicate-visitor', 'fresh-0', set_value('visitors.1', states['fresh-0']['visitors'][0]))
for key, value in [('id', 'X001'), ('catalog_id', 'unknown'), ('name', 'changed'), ('rarity', 'rare'),
                   ('kind', 'bot'), ('description', 'changed'), ('base_value', 0), ('base_value', 10001),
                   ('condition', 4), ('condition', 101), ('repairs', 3), ('last_sale_day', 2),
                   ('last_repair_day', -1), ('origin', 'elsewhere'), ('collected', 1), ('collected', True),
                   ('price', 0), ('price', 10000), ('price', True)]:
    mutate(f'item-{key}-{value!r}', 'items', set_value(f'inventory.0.{key}', value))
for key, value in [('id', 'I001'), ('supplier', '__proto__'), ('name', 1), ('cargo', None),
                   ('cargo.collected', True), ('cargo.base_value', False)]:
    mutate(f'crate-{key}-{value!r}', 'items', set_value(f'crates.0.{key}', value))
mutate('duplicate-id', 'items', set_value('collection.0.id', 'I001'))
mutate('collection-not-collected', 'items', set_value('collection.0.collected', False))
duplicate = copy.deepcopy(states['items']['collection'][0])
duplicate['id'] = 'I100'
mutate('duplicate-collection-catalog', 'items', set_value('collection', [states['items']['collection'][0], duplicate]))
inventory = [dict(states['items']['inventory'][0], id=f'I{index + 100}') for index in range(7)]
mutate('combined-crate-inventory-capacity', 'items', set_value('inventory', inventory))
for key, value in [('id', 'voyage_2'), ('title', 'wrong'), ('day', 6), ('day', 31)]:
    mutate(f'milestone-{key}', 'voyages', set_value(f'milestones.0.{key}', value))
mutate('milestone-order', 'voyages', set_value('milestones', list(reversed(states['voyages']['milestones']))))

for key, value in [
    ('id', 0), ('day', 0), ('item_id', 1), ('item_name', None), ('customer_id', 'unknown'),
    ('customer_name', False), ('stage', 'extra'), ('modifier', True), ('modifier', 5),
    ('modifiers', [{'label': 'bad', 'value': 1}]), ('modifiers', [{'label': 'bad', 'value': 20}]),
    ('modifiers', [{'label': 'bad', 'value': 5, 'extra': 1}]), ('success', 1), ('success', True),
    ('outcome', 'success'), ('price', 0), ('price', 10000), ('explanation', None), ('rules_version', 6),
    ('counter_offer', 1), ('die', 'D20'), ('tens', 99), ('tens', True), ('ones', 10), ('roll', 100),
    ('threshold', 0), ('probability', 0.12345), ('base_chance', 70), ('premium', 0), ('extra', 0),
]:
    mutate(f'roll-{key}-{value!r}', 'initial-99', set_value(f'roll_history.0.{key}', value))
mutate('event-roll-stale', 'initial-99', set_value('last_event.roll.id', 44))
mutate('history-missing-row', 'initial-99', set_value('roll_history', []))
mutate('walkin-used-dropped', 'initial-99', set_value('walkins.used', 0))
for key, value in [('counter_offer', 70), ('counter_offer', 0), ('base_chance', 50),
                   ('threshold', 99), ('premium', 0.5)]:
    mutate(f'final-{key}', 'final-50', set_value(f'roll_history.1.{key}', value))

# Pair/history changes also remove event.roll, so validation must find the
# history inconsistency itself rather than merely a stale copied event row.
for key, value in [('customer_name', 'changed'), ('item_name', 'changed'), ('stage', 'initial'),
                   ('modifier', 5), ('price', 90)]:
    mutate(f'pair-{key}', 'final-50', set_value(f'roll_history.1.{key}', value), remove('last_event.roll'))
row = copy.deepcopy(states['initial-99']['roll_history'][0])
row.update(id=2, item_id='Iother')
mutate('two-ordinary-buyers-same-day', 'initial-99', set_value('roll_seq', 2),
       set_value('roll_history', [states['initial-99']['roll_history'][0], row]), remove('last_event.roll'))
mutate('truncated-final-allowed-only-first', 'history-61',
       set_value('roll_history.1', dict(states['history-61']['roll_history'][0], id=3)), remove('last_event.roll'))
# A 60-row window ending at roll 60 cannot already have evicted an initial.
bad = copy.deepcopy(states['history-61']['roll_history'])
for row in bad:
    row['id'] -= 1
mutate('unpaired-final-before-truncation', 'history-61', set_value('roll_seq', 60),
       set_value('roll_history', bad), remove('last_event.roll'))

for key, value in [
    ('item_id', 'I404'), ('item_name', 'changed'), ('customer_id', 'unknown'), ('customer_name', 'changed'),
    ('original_price', 91), ('counter_offer', 0), ('counter_offer', 89), ('day', 2),
    ('initial_roll_id', 2), ('rules_version', 6), ('origin_rules_version', 6), ('extra', 0),
    ('context.reference', 0), ('context.reference', 123), ('context.budget', 101),
    ('context.modifier', 5), ('context.modifiers', [{'label': 'bad', 'value': 5}]), ('context.extra', 0),
]:
    mutate(f'pending-{key}-{value!r}', 'initial-99', set_value(f'negotiation.{key}', value))
mutate('pending-inactive', 'initial-99', set_value('phase', 'lost'))
mutate('pending-unlocked-item', 'initial-99', set_value('inventory.0.last_sale_day', 0))
mutate('pending-named-visitor-not-negotiating', 'named-pending-nox', set_value('visitors.0.status', 'waiting'))
mutate('pending-named-second-negotiator', 'named-pending-nox', set_value('visitors.1.status', 'negotiating'))
mutate('pending-walkin-has-negotiating-visitor', 'initial-99', set_value('visitors.0.status', 'negotiating'))
mutate('pending-public-condition', 'initial-99', set_value('inventory.0.condition', 44))

# Explicit native-only limits, never reported as importer parity.
for field in ['stats.sales_count', 'roll_seq']:
    operations = [set_value(field, 2**53)]
    base = 'fresh-0'
    if field == 'roll_seq':
        base = 'history-64'
        history = copy.deepcopy(states[base]['roll_history'])
        for index, row in enumerate(history):
            row['id'] = 2**53 - len(history) + index + 1
        operations += [set_value('roll_history', history), remove('last_event.roll')]
    mutate(f'native-safe-integer-{field}', base, *operations, expected=True, native=False)
mutate('native-exact-event-seq', 'fresh-0', set_value('last_event.seq', True), expected=True, native=False)
mutate('native-no-bool-rng-word', 'fresh-0', set_value('rng.1.0', True), expected=True, native=False)
mutate('native-no-rng-word-truncation', 'fresh-0', set_value('rng.1.0', 2**32), expected=True, native=False)
mutate('native-no-bool-rng-cache', 'fresh-0', set_value('rng.2', True), expected=True, native=False)
mutate('native-rng-v3-only', 'fresh-0', set_value('rng.0', 2), expected=True, native=False)
mutate('native-event-item-required', 'fresh-0', remove('last_event.item'), expected=True, native=False)
mutate('native-event-item-record', 'fresh-0', set_value('last_event.item', 1), expected=True, native=False)

# Preserve the source's intentional validation scope: this is consistency
# validation, not proof that every state was reached by replaying all commands.
mutate('allowed-historical-public-item-snapshot', 'items', set_value('last_event.item', {'name': 'historical'}), expected=True)
mutate('allowed-extra-root-data', 'fresh-0', set_value('extra', 'preserved'), expected=True)
mutate('allowed-id-prefix-not-format', 'items', set_value('inventory.0.id', 'Icustom'), expected=True)
mutate('allowed-long-log-source-does-not-limit', 'fresh-0', set_value('log', [{'day': 1, 'text': 'synthetic'}] * 61), expected=True)
mutate('allowed-frozen-modifiers-after-upgrade', 'initial-99', set_value('upgrades.display', 3), set_value('reputation', 99), expected=True)
mutate('allowed-object-key-reorder', 'initial-99', set_value('last_event.roll', dict(reversed(list(states['initial-99']['last_event']['roll'].items())))), expected=True)

print(json.dumps({'states': states, 'mutations': mutations,
                  'state_count': len(states), 'mutation_count': len(mutations)},
                 ensure_ascii=False, allow_nan=False, separators=(',', ':')))
