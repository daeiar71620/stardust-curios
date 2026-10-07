CREATE TABLE `game_archives` (
	`archive_key` text PRIMARY KEY NOT NULL,
	`owner_user_id` text NOT NULL,
	`game_id` text NOT NULL,
	`revision` integer NOT NULL,
	`private_json` text NOT NULL,
	`public_json` text NOT NULL,
	`game_mode` text NOT NULL,
	`archived_at` text NOT NULL
);
--> statement-breakpoint
ALTER TABLE `core_g1_state` ADD `game_id` text DEFAULT 'g2-test' NOT NULL;--> statement-breakpoint
ALTER TABLE `core_g1_state` ADD `game_mode` text DEFAULT 'test' NOT NULL;--> statement-breakpoint
ALTER TABLE `core_g1_state` ADD `updated_at` text;
--> statement-breakpoint
UPDATE core_g1_state SET updated_at=(
 SELECT json_extract(receipt_json,'$.committed_at') FROM core_g1_receipts
 WHERE core_g1_receipts.owner_user_id=core_g1_state.owner_user_id
 AND json_valid(receipt_json)
 AND json_extract(receipt_json,'$.operation_id')=core_g1_state.last_operation_id LIMIT 1
);
