"""V2 regressions: synthetic fixtures only, never the user's original game."""
import copy
import json
from pathlib import Path
import random
import tempfile
import unittest

import engine
import _legacy_v1 as legacy


class ExpansionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="stardust-v2-")
        self.path = Path(self.temp.name) / "game.json"
        self.store = engine.GameStore(self.path)
        self.write(engine.new_state(42))

    def tearDown(self):
        self.temp.cleanup()

    def write(self, state):
        engine._atomic_json(self.path, state)

    def reject(self, command, *args):
        private = self.path.read_bytes()
        public = self.store.execute("status")
        projection = self.store.observation_path.read_bytes()
        with self.assertRaises(engine.GameError):
            self.store.execute(command, *args)
        self.assertEqual(self.path.read_bytes(), private)
        self.assertEqual(self.store.observation_path.read_bytes(), projection)
        self.assertEqual(self.store.execute("status"), public)

    def item(self, key, condition=80):
        row = engine.CATALOG_BY_ID[key]
        state = self.store.load()
        item = dict(catalog_id=row[0], name=row[1], rarity=row[2], kind=row[3], base_value=row[4],
                    description=row[5], condition=condition, origin=engine.SUPPLIERS["salvage"]["name"],
                    collected=False, repairs=0, last_sale_day=0, last_repair_day=0,
                    id=f"I{state['next_item']:03d}", price=1)
        state["next_item"] += 1
        state["inventory"].append(item)
        if key not in state["discovered"]:
            state["discovered"].append(key)
        self.write(state)
        return item["id"]

    def test_catalog_has_24_unique_entries_and_five_possible_sets(self):
        self.assertEqual(len(engine.CATALOG), 24)
        self.assertEqual(len(engine.CATALOG_BY_ID), 24)
        for kind in engine.KINDS:
            self.assertGreaterEqual(sum(row[3] == kind for row in engine.CATALOG), 3)
        codex = self.store.execute("codex")
        self.assertEqual((codex["total"], codex["discovered"], codex["collected"]), (24, 0, 0))

    def test_codex_remembers_discoveries_after_sale(self):
        obs = self.store.execute("buy", "salvage")
        obs = self.store.execute("open", obs["crates"][0]["id"])
        item = obs["inventory"][0]
        self.store.execute("price", item["id"], "1")
        self.store.execute("sell", item["id"])
        codex = self.store.execute("codex")
        self.assertEqual(codex["discovered"], 1)
        self.assertFalse(next(e for e in codex["entries"] if e["name"] == item["name"])["collected"])

    def test_new_read_commands_do_not_change_private_rng_or_revision(self):
        private = self.path.read_bytes()
        for _ in range(3):
            self.store.execute("codex")
            self.store.execute("visitors")
            self.store.execute("market")
        self.assertEqual(self.path.read_bytes(), private)
        self.reject("continue")

    def test_named_customer_buys_once_and_preference_adds_reputation(self):
        visitor = self.store.execute("visitors")["visitors"][0]
        key = next(row[0] for row in engine.CATALOG if row[3] == visitor["preferred_kind"])
        first = self.item(key)
        obs = self.store.execute("sell", first, visitor["id"])
        self.assertEqual(obs["reputation"], 2)
        self.assertEqual(next(v for v in obs["visitors"] if v["id"] == visitor["id"])["status"], "bought")
        second = self.item(key)
        self.reject("sell", second, visitor["id"])
        self.store.execute("sell", second)  # Ordinary traveler remains available.

    def test_named_refusal_consumes_both_opportunities_and_budget_never_leaks(self):
        visitor = self.store.execute("visitors")["visitors"][0]
        item = self.item("wrench")
        self.store.execute("price", item, "9999")
        obs = self.store.execute("sell", item, visitor["id"])
        self.assertTrue(obs["inventory"][0]["sale_attempted_today"])
        self.assertEqual(next(v for v in obs["visitors"] if v["id"] == visitor["id"])["status"], "negotiating")
        self.assertNotIn('"budget":', json.dumps(obs))
        self.reject("sell", item)
        self.reject("sell", item, "unknown")

    def test_display_three_levels_and_extra_guest_next_day(self):
        state = self.store.load()
        state["credits"] = 3000
        self.write(state)
        for level in (1, 2, 3):
            obs = self.store.execute("upgrade", "display")
            self.assertEqual(obs["upgrades"]["display"], level)
        self.assertEqual(len(obs["visitors"]), 3)
        self.assertIsNone(obs["upgrade_costs"]["display"])
        self.reject("upgrade", "display")
        self.assertEqual(len(self.store.execute("endday")["visitors"]), 4)

    def test_all_daily_events_apply_visible_costs_energy_and_discounts(self):
        for event in engine.EVENTS:
            state = engine.new_state(42)
            state["daily_event"] = copy.deepcopy(event)
            state["energy"] = engine._max_energy(state)
            self.write(state)
            obs = self.store.execute("status")
            self.assertEqual(obs["max_energy"], 12 + event["energy_delta"])
            self.assertEqual(obs["operating_cost"], 14 + event["cost_delta"])
            buy = self.store.execute("buy", "salvage")
            self.assertEqual(buy["credits"], 260 - obs["suppliers"][0]["cost"])
            obs = self.store.execute("endday")
            self.assertNotEqual(obs["daily_event"]["id"], event["id"])

    def test_all_five_collection_sets_grant_their_actual_perks(self):
        for kind in engine.KINDS:
            self.write(engine.new_state(42))
            for row in [r for r in engine.CATALOG if r[3] == kind][:3]:
                item = self.item(row[0])
                obs = self.store.execute("collect", item)
            group = next(s for s in obs["collection_sets"] if s["id"] == kind)
            self.assertTrue(group["completed"])
            self.assertEqual(group["current"], 3)
            if kind == "bot":
                self.assertEqual(obs["max_energy"], 13)
                self.assertEqual(obs["energy"], 10)
            elif kind == "plant":
                self.assertEqual(obs["operating_cost"], 10)
            elif kind == "tool":
                item = self.item("wrench")
                self.assertEqual(self.store.execute("inspect", item)["repair_cost"], 11)
            elif kind == "signal":
                self.assertEqual(self.store.execute("endday")["suppliers"][0]["stock"], 5)

    def test_long_game_continues_well_past_week_and_repeated_goals_have_no_day_cutoff(self):
        state = self.store.load()
        state["credits"] = 9000
        self.write(state)
        for _ in range(7):
            self.store.execute("endday")
        before = self.store.execute("status")
        self.assertEqual(before["phase"], "week_summary")
        after = self.store.execute("continue")
        self.assertEqual(after["credits"], before["credits"])
        for _ in range(35):
            after = self.store.execute("endday")
        self.assertEqual((after["day"], after["phase"]), (43, "active"))
        self.assertEqual(after["stats"]["days_traded"], 42)

    def test_milestones_persist_even_when_cash_is_spent(self):
        state = self.store.load()
        state.update(day=8, credits=1500, first_week_result="won", reputation=12)
        state["upgrades"].update(workbench=1, shelf=1)
        for index, row in enumerate(engine.CATALOG[:5]):
            item = dict(catalog_id=row[0], name=row[1], rarity=row[2], kind=row[3], base_value=row[4], description=row[5],
                        condition=80, origin=engine.SUPPLIERS["salvage"]["name"], collected=True, repairs=0,
                        last_sale_day=0, last_repair_day=0, id=f"I{index+1:03d}", price=100)
            state["collection"].append(item)
        state["next_item"] = 6
        self.write(state)
        obs = self.store.execute("upgrade", "workbench")  # Cash below 1400: only first goal.
        self.assertEqual(len(obs["campaign"]["completed_milestones"]), 1)
        state = self.store.load()
        state["credits"] = 1600
        self.write(state)
        obs = self.store.execute("upgrade", "display")
        self.assertEqual(len(obs["campaign"]["completed_milestones"]), 2)
        obs = self.store.execute("buy", "curated")
        self.assertEqual(len(obs["campaign"]["completed_milestones"]), 2)

    def test_expanded_validation_rejects_corrupt_fields_without_reset(self):
        for field, value in [("daily_event", {}), ("visitors", []), ("discovered", ["unknown"]),
                             ("milestones", [{"id": "fake"}]), ("stats", {}), ("first_week_result", "fake"),
                             ("migration", {"from_version": 1}), ("day", 9)]:
            self.write(engine.new_state(42))
            state = self.store.load()
            state[field] = value
            self.write(state)
            before = self.path.read_bytes()
            with self.assertRaises(engine.GameError):
                self.store.execute("status")
            self.assertEqual(self.path.read_bytes(), before)


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="stardust-migration-")
        self.source = Path(self.temp.name) / "original.json"
        self.target = Path(self.temp.name) / "new.json"
        self.store = engine.GameStore(self.target)

    def tearDown(self):
        self.temp.cleanup()

    def legacy_state(self, phase="active", day=1, credits=260):
        state = legacy.new_state(17)
        state.update(phase=phase, day=day, credits=credits)
        if phase in {"won", "lost"}:
            legacy._event(state, "end", "星港为你亮灯" if phase == "won" else "七天试营业结束", "合成旧版结算测试")
        legacy._atomic_json(self.source, state)
        return state

    def test_active_import_preserves_source_bytes_rng_and_sealed_contents(self):
        self.legacy_state()
        old = legacy.GameStore(self.source)
        old.execute("buy", "curated")
        state = old.load()
        before = self.source.read_bytes()
        old_public = old.observation_path.read_bytes()
        obs = self.store.execute("import-v1", str(self.source))
        imported = self.store.load()
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(old.observation_path.read_bytes(), old_public)
        self.assertEqual(imported["rng"], state["rng"])
        self.assertEqual(imported["crates"], state["crates"])
        self.assertEqual((obs["day"], obs["phase"], obs["credits"]), (state["day"], "active", state["credits"]))
        self.assertNotIn('"cargo":', json.dumps(obs))
        other = engine.GameStore(Path(self.temp.name) / "same-import.json")
        self.assertEqual(other.execute("import-v1", str(self.source)), obs)

    def test_completed_import_stops_before_day8_and_does_not_charge_twice(self):
        state = self.legacy_state("won", 7, 900)
        before = self.source.read_bytes()
        obs = self.store.execute("import-v1", str(self.source))
        self.assertEqual((obs["phase"], obs["day"], obs["credits"]), ("week_summary", 7, 900))
        self.assertTrue(obs["campaign"]["can_continue"])
        continued = self.store.execute("continue")
        self.assertEqual((continued["day"], continued["credits"]), (8, 900))
        self.assertEqual(self.source.read_bytes(), before)

    def test_missed_old_week_can_continue_even_at_zero_cash(self):
        self.legacy_state("lost", 7, 0)
        obs = self.store.execute("import-v1", str(self.source))
        self.assertEqual(obs["phase"], "week_summary")
        self.assertEqual(obs["campaign"]["first_week_result"], "missed")

    def test_bankruptcy_remains_terminal(self):
        state = self.legacy_state("lost", 7, 0)
        state["last_event"]["title"] = "灯光暂时熄灭"
        legacy._atomic_json(self.source, state)
        obs = self.store.execute("import-v1", str(self.source))
        self.assertEqual(obs["phase"], "lost")
        with self.assertRaises(engine.GameError):
            self.store.execute("continue")

    def test_same_path_existing_target_and_projection_are_never_overwritten(self):
        self.legacy_state()
        before = self.source.read_bytes()
        with self.assertRaises(engine.GameError):
            engine.GameStore(self.source).execute("import-v1", str(self.source))
        self.assertEqual(self.source.read_bytes(), before)
        self.store.execute("import-v1", str(self.source))
        target = self.target.read_bytes()
        with self.assertRaises(engine.GameError):
            self.store.execute("import-v1", str(self.source))
        self.assertEqual(self.target.read_bytes(), target)
        self.target.unlink()
        projection = self.store.observation_path.read_bytes()
        with self.assertRaises(engine.GameError):
            self.store.execute("import-v1", str(self.source))
        self.assertEqual(self.store.observation_path.read_bytes(), projection)

    def test_corrupt_or_public_source_fails_without_destination_save(self):
        for value in [b"bad", b"[]", b'{"version": 2}', json.dumps(legacy.observation(legacy.new_state(1))).encode()]:
            self.source.write_bytes(value)
            with self.assertRaises(engine.GameError):
                self.store.execute("import-v1", str(self.source))
            self.assertFalse(self.target.exists())
            self.assertEqual(self.source.read_bytes(), value)


if __name__ == "__main__":
    unittest.main(verbosity=2)
