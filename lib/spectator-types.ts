/** The current public v9 projection. Never import server engine types in the viewer. */
export type Kind = 'tool' | 'artifact' | 'plant' | 'bot' | 'signal';
export type Rarity = 'common' | 'rare' | 'legendary';
export type BudgetRange = [number, number];
export interface Goal { key: string; label: string; current: number; target: number; met: boolean }
export interface PublicArt { art_id?: string; discovered?: boolean; rarity?: Rarity }
export interface SaleOption {
  customer_id: string | null; customer_name: string; available: boolean; counter_eligible: boolean;
  reasons: string[]; public_reference: number; max_counter_ask: number; budget_range: BudgetRange;
  min_condition: number; preference_match: boolean; condition_met: boolean; ask: number; warning: string;
}
export interface PublicItem extends PublicArt {
  id: string; art_id: string; name: string; rarity: Rarity; kind: Kind; condition: number;
  value_estimate: BudgetRange; public_reference: number; sale_options: SaleOption[];
  repair_cost: number; price: number; origin: string; description: string; collected: boolean;
  sale_attempted_today: boolean; repair_attempted_today: boolean; repairs_remaining: number; negotiating: boolean;
  collection_quality: { min_condition: number; condition_met: boolean; counted: boolean; reason: string };
  repair: { available: boolean; reasons: string[]; cost: number; energy_cost: number; command: string };
  collection_replacement: null | { available: boolean; reasons: string[]; cabinet_item_id: string; cabinet_condition: number; energy_cost: number; command: string };
}
export type CatalogEntry = { slot: number; collected: boolean } & (
  { discovered: false } | { discovered: true; art_id: string; name: string; rarity: Rarity; kind: Kind; description: string }
);
export interface PublicRoll {
  id: number; day: number; item_id: string; item_name: string; customer_id: string | null; customer_name: string;
  stage: 'initial' | 'final'; die: string; tens: number; ones: number; roll: number; modifier: number;
  modifiers: { label: string; value: number }[]; threshold: number; probability: number;
  base_chance: number | null; premium: number | null; rules_version: number; counter_offer: number | null;
  success: boolean; outcome: string; price: number; explanation: string;
}
export interface NegotiationPreview {
  price: number; threshold: number; probability: number; modifier: number;
  modifiers: { label: string; value: number }[]; energy_cost: number; accept_income: number;
  success_income: number; failure_income: number; warning: string; suggested?: boolean;
}
export interface PublicNegotiation {
  item_id: string; item_name: string; customer_id: string | null; customer_name: string;
  original_price: number; counter_offer: number; remaining_offers: number; final_offer_energy: number;
  final_offer_bounds: { available: boolean; min: number; max: number }; accept_income: number;
  final_failure_income: number; preview: NegotiationPreview | null;
}
export interface PublicObservation {
  version: 9; revision: number; day: number; total_days: number; credits: number; reputation: number;
  energy: number; max_energy: number; goal: { credits: number; collection: number };
  phase: 'active' | 'week_summary' | 'lost'; inventory: PublicItem[]; collection: PublicItem[];
  crates: { id: string; supplier: string; name: string }[];
  suppliers: { id: string; name: string; cost: number; stock: number; description: string }[];
  upgrades: Record<string, number>; demand: { label: string; kind: Kind; multiplier: number };
  last_event: null | { seq: number; type: string; title: string; text: string; item?: PublicItem | null; roll?: PublicRoll };
  log: { day: number; text: string }[]; capacity: number; operating_cost: number;
  upgrade_costs: Record<string, number | null>;
  upgrade_details: { id: string; name: string; level: number; max_level: number; next_cost: number | null; effect: string; next_effect: string | null }[];
  campaign: {
    title: string; stage_index: number; first_week_result: 'pending' | 'won' | 'missed';
    completed_milestones: { id: string; title: string; day: number }[];
    next_milestone: { id: string; title: string; description: string; goals: Goal[]; ready: boolean; min_condition: number };
    can_continue: boolean; unlimited: boolean;
  };
  collection_progress: { personal_count: number; qualified_count: number; qualified_categories: number; quality_themes: number;
    min_condition: number; requirements: Goal[]; missing: string[];
    categories: { id: string; name: string; qualified_count: number; theme_complete: boolean }[] };
  daily_event: { id: string; title: string; description: string };
  visitors: { id: string; name: string; role: string; preferred_kind: Kind; preference_label: string; min_condition: number; budget_range: BudgetRange; premium: number; status: string; attempted_today: boolean }[];
  walkins: { daily_limit: number; used: number; remaining: number; budget_range: BudgetRange; min_condition: number; visit_rule: string };
  codex: { total: number; discovered: number; collected: number; entries: CatalogEntry[] };
  collection_sets: { id: string; name: string; description: string; required: number; current: number; completed: boolean; perk: string }[];
  stats: { crates_opened: number; sales_count: number; gross_earnings: number; days_traded: number };
  migration: null; engine_upgrade: null; management_upgrade: null; collection_upgrade: null; budget_upgrade: null;
  negotiation: PublicNegotiation | null; last_roll: PublicRoll | null; roll_history: PublicRoll[];
  trade_rules: { die: string; critical_rule: string; fumble_rule: string; house_rules: string; initial_budget_rule: string; counter_rule: string; final_budget_rule: string; endday: string };
}
export interface SpectatorSnapshot {
  initialized: boolean; mode: 'test' | 'formal'; stream_id: string; revision: number; updated_at: string | null; build: string;
  observation: PublicObservation | null;
}
export type DetailSelection = { type: 'item'; id: string } | { type: 'catalog'; slot: number };
export type DetailValue = { type: 'item'; item: PublicItem } | { type: 'catalog'; entry: Extract<CatalogEntry, {discovered: true}> };
