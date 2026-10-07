/**
 * CPython 3.12 random.Random compatibility for the Stardust engine.
 *
 * Worker-safe: only ECMAScript and Web Crypto APIs, with no Node dependencies.
 * Deterministic integer seeds, MT19937 state, and the discrete/float operations
 * used by the game match CPython, including its rejection-sampling draw order.
 *
 * Intentional boundaries:
 * - Constructor/seed accept exact integer numbers or bigint, not Python float,
 *   None, or arbitrary object seeds. The explicit default is integer zero.
 * - Bytes and UTF-8 string version-2 seeds use the asynchronous factories.
 * - State import accepts canonical, JSON-safe CPython version-3 state only.
 * - Sequence methods accept JavaScript arrays; sample's counts option is absent.
 * - This is a reproducibility PRNG, never a cryptographic random generator.
 */
export type PythonRandomState = [
    3,
    number[],
    number | null
];
export type PythonRandomSeed = number | bigint;
const N = 624;
const M = 397;
const UINT32_MAX = 4294967295;
const TWO_POW_53 = 9007199254740992;
function integer(value: unknown, label: string): asserts value is number {
    if (typeof value !== "number" || !Number.isSafeInteger(value)) {
        throw new TypeError(`${label} must be an exact safe integer; use bigint for larger integers`);
    }
}
function seedInteger(value: PythonRandomSeed): bigint {
    if (typeof value === "bigint")
        return value < 0n ? -value : value;
    integer(value, "seed");
    return BigInt(Math.abs(value));
}
function bisectRight(values: readonly number[], target: number, hi: number): number {
    let lo = 0;
    while (lo < hi) {
        const mid = Math.floor((lo + hi) / 2);
        if (target < values[mid]!)
            hi = mid;
        else
            lo = mid + 1;
    }
    return lo;
}
/** Exact MT19937 engine and CPython random.Random sampling order. */
export class PythonRandom {
    private readonly words = new Uint32Array(N);
    private index = N;
    private gaussNext: number | null = null;
    constructor(seed: PythonRandomSeed = 0) {
        this.seed(seed);
    }
    static fromState(state: unknown): PythonRandom {
        const rng = new PythonRandom(0);
        rng.setstate(state);
        return rng;
    }
    /** CPython seed(bytes, version=2): int.from_bytes(bytes + sha512(bytes)). */
    static async fromBytes(bytes: Uint8Array): Promise<PythonRandom> {
        const rng = new PythonRandom(0);
        await rng.seedBytes(bytes);
        return rng;
    }
    /** CPython's default UTF-8 string seeding, with strict surrogate validation. */
    static async fromString(text: string): Promise<PythonRandom> {
        if (typeof text !== "string")
            throw new TypeError("seed text must be a string");
        for (let i = 0; i < text.length; i++) {
            const code = text.charCodeAt(i);
            if (code >= 0xd800 && code <= 0xdbff) {
                const next = text.charCodeAt(++i);
                if (!(next >= 0xdc00 && next <= 0xdfff)) {
                    throw new TypeError("string seed contains an unpaired UTF-16 surrogate");
                }
            }
            else if (code >= 0xdc00 && code <= 0xdfff) {
                throw new TypeError("string seed contains an unpaired UTF-16 surrogate");
            }
        }
        return PythonRandom.fromBytes(new TextEncoder().encode(text));
    }
    async seedBytes(bytes: Uint8Array): Promise<void> {
        if (!(bytes instanceof Uint8Array))
            throw new TypeError("byte seed must be a Uint8Array");
        // Snapshot before awaiting: caller mutation must not change the seed material.
        const copy = new Uint8Array(bytes);
        const hash = new Uint8Array(await globalThis.crypto.subtle.digest("SHA-512", copy));
        let value = 0n;
        for (const byte of copy)
            value = (value << 8n) | BigInt(byte);
        for (const byte of hash)
            value = (value << 8n) | BigInt(byte);
        this.seed(value);
    }
    seed(value: PythonRandomSeed): void {
        let remaining = seedInteger(value);
        const key: number[] = [];
        do {
            key.push(Number(remaining & 0xffffffffn));
            remaining >>= 32n;
        } while (remaining !== 0n);
        // CPython's integer seed path calls the reference init_by_array algorithm.
        this.words[0] = 19650218;
        for (let i = 1; i < N; i++) {
            const previous = this.words[i - 1]!;
            this.words[i] = (Math.imul(previous ^ (previous >>> 30), 1812433253) + i) >>> 0;
        }
        let i = 1;
        let j = 0;
        for (let k = Math.max(N, key.length); k > 0; k--) {
            const previous = this.words[i - 1]!;
            this.words[i] = ((this.words[i]! ^ Math.imul(previous ^ (previous >>> 30), 1664525))
                + key[j]! + j) >>> 0;
            i++;
            j++;
            if (i >= N) {
                this.words[0] = this.words[N - 1]!;
                i = 1;
            }
            if (j >= key.length)
                j = 0;
        }
        for (let k = N - 1; k > 0; k--) {
            const previous = this.words[i - 1]!;
            this.words[i] = ((this.words[i]! ^ Math.imul(previous ^ (previous >>> 30), 1566083941)) - i) >>> 0;
            i++;
            if (i >= N) {
                this.words[0] = this.words[N - 1]!;
                i = 1;
            }
        }
        this.words[0] = 2147483648;
        this.index = N;
        this.gaussNext = null;
    }
    getstate(): PythonRandomState {
        return [3, [...this.words, this.index], this.gaussNext];
    }
    /** Validate the whole import before mutating the generator. */
    setstate(state: unknown): void {
        if (!Array.isArray(state) || state.length !== 3 || state[0] !== 3) {
            throw new TypeError("only canonical CPython random state version 3 is supported");
        }
        const internal: unknown = state[1];
        if (!Array.isArray(internal) || internal.length !== N + 1) {
            throw new TypeError("random state requires 624 words followed by an index");
        }
        for (let i = 0; i < N; i++) {
            const word: unknown = internal[i];
            if (typeof word !== "number" || !Number.isInteger(word) || word < 0 || word > UINT32_MAX) {
                throw new TypeError(`random state word ${i} is not a uint32`);
            }
        }
        const index: unknown = internal[N];
        if (typeof index !== "number" || !Number.isInteger(index) || index < 0 || index > N) {
            throw new TypeError("random state index must be an integer in [0, 624]");
        }
        const cache: unknown = state[2];
        if (cache !== null && (typeof cache !== "number" || !Number.isFinite(cache))) {
            throw new TypeError("random Gaussian cache must be a finite number or null");
        }
        this.words.set(internal.slice(0, N) as number[]);
        this.index = index;
        this.gaussNext = cache as number | null;
    }
    private nextUint32(): number {
        if (this.index >= N) {
            // The in-place wrap is deliberate; later words use already-twisted words.
            for (let i = 0; i < N; i++) {
                const y = (this.words[i]! & 2147483648) | (this.words[(i + 1) % N]! & 2147483647);
                this.words[i] = (this.words[(i + M) % N]! ^ (y >>> 1) ^ ((y & 1) ? 2567483615 : 0)) >>> 0;
            }
            this.index = 0;
        }
        let y = this.words[this.index++]!;
        y ^= y >>> 11;
        y ^= (y << 7) & 2636928640;
        y ^= (y << 15) & 4022730752;
        y ^= y >>> 18;
        return y >>> 0;
    }
    random(): number {
        const a = this.nextUint32() >>> 5;
        const b = this.nextUint32() >>> 6;
        return (a * 67108864 + b) / TWO_POW_53;
    }
    /** Bigint is always returned, even for small widths, so no bits are lost. */
    getrandbits(k: number): bigint {
        integer(k, "number of bits");
        if (k < 0)
            throw new RangeError("number of bits must be non-negative");
        let result = 0n;
        for (let remaining = k, shift = 0n; remaining > 0; remaining -= 32, shift += 32n) {
            const bits = Math.min(remaining, 32);
            const word = this.nextUint32() >>> (32 - bits);
            result |= BigInt(word) << shift;
        }
        return result;
    }
    private randbelowBigInt(n: bigint): bigint {
        if (n <= 0n)
            throw new RangeError("upper bound must be positive");
        const k = n.toString(2).length;
        let result = this.getrandbits(k);
        while (result >= n)
            result = this.getrandbits(k);
        return result;
    }
    randbelow(n: number): number;
    randbelow(n: bigint): bigint;
    randbelow(n: number | bigint): number | bigint {
        if (typeof n === "bigint")
            return this.randbelowBigInt(n);
        integer(n, "upper bound");
        return Number(this.randbelowBigInt(BigInt(n)));
    }
    randrange(stop: number): number;
    randrange(start: number, stop: number, step?: number): number;
    randrange(stop: bigint): bigint;
    randrange(start: bigint, stop: bigint, step?: bigint): bigint;
    randrange(start: number | bigint, stop?: number | bigint, step?: number | bigint): number | bigint {
        const isBig = typeof start === "bigint";
        const convert = (value: number | bigint, label: string): bigint => {
            if ((typeof value === "bigint") !== isBig)
                throw new TypeError("range arguments must use the same integer type");
            if (typeof value === "bigint")
                return value;
            integer(value, label);
            return BigInt(value);
        };
        let first = convert(start, "start");
        let last: bigint;
        if (stop === undefined) {
            last = first;
            first = 0n;
        }
        else
            last = convert(stop, "stop");
        const stride = step === undefined ? 1n : convert(step, "step");
        if (stride === 0n)
            throw new RangeError("zero step for randrange");
        const width = last - first;
        const count = stride > 0n ? (width + stride - 1n) / stride : (width + stride + 1n) / stride;
        if (count <= 0n || (stride > 0n ? width <= 0n : width >= 0n)) {
            throw new RangeError("empty range for randrange");
        }
        const result = first + stride * this.randbelowBigInt(count);
        return isBig ? result : Number(result);
    }
    randint(a: number, b: number): number;
    randint(a: bigint, b: bigint): bigint;
    randint(a: number | bigint, b: number | bigint): number | bigint {
        if (typeof a === "bigint" && typeof b === "bigint")
            return this.randrange(a, b + 1n);
        if (typeof a !== "number" || typeof b !== "number")
            throw new TypeError("bounds must use the same integer type");
        integer(a, "lower bound");
        integer(b, "upper bound");
        return Number(this.randrange(BigInt(a), BigInt(b) + 1n));
    }
    choice<T>(population: readonly T[]): T {
        if (population.length === 0)
            throw new RangeError("cannot choose from an empty sequence");
        return population[this.randbelow(population.length)]!;
    }
    shuffle<T>(population: T[]): void {
        for (let i = population.length - 1; i > 0; i--) {
            const j = this.randbelow(i + 1);
            [population[i], population[j]] = [population[j]!, population[i]!];
        }
    }
    uniform(a: number, b: number): number {
        return a + (b - a) * this.random();
    }
    /** CPython choices(population, weights, cum_weights=..., k=...). */
    choices<T>(population: readonly T[], weights?: readonly number[] | null, k = 1, cumWeights?: readonly number[]): T[] {
        integer(k, "number of choices");
        const n = population.length;
        if (weights != null && cumWeights !== undefined)
            throw new TypeError("cannot specify both weights and cumulative weights");
        let cumulative = cumWeights;
        if (cumulative === undefined && weights != null) {
            let sum = 0;
            cumulative = weights.map((weight) => (sum += weight));
        }
        if (cumulative === undefined) {
            const result: T[] = [];
            for (let i = 0; i < k; i++) {
                // Match CPython's draw before IndexError for empty uniform populations.
                const index = Math.floor(this.random() * n);
                if (n === 0)
                    throw new RangeError("cannot choose from an empty sequence");
                result.push(population[index]!);
            }
            return result;
        }
        if (cumulative.length !== n)
            throw new RangeError("number of weights does not match the population");
        if (n === 0)
            throw new RangeError("cannot choose from an empty sequence");
        const total = cumulative[n - 1]!;
        if (total <= 0)
            throw new RangeError("total of weights must be greater than zero");
        if (!Number.isFinite(total))
            throw new RangeError("total of weights must be finite");
        const result: T[] = [];
        for (let i = 0; i < k; i++)
            result.push(population[bisectRight(cumulative, this.random() * total, n - 1)]!);
        return result;
    }
    /** CPython's pool/set selection switch matters for exact state consumption. */
    sample<T>(population: readonly T[], k: number): T[] {
        integer(k, "sample size");
        const n = population.length;
        if (k < 0 || k > n)
            throw new RangeError("sample larger than population or is negative");
        let setsize = 21;
        if (k > 5) {
            let size = 1;
            while (size < k * 3)
                size *= 4;
            setsize += size;
        }
        const result: T[] = [];
        if (n <= setsize) {
            const pool = [...population];
            for (let i = 0; i < k; i++) {
                const j = this.randbelow(n - i);
                result.push(pool[j]!);
                pool[j] = pool[n - i - 1]!;
            }
        }
        else {
            const selected = new Set<number>();
            for (let i = 0; i < k; i++) {
                let j = this.randbelow(n);
                while (selected.has(j))
                    j = this.randbelow(n);
                selected.add(j);
                result.push(population[j]!);
            }
        }
        return result;
    }
}
