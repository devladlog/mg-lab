// The slice of the built-in Git extension API this extension uses.
// Full typings: github.com/microsoft/vscode/blob/main/extensions/git/src/api/git.d.ts
import type { Uri } from "vscode";

export interface InputBox {
  value: string;
}

export interface Repository {
  readonly rootUri: Uri;
  readonly inputBox: InputBox;
}

export interface API {
  readonly repositories: Repository[];
  getRepository(uri: Uri): Repository | null;
}

export interface GitExtension {
  readonly enabled: boolean;
  getAPI(version: 1): API;
}
