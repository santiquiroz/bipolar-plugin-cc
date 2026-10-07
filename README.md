# bipolar-plugin-cc

Claude Code plugin that delegates agentic coding tasks to a big local model served by [bipolar-code](https://github.com/santiquiroz/bipolar-code), your self-hosted LLM gateway, in two ways:

1. **`bipolar-rescue`** — a headless Claude Code instance pointed at the **big local model** bipolar-code serves (managed llama.cpp, multi-GPU, Anthropic Messages API native):

   ```bash
   ANTHROPIC_BASE_URL=http://<server>:8000 ANTHROPIC_API_KEY=<key> claude -p ... <<'EOF_TASK'
   <task>
   EOF_TASK
   ```

   The delegate reads and edits files itself; it is not a plain text-completion call. Free, zero-quota, LAN-wide.

2. **`/bipolar:delegate`** (bipolar-code ≥ 2.13) — hands the task to bipolar-code's **delegation broker**, which classifies it by complexity and runs it on the best available CLI agent installed on the server host — `muse` (Muse Code, bipolar-code ≥ 2.17), `claude`, `codex`, `copilot`, `agy` (Antigravity), `cursor-agent` (Cursor, bipolar-code ≥ 2.15), `ollama` or `dsh` (DeepSeek Harness, bipolar-code ≥ 2.16) — skipping agents that are out of quota or busy and failing over when an attempt dies on a quota signal. One call, the right agent, the job followed to the end.

## When it helps

- **Free, zero quota**: the work runs on a local or LAN model on your own hardware instead of your API quota.
- **Agentic**: the delegate reads and edits files itself; it does not just return text.
- **Medium-complexity, well-specified tasks**: multi-file mechanical edits, tests from pasted signatures, boilerplate with real file I/O, refactors with exact instructions.
- **Self-contained prompts**: local models follow exact instructions well and improvise poorly, so paste signatures, paths, and contracts into the task text.
- **Review the diff after every run**: edits are auto-accepted in the delegate session; the caller owns the commit.

## Requirements

- A reachable bipolar-code server (≥ 2.10) with its llama-server running and a model loaded.
- For `/bipolar:delegate`: bipolar-code ≥ 2.13 with the delegation broker enabled (Agentes → switch + workspaces permitidos).
- `claude` CLI on the delegating machine.
- `node` or Python 3 on the delegating machine for `/bipolar:delegate` (it serializes the job's JSON body; `jq` is not needed).

## Install

```
/plugin marketplace add santiquiroz/bipolar-plugin-cc
/plugin install bipolar@bipolar-plugin-cc
```

## Setup

Configure once per machine:

```
/bipolar:setup http://<server-ip>:8000 <api-key>
```

(URL and key come from bipolar-code → Settings → "Conectar PCs remotas".)

## Usage

- `/bipolar:rescue <well-specified task>` — headless Claude Code on the local big model, in the current repo.
- `/bipolar:delegate <task>` — the broker picks the agent. Flags: `--workspace <abs path>` (default: current directory, sent as `C:/...` on Windows; must be in the server's allow-list and exist on the server host, since the broker resolves it there: from another PC of the LAN use `--mode text`), `--agent muse|claude|codex|copilot|antigravity|cursor|ollama|deepseek` to pin one (`cursor` needs bipolar-code ≥ 2.15, `deepseek` ≥ 2.16, `muse` ≥ 2.17), `--mode text` for an answer without file access, `--tier trivial|simple|standard|complex` to override the classifier, `--timeout <s>` to set the per-attempt limit (`timeout_s`, 60-3600 s; default: each agent's own), `--dry-run` to see the choice without running.
- Or let the `bipolar-rescue` subagent fire proactively (see `docs/claude-md-snippet.md` for delegation rules to paste into your `~/.claude/CLAUDE.md`).

What `/bipolar:delegate` reports: job status (`succeeded`, `failed`, `timeout`, `cancelled`, `quota`, `auth_error`), the agent and model used, one line per attempt with the quota signal that caused a failover, `files_touched` and the agent's final output (or the job's `error` when there is none). A `quota` status means every eligible agent of that tier is exhausted; report it to the user so they can choose another route. Long jobs are followed in segments of up to 9 minutes (one Bash call each, with a 600000 ms timeout) until they finish; asking to stop cancels the job on the server (`DELETE /api/delegate/jobs/<id>`) so it stops editing the working tree.

## Configuration

The plugin reads its server URL and API key from (in order):

1. Environment variables `BIPOLAR_URL` and `BIPOLAR_API_KEY`, if set.
2. The file `$HOME/.config/bipolar-cc/env`, written by `/bipolar:setup`:

```
BIPOLAR_URL=<url>
BIPOLAR_API_KEY=<key>
```

Use the full API key (bipolar-code → Settings → "Copiar API Key completa"): the `/api/*` routes only accept it (`/v1` also takes the legacy proxy key).

## Troubleshooting

- **Server unreachable** (wrong URL, backend off, off-LAN): stop, tell the user in one line, and do the work inline. No retry loops.
- **llama-server stopped or still loading** (bipolar-code is up but `/api/llamacpp/status` does not report it `running` and `healthy`): stop, tell the user in one line, and do the work inline. Starting it is the user's call (bipolar-code → Providers → llama.cpp → Iniciar, with a GGUF model configured).
- **Wrong key** (401 on `/api/*`): run `/bipolar:setup` again with the full API key and stop.
- **Broker missing or disabled** (server older than 2.13, or `delegation_enabled:false`): update bipolar-code or enable delegation in bipolar-code → Agentes (switch "Delegación a agentes CLI" + workspaces permitidos). `/bipolar:rescue` works without the broker.
- **`quota` from `/bipolar:delegate`**: every eligible agent of that tier is exhausted; report it to the user so they can choose another route. Do not resubmit in a loop.

## Delegating through bipolar-code's MCP server (no plugin needed)

bipolar-code 2.18 exposes delegation as MCP tools at `/mcp`: `delegate`, `job_status`, `job_output`, `cancel_job`, `list_agents`. To use them without this plugin, register the server once:

```bash
claude mcp add --transport http --scope user bipolar http://<host>:8000/mcp --header "x-api-key: <ui_api_key>"
```

`/mcp` is a control-plane endpoint: it requires the key and honors the server's allowed networks. This plugin remains useful for `/bipolar:rescue` (headless Claude Code on the local model) and for older servers.

## Using it with other delegates

If you run several delegation plugins, the order in which they are tried is yours to define in your own `CLAUDE.md`; this plugin does not assume any other delegate exists.

## Notes

- `bipolar-rescue` runs the child Claude Code with `--permission-mode acceptEdits` and `--disallowedTools Task,Agent,Skill` (no recursive delegation). The child is also isolated from the machine's setup: `--settings '{"disableAllHooks":true}'` (a global Stop hook could otherwise launch a review command on the repo the child leaves uncommitted and spend paid quota), `--strict-mcp-config` (no MCP tool definitions filling the local model's context), `--max-turns 50` (the broker's cap) and `timeout 570`, which stops it before the Bash tool's 10-minute ceiling; exit 124 is reported as a partial result to review with `git diff`. The fuller `--bare` mode (also skips CLAUDE.md, plugins and auto-memory) is not used. The broker applies each CLI's own safety flags server-side (claude `acceptEdits` without `Task/Agent`, codex `workspace-write`, copilot deny list, agy only with its global deny list) and refuses workspaces outside its allow-list. Review `git diff` before committing — the caller owns the commit.
- Recursion guard: bipolar-code's broker launches every CLI with `BIPOLAR_DELEGATION_DEPTH=1`, and `bipolar-rescue` sets the same variable on its child. Inside such a session `/bipolar:delegate` and `bipolar-rescue` refuse to run (exit 77), and `/bipolar:delegate` forwards the value as `X-Bipolar-Depth` so the broker rejects nested jobs with `recursion_guard` even if the local check is skipped.
- Health checks: `bipolar-rescue` only launches its child when `/api/llamacpp/status` reports llama-server `running` and `healthy` (`/v1/models` is a static list that answers even with it stopped); `/bipolar:delegate` validates the key on an authenticated `/api` route before submitting; `/bipolar:setup` shows the smoke's `X-Bipolar-Route` header, since smart routing may send a request to a provider other than `llamacpp` (possibly a paid one).
- The job log lives under bipolar-code's config dir: keep secrets out of task text.

## Tests

The shell logic lives in scripts under `bin/` (Claude Code puts each enabled plugin's `bin/` on the Bash tool's `PATH`), so Claude runs the same tested code every time instead of re-typing it from the markdown: `bipolar-delegate-check`, `bipolar-delegate-submit`, `bipolar-delegate-wait`, `bipolar-delegate-cancel`, `bipolar-rescue-check`, `bipolar-rescue-run` and `bipolar-setup-verify`. They need `bash` and `curl` (Git Bash on Windows).

The tests run those scripts against a stub HTTP server from Python's standard library and a fake `claude` on `PATH` (no bipolar-code, no real CLI, no network beyond 127.0.0.1): `python -m unittest discover -s tests -v`. They also run the command and agent markdown's bash blocks as written.

## License

MIT
