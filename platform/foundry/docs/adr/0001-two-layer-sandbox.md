# ADR 0001: A two-layer sandbox

Status: accepted (2026-10-15)

## Context
A coding agent must run commands (tests, linters, builds), and every command is a chance for a steered agent to
read secrets or send code out. Production harnesses use OS-level isolation: Anthropic describes filesystem and
network isolation for Claude Code built on Linux bubblewrap and macOS seatbelt, and OpenAI's Codex cloud runs tasks
in containers with agent internet access off by default. A Python process cannot give a child that isolation alone.

## Decision
- **In-process, always:** a throwaway clone; paths resolved and contained; commands as argv with no shell; an
  environment of `PATH`, `HOME` and `LANG` only; a timeout; output cut to a fixed size.
- **OS layer, configured:** `sandbox_prefix` wraps every command, for example bubblewrap with `--unshare-net` on
  Linux, `sandbox-exec` on macOS, or `docker run --network none`.

## Consequences
+ The test suite proves the in-process layer on any laptop; the OS layer is one setting per platform.
- Without the prefix there is no network or filesystem isolation for commands. Production runs must set it.
