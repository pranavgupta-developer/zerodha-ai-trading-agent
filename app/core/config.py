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
    TRADING_MODE: str = "LIVE"
    
    # AI Settings
    GEMINI_API_KEY: str | None = None

    # Watchlist for automated trading (comma-separated Yahoo Finance symbols)
    TRADING_SYMBOLS: str = "RELIANCE.NS,TCS.NS,INFY.NS,HDFCBANK.NS,ICICIBANK.NS"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings() # type: ignore
