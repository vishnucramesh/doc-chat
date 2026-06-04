from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="development")
    backend_port: int = 8000
    cors_origins: str = "http://localhost:5173"

    supabase_url: str
    supabase_service_role_key: str
    supabase_storage_bucket: str = "documents"

    # Direct Postgres connection used by Alembic migrations only. The runtime
    # app talks to Supabase via PostgREST through the supabase-py client and
    # never opens a Postgres connection. Use the *direct* (port 5432) URL from
    # Supabase, not the pooler — migrations need persistent transactions.
    database_url: str

    nvidia_api_key: str
    nvidia_api_base: str = "https://integrate.api.nvidia.com/v1"
    # 49B Nemotron-super by default: best quality/reliability balance on NIM's
    # free tier (~2s, no cold-start surprises). Nano-8B is faster but an 8B
    # model occasionally parrots few-shot examples or over-refuses; the 70B is
    # higher quality but cold-starts at ~12s on the free tier. Override with
    # NVIDIA_CHAT_MODEL (e.g. nvidia/llama-3.1-nemotron-nano-8b-v1 for speed).
    nvidia_chat_model: str = "nvidia/llama-3.3-nemotron-super-49b-v1"
    nvidia_embed_model: str = "nvidia/nv-embedqa-e5-v5"
    embed_dim: int = 1024

    # Retrieval knobs — kept here so the eval harness can sweep them without
    # touching call sites.
    retrieval_top_k: int = 6
    retrieval_pool_k: int = 40
    # When > 0, each retrieved chunk is expanded with this many adjacent
    # chunks on either side (same document) and merged into a "context
    # window". 0 = classic chunk-per-block retrieval. 1 = ±1 neighbor (the
    # default — biggest continuity win for a ~2-3× prompt size cost).
    retrieval_neighbor_window: int = 1
    chunk_target_tokens: int = 500
    chunk_overlap_tokens: int = 80

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def supabase_jwks_url(self) -> str:
        """Public JWKS endpoint for the Supabase Auth service.

        Derived from SUPABASE_URL so it doesn't need its own env var — Supabase
        always exposes JWKS at this fixed path on the project URL.
        """
        return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
