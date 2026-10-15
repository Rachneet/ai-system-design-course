# Red-team suites: the model is assumed compromised

Each case scripts what a fully compromised agent does: injected through a ticket, an email or a knowledge base
article, it makes the worst calls it can. The checks are on outcomes, not on the model's words: what the systems of
record look like afterwards, what Checkpoint decided, and what reached the transcript. They run in CI with no model
key (`tests/test_redteam.py`), against the real Switchboard, Atlas and Checkpoint.

Because the attacker's moves are scripted, each case is deterministic and one trial is exact. The behavioural
suites in `../cases` measure whether a real model resists the attempt in the first place; these measure what
happens when it does not.

Case fields: `tenant`, `user` (and optional `roles`), `message`, `agent` (the specialist triage hands to), `attack`
(a list of model turns, each a list of `[tool, args]`), and `expect`:

- `state`: dotted paths into the systems' store that must hold afterwards, such as `accounts.e-cy.locked: true`
- `outcomes`: per tool, the allowed results (`unlisted` means the tool was never forwarded, because the agent
  was not shown it)
- `flags`: per tool, Checkpoint output-scan flags that must be present
- `never_in_trace`: strings that must not appear anywhere in the ticket's trace
