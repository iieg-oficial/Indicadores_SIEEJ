# Python 3.12, la misma que ETL-SIEEJ: los dos repositorios leen las mismas bases y no
# hay razón para divergir en el intérprete.
#
# Dos etapas. La de build se queda con pip, sus wheels y su caché; a la final solo pasa
# el venv ya resuelto, que es lo que mantiene la imagen chica y sin herramientas de
# compilación en producción.
FROM python:3.12-slim AS build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Solo lo que necesita `pip install`: así un cambio en `catalogo/` no reinstala nada.
COPY pyproject.toml ./
COPY src/ src/

# **Editable a propósito, y no es pereza.** `catalog.py` resuelve el catálogo como
# `Path(__file__).parents[2] / "catalogo"`, porque el catálogo vive en la raíz del
# repositorio y no junto al módulo. Con una instalación normal el paquete queda en
# site-packages y ese cálculo apunta adentro del venv. Con `-e` el paquete se importa
# desde `/app/src`, que es el mismo layout del repositorio, y `/app/catalogo` resuelve.
#
# Si alguien quita el `-e`, el contenedor no arranca y lo dice: «no existe el directorio
# del catálogo», con la ruta equivocada en el mensaje.
#
# uvicorn se instala aquí y no como dependencia del proyecto: el servidor que corre el
# app lo fija el despliegue, y en local llega por el extra `dev`.
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -e . uvicorn


FROM python:3.12-slim AS runtime

# Usuario sin privilegios, con UID fijo: un UID estable es lo que hace predecibles los
# permisos de cualquier volumen montado. El puerto es 8000 —por encima de 1024— justo
# para no necesitar root.
RUN useradd --system --uid 10001 --create-home --home-dir /home/banco banco

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY --from=build /opt/venv /opt/venv
COPY --chown=banco:banco src/ src/
COPY --chown=banco:banco catalogo/ catalogo/
COPY --chown=banco:banco migrations/ migrations/
COPY --chown=banco:banco alembic.ini pyproject.toml ./

USER banco
EXPOSE 8000

# **La imagen no lleva ninguna credencial.** Toda la configuración entra por variables
# de entorno en tiempo de ejecución; aquí no se fija ni un valor por defecto que pudiera
# convertirse en uno.

# `/health` es la única ruta anónima, así que la sonda no necesita credencial — y no
# abre ninguna conexión a base de datos, que es lo que la hace barata cada 30 s.
# Se usa urllib y no curl porque la imagen slim no trae curl y agregarlo por esto sería
# una capa entera por una petición.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]

# Sin `--reload` y sin `--workers`: el número de workers lo decide el despliegue, y con
# más de uno el caché de API keys y el límite por IP pasan a ser por worker. Está dicho
# en docs/api-keys.md.
CMD ["uvicorn", "indicadores_sieej.main:app", "--host", "0.0.0.0", "--port", "8000"]
