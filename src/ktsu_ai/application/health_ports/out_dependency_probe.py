"""Puerto de salida: comprobar si una dependencia externa responde."""

from typing import Protocol

from ktsu_ai.domain.health.service_health import DependencyHealth


class IDependencyProbe(Protocol):
    """Lo que la aplicación necesita de infraestructura para saber su salud.

    `check` nunca lanza: si la dependencia no responde, devuelve
    `available=False`. Así una dependencia caída no tumba la comprobación.
    """

    async def check(self) -> DependencyHealth: ...
