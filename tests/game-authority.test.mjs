import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';
import {DatabaseSync} from 'node:sqlite';
import ts from 'typescript';
import * as engine from '../lib/game-engine/index.ts';
import * as sql from '../lib/game-sql.mjs';
import * as hash from '../lib/hash.ts';

// Synthetic, in-memory integration tests. No live API, production save, or network.
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const compiled = new Map();
const plain = value => JSON.parse(JSON.stringify(value));
const input = (operation_id, expected_revision, command, args = []) => ({operation_id, expected_revision, command, args});
const reject = (promise, code) => assert.rejects(promise, error => error.code === code);
const forbiddenKeys = new Set(['private_json', 'rng', 'cargo', 'budget', 'base_value', 'catalog_id', 'context', 'initial_roll_id']);
function noHidden(value) {
  if (value && typeof value === 'object') for (const [key, child] of Object.entries(value)) {
    assert.ok(!forbiddenKeys.has(key), 'Private field leaked: ' + key);
    noHidden(child);
  }
}
function load(file, imports, extras = {}) {
  if (!compiled.has(file)) compiled.set(file, ts.transpileModule(fs.readFileSync(path.join(root, file), 'utf8'), {
    compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022}, fileName: file,
  }).outputText);
  const context = {exports: {}, JSON, Object, Date, Uint8Array, TextEncoder, TextDecoder, Request, Response, URL,
    crypto, ...extras, require(specifier) {
      assert.ok(Object.hasOwn(imports, specifier), 'Unexpected import: ' + specifier);
      return imports[specifier];
    }};
  vm.runInNewContext(compiled.get(file), context, {filename: file});
  return context.exports;
}
function harness(t) {
  const raw = new DatabaseSync(':memory:');
  for (const file of fs.readdirSync(path.join(root, 'drizzle')).filter(file => file.endsWith('.sql')).sort()) {
    raw.exec(fs.readFileSync(path.join(root, 'drizzle', file), 'utf8'));
  }
  t.after(() => raw.close());
  const h = {raw, reads: [], writes: [], failAt: -1, seedCalls: 0, afterReceiptMiss: null, afterStateRead: null};
  const db = {prepare(statement) {
    return {sql: statement, args: [], bind(...args) { this.args = args; return this; }, async first() {
      h.reads.push(statement);
      const result = raw.prepare(statement).get(...this.args) ?? null;
      if (statement.includes('core_g1_receipts') && !result && h.afterReceiptMiss) {
        const hook = h.afterReceiptMiss; h.afterReceiptMiss = null; await hook();
      }
      if (statement.includes('revision,private_json') && h.afterStateRead) {
        const hook = h.afterStateRead; h.afterStateRead = null; await hook();
      }
      return result;
    }};
  }, async batch(statements) {
    raw.exec('BEGIN');
    try {
      for (const [index, statement] of statements.entries()) {
        if (index === h.failAt) throw new Error('synthetic transaction failure');
        h.writes.push(statement.sql);
        raw.prepare(statement.sql).run(...statement.args);
      }
      raw.exec('COMMIT');
    } catch (error) { raw.exec('ROLLBACK'); throw error; }
  }};
  h.auth = load('lib/site-auth.ts', {});
  h.api = load('lib/game-authority.ts', {'@/db': {getDatabase: () => db}, './hash': hash,
    './site-auth': h.auth, './server-art-manifest': {ART_VERSION: 'synthetic-public-build'},
    './game-engine/index': engine, './game-sql.mjs': sql}, {
      crypto: {randomUUID: () => crypto.randomUUID(), getRandomValues(bytes) {
        h.seedCalls++; assert.equal(bytes.length, 32); return crypto.getRandomValues(bytes);
      }},
    });
  h.route = load('app/api/game/state/route.ts', {'@/lib/game-authority': h.api, '@/lib/site-auth': h.auth});
  h.snapshot = user => raw.prepare('SELECT * FROM core_g1_state WHERE owner_user_id=?').get(user);
  h.privateState = user => JSON.parse(h.snapshot(user).private_json);
  h.receipts = user => raw.prepare('SELECT count(*) AS n FROM core_g1_receipts WHERE owner_user_id=?').get(user).n;
  h.archives = user => raw.prepare('SELECT * FROM game_archives WHERE owner_user_id=? ORDER BY revision').all(user);
  h.put = (user, state, mode = 'test') => {
    engine.validateNativeState(state);
    raw.prepare('INSERT INTO core_g1_state(owner_user_id,revision,private_json,public_json,last_operation_id,game_id,game_mode,updated_at) VALUES(?,?,?,?,?,?,?,?)')
      .run(user, state.revision, JSON.stringify(state), JSON.stringify(engine.observationV9(state)), null, 'synthetic-' + user, mode, '2026-10-01T00:00:00.000Z');
  };
  h.act = (user, value) => h.api.gameAction(user, h.api.gameInput(value));
  h.run = async (user, command, args = []) => {
    const before = h.snapshot(user), revision = before?.revision ?? 0;
    const result = await h.act(user, input('op' + (h.receipts(user) + 1), revision, command, args));
    assert.equal(result.revision, revision + 1);
    assert.equal(h.snapshot(user).revision, revision + 1);
    assert.equal(result.public_digest, await hash.sha256(h.snapshot(user).public_json));
    assert.equal(result.verification, 'same_authority_atomic_commit');
    assert.equal(result.stream_id, h.snapshot(user).game_id);
    noHidden(result); noHidden(await h.api.gameState(user));
    return result;
  };
  return h;
}
let negotiationFixture;
async function pendingFixture() {
  if (!negotiationFixture) negotiationFixture = (async () => {
    for (let seed = 1; seed < 150; seed++) {
      let state = await engine.createInitialState(seed);
      state = (await engine.executeNative(state, 'buy', ['salvage'])).state;
      state = (await engine.executeNative(state, 'open', ['C001'])).state;
      state.inventory[0].condition = 90;
      state.inventory[0].price = 100;
      engine.validateNativeState(state);
      for (const option of engine.observationV9(state).inventory[0].sale_options.filter(option => option.counter_eligible)) {
        const args = ['I001', ...(option.customer_id ? [option.customer_id] : [])];
        const pending = (await engine.executeNative(state, 'sell', args)).state;
        if (pending.negotiation && pending.negotiation.original_price > pending.negotiation.counter_offer + 1) return {state, args, pending};
      }
    }
    throw new Error('No lawful synthetic negotiation found');
  })();
  return structuredClone(await negotiationFixture);
}

test('latest migration preserves old G2 bytes and backfills timestamps only from the same owner and last operation', async t => {
  const raw = new DatabaseSync(':memory:'); t.after(() => raw.close());
  const migration = '0005_icy_frank_castle.sql';
  for (const file of fs.readdirSync(path.join(root, 'drizzle')).filter(file => file.endsWith('.sql') && file < migration).sort()) {
    raw.exec(fs.readFileSync(path.join(root, 'drizzle', file), 'utf8'));
  }
  const state = await engine.createInitialState(20261006);
  const privateBytes = JSON.stringify(state, null, 2) + '\n';
  const publicBytes = JSON.stringify(engine.observationV9(state), null, 1) + '\n';
  const owners = ['matching-owner', 'other-owner', 'missing-owner', 'wrong-operation', 'invalid-receipt', 'no-operation'];
  for (const owner of owners) raw.prepare('INSERT INTO core_g1_state VALUES(?,?,?,?,?)')
    .run(owner, state.revision, privateBytes, publicBytes, owner === 'no-operation' ? null : 'shared-operation');
  const receipts = [
    ['matching-old', 'matching-owner', {operation_id: 'older-operation', committed_at: '2026-09-30T00:00:00.000Z'}],
    ['matching-current', 'matching-owner', {operation_id: 'shared-operation', committed_at: '2026-10-01T01:02:03.000Z'}],
    ['other-current', 'other-owner', {operation_id: 'shared-operation', committed_at: '2026-10-02T04:05:06.000Z'}],
    ['wrong-operation', 'wrong-operation', {operation_id: 'different-operation', committed_at: '2026-10-03T00:00:00.000Z'}],
    ['invalid-receipt', 'invalid-receipt', 'synthetic malformed receipt JSON'],
    ['no-operation', 'no-operation', {operation_id: null, committed_at: '2026-10-04T00:00:00.000Z'}],
  ];
  for (const [key, owner, receipt] of receipts) raw.prepare('INSERT INTO core_g1_receipts VALUES(?,?,?,?)')
    .run(key, owner, 'synthetic-request-hash-' + key, typeof receipt === 'string' ? receipt : JSON.stringify(receipt, null, 2) + '\n');
  const oldColumns = 'owner_user_id,revision,private_json,public_json,last_operation_id';
  const beforeStates = raw.prepare('SELECT ' + oldColumns + ' FROM core_g1_state ORDER BY owner_user_id').all();
  const beforeReceipts = raw.prepare('SELECT * FROM core_g1_receipts ORDER BY receipt_key').all();
  raw.exec(fs.readFileSync(path.join(root, 'drizzle', migration), 'utf8'));
  assert.deepEqual(raw.prepare('SELECT ' + oldColumns + ' FROM core_g1_state ORDER BY owner_user_id').all(), beforeStates);
  assert.deepEqual(raw.prepare('SELECT * FROM core_g1_receipts ORDER BY receipt_key').all(), beforeReceipts);
  for (const row of raw.prepare('SELECT * FROM core_g1_state').all()) {
    assert.equal(row.game_id, 'g2-test'); assert.equal(row.game_mode, 'test');
    const expected = row.owner_user_id === 'matching-owner' ? '2026-10-01T01:02:03.000Z'
      : row.owner_user_id === 'other-owner' ? '2026-10-02T04:05:06.000Z' : null;
    assert.equal(row.updated_at, expected, row.owner_user_id);
  }
  assert.equal(raw.prepare('SELECT count(*) AS n FROM game_archives').get().n, 0);
});

test('uninitialized state reads revision zero without private data or creating a game', async t => {
  const h = harness(t), result = await h.api.gameState('uninitialized');
  assert.deepEqual(plain(result.body), {initialized: false, synthetic: true, mode: 'test', stream_id: 'uninitialized',
    revision: 0, updated_at: null, build: h.api.VIEWER_BUILD, observation: null});
  assert.equal(h.reads.length, 1); assert.ok(!h.reads[0].includes('private_json'));
  await reject(h.api.gameQuery('uninitialized', {command: 'status', args: []}), 'initialize_game_first');
  await reject(h.act('uninitialized', input('buy', 0, 'buy', ['salvage'])), 'initialize_game_first');
  assert.equal(h.snapshot('uninitialized'), undefined); assert.equal(h.writes.length, 0); assert.equal(h.seedCalls, 0);
});

test('initialize defaults to test and explicit formal mode uses private crypto seeds', async t => {
  const h = harness(t);
  const a = await h.run('first', 'initialize');
  const b = await h.run('second', 'initialize', ['formal']);
  const c = await h.run('third', 'initialize', ['test']);
  assert.equal(a.mode, 'test'); assert.equal(a.synthetic, true);
  assert.equal(b.mode, 'formal'); assert.equal(b.synthetic, false); assert.equal(c.mode, 'test');
  assert.equal(h.seedCalls, 3);
  assert.equal(new Set([a.stream_id, b.stream_id, c.stream_id]).size, 3);
  assert.notDeepEqual(h.privateState('first').rng, h.privateState('second').rng);
  for (const user of ['first', 'second', 'third']) {
    engine.validateNativeState(h.privateState(user));
    assert.equal(h.receipts(user), 1); assert.equal(h.archives(user).length, 0);
    assert.equal((await h.api.gameState(user)).body.updated_at, h.snapshot(user).updated_at);
  }
});

test('explicit new games retain monotonic revision and archive exact prior private/public bytes and mode', async t => {
  const h = harness(t);
  await h.run('restart', 'initialize', ['formal']);
  await h.run('restart', 'buy', ['salvage']);
  await h.run('restart', 'open', ['C001']);
  const before = h.snapshot('restart'), old = h.privateState('restart');
  const restarted = await h.run('restart', 'initialize');
  const after = h.privateState('restart'), archive = h.archives('restart');
  assert.equal(restarted.revision, before.revision + 1); assert.equal(restarted.mode, 'test');
  assert.notEqual(restarted.stream_id, before.game_id);
  assert.equal(after.day, 1); assert.equal(after.credits, 260); assert.equal(after.energy, 12);
  assert.deepEqual(after.inventory, []); assert.deepEqual(after.collection, []); assert.deepEqual(after.crates, []);
  assert.notDeepEqual(after.rng, old.rng); assert.equal(archive.length, 1);
  for (const key of ['owner_user_id', 'game_id', 'revision', 'private_json', 'public_json', 'game_mode']) assert.equal(archive[0][key], before[key], key);
  assert.equal(archive[0].archived_at, restarted.committed_at);
  const snapshot = h.snapshot('restart');
  assert.deepEqual(plain(await h.act('restart', input('op4', 3, 'initialize'))), plain(restarted));
  assert.deepEqual(h.snapshot('restart'), snapshot); assert.equal(h.archives('restart').length, 1);
});

test('explicit initialization archives an obsolete save byte-for-byte without importing or parsing it', async t => {
  const h = harness(t); h.put('obsolete', await engine.createInitialState(3), 'formal');
  const privateBytes = 'synthetic obsolete private bytes, deliberately not JSON';
  const publicBytes = 'synthetic obsolete public bytes, deliberately not JSON';
  h.raw.prepare('UPDATE core_g1_state SET revision=?,private_json=?,public_json=? WHERE owner_user_id=?')
    .run(19, privateBytes, publicBytes, 'obsolete');
  const result = await h.run('obsolete', 'initialize');
  assert.equal(result.revision, 20); assert.equal(h.privateState('obsolete').day, 1);
  const archived = h.archives('obsolete'); assert.equal(archived.length, 1);
  assert.equal(archived[0].private_json, privateBytes); assert.equal(archived[0].public_json, publicBytes);
  assert.equal(archived[0].revision, 19); assert.equal(archived[0].game_mode, 'formal');
});

test('old retries replay exactly and stale IDs or revisions cannot operate on the replacement game', async t => {
  const h = harness(t);
  const initial = await h.run('replay', 'initialize');
  const buy = await h.run('replay', 'buy', ['salvage']);
  await h.run('replay', 'initialize', ['formal']);
  const before = h.snapshot('replay'), archives = h.archives('replay');
  assert.deepEqual(plain(await h.act('replay', input('op1', 0, 'initialize'))), plain(initial));
  assert.deepEqual(plain(await h.act('replay', input('op2', 1, 'buy', ['salvage']))), plain(buy));
  await reject(h.act('replay', input('op2', 1, 'buy', ['curated'])), 'operation_id_conflict');
  await reject(h.act('replay', input('op2', 3, 'buy', ['salvage'])), 'operation_id_conflict');
  await reject(h.act('replay', input('stale', 2, 'open', ['C001'])), 'revision_conflict');
  await reject(h.act('replay', input('stale-initialize', 2, 'initialize')), 'revision_conflict');
  assert.deepEqual(h.snapshot('replay'), before); assert.deepEqual(h.archives('replay'), archives); assert.equal(h.receipts('replay'), 3);
});

test('old G2 receipt namespace and hash replay unchanged before and after a new game', async t => {
  const h = harness(t), state = await engine.createInitialState(20261006);
  state.revision = 27; h.put('legacy', state);
  const request = input('old-g2-operation', 26, 'endday');
  const key = await hash.sha256(JSON.stringify(['core-g1', 'legacy', request.operation_id]));
  const requestHash = await hash.sha256(JSON.stringify([request.expected_revision, request.command, request.args]));
  const receipt = {ok: true, synthetic: true, milestone: 'G2: native-v9 synthetic only', operation_id: request.operation_id,
    command: 'endday', revision: 27, public_digest: await hash.sha256(h.snapshot('legacy').public_json),
    committed_at: '2026-10-01T00:00:00.000Z', verification: 'same_authority_atomic_commit'};
  h.raw.prepare('INSERT INTO core_g1_receipts VALUES(?,?,?,?)').run(key, 'legacy', requestHash, JSON.stringify(receipt));
  const before = h.snapshot('legacy');
  assert.deepEqual(plain(await h.act('legacy', request)), receipt); assert.deepEqual(h.snapshot('legacy'), before);
  await h.run('legacy', 'initialize', ['formal']);
  const current = h.snapshot('legacy');
  assert.deepEqual(plain(await h.act('legacy', request)), receipt); assert.deepEqual(h.snapshot('legacy'), current);
  assert.equal(h.archives('legacy')[0].private_json, before.private_json);
});

test('all thirteen native mutations persist the canonical engine result', async t => {
  const h = harness(t), covered = new Set();
  async function nativeRun(user, command, args = []) {
    const expected = await engine.executeNative(h.privateState(user), command, args);
    await h.run(user, command, args);
    assert.deepEqual(h.privateState(user), expected.state);
    assert.deepEqual(JSON.parse(h.snapshot(user).public_json), expected.observation);
    covered.add(command);
  }
  h.put('actions', await engine.createInitialState(20261006));
  await nativeRun('actions', 'buy', ['salvage']); await nativeRun('actions', 'open', ['C001']);
  await nativeRun('actions', 'price', ['I001', '123']); await nativeRun('actions', 'repair', ['I001']);
  await nativeRun('actions', 'collect', ['I001']);
  h.put('upgrade', await engine.createInitialState(5)); await nativeRun('upgrade', 'upgrade', ['shelf']);
  const replacement = h.privateState('actions'), previous = replacement.collection[0];
  replacement.energy = 5; replacement.credits = 500; previous.condition = 50;
  const better = {...structuredClone(previous), id: 'I999', condition: 90, collected: false};
  replacement.inventory.push(better); replacement.next_item = 1000; h.put('replace', replacement);
  await nativeRun('replace', 'replace-collection', ['I999']);
  assert.equal(h.privateState('replace').collection[0].id, 'I999');
  h.put('days', await engine.createInitialState(5));
  for (let day = 0; day < 7; day++) await nativeRun('days', 'endday');
  assert.equal(h.privateState('days').phase, 'week_summary'); await nativeRun('days', 'continue');
  assert.equal(h.privateState('days').day, 8);
  const {state, args, pending} = await pendingFixture(); h.put('sell', state); await nativeRun('sell', 'sell', args);
  for (const command of ['accept', 'decline', 'offer']) {
    h.put(command, pending);
    await nativeRun(command, command, [pending.negotiation.item_id, ...(command === 'offer' ? [String(pending.negotiation.counter_offer + 1)] : [])]);
    assert.equal(h.privateState(command).negotiation, null);
  }
  assert.deepEqual([...covered].sort(), plain(h.api.ACTION_NAMES).filter(name => name !== 'initialize').sort());
});

test('all six queries are byte-pure for stored state, receipt count, archive count, and RNG', async t => {
  const h = harness(t), {pending} = await pendingFixture(); h.put('reads', pending);
  const before = h.snapshot('reads');
  const queries = [['status', []], ['market', []], ['codex', []], ['visitors', []], ['inspect', [pending.negotiation.item_id]],
    ['preview-offer', [pending.negotiation.item_id, String(pending.negotiation.counter_offer + 1)]]];
  for (const [command, args] of queries) {
    const result = await h.api.gameQuery('reads', h.api.gameQueryInput({command, args}));
    const expected = await engine.executeNative(pending, command, args);
    assert.equal(result.revision, pending.revision); assert.deepEqual(plain(result.result), expected.result); noHidden(result);
    assert.equal(expected.mutated, false); assert.deepEqual(expected.state, pending);
    assert.deepEqual(h.snapshot('reads'), before); assert.equal(h.receipts('reads'), 0); assert.equal(h.archives('reads').length, 0);
  }
  assert.equal(h.writes.length, 0);
  assert.equal((await h.api.gameState('reads')).body.observation.negotiation.preview.suggested, true);
});

test('invalid native operations and damaged native saves cannot write or create receipts', async t => {
  const h = harness(t); h.put('errors', await engine.createInitialState(9));
  for (const [command, args] of [['open', ['missing']], ['buy', ['unknown']], ['continue', []]]) {
    const before = h.snapshot('errors');
    await assert.rejects(h.act('errors', input('invalid-' + command, before.revision, command, args)), error => error.status === 422);
    assert.deepEqual(h.snapshot('errors'), before); assert.equal(h.receipts('errors'), 0);
  }
  const invalid = h.privateState('errors'); invalid.visitors[0].budget = 100000000;
  h.raw.prepare('UPDATE core_g1_state SET private_json=? WHERE owner_user_id=?').run(JSON.stringify(invalid), 'errors');
  const before = h.snapshot('errors');
  await assert.rejects(h.act('errors', input('bad', before.revision, 'endday')), /Native v9 state rejected/);
  await assert.rejects(h.api.gameQuery('errors', {command: 'status', args: []}), /Native v9 state rejected/);
  assert.deepEqual(h.snapshot('errors'), before); assert.equal(h.receipts('errors'), 0); assert.equal(h.writes.length, 0);
});

test('single shared command metadata defines validator arities and read/mutation boundaries', t => {
  const h = harness(t);
  for (const [command, definition] of Object.entries(engine.NATIVE_COMMANDS)) {
    assert.equal(Object.isFrozen(definition), true); assert.equal(Object.isFrozen(definition.argumentCounts), true);
    for (let count = 0; count < 4; count++) {
      const args = Array(count).fill('x');
      const accept = definition.readOnly ? () => h.api.gameQueryInput({command, args}) : () => h.api.gameInput(input('id', 1, command, args));
      if (definition.argumentCounts.includes(count)) accept(); else assert.throws(accept, error => error.code === 'invalid_arguments');
      const wrong = definition.readOnly ? () => h.api.gameInput(input('id', 1, command, args)) : () => h.api.gameQueryInput({command, args});
      assert.throws(wrong, error => error.code === 'invalid_arguments');
    }
  }
  for (const args of [[], ['test'], ['formal']]) h.api.gameInput(input('id', 1000000000000, 'initialize', args));
  for (const args of [['seed'], ['test', 'formal'], ['test', '1'], [1]]) assert.throws(() => h.api.gameInput(input('id', 1, 'initialize', args)));
  for (const value of [null, [], {}, input('', 1, 'endday'), input('x'.repeat(81), 1, 'endday'), input('a/b', 1, 'endday'),
    ...[-1, 1.5, 1000000000001, NaN, '1'].map(revision => input('id', revision, 'endday')),
    {...input('id', 0, 'initialize'), seed: 1}, input('id', 1, 'buy', [5]), input('id', 1, 'buy', ['x'.repeat(81)]),
    ...['import', 'restart', 'reset', '__proto__', 'constructor'].map(command => input('id', 1, command))]) {
    assert.throws(() => h.api.gameInput(value), error => error.code === 'invalid_arguments');
  }
});

test('concurrent identical initialize and new-game requests produce one receipt and one archive', async t => {
  const h = harness(t), first = input('same', 0, 'initialize');
  const results = await Promise.all([h.act('same', first), h.act('same', first)]);
  assert.deepEqual(plain(results[0]), plain(results[1])); assert.equal(h.receipts('same'), 1); assert.equal(h.snapshot('same').revision, 1);
  const before = h.snapshot('same'), next = input('restart', 1, 'initialize', ['formal']);
  const restarted = await Promise.all([h.act('same', next), h.act('same', next)]);
  assert.deepEqual(plain(restarted[0]), plain(restarted[1])); assert.equal(h.receipts('same'), 2);
  assert.equal(h.snapshot('same').revision, 2); assert.equal(h.archives('same').length, 1);
  assert.equal(h.archives('same')[0].private_json, before.private_json);
});

test('concurrent identical buys charge once and persist exactly the canonical RNG result', async t => {
  const h = harness(t); h.put('buyer', await engine.createInitialState(55));
  const before = h.privateState('buyer'), request = input('same-buy', before.revision, 'buy', ['salvage']);
  const results = await Promise.all([h.act('buyer', request), h.act('buyer', request), h.act('buyer', request)]);
  assert.deepEqual(plain(results[0]), plain(results[1])); assert.deepEqual(plain(results[1]), plain(results[2]));
  const expected = (await engine.executeNative(before, 'buy', ['salvage'])).state;
  assert.deepEqual(h.privateState('buyer'), expected); assert.equal(h.receipts('buyer'), 1);
});

test('different concurrent IDs and conflicting payloads allow one canonical commit', async t => {
  const h = harness(t);
  for (const sameId of [false, true]) {
    const user = sameId ? 'same-id' : 'different-ids'; h.put(user, await engine.createInitialState(55));
    const before = h.privateState(user);
    const values = [input('one', before.revision, 'buy', ['salvage']), input(sameId ? 'one' : 'two', before.revision, 'buy', ['curated'])];
    const results = await Promise.allSettled(values.map(value => h.act(user, value)));
    assert.equal(results.filter(result => result.status === 'fulfilled').length, 1);
    assert.equal(results.filter(result => result.status === 'rejected' && result.reason.code === (sameId ? 'operation_id_conflict' : 'revision_conflict')).length, 1);
    const winner = results.findIndex(result => result.status === 'fulfilled');
    assert.deepEqual(h.privateState(user), (await engine.executeNative(before, values[winner].command, values[winner].args)).state);
    assert.equal(h.receipts(user), 1);
  }
});

test('receipt-miss/state-advance race returns exact original receipt', async t => {
  const h = harness(t), request = input('race', 0, 'initialize'); let winner;
  h.afterReceiptMiss = async () => { winner = await h.act('race', request); };
  const result = await h.act('race', request);
  assert.deepEqual(plain(result), plain(winner)); assert.equal(h.receipts('race'), 1); assert.equal(h.seedCalls, 1);
});

test('stale state-read CAS cannot replace a competing commit or archive the wrong game', async t => {
  const h = harness(t); h.put('race', await engine.createInitialState(7));
  const before = h.privateState('race'); let winner;
  h.afterStateRead = async () => { winner = await h.act('race', input('winner', before.revision, 'endday')); };
  await reject(h.act('race', input('loser', before.revision, 'initialize', ['formal'])), 'revision_conflict');
  assert.equal(h.snapshot('race').revision, winner.revision); assert.equal(h.privateState('race').day, 2);
  assert.equal(h.receipts('race'), 1); assert.equal(h.archives('race').length, 0);
});

test('failure at every batch step rolls back fresh initialization, replacement archive, and ordinary action', async t => {
  const h = harness(t); await h.run('existing', 'initialize', ['formal']);
  for (const [command, args, steps] of [['initialize', [], 4], ['buy', ['salvage'], 3]]) {
    for (let position = 0; position < steps; position++) {
      const before = h.snapshot('existing'), receipts = h.receipts('existing'), archives = h.archives('existing');
      h.failAt = position;
      await assert.rejects(h.act('existing', input('rollback-' + command + position, before.revision, command, args)), /synthetic transaction failure/);
      h.failAt = -1;
      assert.deepEqual(h.snapshot('existing'), before); assert.equal(h.receipts('existing'), receipts); assert.deepEqual(h.archives('existing'), archives);
    }
  }
  for (let position = 0; position < 4; position++) {
    const user = 'fresh-' + position; h.failAt = position;
    await assert.rejects(h.act(user, input('init', 0, 'initialize')), /synthetic transaction failure/);
    h.failAt = -1; assert.equal(h.snapshot(user), undefined); assert.equal(h.receipts(user), 0); assert.equal(h.archives(user).length, 0);
  }
});

test('public state ETags bind owner, stream, revision, operation and build and skip JSON parse for 304', async t => {
  const h = harness(t); h.put('one', await engine.createInitialState(7)); h.put('two', await engine.createInitialState(7));
  const one = await h.api.gameState('one'), two = await h.api.gameState('two');
  assert.notEqual(one.etag, two.etag); assert.equal(one.body.build, h.api.VIEWER_BUILD); noHidden(one.body);
  const row = h.snapshot('one');
  assert.equal(one.etag, '"' + await hash.sha256(JSON.stringify([h.api.VIEWER_BUILD, 'one', row.game_id, row.revision, row.last_operation_id])) + '"');
  const old = one.etag;
  for (const [column, value] of [['game_id', 'different-stream'], ['last_operation_id', 'different-operation'], ['revision', 2]]) {
    const before = await h.api.gameState('one');
    h.raw.prepare(`UPDATE core_g1_state SET ${column}=? WHERE owner_user_id=?`).run(value, 'one');
    assert.notEqual((await h.api.gameState('one')).etag, before.etag);
  }
  const current = await h.api.gameState('one'); assert.notEqual(current.etag, old);
  h.raw.prepare('UPDATE core_g1_state SET public_json=? WHERE owner_user_id=?').run('invalid-json', 'one');
  assert.deepEqual(plain(await h.api.gameState('one', current.etag)), {etag: current.etag, unchanged: true});
  await assert.rejects(h.api.gameState('one'));
  assert.ok(h.reads.every(statement => !statement.includes('private_json')));
});

test('HTTP state requires identity before every 200/304 and exposes no private data or internal error', async t => {
  const h = harness(t); await h.run('http-owner', 'initialize');
  const request = headers => new Request('https://synthetic.invalid/api/game/state', {headers});
  const owner = {'oai-authenticated-user-id': 'http-owner'};
  const first = await h.route.GET(request(owner)); assert.equal(first.status, 200);
  const body = await first.json(); noHidden(body);
  assert.deepEqual(Object.keys(body).sort(), ['build', 'initialized', 'mode', 'observation', 'revision', 'stream_id', 'synthetic', 'updated_at']);
  assert.equal(first.headers.get('cache-control'), 'private, no-cache');
  const etag = first.headers.get('etag');
  const unchanged = await h.route.GET(request({...owner, 'if-none-match': etag}));
  assert.equal(unchanged.status, 304); assert.equal(await unchanged.text(), '');
  const anonymous = await h.route.GET(request({'if-none-match': etag, authorization: 'Bearer synthetic-not-a-credential'}));
  assert.equal(anonymous.status, 401); assert.deepEqual(await anonymous.json(), {error: 'sign_in_required'});
  const different = await h.route.GET(request({'oai-authenticated-user-id': 'other-owner', 'if-none-match': etag})); assert.equal(different.status, 200);
  h.raw.prepare('UPDATE core_g1_state SET public_json=? WHERE owner_user_id=?').run('PRIVATE_SENTINEL', 'http-owner');
  const failed = await h.route.GET(request(owner)); assert.equal(failed.status, 503);
  assert.equal(failed.headers.get('cache-control'), 'no-store'); assert.deepEqual(await failed.json(), {error: 'game_service_unavailable'});
});

test('projection discards extra private fields and hides unopened/undiscovered identities', async () => {
  const {pending} = await pendingFixture();
  for (const object of [pending, pending.visitors[0], pending.inventory[0], pending.last_event.item, pending.negotiation.context, pending.roll_history[0]]) object.secret_marker = 'PRIVATE_SENTINEL';
  const view = engine.observationV9(pending); noHidden(view); assert.ok(!JSON.stringify(view).includes('PRIVATE_SENTINEL'));
  for (const entry of view.codex.entries.filter(entry => !entry.discovered)) assert.equal(Object.keys(entry).sort().join(','), 'collected,discovered,slot');
  const fresh = engine.observationV9(await engine.createInitialState(5));
  assert.ok(fresh.codex.entries.every(entry => Object.keys(entry).sort().join(',') === 'collected,discovered,slot'));
});

test('owners are isolated and writes never touch retired mirror or lab tables', async t => {
  const h = harness(t); await h.run('one', 'initialize'); const before = h.snapshot('one');
  await h.run('two', 'initialize', ['formal']); await h.run('two', 'initialize');
  assert.deepEqual(h.snapshot('one'), before);
  for (const statement of h.writes) assert.match(statement, /(?:INTO|UPDATE) (?:core_g1_(?:state|receipts)|game_archives)/);
  for (const table of ['current_snapshot', 'stream_activations', 'lab_state', 'lab_receipts']) assert.equal(h.raw.prepare('SELECT count(*) AS n FROM ' + table).get().n, 0);
});
