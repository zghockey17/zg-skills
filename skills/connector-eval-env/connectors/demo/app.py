"""The demo app: a tiny notes product with a recorder connector.

This is the "app under test" for the demo adapter. It is deliberately small
but real: a connect step that registers a signed webhook with the vendor, a
webhook receiver that verifies signatures, and a background worker that fetches
each recording, redacts it, summarizes it, and links it, calling the model
through the sidecar proxy at each step. Filed pages land under the session
folder. All state lives in <session>/app-state.json.

One bug is planted on purpose: the webhook receiver does not check whether an
item for the recording already exists, so a duplicate delivery files the same
recording twice. The `dup` scenario exposes it and the evals catch it.

Loopback only. Run it directly:

    python3 connectors/demo/app.py
"""
import hashlib
import hmac
import json
import os
import queue
import secrets
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

BIND = "127.0.0.1"
SIG_HEADER = "X-Demo-Signature"
TS_HEADER = "X-Demo-Timestamp"
TOLERANCE_S = 300
STAGES = ("fetching", "redacting", "summarizing", "linking")
CATEGORIES = ("contact", "health", "compensation")


def _now_ms():
    return int(time.time() * 1000)


class AppState:
    """Everything the app knows, persisted as one JSON file in the session folder."""

    def __init__(self, session_dir):
        self.session_dir = session_dir
        self.path = os.path.join(session_dir, "app-state.json")
        self.lock = threading.Lock()
        self.items = {}
        self.connections = {}
        self.deliveries = {}
        self.transcripts = {}
        self.in_flight = None
        self.next_id = {"item": 1, "connection": 1, "delivery": 1}
        self.load()

    def load(self):
        try:
            with open(self.path) as fh:
                saved = json.load(fh)
        except (OSError, ValueError):
            return
        for key in ("items", "connections", "deliveries", "transcripts", "next_id"):
            if key in saved:
                setattr(self, key, saved[key])

    def save(self):
        snapshot = {"items": self.items, "connections": self.connections,
                    "deliveries": self.deliveries, "transcripts": self.transcripts,
                    "next_id": self.next_id}
        tmp = self.path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(snapshot, fh, indent=1)
        os.replace(tmp, self.path)

    def new_id(self, kind):
        n = self.next_id[kind]
        self.next_id[kind] = n + 1
        return n


class Pipeline:
    """The background worker: one item at a time, four stages, three model calls."""

    def __init__(self, state, vendor_base, model_base, model_key):
        self.state = state
        self.vendor_base = vendor_base
        self.model_base = model_base
        self.model_key = model_key
        self.queue = queue.Queue()
        threading.Thread(target=self._run, daemon=True).start()

    def enqueue(self, item_id):
        self.queue.put(item_id)

    def _run(self):
        while True:
            item_id = self.queue.get()
            try:
                self._process(str(item_id))
            except Exception as err:
                self._set(str(item_id), state="failed", stage=None, last_error=str(err))
            finally:
                self.state.in_flight = None

    def _set(self, item_id, **fields):
        with self.state.lock:
            self.state.items[item_id].update(fields)
            self.state.save()

    def _vendor_get(self, path, api_key):
        req = urllib.request.Request(self.vendor_base + path,
                                     headers={"Authorization": "Bearer " + api_key})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())

    def _fetch(self, item):
        connection = self.state.connections[str(item["connection_id"])]
        last = None
        for attempt in range(3):
            try:
                doc = self._vendor_get("/api/v1/recordings/" + item["external_id"], connection["api_key"])
                return doc["data"]
            except urllib.error.HTTPError as err:
                err.close()
                last = err
                time.sleep(0.5)
        raise RuntimeError("vendor fetch failed after 3 attempts: %s" % last)

    def _chat(self, body):
        raw = json.dumps(body).encode()
        req = urllib.request.Request(self.model_base + "/v1/chat/completions", data=raw, method="POST",
                                     headers={"Content-Type": "application/json",
                                              "Authorization": "Bearer " + self.model_key})
        with urllib.request.urlopen(req, timeout=120) as resp:
            reply = json.loads(resp.read().decode())
        return reply["choices"][0]["message"]["content"]

    def _process(self, item_id):
        item = self.state.items[item_id]
        self.state.in_flight = {"item_id": int(item_id), "rec": item["external_id"]}
        self._set(item_id, state="filing", stage="fetching")
        data = self._fetch(item)
        segments = data.get("transcript") or []
        title = data.get("title") or item["external_id"]
        time.sleep(0.4)

        self._set(item_id, stage="redacting", title=title)
        lines = ["%d [%s]: %s" % (0, "title", title)]
        for k, seg in enumerate(segments):
            lines.append("%d [%s]: %s" % (k + 1, seg.get("speaker", ""), seg.get("text", "")))
        prompt = ("TRANSCRIPT\n" + "\n".join(lines) + "\nCATEGORIES\n" + ", ".join(CATEGORIES)
                  + "\nOUTPUT\nReturn JSON with \"lines\" (line number to redacted text, only "
                  "changed lines) and \"counts\" (category to number of cuts).")
        redaction = json.loads(self._chat({
            "model": "demo-stand-in-1", "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": "You are a redaction assistant. Replace "
                          "sensitive spans with [redacted: category] and keep everything else verbatim."},
                         {"role": "user", "content": prompt}]}))
        changed = redaction.get("lines") or {}
        redacted = []
        for k, seg in enumerate(segments):
            text = changed.get(str(k + 1), seg.get("text", ""))
            redacted.append("%s: %s" % (seg.get("speaker", ""), text))
        words = "\n".join(redacted)
        counts = redaction.get("counts") or {}
        self.state.transcripts[item["external_id"]] = words
        self._set(item_id, redaction_counts=json.dumps(counts), redacted_words=words)
        time.sleep(0.4)

        self._set(item_id, stage="summarizing")
        summary = self._chat({"model": "demo-stand-in-1", "messages": [
            {"role": "system", "content": "You are a meeting summarization assistant. Write two lines."},
            {"role": "user", "content": "TRANSCRIPT\n" + "\n".join(lines)}]})
        time.sleep(0.4)

        self._set(item_id, stage="linking")
        links = self._chat({"model": "demo-stand-in-1", "messages": [
            {"role": "system", "content": "You are linking a meeting summary to existing notes. "
             "Return JSON with a links array."},
            {"role": "user", "content": summary}]})
        time.sleep(0.4)

        filed_dir = os.path.join(self.state.session_dir, "filed")
        os.makedirs(filed_dir, exist_ok=True)
        page = os.path.join(filed_dir, item["external_id"] + ".md")
        with open(page, "w") as fh:
            fh.write("# %s\n\n%s\n\nLinks: %s\n\n## Transcript (redacted)\n\n%s\n" % (title, summary, links, words))
        self._set(item_id, state="filed", stage=None, filed_path=page)


class AppServer(ThreadingHTTPServer):
    def __init__(self, port, state, pipeline, vendor_base, model_base, model_key):
        super().__init__((BIND, port), AppHandler)
        self.daemon_threads = True
        self.state = state
        self.pipeline = pipeline
        self.vendor_base = vendor_base
        self.model_base = model_base
        self.model_key = model_key
        self.port = port


def _esc(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


PAGE = """<!doctype html><html><head><meta charset='utf-8'><title>Demo notes app</title>
<style>body{font-family:system-ui,sans-serif;max-width:820px;margin:2rem auto;padding:0 1rem;color:#1c1c1c}
section{border:1px solid #ddd;border-radius:8px;padding:1rem;margin:1rem 0}
table{border-collapse:collapse;width:100%%}td,th{border:1px solid #ddd;padding:5px 8px;text-align:left}
code{background:#f3f3f3;padding:2px 4px;border-radius:4px}.pill{padding:2px 8px;border-radius:4px;font-size:12px}
.filed{background:#e3efe4}.filing{background:#dfeaec}.failed{background:#f1dcdc}.discovered{background:#eee}</style></head>
<body><h1>Demo notes app</h1>
<p>A small product with one integration: a wearable recorder. Connect an account, then send recordings
from the terminal with <code>evalenv demo arrive rec_demo_001</code>.</p>
<section><h2>Recorder connection</h2>%s</section>
<section><h2>Recordings</h2><div id='items'>%s</div></section>
<script>
"use strict";
function pill(state){ const s=document.createElement("span"); s.className="pill "+state; s.textContent=state; return s; }
function render(state){
  const box=document.getElementById("items"); box.textContent="";
  const rows=Object.values(state.items||{});
  if(!rows.length){ box.textContent="No recordings yet."; return; }
  const t=document.createElement("table"); const h=document.createElement("tr");
  for(const k of ["id","recording","title","state","stage","error"]){ const th=document.createElement("th"); th.textContent=k; h.appendChild(th); }
  t.appendChild(h);
  for(const it of rows){ const tr=document.createElement("tr");
    const cells=[it.item_id,it.external_id,it.title||"",null,it.stage||"",it.last_error||""];
    cells.forEach((c,i)=>{ const td=document.createElement("td"); if(i===3) td.appendChild(pill(it.state)); else td.textContent=c==null?"":String(c); tr.appendChild(td); });
    t.appendChild(tr); }
  box.appendChild(t);
}
setInterval(()=>fetch("/_eval/state").then(r=>r.json()).then(render).catch(()=>{}),1000);
</script></body></html>"""


class AppHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    @property
    def state(self):
        return self.server.state

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, raw, content_type):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj).encode(), "application/json")

    def _html(self, html):
        self._send(200, html.encode(), "text/html; charset=utf-8")

    def _redirect(self):
        self.send_response(303)
        self.send_header("Location", "/")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        return self.rfile.read(length) if length else b""

    # -- GET --

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            return self._html(self._page())
        if path == "/_eval/state":
            return self._json(200, self._eval_state())
        if path == "/_eval/in-flight":
            flight = self.state.in_flight
            return self._json(200, {"item_id": flight["item_id"] if flight else None,
                                    "rec": flight["rec"] if flight else None,
                                    "job_reserved": bool(flight), "ambiguous": False})
        if path.startswith("/_eval/transcript/"):
            rec = path.rsplit("/", 1)[1]
            words = self.state.transcripts.get(rec)
            if words is None:
                return self._json(404, {"error": "no transcript"})
            return self._json(200, {"words": words})
        if path == "/_eval/status":
            sidecar = os.environ.get("EVALENV_SIDECAR", "")
            return self._json(200, {
                "model_via_sidecar": self.server.model_base.rstrip("/") == sidecar.rstrip("/"),
                "storage_in_session": os.path.realpath(self.state.session_dir).startswith(
                    os.path.realpath(os.environ.get("EVALENV_SESSION_DIR", "/nonexistent"))),
                "has_model_key": bool(self.server.model_key)})
        return self._json(404, {"error": "not found"})

    def _page(self):
        conn = next(iter(self.state.connections.values()), None)
        if conn:
            block = ("<p>Connected as <b>%s</b>. Webhook URL <code>%s</code>.</p>"
                     "<form method='post' action='/disconnect'><button>Disconnect</button></form>"
                     % (_esc(conn["account"]), _esc(conn["webhook_url"])))
        else:
            block = ("<form method='post' action='/connect'>"
                     "<label>Recorder API key <input name='api_key' size='32' placeholder='from the vendor dashboard'></label> "
                     "<button>Connect</button></form>"
                     "<p>The app registers its webhook with the vendor and generates a signing secret.</p>")
        return PAGE % (block, "No recordings yet.")

    def _eval_state(self):
        with self.state.lock:
            items = {k: {"item_id": v["item_id"], "external_id": v["external_id"], "state": v["state"],
                         "stage": v.get("stage"), "last_error": v.get("last_error"),
                         "redaction_counts": v.get("redaction_counts"), "title": v.get("title"),
                         "redacted_words": v.get("redacted_words")}
                     for k, v in self.state.items.items()}
            connections = {k: {"connection_id": v["connection_id"], "status": v["status"],
                               "review_before_filing": False,
                               "redact": {c: True for c in CATEGORIES}}
                           for k, v in self.state.connections.items()}
            deliveries = {k: dict(v) for k, v in self.state.deliveries.items()}
        return {"items": items, "connections": connections, "deliveries": deliveries}

    # -- POST --

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/connect":
            return self._connect()
        if path == "/disconnect":
            with self.state.lock:
                self.state.connections.clear()
                self.state.save()
            return self._redirect()
        if path.startswith("/webhooks/demo/"):
            return self._webhook(path.rsplit("/", 1)[1])
        return self._json(404, {"error": "not found"})

    def _connect(self):
        form = parse_qs(self._read_body().decode())
        api_key = form.get("api_key", [""])[0].strip()
        token = secrets.token_hex(8)
        secret = "whsec_demo_" + secrets.token_hex(12)
        url = "http://%s:%d/webhooks/demo/%s" % (BIND, self.server.port, token)
        req = urllib.request.Request(self.server.vendor_base + "/api/v1/webhooks",
                                     data=json.dumps({"url": url, "secret": secret}).encode(),
                                     method="POST", headers={"Content-Type": "application/json",
                                                             "Authorization": "Bearer " + api_key})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                reply = json.loads(resp.read().decode())
        except urllib.error.HTTPError as err:
            err.close()
            return self._html("<p>The vendor rejected that API key (HTTP %d). <a href='/'>Back</a></p>" % err.code)
        with self.state.lock:
            cid = self.state.new_id("connection")
            self.state.connections[str(cid)] = {
                "connection_id": cid, "status": "active", "api_key": api_key,
                "account": reply["data"]["account"], "token": token, "secret": secret,
                "webhook_url": url}
            self.state.save()
        self._redirect()

    def _webhook(self, token):
        raw = self._read_body()
        body_text = raw.decode("utf-8", "replace")
        conn = next((c for c in self.state.connections.values() if c["token"] == token), None)
        timestamp = self.headers.get(TS_HEADER, "")
        signature = self.headers.get(SIG_HEADER, "")
        try:
            payload = json.loads(body_text or "{}")
        except ValueError:
            payload = {}
        event = payload.get("event")
        rec = (payload.get("recording") or {}).get("id")
        if conn is None:
            return self._json(404, {"error": "unknown webhook token"})
        expected = hmac.new(conn["secret"].encode(), (timestamp + "." + body_text).encode(),
                            hashlib.sha256).hexdigest()
        fresh = timestamp.isdigit() and abs(_now_ms() - int(timestamp)) <= TOLERANCE_S * 1000
        accepted = fresh and hmac.compare_digest(expected, signature)
        with self.state.lock:
            did = self.state.new_id("delivery")
            self.state.deliveries[str(did)] = {"delivery_id": did, "external_id": rec, "event": event,
                                               "state": "accepted" if accepted else "rejected",
                                               "attempts": 1}
            self.state.save()
        if not accepted:
            return self._json(401, {"error": "bad signature or stale timestamp"})
        if event == "transcription.completed" and rec:
            # Planted bug: no check for an existing item with this external id.
            with self.state.lock:
                iid = self.state.new_id("item")
                self.state.items[str(iid)] = {"item_id": iid, "external_id": rec,
                                              "connection_id": conn["connection_id"],
                                              "state": "discovered", "stage": None,
                                              "last_error": None, "redaction_counts": None,
                                              "title": None}
                self.state.save()
            self.server.pipeline.enqueue(iid)
        self._json(200, {"ok": True})


def main():
    session_dir = os.environ.get("EVALENV_SESSION_DIR")
    if not session_dir:
        sys.stderr.write("EVALENV_SESSION_DIR is required\n")
        return 2
    port = int(os.environ.get("DEMO_APP_PORT", "8227"))
    vendor_base = os.environ.get("EVALENV_VENDOR", "http://127.0.0.1:8226")
    # The model base is the sidecar proxy, so every prompt and completion is captured.
    model_base = os.environ.get("DEMO_MODEL_BASE") or os.environ.get("EVALENV_SIDECAR", "http://127.0.0.1:8230")
    model_key = os.environ.get("MODEL_API_KEY", "")
    state = AppState(session_dir)
    pipeline = Pipeline(state, vendor_base, model_base, model_key)
    server = AppServer(port, state, pipeline, vendor_base, model_base, model_key)
    sys.stderr.write("demo app on http://%s:%d\n" % (BIND, port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
