from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://epiwatch:epiwatch@localhost:5432/epiwatch"
    redis_url: str = "redis://localhost:6379"

    # B2 hotspot clustering defaults — overridable via env or query param
    hotspot_eps_km: float = 2.0
    hotspot_min_pts: int = 3

    # B3 spike detection — trailing window size (in series points) and the
    # z-score thresholds that map to each severity tier.  outbreak_timeseries
    # data is monthly, so a window of 6 means "6-month rolling baseline".
    spike_window_size: int = 6
    spike_z_low: float = 2.0
    spike_z_medium: float = 3.0
    spike_z_high: float = 4.0
    spike_z_critical: float = 5.0

    model_config = {"env_file": ".env"}


settings = Settings()
