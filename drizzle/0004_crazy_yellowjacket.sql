CREATE TABLE `core_g1_receipts` (
	`receipt_key` text PRIMARY KEY NOT NULL,
	`owner_user_id` text NOT NULL,
	`request_hash` text NOT NULL,
	`receipt_json` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `core_g1_state` (
	`owner_user_id` text PRIMARY KEY NOT NULL,
	`revision` integer NOT NULL,
	`private_json` text NOT NULL,
	`public_json` text NOT NULL,
	`last_operation_id` text
);
