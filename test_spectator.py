"""Headless UI checks; no game-engine import, display, or user save is needed."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from spectator import ObservationReader, Renderer, Spectator, TABS, main, safe_color, number


def fixture():
    item={'id':'I001','name':'彗星玻璃八音盒','kind':'artifact','rarity':'rare','color':'#b7a2ff',
          'condition':76,'price':150,'value_estimate':[130,175],'description':'每次彗星经过，它会多记住一个音符。'}
    return {'version':2,'revision':1,'day':8,'credits':780,'energy':13,'max_energy':13,'reputation':8,
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
        for tab,expected in [('visitors','米拉'),('collection','袖珍巡航鲸'),('upgrades','工作台'),('journal','小店又迎来一个崭新的早晨。')]:
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





def dice_fixture(outcome='failure', face=8, stage='initial', pending=True):
    obs=fixture();obs['version']=3
    obs['inventory'][0]['price']=240
    roll={'id':'R001','day':8,'item_id':'I001','item_name':'彗星玻璃八音盒',
          'customer_id':'mira','customer_name':'米拉','stage':stage,'face':face,
          'modifier':3,'modifiers':[{'label':'店铺声望','value':1},{'label':'投其所好','value':2}],
          'total':face+3,'target':15,'success':outcome in ('success','miracle'),'outcome':outcome,
          'price':9999 if outcome=='miracle' else 240,
          'explanation':'本条记录来自公开判定，点击只会回看，不会再掷骰。'}
    obs['last_roll']=roll;obs['roll_history']=[roll]
    obs['negotiation']={'item_id':'I001','item_name':'彗星玻璃八音盒','customer_id':'mira','customer_name':'米拉',
        'original_price':240,'counter_offer':175,'remaining_offers':1,'final_offer_energy':1,
        'commands':{'accept':'accept I001','decline':'decline I001','offer':'offer I001 金额'}} if pending else None
    if pending:
        obs['inventory'][0]['negotiating']=True
        obs['visitors'][0]['status']='negotiating'
    return obs


class DiceRendererTests(unittest.TestCase):
    def setUp(self):self.renderer=Renderer()
    def test_all_adjudication_outcomes_use_real_face(self):
        outcomes=[('miracle',20,'天然20 · 大成功'),('success',15,'普通成功'),
                  ('failure',4,'失败'),('fumble',1,'天然1 · 大失败')]
        for outcome,face,label in outcomes:
            with self.subTest(outcome=outcome):
                self.renderer.render(dice_fixture(outcome,face,pending=False))
                self.assertIn(str(face),self.renderer.words)
                self.assertIn(label,self.renderer.words)
        self.renderer.render(dice_fixture('miracle',20,pending=False))
        self.assertIn('成交 9,999 星币',self.renderer.words)
    def test_pending_bargain_shows_public_prices_costs_and_waiting(self):
        self.renderer.render(dice_fixture())
        for word in ['还价中','标价 240 → 还价 175','待店主决定 · 只剩一次议价','接受/谢绝免费 · 再报价1体力']:
            self.assertIn(word,self.renderer.words)
        self.assertTrue(any('还价中' in w for w in self.renderer.words))
    def test_pending_does_not_relabel_unrelated_or_final_roll(self):
        for different in [dict(stage='final'),dict(item_id='OTHER')]:
            obs=dice_fixture();obs['last_roll']=dict(obs['last_roll'],**different)
            self.renderer.render(obs)
            self.assertIn('失败',self.renderer.words)
    def test_dice_can_use_last_event_public_roll(self):
        obs=dice_fixture('success',17,pending=False)
        obs['last_event']['roll']=obs.pop('last_roll')
        self.renderer.render(obs)
        self.assertIn('17',self.renderer.words)
        self.assertIn('普通成功',self.renderer.words)
    def test_dice_and_history_render_at_all_sizes(self):
        for size in [(1320,940),(760,1240),(390,844),(320,568)]:
            for mode in ['events','rolls']:
                with self.subTest(size=size,mode=mode):
                    image=self.renderer.render(dice_fixture(),size,'journal',journal_mode=mode,demo=True)
                    self.assertEqual(image.size,size)
                    self.assertIn('演示数据 · 不是真实游玩',self.renderer.words)
                    self.assertIn('演示预览 · 未推进游戏',self.renderer.words)
                    self.assertEqual(len([a for b,a in self.renderer.hits if a[0]=='tab']),5)
    def test_history_pages_newest_first_and_preserves_original_failure(self):
        obs=dice_fixture()
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
    def test_roll_detail_shows_public_calculation_rules_and_pending_options(self):
        obs=dice_fixture()
        detail=dict(obs['last_roll'],_view='roll',negotiation=obs['negotiation'])
        self.renderer.render(obs,(390,844),detail=detail)
        for word in ['8','D20 8 + 3 = 11  /  目标 15','还价 175 星币 · 待店主决定',
                     '接受 / 谢绝免费；最后报价消耗 1 体力','单次天然20：5%奇迹成交 · 天然1：直接告辞']:
            self.assertIn(word,self.renderer.words)
        self.assertEqual(len(self.renderer.hits),1)
        self.assertEqual(self.renderer.action_at(10,10),('close',None))
    def test_demo_flag_is_explicit_and_off_by_default(self):
        self.renderer.render(dice_fixture())
        self.assertNotIn('演示数据 · 不是真实游玩',self.renderer.words)
        self.renderer.render(dice_fixture(),demo=True)
        self.assertIn('演示数据 · 不是真实游玩',self.renderer.words)
        self.assertIn('D20 · 演示判定',self.renderer.words)
    def test_renderer_never_mutates_or_rerolls(self):
        obs=dice_fixture();before=copy.deepcopy(obs)
        self.renderer.render(obs,(390,844),frame=0)
        words=list(self.renderer.words)
        self.renderer.render(obs,(390,844),frame=1000)
        self.assertEqual(words,self.renderer.words)
        for tab,_ in TABS:self.renderer.render(obs,tab=tab,journal_mode='rolls')
        self.assertEqual(obs,before)
    def test_unknown_private_fields_are_never_rendered(self):
        obs=dice_fixture();obs['last_roll']['base_value']='SECRET_BASE';obs['last_roll']['exact_budget']='SECRET_BUDGET'
        obs['negotiation']['reserve_price']='SECRET_RESERVE'
        self.renderer.render(obs,detail=dict(obs['last_roll'],_view='roll',negotiation=obs['negotiation']))
        self.assertFalse(any('SECRET' in word for word in self.renderer.words))
    def test_invalid_face_is_unknown_never_clamped_to_natural_twenty(self):
        for face in [None,True,False,0,21,7.8,'wrong',float('inf')]:
            obs=dice_fixture();obs['last_roll']=dict(obs['last_roll'],face=face)
            self.renderer.render(obs)
            self.assertIn('?',self.renderer.words)
        obs=dice_fixture();obs.update(roll_history=[None,{},'wrong'],negotiation=None,last_roll={'face':'wrong'})
        self.renderer.render(obs,(320,568),'journal',journal_mode='rolls')
    def test_dice_actions_are_only_read_only_views(self):
        obs=dice_fixture();self.renderer.render(obs)
        allowed={'tab','page','inspect','show_rolls','journal_mode','close'}
        self.assertTrue(all(a[0] in allowed for b,a in self.renderer.hits))
        history=[(b,a) for b,a in self.renderer.hits if a[0]=='show_rolls']
        self.assertEqual(len(history),1)
        bounds,action=history[0]
        x=(bounds[0]+bounds[2])/2*self.renderer.scale+self.renderer.offset[0]
        y=(bounds[1]+bounds[3])/2*self.renderer.scale+self.renderer.offset[1]
        self.assertEqual(self.renderer.action_at(x,y),action)
    def test_accepting_counteroffer_shows_sale_not_stale_failed_roll(self):
        obs=dice_fixture();obs['negotiation']=None;obs['inventory']=[]
        obs['last_event']={'type':'sale','title':'就这个价 · 成交','text':'接受米拉的175星币还价，卖出旧物。没有再掷骰或消耗精力。'}
        self.renderer.render(obs)
        self.assertIn('就这个价 · 成交',self.renderer.words)
        self.assertIn(obs['last_event']['text'],self.renderer.words)
        self.assertIn('上次 D20 8 · 初次报价未达标 · 查看记录 ›',self.renderer.words)
        self.assertNotIn('本次交易未成',self.renderer.words)
    def test_later_actions_keep_latest_event_and_previous_dice_distinct(self):
        obs=dice_fixture('miracle',20,pending=False)
        for kind in ['repair','day','price','buy','collect']:
            obs['last_event']={'type':kind,'title':'更新后的经营动态','text':'这是后来完成的动作。'}
            self.renderer.render(obs)
            self.assertIn('更新后的经营动态',self.renderer.words)
            self.assertTrue(any('上次 D20 20' in word for word in self.renderer.words))
            self.assertNotIn('成交 9,999 星币',self.renderer.words)
    def test_engine_generated_public_samples_are_consistent_and_render(self):
        directory=Path(__file__).with_name('dice-fixtures')
        expected=['natural20','ordinary-success','negotiating','accepted','declined','final-miracle','final-success','final-failure','fumble']
        for name in expected:
            path=directory/f'{name}.json';before=path.read_bytes()
            reader=ObservationReader(path)
            self.assertTrue(reader.poll(),name)
            obs=reader.observation
            for size in [(1320,940),(390,844),(320,568)]:
                self.renderer.render(obs,size,demo=True)
                self.assertIn('演示数据 · 不是真实游玩',self.renderer.words)
            self.assertEqual(path.read_bytes(),before)
            if name=='accepted':
                self.assertIn('就这个价 · 成交',self.renderer.words)
                self.assertNotIn('本次交易未成',self.renderer.words)
            if name in ('natural20','final-miracle'):
                self.assertIn('天然20 · 大成功',self.renderer.words)
                self.assertIn('成交 9,999 星币',self.renderer.words)
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
        self.renderer.render(dice_fixture())
        for name in ['show_rolls']:
            bounds,action=next((b,a) for b,a in self.renderer.hits if a[0]==name)
            x=(bounds[0]+bounds[2])/2*self.renderer.scale+self.renderer.offset[0]
            y=(bounds[1]+bounds[3])/2*self.renderer.scale+self.renderer.offset[1]
            viewer.click(SimpleNamespace(x=x,y=y))
        self.assertEqual((viewer.tab,viewer.journal_mode),('journal','rolls'))
        self.renderer.render(dice_fixture(),tab=viewer.tab,journal_mode=viewer.journal_mode)
        bounds,action=next((b,a) for b,a in self.renderer.hits if a[0]=='journal_mode')
        viewer.click(SimpleNamespace(x=(bounds[0]+bounds[2])/2*self.renderer.scale+self.renderer.offset[0],y=(bounds[1]+bounds[3])/2*self.renderer.scale+self.renderer.offset[1]))
        self.assertEqual(viewer.journal_mode,'events')
        viewer.set_tab('shelf');self.assertIsNone(viewer.detail)


if __name__=='__main__':unittest.main()
