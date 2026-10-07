import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import test from "node:test";
import {
  pyRound, clampChance, referenceValue, publicReference, counterCeiling,
  finalChance, initialChance, counterOffer, finalOfferBounds, parseFinalPrice,
  percentileOutcome,
} from "../../lib/game-engine/numeric-rules.ts";

const generated = spawnSync("python3", ["-B",fileURLToPath(new URL("./numeric-oracle.py",import.meta.url))],
  {encoding:"utf8",maxBuffer:128*1024*1024,timeout:120000});
assert.equal(generated.status,0,generated.stderr || generated.error?.message);
const oracle = JSON.parse(generated.stdout);
const bytes = text => Buffer.from(text,"base64");
console.log(`Numeric Python oracle: ${JSON.stringify(oracle.metadata)}`);
console.log(`Numeric Python coverage: ${JSON.stringify(oracle.counts)}`);

function checkInitial(groups, explicitPrices) {
  let count = 0;
  const differences = [];
  for (const group of groups) {
    const expected = bytes(group.expected);
    for (let i=0;i<expected.length;i++) {
      const price = explicitPrices ? group.prices[i] : i+1;
      const actual = initialChance(group.context,price);
      if (actual !== expected[i] && differences.length < 10) {
        differences.push({context:group.context,price,source:group.source,expected:expected[i],actual});
      }
      count++;
    }
  }
  assert.deepEqual(differences,[],`initialChance oracle mismatches: ${JSON.stringify(differences)}`);
  return count;
}

test("Python oracle: round ties + adjacent floats and continuous clamp", () => {
  for (const [input,expected] of oracle.round) assert.equal(pyRound(input),expected,`round(${input})`);
  for (const [input,expected] of oracle.clamp) assert.equal(clampChance(input),expected);
});

test("Python oracle: all catalog references, legal conditions, demand multipliers and public ceiling", () => {
  for (const [base,condition,demand,value,rounded] of oracle.reference) {
    assert.equal(referenceValue(base,condition,demand),value,`reference ${base}/${condition}/${demand}`);
    assert.equal(publicReference(base,condition,demand),rounded);
  }
  for (const [reference,budget,expected] of oracle.ceiling) assert.equal(counterCeiling(reference,budget),expected);
});

test("Python oracle: every legal price for 200 lawful valuations + current regression contexts", () => {
  assert.equal(checkInitial(oracle.initial_sweeps,false),oracle.counts.initial_sweep_prices);
});

test("Python oracle: all hidden base integers 1..10000 sampled at budget and log-floor boundaries", () => {
  assert.equal(checkInitial(oracle.initial_boundaries,true),oracle.counts.initial_boundary_prices);
});

test("Python oracle: final rational thresholds and wide safe-integer arguments", () => {
  let count=0;
  for (const group of oracle.final_sweeps) {
    const expected=bytes(group.expected);
    for (let i=0;i<expected.length;i++) {
      const actual=finalChance(group.modifier,group.counter,group.counter+i+1);
      assert.equal(actual.baseChance,group.base);
      assert.equal(actual.threshold,expected[i]);
      count++;
    }
  }
  assert.equal(count,oracle.counts.final_sweep_prices);
  for (const [modifier,counter,price,[baseChance,threshold]] of oracle.final_extreme) {
    assert.deepEqual(finalChance(modifier,counter,price),{baseChance,threshold});
  }
});

test("Python oracle: counter quote arithmetic and evaluation order", () => {
  for (const [context,asking,expected] of oracle.counter) assert.equal(counterOffer(context,asking),expected);
});

test("Python oracle: final-offer bounds, canonical input and Python whitespace", () => {
  for (const [counter,original,expected] of oracle.bounds) assert.deepEqual(finalOfferBounds(counter,original),expected);
  for (const [raw,counter,original,expected] of oracle.parse) {
    if (expected === null) assert.throws(()=>parseFinalPrice(raw,counter,original),`expected rejection of ${JSON.stringify(raw)}`);
    else assert.equal(parseFinalPrice(raw,counter,original),expected,`parse ${JSON.stringify(raw)}`);
  }
});

test("Python oracle: all100 supplied dice pairs for every threshold1..99", () => {
  for (const [tens,ones,threshold,expected] of oracle.percentile) {
    assert.deepEqual(percentileOutcome(tens,ones,threshold),expected);
  }
});

test("Python oracle: adversarial references that are reachable from valid items still match", () => {
  for (const [context,price,expected,reachableItemReference] of oracle.initial_adversarial) {
    if (reachableItemReference) assert.equal(initialChance(context,price),expected,
      `reachable-reference divergence ${JSON.stringify({context,price})}`);
  }
});

test("UNRESOLVED: global Math.log2 parity at engineered non-item float boundaries", {
  todo: "V8 Math.log2 and this CPython platform libm disagree by an ulp at some floors; arbitrary-reference parity is not established",
}, () => {
  const differences = [];
  for (const [context,price,expected,reachableItemReference] of oracle.initial_adversarial) {
    const actual=initialChance(context,price);
    if (actual !== expected) {
      differences.push({context,price,expected,actual,reachableItemReference});
    }
  }
  console.log(`Adversarial log2 diagnostic: ${differences.length}/${oracle.counts.initial_adversarial} differences; samples=${JSON.stringify(differences.slice(0,5))}`);
  assert.equal(differences.length,0,"known arbitrary-reference Math.log2 mismatches remain; see diagnostic samples above");
});
