(() => {
  'use strict';
  const role = document.body.dataset.role;
  const base = String(window.FOURINCORP_CONFIG?.apiBaseUrl || '').replace(/\/$/, '');
  const form = document.getElementById('teamLogin');
  const notice = document.getElementById('notice');
  let token = null;
  let generation = 0;
  async function api(path, options = {}) {
    if (!base) throw new Error('Portal configuration is unavailable.');
    const response = await fetch(base + path, {...options, headers:{'Content-Type':'application/json', ...(token ? {Authorization:`Bearer ${token}`} : {})}});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.message || `Request failed (${response.status}).`);
    return data;
  }
  function groupsFromToken(value) {
    // Display gating only. API Gateway verifies JWTs and the backend enforces roles.
    const part = value.split('.')[1].replace(/-/g,'+').replace(/_/g,'/');
    const claims = JSON.parse(atob(part.padEnd(Math.ceil(part.length/4)*4, '=')));
    const groups = claims['cognito:groups'] || [];
    return (Array.isArray(groups) ? groups : String(groups).replace(/[\[\]"]/g,'').split(',')).map(g=>g.trim().toLowerCase());
  }
  let overview={tasks:[],applications:[],permissions:[],application_statuses:[]};
  const closed=t=>['Completed','Cancelled'].includes(t.status);
  const date=value=>value?new Date(value).toLocaleString():'—';
  const progress=t=>t.status==='Completed'?100:Number(t.progress||0);
  function td(row,value){const cell=document.createElement('td');cell.textContent=String(value??'—');row.append(cell);return cell;}
  function render() {
    const tasks=overview.tasks,query=document.getElementById('taskSearch').value.toLowerCase(),filter=document.getElementById('taskFilter').value;
    const metrics=document.getElementById('metrics');metrics.replaceChildren();
    [['My tasks',tasks.length],['In progress',tasks.filter(t=>t.status==='In progress').length],['Blocked',tasks.filter(t=>t.status==='Blocked').length],['Overdue',tasks.filter(t=>!closed(t)&&new Date(t.due_at)<new Date()).length],['Completed',tasks.filter(t=>t.status==='Completed').length]].forEach(([label,count])=>{
      const box=document.createElement('article'),number=document.createElement('strong'),text=document.createElement('span');box.className='metric';number.textContent=count;text.textContent=label;box.append(number,text);metrics.append(box);
    });
    const rows=document.getElementById('taskRows');rows.replaceChildren();
    [...tasks].filter(t=>(!filter||t.status===filter)&&`${t.title} ${t.reference}`.toLowerCase().includes(query)).sort((a,b)=>String(a.due_at).localeCompare(String(b.due_at))).forEach(task=>{
      const row=document.createElement('tr');if(!closed(task)&&new Date(task.due_at)<new Date())row.className='overdue';
      td(row,task.title);td(row,task.reference);td(row,task.status);
      const cell=td(row,`${progress(task)}% `),bar=document.createElement('progress');bar.max=100;bar.value=progress(task);cell.append(bar);
      td(row,date(task.starts_at));td(row,date(task.due_at));td(row,task.work_note||'');td(row,date(task.updated_at));
      const action=td(row,''),button=document.createElement('button');button.textContent=closed(task)?'Closed':'Update';button.disabled=closed(task);
      button.addEventListener('click',()=>{
        const editor=document.getElementById('taskEditor');editor.hidden=false;
        editor.elements.task_id.value=task.task_id;editor.elements.version.value=task.version;
        editor.elements.status.value=task.status;editor.elements.progress.value=progress(task);editor.elements.note.value=task.work_note||'';
        document.getElementById('editingTitle').textContent=`Update: ${task.title}`;editor.scrollIntoView({behavior:'smooth'});
      });action.append(button);rows.append(row);
    });
    if(!rows.children.length){const row=document.createElement('tr');td(row,'No matching assigned tasks.').colSpan=9;rows.append(row);}
    const apps=document.getElementById('applications');apps.replaceChildren();
    overview.applications.forEach(a=>{
      const row=document.createElement('tr');[a.reference,a.preferred_name,a.formation_state,a.customer_name].forEach(v=>td(row,v));
      const status=td(row,''),select=document.createElement('select');select.setAttribute('aria-label',`Filing status for ${a.reference}`);
      [...new Set([a.status,...overview.application_statuses])].forEach(s=>{const o=document.createElement('option');o.value=s;o.textContent=s;select.append(o);});select.value=a.status;
      const save=document.createElement('button');save.textContent='Save status';save.addEventListener('click',async()=>{
        save.disabled=true;const current=generation;
        try{await api(`/applications/${encodeURIComponent(a.reference)}`,{method:'PATCH',body:JSON.stringify({status:select.value})});if(current===generation&&token)await refresh();}
        catch(error){notice.textContent=error.message;}finally{save.disabled=false;}
      });status.append(select,save);td(row,date(a.updated_at));apps.append(row);
    });
    if(!apps.children.length){const row=document.createElement('tr');td(row,'No active assigned applications.').colSpan=6;apps.append(row);}
    const permissions=document.getElementById('permissions');permissions.replaceChildren();
    overview.permissions.forEach(p=>{const row=document.createElement('tr');td(row,p.action);td(row,p.allowed?'Allowed':'Admin only');td(row,p.scope);permissions.append(row);});
  }
  async function refresh(){
    const current=generation,result=await api('/staff/overview');if(current!==generation||!token)return;
    overview=result;render();document.getElementById('updated').textContent=`Last refreshed ${date(result.fetched_at)} · ${Intl.DateTimeFormat().resolvedOptions().timeZone}`;
  }
  document.getElementById('taskSearch').addEventListener('input',render);
  document.getElementById('taskFilter').addEventListener('change',render);
  document.getElementById('closeEditor').addEventListener('click',()=>document.getElementById('taskEditor').hidden=true);
  const editor=document.getElementById('taskEditor');
  editor.elements.status.addEventListener('change',()=>{
    if(editor.elements.status.value==='Completed')editor.elements.progress.value=100;
    else if(editor.elements.status.value==='Assigned')editor.elements.progress.value=0;
  });
  editor.addEventListener('submit',async event=>{
    event.preventDefault();if(!editor.reportValidity())return;
    const save=editor.querySelector('[type="submit"]');save.disabled=true;const current=generation;
    const values=Object.fromEntries(new FormData(editor));
    try{await api(`/staff/tasks/${encodeURIComponent(values.task_id)}`,{method:'PATCH',body:JSON.stringify({status:values.status,progress:Number(values.progress),note:values.note,version:Number(values.version)})});
      if(current!==generation||!token)return;
      editor.hidden=true;editor.reset();await refresh();notice.textContent='Task update saved.';
    }catch(error){notice.textContent=error.message;}finally{save.disabled=false;}
  });
  form.addEventListener('submit', async event => {
    event.preventDefault(); if (!form.reportValidity()) return;
    const button=form.querySelector('button');button.disabled=true;notice.textContent='';token=null;
    try {
      const result=await api('/auth/login',{method:'POST',body:JSON.stringify({email:form.elements.email.value,password:form.elements.password.value})});
      form.elements.password.value='';
      if (!result.id_token || !groupsFromToken(result.id_token).includes(role)) throw new Error(`Your account needs membership in the ${role} Cognito group to use this portal.`);
      token=result.id_token;
      await refresh();
      document.getElementById('identity').textContent=result.user?.email || form.elements.email.value;
      document.getElementById('login').hidden=true;document.getElementById('dashboard').hidden=false;
    } catch(error) {token=null;notice.textContent=error.message;}
    finally {button.disabled=false;}
  });
  document.getElementById('refresh').addEventListener('click',async()=>{
    notice.textContent='';try{await refresh();}catch(error){notice.textContent=error.message;}
  });
  document.getElementById('logout').addEventListener('click',()=>{
    generation++;token=null;overview={tasks:[],applications:[],permissions:[],application_statuses:[]};render();editor.hidden=true;editor.reset();document.getElementById('applications').replaceChildren();
    document.getElementById('identity').textContent='';notice.textContent='';
    document.getElementById('dashboard').hidden=true;document.getElementById('login').hidden=false;
  });
})();
