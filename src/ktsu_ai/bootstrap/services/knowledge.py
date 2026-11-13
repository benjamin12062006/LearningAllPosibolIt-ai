"""Construye el servicio de conocimiento: LlamaIndex sobre Qdrant con su embedding."""

from llama_index.core.base.embeddings.base import BaseEmbedding
from qdrant_client import AsyncQdrantClient

from ktsu_ai.application.knowledge_application.knowledge_service import (
    KnowledgeService,
)
from ktsu_ai.application.knowledge_ports.in_knowledge_use_case import (
    IKnowledgeUseCase,
)
from ktsu_ai.config.configuration import Configuration
from ktsu_ai.infrastructure.knowledge_infrastructure.llamaindex_knowledge_index import (
    LlamaIndexKnowledgeIndex,
)


def build_knowledge_service(
    qdrant: AsyncQdrantClient,
    embedder: BaseEmbedding,
    configuration: Configuration,
) -> IKnowledgeUseCase:
    index = LlamaIndexKnowledgeIndex(
        client=qdrant,
        collection_name=configuration.knowledge.collection,
        dimensions=configuration.embedding.dimensions,
        embedder=embedder,
    )
    return KnowledgeService(index)
