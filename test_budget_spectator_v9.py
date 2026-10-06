"""Read-only v9 budget UI checks with synthetic public scenes only.

No actual game, private save, or persisted demonstration artifact is used.
"""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from spectator import (ObservationReader, Renderer, Spectator, TABS,
                       honored_quote_label, percentile_rules, public_negotiation,
                       public_roll, public_sale_detail, roll_rules_label)
from test_customer_spectator_v6 import customer_fixture
from test_spectator import dice_fixture, percentile_fixture


SIZES = ((1320, 940), (760, 1240), (390, 844), (320, 568), (1364, 1024))


def budget_fixture():
    observation = customer_fixture()
    observation.update(version=9, budget_upgrade=None)
    for option in observation['inventory'][0]['sale_options']:
        consequence = ('普通失败会提出一次还价；100仍直接离店。' if option['counter_eligible']
                       else '普通失败直接离店，不会还价；01仍可按标价成交。')
        option['warning'] = (consequence + '正式尝试花1精力，并占用该买家与货物今日接待。'
                             '常规预算表示消费舒适度，超出会逐步降低初次成功率；精确预算隐藏。')
    return observation


def pending_fixture(origin=6):
    observation = percentile_fixture(price=165, threshold=58, pending=True)
    observation.update(version=9, walkins=budget_fixture()['walkins'])
    observation['last_roll']['rules_version'] = origin
    observation['negotiation'].update(rules_version=9, origin_rules_version=origin)
    if origin in (3, 4):
        observation['last_roll'] = dict(dice_fixture('failure', 4, pending=True)['last_roll'],
                                        rules_version=origin)
    return observation


class BudgetSpectatorV9Tests(unittest.TestCase):
    def setUp(self):
        self.renderer = Renderer()
        self.observation = budget_fixture()

    def render(self, **kwargs):
        self.renderer.render(self.observation, **kwargs)
        return self.renderer.words

    def detail(self, page=0):
        return public_sale_detail(self.observation['inventory'][0],
                                  self.observation['walkins'], page)

    def test_v9_percentile_version_is_not_relabeled_v5(self):
        roll = dict(percentile_fixture(tens=0, ones=1, outcome='miracle')['last_roll'],
                    rules_version=9)
        self.assertEqual(roll_rules_label(roll), 'v9 · D100 低骰规则')
        self.assertTrue(percentile_rules({'rules_version': 9}))
        del roll['die']
        self.assertEqual(public_roll(roll)['roll'], 1)
        for version in (5, 6):
            self.assertEqual(roll_rules_label(dict(roll, rules_version=version)),
                             f'v{version} · D100 低骰规则')
        for version in (3, 4):
            old = dict(dice_fixture('miracle', 20, pending=False)['last_roll'],
                       rules_version=version)
            self.assertEqual(roll_rules_label(old), f'v{version} · D20 原高骰规则')
        # Protocol 7/8 never introduced separate transaction rules.
        for version in (7, 8, True, 10):
            self.assertNotIn(f'v{version} ·', roll_rules_label(dict(roll, rules_version=version)))

    def test_mixed_history_uses_each_original_rule_label_on_every_page(self):
        d20 = dice_fixture('miracle', 20, pending=False)['last_roll']
        d100 = percentile_fixture(tens=0, ones=1, outcome='miracle')['last_roll']
        self.observation['roll_history'] = [dict(d20, rules_version=3), dict(d20, rules_version=4),
                                          dict(d100, rules_version=5), dict(d100, rules_version=6),
                                          dict(d100, rules_version=9)]
        before = copy.deepcopy(self.observation)
        for size in SIZES:
            self.render(size=size, tab='journal', journal_mode='rolls')
            words = []
            for page in range(self.renderer.page_count):
                words.extend(self.render(size=size, tab='journal', journal_mode='rolls', page=page))
            for label in ('v3 · D20 原高骰规则', 'v4 · D20 原高骰规则', 'v5 低骰', 'v6 低骰', 'v9 低骰'):
                self.assertTrue(any(label in word for word in words), (size, label))
        self.assertEqual(self.observation, before)

    def test_new_public_range_is_normal_spending_comfort(self):
        for tab, _ in TABS:
            words = self.render(tab=tab)
            self.assertTrue(any('散客剩余 1/1 次 · 常规预算 60–120' in word for word in words))
        words = self.render(tab='visitors')
        self.assertIn('公开常规预算 60–120 星币', words)
        named = next(action[1] for _, action in self.renderer.hits
                     if action[0] == 'inspect' and action[1].get('id') == 'mira')
        self.assertIn('公开常规预算 130–340 星币', named['description'])
        self.assertIn('常规预算是消费舒适度', named['description'])
        self.assertIn('超出会逐步降低初次成功率', named['description'])
        words = self.render(detail=named)
        self.assertTrue(any('常规预算是消费舒适度' in word for word in words))

    def test_sale_details_keep_hard_public_counter_ceiling_and_hidden_initial_odds(self):
        for size in SIZES:
            for page in (0, 1):
                words = self.render(size=size, detail=self.detail(page))
                self.assertIn('还价仍须≤参考价125%及常规预算区间上限', words)
                self.assertIn('常规预算是消费舒适度，超出后初次成功率逐步降低\n还价资格非成交保证；初次精确成功率不公开', words)
                self.assertIn('01 仍可奇迹成交（1%）· 100 直接离店（1%）', words)
                self.assertFalse(any('买得起' in word or '低骰成功：' in word for word in words))
                self.assertTrue(all(action[0] in ('close', 'sale_page') for _, action in self.renderer.hits))
            self.assertIn('不符：类别不合顾客偏好', words)
            self.assertIn('普通失败直接离开', words)

    def test_walkin_detail_explains_soft_initial_budget_and_daily_cap(self):
        detail = dict(_view='walkins', walkins=self.observation['walkins'])
        for size in SIZES:
            words = self.render(size=size, detail=detail)
            self.assertIn('散客剩余 1/1 次 · 常规预算 60–120', words)
            self.assertIn('常规预算是消费舒适度，超出会逐步降低初次成功率；精确预算隐藏，01仍可奇迹成交。', words)
            self.assertIn('今日已用 0 次 · 次日重置', words)
            self.assertTrue(any('改价/换货/重启不刷新' in word for word in words))
        self.assertEqual(self.renderer.hits, [((0, 0, self.renderer.W, self.renderer.H), ('close', None))])

    def test_v9_honors_all_historical_quote_origins_without_changing_final_preview(self):
        for origin in (3, 4, 5, 6):
            self.observation = pending_fixture(origin)
            original = copy.deepcopy(self.observation)
            expected = f'v9 继续履行 v{origin} 已承诺还价'
            self.assertEqual(honored_quote_label(self.observation['negotiation']), expected)
            for size in SIZES:
                words = self.render(size=size)
                self.assertIn(expected, words)
                detail = next(action[1] for _, action in self.renderer.hits
                              if action[0] == 'inspect' and action[1].get('_view') == 'negotiation')
                words = self.render(size=size, detail=detail)
                caption = expected + (' · 原D20加值×5' if origin in (3, 4) else '')
                self.assertIn(caption, words)
                self.assertIn('低骰成功：01–58 · 成功率 58%', words)
                self.assertIn('失败收入 0 · 失去 150 星币还价', words)
            self.assertEqual(self.observation, original)

    def test_native_v9_quote_and_old_v6_quote_are_labeled_honestly(self):
        for rules, origin, expected in ((9, 9, None), (9, 8, None), (9, 7, None),
                                        (6, 6, None), (6, 5, 'v6 继续履行 v5 已承诺还价')):
            self.assertEqual(honored_quote_label(dict(rules_version=rules, origin_rules_version=origin)), expected)
        self.observation = pending_fixture(9)
        self.assertFalse(any('继续履行' in word for word in self.render()))

    def test_imported_quote_with_no_integer_final_price_remains_actionable(self):
        self.observation = pending_fixture(6)
        self.observation['negotiation'].update(preview=None, final_offer_bounds={'available': False})
        words = self.render()
        self.assertIn('没有合法的最终报价', words)
        self.assertIn('可以接受还价，或免费谢绝', words)
        self.assertIn('v9 继续履行 v6 已承诺还价', words)

    def test_current_projection_never_reads_or_fabricates_initial_economics(self):
        item = self.observation['inventory'][0]
        item.update(budget='SECRET', reference='SECRET', initial_probability='SECRET')
        self.observation['walkins'].update(budget='SECRET', rng='SECRET')
        for option in item['sale_options']:
            option.update(exact_budget='SECRET', private_reference='SECRET', threshold=58,
                          initial_probability=.58, budget_factor='SECRET')
        detail = self.detail()
        self.assertNotIn('SECRET', json.dumps(detail))
        self.assertNotIn('initial_probability', json.dumps(detail))
        words = self.render(detail=detail)
        self.assertNotIn('SECRET', str(words))
        self.assertFalse(any('成功率 58%' in word or '低骰成功：' in word for word in words))
        self.observation = pending_fixture(6)
        self.observation['negotiation'].update(exact_budget='SECRET', rng='SECRET')
        self.assertNotIn('SECRET', json.dumps(public_negotiation(self.observation['negotiation'])))

    def test_older_public_observation_does_not_claim_new_budget_semantics(self):
        self.observation = customer_fixture()
        for version in (6, 8):
            self.observation['version'] = version
            words = self.render(detail=self.detail())
            self.assertIn('公开预算 60–120 星币', words)
            self.assertIn('须同时不高于参考价的125%及公开预算上限', words)
            self.assertFalse(any('消费舒适度' in word for word in words))

    def test_refresh_and_paging_remain_read_only(self):
        viewer = Spectator.__new__(Spectator)
        viewer.reader = SimpleNamespace(observation=self.observation)
        viewer.renderer = self.renderer
        viewer.detail = self.detail(1)
        viewer.last_signature = 'old'
        self.observation['walkins'].update(used=1, remaining=0)
        before = copy.deepcopy(self.observation)
        viewer.refresh_detail()
        words = self.render(detail=viewer.detail)
        self.assertIn('散客剩余 0/1 次 · 常规预算 60–120', words)
        self.assertEqual(viewer.detail['_sale_page'], 1)
        self.assertEqual(self.observation, before)

    def test_only_temporary_public_input_is_read_and_never_written(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic.observation.json'
            path.write_text(json.dumps(self.observation, ensure_ascii=False))
            before = path.read_bytes()
            original_read = Path.read_text
            calls = []
            def checked_read(source, *args, **kwargs):
                self.assertEqual(source, path)
                calls.append(source)
                return original_read(source, *args, **kwargs)
            with mock.patch.object(Path, 'read_text', checked_read), mock.patch.object(Path, 'write_text', side_effect=AssertionError('viewer write')):
                reader = ObservationReader(path)
                self.assertTrue(reader.poll())
                self.renderer.render(reader.observation, (390, 844))
                self.assertFalse(reader.poll())
            self.assertEqual(calls, [path])
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(Path(directory).iterdir()), [path])


if __name__ == '__main__':
    unittest.main()
