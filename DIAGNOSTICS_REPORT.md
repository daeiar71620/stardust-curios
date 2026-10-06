# Public sync diagnostics validation

This update makes local game execution and public-screen publication distinguishable in logs. It does not change game rules, permissions, authentication, network destinations, or the existing retry policy. It does not claim to repair tool-layer approval cancellation.

## Changes

- The CLI prints a validated exact Site destination and the fictional-game/public-projection scope before reading hidden credentials. The current-shop entry rechecks its pointer and scope under the existing lock after input.
- Fixed-schema JSONL diagnostics go to stderr. They include monotonic elapsed time, UTC observation time, a generated trace ID, safe stage names, bounded error categories, and applicable numeric status codes. They exclude credentials, payloads, images, private paths, raw exceptions, and operation/session identifiers.
- Additive `sync_status` distinguishes this invocation's action status, the last locally confirmed journal revision and its provenance, the last durable local server-ACK receipt, and the publication stage. It never asserts continuously live server state.
- A verified ACK not yet recorded locally remains distinct from a durable publication receipt. Explicit operator reconciliation retains `operator_review` provenance; abandoned outcomes do not assert a confirmed commit.
- Diagnostic output failure does not change execution or retry behavior. Optional diagnostic reads cannot block an existing recovery that does not require that receipt. The actual publication path still enforces its required receipt checks.

## Verified results

All checks used temporary synthetic games and fake HTTP. No production Site calls or real game operations were made.

| Check | Result |
| --- | --- |
| Full game unit suite | 465 passed |
| Sync/controller/art/CLI suite | 88 passed, including 27 new diagnostic/recovery cases |
| Python compilation | Passed |
| Full synthetic first week | 81 official actions, 82 acknowledged mock publications |
| Duplicate-action suppression | All suppressed |
| Transient upload recovery | No game replay |
| Synthetic public trajectory | Exact match with the prior verified baseline |
| Synthetic outputs | Cleaned by test harness |

Trajectory SHA-256: `32d8631a9a8a2c3dca99b0a0049cc69aebe78bebcda056b321f778a9f7bfce29`.

The 27 new cases cover ordered stages, redaction canaries, pre-action and sync-only authorization failure, commit/publication separation, duplicate IDs, uncertain engine and renderer timeouts, damaged projections and receipts, mismatched ACKs, verified-ACK/local-write failure, epoch changes, operator-reviewed and abandoned outcomes, unchanged transient budgets, unknown review errors without automatic retries, broken diagnostic sinks, preflight ordering/scope changes, and both early-switch and remote-commit recovery.

An independent review found two recovery compatibility issues during development. Both were fixed and retained as independent tests: recovery of the recorded target after early preparation failure, and authenticated pointer recovery despite a malformed optional local ACK receipt. No remaining blocking review findings were reported.

## Commands

```sh
python3 -m unittest discover -v
python3 -m unittest discover -s tools/web_sync/tests -v
python3 -m compileall -q .
python3 tools/web_sync/smoke_pipeline.py --game .
```

## Limits and handoff

- Validation was performed on isolated local source before publication. This public source release does not install the update into a live game runtime, activate a session, or deploy a Site.
- No frontend changes are included. A phone or Site cannot know an upstream local pending revision until information reaches it.
- Logs are stderr output by default. If an outer tool discards output during cancellation, capture it in a new private log during a subsequently authorized run. A missing final event alone does not identify the cancellation cause or prove that no game action committed.
- Recovery of a first switch that failed before any current pointer existed must repeat the original `--target-config` so preflight can show the destination before hidden input. Keep the same switch ID.
- No new credential, grant, daemon, alternate transport, or automatic review-denial retry is introduced. Do not use this update as authorization to retry an already denied live upload.
- Existing browser/Site tests were not rerun because no Site source was changed. No claim about real-network latency or platform-review reliability follows from these synthetic checks.
