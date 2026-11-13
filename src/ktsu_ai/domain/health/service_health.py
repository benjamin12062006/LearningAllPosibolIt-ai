"""Salud del servicio: qué dependencias responden y si se puede trabajar."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DependencyHealth:
    """Una dependencia externa (Qdrant, más adelante el modelo) y si responde."""

    name: str
    available: bool
    # Versión que informa la dependencia, si respondió; sirve para comprobar que
    # el cliente y el servidor son compatibles.
    version: str | None = None


@dataclass(frozen=True)
class ServiceHealth:
    dependencies: tuple[DependencyHealth, ...]

    @property
    def is_ready(self) -> bool:
        """Listo solo si responden todas las dependencias."""
        return all(dependency.available for dependency in self.dependencies)
