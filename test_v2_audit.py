#!/usr/bin/env python3
"""Independent v2 audit. All game data is synthetic and stays in TemporaryDirectory."""
import copy
import json
import os
import stat
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import engine
import _legacy_v1


class V2AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="stardust-v2-audit-")
        self.root = Path(self.temp.name)
        self.store = engine.GameStore(self.root / "audit.json")
        self.write(engine.new_state(391))

    def tearDown(self):
        self.temp.cleanup()

    def write(self, state):
        engine._atomic_json(self.store.save_path, state)
        return state

    def synthetic_item(self, catalog_id, item_id="I001", collected=False):
        row = engine.CATALOG_BY_ID[catalog_id]
        return {"catalog_id": row[0], "name": row[1], "rarity": row[2], "kind": row[3],
                "base_value": row[4], "description": row[5], "condition": 70,
                "origin": engine.SUPPLIERS["salvage"]["name"], "collected": collected,
                "repairs": 0, "last_sale_day": 0, "last_repair_day": 0,
                "id": item_id, "price": 1}

    def put_items(self, *catalog_ids):
        state = self.store.load()
        state["inventory"] = [self.synthetic_item(key, f"I{i:03}") for i, key in enumerate(catalog_ids, 1)]
        state["next_item"] = len(catalog_ids) + 1
        state["discovered"] = list(catalog_ids)
        return self.write(state)

    def reject_unchanged(self, command, *args):
        before = self.store.save_path.read_bytes()
        observation_before = self.store.observation_path.read_bytes() if self.store.observation_path.exists() else None
        with self.assertRaises(engine.GameError):
            self.store.execute(command, *args)
        self.assertEqual(before, self.store.save_path.read_bytes())
        if observation_before is not None:
            self.assertEqual(observation_before, self.store.observation_path.read_bytes())

    def prepare_week(self, credits, won=False):
        state = self.store.load()
        state.update(day=7, credits=credits, daily_event=copy.deepcopy(engine.EVENTS[0]))
        if won:
            state["collection"] = [self.synthetic_item(key, f"I{i:03}", True)
                                   for i, key in enumerate(("wrench", "lamp"), 1)]
            state["discovered"] = ["wrench", "lamp"]
            state["next_item"] = 3
        self.write(state)
        return self.store.execute("endday")

    def test_week_summary_requires_post_cost_cash_and_distinct_collection(self):
        for money, won, result in [(664, True, "won"), (663, True, "missed"), (999, False, "missed"), (14, False, "missed")]:
            with self.subTest(money=money, won=won):
                self.write(engine.new_state(391))
                public = self.prepare_week(money, won)
                self.assertEqual(public["phase"], "week_summary")
                self.assertEqual(public["campaign"]["first_week_result"], result)
                self.assertEqual(public["credits"], money - 14)
                self.assertEqual(public["day"], 7)
                self.assertEqual(public["stats"]["days_traded"], 1)

    def test_continue_preserves_assets_and_does_not_charge_twice(self):
        self.prepare_week(664, True)
        before = self.store.load()
        after = self.store.execute("continue")
        self.assertEqual((after["day"], after["phase"]), (8, "active"))
        private = self.store.load()
        for field in ("credits", "inventory", "collection", "crates", "upgrades", "reputation", "stats"):
            self.assertEqual(before[field], private[field], field)
        self.assertEqual(after["energy"], after["max_energy"])
        self.reject_unchanged("continue")

    def test_week_summary_blocks_mutations_but_allows_reading(self):
        self.put_items("wrench")
        self.prepare_week(100)
        for command, args in [("endday", ()), ("buy", ("salvage",)), ("open", ("C001",)),
                              ("repair", ("I001",)), ("collect", ("I001",)), ("sell", ("I001",)),
                              ("upgrade", ("shelf",)), ("price", ("I001", "20"))]:
            with self.subTest(command=command):
                self.reject_unchanged(command, *args)
        for command in ("status", "market", "visitors", "codex"):
            self.store.execute(command)

    def test_long_campaign_beyond_week_remains_active_and_events_do_not_repeat(self):
        self.prepare_week(100000, True)
        self.store.execute("continue")
        for day in range(8, 101):
            before = self.store.load()
            public = self.store.execute("endday")
            self.assertEqual((public["day"], public["phase"]), (day + 1, "active"))
            self.assertEqual(public["credits"], before["credits"] - engine._operating_cost(before))
            self.assertNotEqual(public["daily_event"]["id"], before["daily_event"]["id"])
            self.assertEqual(public["energy"], public["max_energy"])
            self.assertEqual([s["stock"] for s in public["suppliers"]], [4, 2])
            self.assertTrue(all(v["status"] == "waiting" for v in public["visitors"]))

    def test_late_first_week_goal_can_unlock_after_missed_summary(self):
        self.prepare_week(100, True)
        self.store.execute("continue")
        state = self.store.load()
        state["credits"] = 650
        self.write(state)
        state["inventory"] = [self.synthetic_item("coffee", "I003")]
        state["next_item"] = 4
        state["discovered"].append("coffee")
        self.write(state)
        public = self.store.execute("price", "I003", "40")
        self.assertEqual(public["campaign"]["first_week_result"], "missed")
        self.assertEqual(public["campaign"]["completed_milestones"][0]["id"], "first_week")
        self.assertEqual(public["campaign"]["next_milestone"]["id"], "neighborhood")

    def test_bankruptcy_does_not_offer_continue(self):
        state = self.store.load()
        state.update(day=7, credits=13)
        self.write(state)
        public = self.store.execute("endday")
        self.assertEqual((public["phase"], public["credits"]), ("lost", 0))
        self.assertFalse(public["campaign"]["can_continue"])
        self.reject_unchanged("continue")

    def test_v1_import_preserves_source_and_committed_hidden_assets(self):
        original = _legacy_v1.new_state(13)
        _legacy_v1.apply_command(original, "buy", ["salvage"])
        _legacy_v1.apply_command(original, "open", ["C001"])
        _legacy_v1.apply_command(original, "collect", ["I001"])
        _legacy_v1.apply_command(original, "buy", ["salvage"])
        source = self.root / "legacy.json"
        blob = json.dumps(original, ensure_ascii=False).encode()
        source.write_bytes(blob)
        target = engine.GameStore(self.root / "imported.json")
        target.execute("import-v1", str(source))
        migrated = target.load()
        self.assertEqual(source.read_bytes(), blob)
        self.assertFalse((self.root / "legacy.observation.json").exists())
        for field in ("rng", "credits", "inventory", "crates", "collection", "day", "energy", "reputation"):
            self.assertEqual(json.loads(blob)[field], migrated[field], field)
        self.assertEqual(migrated["upgrades"]["display"], 0)

    def test_v1_import_is_deterministic_and_never_rerolls_rng(self):
        blob = json.dumps(_legacy_v1.new_state(59)).encode()
        one = engine.migrate_v1(blob)
        two = engine.migrate_v1(blob)
        self.assertEqual(one, two)
        self.assertEqual(one["rng"], json.loads(blob)["rng"])

    def test_v1_paid_last_fee_with_zero_balance_is_continuable(self):
        state = _legacy_v1.new_state(1)
        state.update(day=7, credits=14)
        _legacy_v1.apply_command(state, "endday", [])
        self.assertEqual(state["last_event"]["title"], "七天试营业结束")
        imported = engine.migrate_v1(json.dumps(state).encode())
        self.assertEqual(imported["phase"], "week_summary")
        self.assertEqual(imported["first_week_result"], "missed")
        self.write(imported)
        public = self.store.execute("continue")
        self.assertEqual((public["day"], public["credits"]), (8, 0))

    def test_v1_genuine_bankruptcy_stays_lost(self):
        for day in (1, 7):
            state = _legacy_v1.new_state(1)
            state.update(day=day, credits=13)
            _legacy_v1.apply_command(state, "endday", [])
            imported = engine.migrate_v1(json.dumps(state).encode())
            self.assertEqual(imported["phase"], "lost")

    def test_v1_won_and_missed_results_remain_at_day_seven(self):
        for money, expected in ((100, "missed"), (1000, "won")):
            state = _legacy_v1.new_state(1)
            state.update(day=7, credits=money)
            state["collection"] = [self.synthetic_item(key, f"I{i:03}", True)
                                   for i, key in enumerate(("wrench", "lamp"), 1)]
            state["next_item"] = 3
            _legacy_v1.apply_command(state, "endday", [])
            imported = engine.migrate_v1(json.dumps(state).encode())
            self.assertEqual((imported["day"], imported["phase"], imported["first_week_result"]), (7, "week_summary", expected))

    def test_v1_import_refuses_all_existing_destinations(self):
        source = self.root / "legacy.json"
        blob = json.dumps(_legacy_v1.new_state(2)).encode()
        source.write_bytes(blob)
        for path in (source, self.store.save_path):
            with self.subTest(path=path.name), self.assertRaises(engine.GameError):
                engine.GameStore(path).execute("import-v1", str(source))
        target = engine.GameStore(self.root / "fresh.json")
        target.observation_path.write_text("existing public file")
        with self.assertRaises(engine.GameError):
            target.execute("import-v1", str(source))
        self.assertEqual(target.observation_path.read_text(), "existing public file")
        self.assertEqual(source.read_bytes(), blob)

    def test_public_tree_has_no_explicit_private_keys(self):
        self.store.execute("buy", "salvage")
        self.store.execute("buy", "curated")
        self.store.execute("open", "C001")
        public = self.store.execute("status")
        forbidden = {"rng", "base_value", "cargo", "catalog_id", "budget", "next_item", "next_crate"}
        def visit(value):
            if isinstance(value, dict):
                self.assertFalse(set(value) & forbidden, set(value) & forbidden)
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)
        visit(public)
        self.assertEqual(set(public["crates"][0]), {"id", "supplier", "name"})

    def test_public_appraisal_does_not_encode_hidden_base_value(self):
        original = self.put_items("radio")
        changed = copy.deepcopy(original)
        changed["inventory"][0]["base_value"] += 5
        one = engine.observation(original)["inventory"][0]
        two = engine.observation(changed)["inventory"][0]
        self.assertEqual(one["value_estimate"], two["value_estimate"],
                         "Private randomized base value must not be reversibly encoded by public appraisal")

    def test_initial_price_does_not_encode_hidden_base_value(self):
        state = engine.new_state(22)
        engine.apply_command(state, "buy", ["salvage"])
        other = copy.deepcopy(state)
        other["crates"][0]["cargo"]["base_value"] += 5
        engine.apply_command(state, "open", ["C001"])
        engine.apply_command(other, "open", ["C001"])
        self.assertEqual(state["inventory"][0]["price"], other["inventory"][0]["price"])

    def test_reads_do_not_mutate_save_bytes_rng_revision_or_event(self):
        self.put_items("wrench")
        before = self.store.save_path.read_bytes()
        for _ in range(3):
            for command, args in [("status", ()), ("market", ()), ("visitors", ()), ("codex", ()), ("inspect", ("I001",))]:
                self.store.execute(command, *args)
                self.assertEqual(before, self.store.save_path.read_bytes())

    def test_invalid_customer_and_resource_failures_do_not_mutate_any_state(self):
        self.put_items("wrench", "lamp")
        self.store.execute("status")
        for command, args in [("sell", ("I001", "missing")), ("price", ("I001", "nan")),
                              ("open", ("C999",)), ("collect", ("missing",)), ("continue", ())]:
            self.reject_unchanged(command, *args)
        state = self.store.load()
        state["energy"] = 0
        self.write(state)
        self.reject_unchanged("sell", "I001", state["visitors"][0]["id"])

    def test_each_customer_and_item_only_get_one_sale_attempt_daily(self):
        self.put_items("wrench", "lamp")
        visitor = self.store.load()["visitors"][0]["id"]
        self.store.execute("price", "I001", "9999")
        public = self.store.execute("sell", "I001", visitor)
        self.assertEqual(next(v for v in public["visitors"] if v["id"] == visitor)["status"], "negotiating")
        self.reject_unchanged("sell", "I002", visitor)
        self.reject_unchanged("sell", "I001")
        self.reject_unchanged("price", "I001", "1")
        self.store.execute("decline", "I001")
        self.store.execute("price", "I001", "1")
        self.reject_unchanged("sell", "I001")
        public = self.store.execute("endday")
        self.assertFalse(public["inventory"][0]["sale_attempted_today"])
        self.store.execute("sell", "I001")

    def test_display_level_two_adds_visitor_next_day_only(self):
        state = self.store.load()
        state["credits"] = 1000
        self.write(state)
        self.store.execute("upgrade", "display")
        second = self.store.execute("upgrade", "display")
        self.assertEqual(len(second["visitors"]), 3)
        self.assertEqual(len(self.store.execute("endday")["visitors"]), 4)

    def test_collection_sets_unlock_after_three_distinct_items_and_perks_apply(self):
        for kind in engine.KINDS:
            with self.subTest(kind=kind):
                self.write(engine.new_state(391))
                keys = [row[0] for row in engine.CATALOG if row[3] == kind][:3]
                before = self.put_items(*keys)
                old_cost = engine._repair_cost(before, self.synthetic_item("wrench"))
                for index in range(1, 4):
                    public = self.store.execute("collect", f"I{index:03}")
                private = self.store.load()
                self.assertTrue(engine._has_set(private, kind))
                perk = next(row for row in public["collection_sets"] if row["id"] == kind)
                self.assertEqual((perk["current"], perk["completed"]), (3, True))
                if kind == "bot":
                    self.assertEqual(public["energy"], before["energy"] - 3 + 1)
                    self.assertEqual(public["max_energy"], 13)
                elif kind == "plant":
                    self.assertEqual(public["operating_cost"], 10)
                elif kind == "signal":
                    next_day = self.store.execute("endday")
                    self.assertEqual(next_day["suppliers"][0]["stock"], 5)
                elif kind == "tool":
                    self.assertEqual(engine._repair_cost(private, self.synthetic_item("wrench")), old_cost - 4)

    def test_all_upgrades_have_three_levels_and_energy_never_exceeds_cap(self):
        state = self.store.load()
        state["credits"] = 10000
        self.write(state)
        for name in engine.UPGRADE_RULES:
            for level in range(1, 4):
                if self.store.load()["energy"] < 2:
                    self.store.execute("endday")
                public = self.store.execute("upgrade", name)
                self.assertEqual(public["upgrades"][name], level)
                self.assertLessEqual(public["energy"], public["max_energy"])
            self.reject_unchanged("upgrade", name)
            self.assertIsNone(public["upgrade_costs"][name])

    def test_projection_write_error_does_not_report_committed_action_as_failed(self):
        original_atomic = engine._atomic_json
        def fail_projection(path, data):
            if Path(path) == self.store.observation_path:
                raise OSError("Synthetic public projection write failure")
            return original_atomic(path, data)
        before = self.store.save_path.read_bytes()
        try:
            with patch.object(engine, "_atomic_json", side_effect=fail_projection):
                public = self.store.execute("buy", "salvage")
        except OSError:
            self.assertEqual(before, self.store.save_path.read_bytes(),
                             "An action reported as failed has already spent money and advanced RNG")
        else:
            self.assertEqual(self.store.load()["credits"], 212)
            self.assertIn("persistence_warning", public)
            self.assertIn("不要重复", public["persistence_warning"])
            recovered = self.store.execute("status")
            self.assertEqual(recovered["credits"], 212)
            self.assertNotIn("persistence_warning", recovered)
            self.assertEqual(json.loads(self.store.observation_path.read_text()), recovered)

    def test_save_failure_before_commit_preserves_money_and_rng(self):
        before = self.store.save_path.read_bytes()
        with patch.object(engine, "_atomic_json", side_effect=OSError("Synthetic save failure")):
            with self.assertRaises(OSError):
                self.store.execute("buy", "salvage")
        self.assertEqual(before, self.store.save_path.read_bytes())

    def test_directory_sync_failure_after_rename_is_reported_as_committed(self):
        original_fsync = os.fsync
        def fail_directory_sync(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("Synthetic directory sync failure")
            return original_fsync(fd)
        with patch.object(engine.os, "fsync", side_effect=fail_directory_sync):
            public = self.store.execute("buy", "salvage")
        self.assertEqual(public["credits"], 212)
        self.assertIn("persistence_warning", public)
        self.assertEqual(len(self.store.load()["crates"]), 1)
        self.assertEqual(self.store.execute("status")["credits"], 212)


if __name__ == "__main__":
    unittest.main(verbosity=2)
