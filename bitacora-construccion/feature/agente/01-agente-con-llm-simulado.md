# 01 — Agente con LLM simulado (E6.3b)

Fecha de creación: 2026-11-13  
Estado: Implementado y verificado con el LLM simulado y el contrato de Nest simulado.  
Revisión de partida: `7749c0e`  
Relacionada con el [plan E6.3b](../../../docs/plans/feature/agente/01-plan-agente-con-llm-simulado.md), la [ficha de fuentes](../../../docs/fonts/feature/agente/01-fuentes-del-agente.md) y la [base del conocimiento](../base-del-servicio/02-indexar-el-conocimiento.md).

## Construcción por etapas

| Etapa | Evidencia y adaptación | Código |
| --- | --- | --- |
| E1 · Reglas de herramientas | La ficha explica en C5 y C9 la diferencia entre ofrecer un esquema y validar los argumentos. El catálogo solo acepta `read` y `write`. Cada llamada consume presupuesto, incluso si el nombre es desconocido. La búsqueda recibe el alcance de la ejecución. Las escrituras se preparan y devuelven una sola confirmación por turno con el resumen de Nest. | [Dominio](../../../src/ktsu_ai/domain/agent/agent_run.py), [AgentToolbox](../../../src/ktsu_ai/application/agent_application/agent_toolbox.py) y [validación](../../../src/ktsu_ai/application/agent_application/operation_schema.py) |
| E2 · Workflow | E3 y E6 de la ficha respaldan `MockFunctionCallingLLM` y `return_direct`. Se conserva el esquema original en `ToolMetadata`, que de fábrica filtra claves de primer nivel. Una escritura preparada o aclaración válida termina el turno. El servicio limita a 8 llamadas y 10 turnos del modelo, con plazo total de 120 s y cancelación del workflow si se agota. El contenido de herramientas tiene un tope de 16.000 caracteres por lectura y un presupuesto acumulado de 64 KiB. | [AgentService](../../../src/ktsu_ai/application/agent_application/agent_service.py), [LlamaIndexAgent](../../../src/ktsu_ai/infrastructure/agent_infrastructure/llamaindex_agent.py) y [guion de pruebas](../../../tests/support/scripted_llm.py) |
| E3 · Contrato HTTP | El token de servicio autentica `POST /v1/agent/runs`. Una credencial independiente viaja de FastAPI a Nest en `Authorization`; la identidad y el alcance quedan fuera de los argumentos del modelo. `httpx` es dependencia de ejecución. El arranque responde 503 en esa ruta si falta un modelo de chat. | [Ruta](../../../src/ktsu_ai/http/agent_http/routes.py), [DTO](../../../src/ktsu_ai/http/agent_http/agent_dto.py), [NestOperationGateway](../../../src/ktsu_ai/infrastructure/agent_infrastructure/nest_operation_gateway.py) y [composición](../../../src/ktsu_ai/bootstrap/services/agent.py) |
| E4 · Selección | C8 de la ficha y D12 del plan E6 respaldan buscar por relevancia. Se usa el cliente Qdrant existente con filtro por los IDs de las operaciones autorizadas y una segunda comprobación en la aplicación. La colección guarda vectores de nombre y descripción. El ID cambia si cambia la descripción. El catálogo de la petición aporta el esquema y el nivel que se ofrecen al modelo. Se eligió este acceso directo para controlar el filtro y reutilizar los vectores sin guardar instancias de herramientas. | [QdrantOperationSelector](../../../src/ktsu_ai/infrastructure/agent_infrastructure/qdrant_operation_selector.py) y [selección en AgentService](../../../src/ktsu_ai/application/agent_application/agent_service.py) |
| E5 · Entrega | El contrato de preparación concreta la respuesta de Nest como `{ "summary": "…" }`. La integración real con el catálogo, la emisión del token y la confirmación humana corresponde a E6.3a. Gemini para chat corresponde a E6.5. | [Contrato E6.3b](../../../docs/plans/feature/agente/01-plan-agente-con-llm-simulado.md#contrato-implementado), [README](../../../README.md) y [documento 15](../../../../docs-diagrams/15-chat-ia-herramientas-y-propuestas.md#e63b-en-fastapi-2026-11-13) |

## Comprobación

| Comprobación ejecutada | Resultado |
| --- | --- |
| Línea base con `make check` | 72 aprobadas y 19 omitidas. |
| `make check` tras el cambio | Ruff, formato, mypy y los 2 contratos de importaciones correctos. 96 pruebas aprobadas y 20 omitidas. |
| `make test-qdrant` | 18 pruebas aprobadas contra Qdrant 1.19.1 temporal. La primera corrida detectó que Qdrant puede variar el orden y la composición de los empates. La prueba comprueba que se ofrece la herramienta más relevante, se respeta el límite y las demás herramientas pertenecen al catálogo autorizado. |
| Ocho defectos introducidos de uno en uno en una copia temporal | 8 detectados. Cambiaron el modo de escritura, el esquema expuesto, la validación de argumentos, los límites del modelo y de herramientas, el token de ejecución, la autenticación de entrada y el filtro de selección de Qdrant. |
| Arranque real de Uvicorn en localhost con modelo, embeddings y Nest simulados | Salud 200, petición sin token 401, petición autorizada 200 con `confirmation_required`, única llamada a Nest en modo `prepare` y apagado correcto. |

Las pruebas del agente ejecutan el workflow instalado. Usan respuestas guionizadas, embeddings deterministas y datos sintéticos. No se ejecutó `make test-google`. LlamaIndex emite avisos de deprecación de Pydantic al ejecutar estas pruebas. Queda pendiente la comprobación de extremo a extremo con Nest cuando se implemente E6.3a.
