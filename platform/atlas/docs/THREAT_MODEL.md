# Threat model (STRIDE)

Scope: the Atlas API, its Postgres database, and the artifacts it distributes. The main risk is supply chain: an
approved artifact runs inside agents with access to company data.

| Threat | Example | Mitigation | Test or control |
|---|---|---|---|
| **Spoofing** a publisher | Stolen token publishes under a team's name | 256-bit random secrets, only SHA-256 stored, constant-time compare, instant revocation, audit of every write | `test_tokens_roles_and_revocation` |
| Spoofing a name | Another team publishes `io.github.acme/weather` 9.9.9 | A name belongs to the first team that publishes it | `test_versions_are_immutable_and_names_belong_to_their_team` |
| **Tampering** with an approved artifact | Swapping a package after approval | Versions are immutable; content is addressed by sha256; downloads carry the digest | `test_skill_package_flow_with_digest_pinned_download` |
| Tampering with tools after approval | A remote server adds an instruction to a tool description the week after review | The reviewed tool list is pinned by digest and its text scanned; gateways compare the live list ([ADR 0004](adr/0004-pin-tool-lists.md)) | `test_tool_lists_are_pinned_*`, `test_tool_descriptions_are_scanned_*`, Checkpoint's `test_changed_tools_*` |
| Tampering via the archive | Path traversal, symlinks, zip bombs | Paths checked and size, count and ratio limited before any file is read | `test_unsafe_archives_are_refused_before_extraction` |
| Malicious skill content | `curl | sh`, hidden Unicode instructions, embedded keys, binaries | Blocking checks reject at submission; warnings need explicit reviewer acknowledgement | `test_dangerous_skill_scripts_*`, `test_hidden_unicode_*` |
| **Repudiation** | "I never approved that" | Reviewer, time and note on the artifact; append-only audit log | `test_publish_review_and_discover_an_mcp_server` |
| **Information disclosure** | Seeing other teams' unapproved work | Readers see approved and deprecated only; publishers see their own team's queue; reviewers see all | `test_search_ranks_and_hides_unapproved_from_other_teams` |
| **Denial of service** | Huge uploads | 10 MB unpacked and 500-file limits; 413 above the raw size | Config |
| **Elevation of privilege** | A publisher approves their own server | Roles per token; reviewer must differ from submitter; eval gate | `test_nobody_approves_their_own_work_*`, `test_eval_gate_*` |
| Upstream poisoning | A malicious public registry entry | Imports land in review, never approved; same checks; HTTP endpoints rejected | `test_sync_imports_public_servers_into_review_never_approved` |

## Residual risks
- Static checks can be evaded. Runtime enforcement belongs to the MCP gateway (Checkpoint) and agent sandboxes.
- Signatures are recorded (agent card `signatures`) but not yet verified; cosign or Sigstore verification of
  packages and cards is planned.
- The bootstrap admin token is a shared secret; production should use SSO for admins and reviewers.
