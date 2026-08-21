"""Prueba de la rama del brain. Un brain FALSO, sin red de verdad."""
import asyncio, importlib.util, os, sys, types
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pruebas.stubs import instalar
instalar()

os.environ.update({
    "BRAIN_ISSUER": "https://brain.servertoserver.io",
    "BRAIN_INTROSPECT_URL": "https://brain.servertoserver.io/api/mcp/oauth/introspect",
    "BRAIN_MCP_SECRET": "secreto-de-prueba",
    "WORKSPACE_MCP_RESOURCE": "https://workspacedatamx.servertoserver.io/mcp",
})

spec = importlib.util.spec_from_file_location("prov", "auth/external_oauth_provider.py")
prov = importlib.util.module_from_spec(spec); spec.loader.exec_module(prov)

RESPUESTAS = {}
class RespFalsa:
    def __init__(self, code, data): self.status_code, self._d = code, data
    def json(self): return self._d
class ClienteFalso:
    def __init__(self, **kw): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def post(self, url, headers=None, json=None):
        RESPUESTAS["peticion"] = {"url": url, "headers": headers, "json": json}
        r = RESPUESTAS["responder"]
        if isinstance(r, Exception): raise r
        return r
prov.httpx = types.SimpleNamespace(AsyncClient=ClienteFalso)
sys.modules["httpx"] = prov.httpx

p = prov.ExternalOAuthProvider(client_id="cid", client_secret="sec", required_scopes=["s1"])
fallos = []
def comprueba(nombre, cond, extra=""):
    print(("  OK  " if cond else "FALLO ") + nombre + ("" if cond else f"  <- {extra}"))
    if not cond: fallos.append(nombre)

# 1) camino feliz: token opaco -> se cambia por el de Google
RESPUESTAS["responder"] = RespFalsa(200, {"active": True, "email": "ana@elogia.net",
                                          "google_access_token": "ya29.EL-DE-ANA"})
t = asyncio.run(p.verify_token("brain-opaco-123"))
comprueba("token opaco -> token de Google de esa persona", getattr(t, "token", None) == "ya29.EL-DE-ANA", getattr(t,'token',None))
comprueba("la identidad viaja en claims.email", getattr(t, "claims", {}).get("email") == "ana@elogia.net")
pet = RESPUESTAS["peticion"]
comprueba("manda el secreto en Authorization", pet["headers"]["Authorization"] == "Bearer secreto-de-prueba")
comprueba("manda el resource (RFC 8707)", pet["json"].get("resource", "").endswith("/mcp"))
comprueba("NO manda el secreto en el cuerpo", "secreto" not in str(pet["json"]))

# 2) persona reconocida pero SIN permiso de Google -> se rechaza, no se cuela
RESPUESTAS["responder"] = RespFalsa(200, {"active": True, "email": "b@elogia.net",
                                          "motivo": "te falta Drive"})
comprueba("sin credencial de Google -> rechaza", asyncio.run(p.verify_token("x")) is None)

# 3) token no activo
RESPUESTAS["responder"] = RespFalsa(200, {"active": False})
comprueba("token no activo -> rechaza", asyncio.run(p.verify_token("x")) is None)

# 4) el brain nos rechaza el secreto
RESPUESTAS["responder"] = RespFalsa(401, {})
comprueba("brain devuelve 401 -> rechaza", asyncio.run(p.verify_token("x")) is None)

# 5) el brain esta caido -> NO se cuela nadie
RESPUESTAS["responder"] = RuntimeError("sin red")
comprueba("brain caido -> rechaza (falla cerrado)", asyncio.run(p.verify_token("x")) is None)

# 6) un ya29 NO pasa por el brain: lo sigue tratando el codigo de upstream
RESPUESTAS["responder"] = RespFalsa(200, {"active": True, "email": "z", "google_access_token": "NO-DEBERIA-USARSE"})
RESPUESTAS.pop("peticion", None)
t6 = asyncio.run(p.verify_token("ya29.loquesea"))
comprueba("un ya29.* NO pregunta al brain", "peticion" not in RESPUESTAS)
comprueba("un ya29.* lo resuelve upstream con userinfo",
          getattr(t6, "token", None) == "ya29.loquesea" and getattr(t6, "email", None) == "x@y",
          f"token={getattr(t6,'token',None)} email={getattr(t6,'email',None)}")

# 7) sin configurar el brain, todo se comporta como upstream
for k in ("BRAIN_INTROSPECT_URL", "BRAIN_MCP_SECRET"): os.environ.pop(k)
spec2 = importlib.util.spec_from_file_location("prov2", "auth/external_oauth_provider.py")
prov2 = importlib.util.module_from_spec(spec2); spec2.loader.exec_module(prov2)
comprueba("sin configurar -> brain desactivado", prov2.brain_configurado() is False)
p2 = prov2.ExternalOAuthProvider(client_id="c", client_secret="s", required_scopes=["s1"])
comprueba("sin configurar -> token opaco va a upstream", asyncio.run(p2.verify_token("opaco")) == "UPSTREAM")

print()
print("TODO OK" if not fallos else f"{len(fallos)} FALLO(S): {fallos}")
sys.exit(1 if fallos else 0)
