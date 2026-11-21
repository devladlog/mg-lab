// Invariants of the authorization design (portal/table-permissions.json), the Web API site settings, the Dataverse
// schema, the page script and the web template. These are the rules from Learn's Power Pages security guidance,
// checked as data so a careless change fails here and not in front of a customer.
import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const read = (p) => readFileSync(new URL(p, import.meta.url), 'utf8');
const perms = JSON.parse(read('../portal/table-permissions.json'));
const settings = Object.fromEntries(JSON.parse(read('../portal/site-settings.json')).settings.map((s) => [s.name, s.value]));
const table = JSON.parse(read('../dataverse/support-request-table.json'));
const S = require('../portal/web-files/support-requests.js');
const template = read('../portal/web-templates/my-requests.html');

function* walk(list, parent = null, depth = 0) {
  for (const p of list) {
    yield { ...p, parent, depth };
    if (p.children) yield* walk(p.children, p, depth + 1);
  }
}
const all = [...walk(perms.permissions)];

describe('table permissions', () => {
  test('no Global access anywhere', () => {
    for (const p of all) assert.notEqual(p.access, 'Global', p.name);
  });
  test('nothing is granted to the built-in roles: signing up is not authorization', () => {
    for (const p of all.filter((x) => x.roles)) {
      for (const r of p.roles) assert.ok(!perms.builtInRoles.includes(r), `${p.name} -> ${r}`);
      for (const r of p.roles) assert.ok(perms.webRoles.some((w) => w.name === r), `${r} is a defined web role`);
    }
  });
  test('top-level permissions have roles and an access type; children have a relationship and no own access type', () => {
    for (const p of all) {
      if (p.depth === 0) { assert.ok(p.roles?.length, p.name); assert.ok(p.access, p.name); }
      else { assert.ok(p.relationship, p.name); assert.equal(p.access, undefined, p.name); }
    }
  });
  test('the only Create on support requests has Contact access (the row must be the signed-in contact\'s)', () => {
    const creators = all.filter((p) => p.table === 'mgl_supportrequest' && p.privileges.includes('Create'));
    assert.equal(creators.length, 1);
    assert.equal(creators[0].access, 'Contact');
    assert.equal(creators[0].relationship, table.columns.find((c) => c.logicalName === 'mgl_contact').relationship);
  });
  test('company visibility goes through the contact\'s account, and is read-only', () => {
    const colleagues = all.find((p) => p.table === 'contact' && p.access === 'Account');
    assert.deepEqual(colleagues.privileges, ['Read']);
    const theirRequests = colleagues.children.find((c) => c.table === 'mgl_supportrequest');
    assert.ok(!theirRequests.privileges.some((x) => ['Create', 'Write', 'Delete'].includes(x)));
    assert.ok(!table.columns.some((c) => c.type === 'Lookup' && c.target === 'account'), 'no account lookup to spoof');
  });
  test('every permission that reads support requests has its own Document Location child (Learn: one per parent)', () => {
    for (const p of all.filter((x) => x.table === 'mgl_supportrequest')) {
      const docs = (p.children || []).find((c) => c.table === 'sharepointdocumentlocation');
      assert.ok(docs, `${p.name} needs a document location child`);
      assert.ok(docs.privileges.includes('Read'));
      assert.ok(p.privileges.includes('Read') && p.privileges.includes('AppendTo'), `${p.name}: Read + Append to`);
    }
  });
  test('uploads only where the parent allows Write, and colleagues\' documents are read-only', () => {
    for (const p of all.filter((x) => x.table === 'sharepointdocumentlocation')) {
      const uploads = p.privileges.includes('Create');
      if (uploads) assert.ok(p.parent.privileges.includes('Write'), p.name);
      if (p.parent.name === 'Requests raised by colleagues') assert.deepEqual(p.privileges, ['Read']);
    }
  });
  test('nobody can delete', () => {
    for (const p of all) assert.ok(!p.privileges.includes('Delete'), p.name);
  });
  test('the support page has a page permission for the custom role', () => {
    assert.deepEqual(perms.pagePermissions[0].roles, ['Customer contacts']);
  });
});

describe('Web API exposure', () => {
  test('enabled for the support request table only', () => {
    const enabled = Object.entries(settings).filter(([k, v]) => /^Webapi\/[^/]+\/enabled$/.test(k) && v === 'true').map(([k]) => k.split('/')[1]);
    assert.deepEqual(enabled, ['mgl_supportrequest']);
  });
  test('explicit columns, no deprecated wildcard, inner errors off', () => {
    const fields = settings['Webapi/mgl_supportrequest/fields'];
    assert.ok(!fields.includes('*'));
    assert.equal(settings['Webapi/error/innererror'], 'false');
  });
  test('the script uses exactly the exposed columns, and they all exist in the table', () => {
    const fields = settings['Webapi/mgl_supportrequest/fields'].split(',');
    assert.deepEqual([...S.COLUMNS].sort(), [...fields].sort());
    const schema = table.columns.map((c) => c.logicalName);
    for (const f of fields) assert.ok(schema.includes(f), f);
    const xml = S.buildListFetchXml();
    for (const [, a] of xml.matchAll(/attribute name="([^"]+)"/g)) assert.ok(fields.includes(a), `${a} is exposed`);
  });
  test('the script and the template use the schema\'s choice values and names', () => {
    const cat = Object.fromEntries(table.columns.find((c) => c.logicalName === 'mgl_category').options.map((o) => [o.value, o.label]));
    const st = Object.fromEntries(table.columns.find((c) => c.logicalName === 'mgl_status').options.map((o) => [o.value, o.label]));
    assert.deepEqual(S.CATEGORY, cat);
    assert.deepEqual(S.STATUS, st);
    for (const [v, label] of Object.entries(cat)) assert.ok(template.includes(`<option value="${v}">${label}</option>`), label);
    assert.equal(S.ENTITY_SET, table.entitySetName);
    const nav = table.columns.find((c) => c.logicalName === 'mgl_contact').navigationProperty;
    assert.ok(S.buildCreateBody({ title: 'Valid title', category: 100000000 }, '00000000-0000-0000-0000-000000000001')[`${nav}@odata.bind`]);
  });
});

describe('web template', () => {
  test('renders the section only for signed-in users, with the contact ID and the script', () => {
    assert.match(template, /\{% if user %\}/);
    assert.match(template, /data-contact-id="\{\{ user\.id \}\}"/);
    assert.match(template, /<script src="\/support-requests\.js"><\/script>/);
    assert.match(template, /ContosoSupport\.mount\(document, window\)/);
  });
  test('escapes the only Liquid values it prints', () => {
    for (const [, expr] of template.matchAll(/\{\{([^}]+)\}\}/g)) {
      if (expr.trim() === 'user.id') continue;
      assert.match(expr, /\| escape/, expr);
    }
  });
});
