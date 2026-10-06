# 星屑杂货铺 v5 · 双D10百分骰版

首周只是一段开头。回收盲箱、照顾藏品、认识回头客，把停在星港边上的小店慢慢经营下去。

## 这版的成交规则

- 两颗独立十面骰：十位骰 **00、10、…、90**，个位骰 **0–9**；合成01–100，**00+0记100**
- **掷低点**：01大成功，按本次合法报价成交，即使9999星币超过普通预算；100大失败，直接结束当天接待；02–99不高于成功阈值就成交
- 普通初次失败后，接受固定还价、谢绝，或花1精力作唯一一次最终报价；必须满足 **客人还价 < 最终报价 < 初次标价**
- 最终成功率只按公开还价、最终报价和冻结加值计算，涨幅越大成功率越低；**取消固定+3拒价惩罚**，也没有第二道隐藏预算门槛
- `preview-offer I001 金额` 免费显示最终报价的**精确成功率**；不写私档、不耗精力、不推进随机状态
- 谈判落盘、同日货物/顾客锁、重启不重掷、失败不能回头接受旧还价，均保留
- `import-v1` / `import-v2` / `import-v3` / `import-v4` 仅把旧完整私档复制到全新路径，不自动迁移或推进真实游戏；旧D20历史保留原规则，之后的新骰明确使用v5

这是 **CoC启发的简化房规，不是官方完整规则**。01大成功概率为每次1%，不是旧D20天然20的5%；极端高价的中奖机会确实变小了，并非等概率换皮。

## 经营内容

- 第7天首周结算后明确选择继续，进入不限天数的经营
- 24种货物，独立发现图鉴与永久收藏，5套收藏效果
- 8位顾客的类别偏好、品相期待与不确定预算，每日3–4位到访
- 6种港口事件，改变成本、精力或成交基础率
- 工作台、货架、展示柜各3级，阶段目标持续推进

Python标准库独立裁判 + 只读Tkinter观战画面，AI通过CLI经营。没有新增联网服务或游戏引擎依赖。

## 使用

图形界面需要Pillow、Tkinter、中文字体与图形桌面。引擎使用POSIX `fcntl` 锁，Windows原生尚不支持。

Ubuntu / Debian图形环境可先准备依赖：

```sh
sudo apt install python3 python3-venv python3-tk fonts-noto-cjk
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements.txt
```

`requirements.txt` 固定Pillow 12.3.0。引擎本身只用标准库；Tkinter和Noto Sans CJK为系统依赖。无图形桌面时可用CLI经营或从公开状态导出静态截图。字体回退不保证显示中文。

选项一：从新店开始（不会覆盖已存在的默认存档）

```sh
python3 engine.py new
python3 engine.py status
./start_spectator.sh
```

选项二：把旧版存档复制到全新文件。以下路径都是占位示例，请换成自己的路径：

```sh
python3 engine.py --save /path/to/new-percentile-copy.json import-v4 /path/to/old-v4-save.json
python3 spectator.py --observation /path/to/new-percentile-copy.observation.json
```

旧档为v1、v2、v3时，分别使用对应的 `import-v1`、`import-v2`、`import-v3`。输入必须是完整私有存档，不能用公开observation代替。已有目标存档或投影均不会覆盖。

已完成首周的存档仍停在结算；明确执行 `continue` 才进入第8天。所有后续命令都必须选择同一个新存档：

```sh
python3 engine.py --save /path/to/new-percentile-copy.json status
python3 engine.py --save /path/to/new-percentile-copy.json continue
```

迁移与续玩都由玩家选择；阅读说明、打开观战器或展示演示文件不会执行这些操作。

在另一个终端用命令经营新店：

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

自定义存档时，每条命令都须加同一个 `--save /path/to/save.json`。完整规则：[店主手册](PLAY_GUIDE.md)。公开接口：[观察schema](OBSERVATION_SCHEMA.md)。

## 最终报价前先看风险

待谈画面默认展示“还价+1”的示例，不会自动报价。先查看 `status` 中的合法价格范围，再预览想尝试的金额：

```sh
python3 engine.py --save /path/to/save.json preview-offer I001 165
# 只有正式offer才会花1精力并掷骰；165必须在当前合法范围内
python3 engine.py --save /path/to/save.json offer I001 165
```

令冻结加值为 `bonus`（百分点），还价为 `counter`，最终价为 `price`：

- 基础率 `base = clamp(1, 99, 70 + bonus)`
- 最终阈值 `threshold = clamp(1, 99, floor(base × counter / (2 × price − counter)))`
- 等价写法为 `clamp(1, 99, floor(base / (1 + 2 × 涨幅)))`，其中涨幅是 `(price − counter) / counter`
- 成功概率恰好为 `threshold%`，已包含01大成功；100始终失败

例：冻结加值0、客人还价150，最终价165为58%，225为35%，9998为1%。每个例子都要求初次标价严格高于最终价。接受则免费拿到150；最终报价失败收入0，而且失去接受150的机会。

预览与正式最终骰使用相同公式。还价已反映可承受价格，最终骰不会再查询隐藏价值或预算来否决成功。初次检定仍使用隐藏实际参考价值和特邀顾客预算，掷骰前不公布该报价的精确概率；已发生骰的实际阈值与两颗骰面会公开。

预览只刷新公开投影；后续 `status` 或经营命令会恢复“还价+1”的默认示例。预览不承诺报价、不锁定选中的价格，也不改变精力、骰史、谈判或随机状态。

## 幸运经济

01仍可把9999天价全额卖出，但每次只占1%。若初次与最终都只有01能成，且有合法最终价和足够精力、普通失败后选择再报价，两次合计成交率为 `1% + 98% × 1% = 1.98%`，预期耗费1.98精力。初次100会直接结束；第二次须真让价，例如9999降到9998，并按第二次价格结算。

这是有意保留的奇幻经营规则。好运可加速现金目标，收藏、口碑与设施目标仍须经营。

## 存档和公平性

`save.json` 是私有裁判状态，含隐藏箱内货物、实际基价、顾客精确预算和随机状态。按游戏规则，AI玩家与画面只能读公开observation和CLI输出，不得读改私档或预测内部随机数。

所有经营动作落盘，跨进程锁防止重复售出；箱内货物买入时即固定，查看不重抽。失败命令不改变状态。动作已提交而公开投影写入失败时，返回成功并附 `persistence_warning`，不要重复该动作；排除文件系统问题后用 `status` 恢复画面。

v3/v4复制保留已提交骰、待谈还价、当日锁与随机进度。历史D20不重新计算、不换成百分骰；旧待谈局的冻结加值每点转换为5百分点，尚未使用的最终报价使用v5规则。v1未记录的早期发现和销售统计无法凭空补造；详情见手册。

公私分离是程序接口约定，不是操作系统沙箱。不承诺阻止有私档权限的人手改文件或恢复备份；正常CLI操作与窗口重启不会绕过已提交结果。

## 观战与演示

观战器只读公开文件；缺少文件时会等待，不会自行开局。1–5切换货架、旅客、图鉴、成长、日志；←/→翻页，点击物品、骰卡或事件查看详情，Esc关闭详情，F11全屏。骰记录保留最近60次；应按每条 `rules_version` 区分旧D20与新百分骰，接受还价后的旧骰属于历史。

合成演示须明确加 `--demo`，例如：

```sh
python3 spectator.py --observation dice-fixtures/negotiating.json --demo
python3 spectator.py --observation dice-fixtures/mixed-v4-v5.json --demo --tab journal --journal-mode rolls
```

演示包括 `critical01`、`fumble100`、`ordinary-success`、`negotiating`、`preview`、`final-success`、`final-failure`、`final-critical01`、`final-fumble100`、`accepted`、`declined`、`legacy-v3`、`mixed-v4-v5`。这些是公开合成样例，不是玩家存档。

## 测试与文件

```sh
python3 -m unittest discover -v
```

测试使用临时合成存档和模拟画布。本版测试结果、合成长线经营与界面检查范围见 [QA报告](QA_REPORT.md)；请以该报告中的v5记录为准，不沿用旧v4测试数量或截图作验证。

- `engine.py`：持续经营引擎与CLI
- `_legacy_v1.py` 至 `_legacy_v4.py`：冻结的旧版验证器，用于复制导入与历史兼容
- `test_percentile_v5.py`：v5百分骰、概率、预览和兼容回归
- `test_*.py`：经营、持久化、旧规则与观战器等回归测试
- `make_dice_fixtures.py`、`dice-fixtures/`：合成公开演示生成器与样例
- `spectator.py`：公开状态只读观战窗口

许可协议尚未选定，本目录未授予额外开源许可。
