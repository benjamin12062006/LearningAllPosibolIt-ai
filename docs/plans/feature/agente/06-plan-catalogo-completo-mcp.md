# 06 — Completar el catálogo y la revisión de operaciones en MCP

Fecha de creación: 2026-11-21  
Estado: Plan  
Revisión de partida: `feature/ia-contexto` desde `bdf72e0`. MCP de Vercel usa la rama `deploy/vercel-mcp` con la metadata de solo lectura de `ffbb15c`.  
Relacionada con: [MCP local](04-plan-servidor-mcp-local.md), [OAuth de Descope](05-plan-oauth-mcp-descope.md), [plan interno del asistente](../../../../../api/docs/plans/feature/ai-assistant/10-plan-ia-con-contexto-memoria-y-toon.md) y [plan de CLI y matriz de las 18 operaciones](../../../../../api/docs/plans/feature/cli/02-plan-catalogo-completo-y-distribucion-cli.md).

## Objetivo

Dar a MCP local y remoto el mismo catálogo externo que a la CLI para un mismo proyecto, rol y capacidad. Incluir las 18 operaciones nuevas de borradores, hojas, vistas, mapeos, catálogo y configuración del feed, con su recorrido de revisión en la web.

## Flujo y entregas

1. **Nest publica el catálogo.** Añadir las operaciones a la lista externa compartida descrita en el plan CLI. Fijar sus esquemas MCP con los IDs que el cliente debe especificar. Conservar los nombres públicos y los resultados estructurados. Comprobar que `tools/list` coincide con `ktsu operations list` para el mismo alcance y que una llamada directa a una herramienta fuera de esa lista recibe un rechazo. [Pasarela Nest](../../../../../api/src/integrations/integration-gateway.service.ts)
2. **Python traduce el protocolo.** Reutilizar `build_mcp_server` y `NestIntegrationGateway` en `stdio` y HTTP. Revisar el límite del cliente Python de 64 operaciones después de sumar las nuevas y cubrir el catálogo completo en una prueba. Preservar códigos de rechazo y datos JSON para los clientes MCP. El histórico del chat, la ficha inicial y la representación TOON siguen siendo contexto del agente interno. Un asistente externo puede obtener ficha y conocimiento con `get_project_overview` y `search_knowledge`. [Servidor MCP](../../../../src/ktsu_ai/mcp_server/server.py) · [Adaptador Nest](../../../../src/ktsu_ai/infrastructure/integration_infrastructure/nest_integration_gateway.py)
3. **La persona revisa las escrituras.** Cada herramienta de escritura prepara una propuesta con resumen, IDs y enlace. En Nuxt, abrir la revisión del proyecto, aplicar o rechazar y mostrar el estado final con su motivo si falla. Comprobar que el permiso que produjo la propuesta sigue vigente al confirmar. Para cerrar el ciclo desde el asistente, ofrecer el estado de la propuesta o leer la entidad resultante. La descarga por exportación usa el enlace generado tras la revisión.
4. **Activar scopes por etapas.** Publicar primero las lecturas con el scope remoto vigente `ktsu:mcp:read`. Para preparación, habilitar `ktsu:mcp:prepare` en Descope, metadata y el alta del proyecto, tras verificar que el servidor externo exige revisión humana y que la autorización está limitada al proyecto. Mantener la vía local con credencial `mcp` y su capacidad explícita. En Nuxt, distinguir **Solo lectura** de **Lectura y propuestas** y documentar el paso de renovar una autorización al ampliar el scope. [Servidor HTTP](../../../../src/ktsu_ai/bootstrap/mcp_http.py) · [Guía de despliegue](../../../../../../../deploys/docs/plans/07-plan-activar-mcp-y-cli-en-vercel.md)
5. **Desplegar en orden.** Aplicar las migraciones verificadas antes de publicar Nest. Probar el catálogo contra un entorno aislado, publicar la pasarela y actualizar `KTSU_NEST_URL` en `ktsu-mcp` al nuevo origen privado. Mantener la entrada de contenedor MCP y su autenticación exclusiva al actualizar su rama. Verificar el rechazo de la pasarela desde los dominios públicos y la respuesta de `/mcp`. Publicar la pantalla de revisión cuando las interfaces de Nest y MCP sean compatibles.

## Comprobación prevista

- Probar en `stdio` y Streamable HTTP el catálogo completo, un proyecto ajeno y roles de lectura y preparación. Incluir las 18 operaciones en una matriz de descubrimiento, entrada, efecto previo a la confirmación y resultado posterior. Verificar pares de casos para reintento, revocación y propuesta fallida.
- En Codex, completar login, descubrir herramientas y leer **Personal · Prueba**. Con una concesión de preparación y un proyecto desechable, comprobar el ciclo entero desde la propuesta hasta el resultado observado. Probar que un JWT de lectura no descubre ni ejecuta escrituras y que una credencial CLI no cruza la pasarela MCP.
