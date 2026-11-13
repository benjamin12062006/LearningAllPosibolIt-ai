"""Resultado de la búsqueda: los documentos encontrados, del más al menos parecido."""

from dataclasses import dataclass

from ktsu_ai.domain.knowledge.knowledge_document import KnowledgeHit


@dataclass(frozen=True)
class SearchKnowledgeOutput:
    hits: tuple[KnowledgeHit, ...]
