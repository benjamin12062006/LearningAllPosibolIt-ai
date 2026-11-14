# 04 — Fuentes del servidor MCP para E6.7

Fecha de creación: 2026-11-14  
Estado: Consultada.  
Relacionada con: [plan del servidor MCP](../../../plans/feature/agente/04-plan-servidor-mcp-local.md), [plan del agente](../../../plans/feature/agente/01-plan-agente-con-llm-simulado.md).  
Revisión de partida: FastAPI `d9f00fd`, Nest `7be788b`.

| ID | Evidencia | Aplicación |
| --- | --- | --- |
| H1 | [Diseño 15](../../../../../docs-diagrams/15-chat-ia-herramientas-y-propuestas.md), «Herramientas de la primera versión». | Mantener el catálogo de Nest y las confirmaciones humanas al exponer herramientas en MCP. |
| E1 | [`NestOperationGateway`](../../../../src/ktsu_ai/infrastructure/agent_infrastructure/nest_operation_gateway.py) y [`RunIdentity`](../../../../src/ktsu_ai/domain/agent/agent_run.py). | Reutilizar `execute` y `prepare` con credencial acotada a un `runId`. |
| E2 | [`AgentToolbox`](../../../../src/ktsu_ai/application/agent_application/agent_toolbox.py), validación de operaciones y límites. | Mantener los mismos permisos, esquemas y presupuesto para el acceso por MCP. |
| C1 | [Exercise Code an MCP Server](</Users/benji/Documents/chrome-extencions/trancripciones/Python/Aplicaciones GenAI y Sistemas Multiagente/Sección 16 Model Context Protocol (MCP)/179. Exercise Code an MCP Server.md>), líneas 13–21, y [MCP messaging and transport](</Users/benji/Documents/chrome-extencions/trancripciones/Python/Aplicaciones GenAI y Sistemas Multiagente/Sección 16 Model Context Protocol (MCP)/180. MCP messaging and transport.md>), líneas 19–27. | El curso muestra una herramienta Python expuesta por el SDK y la ejecución local como subproceso. El catálogo dinámico y la identidad por ejecución proceden de KTSU. |
| F1 | [Especificación MCP, Tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools), «Capabilities» y «Protocol Messages», consultada el 2026-11-14. | `tools/list` admite listas dependientes de credenciales. `tools/call` usa nombre y argumentos con esquema y puede devolver un error de herramienta. |
| F2 | [Especificación MCP, Transports](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports) y [SDK oficial Python](https://py.sdk.modelcontextprotocol.io/), consultados el 2026-11-14. | Para el piloto local, comprobar `stdio` con el SDK Python y el cliente que usará el usuario. Validar versiones en la etapa de instalación. |
| F3 | [OpenAI, Connect and test your plugin](https://developers.openai.com/plugins/deploy/connect-chatgpt) y [Authentication](https://developers.openai.com/plugins/build/auth), consultadas el 2026-11-14. | ChatGPT alojado requiere un endpoint alcanzable mediante HTTPS o Secure MCP Tunnel. Las herramientas con acceso a datos de cuenta requieren OAuth con audiencia y alcance comprobados. |

| Necesidad | Requisito y fuentes | Decisión prevista |
| --- | --- | --- |
| Usar el agente desde un cliente MCP local | H1, E1–E2, C1, F1–F2 | Reutilizar catálogo y gateway con un adaptador MCP. |
| Revocar el acceso y mantener el control humano | H1, E1–E2, F1 | Verificar vigencia en listados y llamadas, preparar propuestas y confirmarlas en Nest. |
