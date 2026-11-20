# Recording real demos (masked)

MG Lab episodes show **real** Power Platform, SharePoint, Azure and GitHub screens from dedicated demo
environments. Nothing that identifies the real tenant may appear on screen.

## 1. Mask at the source
Before every capture, inject [`pipeline/mask.js`](../pipeline/mask.js) into the page (DevTools console or the
recording automation). It rewrites, live, as the page updates:

| Real | Shown as |
|---|---|
| tenant / org names | `Contoso` |
| user names | `Alex Demo` |
| emails | `admin@contoso.com` |
| environment & SharePoint hosts | `contoso-dev.crm.dynamics.com`, `contoso.sharepoint.com` |
| GUIDs (tenant, app, environment IDs) | `00000000-0000-0000-0000-000000000000` |
| avatars / tenant logos in the top bar | blurred |

Captures are taken of the page viewport only, so the browser address bar is never recorded.

## 2. Use fictional data only
Demo lists, tables and records contain invented names (Alex Martins, Sam Rivera, …) and invented projects.

## 3. Check before publishing
Every captured frame is reviewed before it goes into a video. Screens stay out of the public repo
(`episodes/*/screens/` is git-ignored) and are only kept in the local build folder.

## 4. Use in a script
```yaml
- id: environments-real
  type: screen
  heading: "Three real environments"
  image: screens/ppac-environments.jpg   # relative to the episode folder
  crop: [240, 40, 1328, 380]             # optional, source pixels
  highlight: [30, 200, 1270, 110]        # optional yellow box, cropped-source pixels
  bar: "Power Platform admin center"     # label in the neutral browser frame
  narration: >
    ...
```
