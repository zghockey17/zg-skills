# Edge-case categories

Pick the rows that fit the surface. Each line is a prompt for concrete cases, not a case by itself.

## Input

- **Empty**: blank fields, empty file, no args, `{}` body, whitespace only.
- **Huge**: very long strings, large files, thousands of rows, deep nesting.
- **Boundaries**: 0, -1, max, max+1, first and last item, exactly at a limit.
- **Malformed**: wrong type, bad JSON, invalid dates, missing required fields, extra unknown fields.
- **Unicode and text**: emoji, accents, right-to-left text, zero-width characters, leading and trailing spaces, mixed line endings.
- **Injection-shaped**: quotes, `<script>`, `'; DROP`, `../`, shell metacharacters. Check that they render as text and nothing executes.
- **Duplicate**: same value twice, same submit twice, re-uploading the same file.

## State and data

- **Fresh vs full**: brand-new user with no data, and a user with a lot of it.
- **Stale**: data changed or deleted in another tab or by another user.
- **Partial**: half-filled records, missing optional fields, a related record that no longer exists.

## Timing and network

- **Double action**: double-click submit, hammer a button, press Enter twice.
- **Concurrent**: two tabs, two processes, two requests at once on the same record.
- **Slow**: throttled network, slow dependency; is there feedback, a timeout, a way out?
- **Offline or failing**: network drops mid-request, dependency returns 500, request times out.

## Flow

- **Interrupted**: close the tab, Ctrl-C the CLI, kill the request midway; then resume.
- **Back and refresh**: browser back after submit, refresh mid-flow, deep link straight to step 3.
- **Out of order**: skip a step, repeat a step, arrive from an unexpected route.

## Access

- **Permissions**: logged out, wrong role, expired session, another user's ID in the URL.
- **Files and env**: read-only directory, missing config, missing env var, path with spaces.

## Display (UI)

- **Narrow and wide**: phone width (about 375px), large desktop, browser zoom at 200%.
- **Keyboard only**: tab order, focus visible, Escape closes, Enter submits.
- **Long content**: long names and titles that wrap or truncate, empty lists, one item vs many.
- **Motion and scroll**: scroll during a transition, scroll inside nested regions, reduced-motion setting.

## Output (CLI, API, library)

- **Exit codes and errors**: non-zero exit on failure, error to stderr, readable message, no stack trace for user mistakes.
- **Pipes**: output piped to a file or `head`, input from stdin, no TTY.
- **Contract**: status codes, response shape on error, idempotency on retry.
