"use strict";
const $ = id => document.getElementById(id);
const labels = {
  overview:"Overview",organization:"Organization",departments:"Departments",agents:"Agents",
  goals:"Goals",tasks:"Tasks",runs:"Agent runs",orchestrations:"Orchestration",
  messages:"Messages",knowledge:"Knowledge sources",memory:"Memory entries",
  approvals:"Approvals",tools:"Tool versions",recovery:"Recovery cases",audit:"Audit timeline"
};
const descriptions = {
  overview:"Current canonical records for this workspace.",
  recovery:"Classification only. A safe retry candidate is not an execution command.",
  approvals:"Exact intent, actor, digest, decision and consumption metadata. Review is read only.",
  audit:"Select a Goal to inspect its ordered audit events."
};
let view="overview", cursor=null, next=null, history=[], account=null, activeGoal=null;
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
function setView(name){view=name;cursor=null;next=null;history=[];document.querySelectorAll("nav button").forEach(b=>b.classList.toggle("active",b.dataset.view===view));$("heading").textContent=labels[name];$("intro").textContent=descriptions[name]||"Workspace scoped, redacted canonical records.";$("detail").hidden=true;render();}
function card(label,value){const item=node("div","card");item.append(node("span",null,label),node("strong",null,value));return item;}
async function renderOverview(){
  const categories=["goals","tasks","agents","runs","orchestrations","messages","approvals","invocations"];
  const results=await Promise.all(categories.map(async k=>[k,await api("/api/v1/inspect/"+k+"?limit=100")]));
  clear($("overview"));results.forEach(([k,data])=>$("overview").append(card(labels[k]||k,data.items.length+(data.next_cursor?"+":""))));
  $("count").textContent="WORKSPACE SNAPSHOT";
  clear($("data"));$("data").append(node("p","empty","Open a section to inspect records and lineage. Counts are bounded at 100 per category."));clear($("pager"));
}
function summary(item){const fields=Object.fromEntries(item.fields||[]);return fields.objective||fields.title||fields.name||fields["definition.name"]||fields["definition.role"]||fields["intent.operation"]||fields["tool_version.definition.name"]||fields["invocation.status"]||item.subject_type||item.id;}
function state(item){const f=Object.fromEntries(item.fields||[]);return f.status||f["intent.risk"]||f["invocation.status"]||item.event_kind||"";}
function detail(item){const panel=$("detail");clear(panel);panel.hidden=false;panel.append(node("h2",null,summary(item)));const dl=node("dl");const pairs=item.fields||Object.entries(item).filter(([k])=>k!=="fields");pairs.forEach(([k,v])=>{dl.append(node("dt",null,k.replaceAll("_"," ")),node("dd",null,typeof v==="object"?JSON.stringify(v):v));});panel.append(dl);panel.scrollIntoView({behavior:"smooth",block:"nearest"});}
function renderRows(items){const data=$("data");clear(data);if(!items.length){data.append(node("p","empty","No records in this workspace for this section."));return;}items.forEach(item=>{const row=node("button","row");row.type="button";row.append(node("span","id",item.id||item.subject_id||item.event_id),node("span","label",summary(item)),node("span","status",state(item)));row.addEventListener("click",()=>detail(item));data.append(row);});}
function pageButtons(){const pager=$("pager");clear(pager);const back=node("button",null,"Previous");back.disabled=!history.length;back.addEventListener("click",()=>{cursor=history.pop()??null;render();});const forward=node("button",null,"Next");forward.disabled=!next;forward.addEventListener("click",()=>{history.push(cursor);cursor=next;render();});pager.append(back,node("span",null,"Page "+(history.length+1)),forward);}
async function render(){if(!account)return;clear($("overview"));clear($("data"));clear($("pager"));try{
  await status();if(view==="overview"){await renderOverview();return;}
  if(view==="audit"&&!activeGoal){$("data").append(node("p","empty","Open a Goal and choose View timeline to inspect its audit history."));return;}
  const p=new URLSearchParams({limit:"25"});if(cursor)p.set("cursor",cursor);
  const path=view==="recovery"?"/api/v1/recovery":view==="audit"?"/api/v1/audit/goals/"+encodeURIComponent(activeGoal):"/api/v1/inspect/"+view;
  const result=await api(path+"?"+p);next=result.next_cursor;$("count").textContent=result.items.length+" RECORDS ON PAGE";renderRows(result.items);pageButtons();
  if(view==="goals"){$("data").querySelectorAll(".row").forEach((row,index)=>row.addEventListener("click",()=>{const btn=node("button",null,"View timeline");btn.addEventListener("click",()=>{activeGoal=result.items[index].id;setView("audit");});$("detail").append(btn);}));}
}catch(error){$("data").append(node("p","error",error.message));if(error.message==="authentication_required")showLogin();}}
document.querySelectorAll("nav button").forEach(button=>button.addEventListener("click",()=>setView(button.dataset.view)));
$("login-form").addEventListener("submit",async event=>{event.preventDefault();$("login-error").textContent="";try{await api("/api/v1/login",{method:"POST",headers:{"Content-Type":"application/json","X-Operator-Request":"1"},body:JSON.stringify({credential:$("credential").value})});$("credential").value="";showSession(await api("/api/v1/me"));setView("overview");}catch(error){$("login-error").textContent=error.message;}});
$("logout").addEventListener("click",async()=>{try{await api("/api/v1/logout",{method:"POST",headers:{"Content-Type":"application/json","X-Operator-Request":"1"},body:"{}"});}finally{showLogin();}});
api("/api/v1/me").then(person=>{showSession(person);setView("overview");}).catch(showLogin);
