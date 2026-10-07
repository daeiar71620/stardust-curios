"""Generate synthetic in-memory management fixtures from the trusted v9 source.

Only the explicitly supplied public engine module is opened. No save, observation,
account, or deployment data is read or written; fixtures leave via stdout only.
"""
import argparse
import copy
import importlib.util
import json
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--engine', required=True)
source = Path(parser.parse_args().engine).resolve()
sys.path.insert(0, str(source.parent))
spec = importlib.util.spec_from_file_location('management_oracle_engine', source)
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)


def normalized(value):
    return json.loads(json.dumps(value, ensure_ascii=False))


def state(seed=123, day=1):
    result = engine.new_state(seed)
    result['revision'] = 1
    result['day'] = day
    result['walkins']['day'] = day
    result['energy'] = 11
    result['credits'] = 10000
    if day >= 8:
        result['first_week_result'] = 'missed'
    return result


def add(s, catalog, condition=65, collected=False, **patch):
    row = engine.CATALOG_BY_ID[catalog]
    item = {
        'catalog_id': row[0], 'name': row[1], 'rarity': row[2], 'kind': row[3],
        'base_value': round(row[4] * 1.02), 'condition': condition,
        'description': row[5], 'origin': engine.SUPPLIERS['curated']['name'],
        'collected': collected, 'repairs': 0, 'last_sale_day': 0, 'last_repair_day': 0,
        'id': f"I{s['next_item']:03d}", 'price': 79,
    }
    item.update(patch)
    s['next_item'] += 1
    s['stats']['crates_opened'] += 1
    s['collection' if collected else 'inventory'].append(item)
    if catalog not in s['discovered']:
        s['discovered'].append(catalog)
    return item


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
        steps.append({
            'command': command, 'args': args, 'error': error,
            'state': normalized(current),
            'observation': engine.observation(current),
        })
    cases.append({
        'label': label, 'initial': normalized(initial),
        'initial_observation': engine.observation(initial),
        'steps': steps,
    })


# Exact cost/rounding/event snapshots across all facilities, rarities, events and
# tool-set status. A second same-day attempt must fail without spending or RNG.
for level in range(4):
    for rarity, catalog in [('common', 'coffee'), ('rare', 'music'), ('legendary', 'dawn')]:
        for event_index, event in enumerate(engine.EVENTS):
            for tool_set in [False, True]:
                s = state(1000 + level * 100 + event_index * 13 + int(tool_set))
                s['upgrades']['workbench'] = level
                s['daily_event'] = copy.deepcopy(event)
                if tool_set:
                    for key in ['wrench', 'lamp', 'welder']:
                        add(s, key, collected=True)
                item = add(s, catalog, 61, collected=bool(event_index % 2))
                run(f'repair-matrix-{level}-{rarity}-{event["id"]}-{tool_set}', s,
                    [('repair', [item['id'].lower()]), ('repair', [item['id']])])

# Both RNG branches and both condition clamps at every workbench level, including
# an allowed second repair on a later day and an exhausted repair counter after it.
for level in range(4):
    fail_chance = [0.24, 0.14, 0.07, 0.03][level]
    seeds = {}
    for seed in range(2000):
        s = state(seed)
        fails = engine._rng(s).random() < fail_chance
        seeds.setdefault(fails, seed)
        if len(seeds) == 2:
            break
    for fails, seed in seeds.items():
        for condition in [5, 6, 35, 98, 99]:
            s = state(seed, day=2)
            s['upgrades']['workbench'] = level
            item = add(s, 'whale', condition, collected=bool(condition % 2),
                       repairs=1, last_repair_day=1, price=9999)
            run(f'repair-branch-{level}-{fails}-{condition}', s,
                [('repair', [item['id']]), ('repair', [item['id']])])

# Ordered preconditions: condition, repair count, day lock, energy, then credits.
for patch in [
    {'condition': 100, 'repairs': 2, 'last_repair_day': 1},
    {'condition': 99, 'repairs': 2, 'last_repair_day': 1},
    {'condition': 99, 'repairs': 1, 'last_repair_day': 1},
    {'condition': 99, 'repairs': 0, 'last_repair_day': 0},
]:
    for energy, credits in [(0, 0), (1, 10000), (2, 0), (2, 14), (2, 15)]:
        s = state()
        s.update(energy=energy, credits=credits)
        add(s, 'coffee', **patch)
        run(f'repair-errors-{patch}-{energy}-{credits}', s, [('repair', ['i001'])])

# Every catalog can be collected; only the third distinct bot refunds one energy.
# Tool cost, signal stock, plant maintenance and bot max-energy snapshots are all
# compared. Duplicate and replacement are tested at a low-quality set threshold.
for kind in engine.KINDS:
    rows = [row for row in engine.CATALOG if row[3] == kind]
    s = state()
    commands = []
    for row in rows:
        item = add(s, row[0], 5)
        commands.append(('collect', [item['id'].lower()]))
    duplicate = add(s, rows[0][0], 6)
    commands += [('collect', [duplicate['id']]), ('replace-collection', [duplicate['id']])]
    run(f'collect-set-{kind}', s, commands)

for energy in [0, 1]:
    s = state()
    s['energy'] = energy
    add(s, 'coffee', 69)
    run(f'collect-exact-energy-{energy}', s, [('collect', ['I001']), ('collect', ['I001'])])

# Replacement preserves exact in-place positions and every property except
# membership. A same-day repair/sale lock remains attached to both objects.
for kind in engine.KINDS:
    rows = [row for row in engine.CATALOG if row[3] == kind]
    for condition in [64, 65, 66, 100]:
        s = state(day=3)
        add(s, rows[1][0], 70, collected=True)
        old = add(s, rows[0][0], 65, collected=True, repairs=2,
                  last_sale_day=3, last_repair_day=3, price=17, base_value=123)
        add(s, rows[2][0], 71, collected=True)
        add(s, rows[1][0], 45)
        new = add(s, rows[0][0], condition, repairs=1,
                  last_sale_day=3, last_repair_day=3, price=654,
                  origin=engine.SUPPLIERS['salvage']['name'], base_value=144)
        add(s, rows[2][0], 46)
        run(f'replacement-{kind}-{condition}', s,
            [('replace-collection', [new['id'].lower()]), ('repair', [new['id']]),
             ('repair', [old['id']]), ('replace-collection', [old['id']])])

for energy in [0, 1]:
    s = state()
    s['energy'] = energy
    add(s, 'coffee', 65, collected=True)
    add(s, 'coffee', 66)
    run(f'replacement-exact-energy-{energy}', s, [('replace-collection', ['I002'])])
s = state()
add(s, 'coffee')
run('replacement-no-cabinet-counterpart', s, [('replace-collection', ['I001'])])

# Every upgrade level, exact budget/energy boundaries and prototype-like IDs.
for which, rule in engine.UPGRADE_RULES.items():
    for level in range(4):
        cost = rule['costs'][min(level, 2)]
        for energy, credits in [(0, 0), (1, 10000), (2, cost - 1), (2, cost), (11, 10000)]:
            s = state()
            s['upgrades'][which] = level
            s.update(energy=energy, credits=credits)
            run(f'upgrade-{which}-{level}-{energy}-{credits}', s, [('upgrade', [which])])
s = state()
run('upgrade-sequence', s, [('upgrade', ['shelf'])] * 4 + [('upgrade', ['display'])] * 4)
s = state()
run('unknown-items-and-upgrades', s,
    [(command, ['missing']) for command in ['repair', 'collect', 'replace-collection']] +
    [('upgrade', [which]) for which in ['missing', 'SHELF', '__proto__', 'constructor', 'toString']])

for phase in ['week_summary', 'lost']:
    s = state(day=7)
    s.update(phase=phase, first_week_result='missed', energy=0, credits=0)
    run(f'inactive-{phase}', s, [(command, ['missing']) for command in
                                ['repair', 'collect', 'replace-collection', 'upgrade']])

# The action snapshot is captured before the dispatcher's milestone check.
# A newly qualified collection advances the goal after the event was recorded.
s = state(day=8)
s['credits'] = 660
add(s, 'coffee', 71, collected=True)
add(s, 'wrench', 70)
run('collect-milestone-snapshot-order', s, [('collect', ['I002'])])
s = state(day=8)
s['upgrades'] = {'workbench': 1, 'shelf': 0, 'display': 0}
s['credits'] = 2000
s['reputation'] = 20
s['milestones'] = [{'id': engine.MILESTONES[0]['id'], 'title': engine.MILESTONES[0]['title'], 'day': 7}]
for row in engine.CATALOG[:5]:
    add(s, row[0], 76, collected=True)
run('upgrade-milestone-order', s, [('upgrade', ['shelf'])])

# Make a genuine synthetic pending trade and compare every public field too.
for seed in range(500):
    pending = state(seed)
    add(pending, 'coffee', 75, price=90)
    add(pending, 'wrench', 60)
    add(pending, 'lamp', 50, collected=True)
    add(pending, 'lamp', 80)
    engine.apply_command(pending, 'sell', ['I001'])
    if pending['negotiation'] is not None:
        break
else:
    raise AssertionError('Could not construct synthetic negotiation')
run('pending-trade-locked-item', pending,
    [('repair', ['I001']), ('collect', ['I001']), ('replace-collection', ['I001'])])
run('pending-trade-other-items-and-upgrades', pending,
    [('repair', ['I002']), ('collect', ['I002']), ('replace-collection', ['I004']),
     ('upgrade', ['workbench'])])

print(json.dumps({
    'cases': cases, 'case_count': len(cases),
    'action_count': sum(len(case['steps']) for case in cases),
}, ensure_ascii=False, separators=(',', ':')))
