"""Independent native v9 budget audit using synthetic data only.

No real save or default save path is read or written. Disk checks use fresh
TemporaryDirectory fixtures; expected formulas are independent of engine calls.
"""
import copy
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest import mock

import engine
from native_test_helpers import within_budget_chance, final_chance, counter_offer


def add_item(state, number=1, price=90, condition=80):
    row = engine.CATALOG_BY_ID['wrench']
    item = dict(id=f'I{number:03d}', catalog_id=row[0], name=row[1], rarity=row[2],
                kind=row[3], base_value=row[4], condition=condition,
                description=row[5], origin=engine.SUPPLIERS['salvage']['name'],
                collected=False, repairs=0, last_sale_day=0,
                last_repair_day=0, price=price)
    state['inventory'].append(item)
    state['next_item'] = max(state['next_item'], number + 1)
    if row[0] not in state['discovered']:
        state['discovered'].append(row[0])
    return item


def synthetic(*, price=90, count=1, seed=0):
    state = engine.new_state(42)
    for index in range(1, count + 1):
        add_item(state, index, price)
    # Fixed fixture seed: D100 66 then 04. No preferred-outcome seed search.
    state['rng'] = random.Random(seed).getstate()
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

    def test_within_budget_at_every_integer_price(self):
        for reference in (1, 17.3, 100, 1000):
            for budget in (60, 100, 240):
                for bonus in (-30, 0, 15, 45):
                    context = self.context(reference, budget, bonus)
                    for price in range(1, budget + 1):
                        self.assertEqual(engine._initial_chance(context, price),
                                         within_budget_chance(context, price),
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
                                     final_chance(bonus, counter, price))
            for budget in (60, 240):
                context = self.context(121.75, budget, bonus)
                for price in (2, 90, 250, 9999):
                    self.assertEqual(engine._counter_offer(context, price),
                                     counter_offer(context, price))


class BudgetStateIndependentAudit(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='budget-v9-independent-synthetic-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)


    def assert_corrupt_rejected_atomically(self, state):
        target = engine.GameStore(self.root / 'synthetic-corruption.json')
        target.save_path.write_text(json.dumps(state), encoding='utf-8')
        target.observation_path.write_text('preserve existing public projection', encoding='utf-8')
        before = target.save_path.read_bytes(), target.observation_path.read_bytes()
        with self.assertRaises(engine.GameError):
            target.execute('status')
        self.assertEqual(before, (target.save_path.read_bytes(), target.observation_path.read_bytes()))


















    def test_native_walkin_limit_cannot_be_duplicated(self):
        state = synthetic(price=9999, count=2)
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


if __name__ == '__main__':
    unittest.main()
