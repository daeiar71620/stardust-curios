import test from 'node:test';
import assert from 'node:assert/strict';
import {spawn}from'node:child_process';
import {createInterface}from'node:readline';
import {fileURLToPath}from'node:url';
import path from'node:path';
import {executeNative}from'../../lib/game-engine/native-engine.ts';
import {observationV9}from'../../lib/game-engine/projection-v9.ts';
import {validateNativeState}from'../../lib/game-engine/native-validation.ts';
import {CoreGameError}from'../../lib/game-engine/mutation-utils.ts';
const engine=process.env.STARDUST_ENGINE_SOURCE;if(!engine)throw Error('STARDUST_ENGINE_SOURCE is required; synthetic source fixtures only.');
const child=spawn('python3',[fileURLToPath(new URL('./native-oracle.py',import.meta.url)),'--engine',path.resolve(engine)],{env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'},stdio:['ignore','pipe','pipe']});let stderr='';child.stderr.on('data',chunk=>{stderr+=chunk});const closed=new Promise(resolve=>child.on('close',(code,signal)=>resolve({code,signal})));let summary;
for await(const line of createInterface({input:child.stdout,crlfDelay:Infinity})){
 const sample=JSON.parse(line);if(sample.summary){summary=sample;continue;}
 await test(`native integration: ${sample.label}`,async()=>{let state=structuredClone(sample.initial);validateNativeState(state);assert.deepEqual(observationV9(state),sample.initial_observation,'initial complete public projection');for(const step of sample.steps){const input=state,before=structuredClone(state);if(step.error!==null)await assert.rejects(executeNative(state,step.command,step.args),error=>error instanceof CoreGameError&&error.message===step.error,`exact error for ${step.command}`);else{const result=await executeNative(state,step.command,step.args);state=result.state;assert.deepEqual(result.observation,step.observation,`complete projection for ${step.command}`);assert.deepEqual(result.result,step.result??step.observation,`public command result for ${step.command}`);assert.equal(result.mutated,step.mutated);}assert.deepEqual(input,before,'input snapshot never changed');assert.deepEqual(state,step.state,'all private fields and RNG match after the chosen command');}});
}
const exit=await closed;assert.equal(exit.code,0,`oracle exited ${JSON.stringify(exit)}: ${stderr}`);
test('native integrated fixture coverage remains broad',t=>{assert.ok(summary.case_count>=1000);assert.ok(summary.action_count>=4000);t.diagnostic(`NATIVE_COUNTS ${JSON.stringify(summary)}`);});
