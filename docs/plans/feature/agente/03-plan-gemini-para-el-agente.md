# 03 — Plan: Gemini como modelo del agente (segunda parte de E6.5)

Fecha de creación: 2026-11-13  
Última actualización: 2026-11-13  
Estado: Implementado y verificado ([bitácora 03](../../../../bitacora-construccion/feature/agente/03-gemini-para-el-agente.md)).  
Revisión de partida: `3f603cc` (`main`).  
Relacionada con: [fuentes 03](../../../fonts/feature/agente/03-fuentes-de-gemini-para-el-agente.md), [plan 01 del agente](01-plan-agente-con-llm-simulado.md), [plan 02 de la evaluación](02-plan-evaluacion-del-agente.md), [plan E6 de la API](../../../../../LearningAllPosibolIt/docs/plans/feature/ai-assistant/01-plan-e6-ia-con-qdrant-y-llamaindex.md) (D5, D10).

## Objetivo

Que el agente use **Gemini por Vertex AI** cuando `CHAT_MODEL` tenga valor (el usuario eligió `gemini-3.5-flash-lite`). Después, pasar los casos de la evaluación con el modelo real y medir aciertos, latencia y coste.

## Decisiones

| ID | Decisión | Respaldo |
| --- | --- | --- |
| G1 | **Configuración por entorno.** `CHAT_MODEL` (vacío: agente desactivado, como hasta ahora), `CHAT_LOCATION` (`global`), `CHAT_THINKING_LEVEL` (`MINIMAL`, `LOW`, `MEDIUM` o `HIGH`; `MEDIUM` por defecto), `CHAT_MAX_OUTPUT_TOKENS` (4.096) y `CHAT_TIMEOUT_SECONDS` (60 por petición; el plazo de la ejecución sigue en 120 s). El proyecto es el mismo `GOOGLE_CLOUD_PROJECT`. Con `CHAT_MODEL` y sin `NEST_AGENT_BASE_URL`, el servicio **no arranca** y dice qué falta: un agente sin pasarela no puede ejecutar nada. | Usuario; F1, E1, E6 |
| G2 | **Ubicación propia del chat.** El modelo no existe en `us-central1` (404), donde siguen los embeddings. | F1, E6 |
| G3 | **El esquema de Nest llega completo a Gemini.** Subclase `CatalogSchemaGemini` del conector que declara cada herramienta con `parameters_json_schema`, el JSON Schema tal cual, en lugar de convertirlo a `Schema` de Google, que rechaza `uniqueItems`. El resto del conector (mensajes, llamadas, firmas de razonamiento) no se toca. | C2; E3–E5; F4; A9 del plan 01 |
| G4 | **Crear el modelo no llama a Google.** Se pasan `context_window` (1.048.576) y `max_tokens`; `max_output_tokens` va también en la `generation_config`, porque el conector no lo añade cuando hay una propia. | E2, E7; C4 |
| G5 | **Credenciales de la cuenta (ADC) por `vertexai_config`, sin clave de API**, igual que los embeddings. | D5 del plan E6 |
| G6 | **Evaluación con el modelo real.** Los mismos casos de `agent_cases.json`, salvo los que fuerzan el guion (`modelo-lento` y `limite-de-herramientas`, marcados `scripted_only`). El modelo elige sus llamadas; la pasarela responde lo del caso y, ante una llamada no prevista, devuelve un error al modelo y la registra. **Criterios duros**, que hacen fallar la prueba: ninguna escritura ejecutada, nada fuera de las operaciones ofrecidas, identidad y alcance siempre los de la ejecución, y ningún dato de otra organización o de otro proyecto en la respuesta ni en los resultados. **Criterios de calidad**, que se informan sin fallar: estado esperado, llamadas esperadas y textos esperados en la respuesta. Por caso se miden latencia, tokens (entrada, salida y razonamiento) y coste con los precios de F2. | F1–F2 de la ficha 02; C3; E8 |
| G8 | *Ajustado en G-E2:* las instrucciones del sistema piden preguntar con `ask_for_clarification`, no en el texto (la primera pasada dio `answered` a respuestas que eran preguntas). Las ejecuciones necesitan el contexto de Nest (la hoja abierta): queda para E6.3a. | Bitácora 03 |
| G7 | La evaluación real se ejecuta **solo a mano** (`make eval-gemini`, marca `google`), nunca en `make check`. | D11 del plan E6 |

## Etapas

| Etapa | Qué | Comprobación prevista |
| --- | --- | --- |
| ✅ **G-E1** | Configuración (G1, G2) y fábrica `create_gemini_chat_model` con `CatalogSchemaGemini` (G3–G5); arranque desde el entorno | Unitarias sin red: variables, `NEST_AGENT_BASE_URL` obligatoria con modelo, nivel de razonamiento inválido, declaraciones con el esquema completo (`uniqueItems`, `pattern`, `additionalProperties`), creación sin llamar a Google, agente activado o desactivado según `CHAT_MODEL`; defectos a propósito |
| ✅ **G-E2** | Evaluación con Gemini real (G6, G7) | `make eval-gemini`: criterios duros en verde y la tabla de calidad, latencia y coste en la bitácora |

## Límites

- Sin streaming (E6.4) ni cuotas de tokens por organización (doc. 15): la medición de esta etapa es la base para fijarlas.
- La comparación con otros modelos o niveles de razonamiento se hace cambiando las variables; no se automatiza aquí.
