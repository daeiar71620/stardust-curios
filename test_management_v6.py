"""Current v6 contract. Synthetic in-memory and temporary fixtures only."""
import copy
import json
from pathlib import Path
import random
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

import engine
import _legacy_v1
import _legacy_v2
import _legacy_v3
import _legacy_v4
import _legacy_v5
from test_percentile_v5 import rng_for, fixture as v5_fixture
from test_dice_engine import fixture as d20_fixture


def fixture(*rolls, price=90, condition=80, kind='wrench', count=1):
    state = engine.new_state(42)
    row = engine.CATALOG_BY_ID[kind]
    state['inventory'] = [dict(id=f'I{x+1:03}', catalog_id=row[0], name=row[1], rarity=row[2],
        kind=row[3], base_value=row[4], condition=condition, description=row[5],
        origin=engine.SUPPLIERS['salvage']['name'], collected=False, repairs=0,
        last_sale_day=0, last_repair_day=0, price=price) for x in range(count)]
    state['next_item'] = count + 1
    state['discovered'] = [row[0]]
    state['rng'] = rng_for(*(rolls or (99,)))
    return state


def named(state, match=True):
    row = next(r for r in engine.CUSTOMERS if (r[3] == state['inventory'][0]['kind']) == match)
    key,name,role,kind,condition,low,high=row
    visitor=dict(id=key,name=name,role=role,preferred_kind=kind,
        preference_label=f'偏爱{engine.KINDS[kind]}，品相{condition}%以上更喜欢',
        min_condition=condition,budget_range=[low,high],premium=1.25,status='waiting',budget=low)
    state['visitors']=[visitor]+[v for v in state['visitors'] if v['id']!=key][:2]
    return visitor


class ManagementV6Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='v6-synthetic-')
        self.root=Path(self.tmp.name)
        self.store=engine.GameStore(self.root/'synthetic.json')

    def tearDown(self): self.tmp.cleanup()

    def write(self,state):
        engine._validate_state(state)
        engine._atomic_json(self.store.save_path,state)
        return self.store.execute('status')

    def unchanged_error(self,command,*args):
        before=self.store.save_path.read_bytes(),self.store.observation_path.read_bytes()
        with self.assertRaises(engine.GameError): self.store.execute(command,*args)
        self.assertEqual(before,(self.store.save_path.read_bytes(),self.store.observation_path.read_bytes()))

    def pending(self,second=50,named_buyer=False):
        state=fixture(99,second)
        visitor=named(state) if named_buyer else None
        self.write(state)
        return self.store.execute('sell','I001',*([visitor['id']] if visitor else []))

    def test_public_walkin_capacity_budget_and_no_private_fields(self):
        state=fixture();public=self.write(state)
        self.assertEqual(public['version'],6)
        self.assertEqual(public['walkins']['remaining'],1)
        self.assertEqual(public['walkins']['budget_range'],[60,120])
        self.assertEqual(public['walkins']['min_condition'],45)
        for key in ('"rng":','"budget":','"base_value":','"context":'):
            self.assertNotIn(key,json.dumps(public))
        for command,args in [('inspect',['I001']),('market',[]),('visitors',[])]:
            result=self.store.execute(command,*args)
            self.assertIn('sale_options' if command=='inspect' else 'walkins',result)

    def test_public_reference_and_eligibility_ignore_exact_values_and_budgets(self):
        state=fixture();other=copy.deepcopy(state)
        other['inventory'][0]['base_value']*=3
        other['walkins']['budget']=60
        for visitor in other['visitors']: visitor['budget']=visitor['budget_range'][0]
        self.assertEqual(engine.observation(state),engine.observation(other))
        option=engine.observation(state)['inventory'][0]['sale_options'][0]
        self.assertEqual(option['public_reference'],round(engine._reference_value(state,state['inventory'][0])))
        self.assertEqual(option['max_counter_ask'],min(120,option['public_reference']*5//4))

    def test_reasonable_ordinary_failure_enters_one_binding_counter(self):
        state=fixture(99);public=self.write(state)
        self.assertTrue(public['inventory'][0]['sale_options'][0]['counter_eligible'])
        public=self.store.execute('sell','I001')
        self.assertEqual(public['last_roll']['outcome'],'failure')
        self.assertIsNotNone(public['negotiation'])
        self.assertEqual(public['walkins']['remaining'],0)
        self.assertLess(public['negotiation']['counter_offer'],90)
        self.assertLessEqual(public['negotiation']['counter_offer'],state['walkins']['budget'])
        self.assertEqual(public['energy'],state['energy']-1)

    def test_absurd_ordinary_failure_leaves_without_counter_and_consumes_visit(self):
        self.write(fixture(99,price=9999,count=2))
        public=self.store.execute('sell','I001')
        self.assertIsNone(public['negotiation'])
        self.assertEqual(public['walkins']['remaining'],0)
        self.assertIn('没有还价',public['last_event']['title'])
        self.unchanged_error('sell','I002')
        self.unchanged_error('accept','I001')

    def test_budget_ceiling_and_public_reference_boundary_are_inclusive(self):
        state=fixture();item=state['inventory'][0]
        option=engine._sale_option(state,item,None)
        item['price']=option['max_counter_ask']
        self.assertTrue(engine._sale_option(state,item,None)['counter_eligible'])
        item['price']+=1
        self.assertFalse(engine._sale_option(state,item,None)['counter_eligible'])
        state=fixture(kind='letter',price=120);item=state['inventory'][0]
        self.assertTrue(engine._sale_option(state,item,None)['counter_eligible'])
        item['price']=121
        self.assertIn('公开预算',','.join(engine._sale_option(state,item,None)['reasons']))

    def test_walkin_condition_boundary_and_cheap_one_coin_no_counter(self):
        state=fixture(condition=45,price=50)
        self.assertTrue(engine._sale_option(state,state['inventory'][0],None)['counter_eligible'])
        state['inventory'][0]['condition']=44
        self.assertFalse(engine._sale_option(state,state['inventory'][0],None)['counter_eligible'])
        state['inventory'][0].update(condition=80,price=1)
        self.assertFalse(engine._sale_option(state,state['inventory'][0],None)['counter_eligible'])

    def test_unfit_condition_normal_failure_is_terminal(self):
        self.write(fixture(99,condition=44,price=60))
        public=self.store.execute('sell','I001')
        self.assertIsNone(public['negotiation'])
        self.assertIn('品相未达到45%',public['last_event']['text'])
        self.assertEqual(public['walkins']['used'],1)

    def test_named_preference_and_condition_are_public_deterministic_requirements(self):
        state=fixture(99);visitor=named(state,False);self.write(state)
        option=next(o for o in engine.observation(state)['inventory'][0]['sale_options'] if o['customer_id']==visitor['id'])
        self.assertFalse(option['counter_eligible']);self.assertIn('类别不合顾客偏好',option['reasons'])
        public=self.store.execute('sell','I001',visitor['id'])
        self.assertIsNone(public['negotiation'])
        self.assertEqual(public['walkins']['remaining'],1)
        state=fixture(99,condition=44,price=60);visitor=named(state);self.write(state)
        public=self.store.execute('sell','I001',visitor['id'])
        self.assertIsNone(public['negotiation'])

    def test_matching_named_failure_bargains_and_named_cap_remains(self):
        state=fixture(99,count=2);visitor=named(state);self.write(state)
        public=self.store.execute('sell','I001',visitor['id'])
        self.assertIsNotNone(public['negotiation'])
        self.store.execute('decline','I001')
        self.unchanged_error('sell','I002',visitor['id'])
        self.assertEqual(self.store.execute('status')['walkins']['remaining'],1)

    def test_miracle_01_at_9999_ignores_eligibility_and_exact_budget(self):
        for use_named in (False,True):
            state=fixture(1,price=9999,condition=5)
            visitor=named(state,False) if use_named else None
            self.write(state)
            public=self.store.execute('sell','I001',*([visitor['id']] if visitor else []))
            self.assertEqual(public['credits'],state['credits']+9999)
            self.assertEqual(public['last_roll']['outcome'],'miracle')
            self.assertIsNone(public['negotiation']);self.assertEqual(public['inventory'],[])

    def test_fumble100_never_bargains_and_consumes_ordinary_visit(self):
        self.write(fixture(100))
        public=self.store.execute('sell','I001')
        self.assertEqual(public['last_roll']['outcome'],'fumble')
        self.assertIsNone(public['negotiation']);self.assertEqual(public['walkins']['used'],1)

    def test_deterministic_checks_add_no_rng_draw(self):
        state=fixture(99);before=engine._rng(state)
        before.randint(0,9);before.randint(0,9)
        self.write(state);self.store.execute('sell','I001')
        self.assertEqual(engine._rng(self.store.load()).getstate(),before.getstate())

    def test_invalid_attempts_zero_energy_and_unknown_customer_are_atomic(self):
        state=fixture(count=2);self.write(state)
        self.unchanged_error('sell','missing');self.unchanged_error('sell','I001','missing')
        state['energy']=0;self.write(state);self.unchanged_error('sell','I001')
        self.assertEqual(self.store.load()['walkins']['used'],0)

    def test_reprice_switch_items_restart_process_read_commands_do_not_refresh(self):
        state=fixture(99,price=9999,count=2);self.write(state)
        self.store.execute('sell','I001');self.store.execute('price','I002','40')
        before=self.store.save_path.read_bytes()
        for command in ('status','market','visitors','codex'):
            engine.GameStore(self.store.save_path).execute(command)
        self.assertEqual(before,self.store.save_path.read_bytes())
        self.unchanged_error('sell','I002')
        self.store.execute('price','I001','1');self.unchanged_error('sell','I001')
        public=self.store.execute('endday')
        self.assertEqual((public['day'],public['walkins']['used'],public['walkins']['remaining']),(2,0,1))

    def test_named_buyer_remains_available_after_ordinary_visit_used(self):
        state=fixture(99,1,price=9999,count=2);visitor=named(state);self.write(state)
        self.store.execute('sell','I001')
        public=self.store.execute('sell','I002',visitor['id'])
        self.assertEqual(public['stats']['sales_count'],1)
        self.assertEqual(public['walkins']['used'],1)

    def test_accept_decline_remain_free_and_no_random_draw(self):
        for command in ('accept','decline'):
            self.pending();before=self.store.load()
            public=self.store.execute(command,'I001');after=self.store.load()
            self.assertEqual((before['energy'],before['rng']),(after['energy'],after['rng']))
            self.assertEqual(public['walkins']['used'],1);self.assertIsNone(public['negotiation'])
            self.unchanged_error(command,'I001')

    def test_final_preview_exact_strict_bounds_and_one_energy_retry(self):
        public=self.pending(50)
        pending=public['negotiation'];counter=pending['counter_offer'];price=counter+1
        for bad in (counter,90,91):
            self.unchanged_error('preview-offer','I001',str(bad));self.unchanged_error('offer','I001',str(bad))
        before=self.store.save_path.read_bytes()
        public=self.store.execute('preview-offer','I001',str(price));preview=public['negotiation']['preview']
        self.assertEqual(before,self.store.save_path.read_bytes())
        self.assertEqual(preview['threshold'],engine._final_chance(preview['modifier'],counter,price)[1])
        result=self.store.execute('offer','I001',str(price))
        self.assertEqual(result['last_roll']['threshold'],preview['threshold'])
        self.assertEqual(result['energy'],public['energy']-1);self.assertIsNone(result['negotiation'])
        self.assertEqual(result['walkins']['used'],1);self.unchanged_error('offer','I001',str(price))

    def test_final_failure_cannot_return_to_old_counter(self):
        public=self.pending(99);price=public['negotiation']['counter_offer']+1
        result=self.store.execute('offer','I001',str(price))
        self.assertEqual(result['last_roll']['outcome'],'failure')
        self.unchanged_error('accept','I001');self.unchanged_error('sell','I001')

    def test_final_miracle_and_fumble_still_apply(self):
        for value,outcome in [(1,'miracle'),(100,'fumble')]:
            public=self.pending(value);price=public['negotiation']['counter_offer']+1
            result=self.store.execute('offer','I001',str(price))
            self.assertEqual(result['last_roll']['outcome'],outcome)

    def test_final_formula_and_initial_formula_unchanged_from_v5(self):
        for bonus in range(-20,66,5):
            for counter in (1,40,100,500,9997):
                for price in (counter+1,min(9999,counter*2),9999):
                    self.assertEqual(engine._final_chance(bonus,counter,price),_legacy_v5._final_chance(bonus,counter,price))
        for price in range(1,10000):
            context=dict(reference=100,budget=90,modifier=5,modifiers=[dict(label='口碑',value=5)])
            self.assertEqual(engine._initial_chance(context,price),_legacy_v5._initial_chance(context,price))

    def test_all_hundred_digit_pairs_still_use_exactly_two_d10_draws(self):
        seen=set()
        for tens in range(10):
            for ones in range(10):
                state=fixture();source=mock.Mock();source.randint.side_effect=[tens,ones]
                roll=engine._trade_roll(state,source,state['inventory'][0],None,90,engine._trade_context(state,state['inventory'][0],None),'initial')
                seen.add(roll['roll']);self.assertEqual(source.randint.call_args_list,[mock.call(0,9),mock.call(0,9)])
                self.assertEqual(roll['success'],roll['roll']==1 or roll['roll']!=100 and roll['roll']<=roll['threshold'])
        self.assertEqual(seen,set(range(1,101)))

    def test_economy_costs_prices_upgrades_unchanged(self):
        for field in ('CATALOG','SUPPLIERS','UPGRADE_RULES','EVENTS','SET_RULES','OPERATING_COST'):
            self.assertEqual(getattr(engine,field),getattr(_legacy_v5,field))

    def test_copy_migration_v1_to_v5_preserves_rng_resources_source_and_history(self):
        for version in range(1,6):
            with self.subTest(version=version):
                module=globals()[f'_legacy_v{version}'];state=module.new_state(17)
                module.apply_command(state,'buy',['salvage']);module.apply_command(state,'open',['C001'])
                source=self.root/f'old-{version}.json';source.write_text(json.dumps(state));raw=source.read_bytes()
                store=engine.GameStore(self.root/f'new-{version}.json')
                public=store.execute(f'import-v{version}',str(source));result=store.load()
                self.assertEqual(source.read_bytes(),raw)
                for field in ('credits','inventory','crates','collection','upgrades','rng','day','energy'):
                    self.assertEqual(json.loads(raw)[field] | {"display": 0} if version==1 and field=="upgrades" else json.loads(raw)[field],result[field],field)
                self.assertEqual(result['version'],6)
                self.assertEqual(result['roll_history'],state.get('roll_history',[]))
                self.assertEqual(public['walkins']['used'],int(version<=2))
                with self.assertRaises(engine.GameError):store.execute(f'import-v{version}',str(source))

    def test_old_pending_quote_honored_despite_new_ineligibility(self):
        for version in (3,4,5):
            for action in ('accept','decline','offer'):
                with self.subTest(version=version,action=action):
                    module=globals()[f'_legacy_v{version}']
                    state=v5_fixture(50,1) if version==5 else d20_fixture(10,20)
                    state['version']=version
                    module.apply_command(state,'sell',['I001']);module._validate_state(state)
                    raw=json.dumps(state).encode();migrated=getattr(engine,f'migrate_v{version}')(raw)
                    self.write(migrated);before=self.store.load()
                    self.assertEqual(before['negotiation']['counter_offer'],state['negotiation']['counter_offer'])
                    self.assertFalse(engine.observation(before)['inventory'][0]['sale_options'][0]['counter_eligible'])
                    self.assertEqual(before['walkins']['used'],1)
                    public=self.store.execute(action,'I001',*(['100'] if action=='offer' else []))
                    self.assertIsNone(public['negotiation'])
                    self.assertEqual(public['roll_history'][0]['rules_version'],version)
                    if action=='offer':self.assertEqual(public['roll_history'][-1]['rules_version'],6)

    def test_v5_used_ordinary_capacity_carries_even_after_item_sold(self):
        state=v5_fixture(1,price=9999);_legacy_v5.apply_command(state,'sell',['I001'])
        migrated=engine.migrate_v5(json.dumps(state).encode());public=self.write(migrated)
        self.assertEqual(public['walkins']['used'],1)
        self.assertEqual(public['roll_history'],state['roll_history'])
        self.assertEqual(self.store.execute('endday')['walkins']['remaining'],1)

    def test_v5_named_only_attempt_does_not_consume_walkin(self):
        state=v5_fixture(1);_legacy_v5.apply_command(state,'sell',['I001',state['visitors'][0]['id']])
        public=self.write(engine.migrate_v5(json.dumps(state).encode()))
        self.assertEqual(public['walkins']['remaining'],1)

    def test_mixed_v3_v4_v5_history_retains_boundaries_into_v6(self):
        state=d20_fixture(10,20);state['version']=3;_legacy_v3.apply_command(state,'sell',['I001'])
        v4=_legacy_v4.migrate_v3(json.dumps(state).encode())
        _legacy_v4.apply_command(v4,'offer',['I001','100'])
        v5=_legacy_v5.migrate_v4(json.dumps(v4).encode())
        _legacy_v5.apply_command(v5,'endday',[])
        v6=engine.migrate_v5(json.dumps(v5).encode());self.write(v6)
        self.assertEqual(v6['roll_history'],v5['roll_history'])
        self.assertEqual(v6['engine_upgrade'],v5['engine_upgrade'])
        self.assertEqual([r['rules_version'] for r in v6['roll_history']],[3,4])

    def test_migration_rejects_public_projection_and_in_place_or_existing_projection(self):
        state=_legacy_v5.new_state(42);source=self.root/'v5.json';source.write_text(json.dumps(state))
        with self.assertRaises(engine.GameError):engine.GameStore(source).execute('import-v5',str(source))
        source.write_text(json.dumps(_legacy_v5.observation(state)))
        with self.assertRaises(engine.GameError):self.store.execute('import-v5',str(source))
        source.write_text(json.dumps(state));self.store.observation_path.write_text('{}')
        with self.assertRaises(engine.GameError):self.store.execute('import-v5',str(source))

    def test_capacity_corruption_and_version_relabeling_rejected(self):
        self.pending();good=self.store.load()
        for change in ('used','day','budget','history_version','pending_origin','management_boundary'):
            state=copy.deepcopy(good)
            if change=='used':state['walkins']['used']=0
            elif change=='day':state['walkins']['day']+=1
            elif change=='budget':state['walkins']['budget']=9999
            elif change=='history_version':state['roll_history'][0]['rules_version']=5
            elif change=='pending_origin':state['negotiation']['origin_rules_version']=5
            else:state['management_upgrade']={'from_version':5,'source_day':1,'source_phase':'active','source_roll_seq':2,'walkins_used_on_import':0}
            with self.subTest(change=change):
                with self.assertRaises(engine.GameError):engine._validate_state(state)

    def test_simultaneous_ordinary_attempts_allow_only_one_commit(self):
        self.write(fixture(99,price=9999,count=2))
        def sell(i):
            try:return engine.GameStore(self.store.save_path).execute('sell',i)['walkins']['used']
            except engine.GameError:return 'denied'
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(sell,['I001','I002']))
        self.assertEqual(sorted(map(str,results)),['1','denied'])
        self.assertEqual(len(self.store.load()['roll_history']),1)

    def test_public_projection_write_failure_does_not_repeat_capacity(self):
        self.write(fixture(99,price=9999));original=engine._atomic_json
        def write(path,data):
            if path==self.store.observation_path:raise OSError('synthetic projection error')
            return original(path,data)
        with mock.patch.object(engine,'_atomic_json',side_effect=write):
            public=self.store.execute('sell','I001')
        self.assertIn('persistence_warning',public)
        self.assertEqual(self.store.load()['walkins']['used'],1)
        self.assertEqual(self.store.execute('status')['walkins']['remaining'],0)

    def test_endday_closes_pending_then_next_day_resets_capacity_only_once(self):
        self.pending();public=self.store.execute('endday')
        self.assertIsNone(public['negotiation']);self.assertEqual(public['walkins']['remaining'],1)
        before=self.store.save_path.read_bytes();self.store.execute('status')
        self.assertEqual(self.store.save_path.read_bytes(),before)


if __name__=='__main__':unittest.main()
