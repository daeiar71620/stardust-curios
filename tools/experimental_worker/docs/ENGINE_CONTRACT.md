# Stardust v9 Python → isolated Worker port contract

Status: source-derived contract and synthetic references, not a full-port certification. No actual save, observation, session, or production deployment was read or changed for this document. A future real-save import, service activation, or MCP grant is a separate explicit action. This is a small private AI-played game; one state owner and a clear action/projection API are sufficient. No multi-user business architecture is required.

## 1. Reference and evidence

Reference package: `stardust-curios-v9-current-shop`, inspected 2026-10-06 UTC. Sources of truth are `engine.py`, its frozen `_legacy_v*.py` validators/converters, `OBSERVATION_SCHEMA.md`, and the test methods inventoried in `ACTION_COVERAGE.md`. The source engine is standard-library Python; the GUI is a separate Tk/Pillow spectator. The web-sync helpers are a separate adapter layer.

Pinned `engine.py` SHA-256:

`53bd47db6dbaa80db3ea1f0e8adedc9dc61fcd28d4bbbf342e6a5c1e853d0dff`

Synthetic reference probes in this document used CPython 3.12.14. No complete regression suite was run by the documentation worker; the 465-test pass is an upstream report, while the 465-method inventory was independently counted from source. Future differential runs must record Python version, engine digest, fixture generator, commands, and the exact TS revision.

Key source anchors:

| Source | Contract |
|---|---|
| `engine.py:23–144` | Constants, ordered catalog/customers/events, CLI help |
| `engine.py:156–267` | RNG restore, derived walk-in budget, public eligibility |
| `engine.py:267–414` | Daily RNG order, milestones, new state |
| `engine.py:415–542` | Values, costs, explicit public projection |
| `engine.py:543–733` | Preconditions, cargo generation, negotiation and dice |
| `engine.py:734–973` | Pure-on-copy command transition |
| `engine.py:976–1000` | Atomic file replacement and commit-warning boundary |
| `engine.py:1003–1348` | Current save/trade/history validation |
| `engine.py:1351–1429` | Explicit copy-only migrations |
| `engine.py:1432–1570` | Store ownership, command arity, revisions, CLI errors |

## 2. Smallest honest milestone and API boundary

First core milestone: execute only `buy`, `open`, and `price` against explicitly synthetic, native-v9 state; return the next private state internally and a full public observation separately. Reproduce their dependency functions and post-action milestone behavior. Include deterministic test-only seeded initialization if implemented. Do not expose seeded `new`/reroll controls through a player API.

The owner-selected initial input envelope is narrower than all valid v9 states: native synthetic no-trade snapshots only, no pending negotiation, no retained roll history, and all five migration/upgrade metadata fields null. Accept synthetic first_week_result/milestones so long-game projection and milestone-event timing can still be compared without implementing day advancement. Preserve all 39 public keys, with negotiation/last_roll/provenance null and roll_history empty. Nonzero roll_seq, an event.roll without history, or negotiating visitors without pending are not valid no-trade inputs and must fail closed. The exact validator acceptance set must be tested rather than inferred from this description.

This milestone is not a playable full port or a save importer. Its separately authorized deployed synthetic route is a transport smoke, not proof of full rule/state equivalence. Unsupported commands return an explicit not_ported-style result without mutating input, consuming RNG, or silently dispatching to Python. Unsupported imported/history-state shapes must be rejected before a partial transition, not “upgraded” by defaults.

Recommended minimal separations (names are illustrative, not an implementation claim):

- `project(privateState) -> publicObservation`, pure and defensive
- `transition(privateState, command, args: string[]) -> nextPrivateState`, copy-on-write, exact game semantics, no filesystem/network
- Store/API adapter validates request shape, authorizes action, serializes one game's transactions, owns exactly one revision increment, and returns only public output
- Test harness alone can construct seeded states and inspect internal next-state/RNG equality

Keep a stable typed action API so a future Windows shell, phone view, or MCP adapter need not know about Python file locks. Do not embed private state in browser bundles, HTML, logs, action error responses, or public fixtures copied from a real game. Public catalog data is already shipped source, but the runtime discovery projection must still not reveal unopened identities.

## 3. JSON and state contract

### 3.1 Types and normalization

The engine writes UTF-8 JSON with `ensure_ascii=False`, two-space indentation, trailing newline, and `allow_nan=False`. Compare decoded structures for semantic differential tests; do not require the entire Python file's whitespace/key ordering for a Worker store. Two byte-level contracts remain important: failed/read-only operations must not rewrite private bytes in the Python adapter, and the compact RNG serialization is a hash input (section 4).

- JSON objects, arrays, strings, booleans, numbers, and explicit null retain their distinctions. Do not substitute missing/undefined for an emitted null
- Canonical counters/prices/condition/rule versions are integers. Python `type(x) is int` excludes booleans and rejects `1.0`; `Number.isInteger(JSON.parse('1.0'))` cannot distinguish that lexical case. Full corrupt-save parity requires an explicit raw-JSON numeric policy or a token-preserving parser; a typed synthetic-state port must state that limit
- Many primary counters have an upper bound of 10^12, safely representable as JS integers. `roll_seq`, stats values, and some derived long-campaign targets do not have that same bound in the Python validator. Do not claim arbitrary Python-int JSON compatibility without deciding how values beyond `Number.MAX_SAFE_INTEGER` are handled
- A 128-bit random seed cannot travel as a JS Number. Keep it as bigint internally, a decimal string in a test envelope, or bytes. Serialized MT words are ordinary safe unsigned 32-bit integers
- Array order is part of the contract: catalog, visitors, modifiers, inventory, collection, discoveries, supplier lists, goals, logs, history, and category lists. Preserve Python list/dict insertion order used to build them. Never sort before RNG selection or projection
- `args` is an array of strings. Numbers/booleans in place of CLI strings are rejected. Price text is accepted only when Python `str(int(raw)) == raw.strip()` and range/bounds pass: `" 12 "` is accepted; `"012"`, `"+12"`, `"12.0"`, exponent notation, and alternate digit glyphs are rejected. Exact Python `.strip()` includes some control whitespace outside JavaScript `.trim()`; test it or document a deliberately narrower API boundary
- Item/crate IDs are case-insensitive on lookup via uppercase; visitor IDs lowercase; supplier and upgrade keys are case-sensitive. Generated IDs use minimum width 3 (`I001`, `C001`, later `I1000`), not a three-digit cap
- Float fields must retain finite binary64 values and evaluation order; JSON infinity/NaN is not a valid saved result

A schema describing generated native states is not identical to every object accepted by Python's validator. For example top-level extra keys are not globally forbidden, `version` uses equality rather than `type is int`, and some record fields are checked more tightly than others. Do not silently expand a “full compatibility” claim from typed fixtures to arbitrary uploaded JSON.

### 3.2 Complete native private-state top level

Fresh `new_state(seed)` yields revision 0; committing `new` through `GameStore.execute` yields revision 1. The following is the full generated key inventory, not a redacted public response:

| Keys | Shape / initial value |
|---|---|
| `version, revision, day` | 9, 0, 1 |
| `credits, reputation, energy, phase` | 260, 0, 12, `active` |
| `inventory, crates, collection` | Empty ordered arrays |
| `upgrades` | `{workbench:0,shelf:0,display:0}` |
| `demand` | `{label,kind,multiplier}` from first two RNG selections |
| `supplier_stock` | `{salvage:4,curated:2}` |
| `next_crate,next_item` | 1, 1 |
| `event_seq,last_event,log` | Start at 0/null/[] then the start event makes sequence 1 and one log entry |
| `daily_event` | Deep copy of the first event `calm` |
| `visitors` | Three ordered sampled profiles, each with exact private budget |
| `discovered` | [] |
| `first_week_result,milestones` | `pending`, [] |
| `stats` | `{crates_opened:0,sales_count:0,gross_earnings:0,days_traded:0}` |
| `migration,engine_upgrade,management_upgrade,collection_upgrade,budget_upgrade` | Each null |
| `negotiation,roll_seq,roll_history` | null, 0, [] |
| `walkins` | `{day:1,used:0,budget:<derived integer 60..120>}` |
| `rng` | Python Random state, described below |

Core validator bounds: `revision/credits` 0..10^12; `day/next_crate/next_item/event_seq` 1..10^12; reputation 0..99; energy 0..17 and not above computed maximum. Phases are `active`, `week_summary`, `lost`. Upgrades have exactly the three keys, integer 0..3. Supplier stock has exactly two keys and respects current set-adjusted limits. Inventory plus crates cannot exceed capacity. Discovery IDs are a unique list from the catalog.

### 3.3 Private item, crate, visitor, and event

Cargo contains exactly the following generated fields:

`catalog_id,name,rarity,kind,base_value,condition,description,origin,collected,repairs,last_sale_day,last_repair_day`

`base_value` is a hidden integer; condition is 5..100 once validated; rarity is common/rare/legendary; kinds are tool/artifact/bot/plant/signal. Catalog name/rarity/kind/description match the catalog row exactly. `origin` is one of the two supplier display names. Cargo initially has `collected:false`, `repairs:0`, and day locks 0. Opened items additionally have `id` and integer `price` 1..9999. Collection items have `collected:true` and distinct catalog identities. Items retain hidden valuation and locks through replacement.

Crate: `{id,supplier,name,cargo}`. Cargo is generated at purchase, never at opening. Public crates omit `cargo` entirely.

Visitor: `{id,name,role,preferred_kind,preference_label,min_condition,budget_range:[low,high],premium:1.25,status,budget}`. IDs are unique and from the fixed eight profiles. Status is waiting/negotiating/bought/left. Exactly three or four visitors appear. `premium:1.25` is retained legacy metadata, not an extra current-sale multiplier. The private integer budget lies in that profile's range.

Event: `{seq,type,title,text,item}` plus optional `roll` only for a dice action. `_event` increments event_seq, snapshots `_public_item` at that instant, stores last_event, appends `{day,text}`, and trims logs to the last 60. It does not increment revision. The event item is a historical public snapshot and need not equal the later live item projection after milestones change. Milestone logs do not replace last_event or increment event_seq. Preserve exact Chinese strings for full output parity.

### 3.4 Pending trade and history

Pending private negotiation has exactly:

`item_id,item_name,customer_id,customer_name,original_price,counter_offer,day,context,initial_roll_id,rules_version,origin_rules_version`

Context is exactly `{reference,budget,modifiers,modifier}`. Reference is hidden actual value; budget is exact private budget for native trades, or null for grandfathered ordinary v3–v5 negotiations. Modifiers are ordered `{label,value}` rows and their sum. Context freezes before initial dice and does not change when display/upgrades/other items change. Pending `rules_version` is 9; origin is 3,4,5,6,9. The initial row must be the latest failed initial roll with matching identity and committed terms.

Percentile roll fields, exactly:

`id,day,item_id,item_name,customer_id,customer_name,stage,die,tens,ones,roll,modifier,modifiers,threshold,probability,base_chance,premium,rules_version,counter_offer,success,outcome,price,explanation`

Initial `base_chance/premium/counter_offer` are null. Final base is 1..99; premium is `(price-counter)/counter`; probability is threshold/100. `die` is D100; tens is 0,10,...90, ones 0..9; sum zero represents 100. Keep at most 60 chronological rows; IDs are absolute and `len(history) == min(roll_seq,60)`. A retained first row may be a final roll whose initial row was evicted. `last_event.roll` equals the newest history row whenever present.

Inherited D20 rows use the same common identity/result fields but replace D100-specific fields with `face,total,target,base_target,rejection_penalty`. Do not relabel or recalculate them as current percentile rolls.

## 4. Python RNG portability and exact serialization

Canonical native state from `random.Random.getstate()` is a three-element tuple which JSON turns into arrays:

`[3, [word0, word1, ... word623, index], gauss_next]`

There are 624 unsigned 32-bit MT19937 words plus index 0..624 (625 elements in the middle array). `gauss_next` is null for native game generation because no game action calls `gauss`; Python may carry a cached value in imported valid RNG state. `_tuple_tree` recursively converts every JSON list to a tuple before `setstate`. Full import compatibility must decide whether to implement all Python-accepted historical RNG state variants, including state version 2, or explicitly reject unsupported ones. Never treat state version 3 as the game protocol version 9.

Required operation compatibility is broader than the same MT generator: `random`, `getrandbits`, rejection-based `randint/_randbelow`, `choice`, `choices(weights)`, `sample`, `uniform`, integer/bytes seeding, and getstate/setstate must consume exactly the same stream. A decimal D10 is `randint(0,9)`, not `floor(random()*10)`. Each D100 calls randint twice, but may consume more than two MT words due to rejection. `random()` consumes two words for a 53-bit float.

Action RNG order:

1. Fresh state: choose kind from ordered `tool,artifact,bot,plant,signal`; choose multiplier `[1.25,1.35,1.45]`; sample three customer profiles in their catalog order; draw budgets in sample-result order; derive walk-in budget without touching the main RNG
2. Start day: increment day; choose event from EVENTS excluding the immediately prior event (preserve remaining order); choose demand kind and multiplier; recompute stock; sample 3 or 4 visitors based on display level>=2; draw their budgets; set energy; derive walk-in budget
3. Buy: weighted rarity via `choices` (`[74,24,2]` salvage or `[28,61,11]` curated), uniform selection among catalog rows of that rarity, uniform(0.92,1.08) hidden base multiplier and Python round, inclusive condition randint(35,88) or randint(48,96)
4. Repair: random() < failure probability `[.24,.14,.07,.03]`; then inclusive randint(3,11) on failure or randint(19,35) on success
5. Sell/final offer: randint(0,9) for tens, then randint(0,9) for ones; no extra willingness/budget roll
6. Open, price, collect, replace, upgrade, accept, decline: no draws. They still restore/store RNG through apply_command. Reads do not even take that path

Walk-in derivation, verbatim bytes contract:

- `material = json.dumps(rng.getstate(), separators=(",", ":")).encode()`
- `digest = SHA256(b"walkin-v6:" + ascii_decimal(day) + b":" + material)`
- `local = random.Random(digest)` (default Python version-2 bytes seed algorithm, not a direct MT integer seed from the hash alone)
- `budget = local.randint(60,120)`

No spaces or newline in material. Native gauss null means JSON.stringify produces compatible numeric-array text if words/index/version are exact. A cached Gaussian or historical state could introduce Python-vs-JS float text differences; do not claim that path without testing it. Even though the game is v9, the literal domain prefix stays `walkin-v6:`.

Synthetic fresh-state reference vectors (after all `new_state` draws, before store revision increment):

| Integer seed (decimal string) | RNG index | compact bytes | SHA-256(compact RNG JSON) | day-1 walk-in budget |
|---|---:|---:|---|---:|
| `0` | 13 | 6723 | `449825d48f60ba23268fdcc59464b73d4e4464db1f3806f23f569f4c3a96ddc1` | 60 |
| `1` | 12 | 6704 | `0674990d2b4e974ddced85e8d7690ba8666c6ee403600ab8365245f197e3aaf4` | 72 |
| `42` | 10 | 6693 | `a0945df2a69aa6780c5669c55919556e2499fe2525614dc8aeda6bcb76dcf19c` | 68 |
| `340282366920938463463374607431768211455` | 18 | 6714 | `878b8bb927a4245fa9b53c3e7bb61e0d84b361538d25b213e4fc3c3de7f492a8` | 72 |

Seed 42 also produces demand tool/1.25, ordered visitors echo budget241, nox budget557, ayu budget172. These are deliberately synthetic hidden values for a test oracle, not any real game's state. Seeding tests must compare complete RNG arrays, not merely these small examples. RNG implementation is owned separately; this document contains no substitute implementation.

## 5. Exact arithmetic and rounding

### 5.1 Values, costs, and non-trade rounding

Let `q = 0.30 + condition * 0.007`; demand multiplier is applied only if item kind matches demand kind.

- Actual reference: hidden base_value * q * demand; preserve left-to-right floating evaluation
- Public raw reference: catalog reference * q * demand, independent of hidden base
- Public integer reference: max(1, Python round(public raw reference))
- Estimate: `[max(1,int(publicRaw*.82)), max(2,ceil(publicRaw*1.20))]`; int truncates toward zero, though valid references are positive
- Initial opened-item price: max(1, Python round(publicRaw*.93))
- Repair cost: max(3, Python round(rarityBase*(1-.18*workbench)) − event repair discount − 4*toolSet); rarityBase 15/28/50
- Daily demand label uses Python round((multiplier−1)*100)

Python `round(x)` is nearest with ties-to-even over the actual binary64 value. JavaScript `Math.round` is not a drop-in replacement. Do not use decimal-string rounding or an arbitrary epsilon to force equality. Preserve ties, negative semantics where a helper is general, and float evaluation order. Source floating constants are part of the contract.

### 5.2 Initial probability, v9 versus historical rules

Only rule versions 5,6,9 are supported by `_initial_chance`; Python requires an actual integer rule version, so 9.0/true/"9" are rejected. Native v9 requires a positive actual integer budget; v5/v6 may have null for an old ordinary customer.

1. `raw = 60 + modifier - 50 * log2(price / reference)`
2. If budget is null, or price <= budget: `threshold = clamp(1,99,floor(raw))`
3. If over budget and historical rule5/6: threshold=1
4. If over budget and rule9: `threshold = clamp(1,99,floor(clamp(1,99,raw) * budget / (2*price-budget)))`

Important: the continuous base is clamped before scaling, and only the final result is floored on the over-budget path. Do not floor the base early. Do not algebraically replace the implementation with `base/(1+2*(price/budget-1))`: cancellation/evaluation changes can move an integer-boundary result. Do not introduce a separate hard budget veto after a successful v9 roll.

With reference=budget=100 and modifier=0: prices 99,100,101,110,150,200,300 produce 60,60,58,44,15,3,1. With reference1000/budget100/modifier=0, price125 yields66, demonstrating continuous-base capping.

CPython `math.log2` and JS `Math.log2` are binary64 operations backed by potentially different libm implementations. A source translation alone does not establish equality at floor boundaries. Differential sweep legal prices1..9999 across all attainable current reference/bonus/budget combinations or a justified exhaustive boundary strategy; any unresolved 1-ULP crossing is a fidelity gap. A numeric-worker Python/V8 comparison has already found an engineered input with reference=145.39725173203104, modifier=0, price=100, budget=120 yielding Python 87 versus JS 86. The numeric worker subsequently enumerated all 3,840,000 validated base/condition/demand reference combinations and found none of the eight divergent engineered references reachable in that domain. This remains an arbitrary-context helper counterexample, not an observed legal-game divergence; the test is retained as an unresolved all-input TODO. It does disprove an unqualified all-input parity claim. Avoid hiding a mismatch with a generic epsilon. The buy/open/price slice does not evaluate initial probability at all: its sale-options projection uses public reference and eligibility only, and its accepted input envelope excludes pending trades/history. This limitation therefore belongs to the future trading gate.

### 5.3 Eligibility, quote, and final probability

Public counter qualification is independent of initial probability:

- ask>=2
- ask<=floor(roundedPublicReference*5/4), with rounding before integer ratio
- ask<=public budget range upper limit
- condition>=buyer minimum (ordinary45)
- named buyer category matches

All failed reasons are emitted in that order. Eligibility does not consult hidden base value or exact budget. Availability separately checks active phase, energy>=1, no pending negotiation, uncollected item, no same-day attempt, and that buyer's capacity.

Binding quote:

`quote = max(1, floor(reference*(.75 + modifier/200)/10)*10)`

If budget is nonnull, cap to `max(1, floor(budget/25)*20)`. Finally return `max(1,min(asking−1,quote))`. Legacy v3/v4 used modifier*.025 instead of modifier/200 before the fivefold bonus conversion.

Final legal price: `counter < price < original`, strict integer. Base=`clamp(1,99,70+modifier)`. Threshold=`clamp(1,99,(base*counter)//(2*price−counter))` using integer floor division. This exact integer rational expression must not be replaced by a rounded floating premium formula. For legal prices/bonuses its intermediate products are safely within JS exact integer range. Success probability is threshold/100, including 01. No extra hidden-budget check. Published premium is still the floating `(price−counter)/counter`; explanation uses Python `.1%` formatting, another text-equivalence boundary.

### 5.4 Modifiers, outcomes, and proceeds

Ordered nonzero percentage-point modifiers: reputation +5*floor(min(rep,15)/5), display +5*level, artifact set+5, festival+10 or fog−10, named preference +15/−10, named condition +5/−10. They affect thresholds, never the dice sum. Daily event `sale_multiplier` and visitor `premium` are inherited display metadata, not additional math.

01 always succeeds at the legal price, including 9999; 100 always fails. Other rolls succeed iff <=threshold. Outcomes are miracle/fumble/success/failure. Settlement adds exact quoted price to credits and gross earnings, increments sales count, removes inventory item, writes that sale price to the item before its event snapshot, sets named buyer bought, and adds capped reputation: legendary2 otherwise1, plus1 if named category matches. Reputation state caps99, but event text uses the computed increment even at cap.

## 6. Exact transition inventory

All ordinary mutations first restore RNG and require active phase except `continue`, which has its own week-summary gate. GameStore validates arity/types before loading, loads/validates state, deep-copies for normal mutations, applies, increments revision once, validates the result, projects, and commits. Errors discard the candidate. Reads and previews do not increment revision or call milestone checks.

| Action and args | Cost / RNG | Required behavior |
|---|---|---|
| `new` | New random seed | Missing-save only; no implicit replacement; fresh revision 1 after store commit |
| `restart --confirm` | New random seed | Exact confirmation flag; preserve previous valid revision then+1; corrupt previous save may reset baseline to0 |
| `buy supplier` | 1 energy, current supplier cost; cargo draws | Known supplier, available stock, space including sealed crates; decrement stock, commit all cargo now, increment crate ID, append crate, buy event |
| `open crateId` | 1 energy; no draws | Find case-insensitive crate; copy cargo, assign next item ID, public-reference-derived initial price, move to inventory, add discovery once, increment crates_opened, reveal event |
| `price itemId text` | Free; no draws | Inventory only; pending target lock; canonical1..9999; set price and emit event even if same price; no reset of daily attempt |
| `repair itemId` | 2 energy, computed cost; random then randint | Cabinet lookup before inventory; pending target lock; condition<100, repairs<2, not repaired today; increment locks, failure max5(before−3..11), success min100(before+19..35+4*workbench); original price unchanged |
| `sell itemId [visitorId]` | 1 energy; two randint calls | Inventory, no pending trade anywhere, unused item/day and buyer; ordinary daily limit 1; freeze context; mark attempt and consume ordinary visit on every valid result; named starts left; success settles,100 closes, ordinary failure quotes only if public eligibility passed |
| `accept itemId` | Free; no draws | Match pending item; close pending, settle fixed counter; legal at zero energy |
| `decline itemId` | Free; no draws | Match pending item; close pending; no refund/reset of locks |
| `offer itemId price` | 1 energy; two randint calls | Match pending, strict bounds; use frozen context; clear pending on either outcome, keep final price even on failure; never third roll or return to old quote |
| `collect itemId` | 1 energy; no draws | Inventory, target unlocked, no duplicate catalog in cabinet; any condition allowed; move and set collected=true; first completed bot set immediately adds1 energy |
| `replace-collection itemId` | 1 energy; no draws | Inventory unlocked, same type in cabinet, strictly better condition; swap in existing array positions, flip collected flags only; preserve both records/locks/price/value; works at full capacity; no repeated set reward |
| `upgrade key` | 2 energy, level cost; no draws | workbench/shelf/display only, max3; shelf adds1 energy immediately; display extra visitor begins next day |
| `endday` | Maintenance; day draws only if advancing | Auto-decline pending first; bankruptcy sets credits0/lost, no new day; otherwise pay and increment days_traded; day 7 pending result checks goals after fee and pauses week_summary; ordinary day calls start_day |
| `continue` | No repeated fee; day draws | week_summary only; active then start_day (day 8), event, save RNG, milestone checks |
| `import-v1`…`import-v6`, `import-v8 source` | No gameplay RNG draws | Copy-only new destination; own validators/converters; preserve source and supported provenance; details in section9 |

Regular buy/open/price/repair/collect/replace/upgrade may occur while another item negotiates. Only mutations of the pending item are locked; every new sell is blocked globally. `price` does not require positive energy. `endday` can occur at zero energy. Read `preview-offer` may show a legal quote without enough execution energy and does not authorize the eventual action.

Read commands and return shape:

- `status`: full observation
- `market`: only revision,day,credits,energy,demand,suppliers,daily_event,visitors,walkins,operating_cost
- `inspect itemId`: matching public inventory or collection item; cannot inspect unopened cargo
- `codex`: codex object
- `visitors`: `{day,visitors,walkins}`
- `preview-offer itemId price`: full observation, with negotiation.preview replaced by exact selected forecast (`suggested:false`); default projection preview uses minimum legal final price and `suggested:true`
- `help`/CLI help flags: text and exit0 without opening a game; handled outside `execute`

Each successful read rebuilds/writes the entire public observation, including preview's selected forecast, but never private state. Market/inspect/codex/visitors return their subset, while the persisted projection is still full. Python CLI success is JSON on stdout; caught GameError/OSError produces `{ok:false,error:<message>}` on stderr with exit2. A Worker adapter can wrap transport status but must preserve the game/result distinction.

## 7. First milestone: buy/open/price dependency and timing checklist

Implementing these three commands faithfully still requires more than a three-branch reducer:

1. `new_state` fixture contract, Python-compatible RNG restore and cargo generation, ordered constants, spend validation, capacity/supplier helpers
2. Reference value/repair cost/public sale eligibility, quality thresholds, replacement/repair advisories, visitors/codex/campaign/sets/trade-rules projection
3. Exact event snapshot and log trimming behavior, plus `_check_milestones` after every successful action
4. Pending-item lock for price, arbitrary-other-negotiation tolerance, active/week-summary/lost rejection, string arity and case behavior
5. Atomic candidate semantics: insufficient money/energy/space or malformed arguments leave original state and full RNG untouched
6. Revision ownership must be explicit. If exported function models `apply_command`, it must not increment; if it models `GameStore.execute`, it must increment once. Differential oracle must compare equivalent layers

Open ordering: spend → copy cargo → assign ID/increment next_item → set price → remove crate/append item → append discovery if new → stats++ → event public snapshot → store RNG → milestone check. A reveal at an earned-stage boundary can have an event item's quality label from the previous stage while the top-level item uses the next stage. Recomputing the event later changes output.

Milestones: return immediately while first_week_result is pending or phase lost. Otherwise check up to `len(MILESTONES)+1 = 5` successive goals; append `{id,title,day}` and a bounded log entry each. Do not award cash, draw RNG, rewrite first_week_result, revoke earned milestones, or loop without this cap. Spending on buy can lower cash; opening/pricing can still trigger previously ready goals in synthetic states, so skipping checks is not generally equivalent.

## 8. Public projection boundary

Full generated observation has 39 top-level keys (excluding optional persistence_warning):

`version,revision,day,total_days,credits,reputation,energy,max_energy,goal,phase,inventory,crates,collection,suppliers,upgrades,demand,last_event,log,capacity,operating_cost,upgrade_costs,upgrade_details,campaign,collection_progress,daily_event,visitors,walkins,codex,collection_sets,stats,migration,engine_upgrade,management_upgrade,collection_upgrade,budget_upgrade,negotiation,last_roll,roll_history,trade_rules`

`persistence_warning` is an optional return-only transport/persistence annotation, not a game field.

Public item keys, exactly for a canonical generated item:

`id,art_id,name,rarity,kind,color,condition,value_estimate,public_reference,sale_options,repair_cost,price,origin,collection_quality,repair,collection_replacement,description,collected,sale_attempted_today,repair_attempted_today,repairs_remaining,negotiating`

Sale options are ordinary first then visitors in their current order, each `{customer_id,customer_name,available,counter_eligible,reasons,public_reference,max_counter_ask,budget_range,min_condition,preference_match,condition_met,ask,warning}`. Condition/reference/price are public; exact budgets are not.

Public visitors retain their profile fields except private budget, and add attempted_today. Walkins contain daily_limit 1,used,remaining,budget_range[60,120],min_condition45,visit_rule; no day/exact-budget echo. Crates contain id/supplier/name only.

Unknown codex entry is exactly `{slot,discovered:false,collected:false}`. Known adds art_id,name,rarity,kind,description. Discovery is union of stored discovered IDs and currently opened inventory/cabinet identities; never scan cargo. Selling never forgets a discovery. Public progress aggregates count opened cabinet identities and categories, without naming unknown candidates.

Public negotiation retains item/buyer identity, original/counter prices, both rule-version labels; adds remaining_offers1, final_offer_energy1, bounds `{min:counter+1,max:original−1,available}`, accept/failure incomes, default minimum-price preview or null, and textual commands. It excludes day, context, and initial_roll_id. Forecast contains exactly price,basis,base_chance,threshold,probability,premium,modifier,modifiers,critical_probability,fumble_probability,energy_cost,accept_income,success_income,failure_income,warning, plus suggested at its embedding site.

Never infer exact initial odds before a roll from public bands. After a committed roll, the threshold and probability are public. `last_roll` may remain an old failed initial row after a free accept; use last_event/stats for actual sale proceeds. Never reinterpret every historical row using top-level version9.

Projection must be pure and defensively copied, including nested histories/modifiers/events. Current source builds whitelisted live items, but deep-copies some event/history/provenance trees; its validator is not a universal recursive secret-key sanitizer for arbitrary maliciously extended JSON. Before an externally supplied save is accepted later, audit that boundary explicitly. Do not claim every arbitrary Python-validator-accepted extension is safe to publish.

## 9. Compatibility and inherited semantics

### 9.1 Campaign/economy retained in v9

Capacity=7+3*shelf. Max energy=12+shelf+botSet+event delta. Maintenance=max(4, 14+event cost delta−4*plantSet). Stock salvage=4+signalSet, curated=2. Costs and catalog are the source constants, not recalibrated port values. All five any-condition 3-distinct-item set perks remain: tool repair −4; artifact chance +5pp; bot energy +1; plant upkeep −4; signal salvage stock +1. Quality themes are a separate milestone requirement.

Milestones preserve stage order: first week credits 650 +2 at 70; neighborhood credits 1400 +5 at 75  +rep 12 +upgrade sum 2 +qualified categories 3; lighthouse credits 2800 +9 at 80  +rep 25  +upgrades 4 +quality themes 1 (no category-count requirement); landmark credits 5000 +15 at 85  +rep 40  +upgrades 6 +all 5 categories +themes 3. Longhaul n: cash 5000+3000*n, count min(24,15+2*n), condition min(90,85+n), rep min(99,40+10*n), all 5 categories, themes min(5,3+n); no new upgrade requirement.

Week7 charges maintenance before checking result, then waits for explicit continue to day 8. Missed goals can be earned later; won/missed history is not rewritten. If maintenance cannot be paid, loss is terminal; exact-fee payment leaving zero can still reach week_summary and continue. Daily events never repeat immediately. Set benefits and goals are not a license to change collection membership order or reward replacement twice.

### 9.2 v8 → v9 is not a relabel

`migrate_v8(source_bytes)` parses and validates with frozen `_legacy_v8`, rejects an existing budget_upgrade key, deep-copies, changes version to9, adds budget_upgrade `{from_version:8,source_day,source_phase,source_roll_seq}`, changes pending.rules_version to9 if pending, then adds one import event/log. It retains collection_upgrade unchanged, so there is no new quality-grace stage. It does not perform gameplay, call start_day, consume RNG, recalculate history, or choose continue. Store layer then increments the inherited revision once and writes the new destination. Source path never enters public metadata.

v8 protocol8 used trade rules6. Old history remains6 or earlier; new rows9. Initial historical thresholds use their original 5/6 hard budget gate when validating a pending quote; final-offer math remains current exact rational. Pending origin label stays original. Accept/decline remain free; a committed older quote is not canceled because current eligibility would deny a fresh quote.

### 9.3 v1–v6 compatibility chain

`engine._migrate` rejects already upgraded collection/budget keys, converts via `_legacy_v6` when source<6, validates with `_legacy_v6`, then adds a one-stage collection grace and budget boundary. There is no import-v7: that release uses private protocol6. Full v1–v6 conversion depends on `_legacy_v5` and older validators; retaining only engine.py is insufficient for exact old-save support.

- v1 supplies missing expanded state, starts import-scoped statistics, derives migration visitors with a separate RNG seeded from SHA256 of the exact source bytes, and distinguishes the old completed-but-missed week from genuine bankruptcy. Formatting the source before hashing changes deterministic visitors
- v2 adds dice/history structures without replaying prior actions
- v3/v4 D20 history remains high-roll, with natural20 success/natural1 failure. Native v4 final rejection penalty is3; v3 historical same-price final can remain valid. Pending D20 modifiers are multiplied by5 for future percentile rules
- v5/v6 percentile records retain their exact digits, results, and rule labels
- Management import tracks whether today's ordinary slot was spent; v1/v2 conservatively set used1 because complete sold-visit history was absent. v3–v5 use retained initial ordinary history. Next-day transition resets it once
- v1–v6 add collection_upgrade `{from_version,source_day,source_phase,legacy_stage_index}`. Grace applies only while completed milestone count equals that immutable index; minimum condition0 and category/theme requirements removed for that one stage. It cannot be granted again through reimport or version relabeling

Absolute history boundaries: old v3 end from engine_upgrade.legacy_v3_roll_seq; D20 end from engine_upgrade.source_roll_seq; v5 end from management_upgrade.source_roll_seq; v6 end from budget_upgrade.source_roll_seq; later rows9. Boundary checks continue to matter after those rows fall out of the 60-row tail. A v6 initial row and v9 final row can be one valid pair; no retroactive replay.

All imports require unused destination save and unused destination projection; source cannot equal either. Public-only observations are not importable saves. Existing targets, unsupported versions, corrupt markers, relabeled future dice, or repeated migration must fail without overwriting source or creating a destination save. Production import remains outside this synthetic milestone.

## 10. Persistence adapter equivalence

Python serializes all commands under one per-save flock. It writes candidate private state first via fsync+atomic replace, then the public projection. If private replacement fails before commit, action fails and old money/RNG/state remain; retry uses the same future roll. If replacement happened but directory fsync failed, result says action committed with a warning. If public projection fails after private commit, do not replay; status repairs the projection. Reads may fail to refresh projection but still return the current true public state plus warning.

A Worker need not emulate POSIX files, but must establish the same observable one-commit boundary with one game's transactional storage/serialization. Keep private state as authority; public projection can be derived. A revision guard or idempotency key is an adapter concern, not another RNG draw or rule revision. The existing Python GameStore has no operation-ID deduplication itself; web_sync adds that separately. Do not promise duplicate network retries are safe until the adapter has tested them.

Required tests before activation: simultaneous competing sells/final offers settle once; rejected or precommit-failed requests preserve all state; ambiguous postcommit response can be resolved without replay; reads do not advance; stale clients cannot overwrite newer state; new/restart/import cannot silently replace a current session. HTTP/MCP authorization and deployment gates remain separate from game-equivalence tests.

## 11. Differential acceptance and unresolved gaps

For every supported synthetic command sequence compare: next canonical private JSON (including all RNG words/index), public observation, event/log/history order, numeric types/values, error behavior, revision layer, and unchanged input. Compare after each step and after serialize/reload, not only final credits. Inject failures at candidate validation and store commit/projection stages once that layer exists. Test both supplier branches, rarity selections, resource/capacity boundaries, both phases, pending locks, discovered/unknown catalog handling, and >60 logs/history.

Explicit unresolved work at documentation time:

- This document does not certify TS implementations, migrated current tests, or any production readiness
- Numeric and RNG kernels require their own differential results; libm boundary equality, percentage-format strings, cached-gauss serialization, historical RNG versions, arbitrary seeds, and beyond-safe-integer saves cannot be assumed
- buy/open/price alone omit repair, trading, cabinet actions, upgrades, day advancement, new/restart persistence, and all imports; post-action milestone checks and campaign projection are still required. The initial no-trade envelope explicitly excludes pending/history/provenance input support
- Full save/trade validation and malicious-publication boundary are not replaced by TypeScript types
- Legacy tests and Pillow render tests need retained-oracle versus adapted-web separation; passing Python tests does not execute TS
- Worker transactional storage, idempotency, mobile UI/API refresh/error behavior, and any live integration remain independent acceptance stages

Use `ACTION_COVERAGE.md` to track the exact 465 reference methods and staged implementation gates. Narrow claims such as “synthetic buy/open/price transitions match these specified oracle cases” are appropriate when demonstrated; “v9 fully ported” is not.
