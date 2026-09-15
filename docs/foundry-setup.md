# Configuração no Azure e no Microsoft Foundry

## 1. App registration existente (sem criar novo)
Verificar (somente leitura):
- **Expose an API**: Application ID URI `api://{client_id}` e o nome do scope exposto (→ `MCP_REQUIRED_SCOPE`, padrão `access_as_user`).
- **Manifest** `requestedAccessTokenVersion` (define token v1 ou v2 — ambos são aceitos).
- **API permissions**: permissão **delegada** do Microsoft Graph para ler o site (ex.: `Sites.Read.All`) com consentimento já concedido; `User.Read` para a sonda `/me`.
- **Client secret**: validade.

Única alteração: após criar a connection no Foundry, adicionar a **redirect URL** gerada em *Authentication → Web → Redirect URIs*.

## 2. Container App
```bash
az acr build -r <acr> -t ui-genai-mcp:<tag> .
az containerapp create -n ui-genai-mcp -g <rg> --environment <env> \
  --image <acr>.azurecr.io/ui-genai-mcp:<tag> --registry-server <acr>.azurecr.io \
  --ingress external --target-port 8000 --min-replicas 1 --max-replicas 3 \
  --secrets azure-ad-client-secret=<valor-ou-keyvaultref> \
  --env-vars ENVIRONMENT=dev AUTH_ENABLED=true \
    AZURE_AD_TENANT_ID=<tid> AZURE_AD_CLIENT_ID=<cid> AZURE_AD_CLIENT_SECRET=secretref:azure-ad-client-secret \
    PUBLIC_BASE_URL=https://<fqdn> ALLOWED_HOSTS=<fqdn> ENABLED_TOOLSETS=diagnostico
```
- Probes: liveness `/healthz`, readiness `/readyz`.
- Sem EasyAuth (quebraria o 401 + Protected Resource Metadata).
- `PUBLIC_BASE_URL`/`ALLOWED_HOSTS` precisam do FQDN real (senão 421 / metadata errado).

Verificação rápida:
```bash
curl https://<fqdn>/healthz
curl -i -X POST https://<fqdn>/mcp          # 401 + WWW-Authenticate com resource_metadata
curl https://<fqdn>/.well-known/oauth-protected-resource/mcp
```

## 3. Connection MCP no Foundry
*Tools → Custom → Model Context Protocol → OAuth Identity Passthrough → Custom OAuth*

| Campo | Valor |
|---|---|
| Endpoint | `https://<fqdn>/mcp` |
| Client ID / Secret | do app registration existente |
| Auth URL | `https://login.microsoftonline.com/<tid>/oauth2/v2.0/authorize` |
| Token URL | `https://login.microsoftonline.com/<tid>/oauth2/v2.0/token` |
| Refresh URL | igual ao Token URL |
| Scopes | `api://<cid>/access_as_user offline_access` (separados por **um espaço**) |

Não usar *managed OAuth* com audiência Microsoft (o Foundry bloqueia: "Cannot pass Microsoft token to untrusted MCP endpoint").

## 4. Agente
- Tool MCP: `server_label=ui_genai_mcp`, `project_connection_id=<connection>`, `allowed_tools=[...]`, `require_approval="never"` (tools somente leitura).
- Usuários: role **Foundry Agent Consumer** no projeto (mesmo tenant).
- Publicar inicialmente para "Just you" durante o spike.
