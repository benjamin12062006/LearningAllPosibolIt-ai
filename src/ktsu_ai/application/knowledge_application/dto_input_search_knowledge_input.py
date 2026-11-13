"""Entrada de la búsqueda: la pregunta y el alcance que resolvió Nest."""

from dataclasses import dataclass

from ktsu_ai.domain.access.access_scope import AccessScope
from ktsu_ai.domain.knowledge.knowledge_document import SourceType


@dataclass(frozen=True)
class SearchKnowledgeInput:
    scope: AccessScope
    query: str
    limit: int
    # Vacío: todos los tipos.
    source_types: frozenset[SourceType]
