# demo vendor facts

The vendor is invented, so every row is Confirmed by construction. The table shows the shape a real `vendor.md` takes.

| Claim | Label | Source | Scenario that flips it |
| --- | --- | --- | --- |
| Bearer key auth on `/api/v1` | Confirmed | `stub.py` | `revoke-key` |
| `GET /api/v1/recordings?start_date&end_date` lists visible records, newest first | Confirmed | `stub.py` | |
| `GET /api/v1/recordings/{id}` returns `{success, data:{id, title, recording_at, duration, state, transcript:[{speaker, text, start, end}]}}` | Confirmed | `stub.py` | `retry-500`, `slow-fetch` |
| `POST /api/v1/webhooks {url, secret}` registers the account's webhook; loopback URLs only | Confirmed | `stub.py` | |
| Webhook signature: HMAC-SHA256 over `"{timestamp}.{body}"`, hex, in `X-Demo-Signature`; millisecond timestamp in `X-Demo-Timestamp` | Confirmed | `stub.py`, verified in `app.py` | `stale-sig` |
| Events `recording.created` then `transcription.completed`, body `{event, recording:{id}}` | Confirmed | `stub.py` | `out-of-order`, `dup` |
| Retries on non-2xx: 3 attempts, 1 s then 2 s backoff, same signature | Confirmed | `stub.py` | |
