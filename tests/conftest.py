"""Pruebas que salen del portátil: solo corren cuando se piden a propósito.

- `qdrant`: `make test-qdrant` (contenedor temporal).
- `google`: `make test-google` (llama a Vertex AI con textos inventados; cuesta
  muy poco, pero no es gratis).
"""

import os

import pytest

OPT_IN_MARKERS = {
    "qdrant": ("TEST_QDRANT_URL", "Sin Qdrant real: ejecuta `make test-qdrant`"),
    "google": (
        "TEST_GOOGLE_EMBEDDINGS",
        "Sin llamadas a Google: ejecuta `make test-google`",
    ),
}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for marker, (variable, reason) in OPT_IN_MARKERS.items():
        if os.environ.get(variable):
            continue
        skip = pytest.mark.skip(reason=reason)
        for item in items:
            if marker in item.keywords:
                item.add_marker(skip)
