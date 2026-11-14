# 02 — E6.1a: indexar y buscar el conocimiento (servicio de IA)

Fecha de creación: 2026-11-09  
Última actualización: 2026-11-09  
Estado: Implementado y verificado (2026-11-09), también contra Vertex AI una vez que el usuario lo activó. Sin commit.  
Relacionada con: [plan 01 del servicio](../../../docs/plans/feature/base-del-servicio/01-plan-servicio-de-ia.md), [plan E6 de la API](../../../../LearningAllPosibolIt/docs/plans/feature/ai-assistant/01-plan-e6-ia-con-qdrant-y-llamaindex.md) (D4, D5, D7), [ficha 03 de la API](../../../../LearningAllPosibolIt/docs/fonts/feature/ai-assistant/03-fuentes-de-indexar-el-conocimiento.md), [bitácora 01](01-base-del-servicio.md).

## Necesidad

Que el servicio de IA guarde en Qdrant lo que Nest le mande de cada fuente de un proyecto (catálogo, hojas, feed…) y busque por significado **sin salirse nunca** de la organización y los proyectos que Nest dice que la persona puede ver. E6.1b (Nest) le mandará esos documentos.

## Decisiones del usuario durante la etapa (2026-11-09)

1. Qdrant recibe **todo lo que la persona puede ver**: inventario tabla a tabla en la ficha 03 de la API.
2. **Modelos de la API de Google, ninguno descargado ni propio** («usaremos los modelos de su api de google, no crearemos modelos»). Se retiró FastEmbed y el BM25 local que se había empezado a plantear.
3. FastAPI como framework HTTP, respaldado con sus cursos (fuentes 01, C6–C11).
4. Arquitectura hexagonal como su backend en Rust, y que se vea al aprender: mapa en el [README](../../../README.md#arquitectura-hexagonal-recorrido-de-una-petición).

## Arquitectura (puertos y adaptadores)

| Pieza | Archivo |
| --- | --- |
| Dominio | `domain/knowledge/knowledge_document.py` (`SourceType`, `SourceKey`, `KnowledgeDocument` con `content_hash`, `KnowledgeHit`, metadatos reservados), `domain/access/access_scope.py` |
| Puerto de entrada | `application/knowledge_ports/in_knowledge_use_case.py` |
| Servicio y casos de uso | `knowledge_application/knowledge_service.py`, `use_cases/replace_source.py`, `use_cases/search_knowledge.py` |
| Puerto de salida | `application/knowledge_ports/out_knowledge_index.py` |
| Adaptador de salida | `infrastructure/knowledge_infrastructure/llamaindex_knowledge_index.py` y `collection.py`; `infrastructure/embeddings/google_embedding.py` |
| Adaptador de entrada | `http/knowledge_http/routes.py`, `dto/knowledge_request_dto.py`, `dto/knowledge_response_dto.py` |
| Composición | `bootstrap/services/knowledge.py`, `bootstrap/app.py` (`create_app(configuration, embedder=None)`: sin `embedder`, Google) |

## Evidencia → decisión → aplicación

| Evidencia | Decisión | Aplicación |
| --- | --- | --- |
| Ficha 01 de la API F1 (Qdrant, multitenancy); ficha 03 L3 (LlamaIndex no crea `is_tenant`) | Una colección; índices propios | `collection.ensure_collection`: vector `dense` coseno, `organization_id` con `is_tenant`, índices `keyword` de proyecto, tipo, fuente y documento |
| Ficha 03 L2 (`aquery(…, qdrant_filters=…)`) | Filtro de inquilino calculado aquí en **cada** búsqueda | `scope_filter`: organización + `MatchAny` de proyectos visibles (+ tipos) |
| Curso LlamaIndex 17 y 19 (pipeline y no reprocesar) | Solo se reescriben los documentos cuyo hash cambió | `use_cases/replace_source.py` con `content_hash` (texto + metadatos) |
| Curso LlamaIndex 28 (citas) | Cada resultado lleva proyecto, fuente, documento y metadatos de Nest | `KnowledgeHit`, `HitResponse` |
| Ficha 03 G1–G3 | `gemini-embedding-001`, 768 dimensiones, ADC | `create_google_embedding`, `EmbeddingConfiguration` |
| Ficha 03 L5 | `SentenceSplitter` de 512 tokens, ids de punto estables (UUID v5) | `_nodes_of`, `_point_id` |

## Contrato (solo Nest, con el token de servicio)

```http
PUT    /v1/knowledge/organizations/{org}/projects/{project}/sources/{sourceType}/{sourceId}
       { "documents": [{ "documentId": "SKU-42", "text": "…", "metadata": { "outcome": "invalid" } }] }
       → 200 { "written": 1, "unchanged": 0, "removed": 0 }
DELETE /v1/knowledge/organizations/{org}/projects/{project}/sources/{sourceType}/{sourceId}  → 204
DELETE /v1/knowledge/organizations/{org}/projects/{project}                                  → 204
POST   /v1/knowledge/search
       { "organizationId": "…", "projectIds": ["…"], "query": "…", "limit": 8, "sourceTypes": ["catalog"] }
       → 200 { "hits": [{ "projectId", "sourceType", "sourceId", "documentId", "text", "score", "metadata" }] }
```

- `sourceType`: `organization`, `project`, `workbook`, `worksheet`, `catalog`, `evaluation`, `ruleset`, `feed`, `changeset`, `worksheet_import`.
- Límites: 5.000 documentos por fuente, 8.000 caracteres por texto, 20 metadatos (nombre `^[a-z][a-z0-9_]{0,39}$`, valor simple, textos de 500 como mucho), pregunta de 1.000, 20 resultados, 500 proyectos visibles.
- Metadatos reservados (400): los del servicio (`organization_id`, `project_id`, `source_type`, `source_id`, `knowledge_document_id`, `document_hash`, `chunk`) y los que escribe LlamaIndex (`_node_content`, `_node_type`, `document_id`, `doc_id`, `ref_doc_id`).
- Errores: 400 `VALIDATION_FAILED`, 400 `KNOWLEDGE_DOCUMENT_DUPLICATED`, 401 `AUTH_SERVICE_TOKEN_INVALID`, 503 `KNOWLEDGE_UNAVAILABLE` (Qdrant o Google no responden: Nest reintenta).

## Ajustes al escribir el código

- **LlamaIndex pisaba nuestro `document_id`.** Las pruebas contra Qdrant fallaron (3 de 16): todos los documentos parecían uno solo. Leyendo `llama_index/core/vector_stores/utils.py` (`node_to_metadata_dict`): escribe `document_id`, `doc_id` y `ref_doc_id` con el id de documento de LlamaIndex (`"None"` si no hay). Nuestro campo pasó a `knowledge_document_id` y esos nombres quedan reservados.
- **Metadatos reservados en el dominio**, no en infraestructura: el DTO HTTP los necesita y `import-linter` le prohíbe importar infraestructura.
- **Los campos del servicio van después de los metadatos de Nest** al construir cada punto: ganan aunque alguien los colara (prueba nueva antes de los defectos).
- **Sin BM25 ni FastEmbed** (decisión 2): búsqueda solo densa; lo exacto irá por herramientas SQL (E6.3).
- **`EMBEDDING_BATCH_SIZE=1`** hasta comprobar con Vertex activado cuántos textos admite `gemini-embedding-001` por petición (la página de Google se contradice, ficha 03 G1).
- **`E501` desactivada en ruff**: el formateador ya corta las líneas; solo quedaban largas las rutas de import.
- **`create_app` recibe el modelo de embeddings opcionalmente**: las pruebas pasan uno determinista (`tests/support/word_hash_embedding.py`) y nunca llaman a Google.
- Las borradas responden 204 aunque no hubiera nada, para que Nest pueda repetirlas.

## Comprobaciones realmente ejecutadas

2026-11-09.

- `ruff`, formato, `mypy --strict` (67 archivos) e `import-linter` (2 contratos KEPT): limpios.
- `pytest`: **70 pasan**, 17 se saltan (las de Qdrant real).
- `make test-qdrant` (contenedor temporal 1.19.1, 2 CPU, 1 GiB): **17 de 17**. Cubren: buscar por significado con sus metadatos; **aislamiento** (otra organización, proyecto no visible, proyecto de otra organización pedido con la propia y una pregunta que pide saltarse el filtro: nada se cruza); filtro por tipo; no recalcular lo que no cambió (3 embebidos, después 0, después 1); quitar documentos que faltan; troceo y retirada de trozos sobrantes; un resultado por documento; borrar una fuente o un proyecto; índice `is_tenant`; colección con otras dimensiones rechazada; 503 con Qdrant caído; recorrido HTTP completo; y que los campos del servicio ganan a los metadatos de Nest.
- **Defectos a propósito** (copia, uno cada vez, con Qdrant real; la copia sin defecto pasa 87 de 87):

  | Defecto | Resultado |
  | --- | --- |
  | Filtro sin proyectos visibles | Detectado |
  | Filtro sin organización | Detectado |
  | Búsqueda sin filtro de inquilino | Detectado |
  | Filtro de tipos ignorado | Detectado |
  | Reescribe todo aunque no cambie | Detectado |
  | No quita los documentos que faltan | Detectado |
  | No quita trozos sobrantes | Detectado |
  | No se queda con el mejor trozo por documento | Detectado |
  | Los metadatos de Nest ganan a los del servicio | Detectado |
  | HTTP admite metadatos reservados | Detectado |
  | Busca aunque no vea proyectos | Detectado |
  | Admite ids repetidos | Detectado |
  | Índice de organización sin `is_tenant` | Detectado |
  | Qdrant caído da 500 en lugar de 503 | Detectado |
  | Sin comprobar dimensiones | Detectado |
  | El hash ignora los metadatos | Detectado |
  | Id de punto sin el documento | Detectado |

  17 de 17.
- **Vertex AI** (después de que el usuario lo activara; ver abajo): `make test-google`, 2 de 2.

## Vertex AI activado (2026-11-09)

El usuario ejecutó `gcloud services enable aiplatform.googleapis.com --project estadistica-forms-api` («finished successfully»). Mediciones con textos **inventados**, nunca datos del usuario:

| Medición | Resultado |
| --- | --- |
| Pregunta «zapatillas para correr» | 768 dimensiones; los textos más parecidos fueron las zapatillas (0,694) y la gorra para correr (0,685); el resto, por debajo de 0,58 |
| Varios textos por petición con `gemini-embedding-001` | **Sí**: 5, 32 y 64 textos por petición funcionan. Resuelve la contradicción de la documentación (ficha 03, G1) |
| 32 textos largos (~1.400 tokens cada uno) en una petición | Funciona (2,0 s) |
| 64 fichas de producto | Lotes de 1: 1,3 s; de 32: 1,8 s; de 64: 2,4 s |
| 200 textos con lotes de 32 y como mucho 4 peticiones a la vez | 2,6 s, y nunca más de 4 en vuelo |

**Hallazgo:** los lotes de 1 eran los más rápidos porque `BaseEmbedding.aget_text_embedding_batch` de LlamaIndex lanza **todas** las peticiones a la vez con `asyncio.gather` si no se le da `num_workers` (`llama_index/core/base/embeddings/base.py`, líneas 545–600). Con una hoja de 5.000 filas serían 5.000 peticiones simultáneas a Google y chocaría con la cuota. Con `num_workers` ≥ 2 usa su cola de trabajadores.

**Aplicado:** `EMBEDDING_BATCH_SIZE=32` y `EMBEDDING_CONCURRENCY=4` (nueva; la configuración rechaza 1, que no limita, y más de 16). Prueba marcada [`test_google_embedding.py`](../../../tests/integration/test_google_embedding.py) que solo corre con `make test-google`: dimensiones y sentido, y que nunca hay más peticiones a la vez que el límite. **Defecto a propósito:** quitar `num_workers` → la prueba falla («assert 1 < peak <= 4»); restaurado.

Los dos avisos de esa prueba son internos de `google-genai` (una advertencia de `aiohttp`), no de este código.

Estimación: una hoja de 5.000 filas tardaría alrededor de un minuto la primera vez; después solo se recalculan las filas que cambien.

## Consecuencias

- E6.1b (Nest) ya tiene contra qué escribir: cliente HTTP, documentos por fuente y reconciliador.
- Google ya responde. Queda medir el coste real de indexar un proyecto típico cuando E6.1b mande datos (consola de facturación de Google Cloud).
