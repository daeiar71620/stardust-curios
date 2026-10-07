import {getBucket} from '@/db';
import {gameState} from './game-authority';
import {SiteError} from './site-auth';
import {sha256Bytes} from './hash';
import {ART_VERSION, PRIVATE_ART_METADATA} from './server-art-manifest';
import type {PublicRecord} from './game-engine/index';

/** Gate BEFORE importing private illustrations or consulting the R2 cache. */
export async function discoveredArtwork(user: string, id: string, stream?: string | null) {
 if (!/^[a-z0-9_-]{1,48}$/.test(id)) throw new SiteError('art_not_found', 404);
 const state = await gameState(user);
 if (state.unchanged || !state.body.initialized || (stream && stream !== state.body.stream_id)) throw new SiteError('art_not_found', 404);
 const observation = state.body.observation;
 const codex = observation?.codex as PublicRecord | undefined;
 const entries = codex?.entries;
 if (!Array.isArray(entries) || !entries.some(entry => entry && entry.discovered === true && entry.art_id === id)) throw new SiteError('art_not_found', 404);
 const asset = PRIVATE_ART_METADATA[id];
 if (!asset) throw new SiteError('art_not_found', 404);
 const key = 'illustrations/' + ART_VERSION + '/' + id + '.png';
 // This cache is independent of game commits. A cache failure must not block play.
 try {
  const cached = await getBucket().get(key);
  if (cached) {
   const bytes = new Uint8Array(await cached.arrayBuffer());
   if (await sha256Bytes(bytes) === asset.sha256) return {bytes, digest: asset.sha256};
  }
 } catch { /* Return the already-packaged illustration below. */ }
 const {PRIVATE_ART} = await import('./server-art-data');
 const bytes = Uint8Array.from(atob(PRIVATE_ART[id].base64), char => char.charCodeAt(0));
 try { await getBucket().put(key, bytes, {httpMetadata: {contentType: 'image/png'}}); }
 catch { /* Artwork remains available even when private cache storage is offline. */ }
 return {bytes, digest: asset.sha256};
}
