---
name: taste
description: Taste, your own standards for anything rendered (pages, decks, dashboards, prototypes, product UI). Use before building or editing rendered UI and again before reporting it done. Also on "set up my taste", "refresh my taste", "house style", or "this looks vibe-coded".
license: MIT
metadata:
  author: Zave Greene
  version: "1.0.0"
---

# taste

Your taste is two layers kept in your own **taste folder**:

- **Principles** hold on every surface: the pitfalls you correct over and over.
- **House defaults** are the palette, type and motion you pick when a project sets nothing.

Evidence for every rule lives in a ledger, quoted from your own sessions.
A rule earns its place with evidence from 3 distinct sessions, or because you stated it outright.

## Step 0: find the taste folder

The taste folder is `$TASTE_HOME` if set, otherwise `~/.taste/`.
It lives outside this skill so updates never overwrite it.

- `principles.md` missing: run setup in `references/setup.md`, then return here.
- User says "refresh my taste", or `ledger.md` shows a last refresh over 30 days ago: run `references/refresh.md` after the current task, or now if that was the request.

Done when `principles.md` and `house.md` from the taste folder are loaded.

## Step 1: build

Choose the direction first.
House defaults apply unless the project has its own brand, the document has an expected format (a school template, a counterparty's style), or the user asks for something different.
In those cases drop the defaults and keep every principle; name what you dropped and why in the report.

Write the page against every principle and the chosen tokens.

Done when every principle is applied or has a stated reason it does not apply.

## Step 2: review the real render before reporting

Run `references/review.md` against screenshots of the real render.
Code is not evidence; the render is.

Done when every row in `review.md` carries a screenshot path or a measured value, or is marked unchecked with the reason, and the report names both.

## Living files

Mining, promotion and demotion live in `references/refresh.md`.
Keep `principles.md` under about 1,200 tokens (words times 1.33) so it stays sharp when loaded.

Principles hold on every surface; defaults bend to the project; nothing is done until you have looked at the render.
