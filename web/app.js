'use strict';
const $ = id => document.getElementById(id);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const storage = { get(key, fallback='') { try { return localStorage.getItem('black-inbox-'+key) ?? fallback; } catch { return fallback; } }, set(key,value) { try { localStorage.setItem('black-inbox-'+key,value); } catch {} } };
const labels = {needs:'Needs your input',working:'Working',unread:'Unread',read:'Read',settled:'Settled',idle:'Idle',unknown:'Status unknown',interrupted:'Interrupted'};
const number = value => typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString() : '—';
const when = timestamp => new Date(timestamp*1000).toLocaleString([], {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
// Always open on the complete to-do list, never an old search or recovery view.
let ideasRendered='', ideaTimer=0, ideaBusy=0, build=0, state, query='', project='', showAll=false, rendered='', noticeTimer, refreshNumber=0;
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
  const active=state.chats.filter(r=>!r.archived&&!r.managed_by_t3&&!r.automated), todo=active.filter(r=>!r.read);
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
    if(data.build&&build&&data.build!==build) { location.reload(); return; }
    build=data.build||build;
    for(const [key,p] of pending) { if(Date.now()>p.until) { pending.delete(key); continue; } const row=data.chats.find(r=>r.id===p.id); if(row) Object.assign(row,p.fields); }
    const localIdeas=(ideaBusy||ideaTimer)&&state?state.ideas:null;
    if(pending.size) { state=data; applyLocal(); } else state=data;
    if(localIdeas) state.ideas=localIdeas;
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
function compact(n) { return n>=1e6?(n/1e6).toFixed(n>=1e7?0:1)+'M':n>=1e3?Math.round(n/1e3)+'K':String(n); }
function usageHTML(row) {
  const u=row.usage||{}; if(!u.total_tokens) return '';
  const pct=value=>value>0&&value<1?'<1%':Math.round(value)+'%';
  const limit=state.limits&&state.limits[row.source], basis=state.limit_basis&&state.limit_basis[row.source];
  const chips=[`<span class="chip tok" title="Total tokens used so far in this chat">${compact(u.total_tokens)} tok</span>`];
  if(u.context_pct!=null) chips.push(`<span class="chip ctx" title="How full this chat's context window is">ctx ${pct(u.context_pct)}</span>`);
  chips.push(`<span class="chip five" title="Estimated share of your 5-hour limit this chat used in the last 5 hours${limit?' (limit estimated at '+compact(limit)+' weighted tokens from '+basis+')':''}">5h ${pct(u.five_hour_pct)}</span>`);
  return `<span class="chips">${chips.join('')}</span>`;
}
function rowHTML(row) {
  const id=escapeHTML(row.id), href=row.managed_by_t3?'':safeLink(row.href), details=row.details||{};
  const title=href ? `<a class="title" href="${escapeHTML(href)}" title="${escapeHTML(row.title)}" data-action="open">${escapeHTML(row.title)}</a>` : `<span class="title" title="${escapeHTML(row.title)}">${escapeHTML(row.title)}</span>`;
  return `<article class="row ${row.source==='Claude'?'Claude':'Codex'} ${escapeHTML(row.state)} ${row.managed_by_t3?'t3':''}" data-id="${id}" tabindex="0" aria-label="${escapeHTML(row.title)}, ${escapeHTML(labels[row.state]||row.state)}"><div class="top"><i class="dot" aria-hidden="true"></i>${title}${usageHTML(row)}<div class="actions"><button class="pin-btn" data-action="pin" aria-label="${row.pinned?'Unpin':'Pin'} ${escapeHTML(row.title)}" aria-pressed="${row.pinned}">${row.pinned?'◆ Pinned':'◇ Pin'}</button><button class="done-btn${row.read?' undo':''}" data-action="read" aria-label="${row.read?'Return to to-do':'Mark done'} ${escapeHTML(row.title)}">${row.read?'↶ To-do':'<span class="check">✓</span> Done'}</button></div></div><div class="snippet-wrap"><div class="snippet">${escapeHTML(row.last||'No final answer yet.')}</div><time class="stamp">${escapeHTML(when(row.updated_at))}</time></div></article>`;
}
const RECENT_DAYS=7, RECENT_MAX=15;
function doneHTML(row) {
  const href=row.managed_by_t3?'':safeLink(row.href), id=escapeHTML(row.id);
  const attrs=href?`href="${escapeHTML(href)}" data-action="open"`:'';
  const title=attrs?`<a class="title" ${attrs} title="${escapeHTML(row.title)}">${escapeHTML(row.title)}</a>`:`<span class="title">${escapeHTML(row.title)}</span>`;
  return `<article class="row done-row ${row.source==='Claude'?'Claude':'Codex'}" data-id="${id}" tabindex="0"><div class="top">${title}<div class="actions"><button class="done-btn undo" data-action="read" aria-label="Return to to-do ${escapeHTML(row.title)}">↶ To-do</button></div></div><div class="meta"><span>${escapeHTML(row.project)}</span><time>Done ${escapeHTML(when(row.done_at))}</time></div></article>`;
}
const MAKE={'claude-chat':['Claude chat',text=>'claude://claude.ai/new?surface=chat&source=desktop_action&q='+encodeURIComponent(text)],'claude-code':['Claude Code',text=>'claude://code/new?q='+encodeURIComponent(text)],'codex':['Codex',text=>'codex://threads/new?prompt='+encodeURIComponent(text)]};
function ideaApi(path,body) { ideaBusy++; return api(path,body).catch(error=>notice(error.message)).finally(()=>ideaBusy--); }
function ideaHTML(idea) {
  const sent=idea.sent?`Sent to ${escapeHTML((MAKE[idea.sent.target]||[idea.sent.target])[0])} · ${escapeHTML(when(idea.sent.at))}`:'Make this a chat:';
  return `<article class="idea" data-idea="${escapeHTML(idea.id)}"><textarea rows="3" placeholder="Type an idea…" aria-label="Idea">${escapeHTML(idea.text)}</textarea><div class="idea-bar"><span class="idea-label">${sent}</span>${Object.entries(MAKE).map(([key,[label]])=>`<button type="button" class="mk ${key.startsWith('claude')?'claude':'codex'}" data-make="${key}">${label}</button>`).join('')}<button type="button" class="idea-del" data-idea-delete aria-label="Delete idea">✕</button></div></article>`;
}
function renderIdeas(force=false) {
  const ideas=state.ideas||[], signature=JSON.stringify(ideas.map(i=>[i.id,i.sent]));
  $('ideas').hidden=!ideas.length;
  if(!force&&signature===ideasRendered) return;
  ideasRendered=signature;
  $('ideas').innerHTML=`<h2 class="group-heading">Ideas · ${ideas.length}</h2>`+ideas.map(ideaHTML).join('');
  $('ideas').querySelectorAll('textarea').forEach(fit);
}
function fit(box) { box.style.height='auto'; box.style.height=Math.min(320,box.scrollHeight)+'px'; }
function findIdea(node) { const id=node.closest('.idea')?.dataset.idea; return {id,idea:(state.ideas||[]).find(i=>i.id===id)}; }
$('new-todo').onclick=()=>{
  const idea={id:(crypto.randomUUID?crypto.randomUUID():String(Date.now())+Math.random().toString(36).slice(2)).replace(/-/g,'').slice(0,24),text:'',created_at:Date.now()/1000,sent:null};
  state.ideas=[idea,...(state.ideas||[])]; renderIdeas(true);
  ideaApi('idea-add',{id:idea.id,text:''});
  const box=$('ideas').querySelector(`[data-idea="${idea.id}"] textarea`); box.focus(); box.scrollIntoView({block:'center',behavior:'smooth'});
};
$('ideas').addEventListener('input',event=>{
  if(!event.target.matches('textarea')) return;
  const {id,idea}=findIdea(event.target); if(!idea) return;
  idea.text=event.target.value; fit(event.target);
  clearTimeout(ideaTimer); ideaTimer=setTimeout(()=>{ideaTimer=0; ideaApi('idea-update',{id,text:idea.text});},500);
});
$('ideas').addEventListener('focusout',event=>{
  if(!event.target.matches('textarea')) return;
  const {id,idea}=findIdea(event.target); if(!idea) return;
  clearTimeout(ideaTimer); ideaTimer=0;
  if(!idea.text.trim()) { state.ideas=state.ideas.filter(i=>i.id!==id); ideaApi('idea-delete',{id}); setTimeout(()=>renderIdeas(true),0); }
  else ideaApi('idea-update',{id,text:idea.text});
});
$('ideas').addEventListener('click',async event=>{
  const {id,idea}=findIdea(event.target); if(!idea) return;
  if(event.target.closest('[data-idea-delete]')) { state.ideas=state.ideas.filter(i=>i.id!==id); renderIdeas(true); ideaApi('idea-delete',{id}); return; }
  const make=event.target.closest('[data-make]')?.dataset.make; if(!make) return;
  const text=idea.text.trim(); if(!text) { notice('Type something first.'); return; }
  try { await navigator.clipboard.writeText(text); } catch {}
  const link=document.createElement('a'); link.href=MAKE[make][1](text); link.click();
  idea.sent={target:make,at:Date.now()/1000}; renderIdeas(true);
  ideaApi('idea-sent',{id,text,target:make});
  notice(`Copied and opened ${MAKE[make][0]}. If it did not fill in, paste with Ctrl+V.`);
});
function render(force=false) {
  if(!state) return;
  renderIdeas();
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
  const rows=filtered.filter(row=>!row.managed_by_t3&&(showAll||(!row.read&&!row.automated))), t3=filtered.filter(row=>row.managed_by_t3);
  const t3open=state.t3?.unresolved||[];
  $('t3-section').hidden=!t3open.length; $('t3-summary').textContent=t3open.length+' unresolved T3 Code chat'+(t3open.length===1?'':'s');
  $('summary').textContent=`${rows.length} ${showAll?'saved chat':'to-do'}${rows.length===1?'':'s'} · ${state.counts.needs} need your input · ${state.counts.working} working`;
  const cutoff=Date.now()/1000-RECENT_DAYS*86400;
  const recentDone=filtered.filter(row=>!row.managed_by_t3&&!row.automated&&row.read&&row.done_at>cutoff).sort((a,b)=>b.done_at-a.done_at).slice(0,RECENT_MAX);
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
  const working=recent.filter(row=>row.state==='working'&&!row.pinned), idle=recent.filter(row=>!(row.state==='working'&&!row.pinned));
  $('chats').innerHTML=rows.length ? groups(idle)+(working.length?`<h2 class="group-heading">Working · ${working.length}</h2>`+working.map(rowHTML).join(''):'')+(settled.length?`<details class="settled" data-expand="settled" ${expanded.has('settled')||query?'open':''}><summary>Settled · ${settled.length} saved chat${settled.length===1?'':'s'}</summary>${groups(settled)}</details>`:'') : '<p class="empty">'+(query||project?'No matching chats.':showAll?'No saved chats.':'All done. New chat activity will appear here.')+'</p>';
  $('recent-list').innerHTML=recentDone.map(doneHTML).join('');
  $('t3-chats').innerHTML=t3open.map(t=>`<article class="row t3"><div class="top"><span class="title">${escapeHTML(t.title)}</span></div><div class="meta"><time>${escapeHTML(t.updated_at?when(Date.parse(t.updated_at)/1000):'')}</time></div></article>`).join('');
  $('chat-lists').querySelectorAll('details[data-expand]').forEach(details=>details.addEventListener('toggle',()=>{if(details.open) expanded.add(details.dataset.expand); else expanded.delete(details.dataset.expand);}));
  if(focusId) { const article=$('chat-lists').querySelector(`[data-id="${CSS.escape(focusId)}"]`); const next=focusAction?article?.querySelector(`[data-action="${CSS.escape(focusAction)}"]`):article; next?.focus({preventScroll:true}); }
}
$('chat-lists').addEventListener('click',async event=>{
  const article=event.target.closest('[data-id]'); if(!article) return;
  const row=state.chats.find(row=>row.id===article.dataset.id); if(!row) return;
  const action=event.target.closest('[data-action]')?.dataset.action;
  if(action==='pin') await mutate('pin',{id:row.id,pinned:!row.pinned});
  else if(action==='read') {
    if(!row.read&&!article.classList.contains('resolving')&&!matchMedia('(prefers-reduced-motion: reduce)').matches) {
      article.style.height=article.offsetHeight+'px'; article.classList.add('resolving');
      await new Promise(done=>setTimeout(done,520));
    }
    await mutate('read',{id:row.id,read:!row.read});
  }
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
  $('five-limit').value=prefs.five_hour_limit_tokens||0; $('reminders').checked=prefs.reminders_enabled; $('keep-taskbar').checked=prefs.keep_taskbar;
  for(const [id,value] of [['reminder-delay',prefs.reminder_delay_seconds],['settle-days',prefs.settle_days]]) { if(![...$(id).options].some(option=>option.value===String(value))) $(id).add(new Option(String(value),String(value))); $(id).value=String(value); }
  $('settings').showModal();
};
$('settings-close').onclick=()=>$('settings').close();
$('settings-form').onsubmit=async event=>{event.preventDefault();const saved=await mutate('settings',{reminders_enabled:$('reminders').checked,reminder_delay_seconds:Number($('reminder-delay').value),keep_taskbar:$('keep-taskbar').checked,settle_days:Number($('settle-days').value),five_hour_limit_tokens:Math.max(0,Math.round(Number($('five-limit').value)||0))},'Preferences saved');if(saved)$('settings').close();};
$('notification-test').onclick=()=>mutate('test-notification',{},'Notification requested');
document.addEventListener('keydown',event=>{if($('settings').open)return;if(event.key==='Escape'){query='';$('search').value='';storage.set('query','');$('search').blur();render();}else if(event.key==='/'&&!event.ctrlKey&&!event.metaKey&&!event.altKey&&!event.target.matches('input,select,textarea')){event.preventDefault();$('search').focus();}});
refresh();
setInterval(()=>{if(!document.hidden&&!$('settings').open)refresh();},5000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
