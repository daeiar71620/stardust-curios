# 开局、操作、同步与恢复

这个工具把一条已经选定的操作和网页同步接起来。AI负责选操作；代码负责执行一次、保存结果、同步公开画面。它不会自主决定下一步，也不是常驻程序。

运行环境：Linux/macOS的Python 3.10+，沿用游戏的Pillow依赖。当前使用POSIX文件锁；不要在不支持该锁的平台删掉锁强行运行。

## 1. 开始前，只做必要核对

1. 明确这是继续哪一局，还是新开一局。重开、复制导入、进入第八天都要有对应的用户要求，不能由同步工具顺手执行
2. 通过 Sites 工具确认准确网址、项目ID、当前账户是 owner，且网站仅 owner 可见。确认这是本次用户授权的目的地。不要把“能访问”当作“可以发数据到那里”
3. 指定本局引擎、私档路径和对应的公开 observation 路径。控制器只把私档路径传给官方CLI，不读取私档内容。v9不能直接打开v8私档；需在明确授权后复制导入到新的路径
4. 网站配置、运行时配置中的 session_id/session_epoch 必须对应本局。切换游戏要明确调整网站当前会话；不能只把新存档指向旧会话
5. 把 tools/web_sync/config.example.json 的占位符替换为本次已核实的值，保存到私有运行目录，不提交Git。owner_private_verified只能在第2步核实后为true。保持该配置、outbox目录和本局路径不变；控制器会拒绝悄悄换目的地、引擎或恢复目录
6. 从 Sites 工具取得该站已有的服务访问，放在工具内存中。不要新建凭据；不要放入配置文件、环境变量、命令参数、网页或聊天

已有授权足够覆盖的相同步骤，不要重复询问。若请求范围、目标站点或游戏会话发生实质变化，再补齐缺少的授权。

## 2. 给执行者的交接模板

交接中一起提供：

- 原始用户请求：逐字引用本次授权的原话；如需上下文，连同此前明确的网址与用户回应一起提供
- 已核实的准确私人网站网址与项目ID，以及仅owner可见的检查结果
- 本次具体游戏会话、公开观察文件、允许的操作范围与停止条件
- 可以发送的内容：白名单公开游戏投影、已经发现的图片；不发送私档、RNG、隐藏预算、凭据或其他个人数据
- 每次选择一条官方操作，由下述控制器完成操作后上传；到约定结算点停止

真实原话、私有网址、项目ID和运行路径留在当前私有任务交接中。不要写入公共仓库。授权证据不能塞进HTTP头或上传内容来代替审核；也不能绕过拒绝。

## 3. 单次操作控制器（兼容入口）

后续会话统一使用下文固定的 `shop.py` 当前店铺入口；本节说明底层控制器协议。不要同时绕过当前店铺锁运行两种入口。

```text
python3 tools/web_sync/action_publish.py --config /absolute/private/config.local.json
```

启动后会等待隐藏stdin中的一行JSON。执行者从自己的工具内存填入access，不把实际值打印或写入文件：

```json
{
  "access": {"project_id": "VERIFIED_PROJECT_ID", "token": "FROM_TOOL_MEMORY_ONLY"},
  "operation_id": "unique-id-for-this-chosen-action",
  "action": ["buy", "salvage"]
}
```

operation_id在重试和恢复时必须保持原值，不能换ID假装这是新操作。它不是游戏命令，也不是后台任务。

控制器会：

1. 锁住这局游戏的控制器入口，检查本局绑定和未解决的操作
2. 如果还有已提交但未同步的公开状态，先同步最新状态；首次同步也核实服务器接受的是这一会话
3. 持久保存intent和running，再通过argv运行官方CLI一次，不经过shell拼接
4. 保存提交后的公开revision/hash，上传白名单JSON和新增/变化的已知图片
5. 检查服务器返回的会话、revision及本次请求字节的SHA-256；成功后才保存同步回执并退出

只有 `ok: true` 且 `verification: server_commit_ack` 才代表这次同步完成。不必每步打开浏览器或另查网页。手机自己每2秒检查新进展。

## 4. 失败时只修失败的那一步

- 连接超时、暂时网络故障，以及408/429/500/502/503/504：最多3次上传尝试，间隔1秒、2秒；每次网络等待最多20秒。始终只重试同一公开状态，不重做游戏操作
- 401/403、TLS错误、其他HTTP拒绝、回执会话或哈希不符：立即停下。不要换账号、域名、网络路线或新建token绕过。向负责执行的人报告具体缺少的授权或状态
- 工具层“approval review canceled”不等于已知HTTP403，也不证明游戏没执行。保留操作ID和恢复记录，不能自动重跑
- 引擎成功、上传失败：使用同一操作ID重试，会只同步；也可以执行下面的sync模式
- 引擎异常退出，或成功提交后公开投影没写好：结果可能已进入私档。即便投影revision没变，也不能认定没有提交

sync只上传当前公开状态，不操作游戏：

```json
{"access":{"project_id":"VERIFIED_PROJECT_ID","token":"FROM_TOOL_MEMORY_ONLY"},"mode":"sync"}
```

代码会上传最新已提交的公开状态，不把旧回执中的快照覆盖回网页。如果发现本地revision回退或应有的投影尚未刷新，会停下。

## 5. 中断后的不确定结果

本局没有引擎原生幂等actionID。进程可能刚完成游戏提交、还没记下回执就被杀。因此这里提供“同一个ID不自动执行第二次”的保护，不宣称跨任意崩溃的严格exactly-once。

同一ID处于intent/running/uncertain时，不能再执行它。reconcile会调用官方只读status来修复公开投影，返回操作前后的公开revision供核对：

```json
{"access":{"project_id":"VERIFIED_PROJECT_ID","token":"FROM_TOOL_MEMORY_ONLY"},"mode":"reconcile","operation_id":"the-original-id"}
```

仅靠revision增加也无法证明一定是原操作，尤其有人绕过控制器直接用了CLI。负责执行的人应结合公开日志检查；确认后才显式添加 `"resolution":"committed"` 或 `"resolution":"abandoned"`。这会标记为operator_review，不会伪称引擎提供了幂等证明，也永远不会重新执行原ID。abandoned只表示不再追究这次不确定操作，不表示它一定没发生。

记录使用原子替换和fsync保存。游戏锁会由正在运行的引擎子进程继承；父进程被杀时，不能趁引擎尚未退出再发下一步。不要清除锁/绑定/回执来强行继续。

## 6. 结算和收尾

- 到约定的第七天结算就停下，发布状态自动标记finished；不自动continue
- 保存成功的最终网页回执，用户页面可显示最后结算
- 如已获授权，另行制作私有存档备份。真实存档、运行配置、outbox和图片发布回执都不进入公共仓库
- 新一局采用全新游戏路径和明确的新会话；旧局保持原样

## 7. 部署契约与测试

私有网站的POST /api/ingest必须返回 `ok,session_id,session_epoch,revision,digest,request_sha256,published_at`。request_sha256是收到的完整UTF-8请求体的SHA-256；digest是服务器实际保存的白名单投影摘要，两者不是同一种哈希。控制器只接受固定配置中的同一HTTPS Sites目的地，拒绝重定向。

```text
python3 -m unittest discover -s tools/web_sync/tests -v
```

测试使用临时合成存档和假的HTTP响应，既有假的引擎执行器故障测试，也保留真实官方CLI的集成测试。不会运行用户真实游戏，不会向生产写入合成状态。Pillow仅在需要导出新发现图片时使用，沿用游戏的既有依赖。

## 8. 性能与等价性核验

同步过程保留原有文件锁、私档/公开投影原子保存、fsync和操作ID去重，不更改游戏公式或随机数：

- 已知图片缓存按渲染器内容、尺寸和公开绘画字段校验；文件还要通过PNG格式与SHA-256核验。只重画缺失、损坏或输入改变的已知图片。每步同步不再生成联系表；独立导出仍默认生成，`--no-preview`可明确关闭
- 同一次独占游戏锁期间，历史操作回执只完整读取和校验一次；新回执写入成功后才进入本次内存索引。离开锁就丢弃索引，下一次调用重新检查磁盘。不会因长期缓存而漏掉中断恢复或损坏记录
- `publication_epoch`只是已核实切换得到的当前发布租约；原配置、绑定和操作日志身份保持不变。再次激活旧游戏不会得到一套空白操作ID历史。激活成功可保存核实后的回执，不需要紧接着再上传同一状态
- 网络仍只接受固定目的地的服务端提交回执。图片是否已上传，只根据成功确认后的哈希记录决定。失败不更新缓存，不重复游戏动作

以下检查只生成临时合成存档、图片与回执，结束时自动清理，保留测试脚本。不要以真实私档替代其临时目录，也不要把测试接到生产HTTP接口。

```text
python3 -m unittest discover -s tools/web_sync/tests -v
python3 tools/web_sync/smoke_pipeline.py --game .
python3 tools/web_sync/benchmark_pipeline.py --game . --output /tmp/stardust-pipeline-timings.json
```

`smoke_pipeline.py`使用官方CLI完成一轮合成首周，每步都做公开投影、已知图片导出和模拟上传回执，检查重复ID不重做动作、临时上传失败只重传、未知条目不泄露，以及第7天结算后停止。`benchmark_pipeline.py`分别计时加载、保存、投影、CLI、导图、请求准备和历史回执扫描；其中HTTP是内存模拟，结果不代表真实公网、Sites或手机延迟。

## 固定的“当前店铺”入口

新入口使用一个私有 current-shop.json 文件，平时操作不用再选存档路径：

```text
python3 tools/web_sync/shop.py --current /absolute/private/current-shop.json
```

隐藏输入仍是access、唯一operation_id和一条action。入口读取当前店铺的已验证配置，执行后自动同步。所有现代操作与切换共用此文件及其锁；不要同时绕过入口运行旧脚本。

切换到一份已经准备好的游戏：

```text
python3 tools/web_sync/shop.py --current /absolute/private/current-shop.json --target-config /absolute/private/next/config.local.json
```

```json
{"access":{"project_id":"VERIFIED_PROJECT_ID","token":"FROM_TOOL_MEMORY_ONLY"},"mode":"switch","switch_id":"unique-switch-id"}
```

若需把v8复制到新的v9目标，在同一请求加入copy_import：

```json
{"copy_import":{"source_save_path":"/absolute/private/old-game.json","source_observation_path":"/absolute/private/old-game.observation.json"}}
```

使用官方默认save.json与observation.json时，额外提供source_engine_path，准确指向旧版本engine.py以验证默认文件配对。旧私档只交给官方import-v8读取；不会覆盖来源。目标已存在时不会重新导入；复制结果不确定时先只读status核对，不重做导入。

候选公开画面和所有已知图片先准备好，再由owner鉴权的服务器以expected_epoch原子激活。每次激活返回新的递增epoch，同一switch_id的重试只返回原结果；过期切换不能把新版店铺改回旧店铺。图片按激活命名空间保存，失败的准备或上传不会污染当前店铺。切换不需要重新部署网站。

公开状态未变化时网页收到304，不再反复下载整份记录；仍每2秒检查，并保留上次进展时间与断线提示。

若切换时进程中断，当前文件会保留switching状态并阻止游戏操作。使用同一switch_id和mode=recover_switch恢复：服务器若已激活目标，只补齐本地指针；尚未激活则完成原切换；若另一个更晚的切换已生效则停止，绝不回退它。不会为了恢复网页再运行一次游戏动作或复制导入。

跨会话的运行期epoch与原来的操作ID账本分开保存。重新激活同一游戏仍保留它所有操作ID，重复ID不会再操作一次。旧版直接action_publish入口仅用于兼容；后续会话应统一使用固定shop入口。
