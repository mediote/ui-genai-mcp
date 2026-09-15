# ui-genai-mcp

Servidor **MCP** (Model Context Protocol) corporativo em **Python (Starlette/SDK MCP) + Docker**, hospedado em **Azure Container Apps** e consumido por agentes do **Microsoft Foundry** (Teams / M365 Copilot). Serve de **base reutilizável** para projetos de IA: autenticação Entra por endpoint, OBO para Microsoft Graph e uma arquitetura de *toolsets* em fatias verticais. O toolset inicial é o `diagnostico`.

```
Usuário (Teams/Copilot) ─► Agente Foundry ──Bearer (aud=api://app)──► ui-genai-mcp (/mcp)
        ▲ card de consentimento (1ª vez)                                 │ valida JWT Entra
        └──────────── Entra ID ◄─────────────────────────────────────────┤ OBO (mesmo usuário)
                                                                         ▼
                                                              Microsoft Graph / SharePoint
```

**Status:** Fase 0 — spike de autenticação com o toolset `diagnostico` (`diag_whoami`, `diag_sharepoint_probe`). Ver `docs/phase0-spike.md`.

## Pré-requisitos
- [uv](https://docs.astral.sh/uv/) (`winget install astral-sh.uv`). Em rede com inspeção TLS: `UV_SYSTEM_CERTS=1`.
- Python 3.13 (o uv instala: `uv python install 3.13`).
- Azure CLI para deploy (`az acr build` dispensa Docker local).

## Início rápido (local, sem autenticação)
```bash
cp .env.example .env            # AUTH_ENABLED=false
uv sync
uv run uvicorn ui_genai_mcp.app:app_factory --factory --reload --port 8000
curl http://127.0.0.1:8000/healthz
uv run python scripts/smoke_mcp.py --url http://127.0.0.1:8000/mcp --tool diag_whoami
```
Ou com Docker: `docker compose up --build`.

## Qualidade
```bash
uv run pytest                                   # testes (unit, integração HTTP, contrato)
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy src
UPDATE_CONTRACTS=1 uv run pytest tests/contract # após mudar tools de propósito
```

## Configuração
Todas as variáveis estão documentadas em `.env.example`. Principais:

| Variável | Descrição |
|---|---|
| `AUTH_ENABLED` | `true` em Azure; `false` só em dev local (proibido em `prd`). |
| `AZURE_AD_TENANT_ID` / `AZURE_AD_CLIENT_ID` / `AZURE_AD_CLIENT_SECRET` | App registration existente (OBO). |
| `MCP_REQUIRED_SCOPE` | Scope curto exposto pelo app (`access_as_user`). |
| `PUBLIC_BASE_URL` | URL pública (define o recurso e o Protected Resource Metadata). |
| `ALLOWED_HOSTS` | Host(s) aceitos — FQDN do Container App (proteção DNS rebinding). |
| `ENABLED_TOOLSETS` | Toolsets expostos, separados por vírgula. |

## Endpoints
| Rota | Uso |
|---|---|
| `POST /mcp` | Transporte MCP Streamable HTTP (stateless, exige Bearer). |
| `GET /.well-known/oauth-protected-resource/mcp` | Protected Resource Metadata (RFC 9728). |
| `GET /healthz` / `GET /readyz` | Liveness / readiness. |

## Documentação
- `docs/adding-a-toolset.md` — processo de registro de novas tools.
- `docs/foundry-setup.md` — Container Apps, app registration e connection no Foundry.
- `docs/phase0-spike.md` — roteiro e critérios do spike.

## Troubleshooting
| Sintoma | Causa provável |
|---|---|
| `421 Invalid Host header` | FQDN ausente em `ALLOWED_HOSTS`. |
| `401` com token válido | `aud`/tenant diferentes, token app-only (log `access_token_rejected`, campo `reason`). |
| `403 insufficient_scope` | Token sem o scope `MCP_REQUIRED_SCOPE`. |
| `RuntimeError: Task group is not initialized` | Lifespan do app não executado (subir via `app_factory`). |
| Mensagem "faça login novamente" | OBO falhou (`invalid_grant`/consentimento) — ver log `obo_failed`. |
