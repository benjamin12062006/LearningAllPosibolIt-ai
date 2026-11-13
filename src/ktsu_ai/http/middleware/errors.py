"""Traduce cualquier error al cuerpo público `{ code, message, requestId }`."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ktsu_ai.common.error import AppError, ErrorCode
from ktsu_ai.http.middleware.observability import request_id_of

logger = logging.getLogger("ktsu_ai.http")


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(Exception, _handle_unexpected_error)


async def _handle_app_error(request: Request, error: Exception) -> JSONResponse:
    code = error.code if isinstance(error, AppError) else ErrorCode.INTERNAL_ERROR
    return error_response(request, code)


async def _handle_validation_error(request: Request, _: Exception) -> JSONResponse:
    return error_response(request, ErrorCode.VALIDATION_FAILED)


async def _handle_http_exception(request: Request, error: Exception) -> JSONResponse:
    """Starlette lanza 404 y 405 por su cuenta; el resto sería un fallo nuestro."""
    if isinstance(error, StarletteHTTPException) and error.status_code in (404, 405):
        return error_response(request, ErrorCode.ROUTE_NOT_FOUND)
    return await _handle_unexpected_error(request, error)


async def _handle_unexpected_error(request: Request, error: Exception) -> JSONResponse:
    # Solo el tipo y el identificador: el mensaje podría llevar datos de la petición.
    logger.error(
        "Error inesperado %s request_id=%s",
        type(error).__name__,
        request_id_of(request),
    )
    return error_response(request, ErrorCode.INTERNAL_ERROR)


def error_response(request: Request, code: ErrorCode) -> JSONResponse:
    definition = AppError(code).definition
    return JSONResponse(
        status_code=definition.status,
        content={
            "code": code.value,
            "message": {"es": definition.message.es, "en": definition.message.en},
            "requestId": request_id_of(request),
        },
    )
