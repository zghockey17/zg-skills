# My taste: house defaults

Defaults apply when a project sets no direction of its own.
A project brand, an expected document format, or a direct request replaces them; the principles still hold.
A row left as `not set` means: use the project's own value, or derive one (for example, border and panel tints from the ink and accent) and say so in the report.

| Default | Value |
|---|---|
| Type | not set (one family; name a fallback stack) |
| Palette | not set (ink, accent, soft, border, panel as hex tokens on `:root`) |
| Palette notes | not set (colors you never want, colors reserved for status) |
| Theme on load | not set (light, dark, or follow the system) |
| Spacing scale | `--s1..--s8` on a 4px base |
| Motion | not set (one easing curve, a duration range for state changes) |
| Accent use | not set (for example: gradient on one word per page, at most) |

Defaults bend to the project; change a row here when your own choice changes.
