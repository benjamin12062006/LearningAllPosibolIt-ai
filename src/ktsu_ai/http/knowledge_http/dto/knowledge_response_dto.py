"""Respuestas de las rutas de conocimiento, en camelCase como el resto de la API."""

from pydantic import BaseModel, ConfigDict, Field

from ktsu_ai.application.knowledge_application.dto_output_replace_source_output import (
    ReplaceSourceOutput,
)
from ktsu_ai.application.knowledge_application.dto_output_search_knowledge_output import (
    SearchKnowledgeOutput,
)
from ktsu_ai.domain.knowledge.knowledge_document import (
    KnowledgeHit,
    MetadataValue,
    SourceType,
)


class _CamelCase(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)


class ReplaceSourceResponse(_CamelCase):
    written: int
    unchanged: int
    removed: int

    @classmethod
    def from_output(cls, output: ReplaceSourceOutput) -> "ReplaceSourceResponse":
        return cls(
            written=output.written,
            unchanged=output.unchanged,
            removed=output.removed,
        )


class HitResponse(_CamelCase):
    project_id: str = Field(serialization_alias="projectId")
    source_type: SourceType = Field(serialization_alias="sourceType")
    source_id: str = Field(serialization_alias="sourceId")
    document_id: str = Field(serialization_alias="documentId")
    text: str
    score: float
    metadata: dict[str, MetadataValue]

    @classmethod
    def from_hit(cls, hit: KnowledgeHit) -> "HitResponse":
        return cls(
            project_id=hit.key.project_id,
            source_type=hit.key.source_type,
            source_id=hit.key.source_id,
            document_id=hit.document_id,
            text=hit.text,
            score=hit.score,
            metadata=dict(hit.metadata),
        )


class SearchResponse(_CamelCase):
    hits: list[HitResponse]

    @classmethod
    def from_output(cls, output: SearchKnowledgeOutput) -> "SearchResponse":
        return cls(hits=[HitResponse.from_hit(hit) for hit in output.hits])
