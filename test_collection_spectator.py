"""Read-only quality-collection UI checks, using synthetic in-memory scenes only."""
import copy
import json
import math
from types import SimpleNamespace
import unittest
from unittest import mock

from PIL import Image, ImageDraw

from spectator import (font, Renderer, Spectator, public_catalog_entry,
                       public_collection_detail, public_collection_progress,
                       public_collection_quality, public_collection_action)


SIZES = [(1320, 940), (760, 1240), (390, 844), (320, 568), (1364, 1024)]


def fixture():
    progress = dict(personal_count=3, qualified_count=1, qualified_categories=1,
                    quality_themes=0, min_condition=85, legacy_grace=False,
                    requirements=[dict(key='collection', label='合格收藏', current=1, target=15, met=False),
                                  dict(key='collection_categories', label='合格类别', current=1, target=5, met=False),
                                  dict(key='quality_themes', label='品质主题', current=0, target=3, met=False)],
                    missing=['合格收藏还差14种', '合格类别还差4类', '品质主题还差3套'],
                    categories=[dict(id=key, name=name, qualified_count=int(key=='tool'), theme_complete=False)
                                for key, name in [('tool','工具'),('artifact','古物'),('bot','机器人'),('plant','植物'),('signal','信号')]])
    cabinet = dict(id='I001', art_id='wrench', name='折叠离子扳手', kind='tool', rarity='common',
                   condition=65, description='握柄会记住上一位主人的手温。', collected=True,
                   collection_quality=dict(min_condition=85, condition_met=False, counted=False, reason='品相65%，尚未达到本阶段85%的门槛'),
                   repair=dict(available=True, reasons=[], cost=24, energy_cost=2, command='repair I001'))
    better = dict(cabinet, id='I002', condition=90, collected=False,
                  collection_quality=dict(min_condition=85, condition_met=True, counted=False, reason='仍在库存，未进入展柜'),
                  repair=dict(available=False, reasons=['今日已修理'], cost=22, energy_cost=2, command='repair I002'),
                  collection_replacement=dict(available=True, reasons=[], cabinet_item_id='I001', cabinet_condition=65,
                                              energy_cost=1, command='replace-collection I002'))
    worse = dict(better, id='I003', condition=60,
                 collection_quality=dict(min_condition=85, condition_met=False, counted=False, reason='仍在库存，且品相低于85%'),
                 repair=dict(available=False, reasons=['已达修理次数上限'], cost=25, energy_cost=2, command='repair I003'),
                 collection_replacement=dict(available=False, reasons=['品相必须严格高于在柜同款'], cabinet_item_id='I001', cabinet_condition=65,
                                             energy_cost=1, command='replace-collection I003'))
    known = dict(slot=1, discovered=True, collected=True,
                 **{key: cabinet[key] for key in ('art_id','name','kind','rarity','description','collection_quality')})
    entries = [known] + [dict(slot=i, discovered=False, collected=False) for i in range(2,25)]
    return dict(version=9, revision=1, day=15, credits=2000, energy=6, max_energy=12, reputation=20,
                phase='active', inventory=[better,worse], collection=[cabinet], crates=[], capacity=10,
                codex=dict(total=24, discovered=1, collected=1, entries=entries), collection_progress=progress,
                campaign=dict(next_milestone=dict(title='星港地标', goals=[
                    dict(label='现金',current=2000,target=4000),dict(label='合格收藏',current=1,target=15),
                    dict(label='声望',current=20,target=60),dict(label='升级',current=0,target=6),
                    dict(label='合格类别',current=1,target=5),dict(label='品质主题',current=0,target=3)])),
                visitors=[], upgrades={}, log=[],
                last_event=dict(title='继续经营', text='一盏暖灯，静候下一位旅客。'))


def engine_fixture():
    """Return a valid in-memory cabinet + better same-type inventory scene."""
    import engine
    state=engine.new_state(412)
    row=engine.CATALOG_BY_ID['wrench']
    cargo=dict(catalog_id=row[0],name=row[1],rarity=row[2],kind=row[3],base_value=row[4],
               description=row[5],origin=engine.SUPPLIERS['salvage']['name'],condition=65,
               collected=False,repairs=0,last_sale_day=0,last_repair_day=0)
    with mock.patch.object(engine,'_make_cargo',return_value=cargo):
        engine.apply_command(state,'buy',['salvage'])
    engine.apply_command(state,'open',['C001'])
    engine.apply_command(state,'collect',['I001'])
    with mock.patch.object(engine,'_make_cargo',return_value=dict(cargo,condition=90)):
        engine.apply_command(state,'buy',['salvage'])
    engine.apply_command(state,'open',['C002'])
    engine._validate_state(state)
    return state


class CollectionQualityRendererTests(unittest.TestCase):
    def setUp(self):
        self.observation = fixture()
        self.renderer = Renderer()

    def detail(self, page=0):
        return public_collection_detail(self.observation['codex']['entries'][0], self.observation, page)

    def test_main_summary_and_six_goals_render_at_every_existing_size(self):
        for size in SIZES:
            with self.subTest(size=size):
                image = self.renderer.render(self.observation, size, 'collection')
                self.assertEqual(image.size, size)
                words = '\n'.join(self.renderer.words)
                for expected in ['私藏 3 件 · 合格 1 种', '合格类别 1 · 品质主题 0',
                                 '本阶段品相 ≥85%', '合格收藏还差14种', '品质主题 0/3']:
                    self.assertIn(expected, words)
                cards = [(bounds, a) for bounds,a in self.renderer.hits if a[0]=='inspect' and a[1].get('_view')=='codex']
                summary = next(bounds for bounds,a in self.renderer.hits if a[0]=='inspect' and a[1].get('_view')=='collection_progress')
                self.assertTrue(cards)
                for bounds, _ in cards:
                    self.assertGreaterEqual(bounds[1], summary[3])
                    self.assertLess(bounds[3], self.renderer.H-33)

    def test_summary_detail_has_all_missing_requirements_and_category_counts(self):
        for size in SIZES:
            self.renderer.render(self.observation, size, 'collection', detail=dict(_view='collection_progress', progress=self.observation['collection_progress']))
            text = '\n'.join(self.renderer.words)
            for expected in ['合格收藏  1/15', '合格类别  1/5', '品质主题  0/3',
                             '合格收藏还差14种', '合格类别还差4类', '品质主题还差3套',
                             '工具 · 合格 1 种', '信号 · 合格 0 种', '普通收藏套装仍按原规则']:
                self.assertIn(expected, text)
            self.assertEqual(self.renderer.hits, [((0,0,self.renderer.W,self.renderer.H),('close',None))])


    def test_known_item_explains_cabinet_quality_repair_and_replacements(self):
        for size in SIZES:
            for page in range(3):
                self.renderer.render(self.observation, size, 'collection', detail=self.detail(page))
                text = '\n'.join(self.renderer.words)
                self.assertIn('折叠离子扳手', text)
                self.assertIn('未计入本阶段', text)
                self.assertIn('只读命令提示 · 点击不会修理或替换', text)
                self.assertTrue(all(a[0] in ('close','collection_page') for _,a in self.renderer.hits))
                if page==0:
                    for expected in ['在柜珍藏 I001 · 品相 65%', '品相65%，尚未达到', '可修理 · 24 星币 · 2 体力', 'repair I001', '库存同款 2 件 · 当前可替换 1 件']:
                        self.assertIn(expected, text)
                elif page==1:
                    for expected in ['库存同款 I002', '仍在库存，未进入展柜', '可替换 · 在柜 I001 为 65% · 1 体力', 'replace-collection I002', '今日已修理']:
                        self.assertIn(expected, text)
                else:
                    self.assertIn('暂不可替换', text)
                    self.assertIn('品相必须严格高于在柜同款', text)
                    self.assertIn('已达修理次数上限', text)

    def test_pagination_visits_every_public_slot_without_changing_state(self):
        before = copy.deepcopy(self.observation)
        for size in SIZES:
            self.renderer.render(self.observation, size, 'collection')
            seen = set()
            pages = self.renderer.page_count
            for page in range(pages):
                self.renderer.render(self.observation, size, 'collection', page)
                seen.update(a[1]['slot'] for _,a in self.renderer.hits if a[0]=='inspect' and a[1].get('_view')=='codex')
            self.assertEqual(seen, set(range(1,25)))
        self.assertEqual(self.observation,before)

    def test_navigation_is_read_only_and_refreshes_current_public_items(self):
        viewer = Spectator.__new__(Spectator)
        viewer.reader = SimpleNamespace(observation=self.observation)
        viewer.detail = self.detail()
        viewer.renderer = self.renderer
        viewer.last_signature = 'previous'
        before = copy.deepcopy(self.observation)
        self.renderer.render(self.observation, (390,844), 'collection', detail=viewer.detail)
        bounds = next(bounds for bounds,a in self.renderer.hits if a==('collection_page',1))
        x=((bounds[0]+bounds[2])/2)*self.renderer.scale+self.renderer.offset[0]
        y=((bounds[1]+bounds[3])/2)*self.renderer.scale+self.renderer.offset[1]
        viewer.click(SimpleNamespace(x=x,y=y))
        self.assertEqual(viewer.detail['_collection_page'],1)
        self.assertEqual(self.observation,before)
        self.observation['inventory'].pop(0)
        self.observation['collection'][0]['condition']=80
        viewer.refresh_detail()
        self.assertEqual([row['id'] for row in viewer.detail['_collection']['items']], ['I001','I003'])
        self.assertEqual(viewer.detail['_collection']['items'][0]['condition'],80)
        self.observation['codex']['entries'][0]['discovered']=False
        viewer.refresh_detail()
        self.assertEqual(viewer.detail,dict(slot=1,discovered=False,collected=False,_view='codex'))
        self.observation['codex']['entries']=[]
        viewer.refresh_detail()
        self.assertIsNone(viewer.detail)

    def test_sold_discovered_item_has_no_invented_repair_or_replacement(self):
        self.observation['collection']=[]
        self.observation['inventory']=[]
        self.observation['codex']['entries'][0]['collected']=False
        self.renderer.render(self.observation, detail=self.detail())
        self.assertIn('已发现 · 当前未持有', self.renderer.words)
        self.assertFalse(any('命令：' in word for word in self.renderer.words))

    def test_progress_detail_refreshes_and_disappears_with_public_data(self):
        viewer=Spectator.__new__(Spectator)
        viewer.reader=SimpleNamespace(observation=self.observation)
        viewer.detail=dict(_view='collection_progress', progress={})
        viewer.refresh_detail()
        self.assertEqual(viewer.detail['progress']['qualified_count'],1)
        self.observation.pop('collection_progress')
        viewer.refresh_detail()
        self.assertIsNone(viewer.detail)

    def test_new_projections_fail_closed_with_malformed_optional_fields(self):
        values=[None,[],1,'broken',{}]
        for value in values:
            self.assertEqual(public_collection_quality(value),{})
            self.assertEqual(public_collection_action(value),{})
            self.assertEqual(public_collection_progress(value),{})
        progress=public_collection_progress(dict(personal_count=True,qualified_count='bad',categories=[None,{'id':'SECRET'}],requirements=[None,{'key':'SECRET'}]))
        self.assertIsNone(progress['personal_count'])
        self.assertIsNone(progress['qualified_count'])
        self.assertEqual(progress['categories'],[])
        self.assertEqual(progress['requirements'],[])
        self.observation['collection_progress']=progress
        self.observation['collection'][0].update(collection_quality={'reason':None},repair={'available':'yes','reasons':[None]},condition='bad')
        self.renderer.render(self.observation, tab='collection',detail=self.detail())
        self.assertIn('等待公开资格说明',self.renderer.words)


class CollectionBackendProjectionTests(unittest.TestCase):
    def test_current_engine_projection_survives_replacement_and_detail_refresh(self):
        import engine
        state=engine_fixture()
        observation=engine.observation(state)
        before=copy.deepcopy(state)
        entry=next(v for v in observation['codex']['entries'] if v.get('art_id')=='wrench')
        detail=public_collection_detail(entry,observation,1)
        renderer=Renderer()
        renderer.render(observation,(1320,940),'collection',detail=detail)
        words='\n'.join(renderer.words)
        self.assertIn('可替换 · 在柜 I001 为 65% · 1 体力',words)
        self.assertIn('命令：replace-collection I002',words)
        self.assertEqual(state,before)
        engine.apply_command(state,'replace-collection',['I002'])
        engine._validate_state(state)
        viewer=Spectator.__new__(Spectator)
        viewer.reader=SimpleNamespace(observation=engine.observation(state))
        viewer.detail=dict(detail,_collection_page=0)
        viewer.refresh_detail()
        renderer.render(viewer.reader.observation,(390,844),'collection',detail=viewer.detail)
        words='\n'.join(renderer.words)
        self.assertIn('在柜珍藏 I002 · 品相 90%',words)
        self.assertIn('达到本阶段70%品相门槛，计入合格收藏',words)
        self.assertIn('命令：repair I002',words)
        self.assertEqual(viewer.reader.observation['collection_progress']['qualified_count'],1)

    def test_stages_without_category_requirement_do_not_invent_one(self):
        observation=fixture()
        progress=observation['collection_progress']
        progress['requirements']=[v for v in progress['requirements'] if v['key']!='collection_categories']
        progress['missing']=[v for v in progress['missing'] if not v.startswith('合格类别')]
        renderer=Renderer()
        renderer.render(observation,detail=dict(_view='collection_progress',progress=progress))
        self.assertFalse(any('合格类别  1/5' in word for word in renderer.words))
        self.assertFalse(any('合格类别还差' in word for word in renderer.words))


class NumericTokenWrappingTests(unittest.TestCase):
    def rows(self, text, width, lines=20):
        renderer=Renderer()
        renderer.image=Image.new('RGB',(600,400))
        renderer.draw=ImageDraw.Draw(renderer.image)
        with mock.patch.object(renderer.draw,'text') as draw:
            renderer.text((0,0),text,18,max_width=width,lines=lines)
        return [call.args[1] for call in draw.call_args_list]

    def test_percentages_and_fractions_stay_intact_across_narrow_widths(self):
        face=font(18)
        for token in ('70%','99%','100%','0.5%','1/3','12/24','1,234.5%'):
            text='品相至少'+token+'的合格收藏'
            for width in range(math.ceil(face.getlength(token)),math.ceil(face.getlength('品相至少'+token))+2,3):
                with self.subTest(token=token,width=width):
                    rows=self.rows(text,width)
                    self.assertEqual(''.join(rows),text)
                    self.assertTrue(any(token in row for row in rows))
                    self.assertTrue(all(face.getlength(row)<=width for row in rows))

    def test_screenshot_event_break_keeps_70_percent_together(self):
        text='第1天开张！先争取首周650星币与2种品相至少70%的合格收藏，再把小店经营成星港地标。'
        width=font(18).getlength('第1天开张！先争取首周650星币与2种品相至少70')
        rows=self.rows(text,width)
        self.assertEqual(''.join(rows),text)
        self.assertTrue(any('70%' in row for row in rows))
        self.assertFalse(any(row.startswith('%') for row in rows))

    def test_ellipsis_removes_whole_numeric_token_instead_of_its_suffix(self):
        for token in ('70%','99%','1/3'):
            width=font(18).getlength('当前'+token)
            rows=self.rows('当前'+token+'继续经营',width,lines=1)
            self.assertEqual(rows,['当前…'])
            self.assertLessEqual(font(18).getlength(rows[0]),width)

    def test_chinese_wrapping_and_explicit_newlines_remain_unchanged(self):
        self.assertEqual(self.rows('收藏品质\n星港旧物',font(18).getlength('收藏')),['收藏','品质','星港','旧物'])


class CollectionQualityPrivacyTests(unittest.TestCase):
    def test_unknown_exact_allowlist_discards_quality_repairs_replacements(self):
        source=dict(slot=9,discovered=False,collected=True,art_id='SECRET-ID',name='SECRET-NAME',
                    kind='SECRET-KIND',description='SECRET-STORY',
                    collection_quality=dict(reason='SECRET-QUALITY'),repair=dict(command='SECRET-REPAIR'),
                    collection_replacement=dict(command='SECRET-REPLACE'),
                    _collection={'items':[{'id':'SECRET-ITEM','location':'collection'}]})
        expected=dict(slot=9,discovered=False,collected=False)
        self.assertEqual(public_catalog_entry(source),expected)
        self.assertEqual(public_collection_detail(source,fixture()),dict(expected,_view='codex'))
        for flag in (False,None,0,1,'true',[],{}):
            self.assertEqual(set(public_collection_detail(dict(source,discovered=flag),fixture())), {'slot','discovered','collected','_view'})
        renderer=Renderer()
        for size in SIZES:
            for view in ('codex','sale','collection_progress'):
                renderer.render(fixture(),size,'collection',detail=dict(source,_view=view))
                surface='\n'.join(renderer.words)+json.dumps(renderer.hits,ensure_ascii=False)
                self.assertNotIn('SECRET',surface)
                self.assertEqual(renderer.hits,[((0,0,renderer.W,renderer.H),('close',None))])

    def test_private_fields_never_survive_known_item_detail_join(self):
        observation=fixture()
        observation['collection'][0].update(catalog_id='SECRET-CATALOG',base_value='SECRET-VALUE',cargo='SECRET-CARGO')
        observation['collection'][0]['repair']['secret']='SECRET-REPAIR'
        observation['inventory'][0]['collection_replacement']['secret']='SECRET-REPLACEMENT'
        observation['inventory'].append(dict(observation['inventory'][0],art_id='unknown',name='SECRET-UNKNOWN'))
        detail=public_collection_detail(observation['codex']['entries'][0],observation)
        self.assertNotIn('SECRET',json.dumps(detail,ensure_ascii=False))
        self.assertEqual(len(detail['_collection']['items']),3)
        renderer=Renderer()
        for page in range(3):
            renderer.render(observation,detail=dict(detail,_collection_page=page))
            self.assertNotIn('SECRET','\n'.join(renderer.words)+json.dumps(renderer.hits,ensure_ascii=False))


if __name__ == '__main__':
    unittest.main()
