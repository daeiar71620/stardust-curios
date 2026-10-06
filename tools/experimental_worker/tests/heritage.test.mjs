import test from 'node:test';
import assert from 'node:assert/strict';
import {spawn, spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {StringDecoder} from 'node:string_decoder';
import {isDeepStrictEqual} from 'node:util';
import path from 'node:path';
import {validateV8HeritageState} from '../src/v8-heritage-validation.ts';
import {validateCanonicalState, validateNativeState, NativeStateValidationError} from '../src/native-validation.ts';
import {executeNative} from '../src/native-engine.ts';
import {PythonRandom} from '../src/python-random.ts';
import {applyBasic} from '../src/core-transitions.ts';
import {applyManagement} from '../src/management-actions.ts';
import {applyDay} from '../src/day-actions.ts';
import {applyTrade, offerForecast, finalPrice} from '../src/trade-actions.ts';
import {checkMilestones} from '../src/projection-core.ts';
import {observationV9} from '../src/projection-v9.ts';
import {CoreGameError} from '../src/mutation-utils.ts';
import {initialChance} from '../src/numeric-rules.ts';

const source = process.env.STARDUST_ENGINE_SOURCE;
if (!source) throw Error('Set STARDUST_ENGINE_SOURCE to trusted public v9 engine.py; synthetic heritage tests never read real saves.');
const oracle = spawnSync('python3', [fileURLToPath(new URL('./heritage-fixtures.py', import.meta.url)),
  '--engine', path.resolve(source)], {encoding: 'utf8', maxBuffer: 64 * 1024 * 1024,
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
    if (!operation.path.length) {state = structuredClone(operation.value); continue;}
    let parent = state;
    for (const key of operation.path.slice(0, -1)) parent = parent[key];
    const key = operation.path.at(-1);
    if (operation.op === 'delete') delete parent[key];
    else parent[key] = structuredClone(operation.value);
  }
  return state;
}

// Diagnostics name only the first inconsistent path, never dump whole states.
function mismatch(a, b, here = '$') {
  if (isDeepStrictEqual(a, b)) return '';
  if (a && b && typeof a === 'object' && typeof b === 'object') {
    for (const key of new Set([...Object.keys(a), ...Object.keys(b)])) {
      if (!Object.hasOwn(a, key) || !Object.hasOwn(b, key)) return `${here}.${key}: missing/extra field`;
      if (!isDeepStrictEqual(a[key], b[key])) return mismatch(a[key], b[key], `${here}.${key}`);
    }
  }
  return `${here}: unequal values`;
}
function same(a, b, label) {if (!isDeepStrictEqual(a, b)) assert.fail(`${label}: ${mismatch(a, b)}`);}

function migrationPreserved(before, after, label) {
  const expected = structuredClone(before);
  expected.version = 9;
  expected.budget_upgrade = {from_version: 8, source_day: before.day, source_phase: before.phase, source_roll_seq: before.roll_seq};
  if (expected.negotiation) expected.negotiation.rules_version = 9;
  for (const key of ['event_seq', 'last_event', 'log']) expected[key] = after[key];
  same(after, expected, `${label}: every non-migration field preserved`);
  assert.equal(after.event_seq, before.event_seq + 1);
  assert.equal(after.last_event.type, 'import');
  same(after.log.slice(0, -1), before.log.slice(-59), `${label}: prior bounded log preserved`);
  assert.equal(after.log.at(-1).day, before.day);
  assert.equal(after.log.at(-1).text, after.last_event.text);
  for (const key of ['migration', 'engine_upgrade', 'management_upgrade', 'collection_upgrade']) assert.equal(after[key], null);
  assert.ok(before.roll_history.every(row => row.rules_version === 6), `${label}: only native-v8 dice ancestry`);
}

test('offline heritage gate accepts 482 canonical Python-approved synthetic states without mutation', () => {
  assert.equal(fixture.state_count, 482);
  for (const [label, state] of Object.entries(fixture.states)) {
    const before = structuredClone(state);
    assert.equal(validateV8HeritageState(freeze(state)), undefined, label);
    same(state, before, `${label}: no mutation, reseed, reset, or silent repair`);
    assert.throws(() => validateNativeState(state), NativeStateValidationError, `${label}: native gate stays strict`);
  }
  for (const record of fixture.migrations) migrationPreserved(record.source, fixture.states[record.label], record.label);
});

test('heritage marker, rule cutoff, day cutoff, pending history and common corruption match Python', () => {
  assert.ok(fixture.mutation_count >= 90);
  for (const sample of fixture.mutations) {
    const state = apply(structuredClone(fixture.states[sample.base]), sample.operations);
    const before = structuredClone(state);
    freeze(state);
    if (sample.gate_accept) assert.doesNotThrow(() => validateV8HeritageState(state), sample.label);
    else assert.throws(() => validateV8HeritageState(state), NativeStateValidationError, sample.label);
    same(state, before, `${sample.label}: even rejection leaves state and RNG unchanged`);
    if (sample.gate_accept !== sample.python_accept) {
      assert.ok(sample.label.startsWith('native-') || sample.label === 'boundary-budget_upgrade-None',
        `${sample.label}: every stricter host/ancestry restriction is labelled`);
    }
  }
});

test('internal shared-validator profiles cannot substitute unchecked provenance boundaries', () => {
  const state = fixture.states['old-initial-99'];
  const boundary = {sourceDay: state.budget_upgrade.source_day, sourceRollSeq: state.budget_upgrade.source_roll_seq};
  assert.doesNotThrow(() => validateCanonicalState(state, boundary));
  for (const bad of [{...boundary, sourceDay: boundary.sourceDay + 1}, {...boundary, sourceRollSeq: 0},
    {...boundary, extra: 1}, {...boundary, sourceRollSeq: true}, Object.create(boundary)]) {
    assert.throws(() => validateCanonicalState(state, bad), NativeStateValidationError);
  }
  const noMarker = structuredClone(fixture.states['fresh-0']);
  noMarker.budget_upgrade = null;
  assert.throws(() => validateCanonicalState(noMarker, {sourceDay: 1, sourceRollSeq: 0}), NativeStateValidationError);
});

test('all lawful older imported chains remain outside the native-v8 gate', () => {
  assert.deepEqual(fixture.older_chains.map(row => row.from_version), [1, 2, 3, 4, 5, 6]);
  for (const sample of fixture.older_chains) {
    const before = structuredClone(sample.state);
    assert.equal(sample.state.budget_upgrade.from_version, 8, 'from_version8 alone does not prove native-v8 ancestry');
    assert.notEqual(sample.state.collection_upgrade, null);
    assert.throws(() => validateV8HeritageState(freeze(sample.state)), error => error instanceof NativeStateValidationError
      && error.code === 'unsupported_native_state');
    same(sample.state, before, 'rejected older chain remains untouched');
  }
});

test('frozen old chances, crossed final rules, quality and retained-window edges survive validation', () => {
  const cliff = fixture.states['old-budget-cliff-pending'];
  assert.equal(cliff.negotiation.origin_rules_version, 6);
  assert.equal(cliff.negotiation.rules_version, 9);
  assert.equal(cliff.roll_history.at(-1).threshold, 1);
  assert.equal(initialChance(cliff.negotiation.context, cliff.negotiation.original_price, 6), 1);
  assert.ok(initialChance(cliff.negotiation.context, cliff.negotiation.original_price, 9) > 1);
  validateV8HeritageState(cliff);
  for (let roll = 1; roll <= 100; roll++) {
    for (const prefix of ['old-initial', 'old-final', 'cross-final']) {
      const state = fixture.states[`${prefix}-${roll}`];
      assert.equal(state.roll_history.at(-1).roll, roll);
      assert.equal(state.roll_history.at(-1).rules_version, prefix === 'cross-final' ? 9 : 6);
      validateV8HeritageState(state);
    }
  }
  for (const id of ['mira', 'nox', 'pip', 'luna', 'echo', 'sol', 'ayu', 'bo']) {
    for (const mode of ['pending', 'accept', 'decline', 'offer', 'endday']) validateV8HeritageState(fixture.states[`named-${mode}-${id}`]);
  }
  for (const seq of [59, 60, 61, 62, 64, 65]) {
    const state = fixture.states[`ring-${seq}`];
    assert.equal(state.roll_seq, seq);
    assert.equal(state.roll_history.length, Math.min(seq, 60));
    validateV8HeritageState(state);
  }
  assert.equal(fixture.states['ring-61'].roll_history[0].stage, 'final');
  assert.equal(fixture.states['ring-61'].roll_history[0].rules_version, 9);
  assert.ok(fixture.states['ring-62'].roll_history.every(row => row.rules_version === 9));
  const quality = fixture.states['quality-and-voyage'];
  assert.equal(quality.collection.length, 24);
  assert.equal(quality.milestones.at(-1).id, 'voyage_1');
  assert.equal(quality.collection_upgrade, null, 'native v8 quality progress receives no older-chain grace');
});

test('heritage gate rejects raw bytes, exotic markers and unsafe numbers without getters or randomness', async () => {
  const mutations = [
    s => {s.budget_upgrade.from_version = 8n;},
    s => {s.budget_upgrade.source_day = NaN;},
    s => {s.budget_upgrade.source_roll_seq = Infinity;},
    s => {s.budget_upgrade.source_roll_seq = Number.MAX_SAFE_INTEGER + 1;},
    s => {s.budget_upgrade = new Map();},
    s => {s.budget_upgrade = Object.create({from_version: 8, source_day: 1, source_phase: 'active', source_roll_seq: 0});},
    s => {s.budget_upgrade[Symbol('hidden')] = 1;},
    s => {Object.defineProperty(s.budget_upgrade, 'from_version', {get() {throw Error('getter must never run');}, enumerable: true});},
    s => {Object.defineProperty(s, 'budget_upgrade', {get() {throw Error('getter must never run');}, enumerable: true});},
    s => {Object.defineProperty(s.budget_upgrade, 'extra', {value: 1, enumerable: false});},
    s => {s.roll_history = new Array(1);},
    s => {s.rng[1][624] = false;},
  ];
  const random = Math.random;
  try {
    Math.random = () => {throw Error('validation must not draw randomness');};
    for (const mutate of mutations) {
      const state = structuredClone(fixture.states['fresh-0']);
      mutate(state);
      assert.throws(() => validateV8HeritageState(state), NativeStateValidationError, mutate.toString());
    }
    for (const value of [JSON.stringify(fixture.states['fresh-0']), undefined, new Uint8Array([1, 2]), new Date(0)]) {
      assert.throws(() => validateV8HeritageState(value), NativeStateValidationError);
    }
    validateV8HeritageState(freeze(fixture.states['old-budget-cliff-pending']));
  } finally {Math.random = random;}
  const sample = fixture.states['old-budget-cliff-pending'];
  for (const command of ['status', 'endday']) await assert.rejects(executeNative(sample, command, []), NativeStateValidationError,
    'adding offline validation does not open native runtime admission');
  const secret = 'synthetic-hidden-value-must-not-echo';
  const bad = structuredClone(sample);
  bad.budget_upgrade.from_version = secret;
  assert.throws(() => validateV8HeritageState(bad), error => error instanceof NativeStateValidationError && !error.message.includes(secret));
});

// Strictly test-local dispatch to exercise existing shared action modules. This
// is not an exported runtime path, endpoint, bytes importer, or admission API.
async function offlineTransition(input, command, args) {
  validateV8HeritageState(input);
  const state = structuredClone(input), rng = PythonRandom.fromState(state.rng);
  if (['buy', 'open', 'price'].includes(command)) applyBasic(state, command, args, rng);
  else if (['repair', 'collect', 'replace-collection', 'upgrade'].includes(command)) applyManagement(state, command, args, rng);
  else if (['endday', 'continue'].includes(command)) await applyDay(state, command, rng);
  else applyTrade(state, command, args, rng);
  state.rng = rng.getstate();
  checkMilestones(state);
  state.revision++;
  validateV8HeritageState(state);
  return state;
}

async function* jsonLines(stream) {
  const decoder = new StringDecoder('utf8');
  let pending = '';
  for await (const chunk of stream) {
    pending += decoder.write(chunk);
    let index;
    while ((index = pending.indexOf('\n')) >= 0) {
      const line = pending.slice(0, index);
      pending = pending.slice(index + 1);
      if (line) yield JSON.parse(line);
    }
  }
  pending += decoder.end();
  if (pending.trim()) yield JSON.parse(pending);
}

test('eight genuine-command v8→v9 campaigns match Python private state, RNG and every public field', async t => {
  const child = spawn('python3', [fileURLToPath(new URL('./heritage-campaign.py', import.meta.url)), '--engine', path.resolve(source)], {
    env: {...process.env, PYTHONDONTWRITEBYTECODE: '1'}, stdio: ['ignore', 'pipe', 'pipe'],
  });
  let stderr = '';
  child.stderr.on('data', chunk => {stderr = (stderr + chunk).slice(-12000);});
  const closed = new Promise((resolve, reject) => {child.on('error', reject); child.on('close', (code, signal) => resolve({code, signal}));});
  let state, label, summary, commands = 0, campaigns = 0;
  try {
    for await (const sample of jsonLines(child.stdout)) {
      if (sample.type === 'summary') {summary = sample; continue;}
      if (sample.type === 'end') {
        campaigns++;
        assert.equal(label, sample.label);
        t.diagnostic(`${label}: ${sample.old_commands} old commands, ${sample.steps} new commands; day ${sample.source_day}→${sample.day}, ${sample.roll_seq} rolls`);
        state = undefined;
        continue;
      }
      if (sample.type === 'start') {
        assert.equal(state, undefined);
        state = structuredClone(sample.initial);
        label = sample.label;
        migrationPreserved(sample.source, state, label);
        validateV8HeritageState(state);
      } else {
        assert.equal(sample.type, 'step');
        commands++;
        const before = structuredClone(state), input = state;
        const context = `${label} step${sample.index} ${sample.command} (${sample.tag})`;
        if (sample.error !== null) {
          await assert.rejects(offlineTransition(state, sample.command, sample.args), error => error instanceof CoreGameError && error.message === sample.error,
            `${context}: exact command rejection`);
        } else {
          state = await offlineTransition(state, sample.command, sample.args);
          assert.equal(state.revision, before.revision + 1, `${context}: exactly one revision`);
          if (['open', 'price', 'collect', 'replace-collection', 'upgrade', 'accept', 'decline'].includes(sample.command)) {
            same(state.rng, before.rng, `${context}: no RNG on deterministic command`);
          }
        }
        same(input, before, `${context}: immutable input and rejection rollback`);
        same(state, sample.state, `${context}: all private fields and complete saved RNG`);
      }
      const before = structuredClone(state);
      for (let repeat = 0; repeat < 2; repeat++) {
        validateV8HeritageState(state);
        same(observationV9(state), sample.observation, `${label}: all public fields`);
        if (state.negotiation) {
          const price = state.negotiation.counter_offer + 1;
          if (price < state.negotiation.original_price) {
            assert.equal(finalPrice(state.negotiation, String(price)), price);
            const actual = {...offerForecast(state, state.negotiation, price), suggested: true};
            same(actual, sample.observation.negotiation.preview, `${label}: frozen public final-offer forecast`);
          }
        }
      }
      same(state, before, `${label}: repeated reads and validation never mutate or reroll`);
      state = JSON.parse(JSON.stringify(state)); // Canonical object rehydration, not token-aware importer parity.
    }
    const exit = await closed;
    assert.equal(exit.code, 0, `oracle failed ${JSON.stringify(exit)}: ${stderr}`);
    assert.ok(summary);
    assert.equal(campaigns, 8);
    assert.equal(commands, summary.action_count);
    assert.ok(commands > 2500, commands);
    assert.ok(summary.old_action_count > 1000, summary.old_action_count);
    for (const command of ['buy', 'open', 'price', 'repair', 'collect', 'replace-collection', 'upgrade', 'sell', 'accept', 'decline', 'offer', 'endday', 'continue']) {
      assert.ok(summary.successes[command] > 0, `genuine post-migration command: ${command}`);
    }
    for (const tag of ['migration/pending6', 'migration/day8', 'migration/retained', 'cross-boundary/final9',
      'retention/60', 'retention/old-evicted', 'quality/collect/success', 'quality/replacement/success',
      'quality/cabinet-repair/success', 'pending/repair-lock/error', 'pending/price-lock/error',
      'pending/low-bound/error', 'pending/high-bound/error', 'sale/no-reroll/error', 'summary/continue/success']) {
      assert.ok(summary.coverage[tag] > 0, `required genuine trajectory coverage: ${tag}`);
    }
    t.diagnostic(`${campaigns} campaigns: ${summary.old_action_count} old commands + ${commands} v9 commands; source ${summary.engine_sha256}`);
  } finally {
    if (child.exitCode === null) child.kill('SIGTERM');
    await closed;
  }
});
