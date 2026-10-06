import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync}from'node:child_process';
import {fileURLToPath}from'node:url';
import path from'node:path';
import {newSyntheticState,transitionCore,CoreGameError}from'../src/core-transitions.ts';
import {observationCore}from'../src/projection-core.ts';
const engine=process.env.STARDUST_ENGINE_SOURCE;
if(!engine)throw Error('Set STARDUST_ENGINE_SOURCE to the trusted v9 engine.py source; no real saves are used.');
const result=spawnSync('python3',[fileURLToPath(new URL('./core-oracle.py',import.meta.url)),'--engine',path.resolve(engine)],{encoding:'utf8',maxBuffer:64*1024*1024,env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'}});
assert.equal(result.status,0,result.stderr);const fixture=JSON.parse(result.stdout);
for(const sample of fixture.cases)test(`core Python differential: ${sample.label}`,async()=>{let state=structuredClone(sample.initial);if(sample.seed!==null){const created=await newSyntheticState(BigInt(sample.seed));assert.deepEqual(created,state,'initial private state');}assert.deepEqual(observationCore(state),sample.initial_observation,'initial full public projection');
 for(const step of sample.steps){const before=structuredClone(state);if(step.error!==null){assert.throws(()=>transitionCore(state,step.command,step.args),error=>error instanceof CoreGameError&&error.message===step.error,`${step.command} ${step.args}`);}else{const result=transitionCore(state,step.command,step.args);state=result.state;assert.deepEqual(result.observation,step.observation,`full public projection at revision${state.revision}`);}assert.deepEqual(before,sample.steps.indexOf(step)===0?sample.initial:sample.steps[sample.steps.indexOf(step)-1].state,'input snapshot not mutated');assert.deepEqual(state,step.state,`full private state including RNG at revision${step.state.revision}`);}
});
test('core fails closed for unported history/provenance/pending states',async()=>{const state=await newSyntheticState(1);for(const patch of[{negotiation:{}},{roll_seq:1},{roll_history:[{}]},{budget_upgrade:{}},{migration:{}},{last_event:{...state.last_event,roll:{}}},{visitors:[{...state.visitors[0],status:'negotiating'}]}])assert.throws(()=>observationCore({...state,...patch}),/state_shape_not_ported/);for(const action of ['sell','repair','endday','continue','constructor'])assert.throws(()=>transitionCore(state,action,[]),/command_not_ported/);});
test('sealed data, RNG and exact budgets never enter projection',async()=>{const initial=await newSyntheticState(42),{state,observation}=transitionCore(initial,'buy',['salvage']);const text=JSON.stringify(observation);for(const forbidden of['base_value','"rng"','"budget":','"cargo"'])assert.equal(text.includes(forbidden),false,forbidden);assert.equal(observation.codex.discovered,0);assert.equal(observation.crates[0].id,'C001');for(const row of observation.codex.entries)assert.deepEqual(Object.keys(row),['slot','discovered','collected']);assert.ok(state.crates[0].cargo.catalog_id);});
test('oracle has substantial bounded action coverage',()=>{assert.equal(fixture.case_count,61);assert.ok(fixture.action_count>700);});
