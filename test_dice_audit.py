"""Independent D20 audit: synthetic temporary saves only; never launch a game UI.

Fixtures deliberately choose test RNG states to cover rare faces. This is a
test-only capability, not a CLI feature or a strategy for an actual player.
"""
import copy
import json
import os
from pathlib import Path
import random
import stat
import tempfile
import unittest
from unittest.mock import patch

import engine
import _legacy_v2


class DiceTransactionAudit(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="stardust-dice-audit-")
        self.root = Path(self.temp.name)
        self.store = engine.GameStore(self.root / "audit.json")
        self.prepare()

    def tearDown(self):
        self.temp.cleanup()

    def item(self, catalog_id, index=1, price=9999):
        row = engine.CATALOG_BY_ID[catalog_id]
        return dict(catalog_id=row[0], name=row[1], rarity=row[2], kind=row[3],
                    base_value=row[4], description=row[5], condition=70,
                    origin=engine.SUPPLIERS["salvage"]["name"], collected=False,
                    repairs=0, last_sale_day=0, last_repair_day=0,
                    id=f"I{index:03}", price=price)

    @staticmethod
    def rng_for(*faces):
        for seed in range(100000):
            probe = random.Random(seed)
            if tuple(probe.randint(1, 20) for _ in faces) == faces:
                return random.Random(seed).getstate()
        raise AssertionError("No synthetic RNG fixture found")

    def write(self, state):
        engine._validate_state(state)
        engine._atomic_json(self.store.save_path, state)
        return self.store.execute("status")

    def prepare(self, faces=(10, 10), named=True, price=9999):
        state = engine.new_state(391)
        state["inventory"] = [self.item("wrench", 1, price), self.item("lamp", 2, price)]
        state["next_item"] = 3
        state["discovered"] = ["wrench", "lamp"]
        state["rng"] = self.rng_for(*faces)
        self.write(state)
        self.customer = state["visitors"][0]["id"] if named else None
        return state

    def sell(self):
        args = ("I001", self.customer) if self.customer else ("I001",)
        return self.store.execute("sell", *args)

    def reject_unchanged(self, command, *args, store=None):
        store = store or self.store
        before = store.save_path.read_bytes()
        public = store.observation_path.read_bytes()
        with self.assertRaises(engine.GameError):
            store.execute(command, *args)
        self.assertEqual(store.save_path.read_bytes(), before, (command, args))
        self.assertEqual(store.observation_path.read_bytes(), public, (command, args))

    def test_natural_twenty_settles_9999_beyond_named_budget(self):
        before = self.prepare(faces=(20,))
        self.assertLess(before["visitors"][0]["budget"], 9999)
        public = self.sell()
        self.assertEqual(public["credits"], before["credits"] + 9999)
        self.assertEqual(public["stats"]["gross_earnings"], 9999)
        self.assertEqual(public["stats"]["sales_count"], 1)
        self.assertEqual(public["energy"], before["energy"] - 1)
        self.assertEqual(public["last_roll"]["outcome"], "miracle")
        self.assertEqual(public["last_roll"]["face"], 20)
        self.assertFalse(any(item["id"] == "I001" for item in public["inventory"]))
        self.assertEqual(public["visitors"][0]["status"], "bought")
        self.assertIsNone(public["negotiation"])
        self.reject_unchanged("sell", "I001", self.customer)
        self.reject_unchanged("sell", "I002", self.customer)

    def test_natural_twenty_also_settles_9999_with_generic_traveler(self):
        before = self.prepare(faces=(20,), named=False)
        public = self.sell()
        self.assertEqual(public["credits"], before["credits"] + 9999)
        self.assertEqual(public["last_roll"]["customer_name"], "旅客")
        self.assertIsNone(public["last_roll"]["customer_id"])

    def test_ordinary_success_settles_the_exact_initial_or_final_offer(self):
        for final in (False, True):
            with self.subTest(final=final):
                before = self.prepare(faces=(10, 19) if final else (19,), price=9999 if final else 1)
                public = self.sell()
                if final:
                    public = self.store.execute("offer", "I001", "1")
                self.assertEqual(public["last_roll"]["outcome"], "success")
                self.assertEqual(public["credits"], before["credits"] + 1)
                self.assertEqual(public["stats"]["gross_earnings"], 1)
                self.assertEqual(public["stats"]["sales_count"], 1)
                self.assertEqual(public["energy"], before["energy"] - (2 if final else 1))
                self.assertIsNone(public["negotiation"])

    def test_ordinary_nineteen_cannot_ignore_budget_even_for_cheap_valuable_item(self):
        state = self.prepare(faces=(19,))
        state["inventory"][0] = self.item("hammer", 1, 260)
        state["inventory"][0]["condition"] = 100
        state["discovered"].append("hammer")
        visitor = next(v for v in state["visitors"] if v["id"] == "sol")
        visitor["budget"] = visitor["budget_range"][0]
        self.customer = visitor["id"]
        context = engine._trade_context(state, state["inventory"][0], visitor)
        without_budget = dict(context, budget=None)
        self.assertLess(engine._trade_target(without_budget, 260), 19 + context["modifier"])
        self.write(state)
        public = self.sell()
        self.assertEqual(public["last_roll"]["outcome"], "failure")
        self.assertEqual(public["credits"], state["credits"])
        self.assertLessEqual(public["negotiation"]["counter_offer"], visitor["budget"])

    def test_natural_one_ends_even_lowest_price_and_high_modifiers(self):
        before = self.prepare(faces=(1,), price=1)
        before["reputation"] = 99
        before["upgrades"]["display"] = 3
        self.write(before)
        public = self.sell()
        self.assertEqual(public["last_roll"]["outcome"], "fumble")
        self.assertEqual(public["credits"], before["credits"])
        self.assertEqual(public["energy"], before["energy"] - 1)
        self.assertIsNone(public["negotiation"])
        self.assertEqual(public["visitors"][0]["status"], "left")
        for cmd, args in [("sell", ("I001",)), ("accept", ("I001",)),
                          ("offer", ("I001", "1")), ("decline", ("I001",)),
                          ("sell", ("I002", self.customer))]:
            self.reject_unchanged(cmd, *args)

    def test_every_noncritical_face_fails_9999_and_creates_one_counter(self):
        for face in range(2, 20):
            with self.subTest(face=face):
                self.prepare(faces=(face,))
                public = self.sell()
                self.assertEqual(public["last_roll"]["outcome"], "failure")
                self.assertEqual(public["negotiation"]["remaining_offers"], 1)
                self.assertEqual(public["negotiation"]["original_price"], 9999)
                self.assertGreaterEqual(public["negotiation"]["counter_offer"], 1)
                self.assertLess(public["negotiation"]["counter_offer"], 9999)
                self.assertEqual(public["visitors"][0]["status"], "negotiating")
                self.assertEqual(len(public["roll_history"]), 1)

    def test_pending_locks_item_customer_and_all_other_sale_attempts(self):
        self.sell()
        other_customer = self.store.load()["visitors"][1]["id"]
        for cmd, args in [("price", ("I001", "2")), ("repair", ("I001",)),
                          ("collect", ("I001",)), ("sell", ("I001",)),
                          ("sell", ("I001", other_customer)), ("sell", ("I002",)),
                          ("sell", ("I002", self.customer)), ("accept", ("I002",)),
                          ("decline", ("I002",)), ("offer", ("I002", "1"))]:
            with self.subTest(command=cmd, args=args):
                self.reject_unchanged(cmd, *args)

    def test_accept_settles_binding_counter_without_extra_energy_or_rng(self):
        pending = self.sell()["negotiation"]
        before = self.store.load()
        public = self.store.execute("accept", "I001")
        after = self.store.load()
        self.assertEqual(after["rng"], before["rng"])
        self.assertEqual(after["roll_history"], before["roll_history"])
        self.assertEqual(public["energy"], before["energy"])
        self.assertEqual(public["credits"], before["credits"] + pending["counter_offer"])
        self.assertEqual(public["stats"]["gross_earnings"], pending["counter_offer"])
        self.assertEqual(public["stats"]["sales_count"], 1)
        self.assertIsNone(public["negotiation"])
        self.assertEqual(public["visitors"][0]["status"], "bought")
        self.reject_unchanged("accept", "I001")
        self.reject_unchanged("offer", "I001", "1")
        self.reject_unchanged("sell", "I002", self.customer)

    def test_decline_ends_item_for_day_even_after_repricing_and_reload(self):
        self.sell()
        before = self.store.load()
        self.store.execute("decline", "I001")
        after = self.store.load()
        for field in ("rng", "roll_history", "energy", "credits"):
            self.assertEqual(before[field], after[field], field)
        self.assertEqual(after["visitors"][0]["status"], "left")
        self.store.execute("price", "I001", "1")
        reopened = engine.GameStore(self.store.save_path)
        self.reject_unchanged("sell", "I001", store=reopened)
        self.reject_unchanged("sell", "I001", after["visitors"][1]["id"], store=reopened)
        self.reject_unchanged("offer", "I001", "1", store=reopened)
        self.reject_unchanged("sell", "I002", self.customer, store=reopened)

    def test_final_natural_twenty_can_settle_original_9999(self):
        before = self.prepare(faces=(10, 20))
        self.sell()
        public = self.store.execute("offer", "I001", "9999")
        self.assertEqual(public["credits"], before["credits"] + 9999)
        self.assertEqual(public["energy"], before["energy"] - 2)
        self.assertEqual(public["last_roll"]["stage"], "final")
        self.assertEqual(public["last_roll"]["outcome"], "miracle")
        self.assertEqual(len(public["roll_history"]), 2)
        self.assertIsNone(public["negotiation"])
        self.reject_unchanged("offer", "I001", "9999")

    def test_final_failures_never_create_third_roll_or_second_counter(self):
        for face in (1, 2, 10, 19):
            with self.subTest(face=face):
                before = self.prepare(faces=(10, face))
                self.sell()
                public = self.store.execute("offer", "I001", "9999")
                self.assertEqual(public["last_roll"]["face"], face)
                self.assertFalse(public["last_roll"]["success"])
                self.assertEqual(public["credits"], before["credits"])
                self.assertEqual(public["energy"], before["energy"] - 2)
                self.assertIsNone(public["negotiation"])
                self.assertEqual(public["visitors"][0]["status"], "left")
                self.assertEqual(len(public["roll_history"]), 2)
                for cmd, args in [("offer", ("I001", "1")), ("sell", ("I001",)),
                                  ("accept", ("I001",)), ("decline", ("I001",))]:
                    self.reject_unchanged(cmd, *args)

    def test_reloaded_pending_keeps_same_quote_and_next_roll(self):
        self.prepare(faces=(10, 20))
        pending = self.sell()["negotiation"]
        blob = self.store.save_path.read_bytes()
        twin = engine.GameStore(self.root / "control.json")
        twin.save_path.write_bytes(blob)
        for _ in range(3):
            self.store = engine.GameStore(self.store.save_path)
            for cmd, args in [("status", ()), ("market", ()), ("visitors", ()),
                              ("codex", ()), ("inspect", ("I001",))]:
                self.store.execute(cmd, *args)
            self.assertEqual(self.store.execute("status")["negotiation"], pending)
            self.assertEqual(self.store.save_path.read_bytes(), blob)
            self.reject_unchanged("sell", "I001", self.customer)
        actual = self.store.execute("offer", "I001", "9999")
        expected = twin.execute("offer", "I001", "9999")
        self.assertEqual(actual, expected)
        self.assertEqual(self.store.load(), twin.load())

    def test_invalid_offers_and_arity_leave_files_and_rng_byte_identical(self):
        self.sell()
        for amount in ("0", "-1", "10000", "01", "+1", "1.0", "NaN", "", "1e2", "９"):
            with self.subTest(amount=amount):
                self.reject_unchanged("offer", "I001", amount)
        for cmd, args in [("offer", ()), ("offer", ("I001",)),
                          ("offer", ("I001", 1)), ("offer", ("I001", "1", "x")),
                          ("accept", ()), ("accept", ("I001", "x")), ("sell", ())]:
            self.reject_unchanged(cmd, *args)

    def test_no_energy_keeps_pending_and_allows_free_accept_or_decline(self):
        for command in ("accept", "decline"):
            with self.subTest(command=command):
                self.prepare()
                self.sell()
                state = self.store.load()
                state["energy"] = 0
                self.write(state)
                self.reject_unchanged("offer", "I001", "1")
                public = self.store.execute(command, "I001")
                self.assertEqual(public["energy"], 0)
                self.assertIsNone(public["negotiation"])

    def test_endday_clears_pending_for_new_day_week_summary_and_bankruptcy(self):
        for day, credits, phase in ((1, 260, "active"), (7, 260, "week_summary"), (1, 0, "lost")):
            with self.subTest(day=day, credits=credits):
                self.prepare()
                state = self.store.load()
                state.update(day=day, credits=credits)
                self.write(state)
                self.sell()
                before = self.store.load()
                public = self.store.execute("endday")
                self.assertIsNone(public["negotiation"])
                self.assertEqual(public["phase"], phase)
                self.assertEqual(public["roll_history"], before["roll_history"])
                self.assertFalse(any(v["status"] == "negotiating" for v in public["visitors"]))
                self.assertTrue(any("自动谢绝" in entry["text"] for entry in public["log"]))
                self.reject_unchanged("accept", "I001")
                if phase == "active":
                    self.assertFalse(public["inventory"][0]["sale_attempted_today"])
                    self.store.execute("sell", "I001")

    def test_pending_context_is_frozen_across_display_upgrade(self):
        self.sell()
        before = self.store.load()
        context = copy.deepcopy(before["negotiation"]["context"])
        self.store.execute("upgrade", "display")
        self.assertEqual(self.store.load()["negotiation"]["context"], context)
        public = self.store.execute("offer", "I001", "9999")
        self.assertEqual(public["last_roll"]["modifier"], context["modifier"])
        self.assertEqual(public["last_roll"]["modifiers"], context["modifiers"])

    def test_public_trade_output_has_no_private_or_future_rng_fields(self):
        public = self.sell()
        forbidden = {"rng", "base_value", "cargo", "catalog_id", "budget", "reference",
                     "context", "next_item", "next_crate", "initial_roll_id"}
        def visit(value):
            if isinstance(value, dict):
                self.assertFalse(set(value) & forbidden, set(value) & forbidden)
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)
        visit(public)
        visit(json.loads(self.store.observation_path.read_bytes()))
        self.assertEqual(public["last_roll"], public["roll_history"][-1])
        self.assertEqual(public["last_event"]["roll"], public["last_roll"])
        private = self.store.load()
        changed = copy.deepcopy(private)
        changed["rng"] = random.Random(999).getstate()
        self.assertEqual(engine.observation(private), engine.observation(changed))

    def test_public_trade_fields_are_defensive_copies(self):
        self.sell()
        private = self.store.load()
        before = copy.deepcopy(private)
        public = engine.observation(private)
        public["negotiation"]["counter_offer"] = 9999
        public["last_roll"]["face"] = 20
        public["roll_history"][0]["modifiers"].append({"label": "test", "value": 99})
        public["last_event"]["roll"]["face"] = 20
        public["inventory"][0]["price"] = 1
        public["visitors"][0]["status"] = "waiting"
        self.assertEqual(private, before)

    def test_corrupt_pending_consistency_is_refused_without_overwrite(self):
        self.sell()
        original = self.store.load()

        def changed_price(state):
            state["inventory"][0]["price"] = 1234
            state["negotiation"]["original_price"] = 1234

        def changed_customer(state):
            state["visitors"][0]["status"] = "left"
            state["negotiation"].update(customer_id=None, customer_name="旅客")
            state["negotiation"]["context"]["budget"] = None

        def changed_counter(state):
            state["negotiation"]["counter_offer"] = 9999

        def changed_day(state):
            state["day"] = 2
            state["inventory"][0]["last_sale_day"] = 2
            state["negotiation"]["day"] = 2

        for corrupt in (changed_price, changed_customer, changed_counter, changed_day):
            with self.subTest(corruption=corrupt.__name__):
                state = copy.deepcopy(original)
                corrupt(state)
                blob = json.dumps(state, ensure_ascii=False).encode()
                self.store.save_path.write_bytes(blob)
                observation_before = self.store.observation_path.read_bytes()
                for command in ("status", "accept"):
                    with self.assertRaises(engine.GameError):
                        self.store.execute(command, *(("I001",) if command == "accept" else ()))
                    self.assertEqual(self.store.save_path.read_bytes(), blob)
                    self.assertEqual(self.store.observation_path.read_bytes(), observation_before)

    def test_orphan_final_roll_is_refused_without_overwrite(self):
        self.sell()
        state = self.store.load()
        state["negotiation"] = None
        state["visitors"][0]["status"] = "left"
        state["roll_history"][0]["stage"] = "final"
        blob = json.dumps(state, ensure_ascii=False).encode()
        self.store.save_path.write_bytes(blob)
        with self.assertRaises(engine.GameError):
            self.store.execute("status")
        self.assertEqual(self.store.save_path.read_bytes(), blob)

    def test_sixty_roll_history_tail_may_begin_with_preceded_final(self):
        state = self.prepare(named=False)
        # Create actual historical actions in a synthetic in-memory campaign;
        # the oldest initial roll should naturally fall off the 60-row tail.
        for day in range(1, 32):
            state["day"] = day
            state["energy"] = 12
            if day > 7:
                state["first_week_result"] = "missed"
            state["rng"] = self.rng_for(10, 10)
            engine.apply_command(state, "sell", ["I001"])
            if day < 31:
                engine.apply_command(state, "offer", ["I001", "9999"])
        self.assertEqual(state["roll_seq"], 61)
        self.assertEqual(len(state["roll_history"]), 60)
        self.assertEqual(state["roll_history"][0]["stage"], "final")
        self.assertEqual(state["roll_history"][0]["id"], 2)
        self.write(state)
        public = self.store.execute("decline", "I001")
        self.assertEqual(len(public["roll_history"]), 60)
        self.assertIsNone(public["negotiation"])

    def test_save_replace_failure_is_atomic_and_retry_uses_same_die(self):
        self.prepare(faces=(20,))
        before = self.store.save_path.read_bytes()
        public_before = self.store.observation_path.read_bytes()
        with patch.object(engine.os, "replace", side_effect=OSError("synthetic pre-commit failure")):
            with self.assertRaises(OSError):
                self.sell()
        self.assertEqual(self.store.save_path.read_bytes(), before)
        self.assertEqual(self.store.observation_path.read_bytes(), public_before)
        self.assertFalse(list(self.root.glob(".audit.json.*")))
        public = self.sell()
        self.assertEqual(public["last_roll"]["face"], 20)
        self.assertEqual(public["stats"]["sales_count"], 1)

    def test_projection_failure_commits_die_and_recovers_without_replay(self):
        original = engine._atomic_json
        def fail_public(path, data):
            if Path(path) == self.store.observation_path:
                raise OSError("synthetic public failure")
            return original(path, data)
        with patch.object(engine, "_atomic_json", side_effect=fail_public):
            public = self.sell()
        self.assertIn("不要重复", public["persistence_warning"])
        self.assertEqual(self.store.load()["roll_seq"], 1)
        before = self.store.save_path.read_bytes()
        self.reject_unchanged("sell", "I001", self.customer)
        recovered = self.store.execute("status")
        self.assertEqual(self.store.save_path.read_bytes(), before)
        self.assertEqual(recovered["negotiation"], public["negotiation"])
        self.assertEqual(json.loads(self.store.observation_path.read_bytes()), recovered)
        self.assertNotIn("persistence_warning", recovered)

    def test_directory_fsync_failure_reports_committed_high_price_sale(self):
        self.prepare(faces=(20,))
        real_fsync = os.fsync
        def fail_directory(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("synthetic directory sync failure")
            return real_fsync(fd)
        with patch.object(engine.os, "fsync", side_effect=fail_directory):
            public = self.sell()
        self.assertIn("不要重复", public["persistence_warning"])
        self.assertEqual(self.store.load()["credits"], 10259)
        self.assertEqual(self.store.load()["stats"]["sales_count"], 1)
        self.reject_unchanged("sell", "I001")
        self.assertEqual(self.store.execute("status")["last_roll"]["face"], 20)

    def legacy_source(self):
        state = _legacy_v2.new_state(391)
        _legacy_v2.apply_command(state, "buy", ["salvage"])
        _legacy_v2.apply_command(state, "open", ["C001"])
        _legacy_v2.apply_command(state, "price", ["I001", "9999"])
        _legacy_v2.apply_command(state, "sell", ["I001", state["visitors"][0]["id"]])
        _legacy_v2.apply_command(state, "buy", ["salvage"])
        blob = json.dumps(state, ensure_ascii=False).encode()
        source = self.root / "legacy-v2.json"
        source.write_bytes(blob)
        return source, blob, json.loads(blob)

    def test_v2_copy_migration_preserves_rng_assets_and_already_used_attempts(self):
        source, blob, before = self.legacy_source()
        target = engine.GameStore(self.root / "imported.json")
        public = target.execute("import-v2", str(source))
        self.assertEqual(source.read_bytes(), blob)
        self.assertFalse(source.with_name("legacy-v2.observation.json").exists())
        after = target.load()
        for key in ("rng", "day", "phase", "energy", "credits", "inventory", "crates", "collection",
                    "visitors", "stats", "upgrades", "reputation", "supplier_stock", "milestones"):
            self.assertEqual(before[key], after[key], key)
        self.assertEqual(after["roll_history"], [])
        self.assertEqual(after["roll_seq"], 0)
        self.assertIsNone(public["negotiation"])
        self.reject_unchanged("sell", "I001", store=target)
        self.assertEqual(engine.migrate_v2(blob), engine.migrate_v2(blob))

    def test_v2_import_refuses_existing_targets_and_wrong_source_without_changes(self):
        source, blob, _ = self.legacy_source()
        for destination in (source, self.store.save_path):
            with self.subTest(destination=destination.name), self.assertRaises(engine.GameError):
                engine.GameStore(destination).execute("import-v2", str(source))
        target = engine.GameStore(self.root / "protected.json")
        target.observation_path.write_text("existing public sentinel")
        with self.assertRaises(engine.GameError):
            target.execute("import-v2", str(source))
        self.assertEqual(target.observation_path.read_text(), "existing public sentinel")
        self.assertFalse(target.save_path.exists())
        for index, invalid in enumerate((b"{}", b"not-json", json.dumps(_legacy_v2.observation(_legacy_v2.new_state(2))).encode())):
            bad = self.root / f"invalid-{index}.json"
            bad.write_bytes(invalid)
            target = engine.GameStore(self.root / f"refused-{index}.json")
            with self.assertRaises(engine.GameError):
                target.execute("import-v2", str(bad))
            self.assertEqual(bad.read_bytes(), invalid)
            self.assertFalse(target.save_path.exists())
            self.assertFalse(target.observation_path.exists())
        self.assertEqual(source.read_bytes(), blob)

    def test_v2_week_summary_and_bankruptcy_never_autocontinue(self):
        for credits, phase in ((260, "week_summary"), (0, "lost")):
            with self.subTest(phase=phase):
                original = _legacy_v2.new_state(391)
                original.update(day=7, credits=credits)
                _legacy_v2.apply_command(original, "endday", [])
                blob = json.dumps(original).encode()
                migrated = engine.migrate_v2(blob)
                engine._validate_state(migrated)
                self.assertEqual(migrated["phase"], phase)
                self.assertEqual(migrated["day"], 7)
                self.assertEqual(migrated["credits"], original["credits"])
                self.assertEqual(migrated["rng"], json.loads(blob)["rng"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
