#!/usr/bin/env python3
"""Synthetic-only pipeline timings; no real save or network access.

Retains only aggregate metrics. All generated saves, artwork, and receipts live
in TemporaryDirectory and are removed after the run. Use --output for results.
"""
import argparse, base64, copy, hashlib, importlib.util, json, os
from pathlib import Path
import statistics, subprocess, sys, tempfile, time
sys.dont_write_bytecode = True


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def summary(samples):
    ordered = sorted(samples)
    return {'n': len(samples), 'median_ms': round(statistics.median(samples), 3),
            'p95_ms': round(ordered[min(len(ordered)-1, int(len(ordered)*.95))], 3),
            'min_ms': round(ordered[0], 3), 'max_ms': round(ordered[-1], 3)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game', type=Path, required=True, help='Directory containing the official engine.py and spectator.py')
    p.add_argument('--controller', type=Path, default=Path(__file__).resolve().parent)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    args.game = args.game.expanduser().resolve()
    args.controller = args.controller.expanduser().resolve()
    sys.path[:0] = [str(args.controller), str(args.game)]
    engine = load('audit_engine', args.game/'engine.py')
    controller = load('audit_controller', args.controller/'action_publish.py')
    exporter = load('audit_exporter', args.controller/'export_known_art.py')
    policy = load('audit_policy', args.game/'simulate_management_v6.py')
    result = {'scope': 'synthetic temporary saves, in-memory mock HTTP, no production requests',
              'sources': {str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in
                          [args.game/'engine.py', args.game/'spectator.py', args.controller/'action_publish.py', args.controller/'export_known_art.py']},
              'timings': {}, 'payloads': {}, 'notes': []}
    def bench(name, f, n=20):
        samples=[]
        for _ in range(n):
            start=time.perf_counter(); f(); samples.append((time.perf_counter()-start)*1000)
        result['timings'][name]=summary(samples)
        print(name, json.dumps(result['timings'][name]), flush=True)
    with tempfile.TemporaryDirectory(prefix='stardust-synthetic-perf-') as temporary:
        root=Path(temporary); save=root/'synthetic.json'; store=engine.GameStore(save)
        # Fixed synthetic seed only, never a live state's seed or RNG.
        state=engine.new_state(71620); state['revision']=1
        engine._atomic_json(save,state); o=store.execute('status')
        bench('engine_import_fresh_process', lambda: subprocess.run([sys.executable,'-B','-c',f'import sys; sys.path.insert(0,{str(args.game)!r}); import engine'],check=True,stdout=subprocess.DEVNULL,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}), 12)
        bench('new_game_synthetic_state', lambda: engine.new_state(71620))
        bench('load_validate_small_save', store.load)
        bench('public_projection_small', lambda: engine.observation(state))
        bench('private_atomic_save_small', lambda: engine._atomic_json(root/'write-private.json',state))
        bench('public_atomic_save_small', lambda: engine._atomic_json(root/'write.observation.json',o))
        bench('status_in_process_small', lambda: store.execute('status'))
        bench('status_cli_small', lambda: subprocess.run([sys.executable,'-B',str(args.game/'engine.py'),'--save',str(save),'status'],check=True,stdout=subprocess.DEVNULL,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}), 12)
        # Complete exactly the first synthetic week using public observations.
        actions=[]
        while o['phase'] not in ('week_summary','lost'):
            choice=policy.action(o,'careful115') or ('endday',)
            start=time.perf_counter();o=store.execute(*choice);actions.append((time.perf_counter()-start)*1000)
        result['timings']['official_store_action_first_week']=summary(actions)
        result['synthetic_week']={'day':o['day'],'phase':o['phase'],'actions':len(actions),'revision':o['revision'],'known_art_count':len(controller.known_art(o))}
        state=store.load()
        bench('load_validate_week_save',store.load)
        bench('public_projection_week',lambda:engine.observation(state))
        bench('public_sanitize_week',lambda:controller.sanitize(o),100)
        bench('serialize_hash_week',lambda:controller.digest(o),100)
        bench('private_atomic_save_week',lambda:engine._atomic_json(root/'write-private.json',state))
        bench('public_atomic_save_week',lambda:engine._atomic_json(root/'write.observation.json',o))
        bench('status_cli_week',lambda:subprocess.run([sys.executable,'-B',str(args.game/'engine.py'),'--save',str(save),'status'],check=True,stdout=subprocess.DEVNULL,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}),12)
        artroot=root/'art'
        bench('known_art_export_first_week',lambda:exporter.export(store.observation_path,args.game/'spectator.py',artroot),5)
        pngs=list(artroot.glob('*.png'))
        knownpngs=[artroot/(i+'.png') for i in controller.known_art(o)]
        result['payloads']['known_png_bytes']=sum(f.stat().st_size for f in knownpngs)
        result['payloads']['raw_public_bytes']=len(store.observation_path.read_bytes())
        bench('validate_known_pngs',lambda:[controller.valid_png(f) for f in knownpngs],30)
        bench('read_hash_known_pngs',lambda:[hashlib.sha256(f.read_bytes()).hexdigest() for f in knownpngs],30)
        posts=[]
        def transport(url, token, body):
            raw=controller.request_bytes(body);posts.append({'bytes':len(raw),'art_count':len(body['artwork'])})
            return {'ok':True,'revision':body['observation']['revision'],'session_id':body['session_id'],'session_epoch':body['session_epoch'],'digest':'a'*64,'request_sha256':hashlib.sha256(raw).hexdigest(),'published_at':'2026-10-06T00:00:00Z'}
        config={'site_id':'synthetic-perf-only','site_url':'https://synthetic-perf.chatgpt.site','session_id':'synthetic-perf','session_epoch':1,'observation_version':9,'engine_path':str(args.game/'engine.py'),'save_path':str(save),'observation_path':str(store.observation_path),'outbox_dir':str(root/'outbox'),'art_dir':str(artroot),'renderer_path':str(args.game/'spectator.py'),'owner_private_verified':True}
        c=controller.Controller(config,'mock-token-never-networked',transport=transport)
        bench('controller_first_sync_with_art',lambda:c.execute({'mode':'sync'}),1)
        result['payloads']['first_sync']=posts[-1]
        bench('controller_no_change_mock_sync',lambda:c.execute({'mode':'sync'}),30)
        result['payloads']['unchanged_sync']=posts[-1]
        # Finished phase still allows read-only status, which exercises official subprocess and full receipt protocol.
        count=0
        def read_action():
            nonlocal count
            count+=1;c.execute({'operation_id':f'read-{count}','action':['status']})
        bench('controller_official_status_mock_sync',read_action,12)
        # Measure historic receipt scan cost without changing live history.
        template={'schema_version':1,'operation_id':'template','config_fingerprint':c.c['fingerprint'],'stage':'published','revision_after':o['revision']}
        for target in (100,1000,3000):
            c.ops.mkdir(parents=True,exist_ok=True)
            for i in range(target):
                f=c.ops/f'history-{i:05d}.json'
                if not f.exists(): f.write_text(json.dumps(dict(template,operation_id=f'history-{i:05d}')))
            bench(f'journal_scan_{target}',c.pending,5)
            bench(f'controller_status_mock_sync_{target}_history',read_action,5)
        # Isolate all-known synthetic export scaling without exposing unknown real art.
        renderer=exporter.load_renderer(args.game/'spectator.py')
        synthetic=copy.deepcopy(o)
        rows=[{'slot':i+1,'discovered':True,'collected':False,'art_id':identity,'name':name,'kind':'artifact','rarity':'common'} for i,(name,identity) in enumerate(renderer.ITEM_ART_NAMES.items())]
        synthetic['codex']={'total':len(rows),'discovered':len(rows),'collected':0,'entries':rows}
        synthetic['inventory']=[];synthetic['collection']=[]
        all_public=root/'all-synthetic.observation.json';all_public.write_text(json.dumps(synthetic,ensure_ascii=False))
        bench('known_art_export_24_synthetic',lambda:exporter.export(all_public,args.game/'spectator.py',root/'art24'),3)
    result['notes'].append('Synthetic artifacts automatically removed. Export timing currently includes rewriting already existing art and preview sheet.')
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('Saved aggregate results:',args.output)

if __name__=='__main__':main()
