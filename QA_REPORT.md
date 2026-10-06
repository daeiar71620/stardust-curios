# v5 Verification Report

Verified 2026-10-06 using isolated synthetic games and public-only UI fixtures.
No private player save was read or modified, and no real game was imported or advanced. Original source releases remain separate. No repository push or deployment was performed.

## Automated verification

- Final aggregate: `python3 -m unittest discover -v` — **261 tests passed**, 27.057 seconds
- `python3 -m py_compile *.py` — passed
- Breakdown: 69 core/shop tests; 74 retained legacy D20/v4 regressions against the frozen `_legacy_v4` module; 24 native v5 tests; 28 independent percentile audit tests; 66 viewer/projection tests
- The independent audit found no engine defects. Its focused checks used temporary synthetic saves only

Coverage includes all 100 ordered D10 digit pairs; the 00+0→100 convention; roll-low thresholds; 01 success at legal price 9999 beyond budget; 100 failure; exact final success counts across every possible result; native first-offer price sensitivity; final-premium monotonicity and ratio scaling; frozen percentage-point bonuses; public-only previews; deliberate lack of a second hidden final-budget gate; strict price bounds; free accept/decline; one paid retry; failed-quote expiry; RNG persistence; save-write rollback; projection recovery; competing final-offer locking; copy-only v1–v4 imports; retained D20 rule provenance; pending legacy counter preservation; and 60-record mixed-history boundaries.

## Formula examples

With zero bonus, final base chance is 70%:

- Counter 150 → final 165: 10% premium, threshold 58, exactly 58% success
- Counter 150 → final 225: 50% premium, threshold 35, exactly 35% success
- Counter 150 → final 9998: threshold 1, exactly 1% success
- Packaged preview fixture counter 70 → final 100: 42.857% premium, threshold 37, exactly 37% success

Final arithmetic is integer `base * counter // (2 * price - counter)`, clamped to 1–99 after clamping the base. These probabilities include 01; 100 always fails.

## Synthetic campaign smoke

`python3 smoke_public_campaign.py` ran 30 independent synthetic 40-day campaigns using a public-observation-only shop policy. All 30 reached day 41; none became bankrupt. Across 4603 rolls there were 43 critical 01 results, 45 fumbles, and 637 accepted counteroffers. Ending cash ranged 5595–7819, median 6545. This is regression smoke, not a proof of economic balance or a recommendation for real play.

## Read-only viewer

All 66 viewer tests passed, including new and legacy records, malformed public inputs, both D10 faces, combined results, low-roll thresholds, exact previews, mixed rule history, details/refresh/dismiss flows, and renderer sizes 1320×940, 760×1240, 390×844 and 320×568. The viewer has no gameplay controls and reads only public observations.

Focused actual cloud-desktop GUI spot-check passed. The preview card and detail were readable at a native 390-pixel window width and both showed the correct 37% for the packaged preview. Critical 01 showed separate 00 and 1 faces, combined 01, and a 9999 sale. Fumble 100 showed separate 00 and 0 faces and failed even against threshold 99. The mixed journal and detail distinguished original v4 high-roll D20 rules from v5 low-roll D100 rules. Demonstration windows were closed and the pre-existing live spectator was restored; no gameplay or private-save access occurred. Native CUA captures were inspected but were not saved as local files.

Packaged PNGs in `ui-qa/` are public-only headless renders:

- `preview-narrow.png`: packaged counter 70/proposed 100/37% preview at 390×930
- `fumble100-wide.png`:00+0→100 at 1320×940
- `mixed-history-wide.png`: original v4 D20 and new v5 D100 records at 1320×940
- `ten-percent-example-narrow.png`: a separate, explicitly synthetic UI specimen showing counter 150/proposed 165/58%; it is not a player save

## Distribution boundary

The release contains source, frozen legacy validators, documentation, tests, 13 intentional public JSON fixtures, their generated playthrough, and public-only screenshots. It excludes private saves, root observation files, backups, locks, runtime caches, personal state, and environment credentials. Opening the spectator does not create or migrate a game. v1–v4 imports require an explicit command and a new target path; the historical game remains untouched.
