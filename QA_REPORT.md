# Combined v9 Budget + Action/Publish Release Verification

Verified 2026-10-06. The v9 engine/viewer/test sources below are unchanged from the validated 465-test budget release. Public-safe synchronization helpers are now packaged under `tools/web_sync/`; the prior budget-only ZIP remains separate.

## Integration checks

- Preserved budget verification: **465 tests passed** in the prior final engine/viewer aggregate, as detailed below. That full suite was not repeated for this packaging integration.
- `python3 -m unittest discover -s tools/web_sync/tests -v`: **25 tests passed in 1.698 seconds** in the combined directory: the original 23 synthetic controller tests plus 2 real-v9-CLI cross-integration tests.
- Cross-integration ran the documented config/stdin entrypoint with mocked HTTP, actual v9 `new`, `buy`, and `open` commands against temporary synthetic saves, and the actual known-art renderer. It verified revision advancement, no duplicate action on repeated operation ID, upload-only recovery after an engine commit, request-byte hash acknowledgement, known-art delta suppression, undiscovered-entry masking, and absence of the dummy access token from output and durable receipts.
- All distributed Python files compile. Release manifest and ZIP checks cover the complete packaged file set. Only source, example configuration, documentation, tests, historical synthetic aggregate statistics, and sanitized text QA reports are included.

The cross-tests never called the production website and did not inspect, migrate, or advance a real game. They do not establish that a new production gameplay action has completed through the controller. Site deployment and its current private-session receipt are verified separately; no owner-specific Site source, access token, URL, project ID, runtime configuration, receipt, actual game state, or private image is included here.

The helper requires a compatible `/api/ingest` server acknowledgement containing `ok`, `session_id`, `session_epoch`, `revision`, `digest`, `request_sha256`, and `published_at`. Request SHA-256 is checked against the exact transmitted bytes; server projection digest is stored separately. Linux/macOS POSIX locking and Python 3.10+ are required. The controller provides conservative recovery, not an unconditional exactly-once guarantee across arbitrary crashes.

---

# v9 Smooth Budget Verification Report

Verified 2026-10-06 using isolated synthetic states and temporary public-only rendering fixtures. No actual player save or observation was read, copied, migrated, or advanced. The prior v8 source is unchanged; this release is a separate copy.

## Scope and result

V9 replaces only the initial-sale hidden-budget cliff with a continuous relative-overage penalty before integer rounding. Named and ordinary customers use the same rule. Their private budget now means normal spending comfort rather than a hard purchase limit. Public counter eligibility still uses the same public range ceiling, reference-price, preference and condition checks. Final-offer exact previews, the 01 miracle / 100 fumble, two independent D10 draws, buyer quotas, prices/costs, quality collections and RNG sequencing remain unchanged.

## Automated checks

- `python3 -m unittest discover -q`: **465 tests passed in 83.403 seconds** on the final engine/viewer/test sources. This includes all 412 prior tests and 53 new v9 tests: 15 focused curve tests, 26 independent formula/migration audit tests, and 12 viewer/privacy/history tests.
- `python3 -m py_compile *.py`: passed.
- Both standalone fixture generators passed: 13 dice scenes and 16 management scenes, created in temporary directories and cleaned afterward.
- The independent audit passed separately, and the final aggregate includes its additional boundary-date and cross-version-pending regressions.

The expected argparse usage/error output tests rejection of a snapshot path that could overwrite the observation; it is not a failing test.

## Formula calibration and privacy

The implementation calculates raw = 60 + bonus − 50 × log2(price/reference), clamps the continuous base to 1–99, divides by 1 + 2 × max(0,price/budget−1), then floors and clamps the result to 1–99. Within budget it exactly matches the frozen v8 formula. It does not floor the base before applying the penalty, and it does not let an uncapped raw value bypass the overage penalty.

At hidden reference = hidden comfort budget = 100 and bonus = 0, synthetic prices 99 / 100 / 101 / 110 / 150 / 200 / 300 give thresholds 60 / 60 / 58 / 44 / 15 / 3 / 1 percent. This demonstrates the boundary and tail; it is not a forecast for any actual item or buyer. Full price sweeps are non-increasing and bounded 1–99. No fresh balance campaign or claim of economic optimality accompanies this narrow fix; the retained v6 balance report remains historical.

Both buyer types can normally buy just above comfort budget. All 100 digit pairs still use exactly two RNG draws; the number of successes equals the threshold, including 01 and excluding 100. Missing/invalid v9 budget inputs and unknown transaction-rule versions fail closed. Current initial roll records retain null base_chance and premium; no private overage multiplier is exported. Repeated status, inspect, market and visitors reads are deterministic and preserve private bytes/RNG. Changing exact budgets or actual base values cannot change the pre-roll public projection. First-sale exact odds remain unadvertised; final quotes still preview exact odds from public inputs only.

## Save and history compatibility

Private/public protocol and new transaction labels are 9. The added `_legacy_v8.py` is byte-identical to the original v8 engine (SHA-256 ef7e25636884a99b0eac7797379b32e68457f5262a4a5a455945a5295718b17e). `import-v8` is explicit, copy-only, refuses existing destinations and never plays or auto-continues a game. Existing v1–v6 import routes remain supported.

The new budget provenance boundary preserves historical v3/v4/v5/v6 labels and threshold/results. Already-promised pending quotes validate their initial roll with its original rule, including the old 1% over-budget cliff, then preserve the same free accept/decline and unchanged final-offer calculation. A later committed final roll carries v9, while the initial origin stays historical. All resources, private hidden inputs, RNG, buyer usage and v8 quality progress are preserved; collection grace is neither reset nor regranted.

Independent audit covers zero history, pending over-budget quotes, mixed D20/percentile history, absolute sequence boundaries after the 60-row tail truncates, malformed provenance, relabeling attempts, and copy/read rejection atomicity. The audit found two provenance-hardening gaps that were fixed and retested: direct v1–v5 imports must share the existing management boundary, and retained/new rows must lie on the correct day side of the budget-import boundary. Direct v1–v6 metadata also matches its synchronous collection-upgrade point. These checks detect inconsistent saves; no claim is made that local editable save files are tamper-proof.

Prior regression expectations changed only for the new protocol/current rule label and the intentionally replaced over-budget formula. Existing within-budget arithmetic and final-offer parity remain tested against frozen engines, and historical labels remain explicit rather than globally rewritten.

## Viewer verification

V9 percentile detection, new/historical rule labels and honored pending-quote captions are covered by 12 new viewer tests. The worker passed these with 17 existing buyer tests, then passed 95 general/catalog/collection viewer tests, for 124 affected viewer checks. Eight temporary synthetic wide and phone-sized buyer, ordinary-visitor and v3/v6-origin negotiation renders were visually inspected: comfort-budget text, the unchanged hard counter-eligibility ceiling, exact final forecasts and historical captions fit without overlap or clipping. The temporary images were deleted. This was headless Pillow verification; an actual GUI/window check was not run, and the existing real observer was not opened or altered.

## Distribution

The release contains engine/viewer source, frozen validators, documentation, reproducible tests/generators, historical aggregate balance statistics and text-only QA reports. The ZIP excludes private/runtime saves, observations, generated demo scenes, playthroughs, screenshots, cache directories, locks, credentials and temporary outputs. No real-session migration or GitHub publication was performed as part of this development worker.

---

# Historical v8 Quality Collection Verification Report

Verified 2026-10-06 using synthetic states only. No actual player save was read, copied, migrated or advanced. Development used a separate directory; the previous v7 source remains intact.

## Current automated results

- `python3 -m unittest discover -q`: **406 tests passed in 85.373 seconds**. This aggregate includes all 355 previous tests, 40 new independent engine tests and the initial 11 collection UI tests
- Two backend-projection UI cases were added after aggregate discovery, then four narrow-text wrapping regressions. The final affected renderer run passed **112 tests** across collection, catalog, customer and general viewer suites. The final source contains 412 test methods. A second whole-project aggregate was not run for those test additions and the focused wrapping-only change
- `python3 -m py_compile *.py` passed after final source edits
- Both standalone generators validated 13 dice and 16 management scenes and removed their temporary directories. Generated demo observations and screenshots are not release contents
- The expected argparse usage/error line during the aggregate comes from the invalid-snapshot-path rejection test; the aggregate ended OK
- `_legacy_v6.py` is byte-identical to the previous v7 production engine, retaining protocol 6 as an independent migration/trading oracle

## New rule coverage

Forty independent engine tests verify native protocol 8/unchanged trade rules6; inclusive 69/70 quality boundary; qualified-only categories and distinct themes; all four fixed milestones, including no unpromised fourth-category requirement at tier 3; bounded longhaul caps; unchanged any-quality set perks; earned milestones surviving investment and repair failure; explicit strict replacement, one-energy fee, identity and lock preservation, no RNG or repeated robot energy; full-inventory swaps; atomic equal/worse/missing/unavailable rejection; cabinet repair cost, RNG, two-total/once-daily limits and failure degradation; no direct cabinet sale/price; copy-only imports v1–v6; persistent one-stage grace and expiry even during cascaded milestone checks; old first-week won/missed preservation; v6 pending accept/final-offer parity; old-history and exact-budget preservation; rejected v8 re-import/relabel; and hidden-cargo/catalog privacy.

Only expected prior assertions changed: the current protocol now equals 8 and collected items may now be repaired. Legacy trade assertions still require rules_version 6. Known and unknown codex schemas are unchanged.

## Viewer coverage

Read-only collection overview and detail views show personal/qualified totals, qualified categories/themes, the current threshold, missing requirements, known low-condition reasons, cabinet repair commands and inventory same-type replacement eligibility. Old-stage grace is explicit. The viewer never executes these commands.

Renderer tests cover wide 1320×940, portrait 760×1240, phone 390×844, minimum 320×568 and 1364×1024; all 24 slots remain reachable after the taller quality summary. Complete requirements fit the read-only detail panel. Public-item joins are allowlisted; unknown entries retain exactly slot/discovered/collected and cannot acquire repair/replacement/quality identity details. Repeated pages, stale detail refresh, Close, tab changes and disappearances remain covered.

Actual cloud GUI spot-check passed with the real `spectator.py --demo` at 1180×812 and an exact 390×844 window. Checked: personal versus qualified totals, complete category/theme requirements, threshold, cabinet shortfall and repair cost/energy/command, eligible 93% replacement and rejected 60% replacement of a 65% cabinet copy, one-for-one explanation, read-only warning, unknown card/detail staying ???, active legacy grace, next-stage quality wording and live public-observation refresh. No blocking functional defect was found. The one test window was confirmed closed; the pre-existing real viewer was restored focused/fullscreen with its prior view. Temporary synthetic scenes and helper directory were removed and their absence verified. No screenshots were saved or published and no real session was run or save read.

A user-provided narrow screenshot identified a minor percentage-token line break. The final fix only makes numeric percentages/fractions atomic during wrapping and ellipsis truncation; it does not redesign the layout. Four new regressions cover 70%,99%, fractions, the exact event sentence across narrow widths and whole-token ellipsis. The 112 affected renderer tests and compilation pass. A second actual 390×844 window check confirms the event sentence now wraps before the whole 70% token, with no clipping. The user's original screenshot remains untouched outside the release. The second demo window was confirmed closed, its temporary directory removed, and the original real viewer remained fullscreen and was refocused. See [focused actual GUI record](ui-qa/actual/COLLECTION_V8_GUI_QA.md).

## Scope and remaining uncertainty

The new progression changes collection qualification only. Cash/reputation/upgrade schedules, buying/selling values, ordinary buyer capacity/budget, percentile dice and negotiations are unchanged. The original balance report remains historical v6 evidence, not a claim that v8 long-term progression is perfectly balanced. Human pacing of the quality thresholds remains a playtesting question.

Private files, fake saves, generated observations/playthroughs/screenshots, caches and credentials are excluded. The release contains source, frozen validators, tests, docs, temporary-only generators and the pre-existing aggregate economic report. Importing remains an explicit copy-only operation to a new path.

---

# Historical v7 Verification Report

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
