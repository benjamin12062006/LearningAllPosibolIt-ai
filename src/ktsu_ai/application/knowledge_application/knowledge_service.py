"""Fachada de aplicación para el conocimiento: implementa `IKnowledgeUseCase`.

Borrar una fuente o un proyecto no tiene más lógica que pedírselo al índice, así
que no tiene caso de uso propio (no extraer de más).
"""

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
from ktsu_ai.application.knowledge_application.use_cases import (
    replace_source,
    search_knowledge,
)
from ktsu_ai.application.knowledge_ports.out_knowledge_index import IKnowledgeIndex
from ktsu_ai.domain.knowledge.knowledge_document import SourceKey


class KnowledgeService:
    def __init__(self, index: IKnowledgeIndex) -> None:
        self._index = index

    async def replace_source(self, input: ReplaceSourceInput) -> ReplaceSourceOutput:
        return await replace_source.execute(self._index, input)

    async def remove_source(self, key: SourceKey) -> None:
        await self._index.delete_source(key)

    async def remove_project(self, organization_id: str, project_id: str) -> None:
        await self._index.delete_project(organization_id, project_id)

    async def search(self, input: SearchKnowledgeInput) -> SearchKnowledgeOutput:
        return await search_knowledge.execute(self._index, input)
