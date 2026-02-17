from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Risk Control TA"
    debug: bool = False

    model_config = {"env_prefix": "RCTA_"}


settings = Settings()
