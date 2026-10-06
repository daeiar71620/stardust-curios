# Stardust v9 reference coverage and staged port gates

Status: all 465 root-suite Python test methods are inventoried below, with proposed TS/differential gates. This is a coverage plan, not 465 ported or passing TS tests. No real save, observation, user data, or production service was used to make it. The bounded first milestone is synthetic `buy`/`open`/`price` plus their complete public projection within the selected native-v9/no-trade input envelope.

Owner-confirmed initial envelope: reject pending negotiations, nonempty roll history, and nonnull migration/engine_upgrade/management_upgrade/collection_upgrade/budget_upgrade. Keep all 39 public top-level fields; excluded structures are explicitly null or empty in accepted fixtures. Support synthetic first_week_result/milestones for ready-stage tests. Also reject inconsistent no-trade shapes such as roll_seq>0, last_event.roll without history, or a negotiating visitor without pending. All unimplemented commands are explicit not_ported; there is no Python fallback. This restriction is an honest staged boundary, not an import implementation.

Reference is the pinned package and engine digest in `ENGINE_CONTRACT.md`. Inventory was independently derived from Python ASTs on 2026-10-06 UTC; every method below has its source line. The documentation worker did not rerun the whole Python suite. `PERFORMANCE_REPORT.md` records an upstream 465/465 game-suite pass; that report is not a TS execution result.

## 1. What the number 465 actually includes

| Reference target | Methods | Meaning |
|---|---:|---|
| Current `engine` (v9) | 215 | Current behavior, projection, store, validation and compatibility; some module names retain older release suffixes |
| Frozen legacy engines | 126 | 74 D20/v4/history tests and 52 v5 percentile tests; intentionally obsolete rules remain an oracle for old records/imports |
| Python spectator/Pillow | 124 | 66 general,17 customer,12 catalog,17 collection,12 budget viewer methods; neither TS-engine nor browser-render tests |
| Total root methods | 465 | Disjoint source inventory, not a claim of complete mathematical or runtime coverage |

Separate packaged helper tests under `tools/web_sync/tests` are not part of 465. The final performance report records 61 helper tests plus 10 frontend and 4 activation-SQL tests, bringing that separate reported integration total to 540. Those remain separate surfaces and are not automatically satisfied by a new Worker reducer or deployed synthetic route.

## 2. Staged gates

| Gate | Required scope and evidence | Allowed claim after a demonstrated pass |
|---|---|---|
| G0: primitives/oracle | CPython-compatible RNG operations/state/seed envelope; ties-even rounding; numeric formulas and type/serialization policy; exact synthetic oracle comparisons, including known limitations | Named tested primitive cases match the pinned Python oracle |
| G1: first synthetic core | Native synthetic buy/open/price; full projection; immutable candidate; exact event/log/revision layer; post-command milestone checks; matrix below, compare every field after each step | These three actions and the accepted synthetic-state domain match the specified differential cases |
| G2: remaining native game | Repair, sell/accept/decline/offer/preview, collect/replace, upgrades, day/week/continue/loss, initialization/restart semantics; deterministic chains and error branches | Listed native-v9 action cases are covered; no automatic legacy/store/deployment claim |
| G3: validation/compatibility | Full supported save validation and copy-only imports1–6,8; absolute history boundaries, frozen old outcomes, quote origins and immutable one-stage grace; malformed input failure | Exact named import/validation families match; requires separate permission before any actual migration |
| G4: store/API/commit | Serialized mutations, read purity, revision ownership, commit/projection failure distinction, idempotent external retry semantics, new/restart/import safeguards; fault and concurrency tests | Listed storage/transport failure modes established on the selected adapter |
| G5: phone/web viewer | Adapt public-only UI behavior, stale refresh, detail paging/close/back/repeated actions, secret-field redaction, unknown-art consistency, historical labels; browser-specific assertions/screens | Tested phone/web UI paths verified, without pretending Pillow pixels were ported |

Gate tags in the method inventory can overlap: a single original method may exercise multiple concerns. A tag identifies relevant assertions to re-express, not that the entire original Python test runs unchanged on an earlier partial TS engine. The disjoint215/126/124 counts are by actual reference target; do not sum overlapping gate tags as additional tests.

Keep frozen 126 methods against their frozen Python modules to establish legacy reference integrity. They must not be mechanically pointed at v9: e.g. natural20/D20, hard over-budget veto, old fixed final penalty, unlimited ordinary visits, and historic equal-price final rules differ intentionally. G3 uses their outputs/history/commitments when testing the current importer, rather than enabling legacy gameplay in the Worker.

The124 spectator methods require explicit adaptation. Read-only public projection and labeling assertions are reusable; Tk window methods, Pillow drawing, hit testing, font/wrapping and filesystem-reader assertions are not equivalent to a mobile web render merely because JSON matches.

## 3. Immediate G1 acceptance matrix

All fixtures must be explicitly generated from public source with fixed documented seeds or constructed synthetic records; label them synthetic. A full-save JSON fixture is an internal test input, never the HTTP/public response. No current private game should be read, sampled, exported, replayed, or migrated to produce these cases.

For each case compare a pinned Python oracle and TS at the same layer: either apply_command before revision ownership, or a store-style wrapper that increments once. Compare full next private state (including all 625 internal RNG entries), full public observation, error class/message where intended, all ordered arrays, and byte/structural preservation of the input. Equality of a few balance numbers is insufficient. Rehydrate through JSON and repeat read/projection to catch representation or alias bugs.

| Case | Required fixture/action and assertions |
|---|---|
| G1-01 seeded baseline | At least seeds 0, 1, 42 and a 128-bit integer above JS safe range; compare native state, demand, ordered visitor budgets, derived walk-in budget, start event, revision 0 versus committed revision 1; native main state cache null |
| G1-02 buy sequence | Both suppliers across synthetic seeds covering all three rarity branches; exact weighted draw/selection/uniform/condition order, hidden cargo, money/energy/stock, C IDs, event and complete next RNG |
| G1-03 buy modifiers | Every event's supplier cost; signal set salvage stock; shelf capacities; filled inventory+crates; passing and failing resource boundaries; no hidden crate discovery or catalog/story output |
| G1-04 ID and order | C999→C1000 and I999→I1000; remove middle crate, append item, leave unrelated ordering/IDs unchanged; lower-case item/crate IDs allowed, supplier case remains exact |
| G1-05 open each identity | Construct synthetic committed cargo for each of24 catalog types and representative conditions; open computes public-reference-based price, adds exactly one discovery and one stat, costs1 energy, consumes zero RNG draws; sealed cargo removed only after success |
| G1-06 existing discovery | Already-known item, known item later sold, duplicate inventory identity, cabinet identity plus missing discovery list: discovery union/fallback and counts match; sealed copy alone never discovers or changes cabinet progress |
| G1-07 price boundaries | 1,9999, same current price and zero-energy repricing all commit correct event/revision without RNG draw; Python whitespace acceptance; invalid zero/negative/10000, floats, leading zero,+sign, exponent, alternate digits, nonstring/missing/extra args reject atomically |
| G1-08 locks and phases | In the selected initial envelope, every pending-negotiation input fails closed before any command. Reserve pending-target lock versus unrelated-item allowance for envelope expansion (Python permits buy/open/price on unrelated items). Within accepted inputs, active-only mutations reject week_summary/lost unchanged |
| G1-09 failed commands | Unknown supplier/ID/command, no stock, exactly-full shelf, insufficient credits/energy, malformed args, cabinet-only price lookup; error order matches source for supported inputs; no changed counters, logs, event or RNG |
| G1-10 numeric boundaries | Public reference rounds before5/4 ceiling; appraisal endpoints truncate/ceil; initial price and repair-cost ties-even; demand matching versus nonmatching; change only hidden base/exact budget and prove unrolled public item unchanged |
| G1-11 buyer projection | Ordinary first then each visitor; buyer statuses, already attempted item/day, zero energy, pending global lock, collection flag; availability separate from public counter eligibility and all reasons in source order; no initial forecast |
| G1-12 item projections | Inventory and cabinet forms, condition 69/70 and every stage threshold, repairs 0/1/2 and repaired-today, perfect condition, insufficient resources, strictly better/equal/worse replacement; nullable replacement; command strings and arrays match |
| G1-13 milestone timing | First-week pending skips checks even when ready; post-week price or open on ready synthetic state awards stage(s); event snapshot uses pre-check quality label while top-level item/campaign use post-check threshold; event_seq unaffected by milestone logs |
| G1-14 milestone bounds | Already-earned titles survive spending on buy; maximum 5 cascaded checks per command; longhaul count 24 / quality 90 / themes 5 caps; lighthouse no category goal; exact target ordering/labels/missing requirements; no RNG/cash reward |
| G1-15 history/event retention | Initial envelope requires roll_seq=0, empty history and no event.roll; outputs retain last_roll:null, roll_history:[], negotiation:null. New price/reveal events omit roll; truncate logs at 60 including milestone logs; preserve historical nontrade event item snapshots until replaced. Historical dice pass-through is a deferred G3/projection-extension case, not claimed for this slice |
| G1-16 deep-copy isolation | Mutate returned inventory, sale options, campaign goals, history modifiers, event item, visitor ranges and provenance; original private input unchanged; repeated projections deterministic and do not advance RNG |
| G1-17 explicit accepted domain | Reject every nonnull negotiation/provenance input and nonempty history, plus inconsistent no-trade counters/events/statuses, before transition. Do not emit null/empty defaults that silently erase incoming data. Allow synthetic current milestones/first-week states to exercise projection and post-action checks |
| G1-18 unsupported actions | Every not-yet-implemented mutation/read/import rejects clearly without side effects or fallback; UI/API action whitelist agrees with reducer; seeded restart remains test-only |

Start with the synthetic baseline/buy/open/price chain, then add the accepted-domain cases above. Passing only the first few cases is a useful small slice, but must be reported as that slice. A successful deployed phone action or Site/D1/MCP round trip establishes that route; it does not replace G1 differential evidence or authorize importing the real game.

## 4. Complete public-field checklist for G1

Exact native observation has 39 top-level keys, plus optional return-only persistence_warning. Assert key sets as well as values; missing null fields or added secret keys both fail. The full projection schema below also records future shapes: the current initial envelope returns negotiation/last_roll/all five provenance fields as null and history as empty; their populated branches are deferred and must not be counted as covered merely because the schema is documented. Source is engine.observation and its helpers; full definitions and formulas are in ENGINE_CONTRACT.md.

| Public branch | Keys and nested expectations |
|---|---|
| Scalars | version,revision,day,total_days,credits,reputation,energy,max_energy,phase,capacity,operating_cost |
| goal | credits,collection; retained legacy introductory summary |
| inventory/collection | id,art_id,name,rarity,kind,color,condition,value_estimate,public_reference,sale_options,repair_cost,price,origin,collection_quality,repair,collection_replacement,description,collected,sale_attempted_today,repair_attempted_today,repairs_remaining,negotiating |
| item.sale_options[] | customer_id,customer_name,available,counter_eligible,reasons,public_reference,max_counter_ask,budget_range,min_condition,preference_match,condition_met,ask,warning; ordinary first; exact ordered reasons |
| item.collection_quality | min_condition,condition_met,counted,reason; stage-relative and cabinet-sensitive |
| item.repair | available,reasons,cost,energy_cost,command; reason order matches phase→perfect→lifetime→today→pending→energy→cash |
| item.collection_replacement | null or available,reasons,cabinet_item_id,cabinet_condition,energy_cost,command; null for all cabinet items or absent matching cabinet type |
| crates[] | id,supplier,name only; no cargo or hidden identity |
| suppliers[] | id,name,cost,stock,description; ordered salvage then curated, current event/set effects |
| upgrades / upgrade_costs | workbench,shelf,display; next cost null at level 3 |
| upgrade_details[] | id,name,level,max_level,next_cost,effect,next_effect; null next fields at max |
| demand | label,kind,multiplier |
| daily_event | id,title,description,sale_multiplier,salvage_discount,repair_discount,cost_delta,energy_delta; source metadata unchanged |
| last_event | seq,type,title,text,item and optional roll only if inherited/current dice event; item is snapshotted public item/null; never regenerated from later state |
| log[] | day,text; chronological last60 |
| campaign | title,stage_index,first_week_result,completed_milestones,next_milestone,can_continue,continue_command,unlimited |
| campaign.completed_milestones[] | id,title,day; earned history persists |
| campaign.next_milestone | id,title,description,goals,ready,min_condition,legacy_grace; goals[] are key,label,current,target,met |
| collection_progress | personal_count,qualified_count,qualified_categories,quality_themes,min_condition,legacy_grace,requirements,missing,categories; requirements[] key,label,current,target,met; categories[] id,name,qualified_count,theme_complete |
| visitors[] | id,name,role,preferred_kind,preference_label,min_condition,budget_range,premium,status,attempted_today; exact budget absent |
| walkins | daily_limit,used,remaining,budget_range,min_condition,visit_rule; no exact budget |
| codex | total,discovered,collected,entries; unknown entry exactly slot,discovered,collected; known also art_id,name,rarity,kind,description |
| collection_sets[] | id,name,description,required,current,completed,perk; any-condition perks distinct from quality themes |
| stats | crates_opened,sales_count,gross_earnings,days_traded |
| migration | null or from_version,source_day,source_phase,stats_scope; no source path |
| engine_upgrade | null or from_version,source_day,source_phase and D20 sources additionally source_roll_seq,legacy_v3_roll_seq |
| management_upgrade | null or from_version,source_day,source_phase,source_roll_seq,walkins_used_on_import |
| collection_upgrade | null or from_version,source_day,source_phase,legacy_stage_index |
| budget_upgrade | null or from_version,source_day,source_phase,source_roll_seq |
| negotiation | null or item_id,item_name,customer_id,customer_name,original_price,counter_offer,rules_version,origin_rules_version,remaining_offers,final_offer_energy,final_offer_bounds,accept_income,final_failure_income,preview,commands; never context/day/initial_roll_id |
| negotiation.final_offer_bounds/commands | bounds min,max,available; commands accept,decline,preview,offer |
| negotiation.preview | null if no integer price; otherwise price,basis,base_chance,threshold,probability,premium,modifier,modifiers,critical_probability,fumble_probability,energy_cost,accept_income,success_income,failure_income,warning,suggested; modifiers[] label,value |
| last_roll / roll_history[] | null / latest row or ordered max 60 historical rows; exact percentile or historical D20 shape by each rules_version; see contract; no recomputation of old result |
| trade_rules | die,dice,direction,zero_zero,critical,fumble,critical_rule,fumble_rule,house_rules,max_rolls_per_item_day,price_limit,final_offer_energy,final_offer_rule,final_chance_formula,initial_chance_formula,initial_budget_rule,counter_rule,walkin_daily_limit,walkin_budget_range,walkin_min_condition,final_budget_rule,endday,miracle_probability |

Public projection purity is structural, not merely a string search for `rng`. Values can also encode secrets if estimates or opened initial price use hidden base_value. Conversely, committed roll thresholds/counters legitimately carry their specified coarse information; do not redact them or invent different values. Unknown codex rows must omit identities, not fill them with hidden IDs and a display label of??? .

## 5. Evidence ledger and limits

No row below is marked as passing TS by this inventory. Update a completion ledger only after a named test actually runs against the implementation revision being claimed. Record test command, oracle digest/runtime, case count, covered matrix IDs, full-state/public-state comparison mode, failures and excluded state domains.

Kernel results reported separately during work are not expanded here into whole-game claims. A kernel's same-language unit sweep is not a cross-language differential run. A reported Python/V8 counterexample at reference=145.39725173203104, modifier=0, price=100, budget=120 gives initial threshold 87 versus 86; the numeric worker subsequently checked all 3,840,000 validated base/condition/demand reference combinations and found none of the eight engineered divergent references reachable. Global all-input initial-formula parity still cannot be claimed. A deployment smoke is not a source-rule audit. The 39-field projection can be exact while unsupported action transitions remain incomplete.

Documentation-worker checks actually run: all 465 method IDs and their pinned source lines were matched against ASTs with no duplicates; the ordered 39 top-level projection keys and 15 nested key lists were matched against an in-memory synthetic Python projection. A validated Python-only G1-13 probe used seed42, day8, first_week_result=missed, credits650, wrench+lamp cabinet items at70%, coffee inventory item I003 at70%, and walkins.day=8. `price I003 90` earned first_week: event-item minimum stayed70 while live inventory minimum became75; apply_command incremented event_seq once, left revision unchanged, and did not alter RNG. This establishes the oracle expectation, not a TS pass.

Separately reported numeric evidence (2026-10-06, not rerun by the documentation worker): `tests/numeric-oracle.py` and `tests/numeric-oracle.test.mjs`, Python 3.12.14/glibc 2.41 versus Node 24.19.0, pinned engine digest. The numeric worker reports 22 tests: 21 passed, 0 failed, 1 explicit unresolved TODO, with strict ES2022 typecheck passing. Compared cases include 2,440,250 initial thresholds, 1,157,401 finals, 9,216 catalog/condition/demand references, 82,946 eligibility ceilings, 41,575 quotes, 12,011 rounds, 2,201 clamps, 355 parsers, 5 bounds and 9,900 outcomes. Eight of 4,656 engineered arbitrary-reference boundary vectors diverge and remain the explicit TODO; their references were excluded by the exhaustive lawful-reference enumeration. These are primitive comparisons, not a full Cartesian game-state/price/budget/modifier proof, production Worker-runtime verification, or completed G1. Initial probability does not run in the buy/open/price-only slice.

The original suite is method-count based; subTest iterations and exhaustive loops inside a method are not additional methods. Added TS unit/property/differential cases should have their own counts. An equality gate may deliberately compare selected assertions from a legacy/viewer method; disclose that adaptation instead of marking the original test as migrated wholesale.

## 6. Module-level reference inventory

| Module | Actual primary target | Methods | Main staged use |
|---|---|---:|---|
| `test_bargaining_v4.py` | Frozen v4/D20 | 12 | G3 |
| `test_budget_audit_v9.py` | Current v9 engine | 26 | G0/G1/G2/G3/G4 |
| `test_budget_curve_v9.py` | Current v9 engine | 15 | G0/G1/G2/G3/G4 |
| `test_budget_spectator_v9.py` | Spectator/Pillow | 12 | G1/G5 |
| `test_catalog_privacy_v7.py` | Current v9 engine | 12 | G1/G2/G3/G4 |
| `test_catalog_spectator_v7.py` | Spectator/Pillow | 12 | G1/G5 |
| `test_collection_spectator_v8.py` | Spectator/Pillow | 17 | G1/G5 |
| `test_collections_v8.py` | Current v9 engine | 40 | G0/G1/G2/G3/G4 |
| `test_customer_spectator_v6.py` | Spectator/Pillow | 17 | G1/G5 |
| `test_dice_audit.py` | Frozen v4/D20 | 27 | G3 |
| `test_dice_engine.py` | Frozen v4/D20 | 27 | G3 |
| `test_engine.py` | Current v9 engine | 28 | G0/G1/G2/G3/G4 |
| `test_history_boundary_v4.py` | Frozen v4/D20 | 8 | G3 |
| `test_management_audit.py` | Current v9 engine | 21 | G0/G1/G2/G3/G4 |
| `test_management_v6.py` | Current v9 engine | 32 | G0/G1/G2/G3/G4 |
| `test_percentile_audit.py` | Frozen v5 | 28 | G3 |
| `test_percentile_v5.py` | Frozen v5 | 24 | G3 |
| `test_spectator.py` | Spectator/Pillow | 66 | G1/G5 |
| `test_v2_audit.py` | Current v9 engine | 24 | G0/G1/G2/G3/G4 |
| `test_v2_engine.py` | Current v9 engine | 17 | G0/G1/G2/G3/G4 |

## 7. All 465 source methods, mapped to gates

Each symbolic method appears exactly once. Line numbers refer to the pinned public Python package, not the isolated TS project. Status for every row is **reference mapped; TS equivalence not established by this document**.

### test_bargaining_v4.py (12; legacy)

| Method | Line | Gate(s) |
|---|---:|---|
| `BargainingV4Tests.test_new_price_base_twelve_becomes_fifteen_not_initial_target_floor` | 29 | G3 |
| `BargainingV4Tests.test_offer_and_preview_reject_equal_initial_or_at_below_counter_atomically` | 42 | G3 |
| `BargainingV4Tests.test_preview_never_draws_or_changes_private_bytes_and_reopen_keeps_same_roll` | 52 | G3 |
| `BargainingV4Tests.test_forecast_reads_public_bands_not_secret_reference_or_budget` | 68 | G3 |
| `BargainingV4Tests.test_forecast_impossible_ordinary_and_low_threshold_nat_one` | 81 | G3 |
| `BargainingV4Tests.test_preview_and_actual_final_use_frozen_modifiers_after_upgrade` | 94 | G3 |
| `BargainingV4Tests.test_ordinary_threshold_and_critical_faces` | 106 | G3 |
| `BargainingV4Tests.test_no_integer_between_quotes_allows_only_accept_or_decline` | 116 | G3 |
| `BargainingV4Tests.test_v3_import_keeps_pending_resources_rng_and_old_history_no_play` | 142 | G3 |
| `BargainingV4Tests.test_v3_same_price_historical_final_is_preserved_without_rejudging` | 159 | G3 |
| `BargainingV4Tests.test_v3_import_rejects_in_place_existing_target_and_public_projection` | 168 | G3 |
| `BargainingV4Tests.test_highest_base_keeps_full_plus_three_not_capped` | 185 | G3 |

### test_budget_audit_v9.py (26; current)

| Method | Line | Gate(s) |
|---|---:|---|
| `BudgetFormulaIndependentAudit.test_formula_clamps_continuous_base_and_floors_only_at_end` | 62 | G0 |
| `BudgetFormulaIndependentAudit.test_within_budget_matches_frozen_v8_at_every_integer_price` | 68 | G0 |
| `BudgetFormulaIndependentAudit.test_price_sweep_is_monotone_bounded_and_deterministic` | 78 | G0 |
| `BudgetFormulaIndependentAudit.test_historical_5_6_formula_dispatch_keeps_hard_gate_and_none_budget` | 89 | G0/G3 |
| `BudgetFormulaIndependentAudit.test_native_budget_requires_positive_integer` | 100 | G0/G3 |
| `BudgetFormulaIndependentAudit.test_all_hundred_rolls_use_exactly_two_digit_draws_and_no_initial_breakdown` | 105 | G0/G2 |
| `BudgetFormulaIndependentAudit.test_final_offer_and_counter_arithmetic_are_unchanged` | 124 | G0/G2 |
| `BudgetMigrationIndependentAudit.test_frozen_v8_validator_has_expected_release_digest` | 161 | G3 |
| `BudgetMigrationIndependentAudit.test_v8_copy_preserves_every_existing_field_except_explicit_metadata` | 165 | G3 |
| `BudgetMigrationIndependentAudit.test_pending_legacy_hard_gate_survives_reads_accept_decline_and_new_final` | 183 | G1/G2/G3 |
| `BudgetMigrationIndependentAudit.test_collection_grace_and_exhausted_grace_are_never_regranted` | 211 | G1/G3 |
| `BudgetMigrationIndependentAudit.test_zero_history_import_first_new_roll_is_v9` | 227 | G2/G3 |
| `BudgetMigrationIndependentAudit.test_legacy_imports_1_through_6_remain_copyable` | 233 | G3 |
| `BudgetMigrationIndependentAudit.test_budget_marker_is_required_strict_and_bounded` | 245 | G3 |
| `BudgetMigrationIndependentAudit.test_legacy_and_new_history_versions_cannot_be_relabelled` | 272 | G3 |
| `BudgetMigrationIndependentAudit.test_direct_pre_v6_import_cannot_absorb_a_future_v9_roll_into_v6` | 286 | G3 |
| `BudgetMigrationIndependentAudit.test_direct_legacy_budget_and_collection_metadata_share_copy_boundary` | 302 | G3 |
| `BudgetMigrationIndependentAudit.test_v8_tail_uses_absolute_boundary_then_retains_v6_initial_v9_final` | 315 | G2/G3 |
| `BudgetMigrationIndependentAudit.test_mixed_v3_v4_v5_v6_history_survives_v8_then_v9` | 334 | G3 |
| `BudgetMigrationIndependentAudit.test_import_rejects_public_corrupt_repeated_inplace_and_occupied_destinations` | 360 | G3/G4 |
| `BudgetMigrationIndependentAudit.test_legacy_pending_origins_3_4_5_survive_v8_then_v9` | 390 | G2/G3 |
| `BudgetMigrationIndependentAudit.test_budget_boundary_date_cannot_precede_retained_legacy_roll` | 416 | G3 |
| `BudgetMigrationIndependentAudit.test_budget_boundary_date_cannot_follow_new_v9_roll` | 425 | G3 |
| `BudgetMigrationIndependentAudit.test_v8_week_summary_and_loss_copy_without_advancing_play` | 434 | G3 |
| `BudgetMigrationIndependentAudit.test_native_and_imported_walkin_limit_cannot_be_duplicated` | 451 | G2/G3 |
| `BudgetMigrationIndependentAudit.test_unrolled_public_projection_and_eligibility_hide_comfort_budget` | 465 | G1/G3 |

### test_budget_curve_v9.py (15; current)

| Method | Line | Gate(s) |
|---|---:|---|
| `BudgetCurveTests.test_documented_boundary_and_large_overask_examples` | 21 | G0 |
| `BudgetCurveTests.test_budget_minus_one_at_plus_one_has_no_cliff` | 26 | G0 |
| `BudgetCurveTests.test_within_budget_exactly_matches_v8_all_legal_prices` | 36 | G0 |
| `BudgetCurveTests.test_full_price_range_monotone_and_bounded` | 44 | G0 |
| `BudgetCurveTests.test_more_budget_cannot_lower_chance` | 52 | G0 |
| `BudgetCurveTests.test_round_once_and_cap_before_overbudget_penalty` | 57 | G0 |
| `BudgetCurveTests.test_missing_invalid_budget_and_unknown_rules_fail_closed` | 62 | G0/G3 |
| `BudgetCurveTests.test_historical_initial_formula_keeps_old_budget_cliff` | 73 | G0/G3 |
| `BudgetCurveTests.test_both_buyer_types_have_normal_overbudget_success` | 81 | G0/G2 |
| `BudgetCurveTests.test_all_dice_pairs_two_draws_and_exact_threshold_count` | 95 | G0/G2 |
| `BudgetCurveTests.test_extreme_prices_keep_01_miracle_and_100_fumble` | 113 | G0/G2 |
| `BudgetCurveTests.test_counter_eligibility_stays_public_and_unchanged` | 124 | G1/G2 |
| `BudgetCurveTests.test_public_projection_does_not_disclose_budget_or_first_forecast` | 136 | G1 |
| `BudgetCurveTests.test_repeat_json_reads_leave_private_bytes_and_rng_unchanged` | 151 | G1/G4 |
| `BudgetCurveTests.test_identical_state_and_actions_produce_identical_dice_and_rng` | 163 | G0/G2 |

### test_budget_spectator_v9.py (12; viewer)

| Method | Line | Gate(s) |
|---|---:|---|
| `BudgetSpectatorV9Tests.test_v9_percentile_version_is_not_relabeled_v5` | 58 | G5 |
| `BudgetSpectatorV9Tests.test_mixed_history_uses_each_original_rule_label_on_every_page` | 76 | G5 |
| `BudgetSpectatorV9Tests.test_new_public_range_is_normal_spending_comfort` | 92 | G5 |
| `BudgetSpectatorV9Tests.test_sale_details_keep_hard_public_counter_ceiling_and_hidden_initial_odds` | 106 | G5 |
| `BudgetSpectatorV9Tests.test_walkin_detail_explains_soft_initial_budget_and_daily_cap` | 118 | G5 |
| `BudgetSpectatorV9Tests.test_v9_honors_all_historical_quote_origins_without_changing_final_preview` | 128 | G5 |
| `BudgetSpectatorV9Tests.test_native_v9_quote_and_old_v6_quote_are_labeled_honestly` | 146 | G5 |
| `BudgetSpectatorV9Tests.test_imported_quote_with_no_integer_final_price_remains_actionable` | 153 | G5 |
| `BudgetSpectatorV9Tests.test_current_projection_never_reads_or_fabricates_initial_economics` | 161 | G1/G5 |
| `BudgetSpectatorV9Tests.test_older_public_observation_does_not_claim_new_budget_semantics` | 178 | G5 |
| `BudgetSpectatorV9Tests.test_refresh_and_paging_remain_read_only` | 187 | G5 |
| `BudgetSpectatorV9Tests.test_only_temporary_public_input_is_read_and_never_written` | 201 | G5 |

### test_catalog_privacy_v7.py (12; current)

| Method | Line | Gate(s) |
|---|---:|---|
| `CatalogPrivacyV7Tests.test_new_game_has_only_opaque_slots_in_every_public_section` | 83 | G1 |
| `CatalogPrivacyV7Tests.test_buying_any_of_the_24_types_never_reveals_its_identity` | 92 | G1 |
| `CatalogPrivacyV7Tests.test_open_reveals_exactly_one_slot_for_every_catalog_type` | 110 | G1 |
| `CatalogPrivacyV7Tests.test_sealed_copy_of_known_type_does_not_count_as_collection` | 126 | G1 |
| `CatalogPrivacyV7Tests.test_collecting_changes_collection_flag_without_revealing_other_types` | 136 | G1/G2 |
| `CatalogPrivacyV7Tests.test_sale_and_restart_of_reader_keep_discovery_but_not_collection` | 145 | G1/G2 |
| `CatalogPrivacyV7Tests.test_read_commands_repair_stale_projection_without_mutating_private_save` | 163 | G1/G4 |
| `CatalogPrivacyV7Tests.test_failed_open_or_inspect_cannot_reveal_committed_cargo` | 182 | G1 |
| `CatalogPrivacyV7Tests.test_legacy_held_items_are_known_even_with_incomplete_discovery_list` | 201 | G1/G3 |
| `CatalogPrivacyV7Tests.test_all_legacy_imports_preserve_opened_and_sold_discoveries_only` | 215 | G1/G3 |
| `CatalogPrivacyV7Tests.test_cli_outputs_share_the_reveal_boundary` | 257 | G1/G4 |
| `CatalogPrivacyV7Tests.test_public_projection_is_pure_and_isolated_from_caller_mutation` | 284 | G1 |

### test_catalog_spectator_v7.py (12; viewer)

| Method | Line | Gate(s) |
|---|---:|---|
| `CatalogPrivacyRendererTests.test_unknown_projection_is_an_exact_allowlist` | 40 | G1/G5 |
| `CatalogPrivacyRendererTests.test_discovery_requires_explicit_true_not_truthy_or_collection` | 47 | G5 |
| `CatalogPrivacyRendererTests.test_old_catalog_never_leaks_in_any_tab_or_page` | 53 | G5 |
| `CatalogPrivacyRendererTests.test_unknown_card_and_direct_detail_are_safe_at_all_sizes` | 67 | G5 |
| `CatalogPrivacyRendererTests.test_discovered_entries_show_name_story_and_separate_collection` | 84 | G5 |
| `CatalogPrivacyRendererTests.test_detail_refresh_follows_public_slot_and_redacts_or_closes` | 98 | G5 |
| `CatalogPrivacyRendererTests.test_old_catalog_without_explicit_slots_refreshes` | 112 | G5 |
| `CatalogPrivacyRendererTests.test_sale_detail_preserves_public_illustration_identity` | 122 | G5 |
| `DistinctItemArtworkTests.test_all_twenty_four_items_have_unique_color_and_silhouette` | 130 | G5 |
| `DistinctItemArtworkTests.test_old_public_name_fallback_matches_explicit_art_identity` | 142 | G5 |
| `DistinctItemArtworkTests.test_unknown_art_is_identical_across_all_identities_and_rarities` | 149 | G5 |
| `DistinctItemArtworkTests.test_bee_cat_and_whale_are_distinct_at_small_and_large_sizes` | 157 | G5 |

### test_collection_spectator_v8.py (17; viewer)

| Method | Line | Gate(s) |
|---|---:|---|
| `CollectionQualityRendererTests.test_main_summary_and_six_goals_render_at_every_existing_size` | 83 | G5 |
| `CollectionQualityRendererTests.test_summary_detail_has_all_missing_requirements_and_category_counts` | 99 | G5 |
| `CollectionQualityRendererTests.test_grandfathered_current_stage_and_next_stage_rule_are_explicit` | 109 | G5 |
| `CollectionQualityRendererTests.test_known_item_explains_cabinet_quality_repair_and_replacements` | 118 | G5 |
| `CollectionQualityRendererTests.test_pagination_visits_every_public_slot_without_changing_state` | 138 | G5 |
| `CollectionQualityRendererTests.test_navigation_is_read_only_and_refreshes_current_public_items` | 150 | G5 |
| `CollectionQualityRendererTests.test_sold_discovered_item_has_no_invented_repair_or_replacement` | 176 | G5 |
| `CollectionQualityRendererTests.test_progress_detail_refreshes_and_disappears_with_public_data` | 184 | G5 |
| `CollectionQualityRendererTests.test_new_projections_fail_closed_with_malformed_optional_fields` | 194 | G1/G5 |
| `CollectionBackendProjectionTests.test_current_engine_projection_survives_replacement_and_detail_refresh` | 212 | G1/G5 |
| `CollectionBackendProjectionTests.test_stages_without_category_requirement_do_not_invent_one` | 238 | G5 |
| `NumericTokenWrappingTests.test_percentages_and_fractions_stay_intact_across_narrow_widths` | 258 | G5 |
| `NumericTokenWrappingTests.test_screenshot_event_break_keeps_70_percent_together` | 269 | G5 |
| `NumericTokenWrappingTests.test_ellipsis_removes_whole_numeric_token_instead_of_its_suffix` | 277 | G5 |
| `NumericTokenWrappingTests.test_chinese_wrapping_and_explicit_newlines_remain_unchanged` | 284 | G5 |
| `CollectionQualityPrivacyTests.test_unknown_exact_allowlist_discards_quality_repairs_replacements` | 289 | G1/G5 |
| `CollectionQualityPrivacyTests.test_private_fields_never_survive_known_item_detail_join` | 308 | G1/G5 |

### test_collections_v8.py (40; current)

| Method | Line | Gate(s) |
|---|---:|---|
| `QualityMilestoneTests.test_current_schema_keeps_quality_progress_and_marks_current_trades` | 87 | G1 |
| `QualityMilestoneTests.test_first_week_69_70_inclusive_boundary_and_personal_total` | 103 | G1/G2 |
| `QualityMilestoneTests.test_first_week_close_uses_quality_after_operating_cost` | 116 | G2 |
| `QualityMilestoneTests.test_low_quality_collect_still_allowed_without_qualifying_for_goal` | 130 | G1/G2 |
| `QualityMilestoneTests.test_neighborhood_needs_five_at_75_and_three_qualified_categories` | 148 | G1/G2 |
| `QualityMilestoneTests.test_lighthouse_has_no_four_category_requirement` | 162 | G1/G2 |
| `QualityMilestoneTests.test_lighthouse_requires_one_three_item_qualified_theme` | 173 | G1/G2 |
| `QualityMilestoneTests.test_landmark_needs_15_at_85_all_five_categories_and_three_themes` | 186 | G1/G2 |
| `QualityMilestoneTests.test_landmark_category_and_theme_requirements_independent_of_quantity` | 204 | G1/G2 |
| `QualityMilestoneTests.test_quality_themes_count_distinct_catalog_objects_only` | 221 | G1/G2 |
| `QualityMilestoneTests.test_ordinary_sets_and_all_five_perks_keep_any_quality_semantics` | 229 | G1/G2 |
| `QualityMilestoneTests.test_earned_milestones_survive_current_quality_drop` | 246 | G1/G2 |
| `QualityMilestoneTests.test_longhaul_quality_increases_to_cap_without_resetting_history` | 253 | G1/G2 |
| `ReplacementTests.test_explicit_better_copy_swap_preserves_both_full_item_records` | 273 | G2 |
| `ReplacementTests.test_replace_accepts_strict_one_point_improvement` | 300 | G2 |
| `ReplacementTests.test_equal_worse_wrong_catalog_missing_and_zero_energy_fail_atomically` | 306 | G2 |
| `ReplacementTests.test_duplicate_collect_does_not_implicitly_replace` | 323 | G2 |
| `ReplacementTests.test_full_inventory_swap_is_allowed_and_bot_set_not_rewarded_twice` | 328 | G2 |
| `ReplacementTests.test_pending_negotiation_locks_candidate_but_is_not_reset` | 342 | G2 |
| `ReplacementTests.test_replacement_can_complete_stage_without_granting_cash_or_rng` | 356 | G1/G2 |
| `ReplacementTests.test_public_replacement_explains_available_and_blocked_paths` | 372 | G1/G2 |
| `CabinetRepairTests.test_cabinet_repair_uses_same_randomness_price_cost_and_limits_as_inventory` | 393 | G0/G2 |
| `CabinetRepairTests.test_repair_failure_drops_quality_preserves_history_and_can_unqualify` | 415 | G1/G2 |
| `CabinetRepairTests.test_repair_total_two_attempts_one_per_day_and_atomic_resource_errors` | 437 | G2 |
| `CabinetRepairTests.test_cabinet_repair_can_finish_milestone_and_updates_new_threshold` | 458 | G1/G2 |
| `CabinetRepairTests.test_cabinet_repair_preserves_other_items_pending_negotiation` | 470 | G2 |
| `CabinetRepairTests.test_public_repair_eligibility_available_for_cabinet_and_inventory` | 489 | G1/G2 |
| `CollectionMigrationTests.test_import_v1_to_v6_copy_only_preserves_frozen_conversion_fields` | 504 | G3 |
| `CollectionMigrationTests.test_preweek_grace_uses_old_count_then_next_stage_uses_quality` | 531 | G1/G3 |
| `CollectionMigrationTests.test_grace_only_covers_current_milestone_not_multiple_cascaded_stages` | 552 | G1/G3 |
| `CollectionMigrationTests.test_grace_persists_across_days_and_reads_until_its_stage_is_earned` | 573 | G1/G3 |
| `CollectionMigrationTests.test_invalid_grace_markers_fail_instead_of_silently_resetting` | 590 | G3 |
| `CollectionMigrationTests.test_past_first_week_outcome_never_retroactively_changed` | 605 | G3 |
| `CollectionMigrationTests.test_v6_pending_trade_and_rolls_survive_copy_and_final_resolution` | 618 | G2/G3 |
| `CollectionMigrationTests.test_relabeling_v8_as_v6_cannot_regrant_grace` | 655 | G3 |
| `CollectionMigrationTests.test_import_rejects_in_place_public_projection_and_existing_target` | 671 | G3/G4 |
| `CollectionPrivacyAndTradeTests.test_new_quality_sections_do_not_reveal_unknown_catalog_identities` | 710 | G1 |
| `CollectionPrivacyAndTradeTests.test_sealed_unknown_cargo_does_not_change_quality_or_discovery` | 721 | G1 |
| `CollectionPrivacyAndTradeTests.test_repair_and_replacement_forecasts_ignore_private_value_and_budget` | 737 | G1 |
| `CollectionPrivacyAndTradeTests.test_trade_constants_and_within_budget_results_match_frozen_v6` | 749 | G0/G2 |

### test_customer_spectator_v6.py (17; viewer)

| Method | Line | Gate(s) |
|---|---:|---|
| `CustomerSpectatorTests.test_daily_capacity_and_public_budget_visible_before_any_roll` | 54 | G5 |
| `CustomerSpectatorTests.test_shelf_leads_to_public_eligibility_not_a_sale_action` | 65 | G5 |
| `CustomerSpectatorTests.test_named_buyer_has_own_budget_preference_reason_and_consequence` | 81 | G5 |
| `CustomerSpectatorTests.test_price_and_condition_reasons_are_public_not_recomputed` | 89 | G5 |
| `CustomerSpectatorTests.test_unavailable_buyers_never_claim_an_attempt_is_available` | 106 | G5 |
| `CustomerSpectatorTests.test_projection_drops_hidden_economics_and_initial_odds` | 114 | G1/G5 |
| `CustomerSpectatorTests.test_malformed_forecasts_do_not_invent_eligibility_or_crash` | 132 | G5 |
| `CustomerSpectatorTests.test_buyer_paging_wraps_and_close_remains_reachable` | 147 | G5 |
| `CustomerSpectatorTests.test_open_forecast_refreshes_prices_quota_and_closes_when_item_is_gone` | 159 | G5 |
| `CustomerSpectatorTests.test_walkin_detail_explains_consumption_and_refreshes` | 175 | G5 |
| `CustomerSpectatorTests.test_v6_d100_and_mixed_history_preserve_original_rules` | 190 | G5 |
| `CustomerSpectatorTests.test_v6_final_negotiation_retains_single_exact_public_preview` | 205 | G5 |
| `CustomerSpectatorTests.test_v6_honors_pending_quotes_from_each_previous_dice_version` | 216 | G5 |
| `CustomerSpectatorTests.test_migrated_quote_without_final_price_space_is_still_honored` | 237 | G5 |
| `CustomerSpectatorTests.test_negotiating_item_explains_new_conditions_do_not_revoke_quote` | 246 | G5 |
| `CustomerSpectatorTests.test_all_sizes_are_readonly_deterministic_and_overlay_hits_stay_in_bounds` | 264 | G5 |
| `CustomerSpectatorTests.test_legacy_shelves_and_visitors_do_not_gain_v6_capacity` | 279 | G5 |

### test_dice_audit.py (27; legacy)

| Method | Line | Gate(s) |
|---|---:|---|
| `DiceTransactionAudit.test_natural_twenty_settles_9999_beyond_named_budget` | 74 | G3 |
| `DiceTransactionAudit.test_natural_twenty_also_settles_9999_with_generic_traveler` | 90 | G3 |
| `DiceTransactionAudit.test_ordinary_success_settles_the_exact_initial_or_final_offer` | 97 | G3 |
| `DiceTransactionAudit.test_ordinary_nineteen_cannot_ignore_budget_even_for_cheap_valuable_item` | 112 | G3 |
| `DiceTransactionAudit.test_natural_one_ends_even_lowest_price_and_high_modifiers` | 129 | G3 |
| `DiceTransactionAudit.test_every_noncritical_face_fails_9999_and_creates_one_counter` | 145 | G3 |
| `DiceTransactionAudit.test_pending_locks_item_customer_and_all_other_sale_attempts` | 158 | G3 |
| `DiceTransactionAudit.test_accept_settles_binding_counter_without_extra_energy_or_rng` | 169 | G3 |
| `DiceTransactionAudit.test_decline_ends_item_for_day_even_after_repricing_and_reload` | 186 | G3 |
| `DiceTransactionAudit.test_final_natural_twenty_can_settle_lower_9998` | 201 | G3 |
| `DiceTransactionAudit.test_final_failures_never_create_third_roll_or_second_counter` | 213 | G3 |
| `DiceTransactionAudit.test_reloaded_pending_keeps_same_quote_and_next_roll` | 230 | G3 |
| `DiceTransactionAudit.test_invalid_offers_and_arity_leave_files_and_rng_byte_identical` | 249 | G3 |
| `DiceTransactionAudit.test_no_energy_keeps_pending_and_allows_free_accept_or_decline` | 259 | G3 |
| `DiceTransactionAudit.test_endday_clears_pending_for_new_day_week_summary_and_bankruptcy` | 272 | G3 |
| `DiceTransactionAudit.test_pending_context_is_frozen_across_display_upgrade` | 292 | G3 |
| `DiceTransactionAudit.test_public_trade_output_has_no_private_or_future_rng_fields` | 302 | G3 |
| `DiceTransactionAudit.test_public_trade_fields_are_defensive_copies` | 323 | G3 |
| `DiceTransactionAudit.test_corrupt_pending_consistency_is_refused_without_overwrite` | 336 | G3 |
| `DiceTransactionAudit.test_orphan_final_roll_is_refused_without_overwrite` | 370 | G3 |
| `DiceTransactionAudit.test_sixty_roll_history_tail_may_begin_with_preceded_final` | 382 | G3 |
| `DiceTransactionAudit.test_save_replace_failure_is_atomic_and_retry_uses_same_die` | 404 | G3 |
| `DiceTransactionAudit.test_projection_failure_commits_die_and_recovers_without_replay` | 418 | G3 |
| `DiceTransactionAudit.test_directory_fsync_failure_reports_committed_high_price_sale` | 436 | G3 |
| `DiceTransactionAudit.test_v2_copy_migration_preserves_rng_assets_and_already_used_attempts` | 463 | G3 |
| `DiceTransactionAudit.test_v2_import_refuses_existing_targets_and_wrong_source_without_changes` | 479 | G3 |
| `DiceTransactionAudit.test_v2_week_summary_and_bankruptcy_never_autocontinue` | 501 | G3 |

### test_dice_engine.py (27; legacy)

| Method | Line | Gate(s) |
|---|---:|---|
| `DiceEngineTests.test_natural_twenty_sells_9999_beyond_named_budget` | 64 | G3 |
| `DiceEngineTests.test_natural_one_always_fails_without_bargain_even_for_one_coin` | 82 | G3 |
| `DiceEngineTests.test_actual_rng_roll_and_saved_next_rng_are_exact` | 93 | G3 |
| `DiceEngineTests.test_lower_price_quality_and_demand_improve_target` | 102 | G3 |
| `DiceEngineTests.test_preference_quality_events_upgrades_and_sets_have_public_modifiers` | 115 | G3 |
| `DiceEngineTests.test_budget_blocks_ordinary_nineteen_but_not_twenty` | 131 | G3 |
| `DiceEngineTests.test_pending_locks_item_and_other_sales_without_mutation` | 142 | G3 |
| `DiceEngineTests.test_reload_status_inspect_and_reads_preserve_pending_and_rng` | 151 | G3 |
| `DiceEngineTests.test_accept_settles_counteroffer_free_at_zero_energy_and_no_rng` | 160 | G3 |
| `DiceEngineTests.test_decline_is_free_and_ends_daily_attempt` | 174 | G3 |
| `DiceEngineTests.test_final_twenty_sells_lower_9998_and_only_one_more_roll` | 186 | G3 |
| `DiceEngineTests.test_final_failure_and_fumble_close_without_reopening` | 198 | G3 |
| `DiceEngineTests.test_final_lower_price_can_succeed_normally` | 211 | G3 |
| `DiceEngineTests.test_illegal_final_prices_and_zero_energy_never_consume_rng` | 219 | G3 |
| `DiceEngineTests.test_final_target_uses_frozen_context_despite_upgrade` | 227 | G3 |
| `DiceEngineTests.test_endday_declines_pending_and_next_day_unlocks` | 237 | G3 |
| `DiceEngineTests.test_endday_closes_pending_before_summary_or_bankruptcy` | 248 | G3 |
| `DiceEngineTests.test_private_judgement_and_future_rng_never_enter_public_tree` | 262 | G3 |
| `DiceEngineTests.test_final_save_failure_rolls_back_everything_and_retry_same_result` | 274 | G3 |
| `DiceEngineTests.test_projection_failure_keeps_final_roll_and_status_repairs_it` | 288 | G3 |
| `DiceEngineTests.test_corrupt_dice_and_pending_refused_without_repair_or_reroll` | 303 | G3 |
| `DiceEngineTests.test_cross_process_two_final_offers_only_commit_one` | 321 | G3 |
| `DiceEngineTests.test_lowered_high_price_two_roll_miracle_probability_exactly_9_point_5_percent` | 332 | G3 |
| `DiceEngineTests.test_v2_import_preserves_source_rng_assets_statistics_and_used_attempts` | 351 | G3 |
| `DiceEngineTests.test_v2_import_refuses_original_and_existing_target_or_projection` | 374 | G3 |
| `DiceEngineTests.test_v2_load_needs_explicit_copy_upgrade` | 386 | G3 |
| `DiceEngineTests.test_v2_summary_upgrade_does_not_continue_or_charge` | 392 | G3 |

### test_engine.py (28; current)

| Method | Line | Gate(s) |
|---|---:|---|
| `EngineTests.test_help_and_missing_game_never_create_save` | 55 | G4 |
| `EngineTests.test_new_explicit_restart_and_no_silent_reroll` | 64 | G2/G4 |
| `EngineTests.test_status_market_and_inspect_do_not_advance_or_reroll` | 76 | G1/G4 |
| `EngineTests.test_observation_filename_and_recovery` | 85 | G4 |
| `EngineTests.test_buy_commits_contents_and_open_does_not_draw_rng` | 96 | G0/G1 |
| `EngineTests.test_public_projection_excludes_hidden_data_everywhere` | 112 | G1 |
| `EngineTests.test_both_suppliers_and_stock_limits` | 127 | G1 |
| `EngineTests.test_repair_consumes_money_and_energy_and_is_bounded` | 138 | G2 |
| `EngineTests.test_repair_has_success_and_failure_outcomes` | 159 | G0/G2 |
| `EngineTests.test_perfect_condition_repair_rejected` | 169 | G2 |
| `EngineTests.test_prices_validate_without_mutation_or_energy_cost` | 176 | G1 |
| `EngineTests.test_sale_failure_commits_attempt_and_cannot_be_rerolled` | 187 | G2 |
| `EngineTests.test_sale_revenue_and_removal_persist_across_instances` | 208 | G2/G4 |
| `EngineTests.test_collect_removes_item_and_cannot_sell_directly` | 217 | G2 |
| `EngineTests.test_duplicate_catalog_cannot_be_collected` | 230 | G2 |
| `EngineTests.test_workbench_and_shelf_upgrade_costs_and_limits` | 240 | G2 |
| `EngineTests.test_capacity_includes_unopened_crates` | 261 | G1 |
| `EngineTests.test_insufficient_money_and_energy_never_advance_rng` | 273 | G0/G1/G2 |
| `EngineTests.test_invalid_commands_parameters_and_ids` | 282 | G1/G2 |
| `EngineTests.test_endday_maintenance_reset_and_stable_demand` | 290 | G0/G2 |
| `EngineTests.test_week_finishes_and_requires_explicit_continue` | 302 | G2 |
| `EngineTests.test_bankruptcy_ends_without_negative_credits` | 320 | G2 |
| `EngineTests.test_final_win_requires_post_maintenance_cash_and_two_collections` | 325 | G2 |
| `EngineTests.test_invalid_save_never_silently_resets` | 347 | G3 |
| `EngineTests.test_save_validation_rejects_corrupt_fields` | 357 | G3 |
| `EngineTests.test_cli_gameplay_outputs_valid_public_json` | 365 | G1/G4 |
| `EngineTests.test_cross_process_lock_prevents_lost_updates_and_overselling` | 376 | G4 |
| `EngineTests.test_no_temp_files_left_after_atomic_saves` | 390 | G4 |

### test_history_boundary_v4.py (8; legacy)

| Method | Line | Gate(s) |
|---|---:|---|
| `HistoryBoundaryV4Tests.test_native_and_v2_history_cannot_claim_legacy_same_price_final` | 48 | G3 |
| `HistoryBoundaryV4Tests.test_imported_pending_initial_and_new_final_cross_boundary_and_reload` | 62 | G3 |
| `HistoryBoundaryV4Tests.test_future_imported_roll_cannot_be_downgraded` | 74 | G3 |
| `HistoryBoundaryV4Tests.test_committed_v3_same_price_final_keeps_original_history` | 82 | G3 |
| `HistoryBoundaryV4Tests.test_preserved_initial_cannot_be_relabelled_current_rules` | 91 | G3 |
| `HistoryBoundaryV4Tests.test_import_boundary_metadata_is_required_integer_and_bounded` | 97 | G3 |
| `HistoryBoundaryV4Tests.test_zero_history_v3_import_uses_v4_for_first_future_roll` | 111 | G3 |
| `HistoryBoundaryV4Tests.test_history_tail_uses_absolute_roll_ids_at_import_boundary` | 118 | G3 |

### test_management_audit.py (21; current)

| Method | Line | Gate(s) |
|---|---:|---|
| `ManagementIndependentAudit.test_new_management_field_is_required_before_public_projection` | 69 | G3 |
| `ManagementIndependentAudit.test_two_v6_ordinary_visits_on_same_day_are_rejected_in_history` | 76 | G3 |
| `ManagementIndependentAudit.test_import_day_used_capacity_cannot_add_a_v6_ordinary_initial` | 94 | G3 |
| `ManagementIndependentAudit.test_management_source_versions_must_match_legacy_provenance` | 107 | G3 |
| `ManagementIndependentAudit.test_v1_v2_management_boundary_cannot_absorb_a_future_percentile_roll` | 120 | G3 |
| `ManagementIndependentAudit.test_direct_d20_import_boundaries_cannot_absorb_a_future_percentile_roll` | 133 | G3 |
| `ManagementIndependentAudit.test_multiple_committed_legacy_ordinary_visits_remain_grandfathered` | 147 | G3 |
| `ManagementIndependentAudit.test_round_public_reference_before_applying_exact_integer_ratio` | 160 | G0/G1 |
| `ManagementIndependentAudit.test_budget_is_hidden_but_final_offer_has_no_second_private_gate` | 172 | G0/G1/G2 |
| `ManagementIndependentAudit.test_eligibility_and_unrolled_projection_do_not_depend_on_private_values` | 184 | G1 |
| `ManagementIndependentAudit.test_all_read_outputs_and_event_snapshots_exclude_secret_fields` | 195 | G1 |
| `ManagementIndependentAudit.test_frozen_counter_and_chance_survive_upgrade_reload_and_public_mutation` | 210 | G1/G2/G4 |
| `ManagementIndependentAudit.test_pending_item_mutations_and_zero_energy_offer_reject_atomically` | 222 | G1/G2 |
| `ManagementIndependentAudit.test_private_replace_failure_does_not_consume_visit_and_retry_is_identical` | 237 | G4 |
| `ManagementIndependentAudit.test_directory_sync_failure_after_commit_does_not_duplicate_visit` | 249 | G4 |
| `ManagementIndependentAudit.test_parallel_accept_decline_offer_settles_exactly_once` | 266 | G4 |
| `ManagementIndependentAudit.test_parallel_successful_ordinary_sales_have_only_one_winner` | 283 | G4 |
| `ManagementIndependentAudit.test_week_summary_preserves_spent_visit_until_explicit_next_day` | 299 | G2 |
| `ManagementIndependentAudit.test_walkin_generation_does_not_perturb_main_rng_or_daily_world` | 313 | G0/G2 |
| `ManagementIndependentAudit.test_v5_import_with_sixty_history_rows_keeps_absolute_boundary_and_rolls` | 324 | G3 |
| `ManagementIndependentAudit.test_long_campaign_validates_after_all_imported_rolls_leave_history` | 348 | G2/G3 |

### test_management_v6.py (32; current)

| Method | Line | Gate(s) |
|---|---:|---|
| `ManagementV6Tests.test_public_walkin_capacity_budget_and_no_private_fields` | 68 | G1 |
| `ManagementV6Tests.test_public_reference_and_eligibility_ignore_exact_values_and_budgets` | 80 | G0/G1 |
| `ManagementV6Tests.test_reasonable_ordinary_failure_enters_one_binding_counter` | 90 | G2 |
| `ManagementV6Tests.test_absurd_ordinary_failure_leaves_without_counter_and_consumes_visit` | 101 | G2 |
| `ManagementV6Tests.test_budget_ceiling_and_public_reference_boundary_are_inclusive` | 110 | G0/G1/G2 |
| `ManagementV6Tests.test_walkin_condition_boundary_and_cheap_one_coin_no_counter` | 122 | G1/G2 |
| `ManagementV6Tests.test_unfit_condition_normal_failure_is_terminal` | 130 | G2 |
| `ManagementV6Tests.test_named_preference_and_condition_are_public_deterministic_requirements` | 137 | G1/G2 |
| `ManagementV6Tests.test_matching_named_failure_bargains_and_named_cap_remains` | 148 | G2 |
| `ManagementV6Tests.test_miracle_01_at_9999_ignores_eligibility_and_exact_budget` | 156 | G0/G2 |
| `ManagementV6Tests.test_fumble100_never_bargains_and_consumes_ordinary_visit` | 166 | G0/G2 |
| `ManagementV6Tests.test_deterministic_checks_add_no_rng_draw` | 172 | G0/G2 |
| `ManagementV6Tests.test_invalid_attempts_zero_energy_and_unknown_customer_are_atomic` | 178 | G2 |
| `ManagementV6Tests.test_reprice_switch_items_restart_process_read_commands_do_not_refresh` | 184 | G1/G2/G4 |
| `ManagementV6Tests.test_named_buyer_remains_available_after_ordinary_visit_used` | 196 | G2 |
| `ManagementV6Tests.test_accept_decline_remain_free_and_no_random_draw` | 203 | G0/G2 |
| `ManagementV6Tests.test_final_preview_exact_strict_bounds_and_one_energy_retry` | 211 | G0/G1/G2 |
| `ManagementV6Tests.test_final_failure_cannot_return_to_old_counter` | 225 | G2 |
| `ManagementV6Tests.test_final_miracle_and_fumble_still_apply` | 231 | G0/G2 |
| `ManagementV6Tests.test_final_and_within_budget_initial_formula_unchanged_from_v5` | 237 | G0/G2 |
| `ManagementV6Tests.test_all_hundred_digit_pairs_still_use_exactly_two_d10_draws` | 248 | G0/G2 |
| `ManagementV6Tests.test_economy_costs_prices_upgrades_unchanged` | 258 | G0/G1/G2 |
| `ManagementV6Tests.test_copy_migration_v1_to_v5_preserves_rng_resources_source_and_history` | 262 | G0/G3 |
| `ManagementV6Tests.test_old_pending_quote_honored_despite_new_ineligibility` | 278 | G2/G3 |
| `ManagementV6Tests.test_v5_used_ordinary_capacity_carries_even_after_item_sold` | 296 | G3 |
| `ManagementV6Tests.test_v5_named_only_attempt_does_not_consume_walkin` | 303 | G3 |
| `ManagementV6Tests.test_mixed_v3_v4_v5_history_retains_boundaries_into_v6` | 308 | G3 |
| `ManagementV6Tests.test_migration_rejects_public_projection_and_in_place_or_existing_projection` | 319 | G3/G4 |
| `ManagementV6Tests.test_capacity_corruption_and_version_relabeling_rejected` | 327 | G3 |
| `ManagementV6Tests.test_simultaneous_ordinary_attempts_allow_only_one_commit` | 340 | G4 |
| `ManagementV6Tests.test_public_projection_write_failure_does_not_repeat_capacity` | 349 | G4 |
| `ManagementV6Tests.test_endday_closes_pending_then_next_day_resets_capacity_only_once` | 360 | G2 |

### test_percentile_audit.py (28; legacy)

| Method | Line | Gate(s) |
|---|---:|---|
| `PercentileRulesAudit.test_native_initial_thresholds_include_non_d20_steps` | 64 | G3 |
| `PercentileRulesAudit.test_final_integer_rational_and_clamp_boundaries` | 75 | G3 |
| `PercentileRulesAudit.test_all_digit_pairs_are_bijective_and_take_two_independent_draws` | 85 | G3 |
| `PercentileRulesAudit.test_final_preview_exactly_counts_successes_over_all_100_outcomes` | 102 | G3 |
| `PercentileRulesAudit.test_every_native_public_bonus_is_exactly_five_times_legacy` | 124 | G3 |
| `PercentilePersistenceAudit.test_sale_persists_exactly_two_digit_draws_and_reopen_preserves_stream` | 166 | G3 |
| `PercentilePersistenceAudit.test_preview_is_read_only_and_cannot_change_future_percentile` | 176 | G3 |
| `PercentilePersistenceAudit.test_free_accept_and_decline_do_not_advance_rng_even_at_zero_energy` | 192 | G3 |
| `PercentilePersistenceAudit.test_strict_offer_and_preview_bounds_reject_atomically` | 208 | G3 |
| `PercentilePersistenceAudit.test_final_failure_spends_one_energy_and_permanently_closes_old_quote` | 216 | G3 |
| `PercentilePersistenceAudit.test_01_sells_maximum_legal_price_above_budget_and_100_ends_visit` | 227 | G3 |
| `PercentilePersistenceAudit.test_final_ordinary_success_above_named_budget_has_no_second_gate` | 239 | G3 |
| `PercentilePersistenceAudit.test_public_projection_has_no_private_state_or_secret_formula_inputs` | 252 | G3 |
| `PercentilePersistenceAudit.test_precommit_failure_leaves_bytes_and_same_future_roll` | 270 | G3 |
| `PercentilePersistenceAudit.test_projection_failure_does_not_reroll_committed_final_and_status_heals` | 280 | G3 |
| `PercentilePersistenceAudit.test_lock_serializes_competing_final_offers_to_one_pair_and_one_energy` | 296 | G3 |
| `PercentilePersistenceAudit.test_native_final_record_rejects_inconsistent_digits_probability_and_formula` | 311 | G3 |
| `PercentilePersistenceAudit.test_display_upgrade_does_not_change_frozen_final_bonus_or_preview` | 325 | G3 |
| `PercentileMigrationAudit.test_all_four_imports_preserve_source_core_rng_and_committed_cargo` | 358 | G3 |
| `PercentileMigrationAudit.test_old_pending_final_uses_next_two_digits_without_old_d20_reroll` | 388 | G3 |
| `PercentileMigrationAudit.test_v3_same_price_final_history_is_not_rejudged_as_strict_v5` | 405 | G3 |
| `PercentileMigrationAudit.test_v4_with_v3_history_keeps_both_boundaries_and_v5_future_final` | 415 | G3 |
| `PercentileMigrationAudit.test_absolute_import_boundary_survives_sixty_row_history_truncation` | 436 | G3 |
| `PercentileMigrationAudit.test_import_boundary_and_history_relabelling_corruption_rejected` | 454 | G3 |
| `PercentileMigrationAudit.test_import_refuses_in_place_existing_destination_and_public_only_sources` | 471 | G3 |
| `PercentileMigrationAudit.test_old_pending_quote_remains_free_to_accept_or_decline_without_rng_draw` | 489 | G3 |
| `PercentileMigrationAudit.test_zero_history_imports_use_v5_for_first_future_roll` | 509 | G3 |
| `PercentileMigrationAudit.test_v4_container_with_pending_v3_roll_retains_origin_three` | 521 | G3 |

### test_percentile_v5.py (24; legacy)

| Method | Line | Gate(s) |
|---|---:|---|
| `PercentileV5Tests.test_hundred_digit_pairs_are_bijective_uniform_and_independent_calls` | 64 | G3 |
| `PercentileV5Tests.test_critical01_sells_9999_above_private_budget` | 80 | G3 |
| `PercentileV5Tests.test_100_fumble_ends_even_cheapest_offer` | 96 | G3 |
| `PercentileV5Tests.test_native_initial_threshold_price_sensitivity_and_budget` | 108 | G3 |
| `PercentileV5Tests.test_low_roll_boundaries_01_and_100` | 118 | G3 |
| `PercentileV5Tests.test_final_10percent_50percent_hugepremium_and_scale_invariance` | 128 | G3 |
| `PercentileV5Tests.test_exact_preview_independent_of_all_hidden_valuation_budget` | 139 | G3 |
| `PercentileV5Tests.test_preview_no_private_write_rng_draw_energy_or_revision_and_restart_equivalence` | 154 | G3 |
| `PercentileV5Tests.test_final_distribution_matches_public_probability_all100_pairs` | 170 | G3 |
| `PercentileV5Tests.test_final_above_named_budget_has_no_second_hidden_gate` | 185 | G3 |
| `PercentileV5Tests.test_frozen_bonuses_survive_upgrade_and_final` | 195 | G3 |
| `PercentileV5Tests.test_invalid_final_prices_rejected_without_any_write_or_rng` | 206 | G3 |
| `PercentileV5Tests.test_accept_decline_free_zeroenergy_and_no_new_roll` | 216 | G3 |
| `PercentileV5Tests.test_final_fail_loses_quote_one_energy_only_two_pairs` | 229 | G3 |
| `PercentileV5Tests.test_final_critical_bypasses_huge_premium_and_fumble_always_ends` | 240 | G3 |
| `PercentileV5Tests.test_pending_locks_item_and_customer_across_reload` | 249 | G3 |
| `PercentileV5Tests.test_endday_declines_pending_and_leaves_no_stale_accept` | 258 | G3 |
| `PercentileV5Tests.test_public_data_omits_secret_context_and_unrelated_d20_fields` | 265 | G3 |
| `PercentileV5Tests.test_corrupted_digits_probability_outcome_and_version_rejected` | 276 | G3 |
| `PercentileV5Tests.test_copy_v1_v2_resources_and_rng_preserved` | 287 | G3 |
| `PercentileV5Tests.test_copy_v3_v4_pending_counter_rng_resources_kept_with_explicit_retry_rules` | 312 | G3 |
| `PercentileV5Tests.test_historical_v3_sameprice_final_remains_legal_history_only` | 334 | G3 |
| `PercentileV5Tests.test_mixed_v3_v4_boundary_preserved_then_native_v5` | 343 | G3 |
| `PercentileV5Tests.test_import_rejects_overwrite_samepath_wrongversion_and_public_projection` | 356 | G3 |

### test_spectator.py (66; viewer)

| Method | Line | Gate(s) |
|---|---:|---|
| `RendererTests.test_all_tabs_at_portrait_wide_and_phone_sizes` | 36 | G5 |
| `RendererTests.test_new_schema_fields_are_rendered` | 45 | G5 |
| `RendererTests.test_render_does_not_mutate_observation` | 51 | G5 |
| `RendererTests.test_all_item_art_kinds_rarities_and_bad_colors` | 55 | G5 |
| `RendererTests.test_paging_is_bounded_and_reachable` | 62 | G5 |
| `RendererTests.test_hit_testing_handles_scaled_letterboxing` | 68 | G5 |
| `RendererTests.test_detail_overlay_consumes_clicks_and_shows_story` | 77 | G5 |
| `RendererTests.test_missing_state_and_first_week_pause` | 82 | G5 |
| `RendererTests.test_bad_optional_fields_do_not_crash` | 89 | G5 |
| `RendererTests.test_public_only_selected_fields` | 92 | G1/G5 |
| `RendererTests.test_colors_and_numbers_are_defensive` | 96 | G5 |
| `ReaderTests.test_reader_reads_only_one_public_path_and_never_writes` | 108 | G5 |
| `ReaderTests.test_save_path_and_save_symlink_are_rejected_before_read` | 118 | G5 |
| `ReaderTests.test_partial_json_keeps_last_good_snapshot_and_recovers` | 122 | G5 |
| `ReaderTests.test_no_fallback_to_save_when_public_file_is_missing` | 128 | G5 |
| `ReaderTests.test_private_rng_state_rejected` | 131 | G5 |
| `ReaderTests.test_snapshot_cli_is_headless_and_cannot_overwrite_save` | 135 | G5 |
| `DiceRendererTests.test_all_adjudication_outcomes_use_real_face` | 166 | G5 |
| `DiceRendererTests.test_pending_bargain_shows_public_prices_costs_and_waiting` | 176 | G5 |
| `DiceRendererTests.test_pending_does_not_relabel_unrelated_or_final_roll` | 181 | G5 |
| `DiceRendererTests.test_dice_can_use_last_event_public_roll` | 186 | G5 |
| `DiceRendererTests.test_dice_and_history_render_at_all_sizes` | 192 | G5 |
| `DiceRendererTests.test_history_pages_newest_first_and_preserves_original_failure` | 201 | G5 |
| `DiceRendererTests.test_history_empty_state_does_not_invent_dice` | 211 | G5 |
| `DiceRendererTests.test_roll_detail_shows_public_calculation_rules_and_pending_options` | 215 | G5 |
| `DiceRendererTests.test_demo_flag_is_explicit_and_off_by_default` | 224 | G5 |
| `DiceRendererTests.test_renderer_never_mutates_or_rerolls` | 230 | G5 |
| `DiceRendererTests.test_unknown_private_fields_are_never_rendered` | 238 | G1/G5 |
| `DiceRendererTests.test_invalid_face_is_unknown_never_clamped_to_natural_twenty` | 243 | G5 |
| `DiceRendererTests.test_dice_actions_are_only_read_only_views` | 250 | G5 |
| `DiceRendererTests.test_accepting_counteroffer_shows_sale_not_stale_failed_roll` | 260 | G5 |
| `DiceRendererTests.test_later_actions_keep_latest_event_and_previous_dice_distinct` | 268 | G5 |
| `DiceRendererTests.test_engine_generated_public_samples_are_consistent_and_render` | 276 | G5 |
| `DiceRendererTests.test_escape_dismisses_detail_before_leaving_fullscreen` | 299 | G5 |
| `DiceRendererTests.test_spectator_history_clicks_and_repeated_close_change_only_view_state` | 306 | G5 |
| `BargainingRendererTests.test_pre_roll_card_exposes_price_dc_die_income_and_risk` | 348 | G5 |
| `BargainingRendererTests.test_explicit_preview_is_not_labeled_example_even_at_minimum` | 356 | G5 |
| `BargainingRendererTests.test_preview_raw_floor_respects_natural_one_failure` | 361 | G5 |
| `BargainingRendererTests.test_impossible_ordinary_preview_has_only_natural_twenty` | 366 | G5 |
| `BargainingRendererTests.test_partial_range_does_not_promise_nineteen_always_succeeds` | 370 | G5 |
| `BargainingRendererTests.test_no_legal_offer_shows_accept_or_decline_without_fake_forecast` | 375 | G5 |
| `BargainingRendererTests.test_missing_or_malformed_forecast_is_not_filled_in` | 382 | G5 |
| `BargainingRendererTests.test_detail_uses_same_public_forecast_and_frozen_modifiers` | 389 | G5 |
| `BargainingRendererTests.test_exact_final_roll_shows_base_penalty_and_required_raw` | 398 | G5 |
| `BargainingRendererTests.test_exact_final_natural_twenty_and_raw_floor_are_correct` | 407 | G5 |
| `BargainingRendererTests.test_v3_missing_metadata_never_inherits_new_penalty` | 413 | G5 |
| `BargainingRendererTests.test_public_only_projection_and_readonly_actions` | 423 | G1/G5 |
| `BargainingRendererTests.test_new_cards_tabs_history_and_overlay_render_at_all_sizes` | 437 | G5 |
| `BargainingRendererTests.test_accept_after_preview_clears_proposal_and_retains_history` | 447 | G5 |
| `BargainingRendererTests.test_open_preview_refreshes_to_latest_price_then_closes_after_sale` | 455 | G5 |
| `BargainingRendererTests.test_unrelated_new_negotiation_closes_old_preview` | 470 | G5 |
| `BargainingRendererTests.test_legacy_open_roll_drops_stale_pending_label_after_acceptance` | 478 | G5 |
| `PercentileRendererTests.test_real_pair_and_low_roll_outcomes` | 524 | G5 |
| `PercentileRendererTests.test_critical_legal_high_price_and_hundred_are_distinct` | 538 | G5 |
| `PercentileRendererTests.test_modifier_is_percentage_points_and_never_added_to_result` | 548 | G5 |
| `PercentileRendererTests.test_exact_previews_at_near_counter_fifty_percent_and_huge_price` | 555 | G5 |
| `PercentileRendererTests.test_preview_detail_shows_frozen_pp_and_migration_origin` | 569 | G5 |
| `PercentileRendererTests.test_incomplete_or_inconsistent_digits_never_invent_a_roll` | 580 | G5 |
| `PercentileRendererTests.test_missing_or_invalid_threshold_is_not_invented` | 596 | G5 |
| `PercentileRendererTests.test_preview_requires_consistent_public_probability_and_valid_fields` | 602 | G5 |
| `PercentileRendererTests.test_v5_projection_excludes_obsolete_and_private_fields` | 611 | G1/G5 |
| `PercentileRendererTests.test_mixed_history_preserves_original_high_roll_records` | 624 | G5 |
| `PercentileRendererTests.test_exact_final_roll_shows_public_counter_base_and_odds` | 639 | G5 |
| `PercentileRendererTests.test_accept_after_percentile_failure_preserves_the_sale_and_history` | 646 | G5 |
| `PercentileRendererTests.test_percentile_refresh_keeps_latest_preview_and_readonly_actions` | 653 | G5 |
| `PercentileRendererTests.test_new_cards_render_all_sizes_without_mutating_or_rerolling` | 667 | G5 |

### test_v2_audit.py (24; current)

| Method | Line | Gate(s) |
|---|---:|---|
| `V2AuditTests.test_week_summary_requires_post_cost_cash_and_distinct_collection` | 66 | G2 |
| `V2AuditTests.test_continue_preserves_assets_and_does_not_charge_twice` | 77 | G2 |
| `V2AuditTests.test_week_summary_blocks_mutations_but_allows_reading` | 88 | G1/G2 |
| `V2AuditTests.test_long_campaign_beyond_week_remains_active_and_events_do_not_repeat` | 99 | G0/G2 |
| `V2AuditTests.test_late_first_week_goal_can_unlock_after_missed_summary` | 112 | G1/G2 |
| `V2AuditTests.test_bankruptcy_does_not_offer_continue` | 127 | G2 |
| `V2AuditTests.test_v1_import_preserves_source_and_committed_hidden_assets` | 137 | G3 |
| `V2AuditTests.test_v1_import_is_deterministic_and_never_rerolls_rng` | 155 | G0/G3 |
| `V2AuditTests.test_v1_paid_last_fee_with_zero_balance_is_continuable` | 162 | G3 |
| `V2AuditTests.test_v1_genuine_bankruptcy_stays_lost` | 174 | G3 |
| `V2AuditTests.test_v1_won_and_missed_results_remain_at_day_seven` | 182 | G3 |
| `V2AuditTests.test_v1_import_refuses_all_existing_destinations` | 193 | G3/G4 |
| `V2AuditTests.test_public_tree_has_no_explicit_private_keys` | 207 | G1 |
| `V2AuditTests.test_public_appraisal_does_not_encode_hidden_base_value` | 224 | G0/G1 |
| `V2AuditTests.test_initial_price_does_not_encode_hidden_base_value` | 233 | G0/G1 |
| `V2AuditTests.test_reads_do_not_mutate_save_bytes_rng_revision_or_event` | 242 | G1/G4 |
| `V2AuditTests.test_invalid_customer_and_resource_failures_do_not_mutate_any_state` | 250 | G1/G2 |
| `V2AuditTests.test_each_customer_and_item_only_get_one_sale_attempt_daily` | 261 | G2 |
| `V2AuditTests.test_display_level_two_adds_visitor_next_day_only` | 276 | G2 |
| `V2AuditTests.test_collection_sets_unlock_after_three_distinct_items_and_perks_apply` | 285 | G1/G2 |
| `V2AuditTests.test_all_upgrades_have_three_levels_and_energy_never_exceeds_cap` | 309 | G1/G2 |
| `V2AuditTests.test_projection_write_error_does_not_report_committed_action_as_failed` | 323 | G4 |
| `V2AuditTests.test_save_failure_before_commit_preserves_money_and_rng` | 345 | G4 |
| `V2AuditTests.test_directory_sync_failure_after_rename_is_reported_as_committed` | 352 | G4 |

### test_v2_engine.py (17; current)

| Method | Line | Gate(s) |
|---|---:|---|
| `ExpansionTests.test_catalog_has_24_unique_entries_and_five_possible_sets` | 50 | G1 |
| `ExpansionTests.test_codex_remembers_discoveries_after_sale` | 58 | G1/G2 |
| `ExpansionTests.test_new_read_commands_do_not_change_private_rng_or_revision` | 68 | G1/G4 |
| `ExpansionTests.test_named_customer_buys_once_and_preference_adds_reputation` | 77 | G2 |
| `ExpansionTests.test_named_refusal_consumes_both_opportunities_and_budget_never_leaks` | 88 | G1/G2 |
| `ExpansionTests.test_display_three_levels_and_extra_guest_next_day` | 99 | G2 |
| `ExpansionTests.test_all_daily_events_apply_visible_costs_energy_and_discounts` | 111 | G0/G1/G2 |
| `ExpansionTests.test_all_five_collection_sets_grant_their_actual_perks` | 125 | G1/G2 |
| `ExpansionTests.test_long_game_continues_well_past_week_and_repeated_goals_have_no_day_cutoff` | 145 | G1/G2 |
| `ExpansionTests.test_milestones_persist_even_when_cash_is_spent` | 160 | G1/G2 |
| `ExpansionTests.test_expanded_validation_rejects_corrupt_fields_without_reset` | 182 | G3 |
| `MigrationTests.test_active_import_preserves_source_bytes_rng_and_sealed_contents` | 214 | G3 |
| `MigrationTests.test_completed_import_stops_before_day8_and_does_not_charge_twice` | 232 | G3 |
| `MigrationTests.test_missed_old_week_can_continue_even_at_zero_cash` | 242 | G3 |
| `MigrationTests.test_bankruptcy_remains_terminal` | 248 | G3 |
| `MigrationTests.test_same_path_existing_target_and_projection_are_never_overwritten` | 257 | G3/G4 |
| `MigrationTests.test_corrupt_or_public_source_fails_without_destination_save` | 274 | G3/G4 |

## 8. Recommended next checkpoint

Implement and prove G1-01 through G1-10 first, then all accepted-domain projection/timing cases G1-11 through G1-18. A small first tranche can ship only as a visibly synthetic route with an explicit action whitelist and no real-save import. Report concrete differential and phone-route results separately. Proceed to native trading/repair only after the primitive stream and full-state comparison harness are trustworthy; retain G3/G4/G5 as independent gates rather than folding them into a misleading “full port” label.
