"""30 synthetic 40-day campaigns. Policy reads public observation only."""
import engine
import statistics
results=[]
for seed in range(30):
 state=engine.new_state(seed)
 counts={'rolls':0,'miracles':0,'fumbles':0,'negotiations':0}
 def act(command,*args):
  engine.apply_command(state,command,list(args))
  state['revision']+=1
  engine._validate_state(state)
  return engine.observation(state)
 obs=engine.observation(state)
 while obs['day']<=40 and obs['phase']!='lost':
  if obs['phase']=='week_summary':obs=act('continue')
  if obs['day']>40:break
  # Decision inputs are only the public observation from the last action.
  while obs['energy']>0:
   if obs['negotiation']:
    counts['negotiations']+=1
    obs=act('accept',obs['negotiation']['item_id']);continue
   eligible=[i for i in obs['inventory'] if not i['sale_attempted_today']]
   if eligible:
    item=eligible[0]
    price=max(1,round(sum(item['value_estimate'])/2*.90))
    obs=act('price',item['id'],str(price))
    preferred=next((v for v in obs['visitors'] if v['status']=='waiting' and v['preferred_kind']==item['kind']),None)
    obs=act('sell',item['id'],*([preferred['id']] if preferred else []))
    counts['rolls']+=1
    counts['miracles']+=obs['last_roll']['outcome']=='miracle'
    counts['fumbles']+=obs['last_roll']['outcome']=='fumble'
    if obs['negotiation']:
     counts['negotiations']+=1;obs=act('accept',obs['negotiation']['item_id'])
    continue
   if obs['crates']:
    obs=act('open',obs['crates'][0]['id']);continue
   supplier=next(s for s in obs['suppliers'] if s['id']=='salvage')
   if obs['energy']>=3 and obs['credits']>=supplier['cost']+obs['operating_cost'] and supplier['stock'] and len(obs['inventory'])+len(obs['crates'])<obs['capacity']:
    obs=act('buy','salvage');continue
   break
  obs=act('endday')
 results.append((obs['day'],obs['phase'],obs['credits'],counts))
print({'synthetic_games':len(results),'reached_day_41':sum(r[0]==41 for r in results),'lost':sum(r[1]=='lost' for r in results),'cash_min':min(r[2] for r in results),'cash_max':max(r[2] for r in results),'cash_median':statistics.median(r[2] for r in results),'rolls':sum(r[3]['rolls'] for r in results),'natural20':sum(r[3]['miracles'] for r in results),'natural1':sum(r[3]['fumbles'] for r in results),'negotiations_accepted':sum(r[3]['negotiations'] for r in results)})
