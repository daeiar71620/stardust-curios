# Stardust Curios

> Source-release status: this complete integration has **not been deployed**. The actual remotely edited Site source identified as `6f03a60a` still needs reconciliation, and final phone/desktop browser QA remains open. Follow [the Site editor handoff](docs/SITE_EDITOR_HANDOFF.md); do not replace the remote app from a stale local checkout.

A small private AI-run shop game with a read-only phone spectator. The current
TypeScript rules run inside the Site: an operation atomically commits private
state, its public projection and an idempotent receipt to D1. The phone reads that
same public projection. There is no post-action upload process.

## Source layout

- `lib/game-engine/`: the single authoritative TypeScript rules implementation
- `lib/game-authority.ts`: identity-scoped revision checks, atomic commits and receipts
- `app/mcp/`: current and initialization-based MCP transport with three game tools
- `app/viewer.tsx`: read-only phone/desktop spectator
- `assets/server-art/`: private source illustrations; never static web assets
- `scripts/build-art.mjs`: verified, reproducible server-only artwork module generation
- `reference/python/`: latest-only Python reference and renderer for offline verification
- `tests/engine/`: synthetic comparisons against that independent reference

Current game rules remain version 9. Old game formats, migration commands, D20
history and collection-transition grace are unsupported. Transport compatibility
for existing connected MCP clients is separate from game-save compatibility.

## Local checks

Use the supported Sites runtime and Node 22.13+ (Node 24 recommended for tests),
Python 3 and the pinned Pillow dependency for renderer checks.

```sh
npm run build:art
npm run check
npm run test:site
npm run test:engine
npm run build
```

`test:engine` is a long synthetic differential suite. It creates no real game
state and reads no user saves. See docs/ENGINE_VALIDATION.md and the reference
QA report for counts, numeric limits and reproducibility. Native state rejects
non-null historical provenance; the 39-field public contract remains stable.

## Playing through the connected Site

The stable tools are `stardust_game_state`, `stardust_game_query`, and
`stardust_game_action`. Read current revision before choosing an action. A chosen
action supplies one unique operation ID and expected revision. If its response
is uncertain, retry exactly that ID and those arguments. A duplicate returns the
original receipt and never repeats the game action.

`initialize` explicitly starts a new game: args `[]` or `["test"]` creates a test
game; `["formal"]` creates a formal game only when the user asks after testing.
Previous state is retained privately in the database before replacement, in the
same transaction. Authority revisions remain monotonic across new games, so old
requests cannot become valid again. Seeds are server-generated and never accepted
from clients. There is no autoplay, arbitrary-save upload or import endpoint.

The observer has inventory, customers, catalog, collections, facilities, log and
dice views. Visible pages check for changes every 2 seconds, use conditional
responses, and distinguish connection health from the last game-action time.
Gameplay stays in chat; page buttons only navigate or inspect public information.

## Illustrations and privacy

All 24 original Pillow illustrations are prepackaged privately with verified
hashes. An authenticated image request must first match the current game's
discovered catalog. Unknown IDs and stale game IDs are rejected before private
asset or cache access. Only then may an image be served from the private R2 cache
or bundled seed. Cache corruption/outage falls back to the verified seed and
never rolls back a game action. R2 writes are not part of the D1 transaction.

The browser receives no private RNG, hidden budgets, sealed cargo or complete
catalog asset manifest. The public source repository contains game source and
synthetic art, not any player's state, credentials or Site ownership settings.

## Deployment and limits

Use the supported Sites flow for the intended existing private Site. The hosting
manifest here is generic and contains no owner/project identity. Reconcile the
actual remote source before updating an existing Site, retain its hosting
identity/access configuration, then save and deploy the exact verified build.
A local build or source backup is not a deployment.

`drizzle/` preserves applied migration history. Retired mirror/counter tables are
left recoverable and have no live application routes; cleanup never silently
purges data. The historical physical native-table names also preserve existing
operation receipts. New games never accept old rule versions.

Known numeric limit: a small set of engineered arbitrary floating-point references
differs between V8 and CPython log2. Tested reachable item references and long
campaigns match; the explicit numeric TODO is retained rather than hidden.

The current integration still needs a final remote-source reconciliation, native
Sites publication and live full-spectator verification. Local Chromium visual
QA was unavailable where process sockets were denied; synthetic render/sync tests
are separate evidence and do not claim a screenshot was inspected.
