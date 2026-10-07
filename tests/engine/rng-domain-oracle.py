"""Synthetic RNG domain and initialization-sequence oracle.

Reads only the explicitly supplied public engine source. Extracts three audited
pure helpers and their literal constants through AST; never imports the engine,
constructs a game save, reads a save, or writes fixtures to disk.
"""
import ast
import hashlib
import json
from pathlib import Path
import random
import sys


def load_public_helpers(source_path):
    tree = ast.parse(Path(source_path).read_text(encoding="utf-8"))
    constants = {"KINDS", "CUSTOMERS", "WALKIN_BUDGET_RANGE"}
    helpers = {"_daily_demand", "_make_visitors", "_make_walkins"}
    namespace = {"random": random, "hashlib": hashlib, "json": json}
    definitions = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in constants:
                    namespace[target.id] = ast.literal_eval(node.value)
        elif isinstance(node, ast.FunctionDef) and node.name in helpers:
            definitions.append(node)
    if len(definitions) != len(helpers) or not constants.issubset(namespace):
        raise RuntimeError("Expected public pure helper contract is missing")
    module = ast.Module(body=definitions, type_ignores=[])
    exec(compile(module, str(source_path), "exec"), namespace)
    return namespace


def derive_fixture(public, rng, day):
    before = rng.getstate()
    serialized = json.dumps(before, separators=(",", ":"))
    material = b"walkin-v6:" + str(day).encode() + b":" + serialized.encode()
    walkins = public["_make_walkins"](rng, day)
    assert rng.getstate() == before
    return {"day": str(day), "budget": walkins["budget"],
            "digest": hashlib.sha256(material).hexdigest(),
            "walkins_used": walkins["used"]}


def main():
    public = load_public_helpers(sys.argv[1])
    generator = random.Random(0xD0_6A_19)
    domain_cases = []
    days = [-2**128 - 7, -1, 0, 1, 7, 8, 365, 2**53 - 1, 2**53, 2**64 - 1, 10**80 + 123]
    for i, (seed, draws) in enumerate([(0, 0), (42, 1), (-(2**128 + 9), 311), (2**256 + 7, 312), (20261006, 624)]):
        rng = random.Random(seed)
        for _ in range(draws):
            rng.random()
        before = rng.getstate()
        serialized = json.dumps(before, separators=(",", ":"))
        derived = [derive_fixture(public, rng, day) for day in days]
        domain_cases.append({"label": f"seed-{i}-draws-{draws}", "state": before,
                             "serialized": serialized, "derived": derived})
    # Every legal index near the two twist regions and rollover; arbitrary words
    # ensure this does not just retest states already reached through seeding.
    for index in [0, 1, 226, 227, 396, 397, 622, 623, 624]:
        state = (3, tuple([generator.getrandbits(32) for _ in range(624)] + [index]), None)
        rng = random.Random(0)
        rng.setstate(state)
        domain_cases.append({"label": f"synthetic-index-{index}", "state": state,
                             "serialized": json.dumps(state, separators=(",", ":")),
                             "derived": [derive_fixture(public, rng, day) for day in [1, 8, 2**128 + 19]]})

    initial_cases = []
    seeds = [0, 1, -1, 42, 20261006, 2**53 - 1, 2**128 + 17, -(2**256 + 101)]
    seeds.extend(generator.getrandbits(128) for _ in range(12))
    for seed in seeds:
        for display in [0, 2]:
            rng = random.Random(seed)
            demand = public["_daily_demand"](rng)
            after_demand = rng.getstate()
            visitors = public["_make_visitors"](rng, {"upgrades": {"display": display}})
            after_visitors = rng.getstate()
            walkin = derive_fixture(public, rng, 1)
            initial_cases.append({"seed": str(seed), "display": display, "demand": demand,
                                  "afterDemand": after_demand, "visitors": visitors,
                                  "afterVisitors": after_visitors, "walkin": walkin})
    json.dump({"python": sys.version, "kinds": public["KINDS"], "customers": public["CUSTOMERS"],
               "domainCases": domain_cases, "initialCases": initial_cases}, sys.stdout,
              separators=(",", ":"), ensure_ascii=True)


if __name__ == "__main__":
    main()
