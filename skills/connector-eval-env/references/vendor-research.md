# Vendor research: confirm vs assume

Phase 2 labels every claim about the vendor API before the stub encodes it.

- **Confirmed**: a reviewed source proves it. Public docs, a captured response from a real account, a vendor reply.
- **Assumed**: the app already depends on a specific shape, but no reviewed source proves it. This is a live risk.
- **Unknown**: a capability no reviewed source establishes. Keep it in a questions list, not in the design as fact.

| Claim | Label | Source |
| --- | --- | --- |
| example: response fields are snake_case | Assumed | app maps snake_case; no account response captured |
| example: bearer-key auth on the REST base | Confirmed | vendor API docs |
| example: rate-limit quota and Retry-After semantics | Unknown | not found in public docs |

## The rule: every assumed row becomes a shape scenario

An assumption is not tested until the stub can produce the mismatched shape on demand. Each **Assumed** row becomes a named scenario in the stub, and the stub default holds the assumed-correct shape. The scenario flips the shape and drives a record through the pipeline, proving the app either handles the mismatch or fails visibly.

| Assumption | Stub default | Scenario that flips it |
| --- | --- | --- |
| Response field casing is snake_case | snake_case | `camel` |
| Webhook timestamp unit is milliseconds | milliseconds | `seconds-ts` |
| Webhook signature is HMAC-SHA256 over "{ts}.{body}" | valid, fresh | `stale-sig` |
| Vendor retries on non-2xx | 3 attempts, 1 s then 2 s | `retry-500` |
| Events arrive in order, once | ordered, once | `out-of-order`, `dup` |

Exit criterion: every **Assumed** row has a matching scenario, and no assumption rides only on the default.
