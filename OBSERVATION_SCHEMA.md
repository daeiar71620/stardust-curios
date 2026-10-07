# Public observation schema, version 10 (standalone Python engine)

`engine.py` is the canonical runtime and persistence entry point. The optional `spectator.py` viewer and AI player consume its public output; no website or plugin is required.

## V10 normal-budget contract

Save/protocol `version` and new transaction `rules_version` are 10. Both named buyers and ordinary travelers have a private daily normal budget: a spending-comfort input, not a hard ability-to-buy cap. Above that budget, initial success decays smoothly by the formula below; within budget, the prior initial probability is unchanged. 01 still succeeds at the legal price and 100 still fails. The public counter-eligibility ceiling remains hard, including `ask <= budget_range[1]`, reference, category and condition constraints. The exact public final-price formula is unchanged, with no second hidden-budget check.

Public `budget_range` fields keep their established names and numeric ranges. They describe normal spending budgets. Do not expose the precise budget or invent an exact initial pre-roll probability from those ranges.

Only native v10 state is supported. `migration`, `engine_upgrade`, `management_upgrade`, `collection_upgrade`, and `budget_upgrade` are required and always null. Any non-null or missing provenance field rejects the private state. They are rejection guards and cannot activate an upgrade path. The public v10 observation has 42 top-level fields, including the explicit protocol version, operating-cost breakdown, and last settlement.

Old-version saves, previously migrated saves, mixed-rule histories and old-origin negotiations are unsupported. There are no import commands or frozen migration modules. Preserve existing files and explicitly use `new` at an unused path when a fresh game is wanted.

## Quality collection contract

Collection quality requirements, target amounts, values, budgets and dice retain their prior mechanics. V10 adds deadlines, recurring facility fees, and focused procurement; these apply only to new v10 saves.

- Stage1: 2 distinct cabinet items at condition >=70
- Stage2: 5 at >=75, across at least 3 qualified categories
- Stage3: 9 at >=80 and at least 1 quality theme; no category-count constraint
- Stage4: 15 at >=85, all 5 qualified categories, at least 3 themes
- Longhaul chapter n: distinct count `min(24,15+2*n)`, condition `min(90,85+n)`, all 5 categories, themes `min(5,3+n)`; original cash `5000+3000*n`, reputation `min(99,40+10*n)` and no new upgrade target
- A quality theme means at least 3 different cabinet catalog types in one category, all meeting the current threshold. Existing any-condition `collection_sets` benefits are unchanged. Earned milestone records never disappear

`collection_progress` is `{personal_count,qualified_count,qualified_categories,quality_themes,min_condition,legacy_grace,categories,requirements,missing}`. `categories` contains only the 5 public categories as `{id,name,qualified_count,theme_complete}`; it never contains candidate/unknown catalog identities. `requirements` is the current stage's collection/category/theme subset as `{key,label,current,target,met}`. `missing` contains textual unmet counts. `legacy_grace` is always false and cannot lower any requirement. Economic requirements remain in campaign goals.

Every opened public item adds:

- `collection_quality:{min_condition,condition_met,counted,reason}`. `counted` requires cabinet membership. The reason explains a known low-condition item's exact gap, and preserves the option to collect it personally
- `repair:{available,reasons,cost,energy_cost:2,command}` for cabinet and inventory items. Normal cost, two lifetime attempts, once per day and failure degradation all apply. This display is advisory; execution revalidates atomically
- `collection_replacement:null` or `{available,reasons,cabinet_item_id,cabinet_condition,energy_cost:1,command}` for an inventory item when a cabinet item has the same catalog type

`replace-collection INVENTORY_ID` requires strictly higher condition and an unlocked item. It swaps membership one-for-one, including a full inventory. Both identities, hidden base values, prices, origin, repair counts and sale/repair day locks survive; only `collected` flags change. No RNG advance, cash or reputation reward, or repeated set activation. `repair` resolves cabinet items explicitly; `sell` and `price` remain inventory-only. The replacement public event type is `replace_collection`.

`collection_upgrade` must be null. Native first-week settlement uses the current quality requirements; earned milestones and the recorded first-week result remain stable during later play.

The codex entry schema stays unchanged: only discovered entries contain identity fields, and quality details derive from opened public items. Public aggregates never consult unopened cargo.

The spectator and AI player consume only the public observation or CLI output. They must never open the private save. All actions go through `engine.py` / `GameStore.execute`.

Native v10 uses two independent decimal D10s for a roll-low percentile result. These are simplified CoC-inspired house rules, not the complete official rules. Every retained roll and every pending negotiation has rules version 10.


## Public buyer capacity and counter eligibility

`walkins`: `{daily_limit:1,used:0|1,remaining:0|1,budget_range:[60,120],min_condition:45,visit_rule}`. The exact ordinary normal budget is private and committed for the day. A valid initial ordinary `sell` consumes the one visit on every result, including refusal or fumble. Validation failures consume nothing. Named customers retain their separate daily cap. Only entering a new day replenishes capacity; reads, repricing, changing items, preview, reload and declined counters do not.

Each public item adds `public_reference` and `sale_options`. Reference is the catalog reference adjusted for condition/demand and rounded to an integer, never the hidden per-item base.

`sale_options[]`: `{customer_id,customer_name,available,counter_eligible,reasons,public_reference,max_counter_ask,budget_range,min_condition,preference_match,condition_met,ask,warning}`. The ordinary buyer has null `customer_id`; named entries cover today's listed visitors.

- `available` concerns today's transaction locks, active phase, at least 1 energy, uncollected item and remaining buyer capacity
- `counter_eligible` is a separate deterministic condition: ask≥2; ask≤floor(public_reference×5/4); ask≤public normal-budget range upper bound; condition at least the buyer minimum; named buyer category matches
- `max_counter_ask` is min(floor(public_reference×5/4),public normal-budget range upper bound). It does not by itself imply condition/category eligibility
- `reasons` explains failed public eligibility checks, including exact public thresholds. No private spending-comfort input is read. Empty means qualification passes
- Eligibility is **not** initial exact success probability or a promise of initial success
- Normal initial failure gives a binding counter only when qualified. Otherwise the buyer leaves, no revenue, item remains and both daily opportunities are spent
- 01 succeeds at any legal price regardless of eligibility/budget;100 always ends the meeting; ordinary initial success is still possible when counter-ineligible

`trade_rules` additionally includes `counter_rule,walkin_daily_limit,walkin_budget_range,walkin_min_condition`. `market` and `visitors` responses include `walkins`; `inspect` includes the item's new public fields. The spectator must consume these fields instead of deriving hidden initial probability.

## Shop and campaign fields

- `version`: 10; `protocol_version`: 10
- `revision`: monotonic integer for successful mutations; reads and previews do not increment it
- `day`: ongoing day count; `total_days:7` is the introductory checkpoint, not a campaign cutoff
- `credits`, `reputation`, `energy`, `max_energy`, `capacity`, `operating_cost`
- `phase`: `active`, `week_summary` (paused after day 7), or `lost` (bankruptcy)
- `goal`: introductory summary `{credits:650,collection:2}`
- `inventory`, `collection`: public item arrays
- `crates`: sealed `{id,supplier,name}` records; a focused crate also includes only the already-selected `requested_kind` and `requested_kind_label`, never its cargo identity, rarity, condition or value
- Public item fields: `id,art_id,name,rarity,kind,color,condition,value_estimate:[low,high],repair_cost,price,origin,description,collected,sale_attempted_today,repair_attempted_today,repairs_remaining,negotiating`
- `suppliers`: `[{id,name,cost,stock,description,remaining,energy_cost,unlock_day,unlocked,daily_limit}]`; costs reflect today's event. Focused additionally includes `categories:[{id,name}]` using public category labels
- `upgrades`: `{workbench:0..3,shelf:0..3,display:0..3}`
- `upgrade_costs`: matching keys with the next price or null
- `upgrade_details`: `[{id,name,level,max_level:3,next_cost,effect,next_effect,daily_upkeep,daily_upkeep_from_day8,next_daily_upkeep,next_daily_upkeep_from_day8,upkeep_unlock_day}]`; next-level fields are null at maximum level. Day1–7 current upkeep is zero while future day8 costs remain visible
- `demand`: `{label,kind,multiplier}`
- `last_event`: `{seq,type,title,text,item}`; item is public or null. An event that performed a trade roll also contains `roll`, the complete corresponding public roll record. Non-roll events omit it
- `log`: up to 60 recent `{day,text}` records

`campaign`:

- `title`: first-week or ongoing label
- `stage_index`: number of earned milestones
- `first_week_result`: `pending`, `won`, or `missed`; later completion does not rewrite it
- `completed_milestones`: `[{id,title,day}]`
- `next_milestone`: `{id,title,description,goals:[{key,label,current,target,met}],ready,min_condition,legacy_grace,nominal_due_day,effective_due_day,unlocked_day,days_remaining,overdue_days,missed_day,overdue_surcharge}`. Intraday `ready` is progress, not an award; cash is tested after closing payment
- `deadline_history`: activated stages in order, each `{id,title,nominal_due_day,effective_due_day,unlocked_day,missed_day,completed_day,status}`; status is `active`, `missed`, `completed`, or `completed_late`
- `settlement_rule`: public explanation of payment-first settlement and non-stacking late fees
- `can_continue`: true only in `week_summary`
- `continue_command`: `continue` or null
- `unlimited`: true

`daily_event`: `{id,title,description,sale_multiplier,salvage_discount,repair_discount,cost_delta,energy_delta}`. Public event descriptions state current percentage-point bonuses. `sale_multiplier` is public metadata and is not an extra multiplier in native v10 trade calculations.

`visitors`: `[{id,name,role,preferred_kind,preference_label,min_condition,budget_range:[low,high],premium,status,attempted_today}]`. Status is `waiting`, `negotiating`, `bought`, or `left`. Exact normal budget is private; its range is spending comfort, not a hard purchase cap. `premium` is public metadata and is not a native v10 calculation input; it is distinct from a final-roll record's relative price `premium`.

`codex`: `{total,discovered,collected,entries:[...]}`. Unseen identities are withheld by the engine itself. Every entry has a stable, non-semantic 1-based `slot`:

- Undiscovered: exactly `{slot,discovered:false,collected:false}`. No name, semantic ID, art ID, rarity, kind, description, shape hint or item-specific requirement is emitted
- Discovered: `{slot,art_id,name,rarity,kind,description,discovered:true,collected}`. `art_id` identifies the original illustration and is public only after discovery
- Buying a sealed crate does not discover its cargo. Opening it records discovery before revealing the item and its event. Sold items stay discovered; collection status remains independent
- Inventory, collection and public item events may contain `art_id`, because those items have already been opened.
- Collection-set descriptions disclose category/count/perk only; they do not list unknown members
- The viewer redacts undiscovered entries and refuses unsupported observation versions. Unknown illustrations are identical regardless of hidden kind, rarity or name

Save `version` and public `protocol_version` are 10. `status` refreshes a stale current-version public file without changing the private save. Sealed cargo remains private.

`collection_sets`: `[{id,name,description,required:3,current,completed,perk}]`. `current` counts distinct collected types of that kind.

`stats`: `{crates_opened,sales_count,gross_earnings,days_traded}` for this native game.

Optional `persistence_warning`: a committed action or public-projection refresh encountered a filesystem synchronization/write problem. An already committed action remains successful; do not retry that action automatically. Once the filesystem is writable, `status` reconstructs the public projection.

## Deadline, upkeep and settlement contract

Nominal due days are 7,14,28,42, then56 and +14 for subsequent voyages. The first stage starts on day1 with due7. A newly unlocked later stage at closure day D has effective due `max(nominal_due_day,D+7)`. Completion and missed-deadline history are durable; missing or premature missed markers are rejected as corrupted state, never silently repaired; there is no loss merely for being late. Only inability to pay closing costs causes bankruptcy.

The current active stage's surcharge is zero through day7; afterward it is `min(6,2*max(0,day-effective_due_day))`. Due-day closure has no late charge. Only one active stage contributes; completion clears its future charge and does not back-charge newly unlocked stages or create interest/debt. A missed deadline is recorded when a closing leaves the stage unfinished on its due date. Multiple already-qualified stages may complete at the same paid closure, each retaining its own history and next-stage grace.

`operating_cost_breakdown` is `{base,event_delta,plant_discount,base_after_modifiers,facility_upkeep,facility_upkeep_from_day8,facility_upkeep_unlock_day,overdue_surcharge,total}`. Base is14; `base_after_modifiers=max(4,base+event_delta-plant_discount)`. Plant discount is0 or4. Current facility fees are zero before day8. From day8 choose one value for each facility's current level: workbench `[0,0,1,3]`, shelf `[0,1,2,4]`, display `[0,1,3,5]`; sum those values, not every past level. `total` equals modified base plus facility upkeep plus active overdue surcharge, and matches `operating_cost`.

Closing automatically declines pending negotiation, freezes the shown cost, pays it once, then tests goals using post-payment cash, records any missed active deadline, and advances the day. Day7 pauses at `week_summary`; `continue` starts day8 without another payment. Ordinary intraday mutations and reads cannot award stages. Earned milestones are not revoked later.

`last_settlement` is null initially, otherwise `{day,paid,breakdown,credits_after_payment}`. Breakdown is the exact historical charged/attempted quote, not recalculated with next-day weather or changed facilities. Bankruptcy records `paid:false` and zero remaining credits; it is not a successful charge or an accrued debt.

## Focused procurement

`buy focused KIND` unlocks on day8, costs155 credits and1 energy, and uses its own single daily stock. `KIND` is one of tool/artifact/bot/plant/signal. Other suppliers still require exactly one `buy` argument and retain their existing costs, stock and energy.

The focused draw first uses curated rarity weights28/61/11, then chooses uniformly among items of the requested category and that rarity. Condition remains48–96. It does not prefer undiscovered IDs, promise a new entry, raise rare odds, or expose sealed outcomes. The category is chosen and cargo committed at purchase. Invalid arguments, unavailable stock, insufficient cash/energy, read operations, opening and process restart cannot replace that sealed draw.

## Native v10 percentile roll records

- `last_roll`: null before any rolls, otherwise the newest public record
- `roll_history`: the latest 60 records, in chronological order; reads never add or reroll them
- `last_event.roll`, when present, matches the latest history record
- An acceptance or decline adds no roll. `last_roll` can therefore be historical; use `last_event` and `negotiation` for current transaction state and actual accepted-counteroffer income

Every native v10 record has exactly these fields:

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
- `rules_version`: always 10
- `counter_offer`: the forfeited binding quote for a final roll, otherwise null
- `success`: boolean
- `outcome`: `miracle` for 01, `fumble` for 100, otherwise `success` or `failure`
- `price`: the legal asking price for this roll. A later accepted quote has its own sale event/statistics; never use the earlier failed roll's asking price as accepted-sale revenue
- `explanation`: public rule/result text

There are no native v10 `face`, `total`, `target`, `base_target`, or `rejection_penalty` fields. Do not synthesize a D20 total or target from percentile records.

### Threshold formulas and privacy

Define `clamp(x) = max(1,min(99,x))` and `bonus = modifier` in percentage points.

V9 initial threshold:

```text
raw = 60 + bonus - 50 * log2(price / reference)
base = clamp(raw)
excess = max(0, price / budget - 1)
threshold = clamp(floor(base / (1 + 2 * excess)))
```

Clamp `base` before applying the excess factor; floor only after division, then clamp the final result to 1–99. `budget` is the buyer's private normal spending comfort. For either buyer type, `price <= budget` reproduces the prior within-budget result exactly; above budget, there is no one-coin cliff to threshold 1. Higher prices gradually reduce the threshold, with a floor of 1.

Pure formula examples with `reference=budget=100`, `bonus=0`: prices 99/100/101/110/150/200/300 yield thresholds 60/60/58/44/15/3/1. They are illustrative inputs, not forecasts for any actual public item.

Here `reference` is the item's private actual reference: `hidden_base_value * (0.30 + 0.007 * condition) * demand_multiplier`, using the day's multiplier only for the matching kind and 1 otherwise. The ordinary traveler's exact daily budget is committed privately within the public 60–120 range. The 01 exception settles at the full legal price, including 9999.

The formula is public; its private inputs and exact pre-roll initial probability are not. A committed initial record publishes its realized threshold and probability. Public item estimates instead use the catalog's nominal reference value in place of the hidden per-item base; they are not exact trade inputs.

Final threshold:

`base = clamp(70 + bonus)`

`threshold = clamp(floor(base * counter_offer / (2 * price - counter_offer)))`

Equivalently, the unclamped quotient is `base / (1 + 2 * premium)`. The implementation uses integer arithmetic for the final division. First clamp the base, then floor the quotient, then clamp the threshold. There is no fixed +3 rejection penalty, no floor derived from the initial roll, and no further hidden valuation or budget gate. The committed counteroffer already reflects normal spending willingness; final previews and final rolls share exactly the same public-input calculation.

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

- Native v10 initial ordinary failures (02–99 above threshold) create a pending negotiation only when the public counter eligibility checks pass; otherwise the buyer leaves. 100 ends the meeting immediately; 01 succeeds immediately
- `rules_version:10` governs the remaining final attempt. `origin_rules_version` is always 10
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

This is an exact final probability, not a range of hidden-input estimates. It uses only the public counteroffer and frozen public bonuses and exposes no new private reference/budget inputs. There are no `base_target_range`, `target_range`, `required_raw_range`, or `rejection_penalty` fields in the native v10 preview.

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
- `initial_chance_formula`: the initial clamped-base, smooth over-budget formula documented above
- `initial_budget_rule`: normal spending comfort with smooth initial decline above it; no exact pre-roll initial forecast
- `final_budget_rule`: no additional hidden final budget gate
- `endday`: automatically decline unfinished bargaining
- `miracle_probability:0.01`

The critical chance remains 1% per percentile check. A native v10 initial ask of 9999 fails counter eligibility and therefore receives no retry after ordinary failure: it has one 1% miracle chance. This deliberately retained high-price miracle is not an exploit-proof economic design.

## CLI and privacy contract

Invoke one command at a time as `python3 engine.py --save PATH COMMAND [ARGS]`, then inspect its public result before choosing the next action. Place `--save` before the command. Omission selects `save.json` beside `engine.py`, independent of the current working directory. Relative custom paths are resolved against the current working directory.

The resolved default save path maps to `observation.json` beside `engine.py`, including when supplied explicitly through `--save`. Every other save path maps to `<stem>.observation.json` in its own directory. In particular, a `save.json` in another directory maps to `save.observation.json`, not `observation.json`. Pass the matching public path to `spectator.py --observation PATH`.

`status`, `market`, `inspect`, `codex`, and `visitors` are read-only with respect to the private state; they may repair the public projection. `status` and `preview-offer` return complete observations, while `market`, `inspect`, `codex`, and `visitors` return their documented public subsets. Mutating commands return a complete observation after commit.

`continue` is available only after the day-7 summary and does not charge day 7 again. `new` refuses an existing save. `restart --confirm` explicitly resets the selected shop; it is not an item reroll.

The CLI has no action-ID deduplication or idempotency keys. File locking serializes operations but does not make repeat submissions safe. If completion is ambiguous, do not blindly repeat a mutating command: run `status` on the same save and reconcile the prior public `revision`, `last_event`, `log`, resources and relevant inventory/negotiation state. A revision increase alone does not identify the committed action. If public evidence cannot resolve the outcome, stop mutations and report the uncertainty. `persistence_warning` may accompany an already committed private save; resolve filesystem issues and use `status` to repair its public projection.

Never expose `rng`, `base_value`, `cargo`, exact `budget`, private reference inputs, private serial counters, or private catalog IDs in public payloads. Public initial prices and value estimates use nominal catalog reference values, not the hidden per-item base roll. Public event/roll IDs are intentional identifiers, not private item/RNG counters. Diagnostic tools and deterministic tests may inspect synthetic fixtures; an AI playing an actual user game may not inspect private saves.

Automated tests generate synthetic input in memory or temporary directories and clean it up afterward. Generated observations, playthroughs, screenshots and saves are not distributed. The optional balance_audit.py uses an explicit public baseline source and predeclared synthetic seeds for paired policy comparisons; its policy reads only public observations, and it never reads an existing game save.
