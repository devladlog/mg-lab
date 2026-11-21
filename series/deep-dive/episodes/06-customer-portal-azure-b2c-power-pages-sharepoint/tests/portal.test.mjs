// Unit tests for portal/web-files/support-requests.js (node --test). The Web API is replaced by a recording fetch.
import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const S = require('../portal/web-files/support-requests.js');
const ME = '00000000-0000-0000-0000-00000000c001';
const COLLEAGUE = '00000000-0000-0000-0000-00000000c002';

function fakeFetch(responder) {
  const calls = [];
  const fn = async (url, init) => {
    calls.push({ url, init });
    const r = await responder(url, init);
    return {
      ok: r.status >= 200 && r.status < 300,
      status: r.status,
      headers: { get: (h) => (r.headers || {})[h.toLowerCase()] ?? null },
      json: async () => r.body,
      text: async () => (typeof r.body === 'string' ? r.body : JSON.stringify(r.body ?? ''))
    };
  };
  fn.calls = calls;
  return fn;
}

describe('list query', () => {
  test('uses FetchXML on the entity set, with no filter (table permissions decide)', () => {
    const url = S.buildListUrl('', 25);
    assert.ok(url.startsWith('/_api/mgl_supportrequests?fetchXml='));
    const xml = decodeURIComponent(url.split('fetchXml=')[1]);
    assert.match(xml, /^<fetch top="25"><entity name="mgl_supportrequest">/);
    assert.doesNotMatch(xml, /<filter/);
    assert.match(xml, /<order attribute="createdon" descending="true" \/>/);
  });
  test('clamps the page size', () => {
    assert.match(S.buildListFetchXml(5000), /top="200"/);
    assert.match(S.buildListFetchXml('x'), /top="50"/);
  });
  test('maps records, including the nulls FetchXML leaves out', () => {
    const row = S.toRow({ mgl_supportrequestid: 'a', mgl_title: 'Invoice missing', mgl_category: 100000000 }, ME);
    assert.deepEqual(row, { id: 'a', reference: '', title: 'Invoice missing', category: 'Billing', status: 'New',
      raisedBy: '', raisedByMe: false, createdOn: '' });
  });
  test('prefers the formatted value annotation and marks my own requests', () => {
    const row = S.toRow({
      mgl_supportrequestid: 'b', mgl_reference: 'SR-00012', mgl_title: 'Late delivery', mgl_status: 100000001,
      'mgl_status@OData.Community.Display.V1.FormattedValue': 'Em curso', _mgl_contact_value: ME.toUpperCase(),
      '_mgl_contact_value@OData.Community.Display.V1.FormattedValue': 'Riley Demo', createdon: '2026-11-21T10:15:00Z'
    }, ME);
    assert.equal(row.status, 'Em curso');
    assert.equal(row.raisedByMe, true);
    assert.equal(row.raisedBy, 'Riley Demo');
    assert.equal(row.createdOn, '2026-11-21');
  });
});

describe('new request', () => {
  test('validation reports every problem', () => {
    assert.deepEqual(S.validateNewRequest({ title: 'Hi', category: '7' }),
      ['Give the request a title of at least 5 characters.', 'Choose a category.']);
    assert.deepEqual(S.validateNewRequest({ title: 'Wrong invoice amount', category: '100000000' }), []);
    assert.equal(S.validateNewRequest({ title: 'x'.repeat(201), category: 100000003, description: 'y'.repeat(2001) }).length, 2);
  });
  test('binds the request to the signed-in contact and never to an account', () => {
    const body = S.buildCreateBody({ title: '  Wrong invoice amount ', category: '100000000', description: '' }, ME);
    assert.deepEqual(body, { mgl_title: 'Wrong invoice amount', mgl_category: 100000000, 'mgl_Contact@odata.bind': `/contacts(${ME})` });
    assert.ok(!Object.keys(body).some((k) => /account/i.test(k)));
  });
  test('refuses to build a request without a valid contact ID', () => {
    assert.throws(() => S.buildCreateBody({ title: 'Valid title', category: 100000000 }, '') , /contact ID/);
    assert.throws(() => S.buildCreateBody({ title: 'Valid title', category: 100000000 }, "x') or 1 eq 1") , /contact ID/);
  });
});

describe('Web API client', () => {
  const token = async () => 'csrf-123';

  test('sends the CSRF token on every call and returns rows', async () => {
    const f = fakeFetch(async () => ({ status: 200, body: { value: [
      { mgl_supportrequestid: 'r1', mgl_title: 'Mine', _mgl_contact_value: ME },
      { mgl_supportrequestid: 'r2', mgl_title: 'Colleague', _mgl_contact_value: COLLEAGUE }] } }));
    const rows = await S.createClient({ fetch: f, getToken: token }).listRequests(ME);
    assert.equal(rows.length, 2);
    assert.deepEqual(rows.map((r) => r.raisedByMe), [true, false]);
    assert.equal(f.calls[0].init.headers.__RequestVerificationToken, 'csrf-123');
    assert.equal(f.calls[0].init.method, 'GET');
    assert.match(f.calls[0].init.headers.Prefer, /FormattedValue/);
  });
  test('creates a request and returns the entityid header', async () => {
    const f = fakeFetch(async () => ({ status: 204, headers: { entityid: '00000000-0000-0000-0000-0000000000r1' } }));
    const id = await S.createClient({ fetch: f, getToken: token }).createRequest({ title: 'Wrong invoice amount', category: 100000000 }, ME);
    assert.equal(id, '00000000-0000-0000-0000-0000000000r1');
    assert.equal(f.calls[0].url, '/_api/mgl_supportrequests');
    assert.equal(f.calls[0].init.method, 'POST');
    assert.equal(f.calls[0].init.headers['Content-Type'], 'application/json');
    assert.equal(JSON.parse(f.calls[0].init.body)['mgl_Contact@odata.bind'], `/contacts(${ME})`);
  });
  test('does not call the server with an invalid request', async () => {
    const f = fakeFetch(async () => { throw new Error('should not be called'); });
    await assert.rejects(S.createClient({ fetch: f, getToken: token }).createRequest({ title: 'x', category: 1 }, ME), (e) => e.status === 400);
    assert.equal(f.calls.length, 0);
  });
  test('turns 403 into a plain message and other errors into the server message', async () => {
    const forbidden = fakeFetch(async () => ({ status: 403, body: { error: { code: '90040120', message: 'Permission denied' } } }));
    await assert.rejects(S.createClient({ fetch: forbidden, getToken: token }).listRequests(ME), (e) => e.status === 403 && /don.t have access/.test(e.message));
    const bad = fakeFetch(async () => ({ status: 400, body: { error: { message: 'Attribute mgl_secret is not enabled for Web Api.' } } }));
    await assert.rejects(S.createClient({ fetch: bad, getToken: token }).listRequests(ME), /not enabled for Web Api/);
  });
  test('wraps shell.getTokenDeferred() (jQuery Deferred) in a Promise', async () => {
    const shell = { getTokenDeferred: () => ({ done(cb) { cb('tok'); return this; }, fail() { return this; } }) };
    assert.equal(await S.tokenFromShell(shell), 'tok');
    await assert.rejects(S.tokenFromShell(undefined), /Power Pages/);
  });
});

describe('rendering', () => {
  test('escapes everything that came from Dataverse', () => {
    const html = S.renderRows([{ id: 'a"b', reference: 'SR-1', title: '<img src=x onerror=alert(1)>', category: 'Billing', status: 'New', raisedBy: 'O\'Brien & Co', createdOn: '2026-11-21', raisedByMe: true }]);
    assert.doesNotMatch(html, /<img/);
    assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/);
    assert.match(html, /O&#39;Brien &amp; Co/);
    assert.match(html, /id=a%22b/);
    assert.match(html, /class="mine"/);
  });
  test('says so when there is nothing to show', () => {
    assert.match(S.renderRows([]), /No support requests yet/);
  });
});

describe('page glue', () => {
  function fakeDom(contactId) {
    const listeners = {};
    const el = (attrs = {}) => ({ innerHTML: '', textContent: '', getAttribute: (n) => attrs[n], addEventListener: (t, fn) => { listeners[t] = fn; } });
    const form = el();
    form.elements = { title: { value: 'Pallet arrived damaged' }, description: { value: 'Photos follow' }, category: { value: '100000001' } };
    form.reset = () => { form.wasReset = true; };
    const nodes = { 'contoso-requests': el({ 'data-contact-id': contactId }), 'request-rows': el(), 'new-request': form, 'request-message': el() };
    return { doc: { getElementById: (id) => nodes[id] || null }, nodes, listeners };
  }
  test('loads the list, submits the form and reloads', async () => {
    const { doc, nodes, listeners } = fakeDom(ME);
    let created = 0;
    const win = {
      shell: { getTokenDeferred: () => ({ done(cb) { cb('tok'); return this; }, fail() { return this; } }) },
      fetch: fakeFetch(async (url, init) => {
        if (init.method === 'POST') { created++; return { status: 204, headers: { entityid: 'x' } }; }
        return { status: 200, body: { value: created ? [{ mgl_supportrequestid: 'n1', mgl_title: 'Pallet arrived damaged', _mgl_contact_value: ME }] : [] } };
      })
    };
    win.fetch.bind = () => win.fetch;
    await S.mount(doc, win);
    assert.match(nodes['request-rows'].innerHTML, /No support requests yet/);
    await listeners.submit({ preventDefault() {} });
    assert.equal(created, 1);
    assert.equal(nodes['new-request'].wasReset, true);
    assert.match(nodes['request-rows'].innerHTML, /Pallet arrived damaged/);
    assert.match(nodes['request-message'].textContent, /Request sent/);
  });
  test('does nothing on a page without the section', () => {
    assert.equal(S.mount({ getElementById: () => null }, {}), null);
  });
});
