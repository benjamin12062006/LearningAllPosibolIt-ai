import asyncio

from ktsu_ai.application.health_application.health_service import HealthService
from ktsu_ai.domain.health.service_health import DependencyHealth, ServiceHealth


class FixedProbe:
    def __init__(self, dependency: DependencyHealth) -> None:
        self._dependency = dependency

    async def check(self) -> DependencyHealth:
        return self._dependency


class SlowProbe:
    """Tarda en responder: sirve para ver que las comprobaciones van a la vez."""

    def __init__(self, name: str, seconds: float) -> None:
        self._name = name
        self._seconds = seconds

    async def check(self) -> DependencyHealth:
        await asyncio.sleep(self._seconds)
        return DependencyHealth(name=self._name, available=True)


def test_is_ready_only_when_every_dependency_is_available() -> None:
    up = DependencyHealth(name="qdrant", available=True, version="1.19.1")
    down = DependencyHealth(name="modelo", available=False)

    assert ServiceHealth(dependencies=(up,)).is_ready
    assert not ServiceHealth(dependencies=(up, down)).is_ready


def test_reports_each_dependency_with_its_status_and_version() -> None:
    service = HealthService(
        probes=[
            FixedProbe(
                DependencyHealth(name="qdrant", available=True, version="1.19.1")
            ),
            FixedProbe(DependencyHealth(name="modelo", available=False)),
        ]
    )

    output = asyncio.run(service.check_health())

    assert not output.ready
    assert [(d.name, d.status, d.version) for d in output.dependencies] == [
        ("qdrant", "available", "1.19.1"),
        ("modelo", "unavailable", None),
    ]


def test_checks_the_dependencies_at_the_same_time() -> None:
    service = HealthService(
        probes=[SlowProbe("a", 0.2), SlowProbe("b", 0.2), SlowProbe("c", 0.2)]
    )

    async def timed() -> float:
        loop = asyncio.get_running_loop()
        started = loop.time()
        await service.check_health()
        return loop.time() - started

    # En serie serían 0,6 s.
    assert asyncio.run(timed()) < 0.45
