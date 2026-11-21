"""python -m spfake [--first-version] [--max-polls N] [--amount-change]

Plays the episode's scenario against the in-memory Purchasing site and prints what each trigger poll ran:
Alex Demo raises a request, the approval flow (episode 2) approves it, then this flow reacts."""
import argparse
import glob
import json
import os
import sys

from .scenario import Poller, first_version, purchasing_site, user

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LABELS = {"Create_order_folder": "folder", "Grant_requester_read": "permissions", "Tag_summary_file": "summary file",
          "Link_folder_on_request": "link on item", "Tell_requester": "email requester",
          "Mark_escalated": "Escalated", "Notify_purchasing": "email purchasing"}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m spfake")
    p.add_argument("--flow", default=glob.glob(os.path.join(HERE, "solution", "Workflows", "Purchaseorderfolder-*.json"))[0])
    p.add_argument("--first-version", action="store_true", help="run the draft without the 'Needs order folder' check")
    p.add_argument("--amount-change", action="store_true", help="after the folder exists, Alex changes the amount")
    p.add_argument("--max-polls", type=int, default=6)
    a = p.parse_args(argv)
    flow = json.load(open(a.flow, encoding="utf-8-sig"))
    if a.first_version:
        flow = first_version(flow)
    site = purchasing_site()
    alex = user(site, "alex.demo@contoso.com")
    item = site.create_item("Purchase Requests", {"Title": "Laptops for two new developers", "Amount": 12500,
                                                  "Status": "Pending", "Justification": "Two developer laptops"}, alex)
    poller = Poller(site, flow)
    poller.poll()                                       # creation: this trigger ignores new items
    site.edit_item("Purchase Requests", item, {"Status": "Approved", "DecisionBy": "Jordan Demo"}, site.connection_user)
    print(f"Alex Demo's request #{item} approved by Jordan Demo (episode 2's flow)")
    amount_changed = False
    for n in range(1, a.max_polls + 1):
        results = poller.poll()
        started = [r for r in results if r.status != "Skipped"]
        if not results:
            print(f"poll {n}: no changes")
        for r in results:
            if r.status == "Skipped":
                print(f"poll {n}: item changed, trigger condition false: no run")
                continue
            did = [LABELS[name] for name in r.order if name in LABELS and r.actions[name].status == "Succeeded"]
            print(f"poll {n}: run {r.status:<9} " + (", ".join(dict.fromkeys(did)) if did else "nothing to do")
                  + f"  ({sum(1 for x in r.order if r.actions[x].status != 'Skipped')} actions)")
        if not started and a.amount_change and not amount_changed:
            site.edit_item("Purchase Requests", item, {"Amount": 14200}, alex)
            amount_changed = True
            print("Alex Demo changes the amount to 14,200")
        elif not started and n > 1:
            break
    runs = len(poller.started_runs())
    print(f"runs: {runs}  folders: {len(site.lists['Orders'].folders)}  emails: {len(poller.mail)}  "
          f"status: {site.lists['Purchase Requests'].items[item].current['Status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
