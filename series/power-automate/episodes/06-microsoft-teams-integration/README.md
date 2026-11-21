# DEVLADLOG Power Automate #6: A Teams card that gets an answer

An **IT on-call dispatch** cloud flow for the *IT Requests* list from episode 1: a High priority request becomes an
**adaptive card in the on-call channel that waits for an answer**, and the local material that proves every path
(and the traps) **before anyone in Teams gets a card**.

In episode 1, a High priority request emailed on-call. Emails get missed. Now:

- **Trigger:** SharePoint *When an item is created* on IT Requests, trigger condition
  `Priority = High and the title doesn't start with [test]`.
- **Card:** built as an **object** in a Compose (`Build_card`, Adaptive Card 1.4: title, category, requester, time,
  a note box, *Take it*, *Need more info*, *Open the request*) and sent with **`string(outputs('Build_card'))`**, so a
  quote or a backslash in the title can't break the JSON.
- **Post adaptive card and wait for a response** as **Flow bot** to the standard channel *On-call* of the *IT On-call*
  team (team and channel IDs are environment variables), **timeout 30 minutes**, with an update message that replaces
  the card once someone answers.
- **Take it** (`submitActionId` is the button title): the request's *Assigned to* is set to the responder
  (SharePoint *Update item*), and a message **posted as User** in the channel @mentions them (*Get an @mention token
  for a user*).
- **Need more info:** the Flow bot sends the requester a 1:1 chat with the responder's note.
- **Nobody answers in 30 minutes:** the on-call lead is @mentioned in the channel.
- **Join and fail loudly:** `Dispatch done` runs after both paths (*Succeeded* or *Skipped*) and terminates the run
  as **Failed** (`CardNotPosted`) if no path recorded an outcome, i.e. the card was never posted. An unexpected
  button title terminates as Failed too (`UnexpectedResponse`).

| Path | What it is |
|---|---|
| [`src/solution/`](src/solution) | Unpacked solution `ITOnCall` (`pac solution unpack` layout): 1 flow, 2 connection references (SharePoint, Teams), 4 environment variables (site URL, team ID, channel ID, on-call lead) |
| [`src/solution/Workflows/ITon-calldispatch-…601.json`](src/solution/Workflows) | The flow definition |
| [`src/teamsfake/`](src/teamsfake) | In-memory Teams for the tests: standard and private channels, Flow bot chats, wait-for-response cards with scripted answers (or no answer), @mention tokens, the 28 KB and 20-mention limits, and the connector's **throttling budgets** (Flow bot 25 posts per 300 s per connection, others 300). `python -m teamsfake` plays the scenarios |
| [`src/teamsfake/variants.py`](src/teamsfake/variants.py) | Our two earlier drafts as transformations: card pasted as JSON text, every post as Flow bot |
| [`src/flowkit/`](src/flowkit) | Harness from episodes 1–4, **extended for Teams**: [`cards.py`](src/flowkit/cards.py) (card checks from Learn: valid JSON, no templating, ≈28 KB, unique input ids and button titles, Action.Submit only on wait-for-response cards) and lint rules (wait-for-response needs a timeout and a timed-out path, card JSON built by string interpolation, more than 20 mentions) |
| [`tests/`](tests) | 27 pytest tests: every path, gotchas, card checks, lint, `pac solution pack` |
| [`script.yaml`](script.yaml) | Draft video script (16 scenes) · [`demo.md`](demo.md) shot list for the lab tenant |

## Run it

Needs Python 3.10+ and pytest (no other packages). `pac` is optional; the pack test is skipped without it.

```bash
cd series/power-automate/episodes/06-microsoft-teams-integration
python -m pytest                       # 27 passed in ~2.7 s (pac 2.16.1 present)

cd src
python -m flowkit lint solution/Workflows/*.json
python -m teamsfake                    # Sam takes #42, Riley needs more info on #43, nobody answers #44
python -m teamsfake quote --first-version   # a title with a double quote breaks the pasted card
python -m teamsfake quote                   # ...and doesn't break the card built as an object
python -m teamsfake burst 20 --first-version   # card + announcement both as Flow bot: 8 of 20 runs throttled
python -m teamsfake burst 20                   # announcement as User: none throttled
pac solution pack --zipfile ../out/ITOnCall.zip --folder solution --packagetype Unmanaged
```

Result on the build machine (2026-11-21): `27 passed in 2.69s`; lint `OK`; `pac solution pack` then
`pac solution unpack` reproduces `src/solution/` byte for byte. `python -m teamsfake` prints:

```
#42 Sam Demo: Take it              run Succeeded taken by Sam Demo
#43 Riley Demo: Need more info     run Succeeded more info requested by Riley Demo
#44 nobody, 30 minutes             run Succeeded escalated to the on-call lead
On-call channel:
  [Flow bot] updated card: Request #42 has been picked up. Who took it is posted in this channel.
  [User] message: <p><at>Sam Demo</at> took high priority request #42: Laptop won't boot before a client dem
  ...
```

`burst 20 --first-version`: `12 runs succeeded, 8 failed`, `Flow bot calls: 33, throttled (429): 8`.
`burst 20`: `20 runs succeeded`, `throttled (429): 0`. `burst 30`: `25 succeeded, 5 failed` (see gotchas).

## How the material was made, and what still needs the tenant

The definition was written from the Teams connector reference (operation IDs `PostCardAndWaitForResponse`,
`PostMessageToConversation`, `AtMentionUser`; `atMention` output) and the SharePoint connector (`GetOnNewItems`,
`PatchItem`), packed and unpacked with `pac`, and run against `teamsfake`. The Teams and SharePoint actions are
mocked; the card JSON the flow builds is really parsed and checked. **Needs tenant:** the team and channel, the
Workflows app, a real card answered in Teams, a real timeout, and the export (demo.md).

## What we learned / gotchas

- **Don't paste card JSON with dynamic content inside it.** Our first draft pasted the card into the Message box with
  the title inside a JSON string. A title like `Monitor 27" flickers` makes the JSON invalid and the card isn't
  posted; `C:\temp\new` is worse: the JSON stays valid and the card silently shows a tab and a line break
  (`test_a_quote_in_the_title_breaks_a_pasted_card`, `test_a_backslash_is_worse_it_silently_changes_the_text`).
  Build the card as an object in a Compose: the engine fills in the values, and `string()` turns the object into JSON,
  escaping quotes (functions reference, `string` example 2). The linter flags interpolated card JSON. Power Automate
  also doesn't support adaptive card **templating** (`${...}`), so this is the way to put data in a card.
- **The Flow bot has its own, small budget.** Teams connector throttling: "Non-Get requests per connection (for … Post
  an Adaptive Card as Flow bot, and any other Flow bot operations)" **25 per 300 seconds**; all other operations 300.
  Our second draft also posted the "who took it" announcement as Flow bot: 20 High requests in five minutes used 33
  Flow bot calls and 8 runs got 429s (`test_flow_bot_budget_is_25_posts_per_five_minutes`). Posting follow-ups as
  **User** leaves the bot budget for the cards. Honest limit: 30 cards in five minutes still exceed it; in a real
  outage, batch them. (`teamsfake` answers 429 and stops; the real engine retries 429s per the action's retry policy,
  so in the tenant runs would slow down before they fail.)
- **Private channels aren't supported** for posting messages or cards (Teams connector, general known issues). If
  the channel environment variable points to one, the post fails and the run says `CardNotPosted`.
- **Wait-for-response cards: set a timeout, handle it, join.** Without *Settings → Timeout* the card waits until the
  30-day run limit. With a timeout, the timed-out path needs its own steps, and then a join after both paths: without
  it, a handled timeout still fails the run (episode 2's lesson, `test_without_the_join_a_handled_timeout_fails_the_run`).
- **A join can also hide a failure.** A join that runs after *Succeeded* or *Skipped* also runs when the card post
  **failed** (both paths are skipped), and the run turns green with nothing posted
  (`test_the_join_without_its_check_hides_a_failed_post`). Each path records an outcome in a variable; the join
  terminates as Failed when none did.
- **`submitActionId` is the button title.** Rename *Take it* to *I'll take it* in the card and the Switch no longer
  matches. Our default case terminates as Failed instead of doing nothing (`test_renaming_a_button_breaks_the_switch`).
  The card checker refuses two buttons with the same title.
- **Answered once, then replaced.** Learn: wait-for-response cards "can only be submitted once per card"; configure
  the update message so others see it's handled. Only wait-for-response actions can collect data; Action.Submit on
  other cards shows an error.
- **Connector facts that shape the design:** Teams is a **standard** connector; these actions need the **Workflows
  app** allowed in the Teams admin center; message size about **28 KB** ("Request Entity too large"); at most **20
  @mentions** per message; 100 API calls per connection per 60 seconds.

### What was not verified here

- **Designer conventions** not documented on Learn: the parameter keys of the Teams actions (`poster`, `location`,
  `body/body/messageBody`, `body/body/updateMessage`, `body/body/shouldUpdateCard`, `body/body/recipient/groupId|channelId`,
  `body/recipient`, `body/messageBody`), the values `"Flow bot"`, `"User"`, `"Channel"`, `"Chat with Flow bot"`, the
  shape of the wait-for-response output (`responder/userPrincipalName`, `responder/displayName`, `data/<input id>`),
  `item/AssignedTo/Claims` for a person column, and the exact text of the @mention token. demo.md step 6 exports the
  real JSON and replaces ours.
- What Teams does with a card that isn't valid JSON (the fake fails the action; the message is its own), and whether
  a timed-out card can still be pressed (the flow no longer listens either way).
- Adaptive card versions: Learn pages disagree on the highest version Teams supports (1.5 in several articles, 1.6 in
  the Teams platform cards reference). We use **1.4** and no newer features.

## References

- [Microsoft Teams connector reference (actions, known issues, throttling)](https://learn.microsoft.com/connectors/teams/)
- [Overview of adaptive cards for Microsoft Teams (known issues: wait actions, submitted once, update message)](https://learn.microsoft.com/power-automate/overview-adaptive-cards)
- [Create your first adaptive card](https://learn.microsoft.com/power-automate/create-adaptive-cards)
- [Send proactive Teams messages (templating not supported, submitActionId is the button title)](https://learn.microsoft.com/microsoft-copilot-studio/advanced-proactive-message)
- [Reference guide to expression functions (`string`, `formatDateTime`, `startsWith`)](https://learn.microsoft.com/azure/logic-apps/expression-functions-reference)
- [Handle workflow errors and exceptions (branch status after a skipped action)](https://learn.microsoft.com/azure/logic-apps/error-exception-handling)
- [Limits of automated, scheduled, and instant flows (30-day run duration, timeouts)](https://learn.microsoft.com/power-automate/limits-and-config)
- [Customize your triggers with conditions](https://learn.microsoft.com/power-automate/customize-triggers)
- [Teams platform: types of cards (Adaptive Card versions)](https://learn.microsoft.com/microsoftteams/platform/task-modules-and-cards/cards/cards-reference)
- [SharePoint connector reference](https://learn.microsoft.com/connectors/sharepointonline/) · [Use environment variables in solution cloud flows](https://learn.microsoft.com/power-automate/guidance/coding-guidelines/use-environment-variables)
- Blog: [Microsoft Teams Integration: Complete Guide](https://www.devladlog.com/articles/power-automate/2026-06-03-teams-integration-complete-guide-2026/)
