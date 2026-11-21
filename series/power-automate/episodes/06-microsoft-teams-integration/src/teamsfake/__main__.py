"""python -m teamsfake [paths | quote | burst N] [--first-version]

  paths            one High request three times: Sam takes it, Riley needs more info, nobody answers
  quote            a request titled  Monitor 27" flickers  (card as object vs card as pasted JSON text)
  burst N          N High requests in five minutes, every card taken (Flow bot budget: 25 per 300 s)
"""
import argparse
import glob
import json
import os
import sys

from .scenario import Dispatch, it_request
from .teams import Response
from .variants import all_posts_as_flow_bot, card_as_string_template

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load():
    (path,) = glob.glob(os.path.join(HERE, "solution", "Workflows", "ITon-calldispatch-*.json"))
    return json.load(open(path, encoding="utf-8-sig"))


def show(r, label):
    err = f"  {r.terminate_error['code']}" if r.terminate_error else ""
    failed = [f"{n}: {a.error}" for n, a in r.actions.items() if a.status == "Failed" and a.error]
    print(f"{label:<34} run {r.status:<9} {r.variables.get('dispatch', '')}{err}")
    for f in failed:
        print(f"{'':36}{f[:110]}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m teamsfake")
    p.add_argument("scenario", nargs="?", default="paths", choices=["paths", "quote", "burst"])
    p.add_argument("count", nargs="?", type=int, default=20)
    p.add_argument("--first-version", action="store_true")
    a = p.parse_args(argv)
    flow = load()
    if a.scenario == "paths":
        d = Dispatch(flow)
        show(d.run(it_request(42), Response("sam.demo@contoso.com", "Take it")), "#42 Sam Demo: Take it")
        show(d.run(it_request(43, "VPN drops every 10 minutes", category="Access"),
                   Response("riley.demo@contoso.com", "Need more info", "Office or home network?")),
             "#43 Riley Demo: Need more info")
        show(d.run(it_request(44, "Shared printer offline before payroll"), Response(None)), "#44 nobody, 30 minutes")
        print("On-call channel:")
        for m in d.channel.messages:
            print(f"  [{m['poster']}] {m['kind']}: {m['content'][:90]}")
        for who, msgs in d.teams.chats.items():
            for m in msgs:
                print(f"  [Flow bot chat with {who}] {m['content'][:80]}")
    elif a.scenario == "quote":
        f = card_as_string_template(flow) if a.first_version else flow
        d = Dispatch(f)
        r = d.run(it_request(45, 'Monitor 27" flickers on the left side'), Response("sam.demo@contoso.com", "Take it"))
        show(r, "#45 Monitor 27\" flickers")
        if r.ran("Build_card") and r.status == "Succeeded":
            card = json.loads(r.actions["Ask_on_call"].inputs["parameters"]["body/body/messageBody"])
            print(f"{'':36}card title on screen: {card['body'][1]['text']}")
    else:
        f = all_posts_as_flow_bot(flow) if a.first_version else flow
        d = Dispatch(f)
        results = []
        for i in range(a.count):
            results.append(d.run(it_request(100 + i, f"Outage report {i + 1}"), Response("sam.demo@contoso.com", "Take it")))
            d.teams.tick(300 / a.count)          # all within five minutes
        ok = sum(r.status == "Succeeded" for r in results)
        bot = sum(1 for _, op, poster, code in d.teams.calls if poster == "Flow bot")
        print(f"{a.count} requests in 5 minutes: {ok} runs succeeded, {a.count - ok} failed")
        print(f"Flow bot calls: {bot}, throttled (429): {d.teams.throttled('Flow bot')}   "
              f"User calls throttled: {d.teams.throttled('User')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
