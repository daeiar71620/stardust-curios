"""Synthetic in-memory Python v9 oracle; never reads a private save or writes one."""
import argparse,copy,importlib.util,json,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--engine',required=True);args=p.parse_args();path=Path(args.engine).resolve();sys.path.insert(0,str(path.parent));spec=importlib.util.spec_from_file_location('core_oracle_engine',path);e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)

def normalize(v):return json.loads(json.dumps(v,ensure_ascii=False))
def state(seed):
 s=e.new_state(seed);s['revision']=1;return s

def run(label,s,commands,seed=None):
 e._validate_state(s);initial=normalize(s);steps=[]
 for command,argv in commands:
  candidate=copy.deepcopy(s)
  try:
   e.apply_command(candidate,command,argv);candidate['revision']+=1;e._validate_state(candidate);s=candidate;error=None
  except e.GameError as exc:error=str(exc)
  steps.append({'command':command,'args':argv,'error':error,'state':normalize(s),'observation':e.observation(s)})
 return {'label':label,'seed':str(seed)if seed is not None else None,'initial':initial,'initial_observation':e.observation(initial),'steps':steps}

def cargo(row,condition=77):
 return {'catalog_id':row[0],'name':row[1],'rarity':row[2],'kind':row[3],'base_value':round(row[4]*1.02),'condition':condition,'description':row[5],'origin':e.SUPPLIERS['curated']['name'],'collected':False,'repairs':0,'last_sale_day':0,'last_repair_day':0}
def item(s,row,number,condition,collected=False):
 x=cargo(row,condition);x.update(id=f'I{number:03d}',price=1,collected=collected);x['price']=max(1,round(e._reference_value(s,x)*.93));return x

cases=[]
for seed in list(range(30))+[42,2**53-1,2**128+17]:
 s=state(seed)
 commands=[('buy',['salvage']),('open',['c001']),('price',['i001','100']),('price',['I001','100']),('buy',['curated']),('open',['C002']),('price',['I002','9999']),('buy',['salvage']),('open',['C003']),('buy',['salvage']),('open',['C004']),('buy',['curated'])]
 cases.append(run(f'seed-{seed}',s,commands,seed))
for index,row in enumerate(e.CATALOG):
 s=state(100+index);s['credits']=150;s['energy']=11;s['next_crate']=2;s['supplier_stock']['curated']=1;s['crates']=[{'id':'C001','supplier':'curated','name':'夜航封存箱','cargo':cargo(row,48+index*2)}]
 cases.append(run(f'reveal-{row[0]}',s,[('open',['C001']),('price',['I001',' 75 '])]))
s=state(555);s['credits']=10000
commands=[]
for index,supplier in enumerate(['salvage','salvage','salvage','salvage','curated','curated'],1):commands += [('buy',[supplier]),('open',[f'C{index:03d}'])]
commands += [('price',['I001','1']),('price',['I001','9999']),('buy',['salvage']),('buy',['curated']),('open',['C404']),('price',['I001','0']),('price',['I001','01']),('price',['I001','+1']),('price',['I001','1.0']),('price',['I001','\u008575\u0085']),('price',['I001','\ufeff75']),('price',['I001','75\u3000']),('price',['I001','\u001c75']),('price',['I001','75\u001f'])]
cases.append(run('resources-zero-energy-and-parsing',s,commands))
s=state(123);s['credits']=10000;s['next_item']=8;s['stats']['crates_opened']=7;s['inventory']=[item(s,e.CATALOG[i],i+1,75)for i in range(7)];s['discovered']=[i['catalog_id']for i in s['inventory']]
cases.append(run('full-shelf',s,[('buy',['salvage']),('buy',['__proto__']),('price',['I008','50'])]))
s=state(234);s['day']=8;s['walkins']['day']=8;s['walkins']['budget']=e._make_walkins(e._rng(s),8)['budget'];s['first_week_result']='won';s['milestones']=[{'id':'first_week','title':e.MILESTONES[0]['title'],'day':7}];s['credits']=2000;s['reputation']=20;s['upgrades']={'workbench':1,'shelf':1,'display':0};s['stats']['days_traded']=7;s['stats']['crates_opened']=6;s['next_item']=7
s['collection']=[item(s,row,i+1,76,collected=True)for i,row in enumerate(e.CATALOG[:5])];s['inventory']=[item(s,e.CATALOG[17],6,77)];s['discovered']=[i['catalog_id']for i in s['collection']+s['inventory']]
cases.append(run('ready-milestone-event-quality-snapshot',s,[('price',['I006','120'])]))
s=state(345);commands=[('buy',['salvage']),('open',['C001'])]+[('price',['I001',str(1+i%9999)])for i in range(240)];cases.append(run('long-revision-log-and-rng-sequence',s,commands))
print(json.dumps({'cases':cases,'case_count':len(cases),'action_count':sum(len(c['steps'])for c in cases)},ensure_ascii=False,separators=(',',':')))
