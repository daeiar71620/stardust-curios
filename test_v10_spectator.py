"""Native v10 public UI regression scenes; no live GUI or private save access."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import ImageDraw

from spectator import (KINDS, ObservationReader, Renderer, Spectator, TABS,
                       native_observation, public_cost_breakdown, public_deadline,
                       public_management_detail, public_supplier)
from test_spectator import fixture


SIZES = ((390, 844), (1320, 940))


def management_fixture(day=21):
    obs = fixture()
    obs.update(version=10, protocol_version=10, day=day)
    current = 0 if day < 8 else 7
    overdue = max(0, day - 18)
    fee = min(6, overdue * 2) if day >= 8 else 0
    breakdown = dict(base=10, event_delta=-2, plant_discount=4, base_after_modifiers=4,
                     facility_upkeep=current, facility_upkeep_from_day8=7,
                     facility_upkeep_unlock_day=8, overdue_surcharge=fee,
                     total=4 + current + fee)
    obs.update(operating_cost=breakdown['total'], operating_cost_breakdown=breakdown)
    obs['upgrade_details'] = [dict(id=key, name=name, level=level, max_level=3,
                                  effect='合成场景设施效果', next_effect='合成场景下一级效果',
                                  next_cost=100 if level < 3 else None,
                                  daily_upkeep=0 if day < 8 else amount,
                                  daily_upkeep_from_day8=amount,
                                  next_daily_upkeep=0 if day < 8 else amount + 1,
                                  next_daily_upkeep_from_day8=amount + 1 if level < 3 else None,
                                  upkeep_unlock_day=8)
                              for key, name, level, amount in (
                                  ('workbench', '修理工作台', 1, 2),
                                  ('shelf', '陈列货架', 1, 1),
                                  ('display', '收藏展柜', 3, 4))]
    stage = obs['campaign']['next_milestone']
    stage.update(id='neighborhood', nominal_due_day=14, effective_due_day=18,
                 unlocked_day=11, days_remaining=max(0, 18-day), overdue_days=overdue,
                 missed_day=18 if overdue else None, overdue_surcharge=fee)
    obs['campaign']['deadline_history'] = [dict(id='opening', title='首周开门', nominal_due_day=7,
        effective_due_day=7, unlocked_day=1, missed_day=7, completed_day=11, status='completed_late'),
        dict(stage, status='missed' if overdue else 'active', completed_day=None)]
    obs['suppliers'] = [dict(id='salvage', name='废轨回收站', cost=48, stock=4, remaining=4,
                            energy_cost=1, unlock_day=1, unlocked=True, daily_limit=4,
                            description='平价漂流箱'),
                        dict(id='curated', name='夜航商队', cost=110, stock=2, remaining=2,
                            energy_cost=1, unlock_day=1, unlocked=True, daily_limit=2,
                            description='精选封存箱'),
                        dict(id='focused', name='分类采购站', cost=155, stock=int(day>=8),
                            remaining=int(day>=8), energy_cost=1, unlock_day=8,
                            unlocked=day>=8, daily_limit=1,
                            categories=[dict(id=key, name=name) for key, name in KINDS.items()],
                            description='普通28% / 稀有61% / 传说11% · 品相48–96 · 每日1箱')]
    obs['crates'] = [dict(id='C001', supplier='focused', name='分类封存箱',
                          requested_kind='signal', requested_kind_label='信号')] if day>=8 else []
    obs['last_settlement'] = dict(day=20, paid=19, credits_after_payment=500,
        breakdown=dict(breakdown, event_delta=0, base_after_modifiers=6, total=19)) if day>8 else None
    return obs


class RecordingRenderer(Renderer):
    def __init__(self):
        super().__init__()
        self.overlay_text_bounds = []

    def management_detail(self, source):
        original = ImageDraw.ImageDraw.text
        def capture(draw, xy, text, *args, **kwargs):
            bounds = draw.textbbox(xy, text, font=kwargs.get('font'), anchor=kwargs.get('anchor'))
            self.overlay_text_bounds.append((text, bounds))
            return original(draw, xy, text, *args, **kwargs)
        with patch.object(ImageDraw.ImageDraw, 'text', capture):
            return super().management_detail(source)


class V10PublicManagementTests(unittest.TestCase):
    def setUp(self):
        self.obs = management_fixture()
        self.renderer = Renderer()

    def show(self, section, *, size=(1320, 940), page=0):
        detail = public_management_detail(self.obs, section, page)
        self.renderer.render(self.obs, size, 'upgrades', detail=detail)
        return self.renderer.words

    def viewer(self, section, page=0):
        viewer = Spectator.__new__(Spectator)
        viewer.reader = SimpleNamespace(observation=self.obs)
        viewer.detail = public_management_detail(self.obs, section, page)
        viewer.renderer = self.renderer
        viewer.last_signature = 'old'
        return viewer

    def test_version_and_protocol_cannot_claim_v9_compatibility(self):
        self.assertTrue(native_observation(self.obs))
        for field in ('version', 'protocol_version'):
            for version in (9, 11, True, 10.0, '10'):
                source = dict(self.obs, **{field: version})
                self.assertFalse(native_observation(source))
                self.renderer.render(source, (390,844))
                self.assertIn('不支持此公开状态版本 · 仅支持 v10', self.renderer.words)
                self.assertEqual(self.renderer.hits, [])

    def test_goal_exposes_effective_due_day_and_overdue_without_a_control(self):
        for size in SIZES:
            self.renderer.render(self.obs, size)
            self.assertIn('第 18 天到期 · 逾期 3 天', self.renderer.words)
            details = [action[1] for _, action in self.renderer.hits
                       if action[0]=='inspect' and action[1].get('_section')=='deadlines']
            self.assertEqual(len(details), 1)
            self.assertEqual(details[0]['campaign']['next_milestone']['effective_due_day'], 18)
        self.obs['campaign']['next_milestone'].update(days_remaining=0, overdue_days=0)
        self.assertIn('第 18 天到期 · 今日到期', self.show('deadlines'))
        self.obs['campaign']['next_milestone'].update(days_remaining=5)
        self.assertIn('第 18 天到期 · 剩余 5 天', self.show('deadlines'))

    def test_growth_cards_publish_current_future_and_procurement_costs(self):
        self.renderer.render(self.obs, (1320,940), 'upgrades')
        for text in ('闭店费用 · 17 星币', '今日设施 7 · 第8天起 7/日 · 逾期 6',
                     '阶段期限与迟到记录', '分类采购 · 查看公开货源', '155 星币 · 1 精力 · 今日余 1 箱'):
            self.assertIn(text, self.renderer.words)
        sections = {action[1].get('_section') for _,action in self.renderer.hits if action[0]=='inspect'}
        self.assertTrue({'costs','deadlines','suppliers'} <= sections)

    def test_first_week_forecast_does_not_charge_facilities_early(self):
        self.obs = management_fixture(day=6)
        for size in SIZES:
            words = self.show('costs', size=size)
            for text in ('本次闭店应付 4 星币', '今日设施养护  0 星币', '当前阶段逾期费  0 星币',
                         '第8天起，现有设施合计 7 星币/日', '修理工作台  0 / 2 / 3',
                         '尚无已支付的闭店结算'):
                self.assertIn(text, words)
        self.obs = management_fixture(day=8)
        self.assertIn('本次闭店应付 11 星币', self.show('costs'))

    def test_public_invoice_and_prior_payment_are_kept_separate(self):
        for size in SIZES:
            words = self.show('costs', size=size)
            for text in ('本次闭店应付 17 星币', '港口事件调整  -2 星币', '植物套装减免  −4 星币',
                         '最近已结算：第 20 天 · 已支付 19 星币', '扣款后现金 500 星币',
                         '当次调整后营业 6 + 设施 7 + 逾期 6',
                         '闭店先支付当日费用，再以扣款后现金判定阶段目标。当前预估会随设施与事件变化。'):
                self.assertIn(text, words)
        # The UI reports the authoritative total, even in an inconsistent fixture.
        self.obs['operating_cost_breakdown']['total'] = 23
        self.assertIn('本次闭店应付 23 星币', self.show('costs'))
        self.obs['phase'] = 'week_summary'
        self.assertIn('当前规则费用参考 23 星币', self.show('costs'))
        self.assertNotIn('本次闭店应付 23 星币', self.renderer.words)

    def test_history_shows_late_completion_and_current_stage_only_fee(self):
        for size in SIZES:
            words = self.show('deadlines', size=size)
            self.assertIn('计划期限 第 14 天 · 实际期限 第 18 天', words)
            self.assertIn('第 11 天解锁 · 当前逾期费 6 星币/日', words)
            self.assertIn('迟到后完成 · 期限 7 · 错过 7 · 完成 11', words)
            self.assertIn('期限已错过 · 期限 18 · 错过 18 · 尚未完成', words)
            self.assertIn('后续阶段解锁后至少留7天；逾期仍可补齐。只计当前阶段逾期费，旧阶段迟到记录保留。', words)

    def test_focused_category_info_is_visible_before_and_after_unlock(self):
        for day in (7,8):
            self.obs = management_fixture(day)
            for size in SIZES:
                words = self.show('suppliers', size=size)
                self.assertIn('分类采购站', words)
                self.assertIn('每箱 155 星币 · 1 精力', words)
                self.assertIn(f'今日剩余 {int(day>=8)} 箱 · 每日限额 1 箱', words)
                self.assertIn('已开放' if day>=8 else '第 8 天开放', words)
                for key, label in KINDS.items():
                    self.assertIn(f'{label} · {key}', words)
                if day>=8:
                    self.assertIn('待开分类箱：C001（信号）', words)
                self.assertTrue(all(action[0] in ('close','management_page') for _,action in self.renderer.hits))

    def test_unknown_fields_names_and_sealed_contents_never_reach_projection_or_ui(self):
        self.obs.update(private_economics='SECRET_ROOT')
        self.obs['operating_cost_breakdown']['hidden_value'] = 'SECRET_FEE'
        self.obs['last_settlement']['private_state'] = 'SECRET_SETTLEMENT'
        self.obs['last_settlement']['breakdown']['rng'] = 'SECRET_RNG'
        self.obs['campaign']['next_milestone']['catalog'] = 'SECRET_STAGE'
        self.obs['campaign']['deadline_history'][0]['sealed_item'] = 'SECRET_HISTORY'
        for supplier in self.obs['suppliers']:
            supplier.update(catalog_names=['SECRET_UNSEEN'], cargo={'name':'SECRET_CARGO'}, next_item='SECRET_NEXT')
        focused = self.obs['suppliers'][-1]
        focused['categories'].append(dict(id='SECRET_CATEGORY',name='SECRET_CATEGORY_NAME'))
        focused['categories'][0]['name'] = 'SECRET_CATEGORY_ALIAS'
        self.obs['suppliers'].append(dict(id='SECRET_VENDOR',name='SECRET_VENDOR_NAME'))
        self.obs['crates'][0].update(name='SECRET_SEALED_NAME', requested_kind_label='SECRET_KIND_ALIAS',
                                   cargo={'name':'SECRET_CARGO'}, art_id='SECRET_ART')
        for row in self.obs['upgrade_details']:
            row['private_cost'] = 'SECRET_UPGRADE'
        for section in ('costs','deadlines','suppliers'):
            detail = public_management_detail(self.obs, section)
            self.assertNotIn('SECRET', json.dumps(detail))
            # Direct callers cannot bypass the second projection in the overlay.
            detail.update(_private='SECRET_BYPASS')
            for size in SIZES:
                self.renderer.render(self.obs,size,'upgrades',detail=detail)
                self.assertNotIn('SECRET', str(self.renderer.words)+str(self.renderer.hits))

    def test_nested_malformed_fields_cannot_invent_costs_or_categories(self):
        invalid = (None, True, 'bad', float('nan'), -1, [], {})
        for value in invalid:
            self.assertIsNone(public_cost_breakdown(dict(total=value))['total'])
            self.assertIsNone(public_deadline(dict(overdue_days=value))['overdue_days'])
            supplier = public_supplier(dict(id='focused', cost=value, categories=[value]))
            self.assertIsNone(supplier['cost'])
            self.assertEqual(supplier['categories'], [])
        self.obs.update(operating_cost_breakdown={'total': True}, last_settlement={'paid':'bad'},
                        campaign={'next_milestone':{'effective_due_day': True},'deadline_history':[None,[]]},
                        suppliers=[None,[],dict(id='focused',cost=True,remaining=-1,unlocked='yes')],
                        crates=[None,dict(supplier='focused',requested_kind='unknown')])
        for section in ('costs','deadlines','suppliers'):
            for size in SIZES:
                self.show(section,size=size)
        self.assertIn('每箱 ? 星币 · ? 精力', self.renderer.words)
        self.assertIn('等待公开开放状态', self.renderer.words)

    def test_long_labels_draw_within_panel_without_overlaps_at_phone_and_desktop(self):
        long = '这是一段非常长的公开名称用于验证窗口文字换行与省略' * 12
        self.obs['campaign']['next_milestone']['title'] = long
        self.obs['campaign']['deadline_history'] = [dict(row,title=long) for row in self.obs['campaign']['deadline_history']]
        self.obs['suppliers'][-1].update(name=long,description=long)
        for size in SIZES:
            for section in ('costs','deadlines','suppliers'):
                renderer = RecordingRenderer()
                image = renderer.render(self.obs,size,'upgrades',detail=public_management_detail(self.obs,section))
                self.assertEqual(image.size,size)
                panel_width = min(renderer.W-40,710)
                left = (renderer.W-panel_width)/2
                top = (renderer.H-860)/2
                for text,(x0,y0,x1,y1) in renderer.overlay_text_bounds:
                    self.assertGreaterEqual(x0,left+10,(section,text))
                    self.assertLessEqual(x1,left+panel_width-10,(section,text))
                    self.assertGreaterEqual(y0,top+20,(section,text))
                    self.assertLessEqual(y1,top+850,(section,text))
                for i,(a,boxa) in enumerate(renderer.overlay_text_bounds):
                    for b,boxb in renderer.overlay_text_bounds[i+1:]:
                        overlaps = min(boxa[2],boxb[2])>max(boxa[0],boxb[0]) and min(boxa[3],boxb[3])>max(boxa[1],boxb[1])
                        self.assertFalse(overlaps,(section,a,b))

    def test_management_paging_wraps_closes_and_refreshes_public_costs(self):
        viewer = self.viewer('suppliers')
        for delta,expected in ((1,1),(1,2),(1,0),(-1,2)):
            self.renderer.render(self.obs,(390,844),'upgrades',detail=viewer.detail)
            bounds = next(bounds for bounds, action in self.renderer.hits if action==('management_page',delta))
            event = SimpleNamespace(x=(bounds[0]+bounds[2])/2*self.renderer.scale+self.renderer.offset[0],
                                    y=(bounds[1]+bounds[3])/2*self.renderer.scale+self.renderer.offset[1])
            viewer.click(event)
            self.assertEqual(viewer.detail['_management_page'],expected)
        self.obs['suppliers'][-1].update(stock=0,remaining=0)
        viewer.refresh_detail()
        self.assertEqual(viewer.detail['suppliers'][-1]['remaining'],0)
        viewer.detail = public_management_detail(self.obs,'costs')
        self.obs['operating_cost_breakdown']['total'] = 30
        viewer.refresh_detail()
        self.assertEqual(viewer.detail['operating_cost_breakdown']['total'],30)
        viewer.click(SimpleNamespace(x=0,y=0))
        self.assertIsNone(viewer.detail)

    def test_history_pagination_does_not_drop_older_late_records(self):
        self.obs['campaign']['deadline_history'] = [dict(self.obs['campaign']['deadline_history'][0],title=f'阶段 {i}') for i in range(11)]
        shown = []
        for page in range(3):
            shown += list(self.show('deadlines',page=page))
        for i in range(11):
            self.assertIn(f'阶段 {i}',shown)

    def test_render_refresh_and_all_hits_are_pure_readonly(self):
        before = copy.deepcopy(self.obs)
        for size in SIZES:
            for section in ('costs','deadlines','suppliers'):
                viewer = self.viewer(section)
                viewer.refresh_detail()
                self.show(section,size=size)
                first = list(self.renderer.words)
                self.renderer.render(self.obs,size,'upgrades',detail=viewer.detail,frame=999)
                self.assertEqual(first,self.renderer.words)
                for (x0,y0,x1,y1),action in self.renderer.hits:
                    self.assertTrue(0<=x0<=x1<=self.renderer.W)
                    self.assertTrue(0<=y0<=y1<=self.renderer.H)
                    self.assertIn(action[0],('close','management_page'))
        self.assertEqual(self.obs,before)

    def test_only_the_selected_temporary_public_file_is_read(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'v10.synthetic.observation.json'
            path.write_text(json.dumps(self.obs,ensure_ascii=False))
            original = path.read_bytes()
            opener = Path.open
            def readonly(target,*args,**kwargs):
                self.assertEqual(target,path)
                self.assertEqual(args,('rb',))
                return opener(target,*args,**kwargs)
            with patch.object(Path,'open',readonly), patch.object(Path,'write_text',side_effect=AssertionError('write attempted')):
                reader = ObservationReader(path)
                self.assertTrue(reader.poll())
                for section in ('costs','deadlines','suppliers'):
                    self.renderer.render(reader.observation,(390,844),detail=public_management_detail(reader.observation,section))
                self.assertFalse(reader.poll())
            self.assertEqual(path.read_bytes(),original)
            self.assertEqual(list(Path(directory).iterdir()),[path])


if __name__=='__main__':
    unittest.main()
