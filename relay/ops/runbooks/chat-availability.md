# Runbook: chat availability burn

**Alert:** ChatAvailabilityFastBurn / SlowBurn. Turns are ending in errors faster than the SLO allows.

1. Open the Relay dashboard, Health row. Is it all traffic or one route? Did a deploy happen in the last hour?
2. If a deploy correlates: roll back now, diagnose later.
   `gcloud run services update-traffic relay-api --to-revisions=PREVIOUS_REVISION=100`
3. If ProviderErrorsHigh is also firing, follow `provider-outage.md`.
4. Otherwise open error traces (status ERROR) in the trace backend and read three. Database? Tool? Model?
5. If users are getting nothing useful and the cause is unknown after 15 minutes, pause the assistant:
   `PUT /flags {"key": "agent.enabled", "value": false}` (staff token) and post a status update.
6. Afterwards: blameless postmortem, plus an eval case or alert that would have caught it earlier.
