# 星屑杂货铺 · Python 独立版

一间停在星港边上的小店：回收盲箱、修理旧物、接待旅客，也为自己留下收藏。`engine.py` 是游戏的正式规则与存档入口。直接运行 Python 就能玩；有桌面时可以另开只读观战窗口。

原生 v10 保留双 D10 百分骰、平滑预算和品质收藏，并增加后续阶段期限、温和的逾期维护费、设施日常开销与付费定向采购。包含 24 种货物、8 位特邀顾客、3 项设施、5 套收藏与港口事件。详细规则见[店主手册](PLAY_GUIDE.md)，交给 AI 经营时见 [AI_PLAY.md](AI_PLAY.md)。

## 只用命令行

引擎只用 Python 标准库，不需要安装第三方包。文件锁使用 POSIX `fcntl`，适用于 Linux/macOS，不支持 Windows 原生 Python。

在项目目录运行：

```sh
python3 engine.py help
```

确定要开新局时，选一个尚不存在的存档路径：

```sh
python3 engine.py --save ./games/my-shop.json new
```

以后每次使用同一路径，一次执行一个命令，读完结果再决定下一步：

```sh
python3 engine.py --save ./games/my-shop.json status
```

例如看过当天供应商和价格后，可以采购一箱：

```sh
python3 engine.py --save ./games/my-shop.json buy salvage
```

再使用返回结果中的箱子编号执行 `open`。物品、顾客编号和报价都以当前公开状态为准，不要把教程示例当作批量脚本。

常用命令包括 `market`、`visitors`、`open`、`inspect`、`price`、`sell`、`repair`、`collect`、`replace-collection`、`upgrade` 和 `endday`。`help` 列出完整用法。第 7 天闭店会停在首周结算，明确执行 `continue` 才进入第 8 天；未达首周目标也可继续，破产则结束本局。

## 长期经营的新取舍

首周不收设施费或逾期费；从第 8 天开始，设施按当前等级收少量日常费用。升级前的公开状态会列出现在及第 8 天起的费用，避免升级后才发现固定开销。

阶段名义期限为第 7、14、28、42 天，长航从第 56 天起每章加 14 天。新阶段至少给出 7 天经营窗口；以画面中的实际期限为准。闭店先支付当天公开维护费，再用剩余现金核验阶段目标。未按期完成会留下记录，并允许继续补齐；只对当前逾期阶段加费，每天递增 2、封顶 6，不叠加旧阶段欠费。具体结算和缓冲规则见店主手册。

第 8 天起可用 `buy focused KIND` 付费指定类别：每次 155 星币、1 精力，每天限 1 箱。类别为 `tool`、`artifact`、`bot`、`plant`、`signal`。稀有度和品相分布与精选箱相同，依然可能重复；货物买入即封存，不能靠开箱或读档重抽。

## 可选观战窗口

窗口读取公开状态并自动刷新；经营仍通过 CLI 进行。关掉窗口不会闭店，没有窗口也能完整游玩。

窗口需要 Pillow 12.3.0、Tk、中文字体和可用的图形显示环境。当前绘图器查找 Linux 字体路径，以下以 Debian/Ubuntu 为例；macOS 可直接玩命令行，但窗口尚未提供适配的字体安装流程。

```sh
sudo apt install python3-venv python3-tk fonts-noto-cjk
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements-spectator.txt
python3 spectator.py --observation ./games/my-shop.observation.json --fullscreen
```

1–5 切换货架、旅客、图鉴、成长、日志；←/→ 翻页，点击物品查看详情，点击骰卡查看历史，Esc 关闭详情，F11 切换全屏。窗口不创建存档；公开文件不存在时只等待。

## 存档与公开文件

存档路径和画面路径必须配对：

| 引擎存档 | 对应公开文件 |
|---|---|
| 默认：`engine.py` 所在目录的 `save.json` | 同目录 `observation.json` |
| `./games/my-shop.json` | `./games/my-shop.observation.json` |
| 其他目录的 `save.json`，如 `./games/save.json` | `./games/save.observation.json` |

路径按实际解析后的文件位置判断；显式指定默认那个 `save.json`，仍使用同目录的 `observation.json`。其他自定义路径一律取文件主名加 `.observation.json`。相对 `--save` 路径相对于当前工作目录；省略 `--save` 时，默认存档跟随 `engine.py` 的位置。

私档由引擎维护，包含隐藏价值、精确预算、箱内货物和随机状态。玩家、AI 与窗口只读 CLI 的公开输出或对应的公开文件；不要直接读取或修改私档来决定玩法。

`new` 拒绝覆盖已有存档。已有局用 `status` 接着看；不自动开局、覆盖或重启。`restart --confirm` 会清空所选整局，只有明确想重开时才使用。仅支持原生 v10 新档，没有旧档兼容、导入或迁移入口；遇到不支持的文件请保留原件。

本版改变经营规则，不加载 v9 存档，也不自动迁移。旧局请保留其原文件和原程序；只有明确开新局时才为 v10 选择全新路径。正在运行的旧游戏不会因为更新仓库而被修改。继续同一份 v10 游戏时，始终显式使用原 `--save` 路径。

## 出错时先查状态

合法经营动作成功后返回完整公开 JSON，并增加 `revision`。免费查看和最终报价预览不推进随机数、资源或版本号。参数错误、资源不足等游戏拒绝不会改变私档。

CLI 没有动作 ID 去重机制。若命令超时、输出丢失或收到 `persistence_warning`，不要盲目重发：动作可能已经保存。先对同一路径运行 `status`，用公开 `revision`、`last_event`、`log`、库存与谈判状态核对结果；无法判定时暂停经营。修复目录权限或磁盘问题后，`status` 也会重建公开文件。

跨进程锁能防止写入冲突，不能替调用方去掉重复动作。每局只安排一个经营者，窗口可以一直开着。

## 验证与文件

无桌面、无第三方包时运行引擎与独立入口测试：

```sh
python3 run_tests.py --headless
```

装好观战依赖与字体后运行完整测试：

```sh
python3 run_tests.py
```

测试使用合成场景和临时目录，不读取或推进真实游戏。发布包不包含玩家存档、真实公开状态或游玩截图。

- `engine.py`：正式规则、CLI、私档与公开投影
- `spectator.py`：只读窗口与原有 24 种物品绘图
- `AI_PLAY.md`：AI 逐步经营约定
- [PLAY_GUIDE.md](PLAY_GUIDE.md)：完整玩法与规则
- [OBSERVATION_SCHEMA.md](OBSERVATION_SCHEMA.md)：公开 JSON 协议
- [QA_REPORT.md](QA_REPORT.md)：验证范围与结果
- `run_tests.py`、`test_*.py`：测试入口与合成测试

许可协议尚未选定，本目录未授予额外开源许可。
