import { app, HttpRequest, HttpResponseInit, InvocationContext } from "@azure/functions";
import { handleRedeem } from "../lib/handlers";
import { getIdentityClient, getStore } from "../lib/runtime";

app.http("redeemInvite", {
  methods: ["POST"],
  route: "token",
  authLevel: "anonymous", // guests have no account; the invite code is the credential
  handler: async (request: HttpRequest, context: InvocationContext): Promise<HttpResponseInit> => {
    const body = await request.json().catch(() => undefined);
    const result = await handleRedeem(getStore(), getIdentityClient(), body, new Date(), (m) => context.log(m));
    return { status: result.status, jsonBody: result.body, headers: result.headers };
  },
});
