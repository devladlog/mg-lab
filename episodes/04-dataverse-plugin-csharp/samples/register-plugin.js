// MG Lab #4 — register MGLab.Plugins with the Dataverse Web API (no Plugin Registration Tool needed).
// Run in the browser console of your DEV environment (https://<org>.crm.dynamics.com) while signed in.
// 1) Pick the signed MGLab.Plugins.dll when prompted. 2) Everything is added to the MGLabDemo solution.
(async () => {
  const api = location.origin + '/api/data/v9.2/';
  const H = { 'Accept': 'application/json', 'Content-Type': 'application/json; charset=utf-8', 'OData-MaxVersion': '4.0',
              'OData-Version': '4.0', 'MSCRM.SolutionUniqueName': 'MGLabDemo', 'Prefer': 'return=representation' };
  const get = async (p) => (await (await fetch(api + p, { headers: H })).json()).value;
  const post = async (p, b) => { const r = await fetch(api + p, { method: 'POST', headers: H, body: JSON.stringify(b) });
    const j = await r.json(); if (!r.ok) throw new Error(`${p}: ${j.error?.message}`); return j; };

  const file = await new Promise((ok) => { const i = Object.assign(document.createElement('input'), { type: 'file', accept: '.dll' });
    i.onchange = () => ok(i.files[0]); i.click(); });
  const bytes = new Uint8Array(await file.arrayBuffer());
  const content = btoa(Array.from(bytes, (b) => String.fromCharCode(b)).join(''));

  // 1. Assembly (sandbox isolation, stored in the database)
  const asm = await post('pluginassemblies', { name: 'MGLab.Plugins', content, isolationmode: 2, sourcetype: 0 });

  // 2. Plugin type
  const type = await post('plugintypes', { typename: 'MGLab.Plugins.ProjectRequestValidationPlugin',
    name: 'MGLab.Plugins.ProjectRequestValidationPlugin', friendlyname: 'Project request validation',
    'pluginassemblyid@odata.bind': `/pluginassemblies(${asm.pluginassemblyid})` });

  // 3. Steps: Create + Update, pre-operation (20), synchronous (mode 0)
  const columns = 'mgl_budget,mgl_priority,mgl_requeststatus,mgl_departmentid,mgl_duedate';
  for (const message of ['Create', 'Update']) {
    const [msg] = await get(`sdkmessages?$select=sdkmessageid&$filter=name eq '${message}'`);
    const [filter] = await get(`sdkmessagefilters?$select=sdkmessagefilterid&$filter=primaryobjecttypecode eq 'mgl_projectrequest' and _sdkmessageid_value eq ${msg.sdkmessageid}`);
    const step = await post('sdkmessageprocessingsteps', {
      name: `MGLab.Plugins.ProjectRequestValidationPlugin: ${message} of mgl_projectrequest`,
      mode: 0, rank: 1, stage: 20, supporteddeployment: 0,
      ...(message === 'Update' ? { filteringattributes: columns } : {}),
      'eventhandler_plugintype@odata.bind': `/plugintypes(${type.plugintypeid})`,
      'sdkmessageid@odata.bind': `/sdkmessages(${msg.sdkmessageid})`,
      'sdkmessagefilterid@odata.bind': `/sdkmessagefilters(${filter.sdkmessagefilterid})` });

    // 4. Pre-image on Update with the columns the rules read
    if (message === 'Update') await post('sdkmessageprocessingstepimages', { name: 'PreImage', entityalias: 'PreImage',
      imagetype: 0, messagepropertyname: 'Target', attributes: columns,
      'sdkmessageprocessingstepid@odata.bind': `/sdkmessageprocessingsteps(${step.sdkmessageprocessingstepid})` });
  }
  console.log('MGLab.Plugins registered', asm.version);
})();

// To update later: PATCH pluginassemblies(<id>) with { content: <new base64> } — bump the assembly version first.
// Plugin trace log (dev only = All): PATCH organizations(<id>) { plugintracelogsetting: 2 }  (0 Off, 1 Exception, 2 All)
