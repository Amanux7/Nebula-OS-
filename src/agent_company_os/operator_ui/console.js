"use strict";
const $ = id => document.getElementById(id);
const labels = {
  overview:"Overview",organization:"Organization",departments:"Departments",agents:"Agents",
  goals:"Goals",tasks:"Tasks",runs:"Agent runs",orchestrations:"Orchestration",
  messages:"Messages",knowledge:"Knowledge sources",memory:"Memory entries",
  approvals:"Approvals",tools:"Tool definitions",recovery:"Recovery cases",audit:"Audit timeline",
  agent_versions:"Agent versions",graph_versions:"Organization versions",plans:"Plan versions",
  materializations:"Plan materializations",delegations:"Delegations",delegation_attempts:"Delegation attempts",
  results:"Task results",attempts:"Task attempts",executions:"Executions",threads:"Message threads",
  handoffs:"Handoffs",knowledge_versions:"Knowledge versions",intents:"Action intents",
  approval_requests:"Approval requests",approval_decisions:"Approval decisions",tool_versions:"Tool versions",
  invocations:"Tool invocations",receipts:"Tool receipts",restore:"Restore incident",diagnostics:"Host diagnostics",
  workspaces:"Workspace"
};
const descriptions = {
  overview:"Current canonical records for this workspace.",
  recovery:"Classification only. A safe retry candidate is not an execution command.",
  approvals:"Exact intent, actor, digest, decision and consumption metadata. Review is read only.",
  audit:"Select a Goal to inspect its ordered audit events."
};
let generation=0, view="overview", cursor=null, next=null, history=[], account=null, activeGoal=null;
function node(tag,cls,text){const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=String(text);return n;}
function clear(el){el.replaceChildren();}
async function api(path,options={}){
  const response=await fetch(path,{credentials:"same-origin",...options});
  let data;try{data=await response.json();}catch{throw new Error("Response unavailable");}
  if(!response.ok)throw new Error(data.error?.code||"Request failed");
  return data;
}
function showLogin(){account=null;$("navigation").hidden=true;$("logout").hidden=true;$("content").hidden=true;$("login").hidden=false;$("quarantine").hidden=true;$("identity").textContent="Session required";$("connection").textContent="Signed out";$("heading").textContent="Operator console";}
function showSession(person){account=person;$("navigation").hidden=false;$("logout").hidden=false;$("content").hidden=false;$("login").hidden=true;$("identity").textContent=person.id+" · "+person.role+" · "+person.workspace_id;$("connection").textContent="Local canonical store";}
async function status(){const data=await api("/api/v1/status");$("quarantine").hidden=data.mode!=="restore_quarantine";$("connection").textContent=data.mode.replaceAll("_"," ")+" · "+data.recovery_count+" recovery cases";return data;}
async function setView(name){generation++;view=name;cursor=null;next=null;history=[];document.querySelectorAll("nav button").forEach(b=>b.classList.toggle("active",b.dataset.view===view));$("heading").textContent=labels[name]||name;$("intro").textContent=descriptions[name]||"Workspace scoped, redacted canonical records.";$("detail").hidden=true;await render();}
function card(label,value){const item=node("div","card");item.append(node("span",null,label),node("strong",null,value));return item;}
async function renderOverview(epoch){
  const categories=["goals","tasks","agents","runs","orchestrations","messages","approvals","invocations"];
  const results=await Promise.all(categories.map(async k=>[k,await api("/api/v1/inspect/"+k+"?limit=100")]));
  if(epoch!==generation)return;clear($("overview"));results.forEach(([k,data])=>$("overview").append(card(labels[k]||k,data.items.length+(data.next_cursor?"+":""))));
  $("count").textContent="WORKSPACE SNAPSHOT";
  clear($("data"));$("data").append(node("p","empty","Open a section to inspect records and lineage. Counts are bounded at 100 per category."));clear($("pager"));
}
function summary(item){const fields=Object.fromEntries(item.fields||[]);return fields.objective||fields.title||fields.name||fields["definition.name"]||fields["definition.role"]||fields["intent.operation"]||fields["tool_version.definition.name"]||fields["invocation.status"]||item.subject_type||item.id;}
function state(item){const f=Object.fromEntries(item.fields||[]);return f.status||f["intent.risk"]||f["invocation.status"]||item.reason||item.event_kind||"";}
async function openRecord(kind,id){const epoch=generation+1;await setView(kind);if(epoch!==generation)return;try{const data=await api("/api/v1/inspect/"+kind+"?"+new URLSearchParams({id}));if(epoch!==generation)return;detail(data.items[0]);}catch(error){$("data").append(node("p","error",error.message));}}
function recordLink(link){const button=node("button","record-link",link.label+" · "+link.id);button.type="button";button.addEventListener("click",()=>openRecord(link.kind,link.id));return button;}
function detail(item){const panel=$("detail");clear(panel);panel.hidden=false;panel.append(node("h2",null,summary(item)));const dl=node("dl");const pairs=item.fields||Object.entries(item).filter(([k])=>k!=="fields"&&k!=="links");pairs.forEach(([k,v])=>{dl.append(node("dt",null,k.replaceAll("_"," ")),node("dd",null,typeof v==="object"?JSON.stringify(v):v));});panel.append(dl);(item.links||[]).forEach(link=>panel.append(recordLink(link)));
  if(item.kind&&["goals","tasks","runs","orchestrations","plans","intents","approvals","invocations"].includes(item.kind)){
    const button=node("button",null,"Inspect related lineage");button.addEventListener("click",async()=>{button.disabled=true;try{const lineage=await api("/api/v1/lineage/"+item.kind+"/"+encodeURIComponent(item.id));const tree=node("div","lineage");lineage.sections.forEach(section=>{tree.append(node("h3",null,labels[section.kind]||section.kind));section.records.forEach(record=>tree.append(recordLink({label:summary(record),kind:record.kind,id:record.id})));if(section.truncated)tree.append(node("p",null,"First 100 related records; open the category to page through more."));});if(!lineage.sections.length)tree.append(node("p","empty","No related records."));panel.append(tree);}catch(error){panel.append(node("p","error",error.message));}});panel.append(button);
  }
  if(item.kind==="goals"){const button=node("button",null,"View timeline");button.addEventListener("click",()=>{activeGoal=item.id;setView("audit");});panel.append(button);}
  panel.scrollIntoView({behavior:"smooth",block:"nearest"});}

async function renderRestore(epoch){
  const data=await api("/api/v1/restore");if(epoch!==generation)return;$("count").textContent="RESTORE CONTEXT";
  if(!data.context){$("data").append(node("p","empty","No restore incident is recorded for this workspace."));return;}
  const context=data.context;const title=node("h2",null,"Backup "+context.backup_id+" · generation "+context.generation);$("data").append(title);
  for(const key of ["backup_digest","restored_at","manifest_schema_version","principal_id"])$("data").append(node("p",null,key.replaceAll("_"," ")+": "+context[key]));
  $("data").append(node("p",null,"Restored action intents remain blocked after release. Releasing quarantine never resumes work."));
  context.held_intent_ids.forEach(id=>$("data").append(recordLink({label:"Held action intent",kind:"intents",id})));
  if(account.role==="admin"){const button=node("button",null,"Validate and release quarantine");button.addEventListener("click",async()=>{button.disabled=true;try{const result=await fetch("/api/v1/mode/release",{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json","X-Operator-Request":"1"},body:"{}"});const outcome=await result.json();$("data").append(node("p",result.ok?"":"error",outcome.reason||outcome.error?.code));await status();}catch(error){$("data").append(node("p","error",error.message));}finally{button.disabled=false;}});$("data").append(button);}
  $("data").append(node("h3",null,"Release attempts (latest 100)"));data.release_attempts.forEach(a=>$("data").append(node("p",null,a.timestamp+" · "+a.principal_id+" · "+a.reason)));
}
function renderRows(items){const data=$("data");clear(data);if(!items.length){data.append(node("p","empty","No records in this workspace for this section."));return;}items.forEach(item=>{const row=node("button","row");row.type="button";row.append(node("span","id",item.id||item.subject_id||item.event_id),node("span","label",summary(item)),node("span","status",state(item)));row.addEventListener("click",()=>detail(item));data.append(row);});}
function pageButtons(){const pager=$("pager");clear(pager);const back=node("button",null,"Previous");back.disabled=!history.length;back.addEventListener("click",()=>{cursor=history.pop()??null;render();});const forward=node("button",null,"Next");forward.disabled=!next;forward.addEventListener("click",()=>{history.push(cursor);cursor=next;render();});pager.append(back,node("span",null,"Page "+(history.length+1)),forward);}
async function render(){if(!account)return;const epoch=generation;clear($("overview"));clear($("data"));clear($("pager"));try{
  await status();if(epoch!==generation)return;if(view==="overview"){await renderOverview(epoch);return;}
  if(view==="restore"){await renderRestore(epoch);return;}
  if(view==="diagnostics"){const data=await api("/api/v1/diagnostics");$("data").append(node("pre",null,JSON.stringify(data,null,2)));return;}
  if(view==="audit"&&!activeGoal){$("data").append(node("p","empty","Open a Goal and choose View timeline to inspect its audit history."));return;}
  const p=new URLSearchParams({limit:"25"});if(cursor)p.set("cursor",cursor);
  const path=view==="recovery"?"/api/v1/recovery":view==="audit"?"/api/v1/audit/goals/"+encodeURIComponent(activeGoal):"/api/v1/inspect/"+view;
  const result=await api(path+"?"+p);if(epoch!==generation)return;next=result.next_cursor;$("count").textContent=result.items.length+" RECORDS ON PAGE";renderRows(result.items);pageButtons();
}catch(error){$("data").append(node("p","error",error.message));if(error.message==="authentication_required")showLogin();}}
clear($("navigation"));Object.entries(labels).forEach(([name,label])=>{const button=node("button",null,label);button.dataset.view=name;button.addEventListener("click",()=>setView(name));$("navigation").append(button);});
$("login-form").addEventListener("submit",async event=>{event.preventDefault();$("login-error").textContent="";try{await api("/api/v1/login",{method:"POST",headers:{"Content-Type":"application/json","X-Operator-Request":"1"},body:JSON.stringify({credential:$("credential").value})});$("credential").value="";showSession(await api("/api/v1/me"));setView("overview");}catch(error){$("login-error").textContent=error.message;}});
$("logout").addEventListener("click",async()=>{try{await api("/api/v1/logout",{method:"POST",headers:{"Content-Type":"application/json","X-Operator-Request":"1"},body:"{}"});}finally{showLogin();}});
api("/api/v1/me").then(person=>{showSession(person);setView("overview");}).catch(showLogin);
