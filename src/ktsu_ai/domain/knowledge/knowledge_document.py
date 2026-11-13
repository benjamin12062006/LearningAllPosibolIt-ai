"""Documentos de conocimiento: lo que Nest manda indexar (ficha 03 de la API).

Una **fuente** es lo que se reemplaza entero de una vez (una hoja, el catálogo de
un proyecto, su feed…). Cada fuente tiene **documentos** con un id estable dentro
de ella (una fila, un producto, el resumen). Qdrant guarda un trozo o más por
documento.
"""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

type MetadataValue = str | int | float | bool


class ServiceMetadata:
    """Metadatos que pone el servicio en cada trozo: Nest no los puede mandar."""

    ORGANIZATION_ID: Final = "organization_id"
    PROJECT_ID: Final = "project_id"
    SOURCE_TYPE: Final = "source_type"
    SOURCE_ID: Final = "source_id"
    # No `document_id`: ese nombre lo escribe LlamaIndex en cada punto (con el id
    # del documento de LlamaIndex) y pisaría el nuestro.
    DOCUMENT_ID: Final = "knowledge_document_id"
    DOCUMENT_HASH: Final = "document_hash"
    CHUNK: Final = "chunk"


# Los que escribe el almacén de LlamaIndex en cada punto
# (`llama_index.core.vector_stores.utils.node_to_metadata_dict`).
STORE_METADATA_KEYS: Final = frozenset(
    {"_node_content", "_node_type", "document_id", "doc_id", "ref_doc_id"}
)

RESERVED_METADATA_KEYS: Final = STORE_METADATA_KEYS | frozenset(
    {
        ServiceMetadata.ORGANIZATION_ID,
        ServiceMetadata.PROJECT_ID,
        ServiceMetadata.SOURCE_TYPE,
        ServiceMetadata.SOURCE_ID,
        ServiceMetadata.DOCUMENT_ID,
        ServiceMetadata.DOCUMENT_HASH,
        ServiceMetadata.CHUNK,
    }
)


class SourceType(StrEnum):
    """Las fuentes del inventario de la ficha 03. Solo se añaden al final."""

    ORGANIZATION = "organization"
    PROJECT = "project"
    WORKBOOK = "workbook"
    WORKSHEET = "worksheet"
    CATALOG = "catalog"
    EVALUATION = "evaluation"
    RULESET = "ruleset"
    FEED = "feed"
    CHANGESET = "changeset"
    WORKSHEET_IMPORT = "worksheet_import"


@dataclass(frozen=True)
class SourceKey:
    """Dónde vive una fuente: siempre dentro de una organización y un proyecto."""

    organization_id: str
    project_id: str
    source_type: SourceType
    source_id: str


@dataclass(frozen=True)
class KnowledgeDocument:
    document_id: str
    text: str
    metadata: Mapping[str, MetadataValue]

    @property
    def content_hash(self) -> str:
        """Cambia si cambia el texto o un metadato: solo entonces se recalcula."""
        canonical = json.dumps(
            {"text": self.text, "metadata": dict(self.metadata)},
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True)
class KnowledgeHit:
    """Un documento encontrado, con lo necesario para citarlo."""

    key: SourceKey
    document_id: str
    text: str
    score: float
    metadata: Mapping[str, MetadataValue]
