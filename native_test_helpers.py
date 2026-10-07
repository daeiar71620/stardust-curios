"""Native v10 synthetic fixtures; never access a live or default save."""
from functools import lru_cache
import hashlib
import json
import math
import random
import engine


def sync_stage_history(state):
    """Build explicit synthetic history when a fixture supplies earned stages.

    Test-only fixture construction; never a migration or production repair path.
    """
    history = []
    unlocked = 1
    for index in range(len(state['milestones']) + 1):
        definition = (engine.MILESTONES[index] if index < 4 else
                      dict(id=f'voyage_{index - 3}', title=f'星海长航 · 第{index - 3}章'))
        nominal = (7, 14, 28, 42)[index] if index < 4 else 56 + 14 * (index - 4)
        effective = nominal if index == 0 else max(nominal, unlocked + 7)
        completed = state['milestones'][index]['day'] if index < len(state['milestones']) else None
        missed = effective if ((completed is not None and completed > effective) or
                              (completed is None and state['day'] > effective)) else None
        history.append(dict(id=definition['id'], title=definition['title'],
                            nominal_due_day=nominal, effective_due_day=effective,
                            unlocked_day=unlocked, missed_day=missed, completed_day=completed))
        if completed is not None:
            unlocked = completed
    state['stage_history'] = history
    return state


def legacy_trade_digest(value):
    """Retain the v9 behavioral golden while checking v10 tags separately."""
    def normalize(node):
        if isinstance(node, dict):
            return {key: 9 if key in {'rules_version', 'origin_rules_version'} else normalize(item)
                    for key, item in node.items()}
        if isinstance(node, (list, tuple)):
            return [normalize(item) for item in node]
        return node
    return digest(normalize(value))


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

