"""Independent v5 rules, migration, and transaction audit; synthetic data only.

These fixtures are deliberately independent of the main v5 tests. No default
save, existing playthrough, display server, or external service is accessed.
"""
import copy
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest import mock

import engine
import _legacy_v1
import _legacy_v2
import _legacy_v3
import _legacy_v4


@lru_cache(maxsize=None)
def seeded_rolls(version, *values):
    """Find a genuine serialized RNG, not a mocked saved random state."""
    for seed in range(1000000):
        rng = random.Random(seed)
        actual = []
        for _ in values:
            actual.append((10 * rng.randint(0, 9) + rng.randint(0, 9) or 100)
                          if version == 5 else rng.randint(1, 20))
        if tuple(actual) == values:
            return random.Random(seed).getstate()
    raise AssertionError((version, values))


def synthetic(module=engine, *values, price=9999):
    state = module.new_state(42)
    row = module.CATALOG_BY_ID["wrench"]
    state["inventory"] = [{"id": "I001", "catalog_id": row[0], "name": row[1],
        "rarity": row[2], "kind": row[3], "base_value": row[4], "condition": 80,
        "description": row[5], "origin": module.SUPPLIERS["salvage"]["name"],
        "collected": False, "repairs": 0, "last_sale_day": 0,
        "last_repair_day": 0, "price": price}]
    state["next_item"] = 2
    if "discovered" in state:
        state["discovered"] = [row[0]]
    if values:
        state["rng"] = seeded_rolls(module.VERSION, *values)
    return state


class DigitSource:
    def __init__(self, tens_digit, ones_digit):
        self.values = iter((tens_digit, ones_digit))
        self.calls = []

    def randint(self, low, high):
        self.calls.append((low, high))
        return next(self.values)


class PercentileRulesAudit(unittest.TestCase):
    def test_native_initial_thresholds_include_non_d20_steps(self):
        context = {"reference": 100, "budget": None, "modifier": 0, "modifiers": []}
        for price, expected in ((1, 99), (50, 99), (100, 60), (105, 56),
                                (110, 53), (115, 49), (125, 43), (150, 30),
                                (200, 10), (250, 1), (9999, 1)):
            with self.subTest(price=price):
                self.assertEqual(engine._initial_chance(context, price), expected)
        context.update(budget=100, modifier=65)
        self.assertEqual(engine._initial_chance(context, 100), 99)
        self.assertEqual(engine._initial_chance(context, 101), 1)

    def test_final_integer_rational_and_clamp_boundaries(self):
        for bonus, counter, price, expected in (
            (0, 100, 110, (70, 58)), (0, 100, 125, (70, 46)),
            (0, 100, 150, (70, 35)), (0, 100, 200, (70, 23)),
            (0, 100, 500, (70, 7)), (0, 100, 9999, (70, 1)),
            (35, 100, 110, (99, 82)), (-80, 100, 101, (1, 1)),
            (0, 1, 2, (70, 23)), (0, 9997, 9998, (70, 69))):
            with self.subTest(bonus=bonus, counter=counter, price=price):
                self.assertEqual(engine._final_chance(bonus, counter, price), expected)

    def test_all_digit_pairs_are_bijective_and_take_two_independent_draws(self):
        values = []
        for tens in range(10):
            for ones in range(10):
                state = synthetic()
                source = DigitSource(tens, ones)
                context = {"reference": 100, "budget": None, "modifier": 0, "modifiers": []}
                roll = engine._trade_roll(state, source, state["inventory"][0], None,
                                          100, context, "initial")
                self.assertEqual(source.calls, [(0, 9), (0, 9)])
                self.assertEqual((roll["tens"], roll["ones"]), (tens * 10, ones))
                self.assertEqual(roll["roll"], (tens * 10 + ones) or 100)
                self.assertEqual(roll["success"], 1 <= roll["roll"] <= 60)
                self.assertEqual(roll["probability"], .60)
                values.append(roll["roll"])
        self.assertEqual(sorted(values), list(range(1, 101)))

    def test_final_preview_exactly_counts_successes_over_all_100_outcomes(self):
        # Huge changes to the private reference/budget cannot affect the final.
        for bonus, price in ((-20, 101), (0, 110), (15, 150), (35, 125), (0, 9998)):
            state = synthetic()
            context = {"reference": .001, "budget": 1, "modifier": bonus,
                       "modifiers": [{"label": "test", "value": bonus}]}
            pending = {"counter_offer": 100, "context": context}
            state["negotiation"] = pending
            expected_base = max(1, min(99, 70 + bonus))
            expected = max(1, min(99, expected_base * 100 // (2 * price - 100)))
            preview = engine._offer_forecast(state, pending, price)
            successes = 0
            for value in range(1, 101):
                source = DigitSource((value % 100) // 10, value % 10)
                roll = engine._trade_roll(state, source, state["inventory"][0], None,
                                          price, context, "final")
                self.assertEqual(roll["threshold"], expected)
                self.assertEqual(roll["probability"], preview["probability"])
                successes += roll["success"]
            self.assertEqual(successes, expected)
            self.assertEqual(preview["probability"], successes / 100)

    def test_every_native_public_bonus_is_exactly_five_times_legacy(self):
        state = synthetic()
        for reputation in (0, 4, 5, 14, 15, 99):
            for display in range(4):
                for event_id in ("festival", "fog", engine.EVENTS[0]["id"]):
                    state["reputation"] = reputation
                    state["upgrades"]["display"] = display
                    state["daily_event"] = copy.deepcopy(next(e for e in engine.EVENTS if e["id"] == event_id))
                    item = state["inventory"][0]
                    for visitor in (None, *state["visitors"]):
                        old = _legacy_v4._trade_context(state, item, visitor)
                        new = engine._trade_context(state, item, visitor)
                        self.assertEqual(new["modifier"], old["modifier"] * 5)
                        self.assertEqual(new["modifiers"],
                            [dict(m, value=5 * m["value"]) for m in old["modifiers"]])


class PercentilePersistenceAudit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="stardust-percentile-audit-")
        self.root = Path(self.tmp.name)
        self.store = engine.GameStore(self.root / "synthetic-v5.json")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, state):
        engine._validate_state(state)
        engine._atomic_json(self.store.save_path, state)

    def pending(self, second=50, named=False):
        state = synthetic(engine, 99, second)
        self.write(state)
        args = ["I001"] + ([state["visitors"][0]["id"]] if named else [])
        return self.store.execute("sell", *args)

    def assert_rejected_unchanged(self, command, *args):
        before = (self.store.save_path.read_bytes(), self.store.observation_path.read_bytes())
        with self.assertRaises(engine.GameError):
            self.store.execute(command, *args)
        self.assertEqual(before, (self.store.save_path.read_bytes(), self.store.observation_path.read_bytes()))

    def test_sale_persists_exactly_two_digit_draws_and_reopen_preserves_stream(self):
        state = synthetic(engine, 99, 50)
        self.write(state)
        expected = engine._rng(state)
        digits = expected.randint(0, 9) * 10, expected.randint(0, 9)
        public = self.store.execute("sell", "I001")
        self.assertEqual((public["last_roll"]["tens"], public["last_roll"]["ones"]), digits)
        self.assertEqual(engine._tuple_tree(self.store.load()["rng"]), expected.getstate())
        self.assertEqual(engine.GameStore(self.store.save_path).execute("status"), public)

    def test_preview_is_read_only_and_cannot_change_future_percentile(self):
        public = self.pending(named=True)
        private = self.store.save_path.read_bytes()
        control = engine.GameStore(self.root / "control.json")
        control.save_path.write_bytes(private)
        counter = public["negotiation"]["counter_offer"]
        for price in (counter + 1, counter + 9, 9998, counter + 1):
            with mock.patch.object(engine.random.Random, "randint", side_effect=AssertionError("preview drew")):
                result = self.store.execute("preview-offer", "I001", str(price))
            self.assertEqual(self.store.save_path.read_bytes(), private)
            self.assertEqual(result["revision"], public["revision"])
            self.assertEqual(json.loads(self.store.observation_path.read_text()), result)
        price = str(counter + 1)
        self.assertEqual(engine.GameStore(self.store.save_path).execute("offer", "I001", price),
                         control.execute("offer", "I001", price))

    def test_free_accept_and_decline_do_not_advance_rng_even_at_zero_energy(self):
        for command in ("accept", "decline"):
            with self.subTest(command=command):
                self.pending(named=True)
                state = self.store.load()
                state["energy"] = 0
                self.write(state)
                before_rng = state["rng"]
                counter = state["negotiation"]["counter_offer"]
                after = self.store.execute(command, "I001")
                self.assertEqual(after["energy"], 0)
                self.assertEqual(self.store.load()["rng"], before_rng)
                self.assertEqual(after["credits"] - state["credits"], counter if command == "accept" else 0)
                self.assertEqual(after["roll_history"], state["roll_history"])
                self.assertIsNone(after["negotiation"])

    def test_strict_offer_and_preview_bounds_reject_atomically(self):
        public = self.pending()
        counter = public["negotiation"]["counter_offer"]
        for command in ("offer", "preview-offer"):
            for price in ("0", "1", str(counter), "9999", "10000", "1.5", "01", "+100", "nan"):
                with self.subTest(command=command, price=price):
                    self.assert_rejected_unchanged(command, "I001", price)

    def test_final_failure_spends_one_energy_and_permanently_closes_old_quote(self):
        before = self.pending(second=99, named=True)
        public = self.store.execute("offer", "I001", "9998")
        self.assertEqual(public["last_roll"]["outcome"], "failure")
        self.assertEqual(public["energy"], before["energy"] - 1)
        self.assertEqual(public["credits"], before["credits"])
        self.assertIsNone(public["negotiation"])
        for command, args in (("accept", ("I001",)), ("offer", ("I001", "100")),
                              ("sell", ("I001",)), ("sell", ("I001", before["visitors"][1]["id"]))):
            self.assert_rejected_unchanged(command, *args)

    def test_01_sells_maximum_legal_price_above_budget_and_100_ends_visit(self):
        for value, price in ((1, 9999), (100, 1)):
            with self.subTest(value=value):
                state = synthetic(engine, value, price=price)
                self.write(state)
                result = self.store.execute("sell", "I001", state["visitors"][0]["id"])
                self.assertEqual(result["last_roll"]["outcome"], "miracle" if value == 1 else "fumble")
                self.assertEqual(result["credits"] - state["credits"], price if value == 1 else 0)
                self.assertIsNone(result["negotiation"])
                if value == 100:
                    self.assert_rejected_unchanged("sell", "I001")

    def test_final_ordinary_success_above_named_budget_has_no_second_gate(self):
        self.pending(second=2, named=True)
        state = self.store.load()
        budget = state["negotiation"]["context"]["budget"]
        price = max(budget + 1, state["negotiation"]["counter_offer"] + 1)
        preview = self.store.execute("preview-offer", "I001", str(price))["negotiation"]["preview"]
        self.assertGreaterEqual(preview["threshold"], 2)
        result = self.store.execute("offer", "I001", str(price))
        self.assertEqual(result["last_roll"]["outcome"], "success")
        self.assertEqual(result["last_roll"]["threshold"], preview["threshold"])
        self.assertEqual(result["credits"] - state["credits"], price)
        self.assertIn("不再", result["trade_rules"]["final_budget_rule"])

    def test_public_projection_has_no_private_state_or_secret_formula_inputs(self):
        self.pending(named=True)
        forbidden = {"rng", "base_value", "reference", "budget", "cargo", "context"}
        def inspect(value):
            if isinstance(value, dict):
                self.assertFalse(forbidden.intersection(value))
                for child in value.values(): inspect(child)
            elif isinstance(value, list):
                for child in value: inspect(child)
        for command, args in (("status", ()), ("market", ()), ("visitors", ()),
                              ("inspect", ("I001",)), ("preview-offer", ("I001", "9998"))):
            inspect(self.store.execute(command, *args))
        state = self.store.load()
        other = copy.deepcopy(state)
        other["negotiation"]["context"].update(reference=987654321.5, budget=1)
        self.assertEqual(engine._offer_forecast(state, state["negotiation"], 9998),
                         engine._offer_forecast(other, other["negotiation"], 9998))

    def test_precommit_failure_leaves_bytes_and_same_future_roll(self):
        self.pending()
        before = self.store.save_path.read_bytes(), self.store.observation_path.read_bytes()
        control = engine.GameStore(self.root / "control.json")
        control.save_path.write_bytes(before[0])
        with mock.patch.object(engine.os, "replace", side_effect=OSError("synthetic precommit failure")):
            with self.assertRaises(OSError): self.store.execute("offer", "I001", "100")
        self.assertEqual(before, (self.store.save_path.read_bytes(), self.store.observation_path.read_bytes()))
        self.assertEqual(self.store.execute("offer", "I001", "100"), control.execute("offer", "I001", "100"))

    def test_projection_failure_does_not_reroll_committed_final_and_status_heals(self):
        self.pending()
        original = engine._atomic_json
        def fail_public(path, data):
            if Path(path) == self.store.observation_path:
                raise OSError("synthetic projection failure")
            return original(path, data)
        with mock.patch.object(engine, "_atomic_json", side_effect=fail_public):
            result = self.store.execute("offer", "I001", "100")
        self.assertIn("不要重复", result.pop("persistence_warning"))
        committed = self.store.save_path.read_bytes()
        self.assert_rejected_unchanged("offer", "I001", "100")
        self.assertEqual(self.store.execute("status"), result)
        self.assertEqual(self.store.save_path.read_bytes(), committed)
        self.assertEqual(json.loads(self.store.observation_path.read_text()), result)

    def test_lock_serializes_competing_final_offers_to_one_pair_and_one_energy(self):
        before = self.pending()
        def attempt(_):
            try:
                return engine.GameStore(self.store.save_path).execute("offer", "I001", "100")
            except engine.GameError:
                return None
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(attempt, range(4)))
        self.assertEqual(sum(result is not None for result in results), 1)
        after = self.store.load()
        self.assertEqual(after["roll_seq"], 2)
        self.assertEqual(after["energy"], before["energy"] - 1)
        self.assertEqual(after["revision"], before["revision"] + 1)

    def test_native_final_record_rejects_inconsistent_digits_probability_and_formula(self):
        self.pending()
        self.store.execute("offer", "I001", "100")
        original = self.store.load()
        for field, value in (("tens", 95), ("ones", 10), ("roll", 101),
                             ("probability", .123456), ("rules_version", 4),
                             ("base_chance", 99), ("premium", -1), ("modifier", 1)):
            with self.subTest(field=field):
                bad = copy.deepcopy(original)
                bad["roll_history"][-1][field] = value
                bad["last_event"]["roll"] = copy.deepcopy(bad["roll_history"][-1])
                engine._atomic_json(self.store.save_path, bad)
                self.assert_rejected_unchanged("status")

    def test_display_upgrade_does_not_change_frozen_final_bonus_or_preview(self):
        self.pending()
        state = self.store.load()
        state["credits"] = 1000
        self.write(state)
        before = self.store.execute("preview-offer", "I001", "100")["negotiation"]["preview"]
        self.store.execute("upgrade", "display")
        after = self.store.execute("preview-offer", "I001", "100")["negotiation"]["preview"]
        self.assertEqual(after, before)
        final = self.store.execute("offer", "I001", "100")["last_roll"]
        self.assertEqual(final["modifier"], before["modifier"])
        self.assertEqual(final["threshold"], before["threshold"])


class PercentileMigrationAudit(PercentilePersistenceAudit):
    # unittest inherits test methods; keep this class focused through a separate
    # load_tests hook below, without depending on the main worker's fixtures.
    def legacy_source(self, version, *, pending=True, same_price_final=False):
        module = {1: _legacy_v1, 2: _legacy_v2, 3: _legacy_v3, 4: _legacy_v4}[version]
        state = synthetic(module, *((10, 20) if version >= 3 else ()))
        if version >= 3 and (pending or same_price_final):
            state["reputation"] = 10
            state["upgrades"]["display"] = 1
            module.apply_command(state, "sell", ["I001", state["visitors"][0]["id"]])
            if same_price_final:
                module.apply_command(state, "offer", ["I001", "9999" if version == 3 else "100"])
        if version <= 2:
            module.apply_command(state, "buy", ["salvage"])
        module._validate_state(state)
        source = self.root / f"synthetic-v{version}.json"
        source.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        return module, source, state

    def test_all_four_imports_preserve_source_core_rng_and_committed_cargo(self):
        for version in (1, 2, 3, 4):
            with self.subTest(version=version):
                _, source, state = self.legacy_source(version)
                blob = source.read_bytes()
                store = engine.GameStore(self.root / f"copy-from-v{version}.json")
                with mock.patch.object(engine.random.Random, "randint", wraps=None) as randint:
                    # v1 creates visitors from a separate deterministic stream;
                    # all other versions must import without any random draws.
                    if version == 1:
                        randint.side_effect = lambda low, high: low
                    else:
                        randint.side_effect = AssertionError("migration drew RNG")
                    store.execute(f"import-v{version}", str(source))
                after = store.load()
                self.assertEqual(source.read_bytes(), blob)
                for key in ("rng", "day", "phase", "energy", "credits", "inventory", "crates", "collection"):
                    self.assertEqual(after[key], json.loads(json.dumps(state[key])), key)
                self.assertEqual(after["version"], 5)
                if version >= 3:
                    old, new = state["negotiation"], after["negotiation"]
                    for key in old:
                        if key != "context": self.assertEqual(new[key], old[key])
                    self.assertEqual(new["context"]["modifier"], old["context"]["modifier"] * 5)
                    self.assertEqual(new["context"]["modifiers"],
                        [dict(m, value=m["value"] * 5) for m in old["context"]["modifiers"]])
                    self.assertEqual(new["rules_version"], 5)
                    self.assertEqual(new["origin_rules_version"], version)
                    self.assertEqual(new["counter_offer"], old["counter_offer"])

    def test_old_pending_final_uses_next_two_digits_without_old_d20_reroll(self):
        for version in (3, 4):
            with self.subTest(version=version):
                _, source, old = self.legacy_source(version)
                store = engine.GameStore(self.root / f"pending-from-v{version}.json")
                store.execute(f"import-v{version}", str(source))
                expected_rng = engine._rng(old)
                expected_digits = expected_rng.randint(0, 9) * 10, expected_rng.randint(0, 9)
                price = str(old["negotiation"]["counter_offer"] + 1)
                preview = store.execute("preview-offer", "I001", price)["negotiation"]["preview"]
                result = store.execute("offer", "I001", price)
                self.assertEqual([r["rules_version"] for r in result["roll_history"]], [version, 5])
                self.assertEqual((result["last_roll"]["tens"], result["last_roll"]["ones"]), expected_digits)
                self.assertEqual(engine._tuple_tree(store.load()["rng"]), expected_rng.getstate())
                self.assertEqual(result["last_roll"]["threshold"], preview["threshold"])
                self.assertEqual(engine.GameStore(store.save_path).execute("status"), result)

    def test_v3_same_price_final_history_is_not_rejudged_as_strict_v5(self):
        _, source, old = self.legacy_source(3, same_price_final=True)
        public = self.store.execute("import-v3", str(source))
        self.assertEqual([r["price"] for r in public["roll_history"]], [9999, 9999])
        for prior, preserved in zip(old["roll_history"], public["roll_history"]):
            self.assertEqual({key: preserved[key] for key in prior}, prior)
            self.assertEqual(preserved["rules_version"], 3)
        self.assertEqual(public["credits"], old["credits"])
        self.store.execute("status")

    def test_v4_with_v3_history_keeps_both_boundaries_and_v5_future_final(self):
        _, _, old = self.legacy_source(3, same_price_final=True)
        state = _legacy_v4.migrate_v3(json.dumps(old).encode())
        extra = synthetic(_legacy_v4)["inventory"][0]
        extra["id"] = "I002"
        state["inventory"].append(extra)
        state["next_item"] = 3
        state["rng"] = seeded_rolls(4, 10, 20)
        _legacy_v4.apply_command(state, "sell", ["I002"])
        _legacy_v4._validate_state(state)
        source = self.root / "mixed-v3-v4.json"
        source.write_text(json.dumps(state), encoding="utf-8")
        self.store.execute("import-v4", str(source))
        imported = self.store.load()
        self.assertEqual(imported["engine_upgrade"]["source_roll_seq"], 3)
        self.assertEqual(imported["engine_upgrade"]["legacy_v3_roll_seq"], 2)
        self.assertEqual(imported["roll_history"], state["roll_history"])
        public = self.store.execute("offer", "I002", "100")
        self.assertEqual([r["rules_version"] for r in public["roll_history"]], [3, 3, 4, 5])
        self.store.execute("status")

    def test_absolute_import_boundary_survives_sixty_row_history_truncation(self):
        _, source, state = self.legacy_source(3)
        initial = state["roll_history"][0]
        state["roll_history"] = [dict(copy.deepcopy(initial), id=seq,
            item_id="I001" if seq == 61 else f"I{seq:03d}_past") for seq in range(2, 62)]
        state["roll_seq"] = 61
        state["negotiation"]["initial_roll_id"] = 61
        state["last_event"]["roll"] = copy.deepcopy(state["roll_history"][-1])
        _legacy_v3._validate_state(state)
        source.write_text(json.dumps(state), encoding="utf-8")
        self.store.execute("import-v3", str(source))
        price = str(state["negotiation"]["counter_offer"] + 1)
        public = self.store.execute("offer", "I001", price)
        self.assertEqual(public["engine_upgrade"]["source_roll_seq"], 61)
        self.assertEqual([r["id"] for r in public["roll_history"]], list(range(3, 63)))
        self.assertEqual([r["rules_version"] for r in public["roll_history"]], [3] * 59 + [5])
        self.store.execute("status")

    def test_import_boundary_and_history_relabelling_corruption_rejected(self):
        _, source, _ = self.legacy_source(4)
        self.store.execute("import-v4", str(source))
        baseline = self.store.load()
        for key, value in (("source_roll_seq", True), ("source_roll_seq", 2),
                           ("legacy_v3_roll_seq", -1), ("legacy_v3_roll_seq", 1)):
            bad = copy.deepcopy(baseline)
            bad["engine_upgrade"][key] = value
            engine._atomic_json(self.store.save_path, bad)
            self.assert_rejected_unchanged("status")
        for field, value in (("rules_version", 5), ("face", 21), ("total", 900),
                             ("success", True), ("rejection_penalty", 3)):
            bad = copy.deepcopy(baseline)
            bad["roll_history"][0][field] = value
            engine._atomic_json(self.store.save_path, bad)
            self.assert_rejected_unchanged("status")

    def test_import_refuses_in_place_existing_destination_and_public_only_sources(self):
        for version in (1, 2, 3, 4):
            module, source, old = self.legacy_source(version)
            blob = source.read_bytes()
            with self.assertRaises(engine.GameError):
                engine.GameStore(source).execute(f"import-v{version}", str(source))
            self.assertEqual(source.read_bytes(), blob)
            target = engine.GameStore(self.root / f"blocked-v{version}.json")
            target.observation_path.write_text("retain existing projection", encoding="utf-8")
            with self.assertRaises(engine.GameError): target.execute(f"import-v{version}", str(source))
            self.assertFalse(target.save_path.exists())
            self.assertEqual(target.observation_path.read_text(), "retain existing projection")
            public_source = self.root / f"public-v{version}.json"
            public_source.write_text(json.dumps(module.observation(old)), encoding="utf-8")
            target = engine.GameStore(self.root / f"reject-public-v{version}.json")
            with self.assertRaises(engine.GameError): target.execute(f"import-v{version}", str(public_source))
            self.assertFalse(target.save_path.exists())

    def test_old_pending_quote_remains_free_to_accept_or_decline_without_rng_draw(self):
        for version in (3, 4):
            _, source, original = self.legacy_source(version)
            original["energy"] = 0
            source.write_text(json.dumps(original), encoding="utf-8")
            blob = source.read_bytes()
            for command in ("accept", "decline"):
                with self.subTest(version=version, command=command):
                    store = engine.GameStore(self.root / f"free-v{version}-{command}.json")
                    store.execute(f"import-v{version}", str(source))
                    before = store.load()
                    with mock.patch.object(engine.random.Random, "randint", side_effect=AssertionError("free response drew RNG")):
                        result = store.execute(command, "I001")
                    self.assertEqual(store.load()["rng"], before["rng"])
                    self.assertEqual(result["energy"], 0)
                    self.assertEqual(result["roll_history"], before["roll_history"])
                    self.assertEqual(result["credits"] - before["credits"],
                        original["negotiation"]["counter_offer"] if command == "accept" else 0)
                    self.assertEqual(source.read_bytes(), blob)

    def test_zero_history_imports_use_v5_for_first_future_roll(self):
        for version in (3, 4):
            with self.subTest(version=version):
                _, source, _ = self.legacy_source(version, pending=False)
                store = engine.GameStore(self.root / f"no-history-v{version}.json")
                store.execute(f"import-v{version}", str(source))
                self.assertEqual(store.load()["engine_upgrade"]["source_roll_seq"], 0)
                public = store.execute("sell", "I001")
                self.assertEqual(public["last_roll"]["rules_version"], 5)
                self.assertEqual(public["last_roll"]["die"], "D100")
                self.assertEqual(store.execute("status"), public)

    def test_v4_container_with_pending_v3_roll_retains_origin_three(self):
        _, _, original = self.legacy_source(3)
        intermediate = _legacy_v4.migrate_v3(json.dumps(original).encode())
        _legacy_v4._validate_state(intermediate)
        source = self.root / "v4-with-pending-v3.json"
        source.write_text(json.dumps(intermediate), encoding="utf-8")
        self.store.execute("import-v4", str(source))
        imported = self.store.load()
        self.assertEqual(imported["negotiation"]["origin_rules_version"], 3)
        self.assertEqual(imported["engine_upgrade"]["source_roll_seq"], 1)
        self.assertEqual(imported["engine_upgrade"]["legacy_v3_roll_seq"], 1)
        price = str(imported["negotiation"]["counter_offer"] + 1)
        public = self.store.execute("offer", "I001", price)
        self.assertEqual([r["rules_version"] for r in public["roll_history"]], [3, 5])
        self.assertEqual(self.store.execute("status"), public)


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    for cls in (PercentileRulesAudit, PercentilePersistenceAudit, PercentileMigrationAudit):
        for name in sorted(cls.__dict__):
            if name.startswith("test_"):
                suite.addTest(cls(name))
    return suite


if __name__ == "__main__":
    unittest.main()
