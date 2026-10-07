/** Shared daily draws. Selection order is part of the native-v9 RNG contract. */
import { CUSTOMERS, KINDS } from './server-data.ts';
import { pyRound } from './numeric-rules.ts';
import type { PythonRandom } from './python-random.ts';
import type { GameState, Kind, Visitor } from './types.ts';
export function drawDemand(rng: PythonRandom): GameState['demand'] {
    const kind = rng.choice(Object.keys(KINDS) as Kind[]), multiplier = rng.choice([1.25, 1.35, 1.45]);
    return { label: `${KINDS[kind]}收藏热 · +${pyRound((multiplier - 1) * 100)}%`, kind, multiplier };
}
export function drawVisitors(rng: PythonRandom, displayLevel: number): Visitor[] {
    // Sample the complete group before drawing its budgets, exactly as CPython.
    return rng.sample(CUSTOMERS, 3 + Number(displayLevel >= 2)).map(row => ({
        id: row[0], name: row[1], role: row[2], preferred_kind: row[3],
        preference_label: `偏爱${KINDS[row[3]]}，品相${row[4]}%以上更喜欢`,
        min_condition: row[4], budget_range: [row[5], row[6]], premium: 1.25,
        status: 'waiting', budget: rng.randint(row[5], row[6]),
    }));
}
