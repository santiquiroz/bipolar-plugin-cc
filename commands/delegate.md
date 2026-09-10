---
description: Delegate a coding task to the best available CLI agent through bipolar-code's delegation broker (claude, codex, copilot, agy or ollama picked by tier and quota)
argument-hint: "[--workspace <abs path>] [--agent claude|codex|copilot|antigravity|ollama] [--mode task|text] [--tier trivial|simple|standard|complex] [--dry-run] <task>"
allowed-tools: Bash
---

Send the task to bipolar-code's delegation broker (`POST /api/delegate/jobs`, bipolar-code ≥ 2.13) and follow the job until it ends. The broker classifies the task, picks the first agent of that tier that is installed, enabled, not out of quota and not busy, runs it as a bounded subprocess inside an allow-listed workspace, and fails over to the next agent when an attempt dies on a quota signal.

Raw user request:
$ARGUMENTS

Parse the flags out of the request; everything else is the task text. Defaults: `--workspace` = the current working directory (absolute path), `--mode task`, no `--agent` (auto), no `--tier` (classifier decides), no `--dry-run`.

Step 1 — Config and health (one Bash call):

```bash
# Environment variables win; the file written by /bipolar:setup is the fallback
[ -z "$BIPOLAR_URL" ] && [ -f "$HOME/.config/bipolar-cc/env" ] && . "$HOME/.config/bipolar-cc/env"
[ -n "$BIPOLAR_URL" ] && [ -n "$BIPOLAR_API_KEY" ] || { echo "bipolar-cc not configured: run /bipolar:setup"; exit 78; }
curl -s -H "x-api-key: $BIPOLAR_API_KEY" "$BIPOLAR_URL/api/health"
```

- Health must report `"version":"2.13` or newer and `"delegation_enabled":true`. Older server → tell the user to update bipolar-code. `delegation_enabled:false` → tell the user to enable it in bipolar-code → Agentes (switch "Delegación a agentes CLI" + workspaces permitidos) and stop.

Step 2 — Submit. Build the JSON body yourself (escape quotes, backslashes and newlines in the task; forward slashes in the workspace path work on Windows) and post it:

```bash
curl -s -X POST -H "x-api-key: $BIPOLAR_API_KEY" -H "content-type: application/json" -H "X-Bipolar-Depth: 0" \
  -d '{"task":"<task text>","workspace":"<abs path>","mode":"task"}' \
  "$BIPOLAR_URL/api/delegate/jobs"
```

Add `"agent_id"`, `"tier_hint"`, `"mode":"text"` or `"dry_run":true` only when the matching flag was given. Interpret the response:

- 200 with `dry_run` → report the chosen `agent_id`, `model`, `tier` and `skipped` list; stop.
- 202 → note the `id` and continue.
- 400 `workspace_not_allowed` / `workspace_allowlist_empty` → the workspace is not in bipolar-code's allow-list; tell the user to add the path in Agentes → Workspaces permitidos. Stop.
- 400 `no_agent_available` → show `reasons` and `skipped` (each entry says why an agent was skipped: `disabled`, `not_installed`, `exhausted:quota_exhausted`, `busy`, `tier_unsupported`, `agy_deny_list_missing`). Stop; the caller decides another lane.
- 409 `delegation_disabled` / `recursion_guard`, 429 `too_many_jobs` → report verbatim and stop.

Step 3 — Follow the job. Poll every 5 s for up to the job timeout (default 10 min):

```bash
for i in $(seq 1 120); do
  R=$(curl -s -H "x-api-key: $BIPOLAR_API_KEY" "$BIPOLAR_URL/api/delegate/jobs/<id>")
  S=$(printf '%s' "$R" | grep -o '"status":"[a-z_]*"' | head -1 | cut -d'"' -f4)
  case "$S" in queued|running) sleep 5;; *) break;; esac
done
printf '%s\n' "$R"
```

Step 4 — Report. From the final job JSON give: `status` (`succeeded`, `failed`, `timeout`, `cancelled`, `quota`, `auth_error`), `agent_id` and `model`, one line per attempt (`agent_id`, `signal`, `duration_s`, `error`), `files_touched`, and `output_tail` verbatim. When `status` is `quota`, say which agents were tried and what the last quota excerpt was; the caller decides whether another lane or inline work follows. When the output is truncated, offer `GET /api/delegate/jobs/<id>/output` for the full log.

Rules:

- Never run the task yourself and never retry a finished job on your own: the broker already applied its failover policy.
- The delegate edits the live working tree of the workspace (edits are auto-accepted inside each CLI's safety flags). Review `git diff` before committing; the orchestrator owns the commit.
- Do not pass secrets in the task text: the job log is stored under bipolar-code's config dir.
