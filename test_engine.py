#!/usr/bin/env python3
"""Deterministic tests. Every fixture lives in TemporaryDirectory, never save.json."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import engine


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="space-shop-test-")
        self.path = Path(self.temp.name) / "test.json"
        self.store = engine.GameStore(self.path)
        self.seed(17)

    def tearDown(self):
        self.temp.cleanup()

    def seed(self, seed=17):
        state = engine.new_state(seed)
        state["revision"] = 1
        engine._atomic_json(self.path, state)
        return state

    def load(self):
        return self.store.load()

    def patch(self, **kwargs):
        state = self.load()
        state.update(kwargs)
        engine._atomic_json(self.path, state)
        return state

    def cargo(self, supplier="salvage"):
        self.store.execute("buy", supplier)
        crate_id = self.load()["crates"][-1]["id"]
        self.store.execute("open", crate_id)
        return self.load()["inventory"][-1]["id"]

    def assert_rejected_unchanged(self, command, *args):
        before = self.path.read_bytes()
        with self.assertRaises(engine.GameError):
            self.store.execute(command, *args)
        self.assertEqual(before, self.path.read_bytes())

    def cli(self, *args):
        return subprocess.run([sys.executable, str(Path(engine.__file__)), "--save", str(self.path), *args], capture_output=True, text=True)

    def test_help_and_missing_game_never_create_save(self):
        self.path.unlink()
        result = self.cli("help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("七天", result.stdout)
        self.assertFalse(self.path.exists())
        self.assertNotEqual(self.cli("status").returncode, 0)
        self.assertFalse(self.path.exists())

    def test_new_explicit_restart_and_no_silent_reroll(self):
        self.assert_rejected_unchanged("new")
        self.assert_rejected_unchanged("restart")
        self.assert_rejected_unchanged("restart", "yes")
        before = self.load()
        after = self.store.execute("restart", "--confirm")
        self.assertGreater(after["revision"], before["revision"])
        self.assertEqual(after["credits"], 260)
        self.assertNotEqual(before["rng"], self.load()["rng"])
        self.path.unlink()
        self.assertEqual(self.store.execute("new")["day"], 1)

    def test_status_market_and_inspect_do_not_advance_or_reroll(self):
        item_id = self.cargo()
        before = self.path.read_bytes()
        state = self.store.execute("status")
        self.assertEqual(state, self.store.execute("status"))
        self.assertEqual(self.store.execute("market")["demand"], state["demand"])
        self.assertEqual(self.store.execute("inspect", item_id), state["inventory"][0])
        self.assertEqual(before, self.path.read_bytes())

    def test_observation_filename_and_recovery(self):
        self.assertEqual(self.store.observation_path.name, "test.observation.json")
        self.assertEqual(engine.GameStore().observation_path.name, "observation.json")
        state = self.store.execute("status")
        self.assertEqual(json.loads(self.store.observation_path.read_text()), state)
        self.store.observation_path.write_text("corrupt")
        before = self.path.read_bytes()
        self.store.execute("status")
        self.assertEqual(json.loads(self.store.observation_path.read_text()), state)
        self.assertEqual(before, self.path.read_bytes())

    def test_buy_commits_contents_and_open_does_not_draw_rng(self):
        observation = self.store.execute("buy", "salvage")
        private = self.load()
        cargo = copy.deepcopy(private["crates"][0]["cargo"])
        rng = private["rng"]
        self.assertEqual(observation["credits"], 212)
        self.assertEqual(observation["energy"], 11)
        self.assertEqual(set(observation["crates"][0]), {"id", "supplier", "name"})
        self.assert_rejected_unchanged("inspect", "C001")
        opened = self.store.execute("open", "C001")
        self.assertEqual(opened["inventory"][0]["name"], cargo["name"])
        self.assertEqual(opened["inventory"][0]["condition"], cargo["condition"])
        self.assertEqual(self.load()["rng"], rng)
        self.assertEqual(opened["last_event"]["type"], "reveal")
        self.assert_rejected_unchanged("open", "C001")

    def test_public_projection_excludes_hidden_data_everywhere(self):
        self.cargo()
        obs = self.store.execute("status")
        def visit(node):
            if isinstance(node, dict):
                self.assertTrue(set(node).isdisjoint({"rng", "base_value", "cargo", "catalog_id", "next_item", "next_crate", "budget"}))
                for value in node.values():
                    visit(value)
            elif isinstance(node, list):
                for value in node:
                    visit(value)
        visit(obs)
        required = {"version", "revision", "day", "total_days", "credits", "reputation", "energy", "max_energy", "goal", "phase", "inventory", "crates", "collection", "suppliers", "upgrades", "demand", "last_event", "log"}
        self.assertTrue(required.issubset(obs))

    def test_both_suppliers_and_stock_limits(self):
        self.patch(credits=2000)
        for _ in range(4):
            self.store.execute("buy", "salvage")
        self.assert_rejected_unchanged("buy", "salvage")
        for _ in range(2):
            self.store.execute("buy", "curated")
        self.assert_rejected_unchanged("buy", "curated")
        state = self.store.execute("market")
        self.assertEqual([s["stock"] for s in state["suppliers"]], [0, 0])

    def test_repair_consumes_money_and_energy_and_is_bounded(self):
        item_id = self.cargo()
        self.patch(credits=2000)
        before = self.store.execute("inspect", item_id)
        energy = self.load()["energy"]
        state = self.store.execute("repair", item_id)
        after = state["inventory"][0]
        self.assertEqual(state["energy"], energy - 2)
        self.assertEqual(state["credits"], 2000 - before["repair_cost"])
        self.assertNotEqual(before["condition"], after["condition"])
        self.assertEqual(after["repairs_remaining"], 1)
        self.assertTrue(after["repair_attempted_today"])
        self.assert_rejected_unchanged("repair", item_id)
        self.store.execute("endday")
        private = self.load()
        private["inventory"][0]["condition"] = 50
        engine._atomic_json(self.path, private)
        self.store.execute("repair", item_id)
        self.store.execute("endday")
        self.assert_rejected_unchanged("repair", item_id)

    def test_repair_has_success_and_failure_outcomes(self):
        outcomes = set()
        for seed in range(30):
            self.seed(seed)
            item_id = self.cargo()
            old = self.store.execute("inspect", item_id)["condition"]
            new = self.store.execute("repair", item_id)["inventory"][0]["condition"]
            outcomes.add(new > old)
        self.assertEqual(outcomes, {True, False})

    def test_perfect_condition_repair_rejected(self):
        item_id = self.cargo()
        state = self.load()
        state["inventory"][0]["condition"] = 100
        engine._atomic_json(self.path, state)
        self.assert_rejected_unchanged("repair", item_id)

    def test_prices_validate_without_mutation_or_energy_cost(self):
        item_id = self.cargo()
        for value in ["0", "-1", "10000", "1.2", "NaN", "abc", "+12", "0012"]:
            self.assert_rejected_unchanged("price", item_id, value)
        before = self.load()
        self.store.execute("price", item_id, "120")
        after = self.load()
        self.assertEqual(after["inventory"][0]["price"], 120)
        self.assertEqual(after["energy"], before["energy"])
        self.assertEqual(after["rng"], before["rng"])

    def test_sale_failure_commits_attempt_and_cannot_be_rerolled(self):
        item_id = self.cargo()
        self.store.execute("price", item_id, "9999")
        before = self.load()
        public = self.store.execute("sell", item_id)
        self.assertEqual(len(public["inventory"]), 1)
        self.assertTrue(public["inventory"][0]["sale_attempted_today"])
        self.assertEqual(public["energy"], before["energy"] - 1)
        self.assertEqual(public["credits"], before["credits"])
        self.assertNotEqual(self.load()["rng"], before["rng"])
        self.assert_rejected_unchanged("sell", item_id)
        self.assertIsNone(public["negotiation"])  # Outrageous asks no longer guarantee a counter.
        self.store.execute("price", item_id, "1")
        self.assert_rejected_unchanged("sell", item_id)
        self.store.execute("endday")
        self.assertFalse(self.store.execute("inspect", item_id)["sale_attempted_today"])
        sold = self.store.execute("sell", item_id)
        self.assertEqual(sold["inventory"], [])
        self.assertGreater(sold["reputation"], 0)
        self.assertEqual(sold["last_event"]["item"]["id"], item_id)

    def test_sale_revenue_and_removal_persist_across_instances(self):
        item_id = self.cargo()
        self.store.execute("price", item_id, "1")
        before = self.load()
        sold = engine.GameStore(self.path).execute("sell", item_id)
        self.assertEqual(sold["credits"], before["credits"] + 1)
        self.assertEqual(self.load()["inventory"], [])
        self.assert_rejected_unchanged("sell", item_id)

    def test_collect_removes_item_and_is_irreversible(self):
        item_id = self.cargo()
        before = self.load()
        result = self.store.execute("collect", item_id)
        self.assertEqual(result["inventory"], [])
        self.assertEqual(result["collection"][0]["id"], item_id)
        self.assertTrue(result["collection"][0]["collected"])
        self.assertEqual(result["credits"], before["credits"])
        self.assertEqual(result["energy"], before["energy"] - 1)
        self.assertEqual(self.store.execute("inspect", item_id)["id"], item_id)
        for command in ["sell", "repair", "collect"]:
            self.assert_rejected_unchanged(command, item_id)

    def test_duplicate_catalog_cannot_be_collected(self):
        item_id = self.cargo()
        self.store.execute("collect", item_id)
        state = self.load()
        duplicate = copy.deepcopy(state["collection"][0])
        duplicate.update(id="I999", collected=False)
        state["inventory"].append(duplicate)
        engine._atomic_json(self.path, state)
        self.assert_rejected_unchanged("collect", "I999")

    def test_workbench_and_shelf_upgrade_costs_and_limits(self):
        self.patch(credits=2000)
        item_id = self.cargo()
        before = self.store.execute("inspect", item_id)["repair_cost"]
        state = self.store.execute("upgrade", "workbench")
        self.assertEqual(state["upgrades"]["workbench"], 1)
        self.assertLess(self.store.execute("inspect", item_id)["repair_cost"], before)
        self.store.execute("upgrade", "workbench")
        self.store.execute("upgrade", "workbench")
        self.assert_rejected_unchanged("upgrade", "workbench")
        state = self.store.execute("upgrade", "shelf")
        self.assertEqual((state["capacity"], state["max_energy"]), (10, 13))
        self.store.execute("endday")
        state = self.store.execute("upgrade", "shelf")
        self.assertEqual(state["capacity"], 13)
        self.store.execute("endday")
        state = self.store.execute("upgrade", "shelf")
        self.assertEqual(state["capacity"], 16)
        self.assertIsNone(state["upgrade_costs"]["shelf"])
        self.assert_rejected_unchanged("upgrade", "shelf")

    def test_capacity_includes_unopened_crates(self):
        item_id = self.cargo()
        state = self.load()
        template = state["inventory"][0]
        state["inventory"] = [dict(template, id=f"I{x:03}") for x in range(1, 8)]
        state["next_item"] = 8
        engine._atomic_json(self.path, state)
        self.assert_rejected_unchanged("buy", "salvage")
        self.store.execute("collect", item_id)
        self.store.execute("buy", "salvage")
        self.assert_rejected_unchanged("buy", "curated")

    def test_insufficient_money_and_energy_never_advance_rng(self):
        self.patch(credits=47)
        self.assert_rejected_unchanged("buy", "salvage")
        self.assert_rejected_unchanged("upgrade", "shelf")
        self.patch(credits=260, energy=0)
        self.assert_rejected_unchanged("buy", "curated")
        after = self.store.execute("endday")
        self.assertEqual(after["energy"], after["max_energy"])

    def test_invalid_commands_parameters_and_ids(self):
        for command, args in [("unknown", []), ("buy", []), ("buy", ["fake"]), ("buy", ["salvage", "x"]),
                              ("open", ["C999"]), ("inspect", ["I999"]), ("repair", ["I999"]), ("sell", ["I999"]),
                              ("collect", ["I999"]), ("price", ["I999", "1"]), ("upgrade", ["spaceship"]),
                              ("status", ["extra"]), ("endday", ["extra"]), ("new", ["extra"])]:
            with self.subTest(command=command, args=args):
                self.assert_rejected_unchanged(command, *args)

    def test_endday_maintenance_reset_and_stable_demand(self):
        self.store.execute("buy", "salvage")
        before = self.load()
        state = self.store.execute("endday")
        self.assertEqual(state["day"], 2)
        self.assertEqual(state["credits"], before["credits"] - 14)
        self.assertEqual(state["energy"], 12)
        self.assertEqual(state["suppliers"][0]["stock"], 4)
        self.assertEqual(len(state["crates"]), 1)
        self.assertEqual(state["demand"], self.store.execute("status")["demand"])
        self.assertEqual(state["last_event"]["type"], "day")

    def test_week_finishes_and_requires_explicit_continue(self):
        fees = 0
        for day in range(1, 8):
            fees += self.store.execute("status")["operating_cost"]
            state = self.store.execute("endday")
            self.assertEqual(state["day"], min(day + 1, 7))
        self.assertEqual(state["phase"], "week_summary")
        self.assertEqual(state["campaign"]["first_week_result"], "missed")
        self.assertEqual(state["credits"], 260 - fees)
        self.assertEqual(state["last_event"]["type"], "end")
        for command, args in [("endday", []), ("buy", ["salvage"]), ("upgrade", ["shelf"])]:
            self.assert_rejected_unchanged(command, *args)
        self.assertTrue(self.store.execute("status")["campaign"]["can_continue"])
        after = self.store.execute("continue")
        self.assertEqual((after["phase"], after["day"]), ("active", 8))
        self.assertEqual(after["credits"], state["credits"])
        self.assert_rejected_unchanged("continue")

    def test_bankruptcy_ends_without_negative_credits(self):
        self.patch(credits=13)
        state = self.store.execute("endday")
        self.assertEqual((state["phase"], state["credits"], state["day"]), ("lost", 0, 1))

    def test_final_win_requires_post_maintenance_cash_and_two_collections(self):
        first = self.cargo()
        self.store.execute("collect", first)
        state = self.load()
        distinct = engine._make_cargo(__import__("random").Random(0), "curated")
        while distinct["catalog_id"] == state["collection"][0]["catalog_id"]:
            distinct = engine._make_cargo(__import__("random").Random(3), "curated")
        distinct.update(id="I888", collected=True, price=100)
        state["collection"].append(distinct)
        state.update(day=7, credits=664)
        state["walkins"]["day"] = 7
        engine._atomic_json(self.path, state)
        won = self.store.execute("endday")
        self.assertEqual((won["phase"], won["credits"]), ("week_summary", 650))
        self.assertEqual(won["campaign"]["first_week_result"], "won")
        state.update(credits=663)
        engine._atomic_json(self.path, state)
        self.assertEqual(self.store.execute("endday")["campaign"]["first_week_result"], "missed")
        state.update(credits=9999, collection=state["collection"][:1])
        engine._atomic_json(self.path, state)
        self.assertEqual(self.store.execute("endday")["campaign"]["first_week_result"], "missed")

    def test_invalid_save_never_silently_resets(self):
        for content in ["broken JSON", "[]", '{"version":999}', '{"version":1}', 'null']:
            self.path.write_text(content)
            before = self.path.read_bytes()
            with self.assertRaises(engine.GameError):
                self.store.execute("status")
            self.assertEqual(self.path.read_bytes(), before)
        state = self.store.execute("restart", "--confirm")
        self.assertEqual(state["credits"], 260)

    def test_save_validation_rejects_corrupt_fields(self):
        for field, value in [("credits", -1), ("energy", 100), ("phase", "fake"), ("rng", []),
                             ("upgrades", {}), ("supplier_stock", {}), ("demand", {}), ("inventory", None)]:
            self.seed()
            self.patch(**{field: value})
            with self.assertRaises(engine.GameError):
                self.store.execute("status")

    def test_cli_gameplay_outputs_valid_public_json(self):
        for args in [("status",), ("market",), ("buy", "salvage"), ("open", "C001"), ("inspect", "I001"),
                     ("repair", "I001"), ("price", "I001", "1"), ("sell", "I001"), ("endday",),
                     ("buy", "salvage"), ("open", "C002"), ("collect", "I002"), ("upgrade", "shelf")]:
            result = self.cli(*args)
            self.assertEqual(result.returncode, 0, (args, result.stderr))
            self.assertIsInstance(json.loads(result.stdout), dict)
        bad = self.cli("price", "I002", "-1")
        self.assertEqual(bad.returncode, 2)
        self.assertFalse(json.loads(bad.stderr)["ok"])

    def test_cross_process_lock_prevents_lost_updates_and_overselling(self):
        self.patch(credits=2000)
        before = self.load()["revision"]
        cmd = [sys.executable, str(Path(engine.__file__)), "--save", str(self.path), "buy", "salvage"]
        processes = [subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(8)]
        results = [(p.communicate(), p.returncode) for p in processes]
        self.assertEqual(sum(code == 0 for _, code in results), 4)
        self.assertEqual(sum(code == 2 for _, code in results), 4)
        state = self.load()
        self.assertEqual((len(state["crates"]), state["credits"], state["energy"]), (4, 2000 - 4 * 48, 8))
        self.assertEqual(state["revision"], before + 4)
        self.assertEqual(len({c["id"] for c in state["crates"]}), 4)
        self.assertEqual(json.loads(self.store.observation_path.read_text())["revision"], state["revision"])

    def test_no_temp_files_left_after_atomic_saves(self):
        self.cargo()
        self.store.execute("endday")
        files = {p.name for p in Path(self.temp.name).iterdir()}
        self.assertEqual(files, {"test.json", "test.observation.json", "test.json.lock"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
