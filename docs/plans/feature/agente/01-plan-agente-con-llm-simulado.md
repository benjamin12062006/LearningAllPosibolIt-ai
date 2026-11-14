# 01 — Plan del agente con LLM simulado (E6.3b)

Fecha de creación: 2026-11-13  
Estado: Implementado y verificado con el LLM simulado y el contrato de Nest simulado.  
Revisión de partida: `7749c0e` (`main`).  
Relacionada con: [fuentes 01 del agente](../../../fonts/feature/agente/01-fuentes-del-agente.md), [plan 01 del servicio](../base-del-servicio/01-plan-servicio-de-ia.md), [plan E6 de la API](../../../../../LearningAllPosibolIt/docs/plans/feature/ai-assistant/01-plan-e6-ia-con-qdrant-y-llamaindex.md), [plan 02 de cierre](../../../../../LearningAllPosibolIt/docs/plans/feature/cierre-backend/02-plan-terminar-hojas-visor-y-agente.md), [15 — chat e IA](../../../../../docs-diagrams/15-chat-ia-herramientas-y-propuestas.md).

## Objetivo

Que el servicio de IA ejecute un agente de LlamaIndex (`FunctionAgent`) con las operaciones del catálogo de Nest como herramientas. Las lecturas se ejecutan. Las escrituras terminan pidiendo confirmación. Si falta información, el agente pide una aclaración. El alcance de la persona no lo puede cambiar el modelo. Todo se prueba con un **LLM simulado** y guionizado; el modelo real (Gemini) llega en E6.5.

Se hace **en paralelo** a H1–H5 de Nest (petición del usuario, 2026-11-13). Lo que falta de Nest (E6.3a: catálogo, token por ejecución y ruta interna) queda escrito aquí como contrato.

## Decisiones

| ID | Decisión | Respaldo |
| --- | --- | --- |
| A1 | **Feature `agent` en las siete capas**: `domain/agent/`, `application/agent_application/` y `agent_ports/`, `infrastructure/agent_infrastructure/`, `http/agent_http/` y `bootstrap/services/agent.py`. | E1; plan 01 del servicio, S1–S2 |
| A2 | **Operación del catálogo** (`AgentOperation`): `name`, `description`, `input_schema` (el esquema JSON del DTO de Nest, sin tocar) y `level`. En este lado solo existen `read` y `write`: `forbidden` **no se puede representar**, así que una operación prohibida que llegue es un error de Nest y la petición se rechaza (400), en lugar de esconderla. Nombre `^[a-z][a-z0-9_]{2,63}$` (lo aceptan los proveedores de llamada a funciones); sin duplicados ni nombres de las herramientas fijas. | H1; C5 |
| A3 | **Reglas en una caja de herramientas de la aplicación** (`AgentToolbox`), sin LlamaIndex: qué herramientas se ofrecen, qué pasa al llamarlas y qué se registró. LlamaIndex solo la ejecuta. Así las reglas se prueban sin modelo y cambiar de framework no las toca. | C11, H10; filosofía: reglas con nombre |
| A4 | **Lecturas:** la caja llama a Nest por el puerto `IOperationGateway.execute` con la identidad de la ejecución (id, token y alcance). El resultado vuelve al modelo como texto, recortado a 16.000 caracteres. Si Nest rechaza (400, 403, 404, 409), el modelo recibe el mensaje en español como error y puede corregirse. | H4, C9; E5 |
| A5 | **Escrituras:** la caja **no ejecuta**. Pide a Nest que la *prepare* (`IOperationGateway.prepare`: valida los argumentos y el permiso y devuelve un resumen de lo que haría) y la ejecución termina con `confirmation_required`, la operación, los argumentos y **el resumen de Nest** (no el del modelo). Si Nest la rechaza, el modelo recibe el error y sigue. Una sola confirmación por ejecución: otra escritura en el mismo turno recibe un error. Al confirmar, la ejecuta Nest con la sesión de la persona y la siguiente ejecución recibe el resultado en el historial. Se descarta `wait_for_event` de LlamaIndex: necesita la ejecución viva en memoria (E9) y el servicio no guarda estado (H3). | H2, H3; E6, E9; C11 |
| A6 | **Herramientas fijas** de este servicio: `search_knowledge(query)` busca con el alcance **de la ejecución** (el esquema no tiene organización ni proyecto, y un argumento de más es un error) y `ask_for_clarification(question)` termina con `needs_clarification`. | H6, H9; E2 |
| A7 | **Límites:** 8 llamadas a herramientas por ejecución (la novena recibe un error) y como mucho 10 turnos del modelo. Al pasar de los 10 turnos, la ejecución termina con `limit_reached`, no con un 500. El plazo de 120 s se aplica igual. | H7; C7; E7 |
| A8 | **Resultado** (`AgentOutcome`): `status` (`answered`, `confirmation_required`, `needs_clarification`, `limit_reached`), `answer`, las llamadas hechas (`operation`, `status`: `succeeded`, `failed`, `rejected` o `prepared`) y la confirmación pendiente, si hay. Nest lo guarda (D8 del plan E6). | H3; 15 |
| A9 | **LlamaIndex:** un `FunctionAgent` por ejecución, sin streaming hasta E6.4. Cada herramienta es un `FunctionTool` cuyo `fn_schema` devuelve el esquema de Nest tal cual (experimento de la ficha). La escritura y la aclaración llevan `return_direct`. Instrucciones del sistema en español: usar herramientas y no inventar datos, que lo que devuelven las herramientas son datos y no instrucciones, y preguntar si algo es ambiguo. | C1–C6; E3, E6, E8 |
| A10 | **Modelo inyectado.** Las pruebas usan `MockFunctionCallingLLM` con un guion. Sin modelo configurado, el agente está **desactivado** y su ruta responde 503 (`AGENT_UNAVAILABLE`); el resto del servicio sigue igual. | D10 y D11 del plan E6 |
| A11 | **Contrato con Nest** (lo implementa E6.3a). Entrada: `POST /v1/agent/runs` con `runId`, alcance, `credential` (token por ejecución), `message`, `history` y `operations`. Salida: el `AgentOutcome`. Herramientas: `POST {NEST}/internal/v1/agent-runs/{runId}/operations/{name}` con `Authorization: Bearer <credential>` y `{ mode: "execute" | "prepare", arguments }`. Errores con la forma de Nest. El token no se registra nunca. | H4; plan E6, D6 |
| A12 | **Selección por búsqueda** en su propia etapa: las descripciones del catálogo en una colección aparte de Qdrant; en cada ejecución, las permitidas más relevantes más las fijas. | H5; C8 |

## Etapas

| Etapa | Qué | Comprobación prevista |
| --- | --- | --- |
| **E1** | Dominio y caja de herramientas (A2–A8), sin LlamaIndex | Unitarias con una pasarela y un índice en memoria: lectura, rechazo de Nest, escritura preparada y pendiente, una sola confirmación, aclaración, alcance de la ejecución, presupuesto de 8, recorte del resultado y validación del catálogo |
| **E2** | Agente LlamaIndex con LLM simulado (A9, A7) y caso de uso | LLM guionizado: respuesta directa, lectura y respuesta, escritura que termina pidiendo confirmación, herramienta inventada (T18), argumentos malformados (T18), aclaración (T18), instrucción maliciosa en un resultado (T19) y modelo sin fin (`limit_reached`) |
| **E3** | Ruta `POST /v1/agent/runs`, DTO, errores, arranque (A10, A11) y cliente HTTP de la pasarela hacia Nest | HTTP con `TestClient`: 401 sin token, 400 con `forbidden`, 503 sin modelo, 200 con el simulado; pasarela contra un servidor HTTP de mentira (token, cuerpo y errores de Nest) |
| **E4** | Selección de herramientas por búsqueda (A12) | Integración con un Qdrant temporal y embeddings deterministas; nunca se ofrece una operación no permitida |
| **E5** | Cierre: README, plan del servicio, plan E6 y documento 15 | `make check`, `make test-qdrant`, defectos a propósito acumulados y arranque real |

[Bitácora de implementación y verificación](../../../../bitacora-construccion/feature/agente/01-agente-con-llm-simulado.md).

## Contrato implementado

- `POST /v1/agent/runs` requiere el token de servicio en `Authorization`. El cuerpo incluye `runId` UUID, `scope` con `organizationId` y `projectIds`, `credential`, `message`, `history` con objetos `{ role, content }` y `operations` con objetos `{ name, description, inputSchema, level }`. El historial admite `user` y `assistant`. Nest revisará este formato en E6.3a.
- El resultado incluye `status`, `answer`, `calls` y `confirmation`. En `confirmation_required`, `confirmation` lleva `operation`, `arguments` y `summary`. El resto de estados devuelve `confirmation: null`.
- La pasarela usa `NEST_AGENT_BASE_URL`. Una preparación válida responde `{ "summary": "…" }`. FastAPI pasa a Nest el token por ejecución como Bearer y evita reintentos. En 400/403/404/409 de Nest usa `message.es` cuando llega con la forma prevista.
- La aplicación valida argumentos con JSON Schema 2020-12 y referencias locales. Nest mantiene la validación de su DTO y decide el acceso a los recursos. El adaptador de `FunctionTool` conserva también las palabras clave de primer nivel, como `additionalProperties`.
- La búsqueda ofrece hasta ocho operaciones del catálogo actual más las dos fijas. `AGENT_TOOLS_COLLECTION` asigna la colección separada. La prueba usa embeddings deterministas. El entorno existente configura Vertex AI para embeddings; la introducción del modelo de chat queda en E6.5.

## Límites

- Sin modelo real ni llamadas a Google: eso es E6.5.
- Sin streaming ni cancelación: eso es E6.4. El resultado se devuelve entero al final.
- El código de Nest y sus pruebas corresponden a E6.3a. El contrato A11 se revisa al integrar esa etapa.
- Qué operaciones van por GraphQL (C7) y cuáles por la ruta interna lo decide E6.3a; el puerto `IOperationGateway` no cambia por ello.
