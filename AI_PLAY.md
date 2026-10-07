# AI 经营指南

你是店主，`engine.py` 是裁判。使用普通 CLI，一次提交一个动作，读到公开结果后再选择下一步。有桌面时用户可看 `spectator.py`；没有桌面时直接根据公开 JSON 经营。

## 先确定这一局

记住项目目录、用户选定的存档路径和对应公开文件。后续每个命令都使用同一 `--save` 路径。优先使用绝对路径，避免切换工作目录后误入另一局。

已有游戏先看：

```sh
python3 engine.py --save /path/to/my-shop.json status
```

仅在用户确实要开新局时，对不存在的路径执行 `new`。缺失、损坏或不支持的存档都不能成为自动重开的理由；保留原文件并说明问题。`new` 不覆盖已有文件，`restart --confirm` 会清空整局，不能作为普通错误恢复或重掷手段。这里只支持原生 v10，没有导入、迁移或旧版本兼容入口。

v10 的经营规则已更新，只能另开新档。不要用新版打开或迁移 v9 私档；旧局可保留原程序继续。继续同一份 v10 游戏时明确指定原路径，不因代码位置改变而重建这一局。

公开路径规则：默认的 `engine.py` 同目录 `save.json` 对应 `observation.json`；其他路径取文件主名加 `.observation.json`，例如 `/path/to/my-shop.json` 对应 `/path/to/my-shop.observation.json`，其他目录的 `save.json` 对应 `save.observation.json`。显式 `--save` 若仍指向默认那个文件，沿用默认规则。

可选窗口必须指向这一局的公开文件：

```sh
python3 spectator.py --observation /path/to/my-shop.observation.json --fullscreen
```

窗口缺文件时等待，不替你开局。无显示环境时照常使用引擎。安装与系统限制见 [README.md](README.md)。

## 每一步怎样玩

1. 读取 CLI 返回的公开状态；接手已有局或结果有疑问时先执行 `status`
2. 检查 `phase`、精力、现金、维护费明细、实际阶段期限、当前逾期费、货架容量、供应商库存、顾客剩余次数、当前谈判和下一阶段目标
3. 用公开信息选一个合法动作，并说明这一步的取舍；有需要可先免费 `inspect` 或 `preview-offer`
4. 执行一个命令，等待完成并保留返回结果中的 `revision`、`last_event` 和有关状态
5. 根据实际结果重新判断；不要预写依赖未知开箱、骰点或成交结果的整串命令

不要并发提交经营动作，也不要用循环把一天或一周自动跑完。只在用户授权的经营范围内推进。`week_summary` 表示首周已结算，明确选择 `continue` 后才进入第 8 天；`lost` 表示破产，停止经营。其他里程碑不是游戏截止日期，可持续经营。

命令总是采用这一形式，`--save` 放在命令前：

```text
python3 engine.py --save PATH COMMAND [ARGS]
```

| 目的 | COMMAND [ARGS] |
|---|---|
| 完整公开状态 | `status` |
| 当天市场／顾客／图鉴 | `market`／`visitors`／`codex` |
| 第 8 天后定向采购 | `buy focused KIND`，类别和剩余名额看公开供应商信息 |
| 采购／开箱 | `buy salvage` 或 `buy curated`／`open CRATE_ID` |
| 查看货架或收藏中的物品 | `inspect ITEM_ID` |
| 标价／修理 | `price ITEM_ID PRICE`／`repair ITEM_ID` |
| 接待普通旅客 | `sell ITEM_ID` |
| 接待今日特邀顾客 | `sell ITEM_ID CUSTOMER_ID` |
| 接受／谢绝当前还价 | `accept ITEM_ID`／`decline ITEM_ID` |
| 免费预览／提交唯一最终报价 | `preview-offer ITEM_ID PRICE`／`offer ITEM_ID PRICE` |
| 收藏／用更好的同款替换收藏 | `collect ITEM_ID`／`replace-collection ITEM_ID` |
| 升级设施 | `upgrade workbench`、`upgrade shelf` 或 `upgrade display` |
| 闭店／首周结算后继续 | `endday`／`continue` |

编号、可用动作、成本、报价边界均以当前公开输出为准。`status` 和 `preview-offer` 返回完整公开状态；`market`、`visitors`、`codex`、`inspect` 返回公开子集。成功经营动作返回提交后的完整公开状态。

## 公平信息边界

可以读公开 CLI 输出和匹配的 observation 文件。禁止为真实游戏决策打开私档、打印引擎私有状态、读取隐藏实际基价或精确预算、查看未拆箱货物、检查或推进 RNG。不要利用源码中的图鉴清单或插画预先揭露尚未发现的物品。

禁止指定种子选结果、试跑后恢复备份、改存档、回滚骰点或重开局挑收益。开箱内容购买时已经固定，关窗口与重新运行 CLI 都不重抽。演示、确定性测试和真实经营必须分开；测试只能使用合成数据和临时路径。

可以根据公开估值、品相、热需、预算范围和顾客偏好作判断。预算是消费舒适度，超出后初次成功率平滑下降；它不是硬性购买力上限。但精确预算与实际参考价值隐藏，不能声称知道初次报价的精确成功率。掷骰后公开的阈值只说明那次已发生的检定。

还价资格由 `sale_options` 公开说明，资格成立不保证初次成交。普通旅客每天只有一次接待；物品和特邀顾客也有每日限制。01 大成功、100 大失败。天价 01 奇迹是规则的一部分，不能把它描述成稳定收入或无风险策略。

## 谈判与经营取舍

- 存在 `negotiation` 时先处理其接受、谢绝或最终报价选择；不能同时出售另一件货
- 接受公开还价不耗精力、不掷骰；最终报价耗 1 精力，且必须满足“还价 < 最终价 < 初次标价”
- `preview-offer` 给出精确最终成功率，不写私档、不耗资源、不推进随机数；提交后失败收入为 0，不能再接受旧还价
- `last_roll` 可能只是历史骰点；实际成交收入要看最新事件、现金与谈判状态，不把旧失败报价当成收入
- 留出完整 `operating_cost`，并读 `operating_cost_breakdown`；闭店先自动谢绝待谈、支付当天费用，再核验阶段，不能把扣费前的现金当成已经达标
- 首周设施费为 0，但 `facility_upkeep_from_day8` 和升级详情会公开未来开销；决定升级前同时看一次性成本和日费
- 以 `campaign.next_milestone.effective_due_day` 为实际期限；逾期不会直接判负，但当前阶段从次日开始产生封顶加费。完成后旧逾期记录保留，不继续叠收
- 定向采购每日只有一箱，价格高于普通精选箱，采购精力相同；根据公开的类别缺口选择，不根据未发现身份猜测下一抽，也不把它当作保证新品或保证好品相
- 个人收藏允许任何品相，阶段进度只算达到当前门槛的不同藏品；以 `collection_progress` 和 `campaign.next_milestone` 判断缺口
- 收藏柜可修理，也可花 1 精力用货架上严格更好的同款一换一；依据公开可用性判断，不假定旧藏品已达新阶段门槛

## 超时、重复与持久化警告

引擎采用文件锁和原子写入，但**没有动作 ID 或幂等请求去重**。再次发送 `buy`、`repair`、`endday` 等并不表示“只重取上次结果”。

调用前保留公开版本号与相关状态。若输出丢失、调用超时、连接中断或出现 `persistence_warning`：

1. 停止发送经营动作，不直接重试原命令
2. 对原存档路径执行 `status`，获得引擎重新生成的公开状态
3. 对照此前的 `revision`、`last_event`、近期 `log`、库存、现金、精力、日期与 `negotiation`，核对目标动作是否已提交
4. 已提交就从新状态继续；证据不足就暂停并说明不确定处。只有确认未提交且原动作仍适用，才把它当作下一步重新选择

单凭 `revision` 增加不能证明是哪一步完成，尤其不能据此重放动作。只读命令和预览不增加版本号；公开文件也可能滞后，所以优先用 `status` 返回值核对。

`persistence_warning` 表示私档可能已经成功提交，或公开文件刷新遇到问题，不等于动作失败。检查目录权限、空间或同步问题后，用 `status` 修复公开文件，不能通过覆盖私档解决。CLI 退出码 2 的游戏校验拒绝不改私档；若是 I/O 错误或无法判断错误发生阶段，也先查状态。

完整玩法见 [PLAY_GUIDE.md](PLAY_GUIDE.md)，字段定义见 [OBSERVATION_SCHEMA.md](OBSERVATION_SCHEMA.md)。
