import test from 'node:test';
import assert from 'node:assert/strict';
import {acceptSnapshot, createSpectatorSync, knownImagePath, MAX_RETRY_MS, resolveDetail, retryDelay, validateSnapshot} from '../lib/spectator-sync.mjs';

function snapshot(overrides = {}) {
  const revision = overrides.revision ?? 2;
  return {initialized: true, mode: 'test', stream_id: 'test-stream-a', revision, updated_at: '2026-10-07T00:00:00.000Z', build: 'current-build', observation: {
    version: 9, revision, day: 1, phase: 'active', credits: 100, reputation: 0, energy: 10, max_energy: 12, capacity: 7, operating_cost: 14,
    inventory: [], collection: [], crates: [], suppliers: [], visitors: [], log: [], roll_history: [], collection_sets: [], upgrade_details: [],
    codex: {entries: []}, campaign: {next_milestone: {goals: []}}, collection_progress: {categories: [], requirements: [], missing: []},
    walkins: {}, daily_event: {}, demand: {}, stats: {}, trade_rules: {},
  }, ...overrides};
}
const response = (value, etag = 'etag-1') => ({status: 200, ok: true, json: async () => value, headers: {get: key => key.toLowerCase() === 'etag' ? etag : null}});
const notModified = () => ({status: 304, ok: false});
const deferred = () => {let resolve; const promise = new Promise(r => {resolve = r;}); return {promise, resolve};};

test('only accepts the current initialized or empty state contract', () => {
  assert.equal(validateSnapshot(snapshot()), true);
  assert.equal(validateSnapshot(snapshot({initialized: false, observation: null, revision: 0, updated_at: null})), true);
  for (const invalid of [null, {}, snapshot({build: ''}), snapshot({mode: 'legacy'}), snapshot({stream_id: ''}), snapshot({revision: -1}), snapshot({updated_at: 'bad date'}), snapshot({observation: {version: 8, revision: 2}}), snapshot({observation: {...snapshot().observation, revision: 1}})]) assert.equal(validateSnapshot(invalid), false);
});

test('revision increases, new builds and new streams are accepted; older revisions and retired streams are rejected', () => {
  const previous = snapshot();
  assert.equal(acceptSnapshot(null, previous).reason, 'initial');
  assert.equal(acceptSnapshot(previous, snapshot({revision: 3})).reason, 'advanced');
  assert.equal(acceptSnapshot(previous, snapshot({build: 'next-build'})).reason, 'new_build');
  assert.equal(acceptSnapshot(previous, snapshot({revision: 1})).accepted, false);
  assert.equal(acceptSnapshot(previous, snapshot({stream_id: 'test-stream-b', revision: 0})).reason, 'new_stream');
  assert.equal(acceptSnapshot(previous, snapshot({stream_id: 'retired'}), new Set(['retired'])).reason, 'retired_stream');
});

test('ETag checks send credentials and 304 updates connection time without advancing game action time', async () => {
  let now = 1000; const calls = []; const replies = [response(snapshot()), notModified()];
  const sync = createSpectatorSync({now: () => now, fetcher: async (...args) => {calls.push(args); return replies.shift();}});
  await sync.request(); const old = sync.getSnapshot().snapshot; now = 9000; await sync.request();
  assert.equal(calls[0][0], '/api/game/state');
  assert.equal(calls[0][1].credentials, 'same-origin');
  assert.equal(calls[0][1].cache, 'no-store');
  assert.deepEqual(calls[0][1].headers, {});
  assert.deepEqual(calls[1][1].headers, {'If-None-Match': 'etag-1'});
  assert.equal(sync.getSnapshot().snapshot, old);
  assert.equal(sync.getSnapshot().checkedAt, now);
  assert.equal(sync.getSnapshot().snapshot.updated_at, '2026-10-07T00:00:00.000Z');
  sync.dispose();
});

test('304 with no prior state is recoverable and cannot invent a snapshot', async () => {
  const calls = []; const replies = [notModified(), response(snapshot())];
  const sync = createSpectatorSync({fetcher: async (_url, options) => {calls.push(options); return replies.shift();}});
  await sync.request(); assert.equal(sync.getSnapshot().snapshot, null); assert.equal(sync.getSnapshot().status, 'reconnecting');
  await sync.request(); assert.equal(sync.getSnapshot().status, 'connected'); assert.deepEqual(calls[1].headers, {}); sync.dispose();
});

test('network failure retains the picture, backs off within a bound, then reconnects and retries images', async () => {
  let call = 0; const sync = createSpectatorSync({fetcher: async () => {call++; if (call === 2 || call === 3) throw Error('offline'); return response(snapshot({revision: call === 1 ? 2 : 3}));}});
  await sync.request(); const old = sync.getSnapshot().snapshot, imageEpoch = sync.getSnapshot().imageEpoch;
  await sync.request(); assert.equal(sync.getSnapshot().snapshot, old); assert.equal(sync.getSnapshot().status, 'reconnecting'); assert.equal(sync.getSnapshot().failures, 1);
  await sync.request(); assert.equal(sync.getSnapshot().failures, 2);
  await sync.request(); assert.equal(sync.getSnapshot().status, 'connected'); assert.equal(sync.getSnapshot().failures, 0); assert.equal(sync.getSnapshot().snapshot.revision, 3); assert.equal(sync.getSnapshot().imageEpoch, imageEpoch + 1);
  assert.equal(retryDelay(0), 2000); assert.equal(retryDelay(2), 4000); assert.equal(retryDelay(500), MAX_RETRY_MS); sync.dispose();
});

test('synchronously thrown network errors also recover on the next request', async () => {
  let call = 0; const sync = createSpectatorSync({fetcher: () => {if (!call++) throw Error('network'); return Promise.resolve(response(snapshot()));}});
  await sync.request(); assert.equal(sync.getSnapshot().checking, false); await sync.request(); assert.equal(sync.getSnapshot().status, 'connected'); sync.dispose();
});

test('simultaneous refresh and focus share one flight, and disposal rejects delayed completion', async () => {
  const pending = deferred(); let calls = 0; const sync = createSpectatorSync({fetcher: () => {calls++; return pending.promise;}});
  const first = sync.request(), second = sync.request(); assert.equal(first, second);
  await Promise.resolve(); assert.equal(calls, 1); sync.dispose(); pending.resolve(response(snapshot())); await first;
  assert.equal(sync.getSnapshot().snapshot, null);
});

test('disposal during JSON parsing also prevents delayed data from becoming visible', async () => {
  const json = deferred(); const sync = createSpectatorSync({fetcher: async () => ({status: 200, ok: true, json: () => json.promise})});
  const pending = sync.request(); await new Promise(resolve => setImmediate(resolve)); sync.dispose(); json.resolve(snapshot()); await pending;
  assert.equal(sync.getSnapshot().snapshot, null);
});

test('older replies keep the accepted ETag, and a stream reset cannot later roll back to a retired stream', async () => {
  const replies = [response(snapshot({revision: 5}), 'newest-a'), response(snapshot({revision: 2}), 'stale-a'), response(snapshot({stream_id: 'test-stream-b', revision: 1}), 'newest-b'), response(snapshot({revision: 9}), 'retired-a'), notModified()];
  const headers = []; const sync = createSpectatorSync({fetcher: async (_url, options) => {headers.push(options.headers); return replies.shift();}});
  await sync.request(); await sync.request(); assert.equal(sync.getSnapshot().snapshot.revision, 5); assert.equal(sync.getSnapshot().notice, 'stale_response');
  await sync.request(); assert.deepEqual(headers[2], {'If-None-Match': 'newest-a'}); assert.equal(sync.getSnapshot().snapshot.stream_id, 'test-stream-b');
  await sync.request(); assert.equal(sync.getSnapshot().snapshot.stream_id, 'test-stream-b');
  await sync.request(); assert.deepEqual(headers[4], {'If-None-Match': 'newest-b'}); assert.equal(sync.getSnapshot().notice, null); sync.dispose();
});

test('new build at equal revision is accepted and changes art cache identity', async () => {
  const replies = [response(snapshot()), response(snapshot({build: 'next-build'}))]; const sync = createSpectatorSync({fetcher: async () => replies.shift()});
  await sync.request(); const first = knownImagePath({art_id: 'known-item'}, sync.getSnapshot().snapshot); await sync.request(); const second = knownImagePath({art_id: 'known-item'}, sync.getSnapshot().snapshot);
  assert.notEqual(first, second); assert.match(second, /v=next-build$/); sync.dispose();
});

test('401 is explicitly reported while retaining last readable state; a later authorized retry recovers', async () => {
  const replies = [response(snapshot()), {status: 401, ok: false}, response(snapshot({revision: 3}))]; const sync = createSpectatorSync({fetcher: async () => replies.shift()});
  await sync.request(); await sync.request(); assert.equal(sync.getSnapshot().status, 'unauthorized'); assert.equal(sync.getSnapshot().snapshot.revision, 2); assert.equal(sync.getSnapshot().checking, false);
  await sync.request(); assert.equal(sync.getSnapshot().status, 'connected'); assert.equal(sync.getSnapshot().snapshot.revision, 3); sync.dispose();
});

test('bad response data never replaces the last public state', async () => {
  const replies = [response(snapshot()), response({secret: 'not a public state'})]; const sync = createSpectatorSync({fetcher: async () => replies.shift()});
  await sync.request(); const old = sync.getSnapshot().snapshot; await sync.request(); assert.equal(sync.getSnapshot().snapshot, old); assert.equal(sync.getSnapshot().status, 'reconnecting'); sync.dispose();
});

test('unknown or unsafe artwork never gets a URL; known art is scoped to stream and build', () => {
  const current = snapshot({stream_id: 'stream/one', build: 'build one'});
  for (const item of [{discovered: false}, {discovered: false, art_id: 'hidden-item', name: 'hidden name'}, {}, {art_id: '../escape'}, {art_id: 'https://external/image'}, {art_id: ''}]) assert.equal(knownImagePath(item, current), null);
  assert.equal(knownImagePath({art_id: 'known_item'}, current), '/api/game/art/known_item?stream=stream%2Fone&v=build%20one');
  assert.equal(knownImagePath({art_id: 'known_item'}, null), null);
  assert.equal(knownImagePath({art_id: 'known_item'}, snapshot({initialized: false, observation: null})), null);
});

test('detail selection supports repeated opens, collection movement, sold-item invalidation and hidden codex entries', () => {
  const item = {id: 'item-1', name: 'Known item'}; const o = snapshot().observation;
  o.inventory = [item]; o.codex.entries = [{slot: 1, discovered: false, art_id: 'must-stay-hidden'}, {slot: 2, discovered: true, art_id: 'known', name: 'Known'}];
  const selection = {type: 'item', id: 'item-1'};
  for (let i = 0; i < 4; i++) {assert.equal(resolveDetail(o, selection).item, item); assert.equal(resolveDetail(o, null), null);}
  o.inventory = []; o.collection = [item]; assert.equal(resolveDetail(o, selection).item, item);
  o.collection = []; assert.equal(resolveDetail(o, selection), null);
  assert.equal(resolveDetail(o, {type: 'catalog', slot: 1}), null);
  assert.equal(resolveDetail(o, {type: 'catalog', slot: 2}).entry.name, 'Known');
  assert.equal(resolveDetail(null, selection), null);
});
