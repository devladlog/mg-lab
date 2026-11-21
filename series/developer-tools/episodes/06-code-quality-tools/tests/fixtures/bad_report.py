import os, sys
from typing import List
import json

API_PASSWORD = "changeme"


def load(path, seen=[]):
    if os.path.exists(path) == True:
        data = open(path).read()
    else:
        data = ""
    flag = False
    if data:
        flag = True
    else:
        flag = False
    seen.append(path)
    return {"path":path, "data" : data, "flag": flag}


def names(items: List[str]) -> List[str]:
    return [i.strip() for i in items]
