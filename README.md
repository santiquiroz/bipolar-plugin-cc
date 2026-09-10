# bipolar-plugin-cc

Claude Code plugin that delegates coding work to [bipolar-code](https://github.com/santiquiroz/bipolar-code), your self-hosted LLM gateway, in two ways:

1. **`bipolar-rescue`** — a headless Claude Code instance pointed at the **big local model** bipolar-code serves (managed llama.cpp, multi-GPU, Anthropic Messages API native):

   ```bash
   ANTHROPIC_BASE_URL=http://<server>:8000 ANTHROPIC_API_KEY=<key> claude -p "<task>" ...
   ```

   The delegate reads and edits files itself, unlike plain text-completion delegates. Free, zero-quota, LAN-wide.

2. **`/bipolar:delegate`** (bipolar-code ≥ 2.13) — hands the task to bipolar-code's **delegation broker**, which classifies it by complexity and runs it on the best available CLI agent installed on the server host — `claude`, `codex`, `copilot`, `agy` (Antigravity) or `ollama` — skipping agents that are out of quota or busy and failing over when an attempt dies on a quota signal. One call, the right agent, the job followed to the end.

## Where it sits in a delegation chain

| Tier | Delegate | Good for |
|---|---|---|
| trivial | [ollama-plugin-cc](https://github.com/santiquiroz/ollama-plugin-cc) | one-shot text transforms, small local model |
| **medium** | **`bipolar-rescue` (this plugin)** | bounded agentic tasks with exact instructions: multi-file renames, spec generation, boilerplate with real file I/O |
| mechanical | [copilot-plugin-cc](https://github.com/santiquiroz/copilot-plugin-cc) | boilerplate, renames, simple specs |
| frontier | Codex / [antigravity-plugin-cc](https://github.com/santiquiroz/antigravity-plugin-cc) | architecture-adjacent implementation, deep diagnosis |
| **any, chosen for you** | **`/bipolar:delegate` (this plugin)** | let bipolar-code pick the lane by tier and remaining quota |

## Requirements

- A machine running bipolar-code (≥ 2.10 for `bipolar-rescue`, ≥ 2.13 for `/bipolar:delegate`) with the `llamacpp` provider active and a model loaded, or with the delegation broker enabled (Agentes → switch + workspaces permitidos).
- `claude` CLI on the delegating machine.

## Install

```
/plugin marketplace add santiquiroz/bipolar-plugin-cc
/plugin install bipolar@bipolar-plugin-cc
```

Then configure once per machine:

```
/bipolar:setup http://<server-ip>:8000 <api-key>
```

(URL and key come from bipolar-code → Settings → "Conectar PCs remotas".)

## Use

- `/bipolar:rescue <well-specified task>` — headless Claude Code on the local big model, in the current repo.
- `/bipolar:delegate <task>` — the broker picks the agent. Flags: `--workspace <abs path>` (default: current directory; must be in the server's allow-list), `--agent claude|codex|copilot|antigravity|ollama` to pin one, `--mode text` for an answer without file access, `--tier trivial|simple|standard|complex` to override the classifier, `--dry-run` to see the choice without running.
- Or let the `bipolar-rescue` subagent fire proactively (see `docs/claude-md-snippet.md` for delegation rules to paste into your `~/.claude/CLAUDE.md`).

What `/bipolar:delegate` reports: job status (`succeeded`, `failed`, `timeout`, `quota`, `auth_error`), the agent and model used, one line per attempt with the quota signal that caused a failover, `files_touched` and the agent's final output. A `quota` status means every eligible agent of that tier is exhausted; the caller picks another lane.

## Notes

- `bipolar-rescue` runs the child Claude Code with `--permission-mode acceptEdits` and `--disallowedTools Task,Agent` (no recursive delegation). The broker applies each CLI's own safety flags server-side (claude `acceptEdits` without `Task/Agent`, codex `workspace-write`, copilot deny list, agy only with its global deny list) and refuses workspaces outside its allow-list. Review `git diff` before committing — the caller owns the commit.
- Local models follow precise instructions well and improvise badly: paste signatures, paths, and contracts into the task text.
- The job log lives under bipolar-code's config dir: keep secrets out of task text.

## License

MIT
