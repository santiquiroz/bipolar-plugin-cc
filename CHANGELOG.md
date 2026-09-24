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
- `/bipolar:delegate` no longer types the job's JSON inline in `-d '...'`: the
  task goes through a single-quoted heredoc into a temporary file, `node` (or
  Python's `json` as a fallback) serializes the body with only the fields the
  flags ask for, and `curl --data-binary @file` posts it. An apostrophe in the
  task no longer breaks the request or runs the rest of the task as shell.
- `/bipolar:delegate` follows jobs that outlast one Bash call: the polling block
  runs with a 600000 ms tool timeout in segments of at most 9 minutes and is
  re-run while the job is `queued` or `running` (it used to die at the default
  2 minutes and give up after 10). A failed status read is retried up to 3
  times in a row instead of ending the loop, and a 404 is reported as a job
  lost to a server restart. New `--timeout <s>` flag (`timeout_s`, 60-3600),
  a documented cancel (`DELETE /api/delegate/jobs/<id>`), and the report shows
  the job's `error` when `output_tail` is empty.

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
