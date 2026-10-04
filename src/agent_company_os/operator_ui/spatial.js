import {
  InspectionPort,ActivityFeedPort,fields,title,recordState,reviewState
} from './spatial-data.js';
import {
  CommandCore
} from './spatial-core.js';
import {
  AudioManager,AGENT_VOICE_PROFILES
} from './audio.js';
const $=id=>document.getElementById(id);
const port=new InspectionPort();
const feed=new ActivityFeedPort(port);
const testMode=new URLSearchParams(location.search).has('test');
const motionQuery=matchMedia('(prefers-reduced-motion: reduce)');
const audio=new AudioManager({
  reducedMotion:motionQuery.matches,enabled:!testMode
});
const ui={
  view:'overview',account:null,generation:0,core:null,mode:null,goal:null,agent:null,focus:null,zoom:1,tilt:5,motion:true,snapshot:{
  }
  ,lastSync:null,voice:audio.getState(),transcript:[],cursor:null,pageHistory:[],next:null,paletteIndex:0,paletteMatches:[],paletteReturn:null,detailReturn:null
};
const views=[['overview','Command','◎'],['organization','Company','⌘'],['agents','Agents','◈'],['goals','Goals','◇'],['conversation','Talk','⌁'],['brain','Brain','▧'],['tools','Tools','↗'],['approvals','Approvals','◉'],['recovery','Recovery','△'],['audit','Audit','≡']];
const categories={
  workspaces:'Workspaces',organization:'Organization',graph_versions:'Organization versions',departments:'Departments',agents:'Agents',agent_versions:'Agent versions',goals:'Goals',tasks:'Tasks',attempts:'Task attempts',executions:'Executions',runs:'Agent runs',orchestrations:'Orchestration',plans:'Plans',materializations:'Materializations',delegations:'Delegations',delegation_attempts:'Delegation attempts',results:'Results',messages:'Agent messages',threads:'Message threads',handoffs:'Handoffs',knowledge:'Knowledge sources',knowledge_versions:'Source versions',memory:'Memory entries',memory_candidates:'Memory candidates',tools:'Tool definitions',tool_versions:'Tool versions',intents:'Action intents',approval_requests:'Approval requests',approval_decisions:'Approval decisions',invocations:'Tool invocations',receipts:'Tool receipts',approvals:'Approvals',recovery:'Recovery cases',audit:'Audit timeline'
};
const lineageKinds=new Set(['goals','tasks','attempts','executions','runs','orchestrations','plans','materializations','delegations','delegation_attempts','results','messages','threads','handoffs','intents','approvals','approval_requests','approval_decisions','invocations','receipts']);
const diagnostics={
  initialLoadMs:0,sceneLoadMs:0,frameDrops:0,speechInitializationMs:0
};
const start=performance.now();
function node(tag,cls,text){
  const n=document.createElement(tag);
  if(cls)n.className=cls;
  if(text!==undefined)n.textContent=String(text);
  return n;
}
function button(text,action,cls=''){
  const n=node('button',cls,text);
  n.type='button';
  n.addEventListener('click',event=>{audio.cue('interaction',{userGesture:true});action(event);});
  return n;
}
function sectionHeading(text,note=''){
  const n=node('div','section-heading');
  n.append(node('h2','',text),node('p','',note));
  return n;
}
function pretty(value){
  return String(value??'Unavailable').replaceAll('_',' ');
}
function stateTag(value){
  const s=String(value).toLowerCase();
  let cls='';
  let glyph='○';
  if(/unknown|uncertain/.test(s)){
    cls='unknown-state';
    glyph='?';
  }
  else if(/fail|error/.test(s)){
    cls='failed-state';
    glyph='×';
  }
  else if(/approv|blocked|waiting|recovery|quarantine/.test(s)){
    cls='warning-state';
    glyph='Ⅱ';
  }
  else if(/completed|success|accepted|delivered/.test(s)){
    cls='success-state';
    glyph='✓';
  }
  else if(/running|working|communicating|thinking/.test(s)){
    cls='active-state';
    glyph='◉';
  }
  return node('span','state-tag '+cls,glyph+' '+pretty(value));
}
function empty(text,explanation='No canonical records are available in this workspace.'){
  const n=node('div','empty-surface');
  n.append(node('h2','',text),node('p','',explanation));
  return n;
}
function describe(text){
  return node('p','view-description',text);
}
function toast(text){
  $('notification').textContent=text;
  $('notification').hidden=false;
  clearTimeout(toast.timer);
  toast.timer=setTimeout(()=>$('notification').hidden=true,5000);
}
function notice(text){
  $('notice').textContent=text;
  $('notice').hidden=!text;
}
async function api(path,options){
  return port.request(path,options);
}
async function canonical(path){
  const epoch=ui.generation;
  const account=ui.account;
  const result=await api(path);
  if(epoch!==ui.generation||account!==ui.account)throw new DOMException('Stale workspace read','AbortError');
  return result;
}
async function load(kinds){
  const epoch=ui.generation;
  const account=ui.account;
  const result={
  };
  for(let i=0;
  i<kinds.length;
  i+=3){
    await Promise.all(kinds.slice(i,i+3).map(async kind=>{
      const page=await port.collection(kind);
      result[kind]=page.items;
      if(page.next_cursor)result[kind+'Truncated']=true;
    }
    ));
  }
  if(epoch!==ui.generation||account!==ui.account)throw new DOMException('Stale workspace read','AbortError');
  return result;
}
function truncation(data,kinds){
  if(kinds.some(k=>data[k+'Truncated']))return node('p','diagnostics','Showing the first 100 records per category. Use All records in the command palette to page through the complete collection.');
  return node('span');
}
function recordRow(record){
  const b=button('',()=>detail(record),'record-row row');
  b.dataset.recordId=record.id||record.subject_id;
  const copy=node('span');
  copy.append(node('strong','',title(record)),node('small','',record.id||record.subject_id||record.event_id));
  b.append(copy,stateTag(recordState(record)),node('span','record-arrow','↗'));
  return b;
}
function metadata(pairs){
  const dl=node('dl','metadata-grid');
  pairs.forEach(([label,value])=>{
    const pair=node('div','metadata-pair');
    pair.append(node('dt','',label),node('dd','',value??'Unavailable from read API'));
    dl.append(pair);
  });
  return dl;
}
function links(record){
  const box=node('div','record-links');
  (record.links||[]).forEach(l=>box.append(button(pretty(l.label)+' ↗',()=>openRecord(l.kind,l.id))));
  return box;
}
function rawFields(record){
  const wrap=node('details','technical-details');
  wrap.append(node('summary','','Technical details'));
  const dl=node('dl');
  (record.fields||Object.entries(record).filter(([key])=>key!=='links')).forEach(([key,value])=>{
    dl.append(node('dt','',pretty(key)),node('dd','',typeof value==='object'?JSON.stringify(value):value));
  });
  wrap.append(dl);
  return wrap;
}
function defaultAgent(){
  return ui.snapshot.agents?.find(a=>a.id===ui.agent)||ui.snapshot.agents?.[0];
}
function versionFor(id){
  return ui.snapshot.agent_versions?.filter(a=>fields(a)['definition.id']===id).sort((a,b)=>Number(fields(b).version)-Number(fields(a).version))[0];
}
function runsFor(id){
  return (ui.snapshot.runs||[]).filter(r=>fields(r)['definition_version.definition.id']===id).sort((a,b)=>String(fields(b).started_at||fields(b).created_at||'').localeCompare(String(fields(a).started_at||fields(a).created_at||'')));
}
function agentNode(agent,onClick=()=>detail(agent)){
  const b=button('',onClick,'agent-node');
  b.dataset.agentId=agent.id;
  const v=fields(versionFor(agent.id));
  const run=runsFor(agent.id)[0];
  const copy=node('span');
  copy.append(node('span','agent-name',title(agent)),node('small','',pretty(v.role||'Unassigned')+' · '+(run?pretty(recordState(run)):'No recorded run')));
  b.append(node('span','agent-glyph',v.role==='product'?'◇':v.role==='marketing'?'⌁':'◈'),copy);
  return b;
}
function setMode(data){
  ui.mode=data;
  $('quarantine').hidden=data.mode!=='restore_quarantine';
  document.body.classList.toggle('restored-mode',data.mode==='restore_quarantine');
  $('connection').textContent=pretty(data.mode)+' · '+data.recovery_count+' recovery cases';
  ui.core?.setState(coreState());
}
function coreState(){
  if(['listening','speaking','processing','requesting_permission'].includes(ui.voice.speechState))return ui.voice.speechState==='processing'?'thinking':ui.voice.speechState==='requesting_permission'?'listening':ui.voice.speechState;
  if(ui.mode?.mode==='restore_quarantine')return 'warning';
  if(ui.mode?.recovery_count>0)return ui.snapshot.recovery?.some(r=>r.outcome==='outcome_unknown')?'outcome-unknown':'warning';
  if(pendingApprovals().length)return 'approval-needed';
  if((ui.snapshot.runs||[]).some(r=>/running/.test(recordState(r))))return 'agent-working';
  return 'idle';
}
function pendingApprovals(){
  return (ui.snapshot.approvals||[]).filter(r=>!!fields(r)['request.intent_id']&&reviewState(r)==='awaiting review');
}
function syncVoice(state){
  ui.voice=state;
  $('sound-toggle').textContent=state.muted?'Sound off':'Sound on';
  $('sound-toggle').setAttribute('aria-pressed',String(!state.muted));
  ui.core?.setState(coreState());
  document.querySelectorAll('.core-caption').forEach(n=>n.textContent=pretty(coreState()));
  document.querySelectorAll('.voice-state').forEach(n=>n.textContent=state.error?pretty(state.error):pretty(state.speechState));
  document.querySelectorAll('.live-transcription').forEach(n=>n.textContent=state.inputTranscript||'');
  document.querySelectorAll('.waveform path').forEach(path=>path.setAttribute('d',state.outputState==='speaking'?'M0 33 C30 33 48 3 70 33 S96 63 118 33 S141 2 161 33 S185 62 207 33 S235 4 258 33 S280 62 305 33 S343 6 364 33 S401 33 420 33':'M0 33 C45 33 48 20 70 33 S95 55 115 33 S143 8 160 33 S185 57 202 33 S224 12 244 33 S275 53 294 33 S320 18 339 33 S383 33 420 33'));
  document.querySelectorAll('[data-listen]').forEach(b=>{
    b.textContent=state.inputState==='listening'?'Stop listening':'Use microphone';
  });
  document.querySelectorAll('[data-stop-speech]').forEach(b=>b.disabled=state.outputState!=='speaking');
  if(state.error)toast(pretty(state.error));
}
audio.subscribe(syncVoice);
function updateMotion(){
  document.body.classList.toggle('no-motion',motionQuery.matches||!ui.motion);
  $('motion-toggle').textContent=motionQuery.matches?'Reduced motion':ui.motion?'Motion on':'Motion off';
  $('motion-toggle').setAttribute('aria-pressed',String(ui.motion&&!motionQuery.matches));
  ui.core?.setReduced(motionQuery.matches||!ui.motion);
}
function showLogin(message=''){
  ui.account=null;
  port.clear();
  ui.snapshot={
  };
  ui.transcript=[];
  ui.agent=null;
  ui.goal=null;
  ui.focus=null;
  ui.mode=null;
  $('detail-dialog').close();
  $('command-palette').close();
  $('detail').replaceChildren();
  $('data').replaceChildren();
  $('command-results').replaceChildren();
  $('workspace-name').textContent='Local workspace';
  ui.generation++;
  ui.core?.dispose();
  ui.core=null;
  feed.stop();
  audio.resetSession();
  $('content').hidden=true;
  $('navigation').hidden=true;
  $('logout').hidden=true;
  $('login').hidden=false;
  $('quarantine').hidden=true;
  $('connection').textContent='Session required';
  $('login-error').textContent=message;
}
async function showSession(person){
  ui.snapshot={
  };
  ui.transcript=[];
  ui.agent=null;
  ui.goal=null;
  ui.focus=null;
  ui.account=person;
  const epoch=++ui.generation;
  const workspacePage=await port.collection('workspaces');
  if(epoch!==ui.generation||person!==ui.account)return;
  ui.snapshot.workspaces=workspacePage.items;
  $('workspace-name').textContent=workspacePage.items[0]?title(workspacePage.items[0]):person.workspace_id;
  $('login').hidden=true;
  $('content').hidden=false;
  $('navigation').hidden=false;
  $('logout').hidden=false;
  await setView('overview');
  feed.start(data=>{
    const changed=ui.mode&&(data.recovery_count!==ui.mode.recovery_count||data.mode!==ui.mode.mode);
    setMode(data);
    if(changed)notice('The workspace attention state changed. Refresh to inspect updated canonical records.');
  }
  ,error=>{
    if(error.status===401)showLogin('Your session expired. Sign in to continue.');
    else if(error.name!=='AbortError')notice(error.message);
  });
}
async function setView(name){
  if(!ui.account)return;
  audio.cancelListening();
  audio.stopSpeaking();
  const epoch=++ui.generation;
  ui.view=name;
  ui.cursor=null;
  ui.next=null;
  ui.pageHistory=[];
  ui.core?.dispose();
  ui.core=null;
  notice('');
  $('detail-dialog').close();
  $('heading').textContent=views.find(v=>v[0]===name)?.[1]||categories[name]||pretty(name);
  $('view-eyebrow').textContent='Company / '+$('heading').textContent;
  document.querySelectorAll('#navigation button').forEach(b=>{
    const active=b.dataset.view===name;
    b.classList.toggle('active',active);
    if(active)b.setAttribute('aria-current','page');
    else b.removeAttribute('aria-current');
  });
  $('data').replaceChildren(node('div','loading','Loading canonical workspace state…'));
  $('data').setAttribute('aria-busy','true');
  $('pager').replaceChildren();
    try{
    setMode(await canonical('/api/v1/status'));
    let output;
    switch(name){
      case 'overview':output=await commandHome();
      break;
      case 'organization':output=await organizationView();
      break;
      case 'agents':output=await agentsView();
      break;
      case 'goals':output=await goalsView(epoch);
      break;
      case 'conversation':output=await conversationView();
      break;
      case 'brain':output=await brainView();
      break;
      case 'tools':output=await toolView();
      break;
      case 'approvals':output=await approvalsView();
      break;
      case 'recovery':output=await recoveryView();
      break;
      case 'audit':output=await auditView();
      break;
      default:output=await collectionView(name);
    }
        if(epoch!==ui.generation)return;
    $('data').replaceChildren(output);
    ui.lastSync=new Date();
    $('data-origin').textContent=(ui.snapshot.workspaces?.some(w=>/synthetic|demo/i.test(title(w)))?'Canonical demo · ':'Canonical · ')+ui.lastSync.toLocaleTimeString([], {
      hour:'2-digit',minute:'2-digit'
    });
    mountScene();
    updateMotion();
    diagnostics.initialLoadMs ||= Math.round(performance.now()-start);

  }
  catch(error){
    if(epoch!==ui.generation||error.name==='AbortError')return;
    if(error.status===401){
      showLogin('Your session expired. Sign in to continue.');
      return;
    }
    const e=empty(error.status===403?'Access restricted':'Workspace unavailable',error.status===403?'Your operator role does not permit this read view. Backend access policy remains authoritative.':error.message);
    e.classList.add('error','error-surface');
    e.setAttribute('role','alert');
    e.append(button('Try again',()=>setView(name)));
    $('data').replaceChildren(e);
  }
    finally{
    if(epoch===ui.generation)$('data').setAttribute('aria-busy','false');
  }
}
async function commandHome(){
  Object.assign(ui.snapshot,await load(['workspaces','agents','agent_versions','runs','goals','tasks','approvals','messages']));
  const data=ui.snapshot;
  if(['admin','auditor'].includes(ui.account.role))data.recovery=(await canonical('/api/v1/recovery?limit=100')).items;
  const ws=data.workspaces[0];
  $('workspace-name').textContent=ws?title(ws):ui.account.workspace_id;
  if(ws&&/synthetic|demo/i.test(title(ws)))notice('Aurora Desk is a synthetic development workspace. These are persisted canonical records, not live production activity.');
  const root=node('div');
  const scene=node('div','command-scene');
  const left=node('div','scene-side');
  left.append(node('h2','','Agent presence'));
  if(data.agents.length)data.agents.slice(0,4).forEach(a=>left.append(agentNode(a)));
  else left.append(empty('No agents','No agent definitions are registered.'));
  const core=node('div','core-region');
  core.setAttribute('aria-label','Company core presentation');
  const canvas=node('canvas');
  canvas.id='company-core';
  canvas.setAttribute('aria-hidden','true');
  const copy=node('div','core-copy');
  copy.append(node('h2','','AGENT COMPANY OS'),node('p','','Human direction. System intelligence.'));
  core.append(canvas,copy,node('div','core-caption',pretty(coreState())));
  const right=node('div','scene-side scene-right');
  const approvals=button('',()=>setView('approvals'),'attention-card');
  approvals.append(node('div','attention-count',pendingApprovals().length),node('strong','','Approval records to inspect'),node('p','','Decisions stay with authorized backend policy.'));
  const recovery=button('',()=>setView('recovery'),'attention-card recovery-card');
  recovery.append(node('div','attention-count',ui.mode.recovery_count),node('strong','','Recovery classifications'),node('p','','Uncertainty deserves attention, not an automatic retry.'));
  right.append(approvals,recovery);
  scene.append(left,core,right);
  const micNotice=node('p','microphone-note','Microphone activates only on request. Browser recognition may send audio to its vendor service.');
  micNotice.id='home-mic-notice';
  const voiceState=node('p','voice-state',pretty(ui.voice.speechState));
  voiceState.setAttribute('role','status');
  const liveInput=node('p','live-transcription',ui.voice.inputTranscript||'');liveInput.setAttribute('role','status');root.append(scene,composer(),micNotice,voiceState,liveInput);
  if(data.goals.length){
    const current=data.goals.find(g=>!/completed|cancelled|failed/.test(recordState(g)))||data.goals[0];
    const strip=node('div','mission-strip');
    const cp=node('div');
    cp.append(node('div','eyebrow','Recorded goal'),node('h3','',title(current)),node('p','','Inspect the task, agent, and tool lineage behind this outcome.'));
    strip.append(node('span','mission-icon','◇'),cp,stateTag(recordState(current)),button('Unfold the goal ↗',()=>selectGoal(current.id)));
    root.append(strip);
  }
  else root.append(empty('No goals','No work is recorded yet. This read-only environment will show goals when the runtime creates them.'));
  const snap=node('div','snapshot');
  ['agents','goals','tasks','runs'].forEach(k=>{
    const n=node('span');
    n.append(node('strong','',data[k].length+(data[k+'Truncated']?'+':'')),document.createTextNode(categories[k].toLowerCase()));
    snap.append(n);
  });
  root.append(snap,sectionHeading('Recorded communication','History, not simulated activity'));
  const msg=node('div','record-list');
  data.messages.slice(0,3).forEach(m=>msg.append(recordRow(m)));
  if(!data.messages.length)msg.append(empty('No messages','No agent-to-agent communication is recorded.'));
  root.append(msg,truncation(data,['agents','goals','tasks','runs','messages']));
  return root;
}
function mountScene(){
  const canvas=$('company-core');
  if(!canvas)return;
  const t=performance.now();
  ui.core=new CommandCore(canvas,{
    reduced:motionQuery.matches||!ui.motion,fixed:testMode,onMetrics:m=>diagnostics.frameDrops=m.drops
  });
  ui.core.setState(coreState());
  diagnostics.sceneLoadMs=Math.round(performance.now()-t);
}
function composer(){
  const form=node('form','command-composer');
  const input=node('input');
  input.placeholder='Ask what is happening, or open a workspace…';
  input.setAttribute('aria-label','Text command');
  input.maxLength=1000;
  const mic=button('Mic',()=>activateMicrophone(text=>routeCommand(text)));
  mic.dataset.listen='true';
  mic.setAttribute('aria-label','Activate microphone for command input');
  mic.setAttribute('aria-describedby','home-mic-notice');
  const submit=node('button','','↗');
  submit.type='submit';
  submit.setAttribute('aria-label','Submit text command');
  form.append(input,mic,submit);
  form.addEventListener('submit',event=>{
    event.preventDefault();
    const text=input.value.trim();
    if(text){
      input.value='';
      routeCommand(text);
    }
  });
  return form;
}
async function organizationView(){
  Object.assign(ui.snapshot,await load(['departments','agents','agent_versions','organization','graph_versions','runs']));
  const root=node('div');
  root.append(describe('A bounded view of the company graph. Department membership comes from the recorded organization version.'));
  const toolbar=node('div','spatial-toolbar');
  const focus=node('span','current-focus','Company / '+(ui.focus||'All departments'));
  toolbar.append(focus,button('Zoom out',()=>changeRig(-.08)),button('Zoom in',()=>changeRig(.08)),button('Tilt',()=>{
    ui.tilt=ui.tilt===5?-5:5;
    applyRig();
  }
  ),button('Reset view',()=>{
    ui.zoom=1;
    ui.tilt=5;
    ui.focus=null;
    applyRig();
    document.querySelectorAll('.department-cluster').forEach(n=>n.classList.remove('dimmed','focused'));
    focus.textContent='Company / All departments';
  }
  ));
  root.append(toolbar);
  if(!ui.snapshot.departments.length){
    root.append(empty('No departments','No active canonical organization graph is published.'));
    return root;
  }
  const scene=node('div','organization-space');
  const rig=node('div','organization-rig');
  rig.id='organization-rig';
  const anchor=node('div','company-anchor');
  anchor.append(node('b','','◎'),node('span','','Company'));
  rig.append(anchor);
  const grid=node('div','department-grid');
  const graph=ui.snapshot.graph_versions.find(r=>fields(r).version===fields(ui.snapshot.organization[0]).active_version)||ui.snapshot.organization[0];
  const gf=fields(graph);
  ui.snapshot.departments.forEach(d=>{
    const cluster=node('section','department-cluster');
    cluster.dataset.departmentId=d.id;
    if(ui.focus){
      cluster.classList.toggle('focused',title(d)===ui.focus);
      cluster.classList.toggle('dimmed',title(d)!==ui.focus);
    }
    const head=node('div','department-heading');
    head.append(button(title(d),()=>{
      ui.focus=title(d);
      focus.textContent='Company / '+title(d);
      grid.querySelectorAll('.department-cluster').forEach(n=>{
        n.classList.toggle('focused',n===cluster);
        n.classList.toggle('dimmed',n!==cluster);
      });
    }
    ),node('span','',pretty(recordState(d))));
    cluster.append(head);
    const members=[];
    for(let i=0;
    i<Number(gf.membership_count||0);
    i++)if(gf[`membership.${i}.department_id`]===d.id&&gf[`membership.${i}.status`]==='active'&&(!gf[`membership.${i}.effective_from`]||Date.parse(gf[`membership.${i}.effective_from`])<=Date.now())&&(!gf[`membership.${i}.effective_until`]||Date.now()<Date.parse(gf[`membership.${i}.effective_until`])))members.push(gf[`membership.${i}.agent_definition_id`]);
    const agents=ui.snapshot.agents.filter(a=>members.includes(a.id));
    agents.forEach(a=>cluster.append(agentNode(a)));
    if(!agents.length)cluster.append(node('p','evidence-line',gf.membership_count===undefined?'Membership metadata unavailable in this read projection.':'No active member agents.'));
    grid.append(cluster);
  });
  rig.append(grid);
  scene.append(rig);
  root.append(scene,sectionHeading('Organization records','Versions remain inspectable'));
  ui.snapshot.graph_versions.forEach(r=>root.append(recordRow(r)));
  return root;
}
function changeRig(delta){
  ui.zoom=Math.min(1.15,Math.max(.75,ui.zoom+delta));
  applyRig();
}
function applyRig(){
  const rig=$('organization-rig');
  if(rig){
    rig.style.setProperty('--zoom',ui.zoom);
    rig.style.setProperty('--tilt',ui.tilt+'deg');
  }
}
async function agentsView(){
  Object.assign(ui.snapshot,await load(['agents','agent_versions','runs','tasks']));
  const root=node('div');
  root.append(describe('Stable agent identities, their configured boundaries, and the latest recorded runs. An agent definition is separate from an execution.'));
  if(!ui.snapshot.agents.length){
    root.append(empty('No agents','There are no registered agent definitions.'));
    return root;
  }
  const grid=node('div','agents-grid');
  ui.snapshot.agents.forEach(a=>{
    const f=fields(versionFor(a.id));
    const run=runsFor(a.id)[0];
    const c=node('article','agent-card');
    c.append(agentNode(a),node('p','',run?(ui.snapshot.runsTruncated?'Latest loaded run: ':'Latest recorded run: ')+pretty(recordState(run))+'. '+(fields(run).task_id||'No task reference.'):'No recorded runs for this agent.'));
    c.append(metadata([['Role',f.role],['Autonomy ceiling',f.autonomy_ceiling],['Configuration version',f.version]]));
    const actions=node('div','agent-card-actions');
    actions.append(button('Inspect identity',()=>detail(a)),button('Talk to agent',()=>talkTo(a.id)));
    c.append(actions);
    grid.append(c);
  });
  root.append(grid,truncation(ui.snapshot,['agents','runs','tasks']));
  return root;
}
async function goalsView(epoch){
  const data=await load(['goals']);
  ui.snapshot.goals=data.goals;
  const root=node('div');
  root.append(describe('Follow the recorded goal through planning, tasks, agent execution, action intents, and tool receipts.'));
  if(!data.goals.length){
    root.append(empty('No goals','No goals have been created in the canonical workspace.'));
    return root;
  }
  const layout=node('div','goal-layout');
  const picker=node('div','goal-picker');
  const selected=data.goals.find(g=>g.id===ui.goal)||data.goals.find(g=>/cross-department/i.test(title(g)))||data.goals[0];
  ui.goal=selected.id;
  data.goals.forEach(g=>{
    const b=button('',()=>selectGoal(g.id));
    b.classList.toggle('selected',g.id===selected.id);
    b.append(node('strong','',title(g)),stateTag(recordState(g)));
    picker.append(b);
  });
  const space=node('div','goal-workspace');
  space.id='goal-workspace';
  const lineage=await port.lineage('goals',selected.id);
  if(epoch!==ui.generation)return root;
  buildGoal(space,lineage);
  layout.append(picker,space);
  root.append(layout);
  return root;
}
async function selectGoal(id){
  ui.goal=id;
  await setView('goals');
}
function buildGoal(space,lineage){
  const sections=lineage.sections;
  const all=sections.flatMap(s=>s.records);
  const root=lineage.root;
  const summary=node('div','goal-summary');
  summary.append(node('div','eyebrow','Goal / '+root.id),node('h2','',title(root)),node('p','','State: '+pretty(recordState(root))+'. All layers below refer to persisted canonical records.'));
  const tasks=all.filter(r=>r.kind==='tasks');
  const completed=tasks.filter(r=>recordState(r)==='completed').length;
  summary.append(node('p','',completed+' of '+tasks.length+' related tasks completed.'),button('Inspect goal',()=>detail(root)),button('View audit',()=>{
    ui.goal=root.id;
    setView('audit');
  }
  ));
  space.append(summary,sectionHeading('Task relationships','Recorded dependencies'));
  const graph=node('div','task-graph');
  tasks.forEach(t=>{
    const b=button('',()=>detail(t),'task-node');
    b.append(node('strong','',title(t)),stateTag(recordState(t)));
    const f=fields(t);
    const deps=Object.entries(f).filter(([k])=>/^dependency\.\d+\.task_id$/.test(k)).map(([,v])=>tasks.find(task=>task.id===v)?title(tasks.find(task=>task.id===v)):v);
    b.append(node('span','dependency-label',deps.length?'Depends on: '+deps.join(' + '):f.dependency_count!==undefined?'No dependencies in the materialized plan.':'Dependency metadata unavailable.'));
    graph.append(b);
  });
  if(!tasks.length)graph.append(empty('No related tasks','No materialized tasks are linked to this goal.'));
  space.append(graph);
  const heading=node('div','stack-header');
  heading.append(node('h3','','Execution depth'),node('span','','Scroll within the stack to follow lineage ↓'));
  space.append(heading);
  const layers=[root];
  const order=['plans','tasks','runs','intents','invocations','receipts'];
  order.forEach(kind=>all.filter(r=>r.kind===kind).forEach(r=>{
    if(!layers.some(l=>l.kind===r.kind&&l.id===r.id))layers.push(r);
  }
  ));
  const stack=node('div','stack-scroll');
  stack.id='execution-stack';
  stack.tabIndex=0;
  stack.setAttribute('aria-label','Scrollable canonical execution stack');
  const breadcrumb=node('div','stack-breadcrumb','Goal / Related Plan → Task → Run → Tool records');
  stack.append(breadcrumb);
  const list=node('div','stack-layers');
  layers.forEach((r,i)=>{
    const b=button('',()=>detail(r),'stack-layer');
    b.dataset.kind=r.kind;
    b.dataset.recordId=r.id;
    b.style.setProperty('--layer-offset',Math.min(i,4)*7+'px');
    b.append(node('small','',(categories[r.kind]||r.kind)+' / '+String(i+1).padStart(2,'0')),node('strong','',title(r)),stateTag(recordState(r)));
    if(fields(r).outcome_certainty)b.append(stateTag(fields(r).outcome_certainty));
    list.append(b);
  });
  stack.append(list);
  const navigation=node('div','stack-nav');
  navigation.append(button('Previous layer',()=>stack.scrollBy({
    top:-200,behavior:motionQuery.matches||!ui.motion?'instant':'smooth'
  }
  )),button('Go deeper',()=>stack.scrollBy({
    top:200,behavior:motionQuery.matches||!ui.motion?'instant':'smooth'
  }
  )),button('Reset stack',()=>stack.scrollTo({
    top:0,behavior:'instant'
  }
  )));
  space.append(stack,navigation);
  stack.addEventListener('scroll',()=>{
    if(motionQuery.matches||!ui.motion||testMode)return;
    const sr=stack.getBoundingClientRect();
    list.querySelectorAll('.stack-layer').forEach(layer=>{
      const offset=(layer.getBoundingClientRect().top-sr.top)/stack.clientHeight;
      layer.style.opacity=String(Math.max(.55,1-Math.abs(offset-.4)*.3));
      layer.style.setProperty('--layer-depth',Math.round(12-Math.min(1,Math.abs(offset-.4))*70)+'px');
    });
  }
  ,{
    passive:true
  });
  const missing=order.filter(k=>!all.some(r=>r.kind===k));
  if(missing.length)space.append(node('p','diagnostics','No linked records for: '+missing.map(k=>categories[k]).join(', ')+'. Absent layers are not simulated.'));
  if(sections.some(s=>s.truncated))space.append(node('p','diagnostics','Lineage sections are bounded at 100 records. Open All records to inspect remaining pages.'));
}
async function talkTo(id){
  ui.agent=id;
  ui.transcript=[];
  await setView('conversation');
}
async function conversationView(){
  Object.assign(ui.snapshot,await load(['agents','agent_versions','runs','tasks']));
  const root=node('div');
  root.append(describe('Talk through the recorded workspace. Text and voice navigate read contexts and read back metadata; this stage has no live model conversation endpoint.'));
  if(!ui.snapshot.agents.length){
    root.append(empty('No agents to talk to','Register an agent through the governed runtime before inspecting its conversation context.'));
    return root;
  }
  const a=defaultAgent();
  ui.agent=a.id;
  const layout=node('div','conversation-layout');
  const picker=node('div','record-list');
  ui.snapshot.agents.forEach(agent=>picker.append(agentNode(agent,()=>talkTo(agent.id))));
  const stage=node('div','conversation-stage');
  stage.append(node('div','voice-identity','◈'),node('h2','',title(a)),node('p','voice-state',pretty(ui.voice.speechState)),waveform());
  const transcript=node('div','transcript');
  transcript.id='transcript';
  transcript.setAttribute('role','log');
  transcript.setAttribute('aria-label','Visible conversation transcript');
  if(!ui.transcript.length)ui.transcript.push({
    speaker:title(a),text:agentSummary(a.id)
  });
  ui.transcript.forEach(e=>appendTranscript(transcript,e));
  stage.querySelector('.voice-state').setAttribute('role','status');const liveInput=node('p','live-transcription',ui.voice.inputTranscript||'');liveInput.setAttribute('role','status');stage.append(liveInput);
  stage.append(transcript);
  const form=node('form','command-composer');
  const input=node('input');
  input.setAttribute('aria-label','Message to selected agent');
  input.placeholder='What are you working on?';
  input.maxLength=1000;
  const send=node('button','','Send');
  send.type='submit';
  form.append(input,send);
  form.addEventListener('submit',event=>{
    event.preventDefault();
    const text=input.value.trim();
    if(text){
      input.value='';
      conversationCommand(text);
    }
  });
  stage.append(form);
  const controls=node('div','speech-controls');
  const listen=button('Use microphone',()=>activateMicrophone(text=>conversationCommand(text)));
  listen.dataset.listen='true';
  const read=button('Read response',()=>readLatest());
  const stop=button('Stop speaking',()=>audio.stopSpeaking());
  stop.dataset.stopSpeech='true';
  stop.disabled=ui.voice.outputState!=='speaking';
  const interrupt=button('Interrupt',()=>{
    audio.interrupt();
    toast('Voice playback and listening interrupted. Runtime state is unchanged.');
  });
  controls.append(listen,read,stop,interrupt,button('Return to command',()=>setView('overview')));
  stage.append(controls,node('p','microphone-note','Microphone starts only when you press “Use microphone”. Browser speech recognition may send audio to its vendor service. The waveform indicates speech state; it is not measured microphone amplitude.'),voiceSettings(a));
  layout.append(picker,stage);
  root.append(layout);
  return root;
}
function waveform(){
  const ns='http://www.w3.org/2000/svg';
  const svg=document.createElementNS(ns,'svg');
  svg.classList.add('waveform');
  svg.setAttribute('viewBox','0 0 420 65');
  svg.setAttribute('aria-hidden','true');
  const path=document.createElementNS(ns,'path');
  path.setAttribute('d','M0 33 C45 33 48 20 70 33 S95 55 115 33 S143 8 160 33 S185 57 202 33 S224 12 244 33 S275 53 294 33 S320 18 339 33 S383 33 420 33');
  svg.append(path);
  return svg;
}
function agentSummary(id){
  const a=ui.snapshot.agents.find(r=>r.id===id);
  const f=fields(versionFor(id));
  const run=runsFor(id)[0];
  if(!run)return (a?title(a):'This agent')+' has no recorded run. Configured role: '+pretty(f.role)+'. Autonomy ceiling: '+pretty(f.autonomy_ceiling)+'.';
  const rf=fields(run);
  const task=ui.snapshot.tasks?.find(t=>t.id===rf.task_id);
  return (ui.snapshot.runsTruncated?'The latest loaded run is ':'The latest recorded run is ')+pretty(recordState(run))+'. '+(task?'Task: '+title(task)+'. ':'')+'Run '+run.id+'. '+(rf.tool_call_count||0)+' tool calls recorded. '+(rf.evidence_pack_count||0)+' evidence packs. This is recorded metadata, not a live agent response.';
}
function appendTranscript(target,entry){
  const p=node('div','transcript-entry '+(entry.speaker==='You'?'operator':''));
  p.append(node('strong','',entry.speaker),node('p','',entry.text));
  target.append(p);
}
function conversationCommand(text){
  audio.stopSpeaking();
  const entry={
    speaker:'You',text
  };
  ui.transcript.push(entry);
  if($('transcript'))appendTranscript($('transcript'),entry);
  const lower=text.toLowerCase();
  let reply;
  if(/working|status|what happened|morning/.test(lower))reply=agentSummary(ui.agent);
  else if(/source|know|evidence|information/.test(lower)){
    reply='Knowledge lineage is available in Company Brain. Source content remains protected by the read API.';
  }
  else if(/why|wait|block/.test(lower)){
    const run=runsFor(ui.agent)[0];
    reply=run?'The latest recorded run state is '+pretty(recordState(run))+'. Open its canonical record to inspect deadlines, pending invocations, and correlated action intents.':'No run is recorded for this identity.';
  }
  else reply='I can show recorded work, sources, approvals, and recovery. There is no live model chat connection in this stage; this input cannot change runtime permissions.';
  const response={
    speaker:title(defaultAgent()),text:reply
  };
  ui.transcript.push(response);
  if($('transcript')){
    appendTranscript($('transcript'),response);
    $('transcript').scrollTop=$('transcript').scrollHeight;
  }
  if(/source|evidence|information/.test(lower))toast('Company Brain is available in the dock.');
}
function voiceSettings(agent){
  const settings=node('details','voice-settings');
  settings.append(node('summary','','Voice and volume'));
  const grid=node('div','voice-settings-grid');
  const voiceLabel=node('label','','Generic browser voice');
  const select=node('select');
  select.id='voice-select';
  select.append(node('option','','Browser default'));
  if('speechSynthesis'in window)speechSynthesis.getVoices().forEach(v=>{
    const o=node('option','',v.name+' · '+v.lang);
    o.value=v.voiceURI;
    select.append(o);
  });
  voiceLabel.append(select);
  const volumeLabel=node('label','','Playback volume');
  const volume=node('input');
  volume.type='range';
  volume.min='0';
  volume.max='1';
  volume.step='.05';
  volume.value=String(ui.voice.volume);
  volume.setAttribute('aria-label','Playback volume');
  volume.addEventListener('input',()=>audio.setVolume(Number(volume.value)));
  volumeLabel.append(volume);
  grid.append(voiceLabel,volumeLabel);
  settings.append(grid,node('p','microphone-note','Voice settings change presentation only. They never change the agent’s authority.'));
  return settings;
}
async function readLatest(){
  const response=[...ui.transcript].reverse().find(e=>e.speaker!=='You');
  if(!response)return;
  if(ui.voice.muted){
    toast('Sound is off. Turn it on to read the visible response aloud.');
    return;
  }
  const configuredRole=fields(versionFor(ui.agent)).role;
  const role=configuredRole==='product'?'analytical':configuredRole==='marketing'?'writer':configuredRole;
  const profiles=AGENT_VOICE_PROFILES;
  const profile={
    ...(profiles[role]||profiles.research||{
    }
    ),voice_id:$('voice-select')?.value||''
  };
  const started=performance.now();
  await audio.speak(response.text,{
    agentId:ui.agent,profile
  });
  diagnostics.speechInitializationMs=Math.round(performance.now()-started);
}
function activateMicrophone(onFinal){
  if(ui.voice.inputState==='listening'||ui.voice.inputState==='requesting_permission'){
    audio.cancelListening();
    return;
  }
  audio.startListening({
    userGesture:true,onTranscript:({
      text,final
    }
    )=>{
      if(final&&text.trim())onFinal(text.trim());
    }
  });
}
async function brainView(){
  const data=await load(['knowledge','knowledge_versions','memory','runs']);
  Object.assign(ui.snapshot,data);
  const root=node('div');
  root.append(describe('Knowledge is source-bound. Memory is reviewed and scoped. They have different authority, provenance, and lifecycles.'));
  const layout=node('div','brain-layout');
  const lattice=node('section','brain-lattice');
  const anchor=node('div','brain-anchor');
  anchor.append(node('span','','▧'),node('h2','','Company Brain'),node('p','','Sources → versions → chunks → recorded evidence'));
  lattice.append(anchor);
  const sourceGrid=node('div','source-grid');
  data.knowledge.forEach(s=>{
    const f=fields(s);
    const b=button('',()=>detail(s),'source-node');
    b.append(node('strong','',title(s)),node('small','',pretty(f.source_type)+' / '+pretty(f.trust)),stateTag(recordState(s)));
    sourceGrid.append(b);
  });
  if(!data.knowledge.length)sourceGrid.append(empty('No knowledge sources','No source records are published.'));
  lattice.append(sourceGrid,sectionHeading('Source versions','Content stays redacted'));
  data.knowledge_versions.forEach(v=>lattice.append(recordRow(v)));
  let packCount=0;
  data.runs.forEach(run=>{
    const f=fields(run);
    const count=Number(f.evidence_pack_count||0);
    packCount+=count;
    for(let i=0;
    i<count;
    i++){
      const evidence=node('div','evidence-line');
      evidence.append(node('strong','','Evidence pack '+f[`evidence.${i}.pack_id`]),node('p','',title(run)+' · '+(f[`evidence.${i}.returned_count`]||0)+' recorded hits'));
      const sourceIds=Object.entries(f).filter(([k])=>k.startsWith(`evidence.${i}.source.`)&&k.endsWith('.source_id'));
      sourceIds.forEach(([,id])=>{
        const source=data.knowledge.find(s=>s.id===id);
        evidence.append(button(source?title(source):id,()=>openRecord('knowledge',id)));
      });
      lattice.append(evidence);
    }
  });
  if(!packCount)lattice.append(node('p','evidence-line','No evidence packs are recorded in the loaded runs. Source availability does not imply a retrieval occurred.'));
  const memory=node('section','memory-trail');
  memory.append(node('h2','','Memory trail'),node('p','','Temporal, reviewed context with explicit scope and provenance.'));
  data.memory.forEach(m=>{
    const f=fields(m);
    const b=button('',()=>detail(m),'memory-capsule');
    b.append(node('span','',pretty(f.memory_type)+' · '+pretty(recordState(m))),node('small','',pretty(f['scope.kind'])+' / '+pretty(f['candidate.provenance.authority'])),node('small','','Expiry: '+(f.expires_at||'Not exposed')));
    memory.append(b);
  });
  if(!data.memory.length)memory.append(empty('No memory entries','No reviewed memory is present.'));
  layout.append(lattice,memory);
  root.append(layout,truncation(data,['knowledge','knowledge_versions','memory','runs']));
  return root;
}
async function toolView(){
  const data=await load(['invocations','receipts','tools','messages','handoffs']);
  const root=node('div');
  root.append(describe('Inspect exact tool versions, request fingerprints, and observed receipts. A missing receipt is an unknown outcome, not proof of failure.'));
  root.append(sectionHeading('Tool invocations',data.invocations.length+' loaded records'));
  const list=node('div','record-list');
  data.invocations.forEach(inv=>{
    const f=fields(inv);
    const row=recordRow(inv);
    const tool=data.tools.find(t=>t.id===f['tool_version.definition.id']);
    const receipt=data.receipts.find(r=>fields(r)['invocation.id']===inv.id);
    row.querySelector('strong').textContent=tool?title(tool):inv.id;
    row.querySelector('small').textContent=inv.id+' → '+(receipt?'Receipt '+receipt.id:f.receipt_id?'Receipt '+f.receipt_id+' (not loaded)':'No observed receipt');
    row.append(stateTag(f.outcome_certainty||'outcome_unknown'));
    list.append(row);
  });
  if(!data.invocations.length)list.append(empty('No tool invocations','No tool calls are recorded.'));
  root.append(list,sectionHeading('Agent communication','Correlated messages and handoffs'));
  [...data.messages,...data.handoffs].forEach(m=>{
    const f=fields(m);
    const card=node('div','recovery-item');
    card.append(node('h3','',pretty(f.kind||m.kind)),metadata([['Sender',f.sender_definition_id||f.sender_agent_run_id],['Recipient',f.recipient_definition_id||f.recipient_agent_run_id],['Correlation',f.correlation_id],['Task',f.sender_task_id||f.source_task_id],['State',recordState(m)]]),links(m),button('Inspect communication',()=>detail(m)));
    root.append(card);
  });
  root.append(truncation(data,['invocations','receipts','messages','handoffs']));
  return root;
}
async function approvalsView(){
  const data=await load(['approvals','tools','runs','agents']);
  Object.assign(ui.snapshot,data);
  const root=node('div');
  root.append(describe('Deliberate review of action intent, policy, and evidence. This Stage 11 surface has no approval or denial authority.'));
  if(!data.approvals.length){
    root.append(empty('No approval records','No governed action intents are recorded.'));
    return root;
  }
  data.approvals.forEach(record=>{
    const f=fields(record);
    const panel=node('article','approval-panel');
    const run=data.runs.find(r=>r.id===f['intent.run_id']);
    const agent=data.agents.find(a=>a.id===fields(run)['definition_version.definition.id']);
    const tool=data.tools.find(t=>t.id===f['intent.tool.definition.id']);
    const decisions=Object.entries(f).filter(([key])=>/^decisions\.\d+\.kind$/.test(key)).map(([,value])=>value);
    const review=reviewState(record);
    panel.append(stateTag(review),node('h2','',f['intent.operation']||'Governed action'),metadata([['Agent',agent?title(agent):f['intent.run_id']],['Tool',tool?title(tool):f['intent.tool.definition.id']],['Risk',f['intent.tool.definition.risk']],['Policy effect',f['intent.effect']],['Destination','Redacted by read contract'],['Payload digest',f['intent.fingerprint']],['Policy version',f['intent.policy.version']],['Expiry',f['intent.expires_at']],['Review status',pretty(review)],['Restore hold',f.restore_hold]]));
    const actions=node('div','approval-actions');
    const approve=button('Approve',()=>{
    });
    approve.disabled=true;
    const deny=button('Deny',()=>{
    });
    deny.disabled=true;
    actions.append(approve,deny,node('span','','Read-only review. Backend authorization is required.'));
    panel.append(actions,links(record),rawFields(record));
    root.append(panel);
  });
  return root;
}
async function recoveryView(){
  const data=await canonical('/api/v1/recovery?limit=100');
  ui.snapshot.recovery=data.items;
  const root=node('div');
  const summary=node('div','recovery-summary');
  summary.append(node('div','uncertain-mark','?'),node('div'));
  summary.lastChild.append(node('h2','','Uncertain is a distinct state.'),node('p','','An external action may have occurred. Inspection cannot make an automatic retry safe. Follow the original intent, claim, and receipt.'));
  root.append(summary);
  if(!data.items.length)root.append(empty('No recovery cases','No recovery classifications are currently present.'));
  data.items.forEach(r=>{
    const item=node('article','recovery-item');
    item.dataset.recordId=r.subject_id;
    item.append(stateTag(r.outcome||r.reason),node('h3','',pretty(r.reason)),node('p','',r.explanation||'Inspect the linked canonical record.'),node('small','',pretty(r.subject_type)+' / '+r.subject_id),links(r),button('Inspect classification',()=>detail(r)));
    root.append(item);
  });
  if(ui.mode.mode==='restore_quarantine'){
    const restored=await canonical('/api/v1/restore');
    const box=node('div','restore-info');
    box.append(node('h3','','Restore context'));
    if(restored.context){
      box.append(metadata(Object.entries(restored.context).map(([k,v])=>[pretty(k),typeof v==='object'?JSON.stringify(v):v])));
    }
    else box.append(node('p','','Restore provenance unavailable. Review remains required.'));
    box.append(node('p','diagnostics','Quarantine release and execution controls are not exposed in this spatial surface.'));
    root.append(box);
  }
  if(data.next_cursor)root.append(button('More recovery records',()=>loadMoreRecovery(root,data.next_cursor)));
  return root;
}
async function loadMoreRecovery(root,cursor){
  try{
    const page=await api('/api/v1/recovery?'+new URLSearchParams({
      limit:'100',cursor
    }
    ));
    page.items.forEach(r=>root.append(recordRow(r)));
    if(page.next_cursor)root.append(button('More recovery records',()=>loadMoreRecovery(root,page.next_cursor)));
  }
  catch(error){
    toast(error.message);
  }
}
async function auditView(){
  const data=await load(['goals']);
  const root=node('div');
  root.append(describe('A timeline of committed state changes and safe event metadata. Prompts, protected message bodies, and hidden reasoning remain excluded.'));
  if(!data.goals.length){
    root.append(empty('No goal audit','Select a canonical goal after one has been created.'));
    return root;
  }
  const goal=data.goals.find(g=>g.id===ui.goal)||data.goals[0];
  ui.goal=goal.id;
  const selectWrap=node('div','view-select');
  const label=node('label','','Goal');
  const select=node('select');
  data.goals.forEach(g=>{
    const option=node('option','',title(g));
    option.value=g.id;
    option.selected=g.id===goal.id;
    select.append(option);
  });
  select.addEventListener('change',()=>{
    ui.goal=select.value;
    setView('audit');
  });
  label.append(select);
  selectWrap.append(label);
  root.append(selectWrap);
  const timeline=node('div','activity-timeline');
  const page=await port.audit(goal.id);
  renderEvents(timeline,page.items);
  if(!page.items.length)timeline.append(empty('No audit events','No committed events were returned for this goal.'));
  root.append(timeline);
  if(page.next_cursor)root.append(button('Load older events',()=>moreEvents(timeline,page.next_cursor)));
  return root;
}
function renderEvents(target,events){
  events.forEach(event=>{
    const item=node('article','event-item');
    item.append(node('strong','',pretty(event.event_kind)),node('time','',event.timestamp),node('p','',pretty(event.subject_type)+' / '+event.subject_id));
    const m=node('p');
    m.textContent=(event.metadata||[]).map(([k,v])=>pretty(k)+': '+v).join(' · ');
    item.append(m,button('Inspect event',()=>detail(event)));
    target.append(item);
  });
}
async function moreEvents(target,cursor){
  try{
    const page=await port.audit(ui.goal,cursor);
    renderEvents(target,page.items);
    if(page.next_cursor)target.append(button('Load older events',()=>moreEvents(target,page.next_cursor)));
  }
  catch(error){
    toast(error.message);
  }
}
async function collectionView(kind){
  const page=await port.page(kind,ui.cursor);
  ui.next=page.next_cursor;
  const root=node('div','record-list');
  root.append(describe('Workspace-scoped canonical metadata. Protected content is redacted by the backend.'));
  page.items.forEach(record=>root.append(recordRow(record)));
  if(!page.items.length)root.append(empty('No '+(categories[kind]||kind).toLowerCase()));
  const next=button('Next page',()=>pageCollection(kind,ui.next));
  next.disabled=!ui.next;
  const back=button('Previous page',()=>{
    ui.cursor=ui.pageHistory.pop()??null;
    refreshCollection(kind);
  });
  back.disabled=!ui.pageHistory.length;
  $('pager').replaceChildren(back,node('span','','Page '+(ui.pageHistory.length+1)),next);
  return root;
}
async function pageCollection(kind,cursor){
  ui.pageHistory.push(ui.cursor);
  ui.cursor=cursor;
  await refreshCollection(kind);
}
async function refreshCollection(kind){
  const epoch=ui.generation;
  const account=ui.account;
  try{
    $('data').setAttribute('aria-busy','true');
    const output=await collectionView(kind);
    if(epoch===ui.generation&&account===ui.account)$('data').replaceChildren(output);
  }
  catch(error){
    if(epoch===ui.generation&&account===ui.account&&error.name!=='AbortError')toast(error.message);
  }
  finally{
    if(epoch===ui.generation&&account===ui.account)$('data').setAttribute('aria-busy','false');
  }
}
async function openRecord(kind,id){
  const originAccount=ui.account;
  if(kind==='goals'){
    await selectGoal(id);
  }
  if(originAccount!==ui.account||!ui.account)return;
  const epoch=ui.generation;
  const account=ui.account;
  const page=await port.record(kind,id);
  if(epoch===ui.generation&&account===ui.account&&page.items[0])detail(page.items[0]);
}
function detail(record){
  if(!record||!ui.account)return;
  const epoch=ui.generation;
  const account=ui.account;
  ui.detailReturn=document.activeElement;
  const content=$('detail');
  content.replaceChildren();
  content.append(node('h2','',title(record)));
  content.firstChild.id='detail-heading';
  content.append(stateTag(recordState(record)));
  const f=fields(record);
  if(record.kind==='agents'){
    content.append(node('p','view-description',agentSummary(record.id)),button('Talk to this agent',()=>{
      $('detail-dialog').close();
      talkTo(record.id);
    }
    ));
    const v=versionFor(record.id);
    if(v)content.append(button('Inspect exact configuration',()=>detail(v)));
    runsFor(record.id).slice(0,5).forEach(r=>content.append(recordRow(r)));
  }
  const dl=node('dl');
  const pairs=record.fields||Object.entries(record).filter(([key])=>!['fields','links'].includes(key));
  pairs.forEach(([key,value])=>{
    dl.append(node('dt','',pretty(key)),node('dd','',typeof value==='object'?JSON.stringify(value):value));
  });
  content.append(dl,links(record));
  if(lineageKinds.has(record.kind)){
    const inspect=button('Inspect related lineage',async()=>{
      inspect.disabled=true;
      try{
        const lineage=await port.lineage(record.kind,record.id);
        if(epoch!==ui.generation||account!==ui.account||!$('detail-dialog').open)return;
        const tree=node('div','lineage');
        lineage.sections.forEach(section=>{
          const s=node('div','lineage-section');
          s.append(node('h3','',categories[section.kind]||section.kind));
          section.records.forEach(r=>s.append(recordRow(r)));
          if(section.truncated)s.append(node('p','diagnostics','First 100 records. Open All records to page through the rest.'));
          tree.append(s);
        });
        if(!lineage.sections.length)tree.append(empty('No linked records'));
        content.append(tree);
      }
      catch(error){
        if(epoch===ui.generation&&account===ui.account&&error.name!=='AbortError')content.append(node('p','error',error.message));
      }
      finally{
        inspect.disabled=false;
      }
    });
    content.append(inspect);
  }
  if(record.kind==='goals')content.append(button('View timeline',()=>{
    $('detail-dialog').close();
    ui.goal=record.id;
    setView('audit');
  }
  ));
  if(!$('detail-dialog').open)$('detail-dialog').showModal();
  $('detail-close').focus();
}
function routeCommand(text){
  const value=text.toLowerCase();
  if(/team|department/.test(value)&&/research|product|marketing/.test(value)){
    ui.focus=value.includes('research')?'Research':value.includes('product')?'Product':'Marketing';
    setView('organization');
    return;
  }
  if(/ignore|permission|admin|approve|deny|execute|send email|retry|delete/.test(value)){
    toast('This command surface navigates and inspects. It does not grant permissions or execute actions.');
    return;
  }
  if(/recovery|uncertain|unknown/.test(value)){
    setView('recovery');
    return;
  }
  if(/attention|approval/.test(value)){
    setView('approvals');
    return;
  }
  if(/brain|source|know|evidence|customer/.test(value)){
    setView('brain');
    return;
  }
  if(/goal|task|working|work on/.test(value)){
    setView('goals');
    return;
  }
  if(/tool|receipt|action/.test(value)){
    setView('tools');
    return;
  }
  if(/audit|happened|history/.test(value)){
    setView('audit');
    return;
  }
  const matched=ui.snapshot.agents?.find(a=>value.includes(title(a).toLowerCase())||value.includes(fields(versionFor(a.id)).role||'__missing'));
  if(/talk|speak/.test(value)&&matched){
    talkTo(matched.id);
    return;
  }
  if(/research|product|marketing|organization|company graph/.test(value)){
    ui.focus=value.includes('research')?'Research':value.includes('product')?'Product':value.includes('marketing')?'Marketing':null;
    setView('organization');
    return;
  }
  if(/agent/.test(value)){
    setView('agents');
    return;
  }
  if(/company|morning|happening|command|home/.test(value)){
    setView('overview');
    return;
  }
  openPalette(text);
}
function paletteEntries(){
  const items=views.map(([key,label,glyph])=>({
    label:label,meta:'Workspace view',glyph,action:()=>setView(key)
  }
  ));
  (ui.snapshot.agents||[]).forEach(a=>items.push({
    label:'Talk to '+title(a),meta:'Agent conversation',glyph:'◈',action:()=>talkTo(a.id)
  }
  ));
  (ui.snapshot.goals||[]).forEach(g=>items.push({
    label:title(g),meta:'Goal',glyph:'◇',action:()=>selectGoal(g.id)
  }
  ));
  Object.entries(categories).filter(([k])=>!views.some(v=>v[0]===k)).forEach(([kind,label])=>items.push({
    label:'All records / '+label,meta:'Canonical collection',glyph:'▧',action:()=>setView(kind)
  }
  ));
  return items;
}
function openPalette(query=''){
  if(!ui.account)return;
  ui.paletteReturn=document.activeElement;
  $('command-search').value=query;
  ui.paletteIndex=0;
  renderPalette();
  $('command-palette').showModal();
  $('command-search').focus();
}
function renderPalette(){
  const query=$('command-search').value.toLowerCase().trim();
  ui.paletteMatches=paletteEntries().filter(i=>(i.label+' '+i.meta).toLowerCase().includes(query)).slice(0,12);
  ui.paletteIndex=Math.max(0,Math.min(ui.paletteIndex,ui.paletteMatches.length-1));
  const target=$('command-results');
  target.replaceChildren();
  ui.paletteMatches.forEach((item,i)=>{
    const b=button('',()=>choosePalette(i),'palette-result'+(i===ui.paletteIndex?' selected':''));
    const text=node('span','',item.label);
    text.append(node('small','',item.meta));
    b.append(text,node('span','',item.glyph));
    target.append(b);
  });
  if(!ui.paletteMatches.length)target.append(node('p','empty-surface','No matching read context. Try agents, goals, sources, approvals, or recovery.'));
}
function choosePalette(index){
  const selected=ui.paletteMatches[index];
  $('command-palette').close();
  selected?.action();
}
views.forEach(([key,label,glyph])=>{
  const b=button('',()=>setView(key));
  b.dataset.view=key;
  b.setAttribute('aria-label',label);
  b.append(node('span','dock-glyph',glyph),node('span','',label));
  $('navigation').append(b);
});
$('login-form').addEventListener('submit',async event=>{
  event.preventDefault();
  $('login-error').textContent='';
  const submit=event.currentTarget.querySelector('button');
  submit.disabled=true;
  try{
    await api('/api/v1/login',{
      method:'POST',headers:{
        'Content-Type':'application/json','X-Operator-Request':'1'
      }
      ,body:JSON.stringify({
        credential:$('credential').value
      }
      )
    });
    $('credential').value='';
    await showSession(await api('/api/v1/me'));
  }
  catch(error){
    $('login-error').textContent=error.message;
  }
  finally{
    submit.disabled=false;
  }
});
$('logout').addEventListener('click',async()=>{
  try{
    await api('/api/v1/logout',{
      method:'POST',headers:{
        'Content-Type':'application/json','X-Operator-Request':'1'
      }
      ,body:'{}'
    });
  }
  finally{
    port.clear();
    showLogin();
  }
});
$('sound-toggle').addEventListener('click',()=>audio.toggleMuted());
$('motion-toggle').addEventListener('click',()=>{
  ui.motion=!ui.motion;
  updateMotion();
});
motionQuery.addEventListener('change',updateMotion);
$('refresh').addEventListener('click',()=>setView(ui.view));
$('quarantine-inspect').addEventListener('click',()=>setView('recovery'));
$('palette-toggle').addEventListener('click',()=>openPalette());
$('palette-close').addEventListener('click',()=>$('command-palette').close());
$('command-search').addEventListener('input',()=>{
  ui.paletteIndex=0;
  renderPalette();
});
$('command-search').addEventListener('keydown',event=>{
  if(event.key==='ArrowDown'||event.key==='ArrowUp'){
    event.preventDefault();
    ui.paletteIndex+=event.key==='ArrowDown'?1:-1;
    renderPalette();
  }
  if(event.key==='Enter'){
    event.preventDefault();
    choosePalette(ui.paletteIndex);
  }
});
$('command-palette').addEventListener('close',()=>ui.paletteReturn?.focus());
$('detail-close').addEventListener('click',()=>$('detail-dialog').close());
$('detail-dialog').addEventListener('close',()=>{
  if(ui.detailReturn?.isConnected)ui.detailReturn.focus();
});
document.addEventListener('keydown',event=>{
  if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k'){
    event.preventDefault();
    if($('command-palette').open)$('command-palette').close();
    else openPalette();
  }
});
document.addEventListener('visibilitychange',()=>{
  if(document.hidden)audio.cancelListening();
});
window.addEventListener('pagehide',()=>{
  ui.core?.dispose();
  feed.stop();
  audio.dispose();
});
document.body.classList.toggle('test-mode',testMode);
updateMotion();
Object.assign(window,{
  api,setView,openRecord,detail,selectGoal,commandDiagnostics:()=>({
    ...diagnostics,apiLatency:port.latencies.slice(),audio:audio.getState()
  }
  )
});
api('/api/v1/me').then(showSession).catch(error=>showLogin(error.status===401?'':error.message));
