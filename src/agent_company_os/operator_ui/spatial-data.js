export const fields = record => Object.fromEntries(record?.fields || []);
export const title = record => {const f=fields(record);return f.objective||f.title||f.name||f['definition.name']||f['source.title']||f['source.name']||f['intent.operation']||record?.subject_type||record?.id||'Record';};
export const recordState = record => {const f=fields(record);return f.status||f['invocation.status']||f['outcome_certainty']||record?.reason||record?.event_kind||'recorded';};
// Presentation classification only. A review label never authorizes an action.
export function reviewState(record,now=Date.now()){
  const f=fields(record);
  if(f.restore_hold==='True')return 'restore hold';
  if(f.cancelled==='True')return 'cancelled';
  if(f.consumed==='True')return 'consumed';
  const decisions=Object.entries(f)
    .filter(([key])=>/^decisions\.\d+\.kind$/.test(key))
    .sort(([a],[b])=>Number(a.split('.')[1])-Number(b.split('.')[1]));
  const decision=decisions.at(-1)?.[1];
  if(decision&&decision!=='approved')return decision;
  const expiry=f['request.expires_at']||f['intent.expires_at'];
  if(expiry&&Date.parse(expiry)<=now)return 'expired';
  return decision||'awaiting review';
}
export class ApiError extends Error {constructor(code,status){super(code);this.code=code;this.status=status;}}
export class InspectionPort {
  constructor(){this.latencies=[];this.cache=new Map();this.controllers=new Set();this.generation=0;}
  assertCurrent(generation,controller=null){
    if(generation!==this.generation||controller?.signal.aborted)throw new DOMException('Inspection session ended','AbortError');
  }
  async request(path,options={}){
    const start=performance.now(),generation=this.generation,controller=new AbortController();
    this.controllers.add(controller);
    try {
      let response;
      try {response=await fetch(path,{credentials:'same-origin',...options,signal:controller.signal});}
      catch(error) {
        this.assertCurrent(generation,controller);
        if(error.name==='AbortError')throw error;
        throw new ApiError('API unavailable. Check the local host.',0);
      }
      this.assertCurrent(generation,controller);
      let data;
      try {data=await response.json();}
      catch(error) {
        this.assertCurrent(generation,controller);
        if(error.name==='AbortError')throw error;
        throw new ApiError('Invalid API response',response.status);
      }
      this.assertCurrent(generation,controller);
      this.latencies.push({path:path.split('?')[0],ms:Math.round(performance.now()-start)});
      if(this.latencies.length>80)this.latencies.shift();
      if(!response.ok)throw new ApiError(data.error?.code||'Request failed',response.status);
      return data;
    } finally {this.controllers.delete(controller);}
  }
  async page(kind,cursor=null){const query=new URLSearchParams({limit:'100'});if(cursor)query.set('cursor',cursor);return this.request('/api/v1/inspect/'+encodeURIComponent(kind)+'?'+query);}
  async collection(kind){const generation=this.generation,page=await this.page(kind);this.assertCurrent(generation);this.cache.set(kind,page);return page;}
  record(kind,id){return this.request('/api/v1/inspect/'+encodeURIComponent(kind)+'?'+new URLSearchParams({id}));}
  lineage(kind,id){return this.request('/api/v1/lineage/'+encodeURIComponent(kind)+'/'+encodeURIComponent(id));}
  audit(id,cursor=null){const p=new URLSearchParams({limit:'100'});if(cursor)p.set('cursor',cursor);return this.request('/api/v1/audit/goals/'+encodeURIComponent(id)+'?'+p);}
  clear(){this.generation++;this.cache.clear();this.latencies.length=0;for(const c of this.controllers)c.abort();this.controllers.clear();}
}
// Polling observes canonical records; it never synthesizes an event or modifies one.
export class ActivityFeedPort {
  constructor(port,{interval=30000}={}){this.port=port;this.interval=interval;this.timer=null;this.busy=false;this.generation=0;}
  start(onUpdate,onError){this.stop();const generation=this.generation;this.timer=setInterval(async()=>{if(document.hidden||this.busy)return;this.busy=true;try{const data=await this.port.request('/api/v1/status');if(generation===this.generation)onUpdate(data);}catch(error){if(generation===this.generation)onError?.(error);}finally{this.busy=false;}},this.interval);}
  stop(){this.generation++;if(this.timer)clearInterval(this.timer);this.timer=null;}
}
