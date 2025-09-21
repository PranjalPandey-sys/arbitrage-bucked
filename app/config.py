"""Configuration management for arbitrage backend."""

import os
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    # Server Configuration
    host: str = Field(default="0.0.0.0", env="HOST")
    port: int = Field(default=8000, env="PORT")
    debug: bool = Field(default=False, env="DEBUG")
    workers: int = Field(default=4, env="WORKERS")
    
    # Scraping Configuration
    scrape_timeout: int = Field(default=30, env="SCRAPE_TIMEOUT")
    retry_attempts: int = Field(default=3, env="RETRY_ATTEMPTS")
    delay_between_requests: float = Field(default=1.0, env="DELAY_BETWEEN_REQUESTS")
    concurrent_scrapers: int = Field(default=6, env="CONCURRENT_SCRAPERS")
    
    # Matching Configuration
    fuzzy_threshold: int = Field(default=94, env="FUZZY_THRESHOLD")
    time_tolerance_minutes: int = Field(default=15, env="TIME_TOLERANCE_MINUTES")
    odds_tolerance: float = Field(default=0.01, env="ODDS_TOLERANCE")
    
    # Arbitrage Detection
    min_arb_percentage: float = Field(default=0.5, env="MIN_ARB_PERCENTAGE")
    min_profit_amount: float = Field(default=10.0, env="MIN_PROFIT_AMOUNT")
    default_bankroll: float = Field(default=1000.0, env="DEFAULT_BANKROLL")
    
    # Data Freshness (seconds)
    live_odds_max_age: int = Field(default=10, env="LIVE_ODDS_MAX_AGE")
    prematch_odds_max_age: int = Field(default=300, env="PREMATCH_ODDS_MAX_AGE")
    
    # Refresh Intervals (seconds)
    live_refresh_interval: int = Field(default=5, env="LIVE_REFRESH_INTERVAL")
    prematch_refresh_interval: int = Field(default=60, env="PREMATCH_REFRESH_INTERVAL")
    
    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_file: str = Field(default="arbitrage.log", env="LOG_FILE")
    save_raw_data: bool = Field(default=True, env="SAVE_RAW_DATA")
    export_csv: bool = Field(default=True, env="EXPORT_CSV")
    
    # Browser Settings
    headless: bool = Field(default=True, env="HEADLESS")
    user_agent: str = Field(
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        env="USER_AGENT"
    )
    
    # API Settings
    cors_origins: str = Field(default="http://localhost:3000", env="CORS_ORIGINS")
    rate_limit_requests: int = Field(default=100, env="RATE_LIMIT_REQUESTS")
    rate_limit_window: int = Field(default=60, env="RATE_LIMIT_WINDOW")
    
    # Bookmaker Settings
    enabled_bookmakers: List[str] = [
        "mostbet", "stake", "leon", "parimatch", "onexbet", "onewin"
    ]
    
    # Sports & Markets
    supported_sports: List[str] = [
        "football", "basketball", "tennis", "cricket", "baseball", "hockey",
        "esports", "pubg", "csgo", "dota2", "valorant", "lol", "cod"
    ]
    
    supported_markets: List[str] = [
        "moneyline", "1x2", "double_chance", "totals", "handicap", 
        "team_totals", "player_props", "period_markets", "map_winner",
        "total_maps", "round_handicap", "first_blood", "kills_over_under"
    ]
    
    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )


# Global settings instance
settings = Settings()