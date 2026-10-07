CREATE TABLE `stream_activations` (
	`activation_id` text PRIMARY KEY NOT NULL,
	`stream_id` text NOT NULL,
	`session_id` text NOT NULL,
	`session_epoch` integer NOT NULL,
	`expected_epoch` integer NOT NULL,
	`fingerprint` text NOT NULL,
	`revision` integer NOT NULL,
	`digest` text NOT NULL,
	`published_at` text NOT NULL,
	`art_scope` text NOT NULL
);
--> statement-breakpoint
ALTER TABLE `current_snapshot` ADD `activation_id` text;--> statement-breakpoint
ALTER TABLE `current_snapshot` ADD `art_scope` text;