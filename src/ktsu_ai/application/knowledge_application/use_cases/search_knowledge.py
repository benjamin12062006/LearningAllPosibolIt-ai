"""Caso de uso: buscar por significado dentro de lo que la persona puede ver."""

from ktsu_ai.application.knowledge_application.dto_input_search_knowledge_input import (
    SearchKnowledgeInput,
)
from ktsu_ai.application.knowledge_application.dto_output_search_knowledge_output import (
    SearchKnowledgeOutput,
)
from ktsu_ai.application.knowledge_ports.out_knowledge_index import IKnowledgeIndex


async def execute(
    index: IKnowledgeIndex, input: SearchKnowledgeInput
) -> SearchKnowledgeOutput:
    # Sin proyectos visibles no se consulta Qdrant: no hay filtro que poner.
    if input.scope.sees_nothing:
        return SearchKnowledgeOutput(hits=())

    hits = await index.search(input.query, input.scope, input.limit, input.source_types)
    return SearchKnowledgeOutput(hits=tuple(hits))
