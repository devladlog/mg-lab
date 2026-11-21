import { DefaultAzureCredential } from "@azure/identity";
import { CommunicationIdentityClient } from "@azure/communication-identity";
import { loadConfig } from "./config";
import { InviteStore } from "./invites";
import { TableInviteStore } from "./tableStore";
import { IdentityClientLike } from "./token";

// Created on first request and reused: one credential, one table client, one identity client per instance.
let store: InviteStore | undefined;
let identity: IdentityClientLike | undefined;
const credential = new DefaultAzureCredential(); // user-assigned identity: AZURE_CLIENT_ID is set by the Bicep

export function getStore(): InviteStore {
  if (!store) {
    const cfg = loadConfig(process.env);
    store = TableInviteStore.connect(cfg.tableEndpoint, cfg.tableName, credential);
  }
  return store;
}

export function getIdentityClient(): IdentityClientLike {
  if (!identity) {
    const cfg = loadConfig(process.env);
    identity = new CommunicationIdentityClient(cfg.acsEndpoint, credential) as unknown as IdentityClientLike;
  }
  return identity;
}
