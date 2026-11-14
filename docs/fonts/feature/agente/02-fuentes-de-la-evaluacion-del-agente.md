# 02 — Fuentes para evaluar al agente con casos sintéticos

Fecha de creación: 2026-11-13  
Fecha de consulta: 2026-11-13  
Tipo de fuente: diseño y código del proyecto.  
Revisión de referencia: `c87fb20`, agente E6.3b.  
Relacionada con: [plan de evaluación](../../../plans/feature/agente/02-plan-evaluacion-del-agente.md), [fuentes del agente](01-fuentes-del-agente.md) y [bitácora de E6.3b](../../../../bitacora-construccion/feature/agente/01-agente-con-llm-simulado.md).

## Necesidad de consulta

El proyecto prevé evaluar al agente antes de habilitar el modelo externo. Hay que recuperar los casos de aceptación y comprobar qué partes pueden ejecutarse hoy con datos sintéticos en FastAPI.

## Evidencia del proyecto

| ID | Fuente y localizador | Evidencia |
| --- | --- | --- |
| F1 | [15 — Chat lateral con IA y propuestas verificables](../../../../../docs-diagrams/15-chat-ia-herramientas-y-propuestas.md#límites-privacidad-y-evaluación), «Límites, privacidad y evaluación», 118–124 | El dataset contempla mapeo claro y ambiguo, porcentajes con decimales, instrucciones dentro de celdas, herramientas desconocidas, IDs ajenos, salida malformada, contexto antiguo, proveedor lento, cancelación y cuota agotada. La evaluación exige cero escrituras oficiales sin aprobación y cero accesos entre empresas en la suite. |
| F2 | [18 — Secuencia de entregas y matriz de aceptación](../../../../../docs-diagrams/18-secuencia-de-entregas-y-matriz-de-aceptacion.md), filas T18b–T22, 84–90 | T18 admite probar aclaraciones y rechazos con proveedor simulado. T19 exige conservar acceso y selección al recibir instrucciones en celdas. T20 pide cálculo determinista, selección exacta y aprobación humana. T18b comprueba aislamiento del índice con Qdrant real. T21–T22 cubren reconexión, cancelación y cuotas. |
| F3 | [Plan E6 de la API](../../../../../LearningAllPosibolIt/docs/plans/feature/ai-assistant/01-plan-e6-ia-con-qdrant-y-llamaindex.md), D6, D9–D13 y etapas E6.3–E6.5 | Nest controla la identidad, el catálogo y la confirmación de escrituras. E6.4 cubre eventos y cuotas. E6.5 incorpora Gemini por Vertex AI y la evaluación de fidelidad, relevancia y exactitud con LlamaIndex. |

## Evidencia del código

| ID | Archivo y símbolo | Evidencia |
| --- | --- | --- |
| F4 | [ScriptedResponses](../../../../tests/support/scripted_llm.py), `_next_reply` y `tool_call` | El ayudante convierte llamadas descritas por las pruebas en respuestas de un LLM guionizado y registra los mensajes y esquemas recibidos. Permite comprobar casos repetibles con pytest. |
| F5 | [LlamaIndexAgent](../../../../src/ktsu_ai/infrastructure/agent_infrastructure/llamaindex_agent.py), `run`, y [AgentToolbox](../../../../src/ktsu_ai/application/agent_application/agent_toolbox.py), `_invoke`, `_call_nest` y `_search` | `FunctionAgent` recorre las llamadas del modelo. La aplicación controla nombres, argumentos, alcance, límite de herramientas y modo de operación. El alcance de búsqueda sale de la ejecución y una escritura solicita `prepare`. |
| F6 | [AgentOutcome](../../../../src/ktsu_ai/domain/agent/agent_outcome.py), `AgentOutcome`, `ToolCallRecord` y `PendingConfirmation` | El resultado permite comprobar estados, secuencia de llamadas, argumentos y resumen de confirmación. La autorización de un recurso y la vigencia de su revisión dependen del resultado del lado de Nest. |
| F7 | [Pruebas del agente](../../../../tests/unit/test_agent.py), [pruebas HTTP](../../../../tests/http/test_agent_routes.py) y [prueba del selector](../../../../tests/integration/test_agent_operation_selector.py) | E6.3b ya cubre comportamiento puntual del agente, transporte HTTP y selección del catálogo. El dataset de E6.5 aporta mensajes de usuario, referencias esperadas y criterios comparables entre proveedores. |

## Aplicación y límites

De F1–F3 se toman los escenarios de producto. La adaptación conserva la solicitud y los resultados esperados en un archivo de datos, con guiones sintéticos que sirven para reproducir hoy la interacción de F4–F6. En una ejecución futura con Gemini se reutilizarán las solicitudes y los criterios, dejando que el modelo elija sus propias llamadas y formule su respuesta.

El flujo real de FastAPI permite medir si rechaza una llamada inválida o solicita preparar una escritura. Los rechazos por ID ajeno y por revisión antigua se simulan en el puerto de Nest. El ejemplo decimal comprueba la solicitud de preparación y el resumen devuelto por ese puerto. La autorización entre organizaciones, la vigencia de la revisión, el cálculo oficial y la confirmación humana se comprobarán en la integración real. El timeout de un turno se puede ensayar con un doble local. La cancelación explícita y la cuota por organización siguen los criterios T21–T22 al disponer de E6.4.
