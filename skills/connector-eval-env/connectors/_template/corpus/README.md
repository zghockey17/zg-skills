# Corpus (placeholder)

One `rec_*.json` per record in the vendor's detail envelope shape, plus
`targets.json`, the scoring key. Replace `rec_placeholder_001.json` with
records shaped exactly like the real vendor returns them (the stub serves
them verbatim) and list every planted span in `targets.json`.

Rules that keep a corpus honest:

- Fabricated people and companies only. Reserved 555 phone numbers.
- Plant spans in the middle of ordinary conversation, not the first line.
- Include clean records so a correct run that cuts nothing also passes.
- Name the category each span lands in; it must match a key your app writes to redaction counts.
