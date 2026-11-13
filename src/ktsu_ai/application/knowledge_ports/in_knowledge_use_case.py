"""Puerto de entrada: lo que la aplicación ofrece sobre el conocimiento."""

from typing import Protocol

from ktsu_ai.application.knowledge_application.dto_input_replace_source_input import (
    ReplaceSourceInput,
)
from ktsu_ai.application.knowledge_application.dto_input_search_knowledge_input import (
    SearchKnowledgeInput,
)
from ktsu_ai.application.knowledge_application.dto_output_replace_source_output import (
    ReplaceSourceOutput,
)
from ktsu_ai.application.knowledge_application.dto_output_search_knowledge_output import (
    SearchKnowledgeOutput,
)
from ktsu_ai.domain.knowledge.knowledge_document import SourceKey


class IKnowledgeUseCase(Protocol):
    async def replace_source(
        self, input: ReplaceSourceInput
    ) -> ReplaceSourceOutput: ...

    async def remove_source(self, key: SourceKey) -> None: ...

    async def remove_project(self, organization_id: str, project_id: str) -> None: ...

    async def search(self, input: SearchKnowledgeInput) -> SearchKnowledgeOutput: ...
