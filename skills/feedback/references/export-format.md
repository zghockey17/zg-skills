# Export format

The toolkit's **Export Prompt** button produces this markdown.
Phase 2 of the skill parses it.

## Shape

```
# Feedback on <TITLE>[ from <REVIEWER>] · <YYYY-MM-DD>

**Apply to:** `<repo-relative or absolute path of the source>`
**Forked from:** `<source basename> @ <git SHA or sha256:<12 hex>>`
**Items:** <N>

## How to apply
<fixed instructions for an agent that has never seen this skill>

Type legend: <fixed legend>

---

### <n> · <section label> · <nearest heading>     (either part may be absent; "General" if both are)

**Section title:** <only when it differs from the heading>
**Type:** <cut | rewrite | expand | wrong | question | keep>     (optional)
**Selected text:** *"<exact phrase the reviewer drag-selected>"*     (optional)
**Element snippet:** *"<first 240 chars of the clicked element's text, whitespace collapsed>"*

**Directive:**

> <the reviewer's note, one "> " line per line>
```

Fields worth knowing:

- **Forked from** is a git SHA when the source was tracked and clean at fork time, so `git diff <SHA> -- <path>` shows how the source moved since.
  A `sha256:` prefix means the file was untracked or had uncommitted edits; compare by reading the source instead.
- **Element snippet** is the clicked element's rendered text, not its HTML.
  Tags, attributes, and entities are gone, and whitespace is collapsed to single spaces, so search with a flexible pattern or a distinctive substring.
- **Selected text** is the same, but only the dragged phrase. The directive usually targets that phrase, not the whole element.

## Example

```
# Feedback on Pricing page v3 from Sam · 2026-10-28

**Apply to:** `site/pricing.html`
**Forked from:** `pricing.html @ sha256:4f1c9a07be22`
**Items:** 3

## How to apply
Edit the **Apply to** file, not the feedback copy `pricing.sam-feedback.html`. ...

Type legend: **cut** = delete it · ...

---

### 1 · Plans · Team

**Type:** wrong
**Element snippet:** *"Team $24 per seat, billed monthly Up to 50 seats Priority support"*

**Directive:**

> The Team plan caps at 25 seats, not 50. Check the plans config.

### 2 · Plans · Pro

**Type:** rewrite
**Selected text:** *"leverage our best-in-class synergy engine"*
**Element snippet:** *"Pro $12 per seat, billed monthly. Unlock collaboration and leverage our best-in-class synergy engine for growing teams."*

**Directive:**

> Say what it does: shared workspaces and version history.

### 3 · FAQ

**Element snippet:** *"Can I cancel anytime?"*

**Directive:**

> Is this answer still true for annual plans?
```

How each item resolves:

1. `wrong`: check the claim against the data the page is built from (here, the plans config) before editing. If the page was right, say so and leave it.
2. `rewrite` with selected text: replace only that phrase, keep the rest of the sentence.
3. Untyped, phrased as a question: answer in chat. Edit only if the answer makes the fix obvious, and say so.
