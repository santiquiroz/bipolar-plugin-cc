# bipolar-plugin-cc

Claude Code plugin that delegates **agentic** coding tasks to a **big local model** served by [bipolar-code](https://github.com/santiquiroz/bipolar-code) (managed llama.cpp, multi-GPU, Anthropic Messages API native).

The trick: bipolar-code speaks the Anthropic API, so the delegate is a full **headless Claude Code** instance pointed at it —

```bash
ANTHROPIC_BASE_URL=http://<server>:8000 ANTHROPIC_API_KEY=<key> claude -p "<task>" ...
```

— which means the delegate reads and edits files itself, unlike plain text-completion delegates.

## Where it sits in a delegation chain

| Tier | Delegate | Good for |
|---|---|---|
| trivial | [ollama-plugin-cc](https://github.com/santiquiroz/ollama-plugin-cc) | one-shot text transforms, small local model |
| **medium** | **bipolar-plugin-cc (this)** | bounded agentic tasks with exact instructions: multi-file renames, spec generation, boilerplate with real file I/O |
| reasoning | Codex / frontier | architecture, debugging, WHY |

Free, zero-quota, and usable from **any PC on the LAN** — a laptop with no GPU delegates to the rig serving the model.

## Requirements

- A machine running bipolar-code ≥ 2.10 with the `llamacpp` provider active and a model loaded (e.g. Qwen3-Coder-Next 80B-A3B Q4 on 48GB VRAM).
- `claude` CLI installed on the delegating machine.

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

- `/bipolar:rescue <well-specified task>` — explicit delegation.
- Or let the `bipolar-rescue` subagent fire proactively (see `docs/claude-md-snippet.md` for delegation rules to paste into your `~/.claude/CLAUDE.md`).

## Notes

- The child Claude Code runs with `--permission-mode acceptEdits` and `--disallowedTools Task,Agent` (no recursive delegation). Review `git diff` before committing — the caller owns the commit.
- Local models follow precise instructions well and improvise badly: paste signatures, paths, and contracts into the task text.

## License

MIT
