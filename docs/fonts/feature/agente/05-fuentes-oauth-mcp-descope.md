# 05 — Fuentes para OAuth del MCP remoto

Fecha de creación: 2026-11-14  
Relacionada con: [fuentes del MCP local](04-fuentes-del-servidor-mcp.md).

| Evidencia consultada el 2026-11-14 | Decisión en KTSU |
| --- | --- |
| [Descope y MCP](https://docs.descope.com/mcp), roles de Resource Server y Authorization Server | Descope controla el registro, consentimiento, PKCE y emisión. KTSU publica metadata y valida el acceso antes de entregar herramientas. |
| [Discovery de Descope](https://docs.descope.com/agentic-identity-hub/core-components/mcp-servers/discovery-url), issuer y JWKS | Configurar el issuer exacto del Resource y validar el audience exacto del MCP. El SDK normaliza el issuer verificado al ID del proyecto de Descope. Nest usa ese ID y `sub` para encontrar el mismo perfil web. |
| [Administración de Resources](https://docs.descope.com/agentic-identity-hub/core-components/mcp-servers/management), URI, scopes y acceso | Crear un Resource `mcp` con URL pública exacta, dos scopes y acceso de usuario. Denegar client credentials. Consultar por URI antes de crear. |
| [OAuth Protected Resource Metadata](https://www.rfc-editor.org/rfc/rfc9728.html#name-obtaining-protected-resource) y [SDK Python](https://py.sdk.modelcontextprotocol.io/client/transports/) | Publicar la metadata con la ruta del recurso, responder con el desafío Bearer y reutilizar Streamable HTTP del SDK. |
| [Pasarela y contrato actual](../../../../../LearningAllPosibolIt/contracts/integrations/README.md) | Nest impone grant revocable, membresía, rol y alcance. Los scopes OAuth limitan la capacidad del grant y las propuestas conservan su confirmación humana. |
