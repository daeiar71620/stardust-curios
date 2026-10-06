/** Full native-v9 public projection. State import/validation is a separate boundary. */
import type {GameState,PublicRecord} from './types.ts';
import {observationBase} from './projection-core.ts';
import {publicNegotiation} from './trade-actions.ts';
const rollFields='id day item_id item_name customer_id customer_name stage die tens ones roll modifier threshold probability base_chance premium rules_version counter_offer success outcome price explanation'.split(' ');
export function publicRoll(row:PublicRecord){return {...Object.fromEntries(rollFields.filter(k=>Object.hasOwn(row,k)).map(k=>[k,row[k]])),modifiers:Array.isArray(row.modifiers)?row.modifiers.map(m=>({label:(m as PublicRecord).label,value:(m as PublicRecord).value})):[]};}
export function observationV9(s:GameState):PublicRecord{const out=observationBase(s);out.negotiation=publicNegotiation(s);if(s.budget_upgrade!==null){const marker=s.budget_upgrade as PublicRecord;out.budget_upgrade=Object.fromEntries(['from_version','source_day','source_phase','source_roll_seq'].map(k=>[k,marker[k]]));}out.roll_history=s.roll_history.map(publicRoll);out.last_roll=s.roll_history.length?publicRoll(s.roll_history[s.roll_history.length-1]):null;if(s.last_event?.roll)out.last_event={...(out.last_event as PublicRecord),roll:publicRoll(s.last_event.roll)};return out;}
