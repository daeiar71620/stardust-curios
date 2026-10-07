/** Read-only current-protocol synchronization. No engine or catalogue dependency. */
export const POLL_MS = 2000;
export const MAX_RETRY_MS = 30000;
export const REQUEST_TIMEOUT_MS = 8000;
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
export function validateSnapshot(next) {
  if (!object(next) || typeof next.initialized !== 'boolean' || !['test', 'formal'].includes(next.mode) || typeof next.stream_id !== 'string' || !next.stream_id ||
      !Number.isSafeInteger(next.revision) || next.revision < 0 || typeof next.build !== 'string' || !next.build ||
      !(next.updated_at === null || typeof next.updated_at === 'string' && Number.isFinite(Date.parse(next.updated_at)))) return false;
  if (!next.initialized) return next.observation === null;
  const o = next.observation;
  return object(o) && o.version === 9 && o.revision === next.revision && Number.isSafeInteger(o.day) && o.day >= 1 &&
    ['active', 'week_summary', 'lost'].includes(o.phase) &&
    ['credits', 'reputation', 'energy', 'max_energy', 'capacity', 'operating_cost'].every(key => Number.isFinite(o[key])) &&
    ['inventory', 'collection', 'crates', 'suppliers', 'visitors', 'log', 'roll_history', 'collection_sets', 'upgrade_details'].every(key => Array.isArray(o[key])) &&
    object(o.codex) && Array.isArray(o.codex.entries) && object(o.campaign) && object(o.campaign.next_milestone) && Array.isArray(o.campaign.next_milestone.goals) &&
    object(o.collection_progress) && Array.isArray(o.collection_progress.categories) && Array.isArray(o.collection_progress.requirements) && Array.isArray(o.collection_progress.missing) &&
    object(o.walkins) && object(o.daily_event) && object(o.demand) && object(o.stats) && object(o.trade_rules);
}
export function acceptSnapshot(previous, next, retiredStreams = new Set()) {
  if (!validateSnapshot(next)) return { accepted: false, reason: 'invalid' };
  if (!previous) return { accepted: true, reason: 'initial' };
  if (next.stream_id !== previous.stream_id) return retiredStreams.has(next.stream_id)
    ? { accepted: false, reason: 'retired_stream' } : { accepted: true, reason: 'new_stream' };
  if (next.revision < previous.revision) return { accepted: false, reason: 'older_revision' };
  return { accepted: true, reason: next.revision > previous.revision ? 'advanced' : next.build !== previous.build ? 'new_build' : 'unchanged' };
}
export function retryDelay(failures) { return Math.min(MAX_RETRY_MS, POLL_MS * 2 ** Math.min(4, Math.max(0, failures - 1))); }
export function knownImagePath(item, snapshot) {
  if (!snapshot?.initialized || item?.discovered === false || typeof item?.art_id !== 'string' || !/^[a-z0-9_-]{1,60}$/.test(item.art_id)) return null;
  return `/api/game/art/${encodeURIComponent(item.art_id)}?stream=${encodeURIComponent(snapshot.stream_id)}&v=${encodeURIComponent(snapshot.build)}`;
}
/** Resolve selections against each accepted state, so a sold item cannot show stale details. */
export function resolveDetail(observation, selection) {
  if (!observation || !selection) return null;
  if (selection.type === 'item') {
    const item = [...observation.inventory, ...observation.collection].find(item => item.id === selection.id);
    return item ? { type: 'item', item } : null;
  }
  const entry = observation.codex.entries.find(entry => entry.slot === selection.slot);
  return entry?.discovered === true ? { type: 'catalog', entry } : null;
}
/** Single-flight fetches; disposal and retired streams also reject delayed responses. */
export function createSpectatorSync({ fetcher = fetch, now = Date.now } = {}) {
  let state = { snapshot: null, status: 'loading', checkedAt: null, checking: false, failures: 0, imageEpoch: 0, notice: null };
  let etag = null, inFlight = null, controller = null, generation = 0, disposed = false;
  const retiredStreams = new Set(), listeners = new Set();
  const emit = patch => { state = { ...state, ...patch }; for (const listener of listeners) listener(); };
  const request = () => {
    if (disposed) return Promise.resolve(state);
    if (inFlight) return inFlight;
    const requestGeneration = generation;
    controller = new AbortController();
    const signal = controller.signal;
    const timeout = setTimeout(() => controller?.abort(), REQUEST_TIMEOUT_MS);
    emit({ checking: true });
    inFlight = (async () => {
      try {
        const response = await Promise.resolve().then(() => fetcher('/api/game/state', { cache: 'no-store', credentials: 'same-origin', signal, headers: etag ? { 'If-None-Match': etag } : {} }));
        if (disposed || requestGeneration !== generation) return state;
        if (response.status === 401) { emit({ status: 'unauthorized', checking: false }); return state; }
        let next = state.snapshot, decision;
        if (response.status === 304) {
          if (!next) { etag = null; throw new Error('not_modified_without_snapshot'); }
          decision = { accepted: true, reason: 'unchanged' };
        } else {
          if (!response.ok) throw new Error(`state_http_${response.status}`);
          next = await response.json();
          if (disposed || requestGeneration !== generation) return state;
          decision = acceptSnapshot(state.snapshot, next, retiredStreams);
          if (decision.reason === 'invalid') throw new Error('invalid_public_snapshot');
        }
        if (!decision.accepted) {
          // A stale response must not poison the next conditional request.
          emit({ status: 'connected', checkedAt: now(), failures: 0, notice: 'stale_response' });
          return state;
        }
        if (state.snapshot && next.stream_id !== state.snapshot.stream_id) retiredStreams.add(state.snapshot.stream_id);
        if (response.status !== 304) etag = response.headers?.get?.('etag') || null;
        const recovered = state.status !== 'connected';
        emit({ snapshot: next, status: 'connected', checkedAt: now(), failures: 0, notice: null, imageEpoch: state.imageEpoch + Number(recovered) });
      } catch {
        if (!disposed && requestGeneration === generation) emit({ status: 'reconnecting', failures: state.failures + 1 });
      } finally {
        clearTimeout(timeout);
        if (!disposed && requestGeneration === generation) { inFlight = null; controller = null; emit({ checking: false }); }
      }
      return state;
    })();
    return inFlight;
  };
  return {
    getSnapshot: () => state,
    subscribe(listener) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    request,
    retryImages() { if (!disposed) emit({ imageEpoch: state.imageEpoch + 1 }); },
    dispose() { disposed = true; generation++; controller?.abort(); listeners.clear(); },
  };
}
