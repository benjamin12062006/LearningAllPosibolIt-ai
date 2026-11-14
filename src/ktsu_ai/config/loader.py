"""Carga la configuración del entorno y la agrupa por responsabilidad."""

from pydantic import SecretStr

from ktsu_ai.config.configuration import (
    AuthConfiguration,
    ChatModelConfiguration,
    Configuration,
    EmbeddingConfiguration,
    EnvironmentVariables,
    KnowledgeConfiguration,
    QdrantConfiguration,
    ServerConfiguration,
)


def load_configuration(env_file: str | None = ".env") -> Configuration:
    """Lee el entorno (y `env_file` si existe). Sin token válido, lanza al arrancar."""
    variables = EnvironmentVariables(_env_file=env_file)
    return Configuration(
        server=ServerConfiguration(
            host=variables.ai_service_host,
            port=variables.ai_service_port,
            log_level=variables.log_level,
        ),
        auth=AuthConfiguration(service_token=variables.ai_service_token),
        qdrant=QdrantConfiguration(
            url=variables.qdrant_url,
            api_key=_present_secret(variables.qdrant_api_key),
            timeout_seconds=variables.qdrant_timeout_seconds,
        ),
        embedding=EmbeddingConfiguration(
            model=variables.embedding_model,
            dimensions=variables.embedding_dimensions,
            batch_size=variables.embedding_batch_size,
            concurrency=variables.embedding_concurrency,
            timeout_seconds=variables.embedding_timeout_seconds,
            google_cloud_project=variables.google_cloud_project,
            google_cloud_location=variables.google_cloud_location,
        ),
        knowledge=KnowledgeConfiguration(collection=variables.knowledge_collection),
        nest_agent_base_url=variables.nest_agent_base_url,
        agent_tools_collection=variables.agent_tools_collection,
        chat=_chat_model(variables),
    )


def _chat_model(variables: EnvironmentVariables) -> ChatModelConfiguration | None:
    """`CHAT_MODEL=` (vacío) deja el agente desactivado."""
    model = variables.chat_model.strip()
    if model == "":
        return None
    return ChatModelConfiguration(
        model=model,
        location=variables.chat_location,
        thinking_level=variables.chat_thinking_level,
        max_output_tokens=variables.chat_max_output_tokens,
        timeout_seconds=variables.chat_timeout_seconds,
        google_cloud_project=variables.google_cloud_project,
    )


def _present_secret(secret: SecretStr | None) -> SecretStr | None:
    """Una variable vacía (`QDRANT_API_KEY=`) es lo mismo que no tenerla."""
    if secret is None or secret.get_secret_value() == "":
        return None
    return secret
