# 01 — Servicio de IA: arquitectura, configuración y base (E6.0)

Fecha de creación: 2026-11-09  
Última actualización: 2026-11-09  
Estado: En curso. E6.0 y E6.1a hechas y verificadas (2026-11-09).  
Ámbito: `claudeLearningAllPosibolIt-ai`. Las etapas que tocan también la API están en el [plan E6](../../../../../claudeLearningAllPosibolIt/docs/plans/feature/ai-assistant/01-plan-e6-ia-con-qdrant-y-llamaindex.md).  
Relacionada con: [fuentes 01](../../../fonts/feature/base-del-servicio/01-fuentes-de-la-base-del-servicio.md), [revisión 02 de LlamaIndex](../../../../../claudeLearningAllPosibolIt/docs/fonts/feature/ai-assistant/02-revision-de-llamaindex-para-la-api.md).

## Qué es este servicio

El «cerebro» de la IA de KTSU. Con LlamaIndex indexa en Qdrant lo que Nest le manda, busca con el filtro de la organización y, desde E6.3, ejecuta el agente. No tiene base de datos propia ni es público: solo lo llama la API Nest, que es quien conoce a la persona y sus permisos.

## Decisiones

| ID | Decisión | Respaldo |
| --- | --- | --- |
| S1 | **Siete capas como subpaquetes de `ktsu_ai`**, igual que los crates de `HANDLE-BUSINESS/backend`. Dependencias en una sola dirección: `domain` ← `application` ← (`infrastructure`, `http`) ← `bootstrap`; `config` y `common` los puede usar cualquiera menos `domain`. `import-linter` lo comprueba en cada verificación. | E1, E6 |
| S2 | **Por feature dentro de cada capa**, con los nombres de la referencia: `application/<feature>_application/` (DTO `dto_input_…`/`dto_output_…`, `use_cases/`, `<feature>_service.py`) y `application/<feature>_ports/` (`in_…` y `out_…` como `typing.Protocol`); `infrastructure/<feature>_infrastructure/` y `infrastructure/database/qdrant/`; `http/<feature>_http/routes.py` + `dto/`. El dominio son `@dataclass(frozen=True)` sin dependencias de fuera; Pydantic solo en `http` y `config`. | E2–E4, E7 |
| S3 | **Python 3.12 con `uv` y FastAPI** como framework HTTP (rutas con `APIRouter` por feature, protección con dependencias, middleware para registros e identificador, todo asíncrono). `.python-version`, `uv.lock` versionado y dependencias exactas. Base: `fastapi`, `uvicorn`, `pydantic-settings`, `qdrant-client` 1.19.1. LlamaIndex entra en E6.1 con solo los paquetes que se usen. Desarrollo: `pytest`, `httpx`, `ruff`, `mypy` estricto e `import-linter`. | F1, F5, C5; FastAPI: C6–C11 |
| S4 | **Configuración por entorno**, leída una vez al arrancar con `pydantic-settings` (las variables del proceso ganan a `.env`); el `.env` real no se versiona y `.env.example` documenta todo. Secretos como `SecretStr`: nunca salen en registros ni en errores. | E8 |
| S5 | **Qdrant de desarrollo** (`make qdrant-up` / `make qdrant-down`): contenedor `estadistica-forms-qdrant` de la imagen local `qdrant/qdrant:v1.19.1`, `--cpus 2 --memory 1g`, solo en `127.0.0.1:56333`, volumen `estadistica-forms-qdrant-data`. Pruebas contra Qdrant real (`make test-qdrant`): contenedor temporal sin volumen en `127.0.0.1:56334` que se para siempre al terminar; la batería normal las salta. | Plan E6 D3, D11 |
| S6 | **Dos rutas de estado:** `GET /health` (vivo, sin token ni datos, para el orquestador) y `GET /v1/health` (con token: estado de Qdrant y versión del servidor). Si Qdrant no responde, el servicio arranca igual y `/v1/health` responde 503 con `qdrant: unavailable`: Nest lo verá como «IA no disponible», no como API caída. | E5, plan E6 D7 |
| S7 | **Autenticación interna:** toda ruta `/v1/…` exige `Authorization: Bearer <AI_SERVICE_TOKEN>`, comparado en tiempo constante (`hmac.compare_digest`). Sin token configurado el servicio no arranca. En Cloud Run se cambiará por identidad de servicio (E6.6). | Plan E6 D6 |
| S8 | **Errores y registros como la API Nest:** cuerpo `{ code, message: { es, en }, requestId }`, cabecera `X-Request-Id` (se respeta la que manda Nest si es válida) y una línea por petición con método, ruta, estado y duración; nunca tokens, cuerpos ni query strings. | E8; API Nest |

## Árbol

```text
claudeLearningAllPosibolIt-ai/
├── pyproject.toml            dependencias, ruff, mypy, pytest e import-linter
├── uv.lock · .python-version · .env.example · Makefile · README.md
├── src/ktsu_ai/
│   ├── domain/               reglas puras (health/ en E6.0; access/ y knowledge/ en E6.1)
│   ├── application/
│   │   ├── health_application/   dto_output_service_health.py, use_cases/check_health.py, health_service.py
│   │   └── health_ports/         in_health_use_case.py, out_dependency_probe.py
│   ├── infrastructure/
│   │   └── database/qdrant/      connection.py, health.py
│   ├── http/
│   │   ├── health_http/          routes.py, dto/
│   │   ├── middleware/           internal_auth.py, errors.py, observability.py
│   │   ├── routes.py             composición
│   │   └── http_server.py        uvicorn
│   ├── config/                   configuration.py, loader.py
│   ├── bootstrap/                app.py, resources/qdrant.py, services/health.py
│   └── common/                   error.py, messages.py
├── tests/ unit · http · integration (Qdrant real)
├── docs/fonts · docs/plans · bitacora-construccion/
└── scripts/qdrant/           arrancar y parar los contenedores
```

## Configuración

| Variable | Desarrollo | Para qué |
| --- | --- | --- |
| `AI_SERVICE_HOST` | `127.0.0.1` | Solo local: nadie de la red lo alcanza. |
| `AI_SERVICE_PORT` | `8090` | Puerto del servicio. |
| `AI_SERVICE_TOKEN` | 32+ caracteres aleatorios (`make token`) | Lo comparte con Nest (`AI_SERVICE_TOKEN` en su `.env`). Obligatorio. |
| `QDRANT_URL` | `http://127.0.0.1:56333` | Qdrant de desarrollo (S5). |
| `QDRANT_API_KEY` | vacío | Solo para un Qdrant remoto. |
| `QDRANT_TIMEOUT_SECONDS` | `5` | Para no colgar una petición si Qdrant no responde. |
| `LOG_LEVEL` | `INFO` | Nivel de registro. |
| `KNOWLEDGE_COLLECTION` | `ktsu_knowledge` | Colección de Qdrant con el conocimiento de todas las organizaciones. |
| `GOOGLE_CLOUD_PROJECT` | `estadistica-forms-api` | Obligatorio: el proyecto por defecto de `gcloud` puede ser otro. |
| `GOOGLE_CLOUD_LOCATION` | `us-central1` | Región de Vertex AI. |
| `EMBEDDING_MODEL` | `gemini-embedding-001` | Modelo de embeddings de Google. |
| `EMBEDDING_DIMENSIONS` | `768` | Cambiarlo obliga a reindexar. |
| `EMBEDDING_BATCH_SIZE` | `32` | Textos por petición (medido con Vertex). |
| `EMBEDDING_CONCURRENCY` | `4` | Peticiones a Google a la vez; sin él, LlamaIndex las lanza todas juntas. |
| `EMBEDDING_TIMEOUT_SECONDS` | `60` | Plazo de cada llamada a Google. |

En la API Nest (E6.1): `AI_SERVICE_URL=http://127.0.0.1:8090` y el mismo `AI_SERVICE_TOKEN`.

## Comandos

```bash
make install      # uv sync con el lock
make qdrant-up    # Qdrant de desarrollo (un contenedor limitado)
make dev          # servicio con recarga en 127.0.0.1:8090
make check        # ruff, formato, mypy, import-linter y pytest
make test-qdrant  # pruebas contra un Qdrant temporal
make test-google  # pruebas contra Vertex AI con textos inventados (no gratis)
make qdrant-down  # parar Qdrant al terminar
```

## Etapas de este repositorio

1. ✅ **E6.0 — Base** (S1–S8), [bitácora 01](../../../../bitacora-construccion/feature/base-del-servicio/01-base-del-servicio.md). *Ajustado en E6.0:* `check_compatibility=False` en el cliente y la regla de versiones en `QdrantProbe`; plazo de Qdrant en segundos enteros. Comprobación: unitarias del caso de uso y la configuración; HTTP con `TestClient` (sin token 401, token incorrecto 401, `/health` sin token, `/v1/health` 200 y 503 con Qdrant simulado caído, `X-Request-Id`, registro sin token); integración con Qdrant real; `import-linter` con sus contratos; defectos a propósito (romper la comparación del token, la dirección de una capa, el 503) y arranque real con `make dev`.
2. ✅ **E6.1a — Conocimiento**, [bitácora 02](../../../../bitacora-construccion/feature/base-del-servicio/02-indexar-el-conocimiento.md). *Ajustado en E6.1a:* embeddings de Google por Vertex AI (`gemini-embedding-001`, 768) en lugar de FastEmbed, búsqueda solo densa y campo propio `knowledge_document_id` (LlamaIndex usa `document_id`). Comprobado contra Vertex AI (`make test-google`).
3. **E6.3 — Agente**: `FunctionAgent`, selección de herramientas por búsqueda y confirmaciones (plan E6).
4. **E6.4–E6.6**: streaming, modelo real con evaluación y despliegue (plan E6).
