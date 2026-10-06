"""Independent v8 quality-collection acceptance tests.

Fixtures are synthetic, built from the public catalog, and written only into
TemporaryDirectory instances. This suite never reads the default or a real save.
The frozen v6 engine is the oracle for unchanged trading and copy migration.
"""
import copy
import importlib
import json
from pathlib import Path
import random
import tempfile
import unittest

import engine
import _legacy_v6 as legacy
from test_percentile_v5 import rng_for


def item(catalog_id, number, condition=80, collected=False, module=engine, **changes):
    row = module.CATALOG_BY_ID[catalog_id]
    result = dict(id=f"I{number:03d}", catalog_id=row[0], name=row[1], rarity=row[2],
                  kind=row[3], base_value=row[4], condition=condition,
                  description=row[5], origin=module.SUPPLIERS['salvage']['name'],
                  collected=collected, repairs=0, last_sale_day=0,
                  last_repair_day=0, price=90)
    result.update(changes)
    return result


def cabinet(state, ids, conditions=80, module=engine):
    if isinstance(conditions, int):
        conditions = [conditions] * len(ids)
    state['collection'] = [item(key, n, quality, True, module)
                           for n, (key, quality) in enumerate(zip(ids, conditions), 1)]
    state['next_item'] = len(ids) + 1
    state['discovered'] = list(ids)
    return state


def fixture(stage=0, module=engine):
    state = module.new_state(42)
    if stage:
        state.update(day=8, first_week_result='won', credits=100000, reputation=99)
        state['walkins']['day'] = 8
        state['upgrades'] = {key: 3 for key in module.UPGRADE_RULES}
        state['milestones'] = [dict(id=row['id'], title=row['title'], day=7)
                               for row in module.MILESTONES[:stage]]
    return state


def public_goals(state):
    return {row['key']: row for row in
            engine.observation(state)['campaign']['next_milestone']['goals']}


class CollectionHarness(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='collections-v8-synthetic-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = engine.GameStore(self.root / 'synthetic.json')

    def write(self, state):
        engine._validate_state(state)
        engine._atomic_json(self.store.save_path, state)
        return self.store.execute('status')

    def reject(self, command, *args):
        before = (self.store.save_path.read_bytes(), self.store.observation_path.read_bytes())
        with self.assertRaises(engine.GameError):
            self.store.execute(command, *args)
        self.assertEqual(before, (self.store.save_path.read_bytes(),
                                  self.store.observation_path.read_bytes()))

    def migrate(self, old, version=6, suffix='copy'):
        source = self.root / f'legacy-{version}-{suffix}.json'
        source.write_text(json.dumps(old), encoding='utf-8')
        before = source.read_bytes()
        destination = engine.GameStore(self.root / f'current-{version}-{suffix}.json')
        public = destination.execute(f'import-v{version}', str(source))
        self.assertEqual(source.read_bytes(), before)
        return destination, public


class QualityMilestoneTests(CollectionHarness):
    def test_current_schema_keeps_quality_progress_and_marks_current_trades(self):
        state = fixture()
        self.assertEqual(engine.VERSION, 9)
        self.assertEqual(state['version'], engine.VERSION)
        self.assertIsNone(state['collection_upgrade'])
        state['inventory'] = [item('wrench', 1)]
        state['discovered'] = ['wrench']
        state['next_item'] = 2
        state['rng'] = rng_for(99)
        self.write(state)
        public = self.store.execute('sell', 'I001')
        self.assertEqual(public['version'], engine.VERSION)
        self.assertEqual(public['last_roll']['rules_version'], engine.TRADE_RULES_VERSION)
        self.assertEqual(public['negotiation']['rules_version'], engine.TRADE_RULES_VERSION)
        self.assertEqual(public['negotiation']['origin_rules_version'], engine.TRADE_RULES_VERSION)

    def test_first_week_69_70_inclusive_boundary_and_personal_total(self):
        state = cabinet(fixture(), ['wrench', 'lamp'], [69, 70])
        public = self.write(state)
        progress = public['collection_progress']
        self.assertEqual((progress['personal_count'], progress['qualified_count'],
                          progress['min_condition']), (2, 1, 70))
        self.assertFalse(progress['legacy_grace'])
        self.assertEqual(public_goals(state)['collection']['current'], 1)
        self.assertFalse(public_goals(state)['collection']['met'])
        state['collection'][0]['condition'] = 70
        self.assertEqual(public_goals(state)['collection']['current'], 2)
        self.assertTrue(public_goals(state)['collection']['met'])

    def test_first_week_close_uses_quality_after_operating_cost(self):
        for qualities, expected in [([69, 70], 'missed'), ([70, 70], 'won')]:
            with self.subTest(qualities=qualities):
                state = cabinet(fixture(), ['wrench', 'lamp'], qualities)
                state.update(day=7, credits=650 + engine._operating_cost(state))
                state['walkins']['day'] = 7
                self.write(state)
                public = self.store.execute('endday')
                self.assertEqual(public['credits'], 650)
                self.assertEqual(public['campaign']['first_week_result'], expected)
                self.assertEqual(public['phase'], 'week_summary')
                self.assertEqual([m['id'] for m in public['campaign']['completed_milestones']],
                                 ['first_week'] if expected == 'won' else [])

    def test_low_quality_collect_still_allowed_without_qualifying_for_goal(self):
        state = fixture()
        state['inventory'] = [item('wrench', 1, 5)]
        state['discovered'] = ['wrench']
        state['next_item'] = 2
        self.write(state)
        before = self.store.load()
        public = self.store.execute('collect', 'I001')
        self.assertEqual(len(public['collection']), 1)
        self.assertEqual(public['collection_progress']['personal_count'], 1)
        self.assertEqual(public['collection_progress']['qualified_count'], 0)
        quality = public['collection'][0]['collection_quality']
        self.assertFalse(quality['condition_met'])
        self.assertFalse(quality['counted'])
        self.assertTrue(quality['reason'])
        self.assertEqual(self.store.load()['rng'], before['rng'])
        self.assertEqual(public['energy'], before['energy'] - 1)

    def test_neighborhood_needs_five_at_75_and_three_qualified_categories(self):
        state = cabinet(fixture(1), ['wrench', 'lamp', 'welder', 'needle', 'coffee', 'cleaner'],
                        [75, 75, 75, 75, 75, 74])
        goals = public_goals(state)
        self.assertEqual(goals['collection']['target'], 5)
        self.assertEqual(goals['collection']['current'], 5)
        self.assertEqual(goals['collection_categories']['target'], 3)
        self.assertEqual(goals['collection_categories']['current'], 2)
        engine._check_milestones(state)
        self.assertEqual(len(state['milestones']), 1)
        state['collection'][-1]['condition'] = 75
        engine._check_milestones(state)
        self.assertEqual([m['id'] for m in state['milestones']], ['first_week', 'neighborhood'])

    def test_lighthouse_has_no_four_category_requirement(self):
        # Five tools and four artifacts form two qualified themes in two categories.
        ids = ['wrench', 'lamp', 'welder', 'needle', 'hammer', 'coffee', 'music', 'dawn', 'kettle']
        state = cabinet(fixture(2), ids, 80)
        goals = public_goals(state)
        self.assertEqual(goals['collection']['target'], 9)
        self.assertEqual(goals['quality_themes']['target'], 1)
        self.assertNotIn('collection_categories', goals)
        engine._check_milestones(state)
        self.assertEqual(state['milestones'][-1]['id'], 'lighthouse')

    def test_lighthouse_requires_one_three_item_qualified_theme(self):
        ids = ['wrench', 'lamp', 'coffee', 'music', 'cleaner', 'bee', 'moss', 'seed', 'map']
        state = cabinet(fixture(2), ids, 80)
        self.assertEqual(public_goals(state)['quality_themes']['current'], 0)
        engine._check_milestones(state)
        self.assertEqual(len(state['milestones']), 2)
        state = cabinet(state, ids + ['welder'], [80] * 9 + [79])
        self.assertEqual(public_goals(state)['quality_themes']['current'], 0)
        state['collection'][-1]['condition'] = 80
        self.assertEqual(public_goals(state)['quality_themes']['current'], 1)
        engine._check_milestones(state)
        self.assertEqual(state['milestones'][-1]['id'], 'lighthouse')

    def test_landmark_needs_15_at_85_all_five_categories_and_three_themes(self):
        ids = ['wrench', 'lamp', 'welder', 'needle', 'hammer',
               'coffee', 'music', 'dawn', 'kettle',
               'cleaner', 'bee', 'snail', 'moss', 'seed', 'map']
        state = cabinet(fixture(3), ids, 85)
        goals = public_goals(state)
        self.assertEqual((goals['collection']['target'], goals['collection_categories']['target'],
                          goals['quality_themes']['target']), (15, 5, 3))
        self.assertEqual(goals['quality_themes']['current'], 3)
        for index in (14, 11):
            with self.subTest(below_boundary=ids[index]):
                bad = copy.deepcopy(state)
                bad['collection'][index]['condition'] = 84
                engine._check_milestones(bad)
                self.assertEqual(len(bad['milestones']), 3)
        engine._check_milestones(state)
        self.assertEqual(state['milestones'][-1]['id'], 'landmark')

    def test_landmark_category_and_theme_requirements_independent_of_quantity(self):
        # 16 qualifying objects, four categories, four themes: missing signal blocks it.
        ids = [row[0] for row in engine.CATALOG if row[3] != 'signal'][:16]
        state = cabinet(fixture(3), ids, 85)
        self.assertGreaterEqual(public_goals(state)['collection']['current'], 15)
        self.assertEqual(public_goals(state)['collection_categories']['current'], 4)
        engine._check_milestones(state)
        self.assertEqual(len(state['milestones']), 3)
        # Fifteen, all categories, but only two themes (5 + 5 + 2 + 2 + 1).
        ids = ['wrench', 'lamp', 'welder', 'needle', 'hammer',
               'coffee', 'music', 'dawn', 'kettle', 'clock',
               'cleaner', 'bee', 'moss', 'seed', 'map']
        state = cabinet(fixture(3), ids, 85)
        self.assertEqual(public_goals(state)['quality_themes']['current'], 2)
        engine._check_milestones(state)
        self.assertEqual(len(state['milestones']), 3)

    def test_quality_themes_count_distinct_catalog_objects_only(self):
        state = cabinet(fixture(2), ['wrench', 'lamp', 'welder'], 80)
        self.assertEqual(public_goals(state)['quality_themes']['current'], 1)
        state['collection'][2] = item('wrench', 3, 80, True)
        self.assertEqual(public_goals(state)['quality_themes']['current'], 0)
        with self.assertRaises(engine.GameError):
            engine._validate_state(state)

    def test_ordinary_sets_and_all_five_perks_keep_any_quality_semantics(self):
        for kind in engine.KINDS:
            with self.subTest(kind=kind):
                ids = [row[0] for row in engine.CATALOG if row[3] == kind][:3]
                current = cabinet(fixture(), ids, 5)
                old = cabinet(fixture(module=legacy), ids, 5, legacy)
                self.assertTrue(engine._has_set(current, kind))
                self.assertEqual(engine.observation(current)['collection_sets'],
                                 legacy.observation(old)['collection_sets'])
                self.assertEqual(engine._max_energy(current), legacy._max_energy(old))
                self.assertEqual(engine._operating_cost(current), legacy._operating_cost(old))
                self.assertEqual(engine._repair_cost(current, current['collection'][0]),
                                 legacy._repair_cost(old, old['collection'][0]))
                for supplier in engine.SUPPLIERS:
                    self.assertEqual(engine._stock_limit(current, supplier), legacy._stock_limit(old, supplier))
                self.assertEqual(engine.observation(current)['collection_progress']['qualified_count'], 0)

    def test_earned_milestones_survive_current_quality_drop(self):
        state = cabinet(fixture(3), ['wrench', 'lamp', 'welder'], 5)
        earned = copy.deepcopy(state['milestones'])
        engine._check_milestones(state)
        self.assertEqual(state['milestones'], earned)
        self.assertEqual(engine.observation(state)['campaign']['completed_milestones'], earned)

    def test_longhaul_quality_increases_to_cap_without_resetting_history(self):
        state = cabinet(fixture(4), [row[0] for row in engine.CATALOG], 100)
        for voyage in range(1, 8):
            goals = public_goals(state)
            progress = engine.observation(state)['collection_progress']
            self.assertEqual(progress['min_condition'], min(90, 85 + voyage))
            self.assertEqual(goals['collection']['target'], min(24, 15 + 2 * voyage))
            self.assertEqual(goals['collection_categories']['target'], 5)
            self.assertEqual(goals['quality_themes']['target'], 4 if voyage == 1 else 5)
            milestone = engine._next_milestone(state)
            state['milestones'].append(dict(id=milestone['id'], title=milestone['title'], day=8))


class ReplacementTests(CollectionHarness):
    def replacement_fixture(self, condition=80):
        state = cabinet(fixture(), ['wrench'], 50)
        state['inventory'] = [item('wrench', 2, condition)]
        state['next_item'] = 3
        return state

    def test_explicit_better_copy_swap_preserves_both_full_item_records(self):
        state = self.replacement_fixture()
        state['collection'][0].update(base_value=81, price=123, repairs=1,
                                      last_repair_day=1, last_sale_day=1)
        state['inventory'][0].update(base_value=94, price=234, repairs=2,
                                    last_repair_day=1, last_sale_day=1,
                                    origin=engine.SUPPLIERS['curated']['name'])
        self.write(state)
        before = self.store.load()
        public = self.store.execute('replace-collection', 'I002')
        after = self.store.load()
        self.assertEqual(after['collection'], [dict(before['inventory'][0], collected=True)])
        self.assertEqual(after['inventory'], [dict(before['collection'][0], collected=False)])
        for key in ('rng', 'credits', 'reputation', 'stats', 'next_item', 'next_crate', 'roll_history',
                    'roll_seq', 'supplier_stock', 'walkins', 'visitors', 'discovered', 'milestones'):
            self.assertEqual(after[key], before[key], key)
        self.assertEqual(after['energy'], before['energy'] - 1)
        self.assertEqual(public['collection_progress']['qualified_count'], 1)
        self.assertEqual(public['collection'][0]['id'], 'I002')
        self.assertEqual(public['inventory'][0]['id'], 'I001')
        self.assertTrue(public['inventory'][0]['repair_attempted_today'])
        self.assertTrue(public['inventory'][0]['sale_attempted_today'])
        self.reject('sell', 'I001')
        self.reject('repair', 'I001')
        self.reject('price', 'I002', '10')
        self.reject('sell', 'I002')

    def test_replace_accepts_strict_one_point_improvement(self):
        self.write(self.replacement_fixture(condition=51))
        public = self.store.execute('replace-collection', 'I002')
        self.assertEqual(public['collection'][0]['condition'], 51)
        self.assertEqual(public['collection_progress']['qualified_count'], 0)

    def test_equal_worse_wrong_catalog_missing_and_zero_energy_fail_atomically(self):
        for quality in (5, 49, 50):
            with self.subTest(quality=quality):
                self.write(self.replacement_fixture(quality))
                self.reject('replace-collection', 'I002')
        state = self.replacement_fixture()
        state['inventory'][0] = item('lamp', 2, 100)
        state['discovered'].append('lamp')
        self.write(state)
        self.reject('replace-collection', 'I002')
        self.reject('replace-collection', 'I999')
        self.reject('replace-collection', 'I001')
        state = self.replacement_fixture()
        state['energy'] = 0
        self.write(state)
        self.reject('replace-collection', 'I002')

    def test_duplicate_collect_does_not_implicitly_replace(self):
        self.write(self.replacement_fixture())
        self.reject('collect', 'I002')
        self.assertEqual(self.store.load()['collection'][0]['id'], 'I001')

    def test_full_inventory_swap_is_allowed_and_bot_set_not_rewarded_twice(self):
        state = cabinet(fixture(), ['cleaner', 'bee', 'snail'], 5)
        state['inventory'] = [item('cleaner', 4, 80)] + [item('wrench', n) for n in range(5, 11)]
        state['next_item'] = 11
        state['discovered'].append('wrench')
        self.write(state)
        before = self.store.load()
        public = self.store.execute('replace-collection', 'I004')
        self.assertEqual(len(public['inventory']), public['capacity'])
        self.assertEqual(public['energy'], before['energy'] - 1)
        self.assertEqual(public['max_energy'], 13)
        self.assertEqual(public['collection_sets'], engine.observation(before)['collection_sets'])
        self.assertEqual(self.store.load()['rng'], before['rng'])

    def test_pending_negotiation_locks_candidate_but_is_not_reset(self):
        state = self.replacement_fixture()
        state['rng'] = rng_for(99)
        self.write(state)
        public = self.store.execute('sell', 'I002')
        self.assertIsNotNone(public['negotiation'])
        self.reject('replace-collection', 'I002')
        self.reject('repair', 'I002')
        pending = self.store.load()['negotiation']
        self.store.execute('decline', 'I002')
        public = self.store.execute('replace-collection', 'I002')
        self.assertTrue(public['collection'][0]['sale_attempted_today'])
        self.assertEqual(pending['item_id'], 'I002')

    def test_replacement_can_complete_stage_without_granting_cash_or_rng(self):
        state = cabinet(fixture(1), ['wrench', 'lamp', 'welder', 'coffee', 'cleaner'],
                        [75, 75, 75, 75, 74])
        state['inventory'] = [item('cleaner', 6, 75)]
        state['next_item'] = 7
        self.write(state)
        before = self.store.load()
        public = self.store.execute('replace-collection', 'I006')
        self.assertEqual(public['campaign']['completed_milestones'][-1]['id'], 'neighborhood')
        self.assertEqual(public['campaign']['next_milestone']['id'], 'lighthouse')
        self.assertEqual(public['collection_progress']['min_condition'], 80)
        self.assertEqual(public['collection_progress']['qualified_count'], 0)
        self.assertEqual(public['credits'], before['credits'])
        self.assertEqual(self.store.load()['rng'], before['rng'])
        self.assertEqual(public['energy'], before['energy'] - 1)

    def test_public_replacement_explains_available_and_blocked_paths(self):
        state = self.replacement_fixture()
        public = self.write(state)
        replacement = public['inventory'][0]['collection_replacement']
        self.assertTrue(replacement['available'])
        self.assertEqual(replacement['cabinet_item_id'], 'I001')
        self.assertEqual(replacement['cabinet_condition'], 50)
        self.assertEqual(replacement['energy_cost'], 1)
        self.assertEqual(replacement['command'], 'replace-collection I002')
        state['inventory'][0]['condition'] = 50
        blocked = self.write(state)['inventory'][0]['collection_replacement']
        self.assertFalse(blocked['available'])
        self.assertTrue(blocked['reasons'])


class CabinetRepairTests(CollectionHarness):
    def repair_fixture(self, condition=69, seed=0):
        state = cabinet(fixture(), ['wrench'], condition)
        state['rng'] = random.Random(seed).getstate()
        return state

    def test_cabinet_repair_uses_same_randomness_price_cost_and_limits_as_inventory(self):
        cabinet_state = self.repair_fixture()
        inventory_state = copy.deepcopy(cabinet_state)
        inventory_state['inventory'] = [dict(inventory_state['collection'].pop(), collected=False)]
        expected = copy.deepcopy(inventory_state)
        engine.apply_command(expected, 'repair', ['I001'])
        self.write(cabinet_state)
        before = self.store.load()
        public = self.store.execute('repair', 'I001')
        after = self.store.load()
        self.assertEqual(after['collection'][0], dict(expected['inventory'][0], collected=True))
        self.assertEqual(after['rng'], json.loads(json.dumps(expected['rng'])))
        self.assertEqual(after['energy'], before['energy'] - 2)
        self.assertEqual(after['credits'], before['credits'] - engine._repair_cost(before, before['collection'][0]))
        self.assertEqual(public['collection_progress']['qualified_count'], 1)
        self.assertEqual(public['last_event']['type'], 'repair')
        self.assertFalse(public['collection'][0]['repair']['available'])
        self.reject('repair', 'I001')
        self.reject('price', 'I001', '10')
        self.reject('sell', 'I001')
        self.assertEqual(public['inventory'], [])

    def test_repair_failure_drops_quality_preserves_history_and_can_unqualify(self):
        state = self.repair_fixture(condition=70, seed=1)
        state.update(day=8, first_week_result='won')
        state['walkins']['day'] = 8
        state['milestones'] = [dict(id=engine.MILESTONES[0]['id'],
                                    title=engine.MILESTONES[0]['title'], day=7)]
        state['collection'][0]['condition'] = 75
        self.write(state)
        before = self.store.load()
        public = self.store.execute('repair', 'I001')
        after = self.store.load()
        self.assertLess(after['collection'][0]['condition'], 75)
        self.assertEqual(after['collection'][0]['repairs'], 1)
        self.assertEqual(after['collection'][0]['last_repair_day'], 8)
        self.assertEqual(after['milestones'], before['milestones'])
        self.assertEqual(after['roll_history'], before['roll_history'])
        self.assertEqual(after['collection'][0]['price'], before['collection'][0]['price'])
        self.assertEqual(public['collection_progress']['qualified_count'], 0)
        self.assertIn('失手', public['last_event']['text'])
        self.assertEqual(public['energy'], before['energy'] - 2)
        self.assertEqual(public['credits'], before['credits'] - engine._repair_cost(before, before['collection'][0]))

    def test_repair_total_two_attempts_one_per_day_and_atomic_resource_errors(self):
        for changes in ({'condition': 100}, {'repairs': 2}, {'last_repair_day': 1}):
            with self.subTest(changes=changes):
                state = self.repair_fixture()
                state['collection'][0].update(changes)
                self.write(state)
                self.reject('repair', 'I001')
        for key, value in [('energy', 1), ('credits', 0)]:
            state = self.repair_fixture()
            state[key] = value
            self.write(state)
            self.reject('repair', 'I001')
        state = self.repair_fixture(condition=5, seed=1)
        self.write(state)
        self.store.execute('repair', 'I001')
        self.reject('repair', 'I001')
        self.store.execute('endday')
        self.store.execute('repair', 'I001')
        self.store.execute('endday')
        self.reject('repair', 'I001')

    def test_cabinet_repair_can_finish_milestone_and_updates_new_threshold(self):
        state = cabinet(fixture(1), ['wrench', 'lamp', 'welder', 'coffee', 'cleaner'],
                        [75, 75, 75, 75, 74])
        state['rng'] = random.Random(0).getstate()
        self.write(state)
        public = self.store.execute('repair', 'I005')
        self.assertEqual(public['campaign']['completed_milestones'][-1]['id'], 'neighborhood')
        self.assertEqual(public['campaign']['next_milestone']['id'], 'lighthouse')
        self.assertEqual(public['collection_progress']['min_condition'], 80)
        self.assertEqual(public['collection_progress']['qualified_count'], 1)
        self.assertEqual(public['collection'][-1]['id'], 'I005')

    def test_cabinet_repair_preserves_other_items_pending_negotiation(self):
        state = cabinet(fixture(), ['lamp'], 50)
        state['inventory'] = [item('wrench', 2)]
        state['discovered'].append('wrench')
        state['next_item'] = 3
        state['rng'] = rng_for(99)
        self.write(state)
        self.store.execute('sell', 'I002')
        before = self.store.load()
        self.assertIsNotNone(before['negotiation'])
        self.store.execute('repair', 'I001')
        after = self.store.load()
        for key in ('negotiation', 'roll_history', 'roll_seq', 'walkins', 'inventory', 'visitors'):
            self.assertEqual(after[key], before[key], key)
        self.assertEqual(after['energy'], before['energy'] - 2)
        public = self.store.execute('accept', 'I002')
        self.assertIsNone(public['negotiation'])
        self.assertEqual(public['credits'], after['credits'] + before['negotiation']['counter_offer'])

    def test_public_repair_eligibility_available_for_cabinet_and_inventory(self):
        state = self.repair_fixture()
        state['inventory'] = [item('lamp', 2, 60)]
        state['discovered'].append('lamp')
        state['next_item'] = 3
        public = self.write(state)
        for row in public['collection'] + public['inventory']:
            self.assertTrue(row['repair']['available'])
            self.assertEqual(row['repair']['cost'], row['repair_cost'])
            self.assertEqual(row['repair']['energy_cost'], 2)
            self.assertEqual(row['repair']['command'], f"repair {row['id']}")
        self.assertEqual(self.store.execute('inspect', 'I001')['repair'], public['collection'][0]['repair'])


class CollectionMigrationTests(CollectionHarness):
    def test_import_v1_to_v6_copy_only_preserves_frozen_conversion_fields(self):
        for version in range(1, 7):
            with self.subTest(version=version):
                module = importlib.import_module(f'_legacy_v{version}')
                old = module.new_state(17)
                module.apply_command(old, 'buy', ['salvage'])
                module.apply_command(old, 'open', ['C001'])
                module.apply_command(old, 'buy', ['salvage'])
                raw = json.dumps(old).encode()
                baseline = json.loads(raw) if version == 6 else json.loads(json.dumps(
                    getattr(legacy, f'migrate_v{version}')(raw)))
                store, public = self.migrate(old, version)
                current = store.load()
                allowed_changes = {'version', 'revision', 'last_event', 'event_seq', 'log'}
                for key, value in baseline.items():
                    if key not in allowed_changes:
                        self.assertEqual(current[key], value, (version, key))
                self.assertEqual(current['version'], engine.VERSION)
                self.assertEqual(current['collection_upgrade'], dict(from_version=version,
                    source_day=baseline['day'], source_phase=baseline['phase'], legacy_stage_index=0))
                self.assertEqual(public['collection_progress']['min_condition'], 0)
                self.assertTrue(public['collection_progress']['legacy_grace'])
                self.assertEqual(current['log'][:len(baseline['log'])], baseline['log'])
                source = self.root / f'legacy-{version}-copy.json'
                with self.assertRaises(engine.GameError):
                    store.execute(f'import-v{version}', str(source))

    def test_preweek_grace_uses_old_count_then_next_stage_uses_quality(self):
        old = cabinet(fixture(module=legacy), ['wrench', 'lamp'], 5, legacy)
        old.update(day=7, credits=100000, reputation=99)
        old['walkins']['day'] = 7
        old['upgrades'] = {key: 3 for key in legacy.UPGRADE_RULES}
        store, _ = self.migrate(old)
        public = store.execute('endday')
        self.assertEqual(public['campaign']['first_week_result'], 'won')
        self.assertEqual(public['campaign']['next_milestone']['id'], 'neighborhood')
        self.assertFalse(public['collection_progress']['legacy_grace'])
        self.assertEqual(public['collection_progress']['min_condition'], 75)
        self.assertEqual(public['collection_progress']['qualified_count'], 0)
        marker = copy.deepcopy(store.load()['collection_upgrade'])
        raw = store.save_path.read_bytes()
        for command in ('status', 'codex', 'market', 'visitors'):
            engine.GameStore(store.save_path).execute(command)
        self.assertEqual(store.save_path.read_bytes(), raw)
        continued = store.execute('continue')
        self.assertFalse(continued['collection_progress']['legacy_grace'])
        self.assertEqual(store.load()['collection_upgrade'], marker)

    def test_grace_only_covers_current_milestone_not_multiple_cascaded_stages(self):
        old = cabinet(fixture(1, legacy), [row[0] for row in legacy.CATALOG], 5, legacy)
        store, public = self.migrate(old)
        self.assertEqual(len(store.load()['milestones']), 1)
        self.assertTrue(public['collection_progress']['legacy_grace'])
        self.assertEqual(public['campaign']['next_milestone']['id'], 'neighborhood')
        marker = copy.deepcopy(store.load()['collection_upgrade'])
        public = store.execute('endday')
        self.assertEqual([row['id'] for row in public['campaign']['completed_milestones']],
                         ['first_week', 'neighborhood'])
        self.assertEqual(public['campaign']['next_milestone']['id'], 'lighthouse')
        self.assertFalse(public['collection_progress']['legacy_grace'])
        self.assertEqual(public['collection_progress']['qualified_count'], 0)
        self.assertEqual(store.load()['collection_upgrade'], marker)
        store = engine.GameStore(store.save_path)
        self.assertFalse(store.execute('status')['collection_progress']['legacy_grace'])
        with self.assertRaises(engine.GameError):
            engine.GameStore(self.root / 'no-reimport.json').execute('import-v8', str(store.save_path))
        with self.assertRaises(engine.GameError):
            engine.GameStore(self.root / 'no-downcast.json').execute('import-v6', str(store.save_path))

    def test_grace_persists_across_days_and_reads_until_its_stage_is_earned(self):
        old = cabinet(fixture(module=legacy), ['wrench'], 5, legacy)
        old['credits'] = 1000
        store, _ = self.migrate(old)
        marker = copy.deepcopy(store.load()['collection_upgrade'])
        for day in range(2, 5):
            public = store.execute('endday')
            self.assertEqual(public['day'], day)
            self.assertTrue(public['collection_progress']['legacy_grace'])
            self.assertEqual(public['collection_progress']['min_condition'], 0)
            self.assertEqual(public['collection_progress']['qualified_count'], 1)
            self.assertEqual(store.load()['collection_upgrade'], marker)
            raw = store.save_path.read_bytes()
            store = engine.GameStore(store.save_path)
            store.execute('status')
            self.assertEqual(store.save_path.read_bytes(), raw)

    def test_invalid_grace_markers_fail_instead_of_silently_resetting(self):
        store, _ = self.migrate(fixture(module=legacy))
        valid = store.load()
        for key, value in [('legacy_stage_index', 1), ('legacy_stage_index', True),
                           ('from_version', 8), ('source_day', 0), ('source_phase', 'won')]:
            with self.subTest(key=key, value=value):
                corrupted = copy.deepcopy(valid)
                corrupted['collection_upgrade'][key] = value
                with self.assertRaises(engine.GameError):
                    engine._validate_state(corrupted)
        corrupted = copy.deepcopy(valid)
        del corrupted['collection_upgrade']
        with self.assertRaises(engine.GameError):
            engine._validate_state(corrupted)

    def test_past_first_week_outcome_never_retroactively_changed(self):
        for result in ('won', 'missed'):
            old = cabinet(fixture(module=legacy), ['wrench', 'lamp'], 5, legacy)
            old.update(day=7, phase='week_summary', first_week_result=result, credits=1000)
            old['walkins']['day'] = 7
            if result == 'won':
                old['milestones'] = [dict(id=legacy.MILESTONES[0]['id'],
                    title=legacy.MILESTONES[0]['title'], day=7)]
            store, public = self.migrate(old, suffix=result)
            self.assertEqual(public['campaign']['first_week_result'], result)
            public = store.execute('continue')
            self.assertEqual(public['campaign']['first_week_result'], result)

    def test_v6_pending_trade_and_rolls_survive_copy_and_final_resolution(self):
        for action in ('accept', 'offer'):
            with self.subTest(action=action):
                old = cabinet(fixture(module=legacy), ['wrench'], 50, legacy)
                old['inventory'] = [item('wrench', 2, module=legacy)]
                old['next_item'] = 3
                old['rng'] = rng_for(99, 50)
                legacy.apply_command(old, 'sell', ['I002'])
                self.assertIsNotNone(old['negotiation'])
                store, public = self.migrate(old, suffix=action)
                migrated = store.load()
                for field in ('roll_seq', 'roll_history', 'inventory', 'walkins', 'visitors'):
                    self.assertEqual(migrated[field], json.loads(json.dumps(old[field])))
                expected_pending = copy.deepcopy(old['negotiation'])
                expected_pending['rules_version'] = engine.TRADE_RULES_VERSION
                self.assertEqual(migrated['negotiation'], expected_pending)
                self.assertEqual(migrated['negotiation']['context']['budget'], old['walkins']['budget'])
                self.assertEqual(public['negotiation']['rules_version'], engine.TRADE_RULES_VERSION)
                self.assertEqual(public['negotiation']['origin_rules_version'], 6)
                before = (store.save_path.read_bytes(), store.observation_path.read_bytes())
                with self.assertRaisesRegex(engine.GameError, '还价|等待|待谈'):
                    store.execute('replace-collection', 'I002')
                self.assertEqual(before, (store.save_path.read_bytes(), store.observation_path.read_bytes()))
                self.assertFalse(public['inventory'][0]['collection_replacement']['available'])
                price = old['negotiation']['counter_offer'] + 1
                args = ['I002'] + ([str(price)] if action == 'offer' else [])
                expected = copy.deepcopy(old)
                legacy.apply_command(expected, action, args)
                if action == 'offer':
                    expected['roll_history'][-1]['rules_version'] = engine.TRADE_RULES_VERSION
                public = store.execute(action, *args)
                actual = store.load()
                for field in ('credits', 'energy', 'rng', 'roll_history', 'roll_seq', 'negotiation',
                              'inventory', 'walkins', 'stats', 'reputation'):
                    self.assertEqual(actual[field], json.loads(json.dumps(expected[field])), field)
                self.assertEqual(public['last_roll']['rules_version'], engine.TRADE_RULES_VERSION if action == 'offer' else 6)

    def test_relabeling_v8_as_v6_cannot_regrant_grace(self):
        for stage in (0, 1):
            with self.subTest(stage=stage):
                old = fixture(stage, legacy)
                store, _ = self.migrate(old, suffix=f'relabel-{stage}')
                current = store.load()
                current['version'] = 6
                relabeled = self.root / f'relabeled-{stage}.json'
                relabeled.write_text(json.dumps(current), encoding='utf-8')
                before = relabeled.read_bytes()
                destination = engine.GameStore(self.root / f'no-new-grace-{stage}.json')
                with self.assertRaises(engine.GameError):
                    destination.execute('import-v6', str(relabeled))
                self.assertFalse(destination.save_path.exists())
                self.assertEqual(relabeled.read_bytes(), before)

    def test_import_rejects_in_place_public_projection_and_existing_target(self):
        old = fixture(module=legacy)
        source = self.root / 'original.json'
        source.write_text(json.dumps(old), encoding='utf-8')
        before = source.read_bytes()
        with self.assertRaises(engine.GameError):
            engine.GameStore(source).execute('import-v6', str(source))
        self.assertEqual(source.read_bytes(), before)
        projection = self.root / 'public.json'
        projection.write_text(json.dumps(legacy.observation(old)), encoding='utf-8')
        with self.assertRaises(engine.GameError):
            engine.GameStore(self.root / 'copy-public.json').execute('import-v6', str(projection))
        destination = engine.GameStore(self.root / 'occupied.json')
        destination.observation_path.write_text('{}', encoding='utf-8')
        with self.assertRaises(engine.GameError):
            destination.execute('import-v6', str(source))
        self.assertFalse(destination.save_path.exists())


class CollectionPrivacyAndTradeTests(CollectionHarness):
    def assert_public_private_boundary(self, public, known=()):
        text = json.dumps(public, ensure_ascii=False)
        for row in engine.CATALOG:
            if row[0] not in known:
                self.assertNotIn(row[1], text)
                self.assertNotIn(row[5], text)
        forbidden = {'rng', 'base_value', 'cargo', 'catalog_id', 'budget', 'context'}
        def visit(node):
            if isinstance(node, dict):
                self.assertTrue(forbidden.isdisjoint(node), set(node) & forbidden)
                if 'art_id' in node:
                    self.assertIn(node['art_id'], known)
                for value in node.values():
                    visit(value)
            elif isinstance(node, list):
                for value in node:
                    visit(value)
        visit(public)

    def test_new_quality_sections_do_not_reveal_unknown_catalog_identities(self):
        state = fixture()
        self.assert_public_private_boundary(self.write(state))
        state = cabinet(state, ['wrench', 'lamp'], [69, 70])
        public = self.write(state)
        self.assert_public_private_boundary(public, {'wrench', 'lamp'})
        self.assertEqual(public['codex']['discovered'], 2)
        for entry in public['codex']['entries']:
            if not entry['discovered']:
                self.assertEqual(set(entry), {'slot', 'discovered', 'collected'})

    def test_sealed_unknown_cargo_does_not_change_quality_or_discovery(self):
        baseline = None
        for key in ('whale', 'tree', 'hammer', 'letter'):
            state = fixture()
            cargo = item(key, 1)
            cargo.pop('id')
            cargo.pop('price')
            state['crates'] = [dict(id='C001', supplier='salvage', name='漂流回收箱', cargo=cargo)]
            state['next_crate'] = 2
            public = self.write(state)
            self.assert_public_private_boundary(public)
            self.assertEqual(public['collection_progress']['qualified_count'], 0)
            if baseline is not None:
                self.assertEqual(public, baseline)
            baseline = public

    def test_repair_and_replacement_forecasts_ignore_private_value_and_budget(self):
        state = cabinet(fixture(), ['wrench'], 50)
        state['inventory'] = [item('wrench', 2, 80)]
        state['next_item'] = 3
        other = copy.deepcopy(state)
        for row in other['collection'] + other['inventory']:
            row['base_value'] *= 2
        other['walkins']['budget'] = 60
        for visitor in other['visitors']:
            visitor['budget'] = visitor['budget_range'][0]
        self.assertEqual(engine.observation(state), engine.observation(other))

    def test_trade_constants_and_within_budget_results_match_frozen_v6(self):
        for field in ('CATALOG', 'SUPPLIERS', 'UPGRADE_RULES', 'EVENTS', 'SET_RULES',
                      'OPERATING_COST', 'WALKIN_DAILY_LIMIT', 'WALKIN_BUDGET_RANGE',
                      'WALKIN_MIN_CONDITION', 'COUNTER_MAX_RATIO'):
            self.assertEqual(getattr(engine, field), getattr(legacy, field), field)
        for roll in (1, 50, 99, 100):
            with self.subTest(roll=roll):
                current, old = fixture(), fixture(module=legacy)
                for state, module in ((current, engine), (old, legacy)):
                    state['inventory'] = [item('wrench', 1, module=module)]
                    state['next_item'] = 2
                    state['discovered'] = ['wrench']
                    state['rng'] = rng_for(roll)
                    state['walkins']['budget'] = 120
                    module.apply_command(state, 'sell', ['I001'])
                for record in old['roll_history']:
                    record['rules_version'] = engine.TRADE_RULES_VERSION
                if old['negotiation']:
                    old['negotiation'].update(rules_version=engine.TRADE_RULES_VERSION, origin_rules_version=engine.TRADE_RULES_VERSION)
                for field in ('credits', 'energy', 'rng', 'roll_history', 'roll_seq', 'negotiation',
                              'inventory', 'walkins', 'visitors', 'stats', 'reputation'):
                    self.assertEqual(current[field], old[field], (roll, field))
                current_rules = engine.observation(current)['trade_rules']
                old_rules = legacy.observation(old)['trade_rules']
                for key in old_rules:
                    if key != 'initial_chance_formula':
                        self.assertEqual(current_rules[key], old_rules[key], key)


if __name__ == '__main__':
    unittest.main()
