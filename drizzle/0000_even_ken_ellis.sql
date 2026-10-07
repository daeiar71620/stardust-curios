CREATE TABLE `current_snapshot` (
	`stream_id` text PRIMARY KEY NOT NULL,
	`session_id` text NOT NULL,
	`revision` integer NOT NULL,
	`digest` text NOT NULL,
	`play_state` text NOT NULL,
	`source_saved_at` text NOT NULL,
	`published_at` text NOT NULL,
	`payload` text NOT NULL
);
