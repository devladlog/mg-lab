#!/usr/bin/env python3
"""Stand-in for the Azure CLI, used only by the script tests: records its arguments and answers from environment variables."""
import json
import os
import shutil
import sys
from pathlib import Path

a = sys.argv[1:]
with open(os.environ["FAKE_AZ_LOG"], "a") as f:
    f.write(" ".join(a) + "\n")
env = os.environ.get
head = " ".join(a[:3])
if head == "ml model show":
    if env("FAKE_PROD_AUC"):
        print(env("FAKE_PROD_AUC"))
    else:
        sys.exit(3)
elif head == "ml job create":
    print("job-123")
elif head == "ml job show":
    print(env("FAKE_STATUS", "Completed"))
elif head == "ml job download":
    dest = Path(a[a.index("--download-path") + 1]) / "named-outputs" / "decision"
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy(env("FAKE_DECISION"), dest / "decision.json")
elif head == "ml model create":
    print("5")
elif head == "ml online-endpoint show":
    if env("FAKE_EP_EXISTS") != "1":
        sys.exit(1)
    print(env("FAKE_TRAFFIC", '{"blue": 100}'))
