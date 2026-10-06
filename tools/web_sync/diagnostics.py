"""Redacted, observational diagnostics. Never serializes exceptions or requests."""
from __future__ import annotations
from datetime import datetime, timezone
import json
import socket
import ssl
import subprocess
import time
import urllib.error
import uuid

EVENTS = frozenset('preflight_scope execution_started execution_finished execution_stopped state_observed state_unavailable engine_started engine_returned engine_committed engine_failed projection_failed duplicate_suppressed publication_preparing publication_prepared publication_attempt publication_transport_failed publication_ack_received publication_ack_verified publication_recorded publication_failed switch_started switch_finished switch_stopped activation_attempt activation_transport_failed activation_ack_received'.split())
ENUMS = {
    'mode': frozenset('action sync reconcile switch recover_switch invalid'.split()),
    'action_kind': frozenset('buy open repair price sell accept decline offer collect replace-collection upgrade endday continue status market codex visitors inspect preview-offer none invalid'.split()),
    'local_action': frozenset('not_started not_executed unknown committed rejected'.split()),
    'last_local_commit_basis': frozenset('unknown journal_record operator_review'.split()),
    'ack_relation': frozenset('unknown same_snapshot older_snapshot different_epoch inconsistent'.split()),
    'publication': frozenset('not_attempted pending response_received ack_verified_not_recorded acknowledged failed'.split()),
    'error_class': frozenset('http_error tls_error timeout connection_error dns_error os_error json_error value_error type_error process_error interrupted guarded_stop unexpected_error transient_network'.split()),
}
NUMBERS = frozenset('local_public_revision last_local_commit_revision last_ack_revision last_ack_epoch attempt http_status error_errno exit_code duration_ms new_art_count'.split())
STATE_KEYS = frozenset('last_local_commit_basis local_action local_public_revision last_local_commit_revision last_ack_revision last_ack_epoch ack_relation publication'.split())

def error_fields(exc):
    """Only fixed categories and numeric codes; never names/messages from input."""
    if isinstance(exc, urllib.error.HTTPError): kind='http_error'
    elif isinstance(exc, ssl.SSLError): kind='tls_error'
    elif isinstance(exc, (TimeoutError, subprocess.TimeoutExpired)): kind='timeout'
    elif isinstance(exc, ConnectionError): kind='connection_error'
    elif isinstance(exc, socket.gaierror): kind='dns_error'
    elif isinstance(exc, OSError): kind='os_error'
    elif isinstance(exc, json.JSONDecodeError): kind='json_error'
    elif isinstance(exc, ValueError): kind='value_error'
    elif isinstance(exc, TypeError): kind='type_error'
    elif isinstance(exc, subprocess.SubprocessError): kind='process_error'
    elif isinstance(exc, (KeyboardInterrupt, SystemExit)): kind='interrupted'
    else: kind='unexpected_error'
    result={'error_class': kind}
    try:number=exc.errno if isinstance(exc,OSError) else None
    except Exception:number=None
    if type(number) is int and -10000 <= number <= 10000: result['error_errno']=number
    return result

class Diagnostics:
    def __init__(self, stream=None, clock=time.monotonic):
        self.stream=stream; self.clock=clock; self.started=clock(); self.trace_id=uuid.uuid4().hex; self.sequence=0
        self.reset()
    def reset(self):
        self.state={'last_local_commit_basis':'unknown','local_action':'not_started','local_public_revision':None,'last_local_commit_revision':None,
                    'last_ack_revision':None,'last_ack_epoch':None,'ack_relation':'unknown','publication':'not_attempted'}
    def update(self, **fields):
        for key,value in fields.items():
            if key not in STATE_KEYS: continue
            if key in ENUMS and isinstance(value,str) and value in ENUMS[key]: self.state[key]=value
            elif key in NUMBERS and (value is None or type(value) is int and value >= 0): self.state[key]=value
    def status(self):
        return {**self.state,'server_state_basis':'last_durable_local_ack_receipt','live_sync_state':'not_asserted'}
    def emit(self, event, **fields):
        if event not in EVENTS: return
        try:
            self.sequence+=1
            record={'diagnostic_version':1,'trace_id':self.trace_id,'sequence':self.sequence,
                    'event':event,'elapsed_ms':max(0,round((self.clock()-self.started)*1000)),
                    'observed_at':datetime.now(timezone.utc).isoformat()}
            for key,value in fields.items():
                if key in ENUMS and isinstance(value,str) and value in ENUMS[key]: record[key]=value
                elif key in NUMBERS and (value is None or type(value) is int and -10000 <= value): record[key]=value
            record.update(self.status())
            if self.stream is not None:
                self.stream.write(json.dumps(record,ensure_ascii=False,separators=(',',':'))+'\n');self.stream.flush()
        except Exception:
            # Diagnostics never changes execution, persistence or retry behavior.
            pass
    def preflight(self, destination):
        # Caller must pass only validate_config's pinned Site origin. Fail closed
        # if this mandatory scope display cannot be written before hidden input.
        from urllib.parse import urlsplit
        parsed=urlsplit(destination)
        if parsed.scheme!='https' or not parsed.hostname or not parsed.hostname.endswith('.chatgpt.site') or parsed.username or parsed.password or parsed.port not in (None,443) or parsed.path not in ('','/') or parsed.query or parsed.fragment:
            raise ValueError('invalid_preflight_destination')
        record={'diagnostic_version':1,'trace_id':self.trace_id,'event':'preflight_scope',
                'operation_domain':'local_fictional_game','destination':destination,
                'upload_kind':'whitelisted_public_observation_and_discovered_pngs',
                'private_save_upload':False,'real_world_transaction':False,
                'authentication':'existing_site_access_only','operation_started':False}
        if self.stream is not None:
            self.stream.write(json.dumps(record,ensure_ascii=False,separators=(',',':'))+'\n');self.stream.flush()
