"""Todo fichero parcheado tiene que estar en el Dockerfile.

Existe porque el 21-ago-2026 se desplego el registro de auditoria y NO
apuntaba nada: el Dockerfile solo copiaba uno de los dos ficheros. No fallo
nada, no hubo error, simplemente el codigo nuevo no estaba en la imagen.
Un fallo silencioso es el peor tipo de fallo.
"""
import pathlib, subprocess, sys

raiz = pathlib.Path(__file__).resolve().parent.parent
copiados = {l.split()[1] for l in (raiz/"Dockerfile").read_text().splitlines()
            if l.startswith("COPY")}
tocados = {f for f in subprocess.run(["git","diff","--name-only","main...HEAD"],
           cwd=raiz, capture_output=True, text=True).stdout.split()
           if f.startswith("auth/") and f.endswith(".py")}

faltan = tocados - copiados
for f in sorted(tocados):
    print(("  OK  " if f in copiados else "FALLO ") + f)
if faltan:
    print(f"\nFALTAN en el Dockerfile: {sorted(faltan)}")
    sys.exit(1)
print("\nTODO OK" if tocados else "\n(no hay ficheros parcheados)")
