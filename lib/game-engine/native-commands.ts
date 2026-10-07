/** One immutable command contract for native dispatch and external adapters. */
export interface NativeCommandDefinition {
    readonly argumentCounts: readonly number[];
    readonly readOnly: boolean;
}

function defineCommand(readOnly: boolean, ...argumentCounts: number[]): NativeCommandDefinition {
    return Object.freeze({ argumentCounts: Object.freeze(argumentCounts), readOnly });
}

/** Store initialization/replacement is deliberately outside native gameplay. */
export const NATIVE_COMMANDS = Object.freeze({
    status: defineCommand(true, 0),
    market: defineCommand(true, 0),
    codex: defineCommand(true, 0),
    visitors: defineCommand(true, 0),
    inspect: defineCommand(true, 1),
    'preview-offer': defineCommand(true, 2),
    buy: defineCommand(false, 1),
    open: defineCommand(false, 1),
    price: defineCommand(false, 2),
    repair: defineCommand(false, 1),
    collect: defineCommand(false, 1),
    'replace-collection': defineCommand(false, 1),
    upgrade: defineCommand(false, 1),
    sell: defineCommand(false, 1, 2),
    accept: defineCommand(false, 1),
    decline: defineCommand(false, 1),
    offer: defineCommand(false, 2),
    endday: defineCommand(false, 0),
    continue: defineCommand(false, 0),
});

export type NativeCommand = keyof typeof NATIVE_COMMANDS;
export const NATIVE_COMMAND_NAMES: readonly NativeCommand[] = Object.freeze(
    Object.keys(NATIVE_COMMANDS) as NativeCommand[],
);
