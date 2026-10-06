/**
 * Numeric / bargaining rules extracted from public Stardust engine.py v9.
 * Pure ES2022: no filesystem, network, randomness, state mutation, or Node APIs.
 *
 * Monetary inputs use exact safe integers. Python's unbounded integer final-
 * offer arithmetic is performed with BigInt internally, then clamped to 1..99.
 * Floating formulas deliberately retain Python's operation order. Math.log2
 * is host-dependent: differential tests establish their tested domain, not
 * all-input / every-runtime equivalence with CPython's platform libm. The
 * differential suite records known arbitrary-reference threshold divergences
 * as an explicit TODO; no epsilon adjustment is applied to hide that gap.
 *
 * JavaScript cannot distinguish JSON tokens 100 and 100.0 after JSON.parse.
 * A full save importer must preserve/check Python integer types separately.
 * These helpers do not implement state validation, privacy projection, or RNG.
 */

export const TRADE_RULES_VERSION = 9;
export const PRICE_LIMIT = 9999;
export type TradeRulesVersion = 5 | 6 | 9;

export interface TradeContext {
  readonly reference: number;
  readonly budget?: number | null;
  readonly modifier: number;
}

export interface FinalChance {
  readonly baseChance: number;
  readonly threshold: number;
}

export interface FinalOfferBounds {
  readonly min: number;
  readonly max: number;
  readonly available: boolean;
}

export interface PercentileOutcome {
  readonly tens: number;
  readonly ones: number;
  readonly roll: number;
  readonly success: boolean;
  readonly outcome: "miracle" | "fumble" | "success" | "failure";
}

export class NumericRuleError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "NumericRuleError";
  }
}

function safeInteger(value: unknown, label: string, minimum?: number): asserts value is number {
  if (typeof value !== "number" || !Number.isSafeInteger(value)
      || (minimum !== undefined && value < minimum)) {
    throw new NumericRuleError(`${label} must be an exact safe integer${minimum === undefined ? "" : ` >= ${minimum}`}`);
  }
}

function finiteNumber(value: unknown, label: string): asserts value is number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new NumericRuleError(`${label} must be a finite number`);
  }
}

function positiveNumber(value: unknown, label: string): asserts value is number {
  finiteNumber(value, label);
  if (value <= 0) throw new NumericRuleError(`${label} must be positive`);
}

/** Python round(x), with no ndigits: nearest integer, ties to even, no -0. */
export function pyRound(value: number): number {
  finiteNumber(value, "round input");
  if (Number.isInteger(value)) return value === 0 ? 0 : value;
  const lower = Math.floor(value);
  const fraction = value - lower;
  const rounded = fraction < 0.5 ? lower
    : fraction > 0.5 ? lower + 1
    : lower % 2 === 0 ? lower : lower + 1;
  return rounded === 0 ? 0 : rounded;
}

/** Continuous clamp. Do not floor here: v9 must clamp before budget scaling. */
export function clampChance(value: number): number {
  finiteNumber(value, "chance");
  return Math.max(1, Math.min(99, value));
}

/**
 * engine._reference_value evaluation order. The caller supplies catalog base,
 * never hidden per-item base, when producing a public reference. Demand is 1
 * when the item's category does not match the current demand category.
 */
export function referenceValue(catalogBase: number, condition: number, demandMultiplier = 1): number {
  safeInteger(catalogBase, "catalog base", 1);
  safeInteger(condition, "condition", 0);
  positiveNumber(demandMultiplier, "demand multiplier");
  const value = catalogBase * (0.30 + condition * 0.007) * demandMultiplier;
  positiveNumber(value, "reference value");
  return value;
}

export function publicReference(catalogBase: number, condition: number, demandMultiplier = 1): number {
  const reference = Math.max(1, pyRound(referenceValue(catalogBase, condition, demandMultiplier)));
  safeInteger(reference, "public reference", 1);
  return reference;
}

/** Public upper ask for receiving a counter. This is NOT a purchase-price cap. */
export function counterCeiling(reference: number, budgetUpper: number): number {
  safeInteger(reference, "public reference", 1);
  safeInteger(budgetUpper, "public budget upper bound", 1);
  const ratioCeiling = BigInt(reference) * 5n / 4n;
  return Number(ratioCeiling < BigInt(budgetUpper) ? ratioCeiling : BigInt(budgetUpper));
}

/** engine._final_chance. No hidden valuation, budget, or second budget gate. */
export function finalChance(modifier: number, counter: number, price: number): FinalChance {
  safeInteger(modifier, "modifier");
  safeInteger(counter, "counter", 1);
  safeInteger(price, "final price", 1);
  if (price <= counter) throw new NumericRuleError("final price must exceed counter");
  // Clamp first, without risking unsafe integer addition at extreme modifiers.
  const baseChance = modifier >= 29 ? 99 : modifier <= -69 ? 1 : 70 + modifier;
  const quotient = BigInt(baseChance) * BigInt(counter) / (2n * BigInt(price) - BigInt(counter));
  return { baseChance, threshold: Number(quotient < 1n ? 1n : quotient > 99n ? 99n : quotient) };
}

/**
 * engine._initial_chance, including historical rules 5/6 for pending quotes.
 * Never substitute log(x)/log(2), floor(raw) before scaling, or reassociate the
 * multiplication/division. Each can change threshold boundaries.
 */
export function initialChance(context: TradeContext, price: number, rulesVersion: TradeRulesVersion = TRADE_RULES_VERSION): number {
  if (typeof rulesVersion !== "number" || !Number.isInteger(rulesVersion)
      || (rulesVersion !== 5 && rulesVersion !== 6 && rulesVersion !== 9)) {
    throw new NumericRuleError("未知的初次交易规则版本；未重新掷骰。");
  }
  const budget = context.budget;
  if (rulesVersion === 9 && (typeof budget !== "number" || !Number.isSafeInteger(budget) || budget <= 0)) {
    throw new NumericRuleError("顾客日常预算损坏；未重新掷骰。");
  }
  // Historical null/missing budgets are valid. Other malformed contexts belong
  // to the full engine validator; fail closed here rather than silently coerce.
  if (budget !== undefined && budget !== null) safeInteger(budget, "budget", 1);
  safeInteger(price, "price", 1);
  safeInteger(context.modifier, "modifier");
  positiveNumber(context.reference, "reference");
  const ratio = price / context.reference;
  positiveNumber(ratio, "price/reference");
  const raw = 60 + context.modifier - 50 * Math.log2(ratio);
  if (budget === undefined || budget === null || price <= budget) {
    return clampChance(Math.floor(raw));
  }
  if (rulesVersion < TRADE_RULES_VERSION) return 1;
  // Game prices/budgets are small. Restrict the intermediate integer denominator
  // to exact Number arithmetic so a wider caller cannot silently change the rule.
  const denominator = 2n * BigInt(price) - BigInt(budget);
  if (denominator > BigInt(Number.MAX_SAFE_INTEGER)) {
    throw new NumericRuleError("budget denominator exceeds exact Number range");
  }
  return clampChance(Math.floor(clampChance(raw) * budget / Number(denominator)));
}

/** engine._counter_offer. A coarse binding quote, not an exact budget leak. */
export function counterOffer(context: TradeContext, asking: number): number {
  positiveNumber(context.reference, "reference");
  safeInteger(context.modifier, "modifier");
  safeInteger(asking, "asking price", 1);
  if (context.budget !== undefined && context.budget !== null) safeInteger(context.budget, "budget", 1);
  let offer = Math.max(1, Math.floor(context.reference * (0.75 + context.modifier / 200) / 10) * 10);
  if (context.budget !== undefined && context.budget !== null) {
    const affordable = Number(BigInt(context.budget) / 25n * 20n);
    offer = Math.min(offer, Math.max(1, affordable));
  }
  return Math.max(1, Math.min(asking - 1, offer));
}

export function finalOfferBounds(counter: number, originalPrice: number): FinalOfferBounds {
  safeInteger(counter, "counter", 1);
  safeInteger(originalPrice, "original price", 1);
  if (counter >= Number.MAX_SAFE_INTEGER) throw new NumericRuleError("counter leaves no exact successor");
  const min = counter + 1;
  const max = originalPrice - 1;
  return { min, max, available: min <= max };
}

// Whitespace accepted around ASCII integers by Python int(str), excluding the
// ASCII information separators U+001C..U+001F that str.strip alone would accept.
const PYTHON_INTEGER_WHITESPACE = /^[\u0009-\u000D\u0020\u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]+|[\u0009-\u000D\u0020\u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]+$/g;

/** engine._final_price's canonical positive integer text and strict bounds. */
export function parseFinalPrice(raw: string, counter: number, originalPrice: number): number {
  safeInteger(counter, "counter", 1);
  safeInteger(originalPrice, "original price", 1);
  if (typeof raw !== "string") throw new NumericRuleError("最终报价须为整数，且严格高于客人还价、低于初次标价。");
  const canonical = raw.replace(PYTHON_INTEGER_WHITESPACE, "");
  const price = /^[1-9][0-9]*$/.test(canonical) ? Number(canonical) : NaN;
  if (!Number.isSafeInteger(price) || !(counter < price && price < originalPrice)) {
    throw new NumericRuleError("最终报价须严格高于客人还价、低于初次标价；同价不能重掷，可直接 accept 接受还价。");
  }
  return price;
}

/** Pure resolution of two supplied digits; deliberately performs no RNG draws. */
export function percentileOutcome(tensDigit: number, onesDigit: number, threshold: number): PercentileOutcome {
  safeInteger(tensDigit, "tens digit", 0);
  safeInteger(onesDigit, "ones digit", 0);
  safeInteger(threshold, "threshold", 1);
  if (tensDigit > 9 || onesDigit > 9 || threshold > 99) throw new NumericRuleError("digits must be 0..9 and threshold 1..99");
  const tens = tensDigit * 10;
  const roll = tens + onesDigit || 100;
  const success = roll === 1 || (roll !== 100 && roll <= threshold);
  const outcome = roll === 1 ? "miracle" : roll === 100 ? "fumble" : success ? "success" : "failure";
  return { tens, ones: onesDigit, roll, success, outcome };
}
