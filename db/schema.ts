import { integer, sqliteTable, text } from 'drizzle-orm/sqlite-core';
export const currentSnapshot = sqliteTable('current_snapshot', {
  streamId: text('stream_id').primaryKey(),
  activationId: text('activation_id'),
  artScope: text('art_scope'),
  sessionId: text('session_id').notNull(),
  sessionEpoch: integer('session_epoch').notNull().default(1),
  revision: integer('revision').notNull(),
  digest: text('digest').notNull(),
  playState: text('play_state').notNull(),
  sourceSavedAt: text('source_saved_at').notNull(),
  publishedAt: text('published_at').notNull(),
  payload: text('payload').notNull(),
});
export const streamActivations = sqliteTable('stream_activations', {
  activationId: text('activation_id').primaryKey(),
  streamId: text('stream_id').notNull(),
  sessionId: text('session_id').notNull(),
  sessionEpoch: integer('session_epoch').notNull(),
  expectedEpoch: integer('expected_epoch').notNull(),
  fingerprint: text('fingerprint').notNull(),
  revision: integer('revision').notNull(),
  digest: text('digest').notNull(),
  publishedAt: text('published_at').notNull(),
  artScope: text('art_scope').notNull(),
});
// Synthetic vertical-slice tables. They never reference the real game stream.
export const labState = sqliteTable('lab_state', {
  ownerUserId: text('owner_user_id').primaryKey(),
  revision: integer('revision').notNull(),
  boxes: integer('boxes').notNull(),
  publicJson: text('public_json').notNull(),
  lastOperationId: text('last_operation_id'),
});
export const labReceipts = sqliteTable('lab_receipts', {
  receiptKey: text('receipt_key').primaryKey(),
  ownerUserId: text('owner_user_id').notNull(),
  operationId: text('operation_id').notNull(),
  requestHash: text('request_hash').notNull(),
  receiptJson: text('receipt_json').notNull(),
});
// Current native game. Physical names preserve existing receipts; no legacy rules are enabled.
export const gameState = sqliteTable('core_g1_state', {
  ownerUserId: text('owner_user_id').primaryKey(),
  revision: integer('revision').notNull(),
  privateJson: text('private_json').notNull(),
  publicJson: text('public_json').notNull(),
  lastOperationId: text('last_operation_id'),
  gameId: text('game_id').notNull().default('g2-test'),
  gameMode: text('game_mode').notNull().default('test'),
  updatedAt: text('updated_at'),
});
export const gameReceipts = sqliteTable('core_g1_receipts', {
  receiptKey: text('receipt_key').primaryKey(),
  ownerUserId: text('owner_user_id').notNull(),
  requestHash: text('request_hash').notNull(),
  receiptJson: text('receipt_json').notNull(),
});

// Recovery copies created only by an explicitly requested new game.
export const gameArchives = sqliteTable('game_archives', {
 archiveKey: text('archive_key').primaryKey(), ownerUserId: text('owner_user_id').notNull(),
 gameId: text('game_id').notNull(), revision: integer('revision').notNull(),
 privateJson: text('private_json').notNull(), publicJson: text('public_json').notNull(),
 gameMode: text('game_mode').notNull(), archivedAt: text('archived_at').notNull(),
});
