/** Bounded v9 day actions. Mutates only an already-copied private state. */
import type { GameState, SupplierId } from './types.ts';
import { EVENTS, SUPPLIERS } from './server-data.ts';
import { PythonRandom } from './python-random.ts';
import { deriveWalkinBudget } from './python-rng-domain.ts';
import { drawDemand, drawVisitors } from './daily-state.ts';
import { CoreGameError, event, requireActive } from './mutation-utils.ts';
import { goalValues, hasSet, maxEnergy, nextMilestone, operatingCost } from './projection-core.ts';
const suppliers = Object.keys(SUPPLIERS) as SupplierId[];
async function startDay(state: GameState, rng: PythonRandom): Promise<void> {
    state.day++;
    state.daily_event = structuredClone(rng.choice(EVENTS.filter(row => row.id !== state.daily_event.id)));
    state.demand = drawDemand(rng);
    state.supplier_stock = Object.fromEntries(suppliers.map(id => [
        id, SUPPLIERS[id].stock + Number(id === 'salvage' && hasSet(state, 'signal')),
    ])) as GameState['supplier_stock'];
    state.visitors = drawVisitors(rng, state.upgrades.display);
    state.energy = maxEnergy(state);
    state.walkins = { day: state.day, used: 0, budget: await deriveWalkinBudget(rng, state.day) };
}
function closePending(state: GameState): void {
    if (!state.negotiation)
        return;
    const pending = state.negotiation;
    state.log.push({ day: state.day, text: `闭店前自动谢绝${pending.customer_name}对「${pending.item_name}」的${pending.counter_offer}星币还价。` });
    const visitor = state.visitors.find(row => row.id === pending.customer_id);
    if (visitor)
        visitor.status = 'left';
    state.negotiation = null;
    // The following day/end event performs the source's single 60-row trim.
}
/**
 * The caller must clone state and RNG, discard either on any rejection, then
 * persist RNG, check milestones, and increment revision exactly once. This
 * helper neither commits state nor exposes a projection, including when closing a pending trade.
 */
export async function applyDay(state: GameState, command: 'endday' | 'continue', rng: PythonRandom): Promise<void> {
    if (command === 'continue') {
        if (state.phase !== 'week_summary')
            throw new CoreGameError('只有首周结算画面可以 continue；经营中请 endday。');
        state.phase = 'active';
        await startDay(state, rng);
        event(state, 'day', '第8天 · 故事继续', '保留全部现金、库存、收藏与设施，开始长期经营。首周维护费不会重复扣除。');
        return;
    }
    // An internal dispatch mistake must not silently charge a maintenance fee.
    if (command !== 'endday')
        throw new CoreGameError(`未知命令：${command}`);
    requireActive(state);
    closePending(state);
    const oldDay = state.day, cost = operatingCost(state);
    if (state.credits < cost) {
        state.credits = 0;
        state.phase = 'lost';
        event(state, 'end', '灯光暂时熄灭', `第${oldDay}天闭店无法支付${cost}星币维护费。本局结束，你的收藏仍留在这里。`);
        return;
    }
    state.credits -= cost;
    state.stats.days_traded++;
    if (oldDay === 7 && state.first_week_result === 'pending') {
        const firstGoal = nextMilestone(state), values = goalValues(state, firstGoal);
        const won = Object.entries(firstGoal.targets).every(([key, target]) => values[key] >= target);
        state.first_week_result = won ? 'won' : 'missed';
        state.phase = 'week_summary';
        event(state, 'end', won ? '首周达成 · 星港为你亮灯' : '首周结算 · 故事仍在继续', `支付${cost}星币维护费后，留下${state.credits}星币、${state.collection.length}种个人珍藏，其中${values.collection}种计入本阶段目标。`
            + (won ? '首周目标达成！' : '首周目标尚未达成，可以继续经营后补齐。')
            + '使用continue明确进入第8天；所有进度保留。');
        return;
    }
    await startDay(state, rng);
    event(state, 'day', `第${state.day}天 · ${state.daily_event.title}`, `支付${cost}星币维护费，恢复精力并补货。${state.daily_event.description} 今日${state.demand.label}。`);
}
