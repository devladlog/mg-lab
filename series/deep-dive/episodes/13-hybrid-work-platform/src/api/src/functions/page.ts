import * as path from "node:path";
import { app, HttpRequest, HttpResponseInit } from "@azure/functions";
import { PAGE, readSiteFile, resolveAsset } from "../lib/assets";

const SITE_DIR = path.join(__dirname, "..", "..", "site");
const SECURITY = {
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "no-referrer",
  "Cache-Control": "no-store",
};

app.http("joinPage", {
  methods: ["GET"],
  route: "join",
  authLevel: "anonymous",
  handler: async (): Promise<HttpResponseInit> => ({
    status: 200,
    body: await readSiteFile(SITE_DIR, PAGE.file),
    headers: { ...SECURITY, "Content-Type": PAGE.type },
  }),
});

app.http("joinAsset", {
  methods: ["GET"],
  route: "assets/{name}",
  authLevel: "anonymous",
  handler: async (request: HttpRequest): Promise<HttpResponseInit> => {
    const asset = resolveAsset(request.params["name"] ?? "");
    if (!asset) return { status: 404 };
    return { status: 200, body: await readSiteFile(SITE_DIR, asset.file), headers: { ...SECURITY, "Content-Type": asset.type } };
  },
});
