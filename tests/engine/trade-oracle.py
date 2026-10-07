"""Synthetic, in-memory fresh-v9 trade fixtures from the supplied public source.

No saves, accounts, network, or deployment data. The only input file is engine.py.
Fixture construction uses explicit synthetic seeds; production seeding is separate.
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
spec = importlib.util.spec_from_file_location('trade_oracle_engine', source)
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)


def normalized(value):
    return json.loads(json.dumps(value, ensure_ascii=False))


def state(seed=123, day=1):
    result = engine.new_state(123)
    result.update(revision=1, day=day, energy=10, credits=10000,
                  rng=random.Random(seed).getstate())
    result['walkins']['day'] = day
    result['walkins']['budget'] = 100
    result['demand'] = {'kind': 'tool', 'multiplier': 1.25, 'label': '工具收藏热 · +25%'}
    if day >= 8:
        result['first_week_result'] = 'missed'
    return result


def add(s, catalog='coffee', condition=75, collected=False, **patch):
    row = engine.CATALOG_BY_ID[catalog]
    item = {'catalog_id': row[0], 'name': row[1], 'rarity': row[2], 'kind': row[3],
            'base_value': row[4], 'condition': condition, 'description': row[5],
            'origin': engine.SUPPLIERS['salvage']['name'], 'collected': collected,
            'repairs': 0, 'last_sale_day': 0, 'last_repair_day': 0,
            'id': f"I{s['next_item']:03d}", 'price': 90}
    item.update(patch)
    s['next_item'] += 1
    s['stats']['crates_opened'] += 1
    s['collection' if collected else 'inventory'].append(item)
    if catalog not in s['discovered']:
        s['discovered'].append(catalog)
    return item


def visitor(s, key, budget=None):
    row = next(row for row in engine.CUSTOMERS if row[0] == key)
    result = {'id': row[0], 'name': row[1], 'role': row[2], 'preferred_kind': row[3],
              'preference_label': f'偏爱{engine.KINDS[row[3]]}，品相{row[4]}%以上更喜欢',
              'min_condition': row[4], 'budget_range': [row[5], row[6]], 'premium': 1.25,
              'status': 'waiting', 'budget': row[5] if budget is None else budget}
    s['visitors'] = [result] + [v for v in s['visitors'] if v['id'] != key][:2]
    return result


cases = []


def run(label, initial, commands):
    engine._validate_state(initial)
    current = copy.deepcopy(initial)
    steps = []
    for command, args in commands:
        candidate = copy.deepcopy(current)
        try:
            engine.apply_command(candidate, command, args)
            candidate['revision'] += 1
            engine._validate_state(candidate)
            current = candidate
            error = None
        except engine.GameError as exc:
            error = str(exc)
        steps.append({'command': command, 'args': args, 'error': error,
                      'state': normalized(current),
                      'negotiation': engine._public_negotiation(current)})
    cases.append({'label': label, 'initial': normalized(initial),
                  'initial_negotiation': engine._public_negotiation(initial), 'steps': steps})


# Enumerate each initial D100 result with real CPython two-randint draw streams.
first_seeds = {}
final_seeds = {}
for seed in range(20000):
    rng = random.Random(seed)
    initial = rng.randint(0, 9) * 10 + rng.randint(0, 9) or 100
    final = rng.randint(0, 9) * 10 + rng.randint(0, 9) or 100
    first_seeds.setdefault(initial, seed)
    if 60 <= initial <= 99:
        final_seeds.setdefault(final, seed)
    if len(first_seeds) == len(final_seeds) == 100:
        break
assert len(first_seeds) == len(final_seeds) == 100

for roll, seed in sorted(first_seeds.items()):
    for price in [90, 9999]:
        s = state(seed)
        add(s, price=price)
        add(s, 'wrench', price=1)
        run(f'initial-all-digits-{price}-{roll}', s,
            [('sell', ['i001']), ('sell', ['I001']), ('sell', ['I002'])])

# Enumerate each final D100 result. On failure the final price tag persists, the
# old quote is dead, and accepting/retrying has no RNG or resource side effects.
for roll, seed in sorted(final_seeds.items()):
    s = state(seed)
    add(s)
    run(f'final-all-digits-{roll}', s,
        [('sell', ['I001']), ('offer', ['i001', '70']), ('accept', ['I001']), ('sell', ['I001'])])


def pending(seed=None, customer=None, price=90, **patch):
    s = state(final_seeds[50] if seed is None else seed)
    if customer:
        visitor(s, customer)
    item = add(s, price=price, **patch)
    args = [item['id']] + ([customer] if customer else [])
    engine.apply_command(s, 'sell', args)
    assert s['negotiation'] is not None, (seed, customer, price)
    return s


for command in ['accept', 'decline']:
    for energy in [0, 1, 9]:
        s = pending()
        s['energy'] = energy
        run(f'{command}-free-{energy}', s,
            [(command, ['i001']), (command, ['I001']), ('sell', ['I001'])])

# Visitor matrices cover all preferences, condition boundaries, budget edges,
# all event modifiers, every display level and reputation cap, plus artifact sets.
for index, profile in enumerate(engine.CUSTOMERS):
    for condition in [profile[4] - 1, profile[4], 100]:
        for match in [False, True]:
            for event_id in ['calm', 'festival', 'fog']:
                s = state(first_seeds[85])
                v = visitor(s, profile[0], profile[6])
                catalog = next(row[0] for row in engine.CATALOG if (row[3] == profile[3]) == match)
                s['reputation'] = [0, 4, 5, 9, 10, 14, 15, 99][index]
                s['upgrades']['display'] = index % 4
                s['daily_event'] = copy.deepcopy(next(e for e in engine.EVENTS if e['id'] == event_id))
                if index % 2:
                    for key in ['coffee', 'music', 'dawn']:
                        add(s, key, collected=True)
                item = add(s, catalog, condition, price=100)
                run(f'visitor-matrix-{profile[0]}-{condition}-{match}-{event_id}', s,
                    [('sell', [item['id'].lower(), v['id'].upper()])])

# Each catalog and rarity settles with real named buyers; reputation +3 and cap.
for index, row in enumerate(engine.CATALOG):
    s = state(first_seeds[1])
    profile = next(v for v in engine.CUSTOMERS if v[3] == row[3])
    v = visitor(s, profile[0])
    s['reputation'] = [0, 98, 99][index % 3]
    item = add(s, row[0], 5, price=9999)
    run(f'miracle-settlement-{row[0]}', s, [('sell', [item['id'], v['id']])])

# Explicit walk-in condition/price boundaries, public reference and budget caps.
for condition in [5, 44, 45, 100]:
    for price in [1, 2, 40, 41, 81, 82, 120, 121, 9999]:
        s = state(first_seeds[99])
        add(s, condition=condition, price=price)
        run(f'walkin-boundary-{condition}-{price}', s, [('sell', ['I001'])])

# Ordered errors: active, item lookup, existing pending, per-item day lock,
# visitor resolution/status, walk-in cap, energy. Failed candidates are discarded.
for phase in ['lost', 'week_summary']:
    s = state(day=7)
    s.update(phase=phase, first_week_result='missed', energy=0)
    run(f'inactive-{phase}', s, [(command, ['missing', 'abc'] if command == 'offer' else ['missing'])
                               for command in ['sell', 'accept', 'decline', 'offer']])
s = state()
add(s, last_sale_day=1)
add(s)
s['visitors'][0]['status'] = 'left'
s['energy'] = 0
run('sell-error-precedence', s,
    [('sell', ['missing', 'missing']), ('sell', ['I001', 'missing']),
     ('sell', ['I002', 'missing']), ('sell', ['I002', s['visitors'][0]['id']]),
     ('sell', ['I002']), ('accept', ['I001']), ('decline', ['I001']), ('offer', ['I001', 'abc'])])
s = pending()
add(s)
s['energy'] = 0
run('pending-sell-and-offer-precedence', s,
    [('sell', ['missing']), ('sell', ['I001']), ('sell', ['I002', 'missing']),
     ('offer', ['I002', 'abc']), ('offer', ['I001', 'abc']), ('offer', ['I001', '70']),
     ('accept', ['I001'])])
s = state(first_seeds[100])
add(s)
add(s)
engine.apply_command(s, 'sell', ['I001'])
s['energy'] = 0
run('walkin-cap-before-energy', s, [('sell', ['I002'])])

# Python int error classes, whitespace, canonical form, strict bounds, and no
# integer between counter and original. Each valid whitespace test gets a copy.
raw_prices = ['', 'abc', '1.0', 'NaN', 'Infinity', '0x46', '7__0', '7_0', '+70', '-70',
              '070', '0', '60', '90', '9999', '٧٠', '７０', '\ufeff70', '\x1c70', '\x1f70',
              '7 0', '70\x00', '9' * 4301]
s = pending()
run('offer-invalid-price-errors', s, [('offer', ['I001', raw]) for raw in raw_prices])
for raw in ['70', ' 70 ', '\t70\r\n', '\u008570\u0085', '\u00a070\u00a0', '\u200370\u3000']:
    s = pending()
    run(f'offer-valid-whitespace-{raw!r}', s, [('offer', ['I001', raw])])
s = state(first_seeds[99])
add(s, price=2, base_value=1)
engine.apply_command(s, 'sell', ['I001'])
assert s['negotiation']['counter_offer'] == 1
run('adjacent-quote-no-final-offer', s, [('offer', ['I001', '1']), ('offer', ['I001', '2']), ('accept', ['I001'])])

# Frozen final modifiers ignore changed display/reputation/set/event settings.
s = pending()
s['reputation'] = 99
s['upgrades']['display'] = 3
s['daily_event'] = copy.deepcopy(next(e for e in engine.EVENTS if e['id'] == 'festival'))
for key in ['coffee', 'music', 'dawn']:
    add(s, key, collected=True)
run('final-frozen-modifiers', s, [('offer', ['I001', '70'])])

# Named buyer accepting must finish bought, even though close first marks left.
for seed in range(5000):
    s = state(seed)
    visitor(s, 'nox')
    add(s, price=100)
    engine.apply_command(s, 'sell', ['I001', 'NOX'])
    if s['negotiation']:
        break
else:
    raise AssertionError('No synthetic named negotiation')
for command in ['accept', 'decline', 'offer']:
    run(f'named-resolution-{command}', s,
        [(command, ['I001', str(s['negotiation']['counter_offer'] + 1)] if command == 'offer' else ['I001'])])

# Full ring history is reached through source transitions, never forged records.
s = state(day=8)
for index in range(64):
    s['inventory'] = []
    item = add(s, price=1)
    if index >= 58:
        run(f'history-window-{index}', s, [('sell', [item['id']])])
    engine.apply_command(s, 'sell', [item['id']])
    engine.apply_command(s, 'endday', [])

# Capture event snapshot before the dispatcher advances an earned milestone.
s = state(first_seeds[1], day=8)
s['credits'] = 600
add(s, 'wrench', 70, collected=True)
add(s, 'lamp', 70, collected=True)
item = add(s, price=90)
run('sale-milestone-snapshot-order', s, [('sell', [item['id']])])

# Forecast includes only public, frozen inputs and is stable across every legal
# final price for several actual pending quotes; it never draws randomness.
forecasts = []
for seed in range(30):
    s = state(seed)
    add(s)
    engine.apply_command(s, 'sell', ['I001'])
    if s['negotiation'] is None:
        continue
    p = s['negotiation']
    forecasts.append({'state': normalized(s), 'forecasts': [engine._offer_forecast(s, p, price)
        for price in range(p['counter_offer'] + 1, p['original_price'])]})

# Exact decimal formatting at rational and ties-to-even boundaries.
formats = [{'value': (price - counter) / counter, 'text': f'{(price-counter)/counter:.1%}'}
           for counter in range(1, 251) for price in range(counter + 1, min(9999, counter + 101))]

print(json.dumps({'cases': cases, 'case_count': len(cases),
                  'action_count': sum(len(case['steps']) for case in cases),
                  'forecasts': forecasts, 'formats': formats}, ensure_ascii=False, separators=(',', ':')))
