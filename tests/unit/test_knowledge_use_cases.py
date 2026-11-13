"""Casos de uso de conocimiento con un índice en memoria."""

import asyncio
from collections.abc import Sequence

import pytest

from ktsu_ai.application.knowledge_application.dto_input_replace_source_input import (
    ReplaceSourceInput,
)
from ktsu_ai.application.knowledge_application.dto_input_search_knowledge_input import (
    SearchKnowledgeInput,
)
from ktsu_ai.application.knowledge_application.knowledge_service import (
    KnowledgeService,
)
from ktsu_ai.common.error import AppError, ErrorCode
from ktsu_ai.domain.access.access_scope import AccessScope
from ktsu_ai.domain.knowledge.knowledge_document import (
    KnowledgeDocument,
    KnowledgeHit,
    SourceKey,
    SourceType,
)

KEY = SourceKey("org-1", "project-1", SourceType.CATALOG, "project-1")


class MemoryIndex:
    """Guarda `document_id → hash` y anota cada escritura y borrado."""

    def __init__(self) -> None:
        self.hashes: dict[str, str] = {}
        self.written: list[str] = []
        self.deleted: list[str] = []
        self.searches = 0

    async def document_hashes(self, key: SourceKey) -> dict[str, str]:
        return dict(self.hashes)

    async def write_documents(
        self, key: SourceKey, documents: Sequence[KnowledgeDocument]
    ) -> None:
        for document in documents:
            self.hashes[document.document_id] = document.content_hash
            self.written.append(document.document_id)

    async def delete_documents(
        self, key: SourceKey, document_ids: Sequence[str]
    ) -> None:
        for document_id in document_ids:
            self.hashes.pop(document_id)
            self.deleted.append(document_id)

    async def delete_source(self, key: SourceKey) -> None:
        self.hashes.clear()

    async def delete_project(self, organization_id: str, project_id: str) -> None:
        self.hashes.clear()

    async def search(
        self,
        query: str,
        scope: AccessScope,
        limit: int,
        source_types: frozenset[SourceType],
    ) -> list[KnowledgeHit]:
        self.searches += 1
        return []


def document(document_id: str, text: str, **metadata: str) -> KnowledgeDocument:
    return KnowledgeDocument(document_id=document_id, text=text, metadata=metadata)


def replace(service: KnowledgeService, *documents: KnowledgeDocument):  # type: ignore[no-untyped-def]
    return asyncio.run(service.replace_source(ReplaceSourceInput(KEY, documents)))


def test_first_replace_writes_everything() -> None:
    index = MemoryIndex()

    output = replace(
        KnowledgeService(index), document("a", "uno"), document("b", "dos")
    )

    assert (output.written, output.unchanged, output.removed) == (2, 0, 0)
    assert index.written == ["a", "b"]


def test_only_changed_documents_are_written_again() -> None:
    index = MemoryIndex()
    service = KnowledgeService(index)
    replace(service, document("a", "uno"), document("b", "dos"))
    index.written.clear()

    output = replace(service, document("a", "uno"), document("b", "dos editado"))

    assert (output.written, output.unchanged, output.removed) == (1, 1, 0)
    assert index.written == ["b"]


def test_a_metadata_change_also_counts_as_a_change() -> None:
    index = MemoryIndex()
    service = KnowledgeService(index)
    replace(service, document("a", "uno", outcome="valid"))
    index.written.clear()

    output = replace(service, document("a", "uno", outcome="invalid"))

    assert output.written == 1


def test_documents_missing_from_the_new_set_are_removed() -> None:
    index = MemoryIndex()
    service = KnowledgeService(index)
    replace(service, document("a", "uno"), document("b", "dos"), document("c", "tres"))

    output = replace(service, document("b", "dos"))

    assert output.removed == 2
    assert index.deleted == ["a", "c"]
    assert set(index.hashes) == {"b"}


def test_an_empty_replace_empties_the_source() -> None:
    index = MemoryIndex()
    service = KnowledgeService(index)
    replace(service, document("a", "uno"))

    output = replace(service)

    assert output.removed == 1
    assert index.hashes == {}


def test_repeated_document_ids_are_rejected_before_touching_the_index() -> None:
    index = MemoryIndex()

    with pytest.raises(AppError) as raised:
        replace(KnowledgeService(index), document("a", "uno"), document("a", "otro"))

    assert raised.value.code is ErrorCode.KNOWLEDGE_DOCUMENT_DUPLICATED
    assert index.written == []


def test_searching_with_no_visible_projects_does_not_ask_the_index() -> None:
    index = MemoryIndex()

    output = asyncio.run(
        KnowledgeService(index).search(
            SearchKnowledgeInput(
                scope=AccessScope("org-1", frozenset()),
                query="zapatillas",
                limit=5,
                source_types=frozenset(),
            )
        )
    )

    assert output.hits == ()
    assert index.searches == 0


def test_content_hash_ignores_metadata_order() -> None:
    first = KnowledgeDocument("a", "texto", {"x": "1", "y": 2})
    second = KnowledgeDocument("a", "texto", {"y": 2, "x": "1"})

    assert first.content_hash == second.content_hash
