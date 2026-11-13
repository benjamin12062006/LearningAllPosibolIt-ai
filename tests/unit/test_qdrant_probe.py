"""`QdrantProbe` con un cliente simulado: versiones y fallos."""

import asyncio
from dataclasses import dataclass

import pytest

from ktsu_ai.domain.health.service_health import DependencyHealth
from ktsu_ai.infrastructure.database.qdrant.health import (
    QdrantProbe,
    is_compatible_with_client,
)


@dataclass
class FakeInfo:
    version: str


class FakeQdrant:
    def __init__(self, version: str | None) -> None:
        self._version = version

    async def info(self) -> FakeInfo:
        if self._version is None:
            raise ConnectionError("http://usuario:clave@qdrant no responde")
        return FakeInfo(self._version)


def check_with(version: str | None) -> DependencyHealth:
    # Doble de prueba: solo implementa `info`, lo único que usa la comprobación.
    return asyncio.run(QdrantProbe(FakeQdrant(version)).check())  # type: ignore[arg-type]


def test_available_with_the_same_minor_version() -> None:
    dependency = check_with("1.19.1")

    assert dependency.available
    assert dependency.version == "1.19.1"


@pytest.mark.parametrize(
    ("server", "compatible"),
    [
        ("1.18.3", True),
        ("1.20.0", True),
        ("1.21.0", False),
        ("1.17.0", False),
        ("2.19.0", False),
        ("dev", False),
    ],
)
def test_compatibility_follows_the_client_rule(server: str, compatible: bool) -> None:
    # El cliente instalado es qdrant-client 1.19.1 (pyproject.toml).
    assert is_compatible_with_client(server) is compatible


def test_an_incompatible_server_is_unavailable_but_keeps_its_version() -> None:
    dependency = check_with("2.0.0")

    assert not dependency.available
    assert dependency.version == "2.0.0"


def test_a_failure_is_unavailable_and_does_not_log_the_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    dependency = check_with(None)

    assert not dependency.available
    assert "clave" not in caplog.text
    assert "ConnectionError" in caplog.text
