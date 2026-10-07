import test from 'node:test';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {isDeepStrictEqual} from 'node:util';
import {StringDecoder} from 'node:string_decoder';
import path from 'node:path';
import {executeNative} from '../../lib/game-engine/native-engine.ts';
import {observationV9} from '../../lib/game-engine/projection-v9.ts';
import {createInitialState} from '../../lib/game-engine/core-transitions.ts';
import {validateNativeState} from '../../lib/game-engine/native-validation.ts';
import {CoreGameError} from '../../lib/game-engine/mutation-utils.ts';

const source = process.env.STARDUST_ENGINE_SOURCE;
if (!source) throw Error('STARDUST_ENGINE_SOURCE is required; synthetic source fixtures only.');
const marketKeys = ['revision', 'day', 'credits', 'energy', 'demand', 'suppliers', 'daily_event', 'visitors', 'walkins', 'operating_cost'];

// Backpressure reaches Python while native checks are pending. Unlike collecting
// stdout or an eager line-event listener, only the current chunk/record is held.
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

// A mismatch reports its first bounded leaf, never dumps entire fixture states.
function difference(actual, expected, location = '$') {
  if (isDeepStrictEqual(actual, expected)) return '';
  if (actual && expected && typeof actual === 'object' && typeof expected === 'object') {
    for (const key of new Set([...Object.keys(actual), ...Object.keys(expected)])) {
      if (!Object.hasOwn(actual, key) || !Object.hasOwn(expected, key)) return `${location}.${key}: missing/extra key`;
      if (!isDeepStrictEqual(actual[key], expected[key])) return difference(actual[key], expected[key], `${location}.${key}`);
    }
  }
  return `${location}: actual=${JSON.stringify(actual)?.slice(0, 220)} expected=${JSON.stringify(expected)?.slice(0, 220)}`;
}
function same(actual, expected, label) {
  if (!isDeepStrictEqual(actual, expected)) assert.fail(`${label}: ${difference(actual, expected)}`);
}

function readExpected(publicView, probe) {
  const publicResult = structuredClone(publicView);
  let result = publicResult;
  if (probe.command === 'market') result = Object.fromEntries(marketKeys.map(key => [key, publicResult[key]]));
  if (probe.command === 'codex') result = publicResult.codex;
  if (probe.command === 'visitors') result = {day: publicResult.day, visitors: publicResult.visitors, walkins: publicResult.walkins};
  if (probe.command === 'inspect') result = [...publicResult.inventory, ...publicResult.collection].find(item => item.id === probe.args[0].toUpperCase());
  if (probe.command === 'preview-offer') publicResult.negotiation.preview = probe.preview;
  return {observation: publicResult, result};
}

test('public-policy mixed multiday campaigns match the Python oracle at every step', async t => {
  const child = spawn('python3', [fileURLToPath(new URL('./campaign-oracle.py', import.meta.url)), '--engine', path.resolve(source)], {
    env: {...process.env, PYTHONDONTWRITEBYTECODE: '1'}, stdio: ['ignore', 'pipe', 'pipe'],
  });
  let stderr = '';
  child.stderr.on('data', chunk => { stderr = (stderr + chunk).slice(-12000); });
  const closed = new Promise((resolve, reject) => { child.on('error', reject); child.on('close', (code, signal) => resolve({code, signal})); });
  let state, label, summary, records = 0, completed = 0, readCalls = 0, readErrors = 0, publicComparisons = 0;
  const commandSuccesses = new Map();
  const commandFailures = new Map();

  async function checkReads(sample, context) {
    const before = structuredClone(state);
    const viewBefore = structuredClone(sample.observation);
    same(observationV9(state), sample.observation, `${context}: direct full projection`);
    assert.equal(Object.keys(sample.observation).length, 39, `${context}: all 39 public fields`);
    publicComparisons++;
    for (const probe of sample.reads) {
      const expected = probe.error ? null : readExpected(sample.observation, probe);
      // Repeat every read on the same committed state, including error reads.
      for (let repetition = 0; repetition < 2; repetition++) {
        readCalls++;
        if (probe.error) {
          readErrors++;
          await assert.rejects(executeNative(state, probe.command, probe.args), error => error instanceof CoreGameError && error.message === probe.error,
            `${context}: ${probe.command} exact error`);
        } else {
          const read = await executeNative(state, probe.command, probe.args);
          assert.equal(read.mutated, false, `${context}: ${probe.command} is read only`);
          same(read.state, before, `${context}: ${probe.command} private state and complete RNG`);
          same(read.observation, expected.observation, `${context}: ${probe.command} public response`);
          same(read.result, expected.result, `${context}: ${probe.command} command result`);
          publicComparisons++;
        }
        same(state, before, `${context}: ${probe.command} leaves input private state/RNG intact`);
      }
    }
    same(sample.observation, viewBefore, `${context}: expected public source fixture remains immutable`);
  }

  try {
    for await (const sample of jsonLines(child.stdout)) {
      if (sample.type === 'summary') { summary = sample; continue; }
      if (sample.type === 'end') {
        completed++;
        assert.equal(sample.label, label);
        if (sample.endowed) {
          assert.equal(sample.phase, 'active');
          assert.ok(sample.final_day >= 22, 'endowed trajectory crosses the full first week and reaches later days');
        }
        const progress = `${label}: ${sample.steps} commands, day ${sample.final_day}, ${sample.opened} opened, ${sample.sales} sales, ${sample.collection} collected`;
        t.diagnostic(progress);
        if (process.env.STARDUST_CAMPAIGN_PROGRESS === '1') process.stderr.write(`CAMPAIGN_PROGRESS ${progress}\n`);
        state = undefined;
        continue;
      }
      if (sample.type === 'start') {
        label = sample.label;
        assert.equal(state, undefined, 'campaigns are contiguous and not reset midway');
        state = await createInitialState(BigInt(sample.seed));
        if (sample.endowed) state.credits = 12000;
        same(state, sample.initial, `${label}: seeded initial full state`);
        validateNativeState(state);
        await checkReads(sample, `${label} initial`);
        continue;
      }
      assert.equal(sample.type, 'step');
      records++;
      const context = `${label} step ${sample.index}: ${sample.command} ${sample.args.join(' ')} (${sample.tag})`;
      const before = structuredClone(state);
      const input = state;
      if (sample.error !== null) {
        commandFailures.set(sample.command, (commandFailures.get(sample.command) ?? 0) + 1);
        await assert.rejects(executeNative(state, sample.command, sample.args), error => error instanceof CoreGameError && error.message === sample.error, `${context}: exact error`);
        same(state, before, `${context}: rejected transaction has no effects or RNG draw`);
      } else {
        commandSuccesses.set(sample.command, (commandSuccesses.get(sample.command) ?? 0) + 1);
        const result = await executeNative(state, sample.command, sample.args);
        assert.equal(result.mutated, true, `${context}: successful command commits once`);
        same(result.observation, sample.observation, `${context}: returned full public observation`);
        same(result.result, sample.observation, `${context}: returned command result`);
        assert.equal(result.state.revision, before.revision + 1, `${context}: exactly one revision`);
        if (sample.command === 'continue') {
          assert.equal(before.day, 7);
          assert.equal(before.phase, 'week_summary');
          assert.equal(result.state.day, 8);
          assert.equal(result.state.credits, before.credits, 'continue does not charge maintenance twice');
          for (const key of ['inventory', 'collection', 'crates', 'upgrades', 'stats']) same(result.state[key], before[key], `continue preserves ${key}`);
        }
        if (['open', 'price', 'collect', 'replace-collection', 'upgrade', 'accept', 'decline'].includes(sample.command)) {
          same(result.state.rng, before.rng, `${context}: deterministic action consumes no RNG`);
        }
        state = result.state;
      }
      same(input, before, `${context}: caller input is never mutated`);
      same(state, sample.state, `${context}: every private field including full RNG matches`);
      validateNativeState(state);
      // Exercise storage-style JSON rehydration throughout, without creating files.
      state = JSON.parse(JSON.stringify(state));
      await checkReads(sample, context);
    }
    const exit = await closed;
    assert.equal(exit.code, 0, `oracle exited ${JSON.stringify(exit)}: ${stderr}`);
    assert.ok(summary, 'oracle emitted a complete final summary');
    assert.equal(records, summary.action_count);
    assert.equal(completed, summary.case_count);
    assert.equal(completed, 20);
    assert.ok(records >= 5000, 'nontrivial mixed-command trajectories');
    same(Object.fromEntries([...commandSuccesses].sort()), summary.successes, 'independent successful action coverage');
    same(Object.fromEntries([...commandFailures].sort()), summary.failures, 'independent failed action coverage');
    for (const command of ['buy', 'open', 'price', 'repair', 'collect', 'replace-collection', 'upgrade', 'sell', 'accept', 'decline', 'offer', 'endday', 'continue']) {
      assert.ok(summary.successes[command] > 0, `real mixed-run success: ${command}`);
    }
    for (const coverage of ['first-week/won', 'first-week/missed', 'continue/explicit/success', 'continue/repeated-rejected/error',
      'collection/better-replacement/success', 'collection/worse-replacement/error', 'repair/failure', 'repair/success',
      'pending/accept/success', 'pending/decline/success', 'pending/final-offer/success', 'endday/closes-pending',
      'final/success', 'final/failure', 'final/miracle', 'final/fumble',
      'sale/named', 'sale/walkin', 'sale/immediate-no-reroll/error', 'sale/no-reroll-after-price/error',
      'retention/log60', 'retention/roll60', 'crate/carried-overnight']) {
      assert.ok(summary.coverage[coverage] > 0, `required trajectory coverage: ${coverage}`);
    }
    assert.equal(summary.events.length, 6, 'all native daily events arise on mixed trajectories');
    assert.equal(summary.campaigns.filter(campaign => campaign.milestones.includes('voyage_2')).length, 4,
      'long mixed trajectories earn and preserve later milestones');
    assert.ok(readErrors > 0, 'failed inspect/preview reads are repeated without state changes');
    t.diagnostic(`CAMPAIGN_COUNTS ${JSON.stringify({campaigns: completed, commands: records, readCalls, readErrors, publicComparisons, successes: summary.successes, failures: summary.failures, coverage: summary.coverage, events: summary.events, engine_sha256: summary.engine_sha256})}`);
  } finally {
    if (child.exitCode === null) child.kill('SIGTERM');
    await closed;
  }
});
