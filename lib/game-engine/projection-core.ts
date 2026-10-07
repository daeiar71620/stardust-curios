/** Shared native-v9 rules and public observation fields. */
import { CATALOG, COLORS, KINDS, MILESTONES, SET_RULES, SUPPLIERS, TRADE_RULES, UPGRADE_RULES } from './server-data.ts';
import { pyRound, referenceValue } from './numeric-rules.ts';
import type { GameState, Item, Kind, Milestone, PublicRecord, SupplierId, UpgradeId, Visitor } from './types.ts';
const kinds = Object.keys(KINDS) as Kind[];
const clone = <T>(v: T): T => structuredClone(v);
export function hasSet(s: GameState, kind: Kind) { return new Set(s.collection.filter(i => i.kind === kind).map(i => i.catalog_id)).size >= 3; }
export const maxEnergy = (s: GameState) => 12 + s.upgrades.shelf + Number(hasSet(s, 'bot')) + s.daily_event.energy_delta;
export const operatingCost = (s: GameState) => Math.max(4, 14 + s.daily_event.cost_delta - 4 * Number(hasSet(s, 'plant')));
export const capacity = (s: GameState) => 7 + 3 * s.upgrades.shelf;
export const supplierCost = (s: GameState, id: SupplierId) => SUPPLIERS[id].cost - (id === 'salvage' ? s.daily_event.salvage_discount : 0);
export const repairCost = (s: GameState, item: Item) => Math.max(3, pyRound(({ common: 15, rare: 28, legendary: 50 }[item.rarity]) * (1 - 0.18 * s.upgrades.workbench)) - s.daily_event.repair_discount - 4 * Number(hasSet(s, 'tool')));
export function itemReference(s: GameState, item: Item) { const catalog = CATALOG.find(row => row[0] === item.catalog_id); if (!catalog)
    throw Error('unknown_catalog_identity'); return referenceValue(catalog[4], item.condition, item.kind === s.demand.kind ? s.demand.multiplier : 1); }
export function nextMilestone(s: GameState): Milestone {
    let m: Milestone;
    const n = s.milestones.length;
    if (n < MILESTONES.length)
        m = clone(MILESTONES[n]);
    else {
        const voyage = n - MILESTONES.length + 1;
        m = { id: `voyage_${voyage}`, title: `星海长航 · 第${voyage}章`, description: '长期经营继续；收藏数量上限24种、品相上限90%、品质主题上限5套，现金与口碑目标延续原规则。', min_condition: Math.min(90, 85 + voyage), targets: { credits: 5000 + 3000 * voyage, collection: Math.min(CATALOG.length, 15 + 2 * voyage), reputation: Math.min(99, 40 + 10 * voyage), collection_categories: 5, quality_themes: Math.min(5, 3 + voyage) } };
    }
    return m;
}
function qualityCounts(s: GameState, min: number) { const qualified = new Map(s.collection.filter(i => i.condition >= min).map(i => [i.catalog_id, i])); const counts = Object.fromEntries(kinds.map(k => [k, [...qualified.values()].filter(i => i.kind === k).length])) as Record<Kind, number>; return { count: qualified.size, counts }; }
export function goalValues(s: GameState, m = nextMilestone(s)) { const q = qualityCounts(s, m.min_condition); return { credits: s.credits, collection: q.count, reputation: s.reputation, upgrades: Object.values(s.upgrades).reduce((a, b) => a + b, 0), collection_categories: Object.values(q.counts).filter(x => x > 0).length, quality_themes: Object.values(q.counts).filter(x => x >= 3).length } as Record<string, number>; }
export function checkMilestones(s: GameState) { if (s.first_week_result === 'pending' || s.phase === 'lost')
    return; for (let i = 0; i < MILESTONES.length + 1; i++) {
    const m = nextMilestone(s), v = goalValues(s, m);
    if (!Object.entries(m.targets).every(([k, n]) => v[k] >= n))
        break;
    s.milestones.push({ id: m.id, title: m.title, day: s.day });
    s.log.push({ day: s.day, text: `阶段达成：${m.title}。新的长期目标已开启。` });
    s.log = s.log.slice(-60);
} }
function itemQuality(s: GameState, item: Item) { const m = nextMilestone(s), min = m.min_condition, met = item.condition >= min, collected = item.collected; let reason: string; if (!met)
    reason = `品相${item.condition}%低于本阶段${min}%，还差${min - item.condition}个百分点；可个人珍藏，不计入合格目标`;
else
    reason = `达到本阶段${min}%品相门槛` + (collected ? '，计入合格收藏' : '，入柜后计入合格收藏'); return { min_condition: min, condition_met: met, counted: Boolean(collected && met), reason }; }
export function saleOption(s: GameState, item: Item, visitor: Visitor | null) {
    const ref = Math.max(1, pyRound(itemReference(s, item))), maximum = Math.floor(ref * 5 / 4), range = visitor ? [...visitor.budget_range] : [60, 120], minimum = visitor ? visitor.min_condition : 45, preference = !visitor || item.kind === visitor.preferred_kind, condition = item.condition >= minimum;
    const reasons: string[] = [];
    if (item.price < 2)
        reasons.push('标价没有低于初价的合法整数还价空间');
    if (item.price > maximum)
        reasons.push(`标价超过公开参考价125%的${maximum}星币上限`);
    if (item.price > range[1])
        reasons.push(`标价超过公开预算区间上限${range[1]}星币`);
    if (!preference)
        reasons.push('类别不合顾客偏好');
    if (!condition)
        reasons.push(`品相未达到${minimum}%`);
    const available = s.phase === 'active' && s.energy >= 1 && s.negotiation === null && !item.collected && item.last_sale_day !== s.day && (visitor ? visitor.status === 'waiting' : s.walkins.used < 1);
    return { customer_id: visitor ? visitor.id : null, customer_name: visitor ? visitor.name : '旅客', available, counter_eligible: reasons.length === 0, reasons, public_reference: ref, max_counter_ask: Math.min(maximum, range[1]), budget_range: range, min_condition: minimum, preference_match: preference, condition_met: condition, ask: item.price, warning: (reasons.length === 0 ? '普通失败会提出一次还价；100仍直接离店。' : '普通失败直接离店，不会还价；01仍可按标价成交。') + '正式尝试花1精力并用掉该买家今日接待；本货今日不能改价换客重试。' + '日常预算是消费舒适线，超出后初次成功率平滑下降；精确预算与初次概率不预告。' };
}
function publicRepair(s: GameState, item: Item) { const cost = repairCost(s, item), reasons: string[] = []; if (s.phase !== 'active')
    reasons.push('当前不在营业阶段'); if (item.condition >= 100)
    reasons.push('已是完美品相'); if (item.repairs >= 2)
    reasons.push('已用完两次修理机会'); if (item.last_repair_day === s.day)
    reasons.push('今天已经修理过'); if (s.negotiation?.item_id === item.id)
    reasons.push('该物品正在还价中'); if (s.energy < 2)
    reasons.push('精力不足2点'); if (s.credits < cost)
    reasons.push('星币不足'); return { available: reasons.length === 0, reasons, cost, energy_cost: 2, command: `repair ${item.id}` }; }
function publicReplacement(s: GameState, item: Item) { if (item.collected)
    return null; const old = s.collection.find(i => i.catalog_id === item.catalog_id); if (!old)
    return null; const reasons: string[] = []; if (s.phase !== 'active')
    reasons.push('当前不在营业阶段'); if (item.condition <= old.condition)
    reasons.push('品相必须严格高于柜中同款'); if (s.negotiation?.item_id === item.id)
    reasons.push('该物品正在还价中'); if (s.energy < 1)
    reasons.push('精力不足1点'); return { available: reasons.length === 0, reasons, cabinet_item_id: old.id, cabinet_condition: old.condition, energy_cost: 1, command: `replace-collection ${item.id}` }; }
export function publicItem(s: GameState, item: Item): PublicRecord { const estimate = itemReference(s, item); return { id: item.id, art_id: item.catalog_id, name: item.name, rarity: item.rarity, kind: item.kind, color: COLORS[item.rarity], condition: item.condition, value_estimate: [Math.max(1, Math.trunc(estimate * 0.82)), Math.max(2, Math.ceil(estimate * 1.20))], public_reference: Math.max(1, pyRound(estimate)), sale_options: [null, ...s.visitors].map(v => saleOption(s, item, v)), repair_cost: repairCost(s, item), price: item.price, origin: item.origin, collection_quality: itemQuality(s, item), repair: publicRepair(s, item), collection_replacement: publicReplacement(s, item), description: item.description, collected: item.collected, sale_attempted_today: item.last_sale_day === s.day, repair_attempted_today: item.last_repair_day === s.day, repairs_remaining: Math.max(0, 2 - item.repairs), negotiating: Boolean(s.negotiation && s.negotiation.item_id === item.id) }; }
function publicCodex(s: GameState) { const collected = new Set(s.collection.map(i => i.catalog_id)), discovered = new Set([...s.discovered, ...collected, ...s.inventory.map(i => i.catalog_id)]); return { total: CATALOG.length, discovered: discovered.size, collected: collected.size, entries: CATALOG.map((row, index) => ({ slot: index + 1, discovered: discovered.has(row[0]), collected: collected.has(row[0]), ...(discovered.has(row[0]) ? { art_id: row[0], name: row[1], rarity: row[2], kind: row[3], description: row[5] } : {}) })) }; }
function publicCampaign(s: GameState) { const m = nextMilestone(s), values = goalValues(s, m), labels: Record<string, string> = { credits: '现金', collection: '合格收藏', reputation: '口碑', upgrades: '设施总等级', collection_categories: '合格类别', quality_themes: '品质主题' }; const goals = Object.entries(m.targets).map(([key, target]) => ({ key, label: labels[key], current: values[key], target, met: values[key] >= target })); return { title: s.first_week_result === 'pending' ? '七天首周' : '星港长期经营', stage_index: s.milestones.length, first_week_result: s.first_week_result, completed_milestones: clone(s.milestones), next_milestone: { id: m.id, title: m.title, description: m.description, goals, ready: goals.every(g => g.met), min_condition: m.min_condition, legacy_grace: false }, can_continue: s.phase === 'week_summary', continue_command: s.phase === 'week_summary' ? 'continue' : null, unlimited: true }; }
function collectionProgress(s: GameState) { const m = nextMilestone(s), values = goalValues(s, m), q = qualityCounts(s, m.min_condition), labels: Record<string, string> = { collection: '合格收藏', collection_categories: '合格类别', quality_themes: '品质主题' }; const requirements = Object.entries(m.targets).filter(([key]) => key in labels).map(([key, target]) => ({ key, label: labels[key], current: values[key], target, met: values[key] >= target })); return { personal_count: new Set(s.collection.map(i => i.catalog_id)).size, qualified_count: values.collection, qualified_categories: values.collection_categories, quality_themes: values.quality_themes, min_condition: m.min_condition, legacy_grace: false, requirements, missing: requirements.filter(g => !g.met).map(g => `${g.label}还差${g.target - g.current}`), categories: kinds.map(id => ({ id, name: KINDS[id], qualified_count: q.counts[id], theme_complete: q.counts[id] >= 3 })) }; }
// Whitelist historical public item snapshots; do not copy arbitrary private fields.
type Schema = null | {
    [key: string]: Schema;
} | [
    Schema
];
const fields = (names: string, nested: Record<string, Schema> = {}): Record<string, Schema> => ({ ...Object.fromEntries(names.split(' ').map(n => [n, null])), ...nested });
const SALE = fields('customer_id customer_name available counter_eligible public_reference max_counter_ask min_condition preference_match condition_met ask warning', { budget_range: [null], reasons: [null] });
const ITEM = fields('id art_id name rarity kind color condition public_reference repair_cost price origin description collected sale_attempted_today repair_attempted_today repairs_remaining negotiating', { value_estimate: [null], sale_options: [SALE], collection_quality: fields('min_condition condition_met counted reason'), repair: fields('available cost energy_cost command', { reasons: [null] }), collection_replacement: fields('available cabinet_item_id cabinet_condition energy_cost command', { reasons: [null] }) });
function whitelist(value: unknown, schema: Schema): unknown { if (schema === null)
    return value === null || typeof value === 'string' || typeof value === 'boolean' || typeof value === 'number' && Number.isFinite(value) ? value : null; if (Array.isArray(schema))
    return Array.isArray(value) ? value.map(v => whitelist(v, schema[0])) : []; if (value === null)
    return null; if (!value || typeof value !== 'object' || Array.isArray(value))
    return {}; const row = value as PublicRecord; return Object.fromEntries(Object.entries(schema).filter(([key]) => key in row).map(([key, sub]) => [key, whitelist(row[key], sub)])); }
export function observationBase(s: GameState): PublicRecord { const upgrades = (Object.keys(UPGRADE_RULES) as UpgradeId[]).map(id => { const rule = UPGRADE_RULES[id], level = s.upgrades[id]; return { id, name: rule.name, level, max_level: 3, next_cost: level < 3 ? rule.costs[level] : null, effect: rule.effects[level], next_effect: level < 3 ? rule.effects[level + 1] : null }; }); return { version: 9, revision: s.revision, day: s.day, total_days: 7, credits: s.credits, reputation: s.reputation, energy: s.energy, max_energy: maxEnergy(s), goal: { credits: 650, collection: 2 }, phase: s.phase, inventory: s.inventory.map(i => publicItem(s, i)), crates: s.crates.map(c => ({ id: c.id, supplier: c.supplier, name: c.name })), collection: s.collection.map(i => publicItem(s, i)), suppliers: (Object.keys(SUPPLIERS) as SupplierId[]).map(id => ({ ...SUPPLIERS[id], cost: supplierCost(s, id), stock: s.supplier_stock[id] })), upgrades: clone(s.upgrades), demand: { label: s.demand.label, kind: s.demand.kind, multiplier: s.demand.multiplier }, last_event: whitelist(s.last_event, fields('seq type title text', { item: ITEM })), log: s.log.map(e => ({ day: e.day, text: e.text })), capacity: capacity(s), operating_cost: operatingCost(s), upgrade_costs: Object.fromEntries(upgrades.map(u => [u.id, u.next_cost])), upgrade_details: upgrades, campaign: publicCampaign(s), collection_progress: collectionProgress(s), daily_event: whitelist(s.daily_event, fields('id title description sale_multiplier salvage_discount repair_discount cost_delta energy_delta')), visitors: s.visitors.map(v => ({ id: v.id, name: v.name, role: v.role, preferred_kind: v.preferred_kind, preference_label: v.preference_label, min_condition: v.min_condition, budget_range: [...v.budget_range], premium: v.premium, status: v.status, attempted_today: v.status !== 'waiting' })), walkins: { daily_limit: 1, used: s.walkins.used, remaining: Math.max(0, 1 - s.walkins.used), budget_range: [60, 120], min_condition: 45, visit_rule: '每天1次；正式sell无论成交、还价或离店都占用，改价/换货/重启不刷新；次日重置' }, codex: publicCodex(s), collection_sets: kinds.map(id => ({ id, name: SET_RULES[id][0], description: SET_RULES[id][1], required: 3, current: new Set(s.collection.filter(i => i.kind === id).map(i => i.catalog_id)).size, completed: hasSet(s, id), perk: SET_RULES[id][1] })), stats: { crates_opened: s.stats.crates_opened, sales_count: s.stats.sales_count, gross_earnings: s.stats.gross_earnings, days_traded: s.stats.days_traded }, migration: null, engine_upgrade: null, management_upgrade: null, collection_upgrade: null, budget_upgrade: null, negotiation: null, last_roll: null, roll_history: [], trade_rules: clone(TRADE_RULES) }; }
