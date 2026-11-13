"""Configuración del servicio, leída una vez del entorno al arrancar (plan 01, S4).

Las variables del proceso ganan a las del archivo `.env`. Los secretos son
`SecretStr`: al imprimir la configuración salen como `**********`.
"""

from typing import Final, Literal

from pydantic import BaseModel, Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# 32 caracteres aleatorios son 190 bits o más con el alfabeto de `make token`.
MIN_SERVICE_TOKEN_LENGTH: Final = 32

type LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


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


class KnowledgeConfiguration(BaseModel):
    collection: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")


class Configuration(BaseModel):
    server: ServerConfiguration
    auth: AuthConfiguration
    qdrant: QdrantConfiguration
    embedding: EmbeddingConfiguration
    knowledge: KnowledgeConfiguration


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
    embedding_model: str = "gemini-embedding-001"
    embedding_dimensions: int = 768
    embedding_batch_size: int = 32
    embedding_concurrency: int = 4
    embedding_timeout_seconds: int = 60
    # Obligatorio: el proyecto por defecto de `gcloud` puede ser otro.
    google_cloud_project: str = Field(min_length=1)
    google_cloud_location: str = "us-central1"
