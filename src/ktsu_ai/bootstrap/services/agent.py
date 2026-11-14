"""Compone el agente con su modelo y la pasarela a Nest."""

import httpx
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.llms.function_calling import FunctionCallingLLM
from qdrant_client import AsyncQdrantClient

from ktsu_ai.application.agent_application.agent_service import AgentService
from ktsu_ai.application.agent_ports.in_agent_use_case import IAgentUseCase
from ktsu_ai.application.knowledge_ports.in_knowledge_use_case import IKnowledgeUseCase
from ktsu_ai.config.configuration import Configuration
from ktsu_ai.infrastructure.agent_infrastructure.llamaindex_agent import LlamaIndexAgent
from ktsu_ai.infrastructure.agent_infrastructure.nest_operation_gateway import (
    NestOperationGateway,
)
from ktsu_ai.infrastructure.agent_infrastructure.qdrant_operation_selector import (
    QdrantOperationSelector,
)


def build_agent_service(
    llm: FunctionCallingLLM,
    client: httpx.AsyncClient,
    knowledge: IKnowledgeUseCase,
    qdrant: AsyncQdrantClient,
    embedder: BaseEmbedding,
    configuration: Configuration,
) -> IAgentUseCase:
    selector = QdrantOperationSelector(
        qdrant,
        embedder,
        configuration.agent_tools_collection,
        configuration.embedding.dimensions,
    )
    return AgentService(
        LlamaIndexAgent(llm), NestOperationGateway(client), knowledge, selector
    )
