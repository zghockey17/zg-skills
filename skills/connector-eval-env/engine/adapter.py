"""Adapter loading: the declarative `adapter.json` plus the optional `adapter.py` hooks.

An adapter is a folder under `connectors/<name>/`. `adapter.json` declares the
static facts the engine reads (ports, stages, states, fingerprints, caps).
`adapter.py` supplies the app-specific behavior the engine cannot know: how to
start the app, how to observe its items, how to correlate a model call to an
item, how to reset disposable data. Every hook is optional; a missing hook
degrades the matching feature (documented in references/adapter-contract.md)
instead of failing the whole environment.
"""
import importlib.util
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)

HOOK_NAMES = ("processes", "seed", "reset", "observe", "in_flight", "transcript",
              "artifacts", "status", "down")


def connector_dir(connector):
    return os.path.join(ROOT, "connectors", connector)


def load_adapter(connector):
    path = os.path.join(connector_dir(connector), "adapter.json")
    with open(path) as fh:
        adapter = json.load(fh)
    adapter.setdefault("connector", connector)
    adapter["_dir"] = connector_dir(connector)
    return adapter


class Hooks:
    """Thin wrapper so callers can ask `hooks.has("observe")` and call safely."""

    def __init__(self, module):
        self.module = module

    def has(self, name):
        return self.module is not None and callable(getattr(self.module, name, None))

    def call(self, name, *args, **kwargs):
        if not self.has(name):
            raise RuntimeError("adapter has no %s hook" % name)
        return getattr(self.module, name)(*args, **kwargs)


def load_hooks(adapter):
    path = os.path.join(adapter["_dir"], adapter.get("hooks", "adapter.py"))
    if not os.path.exists(path):
        return Hooks(None)
    spec = importlib.util.spec_from_file_location(
        "evalenv_adapter_" + adapter["connector"], path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return Hooks(module)
