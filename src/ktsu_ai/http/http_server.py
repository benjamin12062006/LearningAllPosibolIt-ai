"""Arranca uvicorn con la configuración del servidor."""

import uvicorn
from fastapi import FastAPI

from ktsu_ai.config.configuration import ServerConfiguration


def serve(app: FastAPI, config: ServerConfiguration) -> None:
    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower(),
        # Cada petición ya deja su línea (observability); la de uvicorn repetiría.
        access_log=False,
    )
