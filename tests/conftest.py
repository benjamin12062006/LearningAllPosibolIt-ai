"""Pruebas que salen del portátil: solo corren cuando se piden a propósito.

- `qdrant`: `make test-qdrant` (contenedor temporal).
- `google`: `make test-google` (llama a Vertex AI con textos inventados; cuesta
  muy poco, pero no es gratis).
- `gemini`: `make eval-gemini` (los casos de evaluación con el modelo de chat del
  `.env`; cuesta céntimos por pasada).
"""

import os

import pytest

OPT_IN_MARKERS = {
    "qdrant": ("TEST_QDRANT_URL", "Sin Qdrant real: ejecuta `make test-qdrant`"),
    "google": (
        "TEST_GOOGLE_EMBEDDINGS",
        "Sin llamadas a Google: ejecuta `make test-google`",
    ),
    "gemini": ("TEST_GOOGLE_CHAT", "Sin Gemini real: ejecuta `make eval-gemini`"),
}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for marker, (variable, reason) in OPT_IN_MARKERS.items():
        value = os.environ.get(variable)
        enabled = bool(value) if marker == "qdrant" else value == "1"
        if enabled:
            continue
        skip = pytest.mark.skip(reason=reason)
        for item in items:
            if marker in item.keywords:
                item.add_marker(skip)
