---
name: feedback
description: Annotate an HTML page by click, then apply the annotations. Use when the user wants to mark up or give feedback on an HTML file, prototype, or artifact in the browser, or pastes an exported block that starts with "# Feedback on" and has an "**Apply to:**" line.
license: MIT
metadata:
  author: Zave Greene
  version: "1.0.0"
---

# Feedback

Turn "this part feels off" into a precise edit list.
The skill forks an HTML page into a **feedback copy** with a click-to-annotate toolkit, the reviewer marks elements in the browser and exports a markdown prompt, and the agent applies each directive to the **source** page.
The source never carries the toolkit, so it can keep changing while review happens on the copy.

Two phases. Pick one from the user's message:

- **Phase 1, fork:** the user names an HTML page (or asks to annotate one) and has no exported block. Go to Phase 1.
- **Phase 2, apply:** the message contains a block starting `# Feedback on` with an `**Apply to:**` line, or the user says they exported feedback. Go to Phase 2.

Paths below are relative to this skill's folder.

## Phase 1 · Fork the page

1. **Resolve the source.**
   Use the path the user gave.
   With no path, list recently modified pages and ask which one if more than one fits:
   `find . -maxdepth 4 \( -name '*.html' -o -name '*.htm' \) -not -path '*/node_modules/*' -not -name '*feedback.html' -mtime -7`
   Done when you hold one existing `.html` or `.htm` path.

2. **Pick a title.**
   Use a name the conversation already gave the page ("Pricing page v3"); otherwise let the script default to the file stem.
   Pass `--reviewer <name>` only when the user names who is reviewing; it changes the copy's filename so two reviewers get separate copies.

3. **Inject.**
   `python3 scripts/inject.py <source> --title "<title>"`
   The script writes `<stem>.feedback.html` next to the source, fills every template value with the right escaping, and verifies the result.
   Done when it prints `"ok": true`.
   The copy is a working file; leave it out of commits.
   If it reports that the copy exists, ask the user: reopen the existing copy (annotations persist in the browser), or re-fork with `--force`.
   Re-forking keeps old annotations, because they live in the browser's localStorage under the printed `storage_key`, not in the file. To clear them, run `localStorage.removeItem('<storage_key>')` in the copy's browser console and reload.
   For any other error, report it and stop.

4. **Open the copy.**
   macOS `open <sidecar>`, Linux `xdg-open <sidecar>`, Windows `start "" <sidecar>`.
   No GUI (remote shell, container): give the user the path to open.

5. **Tell the user how to review**, in four lines:
   - Press `A` or click the **Annotate** pill at the bottom center, then click any element. Drag-select a phrase first to pin the note to those exact words.
   - Pick a type chip (cut, rewrite, expand, wrong, question, keep), type the directive, save with Cmd/Ctrl+Enter.
   - Click a note in the panel to edit it. Numbered dashed badges mark annotated elements.
   - **Export Prompt**, then paste it back here or download it.

Without Python, fill the templates by hand: values are listed in `scripts/inject.py`; the charset meta and `assets/protocol-header.html.tmpl` go right after the doctype, and `assets/widget.html.tmpl` goes before the last `</body>`.
Escape values for each context (JSON for `{{CONFIG_JSON}}`, HTML for `*_HTML`, no `--` inside the header comment).

## Phase 2 · Apply the feedback

1. **Get the block.**
   Pasted into chat is the usual path.
   If the user downloaded it instead, take the newest `feedback-*.md` in `~/Downloads` or wherever the browser saves downloads (`ls -t ~/Downloads/feedback-*.md | head -1`) and confirm its title and date match the page.
   Done when you hold the block and have parsed its `Apply to` path, fork id, and every `### N` item.
   `references/export-format.md` documents every field.

2. **Check for drift.**
   Read the source at the `Apply to` path (a relative path is relative to the git repo root); edit it, never the `.feedback.html` copy.
   If the fork id is a git SHA, run `git diff <SHA> -- <path>`. If the source changed inside the regions the items target, tell the user before editing.
   Done when you know whether each targeted region is unchanged, changed, or gone.

3. **Locate every item.**
   Search the source for the **Selected text** first, then the **Element snippet**.
   Both are rendered text with whitespace collapsed and tags stripped, so search for a distinctive substring of a few words, not the whole string.
   Exactly one match: that is the target.
   Several: narrow by the item's section label and heading.
   Zero, or still several: show the user what is there now and ask.
   Done when every item has exactly one target or an open question.

4. **Apply by type.** Apply `wrong` items first, since a factual fix can change what a nearby rewrite should say.

   | Type | Action |
   |---|---|
   | `cut` | Remove the element or phrase. Fix anything that pointed at it. |
   | `rewrite` | Same meaning, new words, in the page's existing voice. Keep facts and length unless the note says otherwise. |
   | `expand` | Add depth or an example drawn from real code or sources. Never pad. |
   | `wrong` | Verify against the data, code, or document the page is built from. If the page was right, say so and leave it. If nothing in reach can confirm it, apply the reviewer's correction and report it as unverified. |
   | `question` | Answer in chat. Edit only when the answer makes the fix obvious, and say you did. |
   | `keep` | Leave it. Use it as the reference for tone and structure in the other items. |

   Untyped notes: apply a specific edit ("rename to Y") directly; implement a structural intent ("merge these two sections") and describe what you did; for a taste call ("this overpromises"), propose one or two concrete edits and ask which.
   Done when every item is applied, answered, or escalated.

5. **Report.** One line per item applied verbatim; a short summary for each item that needed interpretation; the reason for each item skipped or escalated.

6. **Offer to delete the copy.** Ask `Delete <sidecar>? (y/N)` and delete only on yes. The copy may be wanted as a record.

## Why it works this way

- **Anchor by content, not selector.** Selectors break when the DOM changes; headline and body text usually survive. A snippet that no longer exists in the source is a signal the page moved on, so ask instead of guessing.
- **Fork, do not edit in place.** The reviewer annotates a frozen snapshot while the source keeps moving; the fork id says exactly which version they saw.
- **Typed notes.** The chip tells Phase 2 whether to edit, verify, or answer, which removes the most common misreading (treating a question as an instruction).
- **Self-contained toolkit.** One block of CSS, markup, and script, no network calls, state in localStorage namespaced per page and reviewer. It works on `file://` and on any static host.
- **A fallback for direct edits.** If a reviewer edits the copy's HTML instead of using the toolkit, the protocol header inside the copy tells any agent how to apply a plain diff.

## Files

- `scripts/inject.py`: forks, fills, and verifies the copy.
- `assets/widget.html.tmpl`: the toolkit (pill, panel, modals, CSS, script).
- `assets/protocol-header.html.tmpl`: the comment block that explains the copy to any agent that opens it.
- `references/export-format.md`: the export format with a worked example.
