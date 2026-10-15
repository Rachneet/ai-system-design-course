# ADR 0004: Red-team with a compromised model, not only with attack prompts

Status: accepted (2026-10-15)

## Context
A red-team suite of attack prompts measures two things at once: how often the model is fooled, and what the platform
lets a fooled model do. The first varies by model, prompt and day, and needs a model key in CI. The second is the
security boundary, and it should not depend on the model at all.

## Decision
Two kinds of suite:
- **Red-team** (`evals/redteam`): the model is scripted to make the attacker's best calls directly. The checks are on
  outcomes: the systems' state, Checkpoint's decisions and the trace. They run in CI on every change to Helpdesk or the
  platform services, deterministically, with no key, so one trial is exact.
- **Behavioural** (`evals/cases`): real prompts to a real model, including the same attacks as messages, run with
  several trials and gated with pass^k. Must-never categories fail on any miss.

## Consequences
+ A policy or gateway regression fails CI at once, whatever the model. Weakening the own-account rule fails two cases.
+ The behavioural suites stay focused on quality and resistance, where trials and models matter.
- Scripted attacks are only as good as the people who write them. Add a case whenever a new tool, argument or tenant
  appears, and whenever a behavioural failure shows a new kind of attack.
