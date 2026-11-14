# 03 — Fuentes de Gemini como modelo del agente (segunda parte de E6.5)

Fecha de creación: 2026-11-13  
Estado: Cerrada para el plan 03 del agente.  
Revisión de partida: `3f603cc` (`main`).  
Relacionada con: [plan 03](../../../plans/feature/agente/03-plan-gemini-para-el-agente.md), [fuentes 01 del agente](01-fuentes-del-agente.md), [fuentes 02 de la evaluación](02-fuentes-de-la-evaluacion-del-agente.md), [plan E6 de la API](../../../../../LearningAllPosibolIt/docs/plans/feature/ai-assistant/01-plan-e6-ia-con-qdrant-y-llamaindex.md) (D5, D10).

## Decisión del usuario (2026-11-13)

El modelo de chat es **`gemini-3.5-flash-lite`**, elegido de la lista real de Vertex AI del proyecto `estadistica-forms-api` (126 modelos base; `client.models.list`). Debe poder cambiarse por el entorno (`CHAT_MODEL`), sin tocar el código. Acepta el coste de las llamadas de esta etapa.

## Documentación oficial (F)

| ID | Fuente (consulta: 2026-11-13) | Qué se observa |
| --- | --- | --- |
| F1 | Vertex AI, ficha del modelo: `docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/3-5-flash-lite` | ID `gemini-3.5-flash-lite`. Llamada a funciones «Supported». Contexto de 1.048.576 tokens y salida máxima de 65.536. Ubicaciones: `global`, los multirregión `us` y `eu`, y `asia-south1`; **no** `us-central1`. Por defecto razona en nivel mínimo (MINIMAL, LOW, MEDIUM, HIGH) y, para subagentes que llaman a APIs, recomienda MEDIUM o HIGH, porque el mínimo puede provocar un «premature tool termination on multi-step tasks». |
| F2 | Vertex AI, precios: `cloud.google.com/vertex-ai/generative-ai/pricing` (descargada y leída la fila del modelo) | Gemini 3.5 Flash-Lite, `global`: **0,30 $** por millón de tokens de entrada y **2,50 $** por millón de salida («response and reasoning»); caché de entrada, 0,03 $. Fuera de `global`: 0,33 $ y 2,75 $. La página no muestra fecha de actualización. |
| F3 | PyPI, `llama-index-llms-google-genai` | 0.12.0 publicada el 2026-11-14 (UTC); **0.11.3** el 2026-10-14. 0.11.3 requiere `google-genai<3,>=1.52.0` y `llama-index-core<0.15,>=0.14.5`, compatibles con las versiones fijadas (2.32.0 y 0.14.25). |
| F4 | `google-genai` 2.32.0 instalado: `types.FunctionDeclaration` | Tiene `parameters` (tipo `Schema` de Google) y `parameters_json_schema` (JSON Schema tal cual). `types.ThinkingConfig` tiene `thinking_level`. |

## Estado del código y experimentos (E)

| ID | Dónde | Qué se observa |
| --- | --- | --- |
| E1 | `bootstrap/app.py`, `create_app_from_environment` | No se crea ningún modelo de chat: la ruta del agente responde siempre 503. `create_app` exige `NEST_AGENT_BASE_URL` cuando recibe un modelo. |
| E2 | `.venv/…/llama_index/llms/google_genai/base.py:189-300` | `GoogleGenAI(model, vertexai_config, generation_config, max_tokens, context_window, max_retries, http_options…)`. Con `vertexai_config` no usa clave de API. **Si faltan `max_tokens` o `context_window`, llama a Google de forma síncrona al crearse** (`client.models.get`). Con `generation_config` propio no añade `max_output_tokens`. |
| E3 | `…/google_genai/base.py:532-590` y `utils.py:498-520` | Declara cada herramienta con `parameters=_transformers.t_schema(client, fn_schema)`. |
| E4 | Experimento con los esquemas de `tests/evaluation/agent_cases.json` | `t_schema` acepta `additionalProperties`, pero **falla con `uniqueItems`** («Extra inputs are not permitted») en `propose_price_increase`. Con Gemini, una operación de Nest con una palabra clave no soportada rompería la ejecución. |
| E5 | Experimento: llamada real con `parameters_json_schema` y ese mismo esquema | Gemini pidió `propose_price_increase` con `{"rowIds": ["r1", "r3"], "sheetId": "inventario", "percent": "5.25"}`: respeta el esquema completo. 89 tokens de entrada, 43 de salida y 419 de razonamiento. |
| E6 | Experimento: «Responde solo con la palabra: listo» con `thinking_level="MEDIUM"` | En `global`: respuesta correcta en 2,73 s (8 de entrada, 2 de salida y 121 de razonamiento). En `us-central1`: **404 NOT_FOUND**. Confirma F1: el chat necesita su propia ubicación, distinta de la de los embeddings. |
| E7 | Experimento sin red | `GoogleGenAI` con `context_window` y `max_tokens` y credenciales anónimas se crea sin llamar a Google: sirve para pruebas sin credenciales. |
| E8 | `.venv/…/llama_index/core/instrumentation/events/llm.py:239` | `LLMChatEndEvent` lleva la respuesta. El conector pone en `additional_kwargs` `prompt_tokens`, `completion_tokens` y `total_tokens`, y en `raw["usage_metadata"]` los de razonamiento (`utils.py:167-180`). |
| E9 | Las credenciales de la cuenta (ADC) | Tenían como proyecto de cuota `business-managment-rs`, sin Vertex AI: 403 `SERVICE_DISABLED`. El usuario lo corrigió con `gcloud auth application-default set-quota-project estadistica-forms-api`, y después Vertex respondió sin forzar nada. |
| E10 | `LearningAllPosibolIt/src/main.ts:11` | Nest escucha en `127.0.0.1:8080` (`PORT`). |

## Cursos (C)

| ID | Lección | Qué aporta |
| --- | --- | --- |
| C1 | `LlamaIndex para Aplicaciones LLM/Sección 7/54. LlamaIndex Latest- Upgrading code to.md`, líneas 13–17 (ya citada como C5 en la [ficha de la base](../base-del-servicio/01-fuentes-de-la-base-del-servicio.md)) | Un paquete por integración: solo se instala el conector de Gemini. |
| C2 | Sección 5, `43. Function Calling…`, líneas 15–21 ([ficha 01](01-fuentes-del-agente.md), C5) | El modelo recibe el esquema JSON de cada herramienta: debe llegar completo. |
| C3 | Sección 5, `45. Agents In Production.md`, líneas 13–25 ([ficha 01](01-fuentes-del-agente.md), C7–C9) | Cada paso es una llamada pagada y secuencial: medir latencia y coste por caso, y validar la salida del modelo. |
| C4 | `FastAPI Completo/Sección 9…/147. Errores comunes.md`, líneas 13–17 ([ficha de la base](../base-del-servicio/01-fuentes-de-la-base-del-servicio.md), C11) | Una llamada síncrona en una ruta asíncrona bloquea el servidor. Por eso se pasan `context_window` y `max_tokens` (E2). |

## Mapa necesidad → fuentes → decisión

| Necesidad | Fuentes | Decisión (plan 03) |
| --- | --- | --- |
| Modelo por entorno | Usuario; E1 | `CHAT_MODEL` vacío deja el agente desactivado; con valor, se crea Gemini al arrancar |
| Ubicación | F1, E6 | `CHAT_LOCATION`, `global` por defecto, aparte de `GOOGLE_CLOUD_LOCATION` |
| Esquemas de Nest completos | C2, E3–E5, F4 | Subclase del conector que declara con `parameters_json_schema` |
| Arranque sin bloquear | E2, E7, C4 | `context_window` de 1.048.576 y `max_tokens` (`CHAT_MAX_OUTPUT_TOKENS`) explícitos |
| Razonamiento | F1 | `CHAT_THINKING_LEVEL`, `MEDIUM` por defecto (agente que llama a APIs) |
| Sin claves de API | D5 del plan E6; E2 | `vertexai_config` con ADC |
| Coste y latencia | F2, C3, E8 | Evaluación con los casos de la [ficha 02](02-fuentes-de-la-evaluacion-del-agente.md), tokens de `LLMChatEndEvent` y precios de F2 |
