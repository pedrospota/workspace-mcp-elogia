# workspace-mcp-elogia

El MCP de Google Workspace de Elogia, colgado del **brain** — igual que `ga4elo`.

**Esto NO es un fork.** Es la imagen oficial de
[`taylorwilsdon/google_workspace_mcp`](https://github.com/taylorwilsdon/google_workspace_mcp)
con **un solo fichero cambiado**. Forkear 40.000 líneas de otro para tocar 105 significa
quedarse atrás en dos meses.

## Qué cambia y por qué

Upstream, en modo proveedor externo, espera que el Bearer **sea** un token de Google
(`ya29.*`). El brain no manda tokens de Google al cliente: manda uno **opaco suyo** y se
queda el refresh de Google.

Eso importa por dos cosas:

- Si le roban el disco a este MCP, **no se llevan el acceso permanente de nadie**.
- Alguien se va de Elogia → se borra su fila en `user_tokens` del brain y **se le cae
  este MCP, GA4 y todo lo que venga después**, de golpe.

Es justo el modelo contrario al que se cayó el 18-ago-2026 (un refresh token de una sola
cuenta pegado a mano en un `.env`).

El parche, en `auth/external_oauth_provider.py`: cuando el Bearer **no** empieza por
`ya29.`, se le pregunta al brain (RFC 7662) y **se cambia el token opaco por el de Google**
que devuelve. De ahí para abajo, el código de upstream no se entera.

Y el `.well-known` pasa a decir que el servidor de autorización es **el brain**, no
Google. Eso es lo que manda a la persona al login de Elogia — y por tanto al candado
`@elogia.net` que vive en `src/lib/auth.ts` del brain.

## Variables de entorno

| Variable | Para qué |
|---|---|
| `MCP_ENABLE_OAUTH21=true` | obligatoria |
| `EXTERNAL_OAUTH21_PROVIDER=true` | activa el modo *resource server* |
| `BRAIN_ISSUER` | `https://brain.servertoserver.io` |
| `BRAIN_INTROSPECT_URL` | `https://brain.servertoserver.io/api/mcp/oauth/introspect` |
| `BRAIN_MCP_SECRET` | = `MCP_SERVICE_SECRET` (o `CRON_SECRET`) del brain |
| `WORKSPACE_MCP_RESOURCE` | `https://workspacedatamx.servertoserver.io/mcp` |
| `GOOGLE_OAUTH_CLIENT_ID` / `_SECRET` | los de siempre |
| `GOOGLE_MCP_CREDENTIALS_DIR` | `/app/store_creds/credentials` (volumen persistente) |

**Sin `BRAIN_INTROSPECT_URL` y `BRAIN_MCP_SECRET` el parche no se activa** y todo se
comporta exactamente como upstream. Eso es a propósito: se puede desplegar y volver atrás
quitando dos variables, sin reconstruir.

## Cómo subir de versión (la parte que se olvida)

```bash
# 1. mira qué versión hay
curl -s https://api.github.com/repos/taylorwilsdon/google_workspace_mcp/releases/latest | jq -r .tag_name

# 2. saca el fichero NUEVO de upstream
git clone --depth 1 -b <tag> https://github.com/taylorwilsdon/google_workspace_mcp /tmp/up

# 3. reaplica el parche sobre ESE fichero (los bloques van marcados "PARCHE ELOGIA")
#    y compara con el nuestro para no perder nada
diff /tmp/up/auth/external_oauth_provider.py auth/external_oauth_provider.py

# 4. cambia el FROM del Dockerfile al tag nuevo
# 5. pasa las pruebas ANTES de desplegar
python3 pruebas/test_brain.py
```

## Pruebas

```bash
python3 pruebas/test_brain.py
```

13 comprobaciones con un brain falso, sin red: camino feliz, persona sin permiso de
Google, token no activo, secreto rechazado, **brain caído (falla cerrado, no se cuela
nadie)**, y que un `ya29.*` siga yendo por el camino de upstream.

## La otra mitad

El lado del brain va en `pedrospota/elogia-kb-manager`, rama
`feat-workspace-mcp-en-brain`: registra este recurso, dice qué permiso de Google necesita
y añade su ficha a la pantalla de consentimiento.
