#!/usr/bin/env python3
"""星际旧货铺 — persistent, standard-library-only seven-day shop simulation.

The GUI must read the public observation, never the private save. All mutations
run through this CLI (or GameStore.execute), under an advisory file lock.
"""
from __future__ import annotations

import argparse
import copy
import fcntl
import json
import math
import os
from pathlib import Path
import random
import secrets
import sys
import tempfile
from contextlib import contextmanager

VERSION = 1
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
]
CATALOG_BY_ID = {item[0]: item for item in CATALOG}
SUPPLIERS = {
    "salvage": {"id": "salvage", "name": "废轨回收站", "cost": 48, "stock": 4,
                "description": "平价漂流箱 · 普通 74% / 稀有 24% / 传说 2% · 品相 35–88"},
    "curated": {"id": "curated", "name": "夜航商队", "cost": 110, "stock": 2,
                "description": "精选封存箱 · 普通 28% / 稀有 61% / 传说 11% · 品相 48–96"},
}
HELP = """星际旧货铺 · 七天试营业
目标：在第 7 天闭店、扣除维护费后，留下至少 650 星币和 2 件不同藏品。
开局 260 星币，每天 12 点精力；闭店维护费 14 星币，次日补货与恢复精力。

命令（python3 engine.py [--save 路径] 命令）：
  new                    仅在没有存档时开局
  status                 查看公开状态 JSON，不消耗精力或改变随机数
  market                 查看供应商与今日热需 JSON
  buy salvage|curated    买盲箱，1 精力；内容在购买时已确定
  open C001              开箱，1 精力
  inspect I001           查看物品，不改变估价或运气
  repair I001            修理，2 精力；有失败风险，每件最多两次、每日一次
  price I001 120         免费定价（1–9999 整数）；估值含今日热需，不是保证售价
  sell I001              接待买家，1 精力；每件每天只能尝试一次，卖不出也耗精力
  collect I001           永久留作收藏，1 精力；不能再出售，重复品种不能收藏
  upgrade workbench      升级工作台，2 精力；降低修理风险与费用（两级）
  upgrade shelf          升级货架，2 精力；增加 3 格容量与每日 1 精力（两级）
  endday                 支付维护费并结束当天；第 7 天结算胜负
  restart --confirm      明确确认后清空本局，重新随机开局
  help                   查看规则

收藏与现金必须兼顾。热需每天变化，品相越好越值钱；高价有可能无人接手。
工作台 70/110 星币；货架 65/100 星币。货架容量从 7 格开始，盲箱也占格。
同一天失败的销售或修理不能重复尝试。报价过低可能成交，却会少赚。
存档自动落盘；刷新、查看与重开窗口不会重抽。只有确认 restart 才开启新局。
"""


class GameError(Exception):
    """A user-correctable command, save, or resource error."""


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


def new_state(seed=None):
    """Seed is only an in-process test aid; the public CLI has no seed/reroll flag."""
    rng = random.Random(secrets.randbits(128) if seed is None else seed)
    state = {
        "version": VERSION, "revision": 0, "day": 1, "credits": 260, "reputation": 0,
        "energy": 12, "phase": "active", "inventory": [], "crates": [], "collection": [],
        "upgrades": {"workbench": 0, "shelf": 0}, "demand": _daily_demand(rng),
        "supplier_stock": {key: val["stock"] for key, val in SUPPLIERS.items()},
        "next_crate": 1, "next_item": 1, "event_seq": 0, "last_event": None, "log": [],
    }
    state["rng"] = rng.getstate()
    _event(state, "start", "卷帘门升起", "第 1 天开张！用 260 星币起步，七天后留下 650 星币与 2 件不同藏品。")
    return state


def _capacity(state):
    return 7 + 3 * state["upgrades"]["shelf"]


def _max_energy(state):
    return 12 + state["upgrades"]["shelf"]


def _actual_value(state, item):
    demand = state["demand"]["multiplier"] if item["kind"] == state["demand"]["kind"] else 1.0
    return item["base_value"] * (0.30 + item["condition"] * 0.007) * demand


def _repair_cost(state, item):
    base = {"common": 15, "rare": 28, "legendary": 50}[item["rarity"]]
    return max(5, round(base * (1.0 - 0.18 * state["upgrades"]["workbench"])))


def _public_item(state, item):
    # Deliberately whitelisted: no catalog base value, crate contents, or RNG.
    estimate = _actual_value(state, item)
    return {
        "id": item["id"], "name": item["name"], "rarity": item["rarity"], "kind": item["kind"],
        "color": COLORS[item["rarity"]], "condition": item["condition"],
        "value_estimate": [max(1, int(estimate * 0.82)), max(2, math.ceil(estimate * 1.20))],
        "repair_cost": _repair_cost(state, item), "price": item["price"], "origin": item["origin"],
        "description": item["description"], "collected": item.get("collected", False),
        "sale_attempted_today": item.get("last_sale_day", 0) == state["day"],
        "repair_attempted_today": item.get("last_repair_day", 0) == state["day"],
        "repairs_remaining": max(0, 2 - item.get("repairs", 0)),
    }


def observation(state):
    return {
        "version": VERSION, "revision": state["revision"], "day": state["day"], "total_days": TOTAL_DAYS,
        "credits": state["credits"], "reputation": state["reputation"], "energy": state["energy"],
        "max_energy": _max_energy(state), "goal": GOAL.copy(), "phase": state["phase"],
        "inventory": [_public_item(state, item) for item in state["inventory"]],
        "crates": [{"id": crate["id"], "supplier": crate["supplier"], "name": crate["name"]} for crate in state["crates"]],
        "collection": [_public_item(state, item) for item in state["collection"]],
        "suppliers": [dict(info, stock=state["supplier_stock"][key]) for key, info in SUPPLIERS.items()],
        "upgrades": copy.deepcopy(state["upgrades"]), "demand": copy.deepcopy(state["demand"]),
        "last_event": copy.deepcopy(state["last_event"]), "log": copy.deepcopy(state["log"]),
        "capacity": _capacity(state), "operating_cost": OPERATING_COST,
        "upgrade_costs": {"workbench": [70, 110][state["upgrades"]["workbench"]] if state["upgrades"]["workbench"] < 2 else None,
                          "shelf": [65, 100][state["upgrades"]["shelf"]] if state["upgrades"]["shelf"] < 2 else None},
    }


def _require_active(state):
    if state["phase"] != "active":
        raise GameError("本局已经结束；可以查看藏品，或用 restart --confirm 明确开启新局。")


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


def apply_command(state, command, args):
    """Mutate an already-copied state. Errors must be discarded by its caller."""
    if command in {"status", "market", "inspect"}:
        return
    _require_active(state)
    rng = _rng(state)
    if command == "buy":
        supplier = args[0]
        if supplier not in SUPPLIERS:
            raise GameError("未知供应商；请选择 salvage 或 curated。")
        if state["supplier_stock"][supplier] <= 0:
            raise GameError("这位供应商今天已售罄，明天会补货。")
        if len(state["inventory"]) + len(state["crates"]) >= _capacity(state):
            raise GameError("货架已满；出售、收藏物品，或升级 shelf 后再采购。")
        _spend(state, energy=1, credits=SUPPLIERS[supplier]["cost"])
        # All hidden cargo properties are committed now, before the box is opened.
        crate = {"id": f"C{state['next_crate']:03d}", "supplier": supplier,
                 "name": "漂流回收箱" if supplier == "salvage" else "夜航封存箱", "cargo": _make_cargo(rng, supplier)}
        state["next_crate"] += 1
        state["supplier_stock"][supplier] -= 1
        state["crates"].append(crate)
        _event(state, "buy", "新货靠港", f"花费 {SUPPLIERS[supplier]['cost']} 星币购入 {crate['name']} {crate['id']}。箱内货物已封存。")
    elif command == "open":
        crate = next((c for c in state["crates"] if c["id"] == args[0].upper()), None)
        if crate is None:
            raise GameError(f"没有未开封的箱子 {args[0]}。")
        _spend(state, energy=1)
        item = copy.deepcopy(crate["cargo"])
        item["id"] = f"I{state['next_item']:03d}"
        state["next_item"] += 1
        item["price"] = max(1, round(_actual_value(state, item) * 0.93))
        state["crates"].remove(crate)
        state["inventory"].append(item)
        _event(state, "reveal", "封条揭开", f"开出了{RARITIES[item['rarity']]}物品「{item['name']}」！品相 {item['condition']}%，初始标价 {item['price']} 星币。", item)
    elif command == "repair":
        item = _item(state, args[0])
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
        fail_chance = [0.24, 0.14, 0.07][state["upgrades"]["workbench"]]
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
        if item["last_sale_day"] == state["day"]:
            raise GameError("这件物品今天已接待过买家；改价不会产生新买家，明天再试。")
        _spend(state, energy=1)
        item["last_sale_day"] = state["day"]
        # One draw and one attempt per item per day, persisted whether accepted or refused.
        willing_to_pay = _actual_value(state, item) * rng.uniform(0.78, 1.28) * (1 + min(state["reputation"], 15) * 0.006)
        if item["price"] <= willing_to_pay:
            state["credits"] += item["price"]
            state["reputation"] = min(99, state["reputation"] + (2 if item["rarity"] == "legendary" else 1))
            state["inventory"].remove(item)
            _event(state, "sale", "成交！", f"旅客买走了「{item['name']}」，收入 {item['price']} 星币。口碑 +{2 if item['rarity'] == 'legendary' else 1}。", item)
        else:
            _event(state, "sale", "买家摇了摇头", f"「{item['name']}」标价 {item['price']} 星币，这位旅客觉得太贵。今日接待机会已用，明天可再卖。", item)
    elif command == "collect":
        item = _item(state, args[0])
        if any(i["catalog_id"] == item["catalog_id"] for i in state["collection"]):
            raise GameError("收藏柜已有这个品种；请留给未来的买家。")
        _spend(state, energy=1)
        state["inventory"].remove(item)
        item["collected"] = True
        state["collection"].append(item)
        _event(state, "collect", "留给自己的星光", f"将「{item['name']}」永久放入收藏柜。它不再出售；已收藏 {len(state['collection'])} 个品种。", item)
    elif command == "upgrade":
        which = args[0]
        if which not in {"workbench", "shelf"}:
            raise GameError("升级项目为 workbench 或 shelf。")
        level = state["upgrades"][which]
        if level >= 2:
            raise GameError("此设施已经升到最高等级。")
        cost = {"workbench": [70, 110], "shelf": [65, 100]}[which][level]
        _spend(state, energy=2, credits=cost)
        state["upgrades"][which] += 1
        if which == "shelf":
            state["energy"] += 1  # New energy capacity is available immediately, once.
            text = f"花费 {cost} 星币升级货架至 Lv.{level + 1}：容量 {_capacity(state)}，每日精力 {_max_energy(state)}。"
        else:
            text = f"花费 {cost} 星币升级工作台至 Lv.{level + 1}：修理更便宜、更可靠。"
        _event(state, "upgrade", "小店焕新", text)
    elif command == "endday":
        old_day = state["day"]
        if state["credits"] < OPERATING_COST:
            state["credits"] = 0
            state["phase"] = "lost"
            _event(state, "end", "灯光暂时熄灭", f"第 {old_day} 天闭店时无法支付 {OPERATING_COST} 星币维护费。试营业结束，你的收藏仍然留在这里。")
        else:
            state["credits"] -= OPERATING_COST
            if old_day >= TOTAL_DAYS:
                won = state["credits"] >= GOAL["credits"] and len(state["collection"]) >= GOAL["collection"]
                state["phase"] = "won" if won else "lost"
                _event(state, "end", "星港为你亮灯" if won else "七天试营业结束",
                       f"支付最后 {OPERATING_COST} 星币维护费后，留下 {state['credits']} 星币、{len(state['collection'])} 件不同藏品。"
                       + ("目标达成！你拥有了属于自己的星际旧货铺。" if won else "本轮未达到 650 星币与 2 件藏品的双目标；收藏与航行的故事都值得保留。"))
            else:
                state["day"] += 1
                state["energy"] = _max_energy(state)
                state["supplier_stock"] = {k: v["stock"] for k, v in SUPPLIERS.items()}
                state["demand"] = _daily_demand(rng)
                _event(state, "day", f"第 {state['day']} 天 · 星港开市", f"支付 {OPERATING_COST} 星币维护费，新一天恢复精力、供应商补货。今日{state['demand']['label']}。")
    else:
        raise GameError(f"未知命令：{command}")
    state["rng"] = rng.getstate()


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
        directory_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _validate_state(state):
    """Detect damaged/incompatible saves without silently resetting or rerolling."""
    if not isinstance(state, dict) or state.get("version") != VERSION:
        raise GameError("不兼容或损坏的存档；请保留原文件。")
    integers = {"revision": (0, 10**12), "day": (1, TOTAL_DAYS), "credits": (0, 10**12),
                "energy": (0, 14), "reputation": (0, 99), "next_crate": (1, 10**12),
                "next_item": (1, 10**12), "event_seq": (1, 10**12)}
    for key, (minimum, maximum) in integers.items():
        value = state.get(key)
        if type(value) is not int or not minimum <= value <= maximum:
            raise GameError(f"存档字段损坏：{key}。")
    if state.get("phase") not in {"active", "won", "lost"}:
        raise GameError("存档阶段损坏。")
    upgrades = state.get("upgrades", {})
    if not isinstance(upgrades, dict) or set(upgrades) != {"workbench", "shelf"} or any(type(v) is not int or v not in (0, 1, 2) for v in upgrades.values()):
        raise GameError("存档设施状态损坏。")
    if state["energy"] > _max_energy(state):
        raise GameError("存档精力超出上限。")
    stock = state.get("supplier_stock", {})
    if not isinstance(stock, dict) or set(stock) != set(SUPPLIERS) or any(type(stock[k]) is not int or not 0 <= stock[k] <= SUPPLIERS[k]["stock"] for k in stock):
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
        for field, lower, upper in [("base_value", 1, 10000), ("condition", 5, 100), ("repairs", 0, 2), ("last_sale_day", 0, TOTAL_DAYS), ("last_repair_day", 0, TOTAL_DAYS)]:
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
        if not isinstance(row, dict) or type(row.get("day")) is not int or not 1 <= row["day"] <= TOTAL_DAYS or not isinstance(row.get("text"), str):
            raise GameError("存档日志损坏。")
    event = state.get("last_event")
    if not isinstance(event, dict) or event.get("seq") != state["event_seq"] or event.get("type") not in {"start", "buy", "reveal", "repair", "sale", "price", "day", "upgrade", "collect", "end"} or not isinstance(event.get("title"), str) or not isinstance(event.get("text"), str):
        raise GameError("存档事件损坏。")
    _rng(state)


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
                 "repair": 1, "price": 2, "sell": 1, "endday": 0, "upgrade": 1, "collect": 1, "restart": 1}
        if command not in arity:
            raise GameError(f"未知命令：{command}；运行 help 查看用法。")
        if len(args) != arity[command] or any(not isinstance(a, str) for a in args):
            raise GameError(f"{command} 需要 {arity[command]} 个参数；运行 help 查看用法。")
        with self.locked():
            if command == "new":
                if self.save_path.exists():
                    raise GameError("已有存档，new 不会重抽；继续 status，或明确 restart --confirm。")
                state = new_state()
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
                if command in {"status", "market", "inspect"}:
                    public = observation(state)
                    result = public
                    if command == "market":
                        result = {k: public[k] for k in ["revision", "day", "credits", "energy", "demand", "suppliers"]}
                    elif command == "inspect":
                        result = next((item for item in public["inventory"] + public["collection"] if item["id"] == args[0].upper()), None)
                        if result is None:
                            raise GameError(f"未找到物品 {args[0]}。盲箱需先 open 才能查看内容。")
                    # Read commands repair a missing/stale public projection, never private state.
                    _atomic_json(self.observation_path, public)
                    return result
                state = copy.deepcopy(state)
                apply_command(state, command, list(args))
            state["revision"] += 1
            _validate_state(state)
            public = observation(state)
            _atomic_json(self.save_path, state)
            _atomic_json(self.observation_path, public)
            return public


def main(argv=None):
    parser = argparse.ArgumentParser(description="星际旧货铺 · 独立经营引擎", usage="%(prog)s [--save PATH] COMMAND [ARGS]", add_help=False)
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
