"""LOCAL SYNTHETIC PROTOTYPE. No HTTP listener, authentication or deployment.

The DB is the authority. CLI files are disposable transaction workspaces.
A canonical commit is idempotent; speculative CLI execution is not exactly-once.
"""
from __future__ import annotations
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile
import time
from dataclasses import dataclass
from public_projection import sanitize, known_art

ID = re.compile(r'[A-Za-z0-9_-]{1,80}\Z')
MUTATIONS = {'buy','open','repair','price','sell','accept','decline','offer','collect','replace-collection','upgrade','endday','continue'}


def encoded(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Problem(Exception):
    def __init__(self,code,status=409):
        super().__init__(code);self.code=code;self.status=status


@dataclass(frozen=True)
class Candidate:
    private: bytes
    public: dict


class CLIAdapter:
    """Only official CLI interprets opaque private bytes; no real saves accepted."""
    def __init__(self,engine_path,sandbox_root,timeout=20):
        self.engine=Path(engine_path).resolve();self.sandbox=Path(sandbox_root).resolve();self.timeout=timeout
        self.sandbox.mkdir(parents=True,exist_ok=True)
        self.identity=self.fingerprint()
    def fingerprint(self):
        paths=[self.engine,*sorted(self.engine.parent.glob('_legacy_v*.py'))]
        return sha(b''.join(p.name.encode()+b'\0'+p.read_bytes()+b'\0' for p in paths))
    def _run(self,directory,action):
        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
        try:
            result=subprocess.run(['python3',str(self.engine),'--save',str(directory/'working.json'),*action],cwd=directory,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,timeout=self.timeout,check=False)
        except subprocess.TimeoutExpired:raise Problem('engine_timeout',503) from None
        if result.returncode!=0:raise Problem('engine_rejected',422)
    def _candidate(self,directory):
        return Candidate((directory/'working.json').read_bytes(),json.loads((directory/'working.observation.json').read_text()))
    def fresh_synthetic(self):
        with tempfile.TemporaryDirectory(prefix='synthetic-new-',dir=self.sandbox) as name:
            path=Path(name);self._run(path,['new']);return self._candidate(path)
    def apply(self,private,public,action):
        if self.fingerprint()!=self.identity:raise Problem('engine_source_changed')
        with tempfile.TemporaryDirectory(prefix='speculative-action-',dir=self.sandbox) as name:
            path=Path(name);(path/'working.json').write_bytes(private)
            (path/'working.observation.json').write_bytes(encoded(public))
            self._run(path,action)
            observation=path/'working.observation.json'
            if not observation.exists() or json.loads(observation.read_text()).get('revision')!=public['revision']+1:
                # Repairs only the disposable projection; never repeats the action.
                self._run(path,['status'])
            return self._candidate(path)


class ArtStore:
    """Optional local analogue of pre-staged R2 objects, NOT part of DB transaction."""
    MAX_COUNT=24;MAX_FILE=512*1024;MAX_TOTAL=8*1024*1024;MAX_DIMENSION=512
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
    def stage(self,public,artwork):
        if not isinstance(artwork,dict) or len(artwork)>self.MAX_COUNT:raise Problem('art_count_limit',422)
        if not set(artwork).issubset(known_art(public)):raise Problem('unknown_art_forbidden',422)
        total=0;validated=[]
        from PIL import Image
        for identity,data in artwork.items():
            if not isinstance(data,bytes) or len(data)>self.MAX_FILE:raise Problem('art_byte_limit',422)
            total+=len(data)
            if total>self.MAX_TOTAL:raise Problem('art_total_limit',422)
            try:
                with Image.open(io.BytesIO(data)) as im:
                    if im.format!='PNG' or min(im.size)<1 or max(im.size)>self.MAX_DIMENSION:raise ValueError()
                    im.verify()
            except Exception:raise Problem('invalid_art',422) from None
            validated.append((identity,sha(data),data))
        refs={}
        for identity,digest,data in validated:
            path=self.root/(digest+'.png')
            # Content-addressed, immutable writes. Orphans are harmless but need GC.
            if path.exists():
                if sha(path.read_bytes())!=digest:raise Problem('art_store_corrupt',503)
            else:
                fd,temp=tempfile.mkstemp(prefix='staged-',dir=self.root)
                try:
                    with os.fdopen(fd,'wb') as out:out.write(data);out.flush();os.fsync(out.fileno())
                    os.replace(temp,path)
                    directory_fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY)
                    try:os.fsync(directory_fd)
                    finally:os.close(directory_fd)
                finally:
                    if os.path.exists(temp):os.unlink(temp)
            refs[identity]=digest
        return refs
    def read(self,digest):
        if not re.fullmatch(r'[a-f0-9]{64}',digest):return None
        path=self.root/(digest+'.png')
        if not path.exists():return None
        data=path.read_bytes();return data if sha(data)==digest else None


class Authority:
    def __init__(self,db_path,adapter,*,art_store=None,art_provider=None,hook=None):
        self.db=Path(db_path);self.adapter=adapter;self.art_store=art_store;self.art_provider=art_provider;self.hook=hook or (lambda stage:None)
        self.db.parent.mkdir(parents=True,exist_ok=True)
        with contextlib.closing(self.connect()) as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
            CREATE TABLE IF NOT EXISTS games(
                game_id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
                engine_identity TEXT NOT NULL, private_state BLOB NOT NULL,
                public_json BLOB NOT NULL, state_hash TEXT NOT NULL,
                art_json BLOB NOT NULL, committed_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS operations(
                game_id TEXT NOT NULL, operation_id TEXT NOT NULL,
                request_hash TEXT NOT NULL, receipt_json BLOB NOT NULL,
                PRIMARY KEY(game_id,operation_id));
            ''')
    def connect(self):
        db=sqlite3.connect(self.db,timeout=5,isolation_level=None)
        db.row_factory=sqlite3.Row;db.execute('PRAGMA synchronous=FULL');db.execute('PRAGMA busy_timeout=5000');return db
    def initialize_synthetic(self,game_id):
        if not isinstance(game_id,str)or not ID.fullmatch(game_id):raise Problem('invalid_game_id',422)
        candidate=self.adapter.fresh_synthetic();public=sanitize(candidate.public)
        with contextlib.closing(self.connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                db.execute('INSERT INTO games VALUES(?,?,?,?,?,?,?,?)',(game_id,public['revision'],self.adapter.identity,candidate.private,encoded(public),sha(encoded(public)),encoded({}),time.time()))
                db.commit()
            except sqlite3.IntegrityError:db.rollback();raise Problem('game_already_exists') from None
        return self.get_state(game_id)
    def get_state(self,game_id):
        # One SELECT is one consistent public state. Never SELECT private_state here.
        with contextlib.closing(self.connect()) as db:
            row=db.execute('SELECT revision,public_json,state_hash,art_json,committed_at FROM games WHERE game_id=?',(game_id,)).fetchone()
        if row is None:raise Problem('game_not_found',404)
        return {'game_id':game_id,'revision':row['revision'],'state_hash':row['state_hash'],'observation':json.loads(row['public_json']),'images':json.loads(row['art_json']),'committed_at':row['committed_at']}
    def get_art(self,game_id,identity):
        state=self.get_state(game_id)
        if identity not in known_art(state['observation']):raise Problem('art_not_found',404)
        digest=state['images'].get(identity)
        data=self.art_store.read(digest) if digest and self.art_store else None
        if data is None:raise Problem('art_not_found',404)
        return data
    def get_receipt(self,game_id,operation_id):
        with contextlib.closing(self.connect()) as db:
            row=db.execute('SELECT receipt_json FROM operations WHERE game_id=? AND operation_id=?',(game_id,operation_id)).fetchone()
        return json.loads(row[0]) if row else None
    def game_action(self,game_id,operation_id,expected_revision,action):
        if not isinstance(game_id,str)or not ID.fullmatch(game_id)or not isinstance(operation_id,str)or not ID.fullmatch(operation_id):raise Problem('invalid_operation_scope',422)
        if type(expected_revision)is not int or expected_revision<1:raise Problem('invalid_revision',422)
        if not isinstance(action,list)or not 1<=len(action)<=3 or any(not isinstance(v,str)or not ID.fullmatch(v)or v.startswith('-')for v in action) or action[0]not in MUTATIONS:raise Problem('action_not_allowed',422)
        fingerprint=sha(encoded({'game_id':game_id,'operation_id':operation_id,'expected_revision':expected_revision,'action':action}))
        db=self.connect();committed=False
        try:
            try:db.execute('BEGIN IMMEDIATE')
            except sqlite3.OperationalError:raise Problem('authority_busy',503) from None
            prior=db.execute('SELECT request_hash,receipt_json FROM operations WHERE game_id=? AND operation_id=?',(game_id,operation_id)).fetchone()
            if prior:
                if prior['request_hash']!=fingerprint:raise Problem('operation_id_conflict')
                receipt=json.loads(prior['receipt_json']);db.rollback();return receipt
            row=db.execute('SELECT * FROM games WHERE game_id=?',(game_id,)).fetchone()
            if row is None:raise Problem('game_not_found',404)
            if row['revision']!=expected_revision:raise Problem('revision_conflict')
            if row['engine_identity']!=self.adapter.identity:raise Problem('engine_identity_conflict')
            before=json.loads(row['public_json']);self.hook('before_engine')
            candidate=self.adapter.apply(bytes(row['private_state']),before,action);self.hook('after_engine')
            try:public=sanitize(candidate.public)
            except (ValueError,TypeError):raise Problem('invalid_public_candidate',500) from None
            if public.get('version')!=before.get('version')or public['revision']!=expected_revision+1:raise Problem('candidate_revision_invalid')
            raw=encoded(public);state_hash=sha(raw);known=known_art(public)
            refs={k:v for k,v in json.loads(row['art_json']).items()if k in known};art_status='not_requested'
            if self.art_provider and self.art_store:
                try:
                    supplied=self.art_provider(json.loads(raw))
                    refs.update(self.art_store.stage(public,supplied));art_status='staged'
                except (Problem,OSError):
                    # Game/public text can still commit; missing art is a placeholder.
                    art_status='placeholder'
            self.hook('after_art')
            receipt={'ok':True,'game_id':game_id,'operation_id':operation_id,'revision_before':expected_revision,'revision':public['revision'],'state_hash':state_hash,'committed_at':time.time(),'art_status':art_status}
            db.execute('UPDATE games SET revision=?,private_state=?,public_json=?,state_hash=?,art_json=?,committed_at=? WHERE game_id=?',(public['revision'],candidate.private,raw,state_hash,encoded(refs),receipt['committed_at'],game_id))
            self.hook('after_state_update')
            db.execute('INSERT INTO operations VALUES(?,?,?,?)',(game_id,operation_id,fingerprint,encoded(receipt)))
            self.hook('before_commit');db.commit();committed=True;self.hook('after_commit')
            return receipt
        finally:
            if not committed:db.rollback()
            db.close()


def dispatch(authority,method,path,body=None):
    """In-process paper HTTP adapter for tests. No listener and NO authentication.

    A deployed adapter MUST verify owner authority first, separately restrict
    readers/writers, and enforce request/CPU budgets. Never expose this raw adapter.
    """
    try:
        if method=='POST' and path=='/game/action' and isinstance(body,dict) and set(body)=={'game_id','operation_id','expected_revision','action'}:
            return 200,authority.game_action(**body)
        if method=='GET' and path.startswith('/game/state/'):
            return 200,authority.get_state(path.removeprefix('/game/state/'))
        raise Problem('route_not_found',404)
    except Problem as error:return error.status,{'ok':False,'error':error.code}
    except Exception:return 500,{'ok':False,'error':'internal_error'}
