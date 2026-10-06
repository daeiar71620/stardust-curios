/** Bounded fresh-v9 trade mutations and an explicitly public forecast.
 * The dispatcher owns copying, arity, RNG persistence, milestones and revision.
 * Historical/imported rules are a separate validation/integration gate.
 */
import type {GameState, Item, PendingTrade, PublicRecord, TradeContextState, Visitor} from './types.ts';
import type {PythonRandom} from './python-random.ts';
import {CoreGameError, event, itemById, requireActive, spend} from './mutation-utils.ts';
import {hasSet, saleOption} from './projection-core.ts';
import {counterOffer, finalChance, finalOfferBounds, initialChance, NumericRuleError,
  parseFinalPrice, percentileOutcome, referenceValue, TRADE_RULES_VERSION} from './numeric-rules.ts';

const clone = <T>(value: T): T => structuredClone(value);

/** Preserve Python int() failure vs canonical/bounds errors. The numeric helper
 * itself intentionally exposes only canonical-final-price validation. */
export function finalPrice(pending: PendingTrade, raw: string): number {
  const integerWhitespace = /^[\u0009-\u000D\u0020\u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]+|[\u0009-\u000D\u0020\u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]+$/g;
  const stripped = typeof raw === 'string' ? raw.replace(integerWhitespace, '') : '';
  if (!/^[+-]?\p{Decimal_Number}(?:_?\p{Decimal_Number})*$/u.test(stripped)
      || [...stripped].filter(char => /\p{Decimal_Number}/u.test(char)).length > 4300) {
    throw new CoreGameError('最终报价须为整数，且严格高于客人还价、低于初次标价。');
  }
  try {
    return parseFinalPrice(raw, pending.counter_offer, pending.original_price);
  } catch (error) {
    if (error instanceof NumericRuleError) throw new CoreGameError(error.message);
    throw error;
  }
}

/** CPython format(x, '.1%'): binary64 multiply by 100, then exact nearest-even
 * decimal rounding. JS toFixed rounds ties differently and can alter roll text. */
export function percentOne(value: number): string {
  const percent = value * 100;
  if (!Number.isFinite(percent) || percent < 0) throw new Error('invalid_public_premium');
  const bits = new DataView(new ArrayBuffer(8));
  bits.setFloat64(0, percent);
  const binary = bits.getBigUint64(0), exponent = Number((binary >> 52n) & 0x7ffn);
  const significand = (binary & ((1n << 52n) - 1n)) | (exponent === 0 ? 0n : 1n << 52n);
  const power = exponent === 0 ? -1074 : exponent - 1023 - 52;
  let numerator = significand * 10n, denominator = 1n;
  if (power >= 0) numerator <<= BigInt(power); else denominator <<= BigInt(-power);
  let rounded = numerator / denominator;
  const twiceRemainder = numerator % denominator * 2n;
  if (twiceRemainder > denominator || (twiceRemainder === denominator && rounded % 2n === 1n)) rounded++;
  return `${rounded / 10n}.${rounded % 10n}%`;
}

/** Contains no hidden valuation, exact budget, RNG, or initial probability. */
export function offerForecast(_state: GameState, pending: PendingTrade, price: number) {
  const {baseChance, threshold} = finalChance(pending.context.modifier, pending.counter_offer, price);
  return {price, basis: 'public_counter', base_chance: baseChance,
    threshold, probability: threshold / 100,
    premium: (price - pending.counter_offer) / pending.counter_offer,
    modifier: pending.context.modifier, modifiers: clone(pending.context.modifiers),
    critical_probability: 0.01, fumble_probability: 0.01, energy_cost: 1,
    accept_income: pending.counter_offer, success_income: price, failure_income: 0,
    warning: '精确成功率，仅用公开还价和冻结加值；涨幅越大成功率越低。01必成、100必败；最终失败收入0，不能回头接受旧还价。'};
}

export function publicNegotiation(state: GameState): PublicRecord | null {
  const pending = state.negotiation;
  if (pending === null) return null;
  const bounds = finalOfferBounds(pending.counter_offer, pending.original_price);
  return {item_id: pending.item_id, item_name: pending.item_name,
    customer_id: pending.customer_id, customer_name: pending.customer_name,
    original_price: pending.original_price, counter_offer: pending.counter_offer,
    rules_version: pending.rules_version, origin_rules_version: pending.origin_rules_version,
    remaining_offers: 1, final_offer_energy: 1, final_offer_bounds: bounds,
    accept_income: pending.counter_offer, final_failure_income: 0,
    preview: bounds.available ? {...offerForecast(state, pending, bounds.min), suggested: true} : null,
    commands: {accept: `accept ${pending.item_id}`, decline: `decline ${pending.item_id}`,
      preview: `preview-offer ${pending.item_id} 金额`, offer: `offer ${pending.item_id} 金额`}};
}

function tradeContext(state: GameState, item: Item, visitor: Visitor | null): TradeContextState {
  const modifiers: TradeContextState['modifiers'] = [];
  const add = (label: string, value: number) => { if (value) modifiers.push({label, value}); };
  add('口碑', 5 * Math.floor(Math.min(state.reputation, 15) / 5));
  add('展示柜', 5 * state.upgrades.display);
  add('奇物收藏套装', 5 * Number(hasSet(state, 'artifact')));
  add('星灯夜市', state.daily_event.id === 'festival' ? 10 : 0);
  add('星云浓雾', state.daily_event.id === 'fog' ? -10 : 0);
  if (visitor) {
    add(item.kind === visitor.preferred_kind ? '顾客偏爱' : '偏好不合', item.kind === visitor.preferred_kind ? 15 : -10);
    add(item.condition >= visitor.min_condition ? '符合品相期待' : '品相未达期待', item.condition >= visitor.min_condition ? 5 : -10);
  }
  return {reference: referenceValue(item.base_value, item.condition, item.kind === state.demand.kind ? state.demand.multiplier : 1),
    budget: visitor ? visitor.budget : state.walkins.budget, modifiers,
    modifier: modifiers.reduce((sum, entry) => sum + entry.value, 0)};
}

function tradeRoll(state: GameState, rng: PythonRandom, item: Item, visitor: Visitor | null,
  price: number, context: TradeContextState, stage: 'initial' | 'final') {
  // Draw BOTH committed digits before threshold evaluation, just as Python does.
  const tensDigit = rng.randint(0, 9), ones = rng.randint(0, 9);
  const counter = stage === 'final' ? state.negotiation!.counter_offer : null;
  const final = counter !== null ? finalChance(context.modifier, counter, price) : null;
  const base = final?.baseChance ?? null, threshold = final?.threshold ?? initialChance(context, price);
  const outcome = percentileOutcome(tensDigit, ones, threshold);
  let explanation = {
    miracle: '01 · 一见钟情！大成功突破普通意愿与预算，按本次合法报价成交。',
    fumble: '100 · 大失败，客人告辞；今日这件货接待结束。',
    success: '百分骰点数不高于成功阈值，正常成交。',
    failure: '百分骰点数高于成功阈值。',
  }[outcome.outcome];
  if (counter !== null) explanation += ` 基础率${base}%，还价上浮${percentOne((price - counter) / counter)}，成功阈值${threshold}。`;
  if (threshold === 1) explanation += ' 这次报价只有01能成交，成功率1%。';
  const record = {id: ++state.roll_seq, day: state.day, item_id: item.id, item_name: item.name,
    customer_id: visitor?.id ?? null, customer_name: visitor?.name ?? '旅客', stage, die: 'D100',
    ...outcome, modifier: context.modifier, modifiers: clone(context.modifiers),
    threshold, probability: threshold / 100, base_chance: base,
    premium: counter !== null ? (price - counter) / counter : null,
    rules_version: TRADE_RULES_VERSION, counter_offer: counter, price, explanation};
  state.roll_history.push(record);
  state.roll_history = state.roll_history.slice(-60);
  return record;
}

function settleSale(state: GameState, item: Item, visitor: Visitor | null, price: number): number {
  state.credits += price;
  const reputation = (item.rarity === 'legendary' ? 2 : 1) + Number(visitor !== null && item.kind === visitor.preferred_kind);
  state.reputation = Math.min(99, state.reputation + reputation);
  state.stats.sales_count++;
  state.stats.gross_earnings += price;
  item.price = price;
  state.inventory.splice(state.inventory.indexOf(item), 1);
  if (visitor) visitor.status = 'bought';
  return reputation;
}

export function closeNegotiation(state: GameState): void {
  if (state.negotiation) {
    const visitor = state.visitors.find(visitor => visitor.id === state.negotiation!.customer_id);
    if (visitor) visitor.status = 'left';
    state.negotiation = null;
  }
}

function rollText(roll: ReturnType<typeof tradeRoll>): string {
  return `双D10：${String(roll.tens).padStart(2, '0')} + ${roll.ones} → ${String(roll.roll).padStart(2, '0')}；掷低点 ≤ ${roll.threshold}，成功率${roll.threshold}%。${roll.explanation}`;
}

export function applyTrade(state: GameState, command: string, args: string[], rng: PythonRandom): void {
  if (!['sell', 'accept', 'decline', 'offer'].includes(command)) throw new Error(`command_not_ported:${command}`);
  requireActive(state);
  if (command === 'sell') {
    const item = itemById(state, args[0]);
    if (state.negotiation) throw new CoreGameError('还有客人在等你的还价答复；请先 accept、decline 或 offer。');
    if (item.last_sale_day === state.day) throw new CoreGameError('这件物品今天已接待过买家；改价或换客人不能重掷，明天再试。');
    let visitor: Visitor | null = null;
    if (args.length === 2) {
      visitor = state.visitors.find(visitor => visitor.id === args[1].toLowerCase()) ?? null;
      if (visitor === null) throw new CoreGameError('这位顾客今天不在店里；用 visitors 查看。');
      if (visitor.status !== 'waiting') throw new CoreGameError('这位顾客今天已经接待过；明天再安排吧。');
    }
    if (visitor === null && state.walkins.used >= 1) throw new CoreGameError('今日旅客接待已用完；改价、换货或重启不会刷新，明天再试或选择尚未接待的特邀顾客。');
    spend(state, 1);
    const eligibility = saleOption(state, item, visitor);
    if (visitor === null) state.walkins.used++;
    item.last_sale_day = state.day;
    const context = tradeContext(state, item, visitor);
    const roll = tradeRoll(state, rng, item, visitor, item.price, context, 'initial');
    const buyer = visitor?.name ?? '旅客';
    if (visitor) visitor.status = 'left';
    if (roll.success) {
      const rep = settleSale(state, item, visitor, item.price);
      event(state, 'sale', roll.roll === 1 ? '一见钟情 · 01大成功！' : '掷骰成交！',
        rollText(roll) + ` ${buyer}买走「${item.name}」，收入${item.price}星币，口碑+${rep}。`, item);
    } else if (roll.roll === 100) {
      event(state, 'sale', '100大失败 · 客人告辞', rollText(roll), item);
    } else if (!eligibility.counter_eligible) {
      event(state, 'sale', '这次没有还价 · 客人告辞', rollText(roll) +
        ' 公开还价条件未满足：' + eligibility.reasons.join('；') + '。本次收入0，货物留下；今天该货与该买家接待已用。', item);
    } else {
      const offer = counterOffer(context, item.price);
      state.negotiation = {item_id: item.id, item_name: item.name,
        customer_id: visitor?.id ?? null, customer_name: buyer, original_price: item.price,
        counter_offer: offer, day: state.day, context, initial_roll_id: roll.id,
        rules_version: TRADE_RULES_VERSION, origin_rules_version: TRADE_RULES_VERSION};
      if (visitor) visitor.status = 'negotiating';
      event(state, 'negotiation', '客人还了一个价', rollText(roll) +
        ` ${buyer}愿出${offer}星币。接受免费；最终报价须高于还价、低于初价，花1精力，成功率随相对还价涨幅下降；失败收入0，不能再接受旧还价。可先 preview-offer 预览。`, item);
    }
    state.last_event!.roll = clone(roll);
    return;
  }

  const pending = state.negotiation;
  if (pending === null || pending.item_id !== args[0].toUpperCase()) throw new CoreGameError('这件货没有等待答复的还价；用 status 查看。');
  const item = itemById(state, args[0]);
  const visitor = state.visitors.find(visitor => visitor.id === pending.customer_id) ?? null;
  const buyer = pending.customer_name;
  if (command === 'accept') {
    const price = pending.counter_offer;
    closeNegotiation(state);
    const rep = settleSale(state, item, visitor, price);
    event(state, 'sale', '就这个价 · 成交', `接受${buyer}的${price}星币还价，卖出「${item.name}」，口碑+${rep}。没有再掷骰或消耗精力。`, item);
  } else if (command === 'decline') {
    closeNegotiation(state);
    event(state, 'negotiation', '下回有缘', `谢绝${buyer}的还价，「${item.name}」留在货架；今日该货接待结束。`, item);
  } else {
    const price = finalPrice(pending, args[1]);
    spend(state, 1);
    const roll = tradeRoll(state, rng, item, visitor, price, pending.context, 'final');
    closeNegotiation(state);
    item.price = price;
    if (roll.success) {
      const rep = settleSale(state, item, visitor, price);
      event(state, 'sale', roll.roll === 1 ? '最终报价 · 01大成功！' : '最终报价 · 成交！',
        rollText(roll) + ` ${buyer}买走「${item.name}」，收入${price}星币，口碑+${rep}。`, item);
    } else {
      event(state, 'sale', '最终报价 · 客人告辞', rollText(roll) + ' 唯一一次还价已用，本次收入0；不能再接受旧还价，今天不能再出售这件货。', item);
    }
    state.last_event!.roll = clone(roll);
  }
}
