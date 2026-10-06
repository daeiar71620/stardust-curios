import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from action_publish import Controller,Stop,HttpProblem,TransientNetwork,atomic_json,request_bytes
from shop import Shop


def obs(version=9,revision=1):return {'version':version,'revision':revision,'day':7,'phase':'week_summary','credits':668,'reputation':23,'energy':13,'max_energy':13,'inventory':[],'collection':[],'crates':[],'upgrades':{},'stats':{},'campaign':{'first_week_result':'won'},'codex':{'total':24,'entries':[]},'budget_upgrade':{'from_version':8}}
class FakeServer:
    def __init__(self):self.current={'stream_id':'main','session_id':'old','session_epoch':2,'activation_id':None,'revision':89};self.activations={};self.posts=0;self.errors=[];self.die_after_commit=False
    def read(self,c,token):return dict(self.current)
    def post(self,url,token,payload):
        self.posts+=1
        if self.errors:raise self.errors.pop(0)
        if url.endswith('/api/ingest'):
            if payload['session_id']!=self.current['session_id']or payload['session_epoch']!=self.current['session_epoch']:raise HttpProblem(409)
            self.current['revision']=payload['observation']['revision'];return self.ack(payload)
        key=payload['activation_id'];fingerprint=json.dumps([payload['session_id'],payload['expected_epoch'],payload['observation']],sort_keys=True)
        if key in self.activations:
            if self.activations[key]!=fingerprint or self.current['activation_id']!=key:raise HttpProblem(409)
            return self.ack(payload,True)
        if payload['expected_epoch']!=self.current['session_epoch']or payload['expected_session_id']!=self.current['session_id']:raise HttpProblem(409)
        self.current={'stream_id':'main','session_id':payload['session_id'],'session_epoch':payload['expected_epoch']+1,'activation_id':key,'revision':payload['observation']['revision']};self.activations[key]=fingerprint
        if self.die_after_commit:self.die_after_commit=False;raise SystemExit('simulated process kill after remote commit')
        return self.ack(payload)
    def ack(self,payload,duplicate=False):return {'ok':True,'active':True,'idempotent':duplicate,'activation_id':payload.get('activation_id'),'session_id':self.current['session_id'],'session_epoch':self.current['session_epoch'],'revision':payload['observation']['revision'],'digest':'a'*64,'request_sha256':hashlib.sha256(request_bytes(payload)).hexdigest(),'published_at':'fixture-time'}
class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.pointer=self.root/'current-shop.json';self.server=FakeServer();self.imports=0;self.actions=0;self.prepare('one')
    def tearDown(self):self.tmp.cleanup()
    def prepare(self,name,existing=True):
        d=self.root/name;d.mkdir();(d/'engine.py').write_text('# synthetic only');self.config={'site_id':'test-project','site_url':'https://private-test.chatgpt.site','owner_private_verified':True,'session_id':name,'session_epoch':1,'observation_version':9,'engine_path':str(d/'engine.py'),'save_path':str(d/'game.json'),'observation_path':str(d/'game.observation.json'),'outbox_dir':str(d/'outbox'),'art_dir':str(d/'art'),'renderer_path':str(d/'spectator.py')};self.config_path=d/'config.local.json';atomic_json(self.config_path,self.config)
        if existing:(d/'game.json').write_text('synthetic-private-never-read');atomic_json(d/'game.observation.json',obs())
        return self.config_path
    def runner(self,c,action,fd):
        if action!=['status']:
            self.actions+=1;o=json.loads(c['observation_path'].read_text());o['revision']+=1;atomic_json(c['observation_path'],o)
        return 0
    def factory(self,c,t):return Controller(c,t,runner=self.runner,renderer=lambda *args:None,transport=self.server.post,sleeper=lambda n:None)
    def importer(self,c,source,fds):
        self.imports+=1;c['save_path'].write_text('synthetic-private-copy');atomic_json(c['observation_path'],obs());return 0
    def shop(self):return Shop(self.pointer,'test-memory-token','test-project',session_reader=self.server.read,transport=self.server.post,importer=self.importer,controller_factory=self.factory,sleeper=lambda n:None)
    def switch(self,switch='s1',**extra):return self.shop().execute({'mode':'switch','switch_id':switch,**extra},self.config_path)
    def test_activation_and_duplicate_have_no_game_actions(self):
        result=self.switch();self.assertEqual(result['session_epoch'],3);self.assertEqual(self.actions,0);n=self.server.posts;self.assertTrue(self.switch()['idempotent']);self.assertEqual(self.server.posts,n)
    def test_copy_import_once_then_retry_upload_only(self):
        self.prepare('copy',False);source=self.root/'old.json';source.write_text('original-never-read');public=self.root/'old.observation.json';atomic_json(public,obs(8));copy={'source_save_path':str(source),'source_observation_path':str(public)};self.server.errors=[HttpProblem(503)]*3
        with self.assertRaises(Stop):self.switch(copy_import=copy)
        self.assertEqual(self.imports,1);self.assertEqual(self.server.current['session_id'],'old');self.assertEqual(json.loads(self.pointer.read_text())['state'],'switching')
        self.assertTrue(self.switch(copy_import=copy)['ok']);self.assertEqual(self.imports,1);self.assertEqual(source.read_text(),'original-never-read')
    def test_remote_commit_local_kill_recovery_never_imports_twice(self):
        self.server.die_after_commit=True
        with self.assertRaises(SystemExit):self.switch()
        self.assertEqual(json.loads(self.pointer.read_text())['state'],'switching')
        result=self.shop().execute({'mode':'recover_switch','switch_id':'s1'});self.assertTrue(result['recovered']);self.assertEqual(self.imports,0)
    def test_auth_stop_has_no_engine_action_or_pointer_activation(self):
        self.server.errors=[HttpProblem(403)]
        with self.assertRaises(Stop)as e:self.switch()
        self.assertEqual(e.exception.code,'activation_authorization_stop');self.assertEqual(self.server.posts,1);self.assertEqual(self.actions,0);self.assertEqual(self.server.current['session_id'],'old')
    def test_stale_activation_does_not_rollback_newer_remote(self):
        def race(c,token):old=self.server.read(c,token);self.server.current={'stream_id':'main','session_id':'newer','session_epoch':5,'activation_id':'other','revision':9};return old
        shop=self.shop();shop.session_reader=race
        with self.assertRaises(Stop):shop.execute({'mode':'switch','switch_id':'s1'},self.config_path)
        self.assertEqual(self.server.current['session_id'],'newer')
        with self.assertRaises(Stop)as e:self.shop().execute({'mode':'recover_switch','switch_id':'s1'})
        self.assertEqual(e.exception.code,'newer_remote_switch_preserved')
    def test_actions_block_while_switch_pending(self):
        self.server.errors=[HttpProblem(503)]*3
        with self.assertRaises(Stop):self.switch()
        with self.assertRaises(Stop):self.shop().execute({'operation_id':'op1','action':['buy','salvage']})
        self.assertEqual(self.actions,0)
    def test_reactivation_preserves_duplicate_operation_ids(self):
        first=self.config_path;self.switch();self.shop().execute({'operation_id':'op1','action':['buy','salvage']});self.assertEqual(self.actions,1)
        self.prepare('two');self.switch('s2');self.config_path=first;self.switch('s3');self.assertEqual(self.server.current['session_epoch'],5)
        result=self.shop().execute({'operation_id':'op1','action':['buy','salvage']});self.assertFalse(result['engine_executed']);self.assertEqual(self.actions,1)
    def test_preparation_failure_preserves_old_pointer(self):
        self.switch();old=json.loads(self.pointer.read_text());self.prepare('broken');Path(self.config['observation_path']).unlink()
        with self.assertRaises(Exception):self.switch('s2')
        self.assertEqual(json.loads(self.pointer.read_text()),old);self.assertEqual(self.server.current['session_id'],'one')
    def test_duplicate_switch_after_new_game_revision_does_not_rollback(self):
        self.switch();self.shop().execute({'operation_id':'op1','action':['buy','salvage']});revision=self.server.current['revision'];self.switch();self.assertEqual(self.server.current['revision'],revision)
    def test_wrong_ack_hash_leaves_local_pending(self):
        original=self.server.ack
        def corrupt(payload,duplicate=False):a=original(payload,duplicate);a['request_sha256']='0'*64;return a
        self.server.ack=corrupt
        with self.assertRaises(Stop)as e:self.switch()
        self.assertEqual(e.exception.code,'activation_ack_mismatch');self.assertEqual(json.loads(self.pointer.read_text())['state'],'switching')
if __name__=='__main__':unittest.main()
