# Bounded native-v8 heritage compatibility gate

## Scope and authority

`validateV8HeritageState(value)` is an offline, read-only validator for a fully
materialized canonical v9 state descended directly from a **native v8** state.
It neither reads a source save nor performs migration. It does not open an
endpoint, alter `executeNative` admission, enable an import UI, persist state,
change permissions, or authorize transfer of private game state.

All test inputs originate from synthetic `_legacy_v8.new_state(seed)`. The
oracle calls the official `engine.migrate_v8(source_bytes)` on those synthetic
bytes only. No real game, save, observation, database, or service was read or
migrated. No payload fixtures are written to disk or published.

## Accepted profile

- `version` is 9
- `migration`, `engine_upgrade`, `management_upgrade`, and `collection_upgrade`
  exist and are all null
- `budget_upgrade` has exactly `from_version`, `source_day`, `source_phase`, and
  `source_roll_seq`; `from_version` is exactly 8
- `source_day` is an exact safe integer in `1..state.day`; `source_roll_seq` is
  an exact safe integer in `0..state.roll_seq`; source phase is active,
  week_summary, or lost
- Retained roll IDs at or before `source_roll_seq` use rules 6 and occur on or
  before `source_day`; later IDs use rules 9 and occur on or after that day
- A pending trade uses current rules 9 while its `origin_rules_version` matches
  its retained failed initial row, either 6 or 9. An old initial threshold is
  checked with rule 6, including its old over-budget 1% cliff. It is never
  recomputed using the smooth-budget rule 9
- All existing canonical state, D100 outcome, final-offer arithmetic, pair,
  daily-customer, item, quality, pending-lock, event, resource, and canonical
  CPython-v3 RNG invariants remain enforced by the common validator

The native-v9 entry point remains strict. A Python-valid v1–v6→v8→v9 chain is
rejected even though its most recent `budget_upgrade.from_version` says 8.
Such chains carry earlier provenance and are outside this bounded gate.

## Shared implementation boundary

The gate establishes the narrow ancestry marker and calls the shared
`validateCanonicalState(value, {sourceDay, sourceRollSeq})` implementation.
`validateNativeState` continues to use the null/native profile. This avoids a
second copy of the common state validator and D100/pending validation logic.
The common function revalidates the exact provenance marker and requires its
cutoff to match the supplied boundary, so an unchecked boundary cannot bypass
ancestry checks. The low-level function is an internal implementation detail,
not an external admission API; callers should use the strict named wrappers.

The gate and common validator inspect plain data records and exact host numeric
types without coercing, repairing, or normalizing the input. Validation consumes
no random draws and preserves the supplied state, even on rejection. Errors
name a field and reason using the existing `NativeStateValidationError` surface;
they do not echo hidden field contents.

## What the migration oracle checks

The official source migration is a copy operation. The oracle independently
compares the source and result and requires all fields to remain identical except:

1. Version changes from 8 to 9
2. The exact budget-upgrade marker is added
3. A pending trade's current rules change from 6 to 9; its origin, frozen
   context, binding quote, and initial dice stay unchanged
4. One import event is added, incrementing `event_seq` once and preserving the
   previous bounded log before the new entry

In particular, migration preserves revision, source day and phase, resources,
full RNG including its cache, inventory and sealed cargo, repairs, daily usage,
old history, all quality fields, milestones, first-week result, and quality-based
campaign progress. No collection grace stage is inserted for native-v8 origin.
These are migration assertions against the source/result pair. The validator
alone does not receive an original snapshot and cannot prove that a later state
preserved an unavailable original revision or RNG.

## Verification design

### Canonical fixture and corruption differential

`tests/heritage-fixtures.py` produces 482 Python-approved synthetic heritage
states and 95 mutation probes. Explicitly enriched fixtures isolate difficult
boundaries; they are not misrepresented as naturally reached playthroughs.

Coverage includes all 100 old initial outcomes, all 100 old final outcomes,
all 100 v6-initial→v9-final outcomes, every named buyer's pending/accept/decline/
offer/expiry paths, old over-budget pending chance, quality thresholds and
voyages, phase markers, and rolling-window edges 59/60/61/62/64/65. The valid
leading final after its initial falls out is retained; earlier or nonleading
unpaired finals are rejected. All six lawful older-import chains are rejected.

Corruptions cover provenance keys and types, cutoff ordering, source days,
old/new rule labels, pending origin and frozen inputs, stale event rolls,
final pairs and arithmetic, daily caps, quality fields, and common numeric/RNG
limits. Intentional stricter host-domain restrictions are labelled separately
from Python agreement. Non-JSON host probes add getters, inherited records,
hidden properties, sparse arrays, symbols, BigInt, NaN, and Infinity.

### Genuine old-to-new campaign differential

`tests/heritage-campaign.py` uses eight public-observation-driven campaigns.
Each starts with `_legacy_v8.new_state(seed)` and disclosed synthetic initial
financing. After initialization, all changes arise from real source commands;
there are no state patches, fabricated items, forced dice, or reseeds.

Four campaigns migrate while an old pending quote is open, two on day 8 after
real first-week/quality progress, and two after old history already exceeds the
60-record window. Play continues after migration, through later complete old
history eviction, management, collection repair/replacement, and additional
milestones. The fixed matrix runs 1,257 old commands and 4,084 new commands,
reaching day 53. The test-only JavaScript harness uses the existing action modules
with clone/rollback and this gate; it does not add a runtime heritage dispatcher.

At every post-migration command the harness compares the exact error or full
private state (including complete RNG), revision, all public fields, and repeated
read-only projection/forecast behavior against Python. Input states stay
unchanged and failed transactions have no RNG effects. Deterministic actions
retain RNG byte-for-byte in canonical state. Test transport streams with
backpressure and never writes generated state payloads to fixture files.

## Running

From the port workspace, set `STARDUST_ENGINE_SOURCE` to the trusted public v9
`engine.py`, with its sibling `_legacy_v8.py` and prior public engine modules:

```sh
STARDUST_ENGINE_SOURCE=/path/to/public/engine.py \
  node --experimental-strip-types --test tests/heritage.test.mjs
```

The standard `tests/*.test.mjs` test glob also includes the heritage suite. The
aggregate native suites should be rerun after shared-validator integration.

Pinned source bytes used for this gate:

- `engine.py` SHA-256:
  `53bd47db6dbaa80db3ea1f0e8adedc9dc61fcd28d4bbbf342e6a5c1e853d0dff`
- `_legacy_v8.py` SHA-256:
  `ef7e25636884a99b0eac7797379b32e68457f5262a4a5a455945a5295718b17e`

Relevant source definitions are `migrate_v8`, `_mark_budget_upgrade`,
`_validate_state`, `_validate_trades`, `_initial_chance`, `_final_chance`, and
`_public_collection_progress` in v9, and native `new_state`, `apply_command`,
`_validate_state`, and `_validate_trades` in `_legacy_v8.py`.

## Verified result (2026-10-06 UTC)

The focused command above passed all **7 test groups**, with zero failures,
skips, or TODOs, in approximately **93 seconds**. It checked 482 accepted
fixtures, 95 mutation probes, six rejected older-origin chains, and eight
campaigns with 1,257 old commands plus 4,084 post-migration commands.

The first campaign run exposed one shared projection omission: the native-only
projection returned null for `budget_upgrade`. Integration now projects only its
four public marker fields by an explicit whitelist. The complete focused suite
was rerun after that fix and passed. Hosted/native admission remains unchanged;
there is no heritage importer or runtime execution entry point.

This result is the heritage-focused suite. The full existing native regression
matrix and deployment checks are separate integration verification.

## Deliberate limits

- This is bounded consistency and differential evidence, not universal state
  equivalence, save authenticity, or proof of replay reachability
- Once old rows are evicted, their contents cannot be revalidated from the
  retained window. A valid historical marker alone does not authenticate them
- JSON token fidelity is a separate unresolved importer gate. Object-only
  validation cannot distinguish an integer token from an equivalent floating
  token after ordinary `JSON.parse`; raw strings/bytes are rejected here
- Safe integers and canonical CPython RNG v3 deliberately restrict Python's
  broader input space. These native host restrictions remain in effect
- The shared `Math.log2` portability caveat for arbitrary references remains
  explicit. Tested lawful fixtures and campaigns do not establish all-input,
  every-runtime threshold equivalence
- No result here authorizes reading, moving, migrating, resetting, or replacing
  a real game or installing/deploying an import path
