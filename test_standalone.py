"""Standalone smoke tests: relocated source and synthetic temporary games only.

All player actions choose their arguments from public CLI output. Private bytes
are compared only when verifying that a rejected new command cannot overwrite
a synthetic test game; private contents are never parsed or used to play.
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parent
FORBID_GUI = textwrap.dedent("""\
    import importlib.abc
    import sys

    class ForbidGUI(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname.split('.')[0] in {'PIL', 'tkinter', '_tkinter'}:
                raise AssertionError('Headless operation imported ' + fullname)

    sys.meta_path.insert(0, ForbidGUI())
    assert sys.flags.no_site, 'Smoke tests must use python -S'
""")
RUN_CLI = FORBID_GUI + textwrap.dedent("""\
    import runpy
    entry = sys.argv.pop(1)
    sys.argv[0] = entry
    runpy.run_path(entry, run_name='__main__')
""")


class StandaloneTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="standalone-synthetic-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.install = self.root / "relocated shop"
        self.install.mkdir()
        self.engine = self.install / "engine.py"
        shutil.copyfile(ROOT / "engine.py", self.engine)
        self.cwd = self.root / "unrelated working directory"
        self.cwd.mkdir()

    def process(self, script, *args):
        return subprocess.run(
            [sys.executable, "-S", "-B", "-c", script, *map(str, args)],
            cwd=self.cwd, capture_output=True, text=True, encoding="utf-8", timeout=30,
        )

    def cli(self, *args, save=None, returncode=0):
        options = [] if save is None else ["--save", str(save)]
        result = self.process(RUN_CLI, self.engine, *options, *args)
        self.assertEqual(result.returncode, returncode, result.stderr or result.stdout)
        if returncode == 0:
            self.assertEqual(result.stderr, "")
        return result

    def public(self, *args, save=None):
        return json.loads(self.cli(*args, save=save).stdout)

    def assert_public_file(self, path, expected):
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), expected)

    def assert_new_does_not_overwrite(self, save, projection, *, default=False):
        # Opaque byte comparison is limited to this freshly created test game.
        before = save.read_bytes(), projection.read_bytes()
        result = self.cli("new", save=None if default else save, returncode=2)
        self.assertFalse(json.loads(result.stderr)["ok"])
        self.assertEqual(result.stdout, "")
        self.assertEqual((save.read_bytes(), projection.read_bytes()), before)

    def test_engine_import_is_stdlib_only_after_relocation(self):
        script = FORBID_GUI + textwrap.dedent("""\
            from pathlib import Path
            sys.path.insert(0, sys.argv[1])
            import engine
            assert engine.DEFAULT_SAVE == Path(sys.argv[1]) / 'save.json'
            assert not {'PIL', 'tkinter', '_tkinter'} & set(sys.modules)
            print('engine import succeeded without GUI dependencies')
        """)
        result = self.process(script, self.install)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("engine import succeeded", result.stdout)
        self.assertEqual(sorted(p.name for p in self.install.iterdir()), ["engine.py"])
        self.assertEqual(list(self.cwd.iterdir()), [])

    def test_help_and_missing_status_never_create_a_game(self):
        save = self.root / "private" / "unopened.json"
        for command in ("help", "--help"):
            with self.subTest(command=command):
                self.assertIn("buy salvage|curated", self.cli(command, save=save).stdout)
        result = self.cli("status", save=save, returncode=2)
        self.assertFalse(json.loads(result.stderr)["ok"])
        self.assertFalse(save.exists())
        self.assertFalse(save.with_name("unopened.observation.json").exists())
        self.assertFalse((self.install / "save.json").exists())

    def test_custom_cli_new_status_buy_open_uses_only_public_information(self):
        save = self.root / "private" / "captain.save.json"
        projection = save.with_name("captain.save.observation.json")
        opened_shop = self.public("new", save=save)
        self.assertEqual(opened_shop["version"], 10)
        self.assertEqual(opened_shop["day"], 1)
        self.assert_public_file(projection, opened_shop)
        status = self.public("status", save=save)
        self.assertEqual(status, opened_shop)

        supplier = min(
            (row for row in status["suppliers"] if row["stock"] and row["cost"] <= status["credits"]),
            key=lambda row: row["cost"],
        )
        bought = self.public("buy", supplier["id"], save=save)
        self.assertEqual(bought["credits"], status["credits"] - supplier["cost"])
        self.assertEqual(bought["energy"], status["energy"] - 1)
        self.assertEqual(bought["revision"], status["revision"] + 1)
        self.assertEqual(len(bought["crates"]), 1)
        crate = bought["crates"][0]
        self.assertEqual(set(crate), {"id", "supplier", "name"})
        self.assert_public_file(projection, bought)

        opened = self.public("open", crate["id"], save=save)
        self.assertEqual(opened["crates"], [])
        self.assertGreater(len(opened["inventory"]), 0)
        self.assertEqual(opened["last_event"]["type"], "reveal")
        self.assertEqual(opened["credits"], bought["credits"])
        self.assertEqual(opened["energy"], bought["energy"] - 1)
        self.assertEqual(opened["revision"], bought["revision"] + 1)
        self.assert_public_file(projection, opened)
        self.assertEqual(self.public("status", save=save), opened)
        self.assertFalse((self.install / "save.json").exists())
        self.assertFalse((self.install / "observation.json").exists())
        self.assertEqual(list(self.cwd.iterdir()), [])

    def test_default_paths_follow_the_relocated_engine_and_new_cannot_overwrite(self):
        save = self.install / "save.json"
        projection = self.install / "observation.json"
        public = self.public("new")
        self.assertTrue(save.exists())
        self.assert_public_file(projection, public)
        self.assertFalse((self.install / "save.observation.json").exists())
        self.assertEqual(list(self.cwd.iterdir()), [])
        self.assertEqual(self.public("status", save=save), public)
        self.assert_public_file(projection, public)
        self.assertFalse((self.install / "save.observation.json").exists())
        self.assert_new_does_not_overwrite(save, projection, default=True)
        self.assert_new_does_not_overwrite(save, projection)

    def test_custom_save_basename_keeps_custom_mapping_and_cannot_overwrite(self):
        save = self.root / "private" / "save.json"
        projection = save.with_name("save.observation.json")
        public = self.public("new", save=save)
        self.assert_public_file(projection, public)
        self.assertFalse(save.with_name("observation.json").exists())
        self.assertFalse((self.install / "save.json").exists())
        self.assert_new_does_not_overwrite(save, projection)

    def test_full_runner_reports_missing_pillow_without_claiming_a_pass(self):
        runner = self.install / "run_tests.py"
        shutil.copyfile(ROOT / "run_tests.py", runner)
        script = textwrap.dedent("""\
            import importlib.abc
            import runpy
            import sys

            class MissingPillow(importlib.abc.MetaPathFinder):
                def find_spec(self, fullname, path=None, target=None):
                    if fullname.split('.')[0] == 'PIL':
                        raise ModuleNotFoundError('Synthetic missing optional dependency', name=fullname)

            sys.meta_path.insert(0, MissingPillow())
            entry = sys.argv.pop(1)
            sys.argv[0] = entry
            runpy.run_path(entry, run_name='__main__')
        """)
        result = self.process(script, runner)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("Full suite was not run", result.stderr)
        self.assertIn("Pillow", result.stderr)
        self.assertIn("--headless", result.stderr)
        self.assertNotIn("OK", result.stderr)


if __name__ == "__main__":
    unittest.main()
