from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Read from environment variables only. `make` loads `.env` for local runs;
    Easypanel injects them in production. See `.env.example` at the repository root."""

    model_config = SettingsConfigDict(extra="ignore")

    app_env: Literal["local", "production", "test"] = "local"
    database_url: str = Field(min_length=1)
    # NoDecode: read "a,b" as a comma-separated string instead of a JSON list.
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    session_cookie_name: str = "ekb_session"
    session_ttl_hours: int = Field(default=12, gt=0)
    cookie_secure: bool = True
    cookie_domain: str | None = None

    # Object storage (MinIO, S3 API). The bucket is publicly readable, not listable.
    s3_endpoint_url: str = Field(min_length=1)
    s3_access_key: str = Field(min_length=1)
    s3_secret_key: str = Field(min_length=1)
    s3_bucket: str = Field(min_length=1)
    s3_region: str = "us-east-1"
    # Where browsers fetch files from, e.g. https://files.example.dev/portfolio
    public_files_base_url: str = Field(min_length=1)

    # Absolute URLs used in AGENTS.md, llms.txt and the JSON Resume, e.g.
    # https://erick.dev and https://api.erick.dev
    public_site_url: str = Field(min_length=1)
    public_api_url: str = Field(min_length=1)

    # Hybrid search
    qdrant_url: str = Field(min_length=1)
    qdrant_api_key: str | None = None
    qdrant_collection: str = "portfolio"
    # Dense embeddings through OpenRouter. Changing the model or its dimension
    # needs `make reindex`: the collection is created with that size.
    openrouter_api_key: str = Field(min_length=1)
    dense_model: str = "openai/text-embedding-3-small"
    dense_dimension: int = Field(default=1536, gt=0)
    # Where fastembed keeps the BM25 files (a few KB of stopwords per language).
    fastembed_cache_dir: str | None = None

    # The site's agent, through OpenRouter (the same key as the embeddings). Each tier
    # lists fallbacks after the first model.
    chat_models: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["openai/gpt-oss-120b", "google/gemini-2.5-flash"]
    )
    chat_models_strong: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "openai/gpt-4.1-mini",
            "openai/gpt-4o-mini",
            "google/gemini-2.5-flash",
        ]
    )
    # What the agent may cost per day, in US$, across all visitors.
    chat_daily_budget_usd: float = Field(default=0.5, ge=0)

    # Traces of searches and of the agent go to Langfuse when both keys are set.
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    # LANGFUSE_BASE_URL is the name the Langfuse SDKs use; LANGFUSE_HOST the older one.
    langfuse_host: str = Field(
        default="https://cloud.langfuse.com",
        validation_alias=AliasChoices("langfuse_base_url", "langfuse_host"),
    )
    # Separates the site's traces from local runs and evals in Langfuse.
    langfuse_environment: str = Field(
        default="production",
        validation_alias=AliasChoices("langfuse_tracing_environment", "langfuse_environment"),
        pattern=r"^[a-z0-9_-]{1,40}$",
    )

    # Rate limit keys are HMACs of the client IP; the raw IP is never stored.
    ip_hash_secret: str = Field(min_length=32)

    # Only the worker needs these; the API starts without them.
    rabbitmq_url: str | None = None
    resend_api_key: str | None = None
    mail_from: str | None = None
    owner_email: str | None = None

    @field_validator("cors_origins", "chat_models", "chat_models_strong", mode="before")
    @classmethod
    def _split_origins(cls, raw: object) -> object:
        if isinstance(raw, str):
            return [origin.strip() for origin in raw.split(",") if origin.strip()]
        return raw

    @field_validator("cors_origins", mode="after")
    @classmethod
    def _explicit_origins(cls, origins: list[str]) -> list[str]:
        # Credentials are allowed, so "*" would let any website call the admin API
        # with the admin's cookie.
        if "*" in origins:
            raise ValueError("CORS_ORIGINS: list the site's origins, '*' is not allowed")
        return origins

    @field_validator(
        "cookie_domain",
        "rabbitmq_url",
        "resend_api_key",
        "mail_from",
        "owner_email",
        "qdrant_api_key",
        "fastembed_cache_dir",
        "langfuse_public_key",
        "langfuse_secret_key",
        mode="before",
    )
    @classmethod
    def _empty_is_none(cls, raw: object) -> object:
        return None if raw == "" else raw

    @field_validator("s3_endpoint_url", mode="after")
    @classmethod
    def _s3_host_without_underscore(cls, url: str) -> str:
        # botocore refuses such hosts when the client is built, so the API would not
        # start. Easypanel's internal names (project_service) have one.
        if "_" in (urlsplit(url).hostname or ""):
            raise ValueError(
                "S3_ENDPOINT_URL: the S3 client rejects hostnames with '_' (Easypanel's "
                "internal names); use the storage's public domain instead"
            )
        return url

    @field_validator("public_files_base_url", "public_site_url", "public_api_url", mode="after")
    @classmethod
    def _no_trailing_slash(cls, url: str) -> str:
        return url.rstrip("/")
