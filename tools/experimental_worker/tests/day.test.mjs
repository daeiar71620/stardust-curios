import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {applyDay,operatingCost} from '../src/day-actions.ts';
import {newSyntheticState} from '../src/core-transitions.ts';
import {CoreGameError} from '../src/mutation-utils.ts';
import {PythonRandom} from '../src/python-random.ts';
import {assertCoreEnvelope,checkMilestones,observationCore} from '../src/projection-core.ts';
import {EVENTS} from '../src/server-data.ts';

const engine=process.env.STARDUST_ENGINE_SOURCE;
if(!engine)throw Error('Set STARDUST_ENGINE_SOURCE to the trusted v9 engine.py source; no real saves are used.');
const result=spawnSync('python3',[
  fileURLToPath(new URL('./day-oracle.py',import.meta.url)),'--engine',path.resolve(engine),
],{encoding:'utf8',maxBuffer:128*1024*1024,env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'}});
assert.equal(result.status,0,result.stderr);
const fixture=JSON.parse(result.stdout);

// Test-only transaction owner. applyDay intentionally accepts an already-copied
// state; the production owner must commit only after every step succeeds.
async function transition(input,command,{privateOnly=false,validate=()=>{}}={}){
  if(!privateOnly)assertCoreEnvelope(input);
  const state=structuredClone(input),rng=PythonRandom.fromState(state.rng);
  await applyDay(state,command,rng);
  state.rng=rng.getstate();
  checkMilestones(state);
  state.revision++;
  validate(state);
  return {state,observation:privateOnly?null:observationCore(state)};
}

for(const sample of [...fixture.cases,...fixture.private_cases]){
  test(`day Python differential: ${sample.label}`,async()=>{
    let state=structuredClone(sample.initial);
    if(!sample.private_only)assert.deepEqual(observationCore(state),sample.initial_observation,'initial full public projection');
    for(const step of sample.steps){
      const before=structuredClone(state),input=state;
      if(step.error!==null){
        await assert.rejects(transition(state,step.command,{privateOnly:sample.private_only}),
          error=>error instanceof CoreGameError&&error.message===step.error);
      }else{
        const outcome=await transition(state,step.command,{privateOnly:sample.private_only});
        state=outcome.state;
        assert.deepEqual(outcome.observation,step.observation,`full public projection at revision ${state.revision}`);
        assert.equal(state.revision,before.revision+1,'exactly one wrapper revision');
        if(step.command==='continue'){
          assert.equal(state.credits,before.credits,'continue never pays a second day-7 fee');
          assert.equal(state.stats.days_traded,before.stats.days_traded,'continue does not count an extra paid day');
        }else if(state.phase==='lost'){
          assert.equal(state.credits,0);
          assert.equal(state.stats.days_traded,before.stats.days_traded);
          assert.deepEqual(state.rng,before.rng,'loss consumes no RNG');
        }else{
          assert.equal(state.credits,before.credits-operatingCost(before),'outgoing event and set determine the fee');
          assert.equal(state.stats.days_traded,before.stats.days_traded+1);
        }
        if(state.day>before.day){
          assert.equal(state.day,before.day+1);
          assert.notEqual(state.daily_event.id,before.daily_event.id,'consecutive events exclude previous ID');
          assert.equal(state.visitors.length,3+Number(state.upgrades.display>=2));
          assert.equal(new Set(state.visitors.map(row=>row.id)).size,state.visitors.length);
          assert.ok(state.visitors.every(row=>row.status==='waiting'&&row.budget>=row.budget_range[0]&&row.budget<=row.budget_range[1]));
          assert.equal(state.walkins.used,0);
          assert.equal(state.walkins.day,state.day);
          assert.ok(state.walkins.budget>=60&&state.walkins.budget<=120);
        }else{
          assert.deepEqual(state.rng,before.rng,'first-week settlement or loss consumes no RNG');
        }
        assert.equal(state.negotiation,null,'closing day clears any pending quote');
        assert.ok(state.log.length<=60,'retained log remains bounded');
      }
      assert.deepEqual(input,before,'the wrapper never mutates its caller on success or failure');
      assert.deepEqual(state,step.state,`full private state and main RNG at revision ${step.state.revision}`);
    }
  });
}

test('day helper leaves revision, persisted RNG, and milestones to its wrapper',async()=>{
  const before=await newSyntheticState(123),state=structuredClone(before),rng=PythonRandom.fromState(state.rng);
  await applyDay(state,'endday',rng);
  assert.equal(state.revision,before.revision);
  assert.deepEqual(state.rng,before.rng);
  assert.notDeepEqual(rng.getstate(),before.rng);
  const week=structuredClone(fixture.cases.find(row=>row.label==='week-cash-664-quality-[70, 70]').initial);
  await applyDay(week,'endday',PythonRandom.fromState(week.rng));
  assert.equal(week.first_week_result,'won');
  assert.deepEqual(week.milestones,[],'milestones must not be awarded twice');
});

test('day wrapper discards partially advanced state on asynchronous budget failure',async()=>{
  const state=await newSyntheticState(999),snapshot=structuredClone(state);
  const subtle=globalThis.crypto.subtle,original=subtle.digest;
  // Fail the second hash, after sampling and the first domain hash succeeded.
  subtle.digest=async function(algorithm,data){
    if(algorithm==='SHA-512')throw Error('synthetic hash failure');
    return original.call(this,algorithm,data);
  };
  try{
    await assert.rejects(transition(state,'endday'),/synthetic hash failure/);
    assert.deepEqual(state,snapshot,'input, cash, revision, and main RNG survive a rejected candidate');
  }finally{subtle.digest=original;}
  const successful=await transition(state,'endday');
  const retry=await transition(snapshot,'endday');
  assert.deepEqual(successful,retry,'retry produces exactly the uninterrupted next day');
});

test('day wrapper discards completed candidate on validation or projection failure',async()=>{
  const state=await newSyntheticState(456),snapshot=structuredClone(state);
  await assert.rejects(transition(state,'endday',{validate:()=>{throw Error('synthetic commit validation failure');}}),/synthetic commit validation failure/);
  assert.deepEqual(state,snapshot);
  await assert.rejects(transition(state,'endday',{validate:candidate=>{candidate.migration={unsupported:true};}}),/state_shape_not_ported/);
  assert.deepEqual(state,snapshot);
});

test('day sequence respects source day envelope up to 10^12 and owner rejection beyond it',async()=>{
  const sample=fixture.cases.find(row=>row.label==='endless-day-999999999997-log-trim');
  const state=structuredClone(sample.steps.at(-1).state),snapshot=structuredClone(state);
  assert.equal(state.day,10**12);
  await assert.rejects(transition(state,'endday',{validate:candidate=>{
    if(candidate.day>10**12)throw new CoreGameError('存档字段损坏：day。');
  }}),error=>error instanceof CoreGameError&&error.message==='存档字段损坏：day。');
  assert.deepEqual(state,snapshot);
});

test('day dispatch errors do not mutate direct input or passed RNG',async()=>{
  for(const phase of ['active','week_summary','lost']){
    for(const command of ['endday','continue','unexpected']){
      if(phase==='active'&&command==='endday'||phase==='week_summary'&&command==='continue')continue;
      const state=await newSyntheticState(1);state.phase=phase;
      const snapshot=structuredClone(state),rng=PythonRandom.fromState(state.rng),rngBefore=rng.getstate();
      await assert.rejects(applyDay(state,command,rng),CoreGameError);
      assert.deepEqual(state,snapshot);
      assert.deepEqual(rng.getstate(),rngBefore);
    }
  }
});

test('day data stays detached from rule tables and exact budgets remain private',async()=>{
  const initial=await newSyntheticState(17),{state,observation}=await transition(initial,'endday');
  const text=JSON.stringify(observation);
  for(const forbidden of ['base_value','"rng"','"budget":','"cargo"'])assert.equal(text.includes(forbidden),false,forbidden);
  const original=structuredClone(EVENTS);
  state.daily_event.title='synthetic local edit';
  assert.deepEqual(EVENTS,original);
});

test('day oracle spans substantial sequences, every event and collection threshold',()=>{
  assert.equal(fixture.case_count,97);
  assert.equal(fixture.private_case_count,12);
  assert.equal(fixture.action_count,1495);
  const advancing=fixture.cases.flatMap(sample=>sample.steps).filter(row=>row.error===null&&row.state.phase==='active');
  assert.deepEqual([...new Set(advancing.map(row=>row.state.daily_event.id))].sort(),EVENTS.map(row=>row.id).sort());
  assert.deepEqual([...new Set(advancing.map(row=>row.state.demand.kind))].sort(),['artifact','bot','plant','signal','tool']);
  assert.deepEqual([...new Set(advancing.map(row=>row.state.demand.multiplier))].sort(),[1.25,1.35,1.45]);
});
