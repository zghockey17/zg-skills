# Vendor facts (placeholder)

One row per claim about the vendor API, labeled per `references/vendor-research.md`.
Every Assumed row must have a matching scenario in `stub.py`.

| Claim | Label | Source | Scenario that flips it |
| --- | --- | --- | --- |
| Auth is a bearer key on the REST base | Confirmed / Assumed / Unknown | link or file | |
| Response fields are snake_case | | | `camel` |
| Webhook timestamp is milliseconds | | | `seconds-ts` |
| Webhook signature is HMAC-SHA256 over "{ts}.{body}" | | | `stale-sig` |
| Retries on non-2xx: n attempts, backoff | | | `retry-500` |
| Event set: recording.created, transcription.completed | | | `out-of-order`, `dup` |
