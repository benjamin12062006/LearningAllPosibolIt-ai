# 01 — Fuentes del agente con LLM simulado (E6.3b)

Fecha de creación: 2026-11-13  
Estado: Cerrada para el plan 01 del agente.  
Revisión de partida: `7749c0e` (`main`).  
Relacionada con: [plan 01 del agente](../../../plans/feature/agente/01-plan-agente-con-llm-simulado.md), [fuentes de la base del servicio](../base-del-servicio/01-fuentes-de-la-base-del-servicio.md), [plan E6 de la API](../../../../../LearningAllPosibolIt/docs/plans/feature/ai-assistant/01-plan-e6-ia-con-qdrant-y-llamaindex.md) (D6, D8, D9, D12, D13), [15 — chat e IA](../../../../../docs-diagrams/15-chat-ia-herramientas-y-propuestas.md), [18 — matriz de aceptación](../../../../../docs-diagrams/18-secuencia-de-entregas-y-matriz-de-aceptacion.md) (T18, T19), [plan 02 de cierre](../../../../../LearningAllPosibolIt/docs/plans/feature/cierre-backend/02-plan-terminar-hojas-visor-y-agente.md).

## Por qué ahora

El plan maestro pone E6.3b después de E6.3a (el catálogo de operaciones en Nest). El usuario pidió el 2026-11-13 adelantarlo **en paralelo** a H1–H5, que ocupan Nest: este repositorio y sus pruebas no tocan los archivos de Nest. Lo que E6.3b necesita de Nest se define aquí como **contrato** (puertos y forma de los datos). E6.3a lo implementará y la etapa de integración lo comprobará.

## Estado del código (E)

Comprobado en la revisión `7749c0e` y en la versión instalada (`uv.lock`) de `llama-index-core` **0.14.25**.

| ID | Dónde | Qué se observa |
| --- | --- | --- |
| E1 | `src/ktsu_ai/` | Siete capas con `import-linter`; por feature, `<feature>_application` (DTO, `use_cases/`, servicio) y `<feature>_ports` (`in_…`, `out_…` como `Protocol`). No hay nada del agente. |
| E2 | `application/knowledge_application/use_cases/search_knowledge.py` | La búsqueda ya aplica el `AccessScope` que manda Nest y no consulta Qdrant si no hay proyectos visibles. Es la herramienta `search_knowledge` del agente. |
| E3 | `.venv/…/llama_index/core/llms/mock.py:294` | `MockFunctionCallingLLM(response_generator=…)`: un LLM de llamada a funciones cuyo comportamiento se escribe en una función que recibe los mensajes y las herramientas (`kwargs["tools"]`). Sirve como «LLM simulado» guionizado (D10 del plan E6). |
| E4 | `.venv/…/llama_index/core/agent/workflow/base_agent.py:647-656` | Si el modelo pide una herramienta que no se le dio, LlamaIndex no falla: devuelve al modelo `Tool … not found` como error. |
| E5 | `base_agent.py:375-391` | Si una herramienta lanza una excepción, el error se convierte en resultado `is_error=True` que ve el modelo; el agente sigue. |
| E6 | `base_agent.py:697-735` | Una herramienta con `return_direct=True` que no falla **termina la ejecución** y su texto pasa a ser la respuesta. |
| E7 | `base_agent.py:541-552` | Al llegar a `max_iterations` lanza `WorkflowRuntimeError` (con `early_stopping_method="force"`, el valor por defecto). |
| E8 | `.venv/…/llama_index/core/tools/types.py:40` | El esquema sale de `fn_schema.model_json_schema()`. `ToolMetadata.get_parameters_dict()` filtra claves de primer nivel antes de ofrecerlas al modelo. |
| E9 | `.venv/…/workflows/events.py:506-540` y `workflows/context/context.py:536` | La espera humana de LlamaIndex (`InputRequiredEvent`, `HumanResponseEvent`, `ctx.wait_for_event`) mantiene la ejecución **viva en memoria** del proceso hasta que llega la respuesta. |

### Experimento (2026-11-13)

Script en la carpeta temporal de la sesión con `FunctionAgent` y un `MockFunctionCallingLLM` guionizado; ejecutado con el `.venv` del servicio:

| Prueba | Resultado |
| --- | --- |
| Herramienta con `fn_schema` cuyo `model_json_schema()` devuelve el esquema JSON tal cual lo mandaría Nest | `to_openai_tool()` lo envía al modelo idéntico (`projectId`, `limit`, `required`) |
| El modelo pide una lectura y una herramienta que no existe (`delete_project`) en el mismo turno | La lectura se ejecuta; la otra vuelve como error `not found`; el agente sigue |
| El modelo pide una escritura marcada `return_direct` | La ejecución termina y la respuesta es el texto de la herramienta |
| Un modelo que pide herramientas sin parar, con `max_iterations=3` | `workflows.errors.WorkflowRuntimeError` |
| Argumentos | `FunctionTool` pasa los argumentos del modelo como `**kwargs` sin validarlos (el `fn_schema` no tiene campos) |

## Requisitos del diseño (H)

| ID | Fuente | Requisito |
| --- | --- | --- |
| H1 | Plan E6, D9 | El agente maneja casi toda la API mediante un catálogo de Nest. Cada operación declara nombre, descripción, esquema de entrada y nivel `read`, `write` o `forbidden`. Ninguna operación `forbidden` llega al modelo. |
| H2 | Plan E6, D13; 15, «Herramientas» | Una `write` **no se ejecuta** cuando el modelo la pide: el agente dice qué va a hacer (operación, objetivo y resumen) y espera a que la persona confirme con su sesión. Las lecturas se ejecutan directamente. |
| H3 | Plan E6, D8 | El servicio de IA **no guarda estado**: recibe el historial y devuelve el resultado; Nest guarda conversaciones, ejecuciones y eventos. |
| H4 | Plan E6, D6; 23 | El servicio llama a Nest para las herramientas con un **token por ejecución** que Nest liga a la persona y al alcance. Nest autoriza cada operación (404 ajeno, 403 sin permiso). |
| H5 | Plan E6, D12 | Herramientas elegidas por búsqueda, más un núcleo fijo (`search_knowledge`, …). Se hace en una etapa propia. |
| H6 | 15, «Orquestación» | Si faltan datos, la ejecución termina con `needs_clarification`; la respuesta de la persona inicia otra ejecución. |
| H7 | 15, «Límites» | 8 llamadas a herramientas por ejecución y 120 s. |
| H8 | 18, T18 | Un prompt ambiguo pide aclaración; IDs y herramientas ajenas y la salida malformada se rechazan (con un proveedor simulado). |
| H9 | 18, T19 | Una instrucción maliciosa dentro de una celda no amplía el acceso ni la selección, ni aplica nada. |
| H10 | 15, «Límites» | Celdas, mensajes y resultados son contenido **no confiable**: los permisos y las herramientas se validan fuera del modelo. |

## Cursos (C)

Curso local: `Python/LlamaIndex para Aplicaciones LLM/Sección 5 LlamaIndex ReAct Agents/` ([carpeta](/Users/benji/Documents/chrome-extencions/trancripciones/Python/LlamaIndex%20para%20Aplicaciones%20LLM/)). Líneas leídas con `nl -ba`.

| ID | Lección y líneas | Qué aporta |
| --- | --- | --- |
| C1 | `40. Introduction to agents.md`, 13–17 | Un agente aprovecha el razonamiento del modelo para elegir una herramienta y «extraer el argumento correcto» del prompt. La herramienta es una función normal. |
| C2 | `41. Our First ReAct Agent - Hands-on.md`, 31 | La descripción de cada herramienta «es lo que realmente se lee en el interior del modelo»: nombre y descripción del catálogo de Nest llegan al modelo tal cual. |
| C3 | `41. …`, 33 | Sin contexto, cada agente es «apátrida». Aquí se quiere: el historial lo manda Nest en cada ejecución (H3). |
| C4 | `41. …`, 37–47 | `handler.stream_events()` con `ToolCallResult` (nombre y salida de la herramienta) y `AgentStream`: base de los eventos de E6.4. |
| C5 | `43. Function Calling - Deep Dive and Hands-on.md`, 15–21 y 29–31 | La llamada a funciones presenta al modelo un esquema JSON con nombre, descripción, propiedades y `required`. `FunctionAgent` usa la llamada nativa y puede pedir varias herramientas en paralelo; `ReActAgent` razona por texto. Se elige `FunctionAgent` porque Gemini tiene llamada nativa. |
| C6 | `44. LlamaIndex ReAct internals - Under the hood.md`, 21–25 | LlamaIndex inserta las descripciones de las herramientas registradas en lo que manda al modelo: «influye en la forma de decidir qué herramienta utilizar». |
| C7 | `45. Agents In Production.md`, 13–19 | Cada paso es una llamada al modelo; con 0,9 de acierto por paso, seis pasos seguidos bajan a «0. 59». Base de un límite de pasos y llamadas (H7). |
| C8 | `45. …`, 25 | «Aumento de la recuperación para la selección de herramientas» cuando hay demasiadas: base de H5 (etapa 4). |
| C9 | `45. …`, 27 | La salida del modelo hay que validarla, porque un formato incorrecto «puede estropear nuestra aplicación». |
| C10 | `45. …`, 29–31 | Prompt injection y «principio del menor privilegio»: dar a las herramientas los permisos mínimos. Base de H9 y H10. |
| C11 | `45. …`, 31–33 | Lo determinista se programa, no se pide al agente. Por eso el resumen de una escritura lo calcula Nest y no el modelo. |

## Documentación oficial (F)

| ID | Fuente | Qué aporta |
| --- | --- | --- |
| F1 | LlamaIndex, *Agents* (`developers.llamaindex.ai/python/framework/understanding/agent/`), ya citada como F3 en la [ficha de la base](../base-del-servicio/01-fuentes-de-la-base-del-servicio.md) | `FunctionAgent(tools=[…], llm=…, system_prompt=…)` desde `llama_index.core.agent.workflow`. |
| F2 | El código instalado de `llama-index-core` 0.14.25 (E3–E9) | Es la fuente primaria de la versión que se usa: el comportamiento comprobado en el experimento manda sobre los ejemplos de la web. |
| F3 | OWASP, citado en [19](../../../../../docs-diagrams/19-fuentes-trazabilidad-y-decisiones-pendientes.md) como F5 | Validar herramientas y permisos fuera del modelo y tratar como no confiables los datos recuperados y la salida del modelo. |

### Verificación durante la implementación (2026-11-13)

El experimento anterior mantuvo las claves que LlamaIndex deja pasar por defecto. El [adaptador de herramientas](../../../../src/ktsu_ai/infrastructure/agent_infrastructure/llamaindex_agent.py) conserva además `additionalProperties` y las demás claves de primer nivel. La [prueba del esquema y de la lectura](../../../../tests/unit/test_agent.py) compara el esquema completo recibido por el modelo con el del catálogo.

La referencia [Agent Classes de LlamaIndex](https://developers.llamaindex.ai/python/framework-api-reference/agent/#functionagent), consultada el 2026-11-13, describe `allow_parallel_tool_calls`. En la versión instalada el parámetro se pasa al LLM. Un LLM guionizado aún puede producir varias llamadas en un turno, por lo que la aplicación serializa su procesamiento y solo conserva una confirmación.

## Mapa necesidad → fuentes → decisión

| Necesidad | Fuentes | Decisión (plan 01) |
| --- | --- | --- |
| Probar el agente sin modelo real | E3, D10 del plan E6 | `MockFunctionCallingLLM` guionizado en las pruebas; sin modelo configurado, el agente está desactivado |
| Herramientas del catálogo de Nest con su esquema | C2, C5, C6, E8, experimento | Una herramienta por operación con el esquema JSON de Nest tal cual |
| Las reglas no dependen de LlamaIndex | E1, C11, H10 | Las reglas (confirmación, alcance, presupuesto, aclaración) en una «caja de herramientas» de la aplicación; LlamaIndex solo la ejecuta |
| Confirmar escrituras sin guardar estado | H2, H3, E6, E9 | La escritura la **prepara** Nest (valida y resume) y la ejecución **termina** con `confirmation_required`. Se descarta `wait_for_event` (E9): exige memoria viva entre peticiones |
| Herramienta ajena o inventada | E4, H8 | La rechaza LlamaIndex (no existe); además, la caja de herramientas solo conoce las operaciones permitidas |
| Alcance que el modelo no puede cambiar | E2, H9, C10 | El alcance y el token salen de la ejecución, nunca de los argumentos del modelo |
| Pedir aclaración | H6, E6 | Herramienta fija `ask_for_clarification` que termina la ejecución |
| Límite de pasos | C7, H7, E7 | 8 llamadas a herramientas y `max_iterations`; al superarlo, `limit_reached` en lugar de un error 500 |
| Muchas herramientas | C8, H5 | Selección por búsqueda en su propia etapa |
