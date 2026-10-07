"""Headless UI checks using isolated synthetic fixtures, never user saves."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from spectator import (ObservationReader, Renderer, Spectator, TABS, main, safe_color, number,
                       public_roll, public_negotiation, roll_math, roll_status, percentile_preview)


def fixture():
    item={'id':'I001','art_id':'music','name':'彗星玻璃八音盒','kind':'artifact','rarity':'rare','color':'#b7a2ff',
          'condition':76,'price':150,'value_estimate':[130,175],'description':'每次彗星经过，它会多记住一个音符。'}
    return {'version':9,'revision':1,'day':8,'credits':780,'energy':13,'max_energy':13,'reputation':8,
      'phase':'active','inventory':[item], 'collection':[dict(item,collected=True)],'crates':[],
      'capacity':10,'demand':{'label':'机器人收藏热 · +25%'},
      'last_event':{'seq':1,'title':'小店继续开门','text':'首周之后，新的旅客推开了门。','item':item},
      'daily_event':{'title':'星灯夜市','description':'暖灯亮起，客人愿意多停留一会儿。'},
      'campaign':{'title':'持续经营','unlimited':True,'next_milestone':{'title':'街区熟面孔','goals':[
         {'key':'credits','label':'现金','current':780,'target':1400},
         {'key':'collection','label':'收藏','current':1,'target':5},
         {'key':'reputation','label':'声望','current':8,'target':12},
         {'key':'upgrades','label':'升级','current':1,'target':2}]}},
      'visitors':[{'id':'mira','name':'米拉','role':'星港机修师','preference_label':'偏爱工具，品相45%以上更喜欢','budget_range':[130,340],'status':'waiting'}],
      'codex':{'total':24,'discovered':1,'collected':1,'entries':[dict(item,discovered=True,collected=True),{'name':'袖珍巡航鲸','kind':'bot','rarity':'legendary','description':'绕灯游动。','discovered':False,'collected':False}]},
      'upgrades':{'workbench':1,'shelf':1,'display':0},
      'upgrade_details':[{'id':'workbench','name':'工作台','level':1,'max_level':3,'effect':'修理费减18%','next_effect':'修理费减36%','next_cost':110}],
      'collection_sets':[{'id':'tool','name':'星港修理铺','current':1,'required':3,'description':'工具收藏集齐后修理费减少'}],
      'log':[{'day':8,'text':'小店又迎来一个崭新的早晨。'}]}


class RendererTests(unittest.TestCase):
    def setUp(self):self.renderer=Renderer();self.obs=fixture()
    def test_all_tabs_at_portrait_wide_and_phone_sizes(self):
        for size in [(760,1240),(1320,940),(390,844),(1364,1024),(320,568)]:
            for tab,_ in TABS:
                with self.subTest(size=size,tab=tab):
                    image=self.renderer.render(self.obs,size,tab)
                    self.assertEqual(image.size,size)
                    self.assertIn('星屑杂货铺',self.renderer.words)
                    self.assertIn('第 8 天',self.renderer.words)
                    self.assertNotIn('第 8 / 7 天',self.renderer.words)
    def test_new_schema_fields_are_rendered(self):
        for tab,expected in [('visitors','米拉'),('collection','???'),('upgrades','工作台'),('journal','小店又迎来一个崭新的早晨。')]:
            self.renderer.render(self.obs,(1320,940),tab)
            self.assertIn(expected,self.renderer.words)
        self.assertIn('街区熟面孔',self.renderer.words)
        self.assertTrue(any('声望 8/12' in s for s in self.renderer.words))
    def test_render_does_not_mutate_observation(self):
        before=copy.deepcopy(self.obs)
        for tab,_ in TABS:self.renderer.render(self.obs,tab=tab)
        self.assertEqual(self.obs,before)
    def test_all_item_art_kinds_rarities_and_bad_colors(self):
        for kind in ['tool','artifact','plant','bot','signal']:
            for rarity in ['common','rare','legendary']:
                item=dict(self.obs['inventory'][0],kind=kind,rarity=rarity,color='not-a-color')
                self.obs['inventory']=[item];self.obs['last_event']['item']=item
                self.renderer.render(self.obs)
                self.assertIn(item['name'],self.renderer.words)
    def test_paging_is_bounded_and_reachable(self):
        self.obs['inventory']=[dict(self.obs['inventory'][0],name=f'货物{i}') for i in range(11)]
        self.renderer.render(self.obs,(1320,940),page=2)
        self.assertIn('货物8',self.renderer.words)
        self.assertNotIn('货物0',self.renderer.words)
        self.assertEqual(self.renderer.page_count,3)
    def test_hit_testing_handles_scaled_letterboxing(self):
        self.renderer.render(self.obs,(390,844),'shelf')
        for bounds,action in self.renderer.hits:
            if action==('tab','collection'):
                x=(bounds[0]+bounds[2])/2*self.renderer.scale+self.renderer.offset[0]
                y=(bounds[1]+bounds[3])/2*self.renderer.scale+self.renderer.offset[1]
                self.assertEqual(self.renderer.action_at(x,y),action)
                break
        else:self.fail('Collection tab must be reachable')
    def test_detail_overlay_consumes_clicks_and_shows_story(self):
        item=self.obs['inventory'][0]
        self.renderer.render(self.obs,detail=item)
        self.assertIn(item['description'],self.renderer.words)
        self.assertEqual(self.renderer.action_at(300,300),('close',None))
    def test_missing_state_and_first_week_pause(self):
        self.renderer.render(None)
        self.assertIn('等候店长开门',self.renderer.words)
        self.obs['phase']='week_summary'
        self.renderer.render(self.obs)
        self.assertIn('可以继续经营',self.renderer.words)
        self.assertNotIn('这趟旅程结束了',self.renderer.words)
    def test_bad_optional_fields_do_not_crash(self):
        self.obs.update(inventory=[None],credits='oops',upgrades=None,log=[None],last_event=None,visitors=[None],collection=None)
        for tab,_ in TABS:self.renderer.render(self.obs,tab=tab)
    def test_public_only_selected_fields(self):
        self.obs['hidden_price']='DO NOT DISPLAY THIS SECRET'
        self.renderer.render(self.obs)
        self.assertFalse(any('SECRET' in word for word in self.renderer.words))
    def test_colors_and_numbers_are_defensive(self):
        self.assertEqual(safe_color('#wrong'),'#80d8c5')
        self.assertEqual(number(float('nan')),0)
        self.assertEqual(number(None),0)


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.directory=Path(self.tmp.name)
        self.path=self.directory/'observation.json'
        self.path.write_text(json.dumps(fixture(),ensure_ascii=False))
    def tearDown(self):self.tmp.cleanup()
    def test_reader_reads_only_one_public_path_and_never_writes(self):
        sentinel=self.directory/'save.json';sentinel.write_text('PRIVATE_SENTINEL')
        before={p.name:p.read_bytes() for p in self.directory.iterdir()}
        read_calls=[];orig=Path.read_text
        def record(path,*args,**kwargs):read_calls.append(path);return orig(path,*args,**kwargs)
        with patch.object(Path,'read_text',record):
            reader=ObservationReader(self.path);self.assertTrue(reader.poll());self.assertFalse(reader.poll())
            Renderer().render(reader.observation)
        self.assertEqual(read_calls,[self.path])
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.directory.iterdir()})
    def test_save_path_and_save_symlink_are_rejected_before_read(self):
        with self.assertRaises(ValueError):ObservationReader(self.directory/'save.json')
        link=self.directory/'alias.json';link.symlink_to(self.directory/'save.json')
        with self.assertRaises(ValueError):ObservationReader(link)
    def test_partial_json_keeps_last_good_snapshot_and_recovers(self):
        reader=ObservationReader(self.path);reader.poll();old=reader.observation
        self.path.write_text('{broken');self.assertFalse(reader.poll());self.assertIs(reader.observation,old)
        self.assertIsNotNone(reader.error)
        obs=fixture();obs['credits']=990;self.path.write_text(json.dumps(obs))
        self.assertTrue(reader.poll());self.assertEqual(reader.observation['credits'],990);self.assertIsNone(reader.error)
    def test_no_fallback_to_save_when_public_file_is_missing(self):
        self.path.unlink();(self.directory/'save.json').write_text(json.dumps(fixture()))
        reader=ObservationReader(self.path);self.assertFalse(reader.poll());self.assertIsNone(reader.observation)
    def test_private_rng_state_rejected(self):
        obj=fixture();obj['rng_state']='PRIVATE'
        self.path.write_text(json.dumps(obj));reader=ObservationReader(self.path)
        self.assertFalse(reader.poll());self.assertIsNone(reader.observation)
    def test_snapshot_cli_is_headless_and_cannot_overwrite_save(self):
        target=self.directory/'screen.png'
        self.assertEqual(main(['--observation',str(self.path),'--snapshot',str(target),'--width','390','--height','844']),0)
        self.assertTrue(target.is_file())
        with self.assertRaises(SystemExit):main(['--snapshot',str(self.directory/'save.json')])





def percentile_fixture(*, tens=70, ones=5, threshold=58, outcome='failure',
                       pending=False, stage='initial', price=165):
    """Synthetic v9 public data, with no engine import or game-state access."""
    obs=fixture();obs['version']=9
    roll={'id':'P001','day':8,'item_id':'I001','item_name':'彗星玻璃八音盒',
          'customer_id':'mira','customer_name':'米拉','stage':stage,'rules_version':9,
          'die':'D100','tens':tens,'ones':ones,'roll':tens+ones or 100,
          'threshold':threshold,'probability':threshold/100,'modifier':0,'modifiers':[],
          'success':outcome in ('success','miracle'),'outcome':outcome,'price':price,
          'base_chance':70 if stage=='final' else None,
          'counter_offer':150 if stage=='final' else None,
          'premium':(price-150)/150 if stage=='final' else None,
          'explanation':'两颗独立十面骰，低于或等于阈值成功。'}
    obs['last_roll']=roll;obs['roll_history']=[copy.deepcopy(roll)]
    obs['negotiation']=None
    if pending:
        preview={'price':price,'basis':'public_counter','base_chance':70,
                 'threshold':threshold,'probability':threshold/100,
                 'premium':(price-150)/150,'modifier':0,'modifiers':[],
                 'critical_probability':.01,'fumble_probability':.01,'energy_cost':1,
                 'accept_income':150,'success_income':price,'failure_income':0,
                 'warning':'最终失败收入0，不能回头接受旧还价。','suggested':False}
        obs['negotiation']={'item_id':'I001','item_name':roll['item_name'],
            'customer_id':'mira','customer_name':'米拉','rules_version':9,'origin_rules_version':9,
            'original_price':9999,'counter_offer':150,'remaining_offers':1,'final_offer_energy':1,
            'accept_income':150,'final_failure_income':0,
            'final_offer_bounds':{'min':151,'max':9998,'available':True},'preview':preview}
    return obs



class NativeDiceRendererTests(unittest.TestCase):
    def setUp(self):self.renderer=Renderer()
    def test_dice_can_use_last_event_public_roll(self):
        obs=percentile_fixture(tens=10,ones=7,outcome='success')
        obs['last_event']['roll']=obs.pop('last_roll')
        self.renderer.render(obs)
        self.assertIn('D100 17',self.renderer.words)
        self.assertIn('普通成功',self.renderer.words)

    def test_history_pages_newest_first_and_preserves_original_failure(self):
        obs=percentile_fixture()
        obs['roll_history']=[dict(obs['last_roll'],id=f'R{i}',customer_name=f'旅客{i}') for i in range(12)]
        self.renderer.render(obs,(1320,940),'journal',journal_mode='rolls')
        self.assertIn('骰子记录',self.renderer.words)
        self.assertTrue(any('旅客11' in w for w in self.renderer.words))
        self.assertIn('失败',self.renderer.words)
        self.assertGreater(self.renderer.page_count,1)
        self.renderer.render(obs,(1320,940),'journal',page=2,journal_mode='rolls')
        self.assertFalse(any('旅客11' in w for w in self.renderer.words))

    def test_history_empty_state_does_not_invent_dice(self):
        self.renderer.render(fixture(),(1320,940),'journal',journal_mode='rolls')
        self.assertIn('还没有公开骰点',self.renderer.words)
        self.assertFalse(any(a[0]=='inspect' and a[1].get('_view')=='roll' for b,a in self.renderer.hits))

    def test_demo_flag_is_explicit_and_off_by_default(self):
        self.renderer.render(percentile_fixture())
        self.assertNotIn('演示数据 · 不是真实游玩',self.renderer.words)
        self.renderer.render(percentile_fixture(),demo=True)
        self.assertIn('演示数据 · 不是真实游玩',self.renderer.words)
        self.assertIn('v9 · D100 低骰规则 · 演示',self.renderer.words)

    def test_renderer_never_mutates_or_rerolls(self):
        obs=percentile_fixture();before=copy.deepcopy(obs)
        self.renderer.render(obs,(390,844),frame=0)
        words=list(self.renderer.words)
        self.renderer.render(obs,(390,844),frame=1000)
        self.assertEqual(words,self.renderer.words)
        for tab,_ in TABS:self.renderer.render(obs,tab=tab,journal_mode='rolls')
        self.assertEqual(obs,before)

    def test_unknown_private_fields_are_never_rendered(self):
        obs=percentile_fixture(pending=True);obs['last_roll']['base_value']='SECRET_BASE';obs['last_roll']['exact_budget']='SECRET_BUDGET'
        obs['negotiation']['reserve_price']='SECRET_RESERVE'
        self.renderer.render(obs,detail=dict(obs['last_roll'],_view='roll',negotiation=obs['negotiation']))
        self.assertFalse(any('SECRET' in word for word in self.renderer.words))

    def test_dice_actions_are_only_read_only_views(self):
        obs=percentile_fixture();self.renderer.render(obs)
        allowed={'tab','page','inspect','show_rolls','journal_mode','close'}
        self.assertTrue(all(a[0] in allowed for b,a in self.renderer.hits))
        history=[(b,a) for b,a in self.renderer.hits if a[0]=='show_rolls']
        self.assertEqual(len(history),1)
        bounds,action=history[0]
        x=(bounds[0]+bounds[2])/2*self.renderer.scale+self.renderer.offset[0]
        y=(bounds[1]+bounds[3])/2*self.renderer.scale+self.renderer.offset[1]
        self.assertEqual(self.renderer.action_at(x,y),action)

    def test_later_actions_keep_latest_event_and_previous_dice_distinct(self):
        obs=percentile_fixture(tens=0,ones=1,outcome='miracle',price=9999)
        for kind in ['repair','day','price','buy','collect']:
            obs['last_event']={'type':kind,'title':'更新后的经营动态','text':'这是后来完成的动作。'}
            self.renderer.render(obs)
            self.assertIn('更新后的经营动态',self.renderer.words)
            self.assertTrue(any('上次 D100 01' in word for word in self.renderer.words))
            self.assertNotIn('成交 9,999 星币',self.renderer.words)

    def test_escape_dismisses_detail_before_leaving_fullscreen(self):
        from unittest.mock import Mock
        viewer=Spectator.__new__(Spectator);viewer.root=Mock();viewer.detail={'name':'骰子'};viewer.last_signature='old'
        viewer.escape()
        self.assertIsNone(viewer.detail);self.assertIsNone(viewer.last_signature)
        viewer.root.attributes.assert_not_called()
        viewer.escape();viewer.root.attributes.assert_called_once_with('-fullscreen',False)

    def test_spectator_history_clicks_and_repeated_close_change_only_view_state(self):
        from types import SimpleNamespace
        viewer=Spectator.__new__(Spectator)
        viewer.renderer=self.renderer;viewer.tab='shelf';viewer.page=0;viewer.detail=None;viewer.last_signature=None;viewer.journal_mode='events'
        self.renderer.render(percentile_fixture())
        for name in ['show_rolls']:
            bounds,action=next((b,a) for b,a in self.renderer.hits if a[0]==name)
            x=(bounds[0]+bounds[2])/2*self.renderer.scale+self.renderer.offset[0]
            y=(bounds[1]+bounds[3])/2*self.renderer.scale+self.renderer.offset[1]
            viewer.click(SimpleNamespace(x=x,y=y))
        self.assertEqual((viewer.tab,viewer.journal_mode),('journal','rolls'))
        self.renderer.render(percentile_fixture(),tab=viewer.tab,journal_mode=viewer.journal_mode)
        bounds,action=next((b,a) for b,a in self.renderer.hits if a[0]=='journal_mode')
        viewer.click(SimpleNamespace(x=(bounds[0]+bounds[2])/2*self.renderer.scale+self.renderer.offset[0],y=(bounds[1]+bounds[3])/2*self.renderer.scale+self.renderer.offset[1]))
        self.assertEqual(viewer.journal_mode,'events')
        viewer.set_tab('shelf');self.assertIsNone(viewer.detail)



class PercentileRendererTests(unittest.TestCase):
    def setUp(self):self.renderer=Renderer()

    def words(self,obs,size=(1320,940),**kwargs):
        self.last_image=self.renderer.render(obs,size,**kwargs)
        return self.renderer.words

    def test_real_pair_and_low_roll_outcomes(self):
        for tens,ones,outcome,label in [(0,1,'miracle','01 · 大成功'),
                                       (50,8,'success','普通成功'),
                                       (50,9,'failure','失败'),
                                       (0,0,'fumble','100 · 大失败')]:
            obs=percentile_fixture(tens=tens,ones=ones,outcome=outcome)
            words=self.words(obs)
            self.assertIn(f'{tens:02d}',words)
            self.assertIn(str(ones),words)
            self.assertIn(f'D100 {tens+ones or 100:02d}',words)
            self.assertIn('十位',words);self.assertIn('个位',words)
            self.assertIn(label,words)
            self.assertIn(f'D100 {tens:02d} + {ones} = {tens+ones or 100:02d} · ≤58 成功（58%）',words)
            self.assertFalse(any('天然20' in word or '天然1' in word or 'DC' in word for word in words))

    def test_critical_legal_high_price_and_hundred_are_distinct(self):
        critical=percentile_fixture(tens=0,ones=1,outcome='miracle',price=9999)
        self.assertIn('成交 9,999 星币',self.words(critical))
        fumble=percentile_fixture(tens=0,ones=0,outcome='fumble',threshold=99)
        detail=dict(fumble['last_roll'],_view='roll')
        words=self.words(fumble,detail=detail)
        self.assertIn('100 · 大失败',words)
        self.assertIn('D100 00 + 0 = 100 · ≤99 成功（99%）',words)
        self.assertIn('01 必成：1% · 00 + 0 = 100 必败：1%',words)
        self.assertIn('CoC 启发简化房规 · 非完整官方规则 · 只读',words)

    def test_modifier_is_percentage_points_and_never_added_to_result(self):
        obs=percentile_fixture(tens=50,ones=8,outcome='success',stage='final')
        obs['last_roll'].update(modifier=15,modifiers=[{'label':'冻结修正','value':15}])
        words=self.words(obs,detail=dict(obs['last_roll'],_view='roll'))
        self.assertIn('冻结修正 +15百分点',words)
        self.assertIn('D100 50 + 8 = 58 · ≤58 成功（58%）',words)
        self.assertNotIn('D100 58 + 15',str(words))

    def test_exact_previews_at_near_counter_fifty_percent_and_huge_price(self):
        for price,threshold in [(165,58),(225,35),(9998,1)]:
            words=self.words(percentile_fixture(price=price,threshold=threshold,pending=True))
            for expected in [f'拟报价 {price:,} 星币 · 尚未掷骰',
                             f'低骰成功：01–{threshold:02d} · 成功率 {threshold}%',
                             f'基础 70% · 溢价 {(price-150)/150*100:g}% · 双 D10',
                             '01 必成（1%）· 100 必败（1%）',
                             '接受：收入 150 星币 · 免费',
                             f'再报价：1 体力 · 成功收入 {price:,}',
                             '失败收入 0 · 失去 150 星币还价',
                             '公开还价精确预览 · 越低越好 · 不掷骰',
                             '70','5','D100 75']:
                self.assertIn(expected,words)
            self.assertFalse(any('DC' in word or '拒价' in word or '5%必成' in word for word in words))

    def test_preview_detail_shows_frozen_percentage_points(self):
        obs=percentile_fixture(pending=True)
        obs['negotiation']['preview'].update(modifier=15,modifiers=[{'label':'冻结修正','value':15}])
        self.words(obs)
        detail=next(a[1] for _,a in self.renderer.hits if a[0]=='inspect' and a[1].get('_view')=='negotiation')
        words=self.words(obs,(390,844),detail=detail)
        self.assertIn('冻结加值 +15百分点 · 冻结修正 +15百分点',words)
        self.assertIn('CoC 启发的简化房规，并非完整官方规则',words)
        self.assertIn('最终失败收入0，不能回头接受旧还价。',words)
        self.assertEqual(self.renderer.hits,[((0,0,self.renderer.W,self.renderer.H),('close',None))])

    def test_incomplete_or_inconsistent_digits_never_invent_a_roll(self):
        valid=percentile_fixture()['last_roll']
        invalids=[{'tens':1},{'tens':100},{'tens':True},{'tens':None},
                  {'ones':10},{'ones':False},{'ones':2.5},{'ones':float('inf')},
                  {'roll':1},{'roll':0},{'roll':100},{'roll':None},{'roll':True},
                  {'tens':10**400},{'ones':10**400},{'roll':10**400}]
        for changes in invalids:
            with self.subTest(changes=changes):
                source=dict(valid,**changes)
                projected=public_roll(source)
                self.assertIsNone(projected['roll'])
                self.assertEqual(roll_math(projected),'D100 · 等待有效且一致的公开双骰')
                self.assertEqual(roll_status(projected)[0],'等待有效公开双骰')
        no_combined=dict(valid);del no_combined['roll']
        self.assertIsNone(public_roll(no_combined)['roll'])
        self.assertEqual(public_roll(dict(valid,tens='70',ones='5',roll='75'))['roll'],75)

    def test_missing_or_invalid_threshold_is_not_invented(self):
        valid=percentile_fixture()['last_roll']
        for threshold in [None,True,False,0,100,57.5,'bad',float('nan')]:
            source=dict(valid,threshold=threshold)
            self.assertIsNone(public_roll(source)['threshold'])
            self.assertIn('等待完整公开阈值',roll_math(source))

    def test_preview_requires_consistent_public_probability_and_valid_fields(self):
        for changes in [{'threshold':100},{'threshold':0},{'threshold':True},
                        {'probability':.59},{'probability':None},{'base_chance':None},
                        {'price':False},{'modifier':False},{'basis':'private'}]:
            obs=percentile_fixture(pending=True)
            obs['negotiation']['preview'].update(changes)
            self.assertIsNone(percentile_preview(obs['negotiation']['preview']))
            self.assertIn('等待公开报价预览',self.words(obs))
            self.assertFalse(any('低骰成功：' in word for word in self.renderer.words))

    def test_native_projection_excludes_obsolete_and_private_fields(self):
        obs=percentile_fixture(pending=True,stage='final')
        obs['last_roll'].update(face=20,total=100,target=15,base_target=12,rejection_penalty=3,
                                exact_budget='SECRET_BUDGET',rng='SECRET_RNG')
        obs['negotiation'].update(rejection_penalty=3,reserve='SECRET_RESERVE')
        obs['negotiation']['preview'].update(rejection_penalty=3,target_range=[1,20],budget='SECRET_BUDGET')
        projected=public_roll(obs['last_roll']);pending=public_negotiation(obs['negotiation'])
        for key in ('face','total','target','base_target','rejection_penalty','exact_budget','rng'):
            self.assertNotIn(key,projected)
        self.assertNotIn('rejection_penalty',pending)
        self.assertNotIn('rejection_penalty',pending['preview'])
        self.assertNotIn('target_range',pending['preview'])
        self.assertNotIn('SECRET',json.dumps([projected,pending]))

    def test_exact_final_roll_shows_public_counter_base_and_odds(self):
        obs=percentile_fixture(tens=50,ones=8,stage='final',outcome='success')
        for detail in [None,dict(obs['last_roll'],_view='roll')]:
            words=self.words(obs,detail=detail)
            self.assertIn('基础几率 70% · 公开还价 150 → 阈值 58',words)
            self.assertIn('低骰成功：01–58 · 成功率 58%',words)
            self.assertFalse(any('DC' in word or '拒价' in word for word in words))

    def test_accept_after_percentile_failure_preserves_the_sale_and_history(self):
        obs=percentile_fixture()
        obs['last_event']={'type':'sale','title':'就这个价 · 成交','text':'接受150星币还价，没有再掷骰。'}
        words=self.words(obs)
        self.assertIn('就这个价 · 成交',words)
        self.assertIn('上次 D100 75 · 初次报价未达标 · 低骰 · 查看记录 ›',words)
        self.assertNotIn('本次交易未成',words)

    def test_percentile_refresh_keeps_latest_preview_and_readonly_actions(self):
        from types import SimpleNamespace
        obs=percentile_fixture(pending=True)
        self.words(obs)
        detail=next(a[1] for _,a in self.renderer.hits if a[0]=='inspect' and a[1].get('_view')=='negotiation')
        viewer=Spectator.__new__(Spectator);viewer.detail=detail
        newer=percentile_fixture(price=225,threshold=35,pending=True)
        viewer.reader=SimpleNamespace(observation=newer)
        viewer.refresh_detail()
        words=self.words(newer,detail=viewer.detail)
        self.assertIn('低骰成功：01–35 · 成功率 35%',words)
        viewer.reader.observation=dict(newer,negotiation=None)
        viewer.refresh_detail();self.assertIsNone(viewer.detail)
        self.assertTrue(all(a[0] in {'tab','page','inspect','show_rolls','journal_mode','close'} for _,a in self.renderer.hits))

    def test_new_cards_render_all_sizes_without_mutating_or_rerolling(self):
        obs=percentile_fixture(pending=True);before=copy.deepcopy(obs)
        for size in [(1320,940),(760,1240),(390,844),(320,568)]:
            for tab,_ in TABS:
                self.words(obs,size,tab=tab,journal_mode='rolls',demo=True)
                self.assertEqual(self.last_image.size,size)
                self.assertIn('演示数据 · 不是真实游玩',self.renderer.words)
                self.assertIn('D100 75',self.renderer.words)
                self.assertEqual(sum(a[0]=='tab' for _,a in self.renderer.hits),5)
        self.words(obs,frame=0);words=list(self.renderer.words)
        self.words(obs,frame=10000);self.assertEqual(words,self.renderer.words)
        self.assertEqual(obs,before)



class NativeVersionBoundaryTests(unittest.TestCase):
    def test_unsupported_observations_are_redacted_in_every_view(self):
        renderer = Renderer()
        for version in (None, 2, 3, 4, 5, 6, 7, 8, 10, True, 9.0, '9'):
            obs = percentile_fixture(pending=True)
            obs.update(version=version, credits=123456789)
            before = copy.deepcopy(obs)
            for tab, _ in TABS:
                renderer.render(obs, (390, 844), tab, detail=dict(obs['last_roll'], _view='roll'))
                self.assertIn('不支持此公开状态版本 · 仅支持 v9', renderer.words)
                self.assertNotIn('123,456,789', renderer.words)
                self.assertNotIn('D100 75', renderer.words)
                self.assertEqual(renderer.hits, [])
            self.assertEqual(obs, before)

    def test_native_version_cannot_hide_migration_or_collection_grace(self):
        renderer = Renderer()
        for key in ('migration', 'engine_upgrade', 'management_upgrade', 'collection_upgrade', 'budget_upgrade'):
            obs = fixture()
            obs[key] = {'from': 8}
            renderer.render(obs)
            self.assertIn('不支持此公开状态版本 · 仅支持 v9', renderer.words)
        obs = fixture()
        obs['collection_progress'] = {'legacy_grace': True}
        renderer.render(obs)
        self.assertIn('不支持此公开状态版本 · 仅支持 v9', renderer.words)

    def test_reader_rejects_unsupported_schema_and_drops_stale_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic.observation.json'
            path.write_text(json.dumps(fixture()))
            reader = ObservationReader(path)
            self.assertTrue(reader.poll())
            old = fixture(); old['version'] = 8
            path.write_text(json.dumps(old)); before = path.read_bytes()
            self.assertFalse(reader.poll())
            self.assertIsNone(reader.observation)
            self.assertIn('仅支持 v9', reader.error)
            renderer = Renderer()
            renderer.render(reader.observation, error=reader.error, detail={'name': 'STALE_ITEM', 'description': 'STALE_STORY'})
            self.assertNotIn('STALE', str(renderer.words))
            self.assertEqual(renderer.hits, [])
            self.assertEqual(before, path.read_bytes())
            path.write_text(json.dumps(fixture()))
            self.assertTrue(reader.poll())
            self.assertIsNone(reader.error)

    def test_mixed_records_show_unsupported_notice_without_conversion(self):
        renderer = Renderer()
        obs = percentile_fixture(tens=0, ones=1, outcome='miracle')
        old = dict(obs['last_roll'], rules_version=4, face=20, item_name='UNSUPPORTED_ITEM',
                   customer_name='UNSUPPORTED_CUSTOMER', explanation='UNSUPPORTED_EXPLANATION')
        obs['roll_history'] = [old, obs['last_roll']]
        before = copy.deepcopy(obs)
        for size in ((1320, 940), (390, 844)):
            renderer.render(obs, size, 'journal', journal_mode='rolls')
            words = []
            for page in range(renderer.page_count):
                renderer.render(obs, size, 'journal', page=page, journal_mode='rolls')
                words.extend(renderer.words)
            self.assertTrue(any('不支持此规则版本' in word for word in words))
            self.assertTrue(any('v9 低骰' in word for word in words))
            self.assertNotIn('UNSUPPORTED', str(words))
            renderer.render(obs, size, detail=dict(old, _view='roll'))
            self.assertNotIn('UNSUPPORTED', str(renderer.words))
            self.assertEqual(renderer.hits, [((0, 0, renderer.W, renderer.H), ('close', None))])
        self.assertEqual(obs, before)

    def test_old_quotes_cannot_become_native_previews(self):
        renderer = Renderer()
        for rules, origin in ((3, 3), (4, 4), (5, 5), (6, 6), (9, 3), (9, 4), (9, 5), (9, 6), (9, None)):
            obs = percentile_fixture(pending=True)
            obs['negotiation'].update(rules_version=rules, origin_rules_version=origin,
                                      item_name='UNSUPPORTED_QUOTE')
            before = copy.deepcopy(obs)
            self.assertEqual(public_negotiation(obs['negotiation']), {'_unsupported_rules': True})
            for detail in (None, dict(_view='negotiation', negotiation=obs['negotiation'])):
                renderer.render(obs, (390, 844), detail=detail)
                self.assertIn('不支持此议价版本 · 仅支持原生 v9', renderer.words)
                self.assertNotIn('UNSUPPORTED_QUOTE', renderer.words)
                self.assertFalse(any('拟报价' in word or '低骰成功：' in word for word in renderer.words))
            self.assertEqual(obs, before)

    def test_refresh_closes_detail_after_unsupported_observation_or_quote(self):
        from types import SimpleNamespace
        viewer = Spectator.__new__(Spectator)
        obs = percentile_fixture(pending=True)
        for detail in (dict(_view='sale', id='I001'), dict(_view='negotiation', negotiation=obs['negotiation']),
                       dict(obs['last_roll'], _view='roll')):
            viewer.detail = detail
            viewer.reader = SimpleNamespace(observation=dict(obs, version=8))
            viewer.refresh_detail()
            self.assertIsNone(viewer.detail)
        viewer.reader.observation = obs
        viewer.detail = dict(_view='negotiation', negotiation=copy.deepcopy(obs['negotiation']))
        obs['negotiation']['origin_rules_version'] = 6
        viewer.refresh_detail()
        self.assertIsNone(viewer.detail)


class NativePreviewLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.renderer = Renderer()

    def test_pending_status_only_matches_initial_failure_for_the_same_item(self):
        obs = percentile_fixture(pending=True)
        self.assertEqual(roll_status(obs['last_roll'], obs['negotiation'])[0], '还价中')
        for change in (dict(stage='final'), dict(item_id='OTHER')):
            self.assertEqual(roll_status(dict(obs['last_roll'], **change), obs['negotiation'])[0], '失败')

    def test_roll_detail_keeps_native_pending_options_and_closes_cleanly(self):
        obs = percentile_fixture(pending=True)
        self.renderer.render(obs, (390, 844), detail=dict(obs['last_roll'], _view='roll', negotiation=obs['negotiation']))
        for word in ('还价 150 星币 · 待店主决定', '接受 / 谢绝免费；最后报价消耗 1 体力',
                     'D100 70 + 5 = 75 · ≤58 成功（58%）'):
            self.assertIn(word, self.renderer.words)
        self.assertEqual(self.renderer.hits, [((0, 0, self.renderer.W, self.renderer.H), ('close', None))])

    def test_explicit_minimum_price_is_not_relabelled_as_suggested(self):
        obs = percentile_fixture(price=151, pending=True)
        self.renderer.render(obs)
        self.assertIn('拟报价 151 星币 · 尚未掷骰', self.renderer.words)
        obs['negotiation']['preview']['suggested'] = True
        self.renderer.render(obs)
        self.assertIn('拟报价 151 星币 · 最低价示例', self.renderer.words)

    def test_missing_preview_does_not_reconstruct_odds(self):
        for preview in (None, {}, [], 'bad'):
            obs = percentile_fixture(pending=True)
            obs['negotiation']['preview'] = preview
            self.renderer.render(obs)
            self.assertIn('等待公开报价预览', self.renderer.words)
            self.assertFalse(any('低骰成功：' in word for word in self.renderer.words))
            self.assertIsNone(percentile_preview(preview))

    def test_accept_after_preview_clears_proposal_and_keeps_previous_roll(self):
        obs = percentile_fixture(pending=True)
        obs['negotiation'] = None
        obs['last_event'] = dict(type='sale', title='就这个价 · 成交', text='接受150星币还价，没有再掷骰。')
        self.renderer.render(obs)
        self.assertIn('就这个价 · 成交', self.renderer.words)
        self.assertFalse(any('拟报价' in word or '再报价：' in word for word in self.renderer.words))
        self.assertIn('上次 D100 75 · 初次报价未达标 · 低骰 · 查看记录 ›', self.renderer.words)

    def test_unrelated_new_negotiation_closes_old_preview(self):
        from types import SimpleNamespace
        obs = percentile_fixture(pending=True)
        viewer = Spectator.__new__(Spectator)
        viewer.detail = dict(_view='negotiation', negotiation=copy.deepcopy(obs['negotiation']))
        obs['negotiation']['item_id'] = 'I002'
        viewer.reader = SimpleNamespace(observation=obs)
        viewer.refresh_detail()
        self.assertIsNone(viewer.detail)

    def test_open_roll_drops_stale_pending_label_after_acceptance(self):
        from types import SimpleNamespace
        obs = percentile_fixture(pending=True)
        viewer = Spectator.__new__(Spectator)
        viewer.detail = dict(obs['last_roll'], _view='roll', negotiation=obs['negotiation'])
        viewer.reader = SimpleNamespace(observation=dict(obs, negotiation=None))
        viewer.refresh_detail()
        self.assertEqual(viewer.detail['roll'], 75)
        self.assertEqual(viewer.detail['negotiation'], {})

    def test_engine_native_public_scenes_render_without_mutating_state(self):
        import engine
        from native_test_helpers import fixture as native_fixture
        scenes = []
        for result in (1, 2, 99, 100):
            state = native_fixture(result)
            engine.apply_command(state, 'sell', ['I001'])
            scenes.append(copy.deepcopy(state))
            if result == 99:
                for command in ('accept', 'decline'):
                    resolved = copy.deepcopy(state)
                    engine.apply_command(resolved, command, ['I001'])
                    scenes.append(resolved)
        for result in (1, 2, 99, 100):
            state = native_fixture(99, result)
            engine.apply_command(state, 'sell', ['I001'])
            price = state['negotiation']['counter_offer'] + 1
            engine.apply_command(state, 'offer', ['I001', str(price)])
            scenes.append(state)
        self.assertEqual(len(scenes), 10)
        for state in scenes:
            engine._validate_state(state)
            before = copy.deepcopy(state)
            public = engine.observation(state)
            for size in ((1320, 940), (390, 844), (320, 568)):
                self.renderer.render(public, size, demo=True)
                self.assertIn('演示数据 · 不是真实游玩', self.renderer.words)
                self.assertNotIn('不支持的规则版本', self.renderer.words)
            self.assertEqual(state, before)


if __name__ == '__main__':
    unittest.main()
