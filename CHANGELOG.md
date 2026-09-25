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
- `bipolar-rescue` isolates its child `claude -p` from the machine's setup:
  `--settings '{"disableAllHooks":true}'` (a global Stop hook no longer runs
  `codex review` on the child's uncommitted edits), `--strict-mcp-config` (no
  MCP servers), `--max-turns 50` (the broker's cap) and `Skill` added to
  `--disallowedTools`. The child runs under `timeout 570`, below the Bash
  tool's 600 s ceiling, and exit 124 is reported as a partial result.
- `/bipolar:delegate` computes the default workspace in the server's native
  form (`pwd -W`, then `cygpath -m`, then `pwd`): Git Bash's `/c/...` was
  rejected by a Windows server as `workspace_not_absolute`. The error table now
  covers every `workspace_*` code the broker returns (`workspace_required`,
  `workspace_not_absolute`, `workspace_missing`, `workspace_not_dir`,
  `workspace_forbidden`) with its action, and the docs say that `--mode task`
  needs the path to exist on the server host (from another PC: `--mode text`).
- Health checks that check something: `bipolar-rescue` no longer proceeds on a
  200 from `/v1/models` (a static list served even with llama-server stopped);
  it requires `running` and `healthy` from `/api/llamacpp/status`, with its own
  exit code for a rejected key (81), an unreachable server (82), llama-server
  stopped or loading (83) and any other answer (84). `/bipolar:delegate`
  validates the key in step 1 on `GET /api/delegate/jobs?limit=1` (`/api/health`
  is public), expects the 200 the broker really returns for a new job (not
  202) and handles a 401. `/bipolar:setup` checks the key on `/api` (`/v1` also
  accepts the legacy proxy key), reports `version`, `delegation_enabled` and the
  llama-server status, prints the smoke's `X-Bipolar-Route` header and warns
  when a provider other than `llamacpp` answered; its closing reminder mentions
  `/bipolar:delegate`.
- Config and `claude` resolution: `bipolar-rescue` reads
  `~/.config/bipolar-cc/env` only when `BIPOLAR_URL` is not already set (the
  environment wins, as documented) and exits 78 ("run /bipolar:setup") with no
  config instead of reporting an unreachable server; `/bipolar:delegate`'s
  submit block reloads that file too. The child runs the `claude` (or
  `claude.exe`) on `PATH`, else `$HOME/.local/bin/claude.exe`, and exits 79 with
  a clear message when neither exists (Git Bash can list that folder as
  `/Users/<you>/.local/bin`, which does not resolve). `/bipolar:setup` reports
  which `claude` it resolves.

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
