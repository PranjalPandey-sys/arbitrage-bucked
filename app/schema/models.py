"""Pydantic models for arbitrage detection system."""

from datetime import datetime
from typing import List, Optional, Dict, Any, Union
from decimal import Decimal
from enum import Enum
from pydantic import BaseModel, Field, validator, ConfigDict


class SportType(str, Enum):
    FOOTBALL = "football"
    BASKETBALL = "basketball"
    TENNIS = "tennis"
    CRICKET = "cricket"
    BASEBALL = "baseball"
    HOCKEY = "hockey"
    ESPORTS = "esports"
    PUBG = "pubg"
    CSGO = "csgo"
    DOTA2 = "dota2"
    VALORANT = "valorant"
    LOL = "lol"
    COD = "cod"


class MarketType(str, Enum):
    MONEYLINE = "moneyline"
    ONE_X_TWO = "1x2"
    DOUBLE_CHANCE = "double_chance"
    TOTALS = "totals"
    HANDICAP = "handicap"
    TEAM_TOTALS = "team_totals"
    PLAYER_PROPS = "player_props"
    PERIOD_MARKETS = "period_markets"
    MAP_WINNER = "map_winner"
    TOTAL_MAPS = "total_maps"
    ROUND_HANDICAP = "round_handicap"
    FIRST_BLOOD = "first_blood"
    KILLS_OVER_UNDER = "kills_over_under"


class BookmakerName(str, Enum):
    MOSTBET = "mostbet"
    STAKE = "stake"
    LEON = "leon"
    PARIMATCH = "parimatch"
    ONEXBET = "1xbet"
    ONEWIN = "1win"


class OutcomeData(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    
    name: str = Field(..., description="Outcome name (e.g., 'Home', 'Over 2.5')")
    odds: float = Field(..., gt=1.0, description="Decimal odds")
    bookmaker: BookmakerName = Field(..., description="Source bookmaker")
    url: str = Field(..., description="Direct URL to place bet")
    last_seen: datetime = Field(default_factory=datetime.now)
    
    @validator('odds')
    def validate_odds(cls, v):
        if v < 1.01 or v > 1000:
            raise ValueError('Odds must be between 1.01 and 1000')
        return round(v, 3)


class RawOddsData(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    
    event_name: str = Field(..., description="Raw event name from bookmaker")
    start_time: Optional[datetime] = None
    sport: Optional[str] = None
    league: Optional[str] = None
    market_name: str = Field(..., description="Raw market name")
    line: Optional[Union[str, float]] = None
    outcome_name: str = Field(..., description="Raw outcome name")
    odds: float = Field(..., gt=1.0)
    bookmaker: BookmakerName
    url: str = Field(..., description="Direct match/bet URL")
    scraped_at: datetime = Field(default_factory=datetime.now)
    is_live: bool = Field(default=False)
    
    @validator('odds')
    def validate_odds(cls, v):
        return round(v, 3)


class NormalizedEvent(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    
    canonical_name: str = Field(..., description="Normalized event name")
    start_time: Optional[datetime] = None
    sport: Optional[SportType] = None
    league: Optional[str] = None
    original_names: Dict[BookmakerName, str] = Field(default_factory=dict)
    is_live: bool = Field(default=False)


class NormalizedMarket(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    
    market_type: MarketType
    line: Optional[Union[str, float]] = None
    outcomes: Dict[str, OutcomeData] = Field(default_factory=dict)
    
    def add_outcome(self, outcome: OutcomeData) -> None:
        """Add or update outcome data."""
        existing = self.outcomes.get(outcome.name)
        if not existing or outcome.last_seen > existing.last_seen:
            self.outcomes[outcome.name] = outcome


class MatchedEvent(BaseModel):
    event: NormalizedEvent
    markets: Dict[str, NormalizedMarket] = Field(default_factory=dict)
    
    def get_market_key(self, market_type: MarketType, line: Optional[Union[str, float]] = None) -> str:
        """Generate unique key for market."""
        if line is not None:
            return f"{market_type.value}_{line}"
        return market_type.value
    
    def add_market_outcome(self, market_type: MarketType, line: Optional[Union[str, float]], 
                          outcome: OutcomeData) -> None:
        """Add outcome to appropriate market."""
        market_key = self.get_market_key(market_type, line)
        
        if market_key not in self.markets:
            self.markets[market_key] = NormalizedMarket(
                market_type=market_type,
                line=line
            )
        
        self.markets[market_key].add_outcome(outcome)


class StakeCalculation(BaseModel):
    outcome_name: str
    bookmaker: BookmakerName
    stake_amount: float = Field(..., ge=0)
    potential_profit: float
    url: str


class ArbitrageOpportunity(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    
    event_name: str
    start_time: Optional[datetime] = None
    sport: Optional[str] = None
    league: Optional[str] = None
    market_type: str
    line: Optional[Union[str, float]] = None
    
    # Best odds per outcome
    outcomes: List[OutcomeData] = Field(..., min_items=2)
    
    # Arbitrage calculations
    arb_percentage: float = Field(..., description="Arbitrage percentage (< 100 is profitable)")
    profit_percentage: float = Field(..., description="Profit percentage")
    guaranteed_profit: float = Field(..., description="Guaranteed profit amount")
    
    # Stake distribution
    bankroll: float = Field(default=1000.0)
    stakes: List[StakeCalculation] = Field(default_factory=list)
    
    # Metadata
    detected_at: datetime = Field(default_factory=datetime.now)
    freshness_score: float = Field(..., ge=0, le=1, description="Data freshness (1=fresh, 0=stale)")
    
    @validator('arb_percentage')
    def validate_arb_percentage(cls, v):
        return round(v, 4)
    
    @validator('profit_percentage')
    def validate_profit_percentage(cls, v):
        return round(v, 4)
    
    @validator('guaranteed_profit')
    def validate_profit(cls, v):
        return round(v, 2)


class ScrapingResult(BaseModel):
    bookmaker: BookmakerName
    success: bool = True
    odds_count: int = 0
    events_count: int = 0
    error_message: Optional[str] = None
    scrape_duration: float = 0.0
    scraped_at: datetime = Field(default_factory=datetime.now)


class ArbitrageResponse(BaseModel):
    """Main API response model."""
    arbitrages: List[ArbitrageOpportunity] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict)
    scraping_results: List[ScrapingResult] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.now)
    
    def add_summary_stats(self, total_events: int, total_odds: int, 
                         processing_time: float) -> None:
        """Add summary statistics."""
        self.summary.update({
            "total_arbitrages": len(self.arbitrages),
            "total_events_scraped": total_events,
            "total_odds_scraped": total_odds,
            "processing_time_seconds": round(processing_time, 2),
            "average_arb_percentage": round(
                sum(arb.arb_percentage for arb in self.arbitrages) / len(self.arbitrages)
                if self.arbitrages else 0, 2
            ),
            "total_potential_profit": round(
                sum(arb.guaranteed_profit for arb in self.arbitrages), 2
            ),
            "bookmakers_scraped": [r.bookmaker for r in self.scraping_results if r.success],
            "failed_bookmakers": [r.bookmaker for r in self.scraping_results if not r.success]
        })


# Filter models for API requests
class ArbitrageFilters(BaseModel):
    sport: Optional[SportType] = None
    market_type: Optional[MarketType] = None
    min_arb_percentage: Optional[float] = Field(None, ge=0)
    min_profit: Optional[float] = Field(None, ge=0)
    bookmakers: Optional[List[BookmakerName]] = None
    live_only: Optional[bool] = None
    max_start_hours: Optional[int] = Field(None, ge=0, le=168)  # Max 1 week
    bankroll: Optional[float] = Field(None, gt=0)
    
    class Config:
        use_enum_values = True