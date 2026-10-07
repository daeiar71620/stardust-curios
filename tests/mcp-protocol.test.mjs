import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';
import ts from 'typescript';

// Run: node --test tests/mcp-protocol.test.mjs
// Only route code, real input validators, and the real identity gate are loaded.
// Storage, game execution, hashing, and network access are unavailable in the VM.
// Protocol references: https://modelcontextprotocol.io/specification/2026-07-28/
// server/discover, basic/index, basic/transports/streamable-http, and
// server/utilities/caching. The discovery request below is synthetic: its modern
// headers match the observed registration shape, but no production body was saved.
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const routeFile = 'app/mcp/route.ts';
const routeSource = fs.readFileSync(path.join(root, routeFile), 'utf8');
const version = '2026-07-28';
const prefix = 'io.modelcontextprotocol/';
const owner = {'oai-authenticated-user-id': 'synthetic-test-owner'};
const toolNames = ['stardust_game_state', 'stardust_game_query', 'stardust_game_action'];
const actionArgs = {initialize: [], buy: ['salvage'], open: ['C001'], price: ['I001', '123'],
  repair: ['I001'], collect: ['I001'], 'replace-collection': ['I001'], upgrade: ['shelf'],
  sell: ['I001'], accept: ['I001'], decline: ['I001'], offer: ['I001', '123'], endday: [], continue: []};
const queryArgs = {status: [], market: [], codex: [], visitors: [], inspect: ['I001'], 'preview-offer': ['I001', '123']};
const publicResult = {synthetic: true, revision: 7, result: {public: 'synthetic projection'}};
const compiled = new Map();
const encodeName = name => `=?base64?${Buffer.from(name, 'utf8').toString('base64')}?=`;
const metadata = () => ({[prefix + 'protocolVersion']: version,
  [prefix + 'clientCapabilities']: {}, [prefix + 'clientInfo']: {name: 'SyntheticProtocolTest', version: '1.0.0'}});

function loadModule(file, imports, source = fs.readFileSync(path.join(root, file), 'utf8')) {
  if (!compiled.has(source)) compiled.set(source, ts.transpileModule(source, {
    compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022},
    fileName: file,
  }).outputText);
  const context = {exports: {}, Request, Response, URL, JSON, TextEncoder, TextDecoder, Uint8Array, atob,
    require(specifier) {
      assert.ok(Object.hasOwn(imports, specifier), `Unexpected import ${specifier}`);
      return imports[specifier];
    }};
  vm.runInNewContext(compiled.get(source), context, {filename: file});
  return context.exports;
}

function harness(t, source = routeSource) {
  const calls = [], identities = [], forbiddenCalls = [];
  const forbidden = () => { forbiddenCalls.push('state access'); throw new Error('Forbidden synthetic test access'); };
  const auth = loadModule('lib/site-auth.ts', {});
  const commands = loadModule('lib/game-engine/native-commands.ts', {});
  const core = loadModule('lib/game-authority.ts', {'@/db': {getDatabase: forbidden},
    './hash': {sha256: forbidden}, './site-auth': auth,
    './server-art-manifest': {ART_VERSION: 'synthetic-art-version'},
    './game-engine/index': {...commands, createInitialState: forbidden, executeNative: forbidden,
      validateNativeState: forbidden, observationV9: forbidden}, './game-sql.mjs': {}});
  const state = {calls, identities, SiteError: auth.SiteError, failWith: undefined};
  const dispatch = handler => async (user, input) => {
    calls.push({handler, user, input});
    if (state.failWith) throw state.failWith;
    return publicResult;
  };
  state.route = loadModule(routeFile, {
    '@/lib/site-auth': {...auth,
      requireSiteUser(request) { identities.push(request.headers.get('oai-authenticated-user-id')); return auth.requireSiteUser(request); }},
    '@/lib/game-authority': {...core, gameToolState: dispatch('state'),
      gameAction: dispatch('action'), gameQuery: dispatch('query')},
  }, source);
  t.after(() => assert.deepEqual(forbiddenCalls, [], 'No database, hashing, projection, or game access'));
  return state;
}

function request(body, overrides = {}, raw) {
  const headers = new Headers({'content-type': 'application/json', ...overrides});
  for (const [name, value] of Object.entries(overrides)) if (value === null) headers.delete(name);
  return new Request('https://synthetic-protocol.invalid/mcp', {
    method: 'POST', headers, body: raw === undefined ? JSON.stringify(body) : raw,
  });
}
function modern(method, params = {}, headers = {}, body = {}) {
  return request({jsonrpc: '2.0', id: 'request-1', method, params: {_meta: metadata(), ...params}, ...body}, {
    'mcp-protocol-version': version, 'mcp-method': method,
    ...(method === 'tools/call' && typeof params.name === 'string' ? {'mcp-name': encodeName(params.name)} : {}),
    ...headers,
  });
}
function legacy(method, params = {}, headers = {}, body = {}) {
  return request({jsonrpc: '2.0', id: 'request-1', method, params, ...body}, headers);
}
async function response(h, req) {
  const res = await h.route.POST(req);
  const body = res.status === 202 ? undefined : await res.json();
  if (res.status !== 202) assert.equal(res.headers.get('cache-control'), 'no-store');
  return {status: res.status, body, headers: res.headers};
}
function complete(result) {
  assert.equal(result.resultType, 'complete');
  assert.deepEqual(result._meta, {[prefix + 'serverInfo']: {name: 'Stardust Curios', version: '0.2.0'}});
}
async function protocolError(h, req, code, status = 400, id) {
  const expectedId = arguments.length >= 5 ? id : 'request-1';
  const before = h.calls.length;
  const result = await response(h, req);
  assert.equal(result.status, status);
  assert.equal(result.body.jsonrpc, '2.0');
  assert.equal(result.body.error.code, code);
  assert.equal(typeof result.body.error.message, 'string');
  assert.equal(result.body.result, undefined);
  assert.equal(result.body.id, expectedId);
  assert.equal(h.calls.length, before, 'Protocol failure must not dispatch');
  return result.body;
}

test('modern discovery works without initialization, identity, or any data access', async t => {
  const h = harness(t);
  const {status, body} = await response(h, modern('server/discover'));
  assert.equal(status, 200);
  assert.equal(body.id, 'request-1');
  complete(body.result);
  assert.deepEqual(Object.keys(body.result).sort(), ['_meta', 'cacheScope', 'capabilities', 'instructions', 'resultType', 'supportedVersions', 'ttlMs']);
  assert.deepEqual(body.result.supportedVersions, [version]);
  assert.deepEqual(body.result.capabilities, {tools: {}});
  assert.match(body.result.instructions, /initialize.*新开.*备份/);
  assert.equal(body.result.ttlMs, 0);
  assert.equal(body.result.cacheScope, 'private');
  assert.deepEqual(h.calls, []);
  assert.deepEqual(h.identities, []);
});

test('retired core and lab tools are absent and cannot dispatch in either transport', async t => {
  const h = harness(t);
  const retired = ['stardust_core_test_state', 'stardust_core_test_query', 'stardust_core_test_action',
    'stardust_lab_get_state', 'stardust_lab_open_box'];
  for (const name of retired) {
    await protocolError(h, modern('tools/call', {name, arguments: {}}, owner), -32602);
    const {body} = await response(h, legacy('tools/call', {name, arguments: {}}, owner));
    assert.equal(body.result.isError, true);
    assert.deepEqual(JSON.parse(body.result.content[0].text), {ok: false, error: 'unknown_test_tool'});
  }
  assert.deepEqual(h.calls, []);
});

test('modern and legacy lists expose exactly three latest tools and complete command coverage', async t => {
  const h = harness(t);
  const modernList = await response(h, modern('tools/list'));
  const legacyList = await response(h, legacy('tools/list'));
  assert.equal(modernList.status, 200);
  complete(modernList.body.result);
  assert.equal(modernList.body.result.ttlMs, 0);
  assert.equal(modernList.body.result.cacheScope, 'private');
  assert.equal(modernList.body.result.nextCursor, undefined);
  assert.deepEqual(modernList.body.result.tools, legacyList.body.result.tools);
  const tools = modernList.body.result.tools;
  assert.deepEqual(tools.map(tool => tool.name), toolNames);
  assert.deepEqual(tools[1].inputSchema.properties.command.enum, Object.keys(queryArgs));
  assert.deepEqual(tools[2].inputSchema.properties.command.enum, Object.keys(actionArgs));
  for (const tool of tools) {
    assert.equal(tool.inputSchema.additionalProperties, false);
    assert.equal(tool.annotations.destructiveHint, false);
    assert.equal(tool.annotations.openWorldHint, false);
  }
  for (const index of [0, 1]) assert.equal(tools[index].annotations.readOnlyHint, true);
  for (const index of [2]) assert.equal(tools[index].annotations.idempotentHint, true);
  assert.deepEqual(h.calls, []);
  assert.deepEqual(h.identities, []);
});

test('all 14 actions and 6 queries pass real validators and dispatch only to their mocked authority', async t => {
  const h = harness(t);
  for (const [kind, commands] of [['action', actionArgs], ['query', queryArgs]]) {
    for (const [command, args] of Object.entries(commands)) {
      const input = {...(kind === 'action' ? {operation_id: `test-${command}`, expected_revision: 0} : {}), command, args};
      const name = `stardust_game_${kind}`;
      const {status, body} = await response(h, modern('tools/call', {name, arguments: input}, {...owner, 'mcp-name': name}));
      assert.equal(status, 200, command);
      assert.equal(body.result.isError, false, command);
      complete(body.result);
      assert.deepEqual(body.result.structuredContent, publicResult);
      assert.deepEqual(JSON.parse(body.result.content[0].text), publicResult);
      assert.deepEqual(h.calls.at(-1), {handler: kind, user: owner['oai-authenticated-user-id'], input});
    }
  }
  assert.equal(h.calls.length, 20);
});

test('state and explicit test/formal new games dispatch with bounded public results', async t => {
  const h = harness(t);
  const cases = [['stardust_game_state', {}, 'state'],
    ...['test', 'formal'].map(mode => ['stardust_game_action',
      {operation_id: 'new-' + mode, expected_revision: 17, command: 'initialize', args: [mode]}, 'action'])];
  for (const [name, args, handler] of cases) {
    const {status, body} = await response(h, modern('tools/call', {name, arguments: args}, owner));
    assert.equal(status, 200);
    complete(body.result);
    assert.deepEqual(body.result.structuredContent, publicResult);
    assert.deepEqual(JSON.parse(body.result.content[0].text), publicResult);
    assert.equal(body.result.isError, false);
    assert.equal(h.calls.at(-1).handler, handler);
  }
});

test('per-request metadata is required and validates version, capabilities, and optional clientInfo', async t => {
  const h = harness(t);
  const invalid = [undefined, null, [], {}, 'metadata', 1,
    {...metadata(), [prefix + 'protocolVersion']: undefined}, {...metadata(), [prefix + 'protocolVersion']: 1},
    {...metadata(), [prefix + 'clientCapabilities']: undefined},
    ...[null, [], '', 1, false].map(value => ({...metadata(), [prefix + 'clientCapabilities']: value})),
    ...[null, [], 'client', {}, {name: 'test'}, {version: '1'}, {name: 1, version: '1'}, {name: 'test', version: 1}]
      .map(value => ({...metadata(), [prefix + 'clientInfo']: value})),
  ];
  for (const meta of invalid) await protocolError(h, modern('server/discover', {_meta: meta}), -32602);
  for (const params of [null, [], false, 'params']) await protocolError(h, modern('server/discover', {}, {}, {params}), -32602);
  const noClientInfo = metadata();
  delete noClientInfo[prefix + 'clientInfo'];
  assert.equal((await response(h, modern('server/discover', {_meta: noClientInfo}))).status, 200);
  // Successful discovery never grants metadata to the next request.
  await protocolError(h, modern('tools/list', {_meta: {}}), -32602);
  await protocolError(h, modern('server/discover', {unexpected: true}), -32602);
  await protocolError(h, modern('tools/list', {cursor: 'unknown'}), -32602);
  assert.deepEqual(h.identities, []);
});

test('required mirrored version, method, and tool-name headers reject mismatch before authentication', async t => {
  const h = harness(t);
  for (const headers of [
    {'mcp-protocol-version': null}, {'mcp-protocol-version': '2025-06-18'}, {'mcp-protocol-version': '2026-07-29'},
    {'mcp-method': null}, {'mcp-method': 'tools/list'}, {'mcp-method': 'SERVER/DISCOVER'},
  ]) await protocolError(h, modern('server/discover', {}, headers), -32020);
  const name = 'stardust_game_state';
  for (const value of [null, 'stardust_lab_get_state', name.toUpperCase(), encodeName('different')]) {
    await protocolError(h, modern('tools/call', {name, arguments: {}}, {'mcp-name': value}), -32020);
  }
  for (const name of [undefined, null, 1, {}]) await protocolError(h, modern('tools/call', {name, arguments: {}}, {'mcp-name': 'ignored'}), -32602);
  assert.deepEqual(h.identities, []);
});

test('matching unsupported versions return the modern negotiation error, never a silent fallback', async t => {
  const h = harness(t);
  for (const requested of ['2026-07-29', '2099-01-01', '2025-06-18']) {
    const body = await protocolError(h, modern('server/discover', {
      _meta: {...metadata(), [prefix + 'protocolVersion']: requested},
    }, {'mcp-protocol-version': requested}), -32022);
    assert.deepEqual(body.error.data, {supported: [version], requested});
  }
});

test('name headers decode Base64 UTF-8 exactly and reject malformed encoding', async t => {
  const h = harness(t);
  const known = 'stardust_game_state';
  assert.equal((await response(h, modern('tools/call', {name: known, arguments: {}}, owner))).status, 200);
  // These names are intentionally unknown; -32602 proves header decoding matched
  // the body and reached tool lookup, rather than failing with -32020.
  for (const name of ['星屑测试🧪', ' padded ', 'line1\nline2', '=?base64?literal?=']) {
    await protocolError(h, modern('tools/call', {name, arguments: {}}, owner), -32602);
  }
  for (const nameHeader of ['=?base64?!!!!?=', '=?base64?Zg=?=', '=?base64?Z===?=',
    '=?base64?Zm9v-===?=', '=?base64?/w==?=', '=?base64?wK8=?=',
    '=?base64? Zg==?=', '=?BASE64?' + Buffer.from(known).toString('base64') + '?=',
    'stardust_\u007fcore', 'stardust_é']) {
    await protocolError(h, modern('tools/call', {name: known, arguments: {}}, {...owner, 'mcp-name': nameHeader}), -32020);
  }
  assert.equal(h.calls.length, 1);
});

test('modern request IDs, malformed envelopes, and invalid JSON fail without dispatch', async t => {
  const h = harness(t);
  for (const id of [undefined, null, true, false, {}, [], 1.5, Number.MAX_SAFE_INTEGER + 1]) {
    const body = await protocolError(h, modern('tools/list', {}, {}, {id}), -32600, 400, undefined);
    assert.equal(Object.hasOwn(body, 'id'), false);
  }
  for (const id of [0, -1, Number.MAX_SAFE_INTEGER, '', 'request-string']) {
    const res = await response(h, modern('ping', {}, {}, {id}));
    assert.equal(res.status, 200);
    assert.equal(res.body.id, id);
    complete(res.body.result);
  }
  const headers = {'mcp-protocol-version': version, 'mcp-method': 'tools/list'};
  for (const raw of ['{', '', '{"jsonrpc":']) {
    await protocolError(h, request({}, headers, raw), -32700, 400, undefined);
  }
  for (const body of [null, [], [{jsonrpc: '2.0', id: 1, method: 'ping'}], false,
    {jsonrpc: '1.0', id: 1, method: 'ping'}, {jsonrpc: '2.0', id: 1}, {jsonrpc: '2.0', id: 1, method: 9}]) {
    await protocolError(h, request(body, headers), -32600, 400, undefined);
  }
  assert.deepEqual(h.identities, []);
});

test('Base64 UTF-8 decoding preserves a leading BOM during exact header comparisons', async t => {
  const h = harness(t);
  const name = 'stardust_game_state';
  await protocolError(h, modern('tools/call', {name, arguments: {}}, {
    ...owner, 'mcp-name': encodeName('\uFEFF' + name),
  }), -32020);
  await protocolError(h, modern('tools/call', {name: '\uFEFF' + name, arguments: {}}, owner), -32602);
  assert.deepEqual(h.calls, []);
});

test('unknown modern methods and tool names use protocol errors', async t => {
  const h = harness(t);
  for (const method of ['unknown/method', 'initialize', 'resources/list']) {
    await protocolError(h, modern(method), -32601, 404);
  }
  await protocolError(h, modern('tools/call', {name: 'not_a_tool', arguments: {}}, owner), -32602);
});

test('invalid tool arguments are modern protocol errors and never reach a handler', async t => {
  const h = harness(t);
  const action = {operation_id: 'test-operation', expected_revision: 0, command: 'initialize', args: []};
  const invalidActions = [undefined, null, [], {}, {...action, extra: true}, {...action, command: 'import'},
    {...action, operation_id: ''}, {...action, operation_id: 'a'.repeat(81)}, {...action, operation_id: '../unsafe'},
    ...[-1, 1.5, 1000000000001, '0'].map(expected_revision => ({...action, expected_revision})),
    {...action, args: ['extra']}, {...action, command: 'buy', args: [9]}, {...action, command: 'buy', args: ['x'.repeat(81)]}];
  for (const args of invalidActions) await protocolError(h, modern('tools/call', {name: 'stardust_game_action', arguments: args}, owner), -32602);
  for (const args of [undefined, null, [], {}, {command: 'import', args: []}, {command: 'status', args: [], extra: true},
    {command: 'inspect', args: []}, {command: 'inspect', args: [1]}, {command: 'inspect', args: ['x'.repeat(81)]}]) {
    await protocolError(h, modern('tools/call', {name: 'stardust_game_query', arguments: args}, owner), -32602);
  }
  for (const name of ['stardust_game_state']) {
    for (const args of [null, [], 'state', false, {private: true}]) await protocolError(h, modern('tools/call', {name, arguments: args}, owner), -32602);
    assert.equal((await response(h, modern('tools/call', {name}, owner))).status, 200);
  }

});

test('every data tool retains the real identity gate; bearer and body clientInfo cannot substitute', async t => {
  const h = harness(t);
  for (const name of toolNames) for (const headers of [{}, {authorization: 'Bearer synthetic-not-a-credential'}]) {
    const {status, body} = await response(h, modern('tools/call', {name, arguments: {},
      _meta: {...metadata(), [prefix + 'clientInfo']: {name: owner['oai-authenticated-user-id'], version: '1', user: owner['oai-authenticated-user-id']}},
      user: owner['oai-authenticated-user-id'], 'oai-authenticated-user-id': owner['oai-authenticated-user-id'],
    }, headers));
    assert.equal(status, 401);
    assert.deepEqual(body, {error: 'sign_in_required'});
  }
  assert.equal(h.calls.length, 0);
  assert.equal(h.identities.length, 6);
  const name = 'stardust_game_state';
  await response(h, modern('tools/call', {name}, owner));
  await response(h, modern('tools/call', {name}, {'oai-authenticated-user-id': 'different-synthetic-owner'}));
  assert.deepEqual(h.calls.map(call => call.user), ['synthetic-test-owner', 'different-synthetic-owner']);
});

test('business failures remain isError results; unexpected errors expose no internal details', async t => {
  const h = harness(t);
  const req = () => modern('tools/call', {name: 'stardust_game_query', arguments: {command: 'status', args: []}}, owner);
  for (const [error, expected] of [
    [new h.SiteError('revision_conflict', 409), 'revision_conflict'],
    [new h.SiteError('initialize_game_first', 422), 'initialize_game_first'],
    [new Error('PRIVATE_SENTINEL private_json rng catalog secret'), 'test_service_unavailable'],
  ]) {
    h.failWith = error;
    const {status, body} = await response(h, req());
    assert.equal(status, 200);
    complete(body.result);
    assert.equal(body.result.isError, true);
    assert.equal(body.result.structuredContent, undefined);
    assert.deepEqual(JSON.parse(body.result.content[0].text), {ok: false, error: expected});
    assert.doesNotMatch(JSON.stringify(body), /PRIVATE_SENTINEL|private_json|catalog|stack|secret/);
  }
});

test('origin, content type, and 16 KiB byte bounds reject before identity or state access', async t => {
  const h = harness(t);
  const params = {name: 'stardust_game_state', arguments: {}};
  for (const [headers, status, error] of [
    [{origin: 'https://untrusted.invalid'}, 403, 'cross_origin_forbidden'],
    [{'content-type': 'text/plain'}, 415, 'json_required'],
    [{'content-type': null}, 415, 'json_required'],
    [{'content-length': '16385'}, 413, 'request_too_large'],
  ]) {
    const res = await response(h, modern('tools/call', params, {...owner, ...headers}));
    assert.equal(res.status, status);
    assert.deepEqual(res.body, {error});
  }
  for (const raw of [' '.repeat(16385), JSON.stringify({padding: '星'.repeat(6000)})]) {
    const res = await response(h, request({}, {'content-length': '1', ...owner}, raw));
    assert.equal(res.status, 413);
    assert.deepEqual(res.body, {error: 'request_too_large'});
  }
  const allowed = await response(h, modern('server/discover', {}, {origin: 'https://synthetic-protocol.invalid', 'content-type': 'Application/JSON; charset=utf-8'}));
  assert.equal(allowed.status, 200);
  const boundary = JSON.stringify({jsonrpc: '2.0', id: 'boundary', method: 'server/discover', params: {_meta: metadata()}});
  const atLimit = await response(h, request({}, {'mcp-protocol-version': version, 'mcp-method': 'server/discover'},
    boundary + ' '.repeat(16384 - Buffer.byteLength(boundary))));
  assert.equal(atLimit.status, 200);
  assert.deepEqual(h.calls, []);
  assert.deepEqual(h.identities, []);
  const get = h.route.GET();
  assert.equal(get.status, 405);
  assert.equal(get.headers.get('allow'), 'POST');
});

test('legacy initialize, notification, list, ping, tools, and error shapes stay compatible', async t => {
  const h = harness(t);
  for (const protocolVersion of ['2025-06-18', '2025-03-26', '2024-11-05', 'unsupported']) {
    const {status, body} = await response(h, legacy('initialize', {protocolVersion}));
    assert.equal(status, 200);
    assert.equal(body.result.protocolVersion, protocolVersion === 'unsupported' ? '2025-03-26' : protocolVersion);
    assert.deepEqual(body.result.capabilities, {tools: {listChanged: false}});
    assert.deepEqual(body.result.serverInfo, {name: 'Stardust Curios', version: '0.2.0'});
    assert.equal(body.result.resultType, undefined);
    assert.equal(body.result._meta, undefined);
  }
  assert.equal((await response(h, legacy('notifications/initialized', {}, {}, {id: undefined}))).status, 202);
  assert.deepEqual((await response(h, legacy('ping'))).body.result, {});
  for (const protocol of [undefined, '2025-06-18', '2025-03-26', '2024-11-05']) {
    const headers = protocol ? {'mcp-protocol-version': protocol} : {};
    const {body} = await response(h, legacy('tools/list', {}, headers));
    assert.deepEqual(Object.keys(body.result), ['tools']);
    const called = await response(h, legacy('tools/call', {name: 'stardust_game_query', arguments: {command: 'status', args: []}}, {...headers, ...owner}));
    assert.equal(called.status, 200);
    assert.deepEqual(called.body.result, {content: [{type: 'text', text: JSON.stringify(publicResult)}], structuredContent: publicResult, isError: false});
  }
  for (const [name, args, expected] of [['not_a_tool', {}, 'unknown_test_tool'], ['stardust_game_query', {}, 'invalid_arguments']]) {
    const {body, status} = await response(h, legacy('tools/call', {name, arguments: args}, owner));
    assert.equal(status, 200);
    assert.deepEqual(body.result, {content: [{type: 'text', text: JSON.stringify({ok: false, error: expected})}], isError: true});
  }
  const unauthenticated = await response(h, legacy('tools/call', {name: 'stardust_game_state'}));
  assert.equal(unauthenticated.status, 401);
  for (const id of [undefined, null, {}, [], true]) await protocolError(h, legacy('tools/call', {name: 'stardust_game_state'}, owner, {id}), -32600, 400, null);
  await protocolError(h, legacy('not_a_method'), -32601, 404);
});
