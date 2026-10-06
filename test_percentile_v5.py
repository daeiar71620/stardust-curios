"""Native v5 percentile, persistence and copy-only migration regressions.
Every game is synthetic, generated in memory or a TemporaryDirectory.
"""
import copy
from functools import lru_cache
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest import mock

import _legacy_v5 as engine
import _legacy_v1
import _legacy_v2
import _legacy_v3
import _legacy_v4
from test_dice_engine import fixture as old_fixture


@lru_cache(maxsize=None)
def rng_for(*rolls):
    digits = [digit for roll in rolls for digit in ((roll % 100) // 10, roll % 10)]
    for seed in range(1000000):
        rng = random.Random(seed)
        if [rng.randint(0, 9) for _ in digits] == digits:
            return random.Random(seed).getstate()
    raise AssertionError(f"No deterministic seed for {rolls}")


def fixture(*rolls, price=9999, day=1):
    state = engine.new_state(42)
    row = engine.CATALOG_BY_ID['wrench']
    state['inventory'] = [{'id': 'I001', 'catalog_id': row[0], 'name': row[1], 'rarity': row[2],
        'kind': row[3], 'base_value': row[4], 'condition': 80, 'description': row[5],
        'origin': engine.SUPPLIERS['salvage']['name'], 'collected': False, 'repairs': 0,
        'last_sale_day': 0, 'last_repair_day': 0, 'price': price}]
    state['next_item'] = 2
    state['discovered'] = [row[0]]
    state['day'] = day
    state['rng'] = rng_for(*(rolls or (50,)))
    return state


class PercentileV5Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='percentile-v5-synthetic-')
        self.root = Path(self.tmp.name)
        self.store = engine.GameStore(self.root / 'game.json')

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, state):
        engine._validate_state(state)
        engine._atomic_json(self.store.save_path, state)

    def pending(self, second=50, named=False):
        state = fixture(50, second)
        self.write(state)
        args = ['I001'] + ([state['visitors'][0]['id']] if named else [])
        return self.store.execute('sell', *args)

    def test_hundred_digit_pairs_are_bijective_uniform_and_independent_calls(self):
        seen = set()
        for tens in range(10):
            for ones in range(10):
                state = fixture()
                rng = mock.Mock()
                rng.randint.side_effect = [tens, ones]
                record = engine._trade_roll(state, rng, state['inventory'][0], None, 100,
                    {'reference': 100, 'budget': None, 'modifier': 0, 'modifiers': []}, 'initial')
                self.assertEqual(rng.randint.call_args_list, [mock.call(0, 9), mock.call(0, 9)])
                self.assertEqual(record['tens'], tens * 10)
                self.assertEqual(record['ones'], ones)
                self.assertEqual(record['roll'], tens * 10 + ones or 100)
                seen.add(record['roll'])
        self.assertEqual(seen, set(range(1, 101)))

    def test_critical01_sells_9999_above_private_budget(self):
        state = fixture(1)
        visitor = state['visitors'][0]
        self.assertLess(visitor['budget'], 9999)
        self.write(state)
        public = self.store.execute('sell', 'I001', visitor['id'])
        roll = public['last_roll']
        self.assertEqual((roll['tens'], roll['ones'], roll['roll'], roll['threshold']), (0, 1, 1, 1))
        self.assertEqual((roll['outcome'], roll['probability']), ('miracle', .01))
        self.assertEqual(public['credits'], state['credits'] + 9999)
        self.assertEqual(public['stats']['gross_earnings'], 9999)
        self.assertEqual(public['inventory'], [])
        self.assertIsNone(public['negotiation'])
        self.assertEqual(public['energy'], state['energy'] - 1)
        self.assertEqual(engine.GameStore(self.store.save_path).execute('status'), public)

    def test_100_fumble_ends_even_cheapest_offer(self):
        state = fixture(100, price=1)
        self.write(state)
        public = self.store.execute('sell', 'I001')
        self.assertEqual((public['last_roll']['tens'], public['last_roll']['ones']), (0, 0))
        self.assertEqual((public['last_roll']['roll'], public['last_roll']['outcome']), (100, 'fumble'))
        self.assertIsNone(public['negotiation'])
        self.assertEqual(public['credits'], state['credits'])
        self.assertEqual(public['energy'], state['energy'] - 1)
        for command, args in [('sell', ['I001']), ('accept', ['I001']), ('offer', ['I001', '2'])]:
            with self.assertRaises(engine.GameError): self.store.execute(command, *args)

    def test_native_initial_threshold_price_sensitivity_and_budget(self):
        context = {'reference': 100, 'budget': None, 'modifier': 0, 'modifiers': []}
        self.assertEqual([engine._initial_chance(context, p) for p in [25, 50, 100, 200, 400, 9999]], [99, 99, 60, 10, 1, 1])
        context['modifier'] = 5
        self.assertEqual(engine._initial_chance(context, 100), 65)
        context['budget'] = 90
        self.assertEqual(engine._initial_chance(context, 100), 1)
        thresholds = [engine._initial_chance(context, price) for price in range(1, 10000)]
        self.assertEqual(thresholds, sorted(thresholds, reverse=True))

    def test_low_roll_boundaries_01_and_100(self):
        for value, outcome in [(1, 'miracle'), (2, 'success'), (60, 'success'), (61, 'failure'), (99, 'failure'), (100, 'fumble')]:
            with self.subTest(value=value):
                state = fixture()
                rng = mock.Mock(); rng.randint.side_effect = [(value % 100)//10, value%10]
                roll = engine._trade_roll(state, rng, state['inventory'][0], None, 100,
                    {'reference': 100, 'budget': None, 'modifier': 0, 'modifiers': []}, 'initial')
                self.assertEqual(roll['outcome'], outcome)
                self.assertEqual(roll['threshold'], 60)

    def test_final_10percent_50percent_hugepremium_and_scale_invariance(self):
        self.assertEqual(engine._final_chance(0, 150, 165), (70, 58))
        self.assertEqual(engine._final_chance(0, 150, 225), (70, 35))
        self.assertEqual(engine._final_chance(0, 150, 9998), (70, 1))
        for scale in (1, 2, 3, 7, 11):
            self.assertEqual(engine._final_chance(0, 150*scale, 165*scale), (70, 58))
        for bonus in (-30, -10, 0, 25, 65):
            chances = [engine._final_chance(bonus, 150, p)[1] for p in range(151, 10000)]
            self.assertEqual(chances, sorted(chances, reverse=True))
            self.assertTrue(all(1 <= chance <= 99 for chance in chances))

    def test_exact_preview_independent_of_all_hidden_valuation_budget(self):
        self.pending(named=True)
        state = self.store.load()
        twin = copy.deepcopy(state)
        twin['negotiation']['context']['reference'] *= 100
        twin['negotiation']['context']['budget'] = 1
        twin['inventory'][0]['base_value'] *= 100
        twin['visitors'][0]['budget'] = 1
        for price in (100, 225, 9998):
            a = engine._offer_forecast(state, state['negotiation'], price)
            b = engine._offer_forecast(twin, twin['negotiation'], price)
            self.assertEqual(a, b)
            self.assertEqual(a['basis'], 'public_counter')
            self.assertEqual(a['probability'], a['threshold'] / 100)

    def test_preview_no_private_write_rng_draw_energy_or_revision_and_restart_equivalence(self):
        before = self.pending(second=35)
        private = self.store.save_path.read_bytes()
        twin = engine.GameStore(self.root / 'twin.json'); twin.save_path.write_bytes(private)
        for price in [100, 225, 9998, 100]:
            with mock.patch.object(engine.random.Random, 'randint', side_effect=AssertionError('preview drew')):
                public = self.store.execute('preview-offer', 'I001', str(price))
            self.assertEqual(self.store.save_path.read_bytes(), private)
            self.assertEqual(public['revision'], before['revision'])
            self.assertEqual(public['energy'], before['energy'])
            self.assertEqual(public['negotiation']['preview']['price'], price)
            self.assertEqual(json.loads(self.store.observation_path.read_bytes()), public)
        actual = engine.GameStore(self.store.save_path).execute('offer', 'I001', '100')
        self.assertEqual(actual, twin.execute('offer', 'I001', '100'))
        self.assertEqual(actual['last_roll']['threshold'], public['negotiation']['preview']['threshold'])

    def test_final_distribution_matches_public_probability_all100_pairs(self):
        self.pending()
        source = self.store.load()
        for price in [100, 225, 9998]:
            preview = engine._offer_forecast(source, source['negotiation'], price)
            count = 0
            for value in range(1, 101):
                state = copy.deepcopy(source)
                rng = mock.Mock(); rng.randint.side_effect = [(value % 100)//10, value%10]
                row = engine._trade_roll(state, rng, state['inventory'][0], None, price, state['negotiation']['context'], 'final')
                count += row['success']
                self.assertEqual(row['threshold'], preview['threshold'])
            self.assertEqual(count, preview['threshold'])
            self.assertEqual(count / 100, preview['probability'])

    def test_final_above_named_budget_has_no_second_hidden_gate(self):
        self.pending(second=2, named=True)
        state = self.store.load()
        price = state['visitors'][0]['budget'] + 1
        preview = self.store.execute('preview-offer', 'I001', str(price))['negotiation']['preview']
        self.assertGreaterEqual(preview['threshold'], 2)
        public = self.store.execute('offer', 'I001', str(price))
        self.assertEqual(public['last_roll']['outcome'], 'success')
        self.assertEqual(public['last_roll']['threshold'], preview['threshold'])

    def test_frozen_bonuses_survive_upgrade_and_final(self):
        self.pending(second=35)
        state = self.store.load(); state['credits'] = 1000; self.write(state)
        before = self.store.execute('preview-offer', 'I001', '100')['negotiation']['preview']
        self.store.execute('upgrade', 'display')
        after = self.store.execute('preview-offer', 'I001', '100')['negotiation']['preview']
        self.assertEqual(before, after)
        actual = self.store.execute('offer', 'I001', '100')['last_roll']
        self.assertEqual(actual['modifier'], before['modifier'])
        self.assertEqual(actual['threshold'], before['threshold'])

    def test_invalid_final_prices_rejected_without_any_write_or_rng(self):
        before = self.pending()
        counter = before['negotiation']['counter_offer']
        original = self.store.save_path.read_bytes(), self.store.observation_path.read_bytes()
        for command in ['offer', 'preview-offer']:
            for price in [str(counter), str(counter-1), '9999', '10000', '0', '1.5', 'true', '0100', '+100']:
                with self.subTest(command=command, price=price):
                    with self.assertRaises(engine.GameError): self.store.execute(command, 'I001', price)
                    self.assertEqual(original, (self.store.save_path.read_bytes(), self.store.observation_path.read_bytes()))

    def test_accept_decline_free_zeroenergy_and_no_new_roll(self):
        for command in ['accept', 'decline']:
            with self.subTest(command=command):
                before = self.pending()
                state = self.store.load(); state['energy'] = 0; self.write(state)
                private_rng = state['rng']
                after = self.store.execute(command, 'I001')
                self.assertEqual(after['energy'], 0)
                self.assertEqual(after['roll_history'], before['roll_history'])
                self.assertEqual(self.store.load()['rng'], private_rng)
                self.assertEqual(after['credits'] - before['credits'], before['negotiation']['counter_offer'] if command == 'accept' else 0)
                self.assertIsNone(after['negotiation'])

    def test_final_fail_loses_quote_one_energy_only_two_pairs(self):
        before = self.pending(second=99)
        after = self.store.execute('offer', 'I001', '100')
        self.assertEqual(after['last_roll']['outcome'], 'failure')
        self.assertEqual(after['energy'], before['energy'] - 1)
        self.assertEqual(after['credits'], before['credits'])
        self.assertEqual(len(after['roll_history']), 2)
        self.assertIsNone(after['negotiation'])
        for command, args in [('accept', ['I001']), ('offer', ['I001', '99']), ('sell', ['I001'])]:
            with self.assertRaises(engine.GameError): self.store.execute(command, *args)

    def test_final_critical_bypasses_huge_premium_and_fumble_always_ends(self):
        for value, outcome in [(1, 'miracle'), (100, 'fumble')]:
            before = self.pending(second=value, named=True)
            after = self.store.execute('offer', 'I001', '9998')
            self.assertEqual(after['last_roll']['outcome'], outcome)
            self.assertEqual(after['last_roll']['probability'], .01)
            self.assertEqual(after['credits']-before['credits'], 9998 if value == 1 else 0)
            self.assertIsNone(after['negotiation'])

    def test_pending_locks_item_and_customer_across_reload(self):
        self.pending(named=True)
        visitor = self.store.load()['negotiation']['customer_id']
        for command, args in [('repair', ['I001']), ('price', ['I001', '100']), ('collect', ['I001']), ('sell', ['I001', visitor])]:
            with self.assertRaises(engine.GameError): engine.GameStore(self.store.save_path).execute(command, *args)
        self.store.execute('decline', 'I001')
        self.store.execute('price', 'I001', '100')
        with self.assertRaises(engine.GameError): self.store.execute('sell', 'I001')

    def test_endday_declines_pending_and_leaves_no_stale_accept(self):
        self.pending()
        after = self.store.execute('endday')
        self.assertIsNone(after['negotiation'])
        self.assertEqual(after['day'], 2)
        with self.assertRaises(engine.GameError): self.store.execute('accept', 'I001')

    def test_public_data_omits_secret_context_and_unrelated_d20_fields(self):
        public = self.pending(named=True)
        blob = json.dumps(public)
        for secret in ['"rng"', '"base_value"', '"budget"', '"context"', '"reference"', '"rejection_penalty"']:
            self.assertNotIn(secret, blob)
        for old_field in ['face', 'target', 'total', 'rejection_penalty']:
            self.assertNotIn(old_field, public['last_roll'])
        self.assertEqual(public['trade_rules']['miracle_probability'], .01)
        self.assertEqual(public['trade_rules']['die'], 'D100')
        self.assertEqual(public['negotiation']['rules_version'], 5)

    def test_corrupted_digits_probability_outcome_and_version_rejected(self):
        self.pending()
        original = self.store.load()
        mutations = [('tens', 11), ('ones', 10), ('roll', 1), ('threshold', 0), ('probability', 0), ('outcome', 'miracle'), ('rules_version', 4)]
        for key, value in mutations:
            with self.subTest(key=key):
                state = copy.deepcopy(original)
                state['roll_history'][-1][key] = value
                state['last_event']['roll'] = copy.deepcopy(state['roll_history'][-1])
                with self.assertRaises(engine.GameError): engine._validate_state(state)

    def test_copy_v1_v2_resources_and_rng_preserved(self):
        for version, module in [(1, _legacy_v1), (2, _legacy_v2)]:
            with self.subTest(version=version):
                old = module.new_state(42)
                src = self.root / f'v{version}.json'; src.write_text(json.dumps(old))
                original = src.read_bytes()
                store = engine.GameStore(self.root / f'copy{version}.json')
                public = store.execute(f'import-v{version}', str(src))
                after = store.load()
                self.assertEqual(public['version'], 5)
                self.assertEqual(src.read_bytes(), original)
                for key in ['day', 'credits', 'energy', 'inventory', 'crates', 'collection', 'rng']:
                    self.assertEqual(after[key], json.loads(json.dumps(old[key])))
                self.assertEqual(after['roll_seq'], 0)

    def old_source(self, version, *, finished=False):
        module = _legacy_v3 if version == 3 else _legacy_v4
        state = old_fixture(10, 20)
        state['version'] = version
        module.apply_command(state, 'sell', ['I001'])
        if finished: module.apply_command(state, 'offer', ['I001', '9999' if version == 3 else '9998'])
        module._validate_state(state)
        src = self.root / f'old{version}.json'; src.write_text(json.dumps(state))
        return src, state

    def test_copy_v3_v4_pending_counter_rng_resources_kept_with_explicit_retry_rules(self):
        for version in [3, 4]:
            with self.subTest(version=version):
                src, old = self.old_source(version)
                raw = src.read_bytes()
                store = engine.GameStore(self.root / f'copy{version}.json')
                public = store.execute(f'import-v{version}', str(src))
                after = store.load()
                self.assertEqual(src.read_bytes(), raw)
                for key in ['day', 'credits', 'energy', 'inventory', 'crates', 'collection', 'rng', 'visitors', 'roll_seq']:
                    self.assertEqual(after[key], json.loads(json.dumps(old[key])))
                self.assertEqual(after['negotiation']['counter_offer'], old['negotiation']['counter_offer'])
                self.assertEqual(after['negotiation']['rules_version'], 5)
                self.assertEqual(after['negotiation']['origin_rules_version'], version)
                self.assertEqual(after['negotiation']['context']['modifier'], old['negotiation']['context']['modifier'] * 5)
                self.assertEqual(public['last_roll']['face'], 10)
                self.assertEqual(public['last_roll']['rules_version'], version)
                final = store.execute('offer', 'I001', '100')
                self.assertEqual(final['last_roll']['rules_version'], 5)
                self.assertEqual(final['last_roll']['die'], 'D100')
                self.assertEqual(final['roll_history'][0], public['last_roll'])

    def test_historical_v3_sameprice_final_remains_legal_history_only(self):
        src, old = self.old_source(3, finished=True)
        public = self.store.execute('import-v3', str(src))
        self.assertEqual(public['last_roll']['price'], 9999)
        self.assertEqual(public['last_roll']['face'], 20)
        self.assertEqual(public['last_roll']['rules_version'], 3)
        self.assertNotIn('roll', public['last_roll'])
        self.assertEqual(public['roll_history'][-1]['target'], old['roll_history'][-1]['target'])

    def test_mixed_v3_v4_boundary_preserved_then_native_v5(self):
        src, old = self.old_source(3)
        interim = _legacy_v4.GameStore(self.root / 'interim.json')
        interim.execute('import-v3', str(src))
        interim.execute('offer', 'I001', '9998')
        before = interim.save_path.read_bytes()
        public = self.store.execute('import-v4', str(interim.save_path))
        self.assertEqual([row['rules_version'] for row in public['roll_history']], [3, 4])
        self.assertEqual(self.store.load()['engine_upgrade']['legacy_v3_roll_seq'], 1)
        self.assertEqual(interim.save_path.read_bytes(), before)
        bad = self.store.load(); bad['roll_history'][1]['rules_version'] = 3
        with self.assertRaises(engine.GameError): engine._validate_state(bad)

    def test_import_rejects_overwrite_samepath_wrongversion_and_public_projection(self):
        src, _ = self.old_source(4)
        original = src.read_bytes()
        with self.assertRaises(engine.GameError): engine.GameStore(src).execute('import-v4', str(src))
        self.assertEqual(src.read_bytes(), original)
        self.store.execute('import-v4', str(src))
        private = self.store.save_path.read_bytes()
        with self.assertRaises(engine.GameError): self.store.execute('import-v4', str(src))
        self.assertEqual(private, self.store.save_path.read_bytes())
        for command, path in [('import-v3', src), ('import-v4', self.store.observation_path)]:
            with self.assertRaises(engine.GameError): engine.GameStore(self.root / 'invalid.json').execute(command, str(path))
            self.assertFalse((self.root / 'invalid.json').exists())


if __name__ == '__main__': unittest.main()
