import * as vscode from "vscode";
import type { GitExtension, Repository } from "./git";
import { buildHeader, normaliseTypes, replaceHeader, validateScope, validateSubject } from "./commitRules";

export function activate(context: vscode.ExtensionContext): void {
  // No activationEvents needed: since VS Code 1.74 a contributed command activates the extension.
  context.subscriptions.push(
    vscode.commands.registerCommand("mgCommit.compose", (arg?: unknown) => compose(rootUriOf(arg))),
  );
}

export function deactivate(): void {}

/** From the Source Control title bar VS Code passes the source control; from the palette, nothing. */
function rootUriOf(arg: unknown): vscode.Uri | undefined {
  const uri = (arg as { rootUri?: unknown } | undefined)?.rootUri;
  return uri instanceof vscode.Uri ? uri : undefined;
}

async function compose(rootUri?: vscode.Uri): Promise<void> {
  const repo = await pickRepository(rootUri);
  if (!repo) return;

  const config = vscode.workspace.getConfiguration("mgCommit", repo.rootUri);
  const types = normaliseTypes(config.get("types"));
  const scopes = config.get<string[]>("scopes", []);

  const type = await vscode.window.showQuickPick(types, { title: "Commit type (1/4)", placeHolder: "feat, fix, docs..." });
  if (!type) return;

  const scope = await pickScope(scopes);
  if (scope === undefined) return;

  const breaking = await vscode.window.showQuickPick(["No", "Yes: breaking change (adds !)"], { title: "Breaking change? (3/4)" });
  if (!breaking) return;
  const isBreaking = breaking.startsWith("Yes");

  const subject = await vscode.window.showInputBox({
    title: "Subject (4/4)",
    prompt: "Imperative, lower case, no period: add paging to the orders endpoint",
    validateInput: (value) => validateSubject({ type, scope, breaking: isBreaking, subject: value }),
  });
  if (subject === undefined) return;

  const header = buildHeader({ type, scope, breaking: isBreaking, subject });
  repo.inputBox.value = replaceHeader(repo.inputBox.value, header);
  await vscode.commands.executeCommand("workbench.view.scm");
}

async function pickScope(scopes: string[]): Promise<string | undefined> {
  const NONE = "(no scope)";
  const OTHER = "Other...";
  const choice = await vscode.window.showQuickPick([NONE, ...scopes, OTHER], { title: "Scope (2/4)" });
  if (choice === undefined) return undefined;
  if (choice === NONE) return "";
  if (choice !== OTHER) return choice;
  return vscode.window.showInputBox({ title: "Scope (2/4)", prompt: "e.g. api, orders/export", validateInput: validateScope });
}

async function pickRepository(rootUri?: vscode.Uri): Promise<Repository | undefined> {
  const ext = vscode.extensions.getExtension<GitExtension>("vscode.git");
  const gitExt = ext && (ext.isActive ? ext.exports : await ext.activate());
  if (!gitExt?.enabled) {
    void vscode.window.showWarningMessage("The built-in Git extension is disabled (git.enabled = false).");
    return undefined;
  }
  const git = gitExt.getAPI(1);
  const fromTitleBar = rootUri && git.getRepository(rootUri);
  if (fromTitleBar) return fromTitleBar;
  if (git.repositories.length <= 1) {
    if (!git.repositories.length) void vscode.window.showWarningMessage("No Git repository is open.");
    return git.repositories[0];
  }
  const picked = await vscode.window.showQuickPick(
    git.repositories.map((r) => ({ label: vscode.workspace.asRelativePath(r.rootUri), repo: r })),
    { title: "Which repository?" },
  );
  return picked?.repo;
}
