"""Synthetic-only diagnostic and preflight regressions; no production network."""
import contextlib
import io
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import action_publish
import shop
from action_publish import Controller, Stop, HttpProblem, TransientNetwork, atomic_json
from diagnostics import Diagnostics, error_fields
import test_controller as controller_fixtures
import test_shop as shop_fixtures

SECRET='canary-secret-never-print'

class DiagnosticTests(unittest.TestCase):
    runner=controller_fixtures.Harness.runner; renderer=controller_fixtures.Harness.renderer; transport=controller_fixtures.Harness.transport
    sync=controller_fixtures.Harness.sync; action=controller_fixtures.Harness.action
    def setUp(self):
        controller_fixtures.Harness.setUp(self);self.output=io.StringIO();self.trace=Diagnostics(self.output)
    tearDown=controller_fixtures.Harness.tearDown
    def make(self,**kwargs):
        c=controller_fixtures.Harness.make(self,**kwargs);c.diagnostics=self.trace;return c
    def events(self):return [json.loads(line) for line in self.output.getvalue().splitlines()]
    def assert_redacted(self):
        text=self.output.getvalue()
        for forbidden in [SECRET,str(self.root),'memory-only-token','never-send','HIDDEN','game.json','secret_seed']:
            self.assertNotIn(forbidden,text)
    def test_success_has_ordered_stages_and_durable_status(self):
        c=self.make();self.sync(c);self.output.truncate(0);self.output.seek(0)
        result=self.action(c);events=self.events();names=[e['event'] for e in events]
        for earlier,later in [('engine_started','engine_committed'),('engine_committed','publication_attempt'),('publication_ack_received','publication_ack_verified'),('publication_ack_verified','publication_recorded')]:
            self.assertLess(names.index(earlier),names.index(later))
        status=result['sync_status'];self.assertEqual(status['local_action'],'committed');self.assertEqual(status['last_local_commit_revision'],2)
        self.assertEqual(status['last_ack_revision'],2);self.assertEqual(status['ack_relation'],'same_snapshot');self.assertEqual(status['publication'],'acknowledged')
        self.assertEqual(status['live_sync_state'],'not_asserted')
        self.assertEqual([e['elapsed_ms'] for e in events],sorted(e['elapsed_ms'] for e in events));self.assert_redacted()
    def test_pre_action_auth_rejection_is_no_execution_and_single_attempt(self):
        c=self.make();self.responses=[HttpProblem(403)]
        with self.assertRaises(Stop):self.action(c)
        self.assertEqual(self.calls,[]);self.assertEqual(len(self.posts),1)
        status=self.trace.status();self.assertEqual(status['local_action'],'not_started');self.assertEqual(status['publication'],'failed');self.assertIsNone(status['last_ack_revision'])
    def test_sync_only_denial_sets_failed_without_engine(self):
        c=self.make();self.responses=[HttpProblem(401)]
        with self.assertRaises(Stop):self.sync(c)
        self.assertEqual(self.trace.status()['local_action'],'not_executed');self.assertEqual(self.trace.status()['publication'],'failed');self.assertEqual(self.calls,[]);self.assertEqual(len(self.posts),1)
    def test_committed_but_unsynced_status_and_duplicate_recovery(self):
        c=self.make();self.sync(c);self.responses=[HttpProblem(403)]
        with self.assertRaises(Stop):self.action(c)
        status=self.trace.status();self.assertEqual(status['last_local_commit_revision'],2);self.assertEqual(status['last_ack_revision'],1);self.assertEqual(status['ack_relation'],'older_snapshot')
        result=self.action(self.make());self.assertFalse(result['engine_executed']);self.assertEqual(len(self.calls),1)
        self.assertEqual(result['sync_status']['local_action'],'not_executed');self.assertEqual(result['sync_status']['last_local_commit_revision'],2)
        self.assertIn('duplicate_suppressed',[e['event'] for e in self.events()]);self.assert_redacted()
    def test_published_duplicate_keeps_commit_without_second_engine(self):
        c=self.make();self.action(c);result=self.action(c)
        self.assertEqual(result['sync_status']['last_local_commit_revision'],2);self.assertEqual(result['sync_status']['ack_relation'],'same_snapshot');self.assertEqual(len(self.calls),1)
    def test_uncertain_engine_timeout_never_claims_commit(self):
        def timeout(*args):raise subprocess.TimeoutExpired([SECRET,str(self.root)],45,output=SECRET)
        c=self.make(runner=timeout);self.sync(c)
        with self.assertRaises(Stop):self.action(c)
        self.assertEqual(self.trace.status()['local_action'],'unknown');self.assertIsNone(self.trace.status()['last_local_commit_revision'])
        event=[e for e in self.events() if e['event']=='engine_failed'][-1];self.assertEqual(event['error_class'],'timeout');self.assert_redacted()
    def test_projection_failure_after_engine_is_unknown_not_replayed(self):
        def broken(cfg,action,fd):self.runner(cfg,action,fd);self.public.write_text(SECRET);return 0
        c=self.make(runner=broken);self.sync(c)
        with self.assertRaises(Stop):self.action(c)
        self.assertEqual(self.trace.status()['local_action'],'unknown');self.assertIsNone(self.trace.status()['last_local_commit_revision'])
        self.assertEqual([e for e in self.events() if e['event']=='projection_failed'][-1]['error_class'],'json_error');self.assert_redacted()
    def test_renderer_timeout_after_commit_retains_local_fact(self):
        c=self.make();self.sync(c)
        def broken(*args):raise subprocess.TimeoutExpired(SECRET,45)
        c.renderer=broken
        with self.assertRaises(subprocess.TimeoutExpired):self.action(c)
        status=self.trace.status();self.assertEqual(status['last_local_commit_revision'],2);self.assertEqual(status['last_ack_revision'],1);self.assertEqual(status['publication'],'failed')
        self.assertEqual(json.loads((c.ops/'op1.json').read_text())['stage'],'committed')
        c.renderer=self.renderer;self.action(c);self.assertEqual(len(self.calls),1);self.assert_redacted()
    def test_ack_mismatch_is_failed_not_acknowledged(self):
        c=self.make();self.responses=[{'ok':True,'revision':1,'session_id':'wrong','session_epoch':3,'digest':'a'*64,'request_sha256':'b'*64}]
        with self.assertRaises(Stop):self.sync(c)
        self.assertEqual(self.trace.status()['publication'],'failed');self.assertIsNone(self.trace.status()['last_ack_revision'])
    def test_ack_verified_but_local_write_failure_keeps_last_durable_ack(self):
        c=self.make();self.sync(c);original=action_publish.atomic_json
        def fail(path,value):
            if Path(path)==c.state_path:raise OSError(5,SECRET,str(self.root))
            return original(path,value)
        with patch.object(action_publish,'atomic_json',side_effect=fail):
            with self.assertRaises(OSError):self.action(c)
        status=self.trace.status();self.assertEqual(status['publication'],'ack_verified_not_recorded');self.assertEqual(status['last_ack_revision'],1);self.assertEqual(status['last_local_commit_revision'],2)
        self.assertNotIn('publication_recorded',[e['event'] for e in self.events() if e.get('last_local_commit_revision')==2]);self.assert_redacted()
    def test_corrupt_receipt_stops_before_action_and_does_not_leak(self):
        c=self.make();self.action(c);(c.ops/'op1.json').write_text(SECRET)
        with self.assertRaises(json.JSONDecodeError):self.action(c,op='second')
        self.assertEqual(len(self.calls),1);self.assertIsNone(self.trace.status()['last_local_commit_revision']);self.assert_redacted()
    def test_bad_scope_receipt_does_not_report_synced(self):
        c=self.make();self.sync(c);receipt=c.state();receipt['session_id']='foreign';atomic_json(c.state_path,receipt)
        self.responses=[HttpProblem(403)]
        with self.assertRaises(Stop):self.sync(c)
        self.assertIsNone(self.trace.status()['last_ack_revision']);self.assertEqual(self.trace.status()['ack_relation'],'unknown')
    def test_previous_epoch_is_not_same_snapshot(self):
        c=self.make();self.sync(c);c.publication_epoch=4;self.responses=[HttpProblem(403)]
        with self.assertRaises(Stop):self.sync(c)
        self.assertEqual(self.trace.status()['ack_relation'],'different_epoch');self.assertEqual(self.trace.status()['last_ack_epoch'],3)
    def test_committed_reconciliation_preserves_operator_review_basis(self):
        c=self.make();self.sync(c)
        def interrupted(cfg,action,fd):self.runner(cfg,action,fd);raise RuntimeError(SECRET)
        with self.assertRaises(Stop):self.action(self.make(runner=interrupted))
        result=c.execute({'mode':'reconcile','operation_id':'op1','resolution':'committed'})
        self.assertEqual(result['sync_status']['last_local_commit_revision'],2)
        self.assertEqual(result['sync_status']['last_local_commit_basis'],'operator_review')
        self.assertEqual(result['sync_status']['local_action'],'not_executed')
        self.assertEqual(result['resolution_basis'],'operator_review');self.assert_redacted()
    def test_abandoned_reconciliation_does_not_claim_a_commit(self):
        c=self.make();self.sync(c)
        def interrupted(cfg,action,fd):self.runner(cfg,action,fd);raise RuntimeError(SECRET)
        with self.assertRaises(Stop):self.action(self.make(runner=interrupted))
        result=c.execute({'mode':'reconcile','operation_id':'op1','resolution':'abandoned'})
        self.assertIsNone(result['sync_status']['last_local_commit_revision'])
        again=self.sync(self.make());self.assertIsNone(again['sync_status']['last_local_commit_revision'])
        self.assertEqual(again['sync_status']['last_local_commit_basis'],'unknown');self.assert_redacted()
    def test_transient_error_budget_unchanged(self):
        c=self.make();self.sync(c);before=len(self.posts);self.responses=[TransientNetwork({'error_class':'timeout'})]*3
        with self.assertRaises(Stop):self.action(c)
        self.assertEqual(len(self.posts)-before,3);self.assertEqual(len(self.calls),1)
        self.assertEqual([e['error_class'] for e in self.events() if e['event']=='publication_transport_failed'],['timeout']*3)
    def test_unknown_review_error_is_not_retried_or_logged_raw(self):
        c=self.make();self.sync(c);before=len(self.posts);self.responses=[RuntimeError(SECRET+' automatic approval review was cancelled')]
        with self.assertRaises(RuntimeError):self.action(c)
        self.assertEqual(len(self.posts)-before,1);self.assertEqual(len(self.calls),1);self.assert_redacted()
        self.assertEqual(self.events()[-1]['error_class'],'unexpected_error')
    def test_broken_sink_cannot_change_action_or_retries(self):
        class Broken:
            def write(self,*a):raise OSError(5,SECRET)
            def flush(self):raise RuntimeError(SECRET)
        c=self.make();c.diagnostics=Diagnostics(Broken());result=self.action(c);self.assertTrue(result['ok']);self.assertEqual(len(self.calls),1)
        again=self.action(c);self.assertFalse(again['engine_executed']);self.assertEqual(len(self.calls),1)
    def test_fields_are_allowlisted_and_error_strings_ignored(self):
        exc=type(SECRET,(Exception,),{})(SECRET)
        self.trace.emit('publication_failed',**error_fields(exc),payload=SECRET,token=SECRET,private_path=str(self.root),operation_id=SECRET)
        self.assertEqual(self.events()[-1]['error_class'],'unexpected_error');self.assert_redacted()
    def test_legacy_preflight_before_input_has_no_io_side_effects(self):
        config_path=self.root/'config.local.json';atomic_json(config_path,self.config);before=set(self.root.rglob('*'))
        stdout=io.StringIO();stderr=io.StringIO()
        def no_input():
            event=json.loads(stderr.getvalue().splitlines()[0]);self.assertEqual(event['event'],'preflight_scope');self.assertEqual(event['destination'],self.config['site_url']);self.assertFalse(event['private_save_upload'])
            self.assertEqual(set(self.root.rglob('*')),before)
            raise ValueError(SECRET)
        with patch.object(sys,'argv',['action_publish','--config',str(config_path)]),patch.object(action_publish,'hidden_request',side_effect=no_input),contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr):
            self.assertEqual(action_publish.main(),4)
        self.assertNotIn(SECRET,stdout.getvalue()+stderr.getvalue());self.assertNotIn(str(self.root),stdout.getvalue()+stderr.getvalue())

class ShopDiagnosticTests(unittest.TestCase):
    setUp=shop_fixtures.Tests.setUp;tearDown=shop_fixtures.Tests.tearDown;prepare=shop_fixtures.Tests.prepare
    runner=shop_fixtures.Tests.runner;factory=shop_fixtures.Tests.factory;importer=shop_fixtures.Tests.importer
    shop=shop_fixtures.Tests.shop;switch=shop_fixtures.Tests.switch
    def test_preflight_has_no_persistent_effect_and_detects_pointer_change(self):
        before=set(self.root.rglob('*'));scope=shop.preflight_scope(self.pointer,self.config_path);self.assertEqual(set(self.root.rglob('*')),before)
        self.switch()
        target=self.shop();target.expected_scope=scope
        with self.assertRaises(Stop) as error:target.execute({'mode':'switch','switch_id':'s2'},self.config_path)
        self.assertEqual(error.exception.code,'preflight_scope_changed');self.assertEqual(self.actions,0)
    def test_config_change_after_preflight_is_rejected_before_action(self):
        self.switch();scope=shop.preflight_scope(self.pointer);changed=dict(self.config);changed['site_url']='https://changed-test.chatgpt.site';atomic_json(self.config_path,changed)
        target=self.shop();target.expected_scope=scope;before=self.server.posts
        with self.assertRaises(Stop) as error:target.execute({'operation_id':'op1','action':['buy','salvage']})
        self.assertEqual(error.exception.code,'preflight_scope_changed');self.assertEqual(self.actions,0);self.assertEqual(self.server.posts,before)
    def test_activation_auth_failure_has_failed_status(self):
        target=self.shop();target.diagnostics=Diagnostics(io.StringIO());self.server.errors=[HttpProblem(403)]
        with self.assertRaises(Stop):target.execute({'mode':'switch','switch_id':'s1'},self.config_path)
        self.assertEqual(target.diagnostics.status()['publication'],'failed');self.assertEqual(self.server.posts,1)
    def test_pending_switch_recovery_does_not_claim_live_continuous_sync(self):
        self.server.die_after_commit=True
        with self.assertRaises(SystemExit):self.switch()
        scope=shop.preflight_scope(self.pointer);target=self.shop();target.expected_scope=scope
        result=target.execute({'mode':'recover_switch','switch_id':'s1'})
        self.assertTrue(result['recovered']);self.assertEqual(result['sync_status']['live_sync_state'],'not_asserted');self.assertEqual(self.actions,0)
    def test_shop_preflight_before_input_is_safe(self):
        stdout=io.StringIO();stderr=io.StringIO();before=set(self.root.rglob('*'))
        def no_input():
            self.assertEqual(json.loads(stderr.getvalue().splitlines()[0])['destination'],self.config['site_url'])
            self.assertEqual(set(self.root.rglob('*')),before);raise ValueError(SECRET)
        with patch.object(sys,'argv',['shop','--current',str(self.pointer),'--target-config',str(self.config_path)]),patch.object(shop,'hidden_request',side_effect=no_input),contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr):
            self.assertEqual(shop.main(),4)
        self.assertNotIn(SECRET,stdout.getvalue()+stderr.getvalue());self.assertNotIn(str(self.root),stdout.getvalue()+stderr.getvalue())

if __name__=='__main__':unittest.main()
