# MCP request compatibility

The `/mcp` handler supports the new per-request `2026-07-28` protocol alongside
its existing initialization-based POST client flow. Game save compatibility is
separate; this transport change enables no game imports or resets.

Modern requests supply a non-null string/integer request ID, protocol version
and client capabilities in `params._meta`, and matching HTTP version/method
headers. Tool calls also need a matching tool-name header. The header decoder
supports the specified UTF-8 Base64 sentinel. Client metadata never supplies the
authenticated user identity.

`server/discover` and `tools/list` return complete results with `ttlMs: 0` and
`cacheScope: private`. They expose the same single tool definition list as the
legacy path and never read state. These cache hints do not guarantee that a
hosting platform refreshes its stored plugin metadata. State-bearing requests
still pass through the existing trusted Site user-header gate, input validators
and atomic authority layer. Invalid Origin, oversized bodies and wrong content
types remain rejected. New protocol errors use the specified JSON-RPC codes;
ordinary game failures remain completed tool results with `isError: true`.

Legacy requests keep their earlier initialize/initialized and response shapes.
The preserved `2024-11-05` version identifier is an existing client-compatibility
path, not a claim that the original HTTP+SSE transport is implemented. The server
does not advertise modern subscriptions or emit list-change notifications.

## Verification

Run `node --test tests/mcp-protocol.test.mjs`, TypeScript and scoped ESLint checks.
The test uses only synthetic requests and mocked state handlers. It covers modern
discovery, shared tool definitions, header/body consistency, authorization and
legacy initialization. The original production request body was unavailable, so
these synthetic cases do not constitute an exact production packet replay.

A successful local check or build does not establish deployment, production
discovery, or refreshed plugin registration. Those require separate evidence.

## Normative sources

- https://modelcontextprotocol.io/specification/2026-07-28/server/discover
- https://modelcontextprotocol.io/specification/2026-07-28/basic/index
- https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning
- https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http
- https://modelcontextprotocol.io/specification/2026-07-28/server/tools
- https://modelcontextprotocol.io/specification/2026-07-28/server/utilities/caching
