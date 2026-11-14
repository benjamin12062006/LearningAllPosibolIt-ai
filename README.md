# KTSU AI — servicio de IA interno

Fecha de creación: 2026-11-09  
Última actualización: 2026-11-13
Relacionada con: [plan 01 del servicio](docs/plans/feature/base-del-servicio/01-plan-servicio-de-ia.md), [plan E6 de la API](../LearningAllPosibolIt/docs/plans/feature/ai-assistant/01-plan-e6-ia-con-qdrant-y-llamaindex.md).

Servicio Python con FastAPI y LlamaIndex que indexa en Qdrant lo que le manda la API Nest (embeddings de Google por Vertex AI), busca con el filtro de la organización y ejecuta el agente cuando recibe un modelo de llamada a funciones. No es público ni tiene base de datos propia: solo lo llama Nest, con un token de servicio.

## Capas

Las mismas siete capas que `HANDLE-BUSINESS/backend`, como subpaquetes de `src/ktsu_ai/`:

| Capa | Qué contiene | Puede importar |
| --- | --- | --- |
| `domain` | Reglas puras (`@dataclass(frozen=True)`) | Nada del proyecto |
| `application` | Por feature: `<feature>_application` (DTO `dto_input_…`/`dto_output_…`, `use_cases/`, `<feature>_service.py`) y `<feature>_ports` (`in_…` y `out_…`, `typing.Protocol`) | `domain`, `common` |
| `infrastructure` | Implementaciones de los puertos `out_…` (Qdrant, LlamaIndex) | `application`, `domain`, `config`, `common` |
| `http` | FastAPI: `<feature>_http/routes.py` + `dto/`, `middleware/`, `routes.py`, `http_server.py` | `application`, `domain`, `config`, `common` |
| `config` | Configuración del entorno (`pydantic-settings`) | `common` |
| `bootstrap` | Composición: crea recursos y servicios y monta las rutas | Todo |
| `common` | Errores públicos | Nada del proyecto |

`make lint` comprueba estas reglas con `import-linter`.

## Arquitectura hexagonal: recorrido de una petición

El mismo patrón de puertos y adaptadores que `HANDLE-BUSINESS/backend` (Rust). Ejemplo con `PUT …/sources/{type}/{id}` (indexar una fuente):

```text
Nest ──HTTP──▶ [adaptador de entrada]  http/knowledge_http/routes.py (+ dto/)
                     │ llama al
                     ▼
               [puerto de entrada]     application/knowledge_ports/in_knowledge_use_case.py
                     │ lo implementa
                     ▼
               [servicio]              application/knowledge_application/knowledge_service.py
                     │ delega en
                     ▼
               [caso de uso]           …/use_cases/replace_source.py   (reglas: qué cambió, qué sobra)
                     │ usa el
                     ▼
               [puerto de salida]      application/knowledge_ports/out_knowledge_index.py
                     │ lo implementa
                     ▼
               [adaptador de salida]   infrastructure/knowledge_infrastructure/llamaindex_knowledge_index.py
                     │                 (LlamaIndex + Qdrant; embeddings de Google)
                     ▼
                   Qdrant · Vertex AI
```

`bootstrap/` decide qué adaptador va en cada puerto; nadie más lo sabe.

| Pieza | Rust (`HANDLE-BUSINESS/backend`) | Python (este servicio) |
| --- | --- | --- |
| Adaptador de entrada | `backend_http/user_http/user_controller.rs`, `routes.rs` | `http/knowledge_http/routes.py`, `dto/` |
| Puerto de entrada | `user_ports/in_user_use_case.rs` (`trait IUserUseCase`) | `knowledge_ports/in_knowledge_use_case.py` (`Protocol IKnowledgeUseCase`) |
| Servicio de aplicación | `user_application/user_service.rs` | `knowledge_application/knowledge_service.py` |
| Casos de uso | `user_application/use_cases/create_user.rs` | `knowledge_application/use_cases/replace_source.py`, `search_knowledge.py` |
| DTO de aplicación | `dto_input_create_user_input.rs`, `dto_output_user_output.rs` | `dto_input_replace_source_input.py`, `dto_output_replace_source_output.py`… |
| Dominio | `backend_domain/user/user_model.rs` | `domain/knowledge/knowledge_document.py`, `domain/access/access_scope.py` |
| Puerto de salida | `user_ports/out_user_user_repository.rs` (`trait IUserRepository`) | `knowledge_ports/out_knowledge_index.py` (`Protocol IKnowledgeIndex`) |
| Adaptador de salida | `user_infrastructure/repositories/user_repository.rs` | `knowledge_infrastructure/llamaindex_knowledge_index.py`, `collection.py` |
| Composición | `backend_bootstrap/src/bootstrap/services/user.rs` | `bootstrap/services/knowledge.py`, `bootstrap/app.py` |

Diferencia de lenguaje: en Rust el contrato es un `trait` que el compilador exige implementar; en Python es un `typing.Protocol`, y quien lo comprueba es `mypy --strict` (`make lint`). Las pruebas aprovechan el puerto: `tests/unit/test_knowledge_use_cases.py` usa un índice en memoria en lugar de Qdrant.

## Puesta en marcha

```bash
cp .env.example .env      # y rellena AI_SERVICE_TOKEN con `make token`
make install              # dependencias exactas de uv.lock
make qdrant-up            # Qdrant de desarrollo: 127.0.0.1:56333, 2 CPU, 1 GiB
make dev                  # servicio en 127.0.0.1:8090, con recarga
make check                # ruff, formato, mypy, import-linter y pytest
make test-qdrant          # pruebas contra un Qdrant temporal
make test-google          # pruebas contra Vertex AI (textos inventados; no es gratis)
make qdrant-down          # parar conservando el contenedor y su volumen
```

En OrbStack, abre el proyecto Compose `estadistica-forms-ai` para iniciar o detener Qdrant. `make qdrant-up` utiliza el volumen existente `estadistica-forms-qdrant-data` y deja disponible el [panel local de Qdrant](http://127.0.0.1:56333/dashboard).

`GET /health` responde sin token. `GET /v1/health` necesita `Authorization: Bearer <AI_SERVICE_TOKEN>` y devuelve 503 si Qdrant no responde.

## Agente con LLM simulado (E6.3b)

`POST /v1/agent/runs` usa el token de servicio en `Authorization`. El cuerpo lleva la credencial efímera de la ejecución y el catálogo autorizado por Nest. FastAPI prioriza hasta ocho operaciones mediante la colección de herramientas en Qdrant, añade la búsqueda de conocimiento y la aclaración, y devuelve el resultado del turno.

Las lecturas usan `mode: "execute"`. Las escrituras usan `mode: "prepare"` y devuelven el resumen de Nest con `confirmation_required`. La confirmación humana se tramita en Nest. El arranque desde el entorno responde `503 AGENT_UNAVAILABLE` en esta ruta hasta que se conecte un modelo de chat.

Las pruebas inyectan `MockFunctionCallingLLM` en `create_app`. El guion indica las llamadas y respuestas que debe emitir el modelo. El workflow de LlamaIndex, la ruta y la pasarela se ejecutan con el contrato de Nest simulado y embeddings deterministas.

```bash
uv run pytest tests/unit/test_agent.py tests/http/test_agent_routes.py
make test-qdrant
```

[Plan y contrato E6.3b](docs/plans/feature/agente/01-plan-agente-con-llm-simulado.md) · [Bitácora del agente](bitacora-construccion/feature/agente/01-agente-con-llm-simulado.md)

## Registros

Una línea por petición con método, ruta, estado, duración y `request_id` (el `X-Request-Id` de Nest si llega uno válido). No se registran tokens, cuerpos ni query strings.
