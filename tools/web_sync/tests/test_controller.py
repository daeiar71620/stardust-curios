import copy
import base64
import importlib.util
import json
import hashlib
import multiprocessing
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from action_publish import Controller,Stop,HttpProblem,TransientNetwork,atomic_json,game_lock,digest,request_bytes
from public_projection import sanitize

PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=')
def observation(revision=1):
    return {'version':9,'revision':revision,'day':1,'phase':'active','credits':260,'inventory':[],'collection':[],'codex':{'total':24,'discovered':0,'collected':0,'entries':[{'slot':1,'discovered':False,'collected':False,'name':'HIDDEN','art_id':'hidden'}]},'secret_seed':'never-send'}

class Harness(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.public=self.root/'game.observation.json';atomic_json(self.public,observation());(self.root/'engine.py').write_text('# fixture engine, never invoked\n');self.config={'site_id':'test-project','site_url':'https://private-test.chatgpt.site','session_id':'test-session','session_epoch':3,'observation_version':9,'engine_path':str(self.root/'engine.py'),'save_path':str(self.root/'game.json'),'observation_path':str(self.public),'outbox_dir':str(self.root/'outbox'),'art_dir':str(self.root/'art'),'renderer_path':str(self.root/'spectator.py'),'owner_private_verified':True};self.calls=[];self.posts=[];self.responses=[];self.status_projection=None
    def tearDown(self):self.temp.cleanup()
    def runner(self,c,action,fd):
        self.calls.append(action)
        if action==['status']:
            if self.status_projection:atomic_json(self.public,self.status_projection)
            return 0
        value=json.loads(self.public.read_text());value['revision']+=1;value['credits']-=1;atomic_json(self.public,value);return 0
    def renderer(self,c,o,fd):
        c['art_dir'].mkdir(exist_ok=True)
        for row in o.get('inventory',[]):
            if row.get('art_id'): (c['art_dir']/(row['art_id']+'.png')).write_bytes(PNG)
    def transport(self,url,token,body):
        self.posts.append(copy.deepcopy(body))
        self.assertEqual(token,'memory-only-token')
        self.assertNotIn('secret_seed',json.dumps(body));self.assertNotIn('HIDDEN',json.dumps(body));self.assertNotIn('game.json',json.dumps(body))
        if self.responses:
            value=self.responses.pop(0)
            if isinstance(value,BaseException):raise value
            if value is not None:return value
        return {'ok':True,'revision':body['observation']['revision'],'session_id':body['session_id'],'session_epoch':body['session_epoch'],'digest':'a'*64,'request_sha256':hashlib.sha256(request_bytes(body)).hexdigest(),'published_at':'fixture-time'}
    def make(self,**kwargs):return Controller(self.config,'memory-only-token',transport=kwargs.get('transport',self.transport),runner=kwargs.get('runner',self.runner),renderer=self.renderer,sleeper=lambda n:None)
    def sync(self,c):return c.execute({'mode':'sync'})
    def action(self,c,op='op1',action=None):return c.execute({'operation_id':op,'action':action or ['buy','salvage']})
    def test_action_upload_failure_does_not_replay_action(self):
        c=self.make();self.sync(c);self.responses=[HttpProblem(503)]*3
        with self.assertRaises(Stop) as e:self.action(c)
        self.assertEqual(e.exception.code,'publication_retry_exhausted');self.assertEqual(len(self.calls),1)
        self.assertTrue(self.action(self.make())['ok']);self.assertEqual(len(self.calls),1)
    def test_duplicate_id_and_changed_action(self):
        c=self.make();self.action(c);again=self.action(c);self.assertFalse(again['engine_executed']);self.assertEqual(len(self.calls),1)
        with self.assertRaises(Stop):self.action(c,action=['buy','curated'])
    def test_auth_stops_without_retry_after_commit(self):
        c=self.make();self.sync(c);self.responses=[HttpProblem(403)];before=len(self.posts)
        with self.assertRaises(Stop) as e:self.action(c)
        self.assertEqual(e.exception.code,'publication_authorization_stop');self.assertEqual(len(self.posts)-before,1);self.assertEqual(len(self.calls),1)
    def test_preflight_auth_failure_runs_no_engine(self):
        c=self.make();self.responses=[HttpProblem(401)]
        with self.assertRaises(Stop):self.action(c)
        self.assertEqual(self.calls,[])
    def test_transient_retry_budget_and_success(self):
        c=self.make();self.sync(c);self.responses=[TransientNetwork(),HttpProblem(502),None];self.action(c);self.assertEqual(len(self.calls),1);self.assertEqual(len(self.posts),4)
    def test_non_transient_and_ack_scope_mismatch_stop(self):
        for value in [HttpProblem(400),{'ok':True,'revision':1,'session_id':'wrong','session_epoch':3,'digest':'a'*64}]:
            c=self.make();self.responses=[value];before=len(self.posts)
            with self.assertRaises(Stop):self.sync(c)
            self.assertEqual(len(self.posts)-before,1)
    def test_crash_gap_duplicate_never_reexecutes(self):
        c=self.make();self.sync(c)
        def killed(cfg,action,fd):self.runner(cfg,action,fd);raise RuntimeError('crash after commit')
        with self.assertRaises(Stop):self.action(self.make(runner=killed))
        with self.assertRaises(Stop):self.action(self.make())
        self.assertEqual(len(self.calls),1)
        with self.assertRaises(Stop) as e:c.execute({'mode':'reconcile','operation_id':'op1'})
        self.assertEqual(e.exception.code,'action_outcome_needs_review')
        result=c.execute({'mode':'reconcile','operation_id':'op1','resolution':'committed'});self.assertTrue(result['ok']);self.assertEqual(sum(a!=['status'] for a in self.calls),1)
    def test_nonstandard_engine_exit_is_uncertain(self):
        c=self.make(runner=lambda *args:-9);self.sync(c)
        with self.assertRaises(Stop) as e:self.action(c)
        self.assertEqual(e.exception.code,'action_outcome_needs_review')
    def test_projection_lag_does_not_mean_uncommitted(self):
        c=self.make(runner=lambda *args:0);self.sync(c)
        with self.assertRaises(Stop):self.action(c)
        self.status_projection=observation(2);c=self.make();result=c.execute({'mode':'reconcile','operation_id':'op1','resolution':'committed'});self.assertTrue(result['ok'])
        self.assertEqual(self.calls,[['status']])
    def test_stale_revision_and_session_binding(self):
        c=self.make();self.action(c);atomic_json(self.public,observation(1))
        with self.assertRaises(Stop) as e:self.sync(c)
        self.assertEqual(e.exception.code,'source_revision_rollback')
        self.config['session_id']='other'
        with self.assertRaises(Stop) as e:self.sync(self.make())
        self.assertEqual(e.exception.code,'game_scope_or_journal_changed')
    def test_latest_committed_state_resync_not_old_payload(self):
        c=self.make();self.sync(c);self.responses=[HttpProblem(503)]*3
        with self.assertRaises(Stop):self.action(c)
        atomic_json(self.public,observation(3));self.sync(c);self.assertEqual(self.posts[-1]['observation']['revision'],3);self.assertEqual(len(self.calls),1)
    def test_known_art_delta_after_ack_only(self):
        o=observation();o['inventory']=[{'id':'I001','art_id':'known','name':'known'}];atomic_json(self.public,o);c=self.make();self.responses=[HttpProblem(503)]*3
        with self.assertRaises(Stop):self.sync(c)
        self.sync(c);self.assertEqual(set(self.posts[-1]['artwork']),{'known'});self.sync(c);self.assertEqual(self.posts[-1]['artwork'],{})
    def test_resolved_upload_failure_stays_pending_and_does_not_repeat_engine(self):
        c=self.make();self.sync(c)
        def killed(cfg,action,fd):self.runner(cfg,action,fd);raise RuntimeError('killed')
        with self.assertRaises(Stop):self.action(self.make(runner=killed))
        self.responses=[HttpProblem(503)]*3
        with self.assertRaises(Stop):c.execute({'mode':'reconcile','operation_id':'op1','resolution':'committed'})
        result=self.action(c);self.assertTrue(result['ok']);self.assertFalse(result['engine_executed']);self.assertEqual(sum(a!=['status'] for a in self.calls),1)
    def test_mutation_exit_two_is_conservatively_uncertain(self):
        c=self.make(runner=lambda *args:2);self.sync(c)
        with self.assertRaises(Stop) as error:self.action(c)
        self.assertEqual(error.exception.code,'action_outcome_needs_review')
    def test_default_save_has_one_public_path(self):
        config=dict(self.config);config['save_path']=str(self.root/'save.json');config['observation_path']=str(self.root/'save.observation.json')
        with self.assertRaises(Stop):Controller(config,'token')
        config['observation_path']=str(self.root/'observation.json');Controller(config,'token')
        elsewhere=self.root/'elsewhere';elsewhere.mkdir();config['save_path']=str(elsewhere/'save.json');config['observation_path']=str(elsewhere/'observation.json')
        with self.assertRaises(Stop):Controller(config,'token')
    def test_inherited_lock_survives_parent_descriptor_close(self):
        save=Path(self.config['save_path'])
        with game_lock(save) as fd:
            child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(.4)'],pass_fds=(fd,))
        try:
            with self.assertRaises(Stop):
                with game_lock(save):pass
        finally:child.wait(timeout=2)
        with game_lock(save):pass
    def test_request_hash_mismatch_stops(self):
        c=self.make();self.responses=[{'ok':True,'revision':1,'session_id':'test-session','session_epoch':3,'digest':'a'*64,'request_sha256':'0'*64}]
        with self.assertRaises(Stop) as e:self.sync(c)
        self.assertEqual(e.exception.code,'publication_ack_scope_mismatch')
    def test_reconcile_repairs_missing_projection_before_reading_it(self):
        c=self.make();self.sync(c)
        def killed(cfg,action,fd):self.runner(cfg,action,fd);raise RuntimeError('killed')
        with self.assertRaises(Stop):self.action(self.make(runner=killed))
        self.public.unlink();self.status_projection=observation(2)
        result=c.execute({'mode':'reconcile','operation_id':'op1','resolution':'committed'});self.assertTrue(result['ok'])
    def test_symlink_known_art_is_not_read(self):
        o=observation();o['inventory']=[{'id':'I001','art_id':'known','name':'known'}];atomic_json(self.public,o);art=self.root/'art';art.mkdir();private=self.root/'sensitive.bin';private.write_bytes(PNG+b'NEVER_SEND');(art/'known.png').symlink_to(private)
        c=Controller(self.config,'memory-only-token',transport=self.transport,runner=self.runner,renderer=lambda *args:None,sleeper=lambda n:None)
        with self.assertRaises(Stop) as e:self.sync(c)
        self.assertEqual(e.exception.code,'unsafe_art_file');self.assertEqual(self.posts,[])
    def test_truncated_png_is_never_published(self):
        o=observation();o['inventory']=[{'id':'I001','art_id':'known','name':'known'}];atomic_json(self.public,o);art=self.root/'art';art.mkdir();(art/'known.png').write_bytes(PNG[:12])
        c=Controller(self.config,'memory-only-token',transport=self.transport,runner=self.runner,renderer=lambda *args:None,sleeper=lambda n:None)
        with self.assertRaises(Stop) as e:self.sync(c)
        self.assertEqual(e.exception.code,'invalid_known_png');self.assertEqual(self.posts,[])
    def test_no_credential_in_durable_files(self):
        c=self.make();self.action(c)
        for p in (self.root/'outbox').rglob('*.json'):self.assertNotIn('memory-only-token',p.read_text())
    def test_lock_blocks_different_operation_and_journal(self):
        c=self.make()
        with game_lock(Path(self.config['save_path'])):
            with self.assertRaises(Stop) as e:self.action(c)
        self.assertEqual(e.exception.code,'game_busy');self.assertEqual(self.calls,[])
        self.sync(c);self.config['outbox_dir']=str(self.root/'another')
        with self.assertRaises(Stop):self.sync(self.make())
    def test_forbidden_action_and_path(self):
        c=self.make()
        for action in [['restart','--confirm'],['import-v8','old.json'],['buy','salvage;bad'],['status','--save','other']]:
            with self.assertRaises(Stop):self.action(c,action=action)
        self.assertEqual(self.calls,[])
        config=dict(self.config);config['observation_path']=config['save_path']
        with self.assertRaises(Stop):Controller(config,'token')

    def test_journal_is_scanned_once_per_exclusive_execution(self):
        import action_publish
        c = self.make()
        self.sync(c)
        for index in range(150):
            operation_id = 'past-' + str(index)
            atomic_json(c.ops/(operation_id+'.json'), {
                'schema_version': 1, 'operation_id': operation_id,
                'config_fingerprint': c.c['fingerprint'], 'stage': 'published',
                'revision_after': 1})
        original = action_publish.read_json
        reads = []
        def counted(path):
            if Path(path).parent == c.ops:
                reads.append(Path(path).name)
            return original(path)
        with patch.object(action_publish, 'read_json', side_effect=counted):
            self.action(c)
        self.assertEqual(len(reads), 150)
        self.assertEqual(len(set(reads)), 150)
        self.assertFalse(c._cache_active)
        self.assertIsNone(c._pending_cache)

    def test_journal_cache_never_hides_damage_between_executions(self):
        c = self.make()
        self.action(c)
        path = c.ops/'op1.json'
        receipt = json.loads(path.read_text())
        receipt['config_fingerprint'] = 'tampered'
        atomic_json(path, receipt)
        with self.assertRaises(Stop) as error:
            self.action(c, op='op2')
        self.assertEqual(error.exception.code, 'invalid_operation_receipt')
        self.assertEqual(len(self.calls), 1)
        self.assertIsNone(c._pending_cache)

    def test_journal_file_cannot_alias_another_operation_id(self):
        c = self.make()
        self.action(c)
        receipt = json.loads((c.ops/'op1.json').read_text())
        atomic_json(c.ops/'alias.json', receipt)
        with self.assertRaises(Stop) as error:
            self.sync(c)
        self.assertEqual(error.exception.code, 'invalid_operation_receipt')

    def test_new_publication_epoch_preserves_journal_and_deduplication(self):
        c = self.make()
        self.action(c)
        fingerprint, journal = c.c['fingerprint'], c.c['journal']
        c.publication_epoch = 4
        self.sync(c)
        self.assertEqual(self.posts[-1]['session_epoch'], 4)
        self.assertEqual(c.state()['session_epoch'], 4)
        self.assertEqual((c.c['fingerprint'], c.c['journal']), (fingerprint, journal))
        self.assertFalse(self.action(c)['engine_executed'])
        self.assertEqual(len(self.calls), 1)

    def test_old_epoch_ack_is_rejected_after_activation(self):
        c = self.make()
        c.publication_epoch = 4
        def stale_ack(url, token, body):
            ack = self.transport(url, token, body)
            ack['session_epoch'] = 3
            return ack
        c.transport = stale_ack
        with self.assertRaises(Stop) as error:
            self.sync(c)
        self.assertEqual(error.exception.code, 'publication_ack_scope_mismatch')

    def test_activation_receipt_prevents_redundant_presync(self):
        c = self.make()
        self.sync(c)
        c.publication_epoch = 4
        ack = {'ok': True, 'revision': 1, 'session_id': c.c['session_id'],
               'session_epoch': 4, 'request_sha256': 'b'*64, 'digest': 'a'*64,
               'published_at': 'fixture-time'}
        before = len(self.posts)
        with game_lock(c.c['save_path']):
            c.record_publication(c.observation(), ack, request_sha256='b'*64, art_hashes={})
        self.assertEqual(len(self.posts), before)
        self.action(c)
        self.assertEqual(len(self.posts), before+1)
        self.assertEqual(c.state()['session_epoch'], 4)

    def test_activation_receipt_requires_exact_public_source_and_art_scope(self):
        c = self.make()
        ack = {'ok': True, 'revision': 1, 'session_id': c.c['session_id'],
               'session_epoch': 3, 'request_sha256': 'b'*64, 'digest': 'a'*64}
        with game_lock(c.c['save_path']):
            with self.assertRaises(Stop) as error:
                c.record_publication(c.observation(), ack, request_sha256='b'*64,
                                     art_hashes={'undiscovered': 'c'*64})
            self.assertEqual(error.exception.code, 'invalid_art_receipt')
            source = c.observation()
            atomic_json(self.public, observation(2))
            with self.assertRaises(Stop) as error:
                c.record_publication(source, ack, request_sha256='b'*64, art_hashes={})
            self.assertEqual(error.exception.code, 'source_changed_during_publication')
        self.assertFalse(c.state_path.exists())

    def test_invalid_runtime_epoch_cannot_upload(self):
        for epoch in (0, 2, True, '4'):
            c = self.make()
            c.publication_epoch = epoch
            with self.assertRaises(Stop) as error:
                self.sync(c)
            self.assertEqual(error.exception.code, 'invalid_publication_epoch')
        self.assertEqual(self.posts, [])

    def test_stale_runtime_epoch_cannot_replace_newer_local_receipt(self):
        c = self.make()
        c.publication_epoch = 4
        self.sync(c)
        before = len(self.posts)
        stale = self.make()
        with self.assertRaises(Stop) as error:
            self.sync(stale)
        self.assertEqual(error.exception.code, 'stale_publication_epoch')
        ack = {'ok': True, 'revision': 1, 'session_id': c.c['session_id'],
               'session_epoch': 3, 'request_sha256': 'b'*64, 'digest': 'a'*64}
        with game_lock(stale.c['save_path']):
            with self.assertRaises(Stop) as error:
                stale.record_publication(stale.observation(), ack, request_sha256='b'*64, art_hashes={})
        self.assertEqual(error.exception.code, 'stale_publication_epoch')
        self.assertEqual(len(self.posts), before)
        self.assertEqual(c.state()['session_epoch'], 4)

    def test_renderer_cache_miss_is_bounded_and_inherits_game_lock(self):
        import action_publish
        import export_known_art
        c = self.make()
        with game_lock(c.c['save_path']) as fd:
            with patch.object(export_known_art, 'cache_ready', return_value=False):
                with patch.object(action_publish.subprocess, 'run') as run:
                    action_publish.render_known(c.c, c.observation(), fd)
        args, kwargs = run.call_args
        self.assertIn('--no-preview', args[0])
        self.assertEqual(kwargs['timeout'], 45)
        self.assertEqual(kwargs['pass_fds'], (fd,))
        self.assertTrue(kwargs['check'])

    def test_renderer_timeout_after_commit_does_not_repeat_action(self):
        c = self.make()
        self.sync(c)
        with patch.object(c, 'renderer', side_effect=subprocess.TimeoutExpired('synthetic-export', 45)):
            with self.assertRaises(subprocess.TimeoutExpired):
                self.action(c)
        self.assertEqual(len(self.calls), 1)
        result = self.action(c)
        self.assertTrue(result['ok'])
        self.assertFalse(result['engine_executed'])
        self.assertEqual(len(self.calls), 1)

if __name__=='__main__':unittest.main()
