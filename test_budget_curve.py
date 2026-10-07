"""v10 initial budget comfort curve. Synthetic fixtures only, never player saves."""
import copy
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest import mock

import engine
from native_test_helpers import within_budget_chance
from native_test_helpers import fixture, named


class BudgetCurveTests(unittest.TestCase):
    def context(self, budget=100, reference=100, bonus=0):
        return dict(reference=reference, budget=budget, modifier=bonus,
                    modifiers=[] if not bonus else [dict(label='测试加值', value=bonus)])

    def test_documented_boundary_and_large_overask_examples(self):
        context = self.context()
        self.assertEqual([engine._initial_chance(context, p) for p in (99, 100, 101, 110, 150, 200, 300)],
                         [60, 60, 58, 44, 15, 3, 1])

    def test_budget_minus_one_at_plus_one_has_no_cliff(self):
        for budget in (60, 90, 120, 180, 300, 800):
            for bonus in (-20, 0, 20, 50):
                with self.subTest(budget=budget, bonus=bonus):
                    values = [engine._initial_chance(self.context(budget, budget, bonus), p)
                              for p in (budget-1, budget, budget+1)]
                    self.assertGreater(values[-1], 1)
                    self.assertLessEqual(values[0]-values[-1], 5)
                    self.assertEqual(values, sorted(values, reverse=True))

    def test_within_budget_all_legal_prices(self):
        for budget in (60, 120, 400, 9999):
            for reference, bonus in ((17, -20), (100, 0), (999, 65)):
                context = self.context(budget, reference, bonus)
                for price in range(1, budget+1):
                    self.assertEqual(engine._initial_chance(context, price),
                                     within_budget_chance(context, price))

    def test_full_price_range_monotone_and_bounded(self):
        for budget in (60, 100, 120, 400):
            for reference, bonus in ((17, -20), (100, 0), (999, 65), (10000, 50)):
                context = self.context(budget, reference, bonus)
                probabilities = [engine._initial_chance(context, p) for p in range(1, 10000)]
                self.assertEqual(probabilities, sorted(probabilities, reverse=True))
                self.assertTrue(all(1 <= p <= 99 for p in probabilities))

    def test_more_budget_cannot_lower_chance(self):
        for price in (60, 100, 101, 125, 200, 500, 9999):
            values = [engine._initial_chance(self.context(b, 240, 20), price) for b in range(60, 1001)]
            self.assertEqual(values, sorted(values))

    def test_round_once_and_cap_before_overbudget_penalty(self):
        self.assertEqual(engine._initial_chance(self.context(), 101), 58)
        self.assertEqual(engine._initial_chance(self.context(100, 1000), 125), 66)
        self.assertEqual(engine._initial_chance(self.context(100, 1000), 200), 33)

    def test_missing_invalid_budget_and_unknown_rules_fail_closed(self):
        for budget in (None, 0, -1, True, 100.0, '100', float('nan')):
            with self.subTest(budget=budget), self.assertRaises(engine.GameError):
                engine._initial_chance(self.context(budget), 100)
        context = self.context(); del context['budget']
        with self.assertRaises(engine.GameError):
            engine._initial_chance(context, 100)
        for version in (None, True, 7, 8, 9, 11, '10'):
            with self.subTest(version=version), self.assertRaises(engine.GameError):
                engine._initial_chance(self.context(), 100, version)


    def test_both_buyer_types_have_normal_overbudget_success(self):
        for named_buyer in (False, True):
            state = fixture(2, condition=100)
            visitor = named(state) if named_buyer else None
            budget = visitor['budget'] if visitor else state['walkins']['budget']
            state['inventory'][0].update(price=budget+1, base_value=budget)
            context = engine._trade_context(state, state['inventory'][0], visitor)
            self.assertGreater(engine._initial_chance(context, budget+1), 1)
            engine.apply_command(state, 'sell', ['I001'] + ([visitor['id']] if visitor else []))
            self.assertEqual(state['roll_history'][-1]['outcome'], 'success')
            self.assertEqual(state['roll_history'][-1]['rules_version'], engine.TRADE_RULES_VERSION)
            self.assertEqual(state['stats']['gross_earnings'], budget+1)
            engine._validate_state(state)

    def test_all_dice_pairs_two_draws_and_exact_threshold_count(self):
        context = self.context()
        for price in (99, 100, 101, 150, 9999):
            successes = []
            for tens in range(10):
                for ones in range(10):
                    state = fixture()
                    rng = mock.Mock(); rng.randint.side_effect = [tens, ones]
                    row = engine._trade_roll(state, rng, state['inventory'][0], None, price, context, 'initial')
                    self.assertEqual(rng.randint.call_args_list, [mock.call(0, 9), mock.call(0, 9)])
                    self.assertIsNone(row['base_chance']); self.assertIsNone(row['premium'])
                    if row['roll'] == 1:
                        self.assertEqual(row['outcome'], 'miracle'); self.assertTrue(row['success'])
                    if row['roll'] == 100:
                        self.assertEqual(row['outcome'], 'fumble'); self.assertFalse(row['success'])
                    successes.append(row['success'])
            self.assertEqual(sum(successes), engine._initial_chance(context, price))

    def test_extreme_prices_keep_01_miracle_and_100_fumble(self):
        for value, outcome in ((1, 'miracle'), (100, 'fumble')):
            for named_buyer in (False, True):
                state = fixture(value, price=9999)
                visitor = named(state) if named_buyer else None
                engine.apply_command(state, 'sell', ['I001'] + ([visitor['id']] if visitor else []))
                self.assertEqual(state['roll_history'][-1]['outcome'], outcome)
                self.assertEqual(state['stats']['gross_earnings'], 9999 if value == 1 else 0)
                self.assertIsNone(state['negotiation'])
                engine._validate_state(state)

    def test_counter_eligibility_stays_public(self):
        for price in (1, 60, 90, 100, 120, 121, 500, 9999):
            for condition in (44, 45, 80, 100):
                state = fixture(price=price, condition=condition)
                visitor = named(state)
                for buyer in (None, visitor):
                    current = engine._sale_option(state, state['inventory'][0], buyer)
                    maximum_budget = buyer['budget_range'][1] if buyer else 120
                    minimum_condition = buyer['min_condition'] if buyer else 45
                    expected = (price >= 2 and price <= current['public_reference'] * 5 // 4
                                and price <= maximum_budget and condition >= minimum_condition
                                and (buyer is None or buyer['preferred_kind'] == state['inventory'][0]['kind']))
                    self.assertEqual(current['counter_eligible'], expected)
                    self.assertIn('消费舒适线', current['warning'])

    def test_public_projection_does_not_disclose_budget_or_first_forecast(self):
        for price in (99, 100, 101, 110, 200, 9999):
            state = fixture(price=price)
            other = copy.deepcopy(state)
            state['walkins']['budget'] = 60; other['walkins']['budget'] = 120
            for visitor in state['visitors']: visitor['budget'] = visitor['budget_range'][0]
            for visitor in other['visitors']: visitor['budget'] = visitor['budget_range'][1]
            for item in other['inventory']: item['base_value'] += 50
            self.assertEqual(engine.observation(state), engine.observation(other))
            public = json.dumps(engine.observation(state), ensure_ascii=False)
            for key in ('"budget":', '"base_value":', '"context":', '"reference":', '"rng":', '"budget_excess":'):
                self.assertNotIn(key, public)
            for option in engine.observation(state)['inventory'][0]['sale_options']:
                self.assertNotIn('threshold', option); self.assertNotIn('probability', option)

    def test_repeat_json_reads_leave_private_bytes_and_rng_unchanged(self):
        with tempfile.TemporaryDirectory(prefix='budget-v10-reads-') as tmp:
            store = engine.GameStore(Path(tmp)/'synthetic.json')
            engine._atomic_json(store.save_path, fixture(price=101))
            original = store.save_path.read_bytes()
            first = store.execute('status')
            for _ in range(4):
                self.assertEqual(store.execute('status'), first)
                store.execute('inspect', 'I001'); store.execute('visitors'); store.execute('market')
                self.assertEqual(store.save_path.read_bytes(), original)
            self.assertEqual(json.loads(store.observation_path.read_text()), first)

    def test_identical_state_and_actions_produce_identical_dice_and_rng(self):
        one = fixture(99, 50, price=90)
        two = copy.deepcopy(one)
        for state in (one, two):
            engine.apply_command(state, 'sell', ['I001'])
            engine.apply_command(state, 'offer', ['I001', str(state['negotiation']['counter_offer']+1)])
            engine._validate_state(state)
        self.assertEqual(one, two)
        expected = random.Random(); expected.setstate(fixture(99, 50)['rng'])
        for _ in range(4): expected.randint(0, 9)
        self.assertEqual(one['rng'], expected.getstate())


if __name__ == '__main__':
    unittest.main()
