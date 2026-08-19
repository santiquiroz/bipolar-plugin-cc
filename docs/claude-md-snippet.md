# Snippet para ~/.claude/CLAUDE.md

Pegar en la sección de delegación multi-agente:

```markdown
## Auto-delegate to bipolar (local big model — LAN, zero quota)

Tier intermedio entre Ollama (trivial) y Codex (razonamiento). Delegado AGÉNTICO:
un Claude Code headless corriendo sobre el modelo grande local servido por
bipolar-code (llama.cpp multi-GPU). Plugin: `bipolar-plugin-cc` — subagente
`bipolar:bipolar-rescue`, comandos `/bipolar:rescue`, `/bipolar:setup`.

| Trigger | Action |
|---|---|
| Tarea mecánica-media bien especificada que toca archivos (renames multi-file, specs con firmas pegadas, boilerplate con I/O real, config en N archivos) | `bipolar:bipolar-rescue` en background — probar ANTES que Codex si no requiere razonamiento |
| Servidor bipolar inaccesible o llama-server apagado | Fallback: Ollama (si es texto puro) o Codex/inline |

Reglas:
- La tarea debe ser AUTOCONTENIDA: pegar firmas/paths/contratos en el prompt. El modelo local sigue instrucciones exactas bien e improvisa mal.
- Revisar `git diff` al volver — el hijo edita con acceptEdits; el orquestador commitea.
- Salida MEDIUM-TRUST: más confiable que ollama-rescue (agéntico real), menos que Codex.
- Funciona desde cualquier PC de la LAN del rig (laptop sin GPU delega al rig).
```
