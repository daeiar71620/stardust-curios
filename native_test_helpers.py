"""Native v9 synthetic fixtures; never access a live or default save."""
from functools import lru_cache
import hashlib
import json
import math
import random
import engine


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def within_budget_chance(context, price):
    return max(1, min(99, math.floor(60 + context["modifier"] - 50 * math.log2(price / context["reference"]))))


def final_chance(modifier, counter, price):
    base = max(1, min(99, 70 + modifier))
    return base, max(1, min(99, base * counter // (2 * price - counter)))


def counter_offer(context, price):
    quote = max(1, math.floor(context["reference"] * (0.75 + context["modifier"] / 200) / 10) * 10)
    return max(1, min(price - 1, quote, max(1, context["budget"] // 25 * 20)))


@lru_cache(maxsize=None)
def rng_for(*rolls):
    digits = [digit for roll in rolls for digit in ((roll % 100) // 10, roll % 10)]
    for seed in range(1000000):
        rng = random.Random(seed)
        if [rng.randint(0, 9) for _ in digits] == digits:
            return random.Random(seed).getstate()
    raise AssertionError(f"No deterministic seed for {rolls}")


def fixture(*rolls, price=90, condition=80, kind='wrench', count=1):
    state = engine.new_state(42)
    row = engine.CATALOG_BY_ID[kind]
    state['inventory'] = [dict(id=f'I{x+1:03}', catalog_id=row[0], name=row[1], rarity=row[2],
        kind=row[3], base_value=row[4], condition=condition, description=row[5],
        origin=engine.SUPPLIERS['salvage']['name'], collected=False, repairs=0,
        last_sale_day=0, last_repair_day=0, price=price) for x in range(count)]
    state['next_item'] = count + 1
    state['discovered'] = [row[0]]
    state['rng'] = rng_for(*(rolls or (99,)))
    return state


def named(state, match=True):
    row = next(r for r in engine.CUSTOMERS if (r[3] == state['inventory'][0]['kind']) == match)
    key,name,role,kind,condition,low,high=row
    visitor=dict(id=key,name=name,role=role,preferred_kind=kind,
        preference_label=f'偏爱{engine.KINDS[kind]}，品相{condition}%以上更喜欢',
        min_condition=condition,budget_range=[low,high],premium=1.25,status='waiting',budget=low)
    state['visitors']=[visitor]+[v for v in state['visitors'] if v['id']!=key][:2]
    return visitor

