# 星屑杂货铺 · 跑团掷骰与一次还价版

首周只是一段开头。回收盲箱、照顾藏品、认识回头客，把停在星港边上的小店慢慢经营下去。

## 这版增加了什么

- 真实D20成交检定，公开骰点、加值、难度与最近60骰
- 天然20可以突破普通意愿/预算卖出9999天价；天然1直接告辞
- 一次还价：接受、拒绝，或唯一一次最终报价再掷骰
- 谈判落盘、同日货物锁、重启不重掷；v2完整私档只读复制升级

- 第 7 天首周结算后明确选择继续，进入不限天数的经营
- 24 种货物，独立发现图鉴与永久收藏，5 套收藏效果
- 8 位顾客的类别偏好、品相期待与不确定预算，每日 3–4 位到访
- 6 种港口事件，真实改变成本、精力或成交意愿
- 工作台、货架、展示柜各 3 级，阶段目标持续推进
- 旧版首局只读复制迁移，原存档保留，迁移后也不会自动续玩

Python 标准库独立裁判 + 只读 Tkinter 观战画面，AI 通过 CLI 经营。没有新联网服务或游戏引擎依赖。

## 使用

图形界面需要 Pillow、Tkinter、中文字体与图形桌面。已验证环境为 Linux / Python 3.12；引擎使用 POSIX `fcntl` 锁，Windows 原生尚不支持。

Ubuntu / Debian 图形环境可先准备依赖：

```sh
sudo apt install python3 python3-venv python3-tk fonts-noto-cjk
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements.txt
```

`requirements.txt` 固定 Pillow 12.3.0。引擎本身只用标准库；Tkinter 和 Noto Sans CJK 为系统依赖。无图形桌面时可用 CLI 经营或从公开状态导出静态截图。字体回退不保证能显示中文，建议安装上述字体。

选项一：从新店开始（不会覆盖已存在的默认存档）

```sh
python3 engine.py new
python3 engine.py status
./start_spectator.sh
```

选项二：把旧版存档复制到全新文件

```sh
python3 engine.py --save continued.json import-v2 ../stardust-curios-v2/save.json
python3 spectator.py --observation continued.observation.json
```

v1首局仍支持 `import-v1`。示例中的旧版路径需要按实际存放位置调整，输入必须是完整私有 save.json，不能用 observation.json 代替。

已完成首周会停在结算，明确执行 `python3 engine.py --save continued.json continue` 才进入第 8 天。上述迁移和续玩均须由玩家选择，本交付没有代替执行。

观战画面按 1–5 切换货架、旅客、图鉴、成长、日志；←/→ 翻页，点击物品或事件查看完整故事，F11 全屏。界面只读，缺少公开文件时会等待，不会自行开局。

在另一个终端用命令经营：

```sh
python3 engine.py market
python3 engine.py visitors
python3 engine.py buy salvage
python3 engine.py open C001
python3 engine.py inspect I001
python3 engine.py price I001 120
python3 engine.py sell I001
python3 engine.py endday
```

自定义存档时，上述每条命令均须加同一个 `--save continued.json`。查看完整规则与迁移边界：[店主手册](PLAY_GUIDE.md)。公开接口：[观察 schema](OBSERVATION_SCHEMA.md)。

## 存档和公平性

`save.json` 是私有裁判状态，包含隐藏箱内货物、实际基价、顾客预算和随机状态。按游戏规则，AI 玩家与画面只能读取 `observation.json`、CLI 公开输出，不得读改私档或预测内部随机数。

所有经营动作落盘，跨进程锁防止重复售出；开箱内容买入时即固定，查看不重抽。失败命令不改变状态。公共投影写入失败时，已提交动作会明确报告成功与警告，避免错误重试；`status` 可恢复画面。

旧版存档只能导入到未使用的新路径；已有目标或投影文件不会被覆盖。旧版未完整记录的早期发现无法凭空恢复；迁移后的统计仅计新增经营。

## 测试

```sh
python3 -m unittest discover -v
```

测试只使用临时合成存档和模拟画布，不使用个人首局。真实 UI 还需在图形桌面检查。

## 文件

- `engine.py`：持续经营引擎与 CLI
- `_legacy_v1.py`、`_legacy_v2.py`：冻结的旧版验证器，仅用于迁移兼容
- `test_dice_engine.py`：骰点、还价、原子性、存档升级专用回归
- `dice-fixtures/`：纯合成公开展示样例，不是玩家存档
- `spectator.py`：公开状态只读观战窗口
- `test_engine.py`、`test_v2_engine.py`、`test_v2_audit.py`、`test_spectator.py`：回归测试

许可协议尚未选定，本目录未授予额外开源许可。


### 幸运经济

天然20每骰5%，哪怕报价9999也全额成交。初次普通失败后坚持同价再骰，合计天价成交率最多9.5%；因此运气好会大幅加速现金目标。暴富是刻意保留的奇幻规则，收藏/口碑/设施等目标仍要经营。详见店主手册的经济取舍。

存档隔离是程序接口约定，并非操作系统沙箱；不承诺阻止有私档访问权限的人手改文件或恢复旧备份。正常CLI操作与窗口重启不会绕过已提交骰点。


### 观战骰子与谈判

点击大骰卡可查看本次D20、加值、目标和大成功规则；右上“查看骰子记录”展示最近60骰，日志页可切回经营事件。Esc关闭详情。接受还价后显示实际成交事件，旧骰明确作为历史，不会误报仍在谈价。界面始终只读，所有交易由CLI执行。

演示文件须明确加`--demo`，例如 `python3 spectator.py --observation dice-fixtures/negotiating.json --demo`；画面会标注演示。`--journal-mode rolls`可启动在骰子记录模式。这些示例不创建或迁移玩家存档。
