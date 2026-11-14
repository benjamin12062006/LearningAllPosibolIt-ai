# 02 — Evaluación reproducible del agente con LLM simulado

Fecha de creación: 2026-11-13  
Estado: Implementado y verificado con el LLM guionizado. Gemini queda para la segunda parte de E6.5.  
Revisión de partida: `c87fb20`  
Relacionada con el [plan de evaluación](../../../docs/plans/feature/agente/02-plan-evaluacion-del-agente.md), la [ficha de fuentes](../../../docs/fonts/feature/agente/02-fuentes-de-la-evaluacion-del-agente.md) y la [implementación de E6.3b](01-agente-con-llm-simulado.md).

## Qué se hizo

Doce casos sintéticos en [`tests/evaluation/agent_cases.json`](../../../tests/evaluation/agent_cases.json): el catálogo, el mensaje, los datos que devolvería Nest, el guion del modelo y lo esperado. [`test_agent_evaluation.py`](../../../tests/evaluation/test_agent_evaluation.py) los ejecuta con el agente real (`AgentService` + `LlamaIndexAgent` + `FunctionAgent`). Se sustituyen el modelo (`ScriptedResponses`), la pasarela de Nest (`EvaluationGateway`, que falla ante cualquier llamada que el caso no espere) y el índice de conocimiento (Qdrant en memoria con embeddings deterministas).

| Evidencia | Decisión | Aplicación |
| --- | --- | --- |
| F1 (documento 15): mapeo claro y ambiguo, porcentajes decimales, instrucciones en celdas, herramientas desconocidas, IDs ajenos, salida malformada, contexto antiguo y proveedor lento | Un caso por escenario. La cancelación explícita y las cuotas quedan para E6.4 | `lectura-autorizada`, `mapeo-explicito`, `mapeo-ambiguo`, `aumento-decimal-en-seleccion`, `instruccion-en-celda`, `herramienta-desconocida`, `recurso-ajeno`, `argumentos-malformados`, `revision-desactualizada`, `modelo-lento` y `limite-de-herramientas` |
| F2 (T18b, T19): ni otra organización ni un proyecto no visible | La búsqueda pasa por el índice real de LlamaIndex, con documentos de otra organización y de otro proyecto | `busqueda-con-alcance` comprueba que ni la respuesta ni los resultados de la herramienta los contienen |
| F2 y F3 (T20 y D13): la escritura se prepara y el resumen es de Nest | El caso decimal comprueba el modo `prepare` y la confirmación con el resumen de la pasarela | `confirmation_from` en el caso decimal |
| F4: el guion solo fija lo que diría el modelo | Separar el mensaje y lo esperado del guion | En la segunda parte de E6.5, Gemini sustituirá el guion y se compararán los mismos criterios |

## Defecto real encontrado por la evaluación

El caso `modelo-lento` falló: la ejecución terminaba bien con `limit_reached` («Se agotó el tiempo»), pero **la llamada al modelo seguía viva**. Con Gemini, eso deja abierta una petición HTTP y su tarea, que no se liberan nunca.

- **Reproducido** con una sonda fuera del repositorio. Al volver `AgentService.run`, la llamada al modelo no se había cancelado y quedaba una tarea `_run_worker` viva; 0,5 s después, igual.
- **Causa:** al vencer el plazo, `asyncio.timeout` cancela la tarea que espera al workflow, y esa cancelación llega directamente al futuro del workflow. Su bucle de control termina sin cancelar el paso que espera al modelo. Después, `handler.cancel_run()` ya no tiene nada que parar.
- **Por qué no lo vio la prueba unitaria de E6.3b** (`test_deadline_covers_workflow_execution`): comprobaba la cancelación después de `asyncio.run`, que al cerrar el bucle cancela todo lo que queda vivo y escondía la fuga.
- **Arreglo** en [`llamaindex_agent.py`](../../../src/ktsu_ai/infrastructure/agent_infrastructure/llamaindex_agent.py): el workflow se espera con `asyncio.shield`. Al cancelar, `_stop_workflow` llama a `cancel_run()`, que cancela sus pasos, y recoge el `WorkflowCancelledByUser` final; sin recogerlo, asyncio avisa con «Task exception was never retrieved». La sonda, repetida con el arreglo, deja 0 tareas vivas, el modelo cancelado y ningún aviso.
- **Prueba unitaria reforzada:** ahora comprueba la cancelación dentro del bucle, antes de que `asyncio.run` limpie.

## Ajustes al escribir el código

- El aviso «Payload indexes have no effect in the local Qdrant» se filtra solo en este módulo de pruebas. El Qdrant en memoria no crea índices, pero sí aplica el filtro de alcance (lo demuestran los defectos 4 y 5).
- `from __future__ import annotations` en la prueba, porque `_script` anota `SlowModel`, que se define debajo de quien lo usa.

## Comprobación

| Comprobación ejecutada | Resultado |
| --- | --- |
| Línea base (`c87fb20`), `make check` | 96 aprobadas y 20 omitidas |
| Primera ejecución de la evaluación | 11 de 12; falló `modelo-lento` (el defecto real de arriba) |
| `make check` con el arreglo | Ruff, formato, mypy y los 2 contratos de importaciones correctos; **108 aprobadas** y 20 omitidas (las 12 nuevas de evaluación) |
| Sonda de cancelación con el adaptador arreglado | Modelo cancelado antes de volver, 0 tareas vivas y sin avisos |
| 13 defectos a propósito, uno cada vez, en una copia con `PYTHONPATH` a la copia (comprobado: `ktsu_ai` se importaba de la copia) | **13 de 13 detectados**. Tres solo los detecta la evaluación nueva: quitar el `shield`, quitar la condición de organización del filtro y quitar la de proyectos visibles |

Defectos (entre paréntesis, los casos de evaluación que fallaron):

1. Esperar el workflow sin `shield` (`modelo-lento`).
2. No parar el workflow al cancelar (`modelo-lento` y la unitaria del plazo).
3. La búsqueda acepta argumentos de más (`instruccion-en-celda`).
4. El filtro sin organización (`busqueda-con-alcance`).
5. El filtro sin proyectos visibles (`busqueda-con-alcance`).
6. La escritura se ejecuta en lugar de prepararse (`aumento-decimal-en-seleccion`, `revision-desactualizada`).
7. La herramienta inventada no se registra (`herramienta-desconocida`, `instruccion-en-celda`).
8. Sin validar argumentos (`argumentos-malformados`).
9. Presupuesto de 9 llamadas (`limite-de-herramientas`).
10. El error de Nest sin su mensaje (`recurso-ajeno`, `revision-desactualizada`).
11. La aclaración no termina la ejecución (`mapeo-ambiguo`, `argumentos-malformados`, `revision-desactualizada`).
12. La escritura no termina la ejecución (`aumento-decimal-en-seleccion`).
13. El resumen de la confirmación inventado en lugar del de Nest (`aumento-decimal-en-seleccion`).

No se ejecutó `make test-qdrant` ni `make test-google`: esta etapa no cambia el selector ni llama a Google.

## Lo que queda

- **Segunda parte de E6.5:** los mismos mensajes y criterios con Gemini por Vertex AI (sin guion), con medición de calidad, latencia y coste. Necesita elegir Flash o Pro (decisión del usuario) y cuesta dinero.
- **E6.3a (Nest):** autorización real entre organizaciones, vigencia de la revisión, cálculo oficial del porcentaje y aplicación tras la confirmación humana.
- **E6.4:** cancelación pedida por la persona, revocación, cuotas y reconexión (T21–T22). El arreglo de esta etapa (`shield` + `cancel_run`) es la base de esa cancelación.
