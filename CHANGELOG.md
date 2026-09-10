# Changelog

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
