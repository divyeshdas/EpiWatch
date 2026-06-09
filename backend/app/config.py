from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://epiwatch:epiwatch@localhost:5432/epiwatch"
    redis_url: str = "redis://localhost:6379"

    # B2 hotspot clustering defaults — overridable via env or query param
    hotspot_eps_km: float = 2.0
    hotspot_min_pts: int = 3

    model_config = {"env_file": ".env"}


settings = Settings()
