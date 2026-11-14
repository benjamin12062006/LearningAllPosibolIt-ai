# 04 — Plan del servidor MCP para clientes externos

Fecha de creación: 2026-11-14  
Última actualización: 2026-11-14  
Estado: Plan.  
Ámbito: FastAPI y catálogo de Nest, E6.7.  
Relacionada con: [fuentes 04](../../../fonts/feature/agente/04-fuentes-del-servidor-mcp.md), [plan del agente](01-plan-agente-con-llm-simulado.md), [plan E6](../../../../../LearningAllPosibolIt/docs/plans/feature/ai-assistant/01-plan-e6-ia-con-qdrant-y-llamaindex.md), [acceso externo y CLI](../../../../../LearningAllPosibolIt/docs/plans/feature/ai-assistant/07-plan-acceso-externo-y-cli.md).  
Revisión de partida: FastAPI `d9f00fd`, Nest `7be788b`.

## Objetivo

Un cliente externo puede descubrir y ejecutar las herramientas autorizadas por Nest. Una propuesta de escritura aparece para confirmación humana en el mismo flujo de la API. El recorrido empieza con un cliente local y añade el transporte autenticado para clientes alojados.

| Entrada | Recorrido |
| --- | --- |
| Chat de KTSU | Nuxt → Nest → FastAPI → Gemini. Nest guarda la conversación y decide acceso y efectos. |
| MCP externo | Codex, Claude Code o cliente compatible → servidor MCP de FastAPI. El cliente usa su propio modelo. FastAPI pide a Nest la autorización del proyecto, consulta LlamaIndex y Qdrant para conocimiento y pasa las lecturas oficiales y propuestas por la pasarela de integración. |
| CLI | Terminal o agente local → CLI de KTSU → API Nest. Para una operación de conocimiento habilitada, Nest autoriza el proyecto y usa FastAPI por HTTP interno. |

| ID | Decisión propuesta | Evidencia |
| --- | --- | --- |
| D1 | Alojar el servidor MCP en el proyecto FastAPI. Para el piloto, arrancar su adaptador `stdio` como subproceso del cliente desde un comando del mismo proyecto Python. El HTTP del chat arranca con su proceso habitual. Verificar el SDK y el cliente antes de fijar la versión en `uv.lock`. Escribir diagnóstico en `stderr` y mensajes MCP en `stdout`. | C1 y F2 |
| D2 | Obtener de Nest el catálogo filtrado para el proyecto y la delegación autorizados. `tools/list` produce esquemas deterministas y `tools/call` usa esos nombres y argumentos. Nest valida credencial, ámbito, cuota y permiso al listar y al llamar. | H1, E1–E2 y F1 |
| D3 | Nest emite un acceso temporal con audiencia MCP y alcance de proyecto para el cliente autorizado. FastAPI se identifica ante la pasarela interna de integración y transmite el contexto delegado. Nest valida identidad, audiencia, expiración, revocación, membresía y permisos actuales. Cualquier credencial efímera para una operación se emite internamente. | E1 y H1 |
| D4 | Enviar lecturas en `execute` y escrituras en `prepare` a través del mismo catálogo y servicios de dominio. El resultado de una escritura incluye la propuesta pendiente. La confirmación pertenece al actor humano autenticado por Nest. | H1 y E1 |
| D5 | Probar `stdio` con Codex y Claude Code locales. Para ChatGPT alojado, probar Streamable HTTP autenticado con OAuth en un endpoint HTTPS alcanzable o mediante Secure MCP Tunnel y publicar en la UI solo capacidades verificadas. | F2–F3 |
| D6 | Cuando el catálogo MCP habilite `search_knowledge`, verificar en Nest la delegación, operación, cuota y ámbito. Usar el ámbito devuelto por Nest para consultar LlamaIndex y Qdrant desde FastAPI. Revalidar antes de entregar resultados si la consulta cruzó servicios. La forma del texto y los argumentos del cliente no pueden ampliar el subconjunto autorizado. | H1, E1–E2, F1 y [contrato de acceso externo](../../../../../LearningAllPosibolIt/docs/plans/feature/ai-assistant/07-plan-acceso-externo-y-cli.md). |

## Incrementos y comprobaciones

1. Tras E6.6 y la prueba local de las APIs, contrastar el contrato real de ejecuciones, presupuesto y propuestas. Validar el mecanismo de emisión y listado para MCP con vencimiento y pertenencia vigentes.
2. Añadir mapeo de esquemas y resultados como adaptador fino, reutilizando validación del catálogo y pasarela aprobada. Probar herramientas desconocidas y prohibidas, datos fuera del alcance, argumentos extra y credencial vencida o revocada.
3. Ejecutar un subprocess real con cliente MCP. Listar herramientas, hacer una lectura y preparar una propuesta. Comprobar que se conserva el estado oficial del recurso hasta la revisión humana. Incluir dos organizaciones y verificar que el catálogo de MCP coincide con el autorizado en Nest.
4. Ejecutar Ruff, mypy, import-linter y pytest, las comprobaciones de Nest que correspondan, y defectos deliberados en copia temporal. Cerrar con una bitácora en FastAPI y el ejemplo de configuración local sin valores secretos.
5. Validar el contrato de la página Integraciones para copiar o descargar los archivos y el prompt de configuración por cliente. Probar el recorrido remoto con la infraestructura autorizada, incluyendo una sesión OAuth y acceso revocado. La UI presenta el estado de esta capacidad según la disponibilidad real del backend.

En el recorrido local de D6, sembrar marcadores distintos en dos proyectos de la misma organización y en otra organización. La búsqueda con LlamaIndex y Qdrant responde con resultados del proyecto concedido; pruebas de credencial vencida, revocación durante la consulta y argumentos de otro ámbito comprueban que la búsqueda respeta la decisión de Nest. Probar el chat nativo por su contrato HTTP y las lecturas y propuestas del servidor MCP por la pasarela de integración.

El montaje remoto queda para después de probar el flujo local y su política de autorización. La página Integraciones entrega comandos, enlaces y archivos de la versión comprobada. [Contexto de Integraciones](../../../../../CONTEXTO-SIGUIENTE-CHAT-UI.md).
