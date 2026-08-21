"""El registro en el brain: que apunte lo justo y que NUNCA rompa la llamada."""
import asyncio, importlib.util, os, sys, types
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.update({"BRAIN_AUDIT_URL":"https://brain.test/api/mcp/audit","BRAIN_MCP_SECRET":"sec-prueba"})

# postizos justos para importar el middleware
def mod(n, **kw):
    m=types.ModuleType(n); [setattr(m,k,v) for k,v in kw.items()]; sys.modules[n]=m; return m
class _Ctx: pass
mod("fastmcp"); mod("fastmcp.server")
mod("fastmcp.server.dependencies", get_access_token=lambda: None, get_http_headers=lambda: {})
mod("fastmcp.server.middleware", Middleware=object, MiddlewareContext=object)
mod("auth"); mod("auth.external_oauth_provider", get_session_time=lambda: 3600)
class GIE(Exception): pass
mod("auth.gateway_identity", GatewayIdentityError=GIE, extract_email_from_assertion=lambda *a: None)
mod("auth.oauth21_session_store", ensure_session_from_access_token=lambda *a: None, get_oauth21_session_store=lambda: None)
mod("auth.oauth_config", get_oauth_config=lambda: None, is_trust_gateway_identity=lambda: False)
mod("auth.oauth_types", WorkspaceAccessToken=object)
class RI:
    def __init__(s,e,v): s.email, s.via = e, v
async def _gri(ctx=None): return RI("ana@elogia.net","oauth")
mod("auth.request_identity", get_request_identity=_gri, reset_request_identity=lambda *a: None,
    set_request_identity=lambda *a, **k: None)

spec=importlib.util.spec_from_file_location("mw","auth/auth_info_middleware.py")
mw=importlib.util.module_from_spec(spec); spec.loader.exec_module(mw)

ENVIADO={}
class Resp:
    def __init__(s,c): s.status_code=c
class Cli:
    def __init__(s,**k): pass
    async def __aenter__(s): return s
    async def __aexit__(s,*a): return False
    async def post(s,url,headers=None,json=None):
        ENVIADO["url"], ENVIADO["headers"], ENVIADO["json"] = url, headers, json
        if isinstance(ENVIADO.get("responder"), Exception): raise ENVIADO["responder"]
        return Resp(ENVIADO.get("responder", 200))
mw.httpx = types.SimpleNamespace(AsyncClient=Cli); sys.modules["httpx"]=mw.httpx

fallos=[]
def ok(n,c,extra=""):
    print(("  OK  " if c else "FALLO ")+n+("" if c else f"  <- {extra}")); c or fallos.append(n)

class Msg:
    def __init__(s,n,a): s.name, s.arguments = n, a
class Ctx2:
    def __init__(s,n,a): s.message, s.fastmcp_context = Msg(n,a), _Ctx()

m = mw.AuthInfoMiddleware()
m._process_request_for_auth = lambda c: asyncio.sleep(0)

# 1) llamada correcta -> se apunta
async def sigue(c): return "resultado"
r = asyncio.run(m.on_call_tool(Ctx2("search_gmail_messages", {"query":"factura","body":"TEXTO SECRETO DEL CORREO"}), sigue))
ok("la herramienta sigue devolviendo lo suyo", r == "resultado")
j = ENVIADO["json"]
ok("apunta la herramienta", j["tool"] == "search_gmail_messages")
ok("apunta QUIEN, sacado de la identidad", j["user_email"] == "ana@elogia.net")
ok("apunta ok=True", j["ok"] is True)
ok("mide el tiempo", isinstance(j["ms"], int))
ok("manda el secreto en la cabecera", ENVIADO["headers"]["Authorization"] == "Bearer sec-prueba")
ok("guarda los argumentos utiles", j["args"]["query"] == "factura")
ok("NO manda el contenido del correo", j["args"]["body"] == "(omitido)", j["args"])
ok("el secreto NO viaja en el cuerpo", "sec-prueba" not in str(j))

# 2) si la herramienta falla, tambien se apunta
async def revienta(c): raise RuntimeError("google dijo 403")
try: asyncio.run(m.on_call_tool(Ctx2("send_gmail_message", {"to":"x@y"}), revienta))
except RuntimeError: pass
ok("un fallo tambien queda apuntado", ENVIADO["json"]["ok"] is False)
ok("y con el motivo", "403" in (ENVIADO["json"].get("detalle") or ""))

# 3) si el BRAIN esta caido, la herramienta NO se rompe
ENVIADO["responder"] = RuntimeError("brain caido")
r = asyncio.run(m.on_call_tool(Ctx2("search_gmail_messages", {"query":"x"}), sigue))
ok("brain caido -> la herramienta responde igual", r == "resultado")
ENVIADO["responder"] = 500
r = asyncio.run(m.on_call_tool(Ctx2("search_gmail_messages", {"query":"x"}), sigue))
ok("brain devuelve 500 -> la herramienta responde igual", r == "resultado")

# 4) sin configurar, no se manda nada
ENVIADO.clear()
for k in ("BRAIN_AUDIT_URL","BRAIN_MCP_SECRET"): os.environ.pop(k)
sp=importlib.util.spec_from_file_location("mw2","auth/auth_info_middleware.py")
mw2=importlib.util.module_from_spec(sp); sp.loader.exec_module(mw2); mw2.httpx=mw.httpx
m2=mw2.AuthInfoMiddleware(); m2._process_request_for_auth = lambda c: asyncio.sleep(0)
r = asyncio.run(m2.on_call_tool(Ctx2("t", {}), sigue))
ok("sin configurar -> no se manda nada", "json" not in ENVIADO and r == "resultado")

print(); print("TODO OK" if not fallos else f"{len(fallos)} FALLO(S): {fallos}")
sys.exit(1 if fallos else 0)
