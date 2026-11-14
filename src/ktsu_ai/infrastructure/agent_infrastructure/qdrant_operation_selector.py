"""Clasifica el catálogo autorizado usando una colección de vectores de herramientas."""

import asyncio
import json
from typing import Final
from uuid import NAMESPACE_URL, uuid5

from llama_index.core.base.embeddings.base import BaseEmbedding
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qdrant
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from ktsu_ai.common.error import AppError, ErrorCode
from ktsu_ai.domain.agent.agent_run import AgentOperation, AgentRun
from ktsu_ai.infrastructure.knowledge_infrastructure.llamaindex_knowledge_index import (
    UNAVAILABLE_ERRORS,
)

TOOL_VECTOR: Final = "description"
MAX_SELECTED_OPERATIONS: Final = 8


class QdrantOperationSelector:
    def __init__(
        self,
        client: AsyncQdrantClient,
        embedder: BaseEmbedding,
        collection: str,
        dimensions: int,
    ) -> None:
        self._client = client
        self._embedder = embedder
        self._collection = collection
        self._dimensions = dimensions
        self._collection_lock = asyncio.Lock()
        self._collection_ready = False

    async def select(self, run: AgentRun) -> tuple[str, ...]:
        if not run.operations:
            return ()
        allowed = {_point_id(operation): operation for operation in run.operations}
        try:
            await self._ensure_collection()
            await self._cache_tool_vectors(allowed)
            vector = await self._embedder.aget_query_embedding(run.message)
            result = await self._client.query_points(
                collection_name=self._collection,
                query=vector,
                using=TOOL_VECTOR,
                query_filter=qdrant.Filter(
                    must=[qdrant.HasIdCondition(has_id=list(allowed))]
                ),
                limit=MAX_SELECTED_OPERATIONS,
                with_payload=False,
            )
        except UNAVAILABLE_ERRORS as error:
            if isinstance(error, (UnexpectedResponse, ResponseHandlingException)):
                self._collection_ready = False
            raise AppError(ErrorCode.AGENT_UNAVAILABLE) from None

        return tuple(
            allowed[point_id].name
            for point in result.points
            if (point_id := str(point.id)) in allowed
        )

    async def _ensure_collection(self) -> None:
        async with self._collection_lock:
            if self._collection_ready:
                return
            if not await self._client.collection_exists(self._collection):
                await self._create_collection()
            self._collection_ready = True

    async def _create_collection(self) -> None:
        try:
            await self._client.create_collection(
                collection_name=self._collection,
                vectors_config={
                    TOOL_VECTOR: qdrant.VectorParams(
                        size=self._dimensions, distance=qdrant.Distance.COSINE
                    )
                },
            )
        except UnexpectedResponse:
            # Otra instancia puede crear la colección entre la consulta y el alta.
            if not await self._client.collection_exists(self._collection):
                raise

    async def _cache_tool_vectors(self, allowed: dict[str, AgentOperation]) -> None:
        existing = await self._client.retrieve(
            collection_name=self._collection, ids=list(allowed), with_payload=False
        )
        existing_ids = {str(point.id) for point in existing}
        missing = {
            point_id: operation
            for point_id, operation in allowed.items()
            if point_id not in existing_ids
        }
        if not missing:
            return
        vectors = await self._embedder.aget_text_embedding_batch(
            [
                f"{operation.name}: {operation.description}"
                for operation in missing.values()
            ]
        )
        await self._client.upsert(
            collection_name=self._collection,
            points=[
                qdrant.PointStruct(id=point_id, vector={TOOL_VECTOR: vector})
                for point_id, vector in zip(missing, vectors, strict=True)
            ],
            wait=True,
        )


def _point_id(operation: AgentOperation) -> str:
    # Identificar la versión por nombre y descripción evita recuperar vectores antiguos.
    identity = json.dumps(["ktsu-agent-tool", operation.name, operation.description])
    return str(uuid5(NAMESPACE_URL, identity))
