'use client';
/* eslint-disable @next/next/no-img-element */
import {createContext, useContext, useEffect, useRef, useState, type ReactNode} from 'react';
import {ArrowLeft, BookOpen, Check, ChevronRight, Coins, Dice5, Gem, Heart, PackageOpen, Radio, RefreshCw, ScrollText, Sparkles, Users, WifiOff, Wrench, X, Zap} from 'lucide-react';
import {createSpectatorSync, knownImagePath, POLL_MS, resolveDetail, retryDelay, type SpectatorSync, type SyncState} from '@/lib/spectator-sync.mjs';
import type {DetailSelection, DetailValue, Goal, PublicArt, PublicItem, PublicNegotiation, PublicObservation, PublicRoll, SpectatorSnapshot} from '@/lib/spectator-types';
import styles from './shop.module.css';

const kinds = {tool: '工具', artifact: '奇物', plant: '植物', bot: '机械伙伴', signal: '信号'};
const rarities = {common: '普通', rare: '稀有', legendary: '传说'};
const tabs = [
  ['inventory', '货架', PackageOpen], ['customers', '顾客', Users], ['catalog', '图鉴', BookOpen],
  ['collection', '收藏', Gem], ['upgrades', '设施', Wrench], ['logs', '日志', ScrollText], ['dice', '骰子', Dice5],
] as const;
type Tab = typeof tabs[number][0];
const initialSync: SyncState = {snapshot: null, status: 'loading', checkedAt: null, checking: false, failures: 0, imageEpoch: 0, notice: null};
const ArtContext = createContext<{snapshot: SpectatorSnapshot | null; retry: number}>({snapshot: null, retry: 0});
const date = (value: string | number) => new Date(value).toLocaleString('zh-CN', {month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false});
const percent = (value: number) => `${Math.round(value * 1000) / 10}%`;
const range = (value: number[]) => value.join('–');

function Meter({value, max = 100, label}: {value: number; max?: number; label: string}) {
  return <div className={styles.meter} role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={max} aria-valuenow={Math.min(max, Math.max(0, value))}><span style={{width: `${Math.max(0, Math.min(100, max > 0 ? value / max * 100 : 0))}%`}} /></div>;
}
function Empty({children}: {children: ReactNode}) {return <div className={styles.empty}><PackageOpen size={28} aria-hidden="true"/><p>{children}</p></div>;}
function Badge({children, gold = false}: {children: ReactNode; gold?: boolean}) {return <span className={gold ? styles.goldBadge : styles.badge}>{children}</span>;}
function Heading({children, aside}: {children: ReactNode; aside?: ReactNode}) {return <div className={styles.heading}><h2>{children}</h2>{aside && <span className={styles.muted}>{aside}</span>}</div>;}
function ImageAsset({src}: {src: string | null}) {
  const [loaded, setLoaded] = useState(false), [failed, setFailed] = useState(false);
  return <div className={styles.art} aria-hidden="true">
    {!loaded && <span className={styles.artPlaceholder}>{failed ? '图像稍后重试' : src ? '图像载入中' : '暂无图像'}</span>}
    {src && !failed && <img className={loaded ? styles.artLoaded : styles.artLoading} src={src} alt="" loading="lazy" onLoad={() => setLoaded(true)} onError={() => setFailed(true)}/>}
  </div>;
}
function Art({item}: {item: PublicArt}) {const {snapshot, retry} = useContext(ArtContext); const src = knownImagePath(item, snapshot); return <ImageAsset key={`${src}:${retry}`} src={src}/>;}
function ItemCard({item, onOpen}: {item: PublicItem; onOpen: () => void}) {
  return <button className={styles.itemCard} onClick={onOpen} aria-label={`查看${item.name}详情`}>
    <Art item={item}/><div className={styles.itemBody}><div className={styles.itemTags}><span data-rarity={item.rarity}>{rarities[item.rarity]}</span><span>{kinds[item.kind]}</span></div><h3>{item.name}</h3><p className={styles.itemDescription}>{item.description}</p>
    <div className={styles.itemNumbers}><span>品相 <b>{item.condition}%</b></span>{!item.collected && <span>标价 <b className={styles.gold}>{item.price}</b></span>}</div><Meter value={item.condition} label={`${item.name}品相`}/>
    <div className={styles.cardFoot}><span>{item.negotiating ? '正在还价' : item.collected ? item.collection_quality.counted ? '合格收藏' : '个人珍藏' : item.sale_attempted_today ? '今日已接待' : '在售'}</span><span>详情 <ChevronRight size={14}/></span></div></div>
  </button>;
}
function Goals({goals}: {goals: Goal[]}) {return <div className={styles.goals}>{goals.map(goal => <div key={goal.key}><div className={styles.goalLabel}><span>{goal.label}</span><b className={goal.met ? styles.mint : undefined}>{goal.current}<small> / {goal.target}</small>{goal.met && <Check size={14}/>}</b></div><Meter value={goal.current} max={goal.target} label={goal.label}/></div>)}</div>;}
function RollCard({roll, compact = false}: {roll: PublicRoll | null; compact?: boolean}) {
  if (!roll) return <Empty>还没有掷骰记录</Empty>;
  return <article className={styles.panel}><div className={styles.heading}><h3>{compact ? '最近一次掷骰' : `第 ${roll.day} 天 · ${roll.stage === 'final' ? '最终报价' : '初次报价'}`}</h3><Badge gold={!roll.success}>{roll.outcome === 'miracle' ? '大成功' : roll.outcome === 'fumble' ? '大失败' : roll.success ? '成交' : '未成交'}</Badge></div>
    <div className={styles.rollBody}><div className={roll.success ? styles.rollNumber : styles.rollFailed}><strong>{String(roll.roll).padStart(2, '0')}</strong><span>D100</span></div><div><h3>{roll.item_name}</h3><p>{roll.customer_name} · 报价 {roll.price} 星币</p><p>成功阈值 {roll.threshold} · {percent(roll.probability)}</p></div></div>
    {!compact && <><p className={styles.diceDigits}>十位 {String(roll.tens).padStart(2, '0')} + 个位 {roll.ones} <span>00 + 0 记为 100</span></p><div className={styles.chips}>{roll.modifiers.map((m, index) => <span key={`${m.label}:${index}`}>{m.label} {m.value > 0 ? '+' : ''}{m.value}</span>)}</div></>}
    <p className={styles.description}>{roll.explanation}</p>
  </article>;
}
function Negotiation({value}: {value: PublicNegotiation}) {
  return <section className={styles.negotiation}><div className={styles.heading}><h2>柜台前的还价</h2><Badge gold>待回应</Badge></div><h3>{value.customer_name} · {value.item_name}</h3><div className={styles.offerAmounts}><span>原标价 <b>{value.original_price}</b></span><span>顾客愿出 <b>{value.counter_offer}</b> 星币</span></div>
    <p>接受可得 {value.accept_income} 星币；还剩 {value.remaining_offers} 次最终报价机会，消耗 {value.final_offer_energy} 精力</p>
    {value.preview ? <div className={styles.forecast}><strong>公开报价预览</strong><p>报价 {value.preview.price} 星币 · 成功率 {percent(value.preview.probability)} · 阈值 {value.preview.threshold}</p><p>成功收入 {value.preview.success_income}；失败收入 {value.preview.failure_income}</p><p className={styles.muted}>{value.preview.warning}</p></div> : <p className={styles.muted}>当前没有合法的最终报价空间</p>}
    <p className={styles.chatHint}>在聊天里让点点接受、谢绝或继续报价</p>
  </section>;
}
function Inventory({o, onOpen}: {o: PublicObservation; onOpen: (selection: DetailSelection) => void}) {
  return <><Heading aside={`${o.inventory.length + o.crates.length}/${o.capacity} 个货位`}>在售奇物 <span className={styles.gold}>{o.inventory.length}</span></Heading>
    <div className={styles.itemGrid}>{o.inventory.map(item => <ItemCard key={item.id} item={item} onOpen={() => onOpen({type: 'item', id: item.id})}/>)}</div>{!o.inventory.length && <Empty>货架空着，等下一件奇物到来</Empty>}
    {o.crates.length > 0 && <section className={styles.panel}><Heading aside={`${o.crates.length} 箱`}>待开封漂流箱</Heading><div className={styles.crates}>{o.crates.map(crate => <div key={crate.id}><PackageOpen size={24}/><div><strong>{crate.name}</strong><p>内容尚未揭晓</p></div></div>)}</div></section>}
    <section className={styles.panel}><Heading>今日进货</Heading>{o.suppliers.map(supplier => <div className={styles.supplier} key={supplier.id}><div><h3>{supplier.name}</h3><p>{supplier.description}</p><span>{supplier.cost} 星币 / 箱</span></div><b>{supplier.stock} 箱</b></div>)}</section>
  </>;
}
function Customers({o}: {o: PublicObservation}) {return <><Heading aside={`${o.visitors.length} 位`}>今日来客</Heading><div className={styles.twoColumns}>{o.visitors.map(visitor => <article className={styles.panel} key={visitor.id}><div className={styles.customerHeading}><div className={styles.avatar} aria-hidden="true">{visitor.name.slice(0, 1)}</div><div><h3>{visitor.name}</h3><p className={styles.muted}>{visitor.role}</p></div><Badge gold={visitor.status === 'negotiating'}>{{waiting: '等候中', negotiating: '还价中', sold: '已成交', bought: '已成交', left: '已离店'}[visitor.status] || visitor.status}</Badge></div><p>{visitor.preference_label}</p><p>品相期待 ≥ {visitor.min_condition}%</p><div className={styles.budget}>公开预算 <b>{range(visitor.budget_range)}</b> 星币</div></article>)}</div>
    <article className={styles.panel}><Heading aside={`还可接待 ${o.walkins.remaining} 次`}>路过的旅客</Heading><p>公开预算 {range(o.walkins.budget_range)} 星币 · 品相 ≥ {o.walkins.min_condition}%</p><p className={styles.description}>{o.walkins.visit_rule}</p></article><p className={styles.sectionNote}>预算只显示公开区间，初次成交概率不会预告</p></>;}
function Catalog({o, onOpen}: {o: PublicObservation; onOpen: (selection: DetailSelection) => void}) {return <><Heading aside={`${o.codex.discovered}/${o.codex.total} 已发现`}>奇物图鉴</Heading><div className={styles.catalogGrid}>{o.codex.entries.map(entry => entry.discovered ? <button className={styles.catalogCard} key={entry.slot} onClick={() => onOpen({type: 'catalog', slot: entry.slot})} aria-label={`查看${entry.name}图鉴`}><Art item={entry}/><span className={styles.catalogNumber}>NO. {String(entry.slot).padStart(2, '0')}</span><h3>{entry.name}</h3><div className={styles.itemTags}><span data-rarity={entry.rarity}>{rarities[entry.rarity]}</span>{entry.collected && <span className={styles.mint}>已收藏</span>}</div></button> : <article className={styles.unknownCard} key={entry.slot} aria-label={`图鉴 ${entry.slot}，尚未发现`}><div aria-hidden="true">?</div><span className={styles.catalogNumber}>NO. {String(entry.slot).padStart(2, '0')}</span><h3>尚未发现</h3></article>)}</div></>;}
function Collection({o, onOpen}: {o: PublicObservation; onOpen: (selection: DetailSelection) => void}) {
  const progress = o.collection_progress;
  return <><Heading aside={`品相 ≥ ${progress.min_condition}%`}>品质收藏进度</Heading><section className={styles.panel}><div className={styles.qualityCounts}><div><strong>{progress.personal_count}</strong><span>个人珍藏</span></div><div><strong>{progress.qualified_count}</strong><span>合格收藏</span></div><div><strong>{progress.quality_themes}</strong><span>品质主题</span></div></div><Goals goals={progress.requirements}/><p className={styles.description}>{progress.missing.length ? progress.missing.join(' · ') : '本阶段收藏要求已满足'}</p><div className={styles.chips}>{progress.categories.map(category => <span key={category.id}>{category.name} {category.qualified_count}{category.theme_complete ? ' ✓' : ''}</span>)}</div></section>
    <Heading aside={`${o.collection.length} 件`}>收藏柜</Heading><div className={styles.itemGrid}>{o.collection.map(item => <ItemCard key={item.id} item={item} onOpen={() => onOpen({type: 'item', id: item.id})}/>)}</div>{!o.collection.length && <Empty>收藏柜还空着</Empty>}
    <Heading>收藏套组</Heading><div className={styles.twoColumns}>{o.collection_sets.map(set => <article className={styles.panel} key={set.id}><div className={styles.heading}><h3>{set.name}</h3><Badge>{set.completed ? '已完成' : `${set.current}/${set.required}`}</Badge></div><Meter value={set.current} max={set.required} label={set.name}/><p className={styles.description}>{set.perk}</p></article>)}</div>
  </>;
}
function Upgrades({o}: {o: PublicObservation}) {return <><Heading aside={`每日维护 ${o.operating_cost} 星币`}>店铺设施</Heading><div className={styles.twoColumns}>{o.upgrade_details.map(upgrade => <article className={styles.panel} key={upgrade.id}><div className={styles.heading}><h3>{upgrade.name}</h3><Badge>Lv.{upgrade.level} / {upgrade.max_level}</Badge></div><p>{upgrade.effect}</p><div className={styles.nextUpgrade}>{upgrade.next_cost === null ? <strong>已达最高等级</strong> : <><strong>下一级 · {upgrade.next_cost} 星币</strong><p>{upgrade.next_effect}</p></>}</div></article>)}</div><section className={styles.panel}><Heading>经营至今</Heading><dl className={styles.facts}><div><dt>已开漂流箱</dt><dd>{o.stats.crates_opened}</dd></div><div><dt>成交次数</dt><dd>{o.stats.sales_count}</dd></div><div><dt>总营业额</dt><dd>{o.stats.gross_earnings} 星币</dd></div><div><dt>营业天数</dt><dd>{o.stats.days_traded}</dd></div></dl></section></>;}
function Logs({o}: {o: PublicObservation}) {return <><Heading aside={`最近 ${o.log.length} 条`}>店铺日志</Heading>{o.log.length ? <section className={styles.timeline}>{[...o.log].reverse().map((line, index) => <article key={`${line.day}:${index}`}><span>第 {line.day} 天</span><p>{line.text}</p></article>)}</section> : <Empty>新的经营记录会出现在这里</Empty>}</>;}
function Dice({o}: {o: PublicObservation}) {return <><Heading aside={`${o.roll_history.length} 次记录`}>百分骰</Heading><section className={styles.panel}><p>{o.trade_rules.critical_rule}</p><p>{o.trade_rules.fumble_rule}</p><p className={styles.description}>{o.trade_rules.house_rules} · 点数不高于阈值即成功</p></section><div className={styles.rollHistory}>{[...o.roll_history].reverse().map(roll => <RollCard key={roll.id} roll={roll}/>)}</div>{!o.roll_history.length && <Empty>还没有正式成交尝试，骰子记录等待揭晓</Empty>}</>;}

function ItemDetails({item}: {item: PublicItem}) {return <><dl className={styles.facts}><div><dt>品相</dt><dd>{item.condition}%</dd></div><div><dt>{item.collected ? '入柜前标价' : '当前标价'}</dt><dd>{item.price} 星币</dd></div><div><dt>公开参考价</dt><dd>{item.public_reference} 星币</dd></div><div><dt>估值区间</dt><dd>{range(item.value_estimate)} 星币</dd></div><div><dt>来源</dt><dd>{item.origin}</dd></div></dl><section className={styles.detailSection}><h3>收藏品质</h3><p className={item.collection_quality.counted ? styles.mint : styles.description}>{item.collection_quality.reason}</p>{item.collection_replacement && <p>柜中同款品相 {item.collection_replacement.cabinet_condition}%；{item.collection_replacement.available ? `可替换，消耗 ${item.collection_replacement.energy_cost} 精力` : item.collection_replacement.reasons.join(' · ')}</p>}</section>
    <section className={styles.detailSection}><h3>修理情况</h3><p>剩余 {item.repairs_remaining} 次修理 · 花费 {item.repair.cost} 星币、{item.repair.energy_cost} 精力</p><p className={styles.description}>{item.repair.available ? '当前可以修理' : item.repair.reasons.join(' · ')}</p></section>
    {!item.collected && <section className={styles.detailSection}><h3>公开接待信息</h3><p className={styles.description}>只显示已知条件。预算区间不代表精确预算，初次成功率不会提前显示</p><div className={styles.saleOptions}>{item.sale_options.map(option => <article key={option.customer_id ?? 'walkin'}><div className={styles.heading}><strong>{option.customer_name}</strong><Badge gold={!option.available}>{option.available ? '可接待' : '当前不可接待'}</Badge></div><p>公开预算 {range(option.budget_range)} 星币 · 品相 ≥ {option.min_condition}%</p><p className={styles.description}>{option.counter_eligible ? `满足普通失败时的还价条件；标价上限 ${option.max_counter_ask} 星币` : option.reasons.join(' · ')}</p><details><summary>接待规则</summary><p>{option.warning}</p></details></article>)}</div></section>}
  </>;}
function DetailDialog({detail, onClose}: {detail: DetailValue | null; onClose: () => void}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {const element = dialog.current; element?.showModal(); return () => {element?.close();};}, []);
  const value = detail?.type === 'item' ? detail.item : detail?.entry;
  return <dialog ref={dialog} className={styles.dialog} aria-labelledby="item-detail-title" onCancel={event => {event.preventDefault(); onClose();}} onClick={event => {if (event.target === event.currentTarget) onClose();}}><div className={styles.dialogInner}>
    <div className={styles.dialogBar}><button onClick={onClose} className={styles.backButton}><ArrowLeft size={18}/> 返回</button><button onClick={onClose} className={styles.iconButton} aria-label="关闭详情"><X size={22}/></button></div>
    {value ? <><div className={styles.detailHero}><Art item={value}/><div className={styles.itemTags}><span data-rarity={value.rarity}>{rarities[value.rarity]}</span><span>{kinds[value.kind]}</span></div><h2 id="item-detail-title">{value.name}</h2><p>{value.description}</p></div>{detail?.type === 'item' ? <ItemDetails item={detail.item}/> : <p className={styles.catalogNote}>{detail?.entry.collected ? '这件奇物已收入收藏柜' : '已发现，尚未收入收藏柜'}</p>}<p className={styles.chatHint}>这里只读观店，经营操作交给聊天里的点点</p></> : <><h2 id="item-detail-title">物品状态已更新</h2><p>这件奇物已不在当前货架或收藏柜中，返回查看最新进展</p></>}
  </div></dialog>;
}

export default function Viewer() {
  const [sync, setSync] = useState<SyncState>(initialSync), [tab, setTab] = useState<Tab>('inventory'), [selection, setSelection] = useState<DetailSelection | null>(null);
  const client = useRef<SpectatorSync | null>(null), loadNow = useRef<(() => void) | null>(null), lastStream = useRef<string | null>(null), openButton = useRef<HTMLElement | null>(null), historyBackPending = useRef(false), queuedSelection = useRef<DetailSelection | null>(null);
  useEffect(() => {
    const connection = createSpectatorSync(); client.current = connection;
    let timer: ReturnType<typeof setTimeout> | undefined, stopped = false;
    const unsubscribe = connection.subscribe(() => {const next = connection.getSnapshot(); if (next.snapshot && lastStream.current && next.snapshot.stream_id !== lastStream.current) setSelection(null); if (next.snapshot) lastStream.current = next.snapshot.stream_id; setSync(next);});
    const load = async () => {clearTimeout(timer); if (stopped || document.hidden) return; await connection.request(); if (!stopped && !document.hidden && connection.getSnapshot().status !== 'unauthorized') {clearTimeout(timer); timer = setTimeout(load, retryDelay(connection.getSnapshot().failures));}};
    const onVisible = () => {clearTimeout(timer); if (!document.hidden) void load();}; loadNow.current = () => {void load();};
    timer = setTimeout(load, 0); document.addEventListener('visibilitychange', onVisible); window.addEventListener('focus', onVisible); window.addEventListener('online', onVisible);
    return () => {stopped = true; clearTimeout(timer); unsubscribe(); connection.dispose(); client.current = null; loadNow.current = null; document.removeEventListener('visibilitychange', onVisible); window.removeEventListener('focus', onVisible); window.removeEventListener('online', onVisible);};
  }, []);
  useEffect(() => {const onBack = () => {const queued = queuedSelection.current; queuedSelection.current = null; historyBackPending.current = false; if (queued) {window.history.pushState({...window.history.state, spectatorDetail: true}, '', window.location.href); setSelection(queued);} else {setSelection(null); openButton.current?.focus();}}; window.addEventListener('popstate', onBack); return () => window.removeEventListener('popstate', onBack);}, []);
  const open = (next: DetailSelection) => {openButton.current = document.activeElement instanceof HTMLElement ? document.activeElement : null; if (historyBackPending.current) {queuedSelection.current = next; return;} if (!selection) window.history.pushState({...window.history.state, spectatorDetail: true}, '', window.location.href); setSelection(next);};
  const close = () => {setSelection(null); if (window.history.state?.spectatorDetail && !historyBackPending.current) {historyBackPending.current = true; window.history.back();} else openButton.current?.focus();};
  const refresh = () => {client.current?.retryImages(); loadNow.current?.();};
  const o = sync.snapshot?.observation ?? null;
  const modeLabel = sync.snapshot?.mode === 'formal' ? '正式店' : '测试店';
  const connectionText = sync.status === 'connected' ? '连接正常' : sync.status === 'unauthorized' ? '需要登录' : sync.status === 'reconnecting' ? '正在重连' : '连接店铺中';
  return <ArtContext.Provider value={{snapshot: sync.snapshot, retry: sync.imageEpoch}}><main className={styles.shell}>
    <header className={styles.topbar}><div className={styles.brand}><span className={styles.brandMark}><Sparkles size={24}/></span><div><p>STARDUST CURIOS</p><h1>星尘奇物铺</h1></div></div><Badge gold>{modeLabel}</Badge></header>
    <div className={styles.connectionBar}><div className={sync.status === 'connected' ? styles.connectionGood : styles.connectionWaiting} role="status">{sync.status === 'connected' ? <Radio size={16}/> : <WifiOff size={16}/>}<span>{connectionText}</span><small>{sync.status === 'connected' ? `${POLL_MS / 1000} 秒检查` : sync.status === 'reconnecting' ? `${retryDelay(sync.failures) / 1000} 秒后重试` : ''}</small></div><button className={styles.refresh} onClick={refresh} disabled={sync.checking} aria-label="刷新店铺"><RefreshCw size={17} className={sync.checking ? styles.spin : undefined}/><span>刷新</span></button></div>
    {sync.status === 'unauthorized' && <section className={styles.notice} role="alert"><h2>登录后继续观店</h2><p>请在本站登录后刷新。{o ? '下方暂时保留上次成功读取的画面' : '登录后即可读取店铺的公开状态'}</p></section>}
    {sync.status === 'reconnecting' && <div className={styles.notice} role="status">暂时没连上店铺，正在自动重试{o ? '，下方保留上次画面' : ''}</div>}
    {sync.notice && <div className={styles.notice}>收到较早的响应，已保留更新的进展</div>}
    {!o ? <section className={styles.waitingRoom}><Sparkles size={34}/><h2>{sync.snapshot && !sync.snapshot.initialized ? `${modeLabel}还未开张` : sync.status === 'unauthorized' ? '等待登录' : sync.status === 'reconnecting' ? '等待重新连接' : '正在打开小店'}</h2><p>{sync.snapshot && !sync.snapshot.initialized ? '在聊天里让点点开始经营，进展会自动出现在这里' : '连接成功后，这里会显示当前店铺的公开进展'}</p><span>点点经营 · 你来观店</span></section> : <>
      <section className={styles.summary}><div className={styles.dayRow}><div><p className={styles.eyebrow}>{o.campaign.title}</p><h2>第 <strong>{o.day}</strong> 天的小店</h2></div><Badge gold={o.phase !== 'active'}>{o.phase === 'active' ? '营业中' : o.phase === 'week_summary' ? '首周结算' : '本局结束'}</Badge></div>
        <div className={styles.stats}><div><Coins size={19}/><span>星币</span><strong>{o.credits}</strong></div><div><Heart size={19}/><span>口碑</span><strong>{o.reputation}</strong></div><div><Zap size={19}/><span>精力</span><strong>{o.energy}<small>/{o.max_energy}</small></strong></div></div>
        <div className={styles.dayEvent}><span>✦</span><div><strong>{o.daily_event.title}</strong><p>{o.demand.label}</p></div></div>
      </section>
      <div className={styles.freshness}><span>最后经营动作 {sync.snapshot?.updated_at ? date(sync.snapshot.updated_at) : '暂无'}</span><span>版本 {sync.snapshot?.revision}</span></div>
      {o.phase !== 'active' && <section className={styles.result}><h2>{o.phase === 'lost' ? '本局经营已结束' : o.campaign.first_week_result === 'won' ? '首周挑战成功！' : '首周已经结算'}</h2><p>{o.phase === 'week_summary' ? '结果已保存，可在聊天里让点点继续长期经营' : '经营记录会留在这里供你查看'}</p></section>}
      <div className={styles.overview}><section className={styles.panel}><Heading>{o.campaign.next_milestone.title}</Heading><Goals goals={o.campaign.next_milestone.goals}/></section>{o.last_event && <section className={styles.latest}><span>最新动态</span><h2>{o.last_event.title}</h2><p>{o.last_event.text}</p></section>}</div>
      {o.negotiation && <Negotiation value={o.negotiation}/>}
      <div className={styles.workbench}><div className={styles.mainColumn}>
        <div className={styles.tabBar} role="tablist" aria-label="观店分类">{tabs.map(([id, label, Icon]) => <button key={id} id={`tab-${id}`} role="tab" type="button" aria-selected={tab === id} aria-controls={`panel-${id}`} tabIndex={tab === id ? 0 : -1} className={tab === id ? styles.activeTab : styles.tab} onClick={() => setTab(id)} onKeyDown={event => {if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return; event.preventDefault(); const index = tabs.findIndex(entry => entry[0] === tab); const nextIndex = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length; setTab(tabs[nextIndex][0]); document.getElementById(`tab-${tabs[nextIndex][0]}`)?.focus();}}><Icon size={18}/><span>{label}</span></button>)}</div>
        <section className={styles.tabPanel} role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} tabIndex={0}>
          {tab === 'inventory' && <Inventory o={o} onOpen={open}/>}{tab === 'customers' && <Customers o={o}/>}{tab === 'catalog' && <Catalog o={o} onOpen={open}/>}{tab === 'collection' && <Collection o={o} onOpen={open}/>}{tab === 'upgrades' && <Upgrades o={o}/>}{tab === 'logs' && <Logs o={o}/>}{tab === 'dice' && <Dice o={o}/>}
        </section>
      </div><aside className={styles.sidebar}><RollCard roll={o.last_roll} compact/><section className={styles.panel}><h2>今日星港</h2><p className={styles.description}>{o.daily_event.description}</p><p className={styles.chatHint}>在聊天里告诉点点怎么经营，小店会随每次操作更新</p></section></aside></div>
    </>}
    <footer className={styles.footer}><p>{modeLabel} · 只读观店{sync.snapshot?.mode === 'formal' ? '' : ' · 正式游戏稍后开放'}</p><p>{sync.checkedAt ? `最近连通 ${date(sync.checkedAt)}` : '等待首次连接'}{sync.status === 'connected' ? ' · 无新动作时，画面保持不变' : ''}</p></footer>
    {selection && <DetailDialog key={`${selection.type}:${selection.type === 'item' ? selection.id : selection.slot}`} detail={resolveDetail(o, selection)} onClose={close}/>}
  </main></ArtContext.Provider>;
}
