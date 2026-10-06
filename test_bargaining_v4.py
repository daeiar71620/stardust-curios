"""Strict concession + rejection-cost regressions; synthetic saves only."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import _legacy_v4 as engine
import _legacy_v3
from test_dice_engine import fixture, rng_for


class BargainingV4Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="stardust-v4-synthetic-")
        self.root = Path(self.tmp.name)
        self.store = engine.GameStore(self.root / "synthetic.json")

    def tearDown(self):
        self.tmp.cleanup()

    def pending(self, first=10, second=14, price=9999, named=False):
        state = fixture(first, second, price=price)
        engine._atomic_json(self.store.save_path, state)
        args = ["I001"] + ([state["visitors"][0]["id"]] if named else [])
        return self.store.execute("sell", *args)

    def test_new_price_base_twelve_becomes_fifteen_not_initial_target_floor(self):
        before = self.pending(second=14)
        self.assertGreater(before["last_roll"]["target"], 15)
        public = self.store.execute("offer", "I001", "100")
        roll = public["last_roll"]
        self.assertEqual((roll["base_target"], roll["rejection_penalty"], roll["target"]), (12, 3, 15))
        self.assertEqual((roll["face"], roll["modifier"], roll["total"]), (14, 0, 14))
        self.assertEqual(roll["outcome"], "failure")
        self.assertEqual(public["credits"], before["credits"])
        self.assertEqual(public["energy"], before["energy"] - 1)
        self.assertIsNone(public["negotiation"])
        with self.assertRaises(engine.GameError): self.store.execute("accept", "I001")

    def test_offer_and_preview_reject_equal_initial_or_at_below_counter_atomically(self):
        public = self.pending()
        counter = public["negotiation"]["counter_offer"]
        baseline = self.store.save_path.read_bytes(), self.store.observation_path.read_bytes()
        for command in ("offer", "preview-offer"):
            for value in (9999, 10000, counter, counter - 1, 1, 0):
                with self.subTest(command=command, value=value):
                    with self.assertRaises(engine.GameError): self.store.execute(command, "I001", str(value))
                    self.assertEqual(baseline, (self.store.save_path.read_bytes(), self.store.observation_path.read_bytes()))

    def test_preview_never_draws_or_changes_private_bytes_and_reopen_keeps_same_roll(self):
        before = self.pending(second=15, named=True)
        blob = self.store.save_path.read_bytes()
        twin = engine.GameStore(self.root / "control.json")
        twin.save_path.write_bytes(blob)
        for price in (100, 200, 500, 9998, 100):
            with mock.patch.object(engine.random.Random, "randint", side_effect=AssertionError("preview drew RNG")):
                public = self.store.execute("preview-offer", "I001", str(price))
            self.assertEqual(public["negotiation"]["preview"]["price"], price)
            self.assertFalse(public["negotiation"]["preview"]["suggested"])
            self.assertEqual(public["revision"], before["revision"])
            self.assertEqual(self.store.save_path.read_bytes(), blob)
            self.assertEqual(json.loads(self.store.observation_path.read_text()), public)
        self.assertEqual(engine.GameStore(self.store.save_path).execute("offer", "I001", "100"),
                         twin.execute("offer", "I001", "100"))

    def test_forecast_reads_public_bands_not_secret_reference_or_budget(self):
        self.pending(named=True)
        state = self.store.load()
        other = copy.deepcopy(state)
        # Counter/visible state and frozen modifier are unchanged; test the pure projection.
        other["negotiation"]["context"]["reference"] *= 100
        other["negotiation"]["context"]["budget"] = 1
        other["visitors"][0]["budget"] = 1
        other["inventory"][0]["base_value"] *= 100
        for price in (100, 250, 500, 9998):
            self.assertEqual(engine._offer_forecast(state, state["negotiation"], price),
                             engine._offer_forecast(other, other["negotiation"], price))

    def test_forecast_impossible_ordinary_and_low_threshold_nat_one(self):
        self.pending()
        public = self.store.execute("preview-offer", "I001", "9998")
        preview = public["negotiation"]["preview"]
        self.assertFalse(preview["ordinary_possible"])
        self.assertGreater(preview["required_raw_range"][0], 19)
        self.assertTrue(preview["natural_1_fails"])
        self.assertEqual(preview["natural_20_probability"], .05)
        state = self.store.load()
        state["negotiation"]["context"]["modifier"] = 13
        p = engine._offer_forecast(state, state["negotiation"], 1)
        self.assertEqual(p["required_raw_range"], [2, 2])

    def test_preview_and_actual_final_use_frozen_modifiers_after_upgrade(self):
        self.pending()
        state = self.store.load(); state["credits"] = 1000
        engine._atomic_json(self.store.save_path, state)
        before = self.store.execute("preview-offer", "I001", "100")["negotiation"]["preview"]
        self.store.execute("upgrade", "display")
        after = self.store.execute("preview-offer", "I001", "100")["negotiation"]["preview"]
        self.assertEqual(before, after)
        actual = self.store.execute("offer", "I001", "100")["last_roll"]
        self.assertEqual(actual["modifier"], before["modifier"])
        self.assertEqual(actual["target"], actual["base_target"] + 3)

    def test_ordinary_threshold_and_critical_faces(self):
        for face, outcome in ((1, "fumble"), (14, "failure"), (15, "success"), (19, "success"), (20, "miracle")):
            with self.subTest(face=face):
                before = self.pending(second=face)
                public = self.store.execute("offer", "I001", "100")
                self.assertEqual(public["last_roll"]["outcome"], outcome)
                self.assertEqual(public["credits"] - before["credits"], 100 if face >= 15 else 0)
                self.assertEqual(len(public["roll_history"]), 2)
                self.assertIsNone(public["negotiation"])

    def test_no_integer_between_quotes_allows_only_accept_or_decline(self):
        # A legal, weak initial pitch at price2 can fail despite its low base DC.
        state = fixture(2, 20, price=2)
        state["inventory"][0]["condition"] = 35
        visitor = next(v for v in state["visitors"] if v["preferred_kind"] != "tool")
        engine._atomic_json(self.store.save_path, state)
        public = self.store.execute("sell", "I001", visitor["id"])
        pending = public["negotiation"]
        self.assertEqual(pending["counter_offer"], 1)
        self.assertFalse(pending["final_offer_bounds"]["available"])
        self.assertIsNone(pending["preview"])
        for price in (1, 2):
            with self.assertRaises(engine.GameError): self.store.execute("offer", "I001", str(price))
        self.assertEqual(self.store.execute("accept", "I001")["credits"], public["credits"] + 1)

    def v3_source(self, final=False, pending=True):
        state = fixture(10, 20)
        state["version"] = 3
        _legacy_v3.apply_command(state, "sell", ["I001"])
        if final: _legacy_v3.apply_command(state, "offer", ["I001", "9999"])
        elif not pending: _legacy_v3.apply_command(state, "decline", ["I001"])
        _legacy_v3._validate_state(state)
        source = self.root / "legacy-v3.json"
        source.write_text(json.dumps(state, ensure_ascii=False))
        return source, state

    def test_v3_import_keeps_pending_resources_rng_and_old_history_no_play(self):
        source, before = self.v3_source()
        source_bytes = source.read_bytes()
        public = self.store.execute("import-v3", str(source))
        after = self.store.load()
        self.assertEqual(source.read_bytes(), source_bytes)
        for key in ("rng", "day", "phase", "energy", "credits", "visitors", "inventory", "negotiation", "stats", "roll_seq"):
            self.assertEqual(after[key], json.loads(json.dumps(before[key])))
        self.assertEqual(public["engine_upgrade"]["from_version"], 3)
        self.assertEqual(public["last_roll"]["rules_version"], 3)
        self.assertEqual(public["last_roll"]["rejection_penalty"], 0)
        with self.assertRaises(engine.GameError): self.store.execute("offer", "I001", "9999")
        public = self.store.execute("offer", "I001", "9998")
        self.assertEqual(public["last_roll"]["face"], 20)
        self.assertEqual(public["last_roll"]["rejection_penalty"], 3)
        self.assertEqual(source.read_bytes(), source_bytes)

    def test_v3_same_price_historical_final_is_preserved_without_rejudging(self):
        source, before = self.v3_source(final=True)
        public = self.store.execute("import-v3", str(source))
        for old, imported in zip(before["roll_history"], public["roll_history"]):
            self.assertEqual({key: imported[key] for key in old}, old)
            self.assertEqual(imported["rules_version"], 3)
            self.assertEqual(imported["rejection_penalty"], 0)
        self.assertEqual(public["credits"], before["credits"])

    def test_v3_import_rejects_in_place_existing_target_and_public_projection(self):
        source, before = self.v3_source()
        blob = source.read_bytes()
        with self.assertRaises(engine.GameError): engine.GameStore(source).execute("import-v3", str(source))
        self.assertEqual(source.read_bytes(), blob)
        self.store.observation_path.write_text("keep")
        with self.assertRaises(engine.GameError): self.store.execute("import-v3", str(source))
        self.assertEqual(self.store.observation_path.read_text(), "keep")
        dest = engine.GameStore(self.root / "fresh.json")
        public_source = self.root / "public-v3.json"
        public_source.write_text(json.dumps(_legacy_v3.observation(before)))
        with self.assertRaises(engine.GameError): dest.execute("import-v3", str(public_source))
        self.assertFalse(dest.save_path.exists())
        self.assertFalse(dest.observation_path.exists())
        with self.assertRaises(engine.GameError): engine.GameStore(source).execute("status")
        self.assertEqual(source.read_bytes(), blob)

    def test_highest_base_keeps_full_plus_three_not_capped(self):
        state = fixture(10, 20)
        item = state["inventory"][0]
        context = {"reference": .001, "budget": None, "modifier": 0, "modifiers": []}
        state["negotiation"] = {"counter_offer": 1}
        roll = engine._trade_roll(state, engine._rng(state), item, None, 9998, context, "final")
        self.assertEqual((roll["base_target"], roll["target"]), (99, 102))


if __name__ == "__main__":
    unittest.main()
