import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { PythonRandom } from '../src/python-random.ts';
import { deriveWalkinBudget, serializePythonRandomState } from '../src/python-rng-domain.ts';
import { CUSTOMERS, KINDS } from '../src/server-data.ts';

const publicSource = process.env.STARDUST_PUBLIC_ENGINE_SOURCE
  ?? fileURLToPath(new URL('../../stardust-curios-v9-current-shop/engine.py', import.meta.url));
const oracle = spawnSync('python', [
  fileURLToPath(new URL('./rng-domain-oracle.py', import.meta.url)), publicSource,
], { encoding: 'utf8', maxBuffer: 16 * 1024 * 1024 });
assert.equal(oracle.status, 0, `Public-source synthetic oracle failed: ${oracle.stderr}`);
const fixture = JSON.parse(oracle.stdout);
let derivations = 0;

function exactDay(text) {
  const big = BigInt(text);
  return big <= BigInt(Number.MAX_SAFE_INTEGER) && big >= BigInt(Number.MIN_SAFE_INTEGER) ? Number(big) : big;
}

function hex(bytes) {
  return Array.from(new Uint8Array(bytes), byte => byte.toString(16).padStart(2, '0')).join('');
}

test('RNG sequence public constants still match the Python source', () => {
  assert.deepEqual(KINDS, fixture.kinds);
  assert.deepEqual(CUSTOMERS, fixture.customers);
});

for (const entry of fixture.domainCases) {
  test(`Python walk-in derivation ${entry.label}`, async () => {
    const rng = PythonRandom.fromState(entry.state);
    assert.equal(serializePythonRandomState(entry.state), entry.serialized);
    for (const derived of entry.derived) {
      const day = exactDay(derived.day);
      const material = new TextEncoder().encode(`walkin-v6:${derived.day}:${entry.serialized}`);
      assert.equal(hex(await crypto.subtle.digest('SHA-256', material)), derived.digest);
      const before = rng.getstate();
      const pending = deriveWalkinBudget(rng, day);
      assert.deepEqual(rng.getstate(), before, 'derivation consumed main RNG synchronously');
      assert.equal(await pending, derived.budget, `day ${derived.day}`);
      assert.deepEqual(rng.getstate(), before, 'derivation consumed main RNG asynchronously');
      assert.equal(derived.walkins_used, 0);
      assert.ok(derived.budget >= 60 && derived.budget <= 120);
      derivations++;
    }
  });
}

for (const [index, entry] of fixture.initialCases.entries()) {
  test(`Python initial RNG sequence ${index}, display ${entry.display}`, async () => {
    const rng = new PythonRandom(BigInt(entry.seed));
    const kind = rng.choice(Object.keys(KINDS));
    const multiplier = rng.choice([1.25, 1.35, 1.45]);
    const demand = {
      label: `${KINDS[kind]}收藏热 · +${Math.round((multiplier - 1) * 100)}%`,
      kind, multiplier,
    };
    assert.deepEqual(demand, entry.demand);
    assert.deepEqual(rng.getstate(), entry.afterDemand, 'daily demand draw order');
    // Selection must complete before drawing ANY visitor budget. Interleaving
    // sample and randint would change both identities and budgets.
    const selected = rng.sample(CUSTOMERS, 3 + Number(entry.display >= 2));
    const visitors = selected.map(([id, name, role, preferredKind, condition, low, high]) => ({
      id, name, role, preferred_kind: preferredKind,
      preference_label: `偏爱${KINDS[preferredKind]}，品相${condition}%以上更喜欢`,
      min_condition: condition, budget_range: [low, high], premium: 1.25,
      status: 'waiting', budget: rng.randint(low, high),
    }));
    assert.deepEqual(visitors, entry.visitors);
    assert.deepEqual(rng.getstate(), entry.afterVisitors, 'visitor draw order');
    assert.equal(await deriveWalkinBudget(rng, 1), entry.walkin.budget);
    assert.deepEqual(rng.getstate(), entry.afterVisitors, 'derived budget changed main stream');
    derivations++;
  });
}

test('walk-in derivation snapshots its state before async hashing', async () => {
  const rng = new PythonRandom(42);
  const initial = rng.getstate();
  const expected = await deriveWalkinBudget(PythonRandom.fromState(initial), 1);
  const pending = deriveWalkinBudget(rng, 1);
  for (let i = 0; i < 1000; i++) rng.random();
  const advanced = rng.getstate();
  assert.equal(await pending, expected);
  assert.deepEqual(rng.getstate(), advanced);
});

test('reopening and same-day repeat derivation do not reroll or advance state', async () => {
  const state = new PythonRandom(20261006).getstate();
  const rng = PythonRandom.fromState(state);
  const budgets = await Promise.all([
    deriveWalkinBudget(rng, 7), deriveWalkinBudget(rng, 7n),
    deriveWalkinBudget(PythonRandom.fromState(JSON.parse(JSON.stringify(state))), 7),
  ]);
  assert.equal(budgets[0], budgets[1]);
  assert.equal(budgets[1], budgets[2]);
  assert.deepEqual(rng.getstate(), state);
});

test('unsupported Gaussian-cache JSON encodings fail explicitly without advancing', async () => {
  for (const cache of [-0, 0, 1, -2.5, 1e-7, 1e21]) {
    const state = new PythonRandom(42).getstate();
    state[2] = cache;
    const rng = PythonRandom.fromState(state);
    assert.throws(() => serializePythonRandomState(state), /null Gaussian cache/);
    await assert.rejects(deriveWalkinBudget(rng, 1), /null Gaussian cache/);
    assert.deepEqual(rng.getstate(), state);
  }
});

test('unsafe, fractional, or coerced day values are rejected without changing RNG', async () => {
  const rng = new PythonRandom(42);
  const before = rng.getstate();
  for (const day of [2 ** 53, -(2 ** 53), 1.5, Infinity, NaN, '1', null, true, {}, undefined]) {
    await assert.rejects(deriveWalkinBudget(rng, day), /safe integer number or bigint/);
    assert.deepEqual(rng.getstate(), before);
  }
  assert.equal(await deriveWalkinBudget(rng, -0), await deriveWalkinBudget(rng, 0n));
});

test('noncanonical state is rejected before serialization', () => {
  const state = new PythonRandom(42).getstate();
  assert.throws(() => serializePythonRandomState([2, state[1], null]));
  assert.throws(() => serializePythonRandomState([3, state[1].slice(1), null]));
  state[1][0] = -1;
  assert.throws(() => serializePythonRandomState(state));
});

test('domain and initial-sequence coverage summary', () => {
  assert.equal(fixture.domainCases.length, 14);
  assert.equal(fixture.initialCases.length, 40);
  assert.equal(derivations, 122);
  console.log(`Verified ${derivations} exact CPython walk-in budgets and 40 demand/visitor initialization sequences; no saves created or read`);
});
