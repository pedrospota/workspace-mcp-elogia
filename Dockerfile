# Imagen oficial + los ficheros del parche. A proposito NO es un fork.
#
# Forkear 40.000 lineas de otro para tocar ~200 significa quedarse atras en
# dos meses. Subir de version = cambiar el tag de aqui abajo, reaplicar el
# parche (rama feat-brain vs main) y reconstruir. Ver README.
FROM ghcr.io/taylorwilsdon/google_workspace_mcp:1.25.0

# Los dos cambios:
#  - el proveedor OAuth entiende los tokens opacos del brain  (QUIEN eres)
#  - el middleware apunta cada llamada en el registro del brain (QUE hiciste)
#
# Si anades un fichero al parche, ACUERDATE DE ANADIRLO AQUI. El 21-ago-2026
# se desplego el registro sin esta segunda linea: no fallo nada, no hubo
# error, simplemente el codigo no estaba en la imagen y no apuntaba nada.
# Por eso existe pruebas/test_dockerfile.py.
COPY auth/external_oauth_provider.py /app/auth/external_oauth_provider.py
COPY auth/auth_info_middleware.py    /app/auth/auth_info_middleware.py
