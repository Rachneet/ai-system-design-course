# ADR 0001: Typed in-process handoffs, not A2A between processes

Status: accepted (2026-10-15)

## Context
The brief allows "A2A or an equivalent typed handoff carrying ticket ID, tenant, user and a summary". All six
agents belong to one product, are deployed together and share one ticket store. A2A between processes would add a
network hop, a second authentication path and a second place where tenant checks must happen, for agents that
never run apart.

## Decision
- A handoff is a runtime tool, `handoff(to, summary)`, whose `to` is an enum of the targets the roster lists for
  that agent. The runtime moves the ticket, records `{from, to, summary}` in the trace, and gives the target a system
  message with the summary. The target sees the user's messages and the summary, not the previous agent's working.
- Guards the model cannot override: targets fixed per agent and checked to be in the same tenant (at roster load and
  at handoff time); at most `MAX_HANDOFFS` (3) per ticket; never back to an agent that has had the ticket. Any
  refusal escalates to a person with the reason.
- Each agent is still published to Atlas as an A2A agent card, for inventory and review. Its interface points at
  Helpdesk's ticket API, which is not an A2A endpoint; the card says what exists and who approved it.

## Consequences
+ One authorization path (Checkpoint) and one tenant check per hop, in one process.
+ Handoffs are data in the trace, so loops and wrong routing are measurable (`handoffs.yaml`).
- Agents owned by another team, or running elsewhere, need real A2A. Revisit when an agent is deployed outside
  Helpdesk, or when another product wants to call these agents.
