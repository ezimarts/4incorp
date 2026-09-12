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
  async function refresh() {
    const current = generation;
    const result = await api('/applications');
    if (current !== generation || !token) return;
    const tbody = document.getElementById('applications'); tbody.replaceChildren();
    for (const application of result.applications || []) {
      const row = document.createElement('tr');
      for (const key of ['reference','preferred_name','formation_state','status','customer_name']) {
        const cell = document.createElement('td'); cell.textContent = String(application[key] || '—'); row.append(cell);
      }
      tbody.append(row);
    }
    if (!tbody.children.length) {
      const row=document.createElement('tr'), cell=document.createElement('td');
      cell.colSpan=5;cell.textContent='No applications available.';row.append(cell);tbody.append(row);
    }
  }
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
    generation++;token=null;document.getElementById('applications').replaceChildren();
    document.getElementById('identity').textContent='';notice.textContent='';
    document.getElementById('dashboard').hidden=true;document.getElementById('login').hidden=false;
  });
})();
