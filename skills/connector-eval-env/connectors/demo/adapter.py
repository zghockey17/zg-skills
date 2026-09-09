"""Hooks for the demo adapter.

The engine calls these to do the app-specific parts of a session. Every hook
here talks to the demo app over loopback HTTP or touches files inside the
session folder; nothing reads outside it. See references/adapter-contract.md
for the full hook contract and ADAPTING.md for how to write these for a real
app.
"""
import json
import os
import sys
import urllib.error
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))


def _app_base(adapter):
    return "http://127.0.0.1:%d" % adapter["ports"]["app"]


def _get_json(url, timeout=3):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode() or "{}")


def processes(adapter, env, session_dir):
    """The processes beyond the stub and sidecar: the demo app and the stand-in model."""
    return [
        {"role": "app", "argv": [sys.executable, os.path.join(_HERE, "app.py")],
         "cwd": _HERE, "port": adapter["ports"]["app"]},
        {"role": "model", "argv": [sys.executable, os.path.join(_HERE, "model.py")],
         "cwd": _HERE, "port": adapter["ports"]["model"]},
    ]


def seed(adapter, env, session_dir):
    """Nothing to seed: the demo app starts empty and the vendor stub loads its
    accounts from adapter.json. Report the accounts so `up` can print them."""
    return {"accounts": [{"slug": u["slug"], "api_key": u["api_key"]} for u in adapter["users"]]}


def reset(adapter, env, old_session_dir, new_session_dir):
    """Delete the previous session's disposable app data.

    Fails closed: every path must be declared in adapter.json `disposable.paths`,
    must be relative, and must resolve inside the old session folder. Anything
    else raises before a single file is removed.
    """
    paths = adapter.get("disposable", {}).get("paths") or []
    root = os.path.realpath(old_session_dir)
    targets = []
    for rel in paths:
        if os.path.isabs(rel) or ".." in rel.split(os.sep):
            raise RuntimeError("reset refused: disposable path %r is not session-relative" % rel)
        full = os.path.realpath(os.path.join(root, rel))
        if not (full == root or full.startswith(root + os.sep)):
            raise RuntimeError("reset refused: %r resolves outside the session folder" % rel)
        targets.append(full)
    removed = []
    for full in targets:
        if os.path.isdir(full):
            for base, dirs, files in os.walk(full, topdown=False):
                for name in files:
                    os.remove(os.path.join(base, name))
                for name in dirs:
                    os.rmdir(os.path.join(base, name))
            os.rmdir(full)
            removed.append(full)
        elif os.path.exists(full):
            os.remove(full)
            removed.append(full)
    return {"removed": [os.path.relpath(p, root) for p in removed]}


def observe(adapter, env):
    """Items, connections, and deliveries as the demo app reports them."""
    return _get_json(_app_base(adapter) + "/_eval/state")


def in_flight(adapter, env):
    """Which item the demo worker is processing right now, for model-call correlation."""
    return _get_json(_app_base(adapter) + "/_eval/in-flight")


def transcript(adapter, env, rec):
    try:
        return _get_json(_app_base(adapter) + "/_eval/transcript/" + rec).get("words")
    except urllib.error.HTTPError:
        return None


def artifacts(adapter, env, session_dir, rec):
    """A filed record must have a page under <session>/filed/ with a title line."""
    page = os.path.join(session_dir, "filed", rec + ".md")
    if not os.path.exists(page):
        return False, "filed page missing: filed/%s.md" % rec
    with open(page) as fh:
        head = fh.readline().strip()
    if not head.startswith("# ") or len(head) < 3:
        return False, "filed page has no title line"
    return True, "filed page present with title"


def status(adapter, env, session_dir):
    """Booleans only. The app reports whether its model base URL points at the
    sidecar and whether its storage is inside the session folder."""
    try:
        info = _get_json(_app_base(adapter) + "/_eval/status")
    except Exception as err:
        return {"ok": False, "error": str(err)}
    return {"ok": bool(info.get("model_via_sidecar")) and bool(info.get("storage_in_session")),
            "model_via_sidecar": bool(info.get("model_via_sidecar")),
            "storage_in_session": bool(info.get("storage_in_session")),
            "has_model_key": bool(info.get("has_model_key"))}


def down(adapter, env, session_dir):
    """The demo modifies nothing outside the session folder, so there is nothing to undo."""
    return {"app_modifications": "none"}
