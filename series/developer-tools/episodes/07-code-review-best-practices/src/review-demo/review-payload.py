#!/usr/bin/env python3
"""Turn review-comments.json into the request body for "Create a review for a pull request", so the review can be
posted with one call instead of typed line by line. Only the top-level comments (not the author's replies).

    python3 review-payload.py > review.json
    gh api repos/<owner>/<repo>/pulls/1/reviews --input review.json          # event COMMENT: authors can't approve or request changes on their own PR

Replies are posted separately, one per top-level comment:
    gh api repos/<owner>/<repo>/pulls/1/comments/<comment id>/replies -f body='Fair point, fixed in the next commit.'
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def payload(items: list[dict]) -> dict:
    comments = []
    for c in items:
        if c.get("in_reply_to_id") is not None:
            continue
        entry = {"path": c["path"], "line": c["line"], "side": c.get("side", "RIGHT"), "body": c["body"]}
        if "start_line" in c:
            entry.update(start_line=c["start_line"], start_side=c.get("start_side", "RIGHT"))
        comments.append(entry)
    return {"event": "COMMENT",
            "body": "Review of the cancel endpoint: three blocking comments (issue, question, todo); the rest is optional.",
            "comments": comments}


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    json.dump(payload(json.loads((here / "review-comments.json").read_text(encoding="utf-8"))), sys.stdout, indent=2)
    print()
