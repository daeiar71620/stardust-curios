#!/usr/bin/env python3
"""Run the complete suite, or the explicitly maintained stdlib-only suite."""
import argparse
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parent
# Keep this list explicit: new test modules must be reviewed before they become
# part of the promise that --headless never imports Pillow or Tkinter.
HEADLESS_MODULES = (
    "test_engine",
    "test_budget_curve",
    "test_budget_audit",
    "test_campaign",
    "test_campaign_audit",
    "test_catalog_privacy",
    "test_collections",
    "test_latest_only",
    "test_v10_rules",
    "test_management",
    "test_management_audit",
    "test_standalone",
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--headless", action="store_true",
        help="run the engine and standalone CLI tests using only the standard library",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="show each test name")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(ROOT))

    if not args.headless:
        try:
            from PIL import Image, ImageColor, ImageDraw, ImageFont  # noqa: F401
        except ModuleNotFoundError as exc:
            if exc.name != "PIL" and not (exc.name or "").startswith("PIL."):
                raise
            print(
                "Full suite was not run: the optional viewer dependency Pillow is missing.\n"
                "Install it with python3 -m pip install -r requirements-spectator.txt, "
                "then run python3 run_tests.py again.\n"
                "For the standard-library engine and CLI tests, use "
                "python3 run_tests.py --headless.",
                file=sys.stderr,
            )
            return 2

    loader = unittest.TestLoader()
    if args.headless:
        suite = loader.loadTestsFromNames(HEADLESS_MODULES)
        print("Running engine and standalone CLI tests (headless, standard library only).", flush=True)
    else:
        suite = loader.discover(str(ROOT), pattern="test_*.py", top_level_dir=str(ROOT))
        print("Running the full suite, including the optional Pillow spectator tests.", flush=True)
    result = unittest.TextTestRunner(verbosity=2 if args.verbose else 1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
