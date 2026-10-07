import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {applyTrade, finalPrice, offerForecast, percentOne, publicNegotiation} from '../../lib/game-engine/trade-actions.ts';
import {PythonRandom} from '../../lib/game-engine/python-random.ts';
import {CoreGameError} from '../../lib/game-engine/mutation-utils.ts';
import {checkMilestones} from '../../lib/game-engine/projection-core.ts';
import {executeNative} from '../../lib/game-engine/index.ts';

const engine = process.env.STARDUST_ENGINE_SOURCE;
if (!engine) throw Error('Set STARDUST_ENGINE_SOURCE to trusted public v9 engine.py; no real saves are used.');
const oracle = spawnSync('python3', [fileURLToPath(new URL('./trade-oracle.py', import.meta.url)),
  '--engine', path.resolve(engine)], {encoding: 'utf8', maxBuffer: 128 * 1024 * 1024,
  env: {...process.env, PYTHONDONTWRITEBYTECODE: '1'}});
assert.equal(oracle.status, 0, oracle.stderr);
const fixtures = JSON.parse(oracle.stdout);

for (const sample of fixtures.cases) {
  test(`trade Python differential: ${sample.label}`, async () => {
    let state = structuredClone(sample.initial);
    assert.deepEqual(publicNegotiation(state), sample.initial_negotiation);
    for (const step of sample.steps) {
      const input = state, before = structuredClone(state);
      if (step.error === null) state = (await executeNative(input, step.command, step.args)).state;
      else await assert.rejects(executeNative(input, step.command, step.args),
        error => error instanceof CoreGameError && error.message === step.error,
        `${step.command} ${step.args.map(arg => arg.slice(0, 80))}: exact Python error`);
      assert.deepEqual(input, before, 'caller input remains unchanged on success and failure');
      assert.deepEqual(state, step.state, `${step.command}: full private state, RNG, old price snapshots, event and history order`);
      assert.deepEqual(publicNegotiation(state), step.negotiation, 'exact public pending/forecast projection');
    }
  });
}

test('trade forecast exactly matches Python and is isolated from hidden input and mutations', () => {
  assert.ok(fixtures.forecasts.length >= 5);
  for (const sample of fixtures.forecasts) {
    const state = structuredClone(sample.state), before = structuredClone(state);
    for (const expected of sample.forecasts) {
      const result = offerForecast(state, state.negotiation, expected.price);
      assert.deepEqual(result, expected);
      result.modifiers.push({label: 'untrusted', value: 123});
      assert.deepEqual(state, before, 'returned arrays cannot mutate private pending context');
    }
    const publicBefore = publicNegotiation(state);
    state.negotiation.context.reference = 987654.321;
    state.negotiation.context.budget = 3;
    state.walkins.budget = 1;
    state.inventory[0].base_value = 99999;
    state.visitors.forEach(visitor => { visitor.budget = 1; });
    state.reputation = 99;
    state.upgrades.display = 3;
    assert.deepEqual(publicNegotiation(state), publicBefore, 'only public quote/frozen bonuses determine forecast');
    const serialized = JSON.stringify(publicBefore);
    for (const hidden of ['"reference"', '"budget"', '"rng"', '"initial_roll_id"', '"context"']) {
      assert.ok(!serialized.includes(hidden), `${hidden} must not leak`);
    }
  }
});

test('trade Python .1% formatting agrees at rational and half-even boundaries', () => {
  assert.equal(fixtures.formats.length, 25000);
  for (const sample of fixtures.formats) assert.equal(percentOne(sample.value), sample.text, String(sample.value));
  assert.equal(percentOne(0.00125), '0.1%');
  assert.equal(percentOne(0.00625), '0.6%');
  assert.equal(percentOne(0), '0.0%');
});

test('trade helper leaves revision, persisted RNG, and milestone checks to caller', () => {
  const sample = fixtures.cases.find(row => row.label === 'sale-milestone-snapshot-order');
  const state = structuredClone(sample.initial), before = structuredClone(state);
  const rng = PythonRandom.fromState(state.rng);
  applyTrade(state, 'sell', ['I003'], rng);
  assert.equal(state.revision, before.revision);
  assert.deepEqual(state.rng, before.rng);
  assert.notDeepEqual(rng.getstate(), before.rng);
  assert.deepEqual(state.milestones, before.milestones);
  assert.equal(state.last_event.item.collection_quality.min_condition, 70);
  checkMilestones(state);
  assert.equal(state.milestones.length, 1);
  assert.equal(state.last_event.item.collection_quality.min_condition, 70, 'snapshot is historical');
});

test('accept and decline draw no randomness even at zero energy', () => {
  for (const command of ['accept', 'decline']) {
    const sample = fixtures.cases.find(row => row.label === `${command}-free-0`);
    const state = structuredClone(sample.initial), before = structuredClone(state);
    const rng = PythonRandom.fromState(state.rng), oldRng = rng.getstate();
    applyTrade(state, command, ['I001'], rng);
    assert.deepEqual(rng.getstate(), oldRng);
    assert.equal(state.energy, 0);
    assert.equal(state.roll_seq, before.roll_seq);
    assert.deepEqual(state.roll_history, before.roll_history);
    assert.equal('roll' in state.last_event, false, 'free action event does not inherit a previous die');
    if (command === 'accept') assert.equal(state.credits - before.credits, before.negotiation.counter_offer);
  }
});

test('trade event dice record and pending bonuses never alias history', async () => {
  const sample = fixtures.cases.find(row => row.label === 'initial-all-digits-90-99');
  const {state} = await executeNative(sample.initial, 'sell', ['I001']);
  assert.notEqual(state.last_event.roll, state.roll_history.at(-1));
  assert.notEqual(state.last_event.roll.modifiers, state.roll_history.at(-1).modifiers);
  assert.notEqual(state.negotiation.context.modifiers, state.roll_history.at(-1).modifiers);
  const old = structuredClone(state.roll_history);
  state.last_event.roll.explanation = 'changed';
  state.negotiation.context.modifiers.push({label: 'changed', value: 5});
  assert.deepEqual(state.roll_history, old);
});

test('final offer invalid text is rejected before energy and RNG consumption', () => {
  const sample = fixtures.cases.find(row => row.label === 'offer-invalid-price-errors');
  const state = structuredClone(sample.initial), before = structuredClone(state);
  const rng = PythonRandom.fromState(state.rng), oldRng = rng.getstate();
  for (const step of sample.steps) {
    assert.throws(() => applyTrade(state, step.command, step.args, rng),
      error => error instanceof CoreGameError && error.message === step.error);
    assert.deepEqual(state, before);
    assert.deepEqual(rng.getstate(), oldRng);
  }
  assert.throws(() => finalPrice(state.negotiation, undefined), /最终报价须为整数/);
});

test('unsupported trade commands fail closed', () => {
  const state = structuredClone(fixtures.cases[0].initial);
  for (const command of ['buy', 'repair', 'endday', 'preview-offer', 'constructor', '__proto__']) {
    assert.throws(() => applyTrade(state, command, [], PythonRandom.fromState(state.rng)), /command_not_ported/);
  }
});

test('trade differential coverage includes every percentile in both stages', () => {
  assert.ok(fixtures.case_count >= 530, fixtures.case_count);
  assert.ok(fixtures.action_count >= 1250, fixtures.action_count);
  const steps = fixtures.cases.flatMap(row => row.steps).filter(step => step.error === null);
  for (const stage of ['initial', 'final']) {
    const outcomes = new Set(steps.map(step => step.state.last_event?.roll)
      .filter(roll => roll?.stage === stage).map(roll => roll.roll));
    assert.deepEqual([...outcomes].sort((a, b) => a - b), Array.from({length: 100}, (_, i) => i + 1));
  }
  assert.ok(steps.some(step => step.state.roll_seq > 60 && step.state.roll_history.length === 60));
});
