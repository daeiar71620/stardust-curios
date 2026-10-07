"""Catalog reveal boundary regressions. Only synthetic temporary saves are used.

Current catalog discovery and artwork use native v10 save and trade rules.
Buying a sealed crate fixes its cargo privately; only opening it reveals a type.
"""
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


def cargo(catalog_id, module=engine):
    row = module.CATALOG_BY_ID[catalog_id]
    return dict(catalog_id=row[0], name=row[1], rarity=row[2], kind=row[3],
                base_value=row[4], condition=80, description=row[5],
                origin=module.SUPPLIERS["salvage"]["name"], collected=False,
                repairs=0, last_sale_day=0, last_repair_day=0)


class CatalogPrivacyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="catalog-synthetic-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = engine.GameStore(self.root / "synthetic.json")
        self.write(engine.new_state(42))

    def write(self, state):
        engine._validate_state(state)
        engine._atomic_json(self.store.save_path, state)

    def buy(self, catalog_id):
        with mock.patch.object(engine, "_make_cargo", return_value=cargo(catalog_id)):
            return self.store.execute("buy", "salvage")

    def opened(self, catalog_id):
        public = self.buy(catalog_id)
        return self.store.execute("open", public["crates"][-1]["id"])

    def assert_codex(self, codex, discovered=(), collected=()):
        discovered, collected = set(discovered), set(collected)
        self.assertEqual(codex["total"], len(engine.CATALOG))
        self.assertEqual(codex["discovered"], len(discovered))
        self.assertEqual(codex["collected"], len(collected))
        self.assertEqual(len(codex["entries"]), len(engine.CATALOG))
        for slot, (entry, row) in enumerate(zip(codex["entries"], engine.CATALOG), 1):
            expected = dict(slot=slot, discovered=row[0] in discovered,
                            collected=row[0] in collected)
            if row[0] in discovered:
                expected.update(art_id=row[0], name=row[1], rarity=row[2],
                                kind=row[3], description=row[5])
            self.assertEqual(entry, expected)

    def assert_no_unseen_identities(self, public, discovered=()):
        """Check all sections, including narrative logs and historical events."""
        text = json.dumps(public, ensure_ascii=False)
        discovered = set(discovered)
        for row in engine.CATALOG:
            if row[0] not in discovered:
                self.assertNotIn(row[1], text)
                self.assertNotIn(row[5], text)
        def visit(node):
            if isinstance(node, dict):
                self.assertTrue(set(node).isdisjoint(
                    {"catalog_id", "cargo", "base_value", "rng", "budget"}))
                if "art_id" in node:
                    self.assertIn(node["art_id"], discovered)
                for value in node.values():
                    visit(value)
            elif isinstance(node, list):
                for value in node:
                    visit(value)
        visit(public)

    def test_new_game_has_only_opaque_slots_in_every_public_section(self):
        public = self.store.execute("status")
        self.assertEqual(public["version"], engine.VERSION)
        self.assert_codex(public["codex"])
        self.assert_no_unseen_identities(public)
        self.assertEqual(len(public["collection_sets"]), 5)
        self.assertTrue(all(row["current"] == 0 and not row["completed"]
                            for row in public["collection_sets"]))

    def test_buying_any_of_the_24_types_never_reveals_its_identity(self):
        baseline = None
        for row in engine.CATALOG:
            with self.subTest(catalog_id=row[0]):
                self.write(engine.new_state(42))
                public = self.buy(row[0])
                self.assert_codex(public["codex"])
                self.assert_no_unseen_identities(public)
                self.assertEqual(public["last_event"]["type"], "buy")
                self.assertIsNone(public["last_event"]["item"])
                self.assertEqual(set(public["crates"][0]), {"id", "supplier", "name"})
                private = self.store.load()
                self.assertEqual(private["crates"][0]["cargo"]["catalog_id"], row[0])
                self.assertEqual(private["discovered"], [])
                if baseline is None:
                    baseline = public
                self.assertEqual(public, baseline)

    def test_open_reveals_exactly_one_slot_for_every_catalog_type(self):
        for row in engine.CATALOG:
            with self.subTest(catalog_id=row[0]):
                self.write(engine.new_state(42))
                sealed = self.buy(row[0])
                rng = self.store.load()["rng"]
                public = self.store.execute("open", "C001")
                self.assert_codex(public["codex"], [row[0]])
                self.assert_no_unseen_identities(public, [row[0]])
                changes = [(a, b) for a, b in zip(sealed["codex"]["entries"],
                                                  public["codex"]["entries"]) if a != b]
                self.assertEqual(len(changes), 1)
                self.assertEqual(public["inventory"][0]["art_id"], row[0])
                self.assertEqual(public["last_event"]["item"]["art_id"], row[0])
                self.assertEqual(self.store.load()["rng"], rng)

    def test_sealed_copy_of_known_type_does_not_count_as_collection(self):
        self.opened("wrench")
        public = self.buy("wrench")
        self.assert_codex(public["codex"], ["wrench"])
        self.assertEqual(len(public["crates"]), 1)
        self.assertEqual(public["collection"], [])
        public = self.store.execute("open", "C002")
        self.assert_codex(public["codex"], ["wrench"])
        self.assertEqual(len(public["inventory"]), 2)

    def test_collecting_changes_collection_flag_without_revealing_other_types(self):
        self.opened("whale")
        public = self.store.execute("collect", "I001")
        self.assert_codex(public["codex"], ["whale"], ["whale"])
        self.assertEqual(public["collection"][0]["art_id"], "whale")
        self.assertEqual(public["inventory"], [])
        self.assert_no_unseen_identities(public, ["whale"])
        self.assertEqual(self.store.execute("inspect", "I001")["art_id"], "whale")

    def test_sale_and_restart_of_reader_keep_discovery_but_not_collection(self):
        self.opened("wrench")
        state = self.store.load()
        state["rng"] = random.Random(2).getstate()  # First percentile roll is 01.
        self.write(state)
        self.store.execute("price", "I001", "1")
        public = self.store.execute("sell", "I001")
        self.assertEqual(public["inventory"], [])
        self.assertEqual(public["stats"]["sales_count"], 1)
        self.assert_codex(public["codex"], ["wrench"])
        self.assert_no_unseen_identities(public, ["wrench"])
        reopened = engine.GameStore(self.store.save_path)
        self.assert_codex(reopened.execute("codex"), ["wrench"])
        before = self.store.save_path.read_bytes()
        with self.assertRaises(engine.GameError):
            reopened.execute("inspect", "I001")
        self.assertEqual(self.store.save_path.read_bytes(), before)

    def test_read_commands_repair_stale_projection_without_mutating_private_save(self):
        self.opened("wrench")
        self.buy("whale")
        before = self.store.save_path.read_bytes()
        for command, args in [("status", ()), ("codex", ()), ("market", ()),
                              ("visitors", ()), ("inspect", ("I001",))]:
            with self.subTest(command=command):
                stale = engine.observation(self.store.load())
                stale["codex"]["entries"] = [dict(name=row[1], kind=row[3],
                    rarity=row[2], description=row[5], discovered=False, collected=False)
                    for row in engine.CATALOG]
                engine._atomic_json(self.store.observation_path, stale)
                result = self.store.execute(command, *args)
                self.assert_no_unseen_identities(result, ["wrench"])
                projected = json.loads(self.store.observation_path.read_text())
                self.assert_codex(projected["codex"], ["wrench"])
                self.assert_no_unseen_identities(projected, ["wrench"])
                self.assertEqual(self.store.save_path.read_bytes(), before)

    def test_failed_open_or_inspect_cannot_reveal_committed_cargo(self):
        self.buy("letter")
        for command, item in [("inspect", "C001"), ("inspect", "I001"),
                              ("open", "C999")]:
            with self.subTest(command=command, item=item):
                before = self.store.save_path.read_bytes(), self.store.observation_path.read_bytes()
                with self.assertRaises(engine.GameError):
                    self.store.execute(command, item)
                self.assertEqual(before, (self.store.save_path.read_bytes(),
                                          self.store.observation_path.read_bytes()))
        state = self.store.load()
        state["energy"] = 0
        self.write(state)
        before = self.store.save_path.read_bytes()
        with self.assertRaises(engine.GameError):
            self.store.execute("open", "C001")
        self.assertEqual(self.store.save_path.read_bytes(), before)
        self.assert_codex(self.store.execute("codex"))

    def test_held_items_are_known_even_with_incomplete_discovery_list(self):
        self.opened("wrench")
        self.opened("lamp")
        self.store.execute("collect", "I001")
        self.buy("letter")
        state = self.store.load()
        state["discovered"] = []
        self.write(state)
        before = self.store.save_path.read_bytes()
        public = self.store.execute("status")
        self.assert_codex(public["codex"], ["wrench", "lamp"], ["wrench"])
        self.assert_no_unseen_identities(public, ["wrench", "lamp"])
        self.assertEqual(self.store.save_path.read_bytes(), before)


    def test_cli_outputs_share_the_reveal_boundary(self):
        def cli(command, *args):
            return subprocess.run([sys.executable, str(Path(engine.__file__).resolve()),
                "--save", str(self.store.save_path), command, *args],
                capture_output=True, text=True, check=False)
        result = cli("buy", "salvage")
        self.assertEqual(result.returncode, 0, result.stderr)
        sealed = json.loads(result.stdout)
        self.assert_codex(sealed["codex"])
        self.assert_no_unseen_identities(sealed)
        before = self.store.save_path.read_bytes()
        for command in ["status", "codex", "market", "visitors"]:
            result = cli(command)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assert_no_unseen_identities(json.loads(result.stdout))
        self.assertNotEqual(cli("inspect", "C001").returncode, 0)
        self.assertEqual(self.store.save_path.read_bytes(), before)
        result = cli("open", "C001")
        self.assertEqual(result.returncode, 0, result.stderr)
        public = json.loads(result.stdout)
        identity = public["inventory"][0]["art_id"]
        self.assert_codex(public["codex"], [identity])
        self.assert_no_unseen_identities(public, [identity])
        result = cli("inspect", "I001")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["art_id"], identity)

    def test_public_projection_is_pure_and_isolated_from_caller_mutation(self):
        self.opened("wrench")
        state = self.store.load()
        before = copy.deepcopy(state)
        public = engine.observation(state)
        public["codex"]["entries"][0].update(art_id="letter", name="changed")
        public["inventory"][0]["art_id"] = "letter"
        self.assertEqual(state, before)
        self.assert_codex(engine.observation(state)["codex"], ["wrench"])


if __name__ == "__main__":
    unittest.main()
