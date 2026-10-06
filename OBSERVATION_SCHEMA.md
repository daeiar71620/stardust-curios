# Public observation schema, version 6

The spectator and AI player consume only the public observation or CLI output. They must never open the private save. All actions go through `engine.py` / `GameStore.execute`.

V6 retains v5’s two independent decimal D10s for a roll-low percentile result. These are simplified CoC-inspired house rules, not the complete official rules. V3/v4 D20 and v5 percentile records may coexist with new v6 records; inspect each record's `rules_version` rather than interpreting all history using the observation's top-level version.


## V6 public buyer capacity and counter eligibility

`walkins`: `{daily_limit:1,used:0|1,remaining:0|1,budget_range:[60,120],min_condition:45,visit_rule}`. The exact ordinary budget is private and committed for the day. A valid initial ordinary `sell` consumes the one visit on every result, including refusal or fumble. Validation failures consume nothing. Named customers retain their separate daily cap. Only entering a new day replenishes capacity; reads, repricing, changing items, preview, reload and declined counters do not.

Each public item adds `public_reference` and `sale_options`. Reference is the catalog reference adjusted for condition/demand and rounded to an integer, never the hidden per-item base.

`sale_options[]`: `{customer_id,customer_name,available,counter_eligible,reasons,public_reference,max_counter_ask,budget_range,min_condition,preference_match,condition_met,ask,warning}`. The ordinary buyer has null `customer_id`; named entries cover today's listed visitors.

- `available` concerns today's transaction locks, active phase, at least 1 energy, uncollected item and remaining buyer capacity
- `counter_eligible` is a separate deterministic condition: ask≥2; ask≤floor(public_reference×5/4); ask≤public budget upper bound; condition at least the buyer minimum; named buyer category matches
- `max_counter_ask` is min(floor(public_reference×5/4),public budget upper bound). It does not by itself imply condition/category eligibility
- `reasons` explains failed public eligibility checks, including exact public thresholds. No private affordability input is read. Empty means qualification passes
- Eligibility is **not** initial exact success probability or exact personal affordability, and does not revoke already pending imported quotes
- Normal initial failure gives a binding counter only when qualified. Otherwise the buyer leaves, no revenue, item remains and both daily opportunities are spent
- 01 succeeds at any legal price regardless of eligibility/budget;100 always ends the meeting; ordinary initial success is still possible when counter-ineligible

`trade_rules` additionally includes `counter_rule,walkin_daily_limit,walkin_budget_range,walkin_min_condition`. `market` and `visitors` responses include `walkins`; `inspect` includes the item's new public fields. The spectator must consume these fields instead of deriving hidden initial probability.

`management_upgrade`: null for native v6, or `{from_version:1..5,source_day,source_phase,source_roll_seq,walkins_used_on_import}` for copy imports. It preserves the v6 boundary separately from `engine_upgrade`, which still describes earlier D20 boundaries. Old records at or below this sequence keep their original rules, and new records are v6. V5 records and pending quotes are never relabeled to pretend they used v6 eligibility. `walkins_used_on_import` is 0 or 1; any already recorded ordinary initial attempt today consumes today's v6 capacity. V1/v2 lack complete sold-visit records, so copy import conservatively marks today's slot used. Next day restores it.

Old pending quotes are grandfathered even when their ask, category or condition fails today's v6 eligibility. Context budget for old ordinary pending quotes remains null, preserving the original contract. Their final preview and outcome use the unchanged public premium formula without a new hidden budget veto.

## Shop and campaign fields

- `version`: 6
- `revision`: monotonic integer for successful mutations; reads and previews do not increment it
- `day`: ongoing day count; `total_days:7` is the introductory checkpoint, not a campaign cutoff
- `credits`, `reputation`, `energy`, `max_energy`, `capacity`, `operating_cost`
- `phase`: `active`, `week_summary` (paused after day 7), or `lost` (bankruptcy)
- `goal`: introductory legacy summary `{credits:650,collection:2}`
- `inventory`, `collection`: public item arrays
- `crates`: sealed `{id,supplier,name}` records only
- Public item fields: `id,name,rarity,kind,color,condition,value_estimate:[low,high],repair_cost,price,origin,description,collected,sale_attempted_today,repair_attempted_today,repairs_remaining,negotiating`
- `suppliers`: `[{id,name,cost,stock,description}]`; costs already reflect today's event
- `upgrades`: `{workbench:0..3,shelf:0..3,display:0..3}`
- `upgrade_costs`: matching keys with the next price or null
- `upgrade_details`: `[{id,name,level,max_level:3,next_cost,effect,next_effect}]`; `next_cost` and `next_effect` are null at maximum level
- `demand`: `{label,kind,multiplier}`
- `last_event`: `{seq,type,title,text,item}`; item is public or null. An event that performed a trade roll also contains `roll`, the complete corresponding public roll record. Non-roll events omit it
- `log`: up to 60 recent `{day,text}` records

`campaign`:

- `title`: first-week or ongoing label
- `stage_index`: number of earned milestones
- `first_week_result`: `pending`, `won`, or `missed`; later completion does not rewrite it
- `completed_milestones`: `[{id,title,day}]`
- `next_milestone`: `{id,title,description,goals:[{key,label,current,target,met}],ready}`
- `can_continue`: true only in `week_summary`
- `continue_command`: `continue` or null
- `unlimited`: true

`daily_event`: `{id,title,description,sale_multiplier,salvage_discount,repair_discount,cost_delta,energy_delta}`. Public event descriptions state current percentage-point bonuses. `sale_multiplier` remains legacy metadata and is not an extra multiplier in v5/v6 trade calculations.

`visitors`: `[{id,name,role,preferred_kind,preference_label,min_condition,budget_range:[low,high],premium,status,attempted_today}]`. Status is `waiting`, `negotiating`, `bought`, or `left`. Exact budget is private. `premium` remains legacy metadata and is not a v5/v6 calculation input; it is distinct from a final-roll record's relative price `premium`.

`codex`: `{total,discovered,collected,entries:[{name,rarity,kind,description,discovered,collected}]}`. All 24 catalog descriptions are public. Sealed cargo is never exposed.

`collection_sets`: `[{id,name,description,required:3,current,completed,perk}]`. `current` counts distinct collected types of that kind.

`stats`: `{crates_opened,sales_count,gross_earnings,days_traded}`. V1 imports start statistics from import; v2/v3/v4 imports preserve existing statistics.

`migration`: null or `{from_version:1,source_day,source_phase,stats_scope:'since_import'}`. This v1 provenance may remain through later upgrades. It never contains source paths or private data.

`engine_upgrade`: null or `{from_version:2|3|4,source_day,source_phase}`. Imports from v3/v4 additionally include `source_roll_seq` and `legacy_v3_roll_seq`, the boundaries for retained legacy records. See copy-import semantics below.

Optional `persistence_warning`: a committed action or public-projection refresh encountered a filesystem synchronization/write problem. An already committed action remains successful; do not retry that action automatically. Once the filesystem is writable, `status` reconstructs the public projection.

## V5/v6 percentile roll records

- `last_roll`: null before any rolls, otherwise the newest public record
- `roll_history`: the latest 60 records, in chronological order; reads never add or reroll them
- `last_event.roll`, when present, matches the latest history record
- An acceptance or decline adds no roll. `last_roll` can therefore be historical; use `last_event` and `negotiation` for current transaction state and actual accepted-counteroffer income

Every v5/v6 record has exactly these fields:

`{id,day,item_id,item_name,customer_id,customer_name,stage,die,tens,ones,roll,modifier,modifiers,threshold,probability,base_chance,premium,rules_version,counter_offer,success,outcome,price,explanation}`

- `id`: monotonically increasing roll-record ID; `day`: day on which it was committed
- `item_id`, `item_name`, `customer_name`: public identity strings; `customer_id` is null for an ordinary traveler
- `stage`: `initial` or `final`
- `die:'D100'`: notation for the combined percentile result; the engine makes two independent D10 draws
- `tens`: numeric 0,10,20,…,90; render it as 00,10,…,90
- `ones`: numeric 0–9
- `roll`: integer 1–100, computed as `tens + ones`, except a sum of zero is 100. Render 1–9 as 01–09, and 100 as 100
- `modifier`: sum of `modifiers:[{label,value}]`; both use percentage points. The modifier changes the threshold/base rate, not the dice result
- `threshold`: integer 1–99; roll-low comparison is `roll <= threshold`, with 01 always successful and 100 always unsuccessful
- `probability`: `threshold / 100`, the exact success probability for that committed roll, already including 01
- `base_chance`: final base rate 1–99, or null for an initial roll
- `premium`: `(price - counter_offer) / counter_offer` for a final roll, or null for an initial roll
- `rules_version`: 6 for new rolls; retained v5 records remain 5
- `counter_offer`: the forfeited binding quote for a final roll, otherwise null
- `success`: boolean
- `outcome`: `miracle` for 01, `fumble` for 100, otherwise `success` or `failure`
- `price`: the legal asking price for this roll. A later accepted quote has its own sale event/statistics; never use the earlier failed roll's asking price as accepted-sale revenue
- `explanation`: public rule/result text

There are no v5/v6 `face`, `total`, `target`, `base_target`, or `rejection_penalty` fields. Do not synthesize a D20 total or target from percentile records.

### Threshold formulas and privacy

Define `clamp(x) = max(1,min(99,x))` and `bonus = modifier` in percentage points.

Initial threshold:

`clamp(floor(60 + bonus - 50 * log2(price / reference)))`

Here `reference` is the item's private actual reference: `hidden_base_value * (0.30 + 0.007 * condition) * demand_multiplier`, using the day's multiplier only for the matching kind and 1 otherwise. A named customer's initial price above their exact private budget sets the threshold to 1. Ordinary travelers have no named-customer budget gate. The 01 exception still settles at the full legal price, including 9999.

The formula is public; its private inputs and exact pre-roll initial probability are not. A committed initial record publishes its realized threshold and probability. Public item estimates instead use the catalog's nominal reference value in place of the hidden per-item base; they are not exact trade inputs.

Final threshold:

`base = clamp(70 + bonus)`

`threshold = clamp(floor(base * counter_offer / (2 * price - counter_offer)))`

Equivalently, the unclamped quotient is `base / (1 + 2 * premium)`. The implementation uses integer arithmetic for the final division. First clamp the base, then floor the quotient, then clamp the threshold. There is no fixed +3 rejection penalty, no floor derived from the initial roll, and no further hidden valuation or budget gate. The committed counteroffer already reflects affordability; final previews and final rolls share exactly the same public-input calculation.

For `counter_offer:150` and `bonus:0`, `base_chance:70`: final prices 165, 225, and 9998 have thresholds 58, 35, and 1 respectively, provided each price is below the original price. At threshold 1, only 01 succeeds; at threshold 99, only 100 fails.

Native bonus components, frozen at initial contact:

- Reputation: +5 per 5 reputation, capped at +15
- Display: +5 per level, capped at +15
- Artifact collection set: +5
- Festival: +10; fog: −10
- Named customer category match: +15; mismatch: −10
- Named customer condition expectation met: +5; unmet: −10

Ordinary travelers get no category/condition-expectation components. Zero-valued components are omitted. Bonuses affect initial thresholds or final base rates; after final premium scaling and clamps, +5 base points need not mean +5 final probability points.

## One-round negotiation

`negotiation` is null or:

`{item_id,item_name,customer_id,customer_name,original_price,counter_offer,rules_version,origin_rules_version,remaining_offers:1,final_offer_energy:1,final_offer_bounds:{min,max,available},accept_income,final_failure_income:0,preview,commands:{accept,decline,preview,offer}}`

- Native v6 initial ordinary failures (02–99 above threshold) create a pending negotiation only when the public counter eligibility checks pass; otherwise the buyer leaves. 100 ends the meeting immediately; 01 succeeds immediately
- `rules_version:6` governs the remaining final attempt. `origin_rules_version` is 6 for native play or 3/4/5 for an imported pending negotiation
- `counter_offer` is one binding quote, not the exact private budget
- Bounds are `min = counter_offer + 1`, `max = original_price - 1`, and `available = min <= max`
- `accept ITEM`: settles the fixed quote with no energy cost and no dice
- `decline ITEM`: ends the meeting with no energy cost and no dice
- `offer ITEM PRICE`: validates the strict integer inequality `counter_offer < PRICE < original_price`, spends 1 energy, and performs exactly one further two-D10 percentile check
- Either final result ends that item's/customer's meeting for the day. Failure earns zero and permanently withdraws the old quote; it cannot then be accepted
- Only one negotiation can be pending shop-wide. Other sales must wait; unrelated permitted shop actions remain possible. The pending item's price/repair/collect actions are blocked
- Frozen bonus inputs prevent upgrades or other intervening progress from changing the current final rate
- Zero energy permits accept, decline, and preview, but not a committed final offer
- `endday` automatically declines pending negotiations, including when the day ends in bankruptcy or first-week summary

No legal intermediate integer means `available:false` and `preview:null`; only accept/decline remain. Preview selection never changes the binding quote or bounds.

## Exact, read-only final-price preview

`preview-offer ITEM PRICE` returns a complete observation with `negotiation.preview` set to that legal candidate (`suggested:false`) and refreshes only the public projection. It does not write the private save, change revision/resources/locks/pending state, or draw/advance RNG. Invalid candidates leave private and public data files unchanged. Later status/actions restore the default candidate (`counter_offer+1`, `suggested:true`). A preview is not a commitment.

Preview fields:

- `price`: candidate final price
- `basis:'public_counter'`
- `base_chance`: clamped final base rate
- `threshold`: exact final success threshold, 1–99
- `probability`: `threshold / 100`
- `premium`: `(price - counter_offer) / counter_offer`
- `modifier`, `modifiers`: frozen public percentage-point bonuses
- `critical_probability:0.01`, `fumble_probability:0.01`
- `energy_cost:1`: cost of committing, not previewing
- `accept_income`: binding quote; `success_income`: candidate price; `failure_income:0`
- `warning`: public risk explanation
- `suggested`: true for the default candidate, false for an explicitly previewed candidate

This is an exact final probability, not a range of hidden-input estimates. It uses only the public counteroffer and frozen public bonuses and exposes no new private reference/budget inputs. There are no `base_target_range`, `target_range`, `required_raw_range`, or `rejection_penalty` fields in the v5/v6 preview.

## Trade rules object

`trade_rules` contains:

- `die:'D100'`, `dice:['D10 tens 00–90','D10 ones 0–9']`
- `direction:'roll_low'`, `zero_zero:100`, `critical:1`, `fumble:100`
- `critical_rule`: 01 overrides ordinary willingness/budget and settles the legal price
- `fumble_rule`: 100 immediately ends that day's meeting for the item
- `house_rules`: explicitly labels the simplified CoC-inspired, non-official rule set
- `max_rolls_per_item_day:2`: at most two percentile checks, each containing two physical dice results
- `price_limit:9999`, `final_offer_energy:1`
- `final_offer_rule:'counter_offer < price < original_price'`
- `final_chance_formula`: the final clamp/floor formula documented above
- `initial_chance_formula`: the initial formula and above-budget override documented above
- `final_budget_rule`: no additional hidden final budget gate
- `endday`: automatically decline unfinished bargaining
- `miracle_probability:0.01`

The critical chance remains 1% per percentile check. A native v6 initial ask of 9999 fails counter eligibility and therefore receives no retry after ordinary failure: it has one 1% miracle chance. Previously promised imported quotes remain actionable under their grandfathered contract. This deliberately retained high-price miracle is not an exploit-proof economic design.

## Legacy D20 history and copy imports

Old records retain their original D20 results and outcomes. Each uses:

`{id,day,item_id,item_name,customer_id,customer_name,stage,face,modifier,modifiers,total,target,success,outcome,price,explanation,base_target,rejection_penalty,rules_version,counter_offer}`

- `rules_version:3` or `4`; label these records as historical D20
- `face`: 1–20; `total = face + modifier`; old modifier units remain D20 points
- Natural 20 succeeds despite target/budget; natural 1 fails; other faces require `total >= target`
- `base_target`: 2–99. V4 final rolls have `rejection_penalty:3` and `target = base_target + 3`; other legacy rolls have penalty 0
- Imported v3 history receives compatibility annotations `base_target:target`, `rejection_penalty:0`, `rules_version:3`, and `counter_offer:null`; original dice/target/outcome are not rejudged
- `counter_offer` is retained for v4 final records; otherwise null
- No percentile dice or thresholds are invented for legacy history

`import-v1 SOURCE`, `import-v2 SOURCE`, `import-v3 SOURCE`, `import-v4 SOURCE`, and `import-v5 SOURCE` require a complete private source save and a new unused `--save DESTINATION`. The engine refuses in-place import, an existing destination, or an existing destination observation. The matching frozen validator checks the source. Import does not rewrite the source or its observation, play a turn, continue the week, charge maintenance, reroll, or advance the source game RNG. Merely opening an old private save does not auto-upgrade it.

- V1 import supplies campaign fields, limited reconstructed discoveries, and new statistics; independently seeded import visitors do not advance the preserved game RNG
- V2 import preserves resources, committed cargo, customer budgets, used attempts, and statistics; roll history starts empty
- V3/v4 import preserves committed resources, history, binding pending quote, locks, and RNG. Current event descriptions retain their v5 percentage-point wording
- For v3/v4 imports, `source_roll_seq` is the final legacy record ID at import. `legacy_v3_roll_seq` is the end of the retained v3 prefix (equal to the source sequence for a direct v3 import; zero when a v4 source has no v3 prefix). Through the v5 boundary, later old IDs use v5; new v6 IDs follow the management boundary described above
- A pending legacy quote remains immediately acceptable/declinable for free. For a v3/v4 D20 origin, its frozen modifier and each component are multiplied by five to obtain percentage points for the remaining v6 attempt; old history itself retains its original units. The new pending object explicitly reports `rules_version:6` and its initial `origin_rules_version`
- The remaining final attempt must satisfy v5's strict lower-than-initial price boundary and uses the exact v5 final formula. Even a pending v3 negotiation does not authorize a same-price retry

Public v3/v4/v5 observations remain read-only historical inputs for the spectator. A v6 observation may show an old `last_roll`, a v6 pending preview, and mixed D20/percentile history without altering any past result.

## CLI and privacy contract

`status`, `market`, `inspect`, `codex`, and `visitors` are read-only with respect to the private state; they may repair the public projection. `status` and `preview-offer` return complete observations, while `market`, `inspect`, `codex`, and `visitors` return their documented public subsets. Mutating commands return a complete observation after commit.

`continue` is available only after the day-7 summary and does not charge day 7 again. `new` refuses an existing save. `restart --confirm` explicitly resets the selected shop; it is not an item reroll.

Never expose `rng`, `base_value`, `cargo`, exact `budget`, private reference inputs, private serial counters, or private catalog IDs in public payloads. Public initial prices and value estimates use nominal catalog reference values, not the hidden per-item base roll. Public event/roll IDs are intentional identifiers, not private item/RNG counters. Diagnostic tools and deterministic tests may inspect synthetic fixtures; an AI playing an actual user game may not inspect private saves.

`dice-fixtures/` contains synthetic public examples such as `critical01`, `fumble100`, `ordinary-success`, `negotiating`, `preview`, `final-success`, `final-failure`, `final-critical01`, `final-fumble100`, `accepted`, `declined`, `legacy-v3`, and `mixed-v4-v5`. They do not represent a played user game or prove UI/test verification by themselves.
