import type {DetailSelection, DetailValue, PublicArt, PublicObservation, SpectatorSnapshot} from './spectator-types';
export const POLL_MS: number;
export const MAX_RETRY_MS: number;
export const REQUEST_TIMEOUT_MS: number;
export interface SyncState { snapshot: SpectatorSnapshot | null; status: 'loading' | 'connected' | 'reconnecting' | 'unauthorized'; checkedAt: number | null; checking: boolean; failures: number; imageEpoch: number; notice: 'stale_response' | null }
export interface SpectatorSync { getSnapshot(): SyncState; subscribe(listener: () => void): () => void; request(): Promise<SyncState>; retryImages(): void; dispose(): void }
export function validateSnapshot(next: unknown): next is SpectatorSnapshot;
export function acceptSnapshot(previous: SpectatorSnapshot | null, next: unknown, retiredStreams?: Set<string>): {accepted: boolean; reason: string};
export function retryDelay(failures: number): number;
export function knownImagePath(item: PublicArt, snapshot: SpectatorSnapshot | null): string | null;
export function resolveDetail(observation: PublicObservation | null, selection: DetailSelection | null): DetailValue | null;
export function createSpectatorSync(options?: { fetcher?: typeof fetch; now?: () => number }): SpectatorSync;
