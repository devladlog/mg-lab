// MG Lab #3 — create the demo data model with the Dataverse Web API.
// Run in the browser console of your DEV environment (https://<org>.crm.dynamics.com) while signed in.
// Creates: publisher "MG Lab" (mgl), solution MGLabDemo, tables mgl_department + mgl_projectrequest,
// columns, and the Department 1:N Project Request relationship. Then publishes.
(async () => {
  const api = location.origin + '/api/data/v9.2/';
  const base = { 'Accept': 'application/json', 'Content-Type': 'application/json; charset=utf-8', 'OData-MaxVersion': '4.0', 'OData-Version': '4.0' };
  const H = { ...base, 'MSCRM.SolutionUniqueName': 'MGLabDemo' };
  const L = (t) => ({ '@odata.type': 'Microsoft.Dynamics.CRM.Label', LocalizedLabels: [{ '@odata.type': 'Microsoft.Dynamics.CRM.LocalizedLabel', Label: t, LanguageCode: 1033 }] });
  const req = (v) => ({ Value: v, CanBeChanged: true, ManagedPropertyLogicalName: 'canmodifyrequirementlevelsettings' });
  const post = async (path, body, headers = H) => { const r = await fetch(api + path, { method: 'POST', headers, body: JSON.stringify(body) }); if (!r.ok) throw new Error(path + ': ' + await r.text()); return r; };

  const pub = await (await post('publishers', { uniquename: 'mglab', friendlyname: 'MG Lab', customizationprefix: 'mgl', customizationoptionvalueprefix: 10500 }, { ...base, Prefer: 'return=representation' })).json();
  await post('solutions', { uniquename: 'MGLabDemo', friendlyname: 'MG Lab Demo', version: '1.0.0.0', 'publisherid@odata.bind': `/publishers(${pub.publisherid})` }, base);

  const table = (schema, display, plural, ownership, primary) => post('EntityDefinitions', {
    '@odata.type': 'Microsoft.Dynamics.CRM.EntityMetadata', SchemaName: schema, DisplayName: L(display), DisplayCollectionName: L(plural),
    OwnershipType: ownership, HasActivities: false, HasNotes: ownership === 'UserOwned', IsActivity: false,
    Attributes: [{ '@odata.type': 'Microsoft.Dynamics.CRM.StringAttributeMetadata', SchemaName: primary.schema, IsPrimaryName: true, MaxLength: primary.len, FormatName: { Value: 'Text' }, RequiredLevel: req('ApplicationRequired'), DisplayName: L(primary.label) }]
  });
  await table('mgl_Department', 'Department', 'Departments', 'OrganizationOwned', { schema: 'mgl_Name', len: 100, label: 'Name' });
  await table('mgl_ProjectRequest', 'Project Request', 'Project Requests', 'UserOwned', { schema: 'mgl_Title', len: 200, label: 'Title' });

  const attr = (a) => post("EntityDefinitions(LogicalName='mgl_projectrequest')/Attributes", a);
  const choice = (schema, label, opts) => attr({ '@odata.type': 'Microsoft.Dynamics.CRM.PicklistAttributeMetadata', SchemaName: schema, DisplayName: L(label), RequiredLevel: req('None'),
    OptionSet: { '@odata.type': 'Microsoft.Dynamics.CRM.OptionSetMetadata', IsGlobal: false, OptionSetType: 'Picklist', Options: opts.map((t, i) => ({ Value: 105000000 + i, Label: L(t) })) } });
  await attr({ '@odata.type': 'Microsoft.Dynamics.CRM.StringAttributeMetadata', SchemaName: 'mgl_Requester', MaxLength: 100, FormatName: { Value: 'Text' }, RequiredLevel: req('None'), DisplayName: L('Requester') });
  await attr({ '@odata.type': 'Microsoft.Dynamics.CRM.MoneyAttributeMetadata', SchemaName: 'mgl_Budget', PrecisionSource: 2, MinValue: 0, MaxValue: 1000000000, RequiredLevel: req('None'), DisplayName: L('Budget') });
  await attr({ '@odata.type': 'Microsoft.Dynamics.CRM.DateTimeAttributeMetadata', SchemaName: 'mgl_DueDate', Format: 'DateOnly', DateTimeBehavior: { Value: 'DateOnly' }, RequiredLevel: req('None'), DisplayName: L('Due Date') });
  await choice('mgl_RequestStatus', 'Request Status', ['New', 'In review', 'Approved', 'Rejected', 'Done']);
  await choice('mgl_Priority', 'Priority', ['Low', 'Medium', 'High']);

  await post('RelationshipDefinitions', { '@odata.type': 'Microsoft.Dynamics.CRM.OneToManyRelationshipMetadata', SchemaName: 'mgl_department_projectrequest',
    ReferencedEntity: 'mgl_department', ReferencingEntity: 'mgl_projectrequest',
    CascadeConfiguration: { Assign: 'NoCascade', Delete: 'RemoveLink', Merge: 'NoCascade', Reparent: 'NoCascade', Share: 'NoCascade', Unshare: 'NoCascade' },
    Lookup: { '@odata.type': 'Microsoft.Dynamics.CRM.LookupAttributeMetadata', SchemaName: 'mgl_DepartmentId', DisplayName: L('Department'), RequiredLevel: req('None') } });

  await post('PublishXml', { ParameterXml: '<importexportxml><entities><entity>mgl_department</entity><entity>mgl_projectrequest</entity></entities></importexportxml>' }, base);
  console.log('MG Lab demo model created');
})();
