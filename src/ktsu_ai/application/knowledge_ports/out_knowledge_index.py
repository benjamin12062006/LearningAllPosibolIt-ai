"""Puerto de salida: el índice donde vive el conocimiento (Qdrant con LlamaIndex)."""

from collections.abc import Sequence
from typing import Protocol

from ktsu_ai.domain.access.access_scope import AccessScope
from ktsu_ai.domain.knowledge.knowledge_document import (
    KnowledgeDocument,
    KnowledgeHit,
    SourceKey,
    SourceType,
)


class IKnowledgeIndex(Protocol):
    async def document_hashes(self, key: SourceKey) -> dict[str, str]:
        """`document_id → content_hash` de lo que ya está indexado de la fuente."""
        ...

    async def write_documents(
        self, key: SourceKey, documents: Sequence[KnowledgeDocument]
    ) -> None:
        """Escribe (o reescribe) estos documentos y quita sus trozos sobrantes."""
        ...

    async def delete_documents(
        self, key: SourceKey, document_ids: Sequence[str]
    ) -> None: ...

    async def delete_source(self, key: SourceKey) -> None: ...

    async def delete_project(self, organization_id: str, project_id: str) -> None: ...

    async def search(
        self,
        query: str,
        scope: AccessScope,
        limit: int,
        source_types: frozenset[SourceType],
    ) -> list[KnowledgeHit]:
        """Solo dentro del alcance. Sin tipos, en todos."""
        ...
