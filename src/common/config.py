"""Central settings, loaded from environment / .env. Never log secret fields."""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

SYNTHETIC_BANNER = "Synthetic data. Not for clinical use."


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_user: str = "priorauth"
    postgres_password: SecretStr = SecretStr("priorauth_local")
    postgres_db: str = "priorauth"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    fhir_base_url: str = "http://localhost:8080/fhir"
    payer_mock_url: str = "http://localhost:8090"

    llm_provider: Literal["fake", "azure", "openai"] = "fake"
    azure_openai_endpoint: str = ""
    azure_openai_api_key: SecretStr = SecretStr("")
    azure_openai_api_version: str = ""
    azure_openai_chat_deployment: str = ""
    azure_openai_embed_deployment: str = ""
    openai_base_url: str = ""
    openai_api_key: SecretStr = SecretStr("")
    llm_model: str = ""
    embed_model: str = ""

    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "priorauth-agent"
    azure_monitor_enabled: bool = False

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password.get_secret_value()}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
