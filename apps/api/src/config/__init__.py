"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/investment"
    FERNET_KEY: str = ""          # base64-urlsafe 32-byte key; required for secret encryption
    TIINGO_API_KEY: str = ""
    LOG_LEVEL: str = "INFO"
    APP_VERSION: str = "0.1.0"

    # ------------------------------------------------------------------
    # OPTIONS SYSTEM (Phase 11B–11F)
    # Hard-isolated from V2 / equity / governance / live execution.
    # ------------------------------------------------------------------
    # Master enable. Even when True, no live execution is wired in v1.
    OPTIONS_ENABLED: bool = False
    # PERMANENT v1 KILL SWITCH. Mirrors ML_CAN_AFFECT_TRADES discipline.
    # Setting to False would require a new design phase + explicit
    # operator approval. v1 has NO live execution path.
    OPTIONS_PAPER_ONLY: bool = True
    # PERMANENT v1 KILL SWITCH. Options ML output never reaches the
    # paper-trade-decision path; this flag enforces that contractually.
    # Setting to True would require a new design phase + explicit
    # operator approval.
    OPTIONS_ML_CAN_AFFECT_TRADES: bool = False
    # Provider adapter selector; v1 = ThetaData. v2 may add Polygon /
    # ORATS via separate adapters.
    OPTIONS_DATA_PROVIDER: str = "thetadata"
    # Snapshot cadence (frozen v1).
    OPTIONS_SNAPSHOT_INTERVAL_MINUTES: int = 15
    # Default fill model. Alternative: "mid_minus_one_tick".
    OPTIONS_DEFAULT_FILL_MODEL: str = "mid_plus_25_pct_spread"


settings = Settings()
