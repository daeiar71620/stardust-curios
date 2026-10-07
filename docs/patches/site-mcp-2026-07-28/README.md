# Undeployed Site MCP protocol patch

This folder is a **source backup only**. It is not deployed, not a plugin-update ZIP, and not a patch for the game engine in this repository. No Site publishing, tool registration, permission changes, or runtime operations were performed to create this backup.

## Exact target

- Target project: the separately maintained Site application source
- Required Site base commit: `f8b96416f75c18aa06947d4f26fc8b5c1929adde`
- That hash belongs to the separate Site checkout, **not this public game repository**
- Patch paths: `app/mcp/route.ts`, `tests/mcp-protocol.test.mjs`, `docs/MCP_PROTOCOL.md`

Do not apply this patch at the root of the public game repository. A future authorized installation must first confirm the correct Site checkout and base, then check patch applicability there. Deployment and production verification remain separate steps.

## Purpose and validation

The patch adds per-request MCP `2026-07-28` handling, including `server/discover`, while retaining the existing legacy handshake and trusted identity checks. It changes generic route, test, and protocol documentation only.

The frozen validation record reports:

- 17 focused protocol tests passed, included in 27 total Site JavaScript tests
- 30 legacy authority/route/privacy test groups passed
- TypeScript, scoped ESLint, whitespace/diff checks, and the production build passed
- A standards-conformant synthetic discovery request changed from a prepatch 400 response to a patched 200 response

These are local validation results, not proof of a production fix. The original production request body was unavailable, so the regression is not an exact packet replay. The production root cause remains unconfirmed; deployment, successful production discovery, and refreshed plugin/tool registration are unverified.

## Files and integrity

- `modern-mcp.patch`: unchanged validated patch bytes
- `VALIDATION.json`: unchanged frozen implementation validation record
- `VERIFICATION.json`: publication-side hashes, scope and patch-format verification

Patch SHA-256: `98668bb82b80cc33dcf2586ad738eac704ee7baf4ab9754b7de143298a75b97d`

The backup excludes private Site configuration/manifests, environment paths, account identifiers, credentials, saves, actual game state, and generated deployment archives. The source patch contains only generic protocol examples and synthetic test destinations. No game rules, database contents, saved state, identity model or sharing settings are changed by this backup.
