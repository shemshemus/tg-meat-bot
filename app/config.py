from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:postgres@localhost:5432/meat_bot"
    telegram_bot_token: str = ""
    openai_api_key: str = ""

    model_config = {"env_file": ".env"}


settings = Settings()
