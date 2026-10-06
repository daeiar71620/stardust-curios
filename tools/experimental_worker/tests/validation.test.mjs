import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {validateNativeState, NativeStateValidationError} from '../src/native-validation.ts';
import {PythonRandom} from '../src/python-random.ts';
import {newSyntheticState} from '../src/core-transitions.ts';

const engine = process.env.STARDUST_ENGINE_SOURCE;
if (!engine) throw Error('Set STARDUST_ENGINE_SOURCE to trusted public v9 engine.py; validation tests never use real saves.');
const oracle = spawnSync('python3', [fileURLToPath(new URL('./validation-oracle.py', import.meta.url)),
  '--engine', path.resolve(engine)], {encoding: 'utf8', maxBuffer: 64 * 1024 * 1024,
  env: {...process.env, PYTHONDONTWRITEBYTECODE: '1'}});
assert.equal(oracle.status, 0, oracle.stderr);
const fixture = JSON.parse(oracle.stdout);

function freeze(value) {
  if (value && typeof value === 'object') {
    Object.freeze(value);
    for (const child of Object.values(value)) freeze(child);
  }
  return value;
}

function apply(state, operations) {
  for (const operation of operations) {
    if (operation.path.length === 0) {
      state = structuredClone(operation.value);
      continue;
    }
    let parent = state;
    for (const key of operation.path.slice(0, -1)) parent = parent[key];
    const key = operation.path.at(-1);
    if (operation.op === 'delete') delete parent[key];
    else parent[key] = structuredClone(operation.value);
  }
  return state;
}

test('native validation accepts every synthetic Python-approved fixture unchanged', () => {
  assert.ok(fixture.state_count >= 290, fixture.state_count);
  for (const [label, candidate] of Object.entries(fixture.states)) {
    const before = structuredClone(candidate);
    freeze(candidate);
    assert.equal(validateNativeState(candidate), undefined, label);
    assert.deepEqual(candidate, before, `${label}: no mutation, reset, or silent repair`);
  }
});

test('native validation matches the Python mutation corpus plus explicitly labelled native restrictions', () => {
  assert.ok(fixture.mutation_count >= 270, fixture.mutation_count);
  let matched = 0, nativeRestrictions = 0;
  for (const sample of fixture.mutations) {
    const candidate = apply(structuredClone(fixture.states[sample.base]), sample.operations);
    const before = structuredClone(candidate);
    freeze(candidate);
    if (sample.native_accept) {
      assert.doesNotThrow(() => validateNativeState(candidate), sample.label);
    } else {
      assert.throws(() => validateNativeState(candidate), error => error instanceof NativeStateValidationError,
        `${sample.label}: rejected with explicit validation error`);
    }
    assert.deepEqual(candidate, before, `${sample.label}: rejected states are preserved too`);
    if (sample.python_accept === sample.native_accept) matched++;
    else {
      assert.ok(sample.label.startsWith('native-'), 'every difference is explicitly documented');
      nativeRestrictions++;
    }
  }
  assert.ok(matched >= 260, matched);
  assert.ok(nativeRestrictions >= 8, nativeRestrictions);
});

test('native validator preserves rolling history, including only the legitimate leading truncated final', () => {
  for (const sequence of [59, 60, 61, 62, 64]) {
    const candidate = fixture.states[`history-${sequence}`];
    assert.equal(candidate.roll_seq, sequence);
    assert.equal(candidate.roll_history.length, Math.min(sequence, 60));
    assert.equal(candidate.roll_history[0].id, Math.max(1, sequence - 59));
    assert.doesNotThrow(() => validateNativeState(candidate));
  }
  assert.equal(fixture.states['history-61'].roll_history[0].stage, 'final');
  for (const label of ['unpaired-final-before-truncation', 'truncated-final-allowed-only-first', 'two-ordinary-buyers-same-day']) {
    const sample = fixture.mutations.find(row => row.label === label);
    const state = apply(structuredClone(fixture.states[sample.base]), sample.operations);
    assert.throws(() => validateNativeState(state), NativeStateValidationError, label);
  }
});

test('every initial and final percentile outcome, named buyer, settlement, and pending quote is covered', () => {
  for (const stage of ['initial', 'final']) {
    for (let roll = 1; roll <= 100; roll++) {
      const state = fixture.states[`${stage}-${roll}`];
      assert.equal(state.roll_history.at(-1).roll, roll);
      assert.equal(state.roll_history.at(-1).stage, stage);
      validateNativeState(state);
    }
  }
  for (const id of ['mira', 'nox', 'pip', 'luna', 'echo', 'sol', 'ayu', 'bo']) {
    for (const action of ['pending', 'accept', 'decline', 'offer']) validateNativeState(fixture.states[`named-${action}-${id}`]);
  }
});

test('canonical saved RNG is checked exactly, without any advance, cache loss, or reseed', () => {
  for (const index of [0, 1, 623, 624]) {
    for (const cache of [null, 0, 1.25, -4.5]) {
      const state = structuredClone(fixture.states['fresh-0']);
      state.rng[1][624] = index;
      state.rng[2] = cache;
      const saved = structuredClone(state.rng);
      const expected = PythonRandom.fromState(saved);
      const expectedDraws = Array.from({length: 20}, () => expected.randint(0, 9));
      validateNativeState(freeze(state));
      assert.deepEqual(state.rng, saved);
      const actual = PythonRandom.fromState(state.rng);
      assert.deepEqual(Array.from({length: 20}, () => actual.randint(0, 9)), expectedDraws);
      assert.deepEqual(actual.getstate(), expected.getstate());
    }
  }
});

test('legacy versions/provenance and native pending/history rule mismatches fail explicitly', () => {
  for (const field of ['migration', 'engine_upgrade', 'management_upgrade', 'collection_upgrade', 'budget_upgrade']) {
    const state = structuredClone(fixture.states['fresh-0']);
    state[field] = {from_version: 6};
    assert.throws(() => validateNativeState(state), error => error instanceof NativeStateValidationError
      && error.code === 'unsupported_native_state' && error.path === field);
  }
  for (const version of [1, 2, 3, 4, 5, 6, 8, 10]) {
    const state = structuredClone(fixture.states['fresh-0']);
    state.version = version;
    assert.throws(() => validateNativeState(state), error => error instanceof NativeStateValidationError
      && error.code === 'unsupported_native_state');
  }
  for (const field of ['rules_version', 'origin_rules_version']) {
    const state = structuredClone(fixture.states['initial-99']);
    state.negotiation[field] = 6;
    assert.throws(() => validateNativeState(state), error => error instanceof NativeStateValidationError
      && error.code === 'unsupported_native_state');
  }
  const state = structuredClone(fixture.states['initial-99']);
  state.roll_history[0].rules_version = 6;
  assert.throws(() => validateNativeState(state), error => error instanceof NativeStateValidationError
    && error.code === 'unsupported_native_state');
});

test('non-JSON numeric/type hazards and malformed native shape fail closed without coercion', () => {
  const mutations = [
    s => {s.credits = NaN;}, s => {s.energy = Infinity;}, s => {s.revision = 1n;},
    s => {s.stats.sales_count = Number.MAX_SAFE_INTEGER + 1;}, s => {s.roll_seq = undefined;},
    s => {s.rng[2] = Infinity;}, s => {s.rng[2] = NaN;}, s => {s.rng[1][0] = true;},
    s => {s.rng[1].length = 624;}, s => {s.rng[1].push(1);}, s => {s.rng[1][624] = true;},
    s => {s.daily_event.energy_delta = false;}, s => {s.daily_event.sale_multiplier = true;},
    s => {s.log = new Array(1);}, s => {s.discovered = new Array(1);},
    s => {s.upgrades = new Date(0);}, s => {s.last_event.item = [];},
    s => {s.walkins = Object.create({day: 1, used: 0, budget: 100});},
    s => {Object.defineProperty(s.upgrades, 'shelf', {get() {throw Error('getter must not run');}, enumerable: true});},
    s => {s.upgrades[Symbol('hidden')] = 1;},
  ];
  for (const mutate of mutations) {
    const state = structuredClone(fixture.states['fresh-0']);
    mutate(state);
    assert.throws(() => validateNativeState(state), NativeStateValidationError, mutate.toString());
  }
  for (const root of [undefined, Symbol('state'), () => {}, new Date(0), new Map()]) {
    assert.throws(() => validateNativeState(root), NativeStateValidationError);
  }
});

test('fresh Worker-generated states validate and the validator never consults global randomness', async () => {
  const inputs = await Promise.all([0, 42, 123, 2n ** 128n + 17n].map(seed => newSyntheticState(seed)));
  const random = Math.random;
  try {
    Math.random = () => {throw Error('validation must not generate randomness');};
    for (const state of inputs) {
      const rng = structuredClone(state.rng);
      validateNativeState(freeze(state));
      assert.deepEqual(state.rng, rng);
    }
  } finally {Math.random = random;}
});

test('error details identify the field without disclosing its hidden contents', () => {
  const state = structuredClone(fixture.states['initial-99']);
  const secret = 'synthetic-private-secret-do-not-echo';
  state.negotiation.context.reference = secret;
  assert.throws(() => validateNativeState(state), error => error instanceof NativeStateValidationError
    && error.path === 'negotiation.context.reference' && !error.message.includes(secret));
});

test('raw save import is not implemented: input text is rejected and JSON numeric-token ambiguity is documented', () => {
  const state = structuredClone(fixture.states['fresh-0']);
  assert.throws(() => validateNativeState(JSON.stringify(state)), NativeStateValidationError);
  // The host Number values are identical after parsing. No object-only validator
  // can use this observation to claim Python int-vs-float token importer parity.
  const integerToken = JSON.parse('{"revision":1}');
  const floatToken = JSON.parse('{"revision":1.0}');
  assert.deepEqual(integerToken, floatToken);
  validateNativeState({...state, ...integerToken});
  validateNativeState({...state, ...floatToken});
});
