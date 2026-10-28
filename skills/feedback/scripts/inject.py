#!/usr/bin/env python3
"""Fork an HTML page into a feedback copy with the annotation toolkit injected.

Usage:
  python3 inject.py <page.html> [--title "Pricing page v3"] [--reviewer "Sam"] [--force]

Writes <stem>.feedback.html (or <stem>.<reviewer>-feedback.html) next to the source,
leaves the source untouched, verifies the result, and prints one JSON object with
the paths, storage key, and fork id. Exit code 0 on success, 1 on any failure.

Python 3.8+ standard library only. Templates are read from ../assets/.

Why a script and not hand edits: the values land in three contexts (an HTML
comment, HTML text, and a JavaScript literal), each with its own escaping rule.
A title with an apostrophe or a path containing "--" breaks a hand-filled copy.
"""
import argparse, datetime, hashlib, html, json, os, re, subprocess, sys

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
OPEN_MARK = "<!-- ▼▼▼ FEEDBACK TOOLKIT"
CLOSE_MARK = "<!-- ▲▲▲ END FEEDBACK TOOLKIT"


def fail(msg):
    print(json.dumps({"ok": False, "error": msg}))
    sys.exit(1)


def git(args, cwd):
    try:
        out = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def fork_identity(src):
    """Git commit SHA when the file is tracked and unmodified, else a content hash.

    The SHA lets a later agent run `git diff <sha> -- <path>` to see how far the
    source moved. A modified tracked file gets a hash, because the commit would
    not match what the reviewer actually saw.
    """
    d = os.path.dirname(src)
    if git(["rev-parse", "--is-inside-work-tree"], d) == "true":
        sha = git(["log", "-1", "--format=%H", "--", src], d)
        dirty = git(["status", "--porcelain", "--", src], d)
        root = git(["rev-parse", "--show-toplevel"], d)
        if sha and not dirty:
            return sha, os.path.relpath(src, root) if root else src
        target = os.path.relpath(src, root) if root else src
    else:
        target = src
    with open(src, "rb") as f:
        return "sha256:" + hashlib.sha256(f.read()).hexdigest()[:12], target


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "page"


def comment_safe(s):
    # "--" cannot appear inside an HTML comment; ">" after it would close it early.
    return s.replace("--", "- -")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source")
    ap.add_argument("--title", help="human-readable name shown in the panel and export header")
    ap.add_argument("--reviewer", default="", help="optional reviewer name; changes the copy's filename")
    ap.add_argument("--force", action="store_true", help="overwrite an existing feedback copy")
    a = ap.parse_args()

    src = os.path.abspath(a.source)
    if not os.path.isfile(src):
        fail(f"not a file: {src}")
    if not src.lower().endswith((".html", ".htm")):
        fail(f"not an .html or .htm file: {src}")

    stem = re.sub(r"\.html?$", "", os.path.basename(src), flags=re.I)
    suffix = f".{slug(a.reviewer)}-feedback.html" if a.reviewer else ".feedback.html"
    sidecar = os.path.join(os.path.dirname(src), stem + suffix)
    if os.path.exists(sidecar) and not a.force:
        fail(f"feedback copy exists: {sidecar} (open it to continue, or pass --force to re-fork)")

    fork_id, target = fork_identity(src)
    storage_key = f"fbk-{slug(stem)}{'-' + slug(a.reviewer) if a.reviewer else ''}-v1"
    title = a.title or stem.replace("-", " ").replace("_", " ").strip().capitalize()
    values = {
        "SOURCE_BASENAME": os.path.basename(src),
        "SIDECAR_BASENAME": os.path.basename(sidecar),
        "FORK_SHA": fork_id,
        "FORK_DATE": datetime.date.today().isoformat(),
        "TARGET_PATH": target,
        "REVIEWER": a.reviewer or "(not set)",
    }
    config = {
        "storageKey": storage_key, "forkId": fork_id, "target": target, "title": title,
        "reviewer": a.reviewer, "sourceBasename": values["SOURCE_BASENAME"],
        "sidecarBasename": values["SIDECAR_BASENAME"],
    }

    with open(os.path.join(ASSETS, "protocol-header.html.tmpl"), encoding="utf-8") as f:
        header = f.read()
    with open(os.path.join(ASSETS, "widget.html.tmpl"), encoding="utf-8") as f:
        widget = f.read()
    for k, v in values.items():
        header = header.replace("{{" + k + "}}", comment_safe(v))
    # json.dumps handles quotes and backslashes; escaping "<" keeps "</script>" in a
    # title from closing the script element.
    widget = (widget
              .replace("{{CONFIG_JSON}}", json.dumps(config).replace("<", "\\u003c"))
              .replace("{{TITLE_HTML}}", html.escape(title))
              .replace("{{SOURCE_BASENAME_HTML}}", html.escape(values["SOURCE_BASENAME"])))

    with open(src, encoding="utf-8", errors="surrogateescape") as f:
        page = f.read()
    if OPEN_MARK in page:
        fail("this page already contains the feedback toolkit; pass the original page")

    # Widget goes just before the last </body>, else the last </html>, else the end.
    # Skeleton-less pages (doctype, <title>, <style>, content, no <body>) still work:
    # the parser puts trailing content in the body.
    m = None
    for pat in (r"</body\s*>", r"</html\s*>"):
        hits = list(re.finditer(pat, page, re.I))
        if hits:
            m = hits[-1]
            break
    at = m.start() if m else len(page)
    page = page[:at] + "\n" + widget + "\n" + page[at:]

    # Charset pin and header go right after the doctype (or at the top). The pin
    # comes first: browsers only sniff <meta charset> in the first 1024 bytes, and
    # the header would push the page's own declaration past that window.
    d = re.match(r"\s*<!doctype[^>]*>", page, re.I)
    at = d.end() if d else 0
    page = page[:at] + '\n<meta charset="utf-8">\n' + header + page[at:]

    with open(sidecar, "w", encoding="utf-8", errors="surrogateescape") as f:
        f.write(page)

    # Verify: one marker pair, no protocol prose visible outside comments, no
    # unfilled placeholders.
    out = open(sidecar, encoding="utf-8", errors="surrogateescape").read()
    problems = []
    if out.count(OPEN_MARK) != 1 or out.count(CLOSE_MARK) != 1:
        problems.append("toolkit markers not exactly one pair")
    if "WHY THIS FILE EXISTS" in re.sub(r"<!--.*?-->", "", out, flags=re.S):
        problems.append("protocol header leaked outside its comment")
    if re.search(r"\{\{[A-Z_]+\}\}", out):
        problems.append("unfilled placeholder")
    if problems:
        os.remove(sidecar)
        fail("verification failed, copy removed: " + "; ".join(problems))

    print(json.dumps({
        "ok": True, "source": src, "sidecar": sidecar, "target": target,
        "fork_id": fork_id, "storage_key": storage_key, "title": title,
    }, indent=2))


if __name__ == "__main__":
    main()
