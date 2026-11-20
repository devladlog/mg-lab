// MG Lab screen-recording mask.
// Paste/inject into a page BEFORE capturing. It rewrites identifying text on screen
// (tenant names, emails, people, environment hosts) to neutral demo values and keeps
// doing it as the page updates. Nothing is sent anywhere; reload the page to undo.
(() => {
  const RULES = [
    // emails first (most specific)
    [/[A-Za-z0-9._%+-]+@(devladlog|momentogalatico)\.(com|onmicrosoft\.com)/gi, 'admin@contoso.com'],
    // environment / tenant hosts
    [/mglab-(dev|test|prod)\.crm\d*\.dynamics\.com/gi, 'contoso-$1.crm.dynamics.com'],
    [/devladlog(-admin)?\.sharepoint\.com/gi, 'contoso$1.sharepoint.com'],
    [/devladlog\.onmicrosoft\.com/gi, 'contoso.onmicrosoft.com'],
    // GUIDs (tenant, app, environment ids)
    [/\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi, '00000000-0000-0000-0000-000000000000'],
    // people / org names
    [/vladimiro\s+lu[ií]s/gi, 'Alex Demo'],
    [/\bVL\b/g, 'AD'],
    [/momento\s+gal[aá]tico(\s+unipessoal\s+lda)?/gi, 'Contoso'],
    [/devladlog(\s*\(default\))?/gi, (m) => m.toLowerCase().includes('default') ? 'Contoso (default)' : 'contoso'],
  ];
  const fix = (s) => RULES.reduce((t, [re, to]) => t.replace(re, to), s);
  const walk = (root) => {
    const tw = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let n; while ((n = tw.nextNode())) { const v = fix(n.nodeValue); if (v !== n.nodeValue) n.nodeValue = v; }
    root.querySelectorAll?.('input,textarea').forEach((el) => { const v = fix(el.value || ''); if (v !== el.value) el.value = v; });
    root.querySelectorAll?.('[title],[aria-label],[placeholder]').forEach((el) => {
      for (const a of ['title', 'aria-label', 'placeholder']) { const o = el.getAttribute(a); if (o) { const v = fix(o); if (v !== o) el.setAttribute(a, v); } }
    });
    // profile pictures / avatars → neutral circle
    root.querySelectorAll?.('img[src*="profilephoto"],img[src*="avatars"],img[alt*="profile" i]').forEach((img) => { img.style.filter = 'blur(12px)'; });
    // tenant logos / avatars in the top bar (first ~60px of the page)
    root.querySelectorAll?.('img,svg image,[style*="background-image"]').forEach((el) => {
      const r = el.getBoundingClientRect?.(); if (r && r.top < 60 && r.height > 0 && r.height < 60) el.style.filter = 'blur(10px)';
    });
  };
  walk(document.body);
  if (window.__mgMaskObserver) window.__mgMaskObserver.disconnect();
  window.__mgMaskObserver = new MutationObserver((ms) => ms.forEach((m) => m.addedNodes.forEach((n) => n.nodeType === 1 ? walk(n) : n.nodeType === 3 && (n.nodeValue = fix(n.nodeValue)))));
  window.__mgMaskObserver.observe(document.body, { childList: true, subtree: true, characterData: false });
  document.title = fix(document.title);
  return 'masked';
})();
