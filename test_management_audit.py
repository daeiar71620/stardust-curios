"""Independent v6 management audit. Synthetic memory/TemporaryDirectory only.

No default saves, personal play directories, backups, or external services are
read. Fixed RNG seeds avoid searching for preferred outcomes.
"""
import copy
from concurrent.futures import ThreadPoolExecutor
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
import _legacy_v5


def synthetic(module=engine, *, count=1, price=90, seed=0):
    state = module.new_state(42)
    row = module.CATALOG_BY_ID["wrench"]
    state["inventory"] = [dict(id=f"I{index:03d}", catalog_id=row[0],
        name=row[1], rarity=row[2], kind=row[3], base_value=row[4],
        condition=80, description=row[5], origin=module.SUPPLIERS["salvage"]["name"],
        collected=False, repairs=0, last_sale_day=0, last_repair_day=0,
        price=price) for index in range(1, count + 1)]
    state["next_item"] = count + 1
    state["discovered"] = [row[0]]
    # Seed 0 yields 66 then 04. Seed 2 yields 01. These are test fixtures,
    # never player-facing seed controls or searches against a real save.
    state["rng"] = random.Random(seed).getstate()
    return state


class ManagementIndependentAudit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="management-audit-synthetic-")
        self.root = Path(self.tmp.name)
        self.store = engine.GameStore(self.root / "synthetic.json")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, state):
        engine._validate_state(state)
        engine._atomic_json(self.store.save_path, state)
        return self.store.execute("status")

    def pending(self):
        self.write(synthetic())
        result = self.store.execute("sell", "I001")
        self.assertEqual(result["last_roll"]["roll"], 66)
        self.assertIsNotNone(result["negotiation"])
        return result

    def bytes(self):
        return self.store.save_path.read_bytes(), self.store.observation_path.read_bytes()

    def rejected(self, command, *args):
        before = self.bytes()
        with self.assertRaises(engine.GameError):
            self.store.execute(command, *args)
        self.assertEqual(before, self.bytes())

    def test_new_management_field_is_required_before_public_projection(self):
        state = synthetic()
        del state["management_upgrade"]
        engine._atomic_json(self.store.save_path, state)
        self.store.observation_path.write_text("retain public sentinel", encoding="utf-8")
        self.rejected("status")

    def test_two_v6_ordinary_visits_on_same_day_are_rejected_in_history(self):
        state = synthetic(price=9999, count=2)
        engine.apply_command(state, "sell", ["I001"])
        duplicate = copy.deepcopy(state["roll_history"][0])
        duplicate.update(id=2, item_id="I002")
        state["roll_history"].append(duplicate)
        state["roll_seq"] = 2
        state["inventory"][1]["last_sale_day"] = 1
        state["last_event"]["roll"] = copy.deepcopy(duplicate)
        for later_day in (False, True):
            with self.subTest(later_day=later_day):
                changed = copy.deepcopy(state)
                if later_day:
                    changed["day"] = 2
                    changed["walkins"].update(day=2, used=0)
                with self.assertRaises(engine.GameError):
                    engine._validate_state(changed)

    def test_import_day_used_capacity_cannot_add_a_v6_ordinary_initial(self):
        old = synthetic(_legacy_v5, price=9999)
        _legacy_v5.apply_command(old, "sell", ["I001"])
        _legacy_v5.apply_command(old, "decline", ["I001"])
        state = engine.migrate_v5(json.dumps(old).encode())
        duplicate = copy.deepcopy(state["roll_history"][0])
        duplicate.update(id=2, item_id="I002", rules_version=engine.TRADE_RULES_VERSION)
        state["roll_history"].append(duplicate)
        state["roll_seq"] = 2
        state["last_event"]["roll"] = copy.deepcopy(duplicate)
        with self.assertRaises(engine.GameError):
            engine._validate_state(state)

    def test_management_source_versions_must_match_legacy_provenance(self):
        modules = {1: _legacy_v1, 2: _legacy_v2, 3: _legacy_v3, 4: _legacy_v4}
        for version, module in modules.items():
            state = getattr(engine, f"migrate_v{version}")(json.dumps(module.new_state(42)).encode())
            engine._validate_state(state)
            if version == 1:
                state["migration"] = None
            else:
                state["engine_upgrade"] = None
            with self.subTest(source_version=version):
                with self.assertRaises(engine.GameError):
                    engine._validate_state(state)

    def test_v1_v2_management_boundary_cannot_absorb_a_future_percentile_roll(self):
        for version, module in ((1, _legacy_v1), (2, _legacy_v2)):
            state = getattr(engine, f"migrate_v{version}")(json.dumps(synthetic(module, price=9999)).encode())
            engine.apply_command(state, "endday", [])
            engine.apply_command(state, "sell", ["I001"])
            engine._validate_state(state)
            state["management_upgrade"]["source_roll_seq"] = 1
            state["roll_history"][-1]["rules_version"] = 5
            state["last_event"]["roll"]["rules_version"] = 5
            with self.subTest(source_version=version):
                with self.assertRaises(engine.GameError):
                    engine._validate_state(state)

    def test_direct_d20_import_boundaries_cannot_absorb_a_future_percentile_roll(self):
        for version, module in ((3, _legacy_v3), (4, _legacy_v4)):
            old = synthetic(module, price=9999)
            module.apply_command(old, "sell", ["I001"])
            state = getattr(engine, f"migrate_v{version}")(json.dumps(old).encode())
            engine.apply_command(state, "offer", ["I001", "100"])
            engine._validate_state(state)
            state["management_upgrade"]["source_roll_seq"] = 2
            state["roll_history"][-1]["rules_version"] = 5
            state["last_event"]["roll"]["rules_version"] = 5
            with self.subTest(source_version=version):
                with self.assertRaises(engine.GameError):
                    engine._validate_state(state)

    def test_multiple_committed_legacy_ordinary_visits_remain_grandfathered(self):
        old = synthetic(_legacy_v5, count=2, price=9999)
        _legacy_v5.apply_command(old, "sell", ["I001"])
        _legacy_v5.apply_command(old, "decline", ["I001"])
        _legacy_v5.apply_command(old, "sell", ["I002"])
        _legacy_v5._validate_state(old)
        state = engine.migrate_v5(json.dumps(old).encode())
        self.write(state)
        result = self.store.execute("accept", "I002")
        self.assertEqual(result["roll_history"], old["roll_history"])
        self.assertEqual(result["walkins"]["used"], 1)
        self.assertEqual(result["stats"]["sales_count"], 1)

    def test_round_public_reference_before_applying_exact_integer_ratio(self):
        state = synthetic(price=85)
        item = state["inventory"][0]
        item["condition"] = 45
        state["demand"] = {"kind": "tool", "multiplier": 1.25, "label": "synthetic demand"}
        option = engine._sale_option(state, item, None)
        self.assertAlmostEqual(engine._reference_value(state, item), 67.65)
        self.assertEqual((option["public_reference"], option["max_counter_ask"]), (68, 85))
        self.assertTrue(option["counter_eligible"])
        item["price"] = 86
        self.assertFalse(engine._sale_option(state, item, None)["counter_eligible"])

    def test_budget_is_hidden_but_final_offer_has_no_second_private_gate(self):
        initial = self.pending()
        before = self.store.load()
        self.assertLess(before["walkins"]["budget"], 89)
        preview = self.store.execute("preview-offer", "I001", "89")["negotiation"]["preview"]
        result = self.store.execute("offer", "I001", "89")
        self.assertEqual(result["last_roll"]["roll"], 4)
        self.assertTrue(result["last_roll"]["success"])
        self.assertEqual(result["last_roll"]["threshold"], preview["threshold"])
        self.assertEqual(result["credits"], initial["credits"] + 89)
        self.assertEqual(result["walkins"]["used"], 1)

    def test_eligibility_and_unrolled_projection_do_not_depend_on_private_values(self):
        original = synthetic()
        changed = copy.deepcopy(original)
        changed["walkins"]["budget"] = 120
        changed["inventory"][0]["base_value"] = 8888
        changed["rng"] = random.Random(100).getstate()
        for visitor in changed["visitors"]:
            visitor["budget"] = visitor["budget_range"][1]
        engine._validate_state(changed)
        self.assertEqual(engine.observation(original), engine.observation(changed))

    def test_all_read_outputs_and_event_snapshots_exclude_secret_fields(self):
        self.pending()
        forbidden = {"rng", "base_value", "reference", "budget", "cargo", "context"}
        def check(value):
            if isinstance(value, dict):
                self.assertFalse(forbidden.intersection(value))
                for child in value.values(): check(child)
            elif isinstance(value, list):
                for child in value: check(child)
        for command, args in (("status", ()), ("market", ()), ("visitors", ()),
                              ("inspect", ("I001",)), ("codex", ()),
                              ("preview-offer", ("I001", "89"))):
            check(self.store.execute(command, *args))
        check(self.store.execute("accept", "I001"))

    def test_frozen_counter_and_chance_survive_upgrade_reload_and_public_mutation(self):
        public = self.pending()
        original = self.store.load()
        preview = self.store.execute("preview-offer", "I001", "89")["negotiation"]["preview"]
        public["walkins"]["used"] = 0
        public["negotiation"]["counter_offer"] = 9999
        public["inventory"][0]["sale_options"][0]["budget_range"][1] = 9999
        self.store.execute("upgrade", "display")
        reloaded = engine.GameStore(self.store.save_path)
        self.assertEqual(reloaded.load()["negotiation"], original["negotiation"])
        self.assertEqual(reloaded.execute("preview-offer", "I001", "89")["negotiation"]["preview"], preview)

    def test_pending_item_mutations_and_zero_energy_offer_reject_atomically(self):
        self.pending()
        for command, args in (("repair", ("I001",)), ("price", ("I001", "70")),
                              ("collect", ("I001",)), ("sell", ("I001",))):
            self.rejected(command, *args)
        state = self.store.load()
        state["energy"] = 0
        self.write(state)
        self.rejected("offer", "I001", "89")
        before = self.store.load()
        result = self.store.execute("accept", "I001")
        after = self.store.load()
        self.assertEqual((before["rng"], before["energy"]), (after["rng"], after["energy"]))
        self.assertEqual(result["walkins"]["remaining"], 0)

    def test_private_replace_failure_does_not_consume_visit_and_retry_is_identical(self):
        self.write(synthetic())
        before = self.bytes()
        control = engine.GameStore(self.root / "control.json")
        control.save_path.write_bytes(before[0])
        with mock.patch.object(engine.os, "replace", side_effect=OSError("synthetic precommit failure")):
            with self.assertRaises(OSError):
                self.store.execute("sell", "I001")
        self.assertEqual(before, self.bytes())
        self.assertEqual(self.store.load()["walkins"]["used"], 0)
        self.assertEqual(self.store.execute("sell", "I001"), control.execute("sell", "I001"))

    def test_directory_sync_failure_after_commit_does_not_duplicate_visit(self):
        self.write(synthetic(price=9999, count=2))
        original_fsync = engine.os.fsync
        calls = 0
        def fsync(fd):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("synthetic directory sync failure")
            return original_fsync(fd)
        with mock.patch.object(engine.os, "fsync", side_effect=fsync):
            result = self.store.execute("sell", "I001")
        self.assertIn("persistence_warning", result)
        self.assertEqual(self.store.load()["walkins"]["used"], 1)
        self.rejected("sell", "I002")
        self.assertEqual(len(self.store.load()["roll_history"]), 1)

    def test_parallel_accept_decline_offer_settles_exactly_once(self):
        public = self.pending()
        before = self.store.load()
        def act(command):
            try:
                return engine.GameStore(self.store.save_path).execute(command, "I001", *(["89"] if command == "offer" else []))
            except engine.GameError:
                return None
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(act, ("accept", "decline", "offer")))
        self.assertEqual(sum(result is not None for result in results), 1)
        after = self.store.load()
        self.assertIsNone(after["negotiation"])
        self.assertEqual(after["revision"], before["revision"] + 1)
        self.assertEqual(after["walkins"]["used"], 1)
        self.assertIn(after["energy"], (public["energy"], public["energy"] - 1))

    def test_parallel_successful_ordinary_sales_have_only_one_winner(self):
        self.write(synthetic(price=9999, seed=2, count=2))
        before = self.store.load()
        def sell(item):
            try:
                return engine.GameStore(self.store.save_path).execute("sell", item)
            except engine.GameError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(sell, ("I001", "I002")))
        self.assertEqual(sum(result is not None for result in results), 1)
        after = self.store.load()
        self.assertEqual(after["credits"], before["credits"] + 9999)
        self.assertEqual(after["stats"]["sales_count"], 1)
        self.assertEqual((after["walkins"]["used"], after["roll_seq"]), (1, 1))

    def test_week_summary_preserves_spent_visit_until_explicit_next_day(self):
        state = synthetic()
        state["day"] = state["walkins"]["day"] = 7
        self.write(state)
        self.store.execute("sell", "I001")
        summary = self.store.execute("endday")
        self.assertEqual((summary["phase"], summary["day"], summary["walkins"]["used"]), ("week_summary", 7, 1))
        self.rejected("endday")
        self.rejected("sell", "I001")
        result = self.store.execute("continue")
        self.assertEqual((result["phase"], result["day"], result["walkins"]["used"]), ("active", 8, 0))
        self.assertEqual(result["credits"], summary["credits"])
        self.rejected("continue")

    def test_walkin_generation_does_not_perturb_main_rng_or_daily_world(self):
        current, old = engine.new_state(71), _legacy_v5.new_state(71)
        current["credits"] = old["credits"] = 100000
        for _ in range(15):
            for field in ("rng", "visitors", "daily_event", "demand", "energy", "credits", "day"):
                self.assertEqual(current[field], old[field], field)
            command = "continue" if current["phase"] == "week_summary" else "endday"
            engine.apply_command(current, command, [])
            _legacy_v5.apply_command(old, command, [])
            engine._validate_state(current)

    def test_v5_import_with_sixty_history_rows_keeps_absolute_boundary_and_rolls(self):
        old = synthetic(_legacy_v5, price=9999)
        _legacy_v5.apply_command(old, "sell", ["I001"])
        initial = old["roll_history"][0]
        old["roll_history"] = [dict(copy.deepcopy(initial), id=index, day=index)
                               for index in range(1, 61)]
        old.update(day=60, first_week_result="missed", roll_seq=60)
        old["inventory"][0]["last_sale_day"] = 60
        old["negotiation"]["day"] = 60
        old["negotiation"]["initial_roll_id"] = 60
        old["last_event"]["roll"] = copy.deepcopy(old["roll_history"][-1])
        _legacy_v5._validate_state(old)
        source = self.root / "old-v5-synthetic.json"
        source.write_text(json.dumps(old), encoding="utf-8")
        before = source.read_bytes()
        self.store.execute("import-v5", str(source))
        result = self.store.execute("offer", "I001", "100")
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual([row["id"] for row in result["roll_history"]], list(range(2, 62)))
        self.assertEqual([row["rules_version"] for row in result["roll_history"]], [5] * 59 + [engine.TRADE_RULES_VERSION])
        self.assertEqual(result["roll_history"][:-1], old["roll_history"][1:])
        self.assertEqual(self.store.load()["management_upgrade"]["source_roll_seq"], 60)
        self.assertEqual(engine.GameStore(self.store.save_path).execute("status"), result)

    def test_long_campaign_validates_after_all_imported_rolls_leave_history(self):
        old = synthetic(_legacy_v5, price=9999)
        old["credits"] = 100000
        _legacy_v5.apply_command(old, "sell", ["I001"])
        _legacy_v5.apply_command(old, "decline", ["I001"])
        state = engine.migrate_v5(json.dumps(old).encode())
        self.write(state)
        # Actual production commands after a synthetic opening checkpoint. The
        # fixed observation window crosses both week-summary and history-tail
        # boundaries; it does not search for any favorable random outcome.
        for _ in range(65):
            public = self.store.execute("endday")
            if public["phase"] == "week_summary":
                public = self.store.execute("continue")
            if not public["inventory"]:
                public = self.store.execute("buy", "salvage")
                public = self.store.execute("open", public["crates"][0]["id"])
            item = public["inventory"][0]
            self.store.execute("price", item["id"], "9999")
            public = self.store.execute("sell", item["id"])
            self.assertEqual(public["walkins"]["used"], 1)
            self.assertIsNone(public["negotiation"])
            self.assertEqual(engine.GameStore(self.store.save_path).execute("status"), public)
        state = self.store.load()
        self.assertEqual(state["roll_seq"], 66)
        self.assertEqual(len(state["roll_history"]), 60)
        self.assertTrue(all(row["rules_version"] == engine.TRADE_RULES_VERSION for row in state["roll_history"]))
        self.assertEqual(state["management_upgrade"]["source_roll_seq"], 1)


if __name__ == "__main__":
    unittest.main()
