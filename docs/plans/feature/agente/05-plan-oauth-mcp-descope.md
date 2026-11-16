# 05 — OAuth de Descope para el MCP remoto

Fecha de creación: 2026-11-14  
Estado: Implementado y verificado en local. Alta y prueba del Resource de staging pendientes.  
Relacionada con: [fuentes 05](../../../fonts/feature/agente/05-fuentes-oauth-mcp-descope.md), [plan MCP local](04-plan-servidor-mcp-local.md).

1. Montar una entrada Streamable HTTP con URL HTTPS canónica. Publicar metadata RFC 9728 y desafío de autorización. Reutilizar el adaptador MCP y el SDK Python fijado.
2. Registrar un Resource de Descope por URL. Usar un único proyecto KTSU configurado por instancia para el piloto. La pantalla Integraciones usa el endpoint confirmado del proyecto. JWT de OAuth con scopes `ktsu:mcp:read` y `ktsu:mcp:prepare`. El segundo solo permite preparar efectos.
3. En Nest, emitir un grant mediante la sesión humana y reutilizar las rutas de listado, revocación y confirmación. El token del cliente y el grant se validan antes de devolver herramientas o resultados. Seleccionar por sujeto y por URL de recurso, con rol y proyecto actuales.
4. Probar con JWT firmado de prueba, PGlite y cliente MCP HTTP. Verificar con Descope y el cliente final al disponer de la URL pública y acceso administrativo al Resource.

## Activación en staging

- Publicar el servidor HTTP bajo una URL estable del entorno. El endpoint del agente es el de KTSU. El MCP de administración de Descope administra el proyecto de identidad.
- Registrar esa URL en Descope con consentimiento de usuario. Verificar Discovery. En entornos con Project Issuer, DCR se activa en Project Settings → OIDC y se revisa para el proyecto de staging. En entornos con MCP Server Issuer, se gestiona en el propio Resource. [Registro de clientes](https://docs.descope.com/agentic-identity-hub/core-components/mcp-servers/registration-methods)
- Ejecutar la [guía de activación](../../../../README.md#mcp-remoto-con-descope) y probar un inicio de sesión desde el cliente externo antes de etiquetar la conexión como verificada. La Management API devolvió 403 durante el inventario y todavía falta una URL pública de KTSU.
