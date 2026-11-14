# 01 — E6.0: base del servicio de IA

Fecha de creación: 2026-11-09  
Última actualización: 2026-11-09  
Estado: Implementado y verificado (2026-11-09). Sin commit: el repositorio está recién creado (`git init`, rama `main`) y los commits los pide el usuario.  
Relacionada con: [plan 01](../../../docs/plans/feature/base-del-servicio/01-plan-servicio-de-ia.md), [fuentes 01](../../../docs/fonts/feature/base-del-servicio/01-fuentes-de-la-base-del-servicio.md), [plan E6 de la API](../../../../LearningAllPosibolIt/docs/plans/feature/ai-assistant/01-plan-e6-ia-con-qdrant-y-llamaindex.md).

## Necesidad

Un servicio Python, ordenado como `HANDLE-BUSINESS/backend`, que arranque con su configuración, se conecte al Qdrant de desarrollo, diga si está sano y solo acepte llamadas de la API Nest. Es la base sobre la que E6.1 pondrá LlamaIndex.

## Evidencia → decisión → aplicación

| Evidencia | Decisión | Aplicación |
| --- | --- | --- |
| E1 (siete crates) | S1: siete subpaquetes con dependencias hacia abajo | `src/ktsu_ai/{domain,application,infrastructure,http,config,bootstrap,common}`; contratos en `pyproject.toml` (`[tool.importlinter]`) |
| E2–E4 (puertos `in_`/`out_`, un caso de uso por archivo, servicio fachada) | S2 | `health_ports/in_health_use_case.py`, `out_dependency_probe.py` (`Protocol`); `use_cases/check_health.py`; `health_service.py` |
| E5 (conexión y comprobación en infraestructura) | S6: arrancar aunque Qdrant falte | `infrastructure/database/qdrant/connection.py` y `health.py`; `bootstrap/resources/qdrant.py` solo informa |
| E6 (composición en bootstrap) | Solo `bootstrap` conoce infraestructura y rutas | `bootstrap/app.py` (`create_app`, `create_app_from_environment`, `main`), `bootstrap/services/health.py` |
| E7, E8 (rutas por feature, middleware, registros sin secretos) | S7, S8 | `http/health_http/routes.py`, `middleware/{internal_auth,errors,observability}.py`, `routes.py`, `http_server.py` |
| F1, F5 (versiones, Python 3.12) | S3 | `pyproject.toml` con versiones exactas, `.python-version`, `uv.lock` |
| Plan E6 D3 | S5 | `scripts/qdrant/qdrant.sh` y `Makefile` |

## Ajustes al escribir el código

- **Rutas montadas fuera del `lifespan`.** La primera versión montaba middleware y rutas al arrancar; Starlette no admite añadir middleware con la aplicación ya iniciada. El cliente se crea en `create_app` y el `lifespan` solo comprueba y cierra.
- **`check_compatibility=False` en el cliente de Qdrant.** Al ejecutar las pruebas apareció «Failed to obtain server version»: leyendo `qdrant_client/async_qdrant_remote.py` y `common/version_check.py`, el cliente hace un `httpx.get` **síncrono** al crearse, que con Qdrant caído bloquearía el arranque hasta el plazo (5 s). La misma regla (versión mayor igual, menor a ±1) la aplica ahora `QdrantProbe`, de forma asíncrona y en cada comprobación: un servidor incompatible cuenta como no disponible y deja su versión en la respuesta.
- **Plazo de Qdrant en segundos enteros:** el cliente solo admite `int` (lo detectó mypy).
- **`httpx` a nivel `WARNING`:** en el arranque real dejaba una línea por cada llamada a Qdrant.
- **Aviso de Starlette sobre `httpx2`:** se ignora en `pytest` con un comentario; se sigue con `httpx`, que también usa `qdrant-client`.
- **Sin `bootstrap/resources/qdrant.create`:** solo renombraba `create_client`.

## Implementación

- Rutas: `GET /health` (vivo, sin token) y `GET /v1/health` (token; 200 con `ready: true` o 503 con la dependencia `unavailable`).
- Errores con la forma de Nest: `{ code, message: { es, en }, requestId }`; códigos `AUTH_SERVICE_TOKEN_INVALID` (401), `VALIDATION_FAILED` (400), `ROUTE_NOT_FOUND` (404) y `INTERNAL_ERROR` (500).
- `X-Request-Id`: se respeta el de Nest si cumple su mismo patrón (`^[A-Za-z0-9._:-]{8,128}$`); si no, un UUID.
- Configuración: `AI_SERVICE_HOST`, `AI_SERVICE_PORT`, `AI_SERVICE_TOKEN` (obligatorio, 32+), `LOG_LEVEL`, `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_TIMEOUT_SECONDS` (`.env.example`).
- Se creó el `.env` local con un token generado (`secrets.token_urlsafe(32)`), con permisos 600 e ignorado por git. No se imprimió.

## Comprobaciones realmente ejecutadas

2026-11-09, Python 3.12.11, `uv` 0.12.1.

- `ruff check` y `ruff format --check`: limpios. `mypy --strict`: «no issues found in 40 source files». `lint-imports`: 2 contratos KEPT.
- `pytest`: **30 pasan** y 4 se saltan (las de Qdrant real).
- `make test-qdrant` (contenedor temporal `qdrant/qdrant:v1.19.1`, 2 CPU, 1 GiB, 127.0.0.1:56334): **4 de 4**, y el contenedor quedó parado.
- **Arranque real** con `make qdrant-up` y `uv run ktsu-ai`: «Qdrant 1.19.1 disponible»; `/health` 200; `/v1/health` sin token 401 con el cuerpo público; con token 200 `{"ready":true,…"version":"1.19.1"}` y `X-Request-Id: nest-arranque-real-01` devuelto; el token aparece 0 veces en el registro. Después, `make qdrant-down`.
- **Defectos a propósito** (copia en la carpeta temporal, uno cada vez, `pytest` e `import-linter`):

  | Defecto | Detectado por |
  | --- | --- |
  | El token acepta cualquier valor | pytest |
  | El token acepta uno más largo que empieza igual | pytest |
  | `/v1/health` 200 aunque Qdrant caiga | pytest |
  | El dominio importa la configuración | import-linter |
  | HTTP importa infraestructura | import-linter |
  | Se acepta cualquier `X-Request-Id` | pytest |
  | El registro incluye la query string | pytest |
  | Las comprobaciones de salud en serie | pytest |
  | Sin comprobar la compatibilidad de versión | pytest |
  | Se registra el mensaje del error de Qdrant (puede llevar la URL con clave) | pytest |
  | Se admite un token de 8 caracteres | pytest |
  | `QDRANT_API_KEY=` vacío se queda como clave | pytest |
  | Un 404 sin el cuerpo público | pytest |

  13 de 13 detectados.

## Consecuencias

- E6.1 añade LlamaIndex sobre esta base: el recurso Qdrant ya existe y `HealthService` admite más comprobaciones (el modelo de embeddings) sin tocar HTTP.
- La API Nest necesitará `AI_SERVICE_URL` y el mismo `AI_SERVICE_TOKEN` en E6.1; hoy no lo usa.
