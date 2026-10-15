"""Application settings, loaded from environment variables."""

from decimal import Decimal
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str
    frontend_origins: str = "http://localhost:5173"

    # Ingest. Scryfall and 17Lands both ask clients to identify themselves,
    # with a way to get in touch, so they can email rather than block.
    user_agent: str = "BoosterTutor/0.1 (+https://github.com/BumbleBeing/BoosterTutor; jackowen@gmail.com)"
    # Downloaded upstream files. `data/raw/` is gitignored.
    raw_data_dir: Path = Path(__file__).resolve().parents[2] / "data" / "raw"
    # The hand-authored tag taxonomy, one JSON file per set. Git-tracked: it is
    # the system of record, and the database tables are loaded from it.
    taxonomy_dir: Path = Path(__file__).resolve().parents[2] / "data" / "taxonomy"

    # Claude (ADR 0024). The key is set in api/.env locally and in Render's
    # dashboard, never in code. SecretStr keeps it out of logs and reprs.
    anthropic_api_key: SecretStr | None = None
    # The versioned prompt files, at the repository root beside the ADRs.
    prompts_dir: Path = Path(__file__).resolve().parents[3] / "docs" / "prompts"
    # ADR 0027: once today's Claude spend (UTC) reaches this, no further
    # call is made until tomorrow. About $5 a day while the app is small.
    daily_spend_cap_usd: Decimal = Decimal("5.00")

    @property
    def sqlalchemy_url(self) -> str:
        """Supabase hands out `postgresql://`, which SQLAlchemy reads as
        "use psycopg2". We installed psycopg 3, so name the driver explicitly."""
        url = self.database_url
        for prefix in ("postgresql://", "postgres://"):
            if url.startswith(prefix):
                return url.replace(prefix, "postgresql+psycopg://", 1)
        return url

    @property
    def cors_origins(self) -> list[str]:
        """Comma-separated in the environment, list in code. Declaring this as
        list[str] directly would make pydantic-settings try to JSON-parse the
        env var, which fails on a plain comma-separated string."""
        return [o.strip() for o in self.frontend_origins.split(",") if o.strip()]


settings = Settings()
