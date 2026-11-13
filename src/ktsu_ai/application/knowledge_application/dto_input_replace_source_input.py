"""Entrada de «reemplazar una fuente»: todos sus documentos tal como están ahora."""

from dataclasses import dataclass

from ktsu_ai.domain.knowledge.knowledge_document import KnowledgeDocument, SourceKey


@dataclass(frozen=True)
class ReplaceSourceInput:
    key: SourceKey
    documents: tuple[KnowledgeDocument, ...]
