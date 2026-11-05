'use strict';
const $ = id => document.getElementById(id);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const storage = { get(key, fallback='') { try { return localStorage.getItem('black-inbox-'+key) ?? fallback; } catch { return fallback; } }, set(key,value) { try { localStorage.setItem('black-inbox-'+key,value); } catch {} } };
const labels = {needs:'Needs your input',working:'Working',unread:'Unread',read:'Read',settled:'Settled',idle:'Idle',unknown:'Status unknown',interrupted:'Interrupted'};
const number = value => typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString() : '—';
const when = timestamp => new Date(timestamp*1000).toLocaleString([], {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
// Always open on the complete to-do list, never an old search or recovery view.
let state, query='', project='', showAll=false, rendered='', noticeTimer, refreshNumber=0;
const expanded = new Set(), contexts = new Map(), loadingContexts = new Set();
function notice(message) { clearTimeout(noticeTimer); $('notice').textContent=message; $('notice').hidden=false; noticeTimer=setTimeout(()=>$('notice').hidden=true,5000); }
async function api(path,body) {
  const response=await fetch('/api/'+path,body===undefined ? {cache:'no-store'} : {method:'POST',keepalive:true,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data=await response.json();
  if(!response.ok) throw new Error(data.error || 'Request failed');
  return data;
}
const fresh = {pin:b=>({pinned:b.pinned}), read:b=>({read:b.read,done_at:b.read?Date.now()/1000:0})};
const pending = new Map();
function optimistic(path,body) {
  if(!state||!fresh[path]) return;
  const row=state.chats.find(r=>r.id===body.id); if(!row) return;
  const fields=fresh[path](body); Object.assign(row,fields);
  pending.set(body.id+path,{id:body.id,fields,until:Date.now()+8000});
  applyLocal();
}
function applyLocal() {
  state.chats.sort((a,b)=>(b.pinned-a.pinned)||(b.updated_at-a.updated_at));
  const active=state.chats.filter(r=>!r.archived&&!r.managed_by_t3), todo=active.filter(r=>!r.read);
  Object.assign(state.counts,{todo:todo.length,needs:todo.filter(r=>r.state==='needs').length,working:todo.filter(r=>r.state==='working').length,unread:todo.filter(r=>r.state==='unread').length});
  render(true);
}
async function mutate(path,body,message) {
  optimistic(path,body);
  try { await api(path,body); if(message) notice(message); refresh(); return true; }
  catch(error) { pending.clear(); notice(error.message); refresh(); return false; }
}
async function refresh() {
  const request=++refreshNumber;
  try {
    const data=await api('state'); if(request!==refreshNumber) return;
    for(const [key,p] of pending) { if(Date.now()>p.until) { pending.delete(key); continue; } const row=data.chats.find(r=>r.id===p.id); if(row) Object.assign(row,p.fields); }
    if(pending.size) { state=data; applyLocal(); } else state=data;
    $('connection-error').hidden=true; $('connection').textContent='Saved locally · '+new Date(data.updated_at*1000).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});
    render();
  } catch { if(request!==refreshNumber) return; $('connection-error').textContent='Connection lost. Your last loaded list is still here. Reconnecting…'; $('connection-error').hidden=false; $('connection').textContent='Offline · Last loaded list retained'; }
}
function safeLink(href) { try { const u=new URL(href); return ['codex:','claude:'].includes(u.protocol) ? href : ''; } catch { return ''; } }
function tokenHTML(details,source) {
  const tokens=details.tokens||{};
  const entries=[['Total reported',tokens.total_tokens],['Input',tokens.input_tokens],['Cached input',tokens.cached_input_tokens],['Output',tokens.output_tokens],['Reasoning',tokens.reasoning_output_tokens],['Cache creation',tokens.cache_creation_input_tokens]].filter(([,v])=>v!==undefined);
  const usage=entries.length ? '<dl class="tokens">'+entries.map(([key,value])=>`<div><dt>${key}</dt><dd>${number(value)}</dd></div>`).join('')+'</dl>' : '<p>Token counts are not reported in this transcript.</p>';
  const context=Number.isFinite(details.context_window) && details.context_window>0 ? `<progress aria-label="Last reported context usage" max="${details.context_window}" value="${Number(details.context_tokens)||0}"></progress><p>Last context: ${number(details.context_tokens)} / ${number(details.context_window)} tokens</p>` : '';
  const limits=details.rate_limits;
  const windows=limits && !Array.isArray(limits) ? ['primary','secondary'].filter(k=>limits[k]).map(key=>{const w=limits[key],used=w.used_percent??w.usedPercent;return `<p>${key==='primary'?'Short':'Long'} usage window: ${used==null?'not reported':escapeHTML(used)+'% used'}${w.resets_at?' · resets '+escapeHTML(when(w.resets_at)):''}</p>`;}).join('') : '';
  return `<h3>Token usage</h3>${usage}${context}<p>${escapeHTML(details.model||'Model not reported')} · Provider-reported counts, not billing estimates.${source==='Codex'?' Cached input is included in input; reasoning is included in output.':''}</p>${windows}`;
}
function contextHTML(context) {
  if(!context.available) return '<p>The folder is unavailable or is not a Git repository.</p>';
  const pr=context.pull_request;
  let link='';
  if(pr) { try { const url=new URL(pr.url); if(url.protocol==='https:') link=`<p><a href="${escapeHTML(url.href)}" target="_blank" rel="noreferrer">${escapeHTML(pr.title)} · ${escapeHTML(pr.state)}</a></p>`; } catch {} }
  const changes=file=>file.added==='new'?'new file':file.added==='-'||file.removed==='-'?'binary file':`+${Number(file.added)||0} / −${Number(file.removed)||0}`;
  return `<p>Current branch: ${escapeHTML(context.branch||'detached HEAD')}</p>${link||'<p>No pull request found, or GitHub is unavailable.</p>'}${context.files.length?'<ul class="context-files">'+context.files.map(f=>`<li>${escapeHTML(f.path)} · ${changes(f)}</li>`).join('')+'</ul>':'<p>Working tree is clean.</p>'}`;
}
function rowHTML(row) {
  const id=escapeHTML(row.id), href=row.managed_by_t3?'':safeLink(row.href), details=row.details||{};
  const title=href ? `<a class="title" href="${escapeHTML(href)}" title="${escapeHTML(row.title)}" data-action="open">${escapeHTML(row.title)}</a>` : (row.source==='Claude'&&!row.managed_by_t3 ? `<a class="title" href="#" title="No app link for this chat. Click to resume it in a terminal." data-action="resume">${escapeHTML(row.title)}</a>` : `<span class="title" title="${escapeHTML(row.title)}">${escapeHTML(row.title)}</span>`);
  return `<article class="row ${row.source==='Claude'?'Claude':'Codex'} ${escapeHTML(row.state)} ${row.managed_by_t3?'t3':''}" data-id="${id}" tabindex="0" aria-label="${escapeHTML(row.title)}, ${escapeHTML(labels[row.state]||row.state)}"><div class="top">${title}<div class="actions"><button data-action="pin" aria-label="${row.pinned?'Unpin':'Pin'} ${escapeHTML(row.title)}" aria-pressed="${row.pinned}">${row.pinned?'◆ Pinned':'◇ Pin'}</button><button data-action="read" aria-label="${row.read?'Return to to-do':'Mark done'} ${escapeHTML(row.title)}">${row.read?'↶ To-do':'✓ Done'}</button></div></div><div class="meta"><span class="state ${escapeHTML(row.state)}">${escapeHTML(labels[row.state]||row.state)}</span><span>${escapeHTML(row.project)}</span>${row.branch?`<span>⑂ ${escapeHTML(row.branch)}</span>`:''}<time>${escapeHTML(when(row.updated_at))}</time></div><div class="snippet">${escapeHTML(row.last||'No final answer yet.')}</div><div class="row-links"><details data-expand="preview:${id}" ${expanded.has('preview:'+row.id)?'open':''}><summary>Preview</summary><pre class="answer">${escapeHTML(row.last||'No final answer yet.')}</pre></details><details data-expand="details:${id}" ${expanded.has('details:'+row.id)?'open':''}><summary>Details</summary><div class="details-body"><p>${escapeHTML(row.cwd||'No project folder')}</p>${row.state==='needs'?'<p>Answer the pending question in the original app. Done clears it from this list only.</p>':''}${row.state==='interrupted'?'<p>This turn was active before Windows last started. Open the chat to resume.</p>':''}${tokenHTML(details,row.source)}<h3>Project context</h3><button data-action="context" ${loadingContexts.has(row.id)?'disabled':''}>${loadingContexts.has(row.id)?'Loading…':contexts.has(row.id)?'Refresh branch, PR & changes':'Load branch, PR & changes'}</button>${contexts.has(row.id)?contextHTML(contexts.get(row.id)):''}</div></details></div></article>`;
}
const RECENT_DAYS=7, RECENT_MAX=15;
function doneHTML(row) {
  const href=row.managed_by_t3?'':safeLink(row.href), id=escapeHTML(row.id);
  const attrs=href?`href="${escapeHTML(href)}" data-action="open"`:row.source==='Claude'?'href="#" data-action="resume"':'';
  const title=attrs?`<a class="title" ${attrs} title="${escapeHTML(row.title)}">${escapeHTML(row.title)}</a>`:`<span class="title">${escapeHTML(row.title)}</span>`;
  return `<article class="row done-row ${row.source==='Claude'?'Claude':'Codex'}" data-id="${id}" tabindex="0"><div class="top">${title}<div class="actions"><button data-action="read" aria-label="Return to to-do ${escapeHTML(row.title)}">↶ To-do</button></div></div><div class="meta"><span>${escapeHTML(row.project)}</span><time>Done ${escapeHTML(when(row.done_at))}</time></div></article>`;
}
function render(force=false) {
  if(!state) return;
  const chats=state.chats.filter(row=>!row.archived);
  const projects=new Map(chats.map(row=>[row.project_key,row.project]));
  // Drop a stale project filter rather than leaving the saved inbox invisibly empty.
  if(project && !projects.has(project)) { project=''; storage.set('project',''); }
  const projectOptions=JSON.stringify([...projects]);
  if($('project').dataset.options!==projectOptions) { $('project').innerHTML='<option value="">All projects</option>'+[...projects].sort((a,b)=>a[1].localeCompare(b[1])).map(([key,label])=>`<option value="${escapeHTML(key)}">${escapeHTML(label)}</option>`).join(''); $('project').dataset.options=projectOptions; }
  $('project').value=project; $('group').checked=state.settings.group_by_project; $('all-chats').setAttribute('aria-pressed',String(showAll)); $('t3-warning').hidden=state.t3?.status!=='unavailable';
  const count=state.counts.todo;
  $('unread-count').textContent=count; $('unread-count').classList.toggle('zero',count===0);
  document.title=(count?'('+count+') ':'')+(state.title==='Agent Manager'?'Chat inbox':state.title||'Chat inbox');
  const filtered=chats.filter(row=>(!project||row.project_key===project)&&(!query||(row.title+' '+row.project+' '+row.last).toLocaleLowerCase().includes(query.toLocaleLowerCase())));
  const rows=filtered.filter(row=>!row.managed_by_t3&&(showAll||!row.read)), t3=filtered.filter(row=>row.managed_by_t3);
  const t3open=chats.filter(row=>row.managed_by_t3&&!row.read);
  $('t3-section').hidden=!t3open.length; $('t3-summary').textContent=t3open.length+' unresolved T3 Code chat'+(t3open.length===1?'':'s');
  $('summary').textContent=`${rows.length} ${showAll?'saved chat':'to-do'}${rows.length===1?'':'s'} · ${state.counts.needs} need your input · ${state.counts.working} working`;
  const cutoff=Date.now()/1000-RECENT_DAYS*86400;
  const recentDone=filtered.filter(row=>!row.managed_by_t3&&row.read&&row.done_at>cutoff).sort((a,b)=>b.done_at-a.done_at).slice(0,RECENT_MAX);
  $('recent-done').hidden=!recentDone.length; $('recent-summary').textContent='Recently done · '+recentDone.length;
  const signature=JSON.stringify([rows,t3open,recentDone.map(r=>[r.id,r.done_at,r.title]),state.settings.group_by_project,project,query,showAll]);
  if(!force && signature===rendered) return;
  const focus=document.activeElement, focusId=focus?.closest('[data-id]')?.dataset.id, focusAction=focus?.dataset.action;
  rendered=signature;
  function groups(items) {
    const pins=items.filter(row=>row.pinned), rest=items.filter(row=>!row.pinned);
    let result=pins.length?'<h2 class="group-heading">Pinned</h2>'+pins.map(rowHTML).join(''):'';
    if(!state.settings.group_by_project) return result+rest.map(rowHTML).join('');
    const map=new Map(); for(const row of rest) { if(!map.has(row.project_key)) map.set(row.project_key,{label:row.project,rows:[]}); map.get(row.project_key).rows.push(row); }
    return result+[...map.values()].map(group=>`<h2 class="group-heading">${escapeHTML(group.label)}</h2>${group.rows.map(rowHTML).join('')}`).join('');
  }
  const recent=rows.filter(row=>!showAll||row.state!=='settled'||row.pinned), settled=rows.filter(row=>showAll&&row.state==='settled'&&!row.pinned);
  $('chats').innerHTML=rows.length ? groups(recent)+(settled.length?`<details class="settled" data-expand="settled" ${expanded.has('settled')||query?'open':''}><summary>Settled · ${settled.length} saved chat${settled.length===1?'':'s'}</summary>${groups(settled)}</details>`:'') : '<p class="empty">'+(query||project?'No matching chats.':showAll?'No saved chats.':'All done. New chat activity will appear here.')+'</p>';
  $('recent-list').innerHTML=recentDone.map(doneHTML).join('');
  $('t3-chats').innerHTML=t3open.map(rowHTML).join('');
  $('chat-lists').querySelectorAll('details[data-expand]').forEach(details=>details.addEventListener('toggle',()=>{if(details.open) expanded.add(details.dataset.expand); else expanded.delete(details.dataset.expand);}));
  if(focusId) { const article=$('chat-lists').querySelector(`[data-id="${CSS.escape(focusId)}"]`); const next=focusAction?article?.querySelector(`[data-action="${CSS.escape(focusAction)}"]`):article; next?.focus({preventScroll:true}); }
}
$('chat-lists').addEventListener('click',async event=>{
  const article=event.target.closest('[data-id]'); if(!article) return;
  const row=state.chats.find(row=>row.id===article.dataset.id); if(!row) return;
  const action=event.target.closest('[data-action]')?.dataset.action;
  if(action==='pin') await mutate('pin',{id:row.id,pinned:!row.pinned});
  else if(action==='read') await mutate('read',{id:row.id,read:!row.read});
  else if(action==='resume') { event.preventDefault(); mutate('read',{id:row.id,read:true}); try { await api('resume',{id:row.id}); notice('Opening a terminal to resume this chat…'); } catch(error) { notice(error.message); } }
  else if(action==='open'&&!row.managed_by_t3) { mutate('read',{id:row.id,read:true}); }
  else if(action==='context') {
    loadingContexts.add(row.id); render(true);
    try { contexts.set(row.id,await api('context?id='+encodeURIComponent(row.id))); } catch(error) { notice(error.message); }
    finally { loadingContexts.delete(row.id); render(true); }
  } else if(!event.target.closest('a,button,details,pre')) article.querySelector('a.title')?.click();
});
$('chat-lists').addEventListener('keydown',event=>{if(event.key==='Enter'&&event.target.matches('article')){event.preventDefault();event.target.querySelector('a.title')?.click();}});
$('search').value=query;
$('search').addEventListener('input',()=>{query=$('search').value;storage.set('query',query);render();});
$('project').addEventListener('change',()=>{project=$('project').value;storage.set('project',project);render();});
$('all-chats').onclick=()=>{showAll=!showAll;storage.set('show-all',showAll);render();};
$('mark-all').onclick=()=>mutate('mark-all',{},'To-do list cleared');
$('group').onchange=()=>mutate('settings',{group_by_project:$('group').checked});
$('settings-open').onclick=()=>{
  if(!state) return;
  const prefs=state.settings;
  $('reminders').checked=prefs.reminders_enabled; $('keep-taskbar').checked=prefs.keep_taskbar;
  for(const [id,value] of [['reminder-delay',prefs.reminder_delay_seconds],['settle-days',prefs.settle_days]]) { if(![...$(id).options].some(option=>option.value===String(value))) $(id).add(new Option(String(value),String(value))); $(id).value=String(value); }
  $('settings').showModal();
};
$('settings-close').onclick=()=>$('settings').close();
$('settings-form').onsubmit=async event=>{event.preventDefault();const saved=await mutate('settings',{reminders_enabled:$('reminders').checked,reminder_delay_seconds:Number($('reminder-delay').value),keep_taskbar:$('keep-taskbar').checked,settle_days:Number($('settle-days').value)},'Preferences saved');if(saved)$('settings').close();};
$('notification-test').onclick=()=>mutate('test-notification',{},'Notification requested');
document.addEventListener('keydown',event=>{if($('settings').open)return;if(event.key==='Escape'){query='';$('search').value='';storage.set('query','');$('search').blur();render();}else if(event.key==='/'&&!event.ctrlKey&&!event.metaKey&&!event.altKey&&!event.target.matches('input,select,textarea')){event.preventDefault();$('search').focus();}});
refresh();
setInterval(()=>{if(!document.hidden&&!$('settings').open)refresh();},5000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
