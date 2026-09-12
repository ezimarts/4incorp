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
  let overview = {applications:[],tasks:[],staff:[]};
  const statuses = ['Assigned','In progress','Blocked','Completed','Cancelled'];
  const done = t => ['Completed','Cancelled'].includes(t.status);
  const date = value => value ? new Date(value).toLocaleString() : '—';
  function cell(row, value) { const td=document.createElement('td');td.textContent=String(value || '—');row.append(td);return td; }
  function options(select, items, label) {
    const previous=select.value;select.replaceChildren();
    const blank=document.createElement('option');blank.value='';blank.textContent=label;select.append(blank);
    items.forEach(([value,text])=>{const o=document.createElement('option');o.value=value;o.textContent=text;select.append(o);});
    select.value=previous;
  }
  function renderOverview() {
    const {applications,tasks,staff}=overview;
    const search=document.getElementById('search').value.toLowerCase();
    const filter=document.getElementById('statusFilter').value;
    const counts = applications.reduce((result,a)=>{const s=a.status || 'Unknown';result[s]=(result[s]||0)+1;return result;},{});
    const metrics=document.getElementById('metrics');metrics.replaceChildren();
    [['Applications',applications.length],['Open tasks',tasks.filter(t=>!done(t)).length],['Overdue tasks',tasks.filter(t=>!done(t)&&new Date(t.due_at)<new Date()).length],['Staff members',staff.length]].forEach(([name,count])=>{
      const box=document.createElement('article');box.className='metric';const number=document.createElement('strong');number.textContent=count;
      const label=document.createElement('span');label.textContent=name;box.append(number,label);metrics.append(box);
    });
    const progress=document.getElementById('progress');progress.replaceChildren();
    Object.entries(counts).forEach(([status,count])=>{const label=document.createElement('label');label.textContent=`${status}: ${count}`;const bar=document.createElement('progress');bar.max=Math.max(applications.length,1);bar.value=count;label.append(bar);progress.append(label);});
    const tbody=document.getElementById('applications');tbody.replaceChildren();
    applications.filter(a=>(!filter||a.status===filter)&&[a.reference,a.preferred_name,a.customer_name,a.formation_state].join(' ').toLowerCase().includes(search))
      .sort((a,b)=>String(b.submitted_at).localeCompare(String(a.submitted_at))).forEach(a=>{
        const row=document.createElement('tr');
        [a.reference,a.preferred_name,a.formation_state,a.business_type,a.customer_name,a.status,a.assigned_staff_email,date(a.submitted_at),date(a.updated_at)].forEach(v=>cell(row,v));tbody.append(row);
      });
    if(!tbody.children.length){const row=document.createElement('tr');cell(row,'No matching applications.').colSpan=9;tbody.append(row);}
    const work=document.getElementById('staffWork');work.replaceChildren();
    staff.forEach(s=>{const assigned=tasks.filter(t=>t.staff_id===s.user_id);const row=document.createElement('tr');
      [s.name,s.email,assigned.filter(t=>!done(t)).length,assigned.filter(t=>t.status==='In progress').length,assigned.filter(t=>!done(t)&&new Date(t.due_at)<new Date()).length,assigned.filter(t=>t.status==='Completed').length].forEach(v=>cell(row,String(v)));work.append(row);});
    const rows=document.getElementById('taskRows');rows.replaceChildren();
    [...tasks].sort((a,b)=>String(a.due_at).localeCompare(String(b.due_at))).forEach(task=>{
      const row=document.createElement('tr');if(!done(task)&&new Date(task.due_at)<new Date())row.className='overdue';
      [task.title,task.reference,task.staff_email,date(task.starts_at),date(task.due_at)].forEach(v=>cell(row,v));
      const td=document.createElement('td'),select=document.createElement('select');select.setAttribute('aria-label',`Status for ${task.title}`);
      options(select,statuses.map(s=>[s,s]),'Select status');select.value=task.status;
      select.addEventListener('change',async()=>{const selected=select.value;select.disabled=true;const current=generation;
        try{await api(`/admin/tasks/${encodeURIComponent(task.task_id)}`,{method:'PATCH',body:JSON.stringify({status:selected,version:task.version})});if(current===generation&&token)await refresh();}
        catch(error){notice.textContent=error.message;select.value=task.status;}finally{select.disabled=false;}});
      td.append(select);row.append(td);cell(row,date(task.updated_at));rows.append(row);
    });
    if(!rows.children.length){const row=document.createElement('tr');cell(row,'No tasks assigned yet.').colSpan=7;rows.append(row);}
  }
  async function refresh() {
    const current=generation;
    const result=await api('/admin/overview');if(current!==generation||!token)return;
    overview=result;
    options(document.getElementById('statusFilter'),[...new Set(result.applications.map(a=>a.status))].sort().map(s=>[s,s]),'All statuses');
    options(document.getElementById('taskApplication'),result.applications.map(a=>[a.reference,`${a.reference} — ${a.preferred_name}`]),'Choose application');
    options(document.getElementById('taskStaff'),result.staff.map(s=>[s.user_id,`${s.name} — ${s.email}`]),'Choose staff member');
    document.getElementById('updated').textContent=`Last refreshed ${date(result.fetched_at)}. Dates shown in ${Intl.DateTimeFormat().resolvedOptions().timeZone}.`;
    renderOverview();
  }
  document.getElementById('search').addEventListener('input',renderOverview);
  document.getElementById('statusFilter').addEventListener('change',renderOverview);
  document.getElementById('taskForm').addEventListener('submit',async event=>{
    event.preventDefault();const form=event.currentTarget;if(!form.reportValidity())return;
    const submit=form.querySelector('button');submit.disabled=true;notice.textContent='';
    const values=Object.fromEntries(new FormData(form));const current=generation;
    try {
      const start=new Date(values.starts_at),due=new Date(values.due_at);
      if(due<start)throw new Error('Due date must be at or after the start date.');
      await api('/admin/tasks',{method:'POST',body:JSON.stringify({...values,starts_at:start.toISOString(),due_at:due.toISOString()})});
      if(current!==generation||!token)return;
      form.reset();await refresh();notice.textContent='Task assigned successfully.';
    }catch(error){notice.textContent=error.message;}finally{submit.disabled=false;}
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
    generation++;token=null;overview={applications:[],tasks:[],staff:[]};renderOverview();document.getElementById('taskForm').reset();document.getElementById('applications').replaceChildren();
    document.getElementById('identity').textContent='';notice.textContent='';
    document.getElementById('dashboard').hidden=true;document.getElementById('login').hidden=false;
  });
})();
