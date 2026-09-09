"""Placeholder hooks for a new adapter. Replace every body.

The engine calls these with the loaded adapter.json (`adapter`), the child
environment (`env`), and the session folder. Every hook is optional; a missing
hook degrades one feature (references/adapter-contract.md lists which). The
demo adapter (connectors/demo/adapter.py) is a complete, working example.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))


def processes(adapter, env, session_dir):
    """Processes to start after the stub and sidecar: your app and its worker.

    Real value: the exact argv you use to run the app locally, plus its port so
    the engine can wait for it. Placeholder: a Python one-liner that listens on
    the app port so `up` completes.
    """
    return [
        {"role": "app", "cwd": _HERE, "port": adapter["ports"]["app"],
         "argv": [sys.executable, "-c",
                  "import http.server,sys;http.server.HTTPServer(('127.0.0.1',%d),"
                  "http.server.BaseHTTPRequestHandler).serve_forever()" % adapter["ports"]["app"]]},
    ]


def seed(adapter, env, session_dir):
    """Create the users and settings the app needs. Real value: run your seed
    script (seed.py or a framework command) and return what it printed."""
    return {"seeded": "nothing (placeholder)"}


def reset(adapter, env, old_session_dir, new_session_dir):
    """Delete the previous session's data. Runs only when adapter.json
    disposable.confirmed is true. Real value: truncate the throwaway
    database's connector tables, then re-verify the database name is the
    throwaway one. Raise on any doubt; a raise aborts the reset."""
    raise RuntimeError("placeholder reset: fill in adapter.py before confirming disposable data")


def observe(adapter, env):
    """Current rows the monitor should watch. Real value: query the items,
    connections, and deliveries tables. Return dicts keyed by id with the
    keys listed in references/adapter-contract.md."""
    return {"items": {}, "connections": {}, "deliveries": {}}


def in_flight(adapter, env):
    """Which item the worker is processing right now, so a model call can be
    attributed to it. Real value: read the reserved job row. Return
    {"item_id", "rec", "job_reserved", "ambiguous"}."""
    return {"item_id": None, "rec": None, "job_reserved": False, "ambiguous": False}


def transcript(adapter, env, rec):
    """The stored (redacted) text for a record, or None. Real value: join
    your transcript rows for the record; include speaker names."""
    return None


def artifacts(adapter, env, session_dir, rec):
    """(ok, detail) for the filed artifacts. Real value: check the meeting
    row, its transcript rows, and the filed page on disk."""
    return False, "placeholder artifacts hook"


def status(adapter, env, session_dir):
    """Booleans only, never values: is the app pointed at the sidecar, is it
    on the throwaway database, does it have a model key."""
    return {"ok": False, "placeholder": True}


def down(adapter, env, session_dir):
    """Undo any modification `up` made to the app (a placed provider file, a
    config line). Return what was removed."""
    return {"app_modifications": "none (placeholder)"}
