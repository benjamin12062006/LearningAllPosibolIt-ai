"""Rutas de conocimiento (plan E6, E6.1a). Solo para Nest, con el token de servicio.

- `PUT    …/organizations/{o}/projects/{p}/sources/{type}/{id}`: deja la fuente
  exactamente con estos documentos (los que faltan se quitan).
- `DELETE …/organizations/{o}/projects/{p}/sources/{type}/{id}`: quita la fuente.
- `DELETE …/organizations/{o}/projects/{p}`: quita todo el proyecto.
- `POST   /v1/knowledge/search`: busca dentro del alcance que manda Nest.

Los borrados responden 204 aunque no hubiera nada: Nest puede repetirlos.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response, status

from ktsu_ai.application.knowledge_application.dto_input_replace_source_input import (
    ReplaceSourceInput,
)
from ktsu_ai.application.knowledge_ports.in_knowledge_use_case import (
    IKnowledgeUseCase,
)
from ktsu_ai.common.error import AppError, ErrorCode
from ktsu_ai.domain.knowledge.knowledge_document import SourceKey, SourceType
from ktsu_ai.http.knowledge_http.dto.knowledge_request_dto import (
    KnowledgeLimits,
    ReplaceSourceRequest,
    SearchRequest,
)
from ktsu_ai.http.knowledge_http.dto.knowledge_response_dto import (
    ReplaceSourceResponse,
    SearchResponse,
)
from ktsu_ai.http.middleware.internal_auth import InternalAuth

UUID_PATTERN = r"^[0-9a-fA-F-]{36}$"

UuidPath = Annotated[str, Path(pattern=UUID_PATTERN)]

PROJECT_PATH = "/v1/knowledge/organizations/{organization_id}/projects/{project_id}"
SOURCE_PATH = PROJECT_PATH + "/sources/{source_type}/{source_id}"


def build_knowledge_router(
    knowledge: IKnowledgeUseCase, auth: InternalAuth
) -> APIRouter:
    router = APIRouter(tags=["knowledge"], dependencies=[Depends(auth)])

    @router.put(SOURCE_PATH)
    async def replace_source(
        organization_id: UuidPath,
        project_id: UuidPath,
        source_type: SourceType,
        source_id: UuidPath,
        body: ReplaceSourceRequest,
    ) -> ReplaceSourceResponse:
        if (
            source_type != SourceType.WORKSHEET
            and len(body.documents) > KnowledgeLimits.MAX_DOCUMENTS
        ):
            raise AppError(ErrorCode.VALIDATION_FAILED)
        key = SourceKey(organization_id, project_id, source_type, source_id)
        documents = tuple(document.to_domain() for document in body.documents)
        output = await knowledge.replace_source(ReplaceSourceInput(key, documents))
        return ReplaceSourceResponse.from_output(output)

    @router.delete(SOURCE_PATH, status_code=status.HTTP_204_NO_CONTENT)
    async def remove_source(
        organization_id: UuidPath,
        project_id: UuidPath,
        source_type: SourceType,
        source_id: UuidPath,
    ) -> Response:
        key = SourceKey(organization_id, project_id, source_type, source_id)
        await knowledge.remove_source(key)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.delete(PROJECT_PATH, status_code=status.HTTP_204_NO_CONTENT)
    async def remove_project(
        organization_id: UuidPath, project_id: UuidPath
    ) -> Response:
        await knowledge.remove_project(organization_id, project_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.post("/v1/knowledge/search")
    async def search(body: SearchRequest) -> SearchResponse:
        output = await knowledge.search(body.to_input())
        return SearchResponse.from_output(output)

    return router
