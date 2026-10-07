/**
 * Read-only validation of the Worker-generated, fresh-v9 server-state envelope.
 * Ports engine.py _validate_state/_validate_trades without resetting, repairing,
 * reseeding, or drawing from the saved RNG. The caller owns clone/rollback/CAS.
 *
 * This is NOT a save importer: all migration/provenance records and pre-v9
 * trade rules are rejected. Integers must be exact JavaScript safe integers;
 * canonical Python RNG v3 is required. JSON.parse cannot distinguish 1 from
 * 1.0; raw/external-state import is unsupported. The shared initialChance
 * Math.log2 portability caveat applies
 * here too; tested lawful fixtures do not establish arbitrary-float parity.
 */
import { CATALOG, CUSTOMERS, EVENTS, KINDS, MILESTONES, SUPPLIERS, UPGRADE_RULES } from './server-data.ts';
import { counterOffer, finalChance, initialChance, referenceValue } from './numeric-rules.ts';
import { capacity, hasSet, saleOption } from './projection-core.ts';
import { PythonRandom } from './python-random.ts';
import type { GameState, PublicRecord, SupplierId } from './types.ts';
export class NativeStateValidationError extends Error {
    readonly code: 'invalid_native_state' | 'unsupported_native_state';
    readonly path: string;
    constructor(path: string, detail: string, unsupported = false) {
        // Report the field/reason, never interpolate a hidden value into the error.
        super(`Native v9 state rejected at ${path}: ${detail}; state and RNG were not changed`);
        this.name = 'NativeStateValidationError';
        this.code = unsupported ? 'unsupported_native_state' : 'invalid_native_state';
        this.path = path;
    }
}
function fail(path: string, detail: string, unsupported = false): never {
    throw new NativeStateValidationError(path, detail, unsupported);
}
function record(value: unknown, path: string): PublicRecord {
    if (value === null || typeof value !== 'object' || Array.isArray(value)
        || ![Object.prototype, null].includes(Object.getPrototypeOf(value))) {
        fail(path, 'expected a plain data object');
    }
    // Saved/native objects contain data fields, never inherited fields or getters.
    for (const key of Reflect.ownKeys(value)) {
        const descriptor = Object.getOwnPropertyDescriptor(value, key)!;
        if (typeof key !== 'string' || !descriptor.enumerable || !('value' in descriptor)) {
            fail(path, 'expected enumerable data fields');
        }
    }
    return value as PublicRecord;
}
function list(value: unknown, path: string): unknown[] {
    if (!Array.isArray(value))
        fail(path, 'expected an array');
    // Sparse arrays do not exist in a serialized native save. Do not skip holes.
    for (let index = 0; index < value.length; index++) {
        const descriptor = Object.getOwnPropertyDescriptor(value, String(index));
        if (!descriptor || !('value' in descriptor))
            fail(path, 'expected a dense data array');
    }
    return value;
}
function integer(value: unknown, path: string, low = 0, high = Number.MAX_SAFE_INTEGER): number {
    if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < low || value > high) {
        fail(path, 'expected an exact safe integer in range');
    }
    return value;
}
function finite(value: unknown, path: string): number {
    if (typeof value !== 'number' || !Number.isFinite(value))
        fail(path, 'expected a finite number');
    return value;
}
function string(value: unknown, path: string): string {
    if (typeof value !== 'string')
        fail(path, 'expected a string');
    return value;
}
function member<T>(value: unknown, values: readonly T[], path: string): T {
    if (!values.includes(value as T))
        fail(path, 'unrecognized value');
    return value as T;
}
function exactKeys(value: PublicRecord, keys: readonly string[], path: string): void {
    if (Object.keys(value).length !== keys.length || keys.some(key => !Object.hasOwn(value, key))) {
        fail(path, 'unexpected or missing fields');
    }
}
/** Python dict/list equality on the validated JSON-like domain, without JS
 * boolean-number coercion or dependence on object property insertion order. */
function same(actual: unknown, expected: unknown): boolean {
    if (actual === expected)
        return true;
    if (Array.isArray(actual) && Array.isArray(expected)) {
        return actual.length === expected.length && Array.from(actual).every((value, index) => same(value, expected[index]));
    }
    if (actual === null || expected === null || typeof actual !== 'object' || typeof expected !== 'object'
        || Array.isArray(actual) || Array.isArray(expected))
        return false;
    const a = actual as PublicRecord, b = expected as PublicRecord;
    const keys = Object.keys(a);
    return keys.length === Object.keys(b).length && keys.every(key => Object.hasOwn(b, key) && same(a[key], b[key]));
}
function modifiers(value: unknown, total: unknown, path: string): void {
    const rows = list(value, path);
    if (rows.length > 7)
        fail(path, 'too many modifiers');
    let sum = 0;
    for (const [index, value] of rows.entries()) {
        const rowPath = `${path}[${index}]`, row = record(value, rowPath);
        exactKeys(row, ['label', 'value'], rowPath);
        string(row.label, `${rowPath}.label`);
        const bonus = integer(row.value, `${rowPath}.value`, -10, 15);
        if (bonus % 5 !== 0)
            fail(`${rowPath}.value`, 'modifier must be a multiple of five');
        sum += bonus;
    }
    if (integer(total, `${path}.total`, -70, 105) !== sum)
        fail(path, 'modifier sum does not match');
}
const CATALOG_BY_ID = new Map(CATALOG.map(row => [row[0], row]));
const CUSTOMERS_BY_ID = new Map(CUSTOMERS.map(row => [row[0], row]));
const PROVENANCE = ['migration', 'engine_upgrade', 'management_upgrade', 'collection_upgrade', 'budget_upgrade'];
const ROLL_KEYS = ['id', 'day', 'item_id', 'item_name', 'customer_id', 'customer_name', 'stage', 'modifier',
    'modifiers', 'success', 'outcome', 'price', 'explanation', 'rules_version', 'counter_offer',
    'die', 'tens', 'ones', 'roll', 'threshold', 'probability', 'base_chance', 'premium'];
const PENDING_KEYS = ['item_id', 'item_name', 'customer_id', 'customer_name', 'original_price', 'counter_offer',
    'day', 'context', 'initial_roll_id', 'rules_version', 'origin_rules_version'];
function validateTrades(state: GameState): void {
    const sequence = integer(state.roll_seq, 'roll_seq');
    const history = list(state.roll_history, 'roll_history');
    if (history.length !== Math.min(sequence, 60))
        fail('roll_history', 'history length does not match sequence');
    const walkins = record(state.walkins, 'walkins');
    exactKeys(walkins, ['day', 'used', 'budget'], 'walkins');
    integer(walkins.day, 'walkins.day', state.day, state.day);
    integer(walkins.used, 'walkins.used', 0, 1);
    integer(walkins.budget, 'walkins.budget', 60, 120);
    const seen = new Map<number, Map<string, PublicRecord>>();
    const ordinaryDays = new Set<number>();
    for (const [index, value] of history.entries()) {
        const path = `roll_history[${index}]`, row = record(value, path);
        exactKeys(row, ROLL_KEYS, path);
        if (row.rules_version !== 9)
            fail(`${path}.rules_version`, 'only native v9 trades are supported', true);
        const expectedId = sequence - history.length + index + 1;
        integer(row.id, `${path}.id`, expectedId, expectedId);
        const day = integer(row.day, `${path}.day`, 1, state.day);
        const price = integer(row.price, `${path}.price`, 1, 9999);
        for (const key of ['item_id', 'item_name', 'customer_name', 'explanation'])
            string(row[key], `${path}.${key}`);
        const itemId = row.item_id as string;
        if (row.customer_id !== null && (typeof row.customer_id !== 'string' || !CUSTOMERS_BY_ID.has(row.customer_id))) {
            fail(`${path}.customer_id`, 'unknown customer');
        }
        member(row.stage, ['initial', 'final'], `${path}.stage`);
        modifiers(row.modifiers, row.modifier, `${path}.modifiers`);
        if (typeof row.success !== 'boolean')
            fail(`${path}.success`, 'expected a boolean');
        if (row.stage === 'initial' && row.customer_id === null) {
            if (ordinaryDays.has(day))
                fail(path, 'multiple ordinary-customer initial rolls on one day');
            ordinaryDays.add(day);
        }
        if (row.die !== 'D100')
            fail(`${path}.die`, 'expected D100');
        const tens = integer(row.tens, `${path}.tens`, 0, 90);
        if (tens % 10 !== 0)
            fail(`${path}.tens`, 'expected a multiple of ten');
        const ones = integer(row.ones, `${path}.ones`, 0, 9);
        const roll = integer(row.roll, `${path}.roll`, 1, 100);
        if (roll !== (tens + ones || 100))
            fail(`${path}.roll`, 'digits do not match roll');
        const threshold = integer(row.threshold, `${path}.threshold`, 1, 99);
        if (finite(row.probability, `${path}.probability`) !== threshold / 100)
            fail(`${path}.probability`, 'threshold does not match probability');
        if (row.stage === 'final') {
            const counter = integer(row.counter_offer, `${path}.counter_offer`, 1, price - 1);
            const expected = finalChance(row.modifier as number, counter, price);
            if (integer(row.base_chance, `${path}.base_chance`, 1, 99) !== expected.baseChance || threshold !== expected.threshold) {
                fail(path, 'final chance does not match frozen modifiers and quote');
            }
            if (finite(row.premium, `${path}.premium`) !== (price - counter) / counter)
                fail(`${path}.premium`, 'final premium does not match quote');
        }
        else if (row.counter_offer !== null || row.base_chance !== null || row.premium !== null) {
            fail(path, 'initial roll contains final-offer fields');
        }
        const success = roll === 1 || (roll !== 100 && roll <= threshold);
        const outcome = roll === 1 ? 'miracle' : roll === 100 ? 'fumble' : success ? 'success' : 'failure';
        if (row.success !== success || row.outcome !== outcome)
            fail(path, 'recorded outcome does not match dice');
        const previous = seen.get(day)?.get(itemId);
        if (previous) {
            if (row.stage !== 'final' || previous.stage !== 'initial' || previous.outcome !== 'failure'
                || ['customer_id', 'customer_name', 'item_name', 'modifier', 'modifiers'].some(key => !same(row[key], previous[key]))
                || price >= (previous.price as number))
                fail(path, 'invalid initial/final roll pairing');
        }
        else if (row.stage === 'final' && !(index === 0 && sequence > 60)) {
            // At exactly 60 records no initial has fallen out yet. At 61+, only the
            // FIRST retained row may be a final whose initial was dropped by slicing.
            fail(path, 'final roll has no retained initial roll');
        }
        if (!seen.has(day))
            seen.set(day, new Map());
        seen.get(day)!.set(itemId, row);
    }
    if (walkins.used !== Number(ordinaryDays.has(state.day)))
        fail('walkins.used', 'daily use does not match retained initial rolls');
    const eventRoll = state.last_event!.roll;
    if (eventRoll !== undefined && eventRoll !== null && (!history.length || !same(eventRoll, history[history.length - 1]))) {
        fail('last_event.roll', 'event roll is not the latest retained roll');
    }
    const negotiating = state.visitors.filter(visitor => visitor.status === 'negotiating');
    const pending = state.negotiation;
    if (pending === null) {
        if (negotiating.length)
            fail('visitors', 'negotiating visitor has no pending trade');
        return;
    }
    const p = record(pending, 'negotiation');
    exactKeys(p, PENDING_KEYS, 'negotiation');
    if (state.phase !== 'active')
        fail('negotiation', 'pending trade requires active phase');
    integer(p.day, 'negotiation.day', state.day, state.day);
    if (p.rules_version !== 9 || p.origin_rules_version !== 9)
        fail('negotiation.rules_version', 'only native v9 pending trades are supported', true);
    const item = state.inventory.find(item => item.id === p.item_id);
    if (!item || item.last_sale_day !== state.day || p.item_name !== item.name)
        fail('negotiation.item_id', 'pending item is absent or inconsistent');
    if (integer(p.original_price, 'negotiation.original_price', 1, 9999) !== item.price)
        fail('negotiation.original_price', 'initial price does not match locked item');
    integer(p.counter_offer, 'negotiation.counter_offer', 1, item.price);
    const visitor = state.visitors.find(visitor => visitor.id === p.customer_id) ?? null;
    if ((p.customer_id !== null && (!visitor || negotiating.length !== 1 || negotiating[0] !== visitor))
        || (p.customer_id === null && negotiating.length)
        || p.customer_name !== (visitor ? visitor.name : '旅客'))
        fail('negotiation.customer_id', 'pending customer is inconsistent');
    const context = record(p.context, 'negotiation.context');
    exactKeys(context, ['reference', 'budget', 'modifiers', 'modifier'], 'negotiation.context');
    if (finite(context.reference, 'negotiation.context.reference') <= 0)
        fail('negotiation.context.reference', 'reference must be positive');
    modifiers(context.modifiers, context.modifier, 'negotiation.context.modifiers');
    if (integer(context.budget, 'negotiation.context.budget', 1) !== (visitor ? visitor.budget : state.walkins.budget)) {
        fail('negotiation.context.budget', 'pending budget does not match customer');
    }
    const latest = state.roll_history[state.roll_history.length - 1];
    if (!latest)
        fail('negotiation', 'pending trade has no initial roll');
    integer(p.initial_roll_id, 'negotiation.initial_roll_id', latest.id as number, latest.id as number);
    if (latest.stage !== 'initial' || latest.outcome !== 'failure' || latest.rules_version !== p.origin_rules_version
        || ['day', 'item_id', 'item_name', 'customer_id', 'customer_name'].some(key => latest[key] !== p[key])
        || latest.price !== p.original_price)
        fail('negotiation', 'pending trade does not match latest failed initial roll');
    const reference = referenceValue(item.base_value, item.condition, item.kind === state.demand.kind ? state.demand.multiplier : 1);
    if (context.reference !== reference)
        fail('negotiation.context.reference', 'pending reference does not match locked item');
    if (latest.modifier !== context.modifier || !same(latest.modifiers, context.modifiers)
        || latest.threshold !== initialChance(pending.context, pending.original_price)
        || p.counter_offer !== counterOffer(pending.context, pending.original_price)
        || !saleOption(state, item, visitor).counter_eligible)
        fail('negotiation', 'pending initial chance, counter, or public eligibility is inconsistent');
}
/** Reject unsupported or damaged state, preserving the exact supplied object.
 * Accepts a fully materialized native server-state object, never raw JSON. */
export function validateNativeState(value: unknown): asserts value is GameState {
    const state = record(value, 'state');
    if (state.version !== 9)
        fail('version', 'only native v9 states are supported; external import is disabled', true);
    for (const key of PROVENANCE) {
        if (!Object.hasOwn(state, key))
            fail(key, 'required native provenance marker is missing');
        if (state[key] !== null)
            fail(key, 'migration/import provenance is not supported; external import is disabled', true);
    }
    for (const [key, low, high] of [
        ['revision', 0, 1e12], ['day', 1, 1e12], ['credits', 0, 1e12], ['energy', 0, 17],
        ['reputation', 0, 99], ['next_crate', 1, 1e12], ['next_item', 1, 1e12], ['event_seq', 1, 1e12],
    ] as const)
        integer(state[key], key, low, high);
    const day = state.day as number;
    member(state.phase, ['active', 'week_summary', 'lost'], 'phase');
    const upgrades = record(state.upgrades, 'upgrades');
    exactKeys(upgrades, Object.keys(UPGRADE_RULES), 'upgrades');
    for (const [key, level] of Object.entries(upgrades))
        integer(level, `upgrades.${key}`, 0, 3);
    const dailyEvent = record(state.daily_event, 'daily_event');
    if (!EVENTS.some(event => same(dailyEvent, event)))
        fail('daily_event', 'event does not match a canonical event');
    member(state.first_week_result, ['pending', 'won', 'missed'], 'first_week_result');
    if ((state.first_week_result === 'pending' && day > 7) || (state.first_week_result !== 'pending' && day < 7)
        || (state.phase === 'week_summary' && (day !== 7 || state.first_week_result === 'pending')))
        fail('first_week_result', 'phase, day, and first-week result disagree');
    const discovered = list(state.discovered, 'discovered');
    if (new Set(discovered).size !== discovered.length || discovered.some(id => typeof id !== 'string' || !CATALOG_BY_ID.has(id))) {
        fail('discovered', 'unknown or duplicate catalog entry');
    }
    const visitors = list(state.visitors, 'visitors');
    if (visitors.length !== 3 && visitors.length !== 4)
        fail('visitors', 'expected three or four visitors');
    const visitorIds = new Set<string>();
    for (const [index, value] of visitors.entries()) {
        const path = `visitors[${index}]`, visitor = record(value, path), id = string(visitor.id, `${path}.id`);
        const profile = CUSTOMERS_BY_ID.get(id);
        if (!profile || visitorIds.has(id))
            fail(`${path}.id`, 'unknown or duplicate customer');
        visitorIds.add(id);
        const [, name, role, kind, condition, low, high] = profile;
        const expected = [name, role, kind, condition, [low, high], 1.25, `偏爱${KINDS[kind]}，品相${condition}%以上更喜欢`];
        const actual = ['name', 'role', 'preferred_kind', 'min_condition', 'budget_range', 'premium', 'preference_label'].map(key => visitor[key]);
        if (!same(actual, expected))
            fail(path, 'visitor profile does not match canonical customer');
        member(visitor.status, ['waiting', 'bought', 'left', 'negotiating'], `${path}.status`);
        integer(visitor.budget, `${path}.budget`, low, high);
    }
    const stats = record(state.stats, 'stats');
    exactKeys(stats, ['crates_opened', 'sales_count', 'gross_earnings', 'days_traded'], 'stats');
    for (const [key, count] of Object.entries(stats))
        integer(count, `stats.${key}`);
    for (const [index, value] of list(state.milestones, 'milestones').entries()) {
        const path = `milestones[${index}]`, row = record(value, path);
        const chapter = index - MILESTONES.length + 1;
        const expected = index < MILESTONES.length ? MILESTONES[index] : { id: `voyage_${chapter}`, title: `星海长航 · 第${chapter}章` };
        if (row.id !== expected.id || row.title !== expected.title)
            fail(path, 'milestone order or title is inconsistent');
        integer(row.day, `${path}.day`, 7, day);
    }
    const inventory = list(state.inventory, 'inventory'), crates = list(state.crates, 'crates');
    const collection = list(state.collection, 'collection'), log = list(state.log, 'log');
    const demand = record(state.demand, 'demand');
    member(demand.kind, Object.keys(KINDS), 'demand.kind');
    member(demand.multiplier, [1.25, 1.35, 1.45], 'demand.multiplier');
    string(demand.label, 'demand.label');
    const ids = new Set<string>(), collectionCatalog = new Set<string>();
    function validateItem(value: unknown, path: string, cargo = false, collected = false): PublicRecord {
        const item = record(value, path), catalogId = string(item.catalog_id, `${path}.catalog_id`);
        const entry = CATALOG_BY_ID.get(catalogId);
        if (!entry)
            fail(`${path}.catalog_id`, 'unknown catalog entry');
        if (!same([item.name, item.rarity, item.kind, item.description], [entry[1], entry[2], entry[3], entry[5]]))
            fail(path, 'catalog description does not match');
        for (const [key, low, high] of [
            ['base_value', 1, 10000], ['condition', 5, 100], ['repairs', 0, 2], ['last_sale_day', 0, day], ['last_repair_day', 0, day],
        ] as const)
            integer(item[key], `${path}.${key}`, low, high);
        if (item.collected !== collected)
            fail(`${path}.collected`, 'collection marker does not match location');
        member(item.origin, Object.values(SUPPLIERS).map(supplier => supplier.name), `${path}.origin`);
        if (!cargo) {
            const id = string(item.id, `${path}.id`);
            if (!id.startsWith('I') || ids.has(id))
                fail(`${path}.id`, 'invalid or duplicate item identifier');
            ids.add(id);
            integer(item.price, `${path}.price`, 1, 9999);
        }
        return item;
    }
    inventory.forEach((item, index) => validateItem(item, `inventory[${index}]`));
    collection.forEach((value, index) => {
        const item = validateItem(value, `collection[${index}]`, false, true), id = item.catalog_id as string;
        if (collectionCatalog.has(id))
            fail(`collection[${index}].catalog_id`, 'duplicate collected catalog entry');
        collectionCatalog.add(id);
    });
    crates.forEach((value, index) => {
        const path = `crates[${index}]`, crate = record(value, path), id = string(crate.id, `${path}.id`);
        member(crate.supplier, Object.keys(SUPPLIERS), `${path}.supplier`);
        if (!id.startsWith('C') || ids.has(id))
            fail(`${path}.id`, 'invalid or duplicate crate identifier');
        ids.add(id);
        string(crate.name, `${path}.name`);
        validateItem(crate.cargo, `${path}.cargo`, true);
    });
    // All inputs of these shared cross-field helpers have now been validated.
    const typed = state as unknown as GameState;
    if (inventory.length + crates.length > capacity(typed))
        fail('inventory', 'shelf capacity exceeded');
    const maximumEnergy = 12 + typed.upgrades.shelf + Number(hasSet(typed, 'bot')) + typed.daily_event.energy_delta;
    if (typed.energy > maximumEnergy)
        fail('energy', 'daily energy limit exceeded');
    const stock = record(state.supplier_stock, 'supplier_stock');
    exactKeys(stock, Object.keys(SUPPLIERS), 'supplier_stock');
    for (const key of Object.keys(SUPPLIERS) as SupplierId[]) {
        integer(stock[key], `supplier_stock.${key}`, 0, SUPPLIERS[key].stock + Number(key === 'salvage' && hasSet(typed, 'signal')));
    }
    log.forEach((value, index) => {
        const path = `log[${index}]`, row = record(value, path);
        integer(row.day, `${path}.day`, 1, day);
        string(row.text, `${path}.text`);
    });
    const event = record(state.last_event, 'last_event');
    integer(event.seq, 'last_event.seq', typed.event_seq, typed.event_seq);
    member(event.type, ['start', 'buy', 'reveal', 'repair', 'sale', 'price', 'day', 'upgrade', 'collect', 'replace_collection', 'end', 'import', 'negotiation'], 'last_event.type');
    string(event.title, 'last_event.title');
    string(event.text, 'last_event.text');
    // The native builder always writes item:null or a historical public snapshot.
    // Snapshot content must NOT be recomputed against today's state or repaired.
    if (event.item !== null)
        record(event.item, 'last_event.item');
    validateTrades(typed);
    try {
        const rng = PythonRandom.fromState(state.rng);
        if (!same(state.rng, rng.getstate()))
            fail('rng', 'saved RNG did not round-trip exactly');
    }
    catch (error) {
        if (error instanceof NativeStateValidationError)
            throw error;
        fail('rng', 'invalid canonical CPython v3 random state');
    }
}
