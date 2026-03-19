from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    database_url: str = "sqlite+aiosqlite:///./idealab.db"

    # LLM model choices
    reaction_model: str = "claude-haiku-4-5-20251001"
    report_model: str = "claude-sonnet-4-6"

    # Simulation defaults
    default_num_ticks: int = 8
    default_population_size: int = 30
    default_seed_count: int = 5
    max_discussions_per_tick: int = 5
    reaction_batch_size: int = 6

    # Asset uploads
    upload_dir: str = "uploads"
    max_upload_size_mb: int = 5
    max_assets_per_simulation: int = 5
    asset_analysis_model: str = "claude-haiku-4-5-20251001"

    # API
    cors_origins: list[str] = ["http://localhost:5173"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
