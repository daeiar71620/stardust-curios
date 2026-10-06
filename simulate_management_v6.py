"""Paired synthetic new games, decisions only from public observation.
No existing save is opened. No parameters, costs, probabilities, or state are
monkeypatched. Baseline is the frozen v5 module; candidate is production v6.
"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import engine
import _legacy_v5


def ordinary_left(o):
    return o.get('walkins',{}).get('remaining',999)


def estimate(item):
    return sum(item['value_estimate'])/2


def action(o,policy):
    """The policy boundary: this function receives no referee object or module."""
    if o['negotiation']:
        return ('accept',o['negotiation']['item_id'])
    if o['energy']<1:return None
    eligible=[i for i in o['inventory'] if not i['sale_attempted_today']]
    waiting=[v for v in o['visitors'] if v['status']=='waiting']
    if policy=='careful115':
        # Choose matching/ready goods first; retain unmatched expensive inventory
        # instead of dumping it into the limited low-budget walk-in slot.
        pairs=[]
        for item in eligible:
            for v in waiting:
                if v['preferred_kind']==item['kind'] and item['condition']>=v['min_condition']:
                    price=min(round(estimate(item)*1.15),v['budget_range'][1])
                    pairs.append((price,True,item,v))
            if ordinary_left(o) and item['condition']>=45 and estimate(item)<=120:
                price=min(120,round(estimate(item)*.90))
                pairs.append((price,False,item,None))
        if pairs:
            _,_,item,visitor=max(pairs,key=lambda r:(r[1],r[0]))
            price=min(round(estimate(item)*(1.15 if visitor else .90)),visitor['budget_range'][1] if visitor else 120)
            if item['price']!=price:return ('price',item['id'],str(price))
            return ('sell',item['id'],*([visitor['id']] if visitor else []))
        # Repair a near-fit only when a matching waiting customer can plausibly
        # use it today and the public estimate leaves room after the repair bill.
        if o['energy']>=3:
            for item in eligible:
                target=next((v for v in waiting if v['preferred_kind']==item['kind']
                    and 0<v['min_condition']-item['condition']<=25),None)
                if target and item['repairs_remaining'] and not item['repair_attempted_today'] and estimate(item)>item['repair_cost']+45 and o['credits']>=item['repair_cost']+o['operating_cost']:
                    return ('repair',item['id'])
    elif eligible:
        item=eligible[0]
        price=max(1,round(estimate(item)*(.90 if policy=='rush90' else 1.60)))
        visitor=next((v for v in waiting if v['preferred_kind']==item['kind']),None)
        if visitor is None and not ordinary_left(o):
            visitor=max(waiting,key=lambda v:(v['budget_range'][0]>=price,v['budget_range'][1],item['condition']>=v['min_condition'])) if waiting else 'none'
        if visitor=='none':return None
        if item['price']!=price:return ('price',item['id'],str(price))
        return ('sell',item['id'],*([visitor['id']] if visitor else []))
    if o['crates']:
        return ('open',o['crates'][0]['id'])
    supplier=next(s for s in o['suppliers'] if s['id']=='salvage')
    # The careful policy carries at most 3 goods before ordering more. The others
    # use all available capacity, as in the earlier simple-policy baseline.
    buy_room=len(o['inventory'])+len(o['crates'])<(min(o['capacity'],3) if policy=='careful115' else o['capacity'])
    if o['energy']>=3 and o['credits']>=supplier['cost']+o['operating_cost'] and supplier['stock'] and buy_room:
        return ('buy','salvage')
    return None


def run(module,seed,policy,days):
    # Only the runner/referee owns private synthetic state. Decisions above use o.
    state=module.new_state(seed)
    o=module.observation(state)
    metrics=dict(seed=seed,cash=0,lost=False,daily_net=[],inventory_overnight=[],
                 rolls=0,sales=0,counters=0,miracles=0,fumbles=0,repairs=0,initial_failures_no_counter=0)
    def act(command,*args):
        nonlocal o
        before=o
        module.apply_command(state,command,list(args));state['revision']+=1
        module._validate_state(state)
        o=module.observation(state)
        if command=='sell':
            metrics['rolls']+=1
            metrics['miracles']+=o['last_roll']['outcome']=='miracle'
            metrics['fumbles']+=o['last_roll']['outcome']=='fumble'
            metrics['initial_failures_no_counter']+=o['last_roll']['outcome']=='failure' and o['negotiation'] is None
        if command=='accept':metrics['counters']+=1
        if command=='repair':metrics['repairs']+=1
        if command in ('sell','accept'):metrics['sales']+=o['credits']>before['credits']
    while o['day']<=days and o['phase']!='lost':
        if o['phase']=='week_summary':act('continue')
        if o['day']>days:break
        initial=o['credits']
        for _ in range(150):
            choice=action(o,policy)
            if choice is None:break
            act(*choice)
        else:raise AssertionError('Public policy did not converge')
        metrics['inventory_overnight'].append(len(o['inventory'])+len(o['crates']))
        act('endday');metrics['daily_net'].append(o['credits']-initial)
    metrics.update(cash=o['credits'],lost=o['phase']=='lost',day=o['day'],end_inventory=len(o['inventory'])+len(o['crates']))
    return metrics


def aggregate(rows):
    cash=sorted(r['cash'] for r in rows);n=len(rows)
    daily=[x for r in rows for x in r['daily_net']]
    inv=[x for r in rows for x in r['inventory_overnight']]
    sums=lambda k:sum(r[k] for r in rows)
    return dict(games=n,lost=sums('lost'),cash_min=cash[0],cash_p10=cash[n//10],cash_median=statistics.median(cash),
        cash_p90=cash[9*n//10],cash_max=cash[-1],mean_daily_net=round(statistics.mean(daily),2),
        negative_day_pct=round(100*sum(x<0 for x in daily)/len(daily),2),
        mean_overnight_inventory=round(statistics.mean(inv),3),inventory_p90=sorted(inv)[9*len(inv)//10],
        inventory_days_pct=round(100*sum(x>0 for x in inv)/len(inv),2),
        sale_pct=round(100*sums('sales')/sums('rolls'),2),rolls=sums('rolls'),sales=sums('sales'),counters=sums('counters'),
        normal_failures_no_counter=sums('initial_failures_no_counter'),repairs=sums('repairs'),miracles=sums('miracles'),fumbles=sums('fumbles'))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--games',type=int,default=50);parser.add_argument('--days',type=int,default=40)
    parser.add_argument('--output',type=Path,default=Path(__file__).with_name('management-simulation.json'))
    args=parser.parse_args()
    result=dict(method='Fresh paired seed IDs; trajectories diverge after different decisions. Public-policy only; each action validated.',
        days=args.days,seed_range=[0,args.games-1],engine_sha256=hashlib.sha256(Path(engine.__file__).read_bytes()).hexdigest(),runs=[])
    for policy in ('rush90','careful115','aggressive160'):
        pair={}
        for module,label in ((_legacy_v5,'v5'),(engine,'v6')):
            rows=[run(module,seed,policy,args.days) for seed in range(args.games)]
            summary=aggregate(rows);pair[label]=rows
            row=dict(variant=label,policy=policy,summary=summary,seeds=rows)
            result['runs'].append(row);print(json.dumps(dict(variant=label,policy=policy,**summary)),flush=True)
        delta=[new['cash']-old['cash'] for old,new in zip(pair['v5'],pair['v6'])]
        result.setdefault('paired_cash_deltas',{})[policy]=dict(median=statistics.median(delta),min=min(delta),max=max(delta))
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
