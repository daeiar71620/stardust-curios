# Latest-only native engine validation

Both complete aggregates passed on 2026-10-07 UTC: the original trusted v9
source and the cleaned latest-only Python reference each produced **2,196 tests,
2,195 passes, zero failures, and one explicit numeric TODO**. No gameplay or RNG
discrepancy was found in the supported native-v9 test domain.

## Canonical source and supported state

`lib/game-engine/` is the single editable TypeScript runtime. The hosted adapter
and synthetic tests import this tree directly. Its public entry point is
`lib/game-engine/index.ts`:

- `executeNative`: validated, copy-on-write command dispatch
- `createInitialState`: internal initialization using server-owned entropy
- `observationV9`: the complete 39-field public observation
- `validateNativeState`, `NativeStateValidationError`, and `CoreGameError`
- `GameState`, `PublicRecord`, and `NativeEngineResult` types

The engine remains v9. No new state or game-rules version was introduced. It
supports only native v9 state and v9 trades, including real pending negotiations,
full percentile histories, all current management actions, and unlimited days.
The five provenance fields remain required and strictly null. Their public null
values and the `legacy_grace: false` public fields preserve observation parity;
there is no import, migration, grace-period, or old-rule execution path.

Removed from the runtime: `transitionCore`, `assertCoreEnvelope`,
`observationCore`, numeric rules 5/6, optional/null trade budgets, historical
collection-grace branches, and obsolete provenance types. The older heritage
validator and heritage test families are not part of this tree. Basic, management,
day, and trade differential tests now exercise the actual native dispatcher.

Daily demand and visitor draws share `daily-state.ts`; daily and public energy
and operating-cost calculations share the same rule functions. Draw order,
CPython RNG state, event snapshots, milestone timing, price formulas, and gameplay
messages remain unchanged. The literal `walkin-v6:` domain separator intentionally
remains: current v9 uses it to derive deterministic daily budgets. Renaming it
would change gameplay RNG and is not compatibility cleanup.

## Reproduce

Run from the application root with Node 24 and Python 3:

```sh
STARDUST_ENGINE_SOURCE=/path/to/trusted/engine.py \
  STARDUST_CAMPAIGN_PROGRESS=1 \
  node --experimental-strip-types --test --test-reporter=tap \
  --test-concurrency=1 tests/engine/*.test.mjs

./node_modules/.bin/tsc --target ES2022 --module ESNext \
  --moduleResolution Bundler --strict --noEmit \
  --allowImportingTsExtensions --lib ES2022,DOM --skipLibCheck \
  lib/game-engine/*.ts
```

Every source-reading oracle uses the explicit `STARDUST_ENGINE_SOURCE` input.
No fixtures are obtained from saves, observations, databases, accounts, or live
services. Campaign records stream through backpressured process pipes and remain
in memory. The normal package has no dependency on another editable TS source
copy. Local TAP logs are ignored by `tests/engine/.gitignore`.

## Completed checks

On 2026-10-07 UTC, with Node 24.19.0 and Python 3.12.14:

- Strict TypeScript checking passed for all canonical engine modules
- JavaScript syntax checking and Python AST parsing passed for all engine tests
  and source oracles
- Native integration matched 1,015 synthetic cases and 4,157 commands against both
  Python references, comparing complete private state, RNG, public
  observations, command results, exact errors, and immutable caller inputs
- State validation covered 291 accepted synthetic states and 286 mutation cases,
  including strictly rejected historical versions/provenance and malformed
  pending trades/history
- CPython RNG checks covered 56 streams, 9,246 exact operations, state checkpoints,
  and 700-value continuations per stream
- Domain/initial-sequence checks passed 61 tests: 14 domain states, 40 initial
  sequences, and 122 budget derivations. Initialization tests call the same
  `drawDemand` and `drawVisitors` helpers as the hosted runtime

Each complete aggregate took approximately 280 seconds on this environment.
Totals include isolated action cases replayed in full native integration; they
are test counts, not counts of distinct game states or a proof of all-input
equivalence. Both aggregates had zero cancelled or skipped tests.

Numeric differential counts (latest-only):

| Domain | Cases |
| --- | ---: |
| Ties-even rounding | 12,011 |
| Continuous clamp | 2,201 |
| Catalog reference values | 9,216 |
| Public counter ceilings | 82,946 |
| Initial chance, complete asking-price sweeps | 2,049,795 |
| Initial chance, legal boundary probes | 310,463 |
| Final chance, rational price sweeps | 1,155,401 |
| Final chance, extreme safe integers | 2,000 |
| Counter offers with required native budgets | 41,400 |
| Final-offer bounds | 5 |
| Canonical final-price text | 355 |
| Supplied percentile outcomes | 9,900 |

## Campaign gate

All 20 mixed campaigns passed against both references. Eight start with the
normal 260 synthetic credits; twelve are explicitly endowed with
12,000 synthetic credits solely to exercise long collection/upgrade trajectories.
All subsequent inventory, repairs, trades, replacements, upgrades, and days are
command-generated. Actions are selected using public observations.

The gate compares every private field and RNG word, all 39 public fields, exact
rejection messages, JSON rehydration, one-revision commits, deterministic-action
RNG invariance, day-seven settlement/explicit continuation, and repeated reads.
It includes all thirteen mutation commands, all six read commands, both suppliers,
six daily events, pending trade locks, all percentile outcomes, 60-row retention,
and later milestones. The measured totals are identical for both references:

- 11,303 commands: 6,033 successful mutations and 5,270 rejected attempts
- 420 day closures, eight missed and twelve won first weeks, and 20 explicit
  continuations without a second maintenance charge
- 143,838 repeated read calls, including 9,702 expected read errors
- 145,459 complete direct/read public-observation comparisons; successful
  mutation response observations and command results were compared separately
- 28 failed and 274 successful repairs, 23 better collection replacements,
  766 named-buyer and 391 walk-in attempts
- 53 final offers: 33 ordinary successes, 18 ordinary failures, one miracle,
  and one fumble; 32 day closures automatically declined pending bargains
- All six events and later milestones through `voyage_2` in the four longest
  synthetic-funded campaigns

Successful mutation counts:

| Command | Count |
| --- | ---: |
| buy | 1,132 |
| open | 1,131 |
| price | 1,345 |
| repair | 302 |
| collect | 219 |
| replace-collection | 23 |
| upgrade | 142 |
| sell | 1,157 |
| accept | 60 |
| decline | 29 |
| offer | 53 |
| endday | 420 |
| continue | 20 |

## Known numeric limitation

One test is deliberately marked TODO, not passed: JavaScript `Math.log2` and the
CPython platform libm disagree at 8 of 4,656 engineered arbitrary-reference float
boundaries. A one-ulp difference changes a floored threshold by one. None of these
8 references is reachable in the enumerated current item-reference domain
(3,840,000 base/condition/demand combinations). Lawful valuation sweeps and boundary
probes pass. No epsilon adjustment, probability rule change, or RNG change masks
the discrepancy. This establishes the tested domain, not universal mathematical
or cross-platform equivalence.

## References and limits

- Original trusted v9 engine SHA-256:
  `53bd47db6dbaa80db3ea1f0e8adedc9dc61fcd28d4bbbf342e6a5c1e853d0dff`
- Cleaned latest-only Python engine SHA-256:
  `1c527d26473dadd2e586a2d9d1b928ed2c562d930c4e4263b713c035de5ccbe9`

These are bounded deterministic synthetic checks. They do not validate hosted
storage/CAS/idempotence, authorization, transport, UI, production deployment, or
real-save outcomes; those belong to the application integration gates. External
save import is unsupported. Native numeric fields must be safe JavaScript
integers; object validation cannot distinguish JSON tokens `1` and `1.0` after
parsing. No live state was read or changed for this work.
