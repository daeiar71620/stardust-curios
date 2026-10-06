"""Explicit public-only projection. Never accepts a private save as its input."""
import math
import re


def fields(names, **nested):
    return {**{k: None for k in names.split()}, **nested}


def project(value, schema):
    if schema is None:
        if value is None or isinstance(value, (str, bool)):
            return value[:4000] if isinstance(value, str) else value
        if isinstance(value, (int, float)) and math.isfinite(value):
            return value
        return None
    if isinstance(schema, list):
        return [project(v, schema[0]) for v in value[:200]] if isinstance(value, list) else []
    if not isinstance(value, dict):
        return None if value is None else {}
    return {k: project(value[k], sub) for k, sub in schema.items() if k in value}


SALE = fields('customer_id customer_name available counter_eligible public_reference max_counter_ask min_condition preference_match condition_met ask warning', budget_range=[None], reasons=[None])
QUALITY = fields('min_condition condition_met counted reason')
ITEM = fields('id art_id name rarity kind color condition public_reference repair_cost price origin description collected sale_attempted_today repair_attempted_today repairs_remaining negotiating', value_estimate=[None], sale_options=[SALE], collection_quality=QUALITY, repair=fields('available cost energy_cost command', reasons=[None]), collection_replacement=fields('available cabinet_item_id cabinet_condition energy_cost command', reasons=[None]))
ROLL = fields('id day item_id item_name customer_id customer_name stage die tens ones roll modifier threshold probability base_chance premium rules_version counter_offer success outcome price explanation', modifiers=[fields('label value')])
ENTRY = fields('slot discovered collected art_id name rarity kind description')
GOAL = fields('key label current target met')
PUBLIC = fields('version revision day total_days credits reputation energy max_energy phase capacity operating_cost',
    goal=fields('credits collection'), inventory=[ITEM], collection=[ITEM], crates=[fields('id name supplier supplier_id supplier_name origin')],
    suppliers=[fields('id name cost stock description')], upgrades=fields('workbench shelf display'), upgrade_costs=fields('workbench shelf display'), upgrade_details=[fields('id name level max_level next_cost effect next_effect')],
    demand=fields('label kind multiplier'), last_event=fields('seq type title text', item=ITEM, roll=ROLL), log=[fields('day text')],
    campaign=fields('title stage_index first_week_result can_continue continue_command unlimited', completed_milestones=[fields('id title day')], next_milestone=fields('id title description ready min_condition legacy_grace', goals=[GOAL])),
    daily_event=fields('id title description sale_multiplier salvage_discount repair_discount cost_delta energy_delta'), visitors=[fields('id name role preferred_kind preference_label min_condition premium status attempted_today', budget_range=[None])],
    walkins=fields('daily_limit used remaining min_condition visit_rule', budget_range=[None]), codex=fields('total discovered collected', entries=[ENTRY]),
    collection_sets=[fields('id name description required current completed perk reward applied', members=[ENTRY])],
    collection_progress=fields('personal_count qualified_count qualified_categories quality_themes min_condition legacy_grace', categories=[fields('id name qualified_count theme_complete')], requirements=[GOAL], missing=[None]),
    collection_upgrade=fields('from_version source_day source_phase legacy_stage_index'), budget_upgrade=fields('from_version source_roll_seq source_day source_phase'),
    stats=fields('crates_opened sales_count gross_earnings days_traded'), negotiation=fields('item_id item_name customer_id customer_name original_price counter_offer final_chance status'), last_roll=ROLL, roll_history=[ROLL],
    trade_rules=fields('die direction zero_zero critical fumble critical_rule fumble_rule house_rules max_rolls_per_item_day price_limit final_offer_energy final_offer_rule final_chance_formula initial_chance_formula initial_budget_rule counter_rule walkin_daily_limit walkin_min_condition final_budget_rule endday miracle_probability', dice=[None], walkin_budget_range=[None]))


def sanitize(raw):
    if not isinstance(raw, dict) or type(raw.get('revision')) is not int or raw['revision'] < 0 or type(raw.get('version')) is not int or type(raw.get('day')) is not int:
        raise ValueError('Invalid public observation')
    out = project(raw, PUBLIC)
    def mask(entry):
        return entry if entry.get('discovered') is True else {'slot': entry.get('slot'), 'discovered': False, 'collected': False}
    codex = out.get('codex') or {}
    if codex:
        codex['entries'] = [mask(e) for e in codex.get('entries', [])]
        codex['discovered'] = sum(e.get('discovered') is True for e in codex['entries'])
        codex['collected'] = sum(e.get('discovered') is True and e.get('collected') is True for e in codex['entries'])
    for group in out.get('collection_sets', []):
        if 'members' in group:
            group['members'] = [mask(e) for e in group['members']]
    return out


def known_art(observation):
    rows = [*observation.get('inventory', []), *observation.get('collection', []), *(r for r in (observation.get('codex') or {}).get('entries', []) if r.get('discovered') is True)]
    return {r['art_id'] for r in rows if r.get('discovered') is not False and isinstance(r.get('art_id'), str) and re.fullmatch(r'[a-z0-9_-]{1,60}', r['art_id'])}
