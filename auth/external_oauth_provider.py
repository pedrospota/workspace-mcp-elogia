"""
External OAuth Provider for Google Workspace MCP

Extends FastMCP's GoogleProvider to support external OAuth flows where
access tokens (ya29.*) are issued by external systems and need validation.

This provider acts as a Resource Server only - it validates tokens issued by
Google's Authorization Server but does not issue tokens itself.

=== PARCHE DE ELOGIA ===============================================
Anadido: soporte para el brain de Elogia como servidor de autorizacion.

El de arriba (upstream) espera que el Bearer SEA un token de Google. El brain
no manda tokens de Google al cliente: manda uno opaco suyo, y guarda el
refresh de Google. Asi, si le roban el disco a este MCP no se llevan el acceso
permanente de nadie, y despedir a alguien es borrar una fila en `user_tokens`.

Por eso aqui, cuando el Bearer NO empieza por `ya29.`, se le pregunta al brain
(RFC 7662) y se CAMBIA el token opaco por el de Google que devuelve. De ahi
para abajo el codigo de upstream no se entera: ve un token de Google normal.

Mismo patron que `ga4elo`. Se toca UN fichero a proposito: ver README.
====================================================================
"""

import functools
import logging
import os
import time
from typing import Optional

from starlette.routing import Route
from fastmcp.server.auth.providers.google import GoogleProvider
from fastmcp.server.auth import AccessToken
from google.oauth2.credentials import Credentials

from auth.oauth_types import WorkspaceAccessToken

logger = logging.getLogger(__name__)

# Google's OAuth 2.0 Authorization Server
GOOGLE_ISSUER_URL = "https://accounts.google.com"

# --- PARCHE ELOGIA: el brain como servidor de autorizacion ---------------
BRAIN_ISSUER = os.getenv("BRAIN_ISSUER", "").rstrip("/")
BRAIN_INTROSPECT_URL = os.getenv("BRAIN_INTROSPECT_URL", "")
BRAIN_MCP_SECRET = os.getenv("BRAIN_MCP_SECRET", "")
BRAIN_RESOURCE = os.getenv("WORKSPACE_MCP_RESOURCE", "")
BRAIN_RESOURCE_NAME = os.getenv(
    "BRAIN_RESOURCE_NAME", "Google Workspace de Elogia - cada quien entra con su propio Google"
)
# Cuanto damos por bueno el token de Google que nos da el brain.
#
# Corto A PROPOSITO. El brain nos entrega un token de Google que ya puede
# llevar rato vivo — no nos dice cuanto le queda, y los de Google duran ~1h.
# Si aqui estampamos SESSION_TIME (hasta 24h), acabariamos usando un token
# muerto y devolviendo 401 sin poder renovarlo. Con 5 minutos, lo peor que
# pasa es una llamada de mas al introspect, que ademas es la que deja rastro
# en el registro del brain. Barato y honesto.
BRAIN_TOKEN_TTL_S = int(os.getenv("BRAIN_TOKEN_TTL_S", "300"))


def brain_configurado() -> bool:
    """Sin las dos piezas no se activa nada: se cae al comportamiento de upstream."""
    return bool(BRAIN_INTROSPECT_URL and BRAIN_MCP_SECRET)


async def introspectar_en_el_brain(token: str) -> Optional[dict]:
    """Cambia el token opaco del brain por el token de Google de esa persona.

    Devuelve el JSON del brain, o None si no se pudo preguntar. Un fallo de red
    NO se confunde con un token invalido: se distingue arriba.
    """
    import httpx

    cuerpo = {"token": token}
    if BRAIN_RESOURCE:
        cuerpo["resource"] = BRAIN_RESOURCE
    try:
        async with httpx.AsyncClient(timeout=10.0) as cli:
            r = await cli.post(
                BRAIN_INTROSPECT_URL,
                headers={"Authorization": f"Bearer {BRAIN_MCP_SECRET}"},
                json=cuerpo,
            )
        if r.status_code == 401:
            logger.error(
                "brain: nos rechaza el secreto (401). Revisa BRAIN_MCP_SECRET "
                "contra MCP_SERVICE_SECRET/CRON_SECRET del brain."
            )
            return None
        if r.status_code >= 400:
            logger.error("brain: introspect devolvio %s", r.status_code)
            return None
        return r.json()
    except Exception as exc:
        logger.error("brain: no se pudo preguntar al introspect: %s", exc)
        return None
# ------------------------------------------------------------------------

# Configurable session time in seconds (default: 1 hour, max: 24 hours)
_DEFAULT_SESSION_TIME = 3600
_MAX_SESSION_TIME = 86400


@functools.lru_cache(maxsize=1)
def get_session_time() -> int:
    """Parse SESSION_TIME from environment with fallback, min/max clamp.

    Result is cached; changes require a server restart.
    """
    raw = os.getenv("SESSION_TIME", "")
    if not raw:
        return _DEFAULT_SESSION_TIME
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "Invalid SESSION_TIME=%r, falling back to %d", raw, _DEFAULT_SESSION_TIME
        )
        return _DEFAULT_SESSION_TIME
    clamped = max(1, min(value, _MAX_SESSION_TIME))
    if clamped != value:
        logger.warning(
            "SESSION_TIME=%d clamped to %d (allowed range: 1–%d)",
            value,
            clamped,
            _MAX_SESSION_TIME,
        )
    return clamped


class ExternalOAuthProvider(GoogleProvider):
    """
    Extended GoogleProvider that supports validating external Google OAuth access tokens.

    This provider handles ya29.* access tokens by calling Google's userinfo API,
    while maintaining compatibility with standard JWT ID tokens.

    Unlike the standard GoogleProvider, this acts as a Resource Server only:
    - Does NOT create /authorize, /token, /register endpoints
    - Only advertises Google's authorization server in metadata
    - Only validates tokens, does not issue them
    """

    def __init__(
        self,
        client_id: str,
        client_secret: Optional[str] = None,
        resource_server_url: Optional[str] = None,
        **kwargs,
    ):
        """Initialize and store client credentials for token validation."""
        self._resource_server_url = resource_server_url
        if resource_server_url and "resource_base_url" not in kwargs:
            kwargs["resource_base_url"] = resource_server_url
        super().__init__(client_id=client_id, client_secret=client_secret, **kwargs)
        # Store credentials as they're not exposed by parent class
        self._client_id = client_id
        self._client_secret = client_secret
        # Store as string - Pydantic validates it when passed to models
        self.resource_server_url = self._resource_server_url

    async def verify_token(self, token: str) -> Optional[AccessToken]:
        """
        Verify a token - supports both JWT ID tokens and ya29.* access tokens.

        For ya29.* access tokens (issued externally), validates by calling
        Google's userinfo API. For JWT tokens, delegates to parent class.

        Args:
            token: Token string to verify (JWT or ya29.* access token)

        Returns:
            AccessToken object if valid, None otherwise
        """
        # PARCHE ELOGIA: token opaco del brain -> se cambia por el de Google.
        # Va ANTES del ya29 a proposito: un ya29 sigue funcionando igual, para
        # no romper el modo de upstream ni las pruebas.
        if brain_configurado() and not token.startswith("ya29."):
            datos = await introspectar_en_el_brain(token)
            if datos is None:
                # No se pudo PREGUNTAR (red, 5xx, secreto malo). No es lo mismo
                # que "este token no vale": se rechaza igual, pero el log dice
                # cual de las dos cosas fue, que es lo que se busca a las 3am.
                return None
            if not datos.get("active"):
                logger.info("brain: token no activo (%s)", datos.get("error") or "sin motivo")
                return None
            google_token = datos.get("google_access_token")
            if not google_token:
                # El brain SI reconocio a la persona, pero le falta el permiso
                # de Google. Eso no es un fallo del MCP y se dice con palabras.
                logger.warning(
                    "brain: %s identificado pero sin credencial de Google: %s",
                    datos.get("email"), datos.get("motivo") or "sin motivo",
                )
                return None

            email = datos.get("email")
            logger.info("brain: validado %s", email)
            return WorkspaceAccessToken(
                token=google_token,          # <- de aqui abajo, un token de Google normal
                scopes=list(getattr(self, "required_scopes", []) or []),
                expires_at=int(time.time()) + min(BRAIN_TOKEN_TTL_S, get_session_time()),
                claims={"email": email},
                client_id=self._client_id,
                email=email,
                sub=email,
            )

        # For ya29.* access tokens, validate using Google's userinfo API
        if token.startswith("ya29."):
            logger.debug("Validating external Google OAuth access token")

            try:
                from auth.google_auth import get_user_info

                # Create minimal Credentials object for userinfo API call
                credentials = Credentials(
                    token=token,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=self._client_id,
                    client_secret=self._client_secret,
                )

                # Validate token by calling userinfo API
                user_info = get_user_info(credentials, skip_valid_check=True)

                if user_info and user_info.get("email"):
                    session_time = get_session_time()
                    # Token is valid - create AccessToken object
                    logger.info(
                        f"Validated external access token for: {user_info['email']}"
                    )

                    scope_list = list(getattr(self, "required_scopes", []) or [])
                    access_token = WorkspaceAccessToken(
                        token=token,
                        scopes=scope_list,
                        expires_at=int(time.time()) + session_time,
                        claims={
                            "email": user_info["email"],
                            "sub": user_info.get("id"),
                        },
                        client_id=self._client_id,
                        email=user_info["email"],
                        sub=user_info.get("id"),
                    )
                    return access_token
                else:
                    logger.error("Could not get user info from access token")
                    return None

            except Exception as e:
                logger.error(f"Error validating external access token: {e}")
                return None

        # For JWT tokens, use parent class implementation
        return await super().verify_token(token)

    def get_routes(self, mcp_path: str | None = None) -> list[Route]:
        """
        Get OAuth routes for external provider mode.

        Returns only protected resource metadata routes that point to Google
        as the authorization server. Does not create authorization server routes
        (/authorize, /token, etc.) since tokens are issued by Google directly.

        Args:
            mcp_path: Path where FastMCP mounts the protected MCP endpoint.

        Returns:
            List of routes - only protected resource metadata
        """
        from mcp.server.auth.routes import create_protected_resource_routes

        if not self.resource_server_url:
            logger.warning(
                "ExternalOAuthProvider: resource_server_url not set, no routes created"
            )
            return []

        self.set_mcp_path(mcp_path)
        resource_url = self._get_resource_url(mcp_path)
        if not resource_url:
            logger.warning(
                "ExternalOAuthProvider: protected resource URL could not be resolved"
            )
            return []

        # PARCHE ELOGIA: si el brain esta configurado, el servidor de
        # autorizacion es EL BRAIN, no Google. Esto es lo que hace que Claude
        # mande a la persona al login de Elogia (y por tanto al candado
        # @elogia.net) en vez de directamente a Google.
        emisor = BRAIN_ISSUER if (brain_configurado() and BRAIN_ISSUER) else GOOGLE_ISSUER_URL
        nombre = BRAIN_RESOURCE_NAME if emisor != GOOGLE_ISSUER_URL else "Google Workspace MCP"

        # Create protected resource routes that point at the authorization server
        # Pass strings directly - Pydantic validates them during model construction
        protected_routes = create_protected_resource_routes(
            resource_url=resource_url,
            authorization_servers=[emisor],
            scopes_supported=self.required_scopes,
            resource_name=nombre,
            resource_documentation=None,
        )

        logger.info(
            f"ExternalOAuthProvider: Created protected resource routes pointing to {emisor}"
        )
        return protected_routes
