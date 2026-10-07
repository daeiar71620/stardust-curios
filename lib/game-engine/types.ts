import type { PythonRandomState } from './python-random.ts';
export type Kind = 'tool' | 'artifact' | 'bot' | 'plant' | 'signal';
export type Rarity = 'common' | 'rare' | 'legendary';
export type SupplierId = 'salvage' | 'curated';
export type UpgradeId = 'workbench' | 'shelf' | 'display';
export type PublicRecord = Record<string, unknown>;
export type CatalogRow = [
    string,
    string,
    Rarity,
    Kind,
    number,
    string
];
export interface Cargo {
    catalog_id: string;
    name: string;
    rarity: Rarity;
    kind: Kind;
    base_value: number;
    condition: number;
    description: string;
    origin: string;
    collected: boolean;
    repairs: number;
    last_sale_day: number;
    last_repair_day: number;
}
export interface Item extends Cargo {
    id: string;
    price: number;
}
export interface Crate {
    id: string;
    supplier: SupplierId;
    name: string;
    cargo: Cargo;
}
export interface Visitor {
    id: string;
    name: string;
    role: string;
    preferred_kind: Kind;
    preference_label: string;
    min_condition: number;
    budget_range: number[];
    premium: number;
    status: string;
    budget: number;
}
export interface DayEvent {
    id: string;
    title: string;
    description: string;
    sale_multiplier: number;
    salvage_discount: number;
    repair_discount: number;
    cost_delta: number;
    energy_delta: number;
}
export interface SupplierRule {
    id: SupplierId;
    name: string;
    cost: number;
    stock: number;
    description: string;
}
export interface UpgradeRule {
    name: string;
    costs: number[];
    effects: string[];
}
export interface Milestone {
    id: string;
    title: string;
    description: string;
    min_condition: number;
    targets: Record<string, number>;
}
export interface TradeContextState {
    reference: number;
    budget: number;
    modifiers: {
        label: string;
        value: number;
    }[];
    modifier: number;
}
export interface PendingTrade {
    item_id: string;
    item_name: string;
    customer_id: string | null;
    customer_name: string;
    original_price: number;
    counter_offer: number;
    day: number;
    context: TradeContextState;
    initial_roll_id: number;
    rules_version: 9;
    origin_rules_version: 9;
}
export interface GameState {
    version: 9;
    revision: number;
    day: number;
    credits: number;
    reputation: number;
    energy: number;
    phase: 'active' | 'week_summary' | 'lost';
    inventory: Item[];
    crates: Crate[];
    collection: Item[];
    upgrades: Record<UpgradeId, number>;
    demand: {
        label: string;
        kind: Kind;
        multiplier: number;
    };
    supplier_stock: Record<SupplierId, number>;
    next_crate: number;
    next_item: number;
    event_seq: number;
    last_event: {
        seq: number;
        type: string;
        title: string;
        text: string;
        item: PublicRecord | null;
        roll?: PublicRecord;
    } | null;
    log: {
        day: number;
        text: string;
    }[];
    daily_event: DayEvent;
    visitors: Visitor[];
    discovered: string[];
    first_week_result: 'pending' | 'won' | 'missed';
    milestones: {
        id: string;
        title: string;
        day: number;
    }[];
    stats: {
        crates_opened: number;
        sales_count: number;
        gross_earnings: number;
        days_traded: number;
    };
    migration: null;
    engine_upgrade: null;
    management_upgrade: null;
    collection_upgrade: null;
    budget_upgrade: null;
    negotiation: PendingTrade | null;
    roll_seq: number;
    roll_history: PublicRecord[];
    walkins: {
        day: number;
        used: number;
        budget: number;
    };
    rng: PythonRandomState;
}
