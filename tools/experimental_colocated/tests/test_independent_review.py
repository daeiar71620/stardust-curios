"""Independent synthetic-only tests for the colocated prototype. No real saves/network."""
import concurrent.futures
import copy
import json
import multiprocessing
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode=True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from authority import Authority, ArtStore, Candidate, Problem, dispatch, encoded
from public_projection import sanitize

SENTINEL='SYNTHETIC_PRIVATE_SENTINEL_NEVER_PUBLIC'

def public(revision=1):
    return {'version':9,'revision':revision,'day':1,'credits':25,
            'inventory':[{'id':'i1','art_id':'known_art','name':'Known item'}],
            'codex':{'entries':[{'slot':1,'discovered':False,'name':SENTINEL,'art_id':'hidden_art'},
                                {'slot':2,'discovered':True,'name':'Known item','art_id':'known_art'}]},
            'rng_state':SENTINEL,'unknown_future_private_field':{'nested':SENTINEL}}

class SyntheticAdapter:
    identity='synthetic-review-v1'
    def __init__(self): self.calls=0
    def fresh_synthetic(self): return Candidate(encoded({'revision':1,'private_rng':SENTINEL}),public())
    def apply(self,private,public_before,action):
        self.calls+=1
        state=json.loads(private);state['revision']+=1
        return Candidate(encoded(state),public(state['revision']))


def crash_worker(path,failpoint):
    def hook(stage):
        if stage==failpoint: os._exit(83)
    authority=Authority(path,SyntheticAdapter(),hook=hook)
    authority.game_action('game','crash_op',1,['endday'])

class AuthorityReview(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='independent-synthetic-review-')
        self.db=Path(self.temp.name)/'authority.sqlite'
        self.adapter=SyntheticAdapter();self.authority=Authority(self.db,self.adapter)
        self.authority.initialize_synthetic('game')
    def tearDown(self): self.temp.cleanup()
    def test_public_only(self):
        state=self.authority.get_state('game')
        self.assertNotIn(SENTINEL,json.dumps(state))
        self.assertNotIn('rng_state',state['observation'])
        self.assertEqual(state['observation']['codex']['entries'][0],{'slot':1,'discovered':False,'collected':False})
        receipt=self.authority.game_action('game','op1',1,['endday'])
        self.assertNotIn(SENTINEL,json.dumps(receipt))
    def test_duplicate_receipt_precedes_revision_check(self):
        receipt=self.authority.game_action('game','op1',1,['endday'])
        self.authority.game_action('game','op2',2,['endday'])
        self.assertEqual(receipt,self.authority.game_action('game','op1',1,['endday']))
        self.assertEqual(self.adapter.calls,2)
        with self.assertRaises(Problem) as conflict:
            self.authority.game_action('game','op1',1,['continue'])
        self.assertEqual(conflict.exception.code,'operation_id_conflict')
    def test_stale_revision_never_executes(self):
        self.authority.game_action('game','op1',1,['endday'])
        with self.assertRaises(Problem): self.authority.game_action('game','op2',1,['endday'])
        self.assertEqual(self.adapter.calls,1)
    def test_concurrent_distinct_ids(self):
        def call(op):
            try:return self.authority.game_action('game',op,1,['endday'])['revision']
            except Problem as e:return e.code
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(call,['left','right']))
        self.assertCountEqual(results,[2,'revision_conflict'])
        self.assertEqual(self.adapter.calls,1)
    def test_concurrent_same_id(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.authority.game_action('game','same',1,['endday']),range(2)))
        self.assertEqual(results[0],results[1]);self.assertEqual(self.adapter.calls,1)
    def test_actual_process_death_before_commit(self):
        child=multiprocessing.get_context('fork').Process(target=crash_worker,args=(self.db,'before_commit'))
        child.start();child.join(10);self.assertEqual(child.exitcode,83)
        self.assertEqual(self.authority.get_state('game')['revision'],1)
        self.assertIsNone(self.authority.get_receipt('game','crash_op'))
        self.assertEqual(self.authority.game_action('game','crash_op',1,['endday'])['revision'],2)
    def test_actual_process_death_after_commit(self):
        child=multiprocessing.get_context('fork').Process(target=crash_worker,args=(self.db,'after_commit'))
        child.start();child.join(10);self.assertEqual(child.exitcode,83)
        receipt=self.authority.get_receipt('game','crash_op')
        self.assertEqual(self.authority.get_state('game')['revision'],2)
        self.assertEqual(receipt,self.authority.game_action('game','crash_op',1,['endday']))
        self.assertEqual(self.adapter.calls,0)
    def test_read_connections_close_promptly(self):
        import gc
        gc.collect();gc.disable()
        try:
            before=len(os.listdir('/proc/self/fd'))
            for _ in range(20):self.authority.get_state('game');self.authority.get_receipt('game','none')
            after=len(os.listdir('/proc/self/fd'))
            self.assertLessEqual(after-before,3)
        finally:gc.enable();gc.collect()
    def test_image_limits_and_known_ids(self):
        import io
        from PIL import Image
        buf=io.BytesIO();Image.new('RGB',(8,8),'blue').save(buf,format='PNG');png=buf.getvalue()
        store=ArtStore(Path(self.temp.name)/'art')
        refs=store.stage(sanitize(public()),{'known_art':png})
        self.assertEqual(store.read(refs['known_art']),png)
        cases=[({'hidden_art':png},'unknown_art_forbidden'),
               ({'known_art':b'x'*(store.MAX_FILE+1)},'art_byte_limit'),
               ({'known_art':b'invalid'},'invalid_art'),
               ({str(i):png for i in range(25)},'art_count_limit')]
        for art,error in cases:
            with self.subTest(error=error):
                with self.assertRaises(Problem) as caught:store.stage(sanitize(public()),art)
                self.assertEqual(caught.exception.code,error)
        big=io.BytesIO();Image.new('RGB',(513,1),'blue').save(big,format='PNG')
        with self.assertRaises(Problem):store.stage(sanitize(public()),{'known_art':big.getvalue()})
    def test_image_failure_still_commits_text_without_images(self):
        store=ArtStore(Path(self.temp.name)/'art')
        authority=Authority(self.db,self.adapter,art_store=store,art_provider=lambda public:{'hidden_art':b'invalid'})
        receipt=authority.game_action('game','withbadart',1,['endday'])
        self.assertEqual(receipt['art_status'],'placeholder')
        self.assertEqual(authority.get_state('game')['revision'],2)
        self.assertEqual(authority.get_state('game')['images'],{})
    def test_art_provider_cannot_mutate_canonical_public(self):
        def provider(public):
            public['revision']=999
            public['inventory'].append({'art_id':'hidden_art','name':SENTINEL})
            return {}
        authority=Authority(self.db,self.adapter,art_store=ArtStore(Path(self.temp.name)/'art'),art_provider=provider)
        receipt=authority.game_action('game','artmutation',1,['endday'])
        state=authority.get_state('game')
        self.assertEqual(receipt['revision'],2)
        self.assertEqual(state['revision'],state['observation']['revision'])
        self.assertNotIn(SENTINEL,json.dumps(state))
    def test_malformed_action_has_stable_error(self):
        status,result=dispatch(self.authority,'POST','/game/action',{'game_id':'game','operation_id':'bad','expected_revision':1,'action':[[]]})
        self.assertEqual(status,422);self.assertFalse(result['ok'])
    def test_invalid_candidate_has_stable_error_and_rolls_back(self):
        def invalid(*args): return Candidate(encoded({'synthetic':True}),{'version':9,'day':1,'revision':True})
        self.adapter.apply=invalid
        status,result=dispatch(self.authority,'POST','/game/action',{'game_id':'game','operation_id':'badcandidate','expected_revision':1,'action':['endday']})
        self.assertGreaterEqual(status,400);self.assertFalse(result['ok'])
        self.assertEqual(self.authority.get_state('game')['revision'],1)
        self.assertIsNone(self.authority.get_receipt('game','badcandidate'))

if __name__=='__main__':unittest.main(verbosity=2)
