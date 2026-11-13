"""Qué hizo el reemplazo: Nest lo registra y las pruebas lo comprueban."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ReplaceSourceOutput:
    written: int
    unchanged: int
    removed: int
