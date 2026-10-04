// Offline acceptance driver. Chrome's private CDP pipe is not an HTTP debug port.
import {spawn} from 'node:child_process';
import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
const cfg = JSON.parse(readFileSync(0, 'utf8'));
const chrome = spawn(cfg.chrome, ['--headless=new', '--disable-gpu', '--no-first-run',
  '--no-default-browser-check', '--disable-background-networking', '--remote-debugging-pipe',
  '--user-data-dir='+cfg.profile, 'about:blank'],
  {stdio:['ignore','ignore','ignore','pipe','pipe'], windowsHide:true});
let sequence=0, buffer='', session;
const pending=new Map(), dialogs=[], exceptions=[], violations=[];
chrome.stdio[4].on('data', data=>{
  buffer+=data.toString(); let end;
  while((end=buffer.indexOf('\0'))>=0){
    const message=JSON.parse(buffer.slice(0,end)); buffer=buffer.slice(end+1);
    if(message.id){const p=pending.get(message.id);pending.delete(message.id);
      if(p){clearTimeout(p.timer);message.error?p.reject(new Error(JSON.stringify(message.error))):p.resolve(message.result);}}
    if(message.method==='Page.javascriptDialogOpening') dialogs.push(message.params.type);
    if(message.method==='Runtime.exceptionThrown') exceptions.push(message.params.exceptionDetails.text);
  }
});
function send(method,params={},sessionId=session){return new Promise((resolve,reject)=>{
  const id=++sequence;
  const timer=setTimeout(()=>{pending.delete(id);reject(new Error('CDP timeout: '+method));},15000);
  pending.set(id,{resolve,reject,timer});
  chrome.stdio[3].write(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})})+'\0');
});}
async function evaluate(expression){const result=await send('Runtime.evaluate',
  {expression,awaitPromise:true,returnByValue:true,replMode:true});
  if(result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
  return result.result.value;
}
async function until(expression){for(let i=0;i<100;i++){
  if(await evaluate(expression)) return;
  await new Promise(r=>setTimeout(r,100));
}throw new Error('DOM condition timed out: '+expression);}
try{
  const target=await send('Target.createTarget',{url:'about:blank'},null);
  session=(await send('Target.attachToTarget',{targetId:target.targetId,flatten:true},null)).sessionId;
  await send('Page.enable');await send('Runtime.enable');
  await send('Page.addScriptToEvaluateOnNewDocument',{source:
    'window.cspViolations=[];document.addEventListener("securitypolicyviolation",e=>window.cspViolations.push(e.violatedDirective));'});
  await send('Page.navigate',{url:cfg.origin});
  await until('document.getElementById("login") && !document.getElementById("login").hidden');
  await evaluate(`document.getElementById('credential').value=${JSON.stringify(cfg.credential)};document.getElementById('login-form').requestSubmit();`);
  await until('document.querySelectorAll("#overview .card").length===8');
  for(const kind of ['departments','knowledge','messages']){
    await evaluate(`await setView(${JSON.stringify(kind)}); true`);
    await evaluate(`detail((await api('/api/v1/inspect/'+${JSON.stringify(kind)}+'?limit=100')).items.find(r=>JSON.stringify(r.fields).includes(${JSON.stringify(cfg.marker)})))`);
    assert(await evaluate(`document.getElementById('detail').textContent.includes(${JSON.stringify(cfg.marker)})`),kind);
    assert.equal(await evaluate('document.querySelectorAll("#detail script,#detail img").length'),0);
  }
  await evaluate(`await openRecord('goals',${JSON.stringify(cfg.goal)}); true`);
  await evaluate(`[...document.querySelectorAll('#detail button')].find(b=>b.textContent==='View timeline').click()`);
  await until('document.querySelectorAll("#data .row").length>0');
  await evaluate(`detail((await api('/api/v1/audit/goals/'+${JSON.stringify(cfg.goal)})).items.find(r=>JSON.stringify(r.metadata).includes(${JSON.stringify(cfg.marker)})))`);
  assert(await evaluate(`document.getElementById('detail').textContent.includes(${JSON.stringify(cfg.marker)})`));
  // Navigate real structural lineage and follow a returned Task link.
  await evaluate(`await openRecord('goals',(await api('/api/v1/inspect/goals?limit=100')).items.find(r=>JSON.stringify(r.fields).includes('cross-department')).id); true`);
  await evaluate(`[...document.querySelectorAll('#detail button')].find(b=>b.textContent==='Inspect related lineage').click()`);
  await until('document.querySelectorAll(".lineage button").length>0');
  await evaluate('document.querySelector(".lineage button").click()');
  await until('document.querySelector("#heading").textContent==="Tasks" && !document.getElementById("detail").hidden');
  await evaluate(`await setView('recovery'); true`);
  assert(await evaluate('document.querySelectorAll("#data .row").length>0'));
  violations.push(...await evaluate('window.cspViolations'));
  assert.deepEqual(violations,[]);assert.deepEqual(dialogs,[]);assert.deepEqual(exceptions,[]);
  console.log(JSON.stringify({result:'browser_acceptance_passed',stored_fields:4,
    csp_violations:0,dialogs:0,script_exceptions:0,lineage_navigation:true}));
}finally{
  await send('Browser.close',{},null).catch(()=>{});
  chrome.kill();
  for(const p of pending.values())clearTimeout(p.timer);
}
