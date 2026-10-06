"""Independent recovery regressions; synthetic fixtures and fake HTTP only."""
import io
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from diagnostics import Diagnostics
from shop import preflight_scope
import test_shop


class DiagnosticRecoveryReview(unittest.TestCase):
    def setUp(self):
        self.fixture = test_shop.Tests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)

    def test_early_switch_recovery_keeps_recorded_target_on_same_destination(self):
        fixture = self.fixture
        fixture.switch()
        fixture.prepare('second')
        interrupted = fixture.shop()
        original_factory = interrupted.controller_factory

        def failing_factory(config, token):
            controller = original_factory(config, token)

            def fail_render(*args):
                raise RuntimeError('synthetic preparation failure')

            controller.renderer = fail_render
            return controller

        interrupted.controller_factory = failing_factory
        with self.assertRaises(RuntimeError):
            interrupted.execute({'mode': 'switch', 'switch_id': 'second-switch'},
                                fixture.config_path)
        self.assertEqual(json.loads(fixture.pointer.read_text())['session_id'], 'one')
        self.assertEqual(fixture.server.current['session_id'], 'one')

        # Before hidden input reveals the recovery ID, preflight sees the old
        # active shop. Its exact destination remains the same as the recorded
        # switch target; recovery must use that authoritative target record.
        scope = preflight_scope(fixture.pointer)
        recovery = fixture.shop()
        recovery.expected_scope = scope
        result = recovery.execute({'mode': 'recover_switch',
                                   'switch_id': 'second-switch'})
        self.assertTrue(result['ok'])
        self.assertEqual(result['session_id'], 'second')
        self.assertEqual(json.loads(fixture.pointer.read_text())['session_id'], 'second')
        self.assertEqual(fixture.server.current['session_id'], 'second')
        self.assertEqual(fixture.actions, 0)
        self.assertEqual(fixture.imports, 0)

    def test_optional_corrupt_ack_does_not_block_authenticated_pointer_recovery(self):
        fixture = self.fixture
        fixture.server.die_after_commit = True
        with self.assertRaises(SystemExit):
            fixture.switch()
        self.assertEqual(json.loads(fixture.pointer.read_text())['state'], 'switching')

        recovery = fixture.shop()
        controller = recovery.controller(fixture.config_path)
        controller.state_path.parent.mkdir(parents=True, exist_ok=True)
        controller.state_path.write_text('synthetic malformed publication receipt')
        recovery.expected_scope = preflight_scope(fixture.pointer)
        output = io.StringIO()
        recovery.diagnostics = Diagnostics(stream=output)
        posts_before = fixture.server.posts

        result = recovery.execute({'mode': 'recover_switch', 'switch_id': 's1'})
        self.assertTrue(result['recovered'])
        self.assertEqual(result['verification'], 'authenticated_current_pointer')
        self.assertEqual(json.loads(fixture.pointer.read_text())['state'], 'active')
        self.assertEqual(fixture.server.posts, posts_before)
        self.assertEqual(fixture.actions, 0)
        self.assertEqual(fixture.imports, 0)
        self.assertIsNone(result['sync_status']['last_ack_revision'])
        self.assertEqual(result['sync_status']['ack_relation'], 'unknown')
        self.assertEqual(result['sync_status']['live_sync_state'], 'not_asserted')
        events = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertTrue(any(event['event'] == 'state_unavailable' and
                            event.get('error_class') == 'json_error'
                            for event in events))
        self.assertNotIn('synthetic malformed publication receipt', output.getvalue())
        self.assertNotIn(str(controller.state_path), output.getvalue())
        self.assertEqual(controller.state_path.read_text(),
                         'synthetic malformed publication receipt')


if __name__ == '__main__':
    unittest.main()
