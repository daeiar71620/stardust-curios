"""Synthetic CPython RNG vectors only. No game imports, saves, or filesystem IO."""
import json
import random
import sys

GENERATOR = random.Random(0x5A7D_0579)


def bigint(value):
    return {"bigint": str(value)}


def run_op(rng, op):
    method = op["method"]
    args = op.get("args", [])
    args = [int(a["bigint"]) if isinstance(a, dict) and "bigint" in a else a for a in args]
    if method == "getrandbits":
        return {"hex": format(rng.getrandbits(*args), "x")}
    if method == "randbelow":
        result = rng._randbelow(*args)
    elif method == "shuffle":
        result = args[0].copy()
        rng.shuffle(result)
    elif method == "choices":
        population, weights, k, cumulative = args
        return rng.choices(population, weights, k=k, cum_weights=cumulative)
    else:
        result = getattr(rng, method)(*args)
    if op.get("bigResult"):
        return {"hex": format(result, "x")}
    return result


def random_op():
    method = GENERATOR.choice(["random", "random", "getrandbits", "randrange", "randint", "choice", "shuffle", "uniform", "choices", "sample", "randbelow"])
    if method == "random":
        return {"method": method}
    if method == "getrandbits":
        return {"method": method, "args": [GENERATOR.choice([0, 1, 2, 3, 7, 8, 16, 31, 32, 33, 53, 54, 63, 64, 65, 127, 128, 129, 623, 1025])]}
    if method == "randbelow":
        n = GENERATOR.choice([1, 2, 3, 7, 16, 256, 65536, 2**32, 2**53 - 1, 2**65 + 3, 2**128])
        if n > 2**53 - 1:
            return {"method": method, "args": [bigint(n)], "bigResult": True}
        return {"method": method, "args": [n]}
    if method == "randrange":
        first = GENERATOR.randint(-1000000, 1000000)
        stride = GENERATOR.choice([-17, -3, -1, 1, 2, 3, 17])
        last = first + stride * GENERATOR.randint(1, 100000)
        return {"method": method, "args": [first, last, stride]}
    if method == "randint":
        low = GENERATOR.randint(-1000000, 1000000)
        return {"method": method, "args": [low, low + GENERATOR.randint(0, 100000)]}
    if method == "choice":
        return {"method": method, "args": [["common", "rare", "legendary", "信号", "植物", "bot"][:GENERATOR.randint(1, 6)]]}
    if method == "shuffle":
        return {"method": method, "args": [list(range(GENERATOR.randint(0, 30)))]}
    if method == "uniform":
        a, b = GENERATOR.choice([(0.92, 1.08), (0.0, 1.0), (-1e30, 1e30), (14.0, -2.7), (1.0, 1.0), (-0.0, 0.0)])
        return {"method": method, "args": [a, b]}
    if method == "choices":
        weights = GENERATOR.choice([None, [74, 24, 2], [28, 61, 11], [0, 0, 1], [0.25, 0, 0.75], [1, -1, 2]])
        cumulative = None
        if weights and GENERATOR.randrange(2):
            cumulative = [sum(weights[:i + 1]) for i in range(len(weights))]
            weights = None
        return {"method": method, "args": [["common", "rare", "legendary"], weights, GENERATOR.randint(0, 15), cumulative]}
    n = GENERATOR.choice([0, 1, 3, 8, 21, 22, 85, 86, 277, 278, 1000])
    k = GENERATOR.randint(0, min(n, 30))
    return {"method": "sample", "args": [list(range(n)), k]}


def edge_ops():
    result = []
    for k in [0, 1, 31, 32, 33, 52, 53, 54, 63, 64, 65, 19967, 19968, 19969]:
        result.append({"method": "getrandbits", "args": [k]})
    for n in [1, 2, 3, 4, 7, 8, 16, 256, 2**31, 2**32, 2**53 - 1]:
        result.append({"method": "randbelow", "args": [n]})
    for args in [[1], [10], [5, 6], [-5, 5], [-2**53 + 1, 2**53 - 1], [10, -10, -3], [10, -10, -40], [-10, 10, 40]]:
        result.append({"method": "randrange", "args": args})
    for args in [[2**100, 2**100 + 27, 3], [-2**100, 2**101, 987654321], [2**100, -2**100, -2**70]]:
        result.append({"method": "randrange", "args": list(map(bigint, args)), "bigResult": True})
    result.extend([
        {"method": "randint", "args": [2**53 - 1, 2**53 - 1]},
        {"method": "randint", "args": [-2**53 + 1, 2**53 - 1]},
        {"method": "randint", "args": [bigint(-2**120), bigint(2**120)], "bigResult": True},
    ])
    for n, k in [(0, 0), (1, 1), (8, 3), (8, 4), (21, 5), (22, 5), (85, 6), (86, 6), (85, 21), (86, 21), (277, 22), (278, 22), (1000, 3), (1000, 999)]:
        result.append({"method": "sample", "args": [list(range(n)), k]})
    return result


def make_case(label, rng, setup, operations):
    checkpoints = []
    expected = []
    initial = rng.getstate()
    for index, op in enumerate(operations):
        expected.append(run_op(rng, op))
        if index % 31 == 30:
            checkpoints.append({"after": index + 1, "state": rng.getstate()})
    return {"label": label, "setup": setup, "initial": initial, "operations": operations,
            "expected": expected, "checkpoints": checkpoints, "final": rng.getstate()}


def main():
    cases = []
    seeds = [0, 1, -1, 42, -42, 2**32 - 1, 2**32, 2**53 - 1, 2**64 + 123, -(2**128 + 11), 2**2048 + 17]
    seeds.extend(GENERATOR.getrandbits(GENERATOR.randint(1, 512)) * GENERATOR.choice([-1, 1]) for _ in range(20))
    for i, seed in enumerate(seeds):
        operations = (edge_ops() if i < 4 else []) + [random_op() for _ in range(180)]
        cases.append(make_case(f"integer-{i}", random.Random(seed), {"seed": str(seed)}, operations))
    for i, seed in enumerate([b"", b"\0", b"a", bytes(range(256)), b"\xff" * 32, GENERATOR.randbytes(32), GENERATOR.randbytes(129)]):
        cases.append(make_case(f"bytes-{i}", random.Random(seed), {"bytes": list(seed)}, [random_op() for _ in range(120)]))
    for i, seed in enumerate(["", "Stardust", "星屑杂货铺", "hello\U0001f680", "e\u0301\0"]):
        cases.append(make_case(f"string-{i}", random.Random(seed), {"string": seed}, [random_op() for _ in range(120)]))
    for index in [0, 1, 2, 225, 226, 227, 396, 397, 622, 623, 624]:
        internal = [GENERATOR.getrandbits(32) for _ in range(624)] + [index]
        cache = GENERATOR.choice([None, -0.0, 0.0, 1.25, -3.75])
        state = (3, tuple(internal), cache)
        rng = random.Random(0)
        rng.setstate(state)
        operations = [{"method": "random"}, {"method": "getrandbits", "args": [32]}] + [random_op() for _ in range(180)]
        cases.append(make_case(f"state-index-{index}", rng, {"state": state}, operations))
    for value in [0, 2**32 - 1]:
        state = (3, tuple([value] * 624 + [623]), 4.25)
        rng = random.Random(0)
        rng.setstate(state)
        operations = [{"method": "random"}] + [{"method": "getrandbits", "args": [k]} for k in [0, 32, 19967, 19968, 19969]]
        cases.append(make_case(f"state-constant-{value}", rng, {"state": state}, operations))
    json.dump({"python": sys.version, "cases": cases}, sys.stdout, separators=(",", ":"), ensure_ascii=True)


if __name__ == "__main__":
    main()
