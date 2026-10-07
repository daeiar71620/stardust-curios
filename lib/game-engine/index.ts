/** Canonical native-v9 engine entry point, shared by the hosted adapter and tests. */
export { executeNative } from './native-engine.ts';
export type { NativeEngineResult } from './native-engine.ts';
export { createInitialState } from './core-transitions.ts';
export { observationV9 } from './projection-v9.ts';
export { validateNativeState, NativeStateValidationError } from './native-validation.ts';
export { CoreGameError } from './mutation-utils.ts';
export type { GameState, PublicRecord } from './types.ts';
export { NATIVE_COMMANDS, NATIVE_COMMAND_NAMES } from './native-commands.ts';
export type { NativeCommand, NativeCommandDefinition } from './native-commands.ts';
