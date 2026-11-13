"""La colección de conocimiento en Qdrant: su forma, sus índices y sus filtros.

Una sola colección para todas las organizaciones (plan E6, D4; Qdrant,
*Multitenancy*): `organization_id` con `is_tenant` agrupa en disco los puntos de
cada organización. LlamaIndex no sabe crear ese índice (ficha 03, L3), así que
la colección la crea este módulo antes de que LlamaIndex la use.
"""

from typing import Final

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qdrant

from ktsu_ai.domain.access.access_scope import AccessScope
from ktsu_ai.domain.knowledge.knowledge_document import (
    ServiceMetadata,
    SourceKey,
    SourceType,
)

# Nombre del vector denso; LlamaIndex lo recibe en `dense_vector_name`.
DENSE_VECTOR: Final = "dense"


_KEYWORD_INDEXES: Final = (
    ServiceMetadata.PROJECT_ID,
    ServiceMetadata.SOURCE_TYPE,
    ServiceMetadata.SOURCE_ID,
    ServiceMetadata.DOCUMENT_ID,
)


class CollectionMismatchError(RuntimeError):
    """La colección existe con otras dimensiones: cambiar de modelo exige reindexar."""


async def ensure_collection(
    client: AsyncQdrantClient, name: str, dimensions: int
) -> None:
    """Crea la colección y sus índices si faltan; si existe, comprueba su forma."""
    if await client.collection_exists(name):
        await _require_dimensions(client, name, dimensions)
    else:
        await client.create_collection(
            collection_name=name,
            vectors_config={
                DENSE_VECTOR: qdrant.VectorParams(
                    size=dimensions, distance=qdrant.Distance.COSINE
                )
            },
        )
    await _create_payload_indexes(client, name)


def source_filter(key: SourceKey) -> qdrant.Filter:
    return qdrant.Filter(
        must=[
            _matches(ServiceMetadata.ORGANIZATION_ID, key.organization_id),
            _matches(ServiceMetadata.PROJECT_ID, key.project_id),
            _matches(ServiceMetadata.SOURCE_TYPE, key.source_type.value),
            _matches(ServiceMetadata.SOURCE_ID, key.source_id),
        ]
    )


def project_filter(organization_id: str, project_id: str) -> qdrant.Filter:
    return qdrant.Filter(
        must=[
            _matches(ServiceMetadata.ORGANIZATION_ID, organization_id),
            _matches(ServiceMetadata.PROJECT_ID, project_id),
        ]
    )


def scope_filter(
    scope: AccessScope, source_types: frozenset[SourceType]
) -> qdrant.Filter:
    """El filtro de inquilino de cada búsqueda: organización y proyectos visibles."""
    conditions: list[qdrant.Condition] = [
        _matches(ServiceMetadata.ORGANIZATION_ID, scope.organization_id),
        qdrant.FieldCondition(
            key=ServiceMetadata.PROJECT_ID,
            match=qdrant.MatchAny(any=sorted(scope.project_ids)),
        ),
    ]
    if source_types:
        conditions.append(
            qdrant.FieldCondition(
                key=ServiceMetadata.SOURCE_TYPE,
                match=qdrant.MatchAny(any=sorted(t.value for t in source_types)),
            )
        )
    return qdrant.Filter(must=conditions)


async def _require_dimensions(
    client: AsyncQdrantClient, name: str, dimensions: int
) -> None:
    info = await client.get_collection(name)
    vectors = info.config.params.vectors
    dense = vectors.get(DENSE_VECTOR) if isinstance(vectors, dict) else None
    if dense is None or dense.size != dimensions:
        raise CollectionMismatchError(
            f"La colección {name} no tiene un vector «{DENSE_VECTOR}» de "
            f"{dimensions} dimensiones: borra la colección y reindexa."
        )


async def _create_payload_indexes(client: AsyncQdrantClient, name: str) -> None:
    """Crear un índice que ya existe con la misma forma no hace nada."""
    await client.create_payload_index(
        collection_name=name,
        field_name=ServiceMetadata.ORGANIZATION_ID,
        field_schema=qdrant.KeywordIndexParams(
            type=qdrant.KeywordIndexType.KEYWORD, is_tenant=True
        ),
    )
    for field in _KEYWORD_INDEXES:
        await client.create_payload_index(
            collection_name=name,
            field_name=field,
            field_schema=qdrant.PayloadSchemaType.KEYWORD,
        )


def _matches(key: str, value: str) -> qdrant.FieldCondition:
    return qdrant.FieldCondition(key=key, match=qdrant.MatchValue(value=value))
