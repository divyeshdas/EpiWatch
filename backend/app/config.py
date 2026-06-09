from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://epiwatch:epiwatch@localhost:5432/epiwatch"
    redis_url: str = "redis://localhost:6379"

    model_config = {"env_file": ".env"}


settings = Settings()
