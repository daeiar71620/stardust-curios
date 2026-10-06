#!/usr/bin/env python3
"""Full synthetic first-week action/save/art/mock-sync smoke; never contacts a Site.

All generated saves, observations, PNGs and operation receipts are temporary.
Decisions use only public observations. The official engine subprocess performs
all actions, and a mock transport verifies request scope/bytes before acking.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time

sys.dont_write_bytecode = True


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    args.game = args.game.expanduser().resolve()
    sys.path.insert(0, str(args.game))
    import action_publish as sync
    engine = load('synthetic_engine', args.game/'engine.py')
    policy = load('synthetic_policy', args.game/'simulate_management_v6.py')
    posts, calls, elapsed, snapshots = [], [], [], []
    transient_injected = False
    with tempfile.TemporaryDirectory(prefix='stardust-full-pipeline-') as directory:
        root = Path(directory)
        save = root/'synthetic.json'
        public = root/'synthetic.observation.json'
        state = engine.new_state(71620)
        state['revision'] = 1
        engine._atomic_json(save, state)
        engine.GameStore(save).execute('status')
        config = {'site_id': 'synthetic-only', 'site_url': 'https://synthetic-only.chatgpt.site',
                  'session_id': 'synthetic-smoke', 'session_epoch': 1, 'observation_version': 9,
                  'engine_path': str(args.game/'engine.py'), 'save_path': str(save),
                  'observation_path': str(public), 'outbox_dir': str(root/'outbox'),
                  'art_dir': str(root/'art'), 'renderer_path': str(args.game/'spectator.py'),
                  'owner_private_verified': True}
        def runner(c, action, lock_fd):
            calls.append(tuple(action))
            return sync.official_runner(c, action, lock_fd)
        def transport(url, token, body):
            nonlocal transient_injected
            assert url == config['site_url']+'/api/ingest'
            assert token == 'synthetic-no-network-token'
            assert set(body) == {'stream_id', 'session_id', 'session_epoch', 'play_state',
                                 'source_saved_at', 'observation', 'artwork'}
            raw = sync.request_bytes(body)
            text = raw.decode()
            assert not any(key in text for key in ('rng_state', 'secret_seed', 'hidden_items', 'random_state'))
            observed = body['observation']
            assert set(body['artwork']) <= sync.known_art(observed)
            for entry in observed.get('codex', {}).get('entries', []):
                if entry.get('discovered') is not True:
                    assert set(entry) <= {'slot', 'discovered', 'collected'}
            # Exactly one transient response proves retry uploads, never replays gameplay.
            if len(calls) == 10 and not transient_injected:
                transient_injected = True
                raise sync.TransientNetwork()
            posts.append({'revision': observed['revision'], 'bytes': len(raw),
                          'art_count': len(body['artwork'])})
            return {'ok': True, 'session_id': body['session_id'], 'session_epoch': body['session_epoch'],
                    'revision': observed['revision'], 'digest': sync.digest(observed),
                    'request_sha256': hashlib.sha256(raw).hexdigest(),
                    'published_at': '2026-10-06T00:00:00Z'}
        controller = sync.Controller(config, 'synthetic-no-network-token',
                                     transport=transport, runner=runner, sleeper=lambda _: None)
        controller.execute({'mode': 'sync'})
        while True:
            observation = controller.observation()
            if observation['phase'] in ('week_summary', 'lost'):
                break
            action = policy.action(observation, 'careful115') or ('endday',)
            operation = {'operation_id': 'synthetic-'+str(len(calls)+1), 'action': list(action)}
            started = time.perf_counter()
            ack = controller.execute(operation)
            elapsed.append((time.perf_counter()-started)*1000)
            assert ack['ok'] and ack['verification'] == 'server_commit_ack'
            snapshots.append(sync.digest(controller.observation()))
            before_calls, before_posts = len(calls), len(posts)
            duplicate = controller.execute(operation)
            assert duplicate['engine_executed'] is False
            assert (len(calls), len(posts)) == (before_calls, before_posts)
        assert observation['day'] == 7 and observation['phase'] == 'week_summary'
        assert len(posts) == len(calls)+1
        assert transient_injected
        assert engine.VERSION == 9
        result = {'scope': 'temporary synthetic save and mock network only',
                  'day': observation['day'], 'phase': observation['phase'],
                  'actions': len(calls), 'successful_posts': len(posts),
                  'all_duplicate_actions_suppressed': True, 'transient_upload_recovered_without_action_replay': True,
                  'public_transcript_sha256': sync.digest({'actions': calls, 'snapshots': snapshots}),
                  'known_art_count': len(sync.known_art(observation)),
                  'action_median_ms': round(statistics.median(elapsed), 3),
                  'action_p95_ms': round(sorted(elapsed)[int(len(elapsed)*.95)], 3),
                  'total_action_ms': round(sum(elapsed), 3),
                  'total_uploaded_bytes': sum(post['bytes'] for post in posts),
                  'art_posts': sum(post['art_count'] > 0 for post in posts)}
    result['all_synthetic_outputs_cleaned'] = True
    if args.output:
        args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
