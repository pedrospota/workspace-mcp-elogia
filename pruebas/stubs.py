"""Postizos minimos para poder importar el proveedor sin instalar fastmcp/google."""
import sys, types

class _Creds:
    def __init__(self, **kw):
        for k, v in kw.items(): setattr(self, k, v)


def instalar():
    # fastmcp.server.auth.providers.google.GoogleProvider
    class GoogleProvider:
        def __init__(self, **kw):
            self._client_id = kw.get("client_id", "cid")
            self._client_secret = kw.get("client_secret", "sec")
            self.required_scopes = kw.get("required_scopes", ["scope-a"])
            self.resource_server_url = kw.get("resource_server_url")
        async def verify_token(self, token):
            return "UPSTREAM"          # marcador: se fue por el camino de upstream
        def set_mcp_path(self, p): pass
        def _get_resource_url(self, p): return "https://x/mcp"
    class AccessToken:
        def __init__(self, **kw):
            for k, v in kw.items(): setattr(self, k, v)

    for nombre, attrs in {
        "fastmcp": {}, "fastmcp.server": {}, "fastmcp.server.auth": {"AccessToken": AccessToken},
        "fastmcp.server.auth.providers": {},
        "fastmcp.server.auth.providers.google": {"GoogleProvider": GoogleProvider},
        "starlette": {}, "starlette.routing": {"Route": object},
        "google": {}, "google.oauth2": {},
        "google.oauth2.credentials": {"Credentials": _Creds},
        "mcp": {}, "mcp.server": {}, "mcp.server.auth": {},
        "mcp.server.auth.routes": {"create_protected_resource_routes": lambda **kw: [kw]},
        "auth": {}, "auth.google_auth": {"get_user_info": lambda *a, **k: {"email": "x@y", "id": "1"}},
    }.items():
        m = types.ModuleType(nombre)
        for k, v in attrs.items(): setattr(m, k, v)
        sys.modules[nombre] = m

    ot = types.ModuleType("auth.oauth_types")
    class WorkspaceAccessToken(AccessToken): pass
    ot.WorkspaceAccessToken = WorkspaceAccessToken
    sys.modules["auth.oauth_types"] = ot
    return GoogleProvider, WorkspaceAccessToken
