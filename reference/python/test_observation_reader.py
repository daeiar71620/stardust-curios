"""Deterministic public-file cache regressions; no live inputs or Tk window."""
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from spectator import ObservationReader, Spectator
from test_spectator import fixture


class ObservationCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'synthetic.observation.json'
        self.original = json.dumps(fixture()).encode('utf-8')
        self.path.write_bytes(self.original)

    def rewrite_preserving_metadata(self, contents, *, replace=False):
        previous = self.path.stat()
        self.assertEqual(len(contents), previous.st_size)
        target = self.path.with_name('replacement.observation.json') if replace else self.path
        target.write_bytes(contents)
        os.utime(target, ns=(previous.st_atime_ns, previous.st_mtime_ns))
        if replace:
            os.replace(target, self.path)
        self.assertEqual(self.path.stat().st_mtime_ns, previous.st_mtime_ns)
        self.assertEqual(self.path.stat().st_size, previous.st_size)

    def test_valid_same_size_same_mtime_changes_are_accepted(self):
        for replace in (False, True):
            with self.subTest(atomic_replace=replace):
                self.path.write_bytes(self.original)
                reader = ObservationReader(self.path)
                self.assertTrue(reader.poll())
                old_stamp = reader.stamp
                changed = self.original.replace(b'"credits": 780', b'"credits": 781')
                self.assertNotEqual(changed, self.original)
                self.rewrite_preserving_metadata(changed, replace=replace)
                self.assertTrue(reader.poll())
                self.assertEqual(reader.observation['credits'], 781)
                self.assertNotEqual(reader.stamp, old_stamp)
                self.assertFalse(reader.poll())

    def test_unsupported_same_metadata_clears_snapshot_and_exact_bytes_recover(self):
        for replace in (False, True):
            with self.subTest(atomic_replace=replace):
                self.path.write_bytes(self.original)
                reader = ObservationReader(self.path)
                self.assertTrue(reader.poll())
                stamp = reader.stamp
                invalid = self.original.replace(b'"version": 9', b'"version": 8')
                self.assertNotEqual(invalid, self.original)
                self.rewrite_preserving_metadata(invalid, replace=replace)
                self.assertFalse(reader.poll())
                self.assertIsNone(reader.observation)
                self.assertIsNone(reader.stamp)
                self.assertIsNone(reader.updated_at)
                self.assertIn('仅支持 v9', reader.error)
                self.rewrite_preserving_metadata(self.original, replace=replace)
                self.assertTrue(reader.poll())
                self.assertEqual(reader.observation['version'], 9)
                self.assertNotEqual(reader.stamp, stamp)
                self.assertIsNone(reader.error)

    def test_unchanged_bytes_are_read_bounded_but_parsed_once(self):
        reader = ObservationReader(self.path)
        real_open = Path.open
        read_sizes = []

        class RecordedFile(io.BytesIO):
            def read(self, size=-1):
                read_sizes.append(size)
                return super().read(size)

        def read_only(path, mode):
            self.assertEqual(path, self.path)
            self.assertEqual(mode, 'rb')
            with real_open(path, mode) as source:
                return RecordedFile(source.read())

        with patch.object(Path, 'open', read_only), patch('spectator.json.loads', wraps=json.loads) as parse:
            self.assertTrue(reader.poll())
            old = (reader.observation, reader.stamp, reader.updated_at)
            for _ in range(3):
                self.assertFalse(reader.poll())
            self.assertEqual(parse.call_count, 1)
        self.assertEqual(read_sizes, [4 * 1024 * 1024 + 1] * 4)
        self.assertIs(reader.observation, old[0])
        self.assertEqual((reader.stamp, reader.updated_at), old[1:])

    def test_transient_failure_preserves_last_good_and_identical_recovery(self):
        for failure in ('partial_json', 'missing', 'permission'):
            with self.subTest(failure=failure):
                self.path.write_bytes(self.original)
                reader = ObservationReader(self.path)
                self.assertTrue(reader.poll())
                old = (reader.observation, reader.stamp, reader.updated_at)
                if failure == 'permission':
                    with patch.object(Path, 'open', side_effect=PermissionError('synthetic denial')):
                        self.assertFalse(reader.poll())
                else:
                    if failure == 'missing':
                        self.path.unlink()
                    else:
                        self.rewrite_preserving_metadata(b'{' + b' ' * (len(self.original) - 1))
                    self.assertFalse(reader.poll())
                self.assertIs(reader.observation, old[0])
                self.assertIsNotNone(reader.error)
                self.path.write_bytes(self.original)
                self.assertFalse(reader.poll())
                self.assertIsNone(reader.error)
                self.assertIs(reader.observation, old[0])
                self.assertEqual((reader.stamp, reader.updated_at), old[1:])

    def test_utf16_is_not_silently_accepted(self):
        self.path.write_bytes(self.original.decode('utf-8').encode('utf-16'))
        reader = ObservationReader(self.path)
        self.assertFalse(reader.poll())
        self.assertIsNone(reader.observation)
        self.assertIsNotNone(reader.error)

    def test_size_limit_is_enforced_on_read_bytes_before_parsing(self):
        reader = ObservationReader(self.path)
        limit = 4 * 1024 * 1024
        self.path.write_bytes(self.original + b' ' * (limit - len(self.original)))
        self.assertTrue(reader.poll())
        old = reader.observation
        with self.path.open('ab') as source:
            source.write(b' ')
        with patch('spectator.json.loads', side_effect=AssertionError('oversize parsed')):
            self.assertFalse(reader.poll())
        self.assertIs(reader.observation, old)
        self.assertIsNotNone(reader.error)

    def test_tick_redraws_valid_same_metadata_update(self):
        viewer = Spectator.__new__(Spectator)
        viewer.reader = ObservationReader(self.path)
        viewer.canvas = Mock()
        viewer.canvas.winfo_width.return_value = 390
        viewer.canvas.winfo_height.return_value = 844
        viewer.renderer = Mock()
        viewer.root = Mock()
        viewer.ImageTk = SimpleNamespace(PhotoImage=Mock())
        viewer.canvas_image = 1
        viewer.tab, viewer.page, viewer.detail = 'shelf', 0, None
        viewer.journal_mode, viewer.demo = 'events', False
        viewer.last_signature = None
        viewer.refresh_detail = Mock()
        viewer.tick()
        first_signature = viewer.last_signature
        changed = self.original.replace(b'"credits": 780', b'"credits": 781')
        self.rewrite_preserving_metadata(changed)
        viewer.tick()
        self.assertEqual(viewer.renderer.render.call_count, 2)
        self.assertEqual(viewer.renderer.render.call_args.args[0]['credits'], 781)
        self.assertNotEqual(viewer.last_signature, first_signature)
        viewer.tick()
        self.assertEqual(viewer.renderer.render.call_count, 2)


if __name__ == '__main__':
    unittest.main()
