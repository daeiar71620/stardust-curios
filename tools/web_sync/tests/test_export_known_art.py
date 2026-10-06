"""Incremental public artwork tests: synthetic observations only, no network."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import export_known_art as exporter


class IncrementalArt(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.public = self.root / 'synthetic.observation.json'
        self.source = self.root / 'spectator.py'
        self.source.write_text('# synthetic public renderer v1\n')
        self.output = self.root / 'art'
        self.renders = []
        owner = self

        class Reader:
            error = None
            def __init__(self, path):
                self.path = path
            def poll(self):
                self.observation = json.loads(self.path.read_text())
                return True

        class Renderer:
            def item_art(self, x, y, size, item):
                owner.renders.append(item['art_id'])
                self.draw.rectangle((10, 10, size-10, size-10), fill=item.get('color', '#80d8c5'))

        self.renderer = SimpleNamespace(
            ITEM_ART_IDS={'one', 'two'}, ITEM_ART_NAMES={'One': 'one', 'Two': 'two'},
            ObservationReader=Reader, Renderer=Renderer,
            public_catalog_entry=lambda row: row if row.get('discovered') is True else {'discovered': False},
            BG='#101c29', INK='#f6edda', MUTED='#aec1bb',
            font=lambda size: ImageFont.load_default(size=size))
        self.patch = patch.object(exporter, 'load_renderer', return_value=self.renderer)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.observation = {'credits': 260, 'revision': 1, 'day': 1,
                            'inventory': [], 'collection': [],
                            'codex': {'entries': [self.item('one')]}}
        self.write()

    def item(self, identity):
        return {'art_id': identity, 'name': identity.title(), 'kind': 'tool',
                'rarity': 'common', 'discovered': True, 'slot': 1 if identity == 'one' else 2}

    def write(self):
        self.public.write_text(json.dumps(self.observation))

    def export(self, **kwargs):
        return exporter.export(self.public, self.source, self.output, **kwargs)

    def test_unchanged_art_and_preview_are_not_rewritten(self):
        first = self.export()
        stamps = {p.name: p.stat().st_mtime_ns for p in self.output.iterdir()}
        self.observation['revision'] += 1
        self.write()
        second = self.export()
        self.assertEqual(self.renders, ['one'])
        self.assertEqual(first['items'], second['items'])
        for name in ('one.png', 'known-art-preview.png'):
            self.assertEqual((self.output/name).stat().st_mtime_ns, stamps[name])
        self.assertEqual(second['observation_revision'], 2)

    def test_new_discovery_renders_only_new_art(self):
        self.export(preview=False)
        self.observation['codex']['entries'].append(self.item('two'))
        self.write()
        result = self.export(preview=False)
        self.assertEqual(self.renders, ['one', 'two'])
        self.assertEqual(set(result['art']), {'one', 'two'})
        self.assertFalse((self.output/'known-art-preview.png').exists())

    def test_preview_refreshes_after_no_preview_manifest_update(self):
        self.export()
        preview = self.output/'known-art-preview.png'
        before = preview.read_bytes()
        self.observation['codex']['entries'].append(self.item('two'))
        self.write()
        self.export(preview=False)
        self.assertEqual(preview.read_bytes(), before)
        result = self.export()
        self.assertNotEqual(preview.read_bytes(), before)
        self.assertEqual(self.renders, ['one', 'two'])
        self.assertIsInstance(result['preview_key'], str)

    def test_changed_public_paint_invalidates_only_affected_art(self):
        self.observation['codex']['entries'].append(self.item('two'))
        self.write()
        self.export(preview=False)
        self.observation['inventory'] = [dict(self.item('one'), color='#ff0000')]
        self.write()
        self.export(preview=False)
        self.assertEqual(self.renders, ['one', 'two', 'one'])

    def test_source_or_size_change_invalidates_cache(self):
        self.export(preview=False)
        self.source.write_text('# synthetic public renderer v2\n')
        self.export(preview=False)
        self.export(size=256, preview=False)
        self.assertEqual(self.renders, ['one', 'one', 'one'])

    def test_missing_corrupt_or_hash_mismatched_art_is_rebuilt(self):
        self.export(preview=False)
        path = self.output/'one.png'
        path.unlink()
        self.export(preview=False)
        path.write_bytes(b'not a PNG')
        self.export(preview=False)
        manifest = self.output/'manifest.json'
        value = json.loads(manifest.read_text())
        value['items'][0]['sha256'] = '0'*64
        manifest.write_text(json.dumps(value))
        result = self.export(preview=False)
        self.assertEqual(self.renders, ['one']*4)
        self.assertEqual(result['items'][0]['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())

    def test_unknown_entries_remain_unknown(self):
        self.observation['codex']['entries'].append(dict(self.item('two'), discovered=False))
        self.write()
        result = self.export(preview=False)
        self.assertEqual(set(result['art']), {'one'})
        self.assertFalse((self.output/'two.png').exists())

    def test_legacy_manifest_rebuilds_once(self):
        self.export(preview=False)
        manifest = self.output/'manifest.json'
        value = json.loads(manifest.read_text())
        value['schema_version'] = 1
        value['items'][0].pop('render_key')
        manifest.write_text(json.dumps(value))
        self.export(preview=False)
        self.export(preview=False)
        self.assertEqual(self.renders, ['one', 'one'])

    def test_stale_art_is_rejected_without_removing_it(self):
        self.export(preview=False)
        stale = self.output/'unknown.png'
        stale.write_bytes(b'untouched')
        with self.assertRaises(ValueError):
            self.export(preview=False)
        self.assertEqual(stale.read_bytes(), b'untouched')

    def test_cached_symlink_and_hardlink_are_rejected(self):
        self.export(preview=False)
        art = self.output/'one.png'
        external = self.root/'external.png'
        art.rename(external)
        art.symlink_to(external)
        with self.assertRaises(ValueError):
            self.export(preview=False)
        art.unlink()
        os.link(external, art)
        with self.assertRaises(ValueError):
            self.export(preview=False)

    def test_manifest_symlink_is_rejected(self):
        self.output.mkdir()
        external = self.root/'external.json'
        external.write_text('{}')
        (self.output/'manifest.json').symlink_to(external)
        with self.assertRaises(ValueError):
            self.export(preview=False)
        self.assertEqual(external.read_text(), '{}')

    def test_empty_known_set_needs_no_image_or_preview(self):
        self.observation['codex']['entries'] = []
        self.write()
        result = self.export()
        self.assertEqual(result['art'], {})
        self.assertEqual(self.renders, [])
        self.assertFalse((self.output/'known-art-preview.png').exists())

    def test_fast_path_checks_source_renderer_and_png_content(self):
        self.export(preview=False)
        ready = lambda: exporter.cache_ready(self.observation, self.source, self.output)
        self.assertTrue(ready())
        self.observation['revision'] += 1
        self.observation['credits'] += 10
        self.assertTrue(ready())
        self.observation['inventory'] = [dict(self.item('one'), color='#ff0000')]
        self.assertFalse(ready())
        self.write()
        self.export(preview=False)
        self.assertTrue(ready())
        self.source.write_text('# changed renderer\n')
        self.assertFalse(ready())
        self.export(preview=False)
        self.assertTrue(ready())
        (self.output/'one.png').write_bytes(b'corrupted')
        self.assertFalse(ready())

    def test_fast_path_cannot_infer_art_from_unknown_rows(self):
        self.export(preview=False)
        self.observation['codex']['entries'].append(dict(self.item('two'), discovered=False))
        self.assertTrue(exporter.cache_ready(self.observation, self.source, self.output))
        self.observation['codex']['entries'][-1]['discovered'] = True
        self.assertFalse(exporter.cache_ready(self.observation, self.source, self.output))

    def test_duplicate_public_possessions_do_not_invalidate_equal_paint(self):
        self.observation['inventory'] = [self.item('one')]
        self.write()
        self.export(preview=False)
        self.observation['inventory'].append(dict(self.item('one'), id='I002', price=90))
        self.assertTrue(exporter.cache_ready(self.observation, self.source, self.output))
        self.observation['collection'] = [self.observation['inventory'].pop()]
        self.assertTrue(exporter.cache_ready(self.observation, self.source, self.output))
        self.observation['collection'][0]['color'] = '#ff0000'
        self.assertFalse(exporter.cache_ready(self.observation, self.source, self.output))


if __name__ == '__main__':
    unittest.main()
