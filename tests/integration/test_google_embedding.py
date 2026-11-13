"""Contra Vertex AI de verdad (`make test-google`), con textos inventados.

Comprueba lo que se midió al activar Vertex AI (bitácora 02): dimensiones,
que la pregunta se acerca al texto que toca y que nunca hay más peticiones a la
vez que `EMBEDDING_CONCURRENCY`.
"""

import asyncio
import math
from collections.abc import Iterator

import google.genai.models as genai_models
import pytest

from ktsu_ai.config.loader import load_configuration
from ktsu_ai.infrastructure.embeddings.google_embedding import create_google_embedding

pytestmark = pytest.mark.google

PRODUCTS = [
    "Zapatillas de running rojas, talla 42, 59,90 EUR",
    "Cámara réflex con objetivo 18-55",
    "Mesa de roble macizo para comedor",
]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return dot / math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))


@pytest.fixture
def peak_concurrency(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[int]]:
    """Cuenta cuántas llamadas a `embed_content` hay en vuelo a la vez."""
    original = genai_models.AsyncModels.embed_content
    state = {"active": 0}
    peak = [0]

    async def counting(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        state["active"] += 1
        peak[0] = max(peak[0], state["active"])
        try:
            return await original(self, *args, **kwargs)
        finally:
            state["active"] -= 1

    monkeypatch.setattr(genai_models.AsyncModels, "embed_content", counting)
    yield peak


def test_vertex_returns_vectors_of_the_configured_size_that_make_sense() -> None:
    config = load_configuration().embedding
    embedder = create_google_embedding(config)

    async def run() -> tuple[list[float], list[list[float]]]:
        query = await embedder.aget_query_embedding("zapatillas para correr")
        documents = await embedder.aget_text_embedding_batch(PRODUCTS)
        return query, documents

    query, documents = asyncio.run(run())

    assert len(query) == config.dimensions
    assert all(len(vector) == config.dimensions for vector in documents)
    similarities = [cosine(query, vector) for vector in documents]
    assert similarities.index(max(similarities)) == 0


def test_vertex_is_never_called_more_than_the_concurrency_limit(
    peak_concurrency: list[int],
) -> None:
    config = load_configuration().embedding
    embedder = create_google_embedding(config)
    texts = [f"Ficha inventada {n}: producto de prueba {n}" for n in range(200)]

    vectors = asyncio.run(embedder.aget_text_embedding_batch(texts))

    assert len(vectors) == 200
    assert 1 < peak_concurrency[0] <= config.concurrency
