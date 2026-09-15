# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## O que é
Servidor MCP (Python 3.13, Starlette + SDK `mcp` 2.x, Streamable HTTP **stateless**) hospedado em Azure Container Apps e consumido por agentes do Microsoft Foundry (Teams/M365 Copilot). Base reutilizável para projetos de IA: hospeda vários **toolsets** corporativos em fatias verticais. O toolset inicial é o `diagnostico` (`diag_whoami`, `diag_sharepoint_probe`), que valida a cadeia de autenticação Entra + OBO. Plano e fases: `docs/phase0-spike.md`.

Não há FastAPI de propósito: a superfície de negócio são tools MCP (schema/validação vêm do SDK) e o SDK já entrega uma app Starlette. Se surgirem rotas REST de negócio, reavaliar.

## Comandos
```bash
uv sync                                    # rede corporativa: UV_SYSTEM_CERTS=1 uv sync
uv run pytest                              # todos os testes
uv run pytest tests/unit/auth/test_verifier.py::test_rejects_invalid_claims   # um teste
UPDATE_CONTRACTS=1 uv run pytest tests/contract   # regenerar snapshot de contrato das tools
uv run ruff check src tests scripts && uv run ruff format --check src tests scripts
uv run mypy src                            # strict
uv run uvicorn ui_genai_mcp.app:app_factory --factory --reload --port 8000   # local (use .env, AUTH_ENABLED=false)
uv run python scripts/smoke_mcp.py --url http://127.0.0.1:8000/mcp --tool diag_whoami
```

## Arquitetura
- `app.py::create_app(settings, services)` é a composition root (app Starlette). O sub-app MCP é montado em **`/`** (não num subcaminho) porque o Protected Resource Metadata é servido em `/.well-known/oauth-protected-resource/mcp`; as rotas `/healthz` e `/readyz` (também em `app.py`) vêm **antes** do mount. O lifespan do app host precisa entrar em `mcp.session_manager.run()` (sub-apps montados não rodam lifespan).
- `mcp_server.py::build_mcp` cria o `MCPServer` com `EntraTokenVerifier` + `AuthSettings` e chama `register(mcp, ctx)` de cada toolset habilitado (`ENABLED_TOOLSETS`). **Não** usamos o `lifespan` do `MCPServer`; recursos compartilhados vivem em `core/services.py::Services`.
- Auth é por endpoint (todo `/mcp` exige Bearer), não por tool. O Foundry (custom OAuth passthrough) obtém um token do usuário com `aud` = app registration existente. `auth/verifier.py` valida (RS256/JWKS, aud v1+v2, issuer, tenant, exige `scp` — rejeita app-only) e converte `scp` curto em URI completa (`api://{client_id}/{scope}`), pois o SDK compara `required_scopes` literalmente. Tools obtêm o usuário via `ctx.current_user()`; chamadas downstream usam **OBO** (`auth/obo.py`) através de `integrations/graph.py`.
- Toolsets em fatias verticais: `toolsets/<nome>/` contém tudo do domínio (models, tools, settings, domínio puro, adapters). Registro **explícito** em `toolsets/registry.py::ALL_TOOLSETS`. Guia: `docs/adding-a-toolset.md`.
- Toda tool envolve o corpo em `async with tool_invocation(ctx, "<nome>") as user:` (`toolsets/_shared.py`): checa scopes do toolset, injeta contexto de log e converte `AppError` → `ToolError` com `user_message` pt-BR. É context manager (não decorator) para não alterar a assinatura da qual o SDK gera o `inputSchema`.
- Middleware HTTP deve ser ASGI puro (ver `core/request_context.py`), não `BaseHTTPMiddleware`, para não interferir no streaming do transporte MCP.

## Regras do projeto
- Nunca repassar o token do usuário para APIs downstream (token passthrough) — sempre OBO.
- Nunca logar tokens, argumentos de tools, nomes pesquisados, e-mails ou resultados (LGPD). Identificar usuário só por `user_ref`. Não versionar bases corporativas reais nem segredos.
- Erros esperados: levantar subclasses de `core/errors.py::AppError`; o texto técnico (`str(exc)`) vai só para log. "Não encontrado" é resultado normal, não erro.
- Nomes/schemas/annotations de tools são contrato com os agentes: `tests/contract/snapshots/tools.json` quebra em mudanças acidentais. Nomes: `^[a-z0-9_]{1,64}$`, sem pontos; novos toolsets usam prefixo do domínio.
- Código em inglês; nomes, descrições e mensagens de tools em pt-BR. Tools de leitura usam `READ_ONLY_CLOSED`.
- `domain/` de cada toolset não importa `mcp`, `starlette` nem `httpx`.
- Testes: `Client(mcp)` em memória **ignora autenticação**; comportamento de auth/HTTP é testado em `tests/integration/test_http_app.py` com tokens assinados localmente (`tests/support.py`).
