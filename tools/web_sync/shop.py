#!/usr/bin/env python3
"""Stable current-shop entry: verified one-command copy/switch, then chosen actions."""
from __future__ import annotations
import argparse
import base64
import contextlib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request
from diagnostics import Diagnostics, error_fields
from action_publish import Controller, Stop, HttpProblem, TransientNetwork, NoRedirect, ID, TRANSIENT, atomic_json, read_json, digest, request_bytes, game_lock, hidden_request, real_transport, validate_config, durable_mkdir


def preflight_scope(pointer_path, target_config=None):
    """Read scope only, before credentials; no locks, mkdir, save or network."""
    pointer=Path(pointer_path).resolve()
    current=read_json(pointer) if pointer.exists() else None
    if current is not None and (current.get('kind')!='stardust_current_shop' or current.get('schema_version')!=1):
        raise Stop('invalid_local_pointer')
    config_path=target_config or (current or {}).get('config_path') or (current or {}).get('target_config')
    if not config_path: raise Stop('target_config_required')
    path=Path(config_path)
    if path.name not in ('config.local.json','config.json') or path.is_symlink(): raise Stop('private_config_path_required')
    config=validate_config(read_json(path))
    if current and current.get('site_id')!=config['site_id']: raise Stop('site_pointer_scope_changed')
    return {'destination':config['site_url'],'pointer_digest':digest(current),'config_fingerprint':config['fingerprint']}


def read_session(c, token):
    request=urllib.request.Request(c['site_url']+'/api/session',headers={'OAI-Sites-Authorization':'Bearer '+token})
    try:
        with urllib.request.build_opener(NoRedirect).open(request,timeout=20) as response:
            value=json.load(response)
    except urllib.error.HTTPError as exc: raise Stop('session_read_failed',http_status=exc.code)
    if value.get('stream_id')!='main' or type(value.get('session_epoch')) is not int or value['session_epoch']<0: raise Stop('invalid_remote_pointer')
    return value


def import_copy(c, source, lock_fds):
    return subprocess.run(['python3',str(c['engine_path']),'--save',str(c['save_path']),'import-v8',str(source)],cwd=c['engine_path'].parent,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,pass_fds=tuple(lock_fds),timeout=45,check=False).returncode


def invariants(o):
    keep={k:o.get(k) for k in ('day','phase','credits','reputation','energy','max_energy','upgrades','stats')}
    for kind in ('inventory','collection','crates'):
        keep[kind]=[{k:r.get(k) for k in ('id','art_id','condition','price','collected','repairs_remaining','sale_attempted_today','repair_attempted_today')} for r in o.get(kind,[])]
    keep['first_week_result']=(o.get('campaign')or{}).get('first_week_result')
    return keep


class Shop:
    def __init__(self,pointer,token,project_id,session_reader=read_session,transport=real_transport,importer=import_copy,controller_factory=Controller,sleeper=time.sleep,diagnostics=None,expected_scope=None):
        self.diagnostics=diagnostics if diagnostics is not None else Diagnostics();self.expected_scope=expected_scope
        self.pointer=Path(pointer).resolve();self.token=token;self.project_id=project_id;self.session_reader=session_reader;self.transport=transport;self.importer=importer;self.controller_factory=controller_factory;self.sleep=sleeper
        if self.pointer.name!='current-shop.json' and not self.pointer.name.endswith('.current-shop.json'):raise Stop('explicit_current_shop_path_required')
        durable_mkdir(self.pointer.parent)
        self.switches=Path(str(self.pointer)+'.switches')
    def current(self):
        if not self.pointer.exists():return None
        p=read_json(self.pointer)
        if p.get('kind')!='stardust_current_shop' or p.get('schema_version')!=1:raise Stop('invalid_local_pointer')
        return p
    def controller(self,config_path,recorded_recovery=False):
        path=Path(config_path)
        if path.name not in ('config.local.json','config.json') or path.is_symlink():raise Stop('private_config_path_required')
        c=self.controller_factory(read_json(path),self.token)
        if c.c['site_id']!=self.project_id:raise Stop('site_access_scope_mismatch')
        if self.expected_scope and (c.c['site_url']!=self.expected_scope['destination'] or (not recorded_recovery and c.c['fingerprint']!=self.expected_scope['config_fingerprint'])):raise Stop('preflight_scope_changed')
        c.diagnostics=self.diagnostics
        return c
    def write_record(self,path,record,stage,**extra):
        record.update(stage=stage,updated_at=time.time(),**extra);atomic_json(path,record)
    def check_ack(self,ack,payload):
        expected_epoch=payload['expected_epoch']+1
        if not isinstance(ack,dict) or ack.get('ok') is not True or ack.get('active') is not True or ack.get('activation_id')!=payload['activation_id'] or ack.get('session_id')!=payload['session_id'] or ack.get('session_epoch')!=expected_epoch or ack.get('revision')!=payload['observation']['revision'] or ack.get('request_sha256')!=hashlib.sha256(request_bytes(payload)).hexdigest():raise Stop('activation_ack_mismatch')
    def post_activation(self,c,payload):
        for attempt in range(3):
            try:
                self.diagnostics.emit('activation_attempt',attempt=attempt+1)
                ack=self.transport(c.c['site_url']+'/api/activate',self.token,payload)
                self.diagnostics.update(publication='response_received');self.diagnostics.emit('activation_ack_received')
                return ack
            except HttpProblem as exc:
                self.diagnostics.emit('activation_transport_failed',error_class='http_error',http_status=exc.status)
                if exc.status in (401,403):raise Stop('activation_authorization_stop',http_status=exc.status)
                if exc.status not in TRANSIENT:raise Stop('activation_rejected',http_status=exc.status)
                if attempt==2:raise Stop('activation_retry_exhausted',http_status=exc.status)
            except TransientNetwork as exc:
                self.diagnostics.emit('activation_transport_failed',**exc.diagnostic_fields)
                if attempt==2:raise Stop('activation_retry_exhausted')
            if attempt<2:self.sleep(attempt+1)
    def active_descriptor(self,c,config_path,record,epoch):
        return {'kind':'stardust_current_shop','schema_version':1,'state':'active','site_id':c.c['site_id'],'site_url':c.c['site_url'],'config_path':str(Path(config_path).resolve()),'session_id':c.c['session_id'],'session_epoch':epoch,'activation_id':record['switch_id'],'save_path':str(c.c['save_path']),'updated_at':time.time()}
    def execute(self,request,target_config=None):
        self.diagnostics.reset()
        mode=request.get('mode','action')
        if mode in ('switch','recover_switch'):self.diagnostics.emit('switch_started',mode=mode)
        try:
            result=self._execute(request,target_config)
            if mode in ('switch','recover_switch'):self.diagnostics.emit('switch_finished',mode=mode)
            return {**result,'sync_status':self.diagnostics.status()}
        except BaseException as exc:
            if self.diagnostics.state['publication'] in ('pending','response_received'):self.diagnostics.update(publication='failed')
            self.diagnostics.emit('switch_stopped' if mode in ('switch','recover_switch') else 'execution_stopped',**error_fields(exc))
            raise
    def _execute(self,request,target_config=None):
        mode=request.get('mode','action')
        with game_lock(self.pointer) as site_fd:
            current=self.current()
            if self.expected_scope and digest(current)!=self.expected_scope['pointer_digest']:raise Stop('preflight_scope_changed')
            if mode not in ('switch','recover_switch'):
                if not current or current.get('state')!='active':raise Stop('shop_switch_not_complete')
                c=self.controller(current['config_path'])
                if current['site_id']!=c.c['site_id'] or current['session_id']!=c.c['session_id']:raise Stop('active_config_mismatch')
                c.publication_epoch=current['session_epoch']
                return c.execute(request)
            switch_id=request.get('switch_id')
            if not isinstance(switch_id,str)or not ID.fullmatch(switch_id):raise Stop('unique_switch_id_required')
            if current and current.get('state')=='switching' and current.get('switch_id')!=switch_id:raise Stop('another_switch_is_pending')
            record_path=self.switches/(switch_id+'.json');record=read_json(record_path)if record_path.exists()else None
            config_path=target_config or (record or {}).get('config_path')
            if not config_path:raise Stop('target_config_required')
            c=self.controller(config_path,recorded_recovery=record is not None and target_config is None)
            if current and current.get('site_id')!=c.c['site_id']:raise Stop('site_pointer_scope_changed')
            copy=request.get('copy_import')
            if copy is not None and (not isinstance(copy,dict) or not {'source_save_path','source_observation_path'}.issubset(copy) or not set(copy).issubset({'source_save_path','source_observation_path','source_engine_path'}) or any(not isinstance(v,str) or not Path(v).is_absolute() for v in copy.values())):raise Stop('explicit_copy_paths_required')
            intent={'config_fingerprint':c.c['fingerprint'],'config_path':str(Path(config_path).resolve()),'copy_import':copy}
            if record:
                # Recovery does not need to repeat private source paths in input.
                if record['config_fingerprint']!=intent['config_fingerprint']or (copy is not None and copy!=record.get('copy_import')):raise Stop('switch_id_reused_for_other_target')
                copy=record.get('copy_import')
                if current and current.get('state')=='active' and current.get('activation_id')==switch_id:return{'ok':True,'idempotent':True,'switched':True,'session_id':current['session_id'],'session_epoch':current['session_epoch'],'verification':'previous_activation_receipt'}
            else:
                record={'schema_version':1,'switch_id':switch_id,**intent,'previous_descriptor':current,'created_at':time.time()}
                self.write_record(record_path,record,'intent')
            with contextlib.ExitStack() as stack:
                # All modern operations hold site lock first, then game lock.
                paths={c.c['save_path']}
                if current and current.get('state')=='active':paths.add(Path(current['save_path']).resolve())
                if copy:
                    source=Path(copy['source_save_path']).resolve();source_public=Path(copy['source_observation_path'])
                    source_engine=Path(copy['source_engine_path']).resolve() if copy.get('source_engine_path') else None
                    expected_public=source.with_name('observation.json') if source_engine and source==source_engine.with_name('save.json') else source.with_suffix('.observation.json')
                    if source==c.c['save_path'] or source_public.is_symlink() or source_public.resolve()!=expected_public or (source.exists() and source_public.exists() and os.path.samefile(source,source_public)):raise Stop('invalid_copy_source')
                    paths.add(source)
                lock_fds=[site_fd];target_fd=None
                for path in sorted(paths,key=str):
                    fd=stack.enter_context(game_lock(path));lock_fds.append(fd)
                    if path==c.c['save_path']:target_fd=fd
                c.lock_fd=target_fd
                if copy and record['stage']=='intent':
                    if c.c['save_path'].exists():raise Stop('copy_destination_already_exists')
                    source_observation=read_json(source_public)
                    if source_observation.get('version')!=8 or c.c['observation_version']!=9:raise Stop('only_explicit_v8_to_v9_copy_supported')
                    self.write_record(record_path,record,'importing',source_invariants=invariants(source_observation))
                    code=self.importer(c.c,source,lock_fds)
                    if code!=0:raise Stop('copy_outcome_uncertain_do_not_repeat')
                    self.write_record(record_path,record,'import_returned')
                elif copy and record['stage']=='importing':
                    if not c.c['save_path'].exists():raise Stop('copy_outcome_uncertain_do_not_repeat')
                    if c.runner(c.c,['status'],target_fd)!=0:raise Stop('copy_status_repair_failed')
                    self.write_record(record_path,record,'import_returned')
                observation=c.observation()
                c.observe_optional_diagnostic_state(observation)
                self.diagnostics.update(local_action='not_executed')
                if copy and record['stage']=='import_returned':
                    if invariants(observation)!=record['source_invariants']or (observation.get('budget_upgrade')or{}).get('from_version')!=8:raise Stop('copy_public_verification_failed')
                    self.write_record(record_path,record,'prepared',candidate_hash=digest(observation),candidate_revision=observation['revision'])
                if not copy and record['stage']=='intent':self.write_record(record_path,record,'prepared',candidate_hash=digest(observation),candidate_revision=observation['revision'])
                if record.get('candidate_hash')!=digest(observation):raise Stop('switch_candidate_changed_needs_review')
                if 'expected_remote' not in record:
                    remote=self.session_reader(c.c,self.token)
                    if current and current.get('state')=='active' and (remote['session_id']!=current['session_id']or remote['session_epoch']!=current['session_epoch']):raise Stop('local_remote_pointer_disagree')
                    self.write_record(record_path,record,'prepared',expected_remote=remote)
                remote_expected=record['expected_remote']
                if mode=='recover_switch':
                    remote=self.session_reader(c.c,self.token)
                    if remote.get('activation_id')==switch_id and remote.get('session_id')==c.c['session_id'] and remote.get('session_epoch')==remote_expected['session_epoch']+1:
                        descriptor=self.active_descriptor(c,config_path,record,remote['session_epoch']);atomic_json(self.pointer,descriptor);self.write_record(record_path,record,'active',activation_epoch=remote['session_epoch']);return{'ok':True,'recovered':True,'session_id':remote['session_id'],'session_epoch':remote['session_epoch'],'verification':'authenticated_current_pointer'}
                    if (remote.get('session_id'),remote.get('session_epoch'))!=(remote_expected.get('session_id'),remote_expected.get('session_epoch')):raise Stop('newer_remote_switch_preserved')
                    # Complete the same pending intent; never repeat import.
                if remote_expected['session_epoch']+1<c.c['session_epoch']:raise Stop('target_epoch_floor_not_reached')
                self.diagnostics.update(publication='pending');self.diagnostics.emit('publication_preparing')
                try:c.renderer(c.c,observation,target_fd)
                except BaseException as exc:
                    self.diagnostics.update(publication='failed');self.diagnostics.emit('publication_failed',**error_fields(exc));raise
                from public_projection import known_art
                from action_publish import valid_png
                artwork={};art_hashes={}
                for identity in sorted(known_art(observation)):
                    path=c.c['art_dir']/(identity+'.png')
                    if not valid_png(path):raise Stop('invalid_activation_art')
                    data=path.read_bytes();artwork[identity]=base64.b64encode(data).decode();art_hashes[identity]=hashlib.sha256(data).hexdigest()
                if digest(c.observation())!=record['candidate_hash']:raise Stop('switch_candidate_changed_needs_review')
                from datetime import datetime,timezone
                payload={'stream_id':'main','activation_id':switch_id,'expected_epoch':remote_expected['session_epoch'],'expected_session_id':remote_expected['session_id'],'session_id':c.c['session_id'],'play_state':'finished'if observation['phase']in('week_summary','lost')else'ready','source_saved_at':datetime.fromtimestamp(c.c['observation_path'].stat().st_mtime,timezone.utc).isoformat(),'observation':observation,'artwork':artwork}
                atomic_json(self.pointer,{'kind':'stardust_current_shop','schema_version':1,'state':'switching','site_id':c.c['site_id'],'site_url':c.c['site_url'],'switch_id':switch_id,'target_config':str(Path(config_path).resolve()),'updated_at':time.time()})
                self.write_record(record_path,record,'activating')
                started=time.monotonic();ack=self.post_activation(c,payload);self.check_ack(ack,payload)
                c.publication_epoch=ack['session_epoch']
                c.record_publication(observation,ack,request_sha256=hashlib.sha256(request_bytes(payload)).hexdigest(),art_hashes=art_hashes)
                descriptor=self.active_descriptor(c,config_path,record,ack['session_epoch']);atomic_json(self.pointer,descriptor)
                self.write_record(record_path,record,'active',activation_epoch=ack['session_epoch'],activated_revision=observation['revision'])
                return{'ok':True,'switched':True,'idempotent':ack.get('idempotent',False),'session_id':ack['session_id'],'session_epoch':ack['session_epoch'],'revision':ack['revision'],'activation_ms':round((time.monotonic()-started)*1000),'verification':'server_activation_ack'}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--current',required=True);parser.add_argument('--target-config');args=parser.parse_args()
    diagnostics=Diagnostics(stream=sys.stderr)
    try:
        scope=preflight_scope(args.current,args.target_config);diagnostics.preflight(scope['destination'])
        request=hidden_request();access=request.pop('access',{})
        if not isinstance(access.get('token'),str)or not access['token']or not isinstance(access.get('project_id'),str):raise Stop('existing_site_access_required')
        shop=Shop(args.current,access['token'],access['project_id'],diagnostics=diagnostics,expected_scope=scope);access.clear();result=shop.execute(request,args.target_config);print(json.dumps(result,ensure_ascii=False),flush=True);return 0 if result.get('ok') else 2
    except Stop as exc:
        diagnostics.emit('execution_stopped',error_class='guarded_stop')
        print(json.dumps({'ok':False,'error':exc.code,**exc.details,'sync_status':diagnostics.status()},ensure_ascii=False),flush=True);return 3
    except Exception as exc:
        diagnostics.emit('execution_stopped',**error_fields(exc))
        print(json.dumps({'ok':False,'error':'switch_or_action_interrupted_preserve_receipts','sync_status':diagnostics.status()}),flush=True);return 4

if __name__=='__main__':raise SystemExit(main())
