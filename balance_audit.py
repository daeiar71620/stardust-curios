#!/usr/bin/env python3
"""Bounded synthetic campaign comparison, never a live-save player.

The policy accepts only a copied public observation and its own public action
history. The referee owns private state; it never exposes seed, RNG, hidden
budgets, hidden values, or sealed cargo to the policy. No files named save.json
are opened. Feature ablations modify isolated imported modules in this process.

Example:
    python3 balance_audit.py --baseline /path/to/v9/engine.py > /tmp/balance.json
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics


# Declared before collecting results. Every variant uses every seed and day.
SEEDS = tuple(range(1001, 1017))
HORIZON = 56
POLICY_VERSION = "public-cautious-1"
VARIANTS = ("v9", "v10_control", "v10_fees", "v10_deadlines", "v10_combined", "v10_targeted",
            "v10_targeted_energy1")
FORBIDDEN = {"rng", "base_value", "budget", "cargo", "context"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def load_engine(path, label):
    spec = importlib.util.spec_from_file_location("balance_" + label, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def public_boundary(value):
    """Reject private-key regressions at the policy's sole data boundary."""
    if isinstance(value, dict):
        if FORBIDDEN & value.keys():
            raise AssertionError("Private field in public observation")
        for child in value.values():
            public_boundary(child)
    elif isinstance(value, list):
        for child in value:
            public_boundary(child)


def economic_projection(p):
    """Shared v9/v10 public first-week behavior, excluding version/new metadata."""
    result = {key: p[key] for key in ("day", "credits", "energy", "reputation", "phase",
        "upgrades", "demand", "daily_event", "visitors", "walkins", "stats")}
    for place in ("inventory", "collection"):
        result[place] = [{k: item[k] for k in ("id", "art_id", "rarity", "kind", "condition",
            "price", "public_reference", "repairs_remaining", "sale_attempted_today",
            "repair_attempted_today")} for item in p[place]]
    result["crates"] = [{k: crate[k] for k in ("id", "supplier")} for crate in p["crates"]]
    result["suppliers"] = [{k: supplier[k] for k in ("id", "cost", "stock")}
                           for supplier in p["suppliers"] if supplier["id"] != "focused"]
    result["last_roll"] = ({k: p["last_roll"][k] for k in ("id", "day", "item_id", "customer_id",
        "stage", "tens", "ones", "roll", "threshold", "success", "price")} if p["last_roll"] else None)
    return result


class PublicPolicy:
    """One fixed heuristic; targeting is the sole policy treatment switch.

    Sales use published reference/counter eligibility and accept binding quotes.
    There is no inference of hidden budgets from rolls, seed access, or reroll.
    Stage-directed investment begins only with a 50%-of-goal cash buffer.
    """

    def __init__(self, targeting=False):
        self.targeting = targeting
        self.day = None
        self.daily_buys = 0
        self.opened_day = {}
        self.purchased_supplier = {}

    def observe_action(self, before, action, after):
        command, args = action
        if command == "buy":
            self.daily_buys += 1
            old = {item["id"] for item in before["crates"]}
            for crate in after["crates"]:
                if crate["id"] not in old:
                    self.purchased_supplier[crate["id"]] = args[0]
        if command == "open":
            old = {item["id"] for item in before["inventory"]}
            for item in after["inventory"]:
                if item["id"] not in old:
                    self.opened_day[item["id"]] = before["day"]

    def choose(self, p):
        if self.day != p["day"]:
            self.day, self.daily_buys = p["day"], 0
        if p["phase"] == "week_summary":
            return "continue", []
        if p["negotiation"]:
            return "accept", [p["negotiation"]["item_id"]]
        if p["energy"] <= 0:
            return "endday", []
        if p["crates"]:
            return "open", [p["crates"][0]["id"]]

        cash, energy = p["credits"], p["energy"]
        reserve = max(60, 3 * p["operating_cost"])
        stage = p["campaign"]["next_milestone"]
        goals = {g["key"]: g for g in stage["goals"]}
        cash_goal = goals["credits"]["target"]
        minimum = stage["min_condition"]
        collection = {item["art_id"]: item for item in p["collection"]}
        categories = {row["id"]: row["qualified_count"]
                      for row in p["collection_progress"]["categories"]}
        goal_short = lambda key: key in goals and not goals[key]["met"]
        def wanted(item):
            if item["art_id"] in collection:
                return False
            return (goal_short("collection")
                    or (goal_short("collection_categories") and categories[item["kind"]] == 0)
                    or (goal_short("quality_themes") and categories[item["kind"]] < 3))

        # Fix the existing cabinet before spending on another blind box.
        if cash >= max(reserve + 100, cash_goal * .5):
            for item in sorted(p["inventory"], key=lambda i: (i["public_reference"], i["id"])):
                replacement = item["collection_replacement"]
                if (replacement and replacement["available"]
                        and replacement["cabinet_condition"] < minimum
                        and item["condition"] >= minimum):
                    return "replace-collection", [item["id"]]
            repairs = [item for item in p["collection"]
                       if item["condition"] < minimum and item["repair"]["available"]
                       and cash - item["repair_cost"] >= reserve]
            if repairs:
                item = min(repairs, key=lambda i: (minimum-i["condition"], i["repair_cost"], i["id"]))
                return "repair", [item["id"]]
            keep = [item for item in p["inventory"] if wanted(item) and item["condition"] >= minimum]
            if keep:
                item = min(keep, key=lambda i: (i["public_reference"], i["id"]))
                return "collect", [item["id"]]

        # Sell suitable stock to matching guests first, at legal counter asks.
        sales = []
        for item in p["inventory"]:
            for option in item["sale_options"]:
                if (option["available"] and option["customer_id"] is not None
                        and option["preference_match"] and option["condition_met"]):
                    ask = max(2, option["max_counter_ask"])
                    sales.append((ask, item["id"], option["customer_id"]))
        if sales:
            ask, item_id, customer = max(sales)
            item = next(i for i in p["inventory"] if i["id"] == item_id)
            return (("price", [item_id, str(ask)]) if item["price"] != ask
                    else ("sell", [item_id, customer]))

        # A cheap walk-in sale frees a slot; keep expensive stock for guests.
        sales = []
        for item in p["inventory"]:
            option = item["sale_options"][0]
            if (option["available"] and option["condition_met"]
                    and (item["public_reference"] <= 140 or cash < reserve + 48)):
                sales.append((min(option["max_counter_ask"], 120), item["id"]))
        if sales:
            ask, item_id = max(sales)
            item = next(i for i in p["inventory"] if i["id"] == item_id)
            return (("price", [item_id, str(ask)]) if item["price"] != ask
                    else ("sell", [item_id]))

        # Repair one useful item when it can become cabinet- or guest-ready.
        repairs = []
        for item in p["inventory"]:
            if not item["repair"]["available"] or cash-item["repair_cost"] < reserve + 48:
                continue
            guest_need = any(o["available"] and o["customer_id"] and o["preference_match"]
                             and not o["condition_met"] for o in item["sale_options"])
            cabinet_need = wanted(item) and cash >= cash_goal*.5 and minimum-35 <= item["condition"] < minimum
            if guest_need or cabinet_need:
                repairs.append(item)
        if repairs:
            item = min(repairs, key=lambda i: (i["repair_cost"], -i["condition"], i["id"]))
            return "repair", [item["id"]]

        # Meet stage investment requirements; do not max facilities for this test.
        upgrade_order = ("shelf", "workbench", "display", "display", "workbench", "shelf")
        if goal_short("upgrades") and energy >= 2:
            planned = Counter()
            for name in upgrade_order[:goals["upgrades"]["target"]]:
                planned[name] += 1
                cost = p["upgrade_costs"][name]
                if p["upgrades"][name] < planned[name] and cost is not None:
                    if cash - cost >= max(reserve + 150, cash_goal * .5):
                        return "upgrade", [name]
                    break

        slots = len(p["inventory"]) + len(p["crates"])
        suppliers = {s["id"]: s for s in p["suppliers"]}
        # Optional category purchase is for collection gaps, never a named item.
        focused = suppliers.get("focused")
        needs_collection = any(goal_short(k) for k in ("collection", "collection_categories", "quality_themes"))
        if (self.targeting and focused and focused.get("unlocked") and focused["stock"] > 0
                and needs_collection and cash >= cash_goal*.8 + focused["cost"] + reserve
                and energy >= focused.get("energy_cost", 2)+1 and slots < p["capacity"]
                and self.daily_buys < 3):
            kind = min(categories, key=lambda k: (categories[k], k))
            return "buy", ["focused", kind]

        # Two cheap draws then one curated draw on well-funded later days.
        if energy >= 3 and slots < p["capacity"] and self.daily_buys < 3:
            supplier = "salvage"
            if p["day"] >= 8 and self.daily_buys == 2 and cash >= reserve + 400:
                supplier = "curated"
            offer = suppliers[supplier]
            if offer["stock"] > 0 and cash-offer["cost"] >= reserve:
                return "buy", [supplier]

        # Public, conservative clearance for old stock with unmatched guests.
        clearances = []
        for item in p["inventory"]:
            if p["day"]-self.opened_day.get(item["id"], p["day"]) < 2 and slots < p["capacity"]-1:
                continue
            for option in item["sale_options"]:
                if option["available"] and option["customer_id"] is not None:
                    ask = max(2, min(round(item["public_reference"] * .70), option["budget_range"][0]))
                    clearances.append((ask, item["id"], option["customer_id"]))
        if clearances:
            ask, item_id, customer = max(clearances)
            item = next(i for i in p["inventory"] if i["id"] == item_id)
            return (("price", [item_id, str(ask)]) if item["price"] != ask
                    else ("sell", [item_id, customer]))
        return "endday", []


def configure(engine, variant):
    if variant == "v9":
        assert engine.VERSION == 9
        return
    assert engine.VERSION == 10
    if variant in {"v10_control", "v10_deadlines"}:
        engine.FACILITY_UPKEEP = {k: (0, 0, 0, 0) for k in engine.FACILITY_UPKEEP}
    if variant in {"v10_control", "v10_fees"}:
        engine.OVERDUE_DAILY_RATE = 0
    if variant.startswith("v10_targeted"):
        # Keep this explicit if the shipping default is later changed to 1.
        engine.FOCUSED_ENERGY_COST = 1 if variant.endswith("energy1") else 2
    if not variant.startswith("v10_targeted"):
        engine.FOCUSED_DAILY_LIMIT = 0


def run_case(engine, variant, seed, horizon):
    # Referee only. Private state is never passed to PublicPolicy.
    state = engine.new_state(seed)
    policy = PublicPolicy(targeting=variant.startswith("v10_targeted"))
    commands, supplier_counts, opened_by_supplier, duplicates_by_supplier = Counter(), Counter(), Counter(), Counter()
    procurement_spend, missing_cabinet_draws, qualifying_draws = Counter(), Counter(), Counter()
    item_supplier = {}
    seen, transcript, days, first_week_trace = set(), [], [], []
    fees = Counter()
    first_week_digest = None
    read_checks = 0
    p = engine.observation(state)
    while True:
        public_boundary(p)
        if p["phase"] == "lost" or p["stats"]["days_traded"] >= horizon:
            break
        if p["day"] > horizon:
            break
        # Every day verify all no-op read commands + projection leave all state,
        # including RNG, unchanged. Hashing opaque referee state is not a policy input.
        if not transcript or transcript[-1]["day"] != p["day"]:
            before = digest(state)
            for command in ("status", "market", "codex", "visitors"):
                engine.apply_command(state, command, [])
            if p["inventory"]:
                engine.apply_command(state, "inspect", [p["inventory"][0]["id"]])
            assert p == engine.observation(state)
            assert digest(state) == before
            read_checks += 1
        action = policy.choose(copy.deepcopy(p))
        command, args = action
        if command == "endday" and p["credits"] >= p["operating_cost"]:
            breakdown = p.get("operating_cost_breakdown", {})
            fees["operating"] += p["operating_cost"]
            fees["facility"] += breakdown.get("facility_upkeep", 0)
            fees["overdue"] += breakdown.get("overdue_surcharge", 0)
        try:
            # This referee's state is synthetic and memory-only. An invalid
            # action aborts the run; it is never retried or replaced by a fallback.
            engine.apply_command(state, command, args)
        except Exception as exc:
            raise AssertionError(f"{variant} seed{seed} day{p['day']} invalid public policy action {action}: {exc}") from exc
        after = engine.observation(state)
        policy.observe_action(p, action, after)
        commands[command] += 1
        if command == "buy":
            supplier_counts[args[0]] += 1
            procurement_spend[args[0]] += next(s["cost"] for s in p["suppliers"] if s["id"] == args[0])
        if command == "open":
            old_ids = {i["id"] for i in p["inventory"]}
            revealed = next(i for i in after["inventory"] if i["id"] not in old_ids)
            supplier = policy.purchased_supplier[args[0]]
            item_supplier[revealed["id"]] = supplier
            opened_by_supplier[supplier] += 1
            if revealed["art_id"] in seen:
                duplicates_by_supplier[supplier] += 1
            seen.add(revealed["art_id"])
            if revealed["art_id"] not in {i["art_id"] for i in p["collection"]}:
                missing_cabinet_draws[supplier] += 1
            if revealed["condition"] >= p["campaign"]["next_milestone"]["min_condition"]:
                qualifying_draws[supplier] += 1
        transcript.append({"day": p["day"], "command": command, "args": args,
                           "credits": after["credits"], "energy": after["energy"],
                           "last_event": after["last_event"]})
        if p["day"] <= 7 and command != "continue":
            first_week_trace.append({"command": command, "args": args, "public": economic_projection(after)})
        if command == "endday":
            days.append({"day": p["day"], "credits": after["credits"], "phase": after["phase"],
                         "collection": len(after["collection"]), "reputation": after["reputation"],
                         "operating_cost": p["operating_cost"], "upgrades": after["upgrades"]})
            if p["day"] == 7:
                first_week_digest = digest(first_week_trace)
        assert len(transcript) < horizon * 100, "Policy failed to terminate"
        p = after
    public = p
    return {"variant": variant, "seed": seed, "horizon": horizon,
            "days_closed": public["stats"]["days_traded"], "last_day": public["day"],
            "cash": public["credits"], "bankrupt": public["phase"] == "lost",
            "first_week": public["campaign"]["first_week_result"],
            "first_week_digest": first_week_digest,
            "milestones": public["campaign"]["completed_milestones"],
            "collection": len(public["collection"]), "qualified_collection": public["collection_progress"]["qualified_count"],
            "upgrades": public["upgrades"], "reputation": public["reputation"],
            "sales": public["stats"]["sales_count"], "gross_earnings": public["stats"]["gross_earnings"],
            "fees": dict(fees), "actions": dict(commands), "purchases": dict(supplier_counts),
            "procurement_spend": dict(procurement_spend),
            "opened": dict(opened_by_supplier), "duplicate_draws": dict(duplicates_by_supplier),
            "draws_missing_from_cabinet": dict(missing_cabinet_draws), "draws_meeting_stage_quality": dict(qualifying_draws),
            "final_cabinet_sources": dict(Counter(item_supplier[i["id"]] for i in public["collection"])),
            "discovered": len(seen), "daily_results": days, "read_checks": read_checks,
            "transcript_digest": digest(transcript)}


def summarize(cases):
    result = {}
    for variant in VARIANTS:
        rows = [r for r in cases if r["variant"] == variant]
        milestones = {}
        for mid in ("first_week", "neighborhood", "lighthouse", "landmark", "voyage_1"):
            achieved = [m["day"] for r in rows for m in r["milestones"] if m["id"] == mid]
            milestones[mid] = {"completed": len(achieved),
                "day_median_among_completers": statistics.median(achieved) if achieved else None,
                "day_range_among_completers": [min(achieved), max(achieved)] if achieved else None}
        result[variant] = {"runs": len(rows), "cash_median": statistics.median(r["cash"] for r in rows),
            "cash_range": [min(r["cash"] for r in rows), max(r["cash"] for r in rows)],
            "first_week_won": sum(r["first_week"] == "won" for r in rows),
            "bankruptcies": sum(r["bankrupt"] for r in rows),
            "days_closed_total": sum(r["days_closed"] for r in rows),
            "collection_median": statistics.median(r["collection"] for r in rows),
            "facility_fees_total": sum(r["fees"].get("facility", 0) for r in rows),
            "overdue_fees_total": sum(r["fees"].get("overdue", 0) for r in rows),
            "actions_total": sum(sum(r["actions"].values()) for r in rows),
            "focused_purchases": sum(r["purchases"].get("focused", 0) for r in rows),
            "opened_total": sum(sum(r["opened"].values()) for r in rows),
            "duplicate_draws_total": sum(sum(r["duplicate_draws"].values()) for r in rows),
            "milestones": milestones}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True, help="verified native v9 engine.py")
    parser.add_argument("--engine", type=Path, default=Path(__file__).with_name("engine.py"))
    parser.add_argument("--horizon", type=int, default=HORIZON)
    parser.add_argument("--repeat-check", action="store_true", help="repeat every full run and compare public output")
    args = parser.parse_args()
    if not 7 <= args.horizon <= HORIZON:
        parser.error("bounded horizon must be from 7 through 56 days")
    cases = []
    for variant in VARIANTS:
        engine = load_engine(args.baseline if variant == "v9" else args.engine, variant)
        configure(engine, variant)
        for seed in SEEDS:
            result = run_case(engine, variant, seed, args.horizon)
            if args.repeat_check:
                assert result == run_case(engine, variant, seed, args.horizon), (variant, seed)
            cases.append(result)
    for seed in SEEDS:
        traces = {r["first_week_digest"] for r in cases if r["seed"] == seed}
        assert len(traces) == 1, f"First-week economic/action drift at seed {seed}"
    output = {"policy": POLICY_VERSION, "seeds": SEEDS, "horizon": args.horizon,
        "repeat_verified": args.repeat_check, "first_week_equivalent": True,
        "baseline_sha256": hashlib.sha256(args.baseline.read_bytes()).hexdigest(),
        "engine_sha256": hashlib.sha256(args.engine.read_bytes()).hexdigest(),
        "audit_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "summary": summarize(cases), "cases": cases}
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
