// Runs entirely on synthetic CPython fixtures emitted to memory, never game saves.
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { PythonRandom } from '../src/python-random.ts';

const oracle = spawnSync('python', [fileURLToPath(new URL('./rng-oracle.py', import.meta.url))], {
  encoding: 'utf8', maxBuffer: 64 * 1024 * 1024,
});
assert.equal(oracle.status, 0, `Python fixture generator failed: ${oracle.stderr}`);
const fixture = JSON.parse(oracle.stdout);
let operationCount = 0;

function execute(rng, op) {
  const args = (op.args ?? []).map(a => a && typeof a === 'object' && 'bigint' in a ? BigInt(a.bigint) : a);
  let result;
  if (op.method === 'shuffle') {
    result = [...args[0]];
    rng.shuffle(result);
  } else if (op.method === 'choices') {
    result = rng.choices(args[0], args[1], args[2], args[3] ?? undefined);
  } else result = rng[op.method](...args);
  return typeof result === 'bigint' ? { hex: result.toString(16) } : result;
}

for (const entry of fixture.cases) {
  test(`CPython differential ${entry.label}`, async () => {
    const setup = entry.setup;
    const rng = 'seed' in setup ? new PythonRandom(BigInt(setup.seed))
      : 'bytes' in setup ? await PythonRandom.fromBytes(Uint8Array.from(setup.bytes))
        : 'string' in setup ? await PythonRandom.fromString(setup.string)
          : PythonRandom.fromState(setup.state);
    assert.deepEqual(rng.getstate(), entry.initial, 'initial state/seeding mismatch');
    const checkpoints = new Map(entry.checkpoints.map(c => [c.after, c.state]));
    for (let i = 0; i < entry.operations.length; i++) {
      const op = entry.operations[i];
      assert.deepEqual(execute(rng, op), entry.expected[i], `${entry.label} operation ${i}: ${JSON.stringify(op)}`);
      operationCount++;
      if (checkpoints.has(i + 1)) assert.deepEqual(rng.getstate(), checkpoints.get(i + 1), `state after operation ${i}`);
    }
    assert.deepEqual(rng.getstate(), entry.final, 'final state mismatch');
    // Round-tripping JSON state must reproduce the continuation without aliases.
    const cloned = PythonRandom.fromState(JSON.parse(JSON.stringify(rng.getstate())));
    for (let i = 0; i < 700; i++) assert.equal(cloned.random(), rng.random());
    // JSON.stringify canonicalizes -0 to 0; RNG import itself retains -0.
    assert.deepEqual(cloned.getstate(), JSON.parse(JSON.stringify(rng.getstate())));
  });
}

test('JSON state is copied, cache is retained, invalid imports are atomic', () => {
  const rng = new PythonRandom(123);
  const state = rng.getstate();
  state[2] = -3.125;
  rng.setstate(state);
  assert.equal(rng.getstate()[2], -3.125);
  const negativeZeroState = rng.getstate();
  negativeZeroState[2] = -0;
  assert.ok(Object.is(PythonRandom.fromState(negativeZeroState).getstate()[2], -0));
  const original = rng.getstate();
  state[1][0] = 0;
  assert.deepEqual(rng.getstate(), original);
  const invalid = [null, [], [2, original[1], null], [3, original[1].slice(1), null],
    [3, original[1], Infinity], [3, original[1], 'cache'],
    ...[-1, 625, 0.5].map(index => [3, [...original[1].slice(0, 624), index], null]),
    ...[-1, 2 ** 32, NaN, 0.25, 'word'].map(word => [3, [word, ...original[1].slice(1)], null])];
  for (const candidate of invalid) {
    assert.throws(() => rng.setstate(candidate));
    assert.deepEqual(rng.getstate(), original);
  }
  rng.seed(123);
  assert.equal(rng.getstate()[2], null);
});

test('explicit unsupported seeds and malformed arguments reject without hidden fallback', async () => {
  for (const bad of [null, 'abc', 1.25, 2 ** 53, NaN, Infinity, {}, new Uint8Array([1])]) {
    assert.throws(() => new PythonRandom(bad), TypeError);
  }
  for (const bad of ['\ud800', '\udc00', 'x\ud800x']) {
    await assert.rejects(PythonRandom.fromString(bad), TypeError);
  }
  const rng = new PythonRandom(99);
  const original = rng.getstate();
  for (const action of [() => rng.getrandbits(-1), () => rng.getrandbits(1.5),
    () => rng.randbelow(0), () => rng.randrange(0), () => rng.randrange(3, 1),
    () => rng.randrange(1, 3, -1), () => rng.randrange(1, 3, 0),
    () => rng.randrange(1n, 3), () => rng.randint(5, 4),
    () => rng.choice([]), () => rng.sample([1], 2), () => rng.sample([1], -1),
    () => rng.choices([1, 2], [0, 0]), () => rng.choices([1, 2], [1]),
    () => rng.choices([1], [Infinity]), () => rng.choices([1], [NaN]),
    () => rng.choices([1], [1], 1, [1])]) {
    assert.throws(action);
    assert.deepEqual(rng.getstate(), original, 'invalid call consumed state');
  }
  assert.equal(rng.getrandbits(0), 0n);
  assert.deepEqual(rng.sample([], 0), []);
  assert.deepEqual(rng.choices([], null, 0), []);
  assert.deepEqual(rng.choices([1], null, -1), []);
  assert.deepEqual(rng.getstate(), original);
});

test('byte seeding snapshots input before asynchronous digest', async () => {
  const bytes = Uint8Array.from([1, 2, 3]);
  const pending = PythonRandom.fromBytes(bytes);
  bytes.fill(99);
  assert.deepEqual((await pending).getstate(), (await PythonRandom.fromBytes(Uint8Array.from([1, 2, 3]))).getstate());
});

test('differential fixture coverage summary', () => {
  assert.ok(fixture.cases.length >= 50);
  assert.ok(operationCount > 8_000);
  console.log(`Verified ${fixture.cases.length} CPython streams, ${operationCount} exact operations, state checkpoints, and 700-value continuations per stream`);
  console.log(`Oracle: ${fixture.python.split('\n')[0]}`);
});
