# 04 — Servidor MCP local

Fecha de creación: 2026-11-14  
Estado: Implementado y verificado para el piloto local.  
Ámbito: E6.7 y su adaptador `stdio`.  
Relacionada con: [plan MCP](../../../docs/plans/feature/agente/04-plan-servidor-mcp-local.md), [fuentes MCP](../../../docs/fonts/feature/agente/04-fuentes-del-servidor-mcp.md), [pasarela en Nest](../../../../LearningAllPosibolIt/bitacora-construccion/feature/ai-assistant/12-acceso-mcp-desde-nest.md).  
Revisión de partida: `dad7d5d` con el adaptador y MCP 2.3.0 en el árbol de trabajo.

## Necesidad

Un cliente local debe poder descubrir, leer y preparar propuestas usando el catálogo del proyecto con su credencial. La lección 180 de las fuentes MCP (C1, líneas 19–27) explica el proceso hijo por entrada y salida estándar. El [SDK Python v2](https://py.sdk.modelcontextprotocol.io/client/transports/) documenta el cliente de subproceso para comprobar el protocolo real.

## Implementación

[El lanzador](../../../src/ktsu_ai/bootstrap/mcp.py) configura el subproceso `stdio` con el SDK Python 2.3.0. [El servidor](../../../src/ktsu_ai/mcp_server/server.py) publica el catálogo que Nest autoriza y convierte una preparación en una propuesta revisable. [La pasarela HTTP](../../../src/ktsu_ai/infrastructure/integration_infrastructure/nest_integration_gateway.py) presenta el token del adaptador y la delegación. Nest valida el alcance, ejecuta los servicios de producto y envía la búsqueda a FastAPI por su API interna. Así, el token de servicio de IA queda en los backends.

El [README](../../../README.md#servidor-mcp-local) incluye parámetros de cliente con marcadores y el comando para reproducir el recorrido. Se comprobó el cliente del SDK en negociación automática y en modo de protocolo anterior. El transporte alojado y la autenticación OAuth conservan la etapa 5 de su plan.

## Comprobaciones realmente ejecutadas

| Comprobación | Resultado |
| --- | --- |
| Ruff, formato, mypy e import-linter | Sin errores. Los dos contratos de capas se mantuvieron. |
| Pytest con Qdrant 1.19.1 desechable y exclusión explícita de los marcadores `google` y `gemini` | 153 pruebas pasaron y 12 quedaron fuera por el filtro. |
| [Cliente MCP por subproceso y ambos backends](../../../../LearningAllPosibolIt/test/features/integrations/local-stack.e2e-spec.ts) | El cliente listó, leyó, buscó, preparó una propuesta y recibió rechazo tras revocación. La búsqueda usó LlamaIndex y Qdrant, con documentos propios y ajenos. Nest solo creó la hoja tras la confirmación humana. El chat nativo pasó por el mismo FastAPI con su modelo guionizado. |
| P1, modo de preparación alterado en copia temporal | La prueba detectó que la petición usaba el modo equivocado. |
| P2, delegación omitida en copia temporal | La prueba detectó la falta de la cabecera esperada. |

Una corrida intermedia ejecutó por error las 12 pruebas de Google y Gemini con datos sintéticos. El selector de pytest aceptaba cualquier valor presente, incluido `0`. Se corrigió para exigir el valor `1` y se verificó que con `0` las 12 pruebas se omiten. El importe de esa corrida se desconoce. [Selector de pruebas](../../../tests/conftest.py)
