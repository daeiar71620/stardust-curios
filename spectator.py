#!/usr/bin/env python3
"""Stardust Curios: a native, strictly read-only public-observation viewer.

Tk is only a window around a Pillow renderer. --snapshot renders the exact same
UI without connecting to a desktop, so visual QA never disturbs a running game.
This module does not import the engine, advance time, or write game state.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import json
import math
import re
from pathlib import Path
import time
from typing import Any

from PIL import Image, ImageColor, ImageDraw, ImageFont

BG = '#101c29'
PANEL = '#1b2b37'
PANEL2 = '#233743'
INK = '#f6edda'
MUTED = '#aec1bb'
TEAL = '#80d8c5'
GOLD = '#f4c77d'
LILAC = '#c1b0ef'
RED = '#eab099'
LINE = '#3c535b'
TABS = [('shelf', '店内货架'), ('visitors', '来店旅客'), ('collection', '收藏图鉴'), ('upgrades', '小店成长'), ('journal', '经营日志')]
RARITIES = {'common': ('普通', '#9bcbbd'), 'rare': ('稀有', LILAC), 'legendary': ('传说', GOLD)}
PERCENTILE_LABELS = {'miracle': ('01 · 大成功', GOLD), 'success': ('普通成功', TEAL), 'failure': ('失败', RED), 'fumble': ('100 · 大失败', RED)}
KINDS = {'tool': '工具', 'artifact': '古物', 'bot': '机器人', 'plant': '植物', 'signal': '信号'}
UPGRADES = {'workbench': '修理工作台', 'shelf': '陈列货架', 'display': '收藏展柜'}

# These are public illustration identities, not an engine/catalogue import.
# Public-name aliases keep art recognizable when optional art IDs are absent.
ITEM_ART_NAMES = {
    '折叠离子扳手': 'wrench', '重力手电': 'lamp', '轨道咖啡壶': 'coffee',
    '哼歌清洁球': 'cleaner', '瓶装月光苔': 'moss', '二手星图仪': 'map',
    '彗星玻璃八音盒': 'music', '逆相位焊笔': 'welder', '迷路送信蜂': 'bee',
    '低语星籽': 'seed', '微型人造黎明': 'dawn', '最后一封地球来信': 'letter',
    '逆风磁罗盘': 'compass', '口袋气象瓶': 'kettle', '慢半拍含羞草': 'sprout',
    '快递蜗牛机': 'snail', '午睡时间匣': 'clock', '真空缝星针': 'needle',
    '极光玻璃蕨': 'fern', '潮汐回声电台': 'radio', '发条守夜猫': 'cat',
    '微型行星锻锤': 'hammer', '永昼盆栽': 'tree', '袖珍巡航鲸': 'whale',
}
ITEM_ART_IDS = frozenset(ITEM_ART_NAMES.values())


def number(value: Any, default=0):
    """Do not let malformed or half-written public fields crash a live display."""
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError, OverflowError):
        return default


def as_dict(value):
    return value if isinstance(value, dict) else {}


def as_list(value):
    return value if isinstance(value, list) else []


def native_observation(value):
    source = as_dict(value)
    return (type(source.get('version')) is int and source['version'] == 10
            and type(source.get('protocol_version', 10)) is int
            and source.get('protocol_version', 10) == 10
            and all(source.get(key) is None for key in
                    ('migration', 'engine_upgrade', 'management_upgrade', 'collection_upgrade', 'budget_upgrade'))
            and (as_dict(source.get('collection_progress')).get('legacy_grace') is None
                 or as_dict(source.get('collection_progress')).get('legacy_grace') is False))


def safe_color(value, fallback=TEAL):
    try:
        if not isinstance(value, str) or not value.startswith('#'):
            return fallback
        ImageColor.getrgb(value)
        return value
    except (ValueError, TypeError):
        return fallback


def percentile_rules(value):
    """Only native v10 records may use the current percentile renderer."""
    source = as_dict(value)
    return (type(source.get('rules_version')) is int and source['rules_version'] == 10
            and source.get('die') in (None, 'D100'))


def public_integer(value, low, high, step=1):
    result = number(value, None)
    if isinstance(value, bool) or result is None or result != int(result):
        return None
    result = int(result)
    return result if low <= result <= high and (result-low) % step == 0 else None


def public_cost_breakdown(value):
    """Keep the published invoice, never reconstruct payable totals in the UI."""
    source = as_dict(value)
    if not source:
        return {}
    fields = ('base', 'plant_discount', 'base_after_modifiers', 'facility_upkeep',
              'facility_upkeep_from_day8', 'facility_upkeep_unlock_day',
              'overdue_surcharge', 'total')
    result = {key: public_integer(source.get(key), 0, 10**9) for key in fields}
    result['event_delta'] = public_integer(source.get('event_delta'), -10**9, 10**9)
    return result


def public_deadline(value):
    source = as_dict(value)
    if not source:
        return {}
    result = {key: source.get(key) if isinstance(source.get(key), str) else None
              for key in ('id', 'title')}
    fields = ('nominal_due_day', 'effective_due_day', 'unlocked_day', 'days_remaining',
              'overdue_days', 'missed_day', 'completed_day', 'overdue_surcharge')
    result.update({key: public_integer(source.get(key), 0, 10**9) for key in fields})
    result['status'] = source.get('status') if source.get('status') in (
        'active', 'missed', 'completed', 'completed_late') else None
    return result


def public_supplier(value):
    source = as_dict(value)
    if source.get('id') not in ('salvage', 'curated', 'focused'):
        return {}
    result = {key: source.get(key) if isinstance(source.get(key), str) else None
              for key in ('id', 'name', 'description')}
    result.update({key: public_integer(source.get(key), 0, 10**9)
                   for key in ('cost', 'stock', 'remaining', 'energy_cost', 'unlock_day', 'daily_limit')})
    result['unlocked'] = source.get('unlocked') if isinstance(source.get('unlocked'), bool) else None
    # Names come only from the five published category IDs, never a sealed item.
    result['categories'] = [{'id': key, 'name': KINDS[key]} for key in KINDS
                            if any(as_dict(row).get('id') == key
                                   for row in as_list(source.get('categories')))]
    return result


def public_management_detail(value, section='costs', page=0):
    """Explicit projection for every management overlay and its hit payload."""
    source = as_dict(value)
    campaign = as_dict(source.get('campaign'))
    paid = as_dict(source.get('last_settlement'))
    result = {'_view': 'management', '_section': section if section in ('costs', 'deadlines', 'suppliers') else 'costs',
              '_management_page': max(0, int(number(page))),
              'day': public_integer(source.get('day'), 1, 10**9),
              'phase': source.get('phase') if source.get('phase') in ('active', 'week_summary', 'lost') else None,
              'operating_cost': public_integer(source.get('operating_cost'), 0, 10**9),
              'operating_cost_breakdown': public_cost_breakdown(source.get('operating_cost_breakdown')),
              'campaign': {'next_milestone': public_deadline(campaign.get('next_milestone')),
                           'deadline_history': [public_deadline(row) for row in as_list(campaign.get('deadline_history')) if as_dict(row)]},
              'suppliers': [row for row in (public_supplier(v) for v in as_list(source.get('suppliers'))) if row],
              'last_settlement': None, 'crates': [], 'upgrade_details': []}
    for row in as_list(source.get('upgrade_details')):
        row = as_dict(row)
        if row.get('id') in UPGRADES:
            result['upgrade_details'].append(dict(id=row['id'], name=UPGRADES[row['id']], **{
                key: public_integer(row.get(key), 0, 10**9) for key in (
                    'daily_upkeep', 'daily_upkeep_from_day8', 'next_daily_upkeep',
                    'next_daily_upkeep_from_day8', 'upkeep_unlock_day')}))
    if paid:
        result['last_settlement'] = {key: public_integer(paid.get(key), 0, 10**9)
                                     for key in ('day', 'paid', 'credits_after_payment')}
        result['last_settlement']['breakdown'] = public_cost_breakdown(paid.get('breakdown'))
    for crate in as_list(source.get('crates')):
        crate = as_dict(crate)
        if crate.get('supplier') == 'focused' and crate.get('requested_kind') in KINDS:
            result['crates'].append({'id': crate.get('id') if isinstance(crate.get('id'), str) else None,
                                    'supplier': 'focused', 'requested_kind': crate['requested_kind'],
                                    'requested_kind_label': KINDS[crate['requested_kind']]})
    return result


def deadline_summary(value):
    stage = public_deadline(value)
    due = stage.get('effective_due_day')
    if due is None:
        return '等待公开期限'
    overdue = stage.get('overdue_days')
    remaining = stage.get('days_remaining')
    timing = f'逾期 {overdue} 天' if overdue else ('今日到期' if remaining == 0 else f'剩余 {remaining} 天' if remaining is not None else '等待公开进度')
    return f'第 {due} 天到期 · {timing}'


def public_roll(value):
    """Project native public rolls; unsupported records never become new rules."""
    source = as_dict(value)
    if not source:
        return {}
    if not percentile_rules(source):
        return {'_unsupported_rules': True}
    fields = ('id', 'day', 'item_id', 'item_name', 'customer_id', 'customer_name',
              'stage', 'modifier', 'modifiers', 'success', 'outcome', 'price',
              'explanation', 'rules_version', 'counter_offer', 'die', 'tens', 'ones',
              'roll', 'threshold', 'probability', 'base_chance', 'premium')
    roll = {key: source.get(key) for key in fields}
    roll['modifiers'] = [{key: row.get(key) for key in ('label', 'value')}
                         for row in as_list(source.get('modifiers')) if isinstance(row, dict)]
    roll['tens'] = public_integer(source.get('tens'), 0, 90, 10)
    roll['ones'] = public_integer(source.get('ones'), 0, 9)
    roll['roll'] = public_integer(source.get('roll'), 1, 100)
    roll['threshold'] = public_integer(source.get('threshold'), 1, 99)
    # Check consistency without inventing a missing combined roll.
    if (roll['tens'] is None or roll['ones'] is None
            or roll['roll'] != (roll['tens'] + roll['ones'] or 100)):
        roll['roll'] = None
    return roll


def roll_status(roll, negotiation=None):
    roll = public_roll(roll)
    if roll.get('_unsupported_rules'):
        return '不支持的规则版本', MUTED
    if roll.get('roll') is None:
        return '等待有效公开双骰', MUTED
    pending = public_negotiation(negotiation)
    if (pending and not pending.get('_unsupported_rules')
            and pending.get('item_id') == roll.get('item_id')
            and roll.get('stage') == 'initial' and roll.get('outcome') == 'failure'):
        return '还价中', LILAC
    return PERCENTILE_LABELS.get(roll.get('outcome'), ('等待公开判定', MUTED))


def roll_rules_label(roll):
    return 'v10 · D100 低骰规则' if percentile_rules(roll) else '不支持此规则版本 · 仅支持 v10'


def public_budget_range(value):
    pair = as_list(value)
    if len(pair) != 2:
        return []
    result = [public_integer(v, 0, 10**9) for v in pair]
    return result if None not in result and result[0] <= result[1] else []


def public_walkins(value):
    """Project public visit limits; never read a customer's actual budget."""
    source = as_dict(value)
    if not source:
        return {}
    result = {key: public_integer(source.get(key), 0, 10**9)
              for key in ('daily_limit', 'used', 'remaining')}
    result['budget_range'] = public_budget_range(source.get('budget_range'))
    result['min_condition'] = public_integer(source.get('min_condition'), 0, 100)
    result['visit_rule'] = source.get('visit_rule') if isinstance(source.get('visit_rule'), str) else None
    return result


def public_sale_option(value):
    """Forecasts contain public eligibility, not initial odds or private budgets."""
    source = as_dict(value)
    if not source:
        return {}
    result = {key: source.get(key) if isinstance(source.get(key), str) else None
              for key in ('customer_id', 'customer_name', 'warning')}
    for key in ('available', 'counter_eligible', 'preference_match', 'condition_met'):
        result[key] = source.get(key) if isinstance(source.get(key), bool) else None
    for key in ('public_reference', 'max_counter_ask', 'ask'):
        result[key] = public_integer(source.get(key), 0, 10**9)
    result['min_condition'] = public_integer(source.get('min_condition'), 0, 100)
    result['budget_range'] = public_budget_range(source.get('budget_range'))
    result['reasons'] = [v for v in as_list(source.get('reasons')) if isinstance(v, str)]
    return result


def public_sale_detail(item, walkins, page=0):
    source = as_dict(item)
    fields = ('id', 'art_id', 'name', 'kind', 'rarity', 'color', 'condition', 'price',
              'description', 'negotiating', 'public_reference')
    result = {key: source.get(key) for key in fields}
    result.update(_view='sale', _sale_page=max(0, int(number(page))),
                  sale_options=[public_sale_option(v) for v in as_list(source.get('sale_options')) if as_dict(v)],
                  walkins=public_walkins(walkins))
    return result


def public_collection_quality(value):
    """Allow only the engine's published stage assessment; never infer it."""
    source = as_dict(value)
    if not source:
        return {}
    result = {'min_condition': public_integer(source.get('min_condition'), 0, 100)}
    for key in ('condition_met', 'counted'):
        result[key] = source.get(key) if isinstance(source.get(key), bool) else None
    result['reason'] = source.get('reason') if isinstance(source.get('reason'), str) else None
    return result


def public_collection_action(value, replacement=False):
    source = as_dict(value)
    if not source:
        return {}
    result = {'available': source.get('available') if isinstance(source.get('available'), bool) else None,
              'reasons': [v for v in as_list(source.get('reasons')) if isinstance(v, str)],
              'energy_cost': public_integer(source.get('energy_cost'), 0, 100),
              'command': source.get('command') if isinstance(source.get('command'), str) else None}
    if replacement:
        result['cabinet_item_id'] = source.get('cabinet_item_id') if isinstance(source.get('cabinet_item_id'), str) else None
        result['cabinet_condition'] = public_integer(source.get('cabinet_condition'), 0, 100)
    else:
        result['cost'] = public_integer(source.get('cost'), 0, 10**9)
    return result


def public_collection_progress(value):
    source = as_dict(value)
    if not source:
        return {}
    result = {key: public_integer(source.get(key), 0, 10**6)
              for key in ('personal_count', 'qualified_count', 'qualified_categories', 'quality_themes')}
    result['min_condition'] = public_integer(source.get('min_condition'), 0, 100)
    result['missing'] = [v for v in as_list(source.get('missing')) if isinstance(v, str)]
    result['requirements'] = []
    for row in as_list(source.get('requirements')):
        row = as_dict(row)
        if row.get('key') not in ('collection', 'collection_categories', 'quality_themes'):
            continue
        result['requirements'].append({
            'key': row['key'], 'label': row.get('label') if isinstance(row.get('label'), str) else '收藏要求',
            'current': public_integer(row.get('current'), 0, 10**6),
            'target': public_integer(row.get('target'), 0, 10**6), 'met': row.get('met') is True})
    result['categories'] = []
    for row in as_list(source.get('categories')):
        row = as_dict(row)
        if row.get('id') in KINDS:
            result['categories'].append({'id': row['id'], 'name': KINDS[row['id']],
                                         'qualified_count': public_integer(row.get('qualified_count'), 0, 10**6),
                                         'theme_complete': row.get('theme_complete') is True})
    return result


def collection_number(value):
    return str(value) if value is not None else '?'


def public_collection_detail(value, observation=None, page=0):
    """Join discovered identities only with public, currently visible possessions."""
    source = as_dict(value)
    result = dict(public_catalog_entry(source), _view='codex')
    if not result['discovered']:
        return result
    observation = as_dict(observation)
    supplied = as_dict(source.get('_collection'))
    if not observation.get('collection_progress') and not supplied:
        return result
    rows = []
    if observation:
        identity = result.get('art_id')
        if identity:
            for location in ('collection', 'inventory'):
                rows.extend(dict(as_dict(item), location=location)
                            for item in as_list(observation.get(location))
                            if as_dict(item).get('art_id') == identity)
        progress = public_collection_progress(observation.get('collection_progress'))
    else:
        rows = as_list(supplied.get('items'))
        progress = public_collection_progress(supplied.get('progress'))
    items = []
    for row in rows:
        row = as_dict(row)
        if row.get('location') not in ('collection', 'inventory'):
            continue
        item = {key: row.get(key) if isinstance(row.get(key), str) else None for key in ('id', 'location')}
        item['condition'] = public_integer(row.get('condition'), 0, 100)
        item['collection_quality'] = public_collection_quality(row.get('collection_quality'))
        item['repair'] = public_collection_action(row.get('repair'))
        item['collection_replacement'] = public_collection_action(row.get('collection_replacement'), True)
        items.append(item)
    result['_collection'] = {'items': items, 'progress': progress}
    result['_collection_page'] = max(0, int(number(page)))
    return result


def public_catalog_entry(value, slot=None):
    """Fail closed if malformed public data includes unopened identities."""
    source = as_dict(value)
    slot = public_integer(source.get('slot'), 1, 10**6) or slot
    result = {'slot': slot, 'discovered': source.get('discovered') is True,
              'collected': source.get('discovered') is True and source.get('collected') is True}
    if result['discovered']:
        for key in ('art_id', 'name', 'kind', 'rarity', 'description'):
            if isinstance(source.get(key), str):
                result[key] = source[key]
        if as_dict(source.get('collection_quality')):
            result['collection_quality'] = public_collection_quality(source['collection_quality'])
    return result


def walkins_summary(value):
    visits = public_walkins(value)
    if not visits:
        return '普通散客 · 等待公开名额'
    remaining, limit = visits.get('remaining'), visits.get('daily_limit')
    amount = f'{remaining}/{limit} 次' if remaining is not None and limit is not None else '等待公开名额'
    budget = visits.get('budget_range')
    label = '常规预算'
    money = f' · {label} {budget[0]}–{budget[1]}' if budget else f' · {label}待公开'
    return f'散客剩余 {amount}{money}'


def sale_status(option):
    if option.get('available') is False:
        return '当前不可出售', MUTED
    if option.get('available') is not True or option.get('counter_eligible') is None:
        return '等待完整公开条件', MUTED
    if option.get('counter_eligible'):
        return '普通失败可还价', TEAL
    return '普通失败直接离开', RED


def roll_summary(roll):
    roll = public_roll(roll)
    if roll.get('_unsupported_rules'):
        return '不支持的骰子记录'
    result = roll.get('roll')
    return f'D100 {result:02d}' if result is not None else 'D100 ?'


def percentile_chance_text(threshold):
    threshold = public_integer(threshold, 1, 99)
    if threshold is None:
        return '等待完整公开成功阈值'
    return f'低骰成功：01–{threshold:02d} · 成功率 {threshold}%'


def roll_math(roll):
    """Read public adjudication fields verbatim; never estimate hidden economics."""
    roll = public_roll(roll)
    if roll.get('_unsupported_rules'):
        return '不支持此规则版本 · 仅支持 v10'
    tens, ones, result = (roll.get(key) for key in ('tens', 'ones', 'roll'))
    if result is None:
        return 'D100 · 等待有效且一致的公开双骰'
    digits = f'{tens:02d} + {ones} = {result:02d}'
    threshold = roll.get('threshold')
    if threshold is None:
        return f'D100 {digits} · 等待完整公开阈值'
    return f'D100 {digits} · ≤{threshold:02d} 成功（{threshold}%）'


def public_negotiation(value):
    """Keep native v10 quotes and their exact published preview public."""
    source = as_dict(value)
    if not source:
        return {}
    if (not percentile_rules(source) or type(source.get('origin_rules_version')) is not int
            or source['origin_rules_version'] != 10):
        return {'_unsupported_rules': True}
    fields = ('item_id', 'item_name', 'customer_id', 'customer_name', 'rules_version', 'origin_rules_version',
              'original_price', 'counter_offer', 'remaining_offers', 'final_offer_energy',
              'accept_income', 'final_failure_income')
    pending = {key: source.get(key) for key in fields}
    bounds = as_dict(source.get('final_offer_bounds'))
    pending['final_offer_bounds'] = {key: bounds.get(key) for key in ('min', 'max', 'available')}
    preview = as_dict(source.get('preview'))
    fields = ('price', 'basis', 'modifier', 'modifiers', 'energy_cost', 'accept_income',
              'success_income', 'failure_income', 'warning', 'suggested', 'base_chance',
              'threshold', 'probability', 'premium', 'critical_probability', 'fumble_probability')
    pending['preview'] = {key: preview.get(key) for key in fields} if preview else {}
    if preview:
        pending['preview']['modifiers'] = [{key: row.get(key) for key in ('label', 'value')}
                                           for row in as_list(preview.get('modifiers')) if isinstance(row, dict)]
    return pending


def has_bargaining_preview(value):
    return bool(public_negotiation(value))


def has_roll_breakdown(roll):
    return (percentile_rules(roll) and roll.get('stage') == 'final'
            and public_integer(roll.get('threshold'), 1, 99) is not None
            and public_integer(roll.get('base_chance'), 1, 99) is not None
            and number(roll.get('counter_offer'), None) is not None)


def chance_breakdown(roll):
    return (f'基础几率 {number(roll.get("base_chance")):g}% · 公开还价 {number(roll.get("counter_offer")):g}'
            f' → 阈值 {number(roll.get("threshold")):g}')


def percentile_preview(preview):
    """Validate published exact odds, never calculate hidden economic values."""
    preview = as_dict(preview)
    threshold = public_integer(preview.get('threshold'), 1, 99)
    base = public_integer(preview.get('base_chance'), 1, 99)
    probability = number(preview.get('probability'), None)
    if (preview.get('basis') != 'public_counter' or threshold is None or base is None
            or probability is None or not math.isclose(probability, threshold / 100)
            or public_integer(preview.get('price'), 1, 9999) is None
            or isinstance(preview.get('modifier'), bool)
            or number(preview.get('modifier'), None) is None):
        return None
    return base, threshold


@lru_cache(maxsize=160)
def font(size, bold=False):
    name = 'NotoSansCJK-Bold.ttc' if bold else 'NotoSansCJK-Regular.ttc'
    path = Path('/usr/share/fonts/opentype/noto') / name
    if path.exists():
        return ImageFont.truetype(str(path), max(10, int(size)), index=2)
    return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', max(10, int(size)))


class ObservationReader:
    """Poll only the caller-provided observation; never discover another file."""
    def __init__(self, path):
        self.path = Path(path)
        if self.path.name.lower() in {'save.json', 'state.json'} or self.path.resolve().name.lower() in {'save.json', 'state.json'}:
            raise ValueError('观战窗口只能读取公开 observation 文件，不能读取存档')
        self.observation = None
        self.stamp = None
        self._contents = None
        self._generation = 0
        self.error = None
        self.updated_at = None

    def poll(self):
        try:
            # Metadata can remain identical after an in-place or atomic rewrite.
            # Read one bounded snapshot; only unchanged accepted bytes may skip
            # parsing. Opening each time also detects lost read permission.
            limit = 4 * 1024 * 1024
            with self.path.open('rb') as source:
                contents = source.read(limit + 1)
            if len(contents) > limit:
                raise ValueError('公开状态文件过大')
            if contents == self._contents:
                self.error = None
                return False
            data = json.loads(contents.decode('utf-8'))
            if not isinstance(data, dict) or 'credits' not in data or not isinstance(data.get('inventory', []), list):
                raise ValueError('等待有效的公开状态')
            if not native_observation(data):
                self.observation = None
                self.stamp = None
                self._contents = None
                self.updated_at = None
                self.error = '不支持此公开状态版本 · 仅支持 v10'
                return False
            # Private engine state is never public output.
            if any(k in data for k in ('rng_state', 'rng', 'hidden_items', '_rng', 'random_state')):
                raise ValueError('文件含非公开状态，已拒绝读取')
            self.observation = data
            self._contents = contents
            self._generation += 1
            self.stamp = self._generation
            self.error = None
            self.updated_at = time.monotonic()
            return True
        except (OSError, ValueError, UnicodeError):
            self.error = '等待公开状态更新' if self.observation else '等待店长开门'
            return False


class Renderer:
    """Headless, deterministic render surface; optional time only animates artwork."""
    def __init__(self):
        self.image = None
        self.draw = None
        self.words = []
        self.hits = []
        self.tab = 'shelf'
        self.page = 0

    def rect(self, box, fill=PANEL, radius=18, outline=None, width=1):
        self.draw.rounded_rectangle(tuple(round(v) for v in box), radius=radius, fill=fill, outline=outline, width=width)

    def line(self, points, fill=LINE, width=2):
        self.draw.line(points, fill=fill, width=width, joint='curve')

    def ellipse(self, box, fill, outline=None, width=1):
        self.draw.ellipse(box, fill=fill, outline=outline, width=width)

    def polygon(self, points, fill, outline=None):
        self.draw.polygon(points, fill=fill, outline=outline)

    def text(self, xy, text, size=24, color=INK, bold=False, max_width=None, lines=1, anchor='lt', spacing=1.3):
        value = str(text)
        f = font(size, bold)
        paragraphs = value.split('\n')
        wrapped = []
        for paragraph in paragraphs:
            current = ''
            # Keep quantities such as 70%, 0.5% and 1/3 intact in narrow cards.
            for token in re.findall(r'[+-]?\d+(?:[.,]\d+)*(?:/\d+(?:[.,]\d+)*)?[%％]?|.', paragraph):
                if max_width and f.getlength(current + token) > max_width and current:
                    wrapped.append(current)
                    current = token
                else:
                    current += token
            wrapped.append(current)
        truncated = len(wrapped) > lines
        wrapped = wrapped[:lines]
        if truncated and wrapped:
            tokens = re.findall(r'[+-]?\d+(?:[.,]\d+)*(?:/\d+(?:[.,]\d+)*)?[%％]?|.', wrapped[-1])
            while max_width and f.getlength(''.join(tokens) + '…') > max_width and tokens:
                tokens.pop()
            wrapped[-1] = ''.join(tokens) + '…'
        self.words.append(value)
        for i, row in enumerate(wrapped):
            self.draw.text((xy[0], xy[1] + i * size * spacing), row, font=f, fill=color, anchor=anchor)
        return len(wrapped) * size * spacing

    def pill(self, xy, label, color=TEAL, size=18, fill='#203f40', padding=13):
        w = math.ceil(font(size, True).getlength(str(label))) + padding * 2
        self.rect((xy[0], xy[1], xy[0]+w, xy[1]+size+19), fill, 10)
        self.text((xy[0]+padding, xy[1]+8), label, size, color, True)
        return w

    def progress(self, x, y, w, fraction, color=TEAL, h=7):
        self.rect((x,y,x+w,y+h), '#334a50', h//2)
        fraction = max(0, min(1, number(fraction)))
        if fraction:
            self.rect((x,y,x+max(h,w*fraction),y+h), color, h//2)

    def star(self, x, y, size, color=GOLD):
        self.polygon([(x,y-size),(x+size*.28,y-size*.28),(x+size,y),(x+size*.28,y+size*.28),
                      (x,y+size),(x-size*.28,y+size*.28),(x-size,y),(x-size*.28,y-size*.28)],color)

    def item_art(self, x, y, size, item=None, crate=False):
        """Draw a public identity, or a deliberately identical undiscovered mark.

        Identity changes the silhouette, not just its paint. Unknown observations
        return before looking at any identity, kind, rarity or color field.
        """
        item = as_dict(item)
        s = size / 100
        def b(box): return tuple((x if i%2==0 else y)+v*s for i,v in enumerate(box))
        def r(box,c,rad=3,o=None): self.rect(b(box),c,max(1,int(rad*s)),o)
        def e(box,c,o=None): self.ellipse(b(box),c,o,max(1,int(2*s)))
        def l(pts,c,w=2): self.line([(x+a*s,y+bv*s) for a,bv in pts],c,max(1,int(w*s)))
        def p(pts,c,o=None): self.polygon([(x+a*s,y+bv*s) for a,bv in pts],c,o)
        def a(box,start,end,c,w=2): self.draw.arc(b(box),start,end,fill=c,width=max(1,int(w*s)))
        def star(xx,yy,sz,c=GOLD): self.star(x+xx*s,y+yy*s,sz*s,c)
        e((9,85,91,98),'#14212c')
        if item.get('discovered') is False:
            # No rarity-colored trim, shape family, or discoverable-name alias.
            e((20,16,80,80),'#293c47','#667a82')
            a((39,31,61,51),185,360,'#aebcc0',4)
            l([(60,41),(58,49),(50,55),(50,61)],'#aebcc0',4)
            e((47,67,53,73),'#aebcc0')
            return
        rarity = item.get('rarity')
        color = safe_color(item.get('color'), RARITIES.get(rarity if isinstance(rarity,str) else '', ('',TEAL))[1])
        kind = item.get('kind','artifact')
        identity = item.get('art_id')
        if not isinstance(identity,str) or identity not in ITEM_ART_IDS:
            name = item.get('name')
            identity = ITEM_ART_NAMES.get(name) if isinstance(name,str) else None
        dark, metal, light = '#203942', '#789a9e', '#d7e9d9'
        if crate:
            p([(13,28),(48,10),(88,29),(51,49)],'#a17b5c')
            p([(13,28),(51,49),(51,91),(13,69)],'#755744')
            p([(51,49),(88,29),(88,70),(51,91)],'#5a4339')
            l([(32,19),(70,38),(70,80)],GOLD,6)
            l([(14,48),(51,70),(87,50)],'#b38a62',2)
            r((29,43,47,62),'#eed395',2)
            l([(36,48),(41,48),(38,54)],'#79573b',2)
        elif identity == 'wrench':
            # Hinged, partly folded ion wrench, with an unmistakable open jaw.
            p([(43,43),(60,53),(43,87),(30,80)],metal)
            p([(43,70),(60,61),(71,70),(44,91),(33,84)],color)
            p([(36,13),(56,8),(49,27),(62,35),(77,20),(83,40),(65,55),(45,48),(30,29)],color)
            p([(36,13),(38,31),(49,42),(45,48),(30,29)],'#608c90')
            e((43,44,60,61),GOLD);e((48,49,55,56),dark)
            l([(39,75),(46,64)],light,3);e((39,80,46,87),dark)
            l([(60,20),(66,13),(71,16)],GOLD,2)
        elif identity == 'lamp':
            # A chunky flashlight angled upward, with a floating light beam.
            p([(16,79),(31,91),(65,49),(49,35)],metal)
            p([(20,77),(31,86),(60,49),(51,42)],color)
            p([(46,35),(59,20),(82,38),(69,54)],GOLD)
            p([(57,20),(68,17),(91,34),(81,40)],light)
            p([(63,21),(70,22),(84,33),(79,34)],'#7ad2ca')
            p([(73,16),(89,6),(96,19),(91,29)],'#365b61')
            l([(28,74),(37,80)],dark,3);l([(35,65),(44,71)],dark,3)
            e((45,50,52,57),GOLD)
            star(24,29,5,light);star(86,65,4,color)
        elif identity == 'coffee':
            # An orbital moka pot: angular lower chamber, spout and open handle.
            a((61,26,92,66),265,95,GOLD,7)
            p([(22,44),(9,33),(7,40),(19,61),(28,62)],color)
            p([(29,24),(64,24),(73,55),(65,79),(29,79),(21,55)],color)
            p([(27,55),(69,55),(65,79),(29,79)],metal)
            p([(32,25),(39,25),(35,51),(27,51)],light)
            r((25,51,71,59),GOLD,2);r((27,79,68,85),dark,3)
            e((26,19,67,29),GOLD);r((41,12,52,22),dark,3)
            a((8,54,88,78),5,174,'#b9d9d0',2)
            a((40,1,54,17),100,280,'#90aea7',2)
        elif identity == 'cleaner':
            # Spherical singer with a brush skirt and a clearly circular face.
            for xx in (24,34,44,54,64,74): l([(xx,77),(xx-5,88)],metal,3)
            e((15,26,84,86),color);e((20,31,79,73),'#527e81')
            e((26,37,72,70),dark)
            a((33,46,44,57),190,345,GOLD,2);a((54,46,65,57),190,345,GOLD,2)
            a((43,52,55,63),0,180,light,2)
            a((22,31,78,82),30,147,light,2)
            r((39,20,60,28),GOLD,3)
            l([(77,24),(77,9),(88,6),(88,19)],GOLD,3)
            e((70,20,79,27),GOLD);e((81,15,90,22),GOLD)
            star(15,18,4,light)
        elif identity == 'moss':
            # A sealed jar of moonlit moss, with the reflected crescent overhead.
            r((25,28,77,87),'#487878',13,light)
            r((35,15,67,33),'#67908e',4);r((32,12,69,24),'#ae8b65',3)
            l([(40,15),(40,22),(60,22),(60,15)],'#d7b389',2)
            e((31,65,71,85),'#355e59')
            for xx,yy,rr in ((35,70,9),(48,63,10),(61,69,9),(51,76,8)):
                e((xx-rr,yy-rr,xx+rr,yy+rr),color)
            e((46,36,63,53),'#e8e7b3');e((51,32,67,48),'#487878')
            l([(31,39),(31,58)],'#c1e5d9',3)
            star(40,61,3,light);star(62,62,2,light)
        elif identity == 'map':
            # Tripod projector beneath a wide floating star-chart window.
            l([(47,76),(27,93)],metal,4);l([(54,76),(74,93)],metal,4)
            l([(50,78),(50,94)],GOLD,3)
            p([(42,68),(21,51),(77,51),(58,68)],'#35585c')
            r((31,67,69,80),metal,5);e((37,65,63,73),color)
            p([(11,17),(79,9),(89,52),(21,60)],'#2e535c',color)
            l([(17,29),(82,21)],'#487783',1);l([(21,47),(86,39)],'#487783',1)
            l([(32,15),(41,57)],'#487783',1);l([(57,12),(66,54)],'#487783',1)
            l([(28,40),(41,26),(59,35),(71,21)],light,2)
            for xx,yy in ((28,40),(41,26),(59,35)): star(xx,yy,3,GOLD)
            e((66,16,76,26),color);e((69,19,73,23),dark)
            l([(74,42),(79,47)],RED,2);l([(79,42),(74,47)],RED,2)
        elif identity == 'music':
            # Glass bell, comet and brass winding crank over a wooden music box.
            p([(27,64),(73,64),(81,81),(66,91),(23,83)],'#9e735d')
            p([(23,72),(67,80),(81,71),(81,81),(66,91),(23,83)],'#755747')
            l([(30,80),(59,86)],GOLD,2)
            a((20,11,78,74),180,360,light,3)
            l([(20,43),(20,67),(78,67),(78,43)],light,2)
            e((20,61,78,73),metal);e((27,62,71,68),GOLD)
            l([(30,53),(58,31),(66,37),(44,55)],color,4)
            star(39,47,10,GOLD);star(63,26,3,light)
            l([(30,35),(30,43)],'#9dc4c3',2)
            l([(79,77),(90,77),(90,68)],GOLD,3);e((86,64,94,71),color)
        elif identity == 'welder':
            # Slim insulated soldering pen, cable loop and hot split-phase tip.
            a((4,63,37,92),0,300,metal,4)
            p([(22,77),(33,87),(66,43),(55,34)],color)
            p([(25,75),(30,79),(59,40),(55,36)],light)
            p([(54,33),(64,26),(73,34),(67,44)],GOLD)
            p([(64,27),(77,17),(80,22),(72,35)],metal)
            l([(77,18),(86,8)],GOLD,3)
            l([(40,57),(49,64)],dark,3);l([(35,64),(44,71)],dark,3)
            star(87,9,5,light);l([(78,6),(76,2)],color,2)
            l([(89,19),(96,20)],color,2);l([(65,13),(66,7)],GOLD,2)
        elif identity == 'bee':
            # Mail bee: paired translucent wings, antennae, stripes and envelope.
            e((11,21,48,52),'#add7d3',light);e((53,15,90,49),'#add7d3',light)
            l([(20,29),(39,44)],'#699da3',2);l([(80,24),(61,41)],'#699da3',2)
            l([(40,29),(32,12)],metal,3);l([(57,28),(66,9)],metal,3)
            e((28,8,36,16),GOLD);e((63,5,71,13),GOLD)
            e((25,36,77,83),GOLD)
            r((28,50,74,58),dark,3);r((30,66,72,73),dark,3)
            e((30,23,68,53),color);r((35,32,64,46),dark,6)
            e((41,36,46,41),GOLD);e((54,36,59,41),GOLD)
            l([(29,61),(19,67),(30,75)],metal,3);l([(73,60),(82,65),(72,74)],metal,3)
            p([(48,81),(53,91),(58,81)],GOLD)
            r((34,60,68,81),'#f0dfb4',2)
            l([(35,62),(51,72),(67,62)],'#ad8664',2)
            star(52,74,3,RED)
        elif identity == 'seed':
            # Suspended pointed seed with a curled shoot and whispering ripples.
            p([(51,16),(68,37),(72,58),(61,80),(48,88),(30,73),(26,55),(36,31)],color)
            p([(51,16),(46,48),(48,88),(30,73),(26,55),(36,31)],'#5b8a83')
            l([(50,27),(45,48),(50,74)],light,2)
            a((48,2,71,25),20,235,'#a8d19e',3)
            e((66,5,77,13),'#c9dba4')
            a((17,28,81,84),120,213,'#85b9b0',2)
            a((9,22,89,90),131,200,'#527d81',2)
            a((22,25,84,82),302,54,GOLD,2)
            star(77,68,3,light)
        elif identity == 'dawn':
            # A lightbulb whose glass contains a literal rising sun and horizon.
            e((19,8,81,69),'#6f6864',color)
            p([(28,48),(72,48),(64,73),(36,73)],'#6f6864')
            e((32,33,68,65),'#ffe0a0')
            p([(27,54),(40,50),(51,54),(63,51),(72,55),(64,69),(36,69)],'#cf9271')
            l([(29,57),(69,57)],GOLD,2)
            for pts in ([(50,19),(50,26)],[(29,29),(35,34)],[(70,28),(65,34)]):l(pts,GOLD,2)
            l([(29,24),(26,32),(26,40)],light,3)
            r((36,70,65,85),metal,4);l([(38,74),(62,74)],dark,2);l([(38,80),(62,80)],dark,2)
            r((43,85,58,91),GOLD,3)
            star(10,49,4,color);star(88,21,4,color)
        elif identity == 'letter':
            # The last Earth letter: large envelope, wax seal and a blue stamp.
            p([(13,29),(78,18),(90,72),(25,85)],'#decc9e')
            p([(15,32),(54,56),(80,23)],'#f4e7c6')
            l([(15,32),(54,56),(80,23)],'#ab8a69',2)
            l([(24,79),(43,53)],'#b89975',2);l([(85,69),(65,49)],'#b89975',2)
            e((48,50,63,65),'#b76d61');star(56,58,4,GOLD)
            r((65,29,79,43),'#f0e8c9',1);e((67,31,77,41),'#628f9d')
            p([(69,33),(73,32),(72,36),(75,38),(71,40),(70,36)],'#a4c4a4')
            l([(28,62),(37,60)],'#a68568',2);l([(29,67),(43,65)],'#a68568',2)
            a((4,8,41,44),208,287,color,2);a((10,14,35,38),208,287,color,2)
            star(85,85,4,color)
        elif identity == 'compass':
            # Round pocket compass, suspension loop and a two-tone wind needle.
            e((41,3,59,22),GOLD);e((46,7,54,16),dark)
            e((14,18,86,90),GOLD);e((20,24,80,84),metal);e((25,29,75,79),dark)
            for pts in ([(50,31),(50,38)],[(50,70),(50,77)],[(27,54),(34,54)],[(66,54),(73,54)]):l(pts,light,2)
            p([(66,36),(55,59),(35,72),(44,50)],color)
            p([(66,36),(55,59),(50,54)],'#eabb88')
            p([(35,72),(44,50),(50,54)],'#598b90')
            e((46,50,54,58),GOLD)
            a((19,22,80,86),195,269,light,2)
        elif identity == 'kettle':
            # Wide weather flask with a narrow neck, cloud and sugary rainfall.
            r((39,14,62,41),'#88b5b6',4)
            e((18,30,83,89),'#6d9ca1',light)
            r((37,10,65,21),'#ab8a66',3);l([(42,14),(59,14)],GOLD,2)
            e((31,43,48,59),'#e6e6d6');e((42,36,62,59),'#e6e6d6');e((56,44,71,59),'#e6e6d6')
            r((34,51,68,60),'#e6e6d6',4)
            for xx,yy in ((39,69),(51,73),(64,67)):star(xx,yy,3,color)
            a((24,39,76,82),80,150,'#b9d6cf',3)
            l([(40,5),(40,1)],MUTED,2);l([(59,5),(62,2)],MUTED,2)
        elif identity == 'sprout':
            # A shy bent mimosa, paired tiny leaflets and a squat clay pot.
            l([(49,69),(50,43),(43,26),(34,21)],'#9ab69a',3)
            l([(50,51),(29,34)],'#9ab69a',2);l([(50,53),(72,41)],'#9ab69a',2)
            for xx,yy in ((32,35),(39,41),(60,47),(68,43)):
                e((xx-8,yy-7,xx+1,yy),color);e((xx,yy,xx+9,yy+6),'#94bc9b')
            e((24,14,40,24),'#b7d1a6');e((40,23,55,32),color)
            p([(29,67),(73,67),(67,90),(35,90)],'#af785f')
            r((26,63,76,72),'#dcac82',3);l([(40,79),(58,79)],'#d9a179',2)
            e((19,28,23,32),GOLD);e((76,34,80,38),GOLD)
        elif identity == 'snail':
            # Snail courier: spiral parcel-shell, eyestalks and a caterpillar tread.
            r((12,70,83,86),metal,8);r((17,75,78,82),dark,4)
            for xx in (23,35,47,59,71):e((xx-3,76,xx+3,82),GOLD)
            r((17,59,77,75),color,7)
            e((18,28,63,73),'#b1916c',GOLD)
            a((25,34,58,66),5,300,'#ead09d',3)
            a((33,40,52,59),185,359,'#755c50',3)
            l([(50,49),(50,54),(41,54)],'#755c50',3)
            e((64,41,88,72),color)
            l([(72,46),(69,25)],metal,3);l([(82,46),(88,28)],metal,3)
            e((65,20,73,28),GOLD);e((84,23,92,31),GOLD)
            e((71,49,75,54),dark);e((80,49,84,54),dark)
            r((27,18,56,33),'#c0a57b',2);l([(41,19),(41,31)],light,3)
        elif identity == 'clock':
            # A clock cabinet whose lower drawer stores a quiet crescent moon.
            r((22,17,77,79),'#937864',7);r((27,22,72,66),color,5)
            e((33,25,67,59),'#f0dfb3');e((37,29,63,55),'#d1ba8e')
            l([(50,33),(50,43),(59,47)],dark,3);e((47,40,53,46),dark)
            l([(48,29),(52,29)],dark,2);l([(48,55),(52,55)],dark,2)
            p([(24,65),(71,65),(82,80),(31,80)],'#4d5554')
            e((43,65,59,79),GOLD);e((49,62,62,75),'#4d5554')
            r((30,78,84,88),'#b99270',3);r((49,80,64,85),GOLD,2)
            r((28,89,38,94),dark,2);r((67,89,77,94),dark,2)
            star(79,15,4,color)
        elif identity == 'needle':
            # Long needle and an open looping gold thread that sews two stars.
            a((12,12,65,57),55,328,GOLD,3)
            a((25,42,83,87),235,70,GOLD,3)
            l([(24,44),(22,55),(32,65)],GOLD,3)
            p([(69,14),(76,14),(79,22),(25,89),(60,24)],color)
            p([(71,20),(74,20),(29,84)],light)
            l([(67,23),(72,18)],dark,3)
            l([(69,20),(57,12),(45,13)],GOLD,2)
            star(35,70,9,'#d7cca7');star(75,76,7,color)
            l([(36,67),(36,72)],'#8d765e',2);l([(72,75),(77,75)],dark,2)
        elif identity == 'fern':
            # Angular translucent fronds, visibly different from rounded plants.
            l([(51,74),(52,16)],light,3)
            for yy,spread in ((28,17),(40,26),(53,32),(65,26)):
                p([(51,yy+8),(51-spread,yy-5),(53-spread,yy+7)],color)
                p([(53,yy+8),(53+spread,yy-9),(53+spread,yy+3)],'#91d2c1')
                l([(51,yy+7),(53-spread,yy+5)],'#d2e5dd',1)
                l([(53,yy+6),(51+spread,yy-5)],'#d1bde9',1)
            p([(52,7),(44,23),(53,29),(61,19)],'#c4d9ca')
            p([(31,76),(70,76),(64,92),(38,92)],'#657b8c')
            p([(31,76),(48,81),(38,92)],'#99b1af')
            p([(48,81),(70,76),(64,92)],'#a09cb7')
            star(83,23,3,light)
        elif identity == 'radio':
            # Rounded tabletop radio, big speaker, tuning strip and ocean dial.
            l([(26,30),(14,8)],metal,3);e((11,5,17,11),GOLD)
            r((12,29,87,85),'#9b7964',12);r((18,35,81,79),color,8)
            e((24,44,56,74),dark)
            for xx in (31,38,45):l([(xx,49),(xx,69)],metal,2)
            r((60,43,75,50),dark,2);l([(65,43),(65,50)],GOLD,2)
            e((61,58,76,73),GOLD);l([(64,66),(68,62),(72,66)],'#8b735a',2)
            r((20,85,32,91),dark,2);r((66,85,78,91),dark,2)
            a((41,6,77,34),203,337,color,2);a((48,13,70,32),203,337,GOLD,2)
        elif identity == 'cat':
            # Cat anatomy stays readable at thumbnail size: ears, tail and key.
            a((66,43,96,84),275,110,color,7)
            e((35,45,74,90),color)
            p([(24,39),(25,13),(42,23),(56,22),(73,10),(76,43)],color)
            p([(28,20),(30,35),(39,28)],'#d8aaad');p([(60,28),(70,17),(71,34)],'#d8aaad')
            e((25,23,75,61),color)
            p([(33,39),(45,39),(39,44)],GOLD);p([(55,39),(67,39),(61,44)],GOLD)
            p([(47,46),(54,46),(50,50)],dark)
            l([(50,50),(45,54)],dark,2);l([(50,50),(56,54)],dark,2)
            l([(23,47),(35,49)],light,2);l([(65,49),(78,45)],light,2)
            r((32,82,49,91),metal,5);r((56,82,73,91),metal,5)
            l([(51,66),(51,80)],light,2)
            l([(35,69),(21,69)],GOLD,4)
            e((10,58,23,71),GOLD);e((10,69,23,82),GOLD)
            e((14,62,19,67),dark);e((14,73,19,78),dark)
            r((38,57,64,63),dark,3);e((47,60,55,68),GOLD)
        elif identity == 'hammer':
            # Heavy planet forge hammer; a ringed globe forms its striking head.
            p([(48,38),(62,44),(43,92),(28,86)],metal)
            p([(38,65),(50,70),(43,90),(30,85)],'#a2785c')
            l([(37,73),(46,77)],GOLD,2);l([(34,81),(44,85)],GOLD,2)
            p([(25,20),(34,12),(77,30),(81,41),(70,51),(27,33)],color)
            p([(23,21),(31,15),(36,23),(29,39),(21,32)],metal)
            e((49,14,82,48),GOLD);e((57,20,69,32),'#d5a568')
            l([(43,45),(87,19)],'#f7e6b7',3)
            a((15,6,92,57),310,138,'#bd9e72',2)
            star(88,62,6,color);star(16,54,4,'#eea486');e((84,4,90,10),'#e3aa7e')
        elif identity == 'tree':
            # Golden daylight bonsai, spreading crown and a shallow oval planter.
            l([(49,77),(49,50),(36,36)],'#b98c66',6)
            l([(48,59),(66,41)],'#b98c66',5)
            l([(43,49),(24,42)],'#b98c66',4)
            for box,c in (((10,24,42,49),'#b5b778'),((26,9,61,37),color),((49,20,85,48),'#dec879'),((65,32,94,54),'#bdad69')):
                e(box,c)
            e((37,14,53,28),'#f4dfa4');star(67,27,5,'#fff0c3')
            l([(16,14),(12,9)],color,2);l([(64,10),(67,4)],color,2)
            e((20,74,80,92),'#a57b64');e((20,71,80,83),'#d8b486')
            e((27,73,73,79),'#5d6960');l([(46,76),(56,76)],'#b98c66',4)
        elif identity == 'whale':
            # Long cruising whale with tail flukes, belly, fins and cabin lights.
            p([(66,47),(86,27),(96,26),(91,42),(80,53),(93,63),(92,75),(79,70),(67,58)],color)
            e((8,33,80,74),color)
            p([(35,37),(45,23),(50,24),(55,37)],'#a8bcb3')
            a((10,37,79,72),0,176,'#e1d8b6',8)
            p([(42,60),(60,64),(51,81),(40,79)],metal)
            e((19,47,26,54),dark);e((20,47,23,50),light)
            a((11,48,32,63),45,140,dark,2)
            for xx in (37,49,61):
                e((xx-4,43,xx+4,51),GOLD);e((xx-2,45,xx+2,49),dark)
            l([(29,35),(29,65)],'#ad976e',3)
            l([(24,31),(21,22),(27,15)],metal,2)
            e((17,12,24,19),color);e((30,7,36,13),GOLD)
        elif kind == 'plant':
            l([(51,78),(50,29)],'#89c79c',4)
            e((17,28,51,51),color); e((49,10,77,41),'#bedbb0')
            e((50,45,85,65),color)
            p([(27,63),(78,63),(69,91),(35,91)],'#b77e62')
            r((24,61,80,70),'#e3b88e',3)
            e((31,33,40,38),'#e7f5c4')
        elif kind == 'bot':
            l([(50,23),(50,8)],GOLD,3);e((44,3,56,15),GOLD)
            r((20,24,81,65),color,13)
            r((27,33,75,54),'#193940',8)
            e((34,40,43,46),GOLD);e((59,40,68,46),GOLD)
            l([(16,37),(6,54),(17,64)],'#82aaa6',5)
            l([(85,37),(94,54),(84,64)],'#82aaa6',5)
            r((29,68,72,85),'#abc0b0',5)
            e((30,82,46,95),'#789391');e((59,82,75,95),'#789391')
            r((41,72,61,77),GOLD,2)
        elif kind == 'tool':
            p([(43,38),(60,47),(41,93),(25,85)],'#799aa5')
            p([(37,11),(57,7),(48,27),(61,36),(78,20),(84,42),(66,55),(43,47),(30,29)],color)
            l([(37,75),(49,53)],'#cce2cc',3)
            e((30,80,39,89),'#1d3941')
        elif kind == 'signal':
            r((15,35,84,86),color,11)
            r((23,45,65,72),'#173641',4)
            l([(27,59),(34,59),(39,51),(47,66),(54,57),(61,57)],'#a8e3c0',2)
            e((69,49,78,58),GOLD);e((69,66,78,75),GOLD)
            l([(68,33),(83,8)],'#c8cfab',3)
            self.draw.arc(b((18,3,61,43)),205,330,fill=color,width=max(1,int(2*s)))
            self.draw.arc(b((25,10,54,37)),205,330,fill=GOLD,width=max(1,int(2*s)))
        else:
            e((15,22,85,88),'#30444c',color)
            p([(50,6),(79,45),(50,87),(22,45)],color)
            p([(50,6),(50,87),(22,45)],'#687c93')
            p([(50,6),(79,45),(50,46)],'#dfdfc4')
            l([(23,45),(77,45)],'#eff6dd',2)
            self.star(x+50*s,y+45*s,9*s,'#f9e6bb')

    def shop_scene(self, box, o, frame=0):
        """Original procedural illustration. Items on the counter are public items."""
        x,y,w,h = box
        # Paint into a consistent 680 x 320 illustration, then composite to fit.
        old_image, old_draw = self.image, self.draw
        self.image=Image.new('RGB',(680,320),'#233643');self.draw=ImageDraw.Draw(self.image)
        self.rect((0,0,680,320),'#233643',0)
        # Port window, distant ringed planet and pinprick stars.
        self.rect((209,18,537,215),'#4c6668',72)
        self.rect((218,26,528,207),'#142838',68)
        for i in range(34):
            xx=236+i*73%270; yy=38+i*41%150
            self.ellipse((xx,yy,xx+(i%3==0)+1,yy+(i%3==0)+1),'#809d9d')
        self.ellipse((376,45,452,121),'#71818b')
        self.ellipse((379,46,433,101),'#a3a79b')
        self.line([(356,106),(472,60)],'#b0b3a2',3)
        self.line([(362,111),(476,65)],'#576e79',2)
        self.line([(372,27),(372,207)],'#405c60',4)
        self.line([(218,139),(528,139)],'#405c60',4)
        # Wood-panelled side wall and hanging brass lamp.
        for xx in range(17,204,32): self.line([(xx,0),(xx,219)],'#2e4750',2)
        self.line([(160,0),(160,39)],'#a78b61',3)
        self.polygon([(141,39),(179,39),(195,68),(125,68)],'#c09b63')
        self.ellipse((127,62,192,76),'#edd195')
        self.polygon([(130,73),(190,73),(227,218),(90,218)],'#34474a')
        # Shelf with decorative bottles and a real public item when available.
        self.rect((34,91,176,97),'#987453',2)
        self.rect((34,166,176,174),'#987453',2)
        self.rect((44,57,65,90),'#7ca8a3',5);self.rect((49,51,61,60),'#dcc493',2)
        self.rect((77,65,97,90),'#b18f7b',4);self.rect((116,47,128,91),'#bea57e',2)
        self.rect((133,55,150,91),'#839c88',2)
        self.item_art(60,101,69,{'kind':'plant','color':'#8da883'})
        # Handpainted shop plaque, chalkboard, pennant garland.
        self.rect((563,43,653,130),'#b58e63',8)
        self.rect((568,48,648,125),'#203e41',5)
        self.text((608,60),'OPEN',16,GOLD,True,anchor='mt')
        self.text((608,84),'星屑旧物',14,INK,True,anchor='mt')
        self.text((608,104),'欢迎停靠',10,MUTED,anchor='mt')
        self.line([(7,7),(91,23),(236,8)],'#c2a371',2)
        for xx,yy,c in [(24,12,'#b68168'),(58,19,'#98ad9c'),(96,22,'#d3b777'),(134,18,'#7ea7a3'),(171,13,'#b68168')]:
            self.polygon([(xx,yy),(xx+18,yy+1),(xx+10,yy+23)],c)
        # Counter and rug.
        self.rect((0,271,680,320),'#14252e',0)
        self.polygon([(55,293),(605,293),(646,319),(19,319)],'#526565')
        self.line([(56,307),(617,307)],'#89978b',2)
        self.rect((55,218,625,279),'#846a50',7)
        self.rect((55,220,625,233),'#c6a579',4)
        self.rect((71,237,609,272),'#4c5550',3)
        for xx in [206,387]:self.line([(xx,238),(xx,269)],'#a48864',2)
        self.rect((268,242,410,267),'#243c43',4)
        self.text((339,249),'每件旧物，都有新故事',11,GOLD,anchor='mt')
        # Friendly assistant robot and small till; no fabricated game characters.
        self.item_art(540,147,85,{'kind':'bot','color':'#92b6a5'})
        self.rect((466,189,513,220),'#788e87',6)
        self.rect((473,195,506,209),'#29474b',2)
        self.line([(479,201),(499,201)],GOLD,2)
        event=as_dict(o.get('last_event'))
        item=event.get('item')
        inventory=as_list(o.get('inventory'))
        collection=as_list(o.get('collection'))
        item = as_dict(item) or (as_dict(inventory[-1]) if inventory else {}) or (as_dict(collection[-1]) if collection else {})
        self.ellipse((273,207,392,224),'#50645f')
        self.item_art(284,103+math.sin(frame*.8)*2,112,item,crate=not bool(item))
        self.star(277,143,7,GOLD);self.star(407,124,5,TEAL)
        self.star(391,184,4,GOLD)
        scene=self.image.resize((round(w),round(h)),Image.Resampling.LANCZOS)
        self.image,self.draw=old_image,old_draw
        mask=Image.new('L',scene.size,0)
        ImageDraw.Draw(mask).rounded_rectangle((0,0,w-1,h-1),radius=18,fill=255)
        self.image.paste(scene,(round(x),round(y)),mask)

    def header(self, o, wide):
        right=self.W-32
        self.text((32,25),'演示数据 · 不是真实游玩' if self.demo else ('STARDUST CURIOS' if self.W<600 else 'STARDUST CURIOS  /  星港第 07 号泊位'),15,GOLD if self.demo else MUTED,True)
        self.text((30,54),'星屑杂货铺',40 if self.W<600 else 46,INK,True)
        self.pill((right-121 if self.W<600 else right-144,25 if self.W<600 else 30),'只读观战',TEAL,16 if self.W<600 else 19)
        self.text((right,86),f"第 {int(number(o.get('day'),1))} 天",27,GOLD,True,anchor='rt')
        if wide:self.text((360,78),'旧物生意 · 新的故事',21,MUTED)

    def metrics(self, box, o):
        x,y,w,h=box
        self.rect((x,y,x+w,y+h),PANEL,18)
        specs=[('可用星币',f"{int(number(o.get('credits'))):,}",GOLD),
               ('今日体力',f"{int(number(o.get('energy')))}/{int(number(o.get('max_energy')))}",TEAL),
               ('小店声望',f"{int(number(o.get('reputation')))}",LILAC)]
        for i,(label,value,color) in enumerate(specs):
            xx=x+22+i*w/3
            if i:self.line([(xx-15,y+19),(xx-15,y+h-19)],LINE,1)
            self.text((xx,y+16),label,18,MUTED)
            self.text((xx,y+43),value,34,color,True)

    def stage_model(self, o):
        campaign=as_dict(o.get('campaign'))
        stage=as_dict(campaign.get('next_milestone'))
        goals=[as_dict(g) for g in as_list(stage.get('goals'))]
        return {'title':stage.get('title','等待公开阶段目标'),'goals':goals,'campaign':campaign}

    def goal_card(self, box, o):
        x,y,w,h=box
        self.rect((x,y,x+w,y+h),'#233c3e',17, '#466057')
        g=self.stage_model(o)
        summary=o.get('phase')=='week_summary'
        self.text((x+18,y+13),'首周结算' if summary else '下一站',16,TEAL,True)
        stage=as_dict(as_dict(o.get('campaign')).get('next_milestone'))
        deadline=public_deadline(stage)
        label=deadline_summary(stage) if deadline.get('effective_due_day') is not None else '可以继续经营' if summary else '长期经营'
        self.text((x+w-18,y+13),label,15,RED if deadline.get('overdue_days') else GOLD if summary else MUTED,False,w-122,anchor='rt')
        self.text((x+18,y+41),g['title'],24,INK,True,w-36)
        goals=g['goals']
        # The public campaign owns all milestone calculations, including reputation.
        pieces=[f"{v.get('label','目标')} {int(number(v.get('current'))):,}/{int(number(v.get('target'))):,}" for v in goals]
        if len(pieces)>4:
            for i,piece in enumerate(pieces[:6]):
                self.text((x+18+(i%2)*(w-36)/2,y+67+(i//2)*17),piece,14,GOLD,False,(w-42)/2)
        elif len(pieces)>2:
            for i,piece in enumerate(pieces[:4]):
                self.text((x+18+(i%2)*(w-36)/2,y+74+(i//2)*22),piece,16,GOLD,False,(w-42)/2)
        else:self.text((x+18,y+79),'  ·  '.join(pieces),18,GOLD,False,w-36)
        fractions=[number(v.get('current'))/max(1,number(v.get('target'),1)) for v in goals]
        self.progress(x+18,y+h-(7 if len(pieces)>4 else 12 if len(pieces)>2 else 20),w-36,min(fractions) if fractions else 1,TEAL,h=5)
        if deadline.get('effective_due_day') is not None:
            self.hits.append(((x,y,x+w,y+h),('inspect',public_management_detail(o,'deadlines'))))

    def event_card(self, box, o):
        x,y,w,h=box
        self.rect((x,y,x+w,y+h),PANEL,18)
        event=as_dict(o.get('last_event'))
        self.pill((x+18,y+16),'店里刚刚发生',GOLD,16,'#463d2d')
        self.text((x+w-18,y+22),f"DAY {int(number(o.get('day'),1)):02}",15,MUTED,anchor='rt')
        title_y=58 if h<170 else 61
        body_y=96 if h<170 else 104
        body_size=18 if h<170 else 20
        previous_roll=public_roll(o.get('last_roll'))
        body_height=h-(34 if previous_roll else 0)
        self.text((x+18,y+title_y),event.get('title') or '新的旅程开门了',26,INK,True,w-36)
        self.text((x+18,y+body_y),event.get('text') or '一盏暖灯，一只货箱。等待店长的第一笔生意。',body_size,MUTED,False,w-36,max(1,1+int((body_height-body_y-10-body_size)/(body_size*1.3))))

        self.hits.append(((x,y,x+w,y+h),('inspect',dict(name=event.get('title','店里刚刚发生'),description=event.get('text','')))))
        if previous_roll:
            label,color=roll_status(previous_roll)
            if previous_roll.get('stage')=='initial' and previous_roll.get('outcome')=='failure':label='初次报价未达标'
            rules='低骰' if percentile_rules(previous_roll) else '规则不受支持'
            self.text((x+18,y+h-28),f'上次 {roll_summary(previous_roll)} · {label} · {rules} · 查看记录 ›',15,color,False,w-36)
            self.hits.append(((x,y+h-40,x+w,y+h),('show_rolls',None)))


    def roll_art(self, x, y, size, roll, color=GOLD):
        """The two recorded D10 faces, followed by their recorded D100 result."""
        if not percentile_rules(roll):
            self.text((x+size/2,y+size/3),'?',size*.4,MUTED,True,anchor='mt')
            return
        roll=public_roll(roll)
        for index,key in enumerate(('tens','ones')):
            xx=x+index*size*.53;ww=size*.47;hh=size*.65
            points=[(xx+ww/2,y),(xx+ww,y+hh*.3),(xx+ww*.8,y+hh*.85),
                    (xx+ww/2,y+hh),(xx+ww*.2,y+hh*.85),(xx,y+hh*.3)]
            self.polygon(points,'#172e3b',color)
            self.line(points+[points[0]],color,2)
            digit=roll.get(key)
            face='?' if digit is None else (f'{digit:02d}' if key=='tens' else str(digit))
            self.text((xx+ww/2,y+hh*.19),face,max(15,size*.24),color,True,anchor='mt')
            self.text((xx+ww/2,y+hh*.67),'十位' if index==0 else '个位',max(10,size*.1),MUTED,anchor='mt')
        self.text((x+size/2,y+size*.74),roll_summary(roll),max(12,size*.15),color,True,anchor='mt')

    def bargaining_card(self, box, o, *, details=False):
        x,y,w,h=box
        pending=public_negotiation(o.get('negotiation'))
        roll=public_roll(o.get('last_roll') or as_dict(o.get('last_event')).get('roll'))
        preview=as_dict(pending.get('preview'));bounds=as_dict(pending.get('final_offer_bounds'))
        percentile=percentile_preview(preview)
        if pending.get('_unsupported_rules'):
            self.rect((x,y,x+w,y+h),'#20353e',18,MUTED,1)
            self.text((x+18,y+30),'不支持此议价版本 · 仅支持原生 v10',22,MUTED,True,w-36,2)
            return
        offer=int(number(pending.get('counter_offer')))
        accept=int(number(pending.get('accept_income'),offer))
        self.rect((x,y,x+w,y+h),'#20353e',18,LILAC,1)
        self.text((x+18,y+15),'还价中 · 最后一次报价',23,LILAC,True,w-170)
        if not details:self.text((x+w-16,y+21),'查看骰子记录 ›',14,MUTED,anchor='rt')
        who=' · '.join(str(v) for v in (pending.get('customer_name'),pending.get('item_name')) if v)
        header_width=w-151 if percentile_rules(roll) else w-36
        self.text((x+18,y+52),who or '待店主决定 · 只剩一次议价',17,INK,False,header_width)
        self.text((x+18,y+79),f'标价 {int(number(pending.get("original_price"))):,} → 还价 {offer:,}',21,GOLD,True,header_width)
        self.text((x+18,y+110),f'接受：收入 {accept:,} 星币 · 免费',18,TEAL,True,header_width)
        if percentile_rules(roll):self.roll_art(x+w-114,y+47,94,roll,RED)
        self.line([(x+18,y+141),(x+w-18,y+141)],LINE,1)
        if percentile:
            base,threshold=percentile;price=int(number(preview.get('price')))
            example=preview.get('suggested')
            if example is None:example=price==number(bounds.get('min'),None)
            suffix='最低价示例' if example else '尚未掷骰'
            self.text((x+18,y+152),f'拟报价 {price:,} 星币 · {suffix}',21,GOLD,True,w-36)
            self.text((x+18,y+186),percentile_chance_text(threshold),19,INK,True,w-36)
            premium=number(preview.get('premium'),None)
            premium_text=f' · 溢价 {premium*100:g}%' if premium is not None else ''
            self.text((x+18,y+215),f'基础 {base}%{premium_text} · 双 D10',16,MUTED,False,w-36)
            self.text((x+18,y+240),'01 必成（1%）· 100 必败（1%）',16,GOLD,False,w-36)
            energy=number(preview.get('energy_cost'),number(pending.get('final_offer_energy'),1))
            income=int(number(preview.get('success_income'),price))
            self.text((x+18,y+267),f'再报价：{energy:g} 体力 · 成功收入 {income:,}',17,INK,False,w-36)
            self.text((x+18,y+294),f'失败收入 0 · 失去 {offer:,} 星币还价',17,RED,True,w-36)
            self.text((x+18,y+h-24),'公开还价精确预览 · 越低越好 · 不掷骰',13,MUTED,False,w-36)
        elif bounds.get('available') is False:
            self.text((x+18,y+156),'没有合法的最终报价',22,RED,True,w-36)
            self.text((x+18,y+194),'报价须高于还价，并低于初次标价',18,INK,False,w-36)
            self.text((x+18,y+226),'可以接受还价，或免费谢绝',18,MUTED,False,w-36)
            self.text((x+18,y+h-27),'只读观战 · 不会替店主作决定',14,MUTED,False,w-36)
        else:
            self.text((x+18,y+156),'等待公开报价预览',22,GOLD,True,w-36)
            self.text((x+18,y+194),'公开数据不足，暂不推算骰点或难度',17,MUTED,False,w-36)
            self.text((x+18,y+232),f'再报价：{number(pending.get("final_offer_energy"),1):g} 体力',18,INK,False,w-36)
            self.text((x+18,y+267),f'失败收入 0 · 失去 {offer:,} 星币还价',17,RED,True,w-36)
        if not details:
            self.hits.append(((x,y,x+w,y+h),('inspect',dict(_view='negotiation',negotiation=pending,last_roll=roll))))
            self.hits.append(((x+w-153,y+5,x+w,y+47),('show_rolls',None)))

    def bargaining_detail(self, source):
        overlay=Image.new('RGBA',self.image.size,(6,16,24,220))
        self.image=Image.alpha_composite(self.image.convert('RGBA'),overlay).convert('RGB');self.draw=ImageDraw.Draw(self.image)
        w=min(self.W-40,710);h=min(self.H-80,800);x=(self.W-w)/2;y=(self.H-h)/2
        self.rect((x,y,x+w,y+h),'#263d45',25,LILAC,2)
        self.hits=[((0,0,self.W,self.H),('close',None))]
        self.text((x+22,y+24),'掷骰前 · 报价预览',20,TEAL,True,w-140)
        self.text((x+w-22,y+27),'点击返回 ×',16,MUTED,anchor='rt')
        self.bargaining_card((x+12,y+63,w-24,344),source,details=True)
        pending=public_negotiation(source.get('negotiation'));preview=as_dict(pending.get('preview'))
        if pending.get('_unsupported_rules'):
            return
        bounds=as_dict(pending.get('final_offer_bounds'))
        if bounds.get('available') is True:
            self.text((x+27,y+429),f'合法最终报价：{int(number(bounds.get("min"))):,}–{int(number(bounds.get("max"))):,} 星币',18,INK,True,w-54)
        modifiers=[as_dict(v) for v in as_list(preview.get('modifiers'))]
        unit='百分点'
        pieces=[f'{v.get("label", "修正")} {number(v.get("value")):+g}{unit}' for v in modifiers]
        self.text((x+27,y+466),f'冻结加值 {number(preview.get("modifier")):+g}{unit} · ' + (' · '.join(pieces) or '没有公开修正项'),17,MUTED,False,w-54,2)
        fallback='基于公开还价的精确几率；最终失败收入0，不能回头接受旧还价。'
        self.text((x+27,y+525),preview.get('warning') or fallback,17,MUTED,False,w-54,3)
        self.text((x+27,y+599),'CoC 启发的简化房规，并非完整官方规则',15,MUTED,False,w-54)
        roll=public_roll(source.get('last_roll'))
        self.text((x+27,y+632),'上次已判定 · 初次报价',17,LILAC,True,w-54)
        self.text((x+27,y+663),roll_math(roll),18,INK,False,w-54)
        self.text((x+27,y+h-47),'接受 / 谢绝免费；最后报价消耗 1 体力',16,MUTED,False,w-54)
        self.text((x+27,y+h-25),'只读预览 · 不会掷骰或完成交易',14,MUTED,False,w-54)

    def dice_card(self, box, o):
        if has_bargaining_preview(o.get('negotiation')):
            return self.bargaining_card(box,o)
        x,y,w,h=box
        roll=public_roll(o.get('last_roll') or as_dict(o.get('last_event')).get('roll'))
        label,color=roll_status(roll)
        self.rect((x,y,x+w,y+h),'#20353e',18,color,1)
        self.pill((x+16,y+12),roll_rules_label(roll)+(' · 演示' if self.demo else ''),color,15,'#30444b',10)
        self.text((x+w-16,y+20),'查看骰子记录 ›',14,MUTED,anchor='rt')
        if roll.get('_unsupported_rules'):
            self.text((x+18,y+76),'不支持的骰子记录',24,MUTED,True,w-36)
            return
        self.roll_art(x+15,y+54,114,roll,color)
        tx=x+147;tw=w-163
        self.text((tx,y+55),label,28,color,True,tw)
        who=' · '.join(str(v) for v in (roll.get('customer_name'),roll.get('item_name')) if v)
        self.text((tx,y+99),who or '等待下一笔生意的公开判定',16,INK,False,tw)
        price=int(number(roll.get('price')))
        sold=roll.get('outcome') in ('miracle','success')
        self.text((tx,y+130),f'{"成交" if sold else "公开报价"} {price:,} 星币',23,GOLD if sold else INK,True,tw)
        message='再高的报价，也有奇迹时刻' if roll.get('outcome')=='miracle' else '旅客带着新故事离开' if sold else '本次交易未成'
        if has_roll_breakdown(roll):
            self.text((x+18,y+167),chance_breakdown(roll),17,INK,True,w-36)
            self.text((x+18,y+195),percentile_chance_text(roll.get('threshold')),16,MUTED,False,w-36)
        else:self.text((tx,y+166),message,17,MUTED,False,tw)
        self.text((x+18,y+h-27),roll_math(roll),15,MUTED,False,w-36)
        self.hits.append(((x,y,x+w,y+h),('inspect',dict(roll,_view='roll',negotiation={}))))
        self.hits.append(((x+w-153,y+5,x+w,y+47),('show_rolls',None)))

    def current_event(self, box, o):
        event=as_dict(o.get('last_event'))
        # Accept/decline, a new day and later shop actions do not roll again.
        # Keep the actual latest event visible rather than treating the old face
        # as a new result or calling an accepted counter-offer a failed sale.
        if as_dict(event.get('roll')) or as_dict(o.get('negotiation')) or (as_dict(o.get('last_roll')) and not event.get('type')):
            self.dice_card(box,o)
        else:self.event_card(box,o)

    def demand_strip(self, box, o):
        x,y,w,h=box
        demand=as_dict(o.get('demand'))
        daily=as_dict(o.get('daily_event')) or as_dict(o.get('active_event'))
        label=demand.get('label') or '行情平稳'
        self.star(x+11,y+17,6,TEAL)
        self.text((x+27,y+6),f'今日行情  ·  {label}',19,TEAL,False,w-27)
        if as_dict(o.get('walkins')):
            self.text((x+2,y+37),walkins_summary(o.get('walkins'))+' · 查看来客 ›',17,MUTED,False,w-4)
            self.hits.append(((x,y+30,x+w,y+h),('tab','visitors')))
        elif daily:
            label=daily.get('title') or daily.get('name') or daily.get('text','')
            self.text((x+2,y+37),f'星港传闻  {label}',18,MUTED,False,w-4)
            self.hits.append(((x,y+30,x+w,y+h),('inspect',dict(daily,name=label))))

    def tab_bar(self, box):
        x,y,w,h=box
        tabw=w/len(TABS)
        self.rect((x,y,x+w,y+h),'#162731',15)
        for i,(key,label) in enumerate(TABS):
            left=x+i*tabw
            if key==self.tab:self.rect((left+4,y+4,left+tabw-4,y+h-4),'#405950',11)
            self.text((left+tabw/2,y+16),label,18,INK if key==self.tab else MUTED,key==self.tab,anchor='mt')
            self.hits.append(((left,y,left+tabw,y+h),('tab',key)))

    def items(self, box, o, collection=False):
        x,y,w,h=box
        items=as_list(o.get('collection' if collection else 'inventory'))
        capacity=o.get('capacity',len(items))
        forecasts=not collection
        title='私藏的星光' if collection else ('旧物货架 · 点击查看售前条件' if forecasts else '正在等待新主人的旧物')
        self.text((x+2,y+6),title,22,INK,True)
        extra=f'{len(items)} 件珍藏' if collection else f'{len(items)} / {capacity} 件'
        self.text((x+w-2,y+10),extra,17,MUTED,anchor='rt')
        row_h=96 if h>335 else 88
        per_page=max(1,int((h-85)//row_h))
        pages=max(1,math.ceil(len(items)/per_page)); page=self.page%pages
        self.page_count=pages
        visible=items[page*per_page:(page+1)*per_page]
        if not visible:
            self.rect((x,y+46,x+w,y+h-38),PANEL,18)
            self.item_art(x+w/2-38,y+61,76,crate=not collection)
            empty_y=y+145 if h>=220 else y+61
            if h<220:self.rect((x,y+46,x+w,y+h-38),PANEL,18)
            self.text((x+w/2,empty_y),'每件旧物，都值得被好好发现' if collection else '货架空着，星港的货箱正在等你',19,MUTED,False,w-36,2,anchor='mt')
        for i,item in enumerate(visible):
            item=as_dict(item);yy=y+45+i*row_h
            rarity,col=RARITIES.get(item.get('rarity'),RARITIES['common'])
            self.rect((x,yy,x+w,yy+row_h-9),PANEL,14)
            self.rect((x+8,yy+8,x+row_h-18,yy+row_h-17),'#2a4148',12)
            self.item_art(x+12,yy+10,row_h-33,item)
            tx=x+row_h-4
            price=item.get('price')
            estimate=as_list(item.get('value_estimate'))
            price_text='已珍藏' if collection else (f'{int(number(price))} 星币' if price is not None else (f'{estimate[0]}–{estimate[-1]}' if len(estimate)>1 else '尚未标价'))
            reserve=max(105,font(19,True).getlength(price_text)+22)
            self.text((tx,yy+12),item.get('name') or '未命名旧物',23,INK,True,w-(tx-x)-reserve-12)
            self.text((x+w-16,yy+15),price_text,19,GOLD,True,anchor='rt')
            detail=f"{rarity} · {KINDS.get(item.get('kind'),'旧物')}"
            if not collection:detail+=(' · 还价中' if item.get('negotiating') else f" · 品相 {int(number(item.get('condition')))}%")
            if forecasts and not item.get('negotiating'):
                ordinary=next((public_sale_option(v) for v in as_list(item.get('sale_options'))
                               if as_dict(v) and v.get('customer_id') is None),{})
                status,status_color=sale_status(ordinary)
                detail=f"品相 {int(number(item.get('condition')))}% · 散客：{status}"
                col=status_color
            self.text((tx,yy+48),detail,16,col,False,w-(tx-x)-20)
            display=public_sale_detail(item,o.get('walkins')) if forecasts else item
            self.hits.append(((x,yy,x+w,yy+row_h-9),('inspect',display)))
        self.pagination((x,y+h-30,w,30), page, pages)

    def pagination(self, box, page, pages):
        x,y,w,h=box
        if pages>1:
            self.text((x+w/2,y+2),f'{page+1} / {pages}  ·  点击两侧翻页',16,MUTED,anchor='mt')
            self.text((x+16,y),'‹',25,GOLD,True)
            self.text((x+w-16,y),'›',25,GOLD,True,anchor='rt')
            self.hits += [((x,y-5,x+w*.28,y+h),('page',-1)),((x+w*.72,y-5,x+w,y+h),('page',1))]
        else:self.text((x+w/2,y+2),'只翻看展台 · 不会改变游戏',15,MUTED,anchor='mt')

    def growth(self, box, o):
        x,y,w,h=box
        self.text((x+2,y+5),'把小店慢慢变成梦想的样子',22,INK,True,w-4)
        upgrades=o.get('upgrades',{})
        costs=as_dict(o.get('upgrade_costs'))
        if isinstance(upgrades,dict): entries=[dict(id=k,level=v) if not isinstance(v,dict) else dict(v,id=k) for k,v in upgrades.items()]
        else:entries=[as_dict(v) for v in as_list(upgrades)]
        if as_list(o.get('upgrade_details')):entries=[as_dict(e) for e in o['upgrade_details']]
        if not entries:entries=[{'id':'workbench','level':0},{'id':'shelf','level':0}]
        entries += [dict(as_dict(e),is_set=True) for e in as_list(o.get('collection_sets'))]
        management=[]
        costs_public=public_cost_breakdown(o.get('operating_cost_breakdown'))
        n=collection_number
        if costs_public:
            management.append(dict(_management='costs',name=f"闭店费用 · {n(costs_public.get('total'))} 星币",
                                   description=f"今日设施 {n(costs_public.get('facility_upkeep'))} · 第8天起 {n(costs_public.get('facility_upkeep_from_day8'))}/日 · 逾期 {n(costs_public.get('overdue_surcharge'))}"))
        stage=as_dict(as_dict(o.get('campaign')).get('next_milestone'))
        if public_deadline(stage).get('effective_due_day') is not None:
            management.append(dict(_management='deadlines',name='阶段期限与迟到记录',description=deadline_summary(stage)))
        suppliers=[public_supplier(v) for v in as_list(o.get('suppliers'))]
        focused=next((v for v in suppliers if v.get('id')=='focused'),{})
        if focused:
            management.append(dict(_management='suppliers',name='分类采购 · 查看公开货源',
                                   description=f"{n(focused.get('cost'))} 星币 · {n(focused.get('energy_cost'))} 精力 · 今日余 {n(focused.get('remaining'))} 箱"))
        entries=management+entries
        per_page=max(1,int((h-80)/87)); pages=max(1,math.ceil(len(entries)/per_page)); page=self.page%pages
        self.page_count=pages
        for i,item in enumerate(entries[page*per_page:(page+1)*per_page]):
            yy=y+46+i*87;key=item.get('id',''); level=int(number(item.get('level')))
            self.rect((x,yy,x+w,yy+78),PANEL,14)
            if item.get('_management'):
                self.text((x+17,yy+11),item['name'],22,INK,True,w-45)
                self.text((x+17,yy+45),item['description'],16,GOLD,False,w-34)
                self.text((x+w-14,yy+12),'›',24,TEAL,True,anchor='rt')
                self.hits.append(((x,yy,x+w,yy+78),('inspect',public_management_detail(o,item['_management']))))
                continue
            self.item_art(x+10,yy+10,58,{'kind':'tool' if key=='workbench' else 'artifact','color':TEAL if level else '#728884'})
            self.text((x+82,yy+12),item.get('name') or UPGRADES.get(key,key or '小店设施'),22,INK,True,w-220)
            cost=item.get('next_cost',costs.get(key))
            desc=item.get('effect') or item.get('description') or (f'下次升级 {cost} 星币' if cost is not None else '店铺设施')
            badge=f"{item.get('current',0)}/{item.get('required',3)}" if item.get('is_set') else f'Lv.{level}'
            self.text((x+82,yy+45),desc,16,MUTED,False,w-98)
            self.pill((x+w-94,yy+13),badge,GOLD,17,'#463d2d',11)
            upkeep=''
            if not item.get('is_set') and 'daily_upkeep' in item:
                upkeep=f"；今日设施费 {n(public_integer(item.get('daily_upkeep'),0,10**9))} 星币/日，第8天起 {n(public_integer(item.get('daily_upkeep_from_day8'),0,10**9))} 星币/日"
                if item.get('next_daily_upkeep_from_day8') is not None:
                    upkeep+=f"；升级后今日 {n(public_integer(item.get('next_daily_upkeep'),0,10**9))}、第8天起 {n(public_integer(item.get('next_daily_upkeep_from_day8'),0,10**9))} 星币/日"
            details={key:item.get(key) for key in ('id','name','kind','color')}
            details['description']=(item.get('description') or item.get('effect','')) + (f"；下一次：{item.get('next_effect')}（{cost} 星币）" if cost is not None and item.get('next_effect') else '')+upkeep
            self.hits.append(((x,yy,x+w,yy+78),('inspect',details)))
        self.pagination((x,y+h-28,w,28),page,pages)

    def journal(self, box, o):
        x,y,w,h=box
        self.text((x+2,y+5),'骰子记录' if self.journal_mode=='rolls' else '每一笔生意，都是一段航行',22,INK,True,w-151)
        other='经营事件 ›' if self.journal_mode=='rolls' else '最近骰子 ›'
        self.pill((x+w-141,y),other,TEAL,16,'#294441',12)
        self.hits.append(((x+w-150,y,x+w,y+42),('journal_mode','events' if self.journal_mode=='rolls' else 'rolls')))
        if self.journal_mode=='rolls':
            return self.roll_history((x,y+48,w,h-48),o)
        logs=list(reversed(as_list(o.get('log'))))
        per_page=max(1,int((h-80)/91));pages=max(1,math.ceil(len(logs)/per_page));page=self.page%pages
        self.page_count=pages
        for i,entry in enumerate(logs[page*per_page:(page+1)*per_page]):
            log=entry if isinstance(entry,dict) else {'text':str(entry)}; yy=y+49+i*91
            self.ellipse((x+4,yy+8,x+12,yy+16),GOLD if i==0 and page==0 else '#64827e')
            if i<per_page-1:self.line([(x+8,yy+24),(x+8,yy+84)],LINE,1)
            self.text((x+27,yy),f"第 {log.get('day','?')} 天",15,GOLD if i==0 else MUTED)
            self.text((x+27,yy+25),log.get('text',''),18,INK,False,w-34,2)
            self.hits.append(((x,yy,x+w,yy+86),('inspect',dict(name=f"第 {log.get('day','?')} 天 · 经营事件",description=log.get('text','')))))
        if not logs:self.text((x+15,y+70),'等第一位客人推开小店的门',21,MUTED)
        self.pagination((x,y+h-28,w,28),page,pages)

    def roll_history(self, box, o):
        x,y,w,h=box
        rolls=[public_roll(v) for v in reversed(as_list(o.get('roll_history'))) if as_dict(v)]
        if not rolls and as_dict(o.get('last_roll')):rolls=[public_roll(o['last_roll'])]
        rowh=105
        per_page=max(1,int((h-32)/rowh));pages=max(1,math.ceil(len(rolls)/per_page));page=self.page%pages;self.page_count=pages
        for i,roll in enumerate(rolls[page*per_page:(page+1)*per_page]):
            yy=y+i*rowh;label,color=roll_status(roll)
            self.rect((x,yy,x+w,yy+rowh-8),PANEL,14)
            self.roll_art(x+9,yy+12,68,roll,color)
            tx=x+90
            self.text((tx,yy+10),label,21,color,True,w-190)
            stage='最终议价' if roll.get('stage')=='final' else '初次报价'
            self.text((x+w-13,yy+14),f'第 {int(number(roll.get("day"),1))} 天',14,MUTED,anchor='rt')
            rules='v10 低骰' if percentile_rules(roll) else roll_rules_label(roll)
            self.text((tx,yy+43),f'{rules} · {stage} · {roll.get("customer_name") or "旅客"} · {roll.get("item_name") or "旧物"}',15,INK,False,w-105)
            self.text((tx,yy+70),roll_math(roll),14,MUTED,False,w-105)
            self.hits.append(((x,yy,x+w,yy+rowh-8),('inspect',dict(roll,_view='roll'))))
        if not rolls:
            self.text((x+16,y+16),'还没有公开骰点',23,GOLD,True,w-32)
            self.text((x+16,y+54),'店主下次报价后，真实判定会留在这里',18,MUTED,False,w-32,2)
        self.pagination((x,y+h-27,w,27),page,pages)

    def collection_summary(self, box, progress):
        x,y,w,h=box
        self.rect((x,y,x+w,y+h),'#233c3e',14,'#466057')
        n=collection_number
        self.text((x+14,y+11),f"私藏 {n(progress.get('personal_count'))} 件 · 合格 {n(progress.get('qualified_count'))} 种",20,INK,True,w-28)
        self.text((x+14,y+40),f"合格类别 {n(progress.get('qualified_categories'))} · 品质主题 {n(progress.get('quality_themes'))}",16,TEAL,False,w-28)
        rule=f"本阶段品相 ≥{n(progress.get('min_condition'))}%"
        missing='；'.join(progress.get('missing',[])) or '收藏要求已满足'
        self.text((x+14,y+65),rule+' · '+missing,15,GOLD,False,w-28)
        self.text((x+14,y+88),'查看完整要求、类别与主题 ›',14,MUTED,False,w-28)
        self.hits.append(((x,y,x+w,y+h),('inspect',dict(_view='collection_progress',progress=progress))))

    def collection_progress_detail(self, source):
        progress=public_collection_progress(source.get('progress'))
        overlay=Image.new('RGBA',self.image.size,(6,16,24,225))
        self.image=Image.alpha_composite(self.image.convert('RGBA'),overlay).convert('RGB');self.draw=ImageDraw.Draw(self.image)
        w=min(self.W-40,710);h=810;x=(self.W-w)/2;y=(self.H-h)/2
        self.rect((x,y,x+w,y+h),'#263d45',25,TEAL,2)
        self.hits=[((0,0,self.W,self.H),('close',None))]
        self.text((x+24,y+24),'本阶段收藏要求',24,INK,True,w-150)
        self.text((x+w-22,y+30),'点击返回 ×',16,MUTED,anchor='rt')
        n=collection_number
        self.text((x+24,y+73),f"私藏总数 {n(progress.get('personal_count'))} 件 · 合格收藏 {n(progress.get('qualified_count'))} 种",21,GOLD,True,w-48)
        self.text((x+24,y+109),f"合格类别 {n(progress.get('qualified_categories'))} · 品质主题 {n(progress.get('quality_themes'))}",19,TEAL,False,w-48)
        rule=f"合格收藏：不同种类、品相至少 {n(progress.get('min_condition'))}%。同款重复不增加合格种数。"
        self.text((x+24,y+150),rule,18,INK,False,w-48,3)
        self.text((x+24,y+226),'本阶段需要',18,TEAL,True,w-48)
        requirements=progress.get('requirements',[])
        for i,goal in enumerate(requirements[:3]):
            yy=y+258+i*31
            text=f"{goal.get('label')}  {n(goal.get('current'))}/{n(goal.get('target'))}  · {'已满足' if goal.get('met') else '未满足'}"
            self.text((x+24,yy),text,18,TEAL if goal.get('met') else GOLD,False,w-48)
        if not requirements:self.text((x+24,y+258),'等待公开阶段要求',18,MUTED,False,w-48)
        missing='；'.join(progress.get('missing',[])) or '收藏要求已满足'
        self.text((x+24,y+366),missing,17,GOLD,False,w-48,3)
        self.line([(x+24,y+439),(x+w-24,y+439)],LINE,1)
        self.text((x+24,y+456),'品质主题：同一类别 3 种不同旧物，均达本阶段品相门槛',17,TEAL,True,w-48,2)
        for i,category in enumerate(progress.get('categories',[])[:5]):
            label=f"{category['name']} · 合格 {n(category.get('qualified_count'))} 种 · {'主题完成' if category.get('theme_complete') else '主题未完成'}"
            self.text((x+24,y+512+i*31),label,18,TEAL if category.get('theme_complete') else MUTED,False,w-48)
        self.text((x+24,y+h-99),'普通收藏套装仍按原规则提供经营收益，与阶段品质主题分别计算。',16,MUTED,False,w-48,2)
        self.text((x+24,y+h-40),'只读说明 · 不推进游戏，也不执行收藏或修理',15,MUTED,False,w-48)

    def collection_item_detail(self, source):
        item=public_collection_detail(source,page=source.get('_collection_page',0))
        info=as_dict(item.get('_collection'));items=as_list(info.get('items'))
        count=len(items);page=int(number(item.get('_collection_page')))%max(1,count)
        current=as_dict(items[page]) if items else {}
        overlay=Image.new('RGBA',self.image.size,(6,16,24,225))
        self.image=Image.alpha_composite(self.image.convert('RGBA'),overlay).convert('RGB');self.draw=ImageDraw.Draw(self.image)
        w=min(self.W-40,710);h=820;x=(self.W-w)/2;y=(self.H-h)/2
        self.rect((x,y,x+w,y+h),'#263d45',25,TEAL,2)
        self.hits=[((0,0,self.W,self.H),('close',None))]
        self.text((x+24,y+24),'收藏档案 · 公开品相',21,TEAL,True,w-152)
        self.text((x+w-22,y+29),'点击返回 ×',16,MUTED,anchor='rt')
        self.item_art(x+22,y+65,84,item)
        self.text((x+122,y+75),item.get('name','已发现旧物'),26,INK,True,w-146)
        self.text((x+122,y+117),f"{KINDS.get(item.get('kind'),'旧物')} · {'已珍藏' if item.get('collected') else '已发现'}",18,GOLD,False,w-146)
        self.text((x+24,y+165),item.get('description') or '故事等待继续。',17,MUTED,False,w-48,2)
        self.line([(x+24,y+221),(x+w-24,y+221)],LINE,1)
        if current:
            n=collection_number
            in_cabinet=current.get('location')=='collection'
            label='在柜珍藏' if in_cabinet else '库存同款'
            self.text((x+24,y+242),f"{label} {current.get('id') or '?'} · 品相 {n(current.get('condition'))}%",23,INK,True,w-48)
            quality=as_dict(current.get('collection_quality')) or as_dict(item.get('collection_quality'))
            status='计入本阶段' if quality.get('counted') else '未计入本阶段'
            self.text((x+24,y+282),status,19,TEAL if quality.get('counted') else GOLD,True,w-48)
            self.text((x+24,y+315),quality.get('reason') or '等待公开资格说明',18,MUTED,False,w-48,3)
            repair=as_dict(current.get('repair'))
            self.text((x+24,y+395),'展柜修理' if in_cabinet else '库存修理',18,TEAL,True,w-48)
            repair_status='可修理' if repair.get('available') is True else '暂不可修理' if repair.get('available') is False else '等待公开修理条件'
            self.text((x+24,y+426),f"{repair_status} · {n(repair.get('cost'))} 星币 · {n(repair.get('energy_cost'))} 体力",18,INK,False,w-48)
            self.text((x+24,y+457),'；'.join(repair.get('reasons',[])) or '每件最多 2 次、每天 1 次；沿用现有费用与效果',16,MUTED,False,w-48,2)
            if repair.get('command'):self.text((x+24,y+505),'命令：'+repair['command'],18,GOLD,True,w-48)
            replacement=as_dict(current.get('collection_replacement'))
            self.text((x+24,y+550),'同款替换 · 严格更高品相 · 一进一出',18,TEAL,True,w-48)
            if replacement:
                status='可替换' if replacement.get('available') is True else '暂不可替换'
                desc=f"{status} · 在柜 {replacement.get('cabinet_item_id') or '?'} 为 {n(replacement.get('cabinet_condition'))}% · {n(replacement.get('energy_cost'))} 体力"
                self.text((x+24,y+582),desc,17,INK,False,w-48)
                self.text((x+24,y+613),'；'.join(replacement.get('reasons',[])) or '替换后旧珍藏返回库存，私藏总数不变',16,MUTED,False,w-48,2)
                if replacement.get('command'):self.text((x+24,y+662),'命令：'+replacement['command'],18,GOLD,True,w-48)
            elif in_cabinet:
                candidates=[v for v in items if as_dict(v).get('location')=='inventory']
                eligible=sum(as_dict(v.get('collection_replacement')).get('available') is True for v in candidates)
                self.text((x+24,y+585),f'库存同款 {len(candidates)} 件 · 当前可替换 {eligible} 件',18,INK,False,w-48)
                self.text((x+24,y+619),'翻页查看同款的资格与命令' if candidates else '暂无库存同款；先寻找品相更好的同种旧物',17,MUTED,False,w-48,2)
            else:self.text((x+24,y+585),'暂无同款在柜珍藏，尚不适用替换',17,MUTED,False,w-48,2)
        else:
            self.text((x+24,y+250),'已发现 · 当前未持有',24,GOLD,True,w-48)
            self.text((x+24,y+302),'发现记录会保留；只有进入展柜并满足本阶段条件，才计入合格收藏。',20,MUTED,False,w-48,3)
        if count>1:
            self.text((x+w/2,y+h-83),f'{page+1}/{count} · 逐件查看展柜与库存',16,TEAL,anchor='mt')
            self.text((x+29,y+h-88),'‹',26,GOLD,True)
            self.text((x+w-29,y+h-88),'›',26,GOLD,True,anchor='rt')
            self.hits += [((x+12,y+h-101,x+w*.28,y+h-52),('collection_page',-1)),
                          ((x+w*.72,y+h-101,x+w-12,y+h-52),('collection_page',1))]
        self.text((x+24,y+h-36),'只读命令提示 · 点击不会修理或替换',15,MUTED,False,w-48)


    def codex(self, box, o):
        codex=as_dict(o.get('codex'))
        if not as_list(codex.get('entries')):
            return self.items(box,o,True)
        x,y,w,h=box
        entries=[public_catalog_entry(e, slot) for slot,e in enumerate(codex['entries'], 1)]
        entries.sort(key=lambda e:(not bool(e.get('collected')),not bool(e.get('discovered'))))
        self.text((x+2,y+5),'旧物图鉴',22,INK,True)
        self.text((x+w-2,y+10),f"发现 {codex.get('discovered',0)}/{codex.get('total',len(entries))} · 珍藏 {codex.get('collected',0)}",17,MUTED,anchor='rt')
        progress=public_collection_progress(o.get('collection_progress'))
        start=45
        if progress:
            self.collection_summary((x,y+42,w,114),progress)
            start=166
        per_page=max(1,int((h-start-28)/89));pages=max(1,math.ceil(len(entries)/per_page));page=self.page%pages;self.page_count=pages
        for i,item in enumerate(entries[page*per_page:(page+1)*per_page]):
            yy=y+start+i*89
            found=item.get('discovered');collected=item.get('collected')
            self.rect((x,yy,x+w,yy+80),PANEL,14)
            self.item_art(x+10,yy+9,61,item)
            self.text((x+82,yy+11),item.get('name','???'),21,INK if found else MUTED,True,w-205)
            self.text((x+w-16,yy+15),'已珍藏' if collected else '已发现' if found else '待寻访',17,GOLD if collected else TEAL if found else MUTED,anchor='rt')
            self.text((x+82,yy+43),item.get('description','') if found else '尚未遇见 · 开箱后解锁',16,MUTED,False,w-101)
            self.hits.append(((x,yy,x+w,yy+80),('inspect',public_collection_detail(item,o))))
        self.pagination((x,y+h-28,w,28),page,pages)

    def visitors(self, box, o):
        x,y,w,h=box
        visitors=[as_dict(v) for v in as_list(o.get('visitors'))]
        walkins=public_walkins(o.get('walkins'))
        waiting=sum(v.get('status') in ('waiting','negotiating') for v in visitors)
        if walkins:
            budget=walkins.get('budget_range')
            visitors.insert(0,{'name':'普通散客','_view':'walkins','walkins':walkins,
                              'role':f'公开常规预算 {budget[0]}–{budget[1]} 星币' if budget else '等待公开预算范围',
                              'preference_label':f'还价需品相 ≥{walkins["min_condition"]}%' if walkins.get('min_condition') is not None else '等待公开品相条件',
                              'status':'waiting' if number(walkins.get('remaining'))>0 else 'left'})
        self.text((x+2,y+5),'今天谁推开了店门',22,INK,True,w-120)
        self.text((x+w-2,y+9),f'{waiting} 位专客' if walkins else f'{waiting} 位等候',17,TEAL,anchor='rt')
        per_page=max(1,int((h-64)/109));pages=max(1,math.ceil(len(visitors)/per_page));page=self.page%pages;self.page_count=pages
        for i,v in enumerate(visitors[page*per_page:(page+1)*per_page]):
            yy=y+45+i*109
            self.rect((x,yy,x+w,yy+99),PANEL,14)
            # Illustrated astronaut portrait: decoration, not an extra hidden character.
            self.ellipse((x+14,yy+17,x+76,yy+79),'#c5b797')
            self.ellipse((x+21,yy+25,x+70,yy+65),'#34535a')
            self.ellipse((x+33,yy+40,x+39,yy+46),GOLD);self.ellipse((x+52,yy+40,x+58,yy+46),GOLD)
            self.text((x+93,yy+12),v.get('name','星港旅客'),23,INK,True,w-220)
            status={'waiting':'正在等候','negotiating':'还价中','bought':'满载而归','left':'暂别小店'}.get(v.get('status'),'来店看看')
            if v.get('_view')=='walkins':
                remaining=walkins.get('remaining')
                status=f'今日剩 {remaining} 次' if remaining is not None else '名额待公开'
            self.text((x+w-16,yy+16),status,17,LILAC if v.get('status')=='negotiating' else TEAL if v.get('status')=='waiting' else MUTED,anchor='rt')
            self.text((x+93,yy+45),v.get('role','星港旅客'),16,GOLD,False,w-108)
            self.text((x+93,yy+71),v.get('preference_label',''),16,MUTED,False,w-108)
            budget=as_list(v.get('budget_range'))
            desc=str(v.get('preference_label') or '')+(f"。公开常规预算 {budget[0]}–{budget[-1]} 星币。" if len(budget)>1 else '')
            if len(budget)>1:
                desc+='常规预算是消费舒适度，超出会逐步降低初次成功率；精确预算隐藏。'
            self.hits.append(((x,yy,x+w,yy+99),('inspect',dict(v,description=desc))))
        if not visitors:self.text((x+18,y+65),'门口风铃静静响，下一位旅客还在路上',20,MUTED,False,w-36,2)
        self.pagination((x,y+h-28,w,28),page,pages)

    def detail_card(self, item):
        if item.get('_view')=='codex' or item.get('discovered') is False:
            if item.get('discovered') is True and as_dict(item.get('_collection')):
                return self.collection_item_detail(item)
            item=public_catalog_entry(item)
        if item.get('_view')=='collection_progress':return self.collection_progress_detail(item)
        if item.get('_view')=='roll':return self.roll_detail(item)
        if item.get('_view')=='negotiation':return self.bargaining_detail(item)
        if item.get('_view')=='sale':return self.sale_detail(item)
        if item.get('_view')=='walkins':return self.walkins_detail(item)
        if item.get('_view')=='management':return self.management_detail(item)
        overlay=Image.new('RGBA',self.image.size,(6,16,24,210))
        self.image=Image.alpha_composite(self.image.convert('RGBA'),overlay).convert('RGB')
        self.draw=ImageDraw.Draw(self.image)
        w=min(self.W-76,670);h=474;x=(self.W-w)/2;y=(self.H-h)/2
        self.rect((x,y,x+w,y+h),'#263d45',25,'#7f9989',2)
        self.hits=[((0,0,self.W,self.H),('close',None))]
        self.text((x+28,y+24),'旧物档案',19,TEAL,True)
        self.text((x+w-28,y+24),'点击任意处返回 ×',17,MUTED,anchor='rt')
        self.item_art(x+w/2-64,y+71,128,item)
        unknown=item.get('discovered') is False
        self.text((x+w/2,y+220),'???' if unknown else item.get('name','小店档案'),32,INK,True,w-50,1,anchor='mt')
        self.text((x+31,y+284),'尚未遇见。亲手开箱后，才会在这里留下画像和故事。' if unknown else item.get('description') or '这件旧物的故事，还在慢慢展开。',23,MUTED,False,w-62,5)

    def management_detail(self, source):
        """Paginated public explanations; no management action is exposed."""
        data=public_management_detail(source,source.get('_section'),source.get('_management_page'))
        section=data['_section'];n=collection_number
        overlay=Image.new('RGBA',self.image.size,(6,16,24,225))
        self.image=Image.alpha_composite(self.image.convert('RGBA'),overlay).convert('RGB');self.draw=ImageDraw.Draw(self.image)
        w=min(self.W-40,710);h=860;x=(self.W-w)/2;y=(self.H-h)/2
        self.rect((x,y,x+w,y+h),'#263d45',25,TEAL,2)
        self.hits=[((0,0,self.W,self.H),('close',None))]
        title={'costs':'闭店费用明细','deadlines':'阶段期限与记录','suppliers':'公开采购货源'}[section]
        self.text((x+24,y+24),title,24,INK,True,w-162)
        self.text((x+w-22,y+30),'点击返回 ×',16,MUTED,anchor='rt')
        page=data['_management_page'];pages=1
        if section=='costs':
            costs=data['operating_cost_breakdown']
            caption='本次闭店应付' if data.get('phase')=='active' else '当前规则费用参考'
            self.text((x+24,y+85),f"{caption} {n(costs.get('total'))} 星币",26,GOLD,True,w-48)
            labels=(('基础营业费','base'),('港口事件调整','event_delta'),('植物套装减免','plant_discount'),
                    ('调整后营业费','base_after_modifiers'),('今日设施养护','facility_upkeep'),('当前阶段逾期费','overdue_surcharge'))
            for i,(label,key) in enumerate(labels):
                value=costs.get(key)
                amount=f'{value:+d}' if key=='event_delta' and value is not None else f'−{value}' if key=='plant_discount' and value is not None else n(value)
                self.text((x+24,y+136+i*30),f'{label}  {amount} 星币',19,TEAL if key=='base_after_modifiers' else MUTED,False,w-48)
            self.line([(x+24,y+327),(x+w-24,y+327)],LINE,1)
            self.text((x+24,y+343),'设施：今日 / 第8天起 / 升级后第8天起',17,TEAL,True,w-48)
            for i,row in enumerate(data['upgrade_details'][:3]):
                next_fee=n(row.get('next_daily_upkeep_from_day8')) if row.get('next_daily_upkeep_from_day8') is not None else '已满级'
                self.text((x+24,y+377+i*28),f"{row['name']}  {n(row.get('daily_upkeep'))} / {n(row.get('daily_upkeep_from_day8'))} / {next_fee}",18,INK,False,w-48)
            self.text((x+24,y+474),f"第8天起，现有设施合计 {n(costs.get('facility_upkeep_from_day8'))} 星币/日",19,GOLD,True,w-48)
            self.text((x+24,y+510),'首周无设施费；之后设施合计最高12/日。逾期费只计当前阶段，最高6/日。',17,MUTED,False,w-48,2)
            self.text((x+24,y+568),'闭店先支付当日费用，再以扣款后现金判定阶段目标。当前预估会随设施与事件变化。',18,INK,False,w-48,3)
            paid=as_dict(data['last_settlement'])
            if paid:
                self.text((x+24,y+653),f"最近已结算：第 {n(paid.get('day'))} 天 · 已支付 {n(paid.get('paid'))} 星币",19,TEAL,True,w-48,2)
                self.text((x+24,y+709),f"扣款后现金 {n(paid.get('credits_after_payment'))} 星币",18,INK,False,w-48)
                previous=as_dict(paid.get('breakdown'))
                self.text((x+24,y+748),f"当次调整后营业 {n(previous.get('base_after_modifiers'))} + 设施 {n(previous.get('facility_upkeep'))} + 逾期 {n(previous.get('overdue_surcharge'))}",16,MUTED,False,w-48,2)
            else:self.text((x+24,y+661),'尚无已支付的闭店结算',19,MUTED,False,w-48)
        elif section=='deadlines':
            stage=data['campaign']['next_milestone']
            self.text((x+24,y+86),stage.get('title') or '等待公开阶段',26,INK,True,w-48,2)
            self.text((x+24,y+164),deadline_summary(stage),22,RED if stage.get('overdue_days') else GOLD,True,w-48)
            self.text((x+24,y+207),f"计划期限 第 {n(stage.get('nominal_due_day'))} 天 · 实际期限 第 {n(stage.get('effective_due_day'))} 天",18,MUTED,False,w-48,2)
            self.text((x+24,y+261),f"第 {n(stage.get('unlocked_day'))} 天解锁 · 当前逾期费 {n(stage.get('overdue_surcharge'))} 星币/日",18,INK,False,w-48,2)
            self.text((x+24,y+315),'后续阶段解锁后至少留7天；逾期仍可补齐。只计当前阶段逾期费，旧阶段迟到记录保留。',18,MUTED,False,w-48,3)
            self.text((x+24,y+399),'闭店扣费后才判定达标；先前扣过的逾期费不会随阶段完成退回。',17,GOLD,False,w-48,2)
            self.text((x+24,y+461),'阶段历史',20,TEAL,True,w-48)
            history=list(reversed(data['campaign']['deadline_history']))
            pages=max(1,math.ceil(len(history)/4));page%=pages
            statuses={'active':'进行中','missed':'期限已错过','completed':'按期完成','completed_late':'迟到后完成'}
            for i,row in enumerate(history[page*4:(page+1)*4]):
                yy=y+501+i*70
                self.text((x+24,yy),row.get('title') or '公开阶段',18,INK,True,w-48)
                missed=f"错过 {row['missed_day']}" if row.get('missed_day') is not None else '未错过期限'
                completed=f"完成 {row['completed_day']}" if row.get('completed_day') is not None else '尚未完成'
                timing=f"期限 {n(row.get('effective_due_day'))} · {missed} · {completed}"
                self.text((x+24,yy+29),statuses.get(row.get('status'),'等待公开记录')+' · '+timing,15,MUTED,False,w-48)
            if not history:self.text((x+24,y+501),'暂无公开期限记录',18,MUTED,False,w-48)
        else:
            suppliers=sorted(data['suppliers'],key=lambda row:row.get('id')!='focused')
            pages=max(1,len(suppliers));page%=pages
            supplier=suppliers[page] if suppliers else {}
            self.text((x+24,y+86),supplier.get('name') or '等待公开货源',26,INK,True,w-48,2)
            unlocked=supplier.get('unlocked')
            availability='已开放' if unlocked is True else f"第 {n(supplier.get('unlock_day'))} 天开放" if unlocked is False else '等待公开开放状态'
            self.text((x+24,y+164),availability,22,TEAL if unlocked else GOLD,True,w-48)
            self.text((x+24,y+207),f"每箱 {n(supplier.get('cost'))} 星币 · {n(supplier.get('energy_cost'))} 精力",24,GOLD,True,w-48)
            self.text((x+24,y+252),f"今日剩余 {n(supplier.get('remaining'))} 箱 · 每日限额 {n(supplier.get('daily_limit'))} 箱",19,INK,False,w-48)
            self.text((x+24,y+297),supplier.get('description') or '等待公开采购说明',18,MUTED,False,w-48,3)
            focused=supplier.get('id')=='focused'
            self.text((x+24,y+389),'可选类别（由店长在CLI指定）' if focused else '供应商封存箱',20,TEAL,True,w-48)
            for i,row in enumerate(supplier.get('categories',[])[:5]):
                self.text((x+24,y+430+i*30),f"{row['name']} · {row['id']}",19,INK,False,w-48)
            if focused:
                crates=data['crates']
                labels='、'.join(f"{row.get('id') or '货箱'}（{row['requested_kind_label']}）" for row in crates)
                self.text((x+24,y+602),'待开分类箱：'+(labels or '暂无'),17,GOLD,False,w-48,3)
                self.text((x+24,y+683),'类别只限定抽取范围；不指定某件旧物，稀有度、品相与箱内身份仍须开箱揭晓。',18,MUTED,False,w-48,3)
            else:self.text((x+24,y+451),'购买后只看到封存箱。开箱前，不显示任何箱内物品身份。',19,MUTED,False,w-48,3)
            self.text((x+24,y+766),'公开信息可翻看；采购和开箱仍由店长使用CLI执行。',16,MUTED,False,w-48,2)
        if pages>1:
            self.text((x+w/2,y+h-39),f'{page+1} / {pages} · 翻看公开记录',16,TEAL,False,anchor='mt')
            self.text((x+25,y+h-44),'‹',27,GOLD,True)
            self.text((x+w-25,y+h-44),'›',27,GOLD,True,anchor='rt')
            self.hits.extend([((x,y+h-57,x+w*.27,y+h-9),('management_page',-1)),
                              ((x+w*.73,y+h-57,x+w,y+h-9),('management_page',1))])
        else:self.text((x+24,y+h-39),'只读说明 · 不付款、不采购、不推进游戏',15,MUTED,False,w-48)

    def sale_detail(self, source):
        """Public pre-sale conditions only; clicking never attempts a sale."""
        item=public_sale_detail(source,source.get('walkins'),source.get('_sale_page'))
        overlay=Image.new('RGBA',self.image.size,(6,16,24,225))
        self.image=Image.alpha_composite(self.image.convert('RGBA'),overlay).convert('RGB');self.draw=ImageDraw.Draw(self.image)
        w=min(self.W-40,710);h=min(self.H-48,920);x=(self.W-w)/2;y=(self.H-h)/2
        self.rect((x,y,x+w,y+h),'#263d45',25,TEAL,2)
        self.hits=[((0,0,self.W,self.H),('close',None))]
        self.text((x+24,y+23),'售前公开条件 · 逐位查看',20,TEAL,True,w-152)
        self.text((x+w-22,y+27),'点击返回 ×',16,MUTED,anchor='rt')
        self.item_art(x+22,y+64,67,item)
        self.text((x+105,y+68),item.get('name') or '未命名旧物',24,INK,True,w-131)
        price=public_integer(item.get('price'),0,10**9)
        reference=public_integer(item.get('public_reference'),0,10**9)
        self.text((x+105,y+107),f'标价 {price if price is not None else "?"} · 公开参考价 {reference if reference is not None else "?"}',17,GOLD,False,w-131)
        if item.get('negotiating'):
            self.text((x+24,y+150),'已有还价请按待谈面板处理；新售前条件不撤销已承诺还价',16,LILAC,True,w-48,2)
        else:self.text((x+24,y+150),item.get('description') or '这件旧物的故事，还在慢慢展开。',16,MUTED,False,w-48,2)
        self.line([(x+24,y+198),(x+w-24,y+198)],LINE,1)
        self.text((x+24,y+213),walkins_summary(item.get('walkins')),17,TEAL,True,w-48)
        options=item['sale_options'];count=len(options);page=item['_sale_page']%max(1,count)
        if not options:
            self.text((x+24,y+274),'等待公开售前条件',25,GOLD,True,w-48)
            self.text((x+24,y+326),'公开数据不足，暂不推算还价资格或初次成功率。',18,MUTED,False,w-48,3)
        else:
            option=options[page];status,color=sale_status(option)
            if item.get('negotiating'):status,color='已有还价 · 暂不接待新出售',LILAC
            name=option.get('customer_name') or '旅客'
            suffix=' · 普通散客' if option.get('customer_id') is None else ' · 特邀顾客'
            self.text((x+24,y+260),name+suffix,25,INK,True,w-48)
            self.text((x+24,y+300),status,22,color,True,w-48)
            budget=option.get('budget_range')
            self.text((x+24,y+339),f'公开常规预算 {budget[0]}–{budget[1]} 星币' if budget else '等待公开预算范围',18,GOLD,False,w-48)
            maximum=option.get('max_counter_ask')
            cap=(f'还价标价范围：2–{maximum} 星币' if maximum is not None and maximum>=2
                 else '没有合法还价标价空间' if maximum is not None else '等待公开还价标价上限')
            self.text((x+24,y+373),cap,18,INK,True,w-48)
            counter_rule='还价仍须≤参考价125%及常规预算区间上限'
            self.text((x+24,y+404),counter_rule,16,MUTED,False,w-48,2)
            minimum=option.get('min_condition')
            condition='达标' if option.get('condition_met') is True else '未达标' if option.get('condition_met') is False else '待公开'
            preference='匹配' if option.get('preference_match') is True else '不匹配' if option.get('preference_match') is False else '待公开'
            terms=f'品相 ≥{minimum if minimum is not None else "?"}%（{condition}）'
            if option.get('customer_id') is not None:terms+=f' · 偏好{preference}'
            self.text((x+24,y+446),terms,17,INK,False,w-48,2)
            reasons=option.get('reasons')
            reason_text=('不符：'+'；'.join(reasons)) if reasons else ('公开还价条件均符合' if option.get('counter_eligible') is True else '等待完整公开还价条件')
            self.text((x+24,y+492),reason_text,16,RED if reasons else MUTED,False,w-48,5)
            warning=option.get('warning') or '初次正式出售消耗1体力，并占用该买家与该货今日接待；普通失败是否还价取决于公开条件。'
            self.text((x+24,y+604),warning,16,INK,False,w-48,6)
            budget_note='常规预算是消费舒适度，超出后初次成功率逐步降低\n还价资格非成交保证；初次精确成功率不公开'
            self.text((x+24,y+738),budget_note,16,MUTED,False,w-48,2)
            self.text((x+24,y+785),'01 仍可奇迹成交（1%）· 100 直接离店（1%）',16,GOLD,False,w-48,2)
        footer=y+h-58
        self.line([(x+24,footer-12),(x+w-24,footer-12)],LINE,1)
        if count>1:
            self.text((x+w/2,footer),f'买家 {page+1}/{count} · 只读条件',16,MUTED,anchor='mt')
            self.text((x+24,footer),'‹ 上一位',17,TEAL,True)
            self.text((x+w-24,footer),'下一位 ›',17,TEAL,True,anchor='rt')
            self.hits.extend([((x+12,footer-7,x+w*.29,footer+29),('sale_page',-1)),
                              ((x+w*.71,footer-7,x+w-12,footer+29),('sale_page',1))])
        else:self.text((x+w/2,footer),'只读条件 · 不会掷骰或完成交易',16,MUTED,anchor='mt')

    def walkins_detail(self, source):
        visits=public_walkins(source.get('walkins'))
        overlay=Image.new('RGBA',self.image.size,(6,16,24,220))
        self.image=Image.alpha_composite(self.image.convert('RGBA'),overlay).convert('RGB');self.draw=ImageDraw.Draw(self.image)
        w=min(self.W-40,670);h=670;x=(self.W-w)/2;y=(self.H-h)/2
        self.rect((x,y,x+w,y+h),'#263d45',25,TEAL,2)
        self.hits=[((0,0,self.W,self.H),('close',None))]
        self.text((x+24,y+24),'普通散客 · 今日接待',23,TEAL,True,w-150)
        self.text((x+w-22,y+29),'点击返回 ×',16,MUTED,anchor='rt')
        self.text((x+24,y+89),walkins_summary(visits),23,GOLD,True,w-48,2)
        used=visits.get('used')
        self.text((x+24,y+158),f'今日已用 {used if used is not None else "?"} 次 · 次日重置',20,INK,True,w-48)
        rule=visits.get('visit_rule') or '正式出售无论成交、还价或离店都占用名额；改价、换货或重启不刷新，次日重置。'
        self.text((x+24,y+208),rule,19,MUTED,False,w-48,4)
        self.text((x+24,y+321),'正式出售花1体力；无效指令不占名额',19,INK,False,w-48,2)
        minimum=visits.get('min_condition')
        self.text((x+24,y+380),f'还价需品相 ≥{minimum if minimum is not None else "?"}%，且符合公开标价条件',18,INK,False,w-48,2)
        self.text((x+24,y+441),'普通失败可能直接离店，收入0；货物留下，今日不能换客重试。',18,RED,False,w-48,3)
        budget_note='常规预算是消费舒适度，超出会逐步降低初次成功率；精确预算隐藏，01仍可奇迹成交。'
        self.text((x+24,y+529),budget_note,18,GOLD,False,w-48,3)
        self.text((x+24,y+h-35),'在货架点击旧物，可逐位查看出售条件',16,MUTED,False,w-48)

    def roll_detail(self, source):
        roll=public_roll(source)
        overlay=Image.new('RGBA',self.image.size,(6,16,24,220))
        self.image=Image.alpha_composite(self.image.convert('RGBA'),overlay).convert('RGB');self.draw=ImageDraw.Draw(self.image)
        w=min(self.W-52,710);h=min(self.H-100,780);x=(self.W-w)/2;y=(self.H-h)/2
        pending=public_negotiation(source.get('negotiation'))
        if pending.get('_unsupported_rules'):pending={}
        label,color=roll_status(roll,pending)
        self.rect((x,y,x+w,y+h),'#263d45',25,color,2)
        self.hits=[((0,0,self.W,self.H),('close',None))]
        self.text((x+24,y+24),'演示数据 · 骰子记录' if self.demo else '已判定的骰子记录',19,TEAL,True,w-145)
        self.text((x+w-24,y+27),'点击返回 ×',16,MUTED,anchor='rt')
        if roll.get('_unsupported_rules'):
            self.text((x+27,y+92),'不支持此规则版本 · 仅支持 v10',24,MUTED,True,w-54,2)
            return
        self.roll_art(x+w/2-72,y+73,144,roll,color)
        self.text((x+w/2,y+222),roll_rules_label(roll),16,MUTED,False,w-54,anchor='mt')
        self.text((x+w/2,y+245),label,30,color,True,w-40,anchor='mt')
        self.text((x+27,y+301),f'第 {int(number(roll.get("day"),1))} 天 · {"最终议价" if roll.get("stage")=="final" else "初次报价"}',19,MUTED,False,w-54)
        self.text((x+27,y+338),f'{roll.get("customer_name") or "旅客"} · {roll.get("item_name") or "旧物"}',22,INK,True,w-54)
        self.text((x+27,y+376),f'公开报价 {int(number(roll.get("price"))):,} 星币',23,GOLD,True,w-54)
        self.text((x+27,y+421),roll_math(roll),21,INK,True,w-54)
        modifiers=[as_dict(v) for v in as_list(roll.get('modifiers'))]
        unit='百分点'
        pieces=[f'{v.get("label", "修正")} {number(v.get("value")):+g}{unit}' for v in modifiers]
        if has_roll_breakdown(roll):
            self.text((x+27,y+462),chance_breakdown(roll),18,INK,True,w-54)
            chance=percentile_chance_text(roll.get('threshold'))
            self.text((x+27,y+493),chance,17,INK,False,w-54,2)
            self.text((x+27,y+542),' · '.join(pieces) or '没有公开修正项',16,MUTED,False,w-54,2)
            self.text((x+27,y+593),roll.get('explanation') or '此处只回看已经完成的公开判定，不会再次掷骰。',17,MUTED,False,w-54,3)
        else:
            self.text((x+27,y+467),' · '.join(pieces) or '没有公开修正项',17,MUTED,False,w-54,2)
            self.text((x+27,y+528),roll.get('explanation') or '此处只回看已经完成的公开判定，不会再次掷骰。',18,MUTED,False,w-54,3)
        pending=public_negotiation(source.get('negotiation'))
        if pending.get('_unsupported_rules'):pending={}
        if pending:
            self.text((x+27,y+612),f'还价 {int(number(pending.get("counter_offer"))):,} 星币 · 待店主决定',20,LILAC,True,w-54)
            self.text((x+27,y+647),'接受 / 谢绝免费；最后报价消耗 1 体力',17,INK,False,w-54,2)
        self.line([(x+27,y+h-76),(x+w-27,y+h-76)],LINE,1)
        rules='01 必成：1% · 00 + 0 = 100 必败：1%'
        self.text((x+27,y+h-60),rules,16,GOLD,False,w-54,2)
        footer='CoC 启发简化房规 · 非完整官方规则 · 只读'
        self.text((x+27,y+h-29),footer,14,MUTED,False,w-54)

    def content(self, box, o):
        if self.tab=='collection':self.codex(box,o)
        elif self.tab=='visitors':self.visitors(box,o)
        elif self.tab=='upgrades':self.growth(box,o)
        elif self.tab=='journal':self.journal(box,o)
        else:self.items(box,o)

    def render(self, observation, size=(760,1240), tab='shelf', page=0, frame=0, error=None, detail=None, journal_mode='events', demo=False):
        width,height=max(240,int(size[0])),max(320,int(size[1]))
        wide=width/height>=1.16
        narrow=width<600 and not wide
        o=as_dict(observation)
        if o and not native_observation(o):
            o={};detail=None;error='不支持此公开状态版本 · 仅支持 v10'
        if not o:detail=None
        current_roll=public_roll(o.get('last_roll') or as_dict(o.get('last_event')).get('roll'))
        extra=126 if has_bargaining_preview(o.get('negotiation')) else (32 if has_roll_breakdown(current_roll) and (as_dict(as_dict(o.get('last_event')).get('roll')) or not as_dict(o.get('last_event')).get('type')) else 0)
        self.W,self.H=(1320,940) if wide else ((520,max(1100,round(height/width*520))) if narrow else (760,1240))
        if narrow and extra:self.H=max(self.H,1100+max(0,extra-48))
        if tab=='collection' and as_dict(o.get('collection_progress')) and not wide:
            self.H=max(self.H,(1196+max(0,extra-48)) if narrow else (1240+max(0,extra-64)))
        self.image=Image.new('RGB',(self.W,self.H),BG); self.draw=ImageDraw.Draw(self.image)
        self.demo=bool(demo);self.journal_mode='rolls' if journal_mode=='rolls' else 'events'
        self.words=[];self.hits=[];self.tab=tab if tab in dict(TABS) else 'shelf';self.page=max(0,page);self.page_count=1
        for yy in range(self.H):
            p=yy/self.H
            self.line([(0,yy),(self.W,yy)],(int(16+4*p),int(28+7*p),int(41+4*p)),1)
        self.header(o,wide)
        if not o:
            self.shop_scene((32,169,self.W-64,round((self.W-64)*320/680)),{},frame)
            cy=670 if not wide else 730
            self.text((self.W/2,cy),error or '等候店长开门',34,GOLD,True,anchor='mt')
            self.text((self.W/2,cy+56),'暖灯已亮起，等待公开的经营动态',22,MUTED,anchor='mt')
        elif wide:
            left=32;lw=706;right=762;rw=526
            self.metrics((left,132,lw,98),o)
            self.shop_scene((left,247,lw,306-extra),o,frame)
            self.demand_strip((left,563-extra,lw,72),o)
            self.current_event((left,650-extra,lw,229+extra),o)
            self.goal_card((right,132,rw,140),o)
            self.tab_bar((right,291,rw,56))
            self.content((right,362,rw,517),o)
        elif narrow:
            trim=min(extra,48);shift=extra-trim
            self.metrics((22,120,476,88),o)
            self.shop_scene((22,222,476,130-trim),o,frame)
            self.demand_strip((22,361-trim,476,61),o)
            self.current_event((22,431-trim,476,218+extra),o)
            self.goal_card((22,663+shift,476,127),o)
            self.tab_bar((22,805+shift,476,55))
            self.content((22,876+shift,476,self.H-918-shift),o)
        else:
            trim=min(extra,64);shift=extra-trim
            self.metrics((32,125,696,90),o)
            self.shop_scene((32,231,696,164-trim),o,frame)
            self.demand_strip((32,404-trim,696,56),o)
            self.current_event((32,473-trim,696,218+extra),o)
            self.goal_card((32,697+shift,696,130),o)
            self.tab_bar((32,843+shift,696,55))
            self.content((32,914+shift,696,self.H-958-shift),o)
        self.line([(32,self.H-33),(self.W-32,self.H-33)],LINE,1)
        status=error or ('演示预览 · 未推进游戏' if self.demo else '首周已结算 · 等店长继续' if o.get('phase')=='week_summary' else '星港只读观战 · 纯虚拟星币')
        self.text((32,self.H-24),status,14,RED if error else MUTED)
        self.text((self.W-32,self.H-24),'F11 全屏' if narrow else '1–5 切换展台  ·  F11 全屏',13,MUTED,anchor='rt')
        # Keep the ending status small so the public history remains readable.
        if o.get('phase')=='lost':self.pill((self.W//2-96,30),'本次航行结束',RED,19,'#503c36')
        if detail:self.detail_card(as_dict(detail))
        self.scale=min(width/self.W,height/self.H)
        outw,outh=round(self.W*self.scale),round(self.H*self.scale)
        self.offset=((width-outw)//2,(height-outh)//2)
        image=self.image.resize((outw,outh),Image.Resampling.LANCZOS)
        result=Image.new('RGB',(width,height),BG);result.paste(image,self.offset)
        return result

    def action_at(self, x, y):
        if not hasattr(self,'scale'):return None
        x=(x-self.offset[0])/self.scale;y=(y-self.offset[1])/self.scale
        for (x1,y1,x2,y2),action in reversed(self.hits):
            if x1<=x<=x2 and y1<=y<=y2:return action
        return None


class Spectator:
    def __init__(self, path, fullscreen=False, geometry=None, demo=False, tab='shelf', page=0, journal_mode='events'):
        # Tk stays lazy: importing the renderer and producing snapshots require no display.
        import tkinter as tk
        from PIL import ImageTk
        self.tk=tk;self.ImageTk=ImageTk
        self.reader=ObservationReader(path);self.demo=bool(demo);self.journal_mode='rolls' if journal_mode=='rolls' else 'events'
        self.renderer=Renderer()
        self.root=tk.Tk();self.root.title('星屑杂货铺 · 双 D10 百分骰 / 只读观战' + (' · 演示' if self.demo else ''))
        self.root.configure(bg=BG)
        sw,sh=self.root.winfo_screenwidth(),self.root.winfo_screenheight()
        self.root.geometry(geometry or f'{min(1320,sw-60)}x{min(940,sh-90)}+30+30')
        self.root.minsize(320,500)
        self.root.attributes('-fullscreen',fullscreen)
        self.canvas=tk.Canvas(self.root,bg=BG,highlightthickness=0)
        self.canvas.pack(fill='both',expand=True)
        self.photo=None;self.canvas_image=self.canvas.create_image(0,0,anchor='nw')
        self.tab=tab if tab in dict(TABS) else 'shelf';self.page=max(0,page);self.detail=None;self.started=time.monotonic();self.last_signature=None
        self.root.bind('<F11>',lambda _:self.root.attributes('-fullscreen',not self.root.attributes('-fullscreen')))
        self.root.bind('<Escape>',self.escape)
        for key,(tab,_) in zip('12345',TABS):self.root.bind(key,lambda _,t=tab:self.set_tab(t))
        self.root.bind('<Left>',lambda _:self.turn_page(-1))
        self.root.bind('<Right>',lambda _:self.turn_page(1))
        self.root.bind('<space>',lambda _:self.turn_page(1))
        self.canvas.bind('<Button-1>',self.click)
        self.root.protocol('WM_DELETE_WINDOW',self.root.destroy)
        self.tick()

    def escape(self, event=None):
        if self.detail is not None:self.detail=None;self.last_signature=None
        else:self.root.attributes('-fullscreen',False)

    def set_tab(self, tab):
        self.tab=tab;self.page=0;self.detail=None;self.last_signature=None

    def turn_page(self, delta):
        self.page=(self.page+delta)%max(1,self.renderer.page_count);self.last_signature=None

    def click(self,event):
        action=self.renderer.action_at(event.x,event.y)
        if action:
            if action[0]=='tab':self.set_tab(action[1])
            elif action[0]=='page':self.turn_page(action[1])
            elif action[0]=='show_rolls':self.set_tab('journal');self.journal_mode='rolls'
            elif action[0]=='journal_mode':self.journal_mode=action[1];self.page=0;self.last_signature=None
            elif action[0]=='inspect':self.detail=action[1];self.last_signature=None
            elif action[0]=='sale_page' and as_dict(self.detail).get('_view')=='sale':
                count=len(as_list(self.detail.get('sale_options')))
                self.detail=dict(self.detail,_sale_page=(int(number(self.detail.get('_sale_page')))+action[1])%max(1,count))
                self.last_signature=None
            elif action[0]=='collection_page' and as_dict(self.detail).get('_view')=='codex':
                count=len(as_list(as_dict(self.detail.get('_collection')).get('items')))
                self.detail=dict(self.detail,_collection_page=(int(number(self.detail.get('_collection_page')))+action[1])%max(1,count))
                self.last_signature=None
            elif action[0]=='management_page' and as_dict(self.detail).get('_view')=='management':
                section=self.detail.get('_section')
                count=len(as_list(self.detail.get('suppliers'))) if section=='suppliers' else math.ceil(len(as_list(as_dict(self.detail.get('campaign')).get('deadline_history')))/4)
                self.detail=dict(self.detail,_management_page=(int(number(self.detail.get('_management_page')))+action[1])%max(1,count))
                self.last_signature=None
            elif action[0]=='close':self.detail=None;self.last_signature=None

    def refresh_detail(self):
        """A projection refresh must not leave a live quote looking current."""
        detail=as_dict(self.detail)
        observation=as_dict(self.reader.observation)
        if not native_observation(observation):
            self.detail=None
            return
        pending=public_negotiation(observation.get('negotiation'))
        if detail.get('_view')=='management':
            self.detail=public_management_detail(observation,detail.get('_section'),detail.get('_management_page'))
        elif detail.get('_view')=='codex':
            entries=as_list(as_dict(as_dict(self.reader.observation).get('codex')).get('entries'))
            entry=next((public_catalog_entry(v,slot) for slot,v in enumerate(entries,1)
                        if (public_integer(as_dict(v).get('slot'),1,10**6) or slot)==detail.get('slot')),None)
            self.detail=public_collection_detail(entry,self.reader.observation,detail.get('_collection_page',0)) if entry else None
        elif detail.get('_view')=='collection_progress':
            progress=public_collection_progress(as_dict(self.reader.observation).get('collection_progress'))
            self.detail=dict(_view='collection_progress',progress=progress) if progress else None
        elif detail.get('_view')=='sale':
            observation=as_dict(self.reader.observation)
            item=next((v for v in as_list(observation.get('inventory'))
                       if as_dict(v) and v.get('id')==detail.get('id')),None)
            self.detail=public_sale_detail(item,observation.get('walkins'),detail.get('_sale_page')) if item else None
        elif detail.get('_view')=='walkins':
            visits=public_walkins(as_dict(self.reader.observation).get('walkins'))
            self.detail=dict(_view='walkins',walkins=visits) if visits else None
        elif detail.get('_view')=='negotiation':
            previous=as_dict(detail.get('negotiation'))
            if not pending or pending.get('_unsupported_rules') or pending.get('item_id')!=previous.get('item_id'):
                self.detail=None
            else:
                self.detail=dict(_view='negotiation',negotiation=public_negotiation(pending),
                                 last_roll=public_roll(as_dict(self.reader.observation).get('last_roll')))
        elif detail.get('_view')=='roll' and detail.get('negotiation'):
            if not pending or pending.get('item_id')!=detail.get('item_id'):
                self.detail=dict(detail,negotiation={})

    def tick(self):
        if self.reader.poll() or self.reader.observation is None:self.refresh_detail()
        w,h=self.canvas.winfo_width(),self.canvas.winfo_height()
        if w>10 and h>10:
            signature=(self.reader.stamp,w,h,self.tab,self.page,self.reader.error,str(self.detail),self.journal_mode,self.demo)
            if signature!=self.last_signature:
                im=self.renderer.render(self.reader.observation,(w,h),self.tab,self.page,frame=0,error=self.reader.error,detail=self.detail,journal_mode=self.journal_mode,demo=self.demo)
                self.photo=self.ImageTk.PhotoImage(im,master=self.root)
                self.canvas.itemconfigure(self.canvas_image,image=self.photo)
                self.last_signature=signature
        self.root.after(250,self.tick)

    def run(self):self.root.mainloop()


def main(argv=None):
    parser=argparse.ArgumentParser(description='星屑杂货铺：v10 双 D10 百分骰低骰房规，只读观战')
    parser.add_argument('--observation',default=str(Path(__file__).with_name('observation.json')))
    parser.add_argument('--fullscreen',action='store_true')
    parser.add_argument('--geometry',help='可选窗口尺寸，例如 760x1240')
    parser.add_argument('--snapshot',help='保存只读画面的 PNG 截图，不启动窗口')
    parser.add_argument('--width',type=int,default=760)
    parser.add_argument('--height',type=int,default=1240)
    parser.add_argument('--tab',choices=list(dict(TABS)),default='shelf')
    parser.add_argument('--page',type=int,default=0)
    parser.add_argument('--journal-mode',choices=['events','rolls'],default='events')
    parser.add_argument('--demo',action='store_true',help='明显标记为演示数据，不是真实游玩')
    args=parser.parse_args(argv)
    if args.snapshot:
        output=Path(args.snapshot)
        # Protect both public state and private saves from accidental screenshot paths.
        if output.suffix.lower()!='.png':parser.error('--snapshot 必须是独立的 .png 文件')
        if output.resolve()==Path(args.observation).resolve():parser.error('截图不能覆盖公开状态')
        reader=ObservationReader(args.observation);reader.poll()
        image=Renderer().render(reader.observation,(args.width,args.height),args.tab,args.page,error=reader.error,journal_mode=args.journal_mode,demo=args.demo)
        output.parent.mkdir(parents=True,exist_ok=True);image.save(output,'PNG')
        print(output)
        return 0
    Spectator(args.observation,args.fullscreen,args.geometry,args.demo,args.tab,args.page,args.journal_mode).run()
    return 0


if __name__=='__main__':raise SystemExit(main())
