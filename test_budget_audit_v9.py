"""Independent v9 budget and migration audit using synthetic data only.

No real save or default save path is read or written. Disk checks use fresh
TemporaryDirectory fixtures; the unchanged frozen v8 engine is the oracle.
"""
import copy
import hashlib
import importlib
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest import mock

import engine
import _legacy_v8 as old


def normalized(value):
    return json.loads(json.dumps(value))


def add_item(state, module, number=1, price=90, condition=80):
    row = module.CATALOG_BY_ID['wrench']
    item = dict(id=f'I{number:03d}', catalog_id=row[0], name=row[1], rarity=row[2],
                kind=row[3], base_value=row[4], condition=condition,
                description=row[5], origin=module.SUPPLIERS['salvage']['name'],
                collected=False, repairs=0, last_sale_day=0,
                last_repair_day=0, price=price)
    state['inventory'].append(item)
    state['next_item'] = max(state['next_item'], number + 1)
    if row[0] not in state['discovered']:
        state['discovered'].append(row[0])
    return item


def synthetic(module=engine, *, price=90, count=1, seed=0):
    state = module.new_state(42)
    for index in range(1, count + 1):
        add_item(state, module, index, price)
    # Fixed fixture seed: D100 66 then 04. No preferred-outcome seed search.
    state['rng'] = random.Random(seed).getstate()
    return state


def legacy_pending():
    state = synthetic(old)
    state['walkins']['budget'] = 60
    old.apply_command(state, 'sell', ['I001'])
    old._validate_state(state)
    assert state['negotiation'] is not None
    assert state['roll_history'][-1]['threshold'] == 1
    return state


class BudgetFormulaIndependentAudit(unittest.TestCase):
    @staticmethod
    def context(reference=100, budget=100, modifier=0):
        return dict(reference=reference, budget=budget, modifier=modifier, modifiers=[])

    def test_formula_clamps_continuous_base_and_floors_only_at_end(self):
        self.assertEqual(engine._initial_chance(self.context(), 101), 58)
        self.assertEqual(engine._initial_chance(self.context(reference=1000), 125), 66)
        self.assertEqual(engine._initial_chance(self.context(reference=1), 9999), 1)
        self.assertEqual(engine._initial_chance(self.context(), 100), 60)

    def test_within_budget_matches_frozen_v8_at_every_integer_price(self):
        for reference in (1, 17.3, 100, 1000):
            for budget in (60, 100, 240):
                for bonus in (-30, 0, 15, 45):
                    context = self.context(reference, budget, bonus)
                    for price in range(1, budget + 1):
                        self.assertEqual(engine._initial_chance(context, price),
                                         old._initial_chance(context, price),
                                         (reference, budget, bonus, price))

    def test_price_sweep_is_monotone_bounded_and_deterministic(self):
        for reference, budget, bonus in ((100, 100, 0), (500, 60, 45), (30, 240, -30)):
            context = self.context(reference, budget, bonus)
            previous = 99
            for price in range(1, 10000):
                threshold = engine._initial_chance(context, price)
                self.assertIs(type(threshold), int)
                self.assertTrue(1 <= threshold <= previous)
                previous = threshold
                self.assertEqual(threshold, engine._initial_chance(context, price))

    def test_historical_5_6_formula_dispatch_keeps_hard_gate_and_none_budget(self):
        for version in (5, 6):
            for budget in (None, 60, 100):
                context = self.context(budget=budget)
                for price in (1, 59, 60, 61, 100, 101, 9999):
                    self.assertEqual(engine._initial_chance(context, price, version),
                                     old._initial_chance(context, price))
        for invalid in (None, True, 0, 3, 4, 7, 8, 9.0, '9'):
            with self.subTest(version=invalid), self.assertRaises(engine.GameError):
                engine._initial_chance(self.context(), 100, invalid)

    def test_native_budget_requires_positive_integer(self):
        for budget in (None, False, True, 0, -1, 100.0, '100'):
            with self.subTest(budget=budget), self.assertRaises(engine.GameError):
                engine._initial_chance(self.context(budget=budget), 100)

    def test_all_hundred_rolls_use_exactly_two_digit_draws_and_no_initial_breakdown(self):
        for tens in range(10):
            for ones in range(10):
                state = synthetic()
                source = mock.Mock()
                source.randint.side_effect = [tens, ones]
                record = engine._trade_roll(state, source, state['inventory'][0], None,
                                            101, self.context(), 'initial')
                self.assertEqual(source.randint.call_args_list,
                                 [mock.call(0, 9), mock.call(0, 9)])
                value = tens * 10 + ones or 100
                self.assertEqual(record['roll'], value)
                self.assertEqual(record['threshold'], 58)
                self.assertEqual(record['success'], value <= 58)
                self.assertEqual(record['rules_version'], 9)
                self.assertIsNone(record['base_chance'])
                self.assertIsNone(record['premium'])
                self.assertIsNone(record['counter_offer'])

    def test_final_offer_and_counter_arithmetic_are_unchanged(self):
        for bonus in (-30, -10, 0, 20, 45):
            for counter in (1, 20, 80, 240):
                for price in (counter + 1, counter * 2 + 1, 9999):
                    self.assertEqual(engine._final_chance(bonus, counter, price),
                                     old._final_chance(bonus, counter, price))
            for budget in (None, 60, 240):
                context = self.context(121.75, budget, bonus)
                for price in (2, 90, 250, 9999):
                    self.assertEqual(engine._counter_offer(context, price),
                                     old._counter_offer(context, price))


class BudgetMigrationIndependentAudit(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='budget-v9-independent-synthetic-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def migrate_disk(self, source_state, suffix='copy'):
        source = self.root / f'synthetic-v8-{suffix}.json'
        source.write_text(json.dumps(source_state), encoding='utf-8')
        raw = source.read_bytes()
        target = engine.GameStore(self.root / f'synthetic-v9-{suffix}.json')
        public = target.execute('import-v8', str(source))
        self.assertEqual(source.read_bytes(), raw)
        return target, public

    def assert_corrupt_rejected_atomically(self, state):
        target = engine.GameStore(self.root / 'synthetic-corruption.json')
        target.save_path.write_text(json.dumps(state), encoding='utf-8')
        target.observation_path.write_text('preserve existing public projection', encoding='utf-8')
        before = target.save_path.read_bytes(), target.observation_path.read_bytes()
        with self.assertRaises(engine.GameError):
            target.execute('status')
        self.assertEqual(before, (target.save_path.read_bytes(), target.observation_path.read_bytes()))

    def test_frozen_v8_validator_has_expected_release_digest(self):
        self.assertEqual(hashlib.sha256(Path(old.__file__).read_bytes()).hexdigest(),
                         'ef7e25636884a99b0eac7797379b32e68457f5262a4a5a455945a5295718b17e')

    def test_v8_copy_preserves_every_existing_field_except_explicit_metadata(self):
        source = legacy_pending()
        target, public = self.migrate_disk(source)
        result = target.load()
        for key, value in normalized(source).items():
            if key not in {'version', 'revision', 'last_event', 'event_seq', 'log', 'negotiation'}:
                self.assertEqual(result[key], value, key)
        expected_pending = normalized(source['negotiation'])
        expected_pending['rules_version'] = 9
        self.assertEqual(result['negotiation'], expected_pending)
        self.assertEqual(result['log'][:-1], source['log'])
        self.assertEqual(result['revision'], source['revision'] + 1)
        self.assertEqual(result['budget_upgrade'], dict(from_version=8, source_day=1,
                         source_phase='active', source_roll_seq=1))
        self.assertEqual(public['last_roll']['rules_version'], 6)
        self.assertEqual(public['negotiation']['origin_rules_version'], 6)
        self.assertEqual(public['negotiation']['rules_version'], 9)

    def test_pending_legacy_hard_gate_survives_reads_accept_decline_and_new_final(self):
        source = legacy_pending()
        pending = source['negotiation']
        self.assertGreater(engine._initial_chance(pending['context'], 90), 1)
        for action in ('accept', 'decline', 'offer'):
            with self.subTest(action=action):
                target, _ = self.migrate_disk(source, action)
                before = target.save_path.read_bytes()
                for command in ('status', 'market', 'visitors', 'codex'):
                    target.execute(command)
                price = str(pending['counter_offer'] + 1)
                preview = target.execute('preview-offer', 'I001', price)['negotiation']['preview']
                self.assertEqual(target.save_path.read_bytes(), before)
                expected = copy.deepcopy(source)
                args = ['I001'] + ([price] if action == 'offer' else [])
                old.apply_command(expected, action, args)
                public = target.execute(action, *args)
                result = target.load()
                for key in ('rng', 'credits', 'energy', 'reputation', 'inventory', 'visitors',
                            'walkins', 'stats', 'roll_seq', 'negotiation'):
                    self.assertEqual(result[key], normalized(expected[key]), key)
                expected_rows = normalized(expected['roll_history'])
                if action == 'offer':
                    expected_rows[-1]['rules_version'] = 9
                    self.assertEqual(public['last_roll']['threshold'], preview['threshold'])
                self.assertEqual(result['roll_history'], expected_rows)
                engine.GameStore(target.save_path).execute('status')

    def test_collection_grace_and_exhausted_grace_are_never_regranted(self):
        legacy6 = importlib.import_module('_legacy_v6')
        for exhausted in (False, True):
            source = old.migrate_v6(json.dumps(legacy6.new_state(42)).encode())
            if exhausted:
                source.update(day=8, first_week_result='won')
                source['walkins']['day'] = 8
                source['milestones'] = [dict(id='first_week', title=old.MILESTONES[0]['title'], day=7)]
            old._validate_state(source)
            result = engine.migrate_v8(json.dumps(source).encode())
            engine._validate_state(result)
            self.assertEqual(result['collection_upgrade'], source['collection_upgrade'])
            self.assertEqual(engine.observation(result)['collection_progress'],
                             old.observation(source)['collection_progress'])
            self.assertEqual(engine._next_milestone(result)['legacy_grace'], not exhausted)

    def test_zero_history_import_first_new_roll_is_v9(self):
        target, _ = self.migrate_disk(synthetic(old, price=9999))
        self.assertEqual(target.load()['budget_upgrade']['source_roll_seq'], 0)
        self.assertEqual(target.execute('sell', 'I001')['last_roll']['rules_version'], 9)
        target.load()

    def test_legacy_imports_1_through_6_remain_copyable(self):
        for version in range(1, 7):
            module = importlib.import_module(f'_legacy_v{version}')
            source = module.new_state(42)
            raw = json.dumps(source).encode()
            result = getattr(engine, f'migrate_v{version}')(raw)
            engine._validate_state(result)
            self.assertEqual(result['rng'], normalized(source['rng']))
            self.assertEqual(result['budget_upgrade']['from_version'], version)
            self.assertEqual(result['budget_upgrade']['source_roll_seq'], 0)
            self.assertEqual(result['collection_upgrade']['from_version'], version)

    def test_budget_marker_is_required_strict_and_bounded(self):
        state = engine.migrate_v8(json.dumps(legacy_pending()).encode())
        variants = []
        absent = copy.deepcopy(state)
        del absent['budget_upgrade']
        variants.append(absent)
        for value in (None, False, True, [], {}, 'invalid'):
            changed = copy.deepcopy(state)
            changed['budget_upgrade'] = value
            variants.append(changed)
        for key, values in {
            'from_version': (None, True, 0, 7, 9, 8.0, '8'),
            'source_roll_seq': (None, True, -1, 2, 1.0, '1'),
            'source_day': (None, True, 0, 2, 1.0, '1'),
            'source_phase': (None, 'won', 'pending'),
        }.items():
            for value in values:
                changed = copy.deepcopy(state)
                changed['budget_upgrade'][key] = value
                variants.append(changed)
        changed = copy.deepcopy(state)
        changed['budget_upgrade']['extra'] = 1
        variants.append(changed)
        for index, changed in enumerate(variants):
            with self.subTest(index=index):
                self.assert_corrupt_rejected_atomically(changed)

    def test_legacy_and_new_history_versions_cannot_be_relabelled(self):
        state = engine.migrate_v8(json.dumps(legacy_pending()).encode())
        for version in (5, 7, 8, 9):
            changed = copy.deepcopy(state)
            changed['roll_history'][0]['rules_version'] = version
            self.assert_corrupt_rejected_atomically(changed)
        engine.apply_command(state, 'offer', ['I001', '89'])
        engine._validate_state(state)
        for version in (5, 6, 7, 8):
            changed = copy.deepcopy(state)
            changed['roll_history'][-1]['rules_version'] = version
            changed['last_event']['roll']['rules_version'] = version
            self.assert_corrupt_rejected_atomically(changed)

    def test_direct_pre_v6_import_cannot_absorb_a_future_v9_roll_into_v6(self):
        for version in range(1, 6):
            module = importlib.import_module(f'_legacy_v{version}')
            source = module.new_state(42)
            state = getattr(engine, f'migrate_v{version}')(json.dumps(source).encode())
            engine.apply_command(state, 'endday', [])
            add_item(state, engine, price=9999)
            state['rng'] = random.Random(0).getstate()
            engine.apply_command(state, 'sell', ['I001'])
            engine._validate_state(state)
            state['budget_upgrade']['source_roll_seq'] = 1
            state['roll_history'][-1]['rules_version'] = 6
            state['last_event']['roll']['rules_version'] = 6
            with self.subTest(source_version=version):
                self.assert_corrupt_rejected_atomically(state)

    def test_direct_legacy_budget_and_collection_metadata_share_copy_boundary(self):
        for version in range(1, 7):
            module = importlib.import_module(f'_legacy_v{version}')
            source = module.new_state(42)
            state = getattr(engine, f'migrate_v{version}')(json.dumps(source).encode())
            engine.apply_command(state, 'endday', [])
            engine._validate_state(state)
            for key, value in (('source_day', 2), ('source_phase', 'week_summary')):
                changed = copy.deepcopy(state)
                changed['budget_upgrade'][key] = value
                with self.subTest(source_version=version, field=key):
                    self.assert_corrupt_rejected_atomically(changed)

    def test_v8_tail_uses_absolute_boundary_then_retains_v6_initial_v9_final(self):
        source = legacy_pending()
        initial = source['roll_history'][0]
        source.update(day=61, first_week_result='won', roll_seq=61)
        source['walkins']['day'] = 61
        source['inventory'][0]['last_sale_day'] = 61
        source['negotiation'].update(day=61, initial_roll_id=61)
        source['roll_history'] = [dict(copy.deepcopy(initial), id=index, day=index,
            item_id='I001' if index == 61 else f'I{index:03d}_historical')
            for index in range(2, 62)]
        source['last_event']['roll'] = copy.deepcopy(source['roll_history'][-1])
        old._validate_state(source)
        target, _ = self.migrate_disk(source, 'tail')
        public = target.execute('offer', 'I001', '89')
        self.assertEqual(public['budget_upgrade']['source_roll_seq'], 61)
        self.assertEqual([row['id'] for row in public['roll_history']], list(range(3, 63)))
        self.assertEqual([row['rules_version'] for row in public['roll_history']], [6] * 59 + [9])
        target.load()

    def test_mixed_v3_v4_v5_v6_history_survives_v8_then_v9(self):
        v3, v4, v5, v6 = [importlib.import_module(f'_legacy_v{v}') for v in (3, 4, 5, 6)]
        state = synthetic(v3, price=9999)
        v3.apply_command(state, 'sell', ['I001'])
        state = v4.migrate_v3(json.dumps(state).encode())
        v4.apply_command(state, 'offer', ['I001', '100'])
        v4.apply_command(state, 'endday', [])
        state = v5.migrate_v4(json.dumps(state).encode())
        add_item(state, v5, 2, 9999)
        state['rng'] = random.Random(0).getstate()
        v5.apply_command(state, 'sell', ['I002'])
        v5.apply_command(state, 'decline', ['I002'])
        state = v6.migrate_v5(json.dumps(state).encode())
        v6.apply_command(state, 'endday', [])
        add_item(state, v6, 3, 9999)
        state['rng'] = random.Random(0).getstate()
        v6.apply_command(state, 'sell', ['I003'])
        state = old.migrate_v6(json.dumps(state).encode())
        old._validate_state(state)
        target, public = self.migrate_disk(state, 'mixed')
        self.assertEqual([row['rules_version'] for row in public['roll_history']], [3, 4, 5, 6])
        self.assertEqual(target.load()['roll_history'], state['roll_history'])
        self.assertEqual(target.load()['engine_upgrade'], state['engine_upgrade'])
        self.assertEqual(target.load()['management_upgrade'], state['management_upgrade'])
        target.load()

    def test_import_rejects_public_corrupt_repeated_inplace_and_occupied_destinations(self):
        source = legacy_pending()
        corrupt = copy.deepcopy(source)
        corrupt['roll_history'][0]['threshold'] = 58
        corrupt['roll_history'][0]['probability'] = .58
        corrupt['last_event']['roll'] = copy.deepcopy(corrupt['roll_history'][0])
        for index, value in enumerate((old.observation(source), corrupt, engine.migrate_v8(json.dumps(source).encode()))):
            src = self.root / f'invalid-{index}.json'
            src.write_text(json.dumps(value), encoding='utf-8')
            before = src.read_bytes()
            target = engine.GameStore(self.root / f'rejected-{index}.json')
            with self.assertRaises(engine.GameError):
                target.execute('import-v8', str(src))
            self.assertFalse(target.save_path.exists())
            self.assertFalse(target.observation_path.exists())
            self.assertEqual(src.read_bytes(), before)
        src = self.root / 'source.json'
        src.write_text(json.dumps(source), encoding='utf-8')
        before = src.read_bytes()
        with self.assertRaises(engine.GameError):
            engine.GameStore(src).execute('import-v8', str(src))
        self.assertEqual(src.read_bytes(), before)
        for occupied in ('save', 'observation'):
            target = engine.GameStore(self.root / f'occupied-{occupied}.json')
            path = target.save_path if occupied == 'save' else target.observation_path
            path.write_text('existing sentinel', encoding='utf-8')
            with self.assertRaises(engine.GameError):
                target.execute('import-v8', str(src))
            self.assertEqual(path.read_text(encoding='utf-8'), 'existing sentinel')

    def test_legacy_pending_origins_3_4_5_survive_v8_then_v9(self):
        for version in (3, 4, 5):
            module = importlib.import_module(f'_legacy_v{version}')
            original = synthetic(module, price=9999)
            module.apply_command(original, 'sell', ['I001'])
            source = getattr(old, f'migrate_v{version}')(json.dumps(original).encode())
            old._validate_state(source)
            target, public = self.migrate_disk(source, f'pending-origin-{version}')
            self.assertEqual(public['negotiation']['origin_rules_version'], version)
            self.assertEqual(public['negotiation']['rules_version'], 9)
            self.assertEqual(public['last_roll']['rules_version'], version)
            self.assertEqual(target.load()['negotiation']['context'], source['negotiation']['context'])
            if version == 5:
                self.assertIsNone(target.load()['negotiation']['context']['budget'])
            target.execute('preview-offer', 'I001', '100')
            expected = copy.deepcopy(source)
            old.apply_command(expected, 'offer', ['I001', '100'])
            target.execute('offer', 'I001', '100')
            result = target.load()
            for key in ('rng', 'credits', 'energy', 'reputation', 'inventory', 'visitors',
                        'walkins', 'stats', 'roll_seq', 'negotiation'):
                self.assertEqual(result[key], normalized(expected[key]), (version, key))
            expected_rows = normalized(expected['roll_history'])
            expected_rows[-1]['rules_version'] = 9
            self.assertEqual(result['roll_history'], expected_rows)

    def test_budget_boundary_date_cannot_precede_retained_legacy_roll(self):
        source = synthetic(old, price=9999)
        old.apply_command(source, 'endday', [])
        old.apply_command(source, 'sell', ['I001'])
        state = engine.migrate_v8(json.dumps(source).encode())
        engine._validate_state(state)
        state['budget_upgrade']['source_day'] = 1
        self.assert_corrupt_rejected_atomically(state)

    def test_budget_boundary_date_cannot_follow_new_v9_roll(self):
        source = synthetic(old, price=9999)
        state = engine.migrate_v8(json.dumps(source).encode())
        engine.apply_command(state, 'sell', ['I001'])
        engine.apply_command(state, 'endday', [])
        engine._validate_state(state)
        state['budget_upgrade']['source_day'] = 2
        self.assert_corrupt_rejected_atomically(state)

    def test_v8_week_summary_and_loss_copy_without_advancing_play(self):
        for phase in ('week_summary', 'lost'):
            source = old.new_state(42)
            source['phase'] = phase
            if phase == 'week_summary':
                source.update(day=7, first_week_result='missed')
                source['walkins']['day'] = 7
            else:
                source['credits'] = 0
            old._validate_state(source)
            target, public = self.migrate_disk(source, phase)
            self.assertEqual(public['phase'], phase)
            for key in ('day', 'first_week_result', 'milestones', 'credits', 'energy',
                        'rng', 'roll_seq', 'collection_upgrade'):
                self.assertEqual(target.load()[key], normalized(source[key]), (phase, key))
            self.assertEqual(public['budget_upgrade']['source_phase'], phase)

    def test_native_and_imported_walkin_limit_cannot_be_duplicated(self):
        for imported in (False, True):
            state = synthetic(price=9999, count=2)
            if imported:
                state = engine.migrate_v8(json.dumps(synthetic(old, price=9999, count=2)).encode())
            engine.apply_command(state, 'sell', ['I001'])
            duplicate = copy.deepcopy(state['roll_history'][-1])
            duplicate.update(id=2, item_id='I002')
            state['roll_history'].append(duplicate)
            state['roll_seq'] = 2
            state['inventory'][1]['last_sale_day'] = 1
            state['last_event']['roll'] = copy.deepcopy(duplicate)
            self.assert_corrupt_rejected_atomically(state)

    def test_unrolled_public_projection_and_eligibility_hide_comfort_budget(self):
        source = synthetic()
        changed = copy.deepcopy(source)
        changed['walkins']['budget'] = 120
        changed['inventory'][0]['base_value'] = 9999
        changed['rng'] = random.Random(2).getstate()
        for visitor in changed['visitors']:
            visitor['budget'] = visitor['budget_range'][1]
        engine._validate_state(changed)
        self.assertEqual(engine.observation(source), engine.observation(changed))
        forbidden = {'budget', 'reference', 'base_value', 'rng', 'cargo', 'context', 'budget_factor'}
        def inspect(value):
            if isinstance(value, dict):
                self.assertFalse(forbidden.intersection(value))
                for child in value.values():
                    inspect(child)
            elif isinstance(value, list):
                for child in value:
                    inspect(child)
        inspect(engine.observation(source))
        inspect(engine.observation(engine.migrate_v8(json.dumps(legacy_pending()).encode())))


if __name__ == '__main__':
    unittest.main()
