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
# a) server version and broker switch (public endpoint: proves nothing about the key)
echo "health: $(curl -s --max-time 10 "$BIPOLAR_URL/api/health")"
# b) the key on /api/*, where bipolar-rescue and /bipolar:delegate check it (/v1 also accepts the legacy proxy key)
echo "api key: HTTP $(curl -s --max-time 10 -o /dev/null -w '%{http_code}' -H "x-api-key: $BIPOLAR_API_KEY" "$BIPOLAR_URL/api/delegate/jobs?limit=1")"
# c) the managed llama-server behind the llamacpp provider
echo "llama.cpp: $(curl -s --max-time 10 -H "x-api-key: $BIPOLAR_API_KEY" "$BIPOLAR_URL/api/llamacpp/status")"
# d) end-to-end completion; -D - prints the response headers, X-Bipolar-Route says which provider answered
curl -s -D - -H "x-api-key: $BIPOLAR_API_KEY" -H "content-type: application/json" \
  "$BIPOLAR_URL/v1/messages" \
  -d '{"model":"claude-sonnet-4-6","max_tokens":32,"messages":[{"role":"user","content":"Say OK"}]}'
```

4. Interpret:
   - (a) empty → server unreachable (backend off / wrong IP / off-LAN); stop. Otherwise report `version` and `delegation_enabled`: `/bipolar:delegate` needs version 2.13 or newer and `delegation_enabled:true` (bipolar-code → Agentes → switch "Delegación a agentes CLI" + workspaces permitidos); `bipolar-rescue` works without the broker.
   - (b) `200` → the key is valid on `/api`. `401` → wrong key (a key that only works on `/v1` is the legacy proxy key: copy the full one from Settings → "Copiar API Key completa"). `404` → server older than 2.13 (no broker; `bipolar-rescue` can still work).
   - (c) `"running":true` and `"healthy":true` → llama-server is ready. `"running":false` → bipolar-code is up but llama-server is not: open bipolar-code → Providers → llama.cpp → Iniciar (and make sure a GGUF model is configured and `llamacpp` is the active provider). `"healthy":false` while running → it is still loading the model; check again in a minute.
   - (d) an error mentioning the local server not responding → llama-server is down (see c). Otherwise report the `X-Bipolar-Route` header: `target=provider:llamacpp` means the local model answered. Any other target means smart routing sent the request to another provider (possibly a paid one): warn the user that `bipolar-rescue` is then neither local nor free, and that the routing is set in bipolar-code (smart routing mode and the `llamacpp` provider).
   - All OK → confirm setup complete and remind: delegate with `/bipolar:rescue <task>` (or let the `bipolar-rescue` subagent fire proactively) for the local model, or `/bipolar:delegate <task>` to let bipolar-code's broker pick the CLI agent by tier and quota.
