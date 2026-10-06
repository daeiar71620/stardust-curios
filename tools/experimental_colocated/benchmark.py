"""Small synthetic local benchmark; no network, real save, or deployment."""
import argparse
import json
from pathlib import Path
import statistics
import tempfile
import time
from authority import Authority,CLIAdapter


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--engine',required=True);args=parser.parse_args();times=[];reads=[]
    with tempfile.TemporaryDirectory(prefix='colocated-benchmark-')as name:
        root=Path(name);service=Authority(root/'authority.sqlite',CLIAdapter(args.engine,root/'work'));view=service.initialize_synthetic('synthetic')
        def action(identity,argv):
            nonlocal view
            start=time.perf_counter();receipt=service.game_action('synthetic',identity,view['revision'],argv);times.append((time.perf_counter()-start)*1000)
            start=time.perf_counter();view=service.get_state('synthetic');reads.append((time.perf_counter()-start)*1000)
            assert view['revision']==receipt['revision']and view['state_hash']==receipt['state_hash']
        action('buy',['buy','salvage']);action('open',['open',view['observation']['crates'][0]['id']]);item=view['observation']['inventory'][0]['id']
        action('price-1',['price',item,'60']);action('price-2',['price',item,'61']);action('endday',['endday'])
        print(json.dumps({'synthetic_only':True,'actions':len(times),'action_ms':times,'action_median_ms':statistics.median(times),'same_authority_read_ms':reads,'read_median_ms':statistics.median(reads),'all_snapshot_receipt_pairs_match':True,'network_and_art_rendering_included':False,'temporary_artifacts_cleaned_on_exit':True},indent=2))

if __name__=='__main__':main()
