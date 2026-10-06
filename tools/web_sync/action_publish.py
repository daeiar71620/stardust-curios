#!/usr/bin/env python3
"""One chosen official action, then bounded public-only publication; no daemon."""
from __future__ import annotations
import argparse
import base64
import contextlib
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import ssl
import subprocess
import sys
import termios
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from public_projection import sanitize, known_art
from diagnostics import Diagnostics, error_fields

MUTATIONS = {'buy','open','repair','price','sell','accept','decline','offer','collect','replace-collection','upgrade','endday','continue'}
READS = {'status','market','codex','visitors','inspect','preview-offer'}
ID = re.compile(r'[A-Za-z0-9_-]{1,80}\Z')
TRANSIENT = {408,429,500,502,503,504}

class Stop(Exception):
    def __init__(self, code, **details):
        self.code, self.details = code, details
        super().__init__(code)

class HttpProblem(Exception):
    def __init__(self, status):
        self.status = status

class TransientNetwork(Exception):
    def __init__(self, diagnostic_fields=None):
        super().__init__('transient_network')
        self.diagnostic_fields=diagnostic_fields or {'error_class':'transient_network'}

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()

def durable_mkdir(directory):
    directory=Path(directory);missing=[];cursor=directory
    while not cursor.exists(): missing.append(cursor);cursor=cursor.parent
    for new in reversed(missing):
        try: new.mkdir(mode=0o700)
        except FileExistsError: pass
        parent=os.open(new.parent,os.O_RDONLY|os.O_DIRECTORY)
        try: os.fsync(parent)
        finally: os.close(parent)


def request_bytes(payload):
    return json.dumps(payload,ensure_ascii=False,separators=(',', ':'),allow_nan=False).encode()


def atomic_json(path, value):
    path = Path(path)
    durable_mkdir(path.parent)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w', encoding='utf8') as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if temp.exists(): temp.unlink()

def read_json(path):
    if Path(path).is_symlink(): raise Stop('metadata_symlink_forbidden')
    return json.loads(Path(path).read_text(encoding='utf8'))

@contextlib.contextmanager
def game_lock(public_path):
    # Lock identity follows the canonical game, not the caller's outbox or ID.
    fd = os.open(str(public_path) + '.action-publish.lock', os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise Stop('game_busy')
        yield fd
    finally:
        # Close only: inherited engine fd retains the lock if this parent dies.
        os.close(fd)

def validate_config(raw):
    c = dict(raw)
    required = ['site_id','site_url','session_id','session_epoch','observation_version','engine_path','save_path','observation_path','outbox_dir','art_dir','renderer_path','owner_private_verified']
    if any(k not in c for k in required): raise Stop('incomplete_config')
    url = urllib.parse.urlsplit(c['site_url'])
    if url.scheme != 'https' or not url.hostname or not url.hostname.endswith('.chatgpt.site') or url.username or url.password or url.port not in (None,443) or url.path not in ('','/') or url.query or url.fragment: raise Stop('invalid_pinned_site')
    if not isinstance(c['site_id'],str) or not c['site_id'] or c['observation_version'] not in (6,8,9): raise Stop('invalid_scope_metadata')
    if c['owner_private_verified'] is not True or not ID.fullmatch(c['session_id']) or type(c['session_epoch']) is not int or c['session_epoch'] < 1: raise Stop('scope_not_verified')
    c['site_url'] = 'https://' + url.netloc
    for key in ('engine_path','save_path','observation_path','outbox_dir','art_dir','renderer_path'):
        p = Path(c[key]).expanduser()
        if not p.is_absolute(): raise Stop('absolute_paths_required')
        if key in ('save_path','observation_path') and p.is_symlink(): raise Stop('game_path_symlink_forbidden')
        c[key] = p.resolve()
    if c['engine_path'].name != 'engine.py': raise Stop('official_engine_required')
    expected = c['save_path'].with_name('observation.json') if c['save_path']==c['engine_path'].with_name('save.json') else c['save_path'].with_suffix('.observation.json')
    if c['observation_path'] != expected: raise Stop('public_path_mismatch')
    if c['save_path'].exists() and c['observation_path'].exists() and os.path.samefile(c['save_path'], c['observation_path']): raise Stop('private_save_as_observation')
    if c['outbox_dir'] in (c['save_path'].parent, c['engine_path'].parent): raise Stop('separate_outbox_required')
    c['fingerprint'] = digest({k:str(c[k]) for k in ('site_id','site_url','session_id','session_epoch','observation_version','engine_path','save_path','observation_path')})
    c['journal'] = c['outbox_dir'] / c['fingerprint']
    return c

def validate_action(action):
    if not isinstance(action, list) or not action or len(action)>3 or action[0] not in MUTATIONS|READS or any(not isinstance(v,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', v) or v.startswith('-') for v in action): raise Stop('action_not_allowed')
    return action

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): return None

def real_transport(url, token, payload, timeout=20):
    request = urllib.request.Request(url, data=request_bytes(payload), headers={'OAI-Sites-Authorization':'Bearer '+token,'Content-Type':'application/json','X-Stardust-Publisher':'public-observation-v1'}, method='POST')
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=timeout) as response:
            if response.status!=200: raise HttpProblem(response.status)
            try: return json.load(response)
            except (ValueError, UnicodeError): raise Stop('non_json_acknowledgement')
    except urllib.error.HTTPError as exc: raise HttpProblem(exc.code)
    except ssl.SSLError: raise Stop('tls_security_error')
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, ssl.SSLError): raise Stop('tls_security_error')
        if isinstance(exc.reason, (TimeoutError, ConnectionError)): raise TransientNetwork(error_fields(exc.reason))
        if isinstance(exc.reason, socket.gaierror) and exc.reason.errno==socket.EAI_AGAIN: raise TransientNetwork(error_fields(exc.reason))
        if isinstance(exc.reason, OSError) and exc.reason.errno in (errno.ECONNRESET,errno.ETIMEDOUT,errno.ECONNREFUSED,errno.ENETUNREACH): raise TransientNetwork(error_fields(exc.reason))
        raise Stop('network_error_needs_review', **error_fields(exc.reason))
    except (TimeoutError, ConnectionError) as exc: raise TransientNetwork(error_fields(exc))

def official_runner(c, action, lock_fd):
    # Only the official engine reads its private state. This process never does.
    return subprocess.run(['python3',str(c['engine_path']),'--save',str(c['save_path']),*action], cwd=c['engine_path'].parent, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, pass_fds=(lock_fd,), timeout=45, check=False).returncode

def valid_png(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink!=1: return False
    try:
        from PIL import Image
        with Image.open(path) as image:
            if image.format!='PNG': return False
            image.verify()
        return True
    except Exception: return False


def render_known(c, observation, lock_fd):
    # Warm syncs avoid another process. Cache misses remain bounded and inherit
    # the game lock so a killed parent cannot overlap a still-running exporter.
    from export_known_art import cache_ready
    if c['art_dir'].resolve() in {c['observation_path'].parent.resolve(), c['renderer_path'].parent.resolve()}:
        raise Stop('separate_art_directory_required')
    if cache_ready(observation, c['renderer_path'], c['art_dir']):
        return
    subprocess.run([
        sys.executable, str(Path(__file__).with_name('export_known_art.py')),
        '--observation', str(c['observation_path']),
        '--renderer', str(c['renderer_path']), '--output', str(c['art_dir']),
        '--no-preview',
    ], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, pass_fds=(lock_fd,), timeout=45, check=True)

class Controller:
    def __init__(self, config, token, transport=real_transport, runner=official_runner, renderer=render_known, sleeper=time.sleep, diagnostics=None):
        self.c=validate_config(config); self.token=token; self.transport=transport; self.runner=runner; self.renderer=renderer; self.sleep=sleeper
        self.ops=self.c['journal']/'operations'; self.state_path=self.c['journal']/'publication.json'
        self.diagnostics=diagnostics if diagnostics is not None else Diagnostics()
        # A verified activation may receive a newer server epoch. The original
        # config still identifies this game's binding and operation journal.
        self.publication_epoch = self.c['session_epoch']
        self._cache_active = False
        self._pending_cache = None

    @contextlib.contextmanager
    def execution_cache(self):
        """Reuse validated receipts only while this execution owns game_lock."""
        self._cache_active = True
        self._pending_cache = None
        try:
            yield
        finally:
            self._pending_cache = None
            self._cache_active = False
    def observation(self):
        p=self.c['observation_path']
        if p.is_symlink(): raise Stop('public_symlink_forbidden')
        if self.c['save_path'].exists() and p.exists() and os.path.samefile(self.c['save_path'],p): raise Stop('private_save_as_observation')
        out=sanitize(read_json(p))
        if out['version']!=self.c['observation_version']: raise Stop('observation_version_mismatch')
        return out
    def state(self):
        return read_json(self.state_path) if self.state_path.exists() else {}
    def write_op(self, rec, stage, **extra):
        rec.update(extra,stage=stage,updated_at=time.time());atomic_json(self.ops/(rec['operation_id']+'.json'),rec)
        if self._pending_cache is not None:
            self._pending_cache[rec['operation_id']] = rec
    def pending(self):
        if self._cache_active and self._pending_cache is not None:
            return list(self._pending_cache.values())
        paths = sorted(self.ops.glob('*.json')) if self.ops.exists() else []
        records = [read_json(path) for path in paths]
        allowed={'intent','running','uncertain','committed_projection_pending','committed','sync_pending','published','rejected','resolved_committed','resolved_abandoned','resolved_sync_pending'}
        for path, rec in zip(paths, records):
            if not isinstance(rec, dict) or rec.get('schema_version')!=1 or rec.get('config_fingerprint')!=self.c['fingerprint'] or rec.get('stage') not in allowed or not isinstance(rec.get('operation_id'), str) or not ID.fullmatch(rec['operation_id']) or path.stem != rec['operation_id']: raise Stop('invalid_operation_receipt')
        if self._cache_active:
            self._pending_cache = {rec['operation_id']: rec for rec in records}
        return records

    def observe_diagnostic_state(self, observation, published):
        revision=observation['revision']
        self.diagnostics.update(local_public_revision=revision)
        valid=(isinstance(published,dict) and published.get('session_id')==self.c['session_id']
               and type(published.get('session_epoch')) is int and published['session_epoch']>=1
               and type(published.get('revision')) is int and published['revision']>=0
               and all(re.fullmatch(r'[a-f0-9]{64}',str(published.get(k,''))) for k in ('source_hash','server_digest','request_sha256')))
        if not valid:
            self.diagnostics.update(last_ack_revision=None,last_ack_epoch=None,ack_relation='unknown')
        else:
            relation=('different_epoch' if published['session_epoch']!=self.publication_epoch else
                      'same_snapshot' if published['revision']==revision and published['source_hash']==digest(observation) else
                      'older_snapshot' if published['revision']<revision else 'inconsistent')
            self.diagnostics.update(last_ack_revision=published['revision'],last_ack_epoch=published['session_epoch'],ack_relation=relation)
        self.diagnostics.emit('state_observed')

    def observe_optional_diagnostic_state(self, observation):
        """A diagnostic read must never block a recovery that does not need it."""
        self.diagnostics.update(local_public_revision=observation['revision'])
        try:
            published=self.state()
        except Exception as exc:
            self.diagnostics.update(last_ack_revision=None,last_ack_epoch=None,ack_relation='unknown')
            self.diagnostics.emit('state_unavailable',**error_fields(exc))
            return
        self.observe_diagnostic_state(observation,published)

    def execute(self, request):
        self.diagnostics.reset()
        mode=request.get('mode','action'); action=request.get('action')
        self.diagnostics.emit('execution_started',mode=mode if mode in ('action','sync','reconcile') else 'invalid',
                              action_kind=action[0] if isinstance(action,list) and action and action[0] in MUTATIONS|READS else 'none')
        try:
            result=self._execute(request)
            self.diagnostics.emit('execution_finished')
            return {**result,'sync_status':self.diagnostics.status()}
        except BaseException as exc:
            if self.diagnostics.state['publication'] in ('pending','response_received'):
                self.diagnostics.update(publication='failed')
            fields=error_fields(exc)
            if isinstance(exc,Stop):
                fields={'error_class':'guarded_stop'}
                for key in ('error_class','error_errno','http_status'):
                    if key in exc.details: fields[key]=exc.details[key]
            self.diagnostics.emit('execution_stopped',**fields)
            raise

    def record_publication(self, observation, ack, *, request_sha256, art_hashes):
        """Record a verified upload or activation acknowledgement without POST.

        The caller must hold game_lock. Activation callers also hold their
        Site-wide lock and set publication_epoch from the verified activation.
        Nothing here changes the stable game binding or replays an action.
        """
        revision = observation['revision']
        if type(self.publication_epoch) is not int or self.publication_epoch < self.c['session_epoch']:
            raise Stop('invalid_publication_epoch')
        if not isinstance(ack, dict) or ack.get('ok') is not True or ack.get('revision') != revision or ack.get('session_id') != self.c['session_id'] or ack.get('session_epoch') != self.publication_epoch or ack.get('request_sha256') != request_sha256 or not re.fullmatch(r'[a-f0-9]{64}', str(ack.get('digest', ''))) or not re.fullmatch(r'[a-f0-9]{64}', str(request_sha256)):
            raise Stop('publication_ack_scope_mismatch')
        if not isinstance(art_hashes, dict) or set(art_hashes) != known_art(observation) or any(not re.fullmatch(r'[a-f0-9]{64}', str(value)) for value in art_hashes.values()):
            raise Stop('invalid_art_receipt')
        source_hash = digest(observation)
        if digest(self.observation()) != source_hash:
            raise Stop('source_changed_during_publication')
        records = self.pending()
        previous = self.state()
        if previous.get('session_epoch', 0) > self.publication_epoch:
            raise Stop('stale_publication_epoch')
        if previous.get('revision', -1) > revision:
            raise Stop('source_revision_rollback')
        if previous.get('revision') == revision and previous.get('source_hash') != source_hash:
            raise Stop('same_revision_source_conflict')
        if any(rec.get('revision_after', -1) > revision for rec in records):
            raise Stop('projection_refresh_required')
        saved = {'session_id': self.c['session_id'], 'session_epoch': self.publication_epoch,
                 'revision': revision, 'source_hash': source_hash, 'server_digest': ack['digest'],
                 'request_sha256': request_sha256, 'art_hashes': art_hashes,
                 'published_at': ack.get('published_at'), 'acknowledged_at': time.time()}
        self.diagnostics.update(publication='ack_verified_not_recorded')
        self.diagnostics.emit('publication_ack_verified')
        atomic_json(self.state_path, saved)
        self.observe_diagnostic_state(observation,saved)
        self.diagnostics.update(publication='acknowledged')
        self.diagnostics.emit('publication_recorded')
        for rec in records:
            if rec['stage'] in ('committed', 'sync_pending', 'resolved_sync_pending') and rec.get('revision_after', revision+1) <= revision:
                self.write_op(rec, 'published', published_revision=revision)
        return {'ok': True, 'revision': revision, 'verification': 'server_commit_ack'}

    def publish(self, observation):
        if type(self.publication_epoch) is not int or self.publication_epoch < self.c['session_epoch']:
            raise Stop('invalid_publication_epoch')
        previous=self.state(); revision=observation['revision']; source_hash=digest(observation)
        if previous.get('session_epoch', 0) > self.publication_epoch:
            raise Stop('stale_publication_epoch')
        if any(r.get('revision_after',-1)>revision for r in self.pending()): raise Stop('projection_refresh_required')
        if previous.get('revision',-1)>revision: raise Stop('source_revision_rollback')
        if previous.get('revision')==revision and previous.get('source_hash')!=source_hash: raise Stop('same_revision_source_conflict')
        self.diagnostics.update(publication='pending')
        self.diagnostics.emit('publication_preparing')
        try:
            self.renderer(self.c,observation,self.lock_fd)
        except BaseException as exc:
            self.diagnostics.update(publication='failed')
            self.diagnostics.emit('publication_failed',**error_fields(exc))
            raise
        if digest(self.observation())!=source_hash: raise Stop('source_changed_during_preparation')
        hashes={}; artwork={}
        for identity in sorted(known_art(observation)):
            image_path=self.c['art_dir']/(identity+'.png')
            if image_path.is_symlink() or image_path.stat().st_nlink!=1: raise Stop('unsafe_art_file')
            if not valid_png(image_path): raise Stop('invalid_known_png')
            data=image_path.read_bytes()
            if len(data)>300000 or data[:8]!=b'\x89PNG\r\n\x1a\n': raise Stop('invalid_known_png')
            hashes[identity]=hashlib.sha256(data).hexdigest()
            if previous.get('session_epoch') != self.publication_epoch or previous.get('art_hashes',{}).get(identity)!=hashes[identity]: artwork[identity]=base64.b64encode(data).decode()
        play_state='finished' if observation['phase'] in ('week_summary','lost') else 'ready'
        from datetime import datetime,timezone
        payload={'stream_id':'main','session_id':self.c['session_id'],'session_epoch':self.publication_epoch,'play_state':play_state,'source_saved_at':datetime.fromtimestamp(self.c['observation_path'].stat().st_mtime,timezone.utc).isoformat(),'observation':observation,'artwork':artwork}
        self.diagnostics.emit('publication_prepared',new_art_count=len(artwork))
        ack=None
        for attempt in range(3):
            try:
                self.diagnostics.emit('publication_attempt',attempt=attempt+1)
                ack=self.transport(self.c['site_url']+'/api/ingest',self.token,payload)
                self.diagnostics.update(publication='response_received')
                self.diagnostics.emit('publication_ack_received')
                break
            except HttpProblem as exc:
                self.diagnostics.emit('publication_transport_failed',error_class='http_error',http_status=exc.status)
                if exc.status in (401,403): raise Stop('publication_authorization_stop',http_status=exc.status)
                if exc.status not in TRANSIENT: raise Stop('publication_rejected',http_status=exc.status)
                if attempt==2: raise Stop('publication_retry_exhausted',http_status=exc.status)
            except TransientNetwork as exc:
                self.diagnostics.emit('publication_transport_failed',**exc.diagnostic_fields)
                if attempt==2: raise Stop('publication_retry_exhausted')
            if attempt<2: self.sleep(attempt+1)
        result = self.record_publication(observation, ack,
                                        request_sha256=hashlib.sha256(request_bytes(payload)).hexdigest(),
                                        art_hashes=hashes)
        return {**result, 'new_art_count': len(artwork)}
    def _execute(self, request):
        mode=request.get('mode','action'); opid=request.get('operation_id')
        if mode not in ('action','sync','reconcile'): raise Stop('invalid_mode')
        if mode!='sync' and (not isinstance(opid,str) or not ID.fullmatch(opid)): raise Stop('invalid_operation_id')
        with game_lock(self.c['save_path']) as lock_fd, self.execution_cache():
            self.lock_fd=lock_fd
            binding_path=Path(str(self.c['save_path'])+'.action-publish.binding.json')
            binding={'config_fingerprint':self.c['fingerprint'],'journal':str(self.c['journal'])}
            if binding_path.exists():
                if read_json(binding_path)!=binding: raise Stop('game_scope_or_journal_changed')
            else: atomic_json(binding_path,binding)
            records=self.pending()
            committed=[r for r in records if r['stage'] in ('committed','sync_pending','published','resolved_committed','resolved_sync_pending') and r.get('resolution')!='abandoned' and type(r.get('revision_after')) is int and r['revision_after']>=0]
            latest=max(committed,key=lambda r:r['revision_after']) if committed else None
            self.diagnostics.update(last_local_commit_revision=latest['revision_after'] if latest else None,
                                    last_local_commit_basis=('operator_review' if latest.get('resolution_basis')=='operator_review' else 'journal_record') if latest else 'unknown')
            current=None if mode=='reconcile' else self.observation(); published=self.state()
            if current is not None: self.observe_diagnostic_state(current,published)
            if mode in ('sync','reconcile'): self.diagnostics.update(local_action='not_executed')
            if current is not None and published.get('revision',-1)>current['revision']: raise Stop('source_revision_rollback')
            if mode=='sync': return self.publish(current)
            file=self.ops/(opid+'.json'); existing=read_json(file) if file.exists() else None
            if mode=='reconcile':
                if not existing: raise Stop('unknown_operation')
                if existing['stage'] not in ('running','intent','uncertain','committed_projection_pending','committed','sync_pending','resolved_sync_pending'): return {'ok':True,'operation_id':opid,'stage':existing['stage'],'engine_executed':False}
                # Explicit read-only reconciliation refreshes a possibly stale projection.
                if self.runner(self.c,['status'],lock_fd)!=0: raise Stop('status_refresh_failed')
                current=self.observation()
                self.observe_diagnostic_state(current,self.state())
                if existing['stage'] in ('committed','sync_pending','resolved_sync_pending'): return {**self.publish(current),'operation_id':opid,'engine_executed':False,'resolution_basis':existing.get('resolution_basis')}
                resolution=request.get('resolution')
                if resolution not in ('committed','abandoned'):
                    self.write_op(existing,'uncertain',observed_revision=current['revision'])
                    raise Stop('action_outcome_needs_review',operation_id=opid,before_revision=existing['revision_before'],current_revision=current['revision'])
                if resolution=='committed' and existing['action'][0] in MUTATIONS and current['revision']<=existing['revision_before']: raise Stop('projection_refresh_required')
                self.write_op(existing,'resolved_sync_pending',revision_after=current['revision'],resolution=resolution,resolution_basis='operator_review')
                if resolution=='committed':self.diagnostics.update(last_local_commit_revision=current['revision'],last_local_commit_basis='operator_review')
                result=self.publish(current);return {**result,'operation_id':opid,'engine_executed':False,'resolution':resolution,'resolution_basis':'operator_review'}
            action=validate_action(request.get('action')); action_hash=digest(action)
            if existing:
                self.diagnostics.update(local_action='not_executed')
                self.diagnostics.emit('duplicate_suppressed')
                if existing.get('action_hash')!=action_hash: raise Stop('operation_id_reused_for_different_action')
                if existing['stage'] in ('running','intent','uncertain','committed_projection_pending'): raise Stop('action_outcome_needs_review',operation_id=opid,before_revision=existing['revision_before'],current_revision=current['revision'])
                if existing['stage'] in ('committed','sync_pending','resolved_sync_pending'): return {**self.publish(current),'operation_id':opid,'engine_executed':False}
                return {'ok':existing['stage'] not in ('rejected',),'operation_id':opid,'stage':existing['stage'],'engine_executed':False,'revision':existing.get('revision_after'),'resolution_basis':existing.get('resolution_basis')}
            if any(r['stage'] in ('running','intent','uncertain','committed_projection_pending') for r in self.pending()): raise Stop('unresolved_prior_action')
            # Bring any prior committed state up to date before another action.
            if published.get('session_epoch') != self.publication_epoch or published.get('revision')!=current['revision'] or published.get('source_hash')!=digest(current): self.publish(current)
            rec={'schema_version':1,'operation_id':opid,'session_id':self.c['session_id'],'session_epoch':self.c['session_epoch'],'config_fingerprint':self.c['fingerprint'],'action':action,'action_hash':action_hash,'revision_before':current['revision'],'created_at':time.time()}
            self.write_op(rec,'intent');self.write_op(rec,'running')
            self.diagnostics.update(local_action='unknown')
            self.diagnostics.emit('engine_started',action_kind=action[0])
            try: code=self.runner(self.c,action,lock_fd)
            except BaseException as exc:
                self.diagnostics.emit('engine_failed',**error_fields(exc))
                self.write_op(rec,'uncertain');raise Stop('action_outcome_needs_review',operation_id=opid)
            self.diagnostics.emit('engine_returned',exit_code=code)
            if code!=0 and (action[0] in MUTATIONS or code!=2):
                self.write_op(rec,'uncertain',exit_code=code);raise Stop('action_outcome_needs_review',operation_id=opid)
            if code==2:
                self.diagnostics.update(local_action='rejected')
                self.write_op(rec,'rejected',exit_code=code);return {'ok':False,'operation_id':opid,'stage':'rejected','engine_executed':True,'exit_code':code}
            try: after=self.observation()
            except Exception as exc:
                self.diagnostics.emit('projection_failed',**error_fields(exc))
                self.write_op(rec,'committed_projection_pending');raise Stop('projection_refresh_required',operation_id=opid)
            expected=current['revision']+(1 if action[0] in MUTATIONS else 0)
            if after['revision']!=expected:
                self.write_op(rec,'committed_projection_pending',observed_revision=after['revision']);raise Stop('projection_or_concurrent_action_needs_review',operation_id=opid)
            self.write_op(rec,'committed',revision_after=after['revision'],source_hash=digest(after))
            self.diagnostics.update(local_action='committed',last_local_commit_revision=after['revision'],last_local_commit_basis='journal_record')
            self.observe_diagnostic_state(after,self.state())
            self.diagnostics.emit('engine_committed')
            try: result=self.publish(after)
            except Stop as exc:
                self.diagnostics.update(publication='failed')
                self.diagnostics.emit('publication_failed',error_class=exc.details.get('error_class','guarded_stop'),http_status=exc.details.get('http_status'),error_errno=exc.details.get('error_errno'))
                self.write_op(rec,'sync_pending',sync_error=exc.code);raise Stop(exc.code,operation_id=opid,engine_committed=True,revision=after['revision'],**exc.details)
            return {**result,'operation_id':opid,'engine_executed':True}

def hidden_request():
    original=None
    if sys.stdin.isatty():
        original=termios.tcgetattr(sys.stdin.fileno());modified=termios.tcgetattr(sys.stdin.fileno());modified[3]&=~termios.ECHO;termios.tcsetattr(sys.stdin.fileno(),termios.TCSANOW,modified)
    print('Ready for one authorized operation and existing Site access JSON on hidden stdin.',flush=True)
    try:
        line=sys.stdin.readline(1048577)
        if len(line)>1048576: raise Stop('input_too_large')
        return json.loads(line)
    finally:
        if original is not None: termios.tcsetattr(sys.stdin.fileno(),termios.TCSANOW,original)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',required=True);args=parser.parse_args()
    diagnostics=Diagnostics(stream=sys.stderr)
    try:
        config=read_json(args.config);scope=validate_config(config);diagnostics.preflight(scope['site_url'])
        request=hidden_request();access=request.pop('access',{})
        if access.get('project_id')!=config.get('site_id') or not isinstance(access.get('token'),str) or not access['token']: raise Stop('existing_site_access_required')
        controller=Controller(config,access['token'],diagnostics=diagnostics);access.clear()
        result=controller.execute(request);print(json.dumps(result,ensure_ascii=False),flush=True);return 0 if result.get('ok') else 2
    except Stop as exc:
        diagnostics.emit('execution_stopped',error_class='guarded_stop')
        print(json.dumps({'ok':False,'error':exc.code,**exc.details,'sync_status':diagnostics.status()},ensure_ascii=False),flush=True);return 3
    except Exception as exc:
        diagnostics.emit('execution_stopped',**error_fields(exc))
        # Never echo credential-bearing input, HTTP bodies or engine output.
        print(json.dumps({'ok':False,'error':'unexpected_failure_preserve_receipts_do_not_replay','sync_status':diagnostics.status()}),flush=True);return 4

if __name__=='__main__': raise SystemExit(main())
