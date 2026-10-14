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

| SLI (what you measure) | SLO (target over 28 days) |
|---|---|
| Availability: chat turns that complete without a server error | 99.5% |
| Latency: turns with time to first token under 2.5 s | 95% |
| Latency: turns completing under 15 s | 99% |
| Quality: sampled turns passing the online "no unauthorised promise" judge | 98% |
| Safety: must-never events (cross-customer data, refund over limit without approval) | 0 |
| Freshness: KB changes searchable within 10 minutes | 99% |

An SLO of 99.5% gives an **error budget** of 0.5%: about 3.4 hours of full outage, or a lot of small failures, per 28 days. The budget makes trade-offs explicit: when it is healthy, ship faster; when it is burning, slow down and fix reliability.

## Burn-rate alerts

Alerting on "error rate > 1% for 5 minutes" is noisy for short spikes and slow for gradual problems. The SRE workbook's [Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/) recommends **multi-window burn-rate alerts**: page when you are consuming the error budget much faster than sustainable, confirmed over a short window so it resets quickly once fixed.

> [!numbers] With a 99.5% SLO over 28 days, burning at 14.4× the sustainable rate exhausts 2% of the monthly budget in one hour. A common setup: **page** if the burn rate is above 14.4 over the last hour *and* the last 5 minutes; **page** if above 6 over 6 hours *and* 30 minutes; **ticket** if above 1 over 3 days. A 14.4× burn on a 0.5% budget means an error rate of 7.2%.

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
| Provider outage or overload | Provider error rate, 429 rate, latency from provider spans | Page (with automatic fallback) |
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

- **Detect** fast with error-rate and latency alerts scoped to provider spans, and subscribe to the provider's status page.
- **Fail over automatically** where you have a tested fallback (another model or region), with a circuit breaker so users do not wait on timeouts.
- **Degrade gracefully**: disable optional features, serve canned answers for top FAQs, route to humans, show an honest banner.
- **Protect your budget during recovery**: a backlog of retries can blow through rate limits and cost when the provider comes back. Cap retry queues.

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
