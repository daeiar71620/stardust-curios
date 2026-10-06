/**
 * Offline, read-only compatibility gate for canonical v9 state descended directly
 * from native v8. It does not read bytes, migrate, repair, execute, import, persist,
 * or authorize transferring a save. Earlier migration chains remain unsupported.
 *
 * The common canonical validator owns the full state and D100 invariants. This
 * wrapper only establishes the narrow, validated historical-rule boundary.
 */
import {NativeStateValidationError, validateCanonicalState} from './native-validation.ts';
import type {GameState, PublicRecord} from './types.ts';

function fail(path: string, detail: string, unsupported = false): never {
  throw new NativeStateValidationError(path, detail, unsupported);
}

// Inspect descriptors before reading any values, including provenance getters.
function dataRecord(value: unknown, path: string): PublicRecord {
  if (value === null || typeof value !== 'object' || Array.isArray(value)
      || ![Object.prototype, null].includes(Object.getPrototypeOf(value))) {
    fail(path, 'expected a plain data object');
  }
  for (const key of Reflect.ownKeys(value)) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key)!;
    if (typeof key !== 'string' || !descriptor.enumerable || !('value' in descriptor)) {
      fail(path, 'expected enumerable data fields');
    }
  }
  return value as PublicRecord;
}

function boundedInteger(value: unknown, path: string, low: number, high: number): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < low || value > high) {
    fail(path, 'expected an exact safe integer in range');
  }
  return value;
}

/** In-memory canonical objects only. All reads are validation-only and consume
 * no RNG. A valid marker is consistency evidence, not proof of save authenticity
 * or replay reachability. Acceptance does not enable executeNative/import APIs. */
export function validateV8HeritageState(value: unknown): asserts value is GameState {
  const state = dataRecord(value, 'state');
  if (state.version !== 9) fail('version', 'expected v9 descended directly from native v8', true);
  for (const key of ['migration', 'engine_upgrade', 'management_upgrade', 'collection_upgrade']) {
    if (!Object.hasOwn(state, key)) fail(key, 'required provenance marker is missing');
    if (state[key] !== null) fail(key, 'older imported ancestry is unsupported by the native-v8 heritage gate', true);
  }
  if (!Object.hasOwn(state, 'budget_upgrade')) fail('budget_upgrade', 'required native-v8 boundary is missing');
  const upgrade = dataRecord(state.budget_upgrade, 'budget_upgrade');
  const keys = ['from_version', 'source_day', 'source_phase', 'source_roll_seq'];
  if (Object.keys(upgrade).length !== keys.length || keys.some(key => !Object.hasOwn(upgrade, key))) {
    fail('budget_upgrade', 'unexpected or missing native-v8 boundary fields');
  }
  if (upgrade.from_version !== 8) fail('budget_upgrade.from_version', 'only direct native-v8 ancestry is supported', true);
  const day = boundedInteger(state.day, 'day', 1, 1e12);
  const sequence = boundedInteger(state.roll_seq, 'roll_seq', 0, Number.MAX_SAFE_INTEGER);
  const sourceDay = boundedInteger(upgrade.source_day, 'budget_upgrade.source_day', 1, day);
  const sourceRollSeq = boundedInteger(upgrade.source_roll_seq, 'budget_upgrade.source_roll_seq', 0, sequence);
  if (!['active', 'week_summary', 'lost'].includes(upgrade.source_phase as string)) {
    fail('budget_upgrade.source_phase', 'unrecognized source phase');
  }
  validateCanonicalState(value, {sourceDay, sourceRollSeq});
}
