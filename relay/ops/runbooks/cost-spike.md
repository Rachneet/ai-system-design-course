# Runbook: cost spike or broken prompt cache

**Alerts:** CostSpike, PromptCacheBroken.

1. Dashboard, Cost row: which model, and is spend up per turn or just more turns?
2. Most expensive traces from the last hour (sort by cost attributes):
   - **Many steps on the same tool** (looping)? Check the last deploy; roll back; see `agent-quality.md`.
   - **Huge tool results**? Find the tool; trim its output; disable it if needed (`tools.disabled`).
   - **One customer hammering**? Rate limits should hold; lower their budget or block the account.
   - **Cache hit ratio collapsed**? Diff the system prompt and tool definitions in the last deploy. Anything
     dynamic (dates, IDs, unsorted JSON) near the top of the prompt breaks caching. Roll back if unsure.
3. If spend keeps climbing and the cause is unknown: `agent.force_fallback=true` (the cheaper model) and page the lead.
