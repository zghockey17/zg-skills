"""Seed for the demo adapter.

The demo app starts empty and the vendor stub loads its accounts from
adapter.json, so there is nothing to insert. This file exists because the
adapter contract names a seed step; the `seed` hook in adapter.py is what the
engine calls. Run it by hand to print the demo accounts.
"""
import json
import os

if __name__ == "__main__":
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "adapter.json")) as fh:
        users = json.load(fh)["users"]
    print(json.dumps({"accounts": [{"slug": u["slug"], "api_key": u["api_key"]} for u in users]}))
