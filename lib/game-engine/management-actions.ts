/** Bounded v9 management mutations. The dispatcher owns copying, RNG persistence,
 * revision increments, milestone checks, and public projection. */
import type { GameState, UpgradeId } from './types.ts';
import type { PythonRandom } from './python-random.ts';
import { UPGRADE_RULES } from './server-data.ts';
import { CoreGameError, event, spend, requireActive, itemById, requireUnlocked } from './mutation-utils.ts';
import { hasSet, repairCost } from './projection-core.ts';
export function applyManagement(state: GameState, command: string, args: string[], rng: PythonRandom): void {
    if (!['repair', 'collect', 'replace-collection', 'upgrade'].includes(command)) {
        throw new Error(`command_not_ported:${command}`);
    }
    requireActive(state);
    if (command === 'repair') {
        // Cabinet repairs precede the inventory lookup, just as in v9.
        const item = state.collection.find(item => item.id === args[0].toUpperCase()) ?? itemById(state, args[0]);
        requireUnlocked(state, item);
        if (item.condition >= 100)
            throw new CoreGameError('这件物品已是完美品相，无需修理。');
        if (item.repairs >= 2)
            throw new CoreGameError('这件物品已达到两次修理上限。');
        if (item.last_repair_day === state.day)
            throw new CoreGameError('今天已经修过这件物品；明天再试。');
        const cost = repairCost(state, item);
        spend(state, 2, cost);
        item.repairs++;
        item.last_repair_day = state.day;
        const before = item.condition;
        const failChance = [0.24, 0.14, 0.07, 0.03][state.upgrades.workbench];
        let text: string;
        if (rng.random() < failChance) {
            item.condition = Math.max(5, before - rng.randint(3, 11));
            text = `修理失手：${item.name}的品相从 ${before}% 降到 ${item.condition}%。花费 ${cost} 星币；原标价未变。`;
        }
        else {
            const gain = rng.randint(19, 35) + 4 * state.upgrades.workbench;
            item.condition = Math.min(100, before + gain);
            text = `修理成功：${item.name}的品相从 ${before}% 提升到 ${item.condition}%。花费 ${cost} 星币；记得检查标价。`;
        }
        event(state, 'repair', '工作台火花', text, item);
        return;
    }
    if (command === 'collect') {
        const item = itemById(state, args[0]);
        requireUnlocked(state, item);
        if (state.collection.some(previous => previous.catalog_id === item.catalog_id)) {
            throw new CoreGameError('收藏柜已有这个品种；若手中这件品相更好，可用 replace-collection 进行一换一替换。');
        }
        const hadSet = hasSet(state, item.kind);
        spend(state, 1);
        state.inventory.splice(state.inventory.indexOf(item), 1);
        item.collected = true;
        state.collection.push(item);
        if (!hadSet && hasSet(state, item.kind) && item.kind === 'bot')
            state.energy++;
        event(state, 'collect', '留给自己的星光', `将「${item.name}」放入收藏柜。可修理或用更好同款替换；个人珍藏 ${state.collection.length} 个品种。`, item);
        return;
    }
    if (command === 'replace-collection') {
        const item = itemById(state, args[0]);
        requireUnlocked(state, item);
        const previous = state.collection.find(previous => previous.catalog_id === item.catalog_id);
        if (!previous)
            throw new CoreGameError('收藏柜没有这个品种；请用 collect 收藏。');
        if (item.condition <= previous.condition) {
            throw new CoreGameError('替换品相必须严格高于柜中同款；相同或更低品相不能替换。');
        }
        spend(state, 1);
        // Swap the same objects at their existing indices. Prices, provenance,
        // counters and per-day repair/sale locks travel with each physical item.
        const inventoryIndex = state.inventory.indexOf(item);
        const cabinetIndex = state.collection.indexOf(previous);
        item.collected = true;
        previous.collected = false;
        state.inventory[inventoryIndex] = previous;
        state.collection[cabinetIndex] = item;
        event(state, 'replace_collection', '收藏换上更好的模样', `花1精力，用${item.id}「${item.name}」(${item.condition}%)替换${previous.id}(${previous.condition}%)。` +
            '旧件回到货架；两件编号、原标价、来源、修理次数与今日限制全部保留，套装奖励不重复触发。', item);
        return;
    }
    const raw = args[0];
    if (!Object.hasOwn(UPGRADE_RULES, raw))
        throw new CoreGameError('升级项目为 workbench、shelf 或 display。');
    const which = raw as UpgradeId;
    const level = state.upgrades[which];
    if (level >= 3)
        throw new CoreGameError('此设施已经升到最高等级。');
    const rule = UPGRADE_RULES[which];
    const cost = rule.costs[level];
    spend(state, 2, cost);
    state.upgrades[which]++;
    if (which === 'shelf')
        state.energy++;
    let text = `花费${cost}星币升级${rule.name}至Lv.${level + 1}：${rule.effects[level + 1]}。`;
    if (which === 'display' && level === 1)
        text += '额外访客从明天开始到店。';
    event(state, 'upgrade', '小店焕新', text);
}
