"""Generate temporary current-schema observations of unchanged v6 trade rules."""
import copy
import json
from pathlib import Path
import tempfile
import engine
import _legacy_v5
from test_management_v6 import fixture, named
from test_percentile_v5 import fixture as old_fixture


def generate(output_directory):
    root=Path(output_directory);root.mkdir(parents=True,exist_ok=True)
    log=['# v8公开合成场景（v6交易规则）','', '均来自临时合成局。没有读取、复制或推进任何玩家存档；这里只保留公开投影。','']
    def save(name,public):
        # Deliberate defensive scan: public fixture may have ranges, never exact fields.
        text=json.dumps(public,ensure_ascii=False,indent=2)
        for key in ('"rng":','"budget":','"base_value":','"context":','"cargo":'):
            assert key not in text,key
        (root/f'{name}.json').write_text(text)
        log.extend([f'## {name}',public['last_event']['text'], ''])
    with tempfile.TemporaryDirectory(prefix='v6-public-fixtures-') as tmp:
        store=engine.GameStore(Path(tmp)/'synthetic.json')
        def put(state):
            engine._validate_state(state);engine._atomic_json(store.save_path,state)
            return store.execute('status')
        state=fixture(99,50,count=3);named(state)
        state['inventory'][1]['price']=9999
        state['inventory'][2].update(condition=30,price=50)
        save('ready',put(state))
        public=store.execute('sell','I002');save('walkin-limit-used',public);save('outrageous-departure',public)
        put(fixture(99));public=store.execute('sell','I001');save('negotiating',public)
        price=public['negotiation']['counter_offer']+1
        save('preview',store.execute('preview-offer','I001',str(price)))
        save('accepted',store.execute('accept','I001'))
        put(fixture(99,condition=44,price=60));save('condition-departure',store.execute('sell','I001'))
        state=fixture(99);visitor=named(state,False);put(state)
        save('mismatch-departure',store.execute('sell','I001',visitor['id']))
        put(fixture(1,price=9999,condition=5));save('critical01',store.execute('sell','I001'))
        put(fixture(100));save('fumble100',store.execute('sell','I001'))
        for second,name in [(1,'final-critical01'),(50,'final-success'),(99,'final-failure'),(100,'final-fumble100')]:
            put(fixture(99,second));public=store.execute('sell','I001');price=public['negotiation']['counter_offer']+1
            save(name,store.execute('offer','I001',str(price)))
        old=old_fixture(50,1);_legacy_v5.apply_command(old,'sell',['I001'])
        copied=engine.migrate_v5(json.dumps(old).encode());put(copied)
        save('grandfathered-v5-quote',store.execute('status'))
        save('mixed-v5-v6',store.execute('offer','I001','9998'))
    (root/'PUBLIC_PLAYTHROUGH.md').write_text('\n'.join(log))
    print(f'{len(list(root.glob("*.json")))} public synthetic management fixtures: {root}')


def main():
    with tempfile.TemporaryDirectory(prefix='stardust-management-check-') as tmp:
        generate(tmp)
    print('Temporary management fixtures cleaned up.')


if __name__=='__main__':main()
