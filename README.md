# 星屑杂货铺 v7 · 每件旧物都有模样

这次修正图鉴的发现边界，并为24件旧物分别绘制原创程序插画。迷路送信蜂有翅膀、触角和信封；发条守夜猫有猫耳、尾巴和发条。

## 图鉴要亲手发现

- 尚未开到的条目统一显示 **???** 和相同的未知标记，不预告名字、形状、类别、稀有度或故事
- 只有真正开箱才解锁画像与档案。买到未拆封的箱子不会解锁；卖掉已见过的物品也不会忘记
- “已发现”和“已珍藏”分别计数。收藏套装继续公开进度和经营收益，不列出未知物品的名字
- CLI与公开observation也遵守同一边界。新版观战器会遮住旧版公开文件里尚未发现的条目
- 本次是兼容更新，私档和经营规则仍为 **version 6**，无需导入或迁移v6存档。读取 `status` 只刷新公开投影，不推进天数、骰子或游戏资源

v6的经营取舍保持不变：**普通旅客限量且有预算；普通失败不再必送还价**。

## 小店的新取舍

- 普通旅客每天 **1次接待**，公开预算 **60–120星币**，当日个人预算隐藏。正式 `sell` 尝试即占用，无论成功、还价、拒绝或100；错误命令不占用
- 普通失败只有满足公开条件才提出还价：标价不超过 **公开参考价的125%**、不超过买家公开预算区间上限，且至少2星币；特邀顾客还要求类别匹配及达到其品相期待，普通旅客要求品相 **≥45%**
- 不满足条件仍可尝试初次出售；普通失败会直接离店，物品留下。**01仍按合法标价成交，9999也可以；100仍立即结束接待**
- `status` / `inspect I001` 免费显示每位买家的还价资格、原因和风险。观战器显示剩余旅客、预算范围，以及物品的逐买家还价条件
- 资格只用公开信息，没有额外隐藏“是否愿谈”骰。它不保证初次买得起标价，也不公开初次精确成功率

售价、回收进价、维护费、升级成本、常规初次成功公式及所有加值均未普遍削改。配对顾客、修理、等待与选择进货量现在更有意义。

## 保留的百分骰与谈判

两颗独立D10分别给出十位00–90与个位0–9，00+0记100。掷低点：01大成功；100大失败；02–99不高于阈值成交。每件货每天最多一场接待，每位特邀顾客每天最多一场；改价、换人或重启不能刷新。

得到固定还价后，可以免费 `accept` / `decline`，或花1精力作唯一最终报价：

```sh
python3 engine.py preview-offer I001 85
python3 engine.py offer I001 85
```

始终要求 **客人还价 < 最终报价 < 初次标价**。最终失败收入0，不能回头接受旧还价。预览不写私档、不耗精力、不推进随机数。

最终精确成功率保持：`base=clamp(1,99,70+bonus)`；`threshold=clamp(1,99,floor(base*counter/(2*price-counter)))`。成功率正好等于threshold%，包含01；没有第二道隐藏预算判定。

这是CoC启发的简化房规，不是官方完整规则。

## 使用

引擎使用Python标准库；图形界面使用Tkinter、Pillow与中文字体。POSIX `fcntl` 锁尚不支持Windows原生。

```sh
sudo apt install python3 python3-venv python3-tk fonts-noto-cjk
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 engine.py new
python3 engine.py status
./start_spectator.sh
```

`requirements.txt` 固定Pillow 12.3.0。`new`不会覆盖已有默认存档；观战器只读公开文件，缺少文件时等待，不会开局。

```sh
python3 engine.py visitors
python3 engine.py buy salvage
python3 engine.py open C001
python3 engine.py inspect I001
python3 engine.py price I001 90
python3 engine.py sell I001 mira
python3 engine.py endday
```

仍有24种货物、8位特邀顾客、3项设施、5套收藏、港口事件与持续阶段目标。第7天结算后，必须明确 `continue` 才进入第8天。

## 旧档只能复制导入

示例路径是占位符，请选**全新目标**；不会自动迁移或推进真实游戏：

```sh
python3 engine.py --save /path/to/new-v6-copy.json import-v5 /path/to/old-v5-save.json
python3 spectator.py --observation /path/to/new-v6-copy.observation.json
```

v1–v4分别使用 `import-v1` 至 `import-v4`。必须提供完整私档，公开observation不能代替。已有目标私档或投影均不覆盖。

- v3/v4历史仍是原D20；v5历史仍是原百分骰。新骰标记v6，不重判旧骰
- 旧待谈还价已经承诺，**不会因新资格条件被追溯取消**，仍可免费接受/谢绝或作唯一合法最终报价
- v5复制保留完整资源、随机进度、日期、已用顾客与货物机会；当天已接待普通旅客则新名额视为已用
- v1/v2缺少完整已售接待记录，导入当天普通旅客名额保守视为已用，次日恢复。旧版原有迁移限制见手册
- 已到首周结算仍停在结算，复制不代替玩家选择继续

## 幸运与公平性的边界

新的9999初价不满足还价条件：01概率仍是1%，普通失败直接离店，不能再靠免费还价兜底。旧档已承诺的高价谈判仍可完成。**01天价利润彩票是有意保留的要求，不声称经济系统没有可利用策略**。

所有正式动作原子保存并加跨进程锁；开箱内容买入即固定。正常CLI改价、换货、重开窗口与并发调用不能刷新旅客名额或重掷。失败命令不改状态。若返回 `persistence_warning`，操作可能已提交，不要重做；用 `status` 修复公开画面。

私档包含隐藏基价、精确预算、箱内物品及随机状态；玩家与画面只能读公开输出。这是接口约定，不是操作系统沙箱，不抵抗私档编辑或恢复备份。

## 验证与临时数据

```sh
python3 -m unittest discover -v
python3 make_dice_fixtures.py
python3 make_management_fixtures.py
python3 simulate_management_v6.py --games 50 --days 40
```

自动化测试代码和合成数据生成器保留。测试所需场景在临时目录生成，结束后自动清理；直接运行两个生成器也只作临时验证。演示用假存档、公开投影、演练记录及截图不再放入仓库或发布包。真实存档独立保存，不属于演示清理范围。`management-simulation.json` 是有限样本的平衡统计报告，不是可载入的演示存档。

观战器操作：1–5切页，←/→翻页，点击物品查看逐买家资格，点击骰卡查看历史，Esc关闭详情，F11全屏。

详见 [店主手册](PLAY_GUIDE.md)、[观察schema](OBSERVATION_SCHEMA.md)、[QA报告](QA_REPORT.md)、[经营试验](BALANCE_REPORT.md)。仿真只测公开策略的有限样本，不等于真人体验或全策略平衡证明。

主要文件：`test_catalog_privacy_v7.py`、`test_catalog_spectator_v7.py`、`engine.py`、`spectator.py`、`_legacy_v1.py`至`_legacy_v5.py`、`test_management_v6.py`、`simulate_management_v6.py`。旧版本的专门测试针对冻结旧引擎，当前通用经营/持久化及v6契约测试针对v6。

许可协议尚未选定，本目录未授予额外开源许可。
