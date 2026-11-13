"""Cuerpos de las rutas de conocimiento. Límites con nombre: Nest los conoce."""

import re
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ktsu_ai.application.knowledge_application.dto_input_search_knowledge_input import (
    SearchKnowledgeInput,
)
from ktsu_ai.domain.access.access_scope import AccessScope
from ktsu_ai.domain.knowledge.knowledge_document import (
    RESERVED_METADATA_KEYS,
    KnowledgeDocument,
    MetadataValue,
    SourceType,
)


class KnowledgeLimits:
    # Una hoja tiene como mucho 5.000 filas (límite de E5): cabe en una fuente.
    MAX_DOCUMENTS: Final = 5_000
    MAX_TEXT_LENGTH: Final = 8_000
    MAX_METADATA_KEYS: Final = 20
    MAX_METADATA_TEXT: Final = 500
    MAX_DOCUMENT_ID_LENGTH: Final = 200
    MAX_QUERY_LENGTH: Final = 1_000
    MAX_VISIBLE_PROJECTS: Final = 500
    MAX_RESULTS: Final = 20
    DEFAULT_RESULTS: Final = 8


METADATA_KEY_PATTERN: Final = re.compile(r"^[a-z][a-z0-9_]{0,39}$")

Uuid = Annotated[str, Field(pattern=r"^[0-9a-fA-F-]{36}$")]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DocumentRequest(_Strict):
    document_id: str = Field(
        alias="documentId",
        min_length=1,
        max_length=KnowledgeLimits.MAX_DOCUMENT_ID_LENGTH,
    )
    text: str = Field(min_length=1, max_length=KnowledgeLimits.MAX_TEXT_LENGTH)
    metadata: dict[str, MetadataValue] = Field(
        default_factory=dict, max_length=KnowledgeLimits.MAX_METADATA_KEYS
    )

    @field_validator("metadata")
    @classmethod
    def _metadata_is_safe(
        cls, metadata: dict[str, MetadataValue]
    ) -> dict[str, MetadataValue]:
        for name, value in metadata.items():
            if not METADATA_KEY_PATTERN.match(name) or name in RESERVED_METADATA_KEYS:
                raise ValueError(f"Metadato no permitido: {name}")
            if (
                isinstance(value, str)
                and len(value) > KnowledgeLimits.MAX_METADATA_TEXT
            ):
                raise ValueError(f"Metadato demasiado largo: {name}")
        return metadata

    def to_domain(self) -> KnowledgeDocument:
        return KnowledgeDocument(
            document_id=self.document_id, text=self.text, metadata=self.metadata
        )


class ReplaceSourceRequest(_Strict):
    documents: list[DocumentRequest] = Field(max_length=KnowledgeLimits.MAX_DOCUMENTS)


class SearchRequest(_Strict):
    organization_id: Uuid = Field(alias="organizationId")
    project_ids: list[Uuid] = Field(
        alias="projectIds", max_length=KnowledgeLimits.MAX_VISIBLE_PROJECTS
    )
    query: str = Field(min_length=1, max_length=KnowledgeLimits.MAX_QUERY_LENGTH)
    limit: int = Field(
        default=KnowledgeLimits.DEFAULT_RESULTS, ge=1, le=KnowledgeLimits.MAX_RESULTS
    )
    source_types: list[SourceType] = Field(default_factory=list, alias="sourceTypes")

    def to_input(self) -> SearchKnowledgeInput:
        return SearchKnowledgeInput(
            scope=AccessScope(
                organization_id=self.organization_id,
                project_ids=frozenset(self.project_ids),
            ),
            query=self.query.strip(),
            limit=self.limit,
            source_types=frozenset(self.source_types),
        )
