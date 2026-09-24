# Changelog

## Unreleased

- Recursion guard: `/bipolar:delegate` forwards `BIPOLAR_DELEGATION_DEPTH` as
  `X-Bipolar-Depth` (it was hardcoded to 0) and, like `bipolar-rescue`, refuses
  to run inside a delegated session. `bipolar-rescue` marks its child with
  `BIPOLAR_DELEGATION_DEPTH=1`. Hermetic tests for these shell blocks in `tests/`.
- `bipolar-rescue` hands the task to `claude -p` on stdin through a single-quoted
  heredoc (`<<'EOF_TASK'`) instead of inlining it in double quotes, so pasted
  code with backticks, `$VAR` or `$(...)` is no longer run or mangled by the
  shell, and long tasks avoid the command-line length limit. The child also gets
  `GIT_TERMINAL_PROMPT=0` and `GIT_SSH_COMMAND="ssh -o BatchMode=yes"` so git
  never hangs waiting for credentials.

## 0.2.0 — 2026-09-10

- New `/bipolar:delegate` command: sends the task to bipolar-code's delegation
  broker (`POST /api/delegate/jobs`, bipolar-code ≥ 2.13), which classifies it
  by complexity and runs it on the best available CLI agent on the server host
  (`claude`, `codex`, `copilot`, `agy`, `ollama`), skipping exhausted or busy
  agents and failing over on quota signals. The command follows the job and
  reports status, agent, attempts, `files_touched` and the final output.
  Flags: `--workspace`, `--agent`, `--mode text`, `--tier`, `--dry-run`.
- `bipolar-rescue` unchanged; README and CLAUDE.md snippet describe when to use
  each path.

## 0.1.0 — 2026-08-19

Initial release: `bipolar-rescue` subagent (headless Claude Code against the
local big model served by bipolar-code), `/bipolar:rescue`, `/bipolar:setup`.
