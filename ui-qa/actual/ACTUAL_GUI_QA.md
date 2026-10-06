# v6 limited-customer actual GUI QA

Verified 2026-10-06 using the cloud Linux desktop and the real Tk spectator window. Only public synthetic observations were used. No engine gameplay, private-save access, actual-game advancement, or Codex launch was performed.

## Result

Focused new-feature checks passed. No blocking GUI defect found.

- Ready fixture: ordinary visitor quota 1/1 and public budget 60–120 are visible. A 90-price, 80%-condition item is eligible for a counteroffer after ordinary failure. A 9999-price item clearly warns of direct departure and states the public-reference and budget ceiling reasons. A 30%-condition item clearly shows the unmet 45% minimum.
- Sale-detail buyer paging works and shows invited-customer budget, matching preference, and condition eligibility.
- Quota-used fixture: 0/1 remains visible and ordinary-buyer options show currently unavailable, including other inventory items. The expanded management event explains the high-price rejection, zero income, retained goods, and spent daily reception. No fictitious pending counteroffer appears.
- Pending fixture: 90 → 40 quote, free acceptance, 41 example final price, 66% final success, one-energy cost, and loss-of-old-quote risk are shown.
- Accepted fixture: pending negotiation and inventory clear. Credits become 300, energy stays 11/12, reputation becomes 1; the event says the 40 quote was accepted without another roll or energy charge.
- Grandfathered v5 quote, retested after the clarification patch: main card and quote detail explicitly state that v6 honors the v5 promised quote. The 9999 → 70 quote remains free to accept, with legal final-price range 71–9998 and a 71 example at 68% success. The inventory detail explicitly says the new pre-sale conditions do not revoke the existing quote and that new sales are temporarily unavailable.
- Actual narrow resize to 390×812: ready sale detail, grandfathered main card, grandfathered sale detail, and grandfathered quote detail remain readable, without text overlap or clipped navigation. Wide verification used the actual 1180×812 window.

## Evidence handling

Actual 390-pixel-wide captures of the ready sale conditions and the preserved v5 quote detail were inspected during verification. The generated screenshots were removed after testing and are not distributed with this report.

The desktop window manager initially imposed 1180×812 regardless of launch geometry; narrow coverage was established by actual mouse resizing, with window inventory confirming width 390.

## Preservation

All demo windows were closed. The pre-existing non-demo spectator was restored and visually checked as unchanged. No real-game commands or writes were made. No personal game-state values are included in this release report.

Final spectator.py SHA-256 checked after legacy-quote retest: `70925f59ca96fc2dc3be7ba8068636563a29d9e51816a5a18d42fcb29b856f60`.

This was focused GUI verification, not a new comprehensive engine or framework test run.
