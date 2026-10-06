import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {applyManagement} from '../src/management-actions.ts';
import {PythonRandom} from '../src/python-random.ts';
import {CoreGameError} from '../src/mutation-utils.ts';
import {checkMilestones, observationCore} from '../src/projection-core.ts';

const engine = process.env.STARDUST_ENGINE_SOURCE;
if (!engine) throw Error('Set STARDUST_ENGINE_SOURCE to trusted public v9 engine.py; no real saves are used.');
const oracle = spawnSync('python3', [
  fileURLToPath(new URL('./management-oracle.py', import.meta.url)), '--engine', path.resolve(engine),
], {encoding: 'utf8', maxBuffer: 128 * 1024 * 1024, env: {...process.env, PYTHONDONTWRITEBYTECODE: '1'}});
assert.equal(oracle.status, 0, oracle.stderr);
const fixtures = JSON.parse(oracle.stdout);

function transition(input, command, args, projection) {
  const state = structuredClone(input);
  const rng = PythonRandom.fromState(state.rng);
  applyManagement(state, command, args, rng);
  state.rng = rng.getstate();
  checkMilestones(state);
  state.revision++;
  return {state, observation: projection ? observationCore(state) : null};
}

for (const sample of fixtures.cases) {
  test(`management Python differential: ${sample.label}`, () => {
    let state = structuredClone(sample.initial);
    if (sample.projection) assert.deepEqual(observationCore(state), sample.initial_observation, 'initial full public projection');
    for (const step of sample.steps) {
      const before = structuredClone(state);
      const input = state;
      if (step.error === null) {
        const result = transition(input, step.command, step.args, sample.projection);
        state = result.state;
        assert.deepEqual(result.observation, step.observation, `${step.command}: full public projection`);
      } else {
        assert.throws(() => transition(input, step.command, step.args, sample.projection),
          error => error instanceof CoreGameError && error.message === step.error,
          `${step.command} ${step.args}: exact error`);
      }
      assert.deepEqual(input, before, 'caller input unchanged on both success and failure');
      assert.deepEqual(state, step.state, `${step.command}: full private state, RNG, event order and locks`);
    }
  });
}

test('management leaves revision, RNG persistence and milestone checks to dispatcher', () => {
  const sample = fixtures.cases.find(row => row.label === 'collect-milestone-snapshot-order');
  const state = structuredClone(sample.initial);
  const rng = PythonRandom.fromState(state.rng);
  const before = structuredClone(state);
  applyManagement(state, 'collect', ['I002'], rng);
  assert.equal(state.revision, before.revision);
  assert.deepEqual(state.rng, before.rng);
  assert.deepEqual(state.milestones, before.milestones);
  assert.equal(state.last_event.item.collection_quality.min_condition, 70);
  checkMilestones(state);
  assert.equal(state.milestones.length, 1);
  assert.equal(observationCore(state).collection[1].collection_quality.min_condition, 75);

  const repair = structuredClone(fixtures.cases[0].initial);
  const repairRng = PythonRandom.fromState(repair.rng);
  const persisted = structuredClone(repair.rng);
  const item = repair.inventory[0] ?? repair.collection.find(item => item.catalog_id === 'coffee');
  applyManagement(repair, 'repair', [item.id], repairRng);
  assert.deepEqual(repair.rng, persisted, 'helper must not write back the mutable RNG');
  assert.notDeepEqual(repairRng.getstate(), persisted, 'exact repair draws must still be consumed');
});

test('replacement preserves the same objects at their existing positions', () => {
  const sample = fixtures.cases.find(row => row.label === 'replacement-bot-66');
  const state = structuredClone(sample.initial);
  const old = state.collection[1], replacement = state.inventory[1];
  const oldBefore = structuredClone(old), replacementBefore = structuredClone(replacement);
  const rng = PythonRandom.fromState(state.rng), beforeRng = rng.getstate();
  const beforeEnergy = state.energy;
  applyManagement(state, 'replace-collection', [replacement.id], rng);
  assert.equal(state.collection[1], replacement);
  assert.equal(state.inventory[1], old);
  assert.deepEqual(old, {...oldBefore, collected: false});
  assert.deepEqual(replacement, {...replacementBefore, collected: true});
  assert.equal(state.energy, beforeEnergy - 1, 'bot-set reward does not retrigger');
  assert.deepEqual(rng.getstate(), beforeRng, 'replacement consumes no RNG');
});

test('pending negotiation stays outside this milestone public projection envelope', () => {
  for (const sample of fixtures.cases.filter(row => !row.projection)) {
    assert.throws(() => observationCore(sample.initial), /state_shape_not_ported/);
  }
});

test('management helper fails closed for unsupported commands', () => {
  const state = structuredClone(fixtures.cases[0].initial);
  for (const command of ['sell', 'endday', 'constructor', '__proto__']) {
    assert.throws(() => applyManagement(state, command, [], PythonRandom.fromState(state.rng)), /command_not_ported/);
  }
});

test('management oracle covers both repair branches, clamps, and all four commands', () => {
  assert.ok(fixtures.case_count >= 290, fixtures.case_count);
  assert.ok(fixtures.action_count >= 500, fixtures.action_count);
  const steps = fixtures.cases.flatMap(row => row.steps);
  assert.deepEqual([...new Set(steps.map(step => step.command))].sort(), ['collect', 'repair', 'replace-collection', 'upgrade']);
  for (const prefix of ['修理失手：', '修理成功：']) {
    assert.ok(steps.some(step => step.error === null && step.state.last_event.text.startsWith(prefix)), prefix);
  }
  for (const condition of [5, 100]) {
    assert.ok(steps.some(step => step.error === null && step.command === 'repair' && step.state.last_event.item.condition === condition));
  }
});
