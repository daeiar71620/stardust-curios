import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';
import ts from 'typescript';
import * as manifest from '../lib/server-art-manifest.ts';
import * as hash from '../lib/hash.ts';

// Only public-safe generated artwork and synthetic identity/state/cache fixtures.
// Storage and live game state are unavailable to the test VM.
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const compiled = new Map();
function load(file, imports = {}) {
  if (!compiled.has(file)) compiled.set(file, ts.transpileModule(fs.readFileSync(path.join(root, file), 'utf8'), {
    compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022}, fileName: file,
  }).outputText);
  const context = {exports: {}, Request, Response, URL, Uint8Array, atob, require(specifier) {
    assert.ok(Object.hasOwn(imports, specifier), 'Unexpected import: ' + specifier);
    const imported = imports[specifier];
    return typeof imported === 'function' ? imported() : imported;
  }};
  vm.runInNewContext(compiled.get(file), context, {filename: file});
  return context.exports;
}
const auth = load('lib/site-auth.ts');
const firstId = Object.keys(manifest.PRIVATE_ART_METADATA)[0];
let generated;
function packaged() { return generated ??= load('lib/server-art-data.ts'); }
function packagedBytes(id = firstId) { return Uint8Array.from(atob(packaged().PRIVATE_ART[id].base64), char => char.charCodeAt(0)); }
function harness(options = {}) {
  const h = {calls: [], stateReads: 0, gets: 0, puts: 0, privateLoads: 0, options};
  const observation = {codex: {entries: [{slot: 1, discovered: true, art_id: firstId}, {slot: 2, discovered: false}]}};
  const body = {initialized: true, stream_id: 'synthetic-stream', observation};
  h.body = body;
  h.api = load('lib/game-art.ts', {
    '@/db': {getBucket() {
      h.calls.push('bucket');
      if (options.bucketError) throw Error('PRIVATE_BUCKET_ERROR');
      return {async get(key) {
        h.calls.push('get'); h.gets++; h.key = key;
        if (options.getError) throw Error('PRIVATE_CACHE_ERROR');
        return options.cachedBytes ? {arrayBuffer: async () => Uint8Array.from(options.cachedBytes).buffer} : null;
      }, async put(key, bytes, metadata) {
        h.calls.push('put'); h.puts++; h.put = {key, bytes: Uint8Array.from(bytes), metadata};
        if (options.putError) throw Error('PRIVATE_PUT_ERROR');
      }};
    }},
    './game-authority': {async gameState(user) {
      h.calls.push('state'); h.stateReads++; h.user = user;
      if (options.stateError) throw Error('PRIVATE_STATE_ERROR');
      return {unchanged: options.unchanged || false, body: options.body ?? (options.owner && options.owner !== user ? {...body, initialized: false} : body)};
    }},
    './site-auth': auth, './hash': hash, './server-art-manifest': manifest,
    './server-art-data': () => { h.calls.push('private-assets'); h.privateLoads++; return packaged(); },
  });
  h.route = load('app/api/game/art/[id]/route.ts', {'@/lib/game-art': h.api, '@/lib/site-auth': auth});
  return h;
}
async function notFound(h, id, stream = 'synthetic-stream') {
  await assert.rejects(h.api.discoveredArtwork('synthetic-owner', id, stream), error => error.code === 'art_not_found' && error.status === 404);
  assert.equal(h.gets, 0); assert.equal(h.puts, 0); assert.equal(h.privateLoads, 0);
  assert.ok(h.calls.every(call => call === 'state'), 'Unknown art must not touch the bucket or asset module');
}

test('invalid, sealed, unknown, and wrong-stream artwork fails before private asset imports or cache lookup', async () => {
  for (const id of ['', '../' + firstId, 'A', 'x'.repeat(49), 'not-in-codex', '__proto__']) await notFound(harness(), id);
  const sealed = harness(); sealed.body.observation.codex.entries[0].discovered = false; await notFound(sealed, firstId);
  const wrong = harness(); await notFound(wrong, firstId, 'previous-synthetic-stream');
  for (const body of [{initialized: false}, {initialized: true, stream_id: 'synthetic-stream', observation: null},
    {initialized: true, stream_id: 'synthetic-stream', observation: {codex: {entries: []}}}]) await notFound(harness({body}), firstId);
  await notFound(harness({unchanged: true}), firstId);
  const absent = harness(); absent.body.observation.codex.entries.push({discovered: true, art_id: 'not-in-manifest'});
  await notFound(absent, 'not-in-manifest');
});

test('a discovered cache miss returns validated packaged PNG and writes only versioned private cache', async () => {
  const h = harness(), result = await h.api.discoveredArtwork('synthetic-owner', firstId, 'synthetic-stream');
  assert.equal(result.digest, manifest.PRIVATE_ART_METADATA[firstId].sha256);
  assert.equal(await hash.sha256Bytes(result.bytes), result.digest);
  assert.deepEqual([...result.bytes.slice(0, 8)], [137, 80, 78, 71, 13, 10, 26, 10]);
  assert.equal(h.key, 'illustrations/' + manifest.ART_VERSION + '/' + firstId + '.png');
  assert.equal(h.put.key, h.key); assert.deepEqual(h.put.bytes, result.bytes);
  assert.equal(h.put.metadata.httpMetadata.contentType, 'image/png');
  assert.equal(h.privateLoads, 1); assert.equal(h.gets, 1); assert.equal(h.puts, 1);
  assert.deepEqual(h.calls, ['state', 'bucket', 'get', 'private-assets', 'bucket', 'put']);
});

test('a valid cached PNG returns after owner discovery check without loading private asset data', async () => {
  const h = harness({cachedBytes: packagedBytes()});
  const result = await h.api.discoveredArtwork('synthetic-owner', firstId, 'synthetic-stream');
  assert.deepEqual(result.bytes, packagedBytes()); assert.equal(h.stateReads, 1); assert.equal(h.gets, 1);
  assert.equal(h.privateLoads, 0); assert.equal(h.puts, 0); assert.deepEqual(h.calls, ['state', 'bucket', 'get']);
});

test('cache corruption and R2 get/put/binding failures fall back to the packaged PNG', async () => {
  for (const options of [{cachedBytes: [0, 1, 2, 3]}, {getError: true}, {putError: true}, {getError: true, putError: true}, {bucketError: true}]) {
    const h = harness(options), result = await h.api.discoveredArtwork('synthetic-owner', firstId, 'synthetic-stream');
    assert.equal(await hash.sha256Bytes(result.bytes), manifest.PRIVATE_ART_METADATA[firstId].sha256);
    assert.deepEqual(result.bytes, packagedBytes()); assert.equal(h.privateLoads, 1);
  }
});

test('every generated private artwork matches its manifest hash, byte length, and PNG signature', async () => {
  assert.deepEqual(Object.keys(packaged().PRIVATE_ART).sort(), Object.keys(manifest.PRIVATE_ART_METADATA).sort());
  for (const [id, entry] of Object.entries(manifest.PRIVATE_ART_METADATA)) {
    const bytes = packagedBytes(id);
    assert.equal(bytes.length, entry.bytes, id); assert.equal(await hash.sha256Bytes(bytes), entry.sha256, id);
    assert.deepEqual([...bytes.slice(0, 8)], [137, 80, 78, 71, 13, 10, 26, 10], id);
  }
});

test('art HTTP route authenticates before 200 or 304 and applies private-cache and nosniff headers', async () => {
  const h = harness({cachedBytes: packagedBytes(), owner: 'synthetic-owner'});
  const url = 'https://synthetic.invalid/api/game/art/' + firstId + '?stream=synthetic-stream';
  const call = headers => h.route.GET(new Request(url, {headers}), {params: Promise.resolve({id: firstId})});
  const owner = {'oai-authenticated-user-id': 'synthetic-owner'};
  const first = await call(owner); assert.equal(first.status, 200);
  assert.deepEqual(new Uint8Array(await first.arrayBuffer()), packagedBytes());
  assert.equal(first.headers.get('content-type'), 'image/png'); assert.equal(first.headers.get('x-content-type-options'), 'nosniff');
  assert.equal(first.headers.get('cache-control'), 'private, no-cache');
  const etag = first.headers.get('etag'), readsBefore = h.stateReads;
  const unchanged = await call({...owner, 'if-none-match': etag}); assert.equal(unchanged.status, 304);
  assert.equal(await unchanged.text(), ''); assert.equal(h.stateReads, readsBefore + 1);
  const anonymous = await call({'if-none-match': etag, authorization: 'Bearer synthetic-not-a-credential'});
  assert.equal(anonymous.status, 401); assert.deepEqual(await anonymous.json(), {error: 'sign_in_required'});
  assert.equal(h.stateReads, readsBefore + 1, 'Authentication must happen before state/cache access');
  const getsBefore = h.gets;
  const other = await call({'oai-authenticated-user-id': 'other-owner', 'if-none-match': etag});
  assert.equal(other.status, 404); assert.equal(h.gets, getsBefore);
});

test('art HTTP cannot reuse a known ETag after discovery disappears or the stream changes', async () => {
  const h = harness({cachedBytes: packagedBytes()}), etag = '"' + manifest.PRIVATE_ART_METADATA[firstId].sha256 + '"';
  const headers = {'oai-authenticated-user-id': 'synthetic-owner', 'if-none-match': etag};
  const call = stream => h.route.GET(new Request('https://synthetic.invalid/api/game/art/' + firstId + '?stream=' + stream, {headers}), {params: Promise.resolve({id: firstId})});
  assert.equal((await call('old-stream')).status, 404);
  h.body.observation.codex.entries[0].discovered = false;
  assert.equal((await call('synthetic-stream')).status, 404);
  assert.equal(h.gets, 0); assert.equal(h.puts, 0); assert.equal(h.privateLoads, 0);
});

test('art HTTP unexpected errors reveal no internal state and are never cached', async () => {
  const h = harness({stateError: true});
  const response = await h.route.GET(new Request('https://synthetic.invalid/api/game/art/' + firstId, {
    headers: {'oai-authenticated-user-id': 'synthetic-owner'},
  }), {params: Promise.resolve({id: firstId})});
  assert.equal(response.status, 503); assert.deepEqual(await response.json(), {error: 'art_unavailable'});
  assert.equal(response.headers.get('cache-control'), 'no-store'); assert.equal(h.gets, 0); assert.equal(h.privateLoads, 0);
});

function projectFiles(directory) {
  return fs.existsSync(directory) ? fs.readdirSync(directory, {withFileTypes: true}).flatMap(entry =>
    entry.isDirectory() ? projectFiles(path.join(directory, entry.name)) : /\.[cm]?[jt]sx?$/.test(entry.name) ? [path.join(directory, entry.name)] : []) : [];
}
function resolveLocal(from, specifier) {
  const base = specifier.startsWith('@/') ? path.join(root, specifier.slice(2)) : specifier.startsWith('.') ? path.resolve(path.dirname(from), specifier) : null;
  if (!base) return null;
  return [base, ...['.ts', '.tsx', '.js', '.mjs', '/index.ts', '/index.tsx'].map(extension => base + extension)]
    .find(candidate => fs.existsSync(candidate) && fs.statSync(candidate).isFile()) ?? null;
}
function runtimeImports(file) {
  const source = ts.createSourceFile(file, fs.readFileSync(file, 'utf8'), ts.ScriptTarget.Latest, true);
  const imports = [];
  function visit(node) {
    if ((ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) && node.moduleSpecifier && ts.isStringLiteral(node.moduleSpecifier)) {
      if (node.isTypeOnly || node.importClause?.isTypeOnly) return;
      const bindings = node.importClause?.namedBindings;
      if (bindings && ts.isNamedImports(bindings) && bindings.elements.length > 0 && bindings.elements.every(element => element.isTypeOnly) && !node.importClause?.name) return;
      imports.push(node.moduleSpecifier.text);
    }
    if (ts.isCallExpression(node) && (node.expression.kind === ts.SyntaxKind.ImportKeyword || (ts.isIdentifier(node.expression) && node.expression.text === 'require')) && node.arguments.length === 1 && ts.isStringLiteral(node.arguments[0])) imports.push(node.arguments[0].text);
    ts.forEachChild(node, visit);
  }
  visit(source);
  return imports.map(specifier => resolveLocal(file, specifier)).filter(Boolean);
}
test('no client module transitively imports the engine, private artwork, authority, or full catalog', () => {
  const files = ['app', 'components', 'lib'].flatMap(directory => projectFiles(path.join(root, directory)));
  const clients = files.filter(file => /^\s*['"]use client['"];?/m.test(fs.readFileSync(file, 'utf8')));
  assert.ok(clients.length > 0, 'At least one client entry point is inspected');
  for (const entry of clients) {
    const seen = new Set(), pending = [entry];
    while (pending.length) {
      const file = pending.pop(); if (seen.has(file)) continue; seen.add(file);
      const relative = path.relative(root, file).replaceAll(path.sep, '/');
      assert.doesNotMatch(relative, /^lib\/(?:game-engine\/|server-art-(?:data|manifest)\.|game-(?:authority|art)\.)/, path.relative(root, entry) + ' imports ' + relative);
      pending.push(...runtimeImports(file));
    }
  }
});
