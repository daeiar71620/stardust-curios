"""D20/bargaining regressions. Synthetic fixtures only, no real game started."""
import copy
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import engine
import _legacy_v2


def rng_for(*faces):
    for seed in range(100000):
        rng = random.Random(seed)
        if [rng.randint(1, 20) for _ in faces] == list(faces):
            return random.Random(seed).getstate()
    raise AssertionError(f"No deterministic test seed for {faces}")


def fixture(*faces, price=9999, named=False, day=1):
    state = engine.new_state(42)
    row = engine.CATALOG_BY_ID["wrench"]
    state["inventory"] = [{"id": "I001", "catalog_id": row[0], "name": row[1], "rarity": row[2],
        "kind": row[3], "base_value": row[4], "condition": 80, "description": row[5],
        "origin": engine.SUPPLIERS["salvage"]["name"], "collected": False, "repairs": 0,
        "last_sale_day": 0, "last_repair_day": 0, "price": price}]
    state["next_item"] = 2
    state["discovered"] = [row[0]]
    state["day"] = day
    state["rng"] = rng_for(*faces) if faces else rng_for(10)
    return state


class DiceEngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="stardust-dice-synthetic-")
        self.path = Path(self.tmp.name) / "synthetic.json"
        self.store = engine.GameStore(self.path)
        self.write(fixture(10, 10))

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, state):
        engine._validate_state(state)
        engine._atomic_json(self.path, state)

    def reject(self, command, *args):
        self.store.execute("status")
        before = self.path.read_bytes(), self.store.observation_path.read_bytes()
        with self.assertRaises(engine.GameError):
            self.store.execute(command, *args)
        self.assertEqual(before, (self.path.read_bytes(), self.store.observation_path.read_bytes()))

    def pending(self, first=10, second=10, named=True):
        self.write(fixture(first, second))
        args = ("I001", self.store.load()["visitors"][0]["id"]) if named else ("I001",)
        return self.store.execute("sell", *args)

    def test_natural_twenty_sells_9999_beyond_named_budget(self):
        self.write(fixture(20))
        before = self.store.load()
        visitor = before["visitors"][0]
        self.assertLess(visitor["budget"], 9999)
        obs = self.store.execute("sell", "I001", visitor["id"])
        self.assertEqual(obs["credits"], before["credits"] + 9999)
        self.assertEqual(obs["stats"]["gross_earnings"], 9999)
        self.assertEqual(obs["stats"]["sales_count"], 1)
        self.assertEqual(obs["last_roll"]["outcome"], "miracle")
        self.assertEqual(obs["last_roll"]["face"], 20)
        self.assertLess(obs["last_roll"]["total"], obs["last_roll"]["target"])
        self.assertEqual(obs["inventory"], [])
        self.assertIsNone(obs["negotiation"])
        self.assertEqual(obs["energy"], before["energy"] - 1)
        self.assertEqual(engine.GameStore(self.path).execute("status"), obs)
        self.reject("sell", "I001")

    def test_natural_one_always_fails_without_bargain_even_for_one_coin(self):
        self.write(fixture(1, price=1))
        before = self.store.load()
        obs = self.store.execute("sell", "I001")
        self.assertEqual(obs["last_roll"]["outcome"], "fumble")
        self.assertFalse(obs["last_roll"]["success"])
        self.assertIsNone(obs["negotiation"])
        self.assertEqual(obs["credits"], before["credits"])
        for command, args in [("sell", ("I001",)), ("accept", ("I001",)), ("decline", ("I001",)), ("offer", ("I001", "1"))]:
            self.reject(command, *args)

    def test_actual_rng_roll_and_saved_next_rng_are_exact(self):
        before = self.store.load()
        expected = engine._rng(before)
        face = expected.randint(1, 20)
        obs = self.store.execute("sell", "I001")
        self.assertEqual(obs["last_roll"]["face"], face)
        self.assertEqual(engine._tuple_tree(self.store.load()["rng"]), expected.getstate())
        self.assertEqual(obs["last_event"]["roll"], obs["last_roll"])

    def test_lower_price_quality_and_demand_improve_target(self):
        state = fixture()
        item = state["inventory"][0]
        state["demand"]["kind"] = "plant"
        low = engine._trade_context(state, item, None)
        self.assertLess(engine._trade_target(low, 50), engine._trade_target(low, 100))
        item["condition"] = 100
        high = engine._trade_context(state, item, None)
        self.assertLess(engine._trade_target(high, 100), engine._trade_target(low, 100))
        state["demand"]["kind"] = item["kind"]
        demand = engine._trade_context(state, item, None)
        self.assertLess(engine._trade_target(demand, 100), engine._trade_target(high, 100))

    def test_preference_quality_events_upgrades_and_sets_have_public_modifiers(self):
        state = fixture()
        visitor = state["visitors"][0]
        item = state["inventory"][0]
        visitor["preferred_kind"] = item["kind"]
        visitor["min_condition"] = 70
        state["reputation"] = 99
        state["upgrades"]["display"] = 3
        state["daily_event"] = copy.deepcopy(next(e for e in engine.EVENTS if e["id"] == "festival"))
        ctx = engine._trade_context(state, item, visitor)
        self.assertEqual(ctx["modifier"], 12)  # 3 rep + 3 display + 2 event + 3 preference + 1 condition
        self.assertEqual(ctx["modifier"], sum(m["value"] for m in ctx["modifiers"]))
        visitor["preferred_kind"] = "bot"
        visitor["min_condition"] = 90
        self.assertEqual(engine._trade_context(state, item, visitor)["modifier"], 4)

    def test_budget_blocks_ordinary_nineteen_but_not_twenty(self):
        state = fixture(19, price=150)
        visitor = state["visitors"][0]
        # Tested context directly with high valuation but budget below price.
        context = {"reference": 10000, "budget": 100, "modifier": 5, "modifiers": [{"label": "示例", "value": 5}]}
        self.assertEqual(engine._trade_target(context, 150), 25)
        rng = engine._rng(state)
        roll = engine._trade_roll(state, rng, state["inventory"][0], visitor, 150, context, "initial")
        self.assertEqual(roll["face"], 19)
        self.assertFalse(roll["success"])

    def test_pending_locks_item_and_other_sales_without_mutation(self):
        obs = self.pending()
        self.assertEqual(obs["last_roll"]["face"], 10)
        self.assertTrue(obs["inventory"][0]["negotiating"])
        for command, args in [("price", ("I001", "1")), ("repair", ("I001",)), ("collect", ("I001",)),
                              ("sell", ("I001",)), ("sell", ("I001", obs["visitors"][1]["id"])),
                              ("accept", ("I999",)), ("offer", ("I999", "1"))]:
            self.reject(command, *args)

    def test_reload_status_inspect_and_reads_preserve_pending_and_rng(self):
        obs = self.pending()
        before = self.path.read_bytes()
        for _ in range(3):
            for cmd, args in [("status", ()), ("visitors", ()), ("market", ()), ("inspect", ("I001",)), ("codex", ())]:
                engine.GameStore(self.path).execute(cmd, *args)
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(obs, engine.GameStore(self.path).execute("status"))

    def test_accept_settles_counteroffer_free_at_zero_energy_and_no_rng(self):
        before = self.pending()
        state = self.store.load(); state["energy"] = 0; self.write(state)
        rng = self.store.load()["rng"]
        obs = self.store.execute("accept", "I001")
        self.assertEqual(obs["credits"], before["credits"] + before["negotiation"]["counter_offer"])
        self.assertEqual(obs["energy"], 0)
        self.assertEqual(obs["inventory"], [])
        self.assertEqual(obs["stats"]["sales_count"], 1)
        self.assertEqual(obs["last_roll"], before["last_roll"])
        self.assertEqual(rng, self.store.load()["rng"])
        self.assertIsNone(obs["negotiation"])
        self.reject("accept", "I001")

    def test_decline_is_free_and_ends_daily_attempt(self):
        before = self.pending()
        rng = self.store.load()["rng"]
        obs = self.store.execute("decline", "I001")
        self.assertEqual(obs["credits"], before["credits"])
        self.assertEqual(obs["energy"], before["energy"])
        self.assertEqual(rng, self.store.load()["rng"])
        self.assertIsNone(obs["negotiation"])
        self.store.execute("price", "I001", "1")
        self.reject("sell", "I001")
        self.reject("offer", "I001", "1")

    def test_final_twenty_sells_full_9999_and_only_one_more_roll(self):
        before = self.pending(10, 20)
        obs = engine.GameStore(self.path).execute("offer", "I001", "9999")
        self.assertEqual(obs["credits"], before["credits"] + 9999)
        self.assertEqual(obs["energy"], before["energy"] - 1)
        self.assertEqual(obs["last_roll"]["stage"], "final")
        self.assertEqual(obs["last_roll"]["outcome"], "miracle")
        self.assertEqual(len(obs["roll_history"]), 2)
        self.assertIsNone(obs["negotiation"])
        self.reject("offer", "I001", "9999")
        self.reject("accept", "I001")

    def test_final_failure_and_fumble_close_without_reopening(self):
        for second in (1, 10, 19):
            with self.subTest(second=second):
                self.pending(10, second)
                obs = self.store.execute("offer", "I001", "9999")
                self.assertFalse(obs["last_roll"]["success"])
                self.assertIsNone(obs["negotiation"])
                self.assertEqual(len(obs["roll_history"]), 2)
                self.assertEqual(len(obs["inventory"]), 1)
                self.reject("sell", "I001")
                self.reject("offer", "I001", "1")
                self.reject("accept", "I001")

    def test_final_lower_price_can_succeed_normally(self):
        self.pending(10, 19, named=False)
        obs = self.store.execute("offer", "I001", "40")
        self.assertTrue(obs["last_roll"]["success"])
        self.assertEqual(obs["last_roll"]["outcome"], "success")
        self.assertEqual(obs["credits"], 300)
        self.assertEqual(obs["last_roll"]["price"], 40)

    def test_illegal_final_prices_and_zero_energy_never_consume_rng(self):
        self.pending()
        for bad in ("0", "-1", "10000", "1.0", "01", "nan", "", "一百"):
            self.reject("offer", "I001", bad)
        state = self.store.load(); state["energy"] = 0; self.write(state)
        self.reject("offer", "I001", "9999")
        self.store.execute("decline", "I001")

    def test_final_target_uses_frozen_context_despite_upgrade(self):
        self.pending(named=False)
        state = self.store.load(); state["credits"] = 1000; self.write(state)
        original = copy.deepcopy(state["negotiation"]["context"])
        self.store.execute("upgrade", "display")
        self.assertEqual(original, self.store.load()["negotiation"]["context"])
        obs = self.store.execute("offer", "I001", "9999")
        self.assertEqual(obs["last_roll"]["modifier"], 0)
        self.assertEqual(obs["last_roll"]["target"], engine._trade_target(original, 9999))

    def test_endday_declines_pending_and_next_day_unlocks(self):
        self.pending()
        obs = self.store.execute("endday")
        self.assertEqual(obs["day"], 2)
        self.assertIsNone(obs["negotiation"])
        self.assertFalse(obs["inventory"][0]["negotiating"])
        self.assertFalse(obs["inventory"][0]["sale_attempted_today"])
        self.assertTrue(any("自动谢绝" in entry["text"] for entry in obs["log"]))
        self.store.execute("sell", "I001")
        self.assertEqual(len(self.store.execute("status")["roll_history"]), 2)

    def test_endday_closes_pending_before_summary_or_bankruptcy(self):
        for phase in ("week_summary", "lost"):
            self.pending()
            state = self.store.load()
            if phase == "week_summary":
                state["day"] = 7; state["inventory"][0]["last_sale_day"] = 7
                state["negotiation"]["day"] = 7; state["roll_history"][0]["day"] = 7
            else:
                state["credits"] = 0
            self.write(state)
            obs = self.store.execute("endday")
            self.assertEqual(obs["phase"], phase)
            self.assertIsNone(obs["negotiation"])

    def test_private_judgement_and_future_rng_never_enter_public_tree(self):
        obs = self.pending()
        prohibited = {"rng", "base_value", "cargo", "budget", "reference", "context", "roll_seq", "initial_roll_id"}
        def walk(value):
            if isinstance(value, dict):
                self.assertTrue(prohibited.isdisjoint(value))
                for nested in value.values(): walk(nested)
            elif isinstance(value, list):
                for nested in value: walk(nested)
        walk(obs)
        walk(self.store.execute("offer", "I001", "9999"))

    def test_final_save_failure_rolls_back_everything_and_retry_same_result(self):
        self.pending(10, 20)
        before = self.path.read_bytes(), self.store.observation_path.read_bytes()
        original = engine._atomic_json
        def fail(path, data):
            if Path(path) == self.path: raise OSError("synthetic precommit failure")
            return original(path, data)
        with mock.patch.object(engine, "_atomic_json", side_effect=fail):
            with self.assertRaises(OSError): self.store.execute("offer", "I001", "9999")
        self.assertEqual(before, (self.path.read_bytes(), self.store.observation_path.read_bytes()))
        obs = self.store.execute("offer", "I001", "9999")
        self.assertEqual(obs["last_roll"]["face"], 20)
        self.assertEqual(obs["stats"]["sales_count"], 1)

    def test_projection_failure_keeps_final_roll_and_status_repairs_it(self):
        self.pending(10, 20)
        original = engine._atomic_json
        def fail(path, data):
            if Path(path) == self.store.observation_path: raise OSError("synthetic projection failure")
            return original(path, data)
        with mock.patch.object(engine, "_atomic_json", side_effect=fail):
            obs = self.store.execute("offer", "I001", "9999")
        self.assertIn("persistence_warning", obs)
        fixed = self.store.execute("status")
        self.assertEqual(fixed["last_roll"]["face"], 20)
        self.assertEqual(fixed["stats"]["sales_count"], 1)
        self.assertEqual(json.loads(self.store.observation_path.read_text()), fixed)
        self.reject("offer", "I001", "9999")

    def test_corrupt_dice_and_pending_refused_without_repair_or_reroll(self):
        self.pending()
        original = self.store.load()
        cases = []
        for change in [lambda s: s.update(roll_seq=100), lambda s: s["roll_history"][0].update(face=21),
                       lambda s: s["roll_history"][0].update(total=999), lambda s: s["negotiation"].update(counter_offer=0),
                       lambda s: s["negotiation"]["context"].update(reference=float("inf")),
                       lambda s: s["negotiation"].update(item_id="I999"),
                       lambda s: s["negotiation"].update(initial_roll_id=2),
                       lambda s: s.update(negotiation=None)]:
            state = copy.deepcopy(original); change(state); cases.append(state)
        for state in cases:
            # json.dumps intentionally supports the invalid inf fixture for load validation.
            self.path.write_text(json.dumps(state))
            before = self.path.read_bytes()
            with self.assertRaises(engine.GameError): self.store.execute("status")
            self.assertEqual(before, self.path.read_bytes())

    def test_cross_process_two_final_offers_only_commit_one(self):
        before = self.pending(10, 20)
        cmd = [sys.executable, str(Path(engine.__file__)), "--save", str(self.path), "offer", "I001", "9999"]
        jobs = [subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
        results = [job.communicate(timeout=10) for job in jobs]
        self.assertEqual(sorted(job.returncode for job in jobs), [0, 2], results)
        obs = self.store.execute("status")
        self.assertEqual(obs["revision"], before["revision"] + 1)
        self.assertEqual(len(obs["roll_history"]), 2)
        self.assertEqual(obs["stats"]["gross_earnings"], 9999)

    def test_9999_two_roll_miracle_probability_exactly_9_point_5_percent(self):
        successes = 0
        total_rolls = 0
        for first in range(1, 21):
            for second in range(1, 21):
                state = fixture()
                rng = mock.Mock()
                rng.randint.side_effect = [first, second]
                rng.getstate.return_value = state["rng"]
                with mock.patch.object(engine, "_rng", return_value=rng):
                    engine.apply_command(state, "sell", ["I001"])
                    if state["negotiation"]:
                        engine.apply_command(state, "offer", ["I001", "9999"])
                successes += bool(state["stats"]["sales_count"])
                total_rolls += len(state["roll_history"])
        self.assertEqual(successes, 38)
        self.assertEqual(total_rolls / 400, 1.9)
        self.assertEqual(successes / 400, 0.095)

    def test_v2_import_preserves_source_rng_assets_statistics_and_used_attempts(self):
        source = Path(self.tmp.name) / "v2.json"
        old = _legacy_v2.new_state(55)
        old["credits"] = 2300
        old["stats"]["gross_earnings"] = 2100
        _legacy_v2.apply_command(old, "buy", ["salvage"])
        _legacy_v2.apply_command(old, "open", ["C001"])
        _legacy_v2.apply_command(old, "price", ["I001", "9999"])
        _legacy_v2.apply_command(old, "sell", ["I001"])
        _legacy_v2._atomic_json(source, old)
        original = source.read_bytes()
        destination = engine.GameStore(Path(self.tmp.name) / "copy.json")
        obs = destination.execute("import-v2", str(source))
        upgraded = destination.load()
        self.assertEqual(source.read_bytes(), original)
        for key in ("rng", "inventory", "crates", "collection", "upgrades", "reputation", "visitors", "credits", "energy", "stats"):
            self.assertEqual(upgraded[key], json.loads(original)[key])
        self.assertEqual(obs["roll_history"], [])
        self.assertIsNone(obs["negotiation"])
        self.assertEqual(obs["engine_upgrade"]["from_version"], 2)
        self.assertTrue(obs["inventory"][0]["sale_attempted_today"])
        with self.assertRaises(engine.GameError): destination.execute("sell", "I001")

    def test_v2_import_refuses_original_and_existing_target_or_projection(self):
        source = Path(self.tmp.name) / "v2.json"
        _legacy_v2._atomic_json(source, _legacy_v2.new_state(9))
        original = source.read_bytes()
        with self.assertRaises(engine.GameError): engine.GameStore(source).execute("import-v2", str(source))
        with self.assertRaises(engine.GameError): self.store.execute("import-v2", str(source))
        target = engine.GameStore(Path(self.tmp.name) / "unused.json")
        target.observation_path.write_text("keep")
        with self.assertRaises(engine.GameError): target.execute("import-v2", str(source))
        self.assertEqual(target.observation_path.read_text(), "keep")
        self.assertEqual(source.read_bytes(), original)

    def test_v2_load_needs_explicit_copy_upgrade(self):
        _legacy_v2._atomic_json(self.path, _legacy_v2.new_state(9))
        original = self.path.read_bytes()
        with self.assertRaises(engine.GameError): self.store.execute("status")
        self.assertEqual(self.path.read_bytes(), original)

    def test_v2_summary_upgrade_does_not_continue_or_charge(self):
        old = _legacy_v2.new_state(9)
        old.update(day=7, first_week_result="missed", phase="week_summary", credits=23)
        original = json.dumps(old).encode()
        state = engine.migrate_v2(original)
        engine._validate_state(state)
        self.assertEqual(state["credits"], 23)
        self.assertEqual(state["day"], 7)
        self.assertEqual(state["phase"], "week_summary")
        self.assertEqual(state["rng"], json.loads(original)["rng"])


if __name__ == "__main__":
    unittest.main()
