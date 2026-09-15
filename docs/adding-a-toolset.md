# Como adicionar um toolset

Um **toolset** é um conjunto de tools de um mesmo domínio (ex.: `servicenow`, `jira`). Cada toolset é autocontido numa pasta e registrado explicitamente num único lugar.

## 1. Estrutura

```
src/ui_genai_mcp/toolsets/<nome>/
  __init__.py      # TOOLSET = ToolsetSpec(...)
  settings.py      # <Nome>Settings(BaseSettings) com env_prefix="<NOME>_"
  models.py        # modelos Pydantic de saída (contrato MCP) — sempre com `mensagem: str`
  tools.py         # register(mcp, ctx): declara as tools
  service.py       # casos de uso (orquestra domínio + adapters)       [se necessário]
  ports.py         # Protocol da fonte de dados                       [se houver dados externos]
  domain/          # lógica pura (sem mcp/starlette/httpx)
  adapters/        # implementações das portas (Graph, API, arquivo local para dev/testes)
```

## 2. Declarar o toolset

```python
# toolsets/<nome>/__init__.py
from ui_genai_mcp.toolsets.base import ToolsetSpec
from ui_genai_mcp.toolsets.<nome>.tools import register

TOOLSET = ToolsetSpec(
    name="<nome>",                          # valor usado em ENABLED_TOOLSETS
    description="O que este toolset faz.",
    register=register,
    required_scopes=frozenset(),            # scopes curtos extras (claim scp), se o domínio for sensível
)
```

## 3. Escrever as tools

```python
# toolsets/<nome>/tools.py
from typing import Annotated
from pydantic import Field
from mcp.server.mcpserver import MCPServer

from ui_genai_mcp.toolsets._shared import READ_ONLY_CLOSED, tool_invocation
from ui_genai_mcp.toolsets.base import ToolsetContext

def register(mcp: MCPServer, ctx: ToolsetContext) -> None:
    @mcp.tool(
        name="<prefixo>_<verbo>_<objeto>",
        title="Título curto em pt-BR",
        description="Quando usar, o que retorna, exemplos de perguntas.",
        annotations=READ_ONLY_CLOSED,          # escrita/efeitos colaterais: defina annotations próprias
    )
    async def exemplo(
        termo: Annotated[str, Field(min_length=2, max_length=100, description="...")],
    ) -> ExemploResult:
        async with tool_invocation(ctx, "<prefixo>_<verbo>_<objeto>") as user:
            data = await ctx.services.graph.get_json(user, "...")   # OBO com a identidade do usuário
            return ExemploResult(..., mensagem="Resumo em pt-BR para o modelo.")
```

Regras:
- **Nome**: `^[a-z0-9_]{1,64}$`, sem pontos, com prefixo do domínio. É contrato público com os agentes.
- **Erros esperados**: levante `AppError` (`PermissionDenied`, `UpstreamUnavailable`, …). `tool_invocation` converte em `ToolError` com mensagem amigável. "Não encontrado" é resultado normal (`encontrado=false` + sugestões), não erro.
- **Entradas**: sempre `Annotated[..., Field(...)]` com limites (tamanho, faixa).
- **Saídas**: modelos Pydantic com `Field(description=...)`; strings vazias → `None`; listas com limite e flag `truncado`.
- **LGPD**: não logar argumentos/resultados; não expor dados sensíveis.
- Reutilize: `ctx.services.graph` (Graph via OBO), `core/cache.py` (`TtlCache`, `KeyedLocks`), `core/errors.py`.

## 4. Registrar

1. Em `src/ui_genai_mcp/toolsets/registry.py`, importe o módulo e inclua `<nome>.TOOLSET` em `ALL_TOOLSETS`.
2. Adicione as variáveis `<NOME>_*` e o nome em `ENABLED_TOOLSETS` no `.env.example` e na configuração do Container App.

## 5. Testar

- `tests/unit/toolsets/<nome>/`: domínio puro e adapters (`httpx.MockTransport`).
- `tests/integration/`: `Client(build_mcp(...))` em memória chamando cada tool (sucesso, não encontrado, erro mapeado).
- **Contrato**: `UPDATE_CONTRACTS=1 uv run pytest tests/contract` e revise o diff de `tests/contract/snapshots/tools.json` no PR.
- `uv run ruff check src tests && uv run mypy src && uv run pytest`.

## 6. Impacto no Foundry

- A **mesma connection MCP** passa a expor as novas tools automaticamente.
- Em cada agente: ajuste `allowed_tools` e `require_approval` (`never` para leitura; `always` para escrita).
- Atualize as instruções do agente (quando usar cada tool) e valide no playground antes de publicar.
- Se o toolset precisar de **nova permissão delegada** (Graph/outra API), isso exige alteração no app registration e possivelmente admin consent — sinalize cedo.
