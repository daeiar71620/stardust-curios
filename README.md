# 星屑杂货铺 v9 · 预算之外，也有商量的余地

初次出售不再因超过隐藏预算1星币就骤降到只剩01。特邀顾客和普通旅客的预算都表示**常规消费舒适度**；预算内沿用原成功率，超出后按幅度逐步降温。01奇迹、100失手、公开还价资格和最终报价公式保持不变。

## 操作后同步手机网页

`tools/web_sync/shop.py` 通过固定的私有当前店铺配置执行一条已经选定的官方操作，保存结果，再同步到已核实的私人网页，并检查服务器回执。相同操作ID重试不会再次操作游戏；上传失败只恢复同步。不替AI作选择，也不自动开局、迁移或继续到第八天。

```sh
python3 tools/web_sync/shop.py --current /absolute/private/current-shop.json
```

配置示例、隐藏stdin输入、开局授权、会话绑定及中断恢复见 [同步运行手册](tools/web_sync/SESSION_RUNBOOK.md)。运行配置、回执、真实存档与已发现图片留在私有目录；仓库只含通用工具和合成测试。使用需要兼容回执协议的私人服务端，本代码包不包含个人网站部署或凭据。

## 初次预算曲线

令`reference`为隐藏实际参考价值，`budget`为买家当天隐藏常规预算，`bonus`为冻结加值：

```text
raw = 60 + bonus − 50 × log2(price / reference)
base = clamp(1, 99, raw)
excess = max(0, price / budget − 1)
threshold = clamp(1, 99, floor(base / (1 + 2 × excess)))
```

先夹限基础率，再施加超预算比例，最后向下取整并夹到1–99。预算不是硬性购买力上限；超过预算仍可能普通成功，涨价越多越难。隐藏参考价值和精确预算继续保密，售前不显示初次精确成功率。

纯公式示例：`reference=budget=100`、`bonus=0`时，报价99/100/101/110/150/200/300对应阈值60/60/58/44/15/3/1。这不是对实际货物的预测。

个人珍藏接受任何品相；阶段目标现在只计算达到当前品相要求的不同藏品。收藏柜可修理，也可花1精力用更好的同款一换一，旧件回到货架。

## 品质收藏目标

| 阶段 | 合格收藏 | 品相门槛 | 合格类别 | 品质主题 |
|---|---:|---:|---:|---:|
| 首周站稳脚跟 | 2种 | 70% | 不限 | 不限 |
| 街区熟面孔 | 5种 | 75% | 至少3类 | 不限 |
| 夜航灯塔 | 9种 | 80% | 不限 | 至少1套 |
| 星港地标 | 15种 | 85% | 全5类 | 至少3套 |

品质主题指同一类别的3种不同收藏，且全部达到当前阶段门槛。原来的任意品相3种同类收藏经营收益保持不变。现金、口碑、设施要求及收藏规则保持v8原样。已获得的里程碑不撤回。

星海长航保持原有收藏17/19/21/23/24种后封顶24、现金每章+3000、口碑最多99；品质门槛86/87/88/89/90%后封顶90%，全5类，主题首章4套、之后5套。不会提出超过24种或5套的要求。

```sh
python3 engine.py inspect I001
python3 engine.py repair I001
python3 engine.py replace-collection I002
```

`repair`可找货架或收藏柜的物品，仍花2精力、原费用、每件共2次且每天1次；失手仍降品相。`replace-collection`只能用货架中严格更好的同款替换柜中旧件，花1精力，不掷骰；两件的编号、来源、标价、隐藏估值、修理次数和当日限制都保留。满货架也能一换一，不重复触发套装奖励。收藏柜不能直接出售或改价。

本版私档和公开协议为 **version 9**，新交易规则标签为9。新增`import-v8`；`import-v1`至`import-v6`继续可用，均只复制到全新路径，绝不自动迁移。v8复制保留原有品质目标及已有过渡；v1–v6复制仅当前未完成阶段保留旧收藏数量条件，下一阶段启用品质规则。已结算的首周结果与已获里程碑保留。真实游戏没有随本次开发迁移或推进。

## 图鉴要亲手发现

- 尚未开到的条目统一显示 **???** 和相同的未知标记，不预告名字、形状、类别、稀有度或故事
- 只有真正开箱才解锁画像与档案。买到未拆封的箱子不会解锁；卖掉已见过的物品也不会忘记
- “已发现”和“已珍藏”分别计数。收藏套装继续公开进度和经营收益，不列出未知物品的名字
- CLI与公开observation也遵守同一边界。新版观战器会遮住旧版公开文件里尚未发现的条目
- 读取当前v9的 `status` 只刷新公开投影，不推进天数、骰子或游戏资源。v8及更早旧私档需明确复制导入

v6的经营取舍保持不变：**普通旅客限量且有常规预算；普通失败不再必送还价**。

## 小店的新取舍

- 普通旅客每天 **1次接待**，公开常规预算 **60–120星币**，当日精确消费舒适度隐藏。正式 `sell` 尝试即占用，无论成功、还价、拒绝或100；错误命令不占用
- 普通失败只有满足公开条件才提出还价：标价不超过 **公开参考价的125%**、不超过买家公开常规预算区间上限，且至少2星币；特邀顾客还要求类别匹配及达到其品相期待，普通旅客要求品相 **≥45%**
- 不满足条件仍可尝试初次出售；普通失败会直接离店，物品留下。**01仍按合法标价成交，9999也可以；100仍立即结束接待**
- `status` / `inspect I001` 免费显示每位买家的还价资格、原因和风险。观战器显示剩余旅客、常规预算范围，以及物品的逐买家还价条件
- 资格只用公开信息，没有额外隐藏“是否愿谈”骰。它不保证初次成交，也不公开初次精确成功率；初次预算曲线变平滑不会放宽还价资格

售价、回收进价、维护费、升级成本及所有加值不变；本次只替换初次超预算的一刀切判定。配对顾客、修理、等待与选择进货量现在更有意义。

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
python3 engine.py --save /path/to/new-v9-copy.json import-v8 /path/to/old-v8-save.json
python3 spectator.py --observation /path/to/new-v9-copy.observation.json
```

v1–v6分别使用 `import-v1` 至 `import-v6`；v7发行包的私档协议是6，也使用`import-v6`。必须提供完整私档，公开observation不能代替。已有目标私档或投影均不覆盖。

- v8复制保留`collection_upgrade`，不赠送新过渡；v1–v6当前旧阶段的过渡记录写入存档，读取、重启不会重置。v9不能伪装成v8或更早版本再次导入
- v8/v6复制保留已承诺的还价、旅客名额、骰史和全部资源。v3/v4历史仍是原D20；v5/v6历史仍是原百分骰。新骰标记v9，不重判旧骰；待谈同时标出原始规则版本
- `budget_upgrade`公开记录来源版本、原骰序号、日期和阶段；新局为null，不公开来源路径、隐藏预算或随机状态
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

主要文件：`test_budget_curve_v9.py`、`test_budget_audit_v9.py`、`test_budget_spectator_v9.py`、`test_collections_v8.py`、`test_collection_spectator_v8.py`、`test_catalog_privacy_v7.py`、`test_catalog_spectator_v7.py`、`engine.py`、`spectator.py`、`_legacy_v1.py`至`_legacy_v6.py`、`_legacy_v8.py`、`test_management_v6.py`、`simulate_management_v6.py`。旧版本的专门测试针对冻结旧引擎，当前通用经营/持久化及兼容交易契约测试针对v9引擎。

许可协议尚未选定，本目录未授予额外开源许可。

## 固定当前店铺与自动同步

现在可通过私有的current-shop.json固定入口操作当前游戏；一次命令完成已授权的复制升级、原子切换与公开画面同步，换档不再需要重建网站。旧会话上传会被epoch保护拒绝，重复操作ID不会重新执行。完整步骤与恢复说明见[运行手册](tools/web_sync/SESSION_RUNBOOK.md)。

本轮在临时存档完成全项目测试和81步完整链路检查；性能数据与限制见[性能报告](PERFORMANCE_REPORT.md)。测试与基准源码均保留，实际存档、凭据和运行配置不在发布包里。

## 同步阶段诊断

同步入口还提供发送凭据前的明确目的地说明、脱敏阶段日志和本地提交／最后耐久回执状态；这些状态不宣称手机已实时收到新结果。详见[诊断验证报告](DIAGNOSTICS_REPORT.md)与运行手册。

## 可选架构实验：同一权威状态

[本地实验工具](tools/experimental_colocated/README.md)把官方CLI放在临时副本中执行，将私档、白名单公开画面与操作回执一起提交到SQLite。它只做合成概念验证，没有HTTP服务或生产认证，不会替换现用引擎，也不提供真实存档迁移。不能直接暴露到公网或据此宣称网站已部署。

从仓库根目录分别运行两套测试，使用独立Python进程：

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools/web_sync/tests -v
STARDUST_TEST_ENGINE="$PWD/engine.py" PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools/experimental_colocated/tests -v
python3 tools/experimental_colocated/benchmark.py --engine "$PWD/engine.py"
```

两套工具各有自己的public_projection模块，不要在同一长期Python进程里混合导入它们。实验的40项本地检查、原子提交边界、图片存储限制及部署前缺项见[验证记录](tools/experimental_colocated/VALIDATION.md)和[架构说明](tools/experimental_colocated/ARCHITECTURE.md)。未测公网、平台审核或手机延迟；临时CLI计算可能在崩溃回滚后重算，保证的是权威提交幂等。

## 可选实验：Worker 原生 v9 规则移植（G2）

[TypeScript 移植包](tools/experimental_worker/README.md)保留 Python 官方引擎作为参考，覆盖13种原生v9变更操作和6种公开读取。冻结的G2源码通过2,205项测试，另有1项明确保留的任意浮点log2边界TODO；没有意外失败。20轮混合合成流程比对11,303条命令和143,838次读取。v8继承验证仍是有边界的离线测试，不提供真实存档导入。

需要Node 24、Python 3及本仓库官方源码，从仓库根目录运行：

```sh
STARDUST_ENGINE_SOURCE="$PWD/engine.py" PYTHONDONTWRITEBYTECODE=1 \
node --experimental-strip-types --test --test-concurrency=1 tools/experimental_worker/tests/*.test.mjs
```

测试在内存中生成样本，完整序列可能需要约11分钟。服务端模块包含隐藏规则与图鉴，不应打包到浏览器。公开包不含私人网站配置、凭据或托管服务；生产适配器另行管理。

[G2验证检查点](tools/experimental_worker/G2_CHECKPOINT.json)区分本地差分测试、托管适配器检查、部署与实际工具调用：G1连接工具和手机路径已确认，G2部署后旧读取已看到合成状态，但检查点时新工具目录尚未刷新，G2新动作的在线验证仍待完成。不要把部署成功称作生产迁移完成。任意浮点全域等价、旧版本完整兼容、真实存档迁移和图片交付仍受[契约边界](tools/experimental_worker/docs/ENGINE_CONTRACT.md)约束。
