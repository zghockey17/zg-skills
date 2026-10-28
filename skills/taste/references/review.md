# taste: review before reporting

Run this against the real render, not the code.

## 1. Shoot

Screenshot at desktop (1440 wide) and phone (390 wide), scrolled end to end, plus hover and open states.
Use whatever browser control the host has (a browser extension, Playwright, Puppeteer); it also covers hover, open states and measurements.
Without one, headless Chrome or Chromium covers static pages:

```
chrome --headless --hide-scrollbars --virtual-time-budget=3000 --window-size=1440,3000 --screenshot=desktop.png file:///abs/path/page.html
```

The binary is `google-chrome` or `chromium` on Linux and `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"` on macOS.
`--virtual-time-budget` lets web fonts load before the capture; raise the height until the page bottom is in frame.
Headless Chrome may refuse windows narrower than 500px, so shoot phone width through a wrapper file next to the page, at `--window-size=500,3000`:

```
<body style="margin:0"><iframe src="page.html" style="width:390px;height:3000px;border:0"></iframe></body>
```

For the measured rows, add a temporary script to a copy of the page that writes the numbers into the DOM, then read them with `--dump-dom`:

```
<script>addEventListener("load", async () => { await document.fonts.ready;
  const leaves = [...document.querySelectorAll("body *")].filter(e => !e.children.length && e.tagName !== "SCRIPT" && e.textContent.trim());
  document.body.dataset.taste = JSON.stringify({
    minFontPx: Math.min(...leaves.map(e => parseFloat(getComputedStyle(e).fontSize))),
    loadedFonts: [...document.fonts].filter(f => f.status === "loaded").map(f => f.family),
  }); });</script>
```

```
chrome --headless --virtual-time-budget=3000 --dump-dom file:///abs/path/page-measure.html | grep -o 'data-taste="[^"]*"'
```

Extend the object with any gap the rows need (`getBoundingClientRect` of two neighbours).
Hover and open states need real browser control; without it, mark those rows unchecked.

Open each screenshot and look at it.
Done when every screenshot has been viewed, not just written to disk.

## 2. Check

Build the checklist from the user's `principles.md`: one row per principle, answered by looking for its tell.
Then add the fixed rows.
A row without a screenshot path or a number is not answered; a row you cannot check is marked unchecked with the reason.

Evidence that works for the starter principles:

| Principle | Evidence |
|---|---|
| Spacing | two measured gaps that should match; before and after of one open state |
| Simple | list of elements removed |
| Text earns its place | list of lines removed |
| Readable floors | smallest computed font size and icon size |
| Motion | each animation with duration and easing; first paint settled |
| Hover | hover and open screenshots side by side |
| Accent strip | grep for `border-left` or `border-top` with a color; screenshot past the last section |
| Small text | grep for `monospace` with the selectors it hits |

Fixed rows:

| Check | Evidence |
|---|---|
| The intended font renders, not a fallback | `loadedFonts` from the measuring script lists the family; computed `font-family` and `document.fonts.check` both report success for a font that never loaded |
| Colors come from tokens | grep for color literals outside the token block |
| Defaults used, or the dropped ones named with the reason | one line |

Fix what fails, re-shoot, and re-answer the failed rows.
Done when every row has its evidence and the report lists what was checked and what stayed unchecked.
