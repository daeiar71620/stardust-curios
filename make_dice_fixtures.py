"""Generate intentional public demos, never real saves or default game files."""
import json
from pathlib import Path
import tempfile

import engine
import _legacy_v3
import _legacy_v4
from test_percentile_v5 import fixture
from test_dice_engine import fixture as old_fixture


def main():
    out = Path(__file__).with_name('dice-fixtures')
    out.mkdir(exist_ok=True)
    report = ['# v5 双D10合成公开演练', '',
        '全部由临时合成存档执行引擎命令生成，未读取或开始真实游戏。公开文件不含随机状态、真实基价或确切预算。', '']
    cases = [
        ('critical01', [1], 9999, None, True),
        ('ordinary-success', [35], 80, None, False),
        ('negotiating', [50, 35], 9999, None, False),
        ('preview', [50, 35], 9999, ('preview-offer', 'I001', '100'), False),
        ('accepted', [50], 9999, ('accept', 'I001'), True),
        ('declined', [50], 9999, ('decline', 'I001'), True),
        ('final-critical01', [50, 1], 9999, ('offer', 'I001', '9998'), True),
        ('final-success', [50, 35], 9999, ('offer', 'I001', '100'), False),
        ('final-failure', [50, 99], 9999, ('offer', 'I001', '100'), False),
        ('fumble100', [100], 1, None, True),
        ('final-fumble100', [50, 100], 9999, ('offer', 'I001', '100'), False),
    ]
    for name, rolls, price, final, named in cases:
        with tempfile.TemporaryDirectory(prefix='public-percentile-demo-') as tmp:
            store = engine.GameStore(Path(tmp) / 'synthetic.json')
            state = fixture(*rolls, price=price)
            engine._validate_state(state)
            engine._atomic_json(store.save_path, state)
            command = ['sell', 'I001'] + ([state['visitors'][0]['id']] if named else [])
            public = store.execute(*command)
            if final: public = store.execute(*final)
            engine._atomic_json(out / f'{name}.json', public)
            report += [f'## {name}', f"命令：{' '.join(command)}" + (f"；{' '.join(final)}" if final else ''),
                       public['last_event']['text'], '']
            if final and final[0] == 'preview-offer':
                p = public['negotiation']['preview']
                report += [f"本次预览：还价{p['accept_income']}，最终报价{p['price']}，涨幅{p['premium']:.1%}，基础率{p['base_chance']}%，精确成功率{p['threshold']}%。接受免费；再谈花1精力，失败收入0且旧还价作废。", '']
    for version in [3, 4]:
        with tempfile.TemporaryDirectory(prefix='public-history-demo-') as tmp:
            module = _legacy_v3 if version == 3 else _legacy_v4
            state = old_fixture(10, 20)
            state['version'] = version
            module.apply_command(state, 'sell', ['I001'])
            module._validate_state(state)
            source = Path(tmp) / 'synthetic-old.json'; source.write_text(json.dumps(state))
            original = source.read_bytes()
            store = engine.GameStore(Path(tmp) / 'synthetic-copy.json')
            public = store.execute(f'import-v{version}', str(source))
            if version == 4:
                public = store.execute('offer', 'I001', '100')
            assert source.read_bytes() == original
            name = 'legacy-v3' if version == 3 else 'mixed-v4-v5'
            engine._atomic_json(out / f'{name}.json', public)
            report += [f'## {name}', '只读复制临时旧存档；历史D20保留原规则，未来重试使用v5。',
                f"骰史版本：{[row['rules_version'] for row in public['roll_history']]}", '']
    (out / 'PUBLIC_PLAYTHROUGH.md').write_text('\n'.join(report), encoding='utf-8')
    print(f'{len(cases)+2} public synthetic fixtures: {out}')


if __name__ == '__main__': main()
