#!/usr/bin/env python3
"""Verify private art integrity, distinctness, transparency and reproducibility."""
from __future__ import annotations

import argparse
from io import BytesIO
import json
from pathlib import Path
import sys
import unittest

from PIL import Image

from generate_private_art import EXPECTED_COUNT, load_public_drawing_code, load_public_paint_catalog, render_png, sha256


class PrivateArtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((cls.art_dir / 'manifest.json').read_text(encoding='utf-8'))
        cls.renderer, cls.renderer_hash = load_public_drawing_code(cls.renderer_path)
        cls.paint, cls.colors, cls.paint_hash = load_public_paint_catalog(cls.catalog_path)

    def test_exactly_24_private_assets_and_no_preview_payload(self):
        manifest = self.manifest
        self.assertEqual(manifest['visibility'], 'server-private')
        self.assertEqual(manifest['source'], 'synthetic-public-renderer-items')
        self.assertEqual(manifest['item_count'], EXPECTED_COUNT)
        self.assertEqual(manifest['paint_policy'], 'canonical-public-rarity-colors')
        self.assertEqual(manifest['public_paint_sha256'], self.paint_hash)
        self.assertEqual(manifest['rarity_colors'], self.colors)
        rows = manifest['items']
        self.assertEqual(len(rows), EXPECTED_COUNT)
        self.assertEqual({row['art_id'] for row in rows}, self.renderer.ITEM_ART_IDS)
        self.assertEqual(manifest['art'], {row['art_id']: row['filename'] for row in rows})
        expected_files = {'manifest.json', *(row['filename'] for row in rows)}
        actual_files = {str(path.relative_to(self.art_dir)) for path in self.art_dir.rglob('*') if path.is_file()}
        self.assertEqual(actual_files, expected_files)
        self.assertNotIn('preview', json.dumps(manifest).lower())
        self.assertNotIn('contact', json.dumps(manifest).lower())

    def test_hashes_sizes_and_safe_filenames(self):
        total = 0
        for row in self.manifest['items']:
            with self.subTest(art_id=row['art_id']):
                self.assertEqual(row['filename'], f"png/{row['art_id']}.png")
                self.assertEqual(row['rarity'], self.paint[row['art_id']]['rarity'])
                self.assertEqual(row['paint_color'], self.colors[row['rarity']])
                data = (self.art_dir / row['filename']).read_bytes()
                self.assertEqual(row['sha256'], sha256(data))
                self.assertEqual(row['bytes'], len(data))
                self.assertLess(len(data), 90_000, 'A phone card should remain lightweight')
                total += len(data)
        self.assertEqual(total, self.manifest['total_png_bytes'])

    def test_images_are_transparent_nonblank_and_distinct(self):
        pixel_hashes, file_hashes = set(), set()
        size = self.manifest['width']
        for row in self.manifest['items']:
            with self.subTest(art_id=row['art_id']):
                data = (self.art_dir / row['filename']).read_bytes()
                with Image.open(BytesIO(data)) as image:
                    self.assertEqual(image.format, 'PNG')
                    self.assertEqual(image.mode, 'RGBA')
                    self.assertEqual(image.size, (size, size))
                    self.assertEqual(image.info, {}, 'PNG must not carry unrelated metadata')
                    alpha = image.getchannel('A')
                    self.assertEqual(alpha.getextrema(), (0, 255))
                    visible = sum(alpha.histogram()[1:])
                    self.assertGreater(visible, size * size * .10)
                    self.assertLess(visible, size * size * .90)
                    bounds = alpha.getbbox()
                    self.assertGreater(bounds[2] - bounds[0], size * .50)
                    self.assertGreater(bounds[3] - bounds[1], size * .50)
                    self.assertGreater(len(image.getcolors(size * size)), 50)
                    pixel_hashes.add(sha256(image.tobytes()))
                    file_hashes.add(sha256(data))
        self.assertEqual(len(pixel_hashes), EXPECTED_COUNT)
        self.assertEqual(len(file_hashes), EXPECTED_COUNT)

    def test_repeated_render_has_identical_content_hashes(self):
        self.assertEqual(self.manifest['renderer_sha256'], self.renderer_hash)
        for row in self.manifest['items']:
            with self.subTest(art_id=row['art_id']):
                actual = render_png(self.renderer, row['art_id'], self.manifest['width'], paint=self.paint)
                self.assertEqual(row['sha256'], sha256(actual))

    def test_only_drawing_interface_is_loaded(self):
        self.assertFalse(hasattr(self.renderer, 'ObservationReader'))
        self.assertFalse(hasattr(self.renderer, 'App'))
        self.assertFalse(hasattr(self.renderer, 'main'))
        self.assertFalse(hasattr(self.renderer.Renderer, 'render'))
        self.assertFalse(hasattr(self.renderer.Renderer, 'shop_scene'))
        self.assertFalse(hasattr(self.renderer.Renderer, 'codex'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--renderer', required=True, type=Path)
    parser.add_argument('--catalog', required=True, type=Path)
    parser.add_argument('--art-dir', required=True, type=Path)
    args = parser.parse_args()
    PrivateArtTests.renderer_path = args.renderer
    PrivateArtTests.catalog_path = args.catalog
    PrivateArtTests.art_dir = args.art_dir
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PrivateArtTests))
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    main()
