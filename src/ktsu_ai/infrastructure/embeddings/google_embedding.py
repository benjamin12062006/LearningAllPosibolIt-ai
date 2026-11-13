"""Embeddings de Google por Vertex AI (plan E6, D5): ningún modelo propio ni local.

Credenciales: las de la cuenta (ADC) en local y la cuenta de servicio en Cloud
Run; no hay clave de API. El conector de LlamaIndex ya usa `RETRIEVAL_DOCUMENT`
al indexar y `RETRIEVAL_QUERY` al preguntar.
"""

from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.embeddings.google_genai import GoogleGenAIEmbedding
from llama_index.embeddings.google_genai.base import VertexAIConfig

from ktsu_ai.config.configuration import EmbeddingConfiguration


def create_google_embedding(config: EmbeddingConfiguration) -> BaseEmbedding:
    return GoogleGenAIEmbedding(
        model_name=config.model,
        vertexai_config=VertexAIConfig(
            # Sin credenciales explícitas: las de la cuenta (ADC). Con Vertex, el
            # conector descarta cualquier GOOGLE_API_KEY del entorno.
            credentials=None,
            project=config.google_cloud_project,
            location=config.google_cloud_location,
        ),
        embedding_config={"output_dimensionality": config.dimensions},
        embed_batch_size=config.batch_size,
        num_workers=config.concurrency,
        timeout=config.timeout_seconds,
    )
