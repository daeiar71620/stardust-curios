#!/usr/bin/env python3
"""星屑杂货铺 — persistent, standard-library-only ongoing shop simulation.

The GUI must read the public observation, never the private save. All mutations
run through this CLI (or GameStore.execute), under an advisory file lock.
"""
from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import random
import secrets
import sys
import tempfile
from contextlib import contextmanager

VERSION = 5
TOTAL_DAYS = 7
DEFAULT_SAVE = Path(__file__).resolve().with_name("save.json")
GOAL = {"credits": 650, "collection": 2}
OPERATING_COST = 14
KINDS = {"tool": "工具", "artifact": "奇物", "bot": "机器人", "plant": "植物", "signal": "信号"}
RARITIES = {"common": "普通", "rare": "稀有", "legendary": "传说"}
COLORS = {"common": "#8ed4cb", "rare": "#b7a2ff", "legendary": "#ffd17a"}
CATALOG = [
    ("wrench", "折叠离子扳手", "common", "tool", 88, "一把能伸进四维螺孔的扳手。握柄留着某位机修师的名字。"),
    ("lamp", "重力手电", "common", "tool", 96, "照亮的地方会稍微变轻。请勿对着自己的鞋。"),
    ("coffee", "轨道咖啡壶", "common", "artifact", 105, "在失重时也能倒出完美一杯，不过上一任船长没洗它。"),
    ("cleaner", "哼歌清洁球", "common", "bot", 100, "会一边吸尘一边唱走调的远航民谣。"),
    ("moss", "瓶装月光苔", "common", "plant", 88, "关灯后发出湖蓝色微光，偶尔照出不存在的月亮。"),
    ("map", "二手星图仪", "common", "signal", 105, "标了很多餐馆和一个写着「千万别去」的小行星。"),
    ("music", "彗星玻璃八音盒", "rare", "artifact", 210, "每次彗星经过，它会多记住一个音符。"),
    ("welder", "逆相位焊笔", "rare", "tool", 195, "能焊好昨天断掉的零件，但说明书从明天开始写。"),
    ("bee", "迷路送信蜂", "rare", "bot", 225, "胸腔里藏着一张过期两百年的生日贺卡。"),
    ("seed", "低语星籽", "rare", "plant", 205, "靠近时能听到风穿过尚未长出的枝叶。"),
    ("dawn", "微型人造黎明", "legendary", "artifact", 480, "装在旧灯泡里的第一缕晨光，来自一颗已经熄灭的太阳。"),
    ("letter", "最后一封地球来信", "legendary", "signal", 520, "封面只有两个字：回家。信号仍在缓慢闪烁。"),
    ("compass", "逆风磁罗盘", "common", "signal", 93, "它总指向上一次说过再见的地方。"),
    ("kettle", "口袋气象瓶", "common", "artifact", 98, "瓶口飘出小小的天气预报，今天有糖霜雪。"),
    ("sprout", "慢半拍含羞草", "common", "plant", 91, "摸它一下，要等三秒钟才会害羞。"),
    ("snail", "快递蜗牛机", "common", "bot", 104, "从不超速，也从不投错门牌。"),
    ("clock", "午睡时间匣", "rare", "artifact", 230, "能把午后最安静的十分钟装进抽屉。"),
    ("needle", "真空缝星针", "rare", "tool", 215, "旧宇航服与小小的愿望，都能慢慢缝好。"),
    ("fern", "极光玻璃蕨", "rare", "plant", 225, "叶脉里流动着北方天空的颜色。"),
    ("radio", "潮汐回声电台", "rare", "signal", 240, "退潮时能收听一颗海洋星球的夜间节目。"),
    ("cat", "发条守夜猫", "rare", "bot", 235, "每天巡视货架，偶尔把价签拨到地上。"),
    ("hammer", "微型行星锻锤", "legendary", "tool", 500, "轻敲一下，火星便绕着锤头组成小小星系。"),
    ("tree", "永昼盆栽", "legendary", "plant", 490, "一棵不用等日出的树，也在等待一个家。"),
    ("whale", "袖珍巡航鲸", "legendary", "bot", 540, "会绕着店里的灯慢慢游，唱一首没有结尾的歌。"),
]
CATALOG_BY_ID = {item[0]: item for item in CATALOG}
SUPPLIERS = {
    "salvage": {"id": "salvage", "name": "废轨回收站", "cost": 48, "stock": 4,
                "description": "平价漂流箱 · 普通 74% / 稀有 24% / 传说 2% · 品相 35–88"},
    "curated": {"id": "curated", "name": "夜航商队", "cost": 110, "stock": 2,
                "description": "精选封存箱 · 普通 28% / 稀有 61% / 传说 11% · 品相 48–96"},
}
UPGRADE_RULES = {
    "workbench": {"name": "工作台", "costs": [70, 110, 260], "effects": ["基础修理：失手24%", "修理费减18%，失手14%", "修理费减36%，失手7%", "修理费减54%，失手3%"]},
    "shelf": {"name": "货架", "costs": [65, 100, 240], "effects": ["7格货架 / 每日12精力", "10格货架 / 每日13精力", "13格货架 / 每日14精力", "16格货架 / 每日15精力"]},
    "display": {"name": "展示柜", "costs": [120, 230, 420], "effects": ["朴素展示", "成交基础率+5百分点", "成交基础率+10百分点 / 多1位访客", "成交基础率+15百分点 / 多1位访客"]},
}
SET_RULES = {
    "tool": ("星港修理铺", "收藏3种工具，所有修理费再减4星币"),
    "artifact": ("小小宇宙馆", "收藏3种奇物，所有成交基础率+5百分点"),
    "bot": ("值夜小分队", "收藏3种机器人，每日精力+1"),
    "plant": ("窗边温室", "收藏3种植物，每日维护费减4星币"),
    "signal": ("远方的朋友", "收藏3种信号物品，回收箱每日供货+1"),
}
EVENTS = [
    {"id": "calm", "title": "平静靠港日", "description": "航道平稳，适合整理库存和照顾收藏。", "sale_multiplier": 1.0, "salvage_discount": 0, "repair_discount": 0, "cost_delta": 0, "energy_delta": 0},
    {"id": "meteor", "title": "流星回收潮", "description": "回收箱便宜8星币；忙碌的搬运让每日精力少1点。", "sale_multiplier": 1.0, "salvage_discount": 8, "repair_discount": 0, "cost_delta": 0, "energy_delta": -1},
    {"id": "festival", "title": "星灯夜市", "description": "成交基础率+10百分点；照明维护费多6星币。", "sale_multiplier": 1.12, "salvage_discount": 0, "repair_discount": 0, "cost_delta": 6, "energy_delta": 0},
    {"id": "workshop", "title": "机修师互助日", "description": "修理费减6星币；适合给有潜力的旧物第二次机会。", "sale_multiplier": 1.0, "salvage_discount": 0, "repair_discount": 6, "cost_delta": 0, "energy_delta": 0},
    {"id": "fog", "title": "星云浓雾", "description": "来客更谨慎，成交基础率-10百分点；港务处减免4星币维护费。", "sale_multiplier": 0.90, "salvage_discount": 0, "repair_discount": 0, "cost_delta": -4, "energy_delta": 0},
    {"id": "tailwind", "title": "顺风补给日", "description": "物流顺畅，每日精力+1，今天可以多做一件事。", "sale_multiplier": 1.0, "salvage_discount": 0, "repair_discount": 0, "cost_delta": 0, "energy_delta": 1},
]
CUSTOMERS = [
    ("mira", "米拉", "星港机修师", "tool", 45, 130, 340),
    ("nox", "诺克斯", "旧梦收藏家", "artifact", 65, 180, 620),
    ("pip", "皮普", "机器人护理员", "bot", 40, 150, 430),
    ("luna", "露娜", "轨道园艺师", "plant", 60, 160, 440),
    ("echo", "回声", "远航信号员", "signal", 55, 170, 600),
    ("sol", "索尔", "随船修补匠", "tool", 30, 100, 260),
    ("ayu", "阿鱼", "夜航讲故事的人", "artifact", 35, 120, 390),
    ("bo", "波波", "流浪机偶导演", "bot", 70, 220, 650),
]
MILESTONES = [
    {"id": "first_week", "title": "首周站稳脚跟", "description": "第7天闭店后检查；未达标也能继续，之后补齐。", "targets": {"credits": 650, "collection": 2}},
    {"id": "neighborhood", "title": "街区熟面孔", "description": "积累客源，拓展收藏，并为店铺作长远投资。", "targets": {"credits": 1400, "collection": 5, "reputation": 12, "upgrades": 2}},
    {"id": "lighthouse", "title": "夜航灯塔", "description": "让旅客为了这间小店，愿意在星港多停一天。", "targets": {"credits": 2800, "collection": 9, "reputation": 25, "upgrades": 4}},
    {"id": "landmark", "title": "星港地标", "description": "经营与收藏都留下自己的名字。", "targets": {"credits": 5000, "collection": 15, "reputation": 40, "upgrades": 6}},
]
HELP = """星屑杂货铺 · 七天首周，长期经营
首周目标：第7天闭店扣费后现金650星币、收藏2种。首周结算不会强制终止经营。
命令（python3 engine.py [--save 路径] 命令）：
  new / status / market / codex / visitors
  buy salvage|curated       购买已封存盲箱，1精力
  open C001                 开箱，1精力
  inspect I001              查看公开估值，不改变运气
  repair I001               修理，2精力，每件最多2次、每天1次
  price I001 120            免费定价，1–9999整数
  sell I001 [顾客ID]         初次双D10百分骰检定，1精力；省略顾客为旅客
  accept I001               接受客人的唯一还价，免费且不掷骰
  decline I001              谢绝还价，免费且结束当天接待
  preview-offer I001 120    只读风险预览；不消耗精力或随机数
  offer I001 120            客人还价 < 最终报价 < 初次标价；1精力，最后一次双D10百分骰
  collect I001              永久收藏，1精力；3种同类收藏解锁套装效果
  upgrade workbench|shelf|display  升级，2精力，每项3级
  endday                    支付当日维护费，推进日期
  continue                  首周结算后明确继续到第8天；不重开、不再扣第7天费用
  import-v4 原存档路径       只读还价版并复制至新的 --save 路径；历史D20不重判
  import-v3 原存档路径       只读掷骰版并复制至新的 --save 路径；不重掷
  import-v2 原存档路径       只读扩展版并升级至新的 --save 路径；原文件不变
  import-v1 原存档路径       只读旧版并迁移至新的 --save 路径；原文件不变
  restart --confirm         明确清空当前这一个存档并开新局
  help                      查看命令

24种货物、每日事件、偏好顾客、5种收藏套装和持续阶段目标。
现金用于经营、修理、扩店；收藏不可卖回。顾客预算与成交价有不确定性。
每天每件货物只有一场接待，最多初次与最终两骰；每位特邀顾客只接待一次。
双D10分别取十位00–90和个位0–9；00+0记100。掷低点：01大成功、100大失败。
01一见钟情突破普通意愿与预算，按合法报价成交；100立即结束接待。
最终成功率按相对还价涨幅下降，无固定拒价惩罚。这是CoC启发的简化房规。
普通失败给一次还价，待谈时锁定该货；endday自动谢绝未完成谈判。
公开observation不包含箱内货物、真实基价、买家确切预算或随机状态。
"""


class GameError(Exception):
    """A user-correctable command, save, or resource error."""


class CommittedWriteError(OSError):
    """The replacement happened, but synchronizing the containing directory failed."""


def _tuple_tree(value):
    return tuple(_tuple_tree(v) for v in value) if isinstance(value, list) else value


def _rng(state):
    rng = random.Random()
    try:
        rng.setstate(_tuple_tree(state["rng"]))
    except (KeyError, TypeError, ValueError, IndexError, OverflowError) as exc:
        raise GameError("存档随机状态损坏；请保留原文件，勿直接覆盖。") from exc
    return rng


def _daily_demand(rng):
    kind = rng.choice(list(KINDS))
    multiplier = rng.choice([1.25, 1.35, 1.45])
    return {"label": f"{KINDS[kind]}收藏热 · +{round((multiplier - 1) * 100)}%", "kind": kind, "multiplier": multiplier}


def _event(state, event_type, title, text, item=None):
    state["event_seq"] += 1
    state["last_event"] = {"seq": state["event_seq"], "type": event_type, "title": title, "text": text,
                           "item": _public_item(state, item) if item is not None else None}
    state["log"].append({"day": state["day"], "text": text})
    state["log"] = state["log"][-60:]


def _has_set(state, kind):
    return len({i["catalog_id"] for i in state["collection"] if i["kind"] == kind}) >= 3


def _capacity(state):
    return 7 + 3 * state["upgrades"]["shelf"]


def _max_energy(state):
    return 12 + state["upgrades"]["shelf"] + int(_has_set(state, "bot")) + state["daily_event"]["energy_delta"]


def _operating_cost(state):
    return max(4, OPERATING_COST + state["daily_event"]["cost_delta"] - 4 * int(_has_set(state, "plant")))


def _supplier_cost(state, supplier):
    return SUPPLIERS[supplier]["cost"] - (state["daily_event"]["salvage_discount"] if supplier == "salvage" else 0)


def _stock_limit(state, supplier):
    return SUPPLIERS[supplier]["stock"] + int(supplier == "salvage" and _has_set(state, "signal"))


def _make_visitors(rng, state):
    visitors = []
    for profile in rng.sample(CUSTOMERS, 3 + int(state["upgrades"]["display"] >= 2)):
        key, name, role, kind, condition, low, high = profile
        visitors.append({"id": key, "name": name, "role": role, "preferred_kind": kind,
                         "preference_label": f"偏爱{KINDS[kind]}，品相{condition}%以上更喜欢",
                         "min_condition": condition, "budget_range": [low, high], "premium": 1.25,
                         "status": "waiting", "budget": rng.randint(low, high)})
    return visitors


def _start_day(state, rng):
    state["day"] += 1
    state["daily_event"] = copy.deepcopy(rng.choice([e for e in EVENTS if e["id"] != state["daily_event"]["id"]]))
    state["demand"] = _daily_demand(rng)
    state["supplier_stock"] = {k: _stock_limit(state, k) for k in SUPPLIERS}
    state["visitors"] = _make_visitors(rng, state)
    state["energy"] = _max_energy(state)


def _next_milestone(state):
    completed = len(state["milestones"])
    if completed < len(MILESTONES):
        return MILESTONES[completed]
    voyage = completed - len(MILESTONES) + 1
    return {"id": f"voyage_{voyage}", "title": f"星海长航 · 第{voyage}章",
            "description": "星港的故事继续；目标达成后仍可一直经营。",
            "targets": {"credits": 5000 + 3000 * voyage, "collection": min(len(CATALOG), 15 + 2 * voyage), "reputation": min(99, 40 + 10 * voyage)}}


def _goal_values(state):
    return {"credits": state["credits"], "collection": len(state["collection"]),
            "reputation": state["reputation"], "upgrades": sum(state["upgrades"].values())}


def _check_milestones(state):
    if state["first_week_result"] == "pending" or state["phase"] == "lost":
        return
    # No random rewards or free cash: earned titles persist without a reroll opportunity.
    for _ in range(len(MILESTONES) + 1):
        milestone = _next_milestone(state)
        values = _goal_values(state)
        if not all(values[key] >= target for key, target in milestone["targets"].items()):
            break
        state["milestones"].append({"id": milestone["id"], "title": milestone["title"], "day": state["day"]})
        state["log"].append({"day": state["day"], "text": f"阶段达成：{milestone['title']}。新的长期目标已开启。"})
        state["log"] = state["log"][-60:]


def new_state(seed=None):
    """Seed is only an in-process test aid; the public CLI has no seed/reroll flag."""
    rng = random.Random(secrets.randbits(128) if seed is None else seed)
    state = {
        "version": VERSION, "revision": 0, "day": 1, "credits": 260, "reputation": 0,
        "energy": 12, "phase": "active", "inventory": [], "crates": [], "collection": [],
        "upgrades": {"workbench": 0, "shelf": 0, "display": 0}, "demand": _daily_demand(rng),
        "supplier_stock": {key: val["stock"] for key, val in SUPPLIERS.items()},
        "next_crate": 1, "next_item": 1, "event_seq": 0, "last_event": None, "log": [],
        "daily_event": copy.deepcopy(EVENTS[0]), "visitors": [], "discovered": [],
        "first_week_result": "pending", "milestones": [],
        "stats": {"crates_opened": 0, "sales_count": 0, "gross_earnings": 0, "days_traded": 0},
        "migration": None, "engine_upgrade": None,
        "negotiation": None, "roll_seq": 0, "roll_history": [],
    }
    state["visitors"] = _make_visitors(rng, state)
    state["rng"] = rng.getstate()
    _event(state, "start", "卷帘门升起", "第1天开张！先争取首周650星币与2种收藏，再把小店经营成星港地标。")
    return state


def _actual_value(state, item):
    demand = state["demand"]["multiplier"] if item["kind"] == state["demand"]["kind"] else 1.0
    return item["base_value"] * (0.30 + item["condition"] * 0.007) * demand


def _reference_value(state, item):
    # Public estimates use catalog reference value, not the hidden per-item roll.
    # Otherwise the two rounded interval endpoints can reveal the exact hidden base.
    demand = state["demand"]["multiplier"] if item["kind"] == state["demand"]["kind"] else 1.0
    return CATALOG_BY_ID[item["catalog_id"]][4] * (0.30 + item["condition"] * 0.007) * demand


def _repair_cost(state, item):
    base = {"common": 15, "rare": 28, "legendary": 50}[item["rarity"]]
    return max(3, round(base * (1.0 - 0.18 * state["upgrades"]["workbench"]))
               - state["daily_event"]["repair_discount"] - 4 * int(_has_set(state, "tool")))


def _public_visitors(state):
    return [{key: copy.deepcopy(visitor[key]) for key in ("id", "name", "role", "preferred_kind", "preference_label", "min_condition", "budget_range", "premium", "status")}
            | {"attempted_today": visitor["status"] != "waiting"} for visitor in state["visitors"]]


def _public_codex(state):
    collected = {i["catalog_id"] for i in state["collection"]}
    entries = [{"name": row[1], "rarity": row[2], "kind": row[3], "description": row[5],
                "discovered": row[0] in state["discovered"], "collected": row[0] in collected} for row in CATALOG]
    return {"total": len(CATALOG), "discovered": len(state["discovered"]), "collected": len(collected), "entries": entries}


def _public_campaign(state):
    milestone = _next_milestone(state)
    values = _goal_values(state)
    labels = {"credits": "现金", "collection": "不同收藏", "reputation": "口碑", "upgrades": "设施总等级"}
    goals = [{"key": key, "label": labels[key], "current": values[key], "target": target, "met": values[key] >= target}
             for key, target in milestone["targets"].items()]
    return {"title": "七天首周" if state["first_week_result"] == "pending" else "星港长期经营",
            "stage_index": len(state["milestones"]), "first_week_result": state["first_week_result"],
            "completed_milestones": copy.deepcopy(state["milestones"]),
            "next_milestone": {key: milestone[key] for key in ("id", "title", "description")} | {"goals": goals, "ready": all(g["met"] for g in goals)},
            "can_continue": state["phase"] == "week_summary", "continue_command": "continue" if state["phase"] == "week_summary" else None,
            "unlimited": True}


def _public_upgrades(state):
    result = []
    for key, rule in UPGRADE_RULES.items():
        level = state["upgrades"][key]
        result.append({"id": key, "name": rule["name"], "level": level, "max_level": 3,
                       "next_cost": rule["costs"][level] if level < 3 else None,
                       "effect": rule["effects"][level], "next_effect": rule["effects"][level + 1] if level < 3 else None})
    return result


def _public_item(state, item):
    # Deliberately whitelisted: no catalog base value, crate contents, or RNG.
    estimate = _reference_value(state, item)
    return {
        "id": item["id"], "name": item["name"], "rarity": item["rarity"], "kind": item["kind"],
        "color": COLORS[item["rarity"]], "condition": item["condition"],
        "value_estimate": [max(1, int(estimate * 0.82)), max(2, math.ceil(estimate * 1.20))],
        "repair_cost": _repair_cost(state, item), "price": item["price"], "origin": item["origin"],
        "description": item["description"], "collected": item.get("collected", False),
        "sale_attempted_today": item.get("last_sale_day", 0) == state["day"],
        "repair_attempted_today": item.get("last_repair_day", 0) == state["day"],
        "repairs_remaining": max(0, 2 - item.get("repairs", 0)),
        "negotiating": bool(state["negotiation"] and state["negotiation"]["item_id"] == item["id"]),
    }


def observation(state):
    upgrades = _public_upgrades(state)
    return {
        "version": VERSION, "revision": state["revision"], "day": state["day"], "total_days": TOTAL_DAYS,
        "credits": state["credits"], "reputation": state["reputation"], "energy": state["energy"],
        "max_energy": _max_energy(state), "goal": GOAL.copy(), "phase": state["phase"],
        "inventory": [_public_item(state, item) for item in state["inventory"]],
        "crates": [{"id": crate["id"], "supplier": crate["supplier"], "name": crate["name"]} for crate in state["crates"]],
        "collection": [_public_item(state, item) for item in state["collection"]],
        "suppliers": [dict(info, cost=_supplier_cost(state, key), stock=state["supplier_stock"][key]) for key, info in SUPPLIERS.items()],
        "upgrades": copy.deepcopy(state["upgrades"]), "demand": copy.deepcopy(state["demand"]),
        "last_event": copy.deepcopy(state["last_event"]), "log": copy.deepcopy(state["log"]),
        "capacity": _capacity(state), "operating_cost": _operating_cost(state),
        "upgrade_costs": {row["id"]: row["next_cost"] for row in upgrades}, "upgrade_details": upgrades,
        "campaign": _public_campaign(state), "daily_event": copy.deepcopy(state["daily_event"]),
        "visitors": _public_visitors(state), "codex": _public_codex(state),
        "collection_sets": [{"id": kind, "name": value[0], "description": value[1], "required": 3,
                             "current": len({i["catalog_id"] for i in state["collection"] if i["kind"] == kind}),
                             "completed": _has_set(state, kind), "perk": value[1]} for kind, value in SET_RULES.items()],
        "stats": copy.deepcopy(state["stats"]), "migration": copy.deepcopy(state["migration"]),
        "engine_upgrade": copy.deepcopy(state["engine_upgrade"]),
        "negotiation": _public_negotiation(state),
        "last_roll": copy.deepcopy(state["roll_history"][-1]) if state["roll_history"] else None,
        "roll_history": copy.deepcopy(state["roll_history"]),
        "trade_rules": {"die": "D100", "dice": ["D10 tens 00–90", "D10 ones 0–9"],
                        "direction": "roll_low", "zero_zero": 100,
                        "critical": 1, "fumble": 100,
                        "critical_rule": "01一见钟情，突破普通意愿和预算，按合法报价成交",
                        "fumble_rule": "100大失败，本日该货接待立即结束",
                        "house_rules": "CoC启发的简化房规，非官方完整规则",
                        "max_rolls_per_item_day": 2, "price_limit": 9999, "final_offer_energy": 1,
                        "final_offer_rule": "counter_offer < price < original_price",
                        "final_chance_formula": "clamp(1,99,floor(clamp(1,99,70+bonus)*counter/(2*price-counter)))",
                        "initial_chance_formula": "clamp(1,99,floor(60+bonus-50*log2(price/reference))); above hidden budget: 1",
                        "final_budget_rule": "还价已反映预算，最终报价不再施加隐藏预算门槛",
                        "endday": "自动谢绝未完成还价", "miracle_probability": 0.01},
    }


def _require_active(state):
    if state["phase"] != "active":
        raise GameError("首周已结算，请用 continue 明确继续经营。" if state["phase"] == "week_summary" else "本局因维护费不足而结束；可查看收藏，或 restart --confirm 开新局。")


def _spend(state, *, energy=0, credits=0):
    if state["energy"] < energy:
        raise GameError(f"精力不足：需要 {energy} 点，还剩 {state['energy']} 点。请先 endday。")
    if state["credits"] < credits:
        raise GameError(f"星币不足：需要 {credits}，还剩 {state['credits']}。")
    state["energy"] -= energy
    state["credits"] -= credits


def _item(state, item_id):
    for item in state["inventory"]:
        if item["id"] == item_id.upper():
            return item
    raise GameError(f"货架上没有物品 {item_id}；已收藏的物品不能出售或修理。")


def _make_cargo(rng, supplier):
    rarity = rng.choices(["common", "rare", "legendary"], weights=[74, 24, 2] if supplier == "salvage" else [28, 61, 11])[0]
    entry = rng.choice([e for e in CATALOG if e[2] == rarity])
    catalog_id, name, rarity, kind, base, description = entry
    return {"catalog_id": catalog_id, "name": name, "rarity": rarity, "kind": kind,
            "base_value": round(base * rng.uniform(0.92, 1.08)),
            "condition": rng.randint(35, 88) if supplier == "salvage" else rng.randint(48, 96),
            "description": description, "origin": SUPPLIERS[supplier]["name"],
            "collected": False, "repairs": 0, "last_sale_day": 0, "last_repair_day": 0}



def _final_price(pending, raw_price):
    try:
        price = int(raw_price)
    except (ValueError, TypeError) as exc:
        raise GameError("最终报价须为整数，且严格高于客人还价、低于初次标价。") from exc
    if (str(price) != raw_price.strip()
            or not pending["counter_offer"] < price < pending["original_price"]):
        raise GameError("最终报价须严格高于客人还价、低于初次标价；同价不能重掷，可直接 accept 接受还价。")
    return price


def _clamp_chance(value):
    return max(1, min(99, value))


def _final_chance(modifier, counter, price):
    # Integer rational arithmetic: floor(base / (1 + 2 * premium)).
    # No hidden valuation or second budget gate; the quote reflects affordability.
    base = _clamp_chance(70 + modifier)
    return base, _clamp_chance(base * counter // (2 * price - counter))


def _offer_forecast(state, pending, price):
    base, threshold = _final_chance(pending["context"]["modifier"], pending["counter_offer"], price)
    return {"price": price, "basis": "public_counter", "base_chance": base,
            "threshold": threshold, "probability": threshold / 100,
            "premium": (price - pending["counter_offer"]) / pending["counter_offer"],
            "modifier": pending["context"]["modifier"],
            "modifiers": copy.deepcopy(pending["context"]["modifiers"]),
            "critical_probability": 0.01, "fumble_probability": 0.01, "energy_cost": 1,
            "accept_income": pending["counter_offer"], "success_income": price, "failure_income": 0,
            "warning": "精确成功率，仅用公开还价和冻结加值；涨幅越大成功率越低。01必成、100必败；最终失败收入0，不能回头接受旧还价。"}


def _public_negotiation(state):
    pending = state["negotiation"]
    if pending is None:
        return None
    keys = ("item_id", "item_name", "customer_id", "customer_name", "original_price", "counter_offer",
            "rules_version", "origin_rules_version")
    low, high = pending["counter_offer"] + 1, pending["original_price"] - 1
    return {key: copy.deepcopy(pending[key]) for key in keys} | {
        "remaining_offers": 1, "final_offer_energy": 1,
        "final_offer_bounds": {"min": low, "max": high, "available": low <= high},
        "accept_income": pending["counter_offer"], "final_failure_income": 0,
        "preview": dict(_offer_forecast(state, pending, low), suggested=True) if low <= high else None,
        "commands": {"accept": f"accept {pending['item_id']}", "decline": f"decline {pending['item_id']}",
                     "preview": f"preview-offer {pending['item_id']} 金额",
                     "offer": f"offer {pending['item_id']} 金额"}}


def _require_unlocked_item(state, item):
    if state["negotiation"] and state["negotiation"]["item_id"] == item["id"]:
        raise GameError("这件货正在讨价还价；请先 accept、decline 或 offer，不能换价签、修理或收藏。")


def _trade_context(state, item, visitor):
    # Percentage-point bonuses, frozen before the initial pair of digits.
    modifiers = []
    def add(label, value):
        if value:
            modifiers.append({"label": label, "value": value})
    add("口碑", 5 * (min(state["reputation"], 15) // 5))
    add("展示柜", 5 * state["upgrades"]["display"])
    add("奇物收藏套装", 5 * int(_has_set(state, "artifact")))
    event_id = state["daily_event"]["id"]
    add("星灯夜市", 10 if event_id == "festival" else 0)
    add("星云浓雾", -10 if event_id == "fog" else 0)
    if visitor:
        add("顾客偏爱" if item["kind"] == visitor["preferred_kind"] else "偏好不合",
            15 if item["kind"] == visitor["preferred_kind"] else -10)
        add("符合品相期待" if item["condition"] >= visitor["min_condition"] else "品相未达期待",
            5 if item["condition"] >= visitor["min_condition"] else -10)
    return {"reference": _actual_value(state, item), "budget": visitor["budget"] if visitor else None,
            "modifiers": modifiers, "modifier": sum(m["value"] for m in modifiers)}


def _initial_chance(context, price):
    # Native percentile formula, not a rounded conversion of a D20 target.
    # The exact item reference and named buyer budget remain private.
    threshold = _clamp_chance(math.floor(60 + context["modifier"] - 50 * math.log2(price / context["reference"])))
    if context["budget"] is not None and price > context["budget"]:
        return 1
    return threshold


def _counter_offer(context, asking):
    # Same coarse affordability quote as v4, now expressed in percentage points.
    offer = max(1, math.floor(context["reference"] * (0.75 + context["modifier"] / 200) / 10) * 10)
    if context["budget"] is not None:
        offer = min(offer, max(1, context["budget"] // 25 * 20))
    return max(1, min(asking - 1, offer))


def _trade_roll(state, rng, item, visitor, price, context, stage):
    tens, ones = rng.randint(0, 9) * 10, rng.randint(0, 9)
    value = tens + ones or 100
    counter = state["negotiation"]["counter_offer"] if stage == "final" else None
    base, threshold = (_final_chance(context["modifier"], counter, price) if stage == "final"
                       else (None, _initial_chance(context, price)))
    success = value == 1 or (value != 100 and value <= threshold)
    outcome = "miracle" if value == 1 else "fumble" if value == 100 else "success" if success else "failure"
    explanation = {"miracle": "01 · 一见钟情！大成功突破普通意愿与预算，按本次合法报价成交。",
                   "fumble": "100 · 大失败，客人告辞；今日这件货接待结束。",
                   "success": "百分骰点数不高于成功阈值，正常成交。",
                   "failure": "百分骰点数高于成功阈值。"}[outcome]
    if stage == "final":
        explanation += f" 基础率{base}%，还价上浮{(price-counter)/counter:.1%}，成功阈值{threshold}。"
    if threshold == 1:
        explanation += " 这次报价只有01能成交，成功率1%。"
    state["roll_seq"] += 1
    record = {"id": state["roll_seq"], "day": state["day"], "item_id": item["id"], "item_name": item["name"],
              "customer_id": visitor["id"] if visitor else None, "customer_name": visitor["name"] if visitor else "旅客",
              "stage": stage, "die": "D100", "tens": tens, "ones": ones, "roll": value,
              "modifier": context["modifier"], "modifiers": copy.deepcopy(context["modifiers"]),
              "threshold": threshold, "probability": threshold / 100, "base_chance": base,
              "premium": (price-counter)/counter if counter is not None else None,
              "rules_version": VERSION, "counter_offer": counter,
              "success": success, "outcome": outcome, "price": price, "explanation": explanation}
    state["roll_history"].append(record)
    state["roll_history"] = state["roll_history"][-60:]
    return record


def _sale_settle(state, item, visitor, price):
    state["credits"] += price
    reputation = (2 if item["rarity"] == "legendary" else 1) + int(visitor is not None and item["kind"] == visitor["preferred_kind"])
    state["reputation"] = min(99, state["reputation"] + reputation)
    state["stats"]["sales_count"] += 1
    state["stats"]["gross_earnings"] += price
    item["price"] = price
    state["inventory"].remove(item)
    if visitor:
        visitor["status"] = "bought"
    return reputation


def _close_negotiation(state):
    pending = state["negotiation"]
    if pending:
        visitor = next((v for v in state["visitors"] if v["id"] == pending["customer_id"]), None)
        if visitor:
            visitor["status"] = "left"
        state["negotiation"] = None


def _roll_text(roll):
    return f"双D10：{roll['tens']:02d} + {roll['ones']} → {roll['roll']:02d}；掷低点 ≤ {roll['threshold']}，成功率{roll['threshold']}%。{roll['explanation']}"

def apply_command(state, command, args):
    """Mutate an already-copied state. Errors must be discarded by its caller."""
    if command in {"status", "market", "inspect", "codex", "visitors"}:
        return
    rng = _rng(state)
    if command == "continue":
        if state["phase"] != "week_summary":
            raise GameError("只有首周结算画面可以 continue；经营中请 endday。")
        state["phase"] = "active"
        _start_day(state, rng)
        _event(state, "day", "第8天 · 故事继续", "保留全部现金、库存、收藏与设施，开始长期经营。首周维护费不会重复扣除。")
        state["rng"] = rng.getstate()
        _check_milestones(state)
        return
    _require_active(state)
    if command == "buy":
        supplier = args[0]
        if supplier not in SUPPLIERS:
            raise GameError("未知供应商；请选择 salvage 或 curated。")
        if state["supplier_stock"][supplier] <= 0:
            raise GameError("这位供应商今天已售罄，明天会补货。")
        if len(state["inventory"]) + len(state["crates"]) >= _capacity(state):
            raise GameError("货架已满；出售、收藏物品，或升级 shelf 后再采购。")
        _spend(state, energy=1, credits=_supplier_cost(state, supplier))
        # All hidden cargo properties are committed now, before the box is opened.
        crate = {"id": f"C{state['next_crate']:03d}", "supplier": supplier,
                 "name": "漂流回收箱" if supplier == "salvage" else "夜航封存箱", "cargo": _make_cargo(rng, supplier)}
        state["next_crate"] += 1
        state["supplier_stock"][supplier] -= 1
        state["crates"].append(crate)
        _event(state, "buy", "新货靠港", f"花费 {_supplier_cost(state, supplier)} 星币购入 {crate['name']} {crate['id']}。箱内货物已封存。")
    elif command == "open":
        crate = next((c for c in state["crates"] if c["id"] == args[0].upper()), None)
        if crate is None:
            raise GameError(f"没有未开封的箱子 {args[0]}。")
        _spend(state, energy=1)
        item = copy.deepcopy(crate["cargo"])
        item["id"] = f"I{state['next_item']:03d}"
        state["next_item"] += 1
        item["price"] = max(1, round(_reference_value(state, item) * 0.93))
        state["crates"].remove(crate)
        state["inventory"].append(item)
        if item["catalog_id"] not in state["discovered"]:
            state["discovered"].append(item["catalog_id"])
        state["stats"]["crates_opened"] += 1
        _event(state, "reveal", "封条揭开", f"开出了{RARITIES[item['rarity']]}物品「{item['name']}」！品相 {item['condition']}%，初始标价 {item['price']} 星币。", item)
    elif command == "repair":
        item = _item(state, args[0])
        _require_unlocked_item(state, item)
        if item["condition"] >= 100:
            raise GameError("这件物品已是完美品相，无需修理。")
        if item["repairs"] >= 2:
            raise GameError("这件物品已达到两次修理上限。")
        if item["last_repair_day"] == state["day"]:
            raise GameError("今天已经修过这件物品；明天再试。")
        cost = _repair_cost(state, item)
        _spend(state, energy=2, credits=cost)
        item["repairs"] += 1
        item["last_repair_day"] = state["day"]
        before = item["condition"]
        fail_chance = [0.24, 0.14, 0.07, 0.03][state["upgrades"]["workbench"]]
        if rng.random() < fail_chance:
            item["condition"] = max(5, before - rng.randint(3, 11))
            text = f"修理失手：{item['name']}的品相从 {before}% 降到 {item['condition']}%。花费 {cost} 星币；原标价未变。"
        else:
            gain = rng.randint(19, 35) + 4 * state["upgrades"]["workbench"]
            item["condition"] = min(100, before + gain)
            text = f"修理成功：{item['name']}的品相从 {before}% 提升到 {item['condition']}%。花费 {cost} 星币；记得检查标价。"
        _event(state, "repair", "工作台火花", text, item)
    elif command == "price":
        item = _item(state, args[0])
        _require_unlocked_item(state, item)
        try:
            price = int(args[1])
        except (ValueError, TypeError) as exc:
            raise GameError("标价必须是 1–9999 的整数。") from exc
        if not 1 <= price <= 9999 or str(price) != str(args[1]).strip():
            raise GameError("标价必须是 1–9999 的整数。")
        item["price"] = price
        _event(state, "price", "换上新价签", f"「{item['name']}」现在标价 {price} 星币。", item)
    elif command == "sell":
        item = _item(state, args[0])
        if state["negotiation"]:
            raise GameError("还有客人在等你的还价答复；请先 accept、decline 或 offer。")
        if item["last_sale_day"] == state["day"]:
            raise GameError("这件物品今天已接待过买家；改价或换客人不能重掷，明天再试。")
        visitor = None
        if len(args) == 2:
            visitor = next((v for v in state["visitors"] if v["id"] == args[1].lower()), None)
            if visitor is None:
                raise GameError("这位顾客今天不在店里；用 visitors 查看。")
            if visitor["status"] != "waiting":
                raise GameError("这位顾客今天已经接待过；明天再安排吧。")
        _spend(state, energy=1)
        item["last_sale_day"] = state["day"]
        context = _trade_context(state, item, visitor)
        roll = _trade_roll(state, rng, item, visitor, item["price"], context, "initial")
        buyer = visitor["name"] if visitor else "旅客"
        if visitor:
            visitor["status"] = "left"
        if roll["success"]:
            rep = _sale_settle(state, item, visitor, item["price"])
            _event(state, "sale", "一见钟情 · 01大成功！" if roll["roll"] == 1 else "掷骰成交！",
                   _roll_text(roll) + f" {buyer}买走「{item['name']}」，收入{item['price']}星币，口碑+{rep}。", item)
        elif roll["roll"] == 100:
            _event(state, "sale", "100大失败 · 客人告辞", _roll_text(roll), item)
        else:
            # A real, binding customer quote, not an exact budget disclosure.
            offer = _counter_offer(context, item["price"])
            state["negotiation"] = {"item_id": item["id"], "item_name": item["name"],
                                    "customer_id": visitor["id"] if visitor else None, "customer_name": buyer,
                                    "original_price": item["price"], "counter_offer": offer,
                                    "day": state["day"], "context": context, "initial_roll_id": roll["id"],
                                    "rules_version": VERSION, "origin_rules_version": VERSION}
            if visitor:
                visitor["status"] = "negotiating"
            _event(state, "negotiation", "客人还了一个价", _roll_text(roll) +
                   f" {buyer}愿出{offer}星币。接受免费；最终报价须高于还价、低于初价，花1精力，成功率随相对还价涨幅下降；失败收入0，不能再接受旧还价。可先 preview-offer 预览。", item)
        state["last_event"]["roll"] = copy.deepcopy(roll)
    elif command in {"accept", "decline", "offer"}:
        pending = state["negotiation"]
        if pending is None or pending["item_id"] != args[0].upper():
            raise GameError("这件货没有等待答复的还价；用 status 查看。")
        item = _item(state, args[0])
        visitor = next((v for v in state["visitors"] if v["id"] == pending["customer_id"]), None)
        buyer = pending["customer_name"]
        if command == "accept":
            price = pending["counter_offer"]
            _close_negotiation(state)
            rep = _sale_settle(state, item, visitor, price)
            _event(state, "sale", "就这个价 · 成交", f"接受{buyer}的{price}星币还价，卖出「{item['name']}」，口碑+{rep}。没有再掷骰或消耗精力。", item)
        elif command == "decline":
            _close_negotiation(state)
            _event(state, "negotiation", "下回有缘", f"谢绝{buyer}的还价，「{item['name']}」留在货架；今日该货接待结束。", item)
        else:
            price = _final_price(pending, args[1])
            _spend(state, energy=1)
            roll = _trade_roll(state, rng, item, visitor, price, pending["context"], "final")
            _close_negotiation(state)
            item["price"] = price
            if roll["success"]:
                rep = _sale_settle(state, item, visitor, price)
                _event(state, "sale", "最终报价 · 01大成功！" if roll["roll"] == 1 else "最终报价 · 成交！",
                       _roll_text(roll) + f" {buyer}买走「{item['name']}」，收入{price}星币，口碑+{rep}。", item)
            else:
                _event(state, "sale", "最终报价 · 客人告辞", _roll_text(roll) + " 唯一一次还价已用，本次收入0；不能再接受旧还价，今天不能再出售这件货。", item)
            state["last_event"]["roll"] = copy.deepcopy(roll)
    elif command == "collect":
        item = _item(state, args[0])
        _require_unlocked_item(state, item)
        if any(i["catalog_id"] == item["catalog_id"] for i in state["collection"]):
            raise GameError("收藏柜已有这个品种；请留给未来的买家。")
        had_set = _has_set(state, item["kind"])
        _spend(state, energy=1)
        state["inventory"].remove(item)
        item["collected"] = True
        state["collection"].append(item)
        if not had_set and _has_set(state, item["kind"]) and item["kind"] == "bot":
            state["energy"] += 1
        _event(state, "collect", "留给自己的星光", f"将「{item['name']}」永久放入收藏柜。它不再出售；已收藏 {len(state['collection'])} 个品种。", item)
    elif command == "upgrade":
        which = args[0]
        if which not in UPGRADE_RULES:
            raise GameError("升级项目为 workbench、shelf 或 display。")
        level = state["upgrades"][which]
        if level >= 3:
            raise GameError("此设施已经升到最高等级。")
        rule = UPGRADE_RULES[which]
        cost = rule["costs"][level]
        _spend(state, energy=2, credits=cost)
        state["upgrades"][which] += 1
        if which == "shelf":
            state["energy"] += 1
        text = f"花费{cost}星币升级{rule['name']}至Lv.{level + 1}：{rule['effects'][level + 1]}。"
        if which == "display" and level == 1:
            text += "额外访客从明天开始到店。"
        _event(state, "upgrade", "小店焕新", text)
    elif command == "endday":
        if state["negotiation"]:
            pending = state["negotiation"]
            state["log"].append({"day": state["day"], "text": f"闭店前自动谢绝{pending['customer_name']}对「{pending['item_name']}」的{pending['counter_offer']}星币还价。"})
            _close_negotiation(state)
        old_day = state["day"]
        cost = _operating_cost(state)
        if state["credits"] < cost:
            state["credits"] = 0
            state["phase"] = "lost"
            _event(state, "end", "灯光暂时熄灭", f"第{old_day}天闭店无法支付{cost}星币维护费。本局结束，你的收藏仍留在这里。")
        else:
            state["credits"] -= cost
            state["stats"]["days_traded"] += 1
            if old_day == TOTAL_DAYS and state["first_week_result"] == "pending":
                won = state["credits"] >= GOAL["credits"] and len(state["collection"]) >= GOAL["collection"]
                state["first_week_result"] = "won" if won else "missed"
                state["phase"] = "week_summary"
                _event(state, "end", "首周达成 · 星港为你亮灯" if won else "首周结算 · 故事仍在继续",
                       f"支付{cost}星币维护费后，留下{state['credits']}星币、{len(state['collection'])}种收藏。"
                       + ("首周目标达成！" if won else "首周目标尚未达成，可以继续经营后补齐。")
                       + "使用continue明确进入第8天；所有进度保留。")
            else:
                _start_day(state, rng)
                _event(state, "day", f"第{state['day']}天 · {state['daily_event']['title']}",
                       f"支付{cost}星币维护费，恢复精力并补货。{state['daily_event']['description']} 今日{state['demand']['label']}。")
    else:
        raise GameError(f"未知命令：{command}")
    state["rng"] = rng.getstate()
    _check_milestones(state)


def _atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(data, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        # Persist the rename too; a crash between state and observation is healed on next read.
        try:
            directory_fd = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError as exc:
            raise CommittedWriteError(f"文件已替换，但目录同步失败：{exc}") from exc
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()



def _validate_trades(state):
    def fail():
        raise GameError("存档掷骰或还价记录损坏；请保留原文件，未重新掷骰。")
    def integer(value, low, high):
        return type(value) is int and low <= value <= high
    def modifiers_valid(modifiers, total, scale):
        return (isinstance(modifiers, list) and len(modifiers) <= 7
                and all(isinstance(m, dict) and set(m) == {"label", "value"} and isinstance(m["label"], str)
                        and integer(m["value"], -2 * scale, 3 * scale) and m["value"] % scale == 0 for m in modifiers)
                and type(total) is int and total == sum(m["value"] for m in modifiers))
    if not {"engine_upgrade", "negotiation", "roll_seq", "roll_history"} <= set(state):
        fail()
    sequence, history = state.get("roll_seq"), state.get("roll_history")
    if type(sequence) is not int or sequence < 0 or not isinstance(history, list) or len(history) != min(sequence, 60):
        fail()
    imported_boundary, v3_boundary = 0, 0
    upgrade = state["engine_upgrade"]
    if upgrade is not None:
        if not isinstance(upgrade, dict) or type(upgrade.get("from_version")) is not int or upgrade["from_version"] not in {2, 3, 4}:
            fail()
        expected = {"from_version", "source_day", "source_phase"}
        if upgrade["from_version"] >= 3:
            expected |= {"source_roll_seq", "legacy_v3_roll_seq"}
        if (set(upgrade) != expected or not integer(upgrade["source_day"], 1, state["day"])
                or upgrade["source_phase"] not in {"active", "week_summary", "lost"}):
            fail()
        if upgrade["from_version"] >= 3:
            imported_boundary, v3_boundary = upgrade["source_roll_seq"], upgrade["legacy_v3_roll_seq"]
            if (not integer(imported_boundary, 0, sequence) or not integer(v3_boundary, 0, imported_boundary)
                    or upgrade["from_version"] == 3 and v3_boundary != imported_boundary):
                fail()
    common = {"id", "day", "item_id", "item_name", "customer_id", "customer_name", "stage", "modifier", "modifiers",
              "success", "outcome", "price", "explanation", "rules_version", "counter_offer"}
    old_keys = common | {"face", "total", "target", "base_target", "rejection_penalty"}
    new_keys = common | {"die", "tens", "ones", "roll", "threshold", "probability", "base_chance", "premium"}
    seen = {}
    for index, row in enumerate(history):
        expected_id = sequence - len(history) + index + 1
        version = 3 if expected_id <= v3_boundary else 4 if expected_id <= imported_boundary else VERSION
        if (not isinstance(row, dict) or set(row) != (new_keys if version == VERSION else old_keys)
                or type(row["rules_version"]) is not int or row["rules_version"] != version
                or not integer(row["id"], expected_id, expected_id) or not integer(row["day"], 1, state["day"])
                or not integer(row["price"], 1, 9999)
                or not all(isinstance(row[k], str) for k in ["item_id", "item_name", "customer_name", "explanation"])
                or row["customer_id"] not in {None} | {p[0] for p in CUSTOMERS}
                or row["stage"] not in {"initial", "final"}
                or not modifiers_valid(row["modifiers"], row["modifier"], 5 if version == VERSION else 1)
                or type(row["success"]) is not bool):
            fail()
        if version == VERSION:
            if (row["die"] != "D100" or not integer(row["tens"], 0, 90) or row["tens"] % 10
                    or not integer(row["ones"], 0, 9) or not integer(row["roll"], 1, 100)
                    or row["roll"] != (row["tens"] + row["ones"] or 100)
                    or not integer(row["threshold"], 1, 99)
                    or type(row["probability"]) not in (int, float) or row["probability"] != row["threshold"] / 100):
                fail()
            if row["stage"] == "final":
                if not integer(row["counter_offer"], 1, row["price"] - 1):
                    fail()
                base, threshold = _final_chance(row["modifier"], row["counter_offer"], row["price"])
                if (not integer(row["base_chance"], 1, 99) or row["base_chance"] != base or row["threshold"] != threshold
                        or type(row["premium"]) not in (int, float)
                        or row["premium"] != (row["price"] - row["counter_offer"]) / row["counter_offer"]):
                    fail()
            elif row["counter_offer"] is not None or row["base_chance"] is not None or row["premium"] is not None:
                fail()
            success = row["roll"] == 1 or (row["roll"] != 100 and row["roll"] <= row["threshold"])
            outcome = "miracle" if row["roll"] == 1 else "fumble" if row["roll"] == 100 else "success" if success else "failure"
        else:
            penalty = 3 if version == 4 and row["stage"] == "final" else 0
            if (not integer(row["face"], 1, 20) or type(row["total"]) is not int or row["total"] != row["face"] + row["modifier"]
                    or not integer(row["base_target"], 2, 99) or type(row["rejection_penalty"]) is not int
                    or row["rejection_penalty"] != penalty or not integer(row["target"], 2, 102)
                    or row["target"] != row["base_target"] + penalty):
                fail()
            if version == 4 and row["stage"] == "final":
                if not integer(row["counter_offer"], 1, row["price"] - 1):
                    fail()
            elif row["counter_offer"] is not None:
                fail()
            success = row["face"] == 20 or (row["face"] != 1 and row["total"] >= row["target"])
            outcome = "miracle" if row["face"] == 20 else "fumble" if row["face"] == 1 else "success" if success else "failure"
        if row["success"] != success or row["outcome"] != outcome:
            fail()
        pair = (row["day"], row["item_id"])
        if pair in seen:
            previous = seen[pair]
            previous_modifiers = copy.deepcopy(previous["modifiers"])
            previous_modifier = previous["modifier"]
            if version == VERSION and previous["rules_version"] != VERSION:
                previous_modifier *= 5
                for bonus in previous_modifiers:
                    bonus["value"] *= 5
            if (row["stage"] != "final" or previous["stage"] != "initial" or previous["outcome"] != "failure"
                    or any(row[k] != previous[k] for k in ("customer_id", "customer_name", "item_name"))
                    or row["modifier"] != previous_modifier or row["modifiers"] != previous_modifiers
                    or row["price"] > previous["price"] or version >= 4 and row["price"] >= previous["price"]):
                fail()
        elif row["stage"] == "final" and not (index == 0 and sequence > 60):
            fail()
        seen[pair] = row
    event_roll = state["last_event"].get("roll")
    if event_roll is not None and (not history or event_roll != history[-1]):
        fail()
    negotiating = [v for v in state["visitors"] if v["status"] == "negotiating"]
    pending = state["negotiation"]
    if pending is None:
        if negotiating:
            fail()
        return
    pkeys = {"item_id", "item_name", "customer_id", "customer_name", "original_price", "counter_offer", "day", "context", "initial_roll_id", "rules_version", "origin_rules_version"}
    if (not isinstance(pending, dict) or set(pending) != pkeys or state["phase"] != "active"
            or not integer(pending["day"], state["day"], state["day"])
            or not integer(pending["rules_version"], VERSION, VERSION)
            or not integer(pending["origin_rules_version"], 3, VERSION)):
        fail()
    item = next((i for i in state["inventory"] if i["id"] == pending["item_id"]), None)
    if (item is None or item["last_sale_day"] != state["day"] or pending["item_name"] != item["name"]
            or not integer(pending["original_price"], 1, 9999) or pending["original_price"] != item["price"]
            or not integer(pending["counter_offer"], 1, item["price"])):
        fail()
    visitor = next((v for v in state["visitors"] if v["id"] == pending["customer_id"]), None)
    if (pending["customer_id"] is not None and (visitor is None or negotiating != [visitor])
            or pending["customer_id"] is None and negotiating
            or pending["customer_name"] != (visitor["name"] if visitor else "旅客")):
        fail()
    context = pending["context"]
    if (not isinstance(context, dict) or set(context) != {"reference", "budget", "modifiers", "modifier"}
            or type(context["reference"]) not in (int, float) or not math.isfinite(context["reference"]) or context["reference"] <= 0
            or not modifiers_valid(context["modifiers"], context["modifier"], 5)
            or context["budget"] != (visitor["budget"] if visitor else None)):
        fail()
    if (not history or not integer(pending["initial_roll_id"], history[-1]["id"], history[-1]["id"])
            or history[-1]["stage"] != "initial" or history[-1]["outcome"] != "failure"
            or history[-1]["rules_version"] != pending["origin_rules_version"]
            or any(history[-1][key] != pending[key] for key in ("day", "item_id", "item_name", "customer_id", "customer_name"))
            or history[-1]["price"] != pending["original_price"]
            or context["reference"] != _actual_value(state, item)):
        fail()
    row = history[-1]
    if row["rules_version"] == VERSION:
        if (row["modifier"] != context["modifier"] or row["modifiers"] != context["modifiers"]
                or row["threshold"] != _initial_chance(context, pending["original_price"])
                or pending["counter_offer"] != _counter_offer(context, pending["original_price"])):
            fail()
    else:
        import _legacy_v4
        old_context = copy.deepcopy(context)
        old_context["modifier"] //= 5
        for bonus in old_context["modifiers"]:
            bonus["value"] //= 5
        if (row["modifier"] != old_context["modifier"] or row["modifiers"] != old_context["modifiers"]
                or row["target"] != _legacy_v4._trade_target(old_context, pending["original_price"])
                or pending["counter_offer"] != _legacy_v4._counter_offer(old_context, pending["original_price"])):
            fail()

def _validate_state(state):
    """Detect damaged/incompatible saves without silently resetting or rerolling."""
    if not isinstance(state, dict) or state.get("version") != VERSION:
        raise GameError("不兼容或损坏的存档；请保留原文件。v1/v2/v3/v4存档需用 import-v1/import-v2/import-v3/import-v4 复制至全新路径。")
    integers = {"revision": (0, 10**12), "day": (1, 10**12), "credits": (0, 10**12),
                "energy": (0, 17), "reputation": (0, 99), "next_crate": (1, 10**12),
                "next_item": (1, 10**12), "event_seq": (1, 10**12)}
    for key, (minimum, maximum) in integers.items():
        value = state.get(key)
        if type(value) is not int or not minimum <= value <= maximum:
            raise GameError(f"存档字段损坏：{key}。")
    if state.get("phase") not in {"active", "week_summary", "lost"}:
        raise GameError("存档阶段损坏。")
    upgrades = state.get("upgrades", {})
    if not isinstance(upgrades, dict) or set(upgrades) != set(UPGRADE_RULES) or any(type(v) is not int or v not in (0, 1, 2, 3) for v in upgrades.values()):
        raise GameError("存档设施状态损坏。")
    event = state.get("daily_event")
    if event not in EVENTS:
        raise GameError("存档港口事件损坏。")
    first_week = state.get("first_week_result")
    if first_week not in {"pending", "won", "missed"}:
        raise GameError("存档首周结果损坏。")
    if (first_week == "pending" and state["day"] > 7) or (first_week != "pending" and state["day"] < 7) or (state["phase"] == "week_summary" and (state["day"] != 7 or first_week == "pending")):
        raise GameError("存档日期与首周结果不一致。")
    discovered = state.get("discovered")
    if not isinstance(discovered, list) or any(not isinstance(i, str) or i not in CATALOG_BY_ID for i in discovered) or len(set(discovered)) != len(discovered):
        raise GameError("存档图鉴损坏。")
    visitors = state.get("visitors")
    if not isinstance(visitors, list) or len(visitors) not in (3, 4):
        raise GameError("存档顾客名单损坏。")
    profiles = {p[0]: p for p in CUSTOMERS}
    visitor_ids = set()
    for visitor in visitors:
        if not isinstance(visitor, dict) or visitor.get("id") not in profiles or visitor["id"] in visitor_ids:
            raise GameError("存档顾客损坏。")
        visitor_ids.add(visitor["id"])
        key, name, role, kind, condition, low, high = profiles[visitor["id"]]
        expected = (name, role, kind, condition, [low, high], 1.25, f"偏爱{KINDS[kind]}，品相{condition}%以上更喜欢")
        actual = tuple(visitor.get(k) for k in ("name", "role", "preferred_kind", "min_condition", "budget_range", "premium", "preference_label"))
        if actual != expected or visitor.get("status") not in {"waiting", "bought", "left", "negotiating"} or type(visitor.get("budget")) is not int or not low <= visitor["budget"] <= high:
            raise GameError("存档顾客偏好或预算损坏。")
    stats = state.get("stats")
    if not isinstance(stats, dict) or set(stats) != {"crates_opened", "sales_count", "gross_earnings", "days_traded"} or any(type(v) is not int or v < 0 for v in stats.values()):
        raise GameError("存档经营统计损坏。")
    milestones = state.get("milestones")
    if not isinstance(milestones, list):
        raise GameError("存档阶段目标损坏。")
    for index, row in enumerate(milestones):
        expected = MILESTONES[index] if index < len(MILESTONES) else {"id": f"voyage_{index - len(MILESTONES) + 1}", "title": f"星海长航 · 第{index - len(MILESTONES) + 1}章"}
        if not isinstance(row, dict) or row.get("id") != expected["id"] or row.get("title") != expected["title"] or type(row.get("day")) is not int or not 7 <= row["day"] <= state["day"]:
            raise GameError("存档阶段履历损坏。")
    migration = state.get("migration")
    if migration is not None and (not isinstance(migration, dict) or set(migration) != {"from_version", "source_day", "source_phase", "stats_scope"} or migration["from_version"] != 1 or type(migration["source_day"]) is not int or not 1 <= migration["source_day"] <= 7 or migration["source_phase"] not in {"active", "won", "lost"} or migration["stats_scope"] != "since_import"):
        raise GameError("存档迁移记录损坏。")
    if not isinstance(state.get("collection"), list):
        raise GameError("存档收藏损坏。")
    if state["energy"] > _max_energy(state):
        raise GameError("存档精力超出上限。")
    stock = state.get("supplier_stock", {})
    if not isinstance(stock, dict) or set(stock) != set(SUPPLIERS) or any(type(stock[k]) is not int or not 0 <= stock[k] <= _stock_limit(state, k) for k in stock):
        raise GameError("存档供应商状态损坏。")
    demand = state.get("demand", {})
    if not isinstance(demand, dict) or demand.get("kind") not in KINDS or demand.get("multiplier") not in [1.25, 1.35, 1.45] or not isinstance(demand.get("label"), str):
        raise GameError("存档热需状态损坏。")
    for key in ["inventory", "crates", "collection", "log"]:
        if not isinstance(state.get(key), list):
            raise GameError(f"存档字段损坏：{key}。")
    if len(state["inventory"]) + len(state["crates"]) > _capacity(state):
        raise GameError("存档货架容量异常。")
    ids = set()
    collection_catalog = set()
    def validate_item(item, cargo=False, collected=False):
        if not isinstance(item, dict) or item.get("catalog_id") not in CATALOG_BY_ID:
            raise GameError("存档物品损坏。")
        entry = CATALOG_BY_ID[item["catalog_id"]]
        if (item.get("name"), item.get("rarity"), item.get("kind"), item.get("description")) != (entry[1], entry[2], entry[3], entry[5]):
            raise GameError("存档物品描述异常。")
        for field, lower, upper in [("base_value", 1, 10000), ("condition", 5, 100), ("repairs", 0, 2), ("last_sale_day", 0, state["day"]), ("last_repair_day", 0, state["day"])]:
            if type(item.get(field)) is not int or not lower <= item[field] <= upper:
                raise GameError(f"存档物品字段损坏：{field}。")
        if item.get("collected") is not collected or item.get("origin") not in {s["name"] for s in SUPPLIERS.values()}:
            raise GameError("存档物品来源或收藏状态异常。")
        if not cargo:
            if not isinstance(item.get("id"), str) or not item["id"].startswith("I") or item["id"] in ids:
                raise GameError("存档物品编号异常。")
            ids.add(item["id"])
            if type(item.get("price")) is not int or not 1 <= item["price"] <= 9999:
                raise GameError("存档标价异常。")
    for item in state["inventory"]:
        validate_item(item)
    for item in state["collection"]:
        validate_item(item, collected=True)
        if item["catalog_id"] in collection_catalog:
            raise GameError("存档收藏重复。")
        collection_catalog.add(item["catalog_id"])
    for crate in state["crates"]:
        if not isinstance(crate, dict) or crate.get("supplier") not in SUPPLIERS or not isinstance(crate.get("id"), str) or not crate["id"].startswith("C") or crate["id"] in ids or not isinstance(crate.get("name"), str):
            raise GameError("存档盲箱损坏。")
        ids.add(crate["id"])
        validate_item(crate.get("cargo"), cargo=True)
    for row in state["log"]:
        if not isinstance(row, dict) or type(row.get("day")) is not int or not 1 <= row["day"] <= state["day"] or not isinstance(row.get("text"), str):
            raise GameError("存档日志损坏。")
    event = state.get("last_event")
    if not isinstance(event, dict) or event.get("seq") != state["event_seq"] or event.get("type") not in {"start", "buy", "reveal", "repair", "sale", "price", "day", "upgrade", "collect", "end", "import", "negotiation"} or not isinstance(event.get("title"), str) or not isinstance(event.get("text"), str):
        raise GameError("存档事件损坏。")
    _validate_trades(state)
    _rng(state)


def migrate_v1(source_bytes):
    """Pure migration. Never writes the source or plays a turn."""
    import _legacy_v1
    try:
        original = json.loads(source_bytes)
        _legacy_v1._validate_state(original)
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, _legacy_v1.GameError) as exc:
        raise GameError("旧版存档无法验证；原文件未改动。请提供完整v1 save.json，不能用公开observation代替。") from exc
    state = copy.deepcopy(original)
    state["version"] = VERSION
    state.update(negotiation=None, roll_seq=0, roll_history=[], engine_upgrade=None)
    state["upgrades"]["display"] = 0
    state["daily_event"] = copy.deepcopy(EVENTS[0])
    # Deterministic import visitors, independent of the preserved game RNG.
    migration_rng = random.Random(hashlib.sha256(source_bytes).digest())
    state["visitors"] = _make_visitors(migration_rng, state)
    state["discovered"] = sorted({i["catalog_id"] for i in state["inventory"] + state["collection"]}
                                 | {row[0] for row in CATALOG if any(row[1] in log["text"] for log in state["log"])})
    state["stats"] = {"crates_opened": 0, "sales_count": 0, "gross_earnings": 0, "days_traded": 0}
    state["milestones"] = []
    state["migration"] = {"from_version": 1, "source_day": original["day"], "source_phase": original["phase"], "stats_scope": "since_import"}
    if original["phase"] == "won":
        state["phase"] = "week_summary"
        state["first_week_result"] = "won"
    elif original["phase"] == "lost" and original["day"] == 7 and original["last_event"]["title"] == "七天试营业结束":
        state["phase"] = "week_summary"
        state["first_week_result"] = "missed"
    else:
        state["first_week_result"] = "pending"
    _check_milestones(state)
    _event(state, "import", "旧店的灯还亮着", "旧版进度已复制导入，原文件保持不变。" +
           ("首周结算仍停在第7天；使用continue才会继续。" if state["phase"] == "week_summary" else "现金、物品、收藏与随机状态保留。"))
    return state


def migrate_v2(source_bytes):
    """Read-only v2 upgrade; preserve resources, committed cargo and game RNG."""
    import _legacy_v2
    try:
        original = json.loads(source_bytes)
        _legacy_v2._validate_state(original)
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, _legacy_v2.GameError) as exc:
        raise GameError("扩展版存档无法验证；原文件未改动。请提供完整v2 save.json，不能用公开observation代替。") from exc
    state = copy.deepcopy(original)
    state["daily_event"] = copy.deepcopy(next(e for e in EVENTS if e["id"] == original["daily_event"]["id"]))
    state.update(version=VERSION, negotiation=None, roll_seq=0, roll_history=[],
                 engine_upgrade={"from_version": 2, "source_day": original["day"], "source_phase": original["phase"]})
    _event(state, "import", "骰子来到柜台", "扩展版进度已复制升级。原文件不变，现金、库存、收藏、顾客、当天已用接待与随机状态完整保留；未执行任何经营动作。")
    return state


def _upgrade_d20_copy(original, source_version):
    """Keep original dice and quote, explicitly switch the future retry to v5."""
    state = copy.deepcopy(original)
    state["version"] = VERSION
    state["daily_event"] = copy.deepcopy(next(e for e in EVENTS if e["id"] == original["daily_event"]["id"]))
    prior_upgrade = original.get("engine_upgrade") or {}
    v3_boundary = (original["roll_seq"] if source_version == 3 else
                   prior_upgrade.get("source_roll_seq", 0) if prior_upgrade.get("from_version") == 3 else 0)
    state["engine_upgrade"] = {"from_version": source_version, "source_day": original["day"],
        "source_phase": original["phase"], "source_roll_seq": original["roll_seq"], "legacy_v3_roll_seq": v3_boundary}
    if source_version == 3:
        for row in state["roll_history"]:
            row.update(base_target=row["target"], rejection_penalty=0, rules_version=3, counter_offer=None)
    if state["negotiation"]:
        pending = state["negotiation"]
        pending.update(rules_version=VERSION, origin_rules_version=state["roll_history"][-1]["rules_version"])
        pending["context"]["modifier"] *= 5
        for bonus in pending["context"]["modifiers"]:
            bonus["value"] *= 5
    _event(state, "import", "双D10来到柜台",
           f"v{source_version}进度只读复制到新路径；历史D20保留原规则，不重判、不推进随机数或日期。"
           "已承诺还价保留，可免费接受/谢绝；尚未使用的最终报价明确改用v5百分骰与涨幅成功率，旧加值每点转为5百分点。")
    return state


def migrate_v3(source_bytes):
    import _legacy_v3
    try:
        original = json.loads(source_bytes)
        _legacy_v3._validate_state(original)
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, _legacy_v3.GameError) as exc:
        raise GameError("v3存档无法验证；原文件未改动，请提供完整私有存档。") from exc
    return _upgrade_d20_copy(original, 3)


def migrate_v4(source_bytes):
    import _legacy_v4
    try:
        original = json.loads(source_bytes)
        _legacy_v4._validate_state(original)
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, _legacy_v4.GameError) as exc:
        raise GameError("v4存档无法验证；原文件未改动，请提供完整私有存档。") from exc
    return _upgrade_d20_copy(original, 4)


class GameStore:
    def __init__(self, save_path=DEFAULT_SAVE):
        self.save_path = Path(save_path).expanduser().resolve()
        self.observation_path = (self.save_path.with_name("observation.json") if self.save_path == DEFAULT_SAVE
                                 else self.save_path.with_name(self.save_path.stem + ".observation.json"))
        self.lock_path = self.save_path.with_name(self.save_path.name + ".lock")

    @contextmanager
    def locked(self):
        self.save_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def load(self):
        if not self.save_path.exists():
            raise GameError("尚未开张。运行 new 创建新游戏；不会自动覆盖旧存档。")
        try:
            with self.save_path.open(encoding="utf-8") as handle:
                state = json.load(handle)
        except (json.JSONDecodeError, UnicodeError) as exc:
            raise GameError("存档无法读取；请保留原文件，未自动重置。") from exc
        try:
            _validate_state(state)
        except GameError:
            raise
        except (KeyError, TypeError, ValueError, IndexError, OverflowError) as exc:
            raise GameError("存档内部结构损坏；请保留原文件，未自动重置。") from exc
        return state

    def execute(self, command, *args):
        """Return only public data. Failed commands never change the save or RNG."""
        arity = {"new": 0, "status": 0, "market": 0, "buy": 1, "open": 1, "inspect": 1,
                 "repair": 1, "price": 2, "sell": (1, 2), "endday": 0, "upgrade": 1, "collect": 1, "restart": 1,
                 "continue": 0, "codex": 0, "visitors": 0, "import-v1": 1, "import-v2": 1, "import-v3": 1, "import-v4": 1, "preview-offer": 2,
                 "accept": 1, "decline": 1, "offer": 2}
        if command not in arity:
            raise GameError(f"未知命令：{command}；运行 help 查看用法。")
        allowed = arity[command] if isinstance(arity[command], tuple) else (arity[command],)
        if len(args) not in allowed or any(not isinstance(a, str) for a in args):
            raise GameError(f"{command} 需要 {arity[command]} 个参数；运行 help 查看用法。")
        with self.locked():
            if command == "new":
                if self.save_path.exists():
                    raise GameError("已有存档，new 不会重抽；继续 status，或明确 restart --confirm。")
                state = new_state()
            elif command in {"import-v1", "import-v2", "import-v3", "import-v4"}:
                source = Path(args[0]).expanduser().resolve()
                if source in {self.save_path, self.observation_path}:
                    raise GameError("导入目标必须是新的路径，不能原地覆盖旧版存档。请使用 --save 新路径。")
                if self.save_path.exists() or self.observation_path.exists():
                    raise GameError("目标存档或公开画面已存在；导入不会覆盖，请选全新 --save 路径。")
                state = {"import-v1": migrate_v1, "import-v2": migrate_v2, "import-v3": migrate_v3, "import-v4": migrate_v4}[command](source.read_bytes())
            elif command == "restart":
                if args != ("--confirm",):
                    raise GameError("重新开始会清空本局；确定后使用 restart --confirm。")
                # Even a damaged save can be explicitly reset, but never automatically.
                previous_revision = 0
                if self.save_path.exists():
                    try:
                        previous_revision = self.load()["revision"]
                    except GameError:
                        previous_revision = 0
                state = new_state()
                state["revision"] = previous_revision
            else:
                state = self.load()
                if command in {"status", "market", "inspect", "codex", "visitors", "preview-offer"}:
                    public = observation(state)
                    result = public
                    if command == "preview-offer":
                        pending = state["negotiation"]
                        if pending is None or pending["item_id"] != args[0].upper():
                            raise GameError("这件货没有等待答复的还价；用 status 查看。")
                        price = _final_price(pending, args[1])
                        public["negotiation"]["preview"] = dict(_offer_forecast(state, pending, price), suggested=False)
                    elif command == "market":
                        result = {k: public[k] for k in ["revision", "day", "credits", "energy", "demand", "suppliers", "daily_event", "visitors", "operating_cost"]}
                    elif command in {"codex", "visitors"}:
                        result = public[command] if command == "codex" else {"day": public["day"], "visitors": public["visitors"]}
                    elif command == "inspect":
                        result = next((item for item in public["inventory"] + public["collection"] if item["id"] == args[0].upper()), None)
                        if result is None:
                            raise GameError(f"未找到物品 {args[0]}。盲箱需先 open 才能查看内容。")
                    # Read commands repair a missing/stale public projection, never private state.
                    try:
                        _atomic_json(self.observation_path, public)
                    except OSError:
                        result = dict(result, persistence_warning="公开画面未能更新；返回的是当前存档的真实公开状态。检查目录权限后运行status重建画面。")
                    return result
                state = copy.deepcopy(state)
                apply_command(state, command, list(args))
            state["revision"] += 1
            _validate_state(state)
            public = observation(state)
            warnings = []
            try:
                _atomic_json(self.save_path, state)
            except CommittedWriteError:
                warnings.append("经营操作已提交，但目录同步失败；请检查磁盘。不要重复执行同一动作。")
            try:
                _atomic_json(self.observation_path, public)
            except OSError:
                warnings.append("经营操作已成功保存，但公开画面未更新。不要重复执行同一动作；检查目录权限后运行status重建画面。")
            if warnings:
                public["persistence_warning"] = " ".join(warnings)
            return public


def main(argv=None):
    parser = argparse.ArgumentParser(description="星屑杂货铺 · 独立经营引擎", usage="%(prog)s [--save PATH] COMMAND [ARGS]", add_help=False)
    parser.add_argument("--save", default=str(DEFAULT_SAVE))
    parser.add_argument("-h", "--help", action="store_true")
    parser.add_argument("command", nargs="?", default="help")
    # REMAINDER keeps the explicit restart confirmation with its command.
    parser.add_argument("args", nargs=argparse.REMAINDER)
    ns = parser.parse_args(argv)
    if ns.help or ns.command == "help":
        print(HELP)
        return 0
    try:
        result = GameStore(ns.save).execute(ns.command, *ns.args)
    except (GameError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
