"""Independent v3/v4 history-boundary regressions; synthetic saves only."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import _legacy_v4 as engine
import _legacy_v3
from test_dice_engine import fixture


class HistoryBoundaryV4Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="stardust-history-synthetic-")
        self.root = Path(self.tmp.name)
        self.store = engine.GameStore(self.root / "synthetic-v4.json")

    def tearDown(self):
        self.tmp.cleanup()

    def import_v3(self, *, pending=True, final=False):
        state = fixture(10, 20)
        state["version"] = 3
        if pending or final:
            _legacy_v3.apply_command(state, "sell", ["I001"])
        if final:
            _legacy_v3.apply_command(state, "offer", ["I001", "9999"])
        _legacy_v3._validate_state(state)
        source = self.root / "synthetic-v3.json"
        source.write_text(json.dumps(state), encoding="utf-8")
        self.store.execute("import-v3", str(source))
        return state, self.store.load()

    def assert_corrupt_rejected_atomically(self, state):
        engine._atomic_json(self.store.save_path, state)
        self.store.observation_path.write_text("existing public projection", encoding="utf-8")
        before = self.store.save_path.read_bytes(), self.store.observation_path.read_bytes()
        with self.assertRaises(engine.GameError):
            self.store.execute("status")
        self.assertEqual(before, (self.store.save_path.read_bytes(), self.store.observation_path.read_bytes()))

    @staticmethod
    def downgrade_final(row):
        row.update(rules_version=3, rejection_penalty=0,
                   base_target=row["target"], counter_offer=None)

    def test_native_and_v2_history_cannot_claim_legacy_same_price_final(self):
        state = fixture(10, 14)
        engine.apply_command(state, "sell", ["I001"])
        engine.apply_command(state, "offer", ["I001", "100"])
        engine._validate_state(state)
        self.downgrade_final(state["roll_history"][-1])
        state["roll_history"][-1]["price"] = 9999
        state["last_event"]["roll"] = copy.deepcopy(state["roll_history"][-1])
        for upgrade in (None, {"from_version": 2, "source_day": 1, "source_phase": "active"}):
            with self.subTest(upgrade=upgrade):
                bad = copy.deepcopy(state)
                bad["engine_upgrade"] = upgrade
                self.assert_corrupt_rejected_atomically(bad)

    def test_imported_pending_initial_and_new_final_cross_boundary_and_reload(self):
        old, imported = self.import_v3()
        self.assertEqual(imported["engine_upgrade"]["source_roll_seq"], 1)
        self.assertEqual(imported["negotiation"], old["negotiation"])
        self.assertEqual(imported["rng"], json.loads(json.dumps(old["rng"])))
        public = self.store.execute("offer", "I001", "100")
        self.assertEqual([row["rules_version"] for row in public["roll_history"]], [3, 4])
        self.assertEqual(public["last_roll"]["rejection_penalty"], 3)
        self.assertEqual(public["last_roll"]["face"], 20)
        self.assertEqual(self.store.load()["engine_upgrade"]["source_roll_seq"], 1)
        self.assertEqual(engine.GameStore(self.store.save_path).execute("status"), public)

    def test_future_imported_roll_cannot_be_downgraded(self):
        self.import_v3()
        self.store.execute("offer", "I001", "100")
        bad = self.store.load()
        self.downgrade_final(bad["roll_history"][-1])
        bad["last_event"]["roll"] = copy.deepcopy(bad["roll_history"][-1])
        self.assert_corrupt_rejected_atomically(bad)

    def test_committed_v3_same_price_final_keeps_original_history(self):
        old, imported = self.import_v3(final=True)
        self.assertEqual(imported["engine_upgrade"]["source_roll_seq"], 2)
        for original, preserved in zip(old["roll_history"], imported["roll_history"]):
            self.assertEqual({key: preserved[key] for key in original}, original)
            self.assertEqual(preserved["rules_version"], 3)
        self.assertEqual([row["price"] for row in imported["roll_history"]], [9999, 9999])
        engine.GameStore(self.store.save_path).execute("status")

    def test_preserved_initial_cannot_be_relabelled_current_rules(self):
        _, state = self.import_v3()
        # Initial-roll formulas coincide; only provenance catches this mutation.
        state["roll_history"][0]["rules_version"] = 4
        self.assert_corrupt_rejected_atomically(state)

    def test_import_boundary_metadata_is_required_integer_and_bounded(self):
        _, state = self.import_v3()
        for boundary in (None, False, True, -1, 2, 1.0, "1"):
            with self.subTest(boundary=boundary):
                bad = copy.deepcopy(state)
                if boundary is None:
                    del bad["engine_upgrade"]["source_roll_seq"]
                else:
                    bad["engine_upgrade"]["source_roll_seq"] = boundary
                self.assert_corrupt_rejected_atomically(bad)
        bad = copy.deepcopy(state)
        bad["engine_upgrade"]["unexpected"] = 1
        self.assert_corrupt_rejected_atomically(bad)

    def test_zero_history_v3_import_uses_v4_for_first_future_roll(self):
        _, state = self.import_v3(pending=False)
        self.assertEqual(state["engine_upgrade"]["source_roll_seq"], 0)
        public = self.store.execute("sell", "I001")
        self.assertEqual(public["last_roll"]["rules_version"], 4)
        engine.GameStore(self.store.save_path).execute("status")

    def test_history_tail_uses_absolute_roll_ids_at_import_boundary(self):
        # Model an already-truncated synthetic legacy history with pending roll61.
        state = fixture(10, 20)
        state["version"] = 3
        _legacy_v3.apply_command(state, "sell", ["I001"])
        initial = state["roll_history"][0]
        state["roll_history"] = [dict(copy.deepcopy(initial), id=seq,
            item_id="I001" if seq == 61 else f"I{seq:03d}_past") for seq in range(2, 62)]
        state["roll_seq"] = 61
        state["negotiation"]["initial_roll_id"] = 61
        state["last_event"]["roll"] = copy.deepcopy(state["roll_history"][-1])
        _legacy_v3._validate_state(state)
        source = self.root / "synthetic-tail-v3.json"
        source.write_text(json.dumps(state), encoding="utf-8")
        self.store.execute("import-v3", str(source))
        public = self.store.execute("offer", "I001", "100")
        self.assertEqual(public["engine_upgrade"]["source_roll_seq"], 61)
        self.assertEqual([row["id"] for row in public["roll_history"]], list(range(3, 63)))
        self.assertEqual([row["rules_version"] for row in public["roll_history"]], [3] * 59 + [4])
        engine.GameStore(self.store.save_path).execute("status")


if __name__ == "__main__":
    unittest.main()
