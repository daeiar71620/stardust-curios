"""Create public demo data using the real engine and temporary synthetic saves.
Never opens a player save, never creates default save.json/observation.json.
"""
import json
from pathlib import Path
import tempfile
import engine
from test_dice_engine import fixture


def main():
    out = Path(__file__).with_name("dice-fixtures")
    out.mkdir(exist_ok=True)
    report = ["# 合成公开玩法演练", "", "以下只使用临时合成存档，由真实独立引擎执行命令。未开始或读取任何玩家真实游戏局。", ""]
    cases = [
        ("natural20", [20], 9999, None, True),
        ("ordinary-success", [19], 40, None, False),
        ("negotiating", [10, 20], 9999, None, True),
        ("accepted", [10], 9999, ("accept", "I001"), True),
        ("declined", [10], 9999, ("decline", "I001"), True),
        ("final-miracle", [10, 20], 9999, ("offer", "I001", "9999"), True),
        ("final-success", [10, 19], 9999, ("offer", "I001", "40"), False),
        ("final-failure", [10, 12], 9999, ("offer", "I001", "9999"), True),
        ("fumble", [1], 1, None, True),
    ]
    for name, faces, price, final, named in cases:
        with tempfile.TemporaryDirectory(prefix="public-dice-demo-") as tmp:
            store = engine.GameStore(Path(tmp) / "synthetic.json")
            state = fixture(*faces, price=price)
            engine._validate_state(state)
            engine._atomic_json(store.save_path, state)
            command = ["sell", "I001"] + ([state["visitors"][0]["id"]] if named else [])
            obs = store.execute(*command)
            if final:
                obs = store.execute(*final)
            engine._atomic_json(out / f"{name}.json", obs)
            report += [f"## {name}", f"命令：{' '.join(command)}" + (f"；{' '.join(final)}" if final else ""),
                       f"结果：{obs['last_event']['title']}。{obs['last_event']['text']}",
                       f"公开状态：现金{obs['credits']}，精力{obs['energy']}，成交{obs['stats']['sales_count']}件，骰史{len(obs['roll_history'])}条。", ""]
    (out / "PUBLIC_PLAYTHROUGH.md").write_text("\n".join(report), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
