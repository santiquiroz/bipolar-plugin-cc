---
description: Configure this machine to delegate to a bipolar-code server (URL + API key), then verify the connection
---

Set up delegation to a bipolar-code server. Steps:

1. Ask the user for two values (or take them from $ARGUMENTS if provided as `<url> <api-key>`):
   - **URL**: the bipolar-code server, e.g. `http://192.168.1.50:8000` (shown in bipolar-code → Settings → "Conectar PCs remotas"). On the server machine itself, `http://127.0.0.1:8000`.
   - **API key**: from bipolar-code → Settings → "Copiar API Key completa".

2. Write the config file `$HOME/.config/bipolar-cc/env` (create the directory if needed, never overwrite other keys in it if it exists — update only these two lines):

```
BIPOLAR_URL=<url>
BIPOLAR_API_KEY=<key>
```

3. Verify, in order, reporting each result:

```bash
. "$HOME/.config/bipolar-cc/env"
# a) auth + reachability
curl -s -o /dev/null -w "%{http_code}\n" -H "x-api-key: $BIPOLAR_API_KEY" "$BIPOLAR_URL/v1/models"
# b) end-to-end completion through the local model (needs llama-server running with a model)
curl -s -H "x-api-key: $BIPOLAR_API_KEY" -H "content-type: application/json" \
  "$BIPOLAR_URL/v1/messages" \
  -d '{"model":"claude-sonnet-4-6","max_tokens":32,"messages":[{"role":"user","content":"Say OK"}]}'
```

4. Interpret:
   - (a) `401` → wrong key. `000` → server unreachable (backend off / wrong IP / off-LAN).
   - (b) error mentioning the local server not responding → bipolar-code is up but llama-server is not: open bipolar-code → Providers → llama.cpp → Iniciar (and make sure a GGUF model is configured and `llamacpp` is the active provider).
   - Both OK → confirm setup complete and remind: delegate with `/bipolar:rescue <task>` or let the `bipolar-rescue` subagent fire proactively.
