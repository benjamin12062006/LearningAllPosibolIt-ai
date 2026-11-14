# 01 — Fuentes de la base del servicio de IA

Fecha de creación: 2026-11-09  
Última actualización: 2026-11-09  
Estado: Cerrada para E6.0.  
Relacionada con: [plan 01 del servicio](../../../plans/feature/base-del-servicio/01-plan-servicio-de-ia.md), [plan E6 de la API](../../../../../LearningAllPosibolIt/docs/plans/feature/ai-assistant/01-plan-e6-ia-con-qdrant-y-llamaindex.md), [revisión 02 de LlamaIndex](../../../../../LearningAllPosibolIt/docs/fonts/feature/ai-assistant/02-revision-de-llamaindex-para-la-api.md).

## Referencia de arquitectura (E)

`/Users/benji/Documents/HANDLE-BUSINESS/backend` (Rust, commit `d2a7850`), que el usuario pidió como modelo:

| ID | Pieza | Qué se toma |
| --- | --- | --- |
| E1 | Siete crates: `backend_domain`, `backend_application`, `backend_infrastructure`, `backend_http`, `backend_config`, `backend_bootstrap`, `backend_common` | Las mismas siete capas como subpaquetes de `ktsu_ai`. |
| E2 | `backend_application/src/user_ports/in_user_use_case.rs` y `out_user_user_repository.rs` | Puertos de entrada (`in_…`, lo que ofrece la aplicación) y de salida (`out_…`, lo que necesita de fuera), como `Protocol` de Python. |
| E3 | `user_application/use_cases/create_user.rs`: «Flujo: `CreateUserInput -> User -> CreateUserRecord -> repo -> UserOutput`» | Un caso de uso por archivo, una función `execute` que orquesta; DTO `dto_input_…`/`dto_output_…` planos. |
| E4 | `user_application/user_service.rs`: «`UserService` implementa el puerto de entrada … y delega la lógica real en `use_cases`» | Un servicio fachada por feature que implementa el puerto `in_`. |
| E5 | `infrastructure/database/qdrant/connection.rs` y `health.rs`; `bootstrap/resources/databases/qdrant.rs` | Conexión y comprobación en infraestructura; el arranque crea el recurso y comprueba que responde. |
| E6 | `bootstrap/services/user.rs`: construye data store → repositorio → servicio | La composición (qué implementación va en cada puerto) solo en `bootstrap`. |
| E7 | `backend_http`: rutas por feature, `routes.rs` que compone, `middleware/` (auth, errores, observabilidad) y `http_server/` | Igual con FastAPI: `*_http/routes.py`, `routes.py`, `middleware/`, `http_server.py`. |
| E8 | README, «Logs del servidor»: una línea por petición con `request_id`, método, ruta, estado y duración; sin tokens, cuerpos ni query strings | Mismo registro por petición. |

## Cursos (C)

| ID | Lección | Qué aporta |
| --- | --- | --- |
| C1 | `Python/LlamaIndex para Aplicaciones LLM/Sección 3/17. The Ingestion Pipeline - Architecture Overview and Hands-on.md`, líneas 15–19 | El `IngestionPipeline` recibe en su constructor las transformaciones (trocear, embeber) y devuelve nodos: base de E6.1. |
| C2 | Misma sección, `19. Caching with LlamaIndex and Chroma Vector Store.md`, líneas 13–19 | Caché y docstore para no recalcular embeddings repetidos: base de la estrategia *upsert* de E6.1. |
| C3 | Misma sección, `28. Adding Resources and Citations to our Responses.md`, líneas 13–19 | Devolver los nodos de origen para citar de dónde sale cada respuesta. |
| C4 | `Sección 5/43. Function Calling - Deep Dive and Hands-on.md`, líneas 15–19, y `45. Agents In Production.md`, líneas 13–19 | Herramientas con esquema JSON; en producción, cada paso es una llamada al modelo y la ventana de contexto limita cuántas herramientas y datos caben: base de la selección de herramientas por búsqueda (D12 del plan E6). |
| C5 | `Sección 7/54. LlamaIndex Latest- Upgrading code to.md`, líneas 13–17 | LlamaIndex está dividido en paquetes (`llama-index-core` y uno por integración): se instalan solo los que se usan. |

### FastAPI (añadido el 2026-11-09 a petición del usuario)

Rutas relativas a `/Users/benji/Documents/chrome-extencions/trancripciones/FastAPI/`.

| ID | Lección | Qué aporta |
| --- | --- | --- |
| C6 | `FastAPI Completo/Sección 7 Arquitectura y modularización del proyecto/111. Arquitectura de capas.md`, líneas 13–17 | Separar en capas no es estética: un archivo único de rutas se vuelve «muy difícil de probar y sobre todo de mantener». Respalda S1–S2. |
| C7 | `FastAPI Completo/Sección 8 Dependencias, seguridad y JWT/130. Dependencias.md`, líneas 15–17 | Una dependencia es una función que FastAPI ejecuta por la ruta: se escribe una vez y la usan todos los endpoints. Respalda `InternalAuth` como `Depends`. |
| C8 | `FastAPI Masterclass/Sección 8 App Organization/86. Dependencies in Route Decorator Methods.md`, líneas 13–17 | Dependencias en el decorador (`dependencies=[…]`) cuando no devuelven valor y solo protegen la ruta. Es como se protege `/v1/health`. |
| C9 | `FastAPI Masterclass/Sección 8 App Organization/88. Organizing Code by Feature.md`, líneas 13–17 | Organizar por feature (el ejemplo es Dispatch, de Netflix) frente a por tipo técnico. Respalda `<feature>_http`, `<feature>_application`. |
| C10 | `FastAPI Completo/Sección 15 Middlewares/222. Middleware - Logging de peticiones.md` y `223. Middleware - Generando Request ID.md`, líneas 13–17 | Middleware HTTP con `call_next` para registrar método, ruta y estado, y para poner un `request_id` en la cabecera de respuesta. Respalda S8 (`observability.py`). |
| C11 | `FastAPI Completo/Sección 9 Funciones síncronas y asíncronas/147. Errores comunes.md`, líneas 13–17 | Una llamada síncrona dentro de una ruta asíncrona bloquea el servidor. Respalda quitar la comprobación síncrona del cliente de Qdrant (bitácora 01) y elegir clientes asíncronos (`AsyncQdrantClient`). |

## Documentación y registros (F)

| ID | Fuente | Qué se toma |
| --- | --- | --- |
| F1 | PyPI, consultado 2026-11-09: `llama-index-core` 0.14.25 (2026-09-21, Python ≥3.10), `llama-index-vector-stores-qdrant` 0.10.4 (2026-10-08, `qdrant-client>=1.16.0`), `llama-index-llms-anthropic` 0.12.3, `llama-index-embeddings-fastembed` 0.7.0 (**Python <3.13**), `fastembed` 0.9.1, `qdrant-client` 1.19.1 (2026-09-16), `fastapi` 0.162.2, `uvicorn` 0.54.0, `pydantic-settings` 2.16.2, `import-linter` 2.16, `pytest` 9.2.0, `ruff` 0.17.4, `mypy` 2.4.1 | Python **3.12** (lo exige FastEmbed de LlamaIndex) y `qdrant-client` 1.19.1, la versión menor del servidor. |
| F2 | LlamaIndex, *Qdrant Hybrid Search* (`developers.llamaindex.ai/python/examples/vector_stores/qdrant_hybrid/`) | `QdrantVectorStore(…, enable_hybrid=True, fastembed_sparse_model="Qdrant/bm25")`; consulta `vector_store_query_mode="hybrid"` con `similarity_top_k` y `sparse_top_k`. Para E6.1. |
| F3 | LlamaIndex, *Agents* (`developers.llamaindex.ai/python/framework/understanding/agent/`) | `FunctionAgent(tools=[…], llm=…, system_prompt=…)` desde `llama_index.core.agent.workflow`; funciones normales con docstring y tipos como herramientas. Para E6.3. |
| F4 | Qdrant, *Multitenancy* | Una colección con `is_tenant` y filtro en cada consulta (ver ficha 01 de la API, F1). |
| F5 | `uv` 0.12.1 y Python 3.12.11 instalados en el portátil (`uv python list`) | Sin instalar nada global. |

## Mapa necesidad → fuentes → decisión

| Necesidad | Fuentes | Decisión del plan |
| --- | --- | --- |
| Arquitectura limpia y legible | E1–E7, C6, C9 | S1, S2 |
| Python y dependencias | F1, F5, C5 | S3 |
| Configuración y secretos | E8, plan E6 D6 | S4 |
| FastAPI: protección, registros y asincronía | C7, C8, C10, C11 | S3, S7, S8 |
| Qdrant de desarrollo | Plan E6 D3 | S5 |
| Saber si está vivo | E5, E8 | S6 |
| Ingesta, búsqueda y agente | C1–C4, F2, F3 | Etapas E6.1 y E6.3 |
