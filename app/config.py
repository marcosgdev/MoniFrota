from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    sisatec_codigo: str  = "0000"
    sisatec_key: str     = "MOCK"
    use_mock: bool       = True
    redis_url: str       = "redis://localhost:6379"
    database_url: str    = "postgresql+asyncpg://frotagov:frotagov@localhost/frotagov"
    dashboard_user: str  = "admin"
    dashboard_pass: str  = "admin"
    env: str             = "development"
    sync_interval_min: int = 3   # intervalo do scheduler intraday (minutos)

    class Config:
        env_file = ".env"

settings = Settings()
