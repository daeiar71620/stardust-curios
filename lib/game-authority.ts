import {getDatabase} from '@/db';
import {sha256} from './hash';
import {SiteError} from './site-auth';
import {ART_VERSION} from './server-art-manifest';
import {createInitialState, executeNative, observationV9, validateNativeState, CoreGameError, NATIVE_COMMANDS, NATIVE_COMMAND_NAMES} from './game-engine/index';
import type {GameState, PublicRecord, NativeCommandDefinition} from './game-engine/index';
import {GAME_INITIAL_SQL, GAME_ARCHIVE_SQL, GAME_APPLY_SQL, GAME_RECEIPT_SQL} from './game-sql.mjs';

export const VIEWER_BUILD = 'native-latest-20261007-1-' + ART_VERSION.slice(0, 12);
export const ACTION_NAMES = ['initialize', ...NATIVE_COMMAND_NAMES.filter(name => !NATIVE_COMMANDS[name].readOnly)];
export const QUERY_NAMES = NATIVE_COMMAND_NAMES.filter(name => NATIVE_COMMANDS[name].readOnly);
export type GameMode = 'test' | 'formal';
export type GameInput = {operation_id: string; expected_revision: number; command: string; args: string[]};
export type GameQuery = {command: string; args: string[]};
type Stored = {revision: number; private_json: string; public_json: string; last_operation_id: string | null; game_id: string; game_mode: GameMode; updated_at: string | null};
type Receipt = {request_hash: string; receipt_json: string};
function object(value: unknown): value is Record<string, unknown> { return value !== null && typeof value === 'object' && !Array.isArray(value); }
function validArgs(command: string, args: unknown, readOnly: boolean): args is string[] {
 if (!Array.isArray(args) || args.some(value => typeof value !== 'string' || value.length > 80)) return false;
 if (command === 'initialize') return !readOnly && (args.length === 0 || (args.length === 1 && ['test', 'formal'].includes(args[0])));
 if (!Object.hasOwn(NATIVE_COMMANDS, command)) return false;
 const definition: NativeCommandDefinition = NATIVE_COMMANDS[command as keyof typeof NATIVE_COMMANDS];
 return definition.readOnly === readOnly && definition.argumentCounts.includes(args.length);
}
export function gameInput(value: unknown): GameInput {
 if (!object(value) || Object.keys(value).sort().join(',') !== 'args,command,expected_revision,operation_id'
  || typeof value.operation_id !== 'string' || !/^[A-Za-z0-9_-]{1,80}$/.test(value.operation_id)
  || !Number.isSafeInteger(value.expected_revision) || Number(value.expected_revision) < 0 || Number(value.expected_revision) > 1e12
  || typeof value.command !== 'string' || !validArgs(value.command, value.args, false)) throw new SiteError('invalid_arguments', 422);
 return value as GameInput;
}
export function gameQueryInput(value: unknown): GameQuery {
 if (!object(value) || Object.keys(value).sort().join(',') !== 'args,command'
  || typeof value.command !== 'string' || !validArgs(value.command, value.args, true)) throw new SiteError('invalid_arguments', 422);
 return value as GameQuery;
}
const receiptKey = (user: string, operation: string) => sha256(JSON.stringify(['core-g1', user, operation]));
function receiptValue(row: Receipt, requestHash: string) {
 if (row.request_hash !== requestHash) throw new SiteError('operation_id_conflict');
 return JSON.parse(row.receipt_json);
}
function privateSeed(): bigint {
 const bytes = crypto.getRandomValues(new Uint8Array(32));
 return bytes.reduce((value, byte) => (value << 8n) | BigInt(byte), 0n);
}
export async function gameAction(user: string, input: GameInput) {
 const db = getDatabase();
 const key = await receiptKey(user, input.operation_id);
 const hash = await sha256(JSON.stringify([input.expected_revision, input.command, input.args]));
 const readReceipt = () => db.prepare('SELECT request_hash,receipt_json FROM core_g1_receipts WHERE receipt_key=?').bind(key).first<Receipt>();
 const prior = await readReceipt();
 if (prior) return receiptValue(prior, hash);
 const row = await db.prepare('SELECT revision,private_json,game_id,game_mode FROM core_g1_state WHERE owner_user_id=?').bind(user).first<Stored>();
 const revision = row?.revision || 0;
 if (revision !== input.expected_revision) {
  const raced = await readReceipt();
  if (raced) return receiptValue(raced, hash);
  throw new SiteError('revision_conflict');
 }
 let state: GameState, publicView: PublicRecord;
 let gameId = row?.game_id || '', mode: GameMode = row?.game_mode || 'test';
 const newGame = input.command === 'initialize';
 try {
  if (newGame) {
   state = await createInitialState(privateSeed());
   // Revision belongs to this owner's authority, and never rolls back on a new game.
   state.revision = revision + 1;
   validateNativeState(state);
   publicView = observationV9(state);
   gameId = crypto.randomUUID();
   mode = input.args[0] === 'formal' ? 'formal' : 'test';
  } else {
   if (!row || revision === 0) throw new SiteError('initialize_game_first');
   const result = await executeNative(JSON.parse(row.private_json) as GameState, input.command, input.args);
   state = result.state;
   publicView = result.observation;
  }
 } catch (error) {
  if (error instanceof CoreGameError) throw new SiteError(error.message, 422);
  throw error;
 }
 const publicJson = JSON.stringify(publicView);
 const committedAt = new Date().toISOString();
 const commit = {ok: true, synthetic: mode === 'test', mode, stream_id: gameId, operation_id: input.operation_id, command: input.command,
  revision: state.revision, public_digest: await sha256(publicJson), committed_at: committedAt, verification: 'same_authority_atomic_commit'};
 const statements = [db.prepare(GAME_INITIAL_SQL).bind(user)];
 if (newGame) statements.push(db.prepare(GAME_ARCHIVE_SQL).bind(await sha256(JSON.stringify(['archive', user, revision])), committedAt, user, revision, key));
 statements.push(
  db.prepare(GAME_APPLY_SQL).bind(state.revision, JSON.stringify(state), publicJson, input.operation_id, gameId, mode, committedAt, user, input.expected_revision, key),
  db.prepare(GAME_RECEIPT_SQL).bind(key, user, hash, JSON.stringify(commit), user, state.revision, input.operation_id, publicJson),
 );
 await db.batch(statements);
 const saved = await readReceipt();
 if (!saved) throw new SiteError('revision_conflict');
 return receiptValue(saved, hash);
}
export async function gameState(user: string, ifNoneMatch?: string | null) {
 const row = await getDatabase().prepare('SELECT revision,public_json,last_operation_id,game_id,game_mode,updated_at FROM core_g1_state WHERE owner_user_id=?').bind(user).first<Stored>();
 const revision = row?.revision || 0;
 const stream = row?.game_id || 'uninitialized';
 const etag = '"' + await sha256(JSON.stringify([VIEWER_BUILD, user, stream, revision, row?.last_operation_id])) + '"';
 if (ifNoneMatch === etag) return {etag, unchanged: true as const};
 const body = {initialized: revision > 0, synthetic: (row?.game_mode || 'test') === 'test', mode: row?.game_mode || 'test',
  stream_id: stream, revision, updated_at: row?.updated_at || null, build: VIEWER_BUILD,
  observation: row && revision > 0 ? JSON.parse(row.public_json) as PublicRecord : null};
 return {etag, unchanged: false as const, body};
}
export async function gameQuery(user: string, input: GameQuery) {
 const row = await getDatabase().prepare('SELECT private_json FROM core_g1_state WHERE owner_user_id=?').bind(user).first<{private_json: string}>();
 if (!row || row.private_json === 'null') throw new SiteError('initialize_game_first');
 try {
  const value = await executeNative(JSON.parse(row.private_json) as GameState, input.command, input.args);
  return {revision: value.state.revision, result: value.result};
 } catch (error) {
  if (error instanceof CoreGameError) throw new SiteError(error.message, 422);
  throw error;
 }
}
export async function gameToolState(user: string) {
 const result = await gameState(user);
 if (result.unchanged) throw new SiteError('state_unavailable', 503);
 return result.body;
}
