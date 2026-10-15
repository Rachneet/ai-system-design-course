---
id: w8-policy
week: 8
kind: lesson
title: Policy as code for agents
short: Policy as code
minutes: 50
summary: Decide every tool call deterministically from the agent, the tool, the arguments and the user. Cedar and OPA compared from their docs, where policy should run, how to design human approvals that cannot be replayed or rubber-stamped, and how to test policies before they block real traffic.
---

## Why a prompt is not a policy

Relay's system prompt says "never refund more than 200 without a manager". That sentence is a request to the model, not a control. The [injection lesson](#w3-security) showed why: any text the model reads can override it, and the model can also simply get it wrong. A prompt can make bad behaviour rarer. It cannot make it impossible, and it leaves no record of why anything was allowed.

Week 3 put the refund cap inside the tool, in code. That works for one tool in one service. A company with fifty agents and three hundred tools needs the same rule written once, reviewed by security, enforced in one place and logged for every call. That is **policy as code**: authorization rules in a dedicated language, evaluated by an engine outside the model, for every tool call.

```viz
caption: A prompt asks the model to behave. A policy decides outside the model, so a fooled model changes nothing.
<div class="vz-cols">
  <div class="vz-panel sk b"><h5>Rule in the prompt</h5>
    <div class="vz-row"><span class="ch sk">system prompt: cap 200</span><span class="arr sk"></span><span class="ch sk b">injected review</span></div>
    <div class="vz-row"><span class="arr sk b"></span><span class="ch sk b">refund 900: sent</span></div>
    <p>the model is both the judge and the target</p>
  </div>
  <div class="vz-panel sk g"><h5>Rule as policy</h5>
    <div class="vz-row"><span class="ch sk">model asks: refund 900</span><span class="arr sk"></span><span class="ch sk c">policy engine</span></div>
    <div class="vz-row"><span class="arr sk g"></span><span class="ch sk g">held for a person</span><span class="ch sk">logged with reason</span></div>
    <p>the model can ask for anything; it decides nothing</p>
  </div>
</div>
```

> [!rule] Every tool call gets a deterministic decision from four inputs: which agent, which tool, which arguments, and which user. The model supplies none of the identity and none of the decision.

## The four inputs of a decision

A tool call decision needs more than "is this agent allowed to use this tool".

| Input | Where it comes from | Why it matters |
|---|---|---|
| Agent | The agent's own credential at the gateway | The refunds agent and the FAQ agent should not hold the same tools |
| Tool | The tool name, namespaced by server | `payments__refund` and `weather__get_forecast` carry different risk |
| Arguments | The call body, checked against the tool's schema | A refund of 45 and a refund of 4,500 are different decisions |
| User | A verified token for the person the agent acts for | Support staff may refund; a sales user may not; nobody refunds themselves |

Identity must come from verified tokens, never from the model's arguments. Checkpoint, the course's gateway, takes the agent from its own bearer token and the user from a signed JWT in `X-User-Token`, verified on every request ([`identity.py`](https://github.com/Rachneet/ai-system-design-course/blob/main/platform/checkpoint/checkpoint/identity.py)). The arguments are the only part the model controls, which is exactly why the policy must be able to read them.

## Cedar in ten minutes

[Cedar](https://docs.cedarpolicy.com/) is an open-source (Apache-2.0) authorization language from AWS. Every request has four parts, which Cedar's docs abbreviate PARC: **principal**, **action**, **resource** and **context**. Principal, action and resource are entities; context is a record of anything else you pass in ([authorization docs](https://docs.cedarpolicy.com/auth/authorization.html)).

Three rules make it fit for security work, all stated in those docs:

1. **Default deny.** No request is allowed unless some `permit` policy matches it.
2. **Forbid wins.** If any `forbid` matches, the answer is deny, whatever the permits say.
3. **Errors are skipped.** A policy whose condition fails to evaluate (for example, it reads an attribute that is missing) does not count. With default deny, a broken permit fails closed.

Checkpoint maps tool calls onto PARC like this: the agent is the principal (`Agent::"refunds"`), the namespaced tool is the resource (`Tool::"payments__refund"`), the action is `list` (the tool appears in `tools/list`) or `call`, and the context carries the arguments, the verified user and the server ([ADR 0001](https://github.com/Rachneet/ai-system-design-course/blob/main/platform/checkpoint/docs/adr/0001-cedar-policy-with-approval-annotations.md)). Here is its real policy file, [`policies/default.cedar`](https://github.com/Rachneet/ai-system-design-course/blob/main/platform/checkpoint/policies/default.cedar):

```cedar
// Every agent may see and call read-only weather tools.
@id("weather-read")
permit(principal, action, resource == Tool::"weather__get_forecast");

// The refunds agent may see the refund tool, and call it for support staff up to 200.
@id("refunds-see-refund")
permit(principal == Agent::"refunds", action == Action::"list", resource == Tool::"payments__refund");

@id("refunds-small")
permit(principal == Agent::"refunds", action == Action::"call", resource == Tool::"payments__refund")
when { context.user.roles.contains("support") && context.args.amount <= 200 };

// Larger refunds are allowed only after a person approves that exact call.
@id("refunds-large-need-approval")
@approval("required")
permit(principal == Agent::"refunds", action == Action::"call", resource == Tool::"payments__refund")
when { context.user.roles.contains("support") && context.args.amount > 200 && context.args.amount <= 2000 };

// Nobody refunds their own account, whatever else allows it.
@id("no-self-refund")
forbid(principal, action == Action::"call", resource == Tool::"payments__refund")
when { context.args has customer_id && context.args.customer_id == context.user.id };
```

Things to notice:

- **The scope narrows, the `when` decides.** The head of each policy (`principal == ..., action == ..., resource == ...`) says which requests it is about; `when` adds conditions on the context.
- **`has` before reading an optional field.** `no-self-refund` checks `context.args has customer_id` first, so a call without that field does not make the forbid error out and get skipped.
- **Annotations carry meaning for the gateway, not for Cedar.** Cedar's docs say an annotation "has no impact on policy evaluation" and is stored with the policy so other software can read it ([policy syntax](https://docs.cedarpolicy.com/policies/syntax-policy.html)). Checkpoint reads two: `@id` names the policy in every decision log entry, and `@approval("required")` turns an allow into a hold.

### Three outcomes from a yes/no engine

Cedar answers allow or deny. Agents need a third answer: **allow, but only after a person says yes**. Checkpoint gets it without changing Cedar: when the decision is allow, it looks at the policies that produced it, and if any of them carries `@approval("required")`, the call is held ([`policy.py`](https://github.com/Rachneet/ai-system-design-course/blob/main/platform/checkpoint/checkpoint/policy.py)). Because it checks *any* determining policy, a call that matches both a plain permit and an approval permit still waits for a person. The conservative reading wins.

```viz
caption: One engine, three outcomes. These are real decisions from Checkpoint for the refunds agent and a support user, with the policy that produced each.
<div class="vz-row"><span class="ch sk c">principal: Agent "refunds"</span><span class="ch sk c">action: call</span><span class="ch sk c">resource: payments__refund</span><span class="ch sk c">context: args, user, server</span></div>
<div class="vz-row"><span class="arr d sk"></span></div>
<div class="vz-cols" style="--k:3">
  <div class="vz-panel sk g"><h5>Allow</h5><div class="vz-row"><span class="ch sk g">amount 50</span></div><p>refunds-small</p><p>runs now, logged as allow</p></div>
  <div class="vz-panel sk"><h5>Hold</h5><div class="vz-row"><span class="ch sk">amount 900</span></div><p>refunds-large-need-approval</p><p>waits for a person, logged as hold</p></div>
  <div class="vz-panel sk b"><h5>Deny</h5><div class="vz-row"><span class="ch sk b">own account</span><span class="ch sk b">amount 5,000</span></div><p>no-self-refund; no policy permits</p><p>never reaches the server</p></div>
</div>
```

The denial text matters too. Checkpoint returns policy outcomes as tool results with `isError: true` ("Denied by no-self-refund. Do not retry; explain to the user that this action is not allowed."), not as protocol errors, so the model can read the reason and tell the user instead of retrying in a loop. The MCP spec recommends exactly this split: tool execution errors go back to the model so it can adapt ([MCP tools spec](https://modelcontextprotocol.io/specification/2026-07-28/server/tools#error-handling)).

### Two Cedar traps you will hit

> [!warn] Cedar has no floating-point numbers. Its numeric types are `Long` (a 64-bit integer) and the `decimal` extension type, written `decimal("12.50")` ([Cedar data types](https://docs.cedarpolicy.com/policies/syntax-datatypes.html)). If a refund tool takes `amount: 50.5`, the request cannot be built and the call is denied. That fails closed, which is right, but users see refusals nobody can explain. Use integer minor units (`amount_cents`) in tool schemas that policy reads.

The second trap is the error rule working against you. In Checkpoint, a call to the refund tool with no `amount` makes both refund permits fail to evaluate. Both are skipped, nothing permits, and the call is denied with "no policy permits it". That is safe. A `forbid` that errors is also skipped, though, which is *unsafe*: write every forbid so it cannot error, with `has` guards, and test the missing-field case.

## OPA and Rego: the main alternative

[Open Policy Agent](https://www.openpolicyagent.org/docs) is a graduated CNCF project and a general-purpose policy engine. Your service sends it a JSON input and asks a question; policies are written in Rego, and "your policies can generate arbitrary structured data as output", not only allow or deny. It is widely used for Kubernetes admission, API authorization and infrastructure checks.

The same refund rules in Rego:

```rego
package checkpoint.tools

default allow := false
default needs_approval := false

is_refund if {
	input.agent == "refunds"
	input.action == "call"
	input.tool == "payments__refund"
	"support" in input.user.roles
}

self_refund if input.args.customer_id == input.user.id

permitted if {
	is_refund
	input.args.amount <= 2000
}

allow if {
	permitted
	not self_refund
}

needs_approval if {
	allow
	input.args.amount > 200
}
```

Compared honestly, from each project's own documentation:

| | Cedar | OPA / Rego |
|---|---|---|
| Built for | Application authorization: who may do what to which resource | Any policy question over JSON: admission, authorization, config checks |
| Request shape | Fixed: principal, action, resource, context | Any JSON input you design |
| Combining rules | Built in: default deny, forbid overrides permit | You write it (above: `allow if { permitted; not self_refund }`) |
| Outputs | Allow or deny, plus the determining policies and errors | Any structured value: booleans, reasons, obligations |
| Checking policies | Optional [schema validation](https://docs.cedarpolicy.com/policies/validation.html) catches typos and type errors; designed for analysis with automated reasoning | [`opa test`](https://www.openpolicyagent.org/docs/policy-testing) runs unit tests written as `test_` rules |
| Audit | Your gateway logs decisions | Built-in [decision logs](https://www.openpolicyagent.org/docs/management-decision-logs) with masking of sensitive fields |
| Where it runs | A library inside your process (Rust, with bindings) | A sidecar or service, or embedded as a Go library |

Choose Cedar when the question is always "may this principal do this action on this resource", and you want forbid-wins semantics that a security reviewer can rely on without reading your combining logic. Choose OPA when you already run it for infrastructure, when the decision needs to return more than yes or no (a redaction list, a rate tier), or when the inputs do not fit PARC. Either is far better than `if` statements spread across services.

### What the managed platforms do

Both large clouds now put policy in front of agent tool calls, which is why this skill transfers:

- **AWS Bedrock AgentCore Policy** "intercepts all agent traffic through Amazon Bedrock AgentCore Gateways and evaluates each request against defined policies" before tool access. Policies are written in Cedar, or in plain English that the service turns into Cedar and checks with automated reasoning for rules that are too broad, too narrow or never satisfiable. Default deny and forbid-wins apply ([AgentCore Policy docs](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy.html)). Its [getting-started tutorial](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-getting-started.html) models the tool as the *action* and the gateway as the *resource*, the reverse of Checkpoint's choice, which shows that the PARC mapping is a design decision you make, not something Cedar fixes.
- **Google's Agent Gateway** is "the key enforcement component of Agent Platform", default deny for agent traffic, enforced through IAM allow and deny policies; for MCP traffic only, it parses the request so policies can restrict access to specific tools ([Agent Gateway overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/gateways/agent-gateway-overview)).

## Where policy runs

You have three places to put the decision, and a serious system uses more than one.

```viz
caption: The gateway is the one place that sees every call from every agent. The tool still checks what only it can know.
<div class="vz-cols" style="--k:3">
  <div class="vz-panel sk b"><h5>In the agent</h5><div class="vz-row"><span class="ch sk">agent code</span><span class="arr sk"></span><span class="ch sk b">checks itself</span></div><p>each team re-implements it; a compromised agent skips it</p></div>
  <div class="vz-panel sk g"><h5>At the gateway</h5><div class="vz-row"><span class="ch sk">any agent</span><span class="arr sk"></span><span class="ch sk g">one policy, one log</span><span class="arr sk"></span><span class="ch sk">tool</span></div><p>sees agent, user, tool and arguments for every call</p></div>
  <div class="vz-panel sk c"><h5>At the tool</h5><div class="vz-row"><span class="ch sk">request</span><span class="arr sk"></span><span class="ch sk c">does order 5520 belong to this customer?</span></div><p>only the order system knows; keep this check</p></div>
</div>
```

- **In the agent**: easy to start with, but every team writes its own version, and the code that enforces the rule runs inside the thing you are trying to constrain. Use it only for user experience (do not even offer a tool the agent cannot use).
- **At the gateway**: one enforcement point, one policy language, one decision log. Checkpoint does this, and filters `tools/list` with the same policy so an agent never sees tools it may not call. The gateway must be the only route to the tools, so run servers on a network only the gateway can reach ([ADR 0002](https://github.com/Rachneet/ai-system-design-course/blob/main/platform/checkpoint/docs/adr/0002-signed-assertions-not-shared-credentials.md)).
- **At the tool**: the tool still enforces what needs its own data. The gateway cannot know whether order 5520 belongs to customer c_77; the order service can. Checkpoint sends each server a short-lived signed assertion naming the user (`sub`) and the agent (`act.sub`), so the tool can make that check without trusting plain headers.

> [!warn] A gateway decides on what it parses. If it authorizes the tool name from one place and the server executes a different name from another, the policy is bypassed. MCP 2026-07-28 mirrors the method and tool name into headers (`Mcp-Method`, `Mcp-Name`); Checkpoint rejects any request whose headers disagree with the body with `HeaderMismatch` (-32020), so the value it authorizes is the value the server runs ([ADR 0003](https://github.com/Rachneet/ai-system-design-course/blob/main/platform/checkpoint/docs/adr/0003-mcp-2026-07-28-with-legacy-fallback.md)).

## Designing human approval

The MCP spec says there "SHOULD always be a human in the loop with the ability to deny tool invocations" ([tools spec](https://modelcontextprotocol.io/specification/2026-07-28/server/tools#user-interaction-model)). How you build that loop decides whether it protects anything.

### Bind the approval to the exact call

An approval must cover one specific action, not a topic. Checkpoint stores a held call with the agent, the user, the tool and a SHA-256 digest of the tool name plus the canonical JSON of the arguments. To run the call, the agent repeats it with the approval id in `_meta`; the gateway marks the approval `used` only if agent, user and digest all match, in one SQL statement ([`gateway.py`](https://github.com/Rachneet/ai-system-design-course/blob/main/platform/checkpoint/checkpoint/gateway.py)).

```viz
caption: Approval 1 covers one refund of 340 on order 5520, once. Changing the amount or reusing it creates a new request instead of running.
<div class="vz-row"><span class="ch sk">refund 340, order 5520</span><span class="arr sk"></span><span class="ch sk">held: approval 1</span><span class="arr sk"></span><span class="ch sk g">lead approves</span></div>
<div class="vz-row"><span class="ch wide sk m">approval 1 = agent + user + sha256(tool, arguments)</span></div>
<div class="vz-cols" style="--k:3">
  <div class="vz-panel sk b"><h5>Amount changed to 900</h5><div class="vz-row"><span class="ch sk b">digest differs</span></div><p>held again as approval 2</p></div>
  <div class="vz-panel sk g"><h5>Identical call</h5><div class="vz-row"><span class="ch sk g">digest matches</span></div><p>runs; approval 1 marked used</p></div>
  <div class="vz-panel sk b"><h5>Same call again</h5><div class="vz-row"><span class="ch sk b">approval 1 used</span></div><p>held again as approval 3</p></div>
</div>
```

These are the results you will reproduce in Lab 8. Without the binding, an injected agent could get "refund 340" approved and then send "refund 3,400" with the same approval id.

### Show the arguments, not the model's summary

The approver must see what will execute: `orders__issue_refund {"order_id": "5520", "customer_id": "c_77", "amount": 340}`. Checkpoint's `GET /approvals` returns the stored arguments, not anything the model wrote. A model-written explanation can be part of the screen, labelled as such, because it may itself be the product of an injection.

### Decide who may approve

- **Separate credentials.** In Checkpoint, approvers hold tokens with role `approver`, which cannot call tools, and agent tokens cannot approve (the lab shows the 401).
- **Not the requester.** The person the agent acts for should not approve their own high-value action. Checkpoint does not enforce this yet: any approver token can approve any request. In production, compare the approver's identity with the request's `user_id`, and route by policy (refunds to finance, access grants to the resource owner).
- **Record the decision.** Checkpoint stores `decided_by`, `decided_at` and a free-text note with every approval.

### Time out

A pending request should not wait forever, and an approved one should not stay usable for a week. Give pending requests an expiry (minutes for a live chat, hours for an email workflow), give approvals a short validity window after the decision, and tell the user when a request lapses. Checkpoint's approvals have no expiry today; adding one is a stretch goal in the lab.

### Fight approval fatigue

Anthropic reports that Claude Code users approve 93% of permission prompts, and that "over time that leads to approval fatigue, where people stop paying close attention to what they're approving" ([Anthropic engineering, March 2026](https://www.anthropic.com/engineering/claude-code-auto-mode)). An approval that is always granted is a delay, not a control. Hold only what is both risky and rare: let policy allow the small, reversible cases outright (refunds up to 200), forbid the unacceptable ones outright (over 2,000), and send only the middle band to people. Then watch the approval rate per policy. A policy whose holds are approved nearly every time needs a higher threshold or an automatic rule.

> [!numbers] Suppose Relay handles 4,000 refund requests a day (an illustration, not a measurement). If policy holds every refund, a lead reviews 4,000 prompts, about one every 7 seconds across an 8-hour shift. If 85% are 200 or less (allowed) and 1% are over 2,000 (denied), 14% are held: 560 a day, about one a minute. That is still a lot. Measure your own distribution and set the band so a person can read each request.

## Testing policies

Policies are code that can lock out every user at once, or let everything through. Test them like code, in three layers.

**1. Unit tests of decisions.** Call the engine directly with a table of requests and expected outcomes. With Checkpoint's `Policy` class:

```python
@pytest.mark.parametrize(
    "agent, context, allowed, approval, policies",
    [
        ("refunds", ctx(50), True, False, ["refunds-small"]),
        ("refunds", ctx(900), True, True, ["refunds-large-need-approval"]),
        ("refunds", ctx(5000), False, False, []),
        ("refunds", ctx(50, customer="u1"), False, False, ["no-self-refund"]),
        ("refunds", ctx(50, roles=("sales",)), False, False, []),
        ("concierge", ctx(5), False, False, []),
    ],
)
def test_refund_decisions(agent, context, allowed, approval, policies):
    d = POLICY.decide(agent, "call", "payments__refund", context)
    assert (d.allowed, d.needs_approval, d.policies) == (allowed, approval, policies)
```

Asserting the policy names, not only the outcome, catches the case where a call is denied for the wrong reason. Include the boundaries (200, 201, 2,000, 2,001), missing fields and wrong types.

**2. Golden decision logs.** Export a week of real decisions (agent, tool, arguments, user roles) and replay them against a proposed policy. Every changed decision appears in the pull request for a reviewer to accept. Checkpoint's decision log records the agent, user, tool, outcome and policies, but not the arguments, so to replay you also need the arguments from your traces (week 5), with sensitive values masked.

**3. Shadow mode.** Run a new rule against live traffic without enforcing it, and count what it would have changed. AgentCore Policy has a `LOG_ONLY` mode per policy and per engine; its docs describe evaluating every request "as if it were enforced" and reporting which policies "would have changed the decision" ([testing in LOG_ONLY](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-test-a-policy.html)). Promote the rule once that count is zero or every flip is one you want.

> [!tip] Make a bad deploy impossible to apply. Checkpoint refuses a policy file that does not parse: `POST /admin/policy/reload` returns 422 and the running policy stays in place. Run the same parse, your decision tests and schema validation in CI, so a broken policy never reaches the reload.

## Failure modes

| Failure | What happens | Defence |
|---|---|---|
| Identity from arguments | The model writes `user_id: "admin"` and the policy believes it | User and agent only from verified tokens |
| Policy reads a field the tool ignores, or the reverse | Policy checks `amount`; the tool refunds `total` | Per-tool schemas; validate policies against them |
| Erroring `forbid` | A missing field skips the forbid, and a permit allows the call | `has` guards on every forbid; tests with missing fields |
| Floats in arguments | Cedar cannot build the request; every call denied | Integer minor units in schemas |
| Approval not bound | Approve a small call, run a large one | Digest of tool and arguments, single use |
| Approval fatigue | Holds approved by reflex | Allow and forbid the clear cases; track approval rate per policy |
| Gateway bypass | An agent calls the server directly | Network isolation; servers verify the gateway's signed assertion |
| Policy errors invisible | Denials with no reason in the log | Log the engine's errors with the decision (Checkpoint returns them from `decide` but does not store them yet) |

## Design review questions

> [!interview] Take your highest-impact tool. Write the policy that allows it, the forbid that bounds it, and the test that proves the forbid cannot be skipped by a missing field.

> [!interview] Where does each of the four inputs (agent, tool, arguments, user) come from in your system, and which of them can the model influence?

> [!interview] An approver approves a refund of 340. What stops the agent from using that approval for 3,400, or using it twice?

> [!interview] What fraction of held calls are approved, per policy, and what do you do with a policy whose holds are approved 99% of the time?

> [!interview] You need to tighten a refund threshold. How do you find out, before enforcing it, how many real requests it would have changed?

## Further reading

- [Cedar documentation](https://docs.cedarpolicy.com/): the authorization algorithm, policy syntax and schema validation.
- [Open Policy Agent documentation](https://www.openpolicyagent.org/docs), including [policy testing](https://www.openpolicyagent.org/docs/policy-testing) and [decision logs](https://www.openpolicyagent.org/docs/management-decision-logs).
- [Policy in Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy.html) and [Google Agent Gateway](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/gateways/agent-gateway-overview): how the managed platforms place policy.
- [MCP tools specification, 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/server/tools): human in the loop, error handling, security considerations.
- [Claude Code auto mode](https://www.anthropic.com/engineering/claude-code-auto-mode), Anthropic: approval fatigue measured, and one response to it.
- Checkpoint's [README](https://github.com/Rachneet/ai-system-design-course/tree/main/platform/checkpoint), [ADR 0001](https://github.com/Rachneet/ai-system-design-course/blob/main/platform/checkpoint/docs/adr/0001-cedar-policy-with-approval-annotations.md) and [`policies/default.cedar`](https://github.com/Rachneet/ai-system-design-course/blob/main/platform/checkpoint/policies/default.cedar).

```quiz
[
  {"q": "Why is a refund cap written in the system prompt not a policy?", "options": ["Prompts are too short", "The model enforces it, so injected text or a model error can override it, and nothing records why a call was allowed", "Prompts cannot contain numbers", "It is a policy if the model is large enough"], "answer": 1, "why": "A policy is decided outside the model, deterministically, with a logged reason. A prompt only makes bad behaviour less likely."},
  {"q": "In Cedar, one permit and one forbid both match a request. What is the decision?", "options": ["Allow", "Deny", "The policy listed first wins", "It is an error"], "answer": 1, "why": "Forbid overrides permit. Default deny covers the case where nothing matches."},
  {"q": "A Cedar forbid reads context.args.customer_id, and a call arrives without that field. What happens to the forbid?", "options": ["It denies the call", "It errors and is skipped, so it does not block the call", "Cedar fills in an empty string", "The whole request is rejected as malformed"], "answer": 1, "why": "Policies that error are skipped. Guard optional fields with has, so a forbid can never be bypassed by leaving a field out."},
  {"q": "A refund tool takes amount as 50.5 and Checkpoint's policy compares context.args.amount <= 200. What happens?", "options": ["Allowed, because 50.5 is under 200", "Denied, because Cedar has no floating-point type and the request cannot be built", "Cedar rounds to 50", "Held for approval"], "answer": 1, "why": "Cedar has Long integers and a decimal extension type, not floats. Use integer minor units in schemas that policy reads."},
  {"q": "Which approval design stops an agent from turning an approved refund of 340 into 3,400?", "options": ["Approvals that last for the session", "Approvals bound to agent, user and a digest of the tool and exact arguments, used once", "A longer approval message", "Letting the model summarise the request for the approver"], "answer": 1, "why": "Binding to the exact call and consuming the approval on use means any change creates a new request for a person."},
  {"q": "A policy's held calls are approved 99% of the time. What is the best response?", "options": ["Add a second approver", "Move the clear cases to allow or forbid rules and keep holds for the risky, rare band", "Hide the arguments to save the approver time", "Remove the decision log"], "answer": 1, "why": "An approval that is always granted is a delay, not a control, and it trains people to stop reading."},
  {"q": "Why should the tool still check that order 5520 belongs to the customer, when the gateway already ran policy?", "options": ["It should not; that duplicates the gateway", "Only the order system has the data to answer it; the gateway decides on agent, user, tool and arguments", "Gateways cannot read arguments", "To make the call slower"], "answer": 1, "why": "Policy at the gateway and ownership checks at the tool cover different questions. The signed assertion tells the tool which user to check."}
]
```
