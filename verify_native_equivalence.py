#!/usr/bin/env python3
"""Compare native v9 behavior with a supplied original public engine source.

All state is generated here. This script never reads a game's default save,
accepts a save path, imports frozen legacy modules, or accesses a service.
The original source is a verification input, not a shipped runtime dependency.
"""
from __future__ import annotations
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import random
import tempfile
from collections import Counter

import engine


def normalized(value):
    return json.loads(json.dumps(value, ensure_ascii=False))


def synthetic_item(module, catalog_id, number, *, condition=80, collected=False):
    row = module.CATALOG_BY_ID[catalog_id]
    return dict(id=f'I{number:03d}', catalog_id=row[0], name=row[1], rarity=row[2], kind=row[3],
                base_value=row[4], condition=condition, description=row[5],
                origin=module.SUPPLIERS['salvage']['name'], collected=collected,
                repairs=0, last_sale_day=0, last_repair_day=0, price=90)


def synthetic_state(module, seed):
    state = module.new_state(seed)
    state['credits'] = 100000
    if seed % 2:
        state['collection'] = [synthetic_item(module, key, index, condition=60, collected=True)
                               for index, key in enumerate(('wrench', 'lamp', 'welder'), 1)]
        state['inventory'] = [synthetic_item(module, key, index, condition=80)
                              for index, key in enumerate(('wrench', 'coffee', 'bee', 'moss', 'map', 'lamp'), 4)]
        state['discovered'] = list(dict.fromkeys(item['catalog_id']
                                  for item in state['collection'] + state['inventory']))
        state['next_item'] = 10
    return state


def choose_action(state, rng, step):
    pending = state['negotiation']
    if state['phase'] == 'week_summary':
        return 'continue', []
    if pending and step % 3:
        action = rng.choice(('accept', 'decline', 'offer'))
        args = [pending['item_id']]
        if action == 'offer':
            low, high = pending['counter_offer'] + 1, pending['original_price'] - 1
            args.append(str(rng.randint(low, high)) if low <= high else str(low))
        return action, args
    actions = [('endday', []), ('buy', [rng.choice(('salvage', 'curated'))]),
               ('upgrade', [rng.choice(('workbench', 'shelf', 'display'))])]
    if state['crates']:
        actions += [('open', [state['crates'][0]['id']])] * 3
    if state['inventory']:
        item = rng.choice(state['inventory'])
        actions += [('repair', [item['id']]), ('collect', [item['id']]),
                    ('replace-collection', [item['id']]),
                    ('price', [item['id'], str(rng.choice((1, 45, 60, 90, 120, 121, 200, 9999)))]),
                    ('sell', [item['id']]), ('sell', [item['id'], rng.choice(state['visitors'])['id']])]
    if state['collection']:
        actions.append(('repair', [rng.choice(state['collection'])['id']]))
    if state['energy'] <= 1:
        actions += [('endday', [])] * 4
    return rng.choice(actions)


def compare_native(reference, seeds=40, steps=300):
    counts, failures, reads = Counter(), Counter(), 0
    for seed in range(seeds):
        original, current = synthetic_state(reference, seed), synthetic_state(engine, seed)
        assert normalized(original) == normalized(current), ('initial', seed)
        chooser = random.Random(171000 + seed)
        for step in range(steps):
            command, args = choose_action(original, chooser, step)
            results = []
            for module, state in ((reference, original), (engine, current)):
                candidate = copy.deepcopy(state)
                try:
                    module.apply_command(candidate, command, args)
                    module._validate_state(candidate)
                except module.GameError as exc:
                    results.append((str(exc), state))
                else:
                    results.append((None, candidate))
            assert results[0][0] == results[1][0], ('error', seed, step, command, args, results[0][0], results[1][0])
            original, current = results[0][1], results[1][1]
            assert normalized(original) == normalized(current), ('state', seed, step, command, args)
            assert reference.observation(original) == engine.observation(current), ('public', seed, step, command, args)
            (counts if results[0][0] is None else failures)[command] += 1
            if step % 30 == 0:
                original, current = normalized(original), normalized(current)
                reference._validate_state(original)
                engine._validate_state(current)
                reads += 1
    # Real persistence APIs on separate fresh synthetic paths, never live data.
    with tempfile.TemporaryDirectory(prefix='native-equivalence-synthetic-') as directory:
        for seed in range(8):
            original_store = reference.GameStore(Path(directory) / f'original-{seed}.json')
            current_store = engine.GameStore(Path(directory) / f'current-{seed}.json')
            state = synthetic_state(reference, seed)
            reference._atomic_json(original_store.save_path, state)
            engine._atomic_json(current_store.save_path, state)
            commands = [('status', []), ('market', []), ('codex', []), ('visitors', []),
                        ('buy', ['salvage']), ('open', ['C001']), ('inspect', [f'I{state["next_item"]:03d}']),
                        ('price', [f'I{state["next_item"]:03d}', '90']),
                        ('sell', [f'I{state["next_item"]:03d}']), ('endday', [])]
            for command, args in commands:
                results = []
                for module, store in ((reference, original_store), (engine, current_store)):
                    try:
                        results.append(('ok', store.execute(command, *args)))
                    except module.GameError as exc:
                        results.append(('error', str(exc)))
                assert results[0] == results[1], ('store', seed, command)
                assert original_store.save_path.read_bytes() == current_store.save_path.read_bytes(), ('save-bytes', seed, command)
                assert original_store.observation_path.read_bytes() == current_store.observation_path.read_bytes(), ('public-bytes', seed, command)
                reads += 1
    return dict(seeds=seeds, steps_per_seed=steps, compared_actions=seeds * steps,
                successful_actions=dict(sorted(counts.items())),
                rejected_actions=dict(sorted(failures.items())), persisted_or_reloaded_checks=reads)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', required=True, type=Path, help='Original public native-v9 engine.py source')
    parser.add_argument('--seeds', type=int, default=40)
    parser.add_argument('--steps', type=int, default=300)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('public_native_v9_reference', args.reference.resolve())
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    if reference.VERSION != 9:
        parser.error('Reference must use native v9 rules')
    print(json.dumps(compare_native(reference, args.seeds, args.steps), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
