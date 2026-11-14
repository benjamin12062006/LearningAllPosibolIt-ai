from pathlib import Path

import pytest
from pydantic import ValidationError

from ktsu_ai.config.loader import load_configuration

VALID_TOKEN = "t" * 32


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cada prueba parte solo de lo que ella misma pone en el entorno."""
    for name in (
        "AI_SERVICE_HOST",
        "AI_SERVICE_PORT",
        "AI_SERVICE_TOKEN",
        "LOG_LEVEL",
        "QDRANT_URL",
        "QDRANT_API_KEY",
        "QDRANT_TIMEOUT_SECONDS",
        "KNOWLEDGE_COLLECTION",
        "EMBEDDING_MODEL",
        "EMBEDDING_DIMENSIONS",
        "EMBEDDING_BATCH_SIZE",
        "EMBEDDING_CONCURRENCY",
        "EMBEDDING_TIMEOUT_SECONDS",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_LOCATION",
        "NEST_AGENT_BASE_URL",
        "AGENT_TOOLS_COLLECTION",
        "CHAT_MODEL",
        "CHAT_LOCATION",
        "CHAT_THINKING_LEVEL",
        "CHAT_MAX_OUTPUT_TOKENS",
        "CHAT_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def google_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "estadistica-forms-api")


@pytest.mark.usefixtures("google_project")
def test_defaults_point_to_local_development(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_SERVICE_TOKEN", VALID_TOKEN)

    configuration = load_configuration(env_file=None)

    assert configuration.server.host == "127.0.0.1"
    assert configuration.server.port == 8090
    assert str(configuration.qdrant.url) == "http://127.0.0.1:56333/"
    assert configuration.qdrant.api_key is None
    assert configuration.knowledge.collection == "ktsu_knowledge"
    assert configuration.embedding.model == "gemini-embedding-001"
    assert configuration.embedding.dimensions == 768
    assert configuration.embedding.batch_size == 32
    assert configuration.embedding.concurrency == 4
    assert configuration.embedding.google_cloud_project == "estadistica-forms-api"
    assert configuration.embedding.google_cloud_location == "us-central1"


def test_refuses_to_start_without_a_google_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_SERVICE_TOKEN", VALID_TOKEN)

    with pytest.raises(ValidationError):
        load_configuration(env_file=None)


@pytest.mark.usefixtures("google_project")
@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("EMBEDDING_DIMENSIONS", "4"),
        ("EMBEDDING_DIMENSIONS", "4096"),
        ("EMBEDDING_BATCH_SIZE", "0"),
        ("EMBEDDING_BATCH_SIZE", "251"),
        # 1 no limita: LlamaIndex volvería a lanzar todas las peticiones a la vez.
        ("EMBEDDING_CONCURRENCY", "1"),
        ("EMBEDDING_CONCURRENCY", "17"),
        ("KNOWLEDGE_COLLECTION", "con espacios"),
    ],
)
def test_refuses_out_of_range_knowledge_settings(
    monkeypatch: pytest.MonkeyPatch, variable: str, value: str
) -> None:
    monkeypatch.setenv("AI_SERVICE_TOKEN", VALID_TOKEN)
    monkeypatch.setenv(variable, value)

    with pytest.raises(ValidationError):
        load_configuration(env_file=None)


@pytest.mark.usefixtures("google_project")
def test_refuses_to_start_without_a_token() -> None:
    with pytest.raises(ValidationError):
        load_configuration(env_file=None)


@pytest.mark.usefixtures("google_project")
def test_refuses_a_short_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_SERVICE_TOKEN", "t" * 31)

    with pytest.raises(ValidationError):
        load_configuration(env_file=None)


@pytest.mark.usefixtures("google_project")
def test_an_empty_qdrant_key_means_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_SERVICE_TOKEN", VALID_TOKEN)
    monkeypatch.setenv("QDRANT_API_KEY", "")

    assert load_configuration(env_file=None).qdrant.api_key is None


@pytest.mark.usefixtures("google_project")
def test_process_variables_win_over_the_env_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(f"AI_SERVICE_TOKEN={VALID_TOKEN}\nAI_SERVICE_PORT=9000\n")
    monkeypatch.setenv("AI_SERVICE_PORT", "9100")

    assert load_configuration(env_file=str(env_file)).server.port == 9100


@pytest.mark.usefixtures("google_project")
def test_secrets_never_appear_when_printed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_SERVICE_TOKEN", VALID_TOKEN)
    monkeypatch.setenv("QDRANT_API_KEY", "clave-secreta-de-qdrant")

    printed = repr(load_configuration(env_file=None))

    assert VALID_TOKEN not in printed
    assert "clave-secreta-de-qdrant" not in printed


@pytest.mark.usefixtures("google_project")
def test_without_chat_model_the_agent_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_SERVICE_TOKEN", VALID_TOKEN)
    monkeypatch.setenv("CHAT_MODEL", "  ")

    assert load_configuration(env_file=None).chat is None


@pytest.mark.usefixtures("google_project")
def test_chat_model_gets_its_own_location_and_safe_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_SERVICE_TOKEN", VALID_TOKEN)
    monkeypatch.setenv("CHAT_MODEL", "gemini-3.5-flash-lite")
    monkeypatch.setenv("NEST_AGENT_BASE_URL", "http://127.0.0.1:8080")

    chat = load_configuration(env_file=None).chat

    assert chat is not None
    assert chat.model == "gemini-3.5-flash-lite"
    # No `us-central1` (la de los embeddings): ahí el modelo responde 404.
    assert chat.location == "global"
    assert chat.thinking_level == "MEDIUM"
    assert chat.max_output_tokens == 4_096
    assert chat.timeout_seconds == 60
    assert chat.google_cloud_project == "estadistica-forms-api"


@pytest.mark.usefixtures("google_project")
def test_chat_model_without_nest_refuses_to_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_SERVICE_TOKEN", VALID_TOKEN)
    monkeypatch.setenv("CHAT_MODEL", "gemini-3.5-flash-lite")

    with pytest.raises(ValidationError, match="NEST_AGENT_BASE_URL"):
        load_configuration(env_file=None)


@pytest.mark.usefixtures("google_project")
@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("CHAT_THINKING_LEVEL", "EXTREME"),
        ("CHAT_MAX_OUTPUT_TOKENS", "0"),
        ("CHAT_MAX_OUTPUT_TOKENS", "65537"),
        ("CHAT_TIMEOUT_SECONDS", "0"),
        ("CHAT_TIMEOUT_SECONDS", "121"),
        ("CHAT_LOCATION", ""),
    ],
)
def test_refuses_out_of_range_chat_settings(
    monkeypatch: pytest.MonkeyPatch, variable: str, value: str
) -> None:
    monkeypatch.setenv("AI_SERVICE_TOKEN", VALID_TOKEN)
    monkeypatch.setenv("CHAT_MODEL", "gemini-3.5-flash-lite")
    monkeypatch.setenv("NEST_AGENT_BASE_URL", "http://127.0.0.1:8080")
    monkeypatch.setenv(variable, value)

    with pytest.raises(ValidationError):
        load_configuration(env_file=None)
