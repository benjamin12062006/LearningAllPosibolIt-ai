"""Índice de conocimiento con LlamaIndex sobre Qdrant (implementa `IKnowledgeIndex`).

Qué pone LlamaIndex: el troceo (`SentenceSplitter`), los nodos (`TextNode`), el
modelo de embeddings (`BaseEmbedding`, Google en real) y el almacén
(`QdrantVectorStore`). Qué pone este archivo: ids estables, los campos de
inquilino en cada punto y el filtro obligatorio en cada búsqueda (ficha 03, L2).

No se usa `as_retriever`: se consulta el almacén directamente, con el filtro
calculado aquí y no por LlamaIndex.
"""

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Final

import httpx
from google.auth.exceptions import GoogleAuthError
from google.genai.errors import APIError as GoogleApiError
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import BaseNode, TextNode
from llama_index.core.vector_stores.types import VectorStoreQuery
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qdrant
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse
from tenacity import RetryError

from ktsu_ai.common.error import AppError, ErrorCode
from ktsu_ai.domain.access.access_scope import AccessScope
from ktsu_ai.domain.knowledge.knowledge_document import (
    RESERVED_METADATA_KEYS,
    KnowledgeDocument,
    KnowledgeHit,
    MetadataValue,
    ServiceMetadata,
    SourceKey,
    SourceType,
)
from ktsu_ai.infrastructure.knowledge_infrastructure.collection import (
    DENSE_VECTOR,
    ensure_collection,
    project_filter,
    scope_filter,
    source_filter,
)

# Trozos de ~512 tokens: caben de sobra en los 2048 de `gemini-embedding-001` y
# una fila o una ficha de producto suelen ser un solo trozo.
CHUNK_TOKENS: Final = 512
CHUNK_OVERLAP_TOKENS: Final = 50

SCROLL_PAGE: Final = 1_000

# Se piden más trozos de los que se devuelven porque varios pueden ser del mismo
# documento y solo se devuelve el mejor de cada uno.
CHUNKS_PER_HIT: Final = 3

# Espacio de nombres fijo de los ids de punto (UUID v5): el mismo documento y
# trozo dan siempre el mismo punto, así reescribir no duplica.
POINT_NAMESPACE: Final = uuid.UUID("6f1d3c52-9a8e-4f6b-b3d1-2c7e5a9f0b14")

# Lo que significa «Qdrant o el modelo no responden», no un fallo de programa.
UNAVAILABLE_ERRORS: Final = (
    UnexpectedResponse,
    ResponseHandlingException,
    httpx.HTTPError,
    GoogleApiError,
    GoogleAuthError,
    RetryError,
    TimeoutError,
    ConnectionError,
)

logger = logging.getLogger(__name__)


class LlamaIndexKnowledgeIndex:
    def __init__(
        self,
        client: AsyncQdrantClient,
        collection_name: str,
        dimensions: int,
        embedder: BaseEmbedding,
    ) -> None:
        self._client = client
        self._collection_name = collection_name
        self._dimensions = dimensions
        self._embedder = embedder
        self._splitter = SentenceSplitter(
            chunk_size=CHUNK_TOKENS, chunk_overlap=CHUNK_OVERLAP_TOKENS
        )
        self._store = QdrantVectorStore(
            collection_name=collection_name,
            aclient=client,
            dense_vector_name=DENSE_VECTOR,
        )
        self._ready = False
        self._ready_lock = asyncio.Lock()

    async def document_hashes(self, key: SourceKey) -> dict[str, str]:
        async with self._unavailable_on_failure():
            await self._ensure_ready()
            hashes: dict[str, str] = {}
            async for payload in self._scroll_payloads(source_filter(key)):
                hashes[str(payload[ServiceMetadata.DOCUMENT_ID])] = str(
                    payload[ServiceMetadata.DOCUMENT_HASH]
                )
            return hashes

    async def write_documents(
        self, key: SourceKey, documents: Sequence[KnowledgeDocument]
    ) -> None:
        async with self._unavailable_on_failure():
            await self._ensure_ready()
            nodes = self._nodes_of(key, documents)
            embeddings = await self._embedder.aget_text_embedding_batch(
                [node.get_content() for node in nodes]
            )
            for node, embedding in zip(nodes, embeddings, strict=True):
                node.embedding = embedding
            await self._store.async_add(list[BaseNode](nodes))
            await self._delete_leftover_chunks(key, documents, nodes)

    async def delete_documents(
        self, key: SourceKey, document_ids: Sequence[str]
    ) -> None:
        async with self._unavailable_on_failure():
            await self._ensure_ready()
            await self._delete(_with_documents(source_filter(key), document_ids))

    async def delete_source(self, key: SourceKey) -> None:
        async with self._unavailable_on_failure():
            await self._ensure_ready()
            await self._delete(source_filter(key))

    async def delete_project(self, organization_id: str, project_id: str) -> None:
        async with self._unavailable_on_failure():
            await self._ensure_ready()
            await self._delete(project_filter(organization_id, project_id))

    async def search(
        self,
        query: str,
        scope: AccessScope,
        limit: int,
        source_types: frozenset[SourceType],
    ) -> list[KnowledgeHit]:
        async with self._unavailable_on_failure():
            await self._ensure_ready()
            embedding = await self._embedder.aget_query_embedding(query)
            result = await self._store.aquery(
                VectorStoreQuery(
                    query_embedding=embedding,
                    similarity_top_k=limit * CHUNKS_PER_HIT,
                ),
                qdrant_filters=scope_filter(scope, source_types),
            )
            nodes = result.nodes or []
            scores = result.similarities or []
            return _best_hit_per_document(nodes, scores)[:limit]

    # -------------------------------------------------------------------------

    async def _ensure_ready(self) -> None:
        """Crea la colección al primer uso: Qdrant pudo faltar al arrancar."""
        if self._ready:
            return
        async with self._ready_lock:
            if not self._ready:
                await ensure_collection(
                    self._client, self._collection_name, self._dimensions
                )
                self._ready = True

    def _nodes_of(
        self, key: SourceKey, documents: Sequence[KnowledgeDocument]
    ) -> list[TextNode]:
        nodes: list[TextNode] = []
        for document in documents:
            chunks = self._splitter.split_text(document.text) or [document.text]
            for number, chunk in enumerate(chunks):
                nodes.append(
                    TextNode(
                        id_=_point_id(key, document.document_id, number),
                        text=chunk,
                        metadata=_payload_of(key, document, number),
                    )
                )
        return nodes

    async def _delete_leftover_chunks(
        self,
        key: SourceKey,
        documents: Sequence[KnowledgeDocument],
        written: Sequence[TextNode],
    ) -> None:
        """Si un documento tenía más trozos antes, los sobrantes se quitan."""
        leftover = _with_documents(
            source_filter(key), [document.document_id for document in documents]
        )
        leftover.must_not = [
            qdrant.HasIdCondition(has_id=[node.id_ for node in written])
        ]
        await self._delete(leftover)

    async def _delete(self, selector: qdrant.Filter) -> None:
        await self._client.delete(
            collection_name=self._collection_name,
            points_selector=qdrant.FilterSelector(filter=selector),
            wait=True,
        )

    async def _scroll_payloads(
        self, selector: qdrant.Filter
    ) -> AsyncIterator[dict[str, object]]:
        offset: qdrant.ExtendedPointId | None = None
        while True:
            points, offset = await self._client.scroll(
                collection_name=self._collection_name,
                scroll_filter=selector,
                limit=SCROLL_PAGE,
                offset=offset,
                with_payload=[
                    ServiceMetadata.DOCUMENT_ID,
                    ServiceMetadata.DOCUMENT_HASH,
                ],
                with_vectors=False,
            )
            for point in points:
                yield dict(point.payload or {})
            if offset is None:
                return

    @asynccontextmanager
    async def _unavailable_on_failure(self) -> AsyncIterator[None]:
        """Qdrant o el modelo caídos: 503 para Nest, que reintentará."""
        try:
            yield
        except UNAVAILABLE_ERRORS as error:
            # Solo el tipo: el mensaje podría llevar textos del usuario o la URL.
            logger.warning("Conocimiento no disponible: %s", type(error).__name__)
            raise AppError(ErrorCode.KNOWLEDGE_UNAVAILABLE) from error


def _point_id(key: SourceKey, document_id: str, chunk: int) -> str:
    name = "/".join(
        (
            key.organization_id,
            key.project_id,
            key.source_type.value,
            key.source_id,
            document_id,
            str(chunk),
        )
    )
    return str(uuid.uuid5(POINT_NAMESPACE, name))


def _payload_of(
    key: SourceKey, document: KnowledgeDocument, chunk: int
) -> dict[str, MetadataValue]:
    # Los campos del servicio van al final: ganan a cualquier metadato con su nombre.
    return {
        **document.metadata,
        ServiceMetadata.ORGANIZATION_ID: key.organization_id,
        ServiceMetadata.PROJECT_ID: key.project_id,
        ServiceMetadata.SOURCE_TYPE: key.source_type.value,
        ServiceMetadata.SOURCE_ID: key.source_id,
        ServiceMetadata.DOCUMENT_ID: document.document_id,
        ServiceMetadata.DOCUMENT_HASH: document.content_hash,
        ServiceMetadata.CHUNK: chunk,
    }


def _with_documents(
    selector: qdrant.Filter, document_ids: Sequence[str]
) -> qdrant.Filter:
    must = list(selector.must or [])
    must.append(
        qdrant.FieldCondition(
            key=ServiceMetadata.DOCUMENT_ID,
            match=qdrant.MatchAny(any=list(document_ids)),
        )
    )
    return qdrant.Filter(must=must)


def _best_hit_per_document(
    nodes: Sequence[BaseNode], scores: Sequence[float]
) -> list[KnowledgeHit]:
    """Los nodos llegan del más al menos parecido: el primero de cada documento gana."""
    hits: list[KnowledgeHit] = []
    seen: set[tuple[str, str, str, str]] = set()
    for node, score in zip(nodes, scores, strict=True):
        hit = _hit_of(node, score)
        identity = (
            hit.key.project_id,
            hit.key.source_type.value,
            hit.key.source_id,
            hit.document_id,
        )
        if identity not in seen:
            seen.add(identity)
            hits.append(hit)
    return hits


def _hit_of(node: BaseNode, score: float) -> KnowledgeHit:
    metadata = node.metadata
    return KnowledgeHit(
        key=SourceKey(
            organization_id=str(metadata[ServiceMetadata.ORGANIZATION_ID]),
            project_id=str(metadata[ServiceMetadata.PROJECT_ID]),
            source_type=SourceType(str(metadata[ServiceMetadata.SOURCE_TYPE])),
            source_id=str(metadata[ServiceMetadata.SOURCE_ID]),
        ),
        document_id=str(metadata[ServiceMetadata.DOCUMENT_ID]),
        text=node.get_content(),
        score=score,
        metadata={
            name: value
            for name, value in metadata.items()
            if name not in RESERVED_METADATA_KEYS
        },
    )
