# 02 — Plan de evaluación del agente con datos sintéticos (primera parte de E6.5)

Fecha de creación: 2026-11-13  
Última actualización: 2026-11-13  
Estado: Implementado y verificado con el LLM guionizado ([bitácora 02](../../../../bitacora-construccion/feature/agente/02-evaluacion-del-agente.md)). La segunda parte (Gemini) sigue pendiente.  
Ámbito: `LearningAllPosibolIt-ai`.  
Revisión de referencia: `c87fb20`.  
Relacionada con: [fuentes de evaluación](../../../fonts/feature/agente/02-fuentes-de-la-evaluacion-del-agente.md), [plan E6.3b](01-plan-agente-con-llm-simulado.md) y [plan E6 de la API](../../../../../LearningAllPosibolIt/docs/plans/feature/ai-assistant/01-plan-e6-ia-con-qdrant-y-llamaindex.md).

## Objetivo

Dejar un conjunto de casos sintéticos reutilizable para comparar el comportamiento del agente entre modelos y ejecutar desde ahora una comprobación reproducible con el LLM guionizado de E6.3b.

## Punto de partida y decisiones

`AgentService` y `LlamaIndexAgent` ya ejecutan el flujo con reglas de herramientas verificables. El catálogo y la pasarela de Nest se pueden sustituir en las pruebas. Las decisiones parten de los casos del documento 15, los criterios T18–T20 y los puertos existentes, detallados en F1–F7 de la [ficha de fuentes](../../../fonts/feature/agente/02-fuentes-de-la-evaluacion-del-agente.md).

| Decisión | Motivo |
| --- | --- |
| Guardar en `tests/evaluation/agent_cases.json` el mensaje, los datos sintéticos y las expectativas observables de cada caso, junto con el guion local. | Los mensajes y criterios se pueden reaprovechar cuando Gemini produzca sus propias respuestas. F1–F4. |
| Evaluar con pytest el agente real usando `ScriptedResponses` y dobles de los puertos. | El texto guionizado solo hace reproducible la entrada del modelo. Los efectos, las llamadas y el estado final proceden del código del agente. F4–F7. |
| Comprobar resultados y efectos con aserciones deterministas. | Los rechazos, límites de alcance y operaciones de escritura se observan en las llamadas, sus estados y la confirmación pendiente. F1–F3, F5–F6. |

## Incrementos

1. ✅ **Datos y resultados esperados.** Preparar casos de lectura permitida, mapeo claro y ambiguo, búsqueda con alcance acotado, recurso ajeno, preparación de un ajuste decimal, instrucción dentro de una celda, herramienta desconocida, argumentos inválidos, contexto antiguo, plazo y presupuesto de herramientas. Registrar el estado esperado, las llamadas permitidas y, cuando aplique, los datos de confirmación.
2. ✅ **Ejecución local.** *Ajustado en el incremento 2:* el caso del plazo encontró que la llamada al modelo seguía viva tras vencer el plazo; se arregló en `LlamaIndexAgent` (`shield` + `cancel_run`) y se reforzó la prueba unitaria del plazo. Cargar el catálogo y el guion sintéticos desde pytest, ejecutar el agente y comprobar los estados y las llamadas observadas en los dobles. En cada escritura preparada, comprobar el modo `prepare` y la confirmación pendiente con el resumen devuelto por el puerto de operaciones.
3. ✅ **Comprobación.** 108 pruebas aprobadas y 13 de 13 defectos a propósito detectados. Ejecutar `uv run pytest tests/evaluation -q` y `make check`. Registrar los resultados y los casos que requieren servicios reales en la bitácora.

## Continuidad

En E6.3a se comprueba el catálogo real, la pertenencia de los recursos, el rechazo de contextos antiguos y la aplicación posterior a una confirmación humana. El cálculo decimal y el diff de T20 se validan en el flujo de hoja y cambios de Nest. En E6.4 se comprueban cancelación explícita, revocación, cuotas y reconexión. La segunda parte de E6.5 ejecutará los casos con Gemini por Vertex AI y medirá calidad, latencia y coste. La comprobación guionizada aporta una base de regresión para esas etapas.
