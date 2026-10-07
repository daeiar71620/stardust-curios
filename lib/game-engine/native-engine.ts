/** Native-v9 server-only dispatch. No filesystem, network, import, restart or client seed API. */
import type { GameState, PublicRecord } from './types.ts';
import { PythonRandom } from './python-random.ts';
import { applyBasic } from './core-transitions.ts';
import { applyManagement } from './management-actions.ts';
import { applyDay } from './day-actions.ts';
import { applyTrade, finalPrice, offerForecast } from './trade-actions.ts';
import { checkMilestones } from './projection-core.ts';
import { observationV9 } from './projection-v9.ts';
import { CoreGameError } from './mutation-utils.ts';
import { validateNativeState } from './native-validation.ts';
import { NATIVE_COMMANDS } from './native-commands.ts';
import type { NativeCommand } from './native-commands.ts';
export type NativeEngineResult = {
    state: GameState;
    observation: PublicRecord;
    result: unknown;
    mutated: boolean;
};
/** Internal result contains PRIVATE state: adapters must persist it, never return it to clients. */
export async function executeNative(input: GameState, command: string, args: string[]): Promise<NativeEngineResult> {
    if (!Object.hasOwn(NATIVE_COMMANDS, command))
        throw new CoreGameError(`未移植或未开放的命令：${command}。`);
    const definition = NATIVE_COMMANDS[command as NativeCommand];
    const allowed = definition.argumentCounts;
    if (!Array.isArray(args) || !allowed.includes(args.length) || args.some(v => typeof v !== 'string'))
        throw new CoreGameError(`${command} 需要 ${allowed.length === 1 ? allowed[0] : '(' + allowed.join(', ') + ')'} 个参数；运行 help 查看用法。`);
    validateNativeState(input);
    const state = structuredClone(input);
    if (definition.readOnly) {
        const observation = observationV9(state);
        let result: unknown = observation;
        if (command === 'preview-offer') {
            const pending = state.negotiation;
            if (!pending || pending.item_id !== args[0].toUpperCase())
                throw new CoreGameError('这件货没有等待答复的还价；用 status 查看。');
            const price = finalPrice(pending, args[1]);
            (observation.negotiation as PublicRecord).preview = { ...offerForecast(state, pending, price), suggested: false };
        }
        else if (command === 'market')
            result = Object.fromEntries(['revision', 'day', 'credits', 'energy', 'demand', 'suppliers', 'daily_event', 'visitors', 'walkins', 'operating_cost'].map(k => [k, observation[k]]));
        else if (command === 'codex')
            result = observation.codex;
        else if (command === 'visitors')
            result = { day: state.day, visitors: observation.visitors, walkins: observation.walkins };
        else if (command === 'inspect') {
            result = [...(observation.inventory as PublicRecord[]), ...(observation.collection as PublicRecord[])].find(i => i.id === args[0].toUpperCase());
            if (!result)
                throw new CoreGameError(`未找到物品 ${args[0]}。盲箱需先 open 才能查看内容。`);
        }
        return { state, observation, result, mutated: false };
    }
    const rng = PythonRandom.fromState(state.rng);
    if (['buy', 'open', 'price'].includes(command))
        applyBasic(state, command, args, rng);
    else if (['repair', 'collect', 'replace-collection', 'upgrade'].includes(command))
        applyManagement(state, command, args, rng);
    else if (command === 'endday' || command === 'continue')
        await applyDay(state, command, rng);
    else
        applyTrade(state, command, args, rng);
    state.rng = rng.getstate();
    checkMilestones(state);
    state.revision++;
    validateNativeState(state);
    const observation = observationV9(state);
    return { state, observation, result: observation, mutated: true };
}
