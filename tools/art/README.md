# Server-private Stardust illustration source

This package contains all 24 existing public-renderer illustrations as transparent,
512 × 512 RGBA PNGs. It is an engineering asset source, **not a browser asset
folder or a public catalogue**. Serve individual images only after authentication
and an authoritative discovered-ID check.

The art was drawn by the existing Pillow `Renderer.item_art` implementation,
supersampled at 1024px and reduced with Lanczos. It preserves the original
silhouettes, navy shadows and supporting colors. Every input item is synthetic,
using only its public catalogue identity/name/kind/rarity and the canonical public
rarity color: common `#8ed4cb`, rare `#b7a2ff`, legendary `#ffd17a`. The set contains
10 common, 9 rare and 5 legendary illustrations. No live inventory or discovery
state is read. `discovered: true` here is a drawing switch only; it grants no player
permission. This matches the explicit `color: COLORS[item['rarity']]` emitted by
the public item projection, rather than the renderer's fallback mint.

## Files

- `../../assets/server-art/png/`: the 24 production source PNGs
- `../../assets/server-art/manifest.json`: dimensions, provenance and per-file SHA-256 hashes
- `generate_private_art.py`: deterministic generation from the public drawing code
- `verify_private_art.py`: five integrity and reproducibility tests
- `build_private_contact_sheet.py`: optional local visual QA utility
- `requirements.txt`: pinned Pillow dependency
- `qa-only/`: ignored local contact sheet and size metrics; never deploy or publish it

The manifest and generator include the entire illustration-ID set. Keep them in
server/build source. Do not import either into a client bundle, copy this directory
under a static asset root, expose the complete manifest, or put the QA sheet in a
web payload. Packaging should explicitly select the needed server inputs rather
than recursively copying this whole directory.

## Rebuild and verify

Python 3.10+ and Pillow 12.3.0 are required. From the application root, using its offline reference sources:

```sh
python tools/art/generate_private_art.py --renderer reference/python/spectator.py --catalog reference/python/engine.py --output assets/server-art
python tools/art/verify_private_art.py --renderer reference/python/spectator.py --catalog reference/python/engine.py --art-dir assets/server-art
python tools/art/build_private_contact_sheet.py --art-dir assets/server-art --output qa-only/private-contact-sheet.png
```

The generator accepts no game-state or observation input and uses no network. It
parses the source and loads only drawing constants, `as_dict`, `safe_color`, and
the seven drawing methods needed for `item_art`. Public `CATALOG` and `COLORS`
assignments are read using `ast.literal_eval`; only identity/name/kind/rarity/color
fields are retained as synthetic paint. Reader, GUI, catalogue views and engine
code are not imported or executed. Changes to that drawing interface fail
closed for review. Filenames and manifest JSON have no timestamps or local source
paths. Repeated rendering produced identical hashes in the pinned environment;
different Pillow/compression-library versions may require an intentional rebuild.

## Size and serving choice

Measured output:

| Payload | Bytes |
| --- | ---: |
| 24 PNGs | 1,038,671 |
| Smallest / largest PNG | 29,752 / 58,413 |
| Mean PNG | 43,278.0 |
| Compact base64 JSON map, all 24 | 1,385,201 |
| Gzip of that JSON map, for reference | 1,035,646 |

512px assets work well for roughly 160–240 CSS-pixel phone cards and retain useful
detail in a larger object view. Use `object-fit: contain` and the original dark
palette. Load only images for currently discovered objects, preferably lazily;
a phone should not fetch the full catalogue on opening the spectator.

At this scale, a private Worker seed is practical and avoids a separate asset
provisioning dependency. Bundle the bytes or a private base64 module into the
server only. Decode only the authorized requested image and retain a bounded
in-memory cache if useful; avoid decoding the whole set at Worker startup.

As checked on 2026-10-07, Cloudflare documents a 64 MiB **uncompressed** Worker
bundle limit and no compressed-size limit. Its separate startup budget still
matters. Measure the final application with `wrangler deploy --dry-run`; these
asset measurements are not a deployment verification. See the official
[Worker size limits](https://developers.cloudflare.com/workers/platform/limits/#worker-size)
and [startup limits](https://developers.cloudflare.com/workers/platform/limits/#worker-startup-time).

A private, pre-staged R2 cache is also reasonable if the art grows. Use immutable
SHA-256-based keys and verify uploaded bytes against the manifest. Keep public
bucket access disabled and serve through the same authorized Worker route.
All 24 illustrations may exist privately in R2, while only discovered IDs can be
served. An R2 cache hit never replaces authorization.

R2 and D1 do not form one transaction. Discovery state belongs to the authoritative
D1 transaction; immutable art publication can happen independently before use.
A Worker seed can remain the read fallback on an R2 miss. A missing asset must not
roll back, repeat, or falsely acknowledge a game mutation. This package performs
no R2 upload, deployment, credential setup or database write.

## Discovery boundary for integration

1. Authenticate the spectator request
2. Read the relevant authoritative state and derive its currently discovered IDs
3. Require the requested ID to be in that set before consulting the private seed
   or R2, including conditional/ETag requests
4. Return an individual PNG with correct content type and private cache policy;
   return the same generic unavailable response for unknown and undiscovered IDs
5. Send only discovered image URLs/hashes to the client; do not send hidden IDs,
   private storage keys, a complete art manifest, or a fallback catalogue

For the simplest safe response policy, use `Cache-Control: private, no-store`
until session-scoped caching and revocation semantics have been tested. Do not
redirect the browser to an anonymously accessible object store.

## Validation result

Five tests passed: exactly 24 expected files with no preview payload; canonical
rarity colors, manifest hashes/sizes and safe names; 24 distinct nonblank
transparent pixel images; stable
hashes on a second render; and absence of reader/GUI/catalogue interfaces from the
loaded drawing module. Every PNG is free of extra metadata. The private contact
sheet and representative full-size cat/map/whale images were inspected locally. Shapes
remain distinct at 160px, and their transparent backgrounds compose cleanly onto
the original navy panels. All 24 content hashes changed from the earlier default
mint export, confirming the canonical public paint is materially different.
