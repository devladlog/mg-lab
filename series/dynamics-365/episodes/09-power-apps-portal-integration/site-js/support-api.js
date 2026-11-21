/* Store support pages: cases through the Power Pages (portals) Web API.
 * Runs in a page of a Power Pages site (global `shell` object, same-origin cookies) and in Node for the tests.
 * Learn: every Web API call must carry the CSRF token (header __RequestVerificationToken); tables are addressed by
 * EntitySetName under /_api; create returns the new id in the `entityid` response header; always send $select.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory;
  else root.mgSupport = factory(root);
})(typeof self !== "undefined" ? self : this, function (env) {
  var CASE_COLUMNS = ["title", "description", "prioritycode", "createdon", "statecode", "ticketnumber"];

  function getToken() {
    return new Promise(function (resolve, reject) {
      env.shell.getTokenDeferred().done(resolve).fail(reject);   // the call Learn's safeAjax wrapper uses
    });
  }

  function casesUrl(opts) {
    opts = opts || {};
    var q = ["$select=" + CASE_COLUMNS.join(",")];
    if (opts.top) q.push("$top=" + Number(opts.top));
    if (opts.openOnly) q.push("$filter=statecode eq 0");
    q.push("$orderby=createdon desc");
    return "/_api/incidents?" + q.join("&");
  }

  function parseError(status, text) {
    var msg = text;
    try { var j = JSON.parse(text); msg = (j.error && j.error.message) || msg; } catch (e) { /* not JSON */ }
    var err = new Error("Web API " + status + ": " + msg);
    err.status = status;
    return err;
  }

  function safeFetch(url, init) {
    init = init || {};
    return getToken().then(function (token) {
      var headers = Object.assign({ Accept: "application/json" }, init.headers || {});
      headers["__RequestVerificationToken"] = token;
      if (init.body) headers["Content-Type"] = "application/json";
      return env.fetch(url, Object.assign({}, init, { headers: headers, credentials: "same-origin" }));
    }).then(function (res) {
      if (res.ok) return res;
      return res.text().then(function (t) { throw parseError(res.status, t); });
    });
  }

  function listCases(opts) {
    return safeFetch(casesUrl(opts)).then(function (res) { return res.json(); })
      .then(function (data) { return data.value; });
  }

  function createCase(c) {
    if (!c || !c.title || !c.contactId) return Promise.reject(new Error("title and contactId are required"));
    if (c.title.length > 200) return Promise.reject(new Error("title is limited to 200 characters"));
    var body = { title: c.title, description: c.description || "", prioritycode: c.priority || 2,
                 "customerid_contact@odata.bind": "/contacts(" + c.contactId + ")" };
    return safeFetch("/_api/incidents", { method: "POST", body: JSON.stringify(body) })
      .then(function (res) { return res.headers.get("entityid"); });
  }

  return { CASE_COLUMNS: CASE_COLUMNS, casesUrl: casesUrl, parseError: parseError, safeFetch: safeFetch,
           listCases: listCases, createCase: createCase };
});
