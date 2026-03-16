from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:postgres@localhost:5432/meat_bot"
    telegram_bot_token: str = ""
    openai_api_key: str = ""
    redis_url: str = "redis://localhost:6379/0"

    model_config = {"env_file": ".env"}

    @property
    def database_url_fixed(self) -> str:
        """Fix Railway's postgres:// URL to work with SQLAlchemy 2.0."""
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg2://", 1)
        elif url.startswith("postgresql://") and "+psycopg2" not in url:
            url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return url


settings = Settings()
