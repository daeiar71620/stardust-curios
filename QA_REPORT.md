# v7 Verification Report

## Catalog and item-art release (2026-10-06)

This release changes only the public catalog projection, illustration identity and viewer handling. Private save/protocol version remains 6, and economy/dice mechanics are unchanged. No private player save was read, copied, imported or advanced during development or QA.

Previous v6 results below are retained as historical evidence; this release has its own verification results here.

- Final aggregate: `python3 -m unittest discover -q` passed all **355 tests** in 48.614 seconds. `python3 -m py_compile *.py` passed. This includes all 331 existing regressions and 24 new catalog/privacy/art checks
- The intentional invalid-snapshot-path test prints an argparse error before the successful aggregate summary; this is expected
- Both standalone fixture generators validated all 13 dice and 16 management scenes and removed their temporary directories
- Headless visual checks: the complete 24-item contact sheet and wide (1320×940) / phone (390×844) catalog layouts were inspected. Bee/cat anatomy is distinct; known names/stories and neutral unknown rows are legible. Temporary images were removed
- Actual cloud-window spot-check passed at **1180×812** and **390×844**. Cat/bee portraits are distinct in catalog, stage and details; known stories and collection/discovery labels are correct. Unknown rows and detail modals show only the same question mark, `???` and generic locked copy. Switching tabs after a known detail and paging into unknown entries leaves no stale identity. Narrow paging and zero-discovery scenes also passed
- All v7 test windows were closed; the pre-existing real observer was restored without game actions. All newly generated synthetic observations, launch wrappers and images were removed. No actual save values are included in this report. See [focused GUI QA](ui-qa/actual/CATALOG_V7_GUI_QA.md)

### New coverage

- Exact unknown-entry allowlist: only opaque numeric slot, discovered and collected flags. No semantic ID, name, rarity, category, story, art ID or shape hint
- All 24 types: buying sealed cargo produces identical public output regardless of identity; opening reveals exactly the matching entry
- Selling keeps discovery; collection is tracked separately; v1–v5 imports retain known/opened/sold items while sealed cargo remains secret
- Current CLI, saved observations and read-command repair of stale public projections use the same disclosure boundary without changing private-save bytes or RNG
- Viewer tabs, all catalog pages, card clicks, direct/stale detail overlays and legacy projections cannot expose unseen item identities
- Each of 24 illustrations has a distinct rendered silhouette, including matching legacy public-name fallbacks; unknown art is pixel-identical across all identities/rarities
- Synthetic observations and screenshots are temporary QA material and are removed after checking. Test/generator source remains reproducible

## Historical v6 verification

Verified 2026-10-06 using isolated synthetic games and public-only UI fixtures.
No private player save was read, copied, migrated or advanced. The v5 source release remains separate. The original validation run did not push or deploy code.

## Automated verification

Final aggregate: `python3 -m unittest discover -q` — **331 tests passed**, 37.965 seconds. `python3 -m py_compile *.py` also passed. Breakdown: 69 current core/shop regressions; 74 frozen D20/v4 checks; 52 frozen v5 checks; 32 native v6 management tests; 21 independent v6 audit tests; and 83 viewer tests.

The CLI usage/error line printed during the suite is an intentional invalid-snapshot-path test; the aggregate result is OK.

Coverage includes ordinary budget/capacity commitment; rejected-command atomicity; quota exhaustion across repricing, item changes, reads and process restarts; separate named customer limits; inclusive public price/condition boundaries; deterministic counter eligibility with no extra trade RNG draw; no exact budget/base/RNG leaks; 01 at 9999 despite ineligibility; 100 terminal; unchanged two D10 mapping and final premium arithmetic; free accept/decline and one 1-energy retry; public-preview equality; irrevocable final-failure expiry; frozen quote/bonus behavior; copy-only v1–v5 migration; inherited pending quotes; mixed history boundaries; next-day-only resets; and 65-day persisted-history retention.

The independent audit found and prompted fixes for three damaged-save validation gaps: missing management metadata could reach a projection KeyError; impossible duplicate v6 ordinary visits were not counted per day; and import-version provenance was not cross-checked. These were corruption-hardening defects, not ways exposed by legal CLI actions. The added tests pass after fixes.

Write/race checks cover rollback on precommit failure with identical deterministic retry, committed fsync warnings, public-projection failure/recovery, competing ordinary sales, and competing accept/decline/final offers. Normal CLI use cannot refill a consumed ordinary visit or overwrite a committed result.

## Synthetic balance trial

300 fresh synthetic campaigns: three public-only policies  × 50 seeds  × v5/v6, at most 40 days. The first useful parameter set was retained. Details, tails, bankruptcy and limitations are in [BALANCE_REPORT.md](BALANCE_REPORT.md); raw public-only metrics are in `management-simulation.json`.

This is not a claim of optimal-strategy or long-term economic balance. The preserved 1% 9999 miracle remains a profit lottery; no exploit-proof claim is made.

## Read-only viewer

83 viewer tests passed, including 17 new v6 checks. Ordinary capacity and budget are visible in the public status and visitor views. Item details page through public eligibility/reasons for every buyer. Eligibility is distinguished from buyer availability and initial success probability; exact hidden initial odds are not fabricated. Open details refresh when public price or capacity changes and close when the item disappears.

V3–v5 history remains labeled by its actual rules. Imported pending quotes are explicitly labeled as honored by v6 in both the card and detail; an item’s new-sale eligibility panel cannot be mistaken for revoking a previously promised quote. V6 uses the same roll-low D100 display and exact final-preview math. Wide and phone-sized headless renders were visually inspected. Actual narrow-window captures were checked separately; the sanitized focused report remains under `ui-qa/actual/`. Generated images are no longer distributed.

Actual cloud GUI spot-check passed at 1180×812 and 390×812: ordinary remaining 1/1 and budget 60–120; reasonable, 9999 and poor-condition eligibility; buyer paging; quota-used 0/1 with ordinary buyers unavailable; departure event reasons, zero income and retained item without a fake counter; pending and accepted states; and grandfathered v5 quote messaging. The old quote card/detail explicitly honored the 70 counter, showed legal final range 71–9998 and the 71 example’s 68% chance. The negotiating item panel clearly stated that new conditions do not revoke the promised quote. Text and navigation were readable with no clipping or overlap. All inspected v6 windows were explicit public synthetic demos. Actual narrow-window screenshots and headless render images were removed from the release after verification. Demonstration windows were closed and the pre-existing non-demo spectator was restored visually unchanged. The release report omits all personal game-state values.

## Distribution boundary

The release contains source, frozen legacy validators, docs, tests, generators, synthetic aggregate statistics and textual QA results. Generated demonstration JSON, playthrough records and screenshots are excluded. Automated tests generate the observations they need in temporary directories and clean them up afterward. It excludes private saves, ordinary root observations, backups, locks, runtime caches, personal state, and credentials. Root JSON exceptions contain only deliberate simulation metrics. Opening the spectator does not create or migrate a game; v1–v5 imports require an explicit command and a new target path.

## Post-test artifact cleanup (2026-10-06)

Generated demonstration observations, playthroughs and screenshots were removed from the current release contents. No game rules or runtime engine/viewer source changed. The two fixture generators now use self-cleaning temporary output directories when run directly; the viewer sample test generates its own temporary inputs.

Focused verification after this cleanup: `python3 -m unittest -q test_spectator test_customer_spectator_v6` — **83 tests passed**, 29.032 seconds. Both standalone generators produced their 13 v5 / 16 v6 synthetic observations and removed their temporary output directories. All Python source compiled successfully. The earlier 331-test aggregate above was not rerun for this artifact-only cleanup. The ordinary-buyer budget paragraph in the schema was synchronized with the existing v6 engine rule.
