/*
 * Contoso support portal: "Support requests" page script (Power Pages web file, plain ES2020, no libraries).
 * Reads and creates mgl_supportrequest rows through the Power Pages Web API (/_api). The browser never decides who
 * may see what: table permissions do, server-side. This script only displays what the server returns and sends a
 * new request that the server checks again (Contact access: the row must belong to the signed-in contact).
 * Also loadable in Node (module.exports) so the logic is unit-tested.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) { module.exports = factory(); } else { root.ContosoSupport = factory(); }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var ENTITY_SET = 'mgl_supportrequests';
  var CATEGORY = { 100000000: 'Billing', 100000001: 'Delivery', 100000002: 'Product', 100000003: 'Other' };
  var STATUS = { 100000000: 'New', 100000001: 'In progress', 100000002: 'Waiting for customer', 100000003: 'Resolved' };
  var FORMATTED = '@OData.Community.Display.V1.FormattedValue';
  var GUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  // Every column this script reads or writes. Must equal the Webapi/mgl_supportrequest/fields site setting.
  var COLUMNS = ['mgl_supportrequestid', 'mgl_reference', 'mgl_title', 'mgl_description', 'mgl_category', 'mgl_status', 'mgl_contact', 'createdon'];

  function PortalApiError(status, message) {
    this.name = 'PortalApiError'; this.status = status; this.message = message;
  }
  PortalApiError.prototype = Object.create(Error.prototype);

  /*
   * No filter on purpose: the server returns only rows the table permissions allow (my requests + my colleagues').
   * FetchXML instead of $filter/$expand: Learn lists a known issue with multi-level parent/child permissions on OData
   * GET requests and recommends FetchXML.
   */
  function buildListFetchXml(top) {
    var n = Math.min(Math.max(parseInt(top, 10) || 50, 1), 200);
    var attrs = ['mgl_supportrequestid', 'mgl_reference', 'mgl_title', 'mgl_category', 'mgl_status', 'mgl_contact', 'createdon'];
    return '<fetch top="' + n + '"><entity name="mgl_supportrequest">' +
      attrs.map(function (a) { return '<attribute name="' + a + '" />'; }).join('') +
      '<order attribute="createdon" descending="true" /></entity></fetch>';
  }

  function buildListUrl(baseUrl, top) {
    return (baseUrl || '') + '/_api/' + ENTITY_SET + '?fetchXml=' + encodeURIComponent(buildListFetchXml(top));
  }

  // FetchXML results omit null columns (Learn), so every property is optional here.
  function toRow(record, myContactId) {
    var cat = record.mgl_category, st = record.mgl_status;
    var contact = record._mgl_contact_value || null;
    return {
      id: record.mgl_supportrequestid,
      reference: record.mgl_reference || '',
      title: record.mgl_title || '',
      category: record['mgl_category' + FORMATTED] || (cat != null ? (CATEGORY[cat] || String(cat)) : ''),
      status: record['mgl_status' + FORMATTED] || (st != null ? (STATUS[st] || String(st)) : 'New'),
      raisedBy: record['_mgl_contact_value' + FORMATTED] || '',
      raisedByMe: !!(contact && myContactId && contact.toLowerCase() === String(myContactId).toLowerCase()),
      createdOn: record.createdon ? String(record.createdon).slice(0, 10) : ''
    };
  }

  function validateNewRequest(input) {
    var errors = [];
    var title = (input && input.title ? String(input.title) : '').trim();
    var description = (input && input.description ? String(input.description) : '').trim();
    var category = input ? Number(input.category) : NaN;
    if (title.length < 5) errors.push('Give the request a title of at least 5 characters.');
    if (title.length > 200) errors.push('The title can have at most 200 characters.');
    if (description.length > 2000) errors.push('The description can have at most 2000 characters.');
    if (!Object.prototype.hasOwnProperty.call(CATEGORY, category)) errors.push('Choose a category.');
    return errors;
  }

  function buildCreateBody(input, contactId) {
    if (!GUID.test(String(contactId || ''))) throw new PortalApiError(0, 'The page did not provide your contact ID; sign in again.');
    var body = {
      mgl_title: String(input.title).trim(),
      mgl_category: Number(input.category)
    };
    var description = (input.description ? String(input.description) : '').trim();
    if (description) body.mgl_description = description;
    // Single-valued navigation property = the lookup's schema name. The server refuses a contact that isn't the
    // signed-in user, because the only Create permission has Contact access.
    body['mgl_Contact@odata.bind'] = '/contacts(' + contactId + ')';
    return body;
  }

  function errorMessage(status, text) {
    var message = '';
    try { var parsed = JSON.parse(text); message = parsed && parsed.error && parsed.error.message ? parsed.error.message : ''; } catch (e) { message = ''; }
    if (status === 401 || status === 403) return 'You don’t have access to do that. If you think you should, contact your account manager at Contoso.';
    return message || ('The portal answered HTTP ' + status + '.');
  }

  /* Power Pages CSRF token: shell.getTokenDeferred() (jQuery Deferred) wrapped in a Promise. */
  function tokenFromShell(shell) {
    return new Promise(function (resolve, reject) {
      if (!shell || typeof shell.getTokenDeferred !== 'function') { reject(new PortalApiError(0, 'Not running on a Power Pages page.')); return; }
      shell.getTokenDeferred().done(resolve).fail(function () { reject(new PortalApiError(0, 'Could not get the request verification token.')); });
    });
  }

  function createClient(options) {
    var fetchImpl = options.fetch, getToken = options.getToken, baseUrl = options.baseUrl || '';
    if (typeof fetchImpl !== 'function' || typeof getToken !== 'function') throw new TypeError('fetch and getToken are required');

    function send(method, url, body) {
      return getToken().then(function (token) {
        var headers = {
          '__RequestVerificationToken': token,
          'Accept': 'application/json',
          'Prefer': 'odata.include-annotations="OData.Community.Display.V1.FormattedValue"'
        };
        if (body !== undefined) headers['Content-Type'] = 'application/json';
        return fetchImpl(url, { method: method, headers: headers, body: body === undefined ? undefined : JSON.stringify(body), credentials: 'same-origin' });
      }).then(function (res) {
        if (res.ok) return res;
        return res.text().then(function (t) { throw new PortalApiError(res.status, errorMessage(res.status, t)); });
      });
    }

    return {
      listRequests: function (myContactId, top) {
        return send('GET', buildListUrl(baseUrl, top)).then(function (res) { return res.json(); })
          .then(function (data) { return (data.value || []).map(function (r) { return toRow(r, myContactId); }); });
      },
      createRequest: function (input, contactId) {
        var errors = validateNewRequest(input);
        if (errors.length) return Promise.reject(new PortalApiError(400, errors.join(' ')));
        return send('POST', baseUrl + '/_api/' + ENTITY_SET, buildCreateBody(input, contactId))
          .then(function (res) { return res.headers.get('entityid'); });   // Learn: the new row's ID is in the entityid header
      }
    };
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function renderRows(rows) {
    if (!rows.length) return '<tr><td colspan="5">No support requests yet.</td></tr>';
    return rows.map(function (r) {
      return '<tr' + (r.raisedByMe ? ' class="mine"' : '') + '><td>' + escapeHtml(r.reference) + '</td><td><a href="/support/request/?id=' +
        encodeURIComponent(r.id) + '">' + escapeHtml(r.title) + '</a></td><td>' + escapeHtml(r.category) + '</td><td>' +
        escapeHtml(r.status) + '</td><td>' + escapeHtml(r.raisedBy) + ' · ' + escapeHtml(r.createdOn) + '</td></tr>';
    }).join('');
  }

  /* Browser glue for web-templates/my-requests.html. */
  function mount(doc, win) {
    var section = doc.getElementById('contoso-requests');
    if (!section) return null;
    var contactId = section.getAttribute('data-contact-id');
    var rowsEl = doc.getElementById('request-rows');
    var form = doc.getElementById('new-request');
    var message = doc.getElementById('request-message');
    var client = createClient({ fetch: win.fetch.bind(win), getToken: function () { return tokenFromShell(win.shell); } });
    var refresh = function () {
      return client.listRequests(contactId).then(function (rows) { rowsEl.innerHTML = renderRows(rows); })
        .catch(function (e) { message.textContent = e.message; });
    };
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var input = { title: form.elements.title.value, description: form.elements.description.value, category: form.elements.category.value };
      message.textContent = 'Sending…';
      return client.createRequest(input, contactId)
        .then(function () { form.reset(); message.textContent = 'Request sent. You can add documents from the request page.'; return refresh(); })
        .catch(function (e) { message.textContent = e.message; });
    });
    return refresh();
  }

  return {
    ENTITY_SET: ENTITY_SET, CATEGORY: CATEGORY, STATUS: STATUS, COLUMNS: COLUMNS, PortalApiError: PortalApiError,
    buildListFetchXml: buildListFetchXml, buildListUrl: buildListUrl, toRow: toRow, validateNewRequest: validateNewRequest,
    buildCreateBody: buildCreateBody, tokenFromShell: tokenFromShell, createClient: createClient,
    escapeHtml: escapeHtml, renderRows: renderRows, mount: mount
  };
});
