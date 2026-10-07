import assert from "node:assert/strict";
import test from "node:test";
import {
  pyRound, clampChance, referenceValue, publicReference, counterCeiling,
  finalChance, initialChance, counterOffer, finalOfferBounds, parseFinalPrice,
  percentileOutcome, NumericRuleError,
} from "../../lib/game-engine/numeric-rules.ts";

const context = (budget = 100, reference = 100, modifier = 0) => ({ budget, reference, modifier });

test("Python no-ndigits rounding is ties-to-even, including negative ties and -0", () => {
  const inputs = [-4.5, -3.5, -2.5, -1.5, -0.5, -0, 0, 0.5, 1.5, 2.5, 3.5, 4.5];
  assert.deepEqual(inputs.map(pyRound), [-4, -4, -2, -2, 0, 0, 0, 0, 2, 2, 4, 4]);
  assert.equal(Object.is(pyRound(-0.5), -0), false);
  assert.equal(pyRound(0.5 - Number.EPSILON), 0);
  assert.equal(pyRound(0.5 + Number.EPSILON), 1);
  assert.equal(pyRound(4503599627370495.5), 4503599627370496);
  for (const value of [NaN, Infinity, -Infinity, "2.5", true]) assert.throws(() => pyRound(value), NumericRuleError);
});

test("continuous clamp retains fractions until v9's final floor", () => {
  assert.deepEqual([-10, 0.5, 1, 58.9, 99, 110].map(clampChance), [1, 1, 1, 58.9, 99, 99]);
  assert.throws(() => clampChance(NaN));
});

test("public valuation retains the engine's IEEE754 multiplication order", () => {
  assert.equal(referenceValue(88, 80, 1.35), 88 * (0.30 + 80 * 0.007) * 1.35);
  assert.equal(publicReference(105, 100), 105);
  assert.equal(publicReference(1, 0), 1);
  assert.equal(counterCeiling(79, 120), 98);
  assert.equal(counterCeiling(100, 120), 120);
  assert.equal(counterCeiling(Number.MAX_SAFE_INTEGER, Number.MAX_SAFE_INTEGER), Number.MAX_SAFE_INTEGER);
});

test("final integer rational formula, clamp and exact division boundaries", () => {
  for (const [bonus, counter, price, baseChance, threshold] of [
    [0, 100, 110, 70, 58], [0, 100, 125, 70, 46], [0, 100, 150, 70, 35],
    [0, 100, 200, 70, 23], [0, 100, 500, 70, 7], [0, 100, 9999, 70, 1],
    [35, 100, 110, 99, 82], [-80, 100, 101, 1, 1],
    [0, 1, 2, 70, 23], [0, 9997, 9998, 70, 69],
    [-69, 1, 2, 1, 1], [-68, 1, 2, 2, 1], [28, 1, 2, 98, 32], [29, 1, 2, 99, 33],
  ]) assert.deepEqual(finalChance(bonus, counter, price), { baseChance, threshold });
  // Numerator and denominator exceed Number's exact integer range here.
  assert.deepEqual(finalChance(0, Number.MAX_SAFE_INTEGER - 1, Number.MAX_SAFE_INTEGER), { baseChance: 70, threshold: 69 });
  assert.throws(() => finalChance(0, 100, 100));
});

test("v9 smooth budget curve documented outputs and cap-before-scaling", () => {
  assert.deepEqual([99, 100, 101, 110, 150, 200, 300].map(p => initialChance(context(), p)), [60, 60, 58, 44, 15, 3, 1]);
  assert.equal(initialChance(context(100, 1000), 125), 66);
  assert.equal(initialChance(context(100, 1000), 200), 33);
  assert.equal(initialChance(context(100, 1), 9999), 1);
});

test("missing/noninteger v9 budgets and invalid domains fail closed", () => {
  for (const budget of [undefined, null, false, true, 0, -1, 100.5, "100", NaN]) {
    assert.throws(() => initialChance({...context(), budget}, 100), NumericRuleError);
  }
  assert.throws(() => initialChance({reference:100, modifier:0}, 100));
  for (const reference of [0, -1, NaN, Infinity]) assert.throws(() => initialChance(context(100, reference), 100));
  for (const price of [0, -1, 1.5, NaN, true]) assert.throws(() => initialChance(context(), price));
});

test("initial thresholds monotone and bounded across every legal price", () => {
  for (const ctx of [context(), context(60,500,45), context(240,30,-30)]) {
    let previous = 99;
    for (let price = 1; price <= 9999; price++) {
      const chance = initialChance(ctx, price);
      assert.ok(Number.isInteger(chance) && chance >= 1 && chance <= previous);
      previous = chance;
    }
  }
});

test("counter quote uses ten-coin valuation buckets and 25-to-20 budget buckets", () => {
  assert.throws(() => counterOffer(context(null), 90), NumericRuleError);
  assert.equal(counterOffer(context(99), 90), 60);
  assert.equal(counterOffer(context(100), 90), 70);
  assert.equal(counterOffer(context(100,1000), 90), 80);
  assert.equal(counterOffer(context(24,1000), 90), 1);
  assert.equal(counterOffer(context(25,1000), 90), 20);
  assert.equal(counterOffer(context(100,1000), 50), 49);
  assert.equal(counterOffer(context(), 1), 1);
});

test("one-coin quote gap exposes no legal final offer", () => {
  assert.deepEqual(finalOfferBounds(1,2), {min:2,max:1,available:false});
  assert.deepEqual(finalOfferBounds(1,3), {min:2,max:2,available:true});
  assert.equal(parseFinalPrice("2",1,3),2);
  for (const raw of ["1", "3", "0", "-1", "2.0", "+2", "02", "2_0", "٢", "２", "2e0", "", "true", "\uFEFF2", "\u001c2"]) {
    assert.throws(() => parseFinalPrice(raw,1,3), NumericRuleError);
  }
  for (const raw of [" 2 ", "\t2\n", "\u00852\u3000", "\u20022\u00a0"]) assert.equal(parseFinalPrice(raw,1,3),2);
});

test("all 100 supplied dice pairs are bijective, with exact success counts for every threshold", () => {
  for (let threshold = 1; threshold <= 99; threshold++) {
    const rolls = new Set();
    let successes = 0;
    for (let tens = 0; tens <= 9; tens++) for (let ones = 0; ones <= 9; ones++) {
      const result = percentileOutcome(tens,ones,threshold);
      rolls.add(result.roll);
      successes += Number(result.success);
      if (result.roll === 1) assert.equal(result.outcome,"miracle");
      if (result.roll === 100) assert.equal(result.outcome,"fumble");
    }
    assert.equal(rolls.size,100);
    assert.equal(successes,threshold);
  }
});

test("numeric helpers are deterministic and leave their context unchanged", () => {
  const frozen = Object.freeze(context());
  assert.equal(initialChance(frozen,101), initialChance(frozen,101));
  assert.equal(counterOffer(frozen,90), counterOffer(frozen,90));
});
