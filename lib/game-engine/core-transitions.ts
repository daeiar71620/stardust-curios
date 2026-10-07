/** Native-v9 initial state and basic actions. All seeds stay server-owned. */
import { PythonRandom } from './python-random.ts';
import type { PythonRandomSeed } from './python-random.ts';
import { deriveWalkinBudget } from './python-rng-domain.ts';
import { drawDemand, drawVisitors } from './daily-state.ts';
import { CATALOG, EVENTS, RARITIES, SUPPLIERS } from './server-data.ts';
import { pyRound } from './numeric-rules.ts';
import { CoreGameError, event, spend, requireActive, itemById, requireUnlocked } from './mutation-utils.ts';
import { capacity, itemReference, supplierCost } from './projection-core.ts';
import type { Cargo, GameState, Rarity, SupplierId } from './types.ts';
const clone = <T>(v: T): T => structuredClone(v);
function cargo(rng: PythonRandom, id: SupplierId): Cargo { const rarity = rng.choices<Rarity>(['common', 'rare', 'legendary'], id === 'salvage' ? [74, 24, 2] : [28, 61, 11])[0]; const row = rng.choice(CATALOG.filter(c => c[2] === rarity)); return { catalog_id: row[0], name: row[1], rarity: row[2], kind: row[3], base_value: pyRound(row[4] * rng.uniform(0.92, 1.08)), condition: id === 'salvage' ? rng.randint(35, 88) : rng.randint(48, 96), description: row[5], origin: SUPPLIERS[id].name, collected: false, repairs: 0, last_sale_day: 0, last_repair_day: 0 }; }
/** Internal initialization only: callers supply server entropy; clients cannot choose a seed. */
export async function createInitialState(seed: PythonRandomSeed): Promise<GameState> {
    const rng = new PythonRandom(seed);
    const demand = drawDemand(rng);
    const s: GameState = { version: 9, revision: 1, day: 1, credits: 260, reputation: 0, energy: 12, phase: 'active', inventory: [], crates: [], collection: [], upgrades: { workbench: 0, shelf: 0, display: 0 }, demand, supplier_stock: { salvage: 4, curated: 2 }, next_crate: 1, next_item: 1, event_seq: 0, last_event: null, log: [], daily_event: clone(EVENTS[0]), visitors: [], discovered: [], first_week_result: 'pending', milestones: [], stats: { crates_opened: 0, sales_count: 0, gross_earnings: 0, days_traded: 0 }, migration: null, engine_upgrade: null, management_upgrade: null, collection_upgrade: null, budget_upgrade: null, negotiation: null, roll_seq: 0, roll_history: [], walkins: { day: 1, used: 0, budget: 0 }, rng: rng.getstate() };
    s.visitors = drawVisitors(rng, 0);
    s.walkins.budget = await deriveWalkinBudget(rng, 1);
    s.rng = rng.getstate();
    event(s, 'start', '卷帘门升起', '第1天开张！先争取首周650星币与2种品相至少70%的合格收藏，再把小店经营成星港地标。');
    return s;
}
const pyWhitespace = /^[\u0009-\u000D\u0020\u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]+|[\u0009-\u000D\u0020\u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]+$/g;
function parsePrice(raw: string) { const stripped = raw.replace(pyWhitespace, ''); if (!/^[1-9][0-9]{0,3}$/.test(stripped))
    throw new CoreGameError('标价必须是 1–9999 的整数。'); return Number(stripped); }
export function applyBasic(s: GameState, command: string, args: string[], rng: PythonRandom): void {
    requireActive(s);
    if (!['buy', 'open', 'price'].includes(command))
        throw new Error(`command_not_ported:${command}`);
    if (command === 'buy') {
        const raw = args[0];
        if (!Object.hasOwn(SUPPLIERS, raw))
            throw new CoreGameError('未知供应商；请选择 salvage 或 curated。');
        const supplier = raw as SupplierId;
        if (s.supplier_stock[supplier] <= 0)
            throw new CoreGameError('这位供应商今天已售罄，明天会补货。');
        if (s.inventory.length + s.crates.length >= capacity(s))
            throw new CoreGameError('货架已满；出售、收藏物品，或升级 shelf 后再采购。');
        spend(s, 1, supplierCost(s, supplier));
        const crate = { id: `C${String(s.next_crate).padStart(3, '0')}`, supplier, name: supplier === 'salvage' ? '漂流回收箱' : '夜航封存箱', cargo: cargo(rng, supplier) };
        s.next_crate++;
        s.supplier_stock[supplier]--;
        s.crates.push(crate);
        event(s, 'buy', '新货靠港', `花费 ${supplierCost(s, supplier)} 星币购入 ${crate.name} ${crate.id}。箱内货物已封存。`);
    }
    else if (command === 'open') {
        const crate = s.crates.find(c => c.id === args[0].toUpperCase());
        if (!crate)
            throw new CoreGameError(`没有未开封的箱子 ${args[0]}。`);
        spend(s, 1);
        const item = { ...clone(crate.cargo), id: `I${String(s.next_item).padStart(3, '0')}`, price: 1 };
        s.next_item++;
        item.price = Math.max(1, pyRound(itemReference(s, item) * 0.93));
        s.crates = s.crates.filter(c => c !== crate);
        s.inventory.push(item);
        if (!s.discovered.includes(item.catalog_id))
            s.discovered.push(item.catalog_id);
        s.stats.crates_opened++;
        event(s, 'reveal', '封条揭开', `开出了${RARITIES[item.rarity]}物品「${item.name}」！品相 ${item.condition}%，初始标价 ${item.price} 星币。`, item);
    }
    else {
        const item = itemById(s, args[0]);
        requireUnlocked(s, item);
        item.price = parsePrice(args[1]);
        event(s, 'price', '换上新价签', `「${item.name}」现在标价 ${item.price} 星币。`, item);
    }
}
