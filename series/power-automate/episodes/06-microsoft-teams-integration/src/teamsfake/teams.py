"""An in-memory Microsoft Teams for local tests of the Teams connector actions our flow uses.

Test double, not Teams. Rules taken from the Teams connector reference on Microsoft Learn:

- Throttling, per connection: Flow bot operations ("Post an Adaptive Card as Flow bot, and any other Flow bot
  operations") 25 non-GET requests per 300 seconds; all other non-GET operations 300 per 300 seconds. Over the
  budget the fake answers 429. It does NOT model the engine's retries of a 429 (the default retry policy).
- Posting a message or card to a private channel isn't supported.
- Message size limit about 28 KB ("Request Entity too large"); at most 20 @mentions per message.
- Wait-for-response cards are answered once; the response carries submitActionId (the button title).

Assumptions (not on Learn) are marked: the shape of the wait-for-response output (responder fields, data),
the @mention token text, and the error texts.
"""
from __future__ import annotations

import json
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from flowkit.cards import MAX_MESSAGE_BYTES, card_problems, mention_count

FLOW_BOT_LIMIT = (25, 300)        # calls, seconds
OTHER_LIMIT = (300, 300)
TEAMS_POSTING_OPS = {"PostCardAndWaitForResponse", "PostMessageToConversation", "PostCardToConversation",
                     "ReplyWithMessageToConversation", "ReplyWithCardToConversation", "UpdateCardInConversation"}


@dataclass
class Channel:
    team_id: str
    channel_id: str
    name: str
    private: bool = False
    messages: list = field(default_factory=list)


@dataclass
class Response:
    """What someone does with the card: press a button (and maybe type a note), or nothing (timeout)."""
    by: str | None = None              # UPN of the responder; None = nobody answers before the timeout
    button: str = "Take it"
    note: str = ""


class Teams:
    def __init__(self, now: datetime | None = None):
        self.clock = now or datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc)
        self.channels: dict[tuple[str, str], Channel] = {}
        self.chats: dict[str, list] = defaultdict(list)      # Flow bot 1:1 chats, by recipient email
        self.users: dict[str, str] = {}                       # UPN -> display name
        self.responses: deque[Response] = deque()             # scripted answers, in order
        self.calls: list[tuple[datetime, str, str, int]] = [] # (time, operation, poster, status code)
        self._windows: dict[str, deque] = defaultdict(deque)  # budget name -> timestamps
        self._next_id = 1000

    # --------------------------------------------------------------- setup
    def add_channel(self, team_id, channel_id, name, private=False) -> Channel:
        ch = Channel(team_id, channel_id, name, private)
        self.channels[(team_id, channel_id)] = ch
        return ch

    def add_user(self, upn, name):
        self.users[upn] = name

    def tick(self, seconds: float):
        self.clock += timedelta(seconds=seconds)

    # --------------------------------------------------------------- throttling
    def _admit(self, op: str, poster: str) -> bool:
        if op not in TEAMS_POSTING_OPS and op != "AtMentionUser":
            return True
        budget, (limit, period) = ("flowbot", FLOW_BOT_LIMIT) if poster == "Flow bot" else ("other", OTHER_LIMIT)
        window = self._windows[budget]
        while window and (self.clock - window[0]).total_seconds() >= period:
            window.popleft()
        if len(window) >= limit:
            return False
        window.append(self.clock)
        return True

    def throttled(self, poster="Flow bot") -> int:
        return sum(1 for _, _, p, code in self.calls if p == poster and code == 429)

    # --------------------------------------------------------------- connector entry point
    def connector(self, inputs: dict) -> dict:
        op = inputs["host"]["operationId"]
        p = inputs.get("parameters", {})
        poster = p.get("poster", "-")
        if not self._admit(op, poster):
            self.calls.append((self.clock, op, poster, 429))
            return _fail(429, "Rate limit is exceeded. Try again later.")
        try:
            reply = getattr(self, f"_op_{op}")(p)
        except _TeamsError as e:
            self.calls.append((self.clock, op, poster, e.status))
            return _fail(e.status, e.message)
        self.calls.append((self.clock, op, poster, reply.get("statusCode", 200)))
        return reply

    def _channel(self, p, prefix):
        key = (p.get(f"{prefix}recipient/groupId"), p.get(f"{prefix}recipient/channelId"))
        ch = self.channels.get(key)
        if ch is None:
            raise _TeamsError(404, f"Channel {key[1]!r} not found in team {key[0]!r}")
        if ch.private:
            # Learn: "Posting a message or adaptive card to a private channel currently isn't supported."
            raise _TeamsError(400, "Posting to a private channel isn't supported")
        return ch

    def _post(self, target: list, kind: str, content: str, poster: str, extra=None) -> dict:
        if len(content.encode("utf-8")) > MAX_MESSAGE_BYTES:
            raise _TeamsError(413, "Request Entity too large")
        if mention_count(content) > 20:
            raise _TeamsError(400, "A message can @mention up to 20 users")
        self._next_id += 1
        msg = {"id": str(self._next_id), "kind": kind, "content": content, "poster": poster,
               "time": self.clock.isoformat(), **(extra or {})}
        target.append(msg)
        return msg

    def _op_PostCardAndWaitForResponse(self, p):
        if p.get("location") != "Channel":
            raise NotImplementedError("this fake posts wait-for-response cards to channels only")
        ch = self._channel(p, "body/body/")
        card = p.get("body/body/messageBody")
        problems = card_problems(card, waits_for_response=True)
        if problems:
            raise _TeamsError(400, "Invalid adaptive card: " + "; ".join(problems))   # text is the fake's own
        msg = self._post(ch.messages, "card", card, p.get("poster"))
        answer = self.responses.popleft() if self.responses else Response(by=None)
        if answer.by is None:
            return {"status": "TimedOut"}
        buttons = {a["title"]: a for a in _submits(json.loads(card))}
        if answer.button not in buttons:
            raise ValueError(f"the card has no button {answer.button!r} (has {sorted(buttons)})")
        if p.get("body/body/shouldUpdateCard"):
            msg["content"] = p.get("body/body/updateMessage", "")    # Learn: the update message replaces the card
            msg["kind"] = "updated card"
        data = dict(buttons[answer.button].get("data") or {})
        data["note"] = answer.note
        # Output shape assumed from the designer's dynamic content (not documented on Learn).
        return {"status": "Succeeded", "statusCode": 200, "body": {
            "responseTime": self.clock.isoformat(), "submitActionId": answer.button, "data": data,
            "responder": {"userPrincipalName": answer.by, "email": answer.by,
                          "displayName": self.users.get(answer.by, answer.by)}}}

    def _op_PostMessageToConversation(self, p):
        poster, location = p.get("poster"), p.get("location")
        text = p.get("body/messageBody", "")
        if location == "Channel":
            msg = self._post(self._channel(p, "body/").messages, "message", text, poster)
        elif location == "Chat with Flow bot":
            if poster != "Flow bot":
                raise _TeamsError(400, "Chat with Flow bot needs the Flow bot poster")
            msg = self._post(self.chats[p.get("body/recipient")], "message", text, poster)
        else:
            raise NotImplementedError(location)
        return {"status": "Succeeded", "statusCode": 200,
                "body": {"id": msg["id"], "messageLink": f"https://teams.example/l/message/{msg['id']}",
                         "conversationId": "19:fake@thread.tacv2"}}

    def _op_AtMentionUser(self, p):
        upn = p.get("userId")
        if upn not in self.users:
            raise _TeamsError(404, f"User {upn!r} not found")
        # The real token's exact text isn't documented; this one renders like the documented <at> markup.
        return {"status": "Succeeded", "statusCode": 200, "body": {"atMention": f"<at>{self.users[upn]}</at>"}}


class _TeamsError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status, self.message = status, message


def _submits(card):
    from flowkit.cards import walk
    return [n for n in walk(card) if n.get("type") == "Action.Submit"]


def _fail(status, message):
    return {"status": "Failed", "statusCode": status, "body": {"error": {"message": message}},
            "error": f"{status}: {message}"}
