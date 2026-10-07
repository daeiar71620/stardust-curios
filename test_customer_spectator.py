"""Synthetic public-only v9 UI checks; no engine or personal save access."""
import copy
import json
from types import SimpleNamespace
import unittest

from spectator import (Renderer, Spectator, TABS, public_sale_detail,
                       public_sale_option, public_walkins, sale_status)
from test_spectator import fixture, percentile_fixture


def customer_fixture():
    obs = fixture()
    obs['version'] = 9
    obs['walkins'] = {'daily_limit': 1, 'used': 0, 'remaining': 1,
                      'budget_range': [60, 120], 'min_condition': 45,
                      'visit_rule': '每天1次；正式出售无论成交、还价或离店都占用，改价/换货/重启不刷新；次日重置'}
    item = obs['inventory'][0]
    item.update(price=100, public_reference=100)
    ordinary = {'customer_id': None, 'customer_name': '旅客', 'available': True,
                'counter_eligible': True, 'reasons': [], 'public_reference': 100,
                'max_counter_ask': 120, 'budget_range': [60, 120], 'min_condition': 45,
                'preference_match': True, 'condition_met': True, 'ask': 100,
                'warning': '普通失败会提出一次还价；100仍直接离店。正式尝试花1精力并用掉该买家今日接待；本货今日不能改价换客重试。常规预算表示消费舒适度，超出会逐步降低初次成功率；精确预算隐藏。'}
    named = dict(ordinary, customer_id='mira', customer_name='米拉',
                 counter_eligible=False, reasons=['类别不合顾客偏好'],
                 max_counter_ask=125, budget_range=[130, 340], preference_match=False,
                 warning='普通失败直接离店，不会还价；01仍可按标价成交。正式尝试花1精力并用掉该买家今日接待；本货今日不能改价换客重试。常规预算表示消费舒适度，超出会逐步降低初次成功率；精确预算隐藏。')
    item['sale_options'] = [ordinary, named]
    return obs


class CustomerSpectatorTests(unittest.TestCase):
    def setUp(self):
        self.renderer = Renderer()
        self.obs = customer_fixture()

    def render(self, **kwargs):
        self.renderer.render(self.obs, **kwargs)
        return self.renderer.words

    def detail(self, page=0):
        return public_sale_detail(self.obs['inventory'][0], self.obs['walkins'], page)

    def viewer(self, detail):
        viewer = Spectator.__new__(Spectator)
        viewer.detail = detail
        viewer.reader = SimpleNamespace(observation=self.obs)
        viewer.renderer = self.renderer
        viewer.last_signature = 'old'
        return viewer

    def test_daily_capacity_and_public_budget_visible_before_any_roll(self):
        for tab, _ in TABS:
            words = self.render(tab=tab)
            self.assertTrue(any('散客剩余 1/1 次 · 常规预算 60–120' in v for v in words))
        self.obs['walkins'].update(used=1, remaining=0)
        words = self.render(tab='visitors')
        self.assertIn('普通散客', words)
        self.assertIn('今日剩 0 次', words)
        self.assertIn('公开常规预算 60–120 星币', words)
        self.assertIn('还价需品相 ≥45%', words)

    def test_shelf_leads_to_public_eligibility_not_a_sale_action(self):
        words = self.render()
        self.assertIn('旧物货架 · 点击查看售前条件', words)
        self.assertIn('品相 76% · 散客：普通失败可还价', words)
        payload = next(a[1] for _, a in self.renderer.hits
                       if a[0] == 'inspect' and a[1].get('_view') == 'sale')
        self.assertEqual(payload['id'], 'I001')
        words = self.render(detail=payload)
        for expected in ('旅客 · 普通散客', '普通失败可还价', '公开常规预算 60–120 星币',
                         '还价标价范围：2–120 星币', '公开还价条件均符合',
                         '还价仍须≤参考价125%及常规预算区间上限',
                         '常规预算是消费舒适度，超出后初次成功率逐步降低\n还价资格非成交保证；初次精确成功率不公开',
                         '01 仍可奇迹成交（1%）· 100 直接离店（1%）'):
            self.assertIn(expected, words)
        self.assertTrue(all(a[0] in {'close', 'sale_page'} for _, a in self.renderer.hits))

    def test_named_buyer_has_own_budget_preference_reason_and_consequence(self):
        words = self.render(detail=self.detail(1))
        for expected in ('米拉 · 特邀顾客', '公开常规预算 130–340 星币',
                         '还价标价范围：2–125 星币', '品相 ≥45%（达标） · 偏好不匹配',
                         '不符：类别不合顾客偏好', '普通失败直接离开'):
            self.assertIn(expected, words)
        self.assertTrue(any('普通失败直接离店，不会还价；01仍可按标价成交' in v for v in words))

    def test_price_and_condition_reasons_are_public_not_recomputed(self):
        item = self.obs['inventory'][0]
        item.update(price=9999, condition=30)
        option = item['sale_options'][0]
        option.update(ask=9999, counter_eligible=False, condition_met=False,
                      reasons=['标价超过公开参考价125%的125星币上限',
                               '标价超过公开预算区间上限120星币', '品相未达到45%'])
        words = self.render(detail=self.detail())
        self.assertIn('标价 9999 · 公开参考价 100', words)
        self.assertIn('普通失败直接离开', words)
        self.assertIn('品相 ≥45%（未达标）', words)
        self.assertIn('不符：' + '；'.join(option['reasons']), words)
        # The spectator follows the engine's public decision even if a synthetic
        # fixture is inconsistent. It cannot reconstruct or peek at economics.
        option.update(counter_eligible=True, reasons=[])
        self.assertIn('普通失败可还价', self.render(detail=self.detail()))

    def test_unavailable_buyers_never_claim_an_attempt_is_available(self):
        option = self.obs['inventory'][0]['sale_options'][0]
        option['available'] = False
        self.assertEqual(sale_status(public_sale_option(option))[0], '当前不可出售')
        words = self.render(detail=self.detail())
        self.assertIn('当前不可出售', words)
        self.assertNotIn('普通失败可还价', words)

    def test_projection_drops_hidden_economics_and_initial_odds(self):
        self.obs['walkins'].update(budget='SECRET_EXACT_BUDGET', rng='SECRET_RNG')
        item = self.obs['inventory'][0]
        item.update(context='SECRET_CONTEXT', initial_probability='SECRET_INITIAL_ODDS')
        for option in item['sale_options']:
            option.update(exact_budget='SECRET_BUYER', initial_probability='SECRET_ODDS',
                          threshold='SECRET_THRESHOLD', private_reference='SECRET_VALUE')
        detail = self.detail()
        encoded = json.dumps(detail)
        self.assertNotIn('SECRET', encoded)
        for option in detail['sale_options']:
            self.assertNotIn('threshold', option)
            self.assertNotIn('initial_probability', option)
            self.assertNotIn('exact_budget', option)
        words = self.render(detail=detail)
        self.assertNotIn('SECRET', str(words))
        self.assertFalse(any('成功率 58%' in v or '低骰成功：' in v for v in words))

    def test_malformed_forecasts_do_not_invent_eligibility_or_crash(self):
        for value in (None, [], 'bad', {'remaining': True, 'budget_range': [120, 60]},
                      {'daily_limit': 'bad', 'remaining': -1, 'min_condition': float('nan')}):
            public_walkins(value)
        option = self.obs['inventory'][0]['sale_options'][0]
        option.update(available='yes', counter_eligible='yes', max_counter_ask=True,
                      budget_range=[120, 60], min_condition=101, reasons=[None, {'secret': 'SECRET'}])
        words = self.render(detail=self.detail())
        self.assertIn('等待完整公开条件', words)
        self.assertIn('等待公开预算范围', words)
        self.assertIn('等待公开还价标价上限', words)
        self.assertNotIn('SECRET', str(words))
        self.obs['inventory'][0]['sale_options'] = [None, 'bad']
        self.assertIn('等待公开售前条件', self.render(detail=self.detail()))

    def test_buyer_paging_wraps_and_close_remains_reachable(self):
        viewer = self.viewer(self.detail())
        for delta, expected in ((1, 1), (1, 0), (-1, 1)):
            self.render(detail=viewer.detail)
            bounds = next(b for b, a in self.renderer.hits if a == ('sale_page', delta))
            event = SimpleNamespace(x=(bounds[0]+bounds[2])/2*self.renderer.scale+self.renderer.offset[0],
                                    y=(bounds[1]+bounds[3])/2*self.renderer.scale+self.renderer.offset[1])
            viewer.click(event)
            self.assertEqual(viewer.detail['_sale_page'], expected)
        viewer.click(SimpleNamespace(x=0, y=0))
        self.assertIsNone(viewer.detail)

    def test_open_forecast_refreshes_prices_quota_and_closes_when_item_is_gone(self):
        viewer = self.viewer(self.detail(1))
        self.obs['walkins'].update(used=1, remaining=0)
        item = self.obs['inventory'][0]
        item['price'] = 120
        item['sale_options'][1].update(ask=120, available=False)
        viewer.refresh_detail()
        self.assertEqual(viewer.detail['_sale_page'], 1)
        words = self.render(detail=viewer.detail)
        self.assertIn('标价 120 · 公开参考价 100', words)
        self.assertIn('散客剩余 0/1 次 · 常规预算 60–120', words)
        self.assertIn('当前不可出售', words)
        self.obs['inventory'] = []
        viewer.refresh_detail()
        self.assertIsNone(viewer.detail)

    def test_walkin_detail_explains_consumption_and_refreshes(self):
        detail = dict(_view='walkins', walkins=self.obs['walkins'])
        words = self.render(detail=detail)
        self.assertIn('今日已用 0 次 · 次日重置', words)
        self.assertIn('正式出售花1体力；无效指令不占名额', words)
        self.assertIn('普通失败可能直接离店，收入0；货物留下，今日不能换客重试。', words)
        self.assertTrue(any('改价/换货/重启不刷新' in v for v in words))
        viewer = self.viewer(detail)
        self.obs['walkins'].update(used=1, remaining=0)
        viewer.refresh_detail()
        self.assertEqual(viewer.detail['walkins']['remaining'], 0)
        del self.obs['walkins']
        viewer.refresh_detail()
        self.assertIsNone(viewer.detail)


    def test_native_final_negotiation_retains_single_exact_public_preview(self):
        self.obs = percentile_fixture(price=165, threshold=58, pending=True)
        self.obs.update(version=9, walkins=customer_fixture()['walkins'])
        self.obs['last_roll']['rules_version'] = 9
        self.obs['negotiation'].update(rules_version=9, origin_rules_version=9)
        words = self.render()
        self.assertIn('还价中 · 最后一次报价', words)
        self.assertIn('低骰成功：01–58 · 成功率 58%', words)
        self.assertIn('失败收入 0 · 失去 150 星币还价', words)
        self.assertIn('01 必成（1%）· 100 必败（1%）', words)



    def test_negotiating_item_explains_new_conditions_do_not_revoke_quote(self):
        item = self.obs['inventory'][0]
        item['negotiating'] = True
        for option in item['sale_options']:
            option['available'] = False
        for size in ((1320, 940), (760, 1240), (390, 844), (320, 568)):
            words = self.render(size=size, detail=self.detail(1))
            self.assertIn('已有还价请按待谈面板处理；新售前条件不撤销已承诺还价', words)
            self.assertIn('已有还价 · 暂不接待新出售', words)
            self.assertNotIn('当前不可出售', words)
            self.assertIn('不符：类别不合顾客偏好', words)
        viewer = self.viewer(self.detail())
        item['negotiating'] = False
        viewer.refresh_detail()
        self.assertFalse(viewer.detail['negotiating'])
        self.assertNotIn('已有还价请按待谈面板处理；新售前条件不撤销已承诺还价',
                         self.render(detail=viewer.detail))

    def test_all_sizes_are_readonly_deterministic_and_overlay_hits_stay_in_bounds(self):
        before = copy.deepcopy(self.obs)
        for size in ((1320, 940), (760, 1240), (390, 844), (320, 568)):
            for detail in (None, self.detail(), self.detail(1), dict(_view='walkins', walkins=self.obs['walkins'])):
                with self.subTest(size=size, view=detail and detail['_view']):
                    self.render(size=size, detail=detail, demo=True)
                    for (x0, y0, x1, y1), _ in self.renderer.hits:
                        self.assertTrue(0 <= x0 <= x1 <= self.renderer.W)
                        self.assertTrue(0 <= y0 <= y1 <= self.renderer.H)
        self.render(detail=self.detail(), frame=0)
        words = list(self.renderer.words)
        self.render(detail=self.detail(), frame=999)
        self.assertEqual(words, self.renderer.words)
        self.assertEqual(before, self.obs)



if __name__ == '__main__':
    unittest.main()
