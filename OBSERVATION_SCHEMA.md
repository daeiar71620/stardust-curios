# Public observation schema, version 3

The spectator and AI player consume only `observation.json` or JSON returned by the CLI. They must never open the private save. All actions go through `engine.py` / `GameStore.execute`.

## Compatibility fields

- `version`: 3; `revision`: monotonic integer for successful mutations
- `day`: ongoing day count; `total_days`: 7 means the introductory first-week checkpoint, not a campaign cutoff
- `credits`, `reputation`, `energy`, `max_energy`, `capacity`, `operating_cost`
- `phase`: `active`, `week_summary` (paused after day 7), or `lost` (bankruptcy)
- `goal`: first-week legacy summary `{credits:650, collection:2}`
- `inventory`, `collection`: public item arrays; `crates`: sealed `{id,supplier,name}` only
- Item fields: `id,name,rarity,kind,color,condition,value_estimate:[low,high],repair_cost,price,origin,description,collected,sale_attempted_today,repair_attempted_today,repairs_remaining,negotiating`
- `suppliers`: `id,name,cost,stock,description`, costs already reflect today's event
- `upgrades`: `{workbench:0..3,shelf:0..3,display:0..3}`
- `upgrade_costs`: matching keys with next price or null
- `demand`: `{label,kind,multiplier}`
- `last_event`: `{seq,type,title,text,item}`; item is public or null
- `log`: recent `{day,text}` records, up to 60

## New fields

`campaign`:
- `title`: first-week or ongoing label
- `stage_index`: number of earned milestones
- `first_week_result`: `pending`, `won`, `missed`; later completion does not rewrite this
- `completed_milestones`: `[{id,title,day}]`
- `next_milestone`: `{id,title,description,goals:[{key,label,current,target,met}],ready}`
- `can_continue`: true only in `week_summary`
- `continue_command`: `continue` or null
- `unlimited`: true

`daily_event`: `{id,title,description,sale_multiplier,salvage_discount,repair_discount,cost_delta,energy_delta}`. Modifiers are public rules, not hidden rolls.

`visitors`: `[{id,name,role,preferred_kind,preference_label,min_condition,budget_range:[low,high],premium,status,attempted_today}]`. Status is `waiting`, `negotiating`, `bought`, or `left`. Exact budget is private.

`codex`: `{total,discovered,collected,entries:[{name,rarity,kind,description,discovered,collected}]}`. All 24 catalog descriptions are public. Whether a sealed crate contains one is never exposed.

`collection_sets`: `[{id,name,description,required:3,current,completed,perk}]`. `current` is the number of distinct collected types of that kind.

`upgrade_details`: `[{id,name,level,max_level:3,next_cost,effect,next_effect}]`. Last two next fields are null at maximum level.

`stats`: `{crates_opened,sales_count,gross_earnings,days_traded}`. v1 imported games count only since import; v2 upgrades preserve existing statistics.

`migration`: null, or `{from_version:1,source_day,source_phase,stats_scope:'since_import'}`. Never includes source paths or data.

Optional `persistence_warning`: returned when an action has committed but synchronization/projection has a filesystem problem. Treat the returned action as successful; never retry the same action automatically. `status` repairs a stale projection once the filesystem is writable again.

## CLI additions

- `codex`, `visitors`: read only; do not advance RNG or turns
- `sell ITEM [VISITOR]`: omitted visitor uses an ordinary traveler; a named visitor has one attempt per day
- `upgrade display`; every upgrade now has three levels
- `continue`: only after the day-7 summary, no repeated day-7 charge
- `import-v1 SOURCE`: only into an unused `--save DESTINATION`, never in place

`status`, `market`, `inspect`, `codex`, `visitors` may repair the public projection but never rewrite private state.

Never add `rng`, `base_value`, `cargo`, exact `budget`, private serial counters, or private catalog IDs to any public payload. Public value ranges and initial price use nominal reference values, not the hidden per-item base roll. Diagnostic tools and deterministic tests may inspect synthetic private fixtures; an AI running the actual game may not.


## D20 and one-round bargaining (v3)

- `last_roll`: null before any dice; otherwise the newest complete public roll record
- `roll_history`: the latest 60 records, in chronological order; reads never add or reroll them
- Each record is `{id,day,item_id,item_name,customer_id,customer_name,stage,face,modifier,modifiers,total,target,success,outcome,price,explanation}`
  - `id` monotonically increases; `stage` is `initial` or `final`
  - `face` is the actual independently generated engine D20 result, 1–20
  - `modifier` is the sum of `modifiers:[{label,value}]`; `total = face + modifier`
  - `target` is a public integer difficulty (2–99), calculated from price, condition, demand, hidden reference and budget constraints. It is a coarse difficulty band, not an exact hidden valuation/budget
  - `success`: boolean; `outcome`: `miracle`, `success`, `failure`, or `fumble`
  - Natural 20 succeeds even below the target and beyond the customer's normal budget; natural 1 always fails and ends the meeting. Otherwise total must reach target
  - `price` is that roll's asking price, never a future random number. Actual accepted-counteroffer revenue is in the later sale event/statistics
  - `customer_id` is null for ordinary travelers
- `negotiation`: null, or `{item_id,item_name,customer_id,customer_name,original_price,counter_offer,remaining_offers:1,final_offer_energy:1,commands:{accept,decline,offer}}`
  - Only initial `failure` (faces 2–19) creates a pending negotiation
  - `counter_offer` is the customer's one binding quote, not their exact budget
  - `accept ITEM` settles that quote without energy or dice
  - `decline ITEM` closes it without energy or dice
  - `offer ITEM PRICE` spends 1 energy, validates integer 1–original_price inclusive, and rolls exactly once more. Either result ends today's item/customer meeting
  - Only one negotiation can be pending shop-wide. Other sales must wait; other unrelated shop actions remain possible. The pending item's price/repair/collect are blocked. Frozen judgement inputs prevent upgrading during a conversation from changing its final roll
  - `endday` automatically declines pending negotiations, even if the day ends in bankruptcy or first-week summary
- `last_event.type` additionally allows `negotiation`; events that rolled a die include optional `roll` with the same record. Non-roll events omit it; `last_roll` remains historical and is not rerolled
- `trade_rules`: `{die:'D20',natural_20,natural_1,max_rolls_per_item_day:2,price_limit:9999,final_offer_energy:1,endday,miracle_probability:0.05}`
- `engine_upgrade`: null, or `{from_version:2,source_day,source_phase}`; no source path/private data
- `import-v2 SOURCE`: validates frozen v2 data, copies to an unused new destination, preserves committed RNG/assets/customer budgets/used attempts and existing statistics; no gameplay is run. Legacy event descriptions are updated to D20 rule wording

Compatibility note: `daily_event.sale_multiplier` and visitor `premium` remain as legacy metadata, not v3 calculation inputs. Actual D20 bonuses are shown in `roll.modifiers`, event descriptions and upgrade effects. Target difficulty replaces continuous willingness sampling. Public fixture JSON files under `dice-fixtures/` are synthetic test examples only and do not represent a played user game.
