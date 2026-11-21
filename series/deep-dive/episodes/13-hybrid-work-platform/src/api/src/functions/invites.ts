import { app, HttpRequest, HttpResponseInit, InvocationContext } from "@azure/functions";
import { handleCreateInvite } from "../lib/handlers";
import { getStore } from "../lib/runtime";

app.http("createInvite", {
  methods: ["POST"],
  route: "invites",
  authLevel: "function",
  handler: async (request: HttpRequest, _context: InvocationContext): Promise<HttpResponseInit> => {
    const body = await request.json().catch(() => undefined);
    const baseUrl = new URL(request.url).origin;
    const result = await handleCreateInvite(getStore(), body, baseUrl);
    return { status: result.status, jsonBody: result.body, headers: result.headers };
  },
});
