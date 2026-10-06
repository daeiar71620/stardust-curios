# Hosted synthetic gates

The deployment lives in a separate owner-private Site checkout. This portable
package contains neither that account configuration nor credentials.

## Established before G2

- Counter lab: a connected chat tool committed a synthetic increment and the
  user confirmed the new value on a phone
- G1: initialize, salvage purchase and opening committed through the connected
  chat tool into D1. A subsequent read and the user phone check saw the same
  revision 3 state. That proves the selected connected chat and phone route

## G2 adapter contract

The same synthetic state/receipt tables are reused, so G1 receipts remain valid.
No migration or copy of the real game is part of this gate. The native dispatcher
remains strict v9 with null provenance; import/restart/reset endpoints are absent.

- `stardust_core_test_state`: public state and revision
- `stardust_core_test_query`: command and string args, one of status, market,
  codex, visitors, inspect, preview-offer
- `stardust_core_test_action`: operation_id, expected_revision, command, args;
  initialize once, then the 13 native mutations

Mutations atomically CAS private state, public projection and receipt in one D1
batch. A matching duplicate returns the stored receipt; conflicting parameters
or revisions fail. Platform-authenticated identity scopes every record. Read
queries return only public results and consume no RNG. The final-price preview
is returned to the chat but does not replace the phone's default preview.

The simple phone page at `/lab/core` polls its public endpoint every 2 seconds. It
shows inventory, sealed-box placeholders, collections, goals, negotiations and
dice. Image staging and the complete spectator interface remain separate gates.

Local synthetic SQL/adapter checks cover all 13 actions and 6 reads, legacy receipt
replay, concurrent CAS, duplicates, rollback and hidden-field filtering. The
production client build was checked for all 24 catalog names: none were present.
Deployment success and subsequent live tools must be recorded separately; local
checks alone do not establish hosted Worker parity or arbitrary chat access.
