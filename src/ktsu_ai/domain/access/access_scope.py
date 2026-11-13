"""Lo que una persona puede ver, tal como lo resolvió Nest (plan E6, D4 y D6).

El servicio de IA no conoce a las personas ni sus permisos: confía en el alcance
que le manda Nest y lo aplica en **cada** búsqueda. Ni el modelo ni el texto de
la pregunta pueden cambiarlo.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AccessScope:
    organization_id: str
    project_ids: frozenset[str]

    @property
    def sees_nothing(self) -> bool:
        """Sin proyectos visibles no hay nada que buscar (ni que preguntar a Qdrant)."""
        return len(self.project_ids) == 0
