/** Shared pure helpers; private state is copied by the dispatching transition. */
import type {GameState,Item} from './types.ts';
import {publicItem} from './projection-core.ts';
export class CoreGameError extends Error{constructor(message:string){super(message);this.name='CoreGameError';}}
export function event(s:GameState,type:string,title:string,text:string,item:Item|null=null){s.event_seq++;s.last_event={seq:s.event_seq,type,title,text,item:item?publicItem(s,item):null};s.log.push({day:s.day,text});s.log=s.log.slice(-60);}
export function spend(s:GameState,energy=0,credits=0){if(s.energy<energy)throw new CoreGameError(`精力不足：需要 ${energy} 点，还剩 ${s.energy} 点。请先 endday。`);if(s.credits<credits)throw new CoreGameError(`星币不足：需要 ${credits}，还剩 ${s.credits}。`);s.energy-=energy;s.credits-=credits;}
export function requireActive(s:GameState){if(s.phase!=='active')throw new CoreGameError(s.phase==='week_summary'?'首周已结算，请用 continue 明确继续经营。':'本局因维护费不足而结束；可查看收藏，或 restart --confirm 开新局。');}
export function itemById(s:GameState,id:string){const item=s.inventory.find(i=>i.id===id.toUpperCase());if(!item)throw new CoreGameError(`货架上没有物品 ${id}；柜中物品不能直接出售或改价，可用 repair 修理，或用更好同款 replace-collection。`);return item;}
export function requireUnlocked(s:GameState,item:Item){if(s.negotiation&&(s.negotiation as {item_id:string}).item_id===item.id)throw new CoreGameError('这件货正在讨价还价；请先 accept、decline 或 offer，不能换价签、修理或收藏。');}
