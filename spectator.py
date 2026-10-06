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
ROLL_LABELS = {'miracle': ('天然20 · 大成功', GOLD), 'success': ('普通成功', TEAL), 'failure': ('失败', RED), 'fumble': ('天然1 · 大失败', RED)}
PERCENTILE_LABELS = {'miracle': ('01 · 大成功', GOLD), 'success': ('普通成功', TEAL), 'failure': ('失败', RED), 'fumble': ('100 · 大失败', RED)}
KINDS = {'tool': '工具', 'artifact': '古物', 'bot': '机器人', 'plant': '植物', 'signal': '信号'}
UPGRADES = {'workbench': '修理工作台', 'shelf': '陈列货架', 'display': '收藏展柜', 'showcase': '收藏展柜', 'lounge': '旅客休息角', 'sign': '星港招牌', 'scanner': '鉴定扫描仪'}


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


def safe_color(value, fallback=TEAL):
    try:
        if not isinstance(value, str) or not value.startswith('#'):
            return fallback
        ImageColor.getrgb(value)
        return value
    except (ValueError, TypeError):
        return fallback


def percentile_rules(value):
    source = as_dict(value)
    return (source.get('rules_version') in (5, 6) or source.get('die') == 'D100'
            or 'tens' in source or 'ones' in source)


def public_integer(value, low, high, step=1):
    result = number(value, None)
    if isinstance(value, bool) or result is None or result != int(result):
        return None
    result = int(result)
    return result if low <= result <= high and (result-low) % step == 0 else None


def public_roll(value):
    """An explicit public-field projection, never a derivation or a random roll."""
    source = as_dict(value)
    if not source:
        return {}
    fields = ('id', 'day', 'item_id', 'item_name', 'customer_id', 'customer_name',
              'stage', 'modifier', 'modifiers', 'success', 'outcome', 'price',
              'explanation', 'rules_version', 'counter_offer')
    if percentile_rules(source):
        fields += ('die', 'tens', 'ones', 'roll', 'threshold', 'probability', 'base_chance', 'premium')
    else:
        fields += ('face', 'total', 'target', 'base_target', 'rejection_penalty')
    roll = {key: source.get(key) for key in fields}
    roll['modifiers'] = [{key: row.get(key) for key in ('label', 'value')}
                         for row in as_list(source.get('modifiers')) if isinstance(row, dict)]
    if percentile_rules(source):
        roll['tens'] = public_integer(source.get('tens'), 0, 90, 10)
        roll['ones'] = public_integer(source.get('ones'), 0, 9)
        roll['roll'] = public_integer(source.get('roll'), 1, 100)
        roll['threshold'] = public_integer(source.get('threshold'), 1, 99)
        # Check consistency without inventing a missing combined roll.
        if (roll['tens'] is None or roll['ones'] is None
                or roll['roll'] != (roll['tens'] + roll['ones'] or 100)):
            roll['roll'] = None
    else:
        roll['face'] = public_integer(source.get('face'), 1, 20)
    return roll


def roll_status(roll, negotiation=None):
    roll = as_dict(roll)
    pending = as_dict(negotiation)
    if percentile_rules(roll) and public_roll(roll).get('roll') is None:
        return '等待有效公开双骰', MUTED
    if pending and pending.get('item_id') == roll.get('item_id') and roll.get('stage') == 'initial' and roll.get('outcome') == 'failure':
        return '还价中', LILAC
    labels = PERCENTILE_LABELS if percentile_rules(roll) else ROLL_LABELS
    return labels.get(roll.get('outcome'), ('等待公开判定', MUTED))


def roll_rules_label(roll):
    if percentile_rules(roll):
        version = public_integer(roll.get('rules_version'), 5, 6) or 5
        return f'v{version} · D100 低骰规则'
    version = public_integer(roll.get('rules_version'), 3, 4) or 3
    return f'v{version} · D20 原高骰规则'


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
    fields = ('id', 'name', 'kind', 'rarity', 'color', 'condition', 'price',
              'description', 'negotiating', 'public_reference')
    result = {key: source.get(key) for key in fields}
    result.update(_view='sale', _sale_page=max(0, int(number(page))),
                  sale_options=[public_sale_option(v) for v in as_list(source.get('sale_options')) if as_dict(v)],
                  walkins=public_walkins(walkins))
    return result


def walkins_summary(value):
    visits = public_walkins(value)
    if not visits:
        return '普通散客 · 等待公开名额'
    remaining, limit = visits.get('remaining'), visits.get('daily_limit')
    amount = f'{remaining}/{limit} 次' if remaining is not None and limit is not None else '等待公开名额'
    budget = visits.get('budget_range')
    money = f' · 预算 {budget[0]}–{budget[1]}' if budget else ' · 预算待公开'
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
    if percentile_rules(roll):
        result = roll.get('roll')
        return f'D100 {result:02d}' if result is not None else 'D100 ?'
    return f'D20 {roll.get("face") or "?"}'


def percentile_chance_text(threshold):
    threshold = public_integer(threshold, 1, 99)
    if threshold is None:
        return '等待完整公开成功阈值'
    return f'低骰成功：01–{threshold:02d} · 成功率 {threshold}%'


def roll_math(roll):
    """Read public adjudication fields verbatim; never estimate hidden economics."""
    if percentile_rules(roll):
        roll = public_roll(roll)
        tens, ones, result = (roll.get(key) for key in ('tens', 'ones', 'roll'))
        if result is None:
            return 'D100 · 等待有效且一致的公开双骰'
        digits = f'{tens:02d} + {ones} = {result:02d}'
        threshold = roll.get('threshold')
        if threshold is None:
            return f'D100 {digits} · 等待完整公开阈值'
        return f'D100 {digits} · ≤{threshold:02d} 成功（{threshold}%）'
    face = roll.get('face')
    if face is None:
        return '尚无有效公开骰点'
    if any(roll.get(key) is None or number(roll.get(key), None) is None for key in ('modifier','total','target')):
        return f'D20 {face} · 等待完整公开判定'
    modifier = number(roll.get('modifier'))
    total = number(roll.get('total'))
    target = number(roll.get('target'))
    sign = '+' if modifier >= 0 else '−'
    return f'D20 {face} {sign} {abs(modifier):g} = {total:g}  /  目标 {target:g}'


def public_negotiation(value):
    """Keep previews public, including when passing data into a detail overlay."""
    source = as_dict(value)
    if not source:
        return {}
    fields = ('item_id', 'item_name', 'customer_id', 'customer_name', 'rules_version', 'origin_rules_version',
              'original_price', 'counter_offer', 'remaining_offers',
              'final_offer_energy', 'accept_income',
              'final_failure_income')
    if not percentile_rules(source):
        fields += ('rejection_penalty',)
    pending = {key: source.get(key) for key in fields}
    bounds = as_dict(source.get('final_offer_bounds'))
    pending['final_offer_bounds'] = {key: bounds.get(key) for key in ('min', 'max', 'available')}
    preview = as_dict(source.get('preview'))
    fields = ('price', 'basis', 'modifier', 'modifiers', 'energy_cost',
              'accept_income', 'success_income', 'failure_income', 'warning',
              'suggested')
    if percentile_rules(source) or preview.get('basis') == 'public_counter':
        fields += ('base_chance', 'threshold', 'probability', 'premium', 'critical_probability', 'fumble_probability')
    else:
        fields += ('base_target_range', 'rejection_penalty', 'target_range', 'required_raw_range',
                   'ordinary_possible', 'ordinary_guaranteed_at_19', 'natural_20_probability', 'natural_1_fails')
    pending['preview'] = {key: preview.get(key) for key in fields} if preview else {}
    if preview:
        pending['preview']['modifiers'] = [{key: row.get(key) for key in ('label', 'value')}
                                           for row in as_list(preview.get('modifiers')) if isinstance(row, dict)]
    return pending


def has_bargaining_preview(value):
    source = as_dict(value)
    return bool(source) and any(key in source for key in ('preview', 'final_offer_bounds', 'rejection_penalty'))


def honored_quote_label(value):
    """A migrated, already-promised quote keeps its original commitment."""
    source=as_dict(value)
    origin=public_integer(source.get('origin_rules_version'),3,5)
    if source.get('rules_version')==6 and origin is not None:
        return f'v6 继续履行 v{origin} 已承诺还价'
    return None


def has_roll_breakdown(roll):
    if percentile_rules(roll):
        return (roll.get('stage') == 'final'
                and public_integer(roll.get('threshold'), 1, 99) is not None
                and public_integer(roll.get('base_chance'), 1, 99) is not None
                and number(roll.get('counter_offer'), None) is not None)
    return (roll.get('stage') == 'final'
            and all(number(roll.get(key), None) is not None
                    for key in ('base_target', 'rejection_penalty', 'target', 'modifier')))


def dc_breakdown(roll):
    if percentile_rules(roll):
        return (f'基础几率 {number(roll.get("base_chance")):g}% · 公开还价 {number(roll.get("counter_offer")):g}'
                f' → 阈值 {number(roll.get("threshold")):g}')
    return (f'基础 DC {number(roll.get("base_target")):g} + 拒价 {number(roll.get("rejection_penalty")):g}'
            f' = 最终 DC {number(roll.get("target")):g}')


def needed_raw_text(low, high=None):
    """Natural 1 always fails; an ordinary die can only be 2 through 19."""
    low = max(2, number(low, 2))
    high = max(low, number(high, low))
    if low > 19:
        return (f'原始骰需 ≥{low:g}–{high:g}；普通骰无法成功' if high != low
                else f'原始骰需 ≥{low:g}；仅天然20可成（5%）')
    if low == high:
        return f'普通成功需原始骰 ≥{low:g}（2–19）'
    return f'原始骰门槛 {low:g}–{high:g}（随实际 DC）'


def preview_ranges(preview):
    """Validate public ranges rather than manufacturing hidden target values."""
    if (preview.get('basis') != 'public_bands'
            or number(preview.get('price'), None) is None
            or number(preview.get('modifier'), None) is None):
        return None
    ranges = []
    for key in ('base_target_range', 'target_range', 'required_raw_range'):
        pair = as_list(preview.get(key))
        if len(pair) != 2 or any(number(v, None) is None for v in pair):
            return None
        low, high = (number(v) for v in pair)
        if low > high:
            return None
        ranges.append((low, high))
    if number(preview.get('rejection_penalty'), None) is None:
        return None
    return ranges


def percentile_preview(preview):
    """Validate published exact odds, never calculate hidden economic values."""
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


def compact_range(pair):
    return f'{pair[0]:g}' if pair[0] == pair[1] else f'{pair[0]:g}–{pair[1]:g}'


def preview_chance_text(raw_range):
    if raw_range[0] > 19:
        return '只有天然20可成（5%）· 天然1必败'
    if raw_range[1] > 19:
        return '最难端仅天然20可成（5%）· 天然1必败'
    return '天然20：5%必成 · 天然1必败'


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
        self.error = None
        self.updated_at = None

    def poll(self):
        try:
            stat = self.path.stat()
            if stat.st_size > 4 * 1024 * 1024:
                raise ValueError('公开状态文件过大')
            stamp = (stat.st_mtime_ns, stat.st_size)
            if stamp == self.stamp:
                self.error = None
                return False
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or 'credits' not in data or not isinstance(data.get('inventory', []), list):
                raise ValueError('等待有效的公开状态')
            # Old and new engines deliberately exclude these from public output.
            if any(k in data for k in ('rng_state', 'rng', 'hidden_items', '_rng', 'random_state')):
                raise ValueError('文件含非公开状态，已拒绝读取')
            self.observation = data
            self.stamp = stamp
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
            for char in paragraph:
                if max_width and f.getlength(current + char) > max_width and current:
                    wrapped.append(current)
                    current = char
                else:
                    current += char
            wrapped.append(current)
        truncated = len(wrapped) > lines
        wrapped = wrapped[:lines]
        if truncated and wrapped:
            while max_width and f.getlength(wrapped[-1] + '…') > max_width and wrapped[-1]:
                wrapped[-1] = wrapped[-1][:-1]
            wrapped[-1] += '…'
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
        item = as_dict(item)
        color = safe_color(item.get('color'), RARITIES.get(item.get('rarity'), ('',TEAL))[1])
        kind = item.get('kind','artifact')
        s = size / 100
        def b(box): return tuple((x if i%2==0 else y)+v*s for i,v in enumerate(box))
        def r(box,c,rad=3,o=None): self.rect(b(box),c,max(1,int(rad*s)),o)
        def e(box,c,o=None): self.ellipse(b(box),c,o,max(1,int(2*s)))
        def l(pts,c,w=2): self.line([(x+a*s,y+bv*s) for a,bv in pts],c,max(1,int(w*s)))
        def p(pts,c,o=None): self.polygon([(x+a*s,y+bv*s) for a,bv in pts],c,o)
        e((9,85,91,98),'#14212c')
        if crate:
            p([(13,28),(48,10),(88,29),(51,49)],'#a17b5c')
            p([(13,28),(51,49),(51,91),(13,69)],'#755744')
            p([(51,49),(88,29),(88,70),(51,91)],'#5a4339')
            l([(32,19),(70,38),(70,80)],GOLD,6)
            l([(14,48),(51,70),(87,50)],'#b38a62',2)
            r((29,43,47,62),'#eed395',2)
            l([(36,48),(41,48),(38,54)],'#79573b',2)
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
        if stage:
            goals=[as_dict(g) for g in as_list(stage.get('goals'))]
            return {'title':stage.get('title','下一段旅程'),'goals':goals,'campaign':campaign}
        old=as_dict(o.get('goal'))
        goals=[{'label':'星币','current':number(o.get('credits')),'target':number(old.get('credits'),650)},
               {'label':'珍藏','current':len(as_list(o.get('collection'))),'target':number(old.get('collection'),2)}]
        return {'title':'继续收藏，继续经营' if number(o.get('day'))>7 else '让小店在星港站稳脚跟','goals':goals,'campaign':campaign}

    def goal_card(self, box, o):
        x,y,w,h=box
        self.rect((x,y,x+w,y+h),'#233c3e',17, '#466057')
        g=self.stage_model(o)
        summary=o.get('phase')=='week_summary'
        self.text((x+18,y+13),'首周结算' if summary else '下一站',16,TEAL,True)
        self.text((x+w-18,y+13),'可以继续经营' if summary else '长期经营',15,GOLD if summary else MUTED,anchor='rt')
        self.text((x+18,y+41),g['title'],24,INK,True,w-36)
        goals=g['goals']
        # The public campaign owns all milestone calculations, including reputation.
        pieces=[f"{v.get('label','目标')} {int(number(v.get('current'))):,}/{int(number(v.get('target'))):,}" for v in goals]
        if len(pieces)>2:
            for i,piece in enumerate(pieces[:4]):
                self.text((x+18+(i%2)*(w-36)/2,y+74+(i//2)*22),piece,16,GOLD,False,(w-42)/2)
        else:self.text((x+18,y+79),'  ·  '.join(pieces),18,GOLD,False,w-36)
        fractions=[number(v.get('current'))/max(1,number(v.get('target'),1)) for v in goals]
        self.progress(x+18,y+h-(12 if len(pieces)>2 else 20),w-36,min(fractions) if fractions else 1,TEAL,h=5)

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
            rules='低骰' if percentile_rules(previous_roll) else '原高骰'
            self.text((x+18,y+h-28),f'上次 {roll_summary(previous_roll)} · {label} · {rules} · 查看记录 ›',15,color,False,w-36)
            self.hits.append(((x,y+h-40,x+w,y+h),('show_rolls',None)))

    def dice_art(self, x, y, size, face, color=GOLD):
        """A settled D20 face. No fake spinning numbers or new RNG is used."""
        cx=x+size/2;cy=y+size/2
        points=[(cx,y),(x+size*.94,y+size*.25),(x+size*.9,y+size*.75),
                (cx,y+size),(x+size*.1,y+size*.75),(x+size*.06,y+size*.25)]
        self.polygon(points,'#172e3b',color)
        self.line(points+[points[0]],color,3)
        for a,b in [(points[0],(x+size*.22,y+size*.68)),(points[0],(x+size*.78,y+size*.68)),
                    ((x+size*.22,y+size*.68),(x+size*.78,y+size*.68)),
                    (points[1],(x+size*.78,y+size*.68)),(points[5],(x+size*.22,y+size*.68)),
                    (points[3],(x+size*.22,y+size*.68)),(points[3],(x+size*.78,y+size*.68))]:
            self.line([a,b],'#59766e',1)
        self.text((cx,cy-size*.22),str(face) if face is not None else '?',size*.42,color,True,anchor='mt')
        self.text((cx,y+size*.76),'D20',max(11,size*.105),MUTED,True,anchor='mt')

    def roll_art(self, x, y, size, roll, color=GOLD):
        """The two recorded D10 faces, followed by their recorded D100 result."""
        if not percentile_rules(roll):
            return self.dice_art(x,y,size,roll.get('face'),color)
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
        honored=honored_quote_label(pending)
        roll=public_roll(o.get('last_roll') or as_dict(o.get('last_event')).get('roll'))
        preview=as_dict(pending.get('preview'));bounds=as_dict(pending.get('final_offer_bounds'))
        ranges=preview_ranges(preview);percentile=percentile_preview(preview)
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
            self.text((x+18,y+h-24),honored or '公开还价精确预览 · 越低越好 · 不掷骰',13,LILAC if honored else MUTED,False,w-36)
        elif preview and ranges:
            price=int(number(preview.get('price')))
            example=preview.get('suggested')
            if example is None:example=price==number(bounds.get('min'),None)
            suffix='最低价示例' if example else '尚未掷骰'
            self.text((x+18,y+152),f'拟报价 {price:,} 星币 · {suffix}',21,GOLD,True,w-36)
            base,target,raw=ranges
            penalty=number(preview.get('rejection_penalty'))
            self.text((x+18,y+186),f'预估基础 DC {compact_range(base)} + 拒价 {penalty:g} = 最终 {compact_range(target)}',17,INK,True,w-36)
            self.text((x+18,y+214),needed_raw_text(*raw),17,INK,False,w-36)
            self.text((x+18,y+240),preview_chance_text(raw),16,MUTED,False,w-36)
            energy=number(preview.get('energy_cost'),number(pending.get('final_offer_energy'),1))
            income=int(number(preview.get('success_income'),price))
            self.text((x+18,y+267),f'再报价：{energy:g} 体力 · 成功收入 {income:,}',17,INK,False,w-36)
            self.text((x+18,y+294),f'失败收入 0 · 失去 {offer:,} 星币还价',17,RED,True,w-36)
            self.text((x+18,y+h-24),'v4 原高骰规则 · 仅据公开区间 · 预览不消耗体力',13,MUTED,False,w-36)
        elif bounds.get('available') is False:
            self.text((x+18,y+156),'没有合法的最终报价',22,RED,True,w-36)
            self.text((x+18,y+194),'报价须高于还价，并低于初次标价',18,INK,False,w-36)
            self.text((x+18,y+226),'可以接受还价，或免费谢绝',18,MUTED,False,w-36)
            self.text((x+18,y+h-27),honored or '只读观战 · 不会替店主作决定',14,LILAC if honored else MUTED,False,w-36)
        else:
            self.text((x+18,y+156),'等待公开报价预览',22,GOLD,True,w-36)
            self.text((x+18,y+194),'公开数据不足，暂不推算骰点或难度',17,MUTED,False,w-36)
            self.text((x+18,y+232),f'再报价：{number(pending.get("final_offer_energy"),1):g} 体力',18,INK,False,w-36)
            self.text((x+18,y+267),f'失败收入 0 · 失去 {offer:,} 星币还价',17,RED,True,w-36)
            if honored:self.text((x+18,y+h-24),honored,13,LILAC,False,w-36)
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
        bounds=as_dict(pending.get('final_offer_bounds'))
        if bounds.get('available') is True:
            self.text((x+27,y+429),f'合法最终报价：{int(number(bounds.get("min"))):,}–{int(number(bounds.get("max"))):,} 星币',18,INK,True,w-54)
        modifiers=[as_dict(v) for v in as_list(preview.get('modifiers'))]
        unit='百分点' if preview.get('basis')=='public_counter' else ''
        pieces=[f'{v.get("label", "修正")} {number(v.get("value")):+g}{unit}' for v in modifiers]
        self.text((x+27,y+466),f'冻结加值 {number(preview.get("modifier")):+g}{unit} · ' + (' · '.join(pieces) or '没有公开修正项'),17,MUTED,False,w-54,2)
        fallback=('基于公开还价的精确几率；最终失败收入0，不能回头接受旧还价。' if unit
                  else '预览只使用公开区间；实际难度在最终报价落骰后公开。')
        self.text((x+27,y+525),preview.get('warning') or fallback,17,MUTED,False,w-54,3)
        honored=honored_quote_label(pending)
        if honored:
            origin=public_integer(pending.get('origin_rules_version'),3,5)
            caption=honored+(' · 原D20加值×5' if origin in (3,4) else '')
            self.text((x+27,y+599),caption,15,LILAC,True,w-54)
        elif unit:
            origin=public_integer(pending.get('origin_rules_version'),3,4)
            caption=f'已由 v{origin} 迁移 · 原 D20 加值 ×5 个百分点' if origin else 'CoC 启发的简化房规，并非完整官方规则'
            self.text((x+27,y+599),caption,15,MUTED,False,w-54)
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
        pending=as_dict(o.get('negotiation'))
        if roll and (pending.get('item_id')!=roll.get('item_id') or roll.get('stage')!='initial' or roll.get('outcome')!='failure'):pending={}
        label,color=roll_status(roll,pending)
        self.rect((x,y,x+w,y+h),'#20353e',18,color,1)
        self.pill((x+16,y+12),roll_rules_label(roll)+(' · 演示' if self.demo else ''),color,15,'#30444b',10)
        self.text((x+w-16,y+20),'查看骰子记录 ›',14,MUTED,anchor='rt')
        self.roll_art(x+15,y+54,114,roll,color)
        tx=x+147;tw=w-163
        self.text((tx,y+55),label,28,color,True,tw)
        who=' · '.join(str(v) for v in (roll.get('customer_name'),roll.get('item_name')) if v)
        self.text((tx,y+99),who or '等待下一笔生意的公开判定',16,INK,False,tw)
        if pending:
            ask=int(number(pending.get('original_price')));offer=int(number(pending.get('counter_offer')))
            self.text((tx,y+130),f'标价 {ask:,} → 还价 {offer:,}',21,GOLD,True,tw)
            self.text((tx,y+166),'待店主决定 · 只剩一次议价',17,LILAC,True,tw)
        else:
            price=int(number(roll.get('price')))
            sold=roll.get('outcome') in ('miracle','success')
            self.text((tx,y+130),f'{"成交" if sold else "公开报价"} {price:,} 星币',23,GOLD if sold else INK,True,tw)
            message='再高的报价，也有奇迹时刻' if roll.get('outcome')=='miracle' else '旅客带着新故事离开' if sold else '本次交易未成'
            if has_roll_breakdown(roll):
                self.text((x+18,y+167),dc_breakdown(roll),17,INK,True,w-36)
                chance=percentile_chance_text(roll.get('threshold')) if percentile_rules(roll) else needed_raw_text(number(roll.get('target'))-number(roll.get('modifier')))
                self.text((x+18,y+195),chance,16,MUTED,False,w-36)
            else:self.text((tx,y+166),message,17,MUTED,False,tw)
        if pending:
            math_text=(f'≤{roll.get("threshold") or "?"} 成功' if percentile_rules(roll)
                       else f'合计 {number(roll.get("total")):g} / 目标 {number(roll.get("target")):g}')
            self.text((x+18,y+h-27),math_text,13,MUTED,False,125)
            self.text((tx,y+h-27),'接受/谢绝免费 · 再报价1体力',14,MUTED,False,tw)
        else:self.text((x+18,y+h-27),roll_math(roll),15,MUTED,False,w-36)
        public_pending={key:pending.get(key) for key in ('item_id','original_price','counter_offer','remaining_offers','final_offer_energy')} if pending else {}
        self.hits.append(((x,y,x+w,y+h),('inspect',dict(roll,_view='roll',negotiation=public_pending))))
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
        if number(o.get('version')) >= 6 and as_dict(o.get('walkins')):
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
        forecasts=not collection and number(o.get('version')) >= 6
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
        per_page=max(1,int((h-80)/87)); pages=max(1,math.ceil(len(entries)/per_page)); page=self.page%pages
        self.page_count=pages
        for i,item in enumerate(entries[page*per_page:(page+1)*per_page]):
            yy=y+46+i*87;key=item.get('id',''); level=int(number(item.get('level')))
            self.rect((x,yy,x+w,yy+78),PANEL,14)
            self.item_art(x+10,yy+10,58,{'kind':'tool' if key=='workbench' else 'artifact','color':TEAL if level else '#728884'})
            self.text((x+82,yy+12),item.get('name') or UPGRADES.get(key,key or '小店设施'),22,INK,True,w-220)
            cost=item.get('next_cost',costs.get(key))
            desc=item.get('effect') or item.get('description') or (f'下次升级 {cost} 星币' if cost is not None else '店铺设施')
            badge=f"{item.get('current',0)}/{item.get('required',3)}" if item.get('is_set') else f'Lv.{level}'
            self.text((x+82,yy+45),desc,16,MUTED,False,w-98)
            self.pill((x+w-94,yy+13),badge,GOLD,17,'#463d2d',11)
            details=dict(item,description=(item.get('description') or item.get('effect','')) + (f"；下一次：{item.get('next_effect')}（{cost} 星币）" if cost is not None and item.get('next_effect') else ''))
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
            rules=(f'v{public_integer(roll.get("rules_version"),5,6) or 5} 低骰'
                   if percentile_rules(roll) else roll_rules_label(roll))
            self.text((tx,yy+43),f'{rules} · {stage} · {roll.get("customer_name") or "旅客"} · {roll.get("item_name") or "旧物"}',15,INK,False,w-105)
            self.text((tx,yy+70),roll_math(roll),14,MUTED,False,w-105)
            self.hits.append(((x,yy,x+w,yy+rowh-8),('inspect',dict(roll,_view='roll'))))
        if not rolls:
            self.text((x+16,y+16),'还没有公开骰点',23,GOLD,True,w-32)
            self.text((x+16,y+54),'店主下次报价后，真实判定会留在这里',18,MUTED,False,w-32,2)
        self.pagination((x,y+h-27,w,27),page,pages)

    def codex(self, box, o):
        codex=as_dict(o.get('codex'))
        if not as_list(codex.get('entries')):
            return self.items(box,o,True)
        x,y,w,h=box
        entries=[as_dict(e) for e in codex['entries']]
        entries.sort(key=lambda e:(not bool(e.get('collected')),not bool(e.get('discovered'))))
        self.text((x+2,y+5),'旧物图鉴',22,INK,True)
        self.text((x+w-2,y+10),f"发现 {codex.get('discovered',0)}/{codex.get('total',len(entries))} · 珍藏 {codex.get('collected',0)}",17,MUTED,anchor='rt')
        per_page=max(1,int((h-80)/89));pages=max(1,math.ceil(len(entries)/per_page));page=self.page%pages;self.page_count=pages
        for i,item in enumerate(entries[page*per_page:(page+1)*per_page]):
            yy=y+45+i*89
            found=item.get('discovered');collected=item.get('collected')
            self.rect((x,yy,x+w,yy+80),PANEL,14)
            art=dict(item)
            if not found:art['color']='#68817d'
            self.item_art(x+10,yy+9,61,art)
            self.text((x+82,yy+11),item.get('name','未知旧物'),21,INK if found else MUTED,True,w-205)
            self.text((x+w-16,yy+15),'已珍藏' if collected else '已发现' if found else '待寻访',17,GOLD if collected else TEAL if found else MUTED,anchor='rt')
            self.text((x+82,yy+43),item.get('description',''),16,MUTED,False,w-101)
            self.hits.append(((x,yy,x+w,yy+80),('inspect',item)))
        self.pagination((x,y+h-28,w,28),page,pages)

    def visitors(self, box, o):
        x,y,w,h=box
        visitors=[as_dict(v) for v in as_list(o.get('visitors'))]
        walkins=public_walkins(o.get('walkins')) if number(o.get('version')) >= 6 else {}
        waiting=sum(v.get('status') in ('waiting','negotiating') for v in visitors)
        if walkins:
            budget=walkins.get('budget_range')
            visitors.insert(0,{'name':'普通散客','_view':'walkins','walkins':walkins,
                              'role':f'公开预算 {budget[0]}–{budget[1]} 星币' if budget else '等待公开预算范围',
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
            desc=str(v.get('preference_label') or '')+(f"。公开预算 {budget[0]}–{budget[-1]} 星币。" if len(budget)>1 else '')
            self.hits.append(((x,yy,x+w,yy+99),('inspect',dict(v,description=desc))))
        if not visitors:self.text((x+18,y+65),'门口风铃静静响，下一位旅客还在路上',20,MUTED,False,w-36,2)
        self.pagination((x,y+h-28,w,28),page,pages)

    def detail_card(self, item):
        if item.get('_view')=='roll':return self.roll_detail(item)
        if item.get('_view')=='negotiation':return self.bargaining_detail(item)
        if item.get('_view')=='sale':return self.sale_detail(item)
        if item.get('_view')=='walkins':return self.walkins_detail(item)
        overlay=Image.new('RGBA',self.image.size,(6,16,24,210))
        self.image=Image.alpha_composite(self.image.convert('RGBA'),overlay).convert('RGB')
        self.draw=ImageDraw.Draw(self.image)
        w=min(self.W-76,670);h=474;x=(self.W-w)/2;y=(self.H-h)/2
        self.rect((x,y,x+w,y+h),'#263d45',25,'#7f9989',2)
        self.hits=[((0,0,self.W,self.H),('close',None))]
        self.text((x+28,y+24),'旧物档案',19,TEAL,True)
        self.text((x+w-28,y+24),'点击任意处返回 ×',17,MUTED,anchor='rt')
        self.item_art(x+w/2-64,y+71,128,item)
        self.text((x+w/2,y+220),item.get('name','小店档案'),32,INK,True,w-50,1,anchor='mt')
        self.text((x+31,y+284),item.get('description') or '这件旧物的故事，还在慢慢展开。',23,MUTED,False,w-62,5)

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
            self.text((x+24,y+339),f'公开预算 {budget[0]}–{budget[1]} 星币' if budget else '等待公开预算范围',18,GOLD,False,w-48)
            maximum=option.get('max_counter_ask')
            cap=(f'还价标价范围：2–{maximum} 星币' if maximum is not None and maximum>=2
                 else '没有合法还价标价空间' if maximum is not None else '等待公开还价标价上限')
            self.text((x+24,y+373),cap,18,INK,True,w-48)
            self.text((x+24,y+404),'须同时不高于参考价的125%及公开预算上限',16,MUTED,False,w-48,2)
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
            self.text((x+24,y+738),'若直接离店：收入0，货物留下\n还价资格非成交保证；初次精确成功率不公开',16,MUTED,False,w-48,2)
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
        self.text((x+24,y+529),'预算仅公布范围，不保证买得起标价；01仍可奇迹成交。',18,GOLD,False,w-48,3)
        self.text((x+24,y+h-35),'在货架点击旧物，可逐位查看出售条件',16,MUTED,False,w-48)

    def roll_detail(self, source):
        roll=public_roll(source)
        overlay=Image.new('RGBA',self.image.size,(6,16,24,220))
        self.image=Image.alpha_composite(self.image.convert('RGBA'),overlay).convert('RGB');self.draw=ImageDraw.Draw(self.image)
        w=min(self.W-52,710);h=min(self.H-100,780);x=(self.W-w)/2;y=(self.H-h)/2
        pending=as_dict(source.get('negotiation'))
        label,color=roll_status(roll,pending)
        self.rect((x,y,x+w,y+h),'#263d45',25,color,2)
        self.hits=[((0,0,self.W,self.H),('close',None))]
        self.text((x+24,y+24),'演示数据 · 骰子记录' if self.demo else '已判定的骰子记录',19,TEAL,True,w-145)
        self.text((x+w-24,y+27),'点击返回 ×',16,MUTED,anchor='rt')
        self.roll_art(x+w/2-72,y+73,144,roll,color)
        self.text((x+w/2,y+222),roll_rules_label(roll),16,MUTED,False,w-54,anchor='mt')
        self.text((x+w/2,y+245),label,30,color,True,w-40,anchor='mt')
        self.text((x+27,y+301),f'第 {int(number(roll.get("day"),1))} 天 · {"最终议价" if roll.get("stage")=="final" else "初次报价"}',19,MUTED,False,w-54)
        self.text((x+27,y+338),f'{roll.get("customer_name") or "旅客"} · {roll.get("item_name") or "旧物"}',22,INK,True,w-54)
        self.text((x+27,y+376),f'公开报价 {int(number(roll.get("price"))):,} 星币',23,GOLD,True,w-54)
        self.text((x+27,y+421),roll_math(roll),21,INK,True,w-54)
        modifiers=[as_dict(v) for v in as_list(roll.get('modifiers'))]
        unit='百分点' if percentile_rules(roll) else ''
        pieces=[f'{v.get("label", "修正")} {number(v.get("value")):+g}{unit}' for v in modifiers]
        if has_roll_breakdown(roll):
            self.text((x+27,y+462),dc_breakdown(roll),18,INK,True,w-54)
            chance=percentile_chance_text(roll.get('threshold')) if percentile_rules(roll) else needed_raw_text(number(roll.get('target'))-number(roll.get('modifier')))
            self.text((x+27,y+493),chance,17,INK,False,w-54,2)
            self.text((x+27,y+542),' · '.join(pieces) or '没有公开修正项',16,MUTED,False,w-54,2)
            self.text((x+27,y+593),roll.get('explanation') or '此处只回看已经完成的公开判定，不会再次掷骰。',17,MUTED,False,w-54,3)
        else:
            self.text((x+27,y+467),' · '.join(pieces) or '没有公开修正项',17,MUTED,False,w-54,2)
            self.text((x+27,y+528),roll.get('explanation') or '此处只回看已经完成的公开判定，不会再次掷骰。',18,MUTED,False,w-54,3)
        pending=as_dict(source.get('negotiation'))
        if pending:
            self.text((x+27,y+612),f'还价 {int(number(pending.get("counter_offer"))):,} 星币 · 待店主决定',20,LILAC,True,w-54)
            self.text((x+27,y+647),'接受 / 谢绝免费；最后报价消耗 1 体力',17,INK,False,w-54,2)
        self.line([(x+27,y+h-76),(x+w-27,y+h-76)],LINE,1)
        rules=('01 必成：1% · 00 + 0 = 100 必败：1%' if percentile_rules(roll)
               else '单次天然20：5%奇迹成交 · 天然1：直接告辞')
        self.text((x+27,y+h-60),rules,16,GOLD,False,w-54,2)
        footer=('CoC 启发简化房规 · 非完整官方规则 · 只读' if percentile_rules(roll)
                else '只读回看 · 不会再次掷骰或完成交易')
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
        current_roll=public_roll(o.get('last_roll') or as_dict(o.get('last_event')).get('roll'))
        extra=126 if has_bargaining_preview(o.get('negotiation')) else (32 if has_roll_breakdown(current_roll) and (as_dict(as_dict(o.get('last_event')).get('roll')) or not as_dict(o.get('last_event')).get('type')) else 0)
        self.W,self.H=(1320,940) if wide else ((520,max(1100,round(height/width*520))) if narrow else (760,1240))
        if narrow and extra:self.H=max(self.H,1100+max(0,extra-48))
        self.image=Image.new('RGB',(self.W,self.H),BG); self.draw=ImageDraw.Draw(self.image)
        self.demo=bool(demo);self.journal_mode='rolls' if journal_mode=='rolls' else 'events'
        self.words=[];self.hits=[];self.tab=tab if tab in dict(TABS) else 'shelf';self.page=max(0,page);self.page_count=1
        o=as_dict(observation)
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
            self.content((32,914+shift,696,282-shift),o)
        self.line([(32,self.H-33),(self.W-32,self.H-33)],LINE,1)
        status=error or ('演示预览 · 未推进游戏' if self.demo else '首周已结算 · 等店长继续' if o.get('phase')=='week_summary' else '星港只读观战 · 纯虚拟星币')
        self.text((32,self.H-24),status,14,RED if error else MUTED)
        self.text((self.W-32,self.H-24),'F11 全屏' if narrow else '1–5 切换展台  ·  F11 全屏',13,MUTED,anchor='rt')
        # A small, non-blocking ending label is compatible with old public files.
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
            elif action[0]=='close':self.detail=None;self.last_signature=None

    def refresh_detail(self):
        """A projection refresh must not leave a live quote looking current."""
        detail=as_dict(self.detail)
        pending=as_dict(as_dict(self.reader.observation).get('negotiation'))
        if detail.get('_view')=='sale':
            observation=as_dict(self.reader.observation)
            item=next((v for v in as_list(observation.get('inventory'))
                       if as_dict(v) and v.get('id')==detail.get('id')),None)
            self.detail=public_sale_detail(item,observation.get('walkins'),detail.get('_sale_page')) if item else None
        elif detail.get('_view')=='walkins':
            visits=public_walkins(as_dict(self.reader.observation).get('walkins'))
            self.detail=dict(_view='walkins',walkins=visits) if visits else None
        elif detail.get('_view')=='negotiation':
            previous=as_dict(detail.get('negotiation'))
            if not pending or pending.get('item_id')!=previous.get('item_id'):
                self.detail=None
            else:
                self.detail=dict(_view='negotiation',negotiation=public_negotiation(pending),
                                 last_roll=public_roll(as_dict(self.reader.observation).get('last_roll')))
        elif detail.get('_view')=='roll' and detail.get('negotiation'):
            if not pending or pending.get('item_id')!=detail.get('item_id'):
                self.detail=dict(detail,negotiation={})

    def tick(self):
        if self.reader.poll():self.refresh_detail()
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
    parser=argparse.ArgumentParser(description='星屑杂货铺：双 D10 百分骰低骰房规；兼容原 D20 记录，只读观战')
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
