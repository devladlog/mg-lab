import { createApprovalsApi } from "#src/approvals-api.js";

/** Start the real approvals API on a free port; the caller closes it. */
export async function startApi(options) {
  const api = createApprovalsApi(options);
  const url = await api.listen(0);
  return { api, url };
}

export const noWait = async () => {};

/** Poll until `check()` is true (the server learns about an abort a moment after the client). Fails after `timeoutMs`. */
export async function eventually(check, timeoutMs = 3000) {
  const end = Date.now() + timeoutMs;
  while (!check()) {
    if (Date.now() > end) throw new Error("condition not met in time");
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
}
