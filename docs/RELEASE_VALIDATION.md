# Latest-only integration validation

Validated on 2026-10-07 UTC. This is a source release, not evidence that the
complete application has been deployed or visually verified in a browser.

## Completed gates

| Gate | Result |
| --- | --- |
| Canonical TypeScript engine and synthetic differential tests | 2,195 passed; one explicit numeric TODO |
| Latest-only Python reference and renderer tests | 282 passed |
| Authority, private artwork, MCP transport, and spectator synchronization | 61 passed |
| Reproducible illustration checks | 5 passed |
| TypeScript and ESLint | Passed with no errors or warnings |
| Production build | Passed |

The distinct aggregate is **2,543 passed and one TODO**. The engine suite was
also run independently against both the trusted original v9 implementation and
the cleaned Python reference; those duplicate runs are not counted twice.
The reader cache repair reran the full 282-check Python suite, the 61 Site
checks, artwork verification, type/lint checks, and the production build; its
seven deterministic regressions also passed 50 consecutive runs. Rules and RNG
source remain byte-identical to the preceding validated release. See
[READER_CACHE_FIX.md](READER_CACHE_FIX.md) for the reproduced failure and repair.
See [ENGINE_VALIDATION.md](ENGINE_VALIDATION.md) for exact campaign, RNG, numeric,
and native-state domains, and the reference's QA report for Python details.

The 20 synthetic campaigns include 11,303 commands and 145,459 complete public
comparisons. Full private state and RNG were compared as well. No live save,
account database, or real-game RNG was used as a fixture.

The numeric TODO is limited to engineered arbitrary floating-point reference
values where V8 and CPython log2 differ at a floor boundary. The eight identified
references are absent from the enumerated current item-reference domain.
Reachable-value sweeps and all campaigns passed. Universal floating-point
equivalence is not claimed.

## Authority and privacy

The storage tests cover duplicate operation IDs, revision conflicts, concurrent
writers, atomic state/projection/receipt commits, failed-transaction rollback,
new-game archival, and monotonic revisions across game switches. Legacy physical
table names and migration history are retained solely to preserve committed data
and receipts; old game formats and import execution paths are absent.

All 24 illustration files reproduce byte-for-byte from the cleaned reference.
They are embedded only in a server module. Image access checks authenticated
identity, active game identity, and current discovery before accessing private
art or its cache. Tests cover unknown IDs, stale games, conditional requests,
cache corruption, and cache unavailability. R2 cache writes are explicitly
outside the D1 transaction; verified bundled art remains the fallback.

The final client output was checked against all 24 private catalog names and
24 distinctive encoded image markers: no matches. The built asset binding points
only to `dist/client`, not to server output or the source artwork directory.

## Size and timing

Using the same compression measurement, the previous client output was about
192 KB gzip and this output is about 136 KB gzip, a reduction of approximately
29%. Raw client output fell from 679,867 to 454,445 bytes, with 16 output files
instead of 33. These measurements describe the complete build output rather
than a browser's initial network transfer.

A bounded local synthetic CPU sample of 200 price operations measured a median
of 0.422 ms and p95 of 0.736 ms. Status projection measured a median of 0.214 ms
and p95 of 0.367 ms. These are warm in-memory execution measurements, excluding
D1, network, authentication, cold starts, and rendering; they are not hosted
latency promises.

## Live evidence and remaining gates

The preceding G2 deployment was exercised through the connected native MCP:
repair, collect, end-day, buy, open, and sell committed successfully; an exact
duplicate repair returned its original receipt without another charge. The
phone had already confirmed the same-authority core update path. This verifies
the deployed predecessor's native path, not this new complete integration.

Before applying this release to an existing Site:

1. Retrieve and reconcile its actual current source, including edits performed
   in another editor; preserve its identity and private access configuration.
2. Publish through the supported Sites workflow and confirm deployment success.
3. Verify discovery of the three current game tools, an authenticated read,
   and a bounded synthetic mutation/duplicate check against the new deployment.
4. Inspect the complete spectator on a phone and desktop, including an observed
   update, details, navigation, and private discovered artwork.

Synthetic rendering and synchronization checks passed locally. Actual Chromium
visual QA was blocked by a process-socket permission restriction. No screenshot
inspection or live verification of this final UI is claimed.

No formal game was created by this integration work. Start one only after the
deployment gates pass and the user explicitly asks to begin.
