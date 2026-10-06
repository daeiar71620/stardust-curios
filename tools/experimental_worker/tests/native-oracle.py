"""Composes existing synthetic oracles into a full-dispatch/public-view oracle."""
import argparse,contextlib,copy,importlib.util,io,json,runpy,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--engine',required=True);args=p.parse_args();engine=Path(args.engine).resolve();sys.path.insert(0,str(engine.parent));spec=importlib.util.spec_from_file_location('integrated_native_oracle',engine);e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
ROOT=Path(__file__).resolve().parent
class DiscardOutput:
 def write(self,text):return len(text)
 def flush(self):pass
cases=[]
count=0;actions=0;pending_states=[]
for group in ('core','management','day','trade'):
 with contextlib.redirect_stdout(DiscardOutput()):data=runpy.run_path(str(ROOT/(group+'-oracle.py')),run_name='__main__')
 for case in data['cases']+data.get('private_cases',[]):
  steps=[]
  for step in case['steps']:
   state=step['state']
   if state['negotiation']is not None and len(pending_states)<8:pending_states.append(state)
   steps.append({**step,'args':step.get('args',[]),'observation':e.observation(state),'mutated':step['error']is None})
  sample={'label':group+'/'+case['label'],'initial':case['initial'],'initial_observation':e.observation(case['initial']),'steps':steps}
  print(json.dumps(sample,ensure_ascii=False,separators=(',',':')),flush=True)
  count+=1;actions+=len(steps)
 del data

def normalize(v):return json.loads(json.dumps(v,ensure_ascii=False))
def read_steps(label,initial,commands):
 s=copy.deepcopy(initial);e._validate_state(s);steps=[]
 for command,argv in commands:
  public=e.observation(s);result=public;error=None
  try:
   if command=='market':result={k:public[k]for k in ['revision','day','credits','energy','demand','suppliers','daily_event','visitors','walkins','operating_cost']}
   elif command=='codex':result=public['codex']
   elif command=='visitors':result={'day':public['day'],'visitors':public['visitors'],'walkins':public['walkins']}
   elif command=='inspect':
    result=next((i for i in public['inventory']+public['collection']if i['id']==argv[0].upper()),None)
    if result is None:raise e.GameError(f'未找到物品 {argv[0]}。盲箱需先 open 才能查看内容。')
   elif command=='preview-offer':
    pending=s['negotiation']
    if pending is None or pending['item_id']!=argv[0].upper():raise e.GameError('这件货没有等待答复的还价；用 status 查看。')
    price=e._final_price(pending,argv[1]);public['negotiation']['preview']=dict(e._offer_forecast(s,pending,price),suggested=False)
  except e.GameError as exc:error=str(exc)
  steps.append({'command':command,'args':argv,'error':error,'state':normalize(s),'observation':public,'result':result,'mutated':False})
 cases.append({'label':label,'initial':normalize(s),'initial_observation':e.observation(s),'steps':steps})
s=e.new_state(4321);s['revision']=1;e.apply_command(s,'buy',['salvage']);s['revision']+=1;e.apply_command(s,'open',['C001']);s['revision']+=1
read_steps('reads/normal',s,[(c,[])for c in ['status','market','codex','visitors']]+[('inspect',['i001']),('inspect',['C001']),('preview-offer',['I001','50'])])
for index,s in enumerate(pending_states):
 p=s['negotiation'];lo=p['counter_offer']+1;hi=p['original_price']-1
 commands=[('status',[]),('inspect',[p['item_id']]),('preview-offer',[p['item_id'],str(lo)]),('preview-offer',[p['item_id'],str(hi)]),('preview-offer',[p['item_id'],str(p['original_price'])]),('preview-offer',['I404','50'])]
 read_steps(f'reads/pending-{index}',s,commands)
for sample in cases:
 print(json.dumps(sample,ensure_ascii=False,separators=(',',':')),flush=True);count+=1;actions+=len(sample['steps'])
print(json.dumps({'summary':True,'case_count':count,'action_count':actions}),flush=True)
