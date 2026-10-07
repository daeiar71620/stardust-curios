# Existing Site editor handoff: reconciliation before publication

This is a validated public source release. It is not a deployment, a backup of the actual private Site configuration, or proof that the final spectator has been inspected in a browser. The remotely edited source identified as `6f03a60a` has not been reconciled with this release.

## 1. Establish the actual remote baseline

Use the supported editor/source access for the intended existing private Site. Retrieve its actual current source and full commit identifier. Confirm whether `6f03a60a` is still current; if a newer commit exists, use that newer source. Include edits made in other editor sessions.

Do not substitute a stale local Site checkout or an older exported base. If current remote bytes cannot be retrieved, stop before overwriting or publishing and report the missing source-access step. Keep this public source backup available independently.

## 2. Preserve private identity, authorization and data

Reconcile source changes against the actual remote baseline before replacing files. Identify unrelated remote edits and preserve them; resolve any conflicting intended behavior before continuing.

The public `.openai/hosting.json` is deliberately generic. Preserve the existing Site/project identity, owner-private visibility, authentication middleware and trusted identity source, account-scoped access checks, D1 and R2 bindings, secrets, private runtime settings and applied migration history. Never copy private configuration or credentials into this public repository. Do not weaken authentication, change sharing, add a new connection or replace storage to make a check pass.

Keep the existing physical authority tables and operation receipts. The checked-in migrations preserve history; do not reset databases, drop retired tables, erase archives, reinitialize player state or apply an unreviewed destructive migration. Removing obsolete source routes is not authorization to purge stored data.

## 3. Revalidate the reconciled source

Keep one canonical rules implementation at `lib/game-engine/`; `reference/python/` is an offline oracle, not another deployed runtime. Do not restore old manual-upload flows, import commands, legacy game formats, or experimental runtime entrypoints while merging. Preserve transport compatibility separately from game-format support.

Run the reproducible artwork build, TypeScript/ESLint checks, Site tests and the production build against the reconciled source. If rule, projection, validation or RNG files change, rerun the relevant differential suites and the full engine/reference gates before publishing. Compare the client bundle against hidden catalog names and image markers, and confirm that only the client output is statically served. Server artwork and state must remain server-only.

The release baseline is 2,543 distinct passing checks plus one documented arbitrary-float log2 TODO, with 61 Site tests passing again after clean ZIP extraction. Preserve the TODO and its bounded domain description; do not call it universal floating-point equivalence.

## 4. Publish only the verified source through the supported flow

Within the user's authorized project scope, save the reconciled source to the intended existing Site and deploy the exact verified build using its supported publish workflow. Record the source commit and deployment result. A local build, a GitHub commit or an editor save does not establish that deployment succeeded.

If the supported publishing tools are unavailable or deny access, report that blocker. Do not substitute another route, broaden access, reset identity, or create a parallel Site to bypass it.

## 5. Verify the newly deployed tool and storage path

Confirm discovery of exactly the current game tools: `stardust_game_state`, `stardust_game_query`, and `stardust_game_action`. Test the appropriate current/legacy MCP transport with the existing authenticated identity. A tools-list refresh alone is not evidence of successful gameplay.

Read the current state and revision. Use only a bounded user-authorized synthetic/test game for mutation checks. Verify an expected-revision conflict, one chosen mutation, and replay of the identical operation ID/arguments returning the original receipt without another state change. Never generate a fresh ID merely because a reply was lost. Recheck the public state and receipt from the same authority.

Do not start a formal game merely to perform QA. Any new game must use the user-approved mode and scope after the deployment gates pass; this source publication does not itself initialize or replace a game.

## 6. Complete actual phone and desktop browser QA

Inspect real browser pixels at phone and desktop widths. Verify inventory, customers, catalog, collections, facilities, log and dice views; item details; repeated navigation; Close/Back/Forward behavior; and resizing without clipping. Check a real observed update after the bounded test action, conditional polling while visible, last-action time versus connection status, and recovery after a temporary connection interruption.

Check that undiscovered catalog entries have the same unknown presentation and cannot be fetched by guessed ID. Authenticated artwork reads must enforce current game identity and discovery before private asset/cache access. Check stale game IDs, unauthorized access, changed/failed R2 cache paths and verified bundled-image fallback without replaying gameplay.

The earlier local Chromium attempt was blocked by a process-socket restriction. Synthetic synchronization/render checks and a successful build do not replace these browser checks. Record screenshots only after the corresponding screen was actually inspected; if the browser remains blocked, report the unverified views rather than marking this gate complete.

## Completion evidence

Report the reconciled full remote source commit, successful deployment identifier, exact test results/TODO, tool discovery and bounded state/receipt checks, inspected phone/desktop views, and any remaining blockers. Keep private identifiers, state and screenshots in the authorized private conversation or storage; this public handoff contains no account, credential or player data.
