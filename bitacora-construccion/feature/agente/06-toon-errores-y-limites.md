# 06 — TOON, errores y límites del agente

Fecha de creación: 2026-11-21  
Estado: Implementado y verificado  
Revisión de partida: `bdf72e0` (`deploy/vercel`), rama `feature/ia-contexto`  
Relacionada con: [plan 10 de Nest, etapa E1](../../../../LearningAllPosibolIt/docs/plans/feature/ai-assistant/10-plan-ia-con-contexto-memoria-y-toon.md), [fuentes 12](../../../../LearningAllPosibolIt/docs/fonts/feature/ai-assistant/12-fuentes-ia-con-contexto-memoria-y-toon.md) y la [bitácora 03 de Gemini](03-gemini-para-el-agente.md).

## Necesidad

El agente recibía los resultados en JSON con espacios y los cortaba en 16.000 caracteres, dejando el JSON roto. Agotados 64 KB, los entregaba vacíos sin avisar. Solo entendía los errores 400, 403, 404 y 409. Sus límites (20 llamadas, 24 turnos, 120 s y razonamiento `HIGH`) cortaban las tareas de varios pasos (fuentes 12: E8–E10 y E15).

## Evidencia → decisión → aplicación

| Evidencia | Decisión (plan 10) | Aplicación |
| --- | --- | --- |
| F2, F3 y M1: `toon-format` 1.2.0 pasa los 160 fixtures oficiales | D3: TOON con la librería oficial, fijada | `pyproject.toml` y `uv.lock`: `toon-format==1.2.0` |
| M4 y M5: una lista dentro de cada fila impide la tabla | D3: separar sin pérdida antes de codificar | [`model_text.py`](../../../src/ktsu_ai/application/agent_application/model_text.py): `separate_nested_lists` y `to_model_text` |
| E15: resultados en `json.dumps` | D3: todo lo que va al modelo pasa por `model_text` | [`agent_toolbox.py`](../../../src/ktsu_ai/application/agent_application/agent_toolbox.py): `_for_model`, `knowledge_rows` |
| E9: recorte a ciegas y resultados vacíos | D2: recorte por líneas, con aviso y nunca vacío | `AgentToolbox._fit` y `_cut_at_line` |
| E8: solo cuatro estados de error | D4: cualquier 4xx salvo el 401, con su código y en el idioma de la ejecución | [`nest_operation_gateway.py`](../../../src/ktsu_ai/infrastructure/agent_infrastructure/nest_operation_gateway.py): `_is_nest_rejection` y `_rejection`; `OperationFailedError.for_model` |
| E10 y F1 | D2: 40 llamadas, 48 turnos, 180 s y `MEDIUM` por defecto | `MAX_TOOL_CALLS`, `MAX_MODEL_TURNS`, `RUN_TIMEOUT_SECONDS` y `chat_thinking_level` |

## Cómo queda

- `separate_nested_lists` copia el valor. En una lista de objetos con identificador común (`rowId`, `id`, `columnId`, `changesetId` o `revisionId`), cada campo que en todos los elementos es una lista de objetos sale a una tabla hermana `<lista>.<campo>`, con la clave del padre en cada hija. No separa si una hija ya trae esa clave, si la lista tiene primitivos, si el «identificador» es un booleano o si el nombre hermano ya existe. La prueba `test_nothing_is_lost_the_original_can_be_rebuilt` recompone el original.
- `AgentToolbox._fit` admite hasta 60 KB por resultado y 512 KB por ejecución. Si algo no cabe, corta en el último salto de línea y añade «[Resultado recortado: se muestran X de Y caracteres…]». Si ya no queda espacio útil, dice que se agotó y nunca devuelve un texto vacío.
- `OperationFailedError` conserva `str(error)` en español (lo sigue usando el MCP) y añade `code`, `english` y `for_model(language)`, que devuelve «`CÓDIGO`: mensaje».
- Las búsquedas de conocimiento locales pasan a filas iguales (`sourceType`, `sourceId`, `score`, `text`) antes de TOON.

## Ajustes al escribir el código

- **Turnos: 48, no 40.** Con 40 turnos y 40 llamadas, el límite de turnos llegaba antes que el de llamadas, y el caso `limite-de-herramientas` terminaba en «answered». Se mantiene la proporción anterior (24 para 20). El plan 10 lo recoge como ajuste de D2.
- `NEST_REJECTIONS` desaparece de la pasarela del agente. La pasarela de integraciones tiene su propio conjunto y no se tocó.

## Comprobaciones realmente ejecutadas

- `ruff check`, `ruff format --check`, `mypy --strict` (99 archivos) e `import-linter` (2 contratos): todo en verde.
- `pytest`: **170 pasan y 30 se omiten** (Qdrant y Google reales). La línea base era 146 y 30. Hay 24 pruebas nuevas en [`test_model_text.py`](../../../tests/unit/test_model_text.py), [`test_nest_operation_gateway.py`](../../../tests/unit/test_nest_operation_gateway.py) y [`test_agent.py`](../../../tests/unit/test_agent.py).
- Se actualizaron las aserciones que dependían del JSON (`"rows": 4` → `rows: 4`), el caso de evaluación `limite-de-herramientas` (41 llamadas, 40 aceptadas) y la configuración (`gemini-3.5-flash`, `MEDIUM`).
- Medición con el módulo real y `countTokens` de `gemini-3.5-flash`:

| Carga | Antes (JSON) | Ahora (TOON) |
| --- | --- | --- |
| `query_rows`, 50 filas | 19.712 | 4.503 (−78 %) |
| `query_rows`, 50 filas y 5 con problemas | 19.902 | 4.780 (−76 %) |
| `list_sheet_history`, 30 elementos | 2.674 | 2.144 (−20 %) |
| `search_knowledge`, 8 resultados | 989 | 835 (−16 %) |

### Defectos a propósito: 13 de 13 detectados

| ID | Defecto | Lo detectó |
| --- | --- | --- |
| T1 | La fila conserva la lista separada | `test_nested_levels_are_separated_too` |
| T2 | Un booleano sirve de clave del padre | `test_lists_that_cannot_be_rebuilt_stay_in_place` |
| T3 | Pisa una clave hermana existente | `test_an_existing_key_with_the_sibling_name_is_kept` |
| T4 | Separa hijas que ya traen la clave del padre | `test_lists_that_cannot_be_rebuilt_stay_in_place` |
| T5 | Agotado el turno, el resultado llega vacío | `test_after_the_run_budget_results_say_so_instead_of_arriving_empty` |
| T6 | Recorta a mitad de fila | `test_a_large_result_is_cut_at_a_line_and_says_so` |
| T7 | Recorta sin avisar | `test_a_large_result_is_cut_at_a_line_and_says_so` |
| T8 | Vuelve al JSON | Evaluación `mapeo-explicito` |
| T9 | El 401 llega al modelo | `test_credential_server_and_unreadable_failures_stay_generic` |
| T10 | Se pierde el código de Nest | `test_every_public_rejection_reaches_the_model_with_its_code` |
| T11 | Se ignora el idioma | `test_every_public_rejection_reaches_the_model_with_its_code` |
| T12 | Turnos iguales a llamadas | Evaluación `limite-de-herramientas` |
| T13 | Vuelve `HIGH` | `test_chat_model_gets_its_own_location_and_safe_defaults` |

## Consecuencias

- Nest todavía acepta 20 llamadas por ejecución. Hasta la etapa E2, que sube su límite a 40, la llamada 21 responde `AGENT_RUN_CALL_LIMIT`, aunque ahora llega al modelo con su código.
- El arranque real con Nest se comprueba en la etapa E7.
