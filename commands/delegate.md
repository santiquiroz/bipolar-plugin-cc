---
description: Delegate a coding task to the best available CLI agent through bipolar-code's delegation broker (claude, codex, copilot, agy or ollama picked by tier and quota)
argument-hint: "[--workspace <abs path>] [--agent claude|codex|copilot|antigravity|ollama] [--mode task|text] [--tier trivial|simple|standard|complex] [--timeout <s>] [--dry-run] <task>"
allowed-tools: Bash
---

Send the task to bipolar-code's delegation broker (`POST /api/delegate/jobs`, bipolar-code ≥ 2.13) and follow the job until it ends. The broker classifies the task, picks the first agent of that tier that is installed, enabled, not out of quota and not busy, runs it as a bounded subprocess inside an allow-listed workspace, and fails over to the next agent when an attempt dies on a quota signal.

Raw user request:
$ARGUMENTS

Parse the flags out of the request; everything else is the task text. Defaults: `--workspace` = the current working directory, computed by the submit block in the server's native form (`C:/...` on Windows, never Git Bash's `/c/...`), `--mode task`, no `--agent` (auto), no `--tier` (classifier decides), no `--timeout` (each agent's own limit on the server, e.g. 900 s for codex), no `--dry-run`. `--timeout <s>` is the per-attempt limit in seconds the broker accepts as `timeout_s`: a whole number from 60 to 3600; anything else → tell the user the valid range and stop before submitting.

Step 1 — Config and health (one Bash call):

```bash
# A CLI launched by the broker (or by bipolar-rescue) inherits BIPOLAR_DELEGATION_DEPTH=1
[ "${BIPOLAR_DELEGATION_DEPTH:-0}" = 0 ] || { echo "bipolar recursion guard: this session already runs inside a delegated job (BIPOLAR_DELEGATION_DEPTH=$BIPOLAR_DELEGATION_DEPTH); not delegating again"; exit 77; }
# Environment variables win; the file written by /bipolar:setup is the fallback
[ -z "$BIPOLAR_URL" ] && [ -f "$HOME/.config/bipolar-cc/env" ] && . "$HOME/.config/bipolar-cc/env"
[ -n "$BIPOLAR_URL" ] && [ -n "$BIPOLAR_API_KEY" ] || { echo "bipolar-cc not configured: run /bipolar:setup"; exit 78; }
HEALTH=$(curl -s --max-time 10 "$BIPOLAR_URL/api/health") || { echo "bipolar-code unreachable at $BIPOLAR_URL: backend off, wrong URL or off-LAN"; exit 82; }
printf '%s\n' "$HEALTH"
# /api/health is public: only an authenticated /api route proves the key
KEY_CODE=$(curl -s --max-time 10 -o /dev/null -w '%{http_code}' -H "x-api-key: $BIPOLAR_API_KEY" "$BIPOLAR_URL/api/delegate/jobs?limit=1")
case "$KEY_CODE" in
  200) ;;
  401) echo "bipolar-code rejected the API key on /api (HTTP 401): run /bipolar:setup with the full API key"; exit 81 ;;
  *) echo "key check failed: GET /api/delegate/jobs answered HTTP $KEY_CODE"; exit 84 ;;
esac
```

- Exit 77 → recursion guard: this session is itself a delegate. Report the message verbatim and stop; never work around it (unsetting the variable, sending depth 0, calling the API another way).
- Exit 81 → the key is wrong for `/api/*`, which only accepts the full API key (a legacy proxy key still works on `/v1`, so rescue may have worked with it): tell the user to run `/bipolar:setup` with the key from bipolar-code → Settings → "Copiar API Key completa" and stop.
- Exit 82 → bipolar-code is off, the URL is wrong or this PC is off the LAN; report it and stop. Do not retry in a loop.
- Exit 84 → the key check got another answer: 404 means a server without the broker (older than 2.13; tell the user to update bipolar-code), 503 means authentication is not configured on the server. Report it and stop.
- Health must report `"version":"2.13` or newer and `"delegation_enabled":true`. Older server → tell the user to update bipolar-code. `delegation_enabled:false` → tell the user to enable it in bipolar-code → Agentes (switch "Delegación a agentes CLI" + workspaces permitidos) and stop.

Step 2 — Submit. Copy this block exactly and fill in only the task (verbatim, inside the heredoc — the closing `EOF_TASK` must stay alone at column 0) and the option variables. Never type the JSON yourself: the task is written to a temporary file through a single-quoted heredoc, serialized by `node` (or Python's `json` when node is missing) and posted with `--data-binary @file`, so apostrophes, quotes, backticks, `$VAR`, `$(...)` and newlines reach the broker intact. Keep the `X-Bipolar-Depth` header exactly as written: it forwards the inherited depth so the broker's own guard refuses nested jobs.

```bash
BODY_DIR=$(mktemp -d) || exit 1
trap 'rm -rf "$BODY_DIR"' EXIT
# Native node/python/curl on Windows cannot open Git Bash's /tmp paths
command -v cygpath >/dev/null && BODY_DIR=$(cygpath -m "$BODY_DIR")
TASK_FILE="$BODY_DIR/task.txt" BODY="$BODY_DIR/body.json"
cat > "$TASK_FILE" <<'EOF_TASK'
<task text, verbatim>
EOF_TASK
WORKSPACE=
# Git Bash's pwd gives /c/..., which Python on a Windows server does not treat as absolute
[ -n "$WORKSPACE" ] || WORKSPACE=$(pwd -W 2>/dev/null || cygpath -m "$PWD" 2>/dev/null || pwd)
MODE=task AGENT= TIER= DRY_RUN= TIMEOUT_S=
BODY_JS='const fs = require("fs");
const [taskFile, bodyFile, workspace, mode, agent, tier, dryRun, timeoutS] = process.argv.slice(1);
const text = fs.readFileSync(taskFile, "utf8");
const body = { task: text.endsWith("\n") ? text.slice(0, -1) : text, workspace, mode };
if (agent) body.agent_id = agent;
if (tier) body.tier_hint = tier;
if (dryRun) body.dry_run = true;
if (timeoutS) body.timeout_s = Number(timeoutS);
fs.writeFileSync(bodyFile, JSON.stringify(body));'
BODY_PY='import json, sys
task_file, body_file, workspace, mode, agent, tier, dry_run, timeout_s = sys.argv[1:9]
text = open(task_file, encoding="utf-8", newline="").read()
body = {"task": text[:-1] if text.endswith("\n") else text, "workspace": workspace, "mode": mode}
body.update({key: value for key, value in (("agent_id", agent), ("tier_hint", tier)) if value})
body.update({"dry_run": True} if dry_run else {})
body.update({"timeout_s": int(timeout_s)} if timeout_s else {})
json.dump(body, open(body_file, "w", encoding="utf-8"))'
build_body() {
  node -e "$BODY_JS" "$@" 2>/dev/null || python3 -c "$BODY_PY" "$@" 2>/dev/null || python -c "$BODY_PY" "$@"
}
build_body "$TASK_FILE" "$BODY" "$WORKSPACE" "$MODE" "$AGENT" "$TIER" "$DRY_RUN" "$TIMEOUT_S" || { echo "could not build the JSON body: needs node or python"; exit 79; }
curl -s -X POST -H "x-api-key: $BIPOLAR_API_KEY" -H "content-type: application/json" -H "X-Bipolar-Depth: ${BIPOLAR_DELEGATION_DEPTH:-0}" \
  --data-binary @"$BODY" \
  "$BIPOLAR_URL/api/delegate/jobs"
```

- Set `WORKSPACE='<abs path>'`, `MODE=text`, `AGENT=<id>`, `TIER=<tier>`, `TIMEOUT_S=<s>` or `DRY_RUN=1` only when the matching flag was given; empty values stay out of the body, and an empty `WORKSPACE` becomes the current directory. A `--workspace` path goes in the server's native form: `C:/...` on Windows (forward slashes work), not `/c/...`; if the path contains an apostrophe, write it as `'\''`.
- The broker resolves the workspace on the machine that runs bipolar-code, not on this one. `--mode task` from another PC of the LAN only works when the same path exists on the server host; otherwise use `--mode text` (the agent runs in a scratch directory on the server and answers in text) or `bipolar-rescue`.
- The heredoc delimiter must not occur anywhere in the task text. Use `EOF_TASK` unless the task contains that string; then pick another (e.g. `EOF_TASK_7f3a`) for both the opening `<<'...'` and the closing line.
- Exit 79 → neither node nor python could run; report it and stop. The temporary directory is removed when the call ends.

Interpret the response:

- 200 when `--dry-run` was given → report the chosen `agent_id`, `model`, `tier` and `skipped` list; stop.
- 200 otherwise → the job, with `status: queued`: note its `id` and continue.
- 401 → the key was rejected (changed on the server since step 1): tell the user to run `/bipolar:setup` with the full API key and stop.
- 400 `workspace_allowlist_empty` → bipolar-code has no allowed workspaces yet; tell the user to add the project's path in Agentes → Workspaces permitidos. Stop.
- 400 `workspace_not_allowed` → the workspace is not inside any allowed workspace; tell the user to add the path (or a parent) in Agentes → Workspaces permitidos. Stop.
- 400 `workspace_required` → the body went out without a workspace: the block was not copied as written (the default line was dropped). Restore it and submit again.
- 400 `workspace_not_absolute` → the path is relative or in Git Bash form (`/c/...`), which the server does not treat as absolute. Submit again with the absolute native path (`C:/...` on Windows); the default line already produces it.
- 400 `workspace_missing` → the path does not exist on the server host. From another PC the local path usually does not exist there: tell the user that `--mode task` needs the repo at that same path on the server host, or offer `--mode text`. Stop.
- 400 `workspace_not_dir` → the path is a file, not a directory; ask the user for the project directory. Stop.
- 400 `workspace_forbidden` → the broker never runs agents in a drive root, the home directory, bipolar-code's config dir or anything inside `.git`; ask the user for the project directory. Stop.
- 400 `no_agent_available` → show `reasons` and `skipped` (each entry says why an agent was skipped: `disabled`, `not_installed`, `exhausted:quota_exhausted`, `busy`, `tier_unsupported`, `agy_deny_list_missing`). Stop; the caller decides another lane.
- 409 `delegation_disabled` / `recursion_guard`, 429 `too_many_jobs` → report verbatim and stop.
- 422 → the broker rejected a field (e.g. `timeout_s` outside 60-3600); report its `detail` and stop.

Step 3 — Follow the job. Run this block with the Bash tool's `timeout` set to `600000` (its maximum): the default 120000 ms would kill it after two minutes. One call is a segment of at most 9 minutes; jobs can run far longer (each attempt up to its agent's limit or `timeout_s`, up to 3 attempts with failover, plus time `queued` behind other jobs), so keep re-running the same block while it exits 75.

```bash
[ -z "$BIPOLAR_URL" ] && [ -f "$HOME/.config/bipolar-cc/env" ] && . "$HOME/.config/bipolar-cc/env"
JOB_URL="$BIPOLAR_URL/api/delegate/jobs/<id>"
POLL_S=5 SEGMENT_S=540 MAX_FAILS=3
STATUS_RE='"status" *: *"([a-z_]+)"'
fetch_job() {
  curl -s --max-time 20 -w '\n%{http_code}' -H "x-api-key: $BIPOLAR_API_KEY" "$JOB_URL"
}
DEADLINE=$((SECONDS + SEGMENT_S)) FAILS=0
while :; do
  R=$(fetch_job)
  CODE=${R##*$'\n'} R=${R%$'\n'*}
  [ "$CODE" = 404 ] && { echo "job lost: the server no longer knows it (HTTP 404; bipolar-code restarted and jobs live in memory)"; exit 76; }
  S= FAILS=$((FAILS + 1))
  [[ $R =~ $STATUS_RE ]] && S=${BASH_REMATCH[1]} FAILS=0
  case "$S" in
    queued|running) ;;
    "") [ "$FAILS" -lt "$MAX_FAILS" ] || { printf '%s\n' "$R"; echo "status unreadable $FAILS times in a row (last HTTP $CODE)"; exit 74; } ;;
    *) printf '%s\n' "$R"; exit 0 ;;
  esac
  [ "$SECONDS" -lt "$DEADLINE" ] || { printf '%s\n' "$R"; echo "job still ${S:-unconfirmed} after this segment: run this block again"; exit 75; }
  sleep "$POLL_S"
done
```

- Exit 0 → the last line is the final job JSON; go to step 4.
- Exit 75 → the job is still `queued` or `running`: run the same block again (again with `timeout: 600000`). Tell the user it is still going after each segment.
- Exit 74 → the status could not be read three times in a row (network error, server down or a non-JSON reply). The job may still be running on the server: report it with the last HTTP code and ask the user whether to keep waiting (re-run the block) or cancel it.
- Exit 76 → job lost: bipolar-code restarted, so the job and its log are gone and its CLI may have stopped halfway through an edit. Tell the user to check `git status` in the workspace before resubmitting.

Cancel — when the user asks to stop, or wants to give up on a job that is still `queued` or `running`, cancel it instead of just stopping the polling (otherwise the delegate keeps editing the working tree):

```bash
[ -z "$BIPOLAR_URL" ] && [ -f "$HOME/.config/bipolar-cc/env" ] && . "$HOME/.config/bipolar-cc/env"
curl -s -X DELETE -H "x-api-key: $BIPOLAR_API_KEY" "$BIPOLAR_URL/api/delegate/jobs/<id>"
```

The reply is the job with `status: cancelled`; the broker kills the agent's process tree. Edits already made stay in the working tree: tell the user to review `git status` / `git diff`. A 404 means the job is already gone.

Step 4 — Report. From the final job JSON give: `status` (`succeeded`, `failed`, `timeout`, `cancelled`, `quota`, `auth_error`), `agent_id` and `model`, one line per attempt (`agent_id`, `signal`, `duration_s`, `error`), `files_touched`, and `output_tail` verbatim; when `output_tail` is empty, give the job's `error` instead. When `status` is `quota`, say which agents were tried and what the last quota excerpt was; the caller decides whether another lane or inline work follows. When the output is truncated, offer `GET /api/delegate/jobs/<id>/output` for the full log.

Rules:

- Never run the task yourself and never retry a finished job on your own: the broker already applied its failover policy.
- The delegate edits the live working tree of the workspace (edits are auto-accepted inside each CLI's safety flags). Review `git diff` before committing; the orchestrator owns the commit.
- Do not pass secrets in the task text: the job log is stored under bipolar-code's config dir.
