# 05 — OAuth de Descope para el servidor MCP

Fecha de creación: 2026-11-14  
Estado: Implementado y verificado en local. Activación en Descope pendiente.  
Relacionada con: [plan 05](../../../docs/plans/feature/agente/05-plan-oauth-mcp-descope.md), [fuentes 05](../../../docs/fonts/feature/agente/05-fuentes-oauth-mcp-descope.md).

El cliente remoto descubre Descope desde el MCP. Nest conserva la autoridad sobre los proyectos y efectos.

- El [servidor HTTP](../../../src/ktsu_ai/bootstrap/mcp_http.py) publica la metadata y usa Streamable HTTP sin sesión del transporte. La credencial vive en el contexto de su petición. El cliente y Descope mantienen el estado de OAuth.
- [Nest](../../../../LearningAllPosibolIt/src/integrations/mcp-oauth-access.ts) comprueba el JWT y cruza sus scopes con un grant revocable. Se reutiliza el permiso de proyecto actual y la confirmación humana de propuestas. El Resource queda vinculado al proyecto del piloto.
- El [script de administración](../../../../LearningAllPosibolIt/scripts/descope/ensure-mcp-resource.mjs) prepara el Resource por URI y comprueba su existencia antes de crearlo. Se probó la vista previa. La consulta con la configuración real devolvió HTTP 403. Falta la URL HTTPS del servicio de KTSU para registrar una audiencia real.

## Comprobaciones

- Nest completó compilación, lint, formato, 14 pruebas enfocadas y tres comprobaciones de base. Una prueba usa el SDK Descope real con una clave RSA de prueba y rechaza firma, audiencia e issuer incorrectos. La prueba HTTP de Nest cubre grant, scopes, otro titular y revocación.
- El recorrido anterior del MCP local pasó de nuevo con Nest y FastAPI. Las 41 migraciones se aplicaron en PGlite y `prisma migrate diff` devolvió una migración vacía.
- Las 137 pruebas ejecutadas de Python pasaron. Se verificaron metadata, desafío Bearer, listado y ejecución HTTP con el SDK MCP en modos actual y anterior, dos clientes concurrentes y revocación. Los marcadores de Google y Gemini se excluyeron.
- El [plan de UI](../../../../LearningAllPosibolIt-web/docs/plans/feature/integrations/01-plan-mcp-oauth-descope.md) vincula la sesión de Nuxt con la autorización de proyecto y deja el consentimiento y los tokens en el cliente MCP.
