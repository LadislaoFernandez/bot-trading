"""Arma build/app (archivos del bot para el instalador) y dist/actualizacion.zip (para las actualizaciones de la app).

Solo entra el código: nunca estado, operaciones, registro, ajustes ni claves.
Uso: python installer/armar_zip.py
"""
import glob
import os
import shutil
import sys
import zipfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
import config as K  # noqa: E402

NO_VAN = {"cambiar_a_app.bat"}


def archivos():
    out = []
    for patron in ("*.py", "*.bat", "*.vbs", "*.ico", "*.ttf", "*.sh", "requirements.txt", "requirements_servidor.txt"):
        out += [os.path.basename(p) for p in glob.glob(os.path.join(RAIZ, patron))]
    out += ["estrategias/" + os.path.basename(p) for p in glob.glob(os.path.join(RAIZ, "estrategias", "*.json"))]
    return sorted(set(out) - NO_VAN)


def main():
    app, dist = os.path.join(RAIZ, "build", "app"), os.path.join(RAIZ, "dist")
    shutil.rmtree(app, ignore_errors=True)
    os.makedirs(app); os.makedirs(dist, exist_ok=True)
    lista = archivos()
    assert "app.py" in lista and "config.py" in lista
    zp = os.path.join(dist, "actualizacion.zip")
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for f in lista:
            os.makedirs(os.path.dirname(os.path.join(app, f)), exist_ok=True)
            shutil.copy2(os.path.join(RAIZ, f), os.path.join(app, f))
            z.write(os.path.join(RAIZ, f), f)
    # notas de la versión para la publicación
    v, fecha, cambios = K.HISTORIAL_VERSIONES[0]
    assert v == K.VERSION, f"HISTORIAL_VERSIONES empieza con {v} pero VERSION es {K.VERSION}"
    with open(os.path.join(RAIZ, "build", "notas.md"), "w", encoding="utf-8") as f:
        f.write(f"Versión {v} ({fecha})\n\n" + "\n".join(f"- {c}" for c in cambios) + "\n\n"
                "**Instalar desde cero:** bajá `BotTrading-Setup-" + v + ".exe` y abrilo.\n"
                "**Si ya tenés la app:** se actualiza sola desde Configuración → Actualizaciones.\n")
    with open(os.path.join(RAIZ, "build", "version.txt"), "w") as f:
        f.write(K.VERSION)
    print(f"{len(lista)} archivos, versión {K.VERSION}: {zp}")


if __name__ == "__main__":
    main()
