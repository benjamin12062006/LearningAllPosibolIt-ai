"""Configuración del servicio, leída una vez del entorno al arrancar (plan 01, S4).

Las variables del proceso ganan a las del archivo `.env`. Los secretos son
`SecretStr`: al imprimir la configuración salen como `**********`.
"""

from typing import Annotated, Final, Literal, Self

from pydantic import (
    BaseModel,
    Field,
    HttpUrl,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

# 32 caracteres aleatorios son 190 bits o más con el alfabeto de `make token`.
MIN_SERVICE_TOKEN_LENGTH: Final = 32

type LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]
# Niveles de razonamiento de Gemini 3.x (ficha 03 del agente, F1).
type ThinkingLevel = Literal["MINIMAL", "LOW", "MEDIUM", "HIGH"]


class ServerConfiguration(BaseModel):
    host: str
    port: int = Field(ge=1, le=65535)
    log_level: LogLevel


class AuthConfiguration(BaseModel):
    service_token: SecretStr


class QdrantConfiguration(BaseModel):
    url: HttpUrl
    api_key: SecretStr | None
    # Segundos enteros: es lo que admite el cliente de Qdrant.
    timeout_seconds: int = Field(ge=1, le=60)


class EmbeddingConfiguration(BaseModel):
    """Modelo de embeddings de Google por Vertex AI (plan E6, D5)."""

    model: str = Field(min_length=1)
    # Cambiarlas obliga a reindexar: la colección se crea con estas dimensiones.
    dimensions: int = Field(ge=8, le=3072)
    # Textos por petición. Medido el 2026-11-09 con Vertex activado: 32 textos de
    # ~1.400 tokens pasan en una petición (bitácora 02 del servicio).
    batch_size: int = Field(ge=1, le=250)
    # Peticiones a Google a la vez. Sin este límite LlamaIndex las lanza todas
    # juntas (`asyncio.gather`); con 2 o más usa su cola de trabajadores.
    concurrency: int = Field(ge=2, le=16)
    timeout_seconds: int = Field(ge=1, le=300)
    google_cloud_project: str = Field(min_length=1)
    google_cloud_location: str = Field(min_length=1)


class ChatModelConfiguration(BaseModel):
    """Modelo de chat del agente: Gemini por Vertex AI (plan 03 del agente, G1)."""

    model: str = Field(min_length=1)
    # Propia: `gemini-3.5-flash-lite` no existe en `us-central1`, donde están
    # los embeddings (ficha 03, E6).
    location: str = Field(min_length=1)
    # Google recomienda MEDIUM o HIGH para agentes que llaman a APIs (ficha 03, F1).
    thinking_level: ThinkingLevel
    # 65.536 es el máximo del modelo; el valor por defecto acota el coste.
    max_output_tokens: int = Field(ge=1, le=65_536)
    # Por petición al modelo. La ejecución entera tiene su propio plazo.
    timeout_seconds: int = Field(ge=1, le=120)
    google_cloud_project: str = Field(min_length=1)


CollectionName = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")]


class KnowledgeConfiguration(BaseModel):
    collection: CollectionName


class Configuration(BaseModel):
    server: ServerConfiguration
    auth: AuthConfiguration
    qdrant: QdrantConfiguration
    embedding: EmbeddingConfiguration
    knowledge: KnowledgeConfiguration
    nest_agent_base_url: HttpUrl | None = None
    agent_tools_collection: CollectionName = "ktsu_agent_tools"
    # Sin modelo, el agente está desactivado y su ruta responde 503.
    chat: ChatModelConfiguration | None = None

    @model_validator(mode="after")
    def _validate_distinct_collections(self) -> Self:
        if self.knowledge.collection == self.agent_tools_collection:
            raise ValueError("Las herramientas necesitan su propia colección.")
        return self

    @model_validator(mode="after")
    def _validate_agent_can_reach_nest(self) -> Self:
        # Un agente sin pasarela no podría ejecutar ninguna herramienta.
        if self.chat is not None and self.nest_agent_base_url is None:
            raise ValueError("CHAT_MODEL necesita NEST_AGENT_BASE_URL.")
        return self


class EnvironmentVariables(BaseSettings):
    """Las variables tal como están en el entorno; `loader` las agrupa."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ai_service_host: str = "127.0.0.1"
    ai_service_port: int = 8090
    ai_service_token: SecretStr = Field(min_length=MIN_SERVICE_TOKEN_LENGTH)
    log_level: LogLevel = "INFO"
    qdrant_url: HttpUrl = HttpUrl("http://127.0.0.1:56333")
    qdrant_api_key: SecretStr | None = None
    qdrant_timeout_seconds: int = 5
    knowledge_collection: str = "ktsu_knowledge"
    nest_agent_base_url: HttpUrl | None = None
    agent_tools_collection: CollectionName = "ktsu_agent_tools"
    embedding_model: str = "gemini-embedding-001"
    embedding_dimensions: int = 768
    embedding_batch_size: int = 32
    embedding_concurrency: int = 4
    embedding_timeout_seconds: int = 60
    # Obligatorio: el proyecto por defecto de `gcloud` puede ser otro.
    google_cloud_project: str = Field(min_length=1)
    google_cloud_location: str = "us-central1"
    # Vacío: agente desactivado.
    chat_model: str = ""
    chat_location: str = "global"
    chat_thinking_level: ThinkingLevel = "MEDIUM"
    chat_max_output_tokens: int = 4_096
    chat_timeout_seconds: int = 60

    @field_validator("nest_agent_base_url", mode="before")
    @classmethod
    def _blank_url_is_unset(cls, value: object) -> object:
        return None if value == "" else value
