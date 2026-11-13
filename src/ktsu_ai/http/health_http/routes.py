"""Rutas de salud (plan 01, S6).

- `GET /health`: el proceso está vivo. Sin token ni datos, para el orquestador.
- `GET /v1/health`: estado de las dependencias, solo para Nest. 503 si alguna no
  responde, para que Nest marque la IA como no disponible.
"""

from fastapi import APIRouter, Depends, Response, status

from ktsu_ai.application.health_ports.in_health_use_case import IHealthUseCase
from ktsu_ai.http.health_http.dto.health_response_dto import HealthResponse
from ktsu_ai.http.middleware.internal_auth import InternalAuth


def build_health_router(health: IHealthUseCase, auth: InternalAuth) -> APIRouter:
    router = APIRouter(tags=["health"])

    @router.get("/health")
    async def liveness() -> dict[str, str]:
        return {"status": "ok"}

    @router.get(
        "/v1/health",
        dependencies=[Depends(auth)],
        responses={503: {"model": HealthResponse}},
    )
    async def readiness(response: Response) -> HealthResponse:
        output = await health.check_health()
        if not output.ready:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse.from_output(output)

    return router
