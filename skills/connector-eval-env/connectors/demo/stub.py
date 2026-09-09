"""Fake recorder vendor for the demo adapter.

Stands in for a third-party recording service: a REST API keyed by bearer
token, a webhook registration endpoint, signed webhook deliveries with retries,
a plain HTML settings page that plays the vendor dashboard, and an admin surface
the CLI drives (`arrive`, `backfill`, `scenario`, `reset`). Scenarios inject the
failure modes a connector must survive.

Run it directly to serve on the adapter's vendor port:

    python3 connectors/demo/stub.py

Importing this file starts no server. Every event goes to the sidecar `/emit`;
if the sidecar is down the stub logs to stderr and carries on.
"""
import hashlib
import hmac
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

_HERE = os.path.dirname(os.path.abspath(__file__))
ADAPTER_PATH = os.path.join(_HERE, "adapter.json")
DEFAULT_CORPUS = os.path.join(_HERE, "corpus")
BIND = "127.0.0.1"

LIST_KEYS = ("id", "title", "recording_at", "duration", "state")
MAX_ATTEMPTS = 3
BACKOFFS_S = (1, 2)
SIG_HEADER = "X-Demo-Signature"
TS_HEADER = "X-Demo-Timestamp"


# --- pure helpers -----------------------------------------------------------

def sign(secret, timestamp, body):
    """HMAC-SHA256 over "{timestamp}.{body}", lowercase hex."""
    return hmac.new(secret.encode(), (timestamp + "." + body).encode(), hashlib.sha256).hexdigest()


def plan_deliveries(scenario, rec_id):
    """The ordered webhook sends for one arrival, including reordering and dups.

    stale-sig emits a millisecond stamp 600 s in the past to trip the app's
    freshness window; everything else emits a fresh stamp.
    """
    now_ms = int(time.time() * 1000)
    timestamp = str(now_ms - 600 * 1000) if scenario == "stale-sig" else str(now_ms)
    created = {"event": "recording.created", "timestamp": timestamp}
    completed = {"event": "transcription.completed", "timestamp": timestamp}
    if scenario == "out-of-order":
        return [dict(completed), dict(created)]
    if scenario == "dup":
        return [dict(created), dict(completed), dict(completed)]
    return [dict(created), dict(completed)]


def _webhook_body(rec_id, event):
    return json.dumps({"event": event, "recording": {"id": rec_id}}, separators=(",", ":"))


def _post_webhook(url, raw, timestamp, signature):
    req = urllib.request.Request(url, data=raw, method="POST", headers={
        "Content-Type": "application/json", TS_HEADER: timestamp, SIG_HEADER: signature})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status
    except urllib.error.HTTPError as err:
        err.close()
        return err.code
    except Exception:
        return 0


def deliver_one(url, secret, event, rec_id, timestamp, emit=None):
    """Sign one webhook and POST it, retrying on non-2xx up to MAX_ATTEMPTS."""
    body = _webhook_body(rec_id, event)
    raw = body.encode()
    signature = sign(secret, timestamp, body)
    results = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if emit:
            emit("webhook.sent", rec_id, {"event": event, "attempt": attempt, "url": url,
                                          "timestamp_header": timestamp, "signature_valid": True})
        started = time.time()
        status = _post_webhook(url, raw, timestamp, signature)
        latency_ms = int((time.time() - started) * 1000)
        if emit:
            emit("webhook.result", rec_id, {"event": event, "attempt": attempt,
                                            "status": status, "latency_ms": latency_ms})
        results.append({"attempt": attempt, "status": status, "signature": signature})
        if 200 <= status < 300:
            break
        if attempt < MAX_ATTEMPTS:
            time.sleep(BACKOFFS_S[attempt - 1])
    return results


def _parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- state ------------------------------------------------------------------

class StubState:
    """Accounts, scenario, deliveries, and per-account visibility.

    Webhook settings persist to <session>/stub-state.json so a stub restart
    mid-session never asks the operator to reconnect.
    """

    def __init__(self, users, recs, order):
        self.recs = recs
        self.order = order
        self._users = users
        self.lock = threading.Lock()
        session_dir = os.environ.get("EVALENV_SESSION_DIR")
        self.path = os.path.join(session_dir, "stub-state.json") if session_dir else None
        self.reset()
        self.load()

    def save(self):
        if not self.path:
            return
        snapshot = {"scenario": self.scenario, "accounts": {
            slug: {k: a[k] for k in ("webhook_url", "webhook_secret", "revoked", "visible")}
            for slug, a in self.accounts.items()}}
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w") as fh:
                json.dump(snapshot, fh)
            os.replace(tmp, self.path)
        except OSError as err:
            sys.stderr.write("stub: could not persist state: %s\n" % err)

    def load(self):
        if not self.path:
            return
        try:
            with open(self.path) as fh:
                snapshot = json.load(fh)
        except (OSError, ValueError):
            return
        self.scenario = snapshot.get("scenario", "off")
        for slug, saved in snapshot.get("accounts", {}).items():
            if slug in self.accounts:
                self.accounts[slug].update(saved)

    def reset(self):
        self.scenario = "off"
        self.delivered = []
        self.failed_once = set()
        self.accounts = {}
        self.key_to_slug = {}
        for user in self._users:
            slug = user["slug"]
            self.accounts[slug] = {
                "slug": slug, "name": user.get("name", slug), "email": user.get("email", ""),
                "api_key": user["api_key"], "webhook_url": "", "webhook_secret": "",
                "revoked": False, "visible": {},
            }
            self.key_to_slug[user["api_key"]] = slug

    def account_for_key(self, key):
        slug = self.key_to_slug.get(key)
        return self.accounts.get(slug) if slug else None

    def set_scenario(self, scenario):
        previous = self.scenario
        self.scenario = scenario
        for account in self.accounts.values():
            account["revoked"] = scenario == "revoke-key"
        self.save()
        return previous

    def backfill(self, account, n):
        now = datetime.now(timezone.utc)
        ids = self.order[:n]
        for i, rec_id in enumerate(ids):
            rec_at = now - timedelta(days=7.0 * (i + 1) / (len(ids) + 1))
            account["visible"][rec_id] = _iso(rec_at)
        self.save()
        return ids

    def make_visible_now(self, account, rec_id):
        account["visible"][rec_id] = _iso(datetime.now(timezone.utc))
        self.save()

    def record_delivered(self, event, rec_id, attempt, status):
        with self.lock:
            self.delivered.append({"event": event, "rec": rec_id, "attempt": attempt,
                                   "status": status, "time": _iso(datetime.now(timezone.utc))})

    def emit(self, kind, rec, data, user=None):
        base = os.environ.get("EVALENV_SIDECAR", "http://127.0.0.1:8230").rstrip("/")
        payload = json.dumps({"kind": kind, "rec": rec, "user": user, "data": data}).encode()
        req = urllib.request.Request(base + "/emit", data=payload, method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=2):
                pass
        except Exception as err:
            sys.stderr.write("evalenv sidecar unreachable, dropping %s: %s\n" % (kind, err))


def _run_deliveries(state, account, rec_id):
    scenario = state.scenario
    time.sleep(0.2)
    url = account.get("webhook_url")
    secret = account.get("webhook_secret") or ""
    if not url:
        state.emit("webhook.result", rec_id, {"event": None, "attempt": 0, "status": 0,
                                              "latency_ms": 0, "error": "no webhook configured"},
                   user=account["slug"])
        return
    slug = account["slug"]
    emit = lambda kind, rec, data: state.emit(kind, rec, data, user=slug)
    for delivery in plan_deliveries(scenario, rec_id):
        results = deliver_one(url, secret, delivery["event"], rec_id, delivery["timestamp"], emit=emit)
        for res in results:
            state.record_delivered(delivery["event"], rec_id, res["attempt"], res["status"])


# --- HTML ---------------------------------------------------------------------

def _esc(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _settings_html(state):
    rows = []
    for entry in state.delivered[-50:]:
        rows.append("<tr>" + "".join("<td>%s</td>" % _esc(entry[k])
                                      for k in ("event", "rec", "attempt", "status", "time")) + "</tr>")
    table = "".join(rows) or "<tr><td colspan='5'>none yet</td></tr>"
    forms = []
    for account in state.accounts.values():
        forms.append(
            "<section><h2>%s</h2><p>API key: <code>%s</code>%s</p>"
            "<form method='post' action='/settings'>"
            "<input type='hidden' name='account' value='%s'>"
            "<label>Webhook URL <input name='webhook_url' value='%s' size='60'></label><br>"
            "<label>Webhook secret <input name='webhook_secret' value='%s' size='40'></label><br>"
            "<button type='submit'>Save</button></form></section>"
            % (_esc(account["name"]), _esc(account["api_key"]),
               " (revoked)" if account["revoked"] else "", _esc(account["slug"]),
               _esc(account["webhook_url"]), _esc(account["webhook_secret"])))
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>Demo recorder (fake vendor)</title>"
        "<style>body{font-family:system-ui,sans-serif;max-width:760px;margin:2rem auto;padding:0 1rem}"
        "section{border:1px solid #ddd;border-radius:8px;padding:1rem;margin:1rem 0}"
        "table{border-collapse:collapse;width:100%%}td,th{border:1px solid #ddd;padding:4px 8px;text-align:left}"
        "code{background:#f3f3f3;padding:2px 4px;border-radius:4px}</style></head><body>"
        "<h1>Demo recorder dashboard (fake vendor)</h1>"
        "<p>Scenario: <code>%s</code>. Connect an account from the demo app with its API key, "
        "or paste a webhook URL and secret here by hand.</p>%s"
        "<h2>Delivered events</h2>"
        "<table><tr><th>event</th><th>rec</th><th>attempt</th><th>status</th><th>time</th></tr>%s</table>"
        "</body></html>") % (_esc(state.scenario), "".join(forms), table)


# --- HTTP handler -------------------------------------------------------------

class VendorHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    @property
    def state(self):
        return self.server.state

    def log_message(self, fmt, *args):
        pass

    def _send_json(self, code, body):
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _send_html(self, code, html):
        raw = html.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        return self.rfile.read(length) if length else b""

    def _read_json(self):
        try:
            return json.loads(self._read_body() or b"{}")
        except ValueError:
            return {}

    # -- GET --

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/settings":
            return self._send_html(200, _settings_html(self.state))
        if parsed.path == "/_admin/state":
            return self._send_json(200, {
                "scenario": self.state.scenario,
                "accounts": [{k: a[k] for k in ("slug", "webhook_url", "revoked")}
                             for a in self.state.accounts.values()],
                "delivered": self.state.delivered})
        if "/recordings" in parsed.path:
            return self._handle_api(parsed)
        return self._send_json(404, {"success": False, "error": "not found"})

    def _handle_api(self, parsed):
        started = time.time()
        scenario = self.state.scenario
        account = self._authenticate()
        detail = re.match(r"^/api/v1/recordings/([^/?]+)$", parsed.path)
        rec_id = detail.group(1) if detail else None
        if scenario == "slow-fetch" and detail:
            time.sleep(2.5)
        status, body = self._api_response(parsed, account, rec_id)
        self._send_json(status, body)
        self.state.emit("api.request", rec_id, {
            "path": parsed.path, "method": "GET", "status": status,
            "latency_ms": int((time.time() - started) * 1000),
            "account": account["slug"] if account else None,
        }, user=account["slug"] if account else None)

    def _authenticate(self):
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        account = self.state.account_for_key(auth[len("Bearer "):].strip())
        if account is None or account["revoked"]:
            return None
        return account

    def _api_response(self, parsed, account, rec_id):
        if account is None:
            return 401, {"success": False, "error": "unauthorized"}
        if rec_id is None:
            query = parse_qs(parsed.query)
            start = _parse_dt(query.get("start_date", [None])[0])
            end = _parse_dt(query.get("end_date", [None])[0])
            return 200, {"success": True, "data": self._list_rows(account, start, end)}
        envelope = self.state.recs.get(rec_id)
        if not envelope:
            return 404, {"success": False, "error": "not found"}
        # retry-500: the first detail fetch of each recording fails once.
        if self.state.scenario == "retry-500" and rec_id not in self.state.failed_once:
            self.state.failed_once.add(rec_id)
            return 500, {"success": False, "error": "transient upstream error"}
        data = dict(envelope["data"])
        if rec_id in account["visible"]:
            data["recording_at"] = account["visible"][rec_id]
        return 200, {"success": True, "data": data}

    def _list_rows(self, account, start, end):
        rows = []
        for rec_id, rec_at_iso in account["visible"].items():
            envelope = self.state.recs.get(rec_id)
            if not envelope:
                continue
            rec_at = _parse_dt(rec_at_iso)
            if start and rec_at and rec_at < start:
                continue
            if end and rec_at and rec_at > end:
                continue
            data = dict(envelope["data"])
            data["recording_at"] = rec_at_iso
            rows.append((rec_at, {k: data.get(k) for k in LIST_KEYS}))
        floor = datetime.min.replace(tzinfo=timezone.utc)
        rows.sort(key=lambda pair: pair[0] or floor, reverse=True)
        return [row for _, row in rows]

    # -- POST --

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/settings":
            return self._save_settings()
        if parsed.path == "/api/v1/webhooks":
            return self._register_webhook()
        if parsed.path == "/_admin/scenario":
            return self._admin_scenario()
        if parsed.path == "/_admin/arrive":
            return self._admin_arrive()
        if parsed.path == "/_admin/backfill":
            return self._admin_backfill()
        if parsed.path == "/_admin/reset":
            self.state.reset()
            self.state.save()
            return self._send_json(200, {"ok": True})
        return self._send_json(404, {"success": False, "error": "not found"})

    def _account_or_first(self, slug):
        if slug and slug in self.state.accounts:
            return self.state.accounts[slug]
        return next(iter(self.state.accounts.values()))

    def _save_settings(self):
        form = parse_qs(self._read_body().decode())
        slug = form.get("account", [""])[0]
        account = self.state.accounts.get(slug)
        if account:
            account["webhook_url"] = form.get("webhook_url", [""])[0]
            account["webhook_secret"] = form.get("webhook_secret", [""])[0]
            self.state.save()
        self.send_response(303)
        self.send_header("Location", "/settings")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _register_webhook(self):
        """The API form of the settings page: the app registers its own URL and secret."""
        account = self._authenticate()
        body = self._read_json()
        if account is None:
            return self._send_json(401, {"success": False, "error": "unauthorized"})
        url = body.get("url", "")
        if not urlparse(url).hostname in ("127.0.0.1", "localhost"):
            return self._send_json(400, {"success": False, "error": "webhook url must be loopback"})
        account["webhook_url"] = url
        account["webhook_secret"] = body.get("secret", "")
        self.state.save()
        self._send_json(200, {"success": True, "data": {"url": url, "account": account["slug"]}})

    def _admin_scenario(self):
        body = self._read_json()
        previous = self.state.set_scenario(body.get("scenario", "off"))
        self.state.emit("scenario.changed", None, {"scenario": self.state.scenario, "previous": previous})
        self._send_json(200, {"ok": True, "scenario": self.state.scenario})

    def _admin_arrive(self):
        body = self._read_json()
        rec_id = body.get("rec_id")
        account = self._account_or_first(body.get("account"))
        if rec_id not in self.state.recs:
            return self._send_json(404, {"ok": False, "error": "unknown rec_id"})
        self.state.make_visible_now(account, rec_id)
        if body.get("webhook", True):
            threading.Thread(target=_run_deliveries, args=(self.state, account, rec_id),
                             daemon=True).start()
        self._send_json(200, {"ok": True, "rec_id": rec_id, "account": account["slug"]})

    def _admin_backfill(self):
        body = self._read_json()
        account = self._account_or_first(body.get("account"))
        ids = self.state.backfill(account, int(body.get("n", 0)))
        self._send_json(200, {"ok": True, "visible": ids, "account": account["slug"]})


# --- construction -------------------------------------------------------------

def _load_adapter():
    with open(ADAPTER_PATH) as fh:
        return json.load(fh)


def load_corpus(corpus_dir):
    recs, order = {}, []
    for name in sorted(os.listdir(corpus_dir)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(corpus_dir, name)) as fh:
            doc = json.load(fh)
        data = doc.get("data") if isinstance(doc, dict) else None
        if not isinstance(data, dict) or not isinstance(data.get("id"), str):
            continue
        recs[data["id"]] = doc
        order.append(data["id"])
    return recs, order


def make_app(port=None):
    adapter = _load_adapter()
    if port is None:
        port = adapter["ports"]["vendor"]
    corpus_dir = os.environ.get("EVALENV_CORPUS", DEFAULT_CORPUS)
    recs, order = load_corpus(corpus_dir)
    server = ThreadingHTTPServer((BIND, port), VendorHandler)
    server.state = StubState(adapter["users"], recs, order)
    return server


if __name__ == "__main__":
    app = make_app()
    sys.stderr.write("demo vendor stub on http://%s:%d\n" % (BIND, app.server_address[1]))
    try:
        app.serve_forever()
    except KeyboardInterrupt:
        pass
