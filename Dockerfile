# syntax=docker/dockerfile:1
#
# Imagen del servicio de IA (deploys, plan 06, D12).
#
#   docker build -t ktsu-ai .
#
# Dos etapas: en `build` se crea el entorno virtual con uv; `runtime` solo copia
# ese entorno. La imagen final no lleva uv, ni el código fuente suelto, ni las
# dependencias de desarrollo.

# Bases fijadas por versión y digest (deploys, fuentes 07, F5).
ARG PYTHON_IMAGE=python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.12.1@sha256:cf4eedcaa81655197f625739489effcbe71b61ceb1506f332c3facae5deceded

FROM ${UV_IMAGE} AS uv


# --- Construcción: el entorno virtual, desde `uv.lock` -----------------------
FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /usr/local/bin/uv
# Compilar a bytecode aquí: el usuario de ejecución no puede escribir `.pyc`.
ENV UV_COMPILE_BYTECODE=1
# Copiar en vez de enlazar: la caché de uv está en otro sistema de archivos.
ENV UV_LINK_MODE=copy
# Usar el Python de la imagen, el mismo que tendrá `runtime`.
ENV UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# Primero solo las dependencias: esta capa dura mientras no cambie `uv.lock`.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

# Después el paquete, instalado de verdad (no editable): el entorno no depende
# de que `src/` siga existiendo.
COPY README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable


# --- Ejecución ---------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS runtime
# Usuario sin privilegios, con carpeta propia para lo que escriban las librerías.
RUN useradd --create-home --uid 10001 ktsu
# Misma ruta que en `build`: el entorno virtual guarda rutas absolutas.
COPY --from=build /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:${PATH}
# En el contenedor se escucha en todas las interfaces (plan 02, fila FastAPI).
ENV AI_SERVICE_HOST=0.0.0.0
ENV AI_SERVICE_PORT=8090
# Los registros salen en cuanto se escriben, sin esperar a llenar un búfer.
ENV PYTHONUNBUFFERED=1
WORKDIR /home/ktsu
USER ktsu
EXPOSE 8090
# Forma exec: el servicio es el proceso 1 y recibe el SIGTERM del orquestador.
CMD ["ktsu-ai"]
