"""Latest-only boundary checks on synthetic native v9 data."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import engine
from native_test_helpers import fixture

PROVENANCE = ('migration', 'engine_upgrade', 'management_upgrade', 'collection_upgrade', 'budget_upgrade')
PUBLIC_FIELDS = {'version', 'revision', 'day', 'total_days', 'phase', 'credits', 'energy', 'max_energy',
                 'reputation', 'capacity', 'inventory', 'crates', 'collection', 'collection_sets',
                 'collection_progress', 'upgrades', 'demand', 'daily_event', 'operating_cost', 'suppliers',
                 'upgrade_costs', 'upgrade_details', 'visitors', 'walkins', 'negotiation', 'trade_rules',
                 'last_roll', 'roll_history', 'campaign', 'stats', 'migration', 'engine_upgrade',
                 'management_upgrade', 'collection_upgrade', 'budget_upgrade', 'codex', 'log',
                 'last_event', 'goal'}


class LatestOnlyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='latest-only-synthetic-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = engine.GameStore(self.root / 'synthetic.json')

    def rejected_unchanged(self, state):
        self.store.save_path.write_text(json.dumps(state), encoding='utf-8')
        self.store.observation_path.write_text('public sentinel', encoding='utf-8')
        before = self.store.save_path.read_bytes(), self.store.observation_path.read_bytes()
        with self.assertRaises(engine.GameError):
            self.store.execute('status')
        self.assertEqual(before, (self.store.save_path.read_bytes(), self.store.observation_path.read_bytes()))

    def test_old_commands_and_migration_functions_are_absent(self):
        for version in range(1, 10):
            self.assertFalse(hasattr(engine, f'migrate_v{version}'))
            self.assertNotIn(f'import-v{version}', engine.HELP)
            with self.assertRaises(engine.GameError):
                self.store.execute(f'import-v{version}', str(self.root / 'never-read.json'))
        self.assertFalse(self.store.save_path.exists())
        self.assertFalse(self.store.observation_path.exists())
        self.assertFalse(self.store.lock_path.exists())

    def test_non_native_versions_are_rejected_without_rewriting(self):
        for version in (None, True, 0, *range(1, 9), 9.0, '9', 10):
            state = engine.new_state(42)
            state['version'] = version
            with self.subTest(version=version):
                self.rejected_unchanged(state)

    def test_provenance_fields_are_required_and_strictly_null(self):
        for field in PROVENANCE:
            for value in (False, 0, [], {}, {'from_version': 8}, 'none'):
                state = engine.new_state(42)
                state[field] = value
                with self.subTest(field=field, value=value):
                    self.rejected_unchanged(state)
            state = engine.new_state(42)
            del state[field]
            self.rejected_unchanged(state)

    def test_all_historical_initial_formula_versions_are_rejected(self):
        context = dict(reference=100, budget=100, modifier=0, modifiers=[])
        for version in (None, True, *range(1, 9), 9.0, '9', 10):
            with self.subTest(version=version), self.assertRaises(engine.GameError):
                engine._initial_chance(context, 101, version)

    def test_old_roll_and_negotiation_origins_are_rejected(self):
        native = fixture(99)
        engine.apply_command(native, 'sell', ['I001'])
        self.assertIsNotNone(native['negotiation'])
        for version in (3, 4, 5, 6, 8):
            for target in ('roll', 'origin', 'rules'):
                state = copy.deepcopy(native)
                if target == 'roll':
                    state['roll_history'][0]['rules_version'] = version
                    state['last_event']['roll']['rules_version'] = version
                else:
                    key = 'origin_rules_version' if target == 'origin' else 'rules_version'
                    state['negotiation'][key] = version
                with self.subTest(version=version, target=target):
                    self.rejected_unchanged(state)

    def test_d20_shaped_roll_is_rejected(self):
        state = fixture(99)
        engine.apply_command(state, 'sell', ['I001'])
        row = state['roll_history'][0]
        for key in ('die', 'tens', 'ones', 'roll', 'threshold', 'probability', 'base_chance', 'premium'):
            row.pop(key)
        row.update(face=10, total=10, target=15, base_target=15, rejection_penalty=0)
        state['last_event']['roll'] = copy.deepcopy(row)
        self.rejected_unchanged(state)

    def test_public_contract_remains_39_fields_and_null_provenance(self):
        public = engine.observation(engine.new_state(42))
        self.assertEqual(set(public), PUBLIC_FIELDS)
        self.assertEqual(len(public), 39)
        self.assertTrue(all(public[field] is None for field in PROVENANCE))
        self.assertFalse(public['collection_progress']['legacy_grace'])
        self.assertFalse(public['campaign']['next_milestone']['legacy_grace'])

    def test_latest_only_error_never_suggests_removed_commands(self):
        state = engine.new_state(42)
        state['version'] = 8
        with self.assertRaises(engine.GameError) as caught:
            engine._validate_state(state)
        self.assertIn('new', str(caught.exception))
        self.assertNotIn('import-v', str(caught.exception))

    def test_new_never_overwrites_rejected_old_state(self):
        state = engine.new_state(42)
        state['version'] = 8
        self.store.save_path.write_text(json.dumps(state), encoding='utf-8')
        before = self.store.save_path.read_bytes()
        with self.assertRaises(engine.GameError):
            self.store.execute('new')
        self.assertEqual(before, self.store.save_path.read_bytes())

    def test_explicit_restart_creates_fresh_native_state(self):
        self.store.save_path.write_text('{"version": 8}', encoding='utf-8')
        with mock.patch.object(engine, 'new_state', return_value=engine.new_state(71)):
            public = self.store.execute('restart', '--confirm')
        self.assertEqual(public['version'], 9)
        self.assertEqual(public['day'], 1)
        self.assertTrue(all(public[field] is None for field in PROVENANCE))
        engine._validate_state(self.store.load())


if __name__ == '__main__':
    unittest.main()
