# MG Lab #7 — A Power Apps code component (PCF) in TypeScript

**Budget band** is a field component for currency columns on model-driven forms. It:

- understands `50k`, `1.2m`, `€ 12,500` and the **user's own number format** (`50,000.50` in en-US, `50 000,50` in pt-PT)
- shows which approval band the amount falls into **while you type** (standard / high / above the approval limit)
- uses the same `>= 50,000` threshold as the server-side plug-in from [episode 4](../04-dataverse-plugin-csharp/) —
  the control explains the rule, the plug-in still enforces it on save

| Path | What it is |
|---|---|
| [`src/BudgetBand/BudgetBand/ControlManifest.Input.xml`](src/BudgetBand/BudgetBand/ControlManifest.Input.xml) | Manifest: one bound `amount` property (Currency/Decimal), `highThreshold` and `approvalLimit` inputs |
| [`src/BudgetBand/BudgetBand/budget.ts`](src/BudgetBand/BudgetBand/budget.ts) | Pure logic: `parseAmount` and `classify` — no DOM, no PCF context |
| [`src/BudgetBand/BudgetBand/index.ts`](src/BudgetBand/BudgetBand/index.ts) | The control: wires the input box to `updateView` / `notifyOutputChanged` (only on blur) |
| [`src/BudgetBand/BudgetBand/__tests__/budget.test.ts`](src/BudgetBand/BudgetBand/__tests__/budget.test.ts) | 19 Jest tests |
| [`src/Solution`](src/Solution) | Solution project (`cdsproj`) that packages the component for release |

## Build, test, push

```bash
cd src/BudgetBand
npm ci
npm test                       # 19 passed
npm run build                  # ESLint + webpack

dotnet tool install --global Microsoft.PowerApps.CLI.Tool      # works on Linux and macOS too
pac auth create --deviceCode --environment https://<org>.crm.dynamics.com
pac pcf push --solution-unique-name <YourSolution>             # dev inner loop (~80 s)
```

Then in the form designer: select the currency field → **Components** → **+ Component** → *Get more components* →
**Budget band**, set the threshold and approval limit, **Save and publish**.

## Release

```bash
cd src/Solution
dotnet build -c Release        # bin/Release/Solution.zip  (PcfBuildMode=production in the pcfproj)
```

Import that zip through your normal pipeline (see [episode 1](../01-power-platform-alm/)). **Bump `version` in the
manifest on every change**, or the platform keeps serving the old bundle.

## What the real form taught us

- **Version 1.0.0 showed `$2,500.00` on a euro record.** `context.formatting.formatCurrency(value, precision)` doesn't
  know the record's currency; without the `symbol` argument it falls back to the user's default. Fix: display
  `context.parameters.amount.formatted` (the platform's value, which knows the currency) and use `formatDecimal` only
  as a placeholder. Unit tests can't catch this — they never see the platform.
- **`75.000` is 75 for an en-US user and 75,000 for a pt-PT user.** The parser reads the separators from
  `context.userSettings.numberFormattingInfo`, and both cases have a test.
- **A literal no-break space in a `.ts` file fails the build** (`no-irregular-whitespace`). Write it as ` `.

## References
- [Create your first component](https://learn.microsoft.com/power-apps/developer/component-framework/implementing-controls-using-typescript)
- [Create a model-driven app field component](https://learn.microsoft.com/power-apps/developer/component-framework/tutorial-create-model-driven-field-component)
- [Package a code component / `pac pcf push`](https://learn.microsoft.com/power-apps/developer/component-framework/import-custom-controls)
- [Code components ALM](https://learn.microsoft.com/power-apps/developer/component-framework/code-components-alm)
- [formatCurrency](https://learn.microsoft.com/power-apps/developer/component-framework/reference/formatting/formatcurrency)
