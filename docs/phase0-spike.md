# Fase 0 — Spike de autenticação (Foundry → Teams/M365 Copilot)

**Pergunta a responder:** quando o agente do Foundry publicado no Teams/M365 Copilot chama este MCP, a chamada chega com o **token do próprio usuário** (após o card de consentimento), permitindo OBO para o Graph?

Não há documentação oficial conclusiva (moderador Microsoft afirma que não; relato de funcionário Microsoft afirma que sim). Por isso validamos com as tools `diag_whoami` e `diag_sharepoint_probe` antes de portar toolsets de negócio.

## Passos
1. `uv run pytest` verde; build e deploy conforme `docs/foundry-setup.md` com `ENABLED_TOOLSETS=diagnostico`.
2. Checagens HTTP (`/healthz`, 401 em `/mcp`, metadata em `/.well-known/oauth-protected-resource/mcp`).
3. **Playground do Foundry**: pedir "use a ferramenta diag_whoami". Esperado: card/link de consentimento → após consentir, retorno com seu nome/UPN.
4. `diag_sharepoint_probe`: esperado `sharepoint_file_ok=true`.
5. Repetir 3–4 com um **segundo usuário** (apenas role Foundry Agent Consumer).
6. Publicar ("Just you") e repetir 3–5 no **Teams**.
7. Repetir 3–5 no **M365 Copilot**.
8. No dia seguinte (> 1 h): repetir sem novo consentimento (valida refresh/`offline_access`).
9. Usuário sem acesso ao SharePoint: mensagem amigável, conversa não trava.

Durante os testes, acompanhar logs: `az containerapp logs show -n ui-genai-mcp -g <rg> --follow`. Procurar `access_token_rejected` (campo `reason`; `not_user_token` = chegou token app-only) e `tool_call` (`outcome`).

## Critérios
| Resultado | Condição |
|---|---|
| **Go** | Em Teams **e** Copilot: `diag_whoami` retorna o usuário real (UPNs diferentes para os 2 usuários), `scopes` contém o scope exigido, `diag_sharepoint_probe` ok, consentimento concluível dentro do canal, refresh funciona. |
| **Parcial** | Funciona em só um dos canais → decisão com stakeholders. |
| **No-go** | Sem token, token app-only (`not_user_token`) ou consentimento impossível no canal → registrar evidências (horários, `reason`, request ids), abrir chamado Microsoft e avaliar o fallback. |

## Fallback (não implementado)
Fonte de dados em Blob (lido pela managed identity do Container App) + autenticação por agent identity/project managed identity. Tools e domínio não mudam. **Perde a autorização por usuário** → exige aceite de LGPD/negócio.

## Resultados
| Data | Canal | Usuário | whoami | probe | Observações |
|---|---|---|---|---|---|
| | Playground | | | | |
| | Teams | | | | |
| | M365 Copilot | | | | |
