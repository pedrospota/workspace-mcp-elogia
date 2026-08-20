# Imagen oficial + UN fichero cambiado. A proposito NO es un fork.
#
# Forkear 40.000 lineas de otro para tocar 109 significa quedarse atras en dos
# meses. Subir de version = cambiar el tag de aqui abajo, reaplicar el parche
# a ese fichero (rama feat-brain vs main) y reconstruir. Ver README.
FROM ghcr.io/taylorwilsdon/google_workspace_mcp:1.25.0

# El unico cambio: el proveedor OAuth entiende los tokens opacos del brain.
COPY auth/external_oauth_provider.py /app/auth/external_oauth_provider.py
