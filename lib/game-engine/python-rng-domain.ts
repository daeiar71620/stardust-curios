/** Domain-separated CPython-compatible RNG derivation for Stardust walk-ins. */
import { PythonRandom } from './python-random.ts';
/**
 * Exact json.dumps(state, separators=(',', ':')) for the game's RNG states.
 *
 * MT words and the index are uint32-sized integers, whose JS/Python decimal JSON
 * encodings agree. The game never calls gauss(), so its Gaussian cache is null.
 * Reject other caches rather than silently hashing JS's different float format
 * (for example, 1 versus Python's 1.0, or 0 versus Python's -0.0).
 */
export function serializePythonRandomState(state: unknown): string {
    const validated = PythonRandom.fromState(state).getstate();
    if (validated[2] !== null) {
        throw new TypeError('walk-in derivation requires a null Gaussian cache; Python float JSON serialization is unsupported');
    }
    return JSON.stringify(validated);
}
function decimalDay(day: number | bigint): string {
    if (typeof day === 'bigint')
        return day.toString(10);
    if (typeof day !== 'number' || !Number.isSafeInteger(day)) {
        throw new TypeError('walk-in day must be a safe integer number or bigint');
    }
    // Safe integer numbers never use scientific notation; -0 becomes Python int 0.
    return String(day);
}
/**
 * Equivalent to engine._make_walkins(rng, day)['budget']; consumes no main RNG.
 * The state is snapshotted before the first await, so advancing the caller's RNG
 * while hashing is pending cannot alter this derivation.
 *
 * Range intentionally fixed to the v9 public rule: randint(60, 120), inclusive.
 * Large exact days must be bigint; no float/string coercion or precision loss.
 * This helper derives a budget only. It does not mark a walk-in used or mutate
 * game state, and is not a cryptographic secret-generation primitive.
 */
export async function deriveWalkinBudget(rng: PythonRandom, day: number | bigint): Promise<number> {
    const dayText = decimalDay(day);
    const serialized = serializePythonRandomState(rng.getstate());
    const material = new TextEncoder().encode(`walkin-v6:${dayText}:${serialized}`);
    const digest = new Uint8Array(await globalThis.crypto.subtle.digest('SHA-256', material));
    const local = await PythonRandom.fromBytes(digest);
    return local.randint(60, 120);
}
