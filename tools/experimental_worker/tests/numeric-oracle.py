#!/usr/bin/env python3
"""Read-only public v9 oracle; entirely synthetic, no GameStore/save access.

Outputs compact independent vectors for numeric-oracle.test.mjs. No engine file
is modified and bytecode caching is disabled before importing the public source.
The optional source directory argument supports another explicit source checkout.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import platform
import random
import sys

sys.dont_write_bytecode = True
SOURCE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2] / "stardust-curios-v9-current-shop"
sys.path.insert(0, str(SOURCE))
spec = importlib.util.spec_from_file_location("numeric_oracle_engine", SOURCE / "engine.py")
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)
assert engine.VERSION == 9 and engine.TRADE_RULES_VERSION == 9

rng = random.Random(20261006)
counts = {}
out = {"metadata": {"python": platform.python_version(), "platform": platform.platform(),
                    "engine_sha256": hashlib.sha256((SOURCE / "engine.py").read_bytes()).hexdigest(),
                    "source_version": engine.VERSION, "synthetic_only": True}, "counts": counts}


def ctx(reference, budget=120, modifier=0):
    return dict(reference=reference, budget=budget, modifier=modifier)


def actual(base, condition, demand):
    return engine._actual_value({"demand": {"kind": "tool", "multiplier": demand}},
                                {"base_value": base, "condition": condition, "kind": "tool"})


def encoded(values):
    return base64.b64encode(bytes(values)).decode("ascii")


# Python no-ndigits round: ties and one representable float on each side.
round_inputs = []
for integer in range(-2000, 2001):
    tie = integer + 0.5
    round_inputs.extend((math.nextafter(tie, -math.inf), tie, math.nextafter(tie, math.inf)))
round_inputs.extend((0.0, -0.0, math.ulp(0.0), -math.ulp(0.0), 2**52 - 0.5, -(2**52 - 0.5), 2**52, 2**53))
out["round"] = [[v, round(v)] for v in round_inputs]
counts["round"] = len(out["round"])

clamp_inputs = [i / 10 for i in range(-1000, 1201)]
out["clamp"] = [[v, engine._clamp_chance(v)] for v in clamp_inputs]
counts["clamp"] = len(out["clamp"])

# All 24 catalog entries, every legal condition, every possible demand factor.
reference_rows = []
ceiling_rows = []
for catalog in engine.CATALOG:
    for condition in range(5, 101):
        for demand in (1, 1.25, 1.35, 1.45):
            item = dict(catalog_id=catalog[0], kind=catalog[3], condition=condition,
                        price=2, last_sale_day=0)
            state = dict(demand=dict(kind=catalog[3], multiplier=demand), phase="active",
                         energy=1, negotiation=None, day=1, walkins=dict(used=0))
            value = engine._reference_value(state, item)
            option = engine._sale_option(state, item, None)
            reference_rows.append([catalog[4], condition, demand, value, option["public_reference"]])
            ceiling_rows.append([option["public_reference"], 120, option["max_counter_ask"]])
            for high in (260, 340, 390, 430, 440, 600, 620, 650):
                reference = option["public_reference"]
                ceiling_rows.append([reference, high, min(reference * 5 // 4, high)])
out["reference"] = reference_rows
out["ceiling"] = ceiling_rows + [[2**53-1, 2**53-1, 2**53-1], [2**53-2, 650, 650]]
counts["reference"] = len(reference_rows)
counts["ceiling"] = len(out["ceiling"])

# Every legal asking price for 200 valid item valuations. These are a Cartesian
# base/condition/demand grid; budgets and modifiers cycle through lawful choices.
initial_sweeps = []
modifiers = tuple(range(-30, 66, 5))
budgets = (60, 61, 99, 100, 119, 120, 130, 180, 260, 340, 440, 620, 650)
for base in (1, 2, 17, 81, 88, 100, 480, 520, 583, 10000):
    for condition in (5, 35, 45, 80, 100):
        for demand in (1, 1.25, 1.35, 1.45):
            i = len(initial_sweeps)
            context = ctx(actual(base, condition, demand), budgets[i % len(budgets)], modifiers[(i * 7) % len(modifiers)])
            initial_sweeps.append(dict(context=context, source=[base, condition, demand], rules=9,
                                       expected=encoded(engine._initial_chance(context, p) for p in range(1, 10000))))
# Public regression contexts plus historical nullable budgets and dispatch.
for reference, budget, modifier in ((100,100,0), (500,60,45), (30,240,-30), (17.3,100,15), (1000,100,0)):
    context = ctx(reference, budget, modifier)
    initial_sweeps.append(dict(context=context, rules=9,
                               expected=encoded(engine._initial_chance(context,p) for p in range(1,10000))))
for rules in (5,6):
    for budget in (None,60,120,650):
        context = ctx(121.75, budget, 15)
        initial_sweeps.append(dict(context=context, rules=rules,
                                   expected=encoded(engine._initial_chance(context,p,rules) for p in range(1,10000))))
out["initial_sweeps"] = initial_sweeps
counts["initial_sweep_prices"] = len(initial_sweeps) * 9999

# Cover every allowed hidden base integer 1..10000, varying legal conditions,
# demand, budget, and modifiers. Focus on budget boundaries and logarithmic
# floor/clamp crossings, plus each legal price endpoint. Not a full Cartesian
# product of every possible valid state.
boundary_groups = []
conditions = (5,35,44,45,65,70,80,99,100)
for base in range(1,10001):
    condition = conditions[base % len(conditions)]
    demand = (1,1.25,1.35,1.45)[base % 4]
    budget = budgets[base % len(budgets)]
    modifier = modifiers[base % len(modifiers)]
    reference = actual(base,condition,demand)
    context = ctx(reference,budget,modifier)
    prices = {1,2,9998,9999,budget-1,budget,budget+1}
    for target in (1,2,10,50,60,98,99):
        boundary = math.floor(reference * 2**((60 + modifier - target) / 50))
        prices.update(range(boundary-2,boundary+3))
    prices = sorted(p for p in prices if 1 <= p <= 9999)
    boundary_groups.append(dict(context=context, source=[base,condition,demand], prices=prices,
                                expected=encoded(engine._initial_chance(context,p) for p in prices)))
out["initial_boundaries"] = boundary_groups
counts["initial_boundary_prices"] = sum(len(row["prices"]) for row in boundary_groups)

# Adversarial finite contexts at transcendental threshold crossings. These
# references are NOT asserted reachable from lawful item valuations. Keep the
# independent oracle to expose platform-libm differences instead of epsilon hacks.
adversarial = []
for price in (1,10,100,600):
    for modifier in (-30,0,15,65):
        for target in range(2,99):
            reference = price / 2**((60+modifier-target)/50)
            for value in (math.nextafter(reference,0),reference,math.nextafter(reference,math.inf)):
                context = ctx(value,650,modifier)
                adversarial.append([context,price,engine._initial_chance(context,price)])
# Exhaustively check which adversarial references equal any lawful valuation
# (base1..10000 × condition5..100 × four demand factors). This certifies the
# known divergences' reachability classification without treating coverage as
# proof that every valid initial-price/budget combination has been tested.
adversarial_references = {row[0]["reference"] for row in adversarial}
reachable_adversarial_references = set()
for base in range(1,10001):
    for condition in range(5,101):
        for demand in (1,1.25,1.35,1.45):
            value = actual(base,condition,demand)
            if value in adversarial_references:
                reachable_adversarial_references.add(value)
for row in adversarial:
    row.append(row[0]["reference"] in reachable_adversarial_references)
out["initial_adversarial"] = adversarial
counts["initial_adversarial"] = len(adversarial)
counts["reference_reachability_checks"] = 10000 * 96 * 4

final_sweeps = []
for modifier in (-100,-80,-69,-68,-30,-10,0,5,20,28,29,30,65):
    for counter in (1,2,3,20,80,100,150,240,520,9997):
        base = engine._final_chance(modifier,counter,counter+1)[0]
        final_sweeps.append(dict(modifier=modifier,counter=counter,base=base,
                                expected=encoded(engine._final_chance(modifier,counter,p)[1] for p in range(counter+1,10000))))
out["final_sweeps"] = final_sweeps
counts["final_sweep_prices"] = sum(9999-row["counter"] for row in final_sweeps)
# Exact Python integers well beyond the Number-safe intermediate range.
final_extreme = []
for _ in range(2000):
    counter = rng.randrange(1,2**53-2)
    price = rng.randrange(counter+1,2**53)
    modifier = rng.choice((-2**53+1,-80,-30,0,28,29,65,2**53-1))
    final_extreme.append([modifier,counter,price,list(engine._final_chance(modifier,counter,price))])
out["final_extreme"] = final_extreme
counts["final_extreme"] = len(final_extreme)

counter_rows = []
for group in boundary_groups:
    context = group["context"]
    for asking in (1,2,min(9999,context["budget"]),9999):
        counter_rows.append([context,asking,engine._counter_offer(context,asking)])
# Engine expression-order / floor edges, and historical missing affordability.
for reference in (0.01,1,17.3,100,121.75,1000,10000):
    for modifier in (-100,-30,0,15,65):
        for budget in (None,1,24,25,49,50,99,100,650):
            context = ctx(reference,budget,modifier)
            for asking in (1,2,90,250,9999):
                counter_rows.append([context,asking,engine._counter_offer(context,asking)])
out["counter"] = counter_rows
counts["counter"] = len(counter_rows)

bounds_rows = []
parse_rows = []
for counter, original in ((1,2),(1,3),(70,90),(100,9999),(9997,9999)):
    pending = dict(item_id="SYNTHETIC",item_name="Synthetic",customer_id=None,customer_name="Synthetic",
                   original_price=original,counter_offer=counter,rules_version=9,origin_rules_version=9,
                   context=dict(reference=100,budget=120,modifier=0,modifiers=[]))
    bounds_rows.append([counter,original,engine._public_negotiation(dict(negotiation=pending))["final_offer_bounds"]])
    candidates = [str(n) for n in (counter-1,counter,counter+1,original-1,original,original+1)]
    candidates += ["","0","-0","+2","02","2.0","2e0","٢","２","2_0","NaN","Infinity"]
    candidates += [f"{chr(c)}{counter+1}{chr(c)}" for c in list(range(0x21))+[0x85,0xa0,0x1680,*range(0x2000,0x200b),0x2028,0x2029,0x202f,0x205f,0x3000,0xfeff]]
    for raw in candidates:
        try:
            expected = engine._final_price(pending,raw)
        except engine.GameError:
            expected = None
        parse_rows.append([raw,counter,original,expected])
out["bounds"] = bounds_rows
out["parse"] = parse_rows
counts["bounds"] = len(bounds_rows)
counts["parse"] = len(parse_rows)

class SuppliedDigits:
    def __init__(self,tens,ones):
        self.values = iter((tens,ones))
        self.calls = 0
    def randint(self,a,b):
        assert (a,b) == (0,9)
        self.calls += 1
        return next(self.values)

percentile_rows = []
for threshold in range(1,100):
    for tens in range(10):
        for ones in range(10):
            digits = SuppliedDigits(tens,ones)
            state = dict(day=1,roll_seq=0,roll_history=[])
            row = engine._trade_roll(state,digits,dict(id="SYNTHETIC",name="Synthetic"),None,
                                     100,dict(reference=100,budget=100,modifier=threshold-60,modifiers=[]),"initial")
            assert digits.calls == 2 and row["threshold"] == threshold
            percentile_rows.append([tens,ones,threshold,{key:row[key] for key in ("tens","ones","roll","success","outcome")}])
out["percentile"] = percentile_rows
counts["percentile"] = len(percentile_rows)

print(json.dumps(out,separators=(",",":"),allow_nan=False))
