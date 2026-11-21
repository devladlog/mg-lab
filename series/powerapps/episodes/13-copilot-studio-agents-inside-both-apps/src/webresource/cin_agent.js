/* Model-driven app side of episode 13: a command bar button asks the Inspection Assistant a question about the open inspection.
 * Learn (Xrm.Copilot.executeEvent, preview): the topic receives the record through Global.PA__Copilot_Model_PageContext, so only the
 * question travels in eventParameters (read as Activity.Value in the topic). The agent is the app's "app assistant agent".
 * Register as web resource cin_/scripts/cin_agent.js and call cin.Agent.ask from the command (JavaScript action). */
var cin = cin || {};
cin.Agent = (function () {
  "use strict";
  var EVENT_NAME = "Contoso.Inspections.AskAboutInspection";
  var MAX_QUESTION = 500;
  var MAX_REPLY = 1500;

  function cleanQuestion(text) {
    var q = String(text == null ? "" : text).replace(/\s+/g, " ").trim();
    return q.length > MAX_QUESTION ? q.slice(0, MAX_QUESTION) : q;
  }

  // MCSResponse items: message activities carry text, event activities carry a value. Only message text is shown.
  function replyText(responses) {
    var parts = (responses || [])
      .filter(function (r) { return r && r.type === "message" && typeof r.text === "string" && r.text.trim() !== ""; })
      .map(function (r) { return r.text.trim(); });
    var text = parts.join("\n\n");
    if (text === "") { return "The agent did not answer. Try again, or carry on by hand."; }
    return text.length > MAX_REPLY ? text.slice(0, MAX_REPLY) : text;
  }

  function ask(primaryControl, question) {
    var q = cleanQuestion(question);
    if (q.length < 3) {
      return Xrm.Navigation.openAlertDialog({ title: "Inspection Assistant", text: "Type a question of at least 3 characters." });
    }
    if (!Xrm.Copilot || typeof Xrm.Copilot.executeEvent !== "function") {
      return Xrm.Navigation.openAlertDialog({ title: "Inspection Assistant", text: "The agent is not available in this app. Ask an admin to add the app assistant agent." });
    }
    return Xrm.Copilot.executeEvent(EVENT_NAME, { question: q }).then(
      function (responses) { return Xrm.Navigation.openAlertDialog({ title: "Inspection Assistant", text: replyText(responses) }); },
      function (error) {
        var why = error && error.message ? error.message : "unknown error";
        return Xrm.Navigation.openAlertDialog({ title: "Inspection Assistant", text: "The agent could not answer: " + why });
      });
  }

  return { ask: ask, cleanQuestion: cleanQuestion, replyText: replyText, EVENT_NAME: EVENT_NAME };
}());
if (typeof module !== "undefined") { module.exports = cin.Agent; }
