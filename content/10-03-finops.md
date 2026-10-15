---
id: w10-finops
week: 10
kind: lesson
title: "AI FinOps: unit economics, chargeback and budgets"
short: AI FinOps
minutes: 50
summary: Measure AI cost per resolved ticket instead of per token, allocate it to orgs, teams and apps with Switchboard's ledger, enforce budgets without causing outages, forecast from business drivers, pull the biggest levers (resolution rate, then model mix), choose between commitments, on-demand and self-hosting, and reconcile with provider bills using FOCUS.
---

## Why it matters

The [cost lesson in Week 6](#w6-tradeoffs) taught you to price one conversation and compare designs. That is enough for one product. A company running twenty agents needs more: who spent what, whether it was worth it, what next quarter will cost, and how to stop one runaway app without taking down the others. That practice is **FinOps**, and the FinOps Foundation's [FinOps for AI overview](https://www.finops.org/wg/finops-for-ai-overview/) applies it to AI: track and review AI costs regularly, set quotas, allocate spend, and tie it to business outcomes.

The most important idea in this lesson is the unit. Tokens are how vendors bill you. They are not what the business buys.

## Unit economics: cost per resolved ticket

The FinOps Foundation's [Unit Economics capability](https://www.finops.org/framework/capabilities/unit-economics/) separates **resource efficiency** metrics (its examples include "cost per token") from **business** metrics (its examples include "cost per case resolved" and "cost to serve"). For a helpdesk, the business metric is **cost per resolved ticket**. For other agents it is cost per successful task: per invoice processed, per pull request merged, per lead qualified.

Three definitions make the number honest:

1. **Resolved** means closed and not reopened within a set window (say 7 days), with no human doing the work. A ticket the agent closed and the user reopened is a failure that cost money.
2. **The numerator includes failed attempts.** Every conversation that ended in an escalation still spent tokens. Divide all AI spend by resolved tickets, not by conversations.
3. **Fully loaded** includes the people: approvers' time and the humans who handle escalations. That is the number to compare with the desk before AI.

### Worked numbers: the employee IT desk, one month

Assumptions for this example (label yours the same way in your cost model): 40,000 conversations a month. Each conversation makes one router call on a small model (3,000 tokens in, 50 out) and four agent calls on a mid-tier model (12,000 tokens in, 75% read from the prompt cache and 25% written to it, 300 out). Prices are the course's two tiers from [Week 6](#w6-tradeoffs): mid-tier $2 input, $2.50 cache write, $0.10 cache read, $10 output per million tokens; small $0.10 input and $0.50 output. Human time costs $0.80 a minute, loaded.

| Line | Arithmetic | Per month |
|---|---|---|
| Router calls | 40,000 × (3,000 × $0.10 + 50 × $0.50) / 1M | $13 |
| Agent calls | 40,000 × 4 × (12,000 × (0.25 × $2.50 + 0.75 × $0.10) + 300 × $10) / 1M | $1,824 |
| **Model spend** (Switchboard ledger) | | **$1,837** |
| Platform share: gateways, registry, databases, search, observability | allocated, see chargeback below | $1,100 |
| Eval and red-team runs | metered on the team's eval app key | $250 |
| **AI cost** | | **$3,187** |
| Approvals | 1,500 holds × 2 min × $0.80 | $2,400 |
| Escalations | 16,000 conversations (40%) × 10 min × $0.80 | $128,000 |
| **Fully loaded** | | **$133,587** |

The agent resolves 24,000 tickets (60%). So:

- AI cost per conversation: $3,187 / 40,000 = **$0.080**
- AI cost per AI-resolved ticket: $3,187 / 24,000 = **$0.133**
- Fully loaded cost per resolved ticket: $133,587 / 40,000 = **$3.34**, against **$8.00** when people handled all 40,000 at 10 minutes each.

```viz
caption: Per AI-resolved ticket the agent costs 13 cents, and 40% of that pays for conversations that ended with a human anyway.
<div class="vz-bars"><span>model tokens</span><span class="bar sk"><i class="sk w" style="--w:58%"></i></span><b>$0.077</b><span>platform share</span><span class="bar sk"><i class="sk w" style="--w:35%"></i></span><b>$0.046</b><span>evals, red-team</span><span class="bar sk"><i class="sk w" style="--w:8%"></i></span><b>$0.010</b><span>total</span><span class="bar sk"><i class="sk w" style="--w:100%"></i></span><b>$0.133</b></div>
<div class="vz-row"><span class="ch sk g">$0.080 per conversation</span><span class="arr sk"></span><span class="ch sk b">$0.133 per resolved ticket</span><b>the gap is failed attempts</b></div>
<div class="vz-src">This lesson's worked example: assumed traffic, the Week 6 price tiers (list prices from the <a href="https://platform.claude.com/docs/en/about-claude/pricing">Anthropic</a> and <a href="https://developers.openai.com/api/docs/pricing">OpenAI</a> pricing pages, October 2026), assumed platform and eval allocations.</div>
```

### The lever that matters most

Now compare two improvements. Halving the model bill (a cheaper model with no quality loss) saves $918 a month. Raising the resolution rate from 60% to 70% moves 4,000 tickets from people to the agent: 4,000 × 10 min × $0.80 = **$32,000** a month, about 35 times more.

```viz
caption: Fully loaded, model tokens are about 1% of the cost of a resolved ticket. Resolution rate moves the total; token price barely does.
<div class="vz-cols">
  <div class="vz-panel sk"><h5>Fully loaded, per resolved ticket</h5>
    <div class="vz-bars"><span>people only</span><span class="bar sk"><i class="sk w" style="--w:100%"></i></span><b>$8.00</b><span>agent, 60% resolved</span><span class="bar sk"><i class="sk w" style="--w:42%"></i></span><b>$3.34</b><span>agent, 70% resolved</span><span class="bar sk"><i class="sk g" style="--w:32%"></i></span><b>$2.54</b></div>
  </div>
  <div class="vz-panel sk"><h5>Monthly saving</h5>
    <div class="vz-bars"><span>halve model bill</span><span class="bar sk"><i class="sk g" style="--w:3%"></i></span><b>$918</b><span>+10 points resolved</span><span class="bar sk"><i class="sk g" style="--w:100%"></i></span><b>$32,000</b></div>
  </div>
</div>
<div class="vz-src">This lesson's worked example; human time at an assumed $0.80 per minute, 10 minutes per escalated ticket.</div>
```

> [!rule] Optimise cost per resolved ticket, not cost per token. A change that saves tokens and loses resolutions is a cost increase, and a change that spends more tokens and resolves more tickets is usually a saving.

This is also why cost dashboards must sit next to quality dashboards. The eval suite and online judges from Weeks 3 and 5 are FinOps tools: they tell you whether a cheaper configuration still resolves tickets.

### Joining cost to outcomes

Switchboard's ledger records cost per request, by org, team, app and model. The ticketing system records which tickets were resolved. Cost per resolved ticket needs a key that joins them. Switchboard's `usage_events` table has a `request_id` but no ticket or conversation ID, so the join has to come from somewhere:

- **Trace IDs.** Every model call in a conversation shares a trace. Record the trace ID on the ticket and in the ledger, and join through it.
- **A request tag.** Have the agent send the ticket ID in a header that the gateway stores with the usage row. This is a small extension to Switchboard, and the capstone asks for it.

```sql
-- cost per resolved ticket, per app, for October
SELECT u.app_id,
       sum(u.cost_usd) / count(DISTINCT t.id) FILTER (WHERE t.resolved_by = 'agent'
                                                    AND t.reopened_at IS NULL) AS cost_per_resolved
FROM usage_events u
JOIN tickets t ON t.id = u.ticket_id          -- the tag you add
WHERE u.ts >= '2026-10-01' AND u.ts < '2026-11-01'
GROUP BY u.app_id;
```

## Showback and chargeback

The FinOps Foundation's [Invoicing and Chargeback capability](https://www.finops.org/framework/capabilities/invoicing-chargeback/) separates the two by formality. **Showback** shows each group the cost of what it uses; every FinOps practice needs it. **Chargeback** posts those costs to the group's budget in the accounts, which depends on your company's accounting policies. Start with showback. Move to chargeback when teams trust the numbers.

Switchboard makes allocation nearly free, because every request carries a key, and every key belongs to an app, a team and an org. There is no untagged spend to chase.

```viz
caption: Every request's cost lands on exactly one app, so the tree always adds up. Shared platform cost is the only part you allocate by rule.
<div class="vz-row"><span class="ch wide sk c">org: employee-desk, $2,977 metered</span></div>
<div class="vz-cols">
  <div class="vz-panel sk"><h5>team: it-support, $2,087</h5>
    <div class="vz-row"><span class="ch sk c">it-agent-prod $1,837</span><span class="ch sk c">it-evals $250</span></div>
  </div>
  <div class="vz-panel sk"><h5>team: hr-ops, $890</h5>
    <div class="vz-row"><span class="ch sk c">hr-agent-prod $780</span><span class="ch sk c">hr-evals $110</span></div>
  </div>
</div>
<div class="vz-row"><span class="ch sk m">platform share: allocated by rule</span><span>for example in proportion to metered spend or requests, agreed with finance in advance</span></div>
```

Pull the numbers from the admin API:

```bash
curl -H "Authorization: Bearer $ADMIN" \
  "https://switchboard.internal/admin/usage?month=2026-10&group_by=team"
# rows: id, requests, cost_usd, input_tokens, output_tokens, cache_read_tokens, fallbacks, errors
```

Design choices that keep chargeback fair:

- **One app per environment and purpose.** Production, staging and evals each get their own app and key, so a nightly eval run never looks like production traffic. Eval spend is real spend and belongs to the team that owns the suite.
- **Allocate shared cost by a published rule.** The platform's fixed cost (gateways, databases, observability) is not metered per request. Pick one rule (proportional to metered spend is the simplest), publish it, and do not change it mid-quarter.
- **Show cache and fallback columns.** `cache_read_tokens` and `fallbacks` explain most surprises: a prompt change that broke caching, or a provider outage that pushed traffic to a pricier fallback.

## Budgets and enforcement levels

A budget without enforcement is a forecast. Enforcement without levels is an outage. Use a ladder:

```viz
caption: Escalate enforcement in steps. A hard stop on a customer-facing app is an outage you scheduled yourself.
<div class="vz-row"><span class="ch sk">1. show</span><span class="arr sk"></span><span class="ch sk w">2. alert</span><span class="arr sk"></span><span class="ch sk w">3. degrade</span><span class="arr sk"></span><span class="ch sk b">4. stop</span></div>
<div class="vz-cols" style="--k:4">
  <div class="vz-panel sk"><h5>Show</h5><p>spend to date against budget on the team's dashboard</p></div>
  <div class="vz-panel sk w"><h5>Alert</h5><p>at 50%, 80% and 100%, and when burn rate runs ahead of the month</p></div>
  <div class="vz-panel sk w"><h5>Degrade</h5><p>cheaper model, lower max tokens, sample fewer online judges</p></div>
  <div class="vz-panel sk b"><h5>Stop</h5><p>refuse new requests; for experiments, evals and internal tools</p></div>
</div>
```

Switchboard implements the last step today: before each request it checks the monthly budgets of the app, its team and its org (cached for about two seconds), and refuses with HTTP 429 and an `x-switchboard-limit: budget:<scope>` header when one is used up. Steps 1 to 3 are yours to add from the ledger and the `switchboard_cost_usd_total` metric.

> [!warn] Switchboard reports an exhausted budget as a 429 `rate_limit_error`, and provider SDKs retry 429s by default. It therefore adds `x-should-retry: false`, which the official OpenAI and Anthropic SDKs honour, and `x-switchboard-limit: budget:<scope>`. Your own retry and fallback layers must honour them too (Relay's does): a fallback model through the same gateway hits the same budget. Fail fast with a clear message.

Rules that prevent self-inflicted outages:

- **Customer-facing apps get alerts and degradation, not a hard stop.** Put the hard stop at the org level, set well above expected spend, as a guard against runaway loops.
- **Per-user limits stop denial of wallet.** Budgets protect the month; rate and token limits per user (Week 4) protect the hour.
- **Burn-rate alerts beat threshold alerts.** "80% spent on day 12 of 31" is an incident; "80% spent on day 28" is normal. Alert when spend to date runs more than 10 points ahead of the elapsed share of the month.

## Forecasting from drivers

Forecast from the business, not from last month's bill. The driver model is the same multiplication you used for cost per ticket:

**model spend = tickets × conversations per ticket × model cost per conversation**

> [!numbers] The IT desk expects 30% more tickets in December (year-end access reviews): 52,000 conversations × $0.0459 = **$2,387** of model spend, against $1,837 in October. If the `it-agent-prod` app's budget stays at $2,200, Switchboard would refuse requests in the last days of the month. Raise the budget before December, or plan the degrade step, rather than finding out on 29 December.

Things that break forecasts, and how to see them coming:

| Driver | Watch |
|---|---|
| Volume (seasonality, launches, new tenants) | Ticket forecasts from the business; one line per tenant |
| Conversation length and steps per turn | Calls per conversation from traces; a prompt change can add a step |
| Cache hit rate | `cache_read_tokens` share; a broken prefix can multiply input cost several times |
| Model prices and model mix | Vendors' pricing pages; your routing share per model |
| Fallbacks | `fallbacks` column; an outage can move traffic to a pricier model for hours |

## The model mix: the biggest lever inside the AI bill

Inside the AI bill, which model serves which route is the largest lever. Week 6 showed caching and routing taking one design from $0.19 to $0.035 per conversation. On the IT desk, suppose evals show the small model resolves password resets and account unlocks (35% of conversations) as well as the mid-tier model, at 5 calls of 8,000 tokens in and 300 out:

- Small-model conversation: 5 × (8,000 × $0.10 + 300 × $0.50) / 1M = **$0.00475**
- Blended: 0.35 × $0.00475 + 0.65 × $0.0459 = **$0.0315** per conversation, so model spend falls from $1,837 to **$1,260** a month.

That saves $577 a month. Now check it against the unit that matters: if the cheaper route resolved 5 points fewer of those 14,000 conversations, 700 more tickets would reach people at $8 each, **$5,600** a month. Ship the routing change only when the route's eval suite and online resolution rate say quality held.

> [!tip] Report savings in the unit the business uses: "routing saved $577 a month and resolution held at 60%" is a result; "routing cut tokens by 31%" is not.

## Commitments, on-demand and self-hosting

The FinOps for AI overview lists the purchasing options: on-demand per token; **committed use discounts** and **provisioned capacity** (it cites examples such as Azure OpenAI's provisioned throughput units and OpenAI's Scale Tier), which trade a commitment for a lower rate or reserved throughput and "can result in low utilization" if usage does not match; and **batch** or spare-capacity pricing for work that can wait. Self-hosting an open model is the extreme case of commitment: you pay for GPUs whether or not anyone is asking.

```viz
caption: Commit to the floor of steady usage, pay on demand for the peaks, and send anything that can wait to batch.
<div class="vz-bars"><span>Jan</span><span class="bar sk"><i class="sk w" style="--w:62%"></i></span><b>$1,700</b><span>Feb</span><span class="bar sk"><i class="sk w" style="--w:66%"></i></span><b>$1,800</b><span>Mar</span><span class="bar sk"><i class="sk w" style="--w:70%"></i></span><b>$1,920</b><span>Dec</span><span class="bar sk"><i class="sk w" style="--w:87%"></i></span><b>$2,387</b></div>
<div class="vz-cols" style="--k:3">
  <div class="vz-panel sk g"><h5>Commit</h5><p>up to the lowest month you are confident of, not the average</p></div>
  <div class="vz-panel sk"><h5>On demand</h5><p>everything above the floor</p></div>
  <div class="vz-panel sk g"><h5>Batch</h5><p>nightly evals, offline judging, bulk classification</p></div>
</div>
<p>illustrative monthly model spend for the IT desk</p>
```

Several providers price their batch APIs at about half the on-demand rate (see the [Anthropic](https://platform.claude.com/docs/en/about-claude/pricing) and [OpenAI](https://developers.openai.com/api/docs/pricing) pricing pages). Eval runs and red-team suites rarely need an answer in seconds, so they are the first workload to move.

For self-hosting, use the calculator from the [inference lesson](#w5-inference). It starts at a realistic 40% utilisation; idle hours are the cost that per-token pricing hides from you.

```widget
{"type": "cost", "preset": "Same node at a realistic 40% utilisation"}
```

> [!warn] The calculator prices output tokens. Agent workloads are input-heavy: the IT desk above reads about 51,000 tokens for every 1,250 it writes, roughly 40 to 1. Prefill capacity is a large part of a self-hosted fleet for this shape of traffic, so size GPUs on both, and compare against your cached input price, not the uncached one.

## Reconciling with the bill: FOCUS

Switchboard computes cost from list prices in its own price table. Your invoice includes discounts, commitments, credits and taxes, so the two will differ. Reconcile monthly: the ledger is right about **who** spent, the invoice is right about **how much**, and the ratio between them is your effective discount to apply in showback.

The FinOps Foundation's [FOCUS specification](https://focus.finops.org/what-is-focus/) is an open format for billing data from cloud, SaaS, AI and other technology vendors, so cost from different providers lands in the same columns. The current version, FOCUS 1.4, was ratified on 4 June 2026 and added Invoice Detail and Billing Period datasets for tying usage to invoices. The next version, 1.5, is in its working draft with ratification planned for 3 December 2026; its [release scope](https://focus.finops.org/focus-1-5-release-scope/) includes AI cost columns that name the model and its developer, separate cached from uncached and input from output tokens, and identify the principal and API key behind a charge. Until 1.5 is ratified and vendors adopt it, treat those columns as planned, not available.

> [!tip] Export Switchboard's ledger in FOCUS-style columns (billing period, provider, service, charge, cost, usage quantity and unit, plus your org, team and app as tags). Then your gateway's view and your providers' bills join in one table, and the move to FOCUS 1.5 is a mapping change.

## Failure modes

| Failure | Symptom | Mitigation |
|---|---|---|
| Optimising the wrong unit | Token cost falls, escalations rise | Report cost per resolved ticket beside every saving |
| Budget as outage | Customer desk refuses requests on day 29 | Alerts and degradation for critical apps; hard stops only at org level or for non-critical apps |
| Retry storm on budget refusal | Slow failures, extra load on the gateway | Honour `x-should-retry: false` and the `budget:` header in every retry layer |
| Invisible eval spend | Team bill doubles after adding pass^k trials | Separate eval app keys; show them in the team's tree |
| Cache collapse after a deploy | Input cost jumps several times with no traffic change | Alert on cache-read share per app (Week 5) |
| Fallback cost spike | A provider outage moves traffic to a pricier model | Watch the `fallbacks` column; price fallbacks into the forecast |
| Disputed allocation | Teams argue about shared platform cost every month | One published rule, agreed in advance, reviewed quarterly |
| Ledger and invoice disagree | Finance distrusts showback | Monthly reconciliation and an effective-discount factor |

## Design review questions

> [!interview] What is your cost per resolved ticket, fully loaded, and how does it compare with the process before AI?

> [!interview] What happens to a customer-facing agent when its team runs out of budget on the 29th?

> [!interview] Which single change would most reduce your cost per resolved ticket next quarter, and how would you prove it did not hurt quality?

> [!interview] How much of last month's spend was evals, fallbacks or retries, and where can you see it?

> [!interview] Why does your gateway's cost figure differ from the invoice, and by how much?

## Further reading

- [FinOps for AI overview](https://www.finops.org/wg/finops-for-ai-overview/), FinOps Foundation: KPIs such as cost per inference and cost per API call, and purchasing options.
- FinOps Framework capabilities: [Unit Economics](https://www.finops.org/framework/capabilities/unit-economics/) and [Invoicing and Chargeback](https://www.finops.org/framework/capabilities/invoicing-chargeback/).
- [FOCUS](https://focus.finops.org/what-is-focus/) and the [FOCUS 1.5 release scope](https://focus.finops.org/focus-1-5-release-scope/).
- [Switchboard README](https://github.com/Rachneet/ai-system-design-course/tree/main/platform/switchboard): the ledger, budgets and chargeback endpoint.
- [Failure modes and cost trade-offs](#w6-tradeoffs) and [LLM inference for system designers](#w5-inference).

```quiz
[
  {"q": "Why is cost per resolved ticket a better unit than cost per token?", "options": ["Tokens are hard to count", "It measures what the business buys and includes the cost of attempts that failed", "Vendors bill per ticket", "It is always lower"], "answer": 1, "why": "Tokens are a resource metric. A cheaper configuration that resolves fewer tickets raises the business cost."},
  {"q": "An agent costs $0.080 per conversation and resolves 60% of conversations. What is the AI cost per AI-resolved ticket?", "options": ["$0.048", "$0.080", "About $0.133", "$0.200"], "answer": 2, "why": "All spend divided by resolved tickets: $0.080 / 0.6 is about $0.133."},
  {"q": "What is the difference between showback and chargeback?", "options": ["Showback is for cloud, chargeback for AI", "Showback shows groups their costs; chargeback formally posts them to the groups' budgets", "Chargeback is optional for every practice and showback is forbidden", "They are the same"], "answer": 1, "why": "The FinOps Foundation describes the difference as formality: chargeback goes into the accounts."},
  {"q": "Your customer-support agent's team budget will run out on day 29. What should the platform do?", "options": ["Hard stop at 100%", "Alert early on burn rate and degrade gracefully (cheaper model, fewer online judges); keep hard stops for non-critical apps or a high org-level guard", "Nothing", "Delete the app's key"], "answer": 1, "why": "A hard stop on a customer-facing app is a self-inflicted outage."},
  {"q": "Routing 35% of traffic to a small model saves $577 a month. Resolution on that route drops 5 points, sending 700 more tickets to people at $8 each. What is the net effect?", "options": ["Saves $577", "Costs about $5,000 more a month", "No change", "Saves $5,600"], "answer": 1, "why": "$5,600 of extra human work against $577 saved: a net loss of about $5,000."},
  {"q": "How much model spend should you cover with a commitment?", "options": ["The peak month", "The average month", "The floor of steady usage you are confident of", "None, ever"], "answer": 2, "why": "Commitments are paid whether used or not; cover the floor and pay on demand above it."},
  {"q": "What is the status of AI token columns (model, cached versus uncached tokens) in FOCUS as of October 2026?", "options": ["In FOCUS 1.0", "In FOCUS 1.4, ratified June 2026", "Planned for FOCUS 1.5, with ratification scheduled for 3 December 2026", "FOCUS does not cover AI vendors"], "answer": 2, "why": "FOCUS 1.4 is current; the AI cost columns are in the 1.5 working draft."}
]
```
