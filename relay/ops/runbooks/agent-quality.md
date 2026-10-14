# Runbook: agent quality (looping, judge drop, guardrail anomaly, dead jobs)

**Alerts:** AgentLooping, OnlineJudgeDrop, GuardrailAnomaly, JobsDeadLettered. None of these throw errors.

1. Check deploys, prompt or model changes, and knowledge-base updates in the window. Quality drops usually follow one.
2. Open `GET /review-queue` and read ten items. Write down the first failure in each (error analysis).
3. **Judge drop after a deploy:** roll back, then reproduce with the eval suite on the new version.
4. **Guardrail at zero:** the guardrail probably broke. Check its unit tests and recent changes to `guardrails.py`.
5. **Looping:** find the tool being called repeatedly. Fix its error message or description; disable it if needed.
6. **Dead jobs:** inspect `SELECT kind, last_error FROM jobs WHERE status = 'dead' ORDER BY id DESC LIMIT 20`.
7. Turn each new failure category into eval cases (`python -m evals.error_analysis to-case ...`).
