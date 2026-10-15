---
id: w11-harness
week: 11
kind: lesson
title: Inside a coding-agent harness
short: Coding-agent harnesses
minutes: 50
summary: The loop, the tools, the context, the permissions, the hooks and the sandbox that turn a model into a coding agent, why each is a design decision, and how they map to Foundry, the course's reference harness.
---

## Why the harness matters as much as the model

A coding agent is a model plus a **harness**: the program that gives the model tools, decides what it may do with them, feeds it context, and runs the loop. The same model performs very differently in different harnesses. The SWE-agent team showed this in 2024: a purpose-built interface for viewing, searching and editing files ([Yang et al.](https://arxiv.org/abs/2405.15793)) "significantly enhances an agent's ability to create and edit code files", which they called an **agent-computer interface**. The same year, Agentless ([Xia et al.](https://arxiv.org/abs/2407.01489)) skipped the open-ended loop entirely, with three fixed steps (localise, repair, validate), and resolved 32% of SWE-bench Lite. Both papers make the same point: how you let a model touch code is a design decision with measurable consequences.

This lesson takes a harness apart. Every part is also a control point for safety and cost, which is why a platform team cares about it, not only the people who use it.

```viz
caption: A harness is a loop with checkpoints. Every tool call passes rules and hooks before it touches the workspace, and the sandbox limits what a command can reach even when the rules let it run.
<div class="vz-cols" style="--k:3">
  <div class="vz-panel sk c"><h5>Context</h5><div class="vz-row"><span class="ch sk c">instructions</span><span class="ch sk c">AGENTS.md</span><span class="ch sk">the task</span></div></div>
  <div class="vz-panel sk c"><h5>Loop</h5><div class="vz-row"><span class="ch sk c">model call</span><span class="arr sk"></span><span class="ch sk c">tool calls</span></div><div class="vz-row"><span class="ch sk">results back</span></div></div>
  <div class="vz-panel sk g"><h5>Checkpoints</h5><div class="vz-row"><span class="ch sk g">rules</span><span class="ch sk g">hooks</span></div><div class="vz-row"><span class="ch sk g">sandbox</span></div></div>
</div>
```

## 1. The loop

The loop is the same as the agent loop from [Week 1](#w1-agents): send the conversation and the tool definitions to the model, run the tool calls it makes, append the results, repeat until it says it is done. What changes for code is scale. A repository is far larger than a context window, a test run can print thousands of lines, and a fix can take dozens of steps. So a coding harness needs three limits that a chatbot can skip:

- **A step limit**, so a confused agent cannot loop forever.
- **A token budget per task**, enforced in the harness and backed by the gateway's budget per app ([AI gateways](#w7-gateways)).
- **A size limit on every tool result**, so one large file or log cannot push the task out of the context window. Cut long results and tell the model they were cut, so it can ask for a narrower slice.

## 2. Tools: the agent-computer interface

Coding harnesses converge on a small set of tools: list or find files, read a file (with line numbers, in ranges), search contents, edit a file, and run a command. Three design choices matter more than the list:

- **Edit by exact replacement, not by line numbers or whole files.** "Replace this exact text, which must occur once" fails loudly when the model's picture of the file is out of date, instead of silently corrupting it. Rewriting whole files wastes output tokens, which are the slow and expensive kind ([Attention and the KV cache](#uth-attention)).
- **Feedback in the result.** A failed edit that says "found 3 times; it must match exactly once" lets the model correct itself in one step.
- **Few tools, well described.** Each tool definition costs context on every call, and overlapping tools confuse the choice ([Context engineering](#w1-context)).

## 3. Context: what the agent knows before it starts

The agent starts with the harness's instructions, the task, and whatever the repository says about itself. **AGENTS.md** has become the common place for the last: "a README for agents", a Markdown file with setup, test commands and conventions. It emerged from collaboration across OpenAI Codex, Amp, Google's Jules, Cursor and Factory, and is now stewarded by the Agentic AI Foundation under the Linux Foundation ([agents.md](https://agents.md/)). In a monorepo, the nearest AGENTS.md to the file being edited wins. Some tools use their own file (Claude Code reads CLAUDE.md), so many repositories keep both with the same substance.

Treat everything else the agent reads as data: issue text, code comments, test output, dependency READMEs. That is where injected instructions arrive ([Prompt injection](#w3-security)), and a coding agent reads a lot of text written by strangers.

## 4. Permissions: what the agent may do

Every serious harness puts a permission check in front of tool calls. Claude Code is a good worked example because its rules are documented in detail ([permissions](https://code.claude.com/docs/en/permissions)):

- **Modes** set the default posture: ask before each new kind of action (`default`), accept file edits but ask for other things (`acceptEdits`), read and plan without editing (`plan`), let a classifier review actions instead of a person (`auto`), refuse anything that would ask (`dontAsk`), or skip prompts (`bypassPermissions`).
- **Rules** name a tool and a pattern, such as `Bash(npm run test *)`, in three lists. "Rules are evaluated in order: deny, then ask, then allow. The first match in that order determines the outcome, and rule specificity doesn't change the order." A broad deny cannot be carved open by a narrower allow.

Foundry uses the same shape: `deny`, `ask` and `allow` lists over targets such as `run(python -m pytest*)` and `edit(.github/**)`, evaluated in that order, with anything unmatched treated as ask. One choice is specific to unattended runs: nobody is there to answer, so **ask means no**. A factory that turns ask into yes when nobody answers has no permission system at all.

> [!warn] Rules over command text are not a security boundary. Claude Code's documentation says it plainly: a Bash rule "covers the invocation Claude usually produces and isn't a security boundary around the program". A program can be reached in forms a rule does not name (a wrapper script, another path, an interpreter running it), and a harness that hands command text to a shell without splitting it lets a second command ride along after the first. Rules steer an honest agent; the sandbox stops a hostile one.

Two cheap hardening steps narrow the gap. Run commands without a shell, as an argument list, so `&&`, pipes and `$(...)` are inert text (Foundry does this; a test proves `... && touch pwned` creates nothing). And keep the rules themselves out of the agent's reach: Foundry reads `foundry.toml` from the original repository, never from the agent's copy, and protects the file.

## 5. Hooks: your code at every checkpoint

Hooks let the team that owns a repository add checks without changing the harness. Claude Code fires events around the session, each prompt and each tool call; a `PreToolUse` hook receives the call as JSON, and "exit code 2" blocks it, with the hook's error output shown to the model as the reason ([hooks](https://code.claude.com/docs/en/hooks)). Typical hooks:

- refuse new dependencies that are not on an allow-list (the defence against hallucinated package names, covered next week);
- refuse edits to generated files or vendored code;
- run a formatter after every edit, so diffs stay clean;
- log every command to the audit trail.

Foundry runs hooks the same way (JSON on stdin, exit 2 blocks), from the **original** repository. If hooks ran from the agent's copy, an agent could edit the hook script and then trigger it.

## 6. The sandbox: the boundary that holds

Permissions decide what the agent should do. The sandbox decides what a command *can* do, whatever the agent intended. Two boundaries matter:

- **Filesystem:** the agent works in a copy (a clone, a worktree or a container), and commands cannot read credentials elsewhere on the machine.
- **Network:** commands cannot reach arbitrary hosts, so a steered agent cannot post your code or secrets out, or fetch and run a script.

Anthropic describes both for Claude Code, enforced with Linux bubblewrap and macOS seatbelt, and reports that "sandboxing safely reduces permission prompts by 84%" in internal use ([Claude Code sandboxing](https://www.anthropic.com/engineering/claude-code-sandboxing), October 2025). That second number is the design insight: a strong sandbox does not only add safety, it removes the need to ask a person about every command, because the worst a command can do is bounded. OpenAI's Codex cloud follows the same pattern from the other side: setup scripts run with internet access to install dependencies, and agent internet access is off by default after that ([Codex internet access](https://developers.openai.com/codex/cloud/agent-internet)).

```viz
caption: Rules and the sandbox fail differently. Rules catch the honest mistake; the sandbox contains the hostile command. Build both, and trust only the second.
<div class="vz-cols">
  <div class="vz-panel sk w"><h5>Rules and hooks</h5><p>match command text and paths</p><div class="vz-row"><span class="ch sk g">stop honest mistakes</span></div><div class="vz-row"><span class="ch sk b">a reworded command slips past</span></div></div>
  <div class="vz-panel sk g"><h5>Sandbox</h5><p>limits the process itself</p><div class="vz-row"><span class="ch sk g">no network, no other files</span></div><div class="vz-row"><span class="ch sk g">holds whatever the command says</span></div></div>
</div>
```

Foundry splits the sandbox into two layers ([ADR 0001](https://github.com/Rachneet/ai-system-design-course/blob/main/platform/foundry/docs/adr/0001-two-layer-sandbox.md)). In process, always: a throwaway clone, paths resolved and contained (symlinks included), no shell, an environment with only `PATH`, `HOME` and `LANG`, a timeout and an output limit. At the OS level, by configuration: a `sandbox_prefix` that wraps every command in bubblewrap, `sandbox-exec` or a container with no network.

## 7. Subagents and long tasks

Long tasks outgrow one context window. Harnesses respond in two ways: **subagents**, separate model sessions with their own context for a bounded job (search the codebase, review a diff), returning only a summary; and **compaction**, summarising earlier turns when the window fills. Both trade completeness for focus. Each subagent should get the narrowest tools and permissions its job needs. A review subagent needs read access, not edit access, which is the least-privilege rule from [Week 8](#w8-policy) applied inside one harness.

## How Foundry maps to all of this

| Part | Foundry | Where in the code |
|---|---|---|
| Loop and limits | Step limit, per-job token budget, results cut to 6,000 characters | `harness.py` |
| Tools | `list_files`, `read_file` (numbered, ranged), `search`, `edit_file` (exact, unique), `run`, `finish` | `harness.py` |
| Context | Instructions plus the repository's AGENTS.md; task text is data | `harness.py` |
| Permissions | deny, then ask, then allow; ask means no when unattended | `policy.py` |
| Hooks | JSON on stdin, exit 2 blocks, run from the original repository | `policy.py` |
| Sandbox | Clone, path containment, no shell, no secrets, limits, `sandbox_prefix` | `sandbox.py` |
| Models | Through Switchboard, tagged `job:<id>:coder` | `model.py` |

## Failure modes

| Failure | What it looks like | Defence |
|---|---|---|
| Unbounded loop | The agent re-reads the same files for an hour | Step limit, token budget, alert on cost per task |
| Context flood | One `cat` of a log fills the window and the task is forgotten | Cut every result; read in ranges; search before reading |
| Silent bad edit | A whole-file rewrite drops code the model never saw | Exact, unique replacement; run the tests after editing |
| Rules as a boundary | `run(pytest*)` was allowed, so `pytest; curl ...` ran too | No shell; an OS sandbox with no network |
| Self-loosening | The agent edits its own config or hooks | Read config and hooks from the original; protect those paths |
| Ask means yes | An unattended run auto-approves everything that would ask | Ask means no without a person; hold for approval instead |

## Design review questions

> [!interview] Your agent may run `pytest`. Show two ways a steered agent could run something else with that permission, and what stops each.

> [!interview] Why does a stronger sandbox reduce the number of permission prompts, rather than add to them?

> [!interview] Where does your harness read its rules and hooks from, and what stops the agent editing them?

> [!interview] A task needs network access to install dependencies. How do you allow that without letting the agent reach the internet later?

## Further reading

- [SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering](https://arxiv.org/abs/2405.15793) and [Agentless](https://arxiv.org/abs/2407.01489), the two papers that framed harness design.
- Claude Code: [permissions](https://code.claude.com/docs/en/permissions), [hooks](https://code.claude.com/docs/en/hooks), and [sandboxing](https://www.anthropic.com/engineering/claude-code-sandboxing).
- OpenAI Codex: [agent internet access](https://developers.openai.com/codex/cloud/agent-internet) and [cloud environments](https://developers.openai.com/codex/cloud/environments).
- [AGENTS.md](https://agents.md/), the shared format for instructions to coding agents.
- [Foundry's README](https://github.com/Rachneet/ai-system-design-course/tree/main/platform/foundry), threat model and ADRs.

```quiz
[
  {"q": "In a deny, ask, allow rule system, a call matches both a narrow allow rule and a broad ask rule. What happens?", "options": ["The narrower rule wins, so it is allowed", "Ask: the lists are checked deny, then ask, then allow, and the first list with a match decides", "It is denied", "It depends on the order the rules were written"], "answer": 1, "why": "Specificity does not change the order. A broad ask or deny cannot be carved open by a narrower allow."},
  {"q": "Why does Foundry run commands without a shell?", "options": ["Shells are slow", "So &&, pipes and $(...) are plain arguments and cannot chain a second command past a rule", "Because Python cannot start shells", "To save tokens"], "answer": 1, "why": "With no shell there is nothing to interpret the operators, so a rule over the first command is not bypassed by a second one."},
  {"q": "What is the sandbox for, if you already have permission rules?", "options": ["Nothing; rules are enough", "Rules steer an honest agent; the sandbox bounds what any command can reach, so a hostile or reworded command still cannot read secrets or reach the network", "Speed", "Logging"], "answer": 1, "why": "Rules over command text are not a security boundary. Isolation of the process is."},
  {"q": "An unattended factory run hits a command that matches an ask rule. What should happen?", "options": ["Run it, since nobody objected", "Refuse it, or hold the job for a person: ask means no when nobody can answer", "Retry until it is allowed", "Switch to bypass mode"], "answer": 1, "why": "Treating silence as consent turns the permission system off exactly when nobody is watching."}
]
```
