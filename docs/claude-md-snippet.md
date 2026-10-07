# Snippet para ~/.claude/CLAUDE.md

Pegar en la sección de delegación:

```markdown
## Auto-delegate to bipolar (local big model — LAN, zero quota)

Delegado AGÉNTICO: un Claude Code headless corriendo sobre el modelo grande
local servido por bipolar-code (llama.cpp multi-GPU). Plugin:
`bipolar-plugin-cc` — subagente `bipolar:bipolar-rescue`, comandos
`/bipolar:rescue`, `/bipolar:delegate`, `/bipolar:setup`.

| Trigger | Action |
|---|---|
| Tarea mecánica-media bien especificada que toca archivos (renames multi-file, specs con firmas pegadas, boilerplate con I/O real, config en N archivos) | `bipolar:bipolar-rescue` en background |
| Tarea de código autocontenida cuando se prefiere que bipolar-code elija el agente ejecutor | `/bipolar:delegate <tarea>` — el broker de bipolar-code (≥ 2.13) elige el CLI por tier y cuota restante y hace failover solo |
| Servidor bipolar inaccesible o llama-server apagado | Parar, avisar al usuario en una línea, hacerlo inline |

Reglas:
- La tarea debe ser AUTOCONTENIDA: pegar firmas/paths/contratos en el prompt. El modelo local sigue instrucciones exactas bien e improvisa mal.
- Revisar `git diff` al volver — el hijo edita con acceptEdits; el orquestador commitea.
- `/bipolar:delegate` devuelve `status quota` cuando todos los agentes del tier están agotados: avisar al usuario en una línea y hacerlo inline, no reintentar.
- Salida MEDIUM-TRUST (`bipolar-rescue`, modelo local) o la del CLI elegido (`/bipolar:delegate` reporta cuál).
- `bipolar-rescue` funciona desde cualquier PC de la LAN del rig (laptop sin GPU delega al rig). `/bipolar:delegate` en modo task no: el broker resuelve el workspace en el host del servidor, así que la ruta tiene que existir allá (si no, `workspace_missing`); desde otra PC usar `--mode text`.
- Alternativa sin plugin: bipolar-code 2.18 expone la delegación como herramientas MCP en `/mcp` (`delegate`, `job_status`, `job_output`, `cancel_job`, `list_agents`).
```
