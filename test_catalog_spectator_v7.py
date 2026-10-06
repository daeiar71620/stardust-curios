"""Discovery-safe catalog and identity-specific artwork regressions.

All scenes are synthetic and in memory. No player files or persistent demos.
"""
import copy
import hashlib
import json
from types import SimpleNamespace
import unittest

from PIL import Image, ImageDraw

import engine
from spectator import (BG, Renderer, Spectator, TABS, public_catalog_entry,
                       public_sale_detail)


def public_row(row, *, found=True, slot=1):
    return dict(slot=slot, art_id=row[0], name=row[1], rarity=row[2],
                kind=row[3], description=row[5], discovered=found, collected=False)


def old_projection():
    """An old engine exposed every catalog identity, including unseen items."""
    observation = engine.observation(engine.new_state(seed=409))
    observation['codex']['entries'] = [public_row(row, found=False, slot=slot)
                                       for slot, row in enumerate(engine.CATALOG, 1)]
    return observation


def art_image(item, size=128):
    renderer = Renderer()
    renderer.image = Image.new('RGB', (size, size), BG)
    renderer.draw = ImageDraw.Draw(renderer.image)
    renderer.item_art(0, 0, size, item)
    return renderer.image


class CatalogPrivacyRendererTests(unittest.TestCase):
    def test_unknown_projection_is_an_exact_allowlist(self):
        for slot, row in enumerate(engine.CATALOG, 1):
            source = dict(public_row(row, found=False, slot=slot),
                          color='#ff0000', silhouette='secret', requirements=['secret'])
            self.assertEqual(public_catalog_entry(source),
                             {'slot': slot, 'discovered': False, 'collected': False})

    def test_discovery_requires_explicit_true_not_truthy_or_collection(self):
        for flag in [False, None, 0, 1, 'true', [], {}]:
            source = dict(public_row(engine.CATALOG[0]), discovered=flag, collected=True)
            self.assertNotIn('name', public_catalog_entry(source))
            self.assertFalse(public_catalog_entry(source)['collected'])

    def test_old_catalog_never_leaks_in_any_tab_or_page(self):
        observation = old_projection()
        before = copy.deepcopy(observation)
        renderer = Renderer()
        forbidden = [value for row in engine.CATALOG for value in (row[1], row[5])]
        for tab, _ in TABS:
            renderer.render(observation, (1320, 940), tab)
            for page in range(renderer.page_count):
                renderer.render(observation, (1320, 940), tab, page)
                surface = '\n'.join(renderer.words) + json.dumps(renderer.hits, ensure_ascii=False)
                for identity in forbidden:
                    self.assertNotIn(identity, surface, (tab, page))
        self.assertEqual(observation, before)

    def test_unknown_card_and_direct_detail_are_safe_at_all_sizes(self):
        observation = old_projection()
        leaked = observation['codex']['entries'][8]
        for size in [(1320, 940), (760, 1240), (390, 844), (320, 568)]:
            renderer = Renderer()
            renderer.render(observation, size, 'collection')
            self.assertIn('???', renderer.words)
            action = next(action for _, action in renderer.hits
                          if action[0] == 'inspect' and action[1].get('_view') == 'codex')
            self.assertEqual(set(action[1]), {'slot', 'discovered', 'collected', '_view'})
            for detail in [action[1], leaked, dict(leaked, _view='sale')]:
                renderer.render(observation, size, 'collection', detail=detail)
                self.assertIn('???', renderer.words)
                self.assertNotIn(leaked['name'], renderer.words)
                self.assertNotIn(leaked['description'], renderer.words)
                self.assertEqual(renderer.hits, [((0, 0, renderer.W, renderer.H), ('close', None))])

    def test_discovered_entries_show_name_story_and_separate_collection(self):
        observation = old_projection()
        observation['codex']['entries'][8]['discovered'] = True
        observation['codex']['entries'][20].update(discovered=True, collected=True)
        renderer = Renderer()
        renderer.render(observation, (1320, 940), 'collection')
        self.assertIn('迷路送信蜂', renderer.words)
        self.assertIn('发条守夜猫', renderer.words)
        self.assertIn('已发现', renderer.words)
        self.assertIn('已珍藏', renderer.words)
        actions = [a[1] for _, a in renderer.hits if a[0] == 'inspect' and a[1].get('_view') == 'codex']
        self.assertEqual(actions[0]['art_id'], 'cat')
        self.assertEqual(actions[1]['art_id'], 'bee')

    def test_detail_refresh_follows_public_slot_and_redacts_or_closes(self):
        observation = old_projection()
        viewer = Spectator.__new__(Spectator)
        viewer.reader = SimpleNamespace(observation=observation)
        viewer.detail = dict(observation['codex']['entries'][8], discovered=True, _view='codex')
        viewer.refresh_detail()
        self.assertEqual(viewer.detail, {'slot': 9, 'discovered': False, 'collected': False, '_view': 'codex'})
        observation['codex']['entries'][8]['discovered'] = True
        viewer.refresh_detail()
        self.assertEqual(viewer.detail['name'], '迷路送信蜂')
        observation['codex']['entries'] = []
        viewer.refresh_detail()
        self.assertIsNone(viewer.detail)

    def test_old_catalog_without_explicit_slots_refreshes(self):
        observation = old_projection()
        for row in observation['codex']['entries']:
            row.pop('slot')
        viewer = Spectator.__new__(Spectator)
        viewer.reader = SimpleNamespace(observation=observation)
        viewer.detail = dict(slot=21, discovered=True, name='发条守夜猫', _view='codex')
        viewer.refresh_detail()
        self.assertEqual(viewer.detail, {'slot': 21, 'discovered': False, 'collected': False, '_view': 'codex'})

    def test_sale_detail_preserves_public_illustration_identity(self):
        item = public_row(engine.CATALOG_BY_ID['bee'])
        detail = public_sale_detail(item, {})
        self.assertEqual(detail['art_id'], 'bee')
        self.assertEqual(art_image(item).tobytes(), art_image(detail).tobytes())


class DistinctItemArtworkTests(unittest.TestCase):
    def test_all_twenty_four_items_have_unique_color_and_silhouette(self):
        colored = []
        silhouettes = []
        for row in engine.CATALOG:
            image = art_image(dict(public_row(row), color='#bbbbbb'))
            colored.append(hashlib.sha256(image.tobytes()).hexdigest())
            raw = image.tobytes()
            mask = bytes(raw[i:i+3] != bytes((16, 28, 41)) for i in range(0, len(raw), 3))
            silhouettes.append(hashlib.sha256(mask).hexdigest())
        self.assertEqual(len(set(colored)), 24)
        self.assertEqual(len(set(silhouettes)), 24)

    def test_old_public_name_fallback_matches_explicit_art_identity(self):
        for row in engine.CATALOG:
            item = public_row(row)
            old = dict(item)
            old.pop('art_id')
            self.assertEqual(art_image(item).tobytes(), art_image(old).tobytes(), row[0])

    def test_unknown_art_is_identical_across_all_identities_and_rarities(self):
        signatures = set()
        for slot, row in enumerate(engine.CATALOG, 1):
            item = dict(public_row(row, found=False, slot=slot), color=engine.COLORS[row[2]])
            signatures.add(art_image(item).tobytes())
        signatures.add(art_image({'discovered': False}).tobytes())
        self.assertEqual(len(signatures), 1)

    def test_bee_cat_and_whale_are_distinct_at_small_and_large_sizes(self):
        for size in (42, 61, 128):
            signatures = {art_image(public_row(engine.CATALOG_BY_ID[key]), size).tobytes()
                          for key in ('bee', 'cat', 'whale')}
            self.assertEqual(len(signatures), 3)


if __name__ == '__main__':
    unittest.main()
