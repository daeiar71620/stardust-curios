import { env } from 'cloudflare:workers';
export function getDatabase() { if (!env.DB) throw new Error('Database unavailable'); return env.DB; }
export function getBucket() { if (!env.BUCKET) throw new Error('Artwork unavailable'); return env.BUCKET; }
