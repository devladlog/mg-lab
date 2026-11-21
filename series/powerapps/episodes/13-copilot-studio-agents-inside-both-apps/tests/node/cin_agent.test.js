// node --test tests/node : the model-driven side (command bar JavaScript) against a stub of Xrm. The stub is a test double, not the platform.
const test = require("node:test");
const assert = require("node:assert");
const agent = require("../../src/webresource/cin_agent.js");

function stubXrm(executeEvent) {
  const alerts = [];
  global.Xrm = { Copilot: executeEvent ? { executeEvent } : undefined, Navigation: { openAlertDialog: (o) => { alerts.push(o); return Promise.resolve(); } } };
  return alerts;
}

test("event name is the registered topic event", () => assert.strictEqual(agent.EVENT_NAME, "Contoso.Inspections.AskAboutInspection"));
test("cleanQuestion collapses spaces and caps at 500", () => {
  assert.strictEqual(agent.cleanQuestion("  a   b \n c "), "a b c");
  assert.strictEqual(agent.cleanQuestion("x".repeat(900)).length, 500);
  assert.strictEqual(agent.cleanQuestion(null), "");
});
test("replyText joins message text only, ignores events, caps and falls back", () => {
  assert.strictEqual(agent.replyText([{ type: "message", text: " one " }, { type: "event", value: { a: 1 } }, { type: "message", text: "two" }]), "one\n\ntwo");
  assert.strictEqual(agent.replyText([{ type: "event" }]), "The agent did not answer. Try again, or carry on by hand.");
  assert.strictEqual(agent.replyText(undefined), "The agent did not answer. Try again, or carry on by hand.");
  assert.strictEqual(agent.replyText([{ type: "message", text: "y".repeat(2000) }]).length, 1500);
});
test("ask sends only the question to executeEvent and shows the reply", async () => {
  let seen;
  const alerts = stubXrm(async (name, params) => { seen = [name, params]; return [{ type: "message", text: "Two items are open." }]; });
  await agent.ask({}, "  Which items are open? ");
  assert.deepStrictEqual(seen, ["Contoso.Inspections.AskAboutInspection", { question: "Which items are open?" }]);
  assert.strictEqual(alerts[0].text, "Two items are open.");
});
test("short question is refused without calling the agent", async () => {
  let called = false;
  const alerts = stubXrm(async () => { called = true; return []; });
  await agent.ask({}, "hi");
  assert.strictEqual(called, false);
  assert.match(alerts[0].text, /at least 3/);
});
test("missing Xrm.Copilot and a rejected call are reported, not thrown", async () => {
  let alerts = stubXrm(undefined);
  await agent.ask({}, "Which items are open?");
  assert.match(alerts[0].text, /not available/);
  alerts = stubXrm(async () => { throw new Error("no credits"); });
  await agent.ask({}, "Which items are open?");
  assert.match(alerts[0].text, /could not answer: no credits/);
});
