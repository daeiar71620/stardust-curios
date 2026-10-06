import concurrent.futures
import copy
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from authority import Authority,ArtStore,Candidate,CLIAdapter,Problem,dispatch,encoded,sha
from public_projection import sanitize

ENGINE=Path(os.environ.get('STARDUST_TEST_ENGINE','/nonexistent/engine.py'))


def png(size=(8,8)):
    from PIL import Image
    output=io.BytesIO();Image.new('RGB',size,(30,60,90)).save(output,format='PNG');return output.getvalue()


class FakeAdapter:
    identity='synthetic-fake-v1'
    def __init__(self):self.calls=0;self.corrupt=False
    def fresh_synthetic(self):
        return Candidate(encoded({'rng_state':'PRIVATE-RNG-MARKER','hidden_budget':17,'actions':0}),{'version':9,'revision':1,'day':1,'credits':260,'phase':'active','inventory':[],'collection':[],'rng_state':'MUST-NOT-LEAK','visitors':[{'id':'npc','name':'Example','hidden_budget':999,'budget_range':[10,100]}],'codex':{'total':24,'entries':[{'slot':1,'discovered':False,'art_id':'unknown_secret_shape','name':'HIDDEN-CATALOG-NAME'}]}})
    def apply(self,private,public,action):
        self.calls+=1;raw=json.loads(private);raw['actions']+=1
        out=copy.deepcopy(public);out['revision']+=1;out['credits']-=1
        out['private_save']='PRIVATE-RNG-MARKER'
        if action[0]=='open':
            out['inventory']=[{'id':'I001','art_id':'known','name':'Known object','kind':'tool','condition':70,'hidden_value':456}]
            out['codex']['entries'].append({'slot':2,'discovered':True,'art_id':'known','name':'Known object'})
        if self.corrupt:out['revision']='bad'
        return Candidate(encoded(raw),out)


class AuthorityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='colocated-test-');self.root=Path(self.temp.name);self.adapter=FakeAdapter();self.service=Authority(self.root/'authority.sqlite',self.adapter);self.service.initialize_synthetic('testgame')
    def tearDown(self):self.temp.cleanup()
    def test_public_nested_whitelist_and_unknown_mask(self):
        public=self.service.get_state('testgame');text=json.dumps(public)
        for hidden in ('PRIVATE-RNG','MUST-NOT','hidden_budget','hidden_value','unknown_secret_shape','HIDDEN-CATALOG'):self.assertNotIn(hidden,text)
        self.assertEqual(public['observation']['codex']['entries'],[{'slot':1,'discovered':False,'collected':False}])
    def test_duplicate_replays_exact_receipt_before_revision_check(self):
        first=self.service.game_action('testgame','one',1,['buy','salvage']);second=self.service.game_action('testgame','one',1,['buy','salvage'])
        self.assertEqual(first,second);self.assertEqual(self.adapter.calls,1);self.assertEqual(self.service.get_state('testgame')['revision'],2)
    def test_id_reuse_different_action_rejected(self):
        self.service.game_action('testgame','one',1,['buy','salvage'])
        with self.assertRaisesRegex(Problem,'operation_id_conflict'):self.service.game_action('testgame','one',1,['buy','curated'])
        self.assertEqual(self.adapter.calls,1)
    def test_id_reuse_different_expected_revision_rejected(self):
        self.service.game_action('testgame','one',1,['buy','salvage'])
        with self.assertRaisesRegex(Problem,'operation_id_conflict'):self.service.game_action('testgame','one',2,['buy','salvage'])
    def test_stale_revision_never_calls_engine(self):
        with self.assertRaisesRegex(Problem,'revision_conflict'):self.service.game_action('testgame','one',9,['buy','salvage'])
        self.assertEqual(self.adapter.calls,0);self.assertIsNone(self.service.get_receipt('testgame','one'))
    def test_scope_isolation(self):
        self.service.initialize_synthetic('other');a=self.service.game_action('testgame','same',1,['buy','salvage']);b=self.service.game_action('other','same',1,['buy','salvage'])
        self.assertNotEqual(a['game_id'],b['game_id']);self.assertEqual(self.service.get_state('other')['revision'],2)
    def test_invalid_actions_cannot_read_or_replace_files(self):
        for action in (['restart','--confirm'],['new'],['status'],['buy','../../save'],['__import__','os'],['price','I001','-5'],[[]],[{}],[None]):
            with self.assertRaisesRegex(Problem,'action_not_allowed'):self.service.game_action('testgame','bad',1,action)
        self.assertEqual(self.adapter.calls,0)
    def test_concurrent_same_revision_exactly_one_canonical_commit(self):
        gate=threading.Barrier(2)
        def act(i):
            service=Authority(self.root/'authority.sqlite',self.adapter);gate.wait()
            try:return service.game_action('testgame',f'op-{i}',1,['buy','salvage'])
            except Problem as error:return error.code
        with concurrent.futures.ThreadPoolExecutor(2) as pool:results=list(pool.map(act,[1,2]))
        self.assertEqual(sum(isinstance(r,dict)for r in results),1);self.assertIn('revision_conflict',results);self.assertEqual(self.adapter.calls,1)
    def test_concurrent_identical_operation_replays_one_commit(self):
        gate=threading.Barrier(2)
        def act(_):
            service=Authority(self.root/'authority.sqlite',self.adapter);gate.wait();return service.game_action('testgame','same',1,['buy','salvage'])
        with concurrent.futures.ThreadPoolExecutor(2)as pool:results=list(pool.map(act,[1,2]))
        self.assertEqual(results[0],results[1]);self.assertEqual(self.adapter.calls,1)
    def test_reader_sees_previous_complete_snapshot_until_commit(self):
        entered=threading.Event();release=threading.Event();errors=[]
        def hook(stage):
            if stage=='after_state_update':entered.set();self.assertTrue(release.wait(5))
        service=Authority(self.root/'authority.sqlite',self.adapter,hook=hook)
        def write():
            try:service.game_action('testgame','one',1,['buy','salvage'])
            except Exception as error:errors.append(error)
        worker=threading.Thread(target=write);worker.start();self.assertTrue(entered.wait(5))
        before=self.service.get_state('testgame');self.assertEqual(before['revision'],1);self.assertEqual(before['observation']['credits'],260);self.assertIsNone(self.service.get_receipt('testgame','one'))
        release.set();worker.join(5);self.assertFalse(errors)
        after=self.service.get_state('testgame');self.assertEqual(after['revision'],2);self.assertEqual(after['state_hash'],self.service.get_receipt('testgame','one')['state_hash'])
    def test_exception_after_state_write_rolls_back_receipt_and_state(self):
        def hook(stage):
            if stage=='after_state_update':raise RuntimeError('injected')
        self.service.hook=hook
        with self.assertRaises(RuntimeError):self.service.game_action('testgame','one',1,['buy','salvage'])
        self.assertEqual(self.service.get_state('testgame')['revision'],1);self.assertIsNone(self.service.get_receipt('testgame','one'))
    def test_lost_response_after_commit_recovers_without_engine(self):
        def hook(stage):
            if stage=='after_commit':raise ConnectionError('response lost')
        self.service.hook=hook
        with self.assertRaises(ConnectionError):self.service.game_action('testgame','one',1,['buy','salvage'])
        self.service.hook=lambda _:None;result=self.service.game_action('testgame','one',1,['buy','salvage'])
        self.assertEqual(result,self.service.get_receipt('testgame','one'));self.assertEqual(self.adapter.calls,1)
    def test_invalid_candidate_safe_error_no_commit(self):
        self.adapter.corrupt=True
        code,result=dispatch(self.service,'POST','/game/action',{'game_id':'testgame','operation_id':'one','expected_revision':1,'action':['buy','salvage']})
        self.assertEqual(code,500);self.assertEqual(result['error'],'invalid_public_candidate');self.assertEqual(self.service.get_state('testgame')['revision'],1)
    def test_api_never_returns_private_state_or_engine_errors(self):
        body={'game_id':'testgame','operation_id':'one','expected_revision':1,'action':['open','C001']}
        code,receipt=dispatch(self.service,'POST','/game/action',body);self.assertEqual(code,200)
        code,view=dispatch(self.service,'GET','/game/state/testgame');self.assertEqual(code,200)
        self.assertNotIn('PRIVATE',json.dumps([receipt,view]));self.assertNotIn('hidden_value',json.dumps(view))
        code,_=dispatch(self.service,'POST','/game/action',{**body,'save_path':'private'});self.assertEqual(code,404)
    def test_new_game_does_not_overwrite_existing(self):
        before=self.service.get_state('testgame')
        with self.assertRaisesRegex(Problem,'game_already_exists'):self.service.initialize_synthetic('testgame')
        self.assertEqual(before,self.service.get_state('testgame'))


class ArtTests(AuthorityTests):
    # Run only art methods here, not inherited tests twice.
    def setUp(self):
        super().setUp();self.store=ArtStore(self.root/'objects')
    def test_art_provider_cannot_mutate_canonical_public_state(self):
        def malicious(public):
            public['revision']=999
            public['inventory'][0]['name']='CHANGED'
            return {'known':png()}
        service=Authority(self.root/'authority.sqlite',self.adapter,art_store=self.store,art_provider=malicious)
        receipt=service.game_action('testgame','one',1,['open','C001']);state=service.get_state('testgame')
        self.assertEqual(receipt['revision'],2);self.assertEqual(state['revision'],2);self.assertEqual(state['observation']['revision'],2)
        self.assertEqual(state['state_hash'],sha(encoded(state['observation'])))
        self.assertEqual(state['observation']['inventory'][0]['name'],'Known object')
    def test_staged_known_image_visible_only_after_commit(self):
        service=Authority(self.root/'authority.sqlite',self.adapter,art_store=self.store,art_provider=lambda public:{'known':png()})
        service.game_action('testgame','open',1,['open','C001']);self.assertEqual(service.get_art('testgame','known'),png())
        with self.assertRaisesRegex(Problem,'art_not_found'):service.get_art('testgame','unknown_secret_shape')
    def test_unknown_art_is_not_staged(self):
        service=Authority(self.root/'authority.sqlite',self.adapter,art_store=self.store,art_provider=lambda public:{'unknown':png()})
        receipt=service.game_action('testgame','one',1,['open','C001']);self.assertEqual(receipt['art_status'],'placeholder');self.assertEqual(list(self.store.root.glob('*.png')),[]);self.assertEqual(service.get_state('testgame')['images'],{})
    def test_image_failure_does_not_split_game_and_text(self):
        def fail(_):raise OSError('object storage unavailable')
        service=Authority(self.root/'authority.sqlite',self.adapter,art_store=self.store,art_provider=fail)
        receipt=service.game_action('testgame','one',1,['open','C001']);state=service.get_state('testgame');self.assertEqual(state['revision'],receipt['revision']);self.assertEqual(receipt['art_status'],'placeholder')
    def test_crash_after_staging_leaves_invisible_orphan(self):
        def hook(stage):
            if stage=='after_art':raise RuntimeError('crash before DB commit')
        service=Authority(self.root/'authority.sqlite',self.adapter,art_store=self.store,art_provider=lambda public:{'known':png()},hook=hook)
        with self.assertRaises(RuntimeError):service.game_action('testgame','one',1,['open','C001'])
        self.assertEqual(len(list(self.store.root.glob('*.png'))),1);self.assertEqual(service.get_state('testgame')['revision'],1)
        with self.assertRaisesRegex(Problem,'art_not_found'):service.get_art('testgame','known')
    def test_image_limits(self):
        public={'inventory':[{'art_id':'known'}]}
        for data,code in [(b'x'*(self.store.MAX_FILE+1),'art_byte_limit'),(b'not-png','invalid_art'),(png((513,1)),'invalid_art')]:
            with self.assertRaisesRegex(Problem,code):self.store.stage(public,{'known':data})
        with self.assertRaisesRegex(Problem,'art_count_limit'):self.store.stage(public,{str(i):png()for i in range(25)})
        public={'inventory':[{'art_id':f'known{i}'}for i in range(20)]};data=png()+b'\0'*(450*1024)
        with self.assertRaisesRegex(Problem,'art_total_limit'):self.store.stage(public,{f'known{i}':data for i in range(20)})
    def test_missing_object_after_commit_is_placeholder_not_private_leak(self):
        service=Authority(self.root/'authority.sqlite',self.adapter,art_store=self.store,art_provider=lambda public:{'known':png()})
        service.game_action('testgame','one',1,['open','C001'])
        next(self.store.root.glob('*.png')).unlink()
        with self.assertRaisesRegex(Problem,'art_not_found'):service.get_art('testgame','known')
        self.assertEqual(service.get_state('testgame')['revision'],2)

# Prevent unittest from rerunning inherited AuthorityTests under ArtTests.
for name in list(AuthorityTests.__dict__):
    if name.startswith('test_') and name not in ArtTests.__dict__:setattr(ArtTests,name,None)


@unittest.skipUnless(ENGINE.exists(),'official v9 engine not configured')
class OfficialCLITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='colocated-official-');self.root=Path(self.temp.name);self.adapter=CLIAdapter(ENGINE,self.root/'work');self.service=Authority(self.root/'authority.sqlite',self.adapter);self.service.initialize_synthetic('synthetic')
    def tearDown(self):self.temp.cleanup()
    def test_same_initial_synthetic_state_matches_unwrapped_cli_bytes(self):
        with self.service.connect()as db:private=bytes(db.execute('SELECT private_state FROM games').fetchone()[0])
        public=self.service.get_state('synthetic')['observation']
        actions=[['buy','salvage']]
        for i,action in enumerate(actions):
            baseline=self.adapter.apply(private,public,action);receipt=self.service.game_action('synthetic',f'compare-{i}',public['revision'],action)
            with self.service.connect()as db:actual=bytes(db.execute('SELECT private_state FROM games').fetchone()[0])
            self.assertEqual(actual,baseline.private);self.assertEqual(self.service.get_state('synthetic')['observation'],sanitize(baseline.public));private=baseline.private;public=sanitize(baseline.public)
        crate=public['crates'][0]['id'];baseline=self.adapter.apply(private,public,['open',crate]);receipt=self.service.game_action('synthetic','open',public['revision'],['open',crate])
        with self.service.connect()as db:self.assertEqual(bytes(db.execute('SELECT private_state FROM games').fetchone()[0]),baseline.private)
        view=self.service.get_state('synthetic');self.assertEqual(view['observation'],sanitize(baseline.public));self.assertEqual(view['revision'],3)
        item=view['observation']['inventory'][0]['id'];receipt=self.service.game_action('synthetic','price',3,['price',item,'50']);self.assertEqual(receipt['revision'],4)
    @unittest.skipUnless(hasattr(os,'fork'),'process crash test needs POSIX')
    def test_real_process_death_before_commit_rolls_back(self):
        def kill(stage):
            if stage=='after_engine':os._exit(77)
        pid=os.fork()
        if pid==0:
            try:Authority(self.root/'authority.sqlite',self.adapter,hook=kill).game_action('synthetic','crash',1,['buy','salvage'])
            finally:os._exit(99)
        _,status=os.waitpid(pid,0);self.assertEqual(os.waitstatus_to_exitcode(status),77);self.assertEqual(self.service.get_state('synthetic')['revision'],1);self.assertIsNone(self.service.get_receipt('synthetic','crash'))
        receipt=self.service.game_action('synthetic','crash',1,['buy','salvage']);self.assertEqual(receipt['revision'],2);self.assertEqual(self.service.get_state('synthetic')['observation']['credits'],212)
    @unittest.skipUnless(hasattr(os,'fork'),'process crash test needs POSIX')
    def test_real_process_death_after_commit_replays_receipt(self):
        def kill(stage):
            if stage=='after_commit':os._exit(78)
        pid=os.fork()
        if pid==0:
            try:Authority(self.root/'authority.sqlite',self.adapter,hook=kill).game_action('synthetic','crash',1,['buy','salvage'])
            finally:os._exit(99)
        _,status=os.waitpid(pid,0);self.assertEqual(os.waitstatus_to_exitcode(status),78);before=self.service.get_state('synthetic');receipt=self.service.game_action('synthetic','crash',1,['buy','salvage']);self.assertEqual(receipt,self.service.get_receipt('synthetic','crash'));self.assertEqual(before,self.service.get_state('synthetic'))
    def test_rejected_official_action_keeps_canonical_state(self):
        before=self.service.get_state('synthetic')
        with self.assertRaisesRegex(Problem,'engine_rejected'):self.service.game_action('synthetic','bad',1,['open','C999'])
        self.assertEqual(before,self.service.get_state('synthetic'));self.assertIsNone(self.service.get_receipt('synthetic','bad'))
    def test_temporary_workspaces_cleaned_after_normal_calls(self):
        self.service.game_action('synthetic','one',1,['buy','salvage']);self.assertEqual(list((self.root/'work').iterdir()),[])

if __name__=='__main__':unittest.main()
