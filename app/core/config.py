from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "Zerodha AI Trading Agent"
    
    # Kite Connect Settings
    KITE_API_KEY: str
    KITE_API_SECRET: str
    KITE_REDIRECT_URL: str = "http://localhost:8000/api/v1/auth/callback"
    
    # Database Settings
    DATABASE_URL: str = "sqlite:///./trading_agent.db"
    
    # Environment (DRY_RUN vs LIVE)
    TRADING_MODE: str = "DRY_RUN"
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings() # type: ignore
