# 星屑杂货铺 · Stardust Curios

一间停在星港边上的小店，七天试营业。回收漂流盲箱，修好古怪旧物，给它们找到新主人，也留下一点属于自己的星光。

Python 命令行负责经营，Tkinter 原生窗口实时展示公开画面。图案由代码绘制，无需额外图片资源。当前程序内保留早期名称「星际旧货铺」。

## 环境

已验证：Linux、Python 3.12、Pillow 12.3.0、Tkinter、Noto Sans CJK 字体。

- 经营引擎仅使用 Python 标准库
- 原生观战窗口需要 Pillow、Tkinter、中文字体和图形桌面
- 当前引擎使用 POSIX 文件锁（fcntl），Windows 原生不支持；其他系统未验证
- 字体路径为 `/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc` 和 `NotoSansCJK-Bold.ttc`

Ubuntu / Debian 桌面环境：

```sh
sudo apt update
sudo apt install python3 python3-venv python3-tk fonts-noto-cjk
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements.txt
```

## 开始经营

在项目目录运行：

```sh
python3 engine.py new
python3 engine.py status
sh start.sh
```

`new` 只会在没有存档时开局，已有进度不会被覆盖。`start.sh` 从自身所在目录启动全屏观战画面；也可运行 `python3 spectator.py` 打开普通窗口。

保持观战窗口打开，在另一个终端执行经营命令：

```sh
python3 engine.py market
python3 engine.py buy salvage
python3 engine.py open C001
python3 engine.py inspect I001
python3 engine.py price I001 120
python3 engine.py sell I001
python3 engine.py endday
```

物品和箱子 ID 以你的实际公开状态为准。查看全部命令：`python3 engine.py help`。详细目标、精力、收藏、修理和维护费见 [店主手册](PLAY_GUIDE.md)。

观战窗口只读公开画面数据，经营操作通过命令行完成。F11 切换全屏，Esc 退出全屏，点击或空格翻看货架。关闭窗口不会结束当天或重开本局。

## 存档与新一局

本仓库不附带个人游戏存档。首次 `new` 生成本地 `save.json` 和 `observation.json`，它们已列入 `.gitignore`。

- `save.json` 是完整存档，包含继续经营所需的内部状态；备份进度时应保存它
- `observation.json` 是供画面读取的公开状态，不能单独用来恢复整局
- 只丢失公开画面文件时，运行 `python3 engine.py status` 可重新生成它
- `status`、`market` 和 `inspect` 不消耗精力，也不改变随机结果

推荐用独立路径开新局，保留原进度：

```sh
python3 engine.py --save new-game.json new
python3 spectator.py --observation new-game.observation.json
python3 engine.py --save new-game.json status
```

只有明确执行 `python3 engine.py restart --confirm` 才会重置默认存档。请先自行备份需要保留的进度。

## 测试

```sh
python3 -m unittest -v test_engine test_spectator
```

测试使用独立临时存档和模拟画布，不会重置你的游戏。观战窗口仍需在真实图形桌面运行；无桌面环境可使用命令行经营。

## 许可

许可协议尚未选定，本仓库目前未授予额外的开源许可。
