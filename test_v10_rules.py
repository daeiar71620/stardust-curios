"""Native-v10 boundaries exercised only with synthetic temporary games.

All expected prices, deadlines and thresholds below are independent contractual
values. Private cargo inspection is restricted to fixtures created by this file.
"""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import engine
from native_test_helpers import sync_stage_history


FEES = {'workbench': (0, 0, 1, 3), 'shelf': (0, 1, 2, 4), 'display': (0, 1, 3, 5)}
BREAKDOWN_KEYS = {'base', 'event_delta', 'plant_discount', 'base_after_modifiers',
                  'facility_upkeep', 'facility_upkeep_from_day8',
                  'facility_upkeep_unlock_day', 'overdue_surcharge', 'total'}
HISTORY_KEYS = {'id', 'title', 'nominal_due_day', 'effective_due_day', 'unlocked_day',
                'missed_day', 'completed_day', 'status'}


def synthetic_item(key, number, condition=80, *, collected=True):
    row = engine.CATALOG_BY_ID[key]
    return dict(id=f'I{number:03}', catalog_id=row[0], name=row[1], rarity=row[2],
                kind=row[3], base_value=row[4], description=row[5], condition=condition,
                origin=engine.SUPPLIERS['salvage']['name'], collected=collected,
                repairs=0, last_sale_day=0, last_repair_day=0, price=90)


def put_collection(state, keys, condition=80):
    state['collection'] = [synthetic_item(key, index, condition)
                           for index, key in enumerate(keys, 1)]
    state['next_item'] = len(keys) + 1
    state['discovered'] = list(keys)
    return state


def fixture(day=1, completed=0, credits=10000):
    state = engine.new_state(42)
    state.update(day=day, credits=credits)
    state['walkins']['day'] = day
    if day > 7 or completed:
        state['first_week_result'] = 'won' if completed else 'missed'
    state['milestones'] = [dict(id=row['id'], title=row['title'], day=7)
                           for row in engine.MILESTONES[:completed]]
    sync_stage_history(state)
    state['supplier_stock']['focused'] = int(day >= 8)
    return state


class SyntheticV10Harness(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='v10-boundaries-synthetic-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.store = engine.GameStore(self.root / 'synthetic.json')

    def write(self, state):
        engine._validate_state(state)
        engine._atomic_json(self.store.save_path, state)
        return self.store.execute('status')

    def reject_unchanged(self, command, *args):
        before = (self.store.save_path.read_bytes(), self.store.observation_path.read_bytes())
        with self.assertRaises(engine.GameError):
            self.store.execute(command, *args)
        self.assertEqual(before, (self.store.save_path.read_bytes(),
                                  self.store.observation_path.read_bytes()))

    def assert_public(self, public, known=()):
        forbidden = {'rng', 'cargo', 'catalog_id', 'base_value', 'budget', 'context',
                     'next_item', 'next_crate', 'stage_history'}
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
        text = json.dumps(public, ensure_ascii=False)
        for row in engine.CATALOG:
            if row[0] not in known:
                self.assertNotIn(row[1], text)
                self.assertNotIn(row[5], text)


class V10VersionAndCostTests(SyntheticV10Harness):
    def test_v9_is_refused_before_any_save_or_observation_write(self):
        state = fixture()
        state['version'] = 9
        self.store.save_path.write_text(json.dumps(state), encoding='utf-8')
        self.store.observation_path.write_text('unchanged public sentinel', encoding='utf-8')
        for command, args in [('status', ()), ('market', ()), ('endday', ()),
                              ('buy', ('focused', 'tool')), ('new', ())]:
            with self.subTest(command=command):
                self.reject_unchanged(command, *args)
        self.store.observation_path.unlink()
        with mock.patch.object(engine, '_atomic_json') as writer:
            with self.assertRaises(engine.GameError):
                self.store.execute('status')
            writer.assert_not_called()
        self.assertFalse(self.store.observation_path.exists())

    def test_initial_contract_preserves_first_week_mechanics(self):
        state = engine.new_state(42)
        public = self.write(state)
        self.assertEqual((engine.VERSION, engine.TRADE_RULES_VERSION), (10, 10))
        self.assertEqual((public['day'], public['credits'], public['energy'], public['capacity']),
                         (1, 260, 12, 7))
        self.assertEqual(public['operating_cost'], 14)
        self.assertIsNone(public['last_settlement'])
        self.assertEqual(public['campaign']['completed_milestones'], [])
        history = public['campaign']['deadline_history']
        self.assertEqual(len(history), 1)
        self.assertEqual(set(history[0]), HISTORY_KEYS)
        self.assertEqual((history[0]['nominal_due_day'], history[0]['effective_due_day'],
                          history[0]['unlocked_day']), (7, 7, 1))
        suppliers = {row['id']: row for row in public['suppliers']}
        self.assertEqual([(suppliers[k]['cost'], suppliers[k]['energy_cost'], suppliers[k]['stock'])
                          for k in ('salvage', 'curated')], [(48, 1, 4), (110, 1, 2)])
        self.assertFalse(suppliers['focused']['unlocked'])
        self.assertEqual(suppliers['focused']['remaining'], 0)
        self.assert_public(public)

    def test_days_one_to_seven_never_charge_facilities_or_overdue(self):
        for day in range(1, 8):
            with self.subTest(day=day):
                state = fixture(day=day)
                state['upgrades'] = dict.fromkeys(FEES, 3)
                public = self.write(state)
                breakdown = public['operating_cost_breakdown']
                self.assertEqual(set(breakdown), BREAKDOWN_KEYS)
                self.assertEqual((breakdown['facility_upkeep'], breakdown['overdue_surcharge']), (0, 0))
                self.assertEqual(breakdown['facility_upkeep_from_day8'], 12)
                self.assertEqual(public['operating_cost'], 14)

    def test_each_facility_current_level_fee_is_charged_once(self):
        for facility, fees in FEES.items():
            for level, expected in enumerate(fees):
                with self.subTest(facility=facility, level=level):
                    state = fixture(day=8, completed=1)
                    state['upgrades'][facility] = level
                    public = self.write(state)
                    breakdown = public['operating_cost_breakdown']
                    self.assertEqual(breakdown['facility_upkeep'], expected)
                    self.assertEqual(breakdown['facility_upkeep_from_day8'], expected)
                    self.assertEqual(public['operating_cost'], 14 + expected)
                    row = next(row for row in public['upgrade_details'] if row['id'] == facility)
                    self.assertEqual((row['daily_upkeep'], row['daily_upkeep_from_day8']),
                                     (expected, expected))
                    following = fees[level + 1] if level < 3 else None
                    self.assertEqual(row['next_daily_upkeep'], following)
                    self.assertEqual(row['next_daily_upkeep_from_day8'], following)
                    self.assertEqual(row['upkeep_unlock_day'], 8)

    def test_upgrade_and_status_show_future_day_eight_fee(self):
        self.write(fixture(credits=1000))
        before = self.store.execute('status')
        row = next(row for row in before['upgrade_details'] if row['id'] == 'display')
        self.assertEqual((row['daily_upkeep'], row['next_daily_upkeep'],
                          row['next_daily_upkeep_from_day8']), (0, 0, 1))
        public = self.store.execute('upgrade', 'display')
        row = next(row for row in public['upgrade_details'] if row['id'] == 'display')
        self.assertEqual((row['daily_upkeep'], row['daily_upkeep_from_day8'],
                          row['next_daily_upkeep_from_day8']), (0, 1, 3))
        self.assertEqual(public['credits'], 880)
        self.assertEqual(public['operating_cost'], 14)
        self.assertEqual(public['operating_cost_breakdown']['facility_upkeep_from_day8'], 1)
        self.assertIn('8', public['last_event']['text'])
        self.assertEqual(self.store.execute('status'), public)

    def test_base_event_plant_facility_and_overdue_components_add_once(self):
        for event in engine.EVENTS:
            with self.subTest(event=event['id']):
                state = fixture(day=20, completed=1)
                state['upgrades'] = dict.fromkeys(FEES, 3)
                state['daily_event'] = copy.deepcopy(event)
                put_collection(state, ['moss', 'seed', 'sprout'], condition=5)
                state['energy'] = engine._max_energy(state)
                public = self.write(state)
                expected_base = max(4, 14 + event['cost_delta'] - 4)
                breakdown = public['operating_cost_breakdown']
                self.assertEqual(breakdown, dict(base=14, event_delta=event['cost_delta'],
                    plant_discount=4, base_after_modifiers=expected_base, facility_upkeep=12,
                    facility_upkeep_from_day8=12, facility_upkeep_unlock_day=8,
                    overdue_surcharge=6, total=expected_base + 18))
                self.assertEqual(public['operating_cost'], expected_base + 18)
                self.assertEqual(self.store.execute('market')['operating_cost_breakdown'], breakdown)

    def test_exact_and_insufficient_closing_cash_are_safe(self):
        for day in (1, 7, 8, 20):
            for short in (False, True):
                with self.subTest(day=day, short=short):
                    state = fixture(day=day)
                    state['upgrades'] = dict.fromkeys(FEES, 3)
                    cost = 14 + (12 + min(6, 2 * (day - 7)) if day >= 8 else 0)
                    state['credits'] = cost - int(short)
                    public = self.write(state)
                    self.assertEqual(public['operating_cost'], cost)
                    before = self.store.load()
                    closed = self.store.execute('endday')
                    self.assertEqual(closed['credits'], 0)
                    settlement = closed['last_settlement']
                    self.assertEqual(set(settlement), {'day', 'paid', 'breakdown', 'credits_after_payment'})
                    self.assertIs(settlement['paid'], not short)
                    self.assertEqual(settlement['day'], day)
                    self.assertEqual(settlement['breakdown'], public['operating_cost_breakdown'])
                    self.assertEqual(settlement['credits_after_payment'], 0)
                    self.assertEqual(closed['phase'], 'lost' if short else
                                     ('week_summary' if day == 7 else 'active'))
                    self.assertEqual(closed['stats']['days_traded'], before['stats']['days_traded'] + int(not short))
                    if short:
                        self.assertFalse(closed['campaign']['can_continue'])
                        self.assertEqual(self.store.load()['rng'], before['rng'])
                        self.reject_unchanged('endday')
                        self.reject_unchanged('continue')


class V10DeadlineTests(SyntheticV10Harness):
    def test_first_week_cannot_complete_before_day_seven_close(self):
        state = put_collection(fixture(day=6), ['wrench', 'lamp'], condition=70)
        self.write(state)
        self.assertTrue(self.store.execute('status')['campaign']['next_milestone']['ready'])
        public = self.store.execute('endday')
        self.assertEqual((public['day'], public['phase']), (7, 'active'))
        self.assertEqual(public['campaign']['completed_milestones'], [])
        public = self.store.execute('endday')
        self.assertEqual((public['day'], public['phase']), (7, 'week_summary'))
        self.assertEqual(public['campaign']['completed_milestones'][0]['day'], 7)
        self.assertIsNone(public['campaign']['deadline_history'][0]['missed_day'])

    def test_day_seven_qualification_uses_post_payment_cash(self):
        for cash, expected in ((663, 'missed'), (664, 'won')):
            with self.subTest(cash=cash):
                self.write(put_collection(fixture(day=7, credits=cash), ['wrench', 'lamp'], 70))
                public = self.store.execute('endday')
                self.assertEqual(public['credits'], cash - 14)
                self.assertEqual(public['campaign']['first_week_result'], expected)
                self.assertEqual(len(public['campaign']['completed_milestones']), int(expected == 'won'))
                row = public['campaign']['deadline_history'][0]
                self.assertEqual(row['missed_day'], 7 if expected == 'missed' else None)
                self.assertEqual(row['completed_day'], 7 if expected == 'won' else None)

    def test_continue_preserves_settlement_and_cannot_charge_again(self):
        self.write(fixture(day=7))
        summary = self.store.execute('endday')
        self.assertEqual(summary['operating_cost_breakdown']['overdue_surcharge'], 0)
        public = self.store.execute('continue')
        self.assertEqual(public['credits'], summary['credits'])
        self.assertEqual(public['last_settlement'], summary['last_settlement'])
        self.assertEqual(public['stats'], summary['stats'])
        self.assertEqual((public['day'], public['phase']), (8, 'active'))
        self.assertEqual(public['operating_cost_breakdown']['overdue_surcharge'], 2)
        self.reject_unchanged('continue')

    def test_day_fourteen_due_has_no_fee_then_day_fifteen_has_two(self):
        self.write(fixture(day=14, completed=1))
        before = self.store.execute('status')
        next_goal = before['campaign']['next_milestone']
        self.assertEqual((next_goal['nominal_due_day'], next_goal['effective_due_day'],
                          next_goal['days_remaining'], next_goal['overdue_days']), (14, 14, 0, 0))
        self.assertEqual(before['operating_cost_breakdown']['overdue_surcharge'], 0)
        public = self.store.execute('endday')
        self.assertEqual((public['day'], public['phase']), (15, 'active'))
        row = public['campaign']['deadline_history'][-1]
        self.assertEqual((row['missed_day'], row['completed_day']), (14, None))
        self.assertEqual(public['last_settlement']['breakdown']['overdue_surcharge'], 0)
        self.assertEqual(public['operating_cost_breakdown']['overdue_surcharge'], 2)

    def test_day_fourteen_exact_post_payment_threshold_is_inclusive(self):
        for cash, passes in ((1413, False), (1414, True)):
            with self.subTest(cash=cash):
                state = put_collection(fixture(day=14, completed=1, credits=cash),
                    ['wrench', 'lamp', 'welder', 'coffee', 'cleaner'], 75)
                state['reputation'] = 12
                state['upgrades']['workbench'] = 1
                state['upgrades']['shelf'] = 1
                # Level-one shelf adds one coin; workbench adds zero.
                state['credits'] += 1
                self.write(state)
                closed = self.store.execute('endday')
                self.assertEqual(closed['credits'], cash - 14)
                self.assertEqual(len(closed['campaign']['completed_milestones']), 2 if passes else 1)
                row = closed['campaign']['deadline_history'][1]
                self.assertEqual(row['missed_day'], None if passes else 14)
                self.assertEqual(row['completed_day'], 14 if passes else None)

    def test_single_active_stage_fee_increases_to_six_and_never_accumulates(self):
        for day, expected in ((8, 2), (9, 4), (10, 6), (40, 6), (100, 6)):
            with self.subTest(day=day):
                state = fixture(day=day)
                public = self.write(state)
                self.assertEqual(public['operating_cost_breakdown']['overdue_surcharge'], expected)
                self.assertEqual(public['operating_cost'], 14 + expected)
                public = self.store.execute('endday')
                self.assertEqual(public['last_settlement']['breakdown']['overdue_surcharge'], expected)
                self.assertEqual(public['credits'], 10000 - 14 - expected)

    def test_late_completion_keeps_missed_history_and_new_stage_gets_grace(self):
        state = put_collection(fixture(day=20, credits=670), ['wrench', 'lamp'], 70)
        self.write(state)
        public = self.store.execute('endday')
        self.assertEqual(public['credits'], 650)
        self.assertEqual(public['phase'], 'active')
        history = public['campaign']['deadline_history']
        self.assertEqual((history[0]['missed_day'], history[0]['completed_day']), (7, 20))
        self.assertEqual((history[1]['nominal_due_day'], history[1]['effective_due_day'],
                          history[1]['unlocked_day']), (14, 27, 20))
        self.assertIsNone(history[1]['missed_day'])
        self.assertEqual(public['last_settlement']['breakdown']['overdue_surcharge'], 6)
        self.assertEqual(public['operating_cost_breakdown']['overdue_surcharge'], 0)
        self.assertEqual(public['campaign']['first_week_result'], 'missed')

    def test_already_met_sequential_stages_complete_deterministically_after_payment(self):
        state = put_collection(fixture(day=50, credits=5030),
                               [row[0] for row in engine.CATALOG], 85)
        state['upgrades'] = dict.fromkeys(FEES, 3)
        state['reputation'] = 99
        # Plant set reduces base to ten; facilities twelve plus overdue six.
        state['credits'] = 5028
        public = self.write(state)
        self.assertEqual(public['campaign']['completed_milestones'], [])
        after = self.store.execute('endday')
        self.assertEqual(after['credits'], 5000)
        self.assertEqual([row['id'] for row in after['campaign']['completed_milestones']],
                         ['first_week', 'neighborhood', 'lighthouse', 'landmark'])
        self.assertEqual([row['day'] for row in after['campaign']['completed_milestones']], [50] * 4)
        history = after['campaign']['deadline_history']
        self.assertEqual([row['effective_due_day'] for row in history], [7, 57, 57, 57, 57])
        self.assertEqual([row['nominal_due_day'] for row in history], [7, 14, 28, 42, 56])
        self.assertTrue(all(row['missed_day'] is None for row in history[1:]))
        self.assertEqual(after['campaign']['next_milestone']['id'], 'voyage_1')
        self.assertEqual(after['operating_cost_breakdown']['overdue_surcharge'], 0)
        clone = copy.deepcopy(state)
        engine.apply_command(clone, 'endday', [])
        self.assertEqual(engine.observation(clone)['campaign'], after['campaign'])

    def test_voyage_nominal_deadlines_keep_fourteen_day_spacing(self):
        state = fixture(day=100, completed=4)
        for voyage, due in ((1, 56), (2, 70), (3, 84), (4, 98)):
            public = self.write(state)
            milestone = public['campaign']['next_milestone']
            self.assertEqual((milestone['id'], milestone['nominal_due_day']), (f'voyage_{voyage}', due))
            state['milestones'].append(dict(id=milestone['id'], title=milestone['title'], day=7))
            sync_stage_history(state)

    def test_late_status_reload_and_public_mutation_never_rewrite_history_or_rng(self):
        self.write(fixture(day=20, completed=1))
        before = self.store.save_path.read_bytes()
        expected = self.store.execute('status')
        changed = self.store.execute('status')
        changed['campaign']['deadline_history'][0]['completed_day'] = 999
        changed['operating_cost_breakdown']['total'] = 0
        for _ in range(3):
            reopened = engine.GameStore(self.store.save_path)
            self.assertEqual(reopened.execute('status'), expected)
            for command in ('market', 'codex', 'visitors'):
                reopened.execute(command)
            self.assertEqual(self.store.save_path.read_bytes(), before)

    def test_new_history_and_settlement_corruption_fail_before_public_write(self):
        self.write(fixture(day=14, completed=1))
        self.store.execute('endday')
        valid = self.store.load()
        mutations = (
            lambda state: state.pop('stage_history'),
            lambda state: state.pop('last_settlement'),
            lambda state: state['stage_history'].pop(),
            lambda state: state['stage_history'][-1].update(effective_due_day=1),
            lambda state: state['stage_history'][0].update(completed_day=8),
            lambda state: state['last_settlement'].update(paid=1),
            lambda state: state['last_settlement']['breakdown'].update(total=999),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                bad = copy.deepcopy(valid)
                mutate(bad)
                engine._atomic_json(self.store.save_path, bad)
                self.reject_unchanged('status')

    def test_seven_legal_closes_and_continue_cannot_erase_missed_history(self):
        self.write(fixture())
        for _ in range(7):
            public = self.store.execute('endday')
        self.assertEqual((public['day'], public['phase']), (7, 'week_summary'))
        summary = self.store.load()
        self.assertEqual(summary['stage_history'][-1]['missed_day'], 7)
        bad = copy.deepcopy(summary)
        bad['stage_history'][-1]['missed_day'] = None
        engine._atomic_json(self.store.save_path, bad)
        self.reject_unchanged('status')
        self.reject_unchanged('continue')
        self.write(summary)
        public = self.store.execute('continue')
        self.assertEqual((public['day'], public['phase']), (8, 'active'))
        self.assertEqual(public['campaign']['next_milestone']['overdue_days'], 1)
        self.assertEqual(public['campaign']['deadline_history'][-1]['status'], 'missed')
        bad = self.store.load()
        bad['stage_history'][-1]['missed_day'] = None
        engine._atomic_json(self.store.save_path, bad)
        self.reject_unchanged('status')
        self.reject_unchanged('endday')

    def test_deadline_day_marker_is_forbidden_before_close_and_required_after(self):
        for day, completed in ((7, 0), (14, 1)):
            with self.subTest(day=day):
                valid = fixture(day=day, completed=completed)
                public = self.write(valid)
                self.assertEqual(public['campaign']['deadline_history'][-1]['status'], 'active')
                self.assertIsNone(valid['stage_history'][-1]['missed_day'])
                bad = copy.deepcopy(valid)
                bad['stage_history'][-1]['missed_day'] = day
                engine._atomic_json(self.store.save_path, bad)
                self.reject_unchanged('status')
                self.write(valid)
                public = self.store.execute('endday')
                self.assertEqual(public['campaign']['deadline_history'][-1]['missed_day'], day)
                self.assertEqual(public['campaign']['deadline_history'][-1]['status'], 'missed')
                bad = self.store.load()
                bad['stage_history'][-1]['missed_day'] = None
                engine._atomic_json(self.store.save_path, bad)
                self.reject_unchanged('status')

    def test_completed_on_time_and_late_history_require_opposite_missed_markers(self):
        for day, expected in ((7, None), (20, 7)):
            with self.subTest(completed_day=day):
                state = put_collection(fixture(day=day), ['wrench', 'lamp'], 70)
                self.write(state)
                public = self.store.execute('endday')
                row = public['campaign']['deadline_history'][0]
                self.assertEqual((row['completed_day'], row['missed_day']), (day, expected))
                self.assertEqual(row['status'], 'completed' if expected is None else 'completed_late')
                valid = self.store.load()
                bad = copy.deepcopy(valid)
                bad['stage_history'][0]['missed_day'] = 7 if expected is None else None
                engine._atomic_json(self.store.save_path, bad)
                self.reject_unchanged('status')
                self.assertEqual(self.write(valid), public)

    def test_active_history_cannot_omit_overdue_or_invent_future_missed_markers(self):
        for day, completed in ((6, 0), (13, 1), (20, 0), (20, 1)):
            with self.subTest(day=day, completed=completed):
                valid = fixture(day=day, completed=completed)
                self.write(valid)
                bad = copy.deepcopy(valid)
                row = bad['stage_history'][-1]
                row['missed_day'] = row['effective_due_day'] if day < row['effective_due_day'] else None
                engine._atomic_json(self.store.save_path, bad)
                self.reject_unchanged('status')
                self.write(valid)

    def test_unpaid_close_at_exact_deadline_still_requires_missed_marker(self):
        for day, completed in ((7, 0), (14, 1)):
            with self.subTest(day=day):
                self.write(fixture(day=day, completed=completed, credits=0))
                public = self.store.execute('endday')
                self.assertEqual((public['day'], public['phase']), (day, 'lost'))
                self.assertFalse(public['last_settlement']['paid'])
                self.assertEqual(public['campaign']['deadline_history'][-1]['missed_day'], day)
                bad = self.store.load()
                bad['stage_history'][-1]['missed_day'] = None
                engine._atomic_json(self.store.save_path, bad)
                self.reject_unchanged('status')


class V10FocusedProcurementTests(SyntheticV10Harness):
    def test_supplier_public_schema_advertises_unlock_energy_stock_and_categories(self):
        for day in (7, 8):
            public = self.write(fixture(day=day))
            for supplier in public['suppliers']:
                self.assertTrue({'energy_cost', 'unlock_day', 'unlocked', 'remaining', 'daily_limit'} <= set(supplier))
                self.assertEqual(supplier['remaining'], supplier['stock'])
            row = next(row for row in public['suppliers'] if row['id'] == 'focused')
            self.assertEqual((row['cost'], row['energy_cost'], row['unlock_day'], row['daily_limit']),
                             (155, 1, 8, 1))
            self.assertEqual(row['unlocked'], day >= 8)
            self.assertEqual(row['remaining'], int(day >= 8))
            self.assertEqual(row['categories'], [{'id': key, 'name': label} for key, label in engine.KINDS.items()])
            self.assert_public(public)

    def test_focused_rejects_preunlock_bad_arity_unknown_kind_without_mutation(self):
        invalid = [(), ('focused',), ('focused', 'unknown'), ('focused', 'TOOL'),
                   ('focused', ''), ('focused', 'tool', 'extra'), ('salvage', 'tool'),
                   ('curated', 'plant'), ('unknown', 'tool')]
        self.write(fixture(day=8))
        for args in invalid:
            with self.subTest(args=args):
                self.reject_unchanged('buy', *args)
        self.write(fixture(day=7))
        for kind in engine.KINDS:
            self.reject_unchanged('buy', 'focused', kind)

    def test_focused_rejects_resource_and_capacity_failures_atomically(self):
        for problem in ('energy', 'cash', 'stock', 'capacity'):
            with self.subTest(problem=problem):
                state = fixture(day=8)
                if problem == 'energy':
                    state['energy'] = 0
                elif problem == 'cash':
                    state['credits'] = 154
                elif problem == 'stock':
                    state['supplier_stock']['focused'] = 0
                else:
                    state['inventory'] = [synthetic_item('wrench', index, collected=False)
                                          for index in range(1, 8)]
                    state['next_item'] = 8
                    state['discovered'] = ['wrench']
                self.write(state)
                self.reject_unchanged('buy', 'focused', 'tool')

    def test_invalid_focused_attempts_also_leave_in_memory_state_and_rng_unchanged(self):
        cases = [(8, ['focused'], {}), (8, ['focused', 'unknown'], {}),
                 (8, ['salvage', 'tool'], {}), (7, ['focused', 'tool'], {}),
                 (8, ['focused', 'tool'], {'energy': 0}),
                 (8, ['focused', 'tool'], {'credits': 154})]
        for day, args, changes in cases:
            with self.subTest(day=day, args=args, changes=changes):
                state = fixture(day=day)
                state.update(changes)
                before = copy.deepcopy(state)
                with self.assertRaises(engine.GameError):
                    engine.apply_command(state, 'buy', args)
                self.assertEqual(state, before)

    def test_every_category_purchase_is_sealed_and_open_does_not_reroll(self):
        for kind in engine.KINDS:
            with self.subTest(kind=kind):
                self.write(fixture(day=8, credits=155))
                before = self.store.load()
                public = self.store.execute('buy', 'focused', kind)
                self.assertEqual((public['credits'], public['energy']), (0, before['energy'] - 1))
                crate = public['crates'][0]
                self.assertEqual(set(crate), {'id', 'supplier', 'name', 'requested_kind', 'requested_kind_label'})
                self.assertEqual((crate['requested_kind'], crate['requested_kind_label']), (kind, engine.KINDS[kind]))
                self.assert_public(public)
                private = self.store.load()
                cargo = copy.deepcopy(private['crates'][0]['cargo'])
                self.assertEqual(cargo['kind'], kind)
                self.assertTrue(48 <= cargo['condition'] <= 96)
                self.assertNotEqual(private['rng'], before['rng'])
                committed = self.store.save_path.read_bytes()
                self.assertEqual(engine.GameStore(self.store.save_path).execute('status'), public)
                self.assertEqual(self.store.save_path.read_bytes(), committed)
                self.reject_unchanged('buy', 'focused', kind)
                self.reject_unchanged('inspect', crate['id'])
                opened = engine.GameStore(self.store.save_path).execute('open', crate['id'])
                actual = self.store.load()
                self.assertEqual(actual['rng'], private['rng'])
                self.assertEqual(actual['inventory'][0], dict(cargo, id='I001', price=actual['inventory'][0]['price']))
                self.assertEqual(opened['inventory'][0]['kind'], kind)
                self.assertEqual(opened['codex']['discovered'], 1)
                self.assert_public(opened, {cargo['catalog_id']})

    def test_focused_uses_curated_rarity_weights_and_condition_boundaries(self):
        for kind in engine.KINDS:
            for rarity in ('common', 'rare', 'legendary'):
                for condition in (48, 96):
                    with self.subTest(kind=kind, rarity=rarity, condition=condition):
                        source = mock.Mock()
                        source.choices.return_value = [rarity]
                        source.choice.side_effect = lambda values: values[0]
                        source.uniform.return_value = 1
                        source.randint.return_value = condition
                        cargo = engine._make_cargo(source, 'focused', kind)
                        source.choices.assert_called_once_with(['common', 'rare', 'legendary'], weights=[28, 61, 11])
                        source.randint.assert_called_once_with(48, 96)
                        self.assertEqual((cargo['kind'], cargo['rarity'], cargo['condition']),
                                         (kind, rarity, condition))
                        self.assertTrue(all(row[3] == kind and row[2] == rarity
                                            for row in source.choice.call_args.args[0]))

    def test_focused_limit_is_one_across_categories_and_resets_next_day(self):
        self.write(fixture(day=8))
        public = self.store.execute('buy', 'focused', 'tool')
        self.assertEqual(next(row for row in public['suppliers'] if row['id'] == 'focused')['remaining'], 0)
        self.reject_unchanged('buy', 'focused', 'plant')
        public = self.store.execute('endday')
        self.assertEqual(next(row for row in public['suppliers'] if row['id'] == 'focused')['remaining'], 1)
        public = self.store.execute('buy', 'focused', 'plant')
        self.assertEqual([row['requested_kind'] for row in public['crates']], ['tool', 'plant'])

    def test_hidden_same_category_identity_cannot_change_public_projection(self):
        self.write(fixture(day=8))
        public = self.store.execute('buy', 'focused', 'plant')
        private = self.store.load()
        for key in ('moss', 'seed', 'tree'):
            cargo = synthetic_item(key, 1, collected=False)
            cargo.pop('id')
            cargo.pop('price')
            cargo['origin'] = engine.SUPPLIERS['focused']['name']
            private['crates'][0]['cargo'] = cargo
            self.assertEqual(self.write(private), public)
            self.assert_public(self.store.execute('market'))

    def test_category_seal_tampering_is_refused_before_reveal_or_public_write(self):
        self.write(fixture(day=8))
        self.store.execute('buy', 'focused', 'tool')
        valid = self.store.load()
        for change in ('missing', 'unknown', 'mismatch'):
            with self.subTest(change=change):
                bad = copy.deepcopy(valid)
                if change == 'missing':
                    bad['crates'][0].pop('requested_kind')
                else:
                    bad['crates'][0]['requested_kind'] = 'unknown' if change == 'unknown' else 'plant'
                engine._atomic_json(self.store.save_path, bad)
                self.reject_unchanged('status')
                self.reject_unchanged('open', 'C001')


if __name__ == '__main__':
    unittest.main()
