"""Real v9 CLI + publisher tests; all state is temporary and HTTP is mocked."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from action_publish import Controller, HttpProblem, Stop, main, request_bytes

ROOT = Path(__file__).resolve().parents[3]


class RealV9CliIntegration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.save = self.folder / 'synthetic-game.json'
        self.public = self.save.with_suffix('.observation.json')
        created = subprocess.run(
            [sys.executable, str(ROOT / 'engine.py'), '--save', str(self.save), 'new'],
            cwd=ROOT, capture_output=True, timeout=20, check=False)
        self.assertEqual(created.returncode, 0, created.stderr.decode())
        self.config = {
            'site_id': 'synthetic-project',
            'site_url': 'https://synthetic-test.chatgpt.site',
            'owner_private_verified': True,
            'session_id': 'synthetic-session', 'session_epoch': 1,
            'observation_version': 9,
            'engine_path': str(ROOT / 'engine.py'), 'save_path': str(self.save),
            'observation_path': str(self.public),
            'outbox_dir': str(self.folder / 'outbox'),
            'art_dir': str(self.folder / 'known-art'),
            'renderer_path': str(ROOT / 'spectator.py'),
        }
        self.posts = []
        self.fail = False

    def transport(self, url, token, payload):
        self.assertEqual(url, self.config['site_url'] + '/api/ingest')
        self.assertEqual(token, 'synthetic-memory-only')
        self.posts.append(payload)
        if self.fail:
            raise HttpProblem(503)
        return {'ok': True, 'session_id': payload['session_id'],
                'session_epoch': payload['session_epoch'],
                'revision': payload['observation']['revision'],
                'digest': 'a' * 64,
                'request_sha256': hashlib.sha256(request_bytes(payload)).hexdigest(),
                'published_at': 'synthetic-time'}

    def controller(self):
        # Keep the production runner and renderer: only HTTP and retry delays differ.
        return Controller(self.config, 'synthetic-memory-only',
                          transport=self.transport, sleeper=lambda seconds: None)

    def observation(self):
        return json.loads(self.public.read_text())

    def test_real_buy_open_art_and_failed_publication_recovery(self):
        initial = self.observation()['revision']
        first = self.controller().execute({'operation_id': 'buy-one', 'action': ['buy', 'salvage']})
        self.assertTrue(first['engine_executed'])
        self.assertEqual(first['revision'], initial + 1)
        after_buy = self.save.read_bytes()
        repeated = self.controller().execute({'operation_id': 'buy-one', 'action': ['buy', 'salvage']})
        self.assertFalse(repeated['engine_executed'])
        self.assertEqual(self.save.read_bytes(), after_buy)
        crate = self.observation()['crates'][0]['id']
        self.fail = True
        with self.assertRaises(Stop) as error:
            self.controller().execute({'operation_id': 'open-one', 'action': ['open', crate]})
        self.assertEqual(error.exception.code, 'publication_retry_exhausted')
        self.assertEqual(self.observation()['revision'], initial + 2)
        after_open = self.save.read_bytes()
        self.fail = False
        recovered = self.controller().execute({'operation_id': 'open-one', 'action': ['open', crate]})
        self.assertTrue(recovered['ok'])
        self.assertFalse(recovered['engine_executed'])
        self.assertEqual(recovered['verification'], 'server_commit_ack')
        self.assertEqual(self.save.read_bytes(), after_open)
        self.assertEqual(len(self.posts[-1]['artwork']), 1)
        self.assertEqual(self.posts[-1]['observation']['version'], 9)
        for entry in self.posts[-1]['observation']['codex']['entries']:
            if not entry['discovered']:
                self.assertEqual(set(entry), {'slot', 'discovered', 'collected'})
        payload = json.dumps(self.posts[-1])
        for forbidden in ('rng_state', 'rng_seed', 'actual_base', 'synthetic-memory-only', str(self.save)):
            self.assertNotIn(forbidden, payload)
        self.controller().execute({'mode': 'sync'})
        self.assertEqual(self.posts[-1]['artwork'], {})
        self.assertEqual(self.save.read_bytes(), after_open)

    def test_documented_entrypoint_uses_real_cli_and_mock_http(self):
        config_path = self.folder / 'config.local.json'
        config_path.write_text(json.dumps(self.config))
        request = {'access': {'project_id': self.config['site_id'],
                              'token': 'synthetic-memory-only'},
                   'operation_id': 'entry-buy', 'action': ['buy', 'salvage']}
        testcase = self

        class FakeOpener:
            def open(self, request, timeout):
                body = json.loads(request.data)
                ack = testcase.transport(request.full_url, 'synthetic-memory-only', body)
                testcase.assertEqual(ack['request_sha256'], hashlib.sha256(request.data).hexdigest())
                response = io.BytesIO(json.dumps(ack).encode())
                response.status = 200
                return response

        output = io.StringIO()
        before = self.observation()['revision']
        with patch('sys.argv', ['action_publish.py', '--config', str(config_path)]), \
             patch('sys.stdin', io.StringIO(json.dumps(request) + '\n')), \
             patch('action_publish.urllib.request.build_opener', return_value=FakeOpener()), \
             contextlib.redirect_stdout(output):
            code = main()
        self.assertEqual(code, 0, output.getvalue())
        result = json.loads(output.getvalue().splitlines()[-1])
        self.assertTrue(result['engine_executed'])
        self.assertEqual(result['verification'], 'server_commit_ack')
        self.assertEqual(self.observation()['revision'], before + 1)
        self.assertNotIn('synthetic-memory-only', output.getvalue())
        for path in (self.folder / 'outbox').rglob('*'):
            if path.is_file():
                self.assertNotIn('synthetic-memory-only', path.read_text())


if __name__ == '__main__':
    unittest.main()
