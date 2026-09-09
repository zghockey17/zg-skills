#!/usr/bin/env python3
"""Connector eval environment CLI and process lifecycle.

    python3 engine/evalenv.py <connector> <verb> [args]

Every verb prints exactly one JSON object to stdout and exits 0 on success or
non-zero with {"ok": false, "error": "..."} on failure.

The engine owns two processes, the vendor stub and the capture sidecar. The
adapter's `processes` hook names the rest (the app under test, its worker).
`up` starts them all against a fresh session folder; `down` stops exactly the
processes this session started and runs the adapter's cleanup hook.

Invariants:
  * Every listener binds 127.0.0.1. Nothing here is reachable off the machine.
  * Secrets named in the adapter's `secret_env_keys` are read from the file the
    adapter names in `env_file`, handed to child processes, and never written
    to any file under the skill or session folder, never printed, and never
    placed in JSON output or pids.json.
  * `reset` runs only when the adapter declares its data disposable and ships a
    reset hook; otherwise it fails closed and touches nothing.
  * Process cleanup kills a pid only when its command line still matches the
    marker recorded when it was started.
"""
import json
import os
import subprocess
import sys
import time
import socket
import urllib.error
import urllib.request
from datetime import datetime, timezone

try:
    from engine import evals
    from engine import adapter as adapter_mod
except ImportError:
    import evals
    import adapter as adapter_mod

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
LOOPBACK = "127.0.0.1"
ENGINE_ROLES = ("stub", "sidecar")


# --- small IO helpers -------------------------------------------------------

def _read(path):
    with open(path) as fh:
        return fh.read()


def _read_json(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path) as fh:
            return json.load(fh)
    except (ValueError, OSError):
        return None


def _write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(obj, fh, indent=2)
        fh.write("\n")


def _now_stamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")


# --- environment ------------------------------------------------------------

def parse_env_text(text):
    """Parse a .env body into a plain KEY=VALUE dict.

    Comments, blank lines, an optional `export` prefix, and matched surrounding
    quotes. Variable interpolation like ${NAME} is left literal.
    """
    out = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        out[key] = val
    return out


def build_env(adapter, env_file_text, session_dir):
    """The explicit child environment for every eval process.

    Precedence: the adapter's env_file (if any), then the adapter's `env` map,
    then the pointers every process needs (session dir, sidecar URL, corpus).
    The env_file is the only place a real credential can enter, and it enters
    the child environment only.
    """
    env = parse_env_text(env_file_text or "")
    env.update({k: str(v) for k, v in adapter.get("env", {}).items()})
    ports = adapter["ports"]
    env["EVALENV_SESSION_DIR"] = session_dir
    env["EVALENV_SIDECAR"] = "http://%s:%d" % (LOOPBACK, ports["sidecar"])
    env["EVALENV_VENDOR"] = "http://%s:%d" % (LOOPBACK, ports["vendor"])
    env["EVALENV_CORPUS"] = os.path.join(adapter["_dir"], "corpus")
    env["EVALENV_CONNECTOR"] = adapter["connector"]
    return env


def _env_file_text(adapter):
    path = adapter.get("env_file")
    if not path:
        return ""
    path = os.path.expanduser(path)
    if not os.path.isabs(path):
        path = os.path.join(adapter["_dir"], path)
    if not os.path.exists(path):
        raise RuntimeError("adapter env_file not found: %s" % path)
    return _read(path)


def _child_env(adapter, session_dir):
    env = os.environ.copy()
    env.update(build_env(adapter, _env_file_text(adapter), session_dir))
    return env


def scrub(obj, secret_keys, secret_values):
    """Remove secret names and values from anything about to be printed."""
    if isinstance(obj, dict):
        return {k: ("<redacted>" if k in secret_keys else scrub(v, secret_keys, secret_values))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [scrub(v, secret_keys, secret_values) for v in obj]
    if isinstance(obj, str):
        for value in secret_values:
            if value and value in obj:
                obj = obj.replace(value, "<redacted>")
        return obj
    return obj


def _secret_values(adapter, env):
    return [env.get(k) for k in adapter.get("secret_env_keys", []) if env.get(k)]


# --- session files ----------------------------------------------------------

def sessions_root():
    return os.environ.get("EVALENV_SESSIONS_ROOT") or os.path.join(_ROOT, "sessions")


def current_path(sessions_dir):
    return os.path.join(sessions_dir, "current")


def write_current(sessions_dir, stamp):
    os.makedirs(sessions_dir, exist_ok=True)
    with open(current_path(sessions_dir), "w") as fh:
        fh.write(stamp + "\n")


def read_current(sessions_dir):
    path = current_path(sessions_dir)
    if not os.path.exists(path):
        return None
    val = _read(path).strip()
    return val or None


def pids_path(session_dir):
    return os.path.join(session_dir, "pids.json")


def write_pids(session_dir, procs):
    # Only pid and a command-line marker per role. No environment, so no secret
    # can land here.
    _write_json(pids_path(session_dir),
                {role: {"pid": int(p["pid"]), "match": p["match"]} for role, p in procs.items() if p})


def read_pids(session_dir):
    return _read_json(pids_path(session_dir)) or {}


# --- process control --------------------------------------------------------

def _is_alive(pid):
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError):
        return False


def _cmdline(pid):
    try:
        return subprocess.run(["ps", "-p", str(pid), "-o", "command="],
                              capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def owned(pid, match):
    """True only when the pid is alive and its command line still carries the
    marker recorded at start. A recycled pid never matches."""
    return _is_alive(pid) and bool(match) and match in _cmdline(pid)


def _terminate(pid, hard_after=10):
    if not _is_alive(pid):
        return
    try:
        os.kill(int(pid), 15)
    except (OSError, ValueError):
        return
    deadline = time.time() + hard_after
    while time.time() < deadline:
        if not _is_alive(pid):
            return
        time.sleep(0.2)
    try:
        os.kill(int(pid), 9)
    except (OSError, ValueError):
        pass


def terminate_owned(entry, hard_after=10):
    """Kill the recorded process only if it is still the process we started."""
    if not entry:
        return False
    if not owned(entry.get("pid"), entry.get("match")):
        return False
    _terminate(entry["pid"], hard_after)
    return True


def _port_free(port):
    try:
        with socket.create_connection((LOOPBACK, port), timeout=0.5):
            return False
    except OSError:
        return True


def _wait_port(port, timeout=25):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _port_free(port):
            return True
        time.sleep(0.2)
    return False


def _spawn(argv, env, cwd, log_path):
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    log = open(log_path, "ab")
    proc = subprocess.Popen(argv, env=env, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL)
    return proc.pid


def _log(session_dir, name):
    return os.path.join(session_dir, "run", name + ".log")


def _engine_processes(adapter):
    stub = os.path.join(adapter["_dir"], adapter.get("stub", "stub.py"))
    return [
        {"role": "stub", "argv": [sys.executable, stub], "cwd": _ROOT,
         "port": adapter["ports"]["vendor"]},
        {"role": "sidecar", "argv": [sys.executable, os.path.join(_HERE, "sidecar.py"),
                                     "--connector", adapter["connector"]],
         "cwd": _ROOT, "port": adapter["ports"]["sidecar"]},
    ]


def _plan(adapter, hooks, env, session_dir):
    plan = _engine_processes(adapter)
    if hooks.has("processes"):
        plan.extend(hooks.call("processes", adapter, env, session_dir))
    return plan


def _start_all(plan, env, session_dir, prior):
    procs = dict(prior)
    started = []
    for spec in plan:
        role = spec["role"]
        if owned(procs.get(role, {}).get("pid"), procs.get(role, {}).get("match")):
            continue
        if spec.get("port") and not _port_free(spec["port"]):
            raise RuntimeError("port %d for %s is already in use; nothing was started for it"
                               % (spec["port"], role))
        match = spec.get("match") or os.path.basename(spec["argv"][1] if len(spec["argv"]) > 1
                                                      else spec["argv"][0])
        pid = _spawn(spec["argv"], env, spec.get("cwd", _ROOT), _log(session_dir, role))
        procs[role] = {"pid": pid, "match": match}
        started.append(role)
    write_pids(session_dir, procs)
    return procs, started


def _wait_all(plan):
    missing = []
    for spec in plan:
        if spec.get("port") and not _wait_port(spec["port"]):
            missing.append(spec["role"])
    return missing


# --- sidecar / stub HTTP ----------------------------------------------------

def _sidecar_base(adapter):
    return "http://%s:%d" % (LOOPBACK, adapter["ports"]["sidecar"])


def _stub_base(adapter):
    return "http://%s:%d" % (LOOPBACK, adapter["ports"]["vendor"])


def _http_json(url, method="GET", body=None, timeout=10):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode()
    return json.loads(raw) if raw.strip() else {}


def _emit(adapter, kind, rec, user, data):
    return _http_json(_sidecar_base(adapter) + "/emit", "POST",
                      {"kind": kind, "rec": rec, "user": user, "data": data})


# --- snapshot ---------------------------------------------------------------

_MAX_STR = 20000


def _truncate(obj):
    if isinstance(obj, dict):
        out = {}
        for key, val in obj.items():
            if isinstance(val, str) and len(val) > _MAX_STR:
                out[key] = val[:_MAX_STR]
                out[key + "_truncated"] = True
            else:
                out[key] = _truncate(val)
        return out
    if isinstance(obj, list):
        return [_truncate(v) for v in obj]
    return obj


def build_snapshot(session, events, last_id):
    return {
        "session": session,
        "events": [_truncate(ev) for ev in events],
        "frozen_at_id": last_id,
        "schema_version": "1",
        "renderer_version": "3",
    }


def _snapshot_json(snap):
    # Escape every "<" as \u003c so no string value can close the <script>
    # element it is inlined into or open a new one. JSON.parse restores the
    # character; the page reads the slot with textContent, never as HTML.
    return json.dumps(snap).replace("<", "\\u003c")


def inline_snapshot(html, snap):
    open_tag = '<script id="evalenv-data" type="application/json">'
    start = html.index(open_tag) + len(open_tag)
    end = html.index("</script>", start)
    return html[:start] + _snapshot_json(snap) + html[end:]


def _read_events(session_dir, upto=None):
    events = []
    for ev in evals.read_events(session_dir):
        if upto is not None and ev.get("id", 0) > upto:
            break
        events.append(ev)
    return events


next_finding_id = evals.next_finding_id


def render_findings_md(finding_events):
    lines = ["# Findings", ""]
    for ev in finding_events:
        d = ev.get("data", {})
        lines.append("## %s: %s" % (d.get("finding_id", "F-000"), d.get("title", "")))
        lines.append("")
        lines.append("- **Severity:** %s" % d.get("severity", ""))
        lines.append("- **Expected:** %s" % d.get("expected", ""))
        lines.append("- **Actual:** %s" % d.get("actual", ""))
        lines.append("- **Repro:** %s" % d.get("repro", ""))
        lines.append("")
    return "\n".join(lines)


# --- flag parsing -----------------------------------------------------------

def _pop_opt(args, name):
    if name in args:
        i = args.index(name)
        val = args[i + 1]
        del args[i:i + 2]
        return val
    return None


def _pop_flag(args, name):
    if name in args:
        args.remove(name)
        return True
    return False


# --- verbs ------------------------------------------------------------------

def _bring_up(adapter, hooks, stamp, session_dir, prior, do_seed):
    env = _child_env(adapter, session_dir)
    plan = _plan(adapter, hooks, env, session_dir)
    procs, started = _start_all(plan, env, session_dir, prior)
    missing = _wait_all(plan)
    if missing:
        return {"ok": False, "error": "processes failed to bind: " + ", ".join(missing),
                "stamp": stamp, "logs": os.path.join(session_dir, "run")}
    seeded = hooks.call("seed", adapter, env, session_dir) if (do_seed and hooks.has("seed")) else {}
    result = {
        "ok": True, "stamp": stamp, "session_dir": session_dir,
        "pids": {r: p["pid"] for r, p in procs.items()}, "started": started,
        "vendor_url": _stub_base(adapter) + adapter.get("vendor_page", "/settings"),
        "monitor_url": _sidecar_base(adapter) + "/",
    }
    if adapter["ports"].get("app"):
        result["app_url"] = "http://%s:%d/" % (LOOPBACK, adapter["ports"]["app"])
    if seeded:
        result["seed"] = seeded
    return result


def verb_up(adapter, hooks, args):
    sroot = sessions_root()
    stamp = read_current(sroot)
    if stamp:
        session_dir = os.path.join(sroot, stamp)
        procs = read_pids(session_dir)
        if procs and all(owned(p.get("pid"), p.get("match")) for p in procs.values()):
            return {"ok": True, "already_running": True, "stamp": stamp,
                    "session_dir": session_dir,
                    "pids": {r: p["pid"] for r, p in procs.items()},
                    "vendor_url": _stub_base(adapter) + adapter.get("vendor_page", "/settings"),
                    "monitor_url": _sidecar_base(adapter) + "/",
                    "app_url": ("http://%s:%d/" % (LOOPBACK, adapter["ports"]["app"])
                                if adapter["ports"].get("app") else None)}
        # A partial session: restart only the dead roles in place so the session
        # folder, its events, and the sidecar id counter carry through.
        return _bring_up(adapter, hooks, stamp, session_dir, procs, do_seed=False)

    stamp = _now_stamp()
    session_dir = os.path.join(sroot, stamp)
    os.makedirs(session_dir, exist_ok=True)
    write_current(sroot, stamp)
    return _bring_up(adapter, hooks, stamp, session_dir, {}, do_seed=True)


def verb_status(adapter, hooks, args):
    sroot = sessions_root()
    stamp = read_current(sroot)
    if not stamp:
        return {"ok": False, "error": "no active session"}
    session_dir = os.path.join(sroot, stamp)
    procs = read_pids(session_dir)
    report = {}
    for role, entry in procs.items():
        report[role] = {"pid": entry.get("pid"),
                        "alive": owned(entry.get("pid"), entry.get("match"))}
    env = _child_env(adapter, session_dir)
    effective = {}
    if hooks.has("status"):
        effective = hooks.call("status", adapter, env, session_dir) or {}
    procs_ok = bool(report) and all(r["alive"] for r in report.values())
    return {"ok": procs_ok and bool(effective.get("ok", True)), "stamp": stamp,
            "session_dir": session_dir, "processes": report, "effective": effective}


def verb_reset(adapter, hooks, args):
    sroot = sessions_root()
    stamp = read_current(sroot)
    if not stamp:
        return {"ok": False, "error": "no active session; run up first"}
    disposable = adapter.get("disposable") or {}
    # Fail closed: a reset deletes data, so the adapter must say in writing
    # that the data it targets is disposable, and must ship the hook that
    # knows what to delete. Nothing is touched otherwise.
    if disposable.get("confirmed") is not True:
        return {"ok": False, "error": "reset refused: adapter.json disposable.confirmed is not true"}
    if not hooks.has("reset"):
        return {"ok": False, "error": "reset refused: adapter has no reset hook"}

    old_dir = os.path.join(sroot, stamp)
    old_procs = read_pids(old_dir)
    new_stamp = _now_stamp()
    new_dir = os.path.join(sroot, new_stamp)
    os.makedirs(new_dir, exist_ok=True)
    env = _child_env(adapter, new_dir)

    # Stop everything first so no worker mutates data mid-reset.
    for role in list(old_procs):
        terminate_owned(old_procs[role], hard_after=15)
    reset_info = hooks.call("reset", adapter, env, old_dir, new_dir) or {}
    write_current(sroot, new_stamp)

    plan = _plan(adapter, hooks, env, new_dir)
    procs, started = _start_all(plan, env, new_dir, {})
    missing = _wait_all(plan)
    if missing:
        return {"ok": False, "error": "processes failed to bind: " + ", ".join(missing),
                "stamp": new_stamp}
    seeded = hooks.call("seed", adapter, env, new_dir) if hooks.has("seed") else {}
    _emit(adapter, "action.reset", None, None,
          {"args": ["reset"], "result": {"stamp": new_stamp, "reset": reset_info, "seed": seeded}})
    return {"ok": True, "stamp": new_stamp, "previous": stamp, "session_dir": new_dir,
            "pids": {r: p["pid"] for r, p in procs.items()}, "reset": reset_info, "seed": seeded}


def _stub_action(adapter, path, body, kind, rec, user, argv):
    resp = _http_json(_stub_base(adapter) + path, "POST", body)
    _emit(adapter, kind, rec, user, {"args": argv, "result": resp})
    return resp


def verb_arrive(adapter, hooks, args):
    account = _pop_opt(args, "--account")
    no_webhook = _pop_flag(args, "--no-webhook")
    if not args:
        return {"ok": False, "error": "arrive requires a rec_id"}
    rec_id = args[0]
    body = {"rec_id": rec_id, "webhook": not no_webhook}
    if account:
        body["account"] = account
    resp = _stub_action(adapter, "/_admin/arrive", body, "action.arrive", rec_id, account,
                        ["arrive", rec_id])
    return {"ok": bool(resp.get("ok", True)), "result": resp}


def verb_backfill(adapter, hooks, args):
    account = _pop_opt(args, "--account")
    if not args:
        return {"ok": False, "error": "backfill requires a count"}
    n = int(args[0])
    body = {"n": n}
    if account:
        body["account"] = account
    resp = _stub_action(adapter, "/_admin/backfill", body, "action.backfill", None, account,
                        ["backfill", str(n)])
    return {"ok": bool(resp.get("ok", True)), "result": resp}


def verb_scenario(adapter, hooks, args):
    if not args:
        return {"ok": False, "error": "scenario requires a name"}
    name = args[0]
    known = adapter.get("scenarios") or []
    if known and name not in known:
        return {"ok": False, "error": "unknown scenario %s; adapter knows: %s" % (name, ", ".join(known))}
    resp = _stub_action(adapter, "/_admin/scenario", {"scenario": name},
                        "action.scenario", None, None, ["scenario", name])
    return {"ok": bool(resp.get("ok", True)), "result": resp}


def verb_eval(adapter, hooks, args):
    rec_id = args[0] if args else None
    sroot = sessions_root()
    stamp = read_current(sroot)
    if not stamp:
        return {"ok": False, "error": "no active session"}
    session_dir = os.path.join(sroot, stamp)
    # Hooks that read the app run with the same environment the app got.
    os.environ.update(build_env(adapter, "", session_dir))
    results = evals.run_rules(session_dir, adapter, rec_id, hooks=hooks)
    rules = [ev for ev in results if ev.get("kind") == "eval.rule"]
    passed = sum(1 for ev in rules if ev["data"]["pass"])
    failed = [{"rec": ev["rec"], "check": ev["data"]["check"], "detail": ev["data"]["detail"],
               "evidence": ev["data"]["evidence"]}
              for ev in rules if not ev["data"]["pass"]]
    return {"ok": not failed, "checks": len(rules), "passed": passed, "failed": failed}


def verb_judge(adapter, hooks, args):
    verdict = _pop_opt(args, "--verdict")
    reason = _pop_opt(args, "--reason")
    evidence_raw = _pop_opt(args, "--evidence")
    if not args or verdict not in ("pass", "fail"):
        return {"ok": False, "error": "judge requires <rec_id> --verdict pass|fail --reason ..."}
    rec_id = args[0]
    evidence = [int(x) for x in evidence_raw.split(",")] if evidence_raw else []
    emit = lambda kind, rec, user, data: _emit(adapter, kind, rec, user, data)
    ev = evals.judge(emit, rec_id, verdict, reason, evidence)
    return {"ok": True, "event": ev}


def verb_finding(adapter, hooks, args):
    expected = _pop_opt(args, "--expected")
    actual = _pop_opt(args, "--actual")
    repro = _pop_opt(args, "--repro")
    severity = _pop_opt(args, "--severity") or "med"
    if not args:
        return {"ok": False, "error": "finding requires a title"}
    title = args[0]
    sroot = sessions_root()
    stamp = read_current(sroot)
    if not stamp:
        return {"ok": False, "error": "no active session"}
    events = _read_events(os.path.join(sroot, stamp))
    emit = lambda kind, rec, user, data: _emit(adapter, kind, rec, user, data)
    finding_id, ev = evals.finding(emit, events, title, expected, actual, repro, severity)
    return {"ok": True, "finding_id": finding_id, "event": ev}


def verb_snapshot(adapter, hooks, args):
    sroot = sessions_root()
    stamp = read_current(sroot)
    if not stamp:
        return {"ok": False, "error": "no active session"}
    session_dir = os.path.join(sroot, stamp)
    session = _http_json(_sidecar_base(adapter) + "/session")
    last_id = session.get("last_id", 0)
    events = _read_events(session_dir, upto=last_id)
    snap = build_snapshot(session, events, last_id)

    html = _read(os.path.join(_HERE, "monitor.html"))
    snap_path = os.path.join(session_dir, "snapshot.html")
    with open(snap_path, "w") as fh:
        fh.write(inline_snapshot(html, snap))

    findings = [ev for ev in events if ev.get("kind") == "finding"]
    findings_path = os.path.join(session_dir, "findings.md")
    with open(findings_path, "w") as fh:
        fh.write(render_findings_md(findings))

    return {"ok": True, "snapshot": snap_path, "findings": findings_path,
            "frozen_at_id": last_id, "events": len(events)}


def verb_down(adapter, hooks, args):
    sroot = sessions_root()
    stamp = read_current(sroot)
    session_dir = os.path.join(sroot, stamp) if stamp else None
    procs = read_pids(session_dir) if session_dir else {}
    stopped, skipped = [], []
    for role, entry in procs.items():
        (stopped if terminate_owned(entry, hard_after=10) else skipped).append(role)
    cleanup = {}
    if session_dir and hooks.has("down"):
        env = _child_env(adapter, session_dir)
        cleanup = hooks.call("down", adapter, env, session_dir) or {}
    if session_dir:
        write_pids(session_dir, {})
    if stamp:
        os.remove(current_path(sroot))
    return {"ok": True, "stamp": stamp, "stopped": stopped, "skipped": skipped,
            "cleanup": cleanup, "session_dir": session_dir}


VERBS = {
    "up": verb_up, "down": verb_down, "status": verb_status, "reset": verb_reset,
    "arrive": verb_arrive, "backfill": verb_backfill, "scenario": verb_scenario,
    "eval": verb_eval, "judge": verb_judge, "finding": verb_finding,
    "snapshot": verb_snapshot,
}


def main(argv):
    if len(argv) < 2:
        print(json.dumps({"ok": False, "error": "usage: evalenv.py <connector> <verb> [args]",
                          "verbs": sorted(VERBS)}))
        return 2
    connector, verb = argv[0], argv[1]
    args = list(argv[2:])
    handler = VERBS.get(verb)
    if not handler:
        print(json.dumps({"ok": False, "error": "unknown verb: " + verb, "verbs": sorted(VERBS)}))
        return 2
    secret_keys, secret_values = [], []
    try:
        adapter = adapter_mod.load_adapter(connector)
        secret_keys = adapter.get("secret_env_keys", [])
        try:
            secret_values = _secret_values(adapter, parse_env_text(_env_file_text(adapter)))
        except RuntimeError:
            secret_values = []
        hooks = adapter_mod.load_hooks(adapter)
        result = handler(adapter, hooks, args)
    except Exception as err:  # one JSON object out, always
        result = {"ok": False, "error": str(err)}
    print(json.dumps(scrub(result, set(secret_keys), secret_values)))
    return 0 if result.get("ok", False) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
