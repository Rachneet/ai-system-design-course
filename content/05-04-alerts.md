---
id: w5-alerts
week: 5
kind: lesson
title: Alerts for outages and incidents
short: Alerting + incidents
minutes: 40
summary: Define service level objectives for an AI system, alert on error-budget burn rather than noise, cover the AI-specific failure modes that do not throw errors, and run incidents with runbooks and kill switches.
---

## Alert on symptoms users feel

A good alert means a human must act now, and it fires rarely enough that people still pay attention. Most teams alert on too much (every 5xx, every CPU spike) and on too little (nothing fires when answers quietly get worse).

Start from what users experience, expressed as **service level objectives** (SLOs). The Google SRE [chapter on SLOs](https://sre.google/sre-book/service-level-objectives/) is the reference.

| SLI (what you measure) | SLO (target over 30 days) |
|---|---|
| Availability: chat turns that complete without a server error | 99.5% |
| Latency: turns with time to first token under 2.5 s | 95% |
| Latency: turns completing under 15 s | 99% |
| Quality: sampled turns passing the online "no unauthorised promise" judge | 98% |
| Safety: must-never events (cross-customer data, refund over limit without approval) | 0 |
| Freshness: KB changes searchable within 10 minutes | 99% |

An SLO of 99.5% gives an **error budget** of 0.5%: about 3.6 hours of full outage, or a lot of small failures, per 30 days. The budget makes trade-offs explicit: when it is healthy, ship faster; when it is burning, slow down and fix reliability.

## Burn-rate alerts

Alerting on "error rate > 1% for 5 minutes" is noisy for short spikes and slow for gradual problems. The SRE workbook's [Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/) recommends **multi-window burn-rate alerts**: page when you are consuming the error budget much faster than sustainable, confirmed over a short window so it resets quickly once fixed.

> [!numbers] With a 99.5% SLO over 30 days, burning at 14.4× the sustainable rate exhausts 2% of the monthly budget in one hour. A common setup: **page** if the burn rate is above 14.4 over the last hour *and* the last 5 minutes; **page** if above 6 over 6 hours *and* 30 minutes; **ticket** if above 1 over 3 days *and* 6 hours. A 14.4× burn on a 0.5% budget means an error rate of 7.2%.

```viz
caption: Three windows, three speeds of trouble. A fast burn pages within the hour; a slow leak becomes a ticket before it eats the month.
<div class="vz-bars">
<span>page: 1 h, check 5 min</span><span class="bar sk"><i class="sk b" style="--w:20%"></i></span><b>14.4x: 2% of budget</b>
<span>page: 6 h, check 30 min</span><span class="bar sk"><i class="sk b" style="--w:50%"></i></span><b>6x: 5%</b>
<span>ticket: 3 days, check 6 h</span><span class="bar sk"><i class="sk w" style="--w:100%"></i></span><b>1x: 10%</b>
</div>
<div class="vz-cols" style="--k:3">
  <div class="vz-panel sk"><h5>Budget at 99.5%</h5><p class="big g">3.6 h</p><p>of full outage per 30 days</p></div>
  <div class="vz-panel sk"><h5>Fast burn means</h5><p class="big b">7.2%</p><p>errors: 14.4 x 0.5%</p></div>
  <div class="vz-panel sk"><h5>Short window</h5><p class="big w">1/12</p><p>of the long one, so the alert clears soon after a fix</p></div>
</div>
<div class="vz-src">Windows, burn rates and budget shares from Google's SRE workbook, <a href="https://sre.google/workbook/alerting-on-slos/">Alerting on SLOs</a> (table 5-8). Bars show the share of the 30-day budget each alert has spent when it fires. 0.5% x 720 h = 3.6 h.</div>
```

```yaml
# Prometheus-style rule sketch
- alert: ChatAvailabilityFastBurn
  expr: |
    (sum(rate(chat_turns_failed[1h])) / sum(rate(chat_turns_total[1h]))) > (14.4 * 0.005)
    and
    (sum(rate(chat_turns_failed[5m])) / sum(rate(chat_turns_total[5m]))) > (14.4 * 0.005)
  labels: {severity: page}
  annotations:
    runbook: https://github.com/your-org/relay/blob/main/runbooks/chat-availability.md
```

## AI-specific alerts

Several important failure modes produce no errors at all. Cover them explicitly:

| Condition | Signal | Severity |
|---|---|---|
| Provider outage or overload | Provider error rate (429, 5xx, Anthropic's 529, OpenAI's 503), latency from provider spans, split by `gen_ai.provider.name` | Page (with automatic fallback) |
| Cost spike | $/hour above 2× the same hour last week; any single conversation over $5 | Page for spikes, ticket for drift |
| Looping agents | Step-limit hits per hour; calls per turn p95 | Ticket, page if spiking |
| Quality regression | Online judge pass rate drops X points vs 7-day baseline | Ticket; page if after a deploy |
| Guardrail anomaly | Block rate 3× baseline (or drops to zero, meaning the guardrail broke) | Ticket |
| Must-never event | Any detected occurrence | Page immediately |
| Cache breakage | Cache hit rate drops below threshold | Ticket (it is a cost incident) |
| Ingestion stalled | Queue age > 15 minutes; DLQ growth | Ticket, page for long stalls |
| Escalation surge | Human handoff rate 2× baseline | Ticket to support ops |

Quality alerts need statistical care: with 5% sampling, a drop over 30 minutes may be noise. Compare against a baseline window with enough samples and alert on sustained drops.

## Provider outages

Your system depends on a model API you do not control. Plan for it:

- **Detect** fast with error-rate and latency alerts scoped to provider spans, and subscribe to each provider's status page.
- **Fail over automatically** where you have a tested fallback (another model, region or provider), with a circuit breaker so users do not wait on timeouts. A fallback on a different provider survives that provider's outage; a fallback on the same provider often does not. A self-hosted open model (vLLM, Ollama) is a last-resort fallback that no outside outage can take away, if your evals say it is good enough.
- **Degrade gracefully**: disable optional features, serve canned answers for top FAQs, route to humans, show an honest banner.
- **Protect your budget during recovery**: a backlog of retries can blow through rate limits and cost when the provider comes back. Cap retry queues.

```viz
caption: When the primary provider fails, each step down the chain trades a little quality for staying up. Every step must be tested before the outage, not during it.
<div class="vz-row"><span class="ch sk b">1. primary fails</span><span class="arr sk"></span><span class="ch sk">breaker opens</span></div>
<div class="vz-row"><span class="ch sk g">2. fallback provider</span><span class="arr sk"></span><span class="ch sk">cache starts cold</span></div>
<div class="vz-row"><span class="ch sk w">3. degrade</span><span class="arr sk"></span><span class="ch sk">no rerank, canned FAQs</span></div>
<div class="vz-row"><span class="ch sk w">4. human handoff</span><span class="arr sk"></span><span class="ch sk">honest banner</span></div>
<div class="vz-row"><b>Relay:</b><span class="ch sk">RELAY_MODEL=openai:gpt-5</span></div>
<div class="vz-row"><b>fallback:</b><span class="ch sk">gemini:gemini-2.5-flash</span></div>
```

## Kill switches

Have flags you can flip in seconds, without a deploy, and practice using them:

- Disable a specific tool (for example `issue_refund`) while keeping chat up.
- Force all traffic to a fallback model.
- Turn off the agent entirely and show a support contact form.
- Pause ingestion (if bad content is being indexed).

A kill switch you have never tested is a hope, not a control.

## Runbooks

Every paging alert links to a runbook: a short page that says what the alert means, how to check impact, the first three things to try, and how to escalate. Keep runbooks next to the code, and update them after every incident.

```markdown
# Runbook: Relay cost spike

**Alert:** spend per hour > 2x same hour last week.

1. Open the "Cost" dashboard. Is it one tenant, one route, or everything?
2. Open the top 10 most expensive traces from the last hour.
   - Looping (many steps, same tool)? → check recent deploys; roll back; lower MAX_STEPS via flag.
   - Huge tool results? → identify the tool; enable truncation flag.
   - One user or tenant hammering? → apply per-user block via admin API.
   - Cache hit rate collapsed? → diff system prompt and tools in last deploy; roll back.
3. If spend > $X/hour and cause unknown: flip `agent.force_small_model` and page the on-call lead.
```

## Incident response

When something breaks:

1. **Acknowledge** and name an incident lead.
2. **Mitigate first** (roll back, kill switch, fail over), diagnose later.
3. **Communicate** to stakeholders at regular intervals.
4. **Write a blameless postmortem**: timeline, impact (users, money, data), root causes, what went well, and action items. For AI incidents, one action item is almost always "add eval cases that would have caught this" and often "add an alert for this symptom".

AI incidents are frequently not outages: a prompt change that made refunds too generous for two days, a KB article with wrong information that the agent quoted 3,000 times, an injection that worked. Treat them with the same process.

## Design review questions

> [!interview] What are your SLOs, and how much error budget is left this month?

> [!interview] How would you find out, within an hour, that the agent started promising refunds it cannot give?

> [!interview] Your primary and fallback models: are they on different providers, and when did you last fail over for real?

> [!interview] The model provider is down for 40 minutes. Walk me through what users see minute by minute.

> [!interview] When did you last flip each kill switch?

## Further reading

- [Service Level Objectives](https://sre.google/sre-book/service-level-objectives/), Google SRE book.
- [Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/), Google SRE workbook. The burn-rate method in detail.
- [Monitoring Distributed Systems](https://sre.google/sre-book/monitoring-distributed-systems/), on what to page for.
- [Circuit Breaker](https://martinfowler.com/bliki/CircuitBreaker.html), Martin Fowler.
- The full [SRE book](https://sre.google/sre-book/table-of-contents/), free online.

```quiz
[
  {"q": "With a 99.5% availability SLO, what error rate corresponds to a 14.4x burn rate?", "options": ["0.5%", "1.44%", "7.2%", "14.4%"], "answer": 2, "why": "Sustainable error rate is 0.5%. Multiply by 14.4 to get 7.2%."},
  {"q": "Why combine a long and a short window in burn-rate alerts?", "options": ["To double the alerts", "The long window shows significant budget consumption; the short window confirms it is still happening, so the alert resets quickly after a fix", "Prometheus requires it", "To reduce storage"], "answer": 1, "why": "Multi-window alerts are both significant and responsive, cutting false pages and stale alerts."},
  {"q": "A guardrail's block rate drops to zero. Why might that be an alert?", "options": ["It is good news", "It likely means the guardrail broke or was bypassed, not that all inputs became safe", "It saves money", "It means traffic stopped"], "answer": 1, "why": "Real traffic always contains some blockable content. A sudden zero usually signals a failure."},
  {"q": "During an incident, what comes first?", "options": ["Root cause analysis", "Mitigation: roll back, kill switch, or fail over", "Writing the postmortem", "Adding tests"], "answer": 1, "why": "Stop the harm first. Diagnose and prevent afterwards."}
]
```
