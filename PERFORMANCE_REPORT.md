# Stardust Curios pipeline audit

Date: 2026-10-06 UTC. Scope: game v9 + bounded publication adapter + mobile viewer inspection. No actual game save/RNG was read, advanced, copied or changed. No production request was made by this audit.

## Results

- Final combined game suite: 465/465 tests pass; game engine source hash unchanged by these optimizations.
- Final combined helper suite: 61/61 tests pass, including 49 controller/exporter tests, 10 switch tests and the two preserved real-CLI/mock-HTTP integration tests.
- Full pipeline: the official engine CLI completed 81 chosen synthetic actions through day-7 settlement. The controller received 82 successful mock publication acknowledgements, suppressed every duplicate action ID, and recovered one injected transient upload failure without replaying gameplay.
- Before/after public action/state transcript SHA-256 matches exactly: `32d8631a9a8a2c3dca99b0a0049cc69aebe78bebcda056b321f778a9f7bfce29`.
- All 24 synthetic known PNGs and the contact sheet are byte-for-byte identical to the old exporter for equal inputs.
- Generated synthetic saves, images and receipts were confined to temporary directories and removed after each run. Benchmark/smoke/test sources and aggregate results are retained.

## Local timings

These are local wall-clock measurements with mock/in-memory HTTP. CPU contention and filesystem caching vary; they do not measure Internet, Sites storage, phone rendering, or time spent choosing a move.

| Measurement | Before | After |
|---|---:|---:|
| Repeated export, 10 already-known images (median) | 1,296 ms | 49 ms |
| Repeated export, 24 already-known images (median) | 3,478 ms | 56 ms |
| Repair one missing image among 24 known | Redraw entire set | 177 ms |
| Full 24-image cold export, one comparison | 3,167 ms | 3,321 ms |
| Unchanged controller/mock sync (median) | 14.9 ms | 11.9 ms |
| Official CLI/mock-sync with 3,000 old receipts (median) | 636 ms | 236 ms |
| Full 81-action synthetic week, mean of two matched alternating runs | 22.57 s | 21.37 s |
| Per-action P95, mean across those full-week runs | 1,294 ms | 644 ms |
| Per-action median, mean across those full-week runs | 142 ms | 145 ms |

The full-week figures use two alternating baseline/candidate pairs with matched temporary source locations. Their total elapsed times were baseline 23.19/21.95 s and candidate 21.24/21.50 s (~5.3% lower mean, not a statistical guarantee). Earlier unpaired runs varied enough that some candidate totals were slower; no guaranteed aggregate speedup is claimed. The biggest repeatable improvement is removal of redundant work during discoveries and long operation histories. Ordinary action median is effectively unchanged in the full-week run. Game computation itself is already small: new state ~0.08 ms, small public projection ~0.06 ms, week projection ~0.58 ms. Python process startup/CLI costs about 90–114 ms in baseline samples. Locks, validation and fsync remain intact.

## Changes

1. Incremental exporter: cache by renderer content, output size and public paint fields. Validate cached PNG type/dimensions/hash before reuse. Repair missing/corrupt images and redraw only changed identities. Publish paths skip the contact sheet; standalone exports keep their previous default.
2. Cheap warm-art path: canonicalize effective known public paint, check current renderer content and every cached PNG. Duplicate possessions and price/log/revision changes alone no longer load/recompile the full renderer. Cache misses retain the isolated exporter subprocess, 45-second timeout and inherited game lock. A separate preview key prevents stale contact sheets after no-preview exports.
3. Receipt scans: one complete read/validation per exclusive controller execution; newly durable receipts update that execution's in-memory index. The index is discarded on success or failure when the lock is left. Recovery always reloads from disk next time.
4. Activation integration: a verified runtime publication epoch leaves the original game binding and operation journal unchanged. Exact activation acknowledgements can initialize the publication receipt without an immediate duplicate upload. Stale epochs, rollback, source changes and wrong art scope are rejected.
5. Added retained benchmark and full-pipeline smoke scripts and new regression coverage for cache corruption, missing assets, renderer changes, unknown identity masking, links, journal scan counts, reactivation/deduplication and acknowledgement safety.

## Upload observations and limits

The ten-art fixture's first upload was 606 KB; subsequent JSON-only upload was 34 KB. Acknowledged-image hash deduplication already worked before the change and is retained.

The full-week optimized test uploaded 3.90 MB versus 3.25 MB before (same 82 successful requests). The new cache detects changed public paint when items move between inventory and catalog; the old controller skipped already-existing PNGs until a later discovery, so some images could stay stale. This additional changed-image data is a correctness tradeoff, not extra state polling or additional POSTs.

The viewer now uses session/revision/digest/build-aware ETags: unchanged polls return 304 without transferring/parsing the observation or reading its full stored payload. Independent final checks passed 10 frontend tests, 4 activation-SQL tests and TypeScript. The initial React effect was corrected without disabling the rule; final lint, TypeScript and frontend-test reruns all pass. Total independently verified test cases: 540 (465 game + 61 helpers + 10 frontend + 4 SQL). Initial asset uploads still depend on real network and Site storage. No unmeasured network improvement is claimed.

## Reproduction

From the final combined source directory:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools/web_sync/tests -v
PYTHONDONTWRITEBYTECODE=1 python3 tools/web_sync/smoke_pipeline.py --game .
PYTHONDONTWRITEBYTECODE=1 python3 tools/web_sync/benchmark_pipeline.py --game . --output /tmp/stardust-pipeline-timings.json
```

## Final combined verification location

Final tests ran against the combined current-shop source, with the retained 81-action smoke also passing there. Site deployment, live activation, authenticated production HTTP timings and backup verification are owned by the separate deployment task and are not claimed by this synthetic audit.
