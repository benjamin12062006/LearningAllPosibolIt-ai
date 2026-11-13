"""Caso de uso: dejar una fuente en Qdrant exactamente como la manda Nest.

Flujo: `documentos nuevos + hashes guardados -> qué escribir y qué quitar -> índice`.

Solo se escriben los documentos cuyo contenido cambió: así una hoja de 5.000
filas con una celda editada recalcula un embedding, no 5.000 (curso de
LlamaIndex, lección 19: no reprocesar lo que no cambió).
"""

from ktsu_ai.application.knowledge_application.dto_input_replace_source_input import (
    ReplaceSourceInput,
)
from ktsu_ai.application.knowledge_application.dto_output_replace_source_output import (
    ReplaceSourceOutput,
)
from ktsu_ai.application.knowledge_ports.out_knowledge_index import IKnowledgeIndex
from ktsu_ai.common.error import AppError, ErrorCode
from ktsu_ai.domain.knowledge.knowledge_document import KnowledgeDocument


async def execute(
    index: IKnowledgeIndex, input: ReplaceSourceInput
) -> ReplaceSourceOutput:
    _require_unique_ids(input.documents)
    stored = await index.document_hashes(input.key)

    changed = [
        document for document in input.documents if _has_changed(document, stored)
    ]
    wanted_ids = {document.document_id for document in input.documents}
    gone = sorted(
        document_id for document_id in stored if document_id not in wanted_ids
    )

    if changed:
        await index.write_documents(input.key, changed)
    if gone:
        await index.delete_documents(input.key, gone)

    return ReplaceSourceOutput(
        written=len(changed),
        unchanged=len(input.documents) - len(changed),
        removed=len(gone),
    )


def _require_unique_ids(documents: tuple[KnowledgeDocument, ...]) -> None:
    ids = [document.document_id for document in documents]
    if len(set(ids)) != len(ids):
        raise AppError(ErrorCode.KNOWLEDGE_DOCUMENT_DUPLICATED)


def _has_changed(document: KnowledgeDocument, stored: dict[str, str]) -> bool:
    return stored.get(document.document_id) != document.content_hash
