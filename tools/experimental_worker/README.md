# Stardust Worker compatibility port

Experimental, synthetic-only TypeScript port of the public v9 Python rules. The
existing Python game remains the reference. No real save is bundled, imported,
or migrated by this package. Server-only modules must never be sent to a browser.

## Current verified scope

- CPython MT19937 state and all game-used RNG operations on documented fixtures
- All 13 native-v9 mutations and six public read commands
- Full private-state/RNG and 39-field public-projection differential comparison
- 20 mixed campaigns: 11,303 commands and 143,838 repeated read calls, including
  normal first weeks, day-36 continuation, bargaining and collection replacement
- Strict native-state validation; failed actions leave the supplied state intact
- A separate offline native-v8 heritage gate is under test. It does not enable
  an HTTP import, migration, or acceptance by the strict native dispatcher

The initial G1 checkpoint remains separate. See docs/ENGINE_CONTRACT.md,
docs/ACTION_COVERAGE.md and docs/CAMPAIGN_VALIDATION.md for reproducible scope.
The original Python suite's 465 tests include legacy engines and Pillow UI tests;
that number is not a count of translated Worker tests.

## Run synthetic differential checks

Requires Node 24, Python 3 and the trusted public Python release with its frozen
legacy modules. Point only to engine source, never to a saved game.

```sh
STARDUST_ENGINE_SOURCE=/path/to/public/engine.py \
PYTHONDONTWRITEBYTECODE=1 npm test
```

Tests stream generated fixtures in memory and run serially to bound memory.
Campaign checks can take roughly 11 minutes on the validation machine.

## Internal API and public adapter boundary

`executeNative(state, command, args)` is internal. Its return contains private
state and must not be returned wholesale by an API. The adapter stores private
state, receipt and the allowlisted public projection atomically in D1; readers
select only the public projection. A chosen mutation is keyed by operation ID
and expected revision. A duplicate with identical arguments returns its receipt;
a changed request or stale revision fails. Retry the original operation ID after
an uncertain reply, never create a new action ID to repeat the action.

Native initialization accepts an explicit seed only in synthetic harnesses. No
public reset, restart, arbitrary state, seed, or import endpoint is implemented.
The deployed synthetic adapter and its platform authentication are a separate
Site checkout; this package alone does not expose a service or grant access.

## Remaining gates

- Real-save transfer needs an explicit user decision, token-aware JSON/type
  validation, exact supported provenance, and verified import/rollback semantics
- Earlier legacy ancestry and generic CPython float serialization are not proven
- JavaScript/CPython log2 differences remain a named numeric TODO for arbitrary
  references. Exhaustive membership checks rejected the known bad references
  from the legal item domain; tested legal formulas and campaigns matched. This
  is not a proof over every state, platform, or floating-point input
- Discovered-only artwork needs separate authorized staging and delivery checks.
  D1 atomicity does not make R2 image writes part of the same transaction
- The synthetic phone page verifies state transport; it is not full Pillow UI
  parity. Other chat windows need their own supported connection verification
