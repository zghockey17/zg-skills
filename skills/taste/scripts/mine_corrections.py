#!/usr/bin/env python3
"""Find your recurring UI corrections in your own agent session logs.

Reads only the turns YOU typed in Claude Code and Codex session logs, keeps
the ones that talk about something rendered (a page, slide, button, layout,
animation...), and matches them against a set of correction patterns
(spacing, faint text, aggressive motion, loud hover, "looks AI-generated"...).

Prints a ranked list: each pattern, the number of DISTINCT sessions it shows
up in, and the first quote per session with its source and session id
(--json carries every quote). The same message pasted into several sessions
counts once.
A pattern seen in 3 or more distinct sessions is a candidate rule.

Read-only. It opens log files for reading and writes only to stdout.
Redirect the output to a private file if you want to keep it; it contains
quotes from your own sessions.

Default log locations (override with flags):
  Claude Code  ~/.claude/projects/<project>/<session>.jsonl
  Codex        ~/.codex/sessions/**/rollout-*.jsonl

Usage:
  python3 mine_corrections.py                       # last 180 days
  python3 mine_corrections.py --since 2026-01-01
  python3 mine_corrections.py --quotes 5 --min-sessions 3
  python3 mine_corrections.py --rule "tables=table (is|looks) (cramped|messy)"
  python3 mine_corrections.py --json > "${TASTE_HOME:-$HOME/.taste}/candidates.json"

Counts overcount: a regex cannot tell a correction from praise or from a
brief you pasted.
Read every quote in context before you trust a count.

Standard library only. Python 3.8 or newer.
"""
import argparse
import datetime as dt
import glob
import json
import os
import re
import sys
from collections import defaultdict

# Each pattern is matched against one lowercased user message.
# Names line up with the starter principles in ../assets/starter-principles.md.
RULES = {
    "spacing": r"\b(spacing|white ?space|cramped|crunched|jammed|overlap\w*|section breaks?|evenly spaced|too much space|padding|misaligned|not aligned)\b",
    "simplify": r"\b(simplif(y|ied)|too (complex|complicated|cluttered|busy|much going on)|unclutter|less is more|simpler|declutter)\b",
    "looks_generated": r"vibe.?cod\w*|ai slop|looks? like ai|ai.?looking|\bgeneric\b|template.?y|looks? cheap|juvenile|goofy|tacky",
    "text_earns_place": r"too much text|faint text|fine.?print|(tiny|little|small|mini) text|hard to read|subtitle is( not)? needed|(delete|remove|cut) (this|that|the) (text|copy|line|subtitle|caption)|earns? (its|their) (place|spot)|wordy",
    "readable_size": r"\b(text|font|words?|title|labels?|icons?)\b[^.]{0,30}\b(bigger|larger|too small)\b|bump (up )?the font|make (the|that|this) text bigger",
    "motion_calm": r"too (fast|aggressive|hectic|choppy|jarring|flashy)|calm (it|that|this) down|slow (it|that|them|this) down|\bchoppy\b|\bjanky\b|stop (the )?(pulsing|bouncing|flashing)|(annoying|weird|distracting) animation",
    "hover": r"\bhover\b",
    "accent_strip": r"colou?r(ed)? (border|strip|bar|edge|corner)|border.?left|left border|accent (bar|stripe|strip)",
    "type": r"wrong font|same font|consistent fonts?|font (is|looks) (off|wrong|weird)|monospace|\bmono\b|serif",
    "color": r"brand colou?rs|our colou?rs|too many colou?rs|colou?r scheme|\bpalette\b|\bpurple\b|\bneon\b|gradients?",
    "shadow_border": r"drop ?shadows?|(weird|heavy|harsh) shadows?|borders? around|outlines? (around|on)",
    "consistency": r"\b(inconsisten\w*|consisten(t|cy))\b",
    "look_before_reporting": r"(did|have) you (look|check|open)|look at (it|the page|the render)|screenshot (it|this)|preview (it|this|that)|you didn'?t (look|check)|open it in (the )?browser",
    "theme": r"light mode|dark mode",
    "bold": r"(too much|so much|everything is) bold|don'?t bold|bold (strategically|everything)",
}

# A message must mention a rendered surface before any rule can count it.
SURFACE = re.compile(
    r"\b(page|slide|deck|html|site|website|ui|ux|button|card|section|layout|prototype|"
    r"animation|font|spacing|design|header|nav|icon|logo|hover|screen|image|visual|"
    r"explainer|dashboard|artifact|background|modal|table|chart|component|css|theme)s?\b"
)

# Turns that are not really the user speaking: injected instructions, pasted
# tool output, skill bodies, long pastes of someone else's text.
INJECTED_MARKERS = (
    "base directory for this skill",
    "<command-name>",
    "<local-command",
    "<system-reminder>",
    "<environment_context>",
    "<user_instructions>",
    "agents.md instructions",
    "<task-notification>",
)


def is_user_voice(text, max_chars):
    head = text.lstrip()[:200].lower()
    if not head or head.startswith("<"):
        return False
    if len(text) > max_chars:
        return False
    return not any(m in text[:400].lower() for m in INJECTED_MARKERS)


def project_label(path):
    """Claude Code encodes the working directory as the folder name."""
    name = os.path.basename(os.path.dirname(path))
    home = os.path.expanduser("~").replace("/", "-").replace(".", "-")
    if name.startswith(home):
        name = name[len(home):]
    name = name.strip("-") or "home"
    return name if len(name) <= 40 else "..." + name[-37:]


def text_of(content, part_type):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == part_type
        )
    return ""


def read_jsonl(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                try:
                    yield json.loads(line)
                except ValueError:
                    continue
    except OSError:
        return


def claude_turns(root):
    # Top-level session files only; subagent transcripts live deeper and are not you.
    for path in glob.glob(os.path.join(root, "*", "*.jsonl")):
        sid = os.path.splitext(os.path.basename(path))[0][:8]
        proj = project_label(path)
        for o in read_jsonl(path):
            if o.get("type") != "user" or o.get("isSidechain") or o.get("isMeta"):
                continue
            text = text_of((o.get("message") or {}).get("content"), "text")
            if text:
                yield o.get("timestamp", "")[:10], "claude", proj, sid, text


def codex_turns(root):
    for path in glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True):
        sid = os.path.splitext(os.path.basename(path))[0].replace("rollout-", "")[:19]
        proj = ""
        for o in read_jsonl(path):
            kind = o.get("type")
            payload = o.get("payload") or {}
            if kind == "session_meta":
                proj = os.path.basename(str(payload.get("cwd", "")).rstrip("/"))
                if "subagent" in str(payload.get("source", "")):
                    break
                continue
            if kind != "response_item" or payload.get("type") != "message" or payload.get("role") != "user":
                continue
            text = text_of(payload.get("content"), "input_text")
            if text:
                yield o.get("timestamp", "")[:10], "codex", proj, sid, text


def quote_around(text, match, radius):
    start = max(0, match.start() - radius)
    end = min(len(text), match.end() + radius)
    snippet = " ".join(text[start:end].split())
    return ("..." if start else "") + snippet + ("..." if end < len(text) else "")


def parse_args(argv):
    default_since = (dt.date.today() - dt.timedelta(days=180)).isoformat()
    ap = argparse.ArgumentParser(
        description="Rank your recurring UI corrections from Claude Code and Codex logs. Read-only.",
        epilog="Quotes come from your own sessions. Keep any saved output private.",
    )
    ap.add_argument("--since", default=default_since, help="earliest date, YYYY-MM-DD (default: 180 days ago)")
    ap.add_argument("--claude-dir", default="~/.claude/projects", help="Claude Code projects folder")
    ap.add_argument("--codex-dir", default="~/.codex/sessions", help="Codex sessions folder")
    ap.add_argument("--no-claude", action="store_true", help="skip Claude Code logs")
    ap.add_argument("--no-codex", action="store_true", help="skip Codex logs")
    ap.add_argument("--quotes", type=int, default=3, help="quotes to print per rule (default 3, 0 for all)")
    ap.add_argument("--min-sessions", type=int, default=1, help="hide rules seen in fewer sessions")
    ap.add_argument("--radius", type=int, default=120, help="characters of context on each side of a match")
    ap.add_argument("--rule", action="append", default=[], metavar="NAME=REGEX",
                    help="add or replace a rule; repeatable")
    ap.add_argument("--only", action="append", default=[], metavar="NAME", help="run only these rules")
    ap.add_argument("--max-chars", type=int, default=6000,
                    help="skip turns longer than this; long pastes are rarely your own words (default 6000)")
    ap.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = ap.parse_args(argv)
    try:
        dt.date.fromisoformat(args.since)
    except ValueError:
        ap.error("--since must be YYYY-MM-DD")
    return args


def build_rules(args):
    rules = dict(RULES)
    for item in args.rule:
        name, sep, pattern = item.partition("=")
        if not sep or not name.strip():
            sys.exit("--rule needs NAME=REGEX, got: " + item)
        rules[name.strip()] = pattern
    if args.only:
        missing = [n for n in args.only if n not in rules]
        if missing:
            sys.exit("unknown rule(s): " + ", ".join(missing))
        rules = {n: rules[n] for n in args.only}
    try:
        return {n: re.compile(p) for n, p in rules.items()}
    except re.error as exc:
        sys.exit("bad regex: %s" % exc)


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    rules = build_rules(args)

    sources = []
    if not args.no_claude:
        sources.append(("claude", os.path.expanduser(args.claude_dir), claude_turns))
    if not args.no_codex:
        sources.append(("codex", os.path.expanduser(args.codex_dir), codex_turns))

    # rule -> {(source, sid): [date, project, [quotes in that session]]}
    hits = defaultdict(dict)
    # The same prompt pasted into many sessions (eval runs, templates) counts once.
    seen_text = defaultdict(set)
    scanned = defaultdict(int)
    found_any = False
    for label, root, reader in sources:
        if not os.path.isdir(root):
            print("note: %s logs not found at %s" % (label, root), file=sys.stderr)
            continue
        found_any = True
        for date, src, proj, sid, text in reader(root):
            if date < args.since or not is_user_voice(text, args.max_chars):
                continue
            lower = text.lower()
            if not SURFACE.search(lower):
                continue
            scanned[src] += 1
            for name, rx in rules.items():
                m = rx.search(lower)
                if not m:
                    continue
                fingerprint = " ".join(lower.split())[:300]
                entry = hits[name].get((src, sid))
                if entry is None:
                    if fingerprint in seen_text[name]:
                        continue
                    entry = hits[name][(src, sid)] = [date, proj, []]
                seen_text[name].add(fingerprint)
                entry[0] = max(entry[0], date)
                entry[2].append(quote_around(text, m, args.radius))
    if not found_any:
        sys.exit("no session logs found; pass --claude-dir or --codex-dir")

    ranked = sorted(rules, key=lambda n: (-len(hits[n]), n))
    ranked = [n for n in ranked if len(hits[n]) >= args.min_sessions]

    if args.json:
        out = {
            "since": args.since,
            "ui_messages_scanned": dict(scanned),
            "rules": [
                {
                    "rule": n,
                    "sessions": len(hits[n]),
                    "last_seen": max((v[0] for v in hits[n].values()), default=None),
                    "hits": [
                        {"date": d, "source": s, "session": sid, "project": p, "quotes": q}
                        for (s, sid), (d, p, q) in sorted(hits[n].items(), key=lambda x: x[1][0], reverse=True)
                    ],
                }
                for n in ranked
            ],
        }
        json.dump(out, sys.stdout, indent=2)
        print()
        return

    print("UI corrections since %s (UI messages scanned: %s)" % (
        args.since, ", ".join("%s %d" % kv for kv in sorted(scanned.items())) or "none"))
    print("Candidate rule = 3+ distinct sessions. Read every quote before trusting a count.\n")
    for n in ranked:
        items = sorted(hits[n].items(), key=lambda x: x[1][0], reverse=True)
        last = items[0][1][0] if items else "-"
        flag = "  <- candidate" if len(items) >= 3 else ""
        print("## %s: %d sessions, last seen %s%s" % (n, len(items), last, flag))
        shown = items if args.quotes == 0 else items[: args.quotes]
        for (src, sid), (date, proj, quotes) in shown:
            more = "  (+%d more in this session)" % (len(quotes) - 1) if len(quotes) > 1 else ""
            print("  %s %s %s [%s] %s%s" % (date, src, sid, proj, quotes[0][:400], more))
        if len(shown) < len(items):
            print("  ... %d more" % (len(items) - len(shown)))
        print()


if __name__ == "__main__":
    main()
