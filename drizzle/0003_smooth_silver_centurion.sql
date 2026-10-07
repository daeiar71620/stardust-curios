CREATE TABLE `lab_receipts` (
	`receipt_key` text PRIMARY KEY NOT NULL,
	`owner_user_id` text NOT NULL,
	`operation_id` text NOT NULL,
	`request_hash` text NOT NULL,
	`receipt_json` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `lab_state` (
	`owner_user_id` text PRIMARY KEY NOT NULL,
	`revision` integer NOT NULL,
	`boxes` integer NOT NULL,
	`public_json` text NOT NULL,
	`last_operation_id` text
);
