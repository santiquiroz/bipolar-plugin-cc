---
description: Delegate a coding task to the best available CLI agent through bipolar-code's delegation broker (claude, codex, copilot, agy, cursor or ollama picked by tier and quota)
argument-hint: "[--workspace <abs path>] [--agent claude|codex|copilot|antigravity|cursor|ollama] [--mode task|text] [--tier trivial|simple|standard|complex] [--timeout <s>] [--dry-run] <task>"
allowed-tools: Bash
---

Send the task to bipolar-code's delegation broker (`POST /api/delegate/jobs`, bipolar-code ≥ 2.13) and follow the job until it ends. The broker classifies the task, picks the first agent of that tier that is installed, enabled, not out of quota and not busy, runs it as a bounded subprocess inside an allow-listed workspace, and fails over to the next agent when an attempt dies on a quota signal.

Raw user request:
$ARGUMENTS

Parse the flags out of the request; everything else is the task text. Defaults: `--workspace` = the current working directory, computed by `bipolar-delegate-submit` in the server's native form (`C:/...` on Windows, never Git Bash's `/c/...`), `--mode task`, no `--agent` (auto), no `--tier` (classifier decides), no `--timeout` (each agent's own limit on the server, e.g. 900 s for codex), no `--dry-run`. `--timeout <s>` is the per-attempt limit in seconds the broker accepts as `timeout_s`: a whole number from 60 to 3600; anything else → tell the user the valid range and stop before submitting.

The steps below run scripts from this plugin's `bin/`, which Claude Code puts on the Bash tool's `PATH`: call them by name, exactly as written, and never re-type their logic as inline shell. Exit 127 (`command not found`) means the plugin's `bin/` is not on `PATH` (plugin disabled, or an older version without `bin/` installed): tell the user to update the plugin and reload Claude Code, and stop.

Step 1 — Config and health (one Bash call):

```bash
bipolar-delegate-check
```

It refuses to run inside a delegated session, reads the config (environment variables first, then the file written by `/bipolar:setup`), prints `GET /api/health` and checks the key on an authenticated `/api` route (`/api/health` is public and proves nothing about the key).

- Exit 77 → recursion guard: this session is itself a delegate. Report the message verbatim and stop; never work around it (unsetting the variable, sending depth 0, calling the API another way).
- Exit 81 → the key is wrong for `/api/*`, which only accepts the full API key (a legacy proxy key still works on `/v1`, so rescue may have worked with it): tell the user to run `/bipolar:setup` with the key from bipolar-code → Settings → "Copiar API Key completa" and stop.
- Exit 82 → bipolar-code is off, the URL is wrong or this PC is off the LAN; report it and stop. Do not retry in a loop.
- Exit 84 → the key check got another answer: 404 means a server without the broker (older than 2.13; tell the user to update bipolar-code), 503 means authentication is not configured on the server. Report it and stop.
- Health must report `"version":"2.13` or newer and `"delegation_enabled":true`. Older server → tell the user to update bipolar-code. `delegation_enabled:false` → tell the user to enable it in bipolar-code → Agentes (switch "Delegación a agentes CLI" + workspaces permitidos) and stop.

Step 2 — Submit. Pass the task verbatim on stdin through a single-quoted heredoc (the closing `EOF_TASK` must stay alone at column 0) and put only the given flags on the command line. Never type the JSON yourself: the script writes the task to a temporary file, serializes the body with `node` (or Python's `json` when node is missing) and posts it with `--data-binary @file`, so apostrophes, quotes, backticks, `$VAR`, `$(...)` and newlines reach the broker intact. It also forwards the inherited `BIPOLAR_DELEGATION_DEPTH` as `X-Bipolar-Depth`, so the broker's own guard refuses nested jobs.

```bash
bipolar-delegate-submit <<'EOF_TASK'
<task text, verbatim>
EOF_TASK
```

- Add `--workspace '<abs path>'`, `--mode text`, `--agent <id>`, `--tier <tier>`, `--timeout <s>` or `--dry-run` right after `bipolar-delegate-submit` only when the matching flag was given; without them the body carries only `task`, `workspace` and `mode`. Without `--workspace` the script sends the current directory in the server's native form. A `--workspace` path goes in the server's native form: `C:/...` on Windows (forward slashes work), not `/c/...`; if the path contains an apostrophe, write it as `'\''`.
- The broker resolves the workspace on the machine that runs bipolar-code, not on this one. `--mode task` from another PC of the LAN only works when the same path exists on the server host; otherwise use `--mode text` (the agent runs in a scratch directory on the server and answers in text) or `bipolar-rescue`.
- The heredoc delimiter must not occur anywhere in the task text. Use `EOF_TASK` unless the task contains that string; then pick another (e.g. `EOF_TASK_7f3a`) for both the opening `<<'...'` and the closing line.
- The output is the broker's reply followed by a last line `HTTP <code>`; interpret it with the table below.
- Exit 64 → a flag was invalid (`--timeout` outside 60-3600, an unknown flag) or the task was empty: report the message and stop.
- Exit 78 → no config in the environment nor in the file written by `/bipolar:setup`; tell the user to run `/bipolar:setup` and stop.
- Exit 79 → neither node nor python could run; report it and stop. The temporary directory is removed when the call ends.
- Exit 82 → the POST got no answer: bipolar-code is off, the URL is wrong or this PC is off the LAN; report it and stop.

Interpret the response:

- 200 when `--dry-run` was given → report the chosen `agent_id`, `model`, `tier` and `skipped` list; stop.
- 200 otherwise → the job, with `status: queued`: note its `id` and continue.
- 401 → the key was rejected (changed on the server since step 1): tell the user to run `/bipolar:setup` with the full API key and stop.
- 400 `workspace_allowlist_empty` → bipolar-code has no allowed workspaces yet; tell the user to add the project's path in Agentes → Workspaces permitidos. Stop.
- 400 `workspace_not_allowed` → the workspace is not inside any allowed workspace; tell the user to add the path (or a parent) in Agentes → Workspaces permitidos. Stop.
- 400 `workspace_required` → the body went out without a workspace, which `bipolar-delegate-submit` never sends (it falls back to the current directory): an outdated or modified script. Report it verbatim and stop.
- 400 `workspace_not_absolute` → the path is relative or in Git Bash form (`/c/...`), which the server does not treat as absolute. Submit again with the absolute native path (`C:/...` on Windows); leaving out `--workspace` already produces it.
- 400 `workspace_missing` → the path does not exist on the server host. From another PC the local path usually does not exist there: tell the user that `--mode task` needs the repo at that same path on the server host, or offer `--mode text`. Stop.
- 400 `workspace_not_dir` → the path is a file, not a directory; ask the user for the project directory. Stop.
- 400 `workspace_forbidden` → the broker never runs agents in a drive root, the home directory, bipolar-code's config dir or anything inside `.git`; ask the user for the project directory. Stop.
- 400 `no_agent_available` → show `reasons` and `skipped` (each entry says why an agent was skipped: `disabled`, `not_installed`, `exhausted:quota_exhausted`, `busy`, `tier_unsupported`, `agy_deny_list_missing`, `cursor_deny_list_missing`). Stop; the caller decides another lane. `cursor_deny_list_missing` means the server host lacks `~/.cursor-rescue/cli-config.json`: run `/cursor:setup` from the cursor plugin (cursor-plugin-cc) on that host.
- 409 `delegation_disabled` / `recursion_guard`, 429 `too_many_jobs` → report verbatim and stop.
- 422 → the broker rejected a field (e.g. `timeout_s` outside 60-3600); report its `detail` and stop.

Step 3 — Follow the job. Run this with the Bash tool's `timeout` set to `600000` (its maximum): the default 120000 ms would kill it after two minutes. One call is a segment of at most 9 minutes; jobs can run far longer (each attempt up to its agent's limit or `timeout_s`, up to 3 attempts with failover, plus time `queued` behind other jobs), so keep re-running the same command while it exits 75.

```bash
bipolar-delegate-wait <id>
```

- Exit 0 → the last line is the final job JSON; go to step 4.
- Exit 75 → the job is still `queued` or `running`: run the same command again (again with `timeout: 600000`). Tell the user it is still going after each segment.
- Exit 74 → the status could not be read three times in a row (network error, server down or a non-JSON reply). The job may still be running on the server: report it with the last HTTP code and ask the user whether to keep waiting (re-run the command) or cancel it.
- Exit 76 → job lost: bipolar-code restarted, so the job and its log are gone and its CLI may have stopped halfway through an edit. Tell the user to check `git status` in the workspace before resubmitting.
- Exit 64 → the id is not a job id; exit 78 → no config (see step 2). Report it and stop.

Cancel — when the user asks to stop, or wants to give up on a job that is still `queued` or `running`, cancel it instead of just stopping the polling (otherwise the delegate keeps editing the working tree):

```bash
bipolar-delegate-cancel <id>
```

The reply is the job with `status: cancelled`; the broker kills the agent's process tree. Edits already made stay in the working tree: tell the user to review `git status` / `git diff`. A last line `HTTP 404` means the job is already gone.

Step 4 — Report. From the final job JSON give: `status` (`succeeded`, `failed`, `timeout`, `cancelled`, `quota`, `auth_error`), `agent_id` and `model`, one line per attempt (`agent_id`, `signal`, `duration_s`, `error`), `files_touched`, and `output_tail` verbatim; when `output_tail` is empty, give the job's `error` instead. When `status` is `quota`, say which agents were tried and what the last quota excerpt was; the caller decides whether another lane or inline work follows. When the output is truncated, offer `GET /api/delegate/jobs/<id>/output` for the full log.

Rules:

- Never run the task yourself and never retry a finished job on your own: the broker already applied its failover policy.
- The delegate edits the live working tree of the workspace (edits are auto-accepted inside each CLI's safety flags). Review `git diff` before committing; the orchestrator owns the commit.
- Do not pass secrets in the task text: the job log is stored under bipolar-code's config dir.
