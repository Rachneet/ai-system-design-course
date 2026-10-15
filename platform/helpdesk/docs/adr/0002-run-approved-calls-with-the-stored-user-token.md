# ADR 0002: Run approved calls with the requester's stored token

Status: accepted (2026-10-15)

## Context
Checkpoint holds a risky call until a person approves it, then accepts the same call once, with the same agent,
user and arguments, carrying the approval id. Checkpoint needs the user's token to know who the call is for. The
person who approves is someone else, minutes later, while the user may have closed the page. Checkpoint's approval
must be used within its use window (5 minutes by default).

## Options
1. Run the call when the user next opens the ticket, with their fresh token. No stored token, but the approval
   usually lapses first, and the user waits for nothing.
2. Store the requester's token with the pending call and run it as soon as the approver decides.
3. Exchange the user's token at the IdP for a narrow, longer-lived token for this one call (RFC 8693).

## Decision
Option 2, with option 1 as the fallback. `pending_calls.user_token` holds the JWT, which row-level security
isolates per tenant. It is deleted when the call runs or is refused. If it has expired when the decision arrives,
the call runs on the user's next visit with a fresh token. If the approval lapsed meanwhile, Checkpoint opens a new
request and the runtime records it. A pending call is claimed with `FOR UPDATE SKIP LOCKED`, so a double click or a
racing poll cannot run it twice. Checkpoint's single-use approval is the second guard.

## Consequences
+ The approved refund runs within seconds of the approval, with exactly the approved arguments.
- A bearer token rests in the database until it is used or expires. Keep user tokens short-lived, restrict database
  access, and treat this table like a session store. Revisit with option 3 when the IdP supports token exchange.
