"""Arbitrage detection and calculation engine."""

import math
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from decimal import Decimal, ROUND_HALF_UP

from schema.models import (
    MatchedEvent, ArbitrageOpportunity, OutcomeData, 
    StakeCalculation, ArbitrageFilters
)
from config import settings
from utils.logging import get_logger

logger = get_logger(__name__)


class ArbitrageEngine:
    """Engine for detecting and calculating arbitrage opportunities."""
    
    def __init__(self):
        self.min_arb_percentage = settings.min_arb_percentage
        self.min_profit_amount = settings.min_profit_amount
        self.default_bankroll = settings.default_bankroll
        self.odds_tolerance = settings.odds_tolerance
    
    def detect_arbitrages(self, matched_events: List[MatchedEvent], 
                         filters: Optional[ArbitrageFilters] = None) -> List[ArbitrageOpportunity]:
        """Detect arbitrage opportunities from matched events."""
        logger.info(f"Detecting arbitrages from {len(matched_events)} matched events")
        
        arbitrages = []
        
        for event in matched_events:
            try:
                # Apply filters early to skip irrelevant events
                if not self._passes_event_filters(event, filters):
                    continue
                
                # Check each market in the event
                for market_key, market in event.markets.items():
                    market_arbs = self._detect_market_arbitrages(event, market_key, market, filters)
                    arbitrages.extend(market_arbs)
                
                # Check for cross-market arbitrages (e.g., combining different lines)
                cross_market_arbs = self._detect_cross_market_arbitrages(event, filters)
                arbitrages.extend(cross_market_arbs)
                
            except Exception as e:
                logger.error(f"Error processing event {event.event.canonical_name}: {e}")
                continue
        
        # Sort by profit percentage (descending)
        arbitrages.sort(key=lambda x: x.profit_percentage, reverse=True)
        
        logger.info(f"Detected {len(arbitrages)} arbitrage opportunities")
        return arbitrages
    
    def _passes_event_filters(self, event: MatchedEvent, filters: Optional[ArbitrageFilters]) -> bool:
        """Check if event passes basic filters."""
        if not filters:
            return True
        
        # Sport filter
        if filters.sport and event.event.sport != filters.sport:
            return False
        
        # Live/pre-match filter
        if filters.live_only is not None:
            if filters.live_only != event.event.is_live:
                return False
        
        # Time filter for future events
        if filters.max_start_hours and event.event.start_time:
            max_time = datetime.now() + timedelta(hours=filters.max_start_hours)
            if event.event.start_time > max_time:
                return False
        
        return True
    
    def _detect_market_arbitrages(self, event: MatchedEvent, market_key: str, 
                                 market, filters: Optional[ArbitrageFilters]) -> List[ArbitrageOpportunity]:
        """Detect arbitrages within a single market."""
        arbitrages = []
        
        try:
            # Apply market type filter
            if filters and filters.market_type and market.market_type != filters.market_type:
                return arbitrages
            
            # Get fresh outcomes (filter stale data)
            fresh_outcomes = self._get_fresh_outcomes(market.outcomes, event.event.is_live)
            
            if len(fresh_outcomes) < 2:
                return arbitrages
            
            # Get best odds per outcome from different bookmakers
            best_odds = self._get_best_odds_per_outcome(fresh_outcomes, filters)
            
            if len(best_odds) < 2:
                return arbitrages
            
            # Calculate arbitrage percentage
            arb_calc = self._calculate_arbitrage(best_odds)
            if not arb_calc:
                return arbitrages
            
            arb_percentage, profit_percentage = arb_calc
            
            # Apply arbitrage filters
            if not self._passes_arbitrage_filters(arb_percentage, profit_percentage, filters):
                return arbitrages
            
            # Calculate stakes and profit
            bankroll = filters.bankroll if filters and filters.bankroll else self.default_bankroll
            stakes = self._calculate_stakes(best_odds, bankroll)
            guaranteed_profit = bankroll * (profit_percentage / 100)
            
            # Apply minimum profit filter
            if filters and filters.min_profit and guaranteed_profit < filters.min_profit:
                return arbitrages
            
            # Create arbitrage opportunity
            arb = ArbitrageOpportunity(
                event_name=event.event.canonical_name,
                start_time=event.event.start_time,
                sport=event.event.sport.value if event.event.sport else None,
                league=event.event.league,
                market_type=market.market_type.value,
                line=market.line,
                outcomes=list(best_odds.values()),
                arb_percentage=arb_percentage,
                profit_percentage=profit_percentage,
                guaranteed_profit=guaranteed_profit,
                bankroll=bankroll,
                stakes=stakes,
                freshness_score=self._calculate_freshness_score(best_odds.values())
            )
            
            arbitrages.append(arb)
            
        except Exception as e:
            logger.debug(f"Error detecting arbitrage in market {market_key}: {e}")
        
        return arbitrages
    
    def _get_fresh_outcomes(self, outcomes: Dict[str, OutcomeData], is_live: bool) -> Dict[str, OutcomeData]:
        """Filter outcomes by data freshness."""
        fresh_outcomes = {}
        
        max_age_seconds = settings.live_odds_max_age if is_live else settings.prematch_odds_max_age
        cutoff_time = datetime.now() - timedelta(seconds=max_age_seconds)
        
        for outcome_name, outcome in outcomes.items():
            if outcome.last_seen >= cutoff_time:
                fresh_outcomes[outcome_name] = outcome
        
        return fresh_outcomes
    
    def _get_best_odds_per_outcome(self, outcomes: Dict[str, OutcomeData], 
                                  filters: Optional[ArbitrageFilters]) -> Dict[str, OutcomeData]:
        """Get best odds for each outcome, ensuring different bookmakers."""
        best_odds = {}
        used_bookmakers = set()
        
        # Group outcomes by name
        outcome_groups = {}
        for outcome_name, outcome in outcomes.items():
            if outcome_name not in outcome_groups:
                outcome_groups[outcome_name] = []
            outcome_groups[outcome_name].append(outcome)
        
        # For each outcome, find the best odds from an unused bookmaker
        for outcome_name, outcome_list in outcome_groups.items():
            # Apply bookmaker filter
            if filters and filters.bookmakers:
                outcome_list = [o for o in outcome_list if o.bookmaker in filters.bookmakers]
            
            # Sort by odds (descending) and filter by unused bookmakers
            available_outcomes = [o for o in outcome_list if o.bookmaker not in used_bookmakers]
            
            if available_outcomes:
                best_outcome = max(available_outcomes, key=lambda x: x.odds)
                best_odds[outcome_name] = best_outcome
                used_bookmakers.add(best_outcome.bookmaker)
        
        return best_odds
    
    def _calculate_arbitrage(self, best_odds: Dict[str, OutcomeData]) -> Optional[Tuple[float, float]]:
        """Calculate arbitrage percentage and profit percentage."""
        if len(best_odds) < 2:
            return None
        
        try:
            # Calculate implied probabilities
            implied_probabilities = []
            for outcome in best_odds.values():
                if outcome.odds <= 1.0:
                    return None
                implied_prob = 1.0 / outcome.odds
                implied_probabilities.append(implied_prob)
            
            # Calculate arbitrage percentage
            total_implied_prob = sum(implied_probabilities)
            arb_percentage = total_implied_prob * 100
            
            # Calculate profit percentage
            if total_implied_prob >= 1.0:
                return None  # No arbitrage opportunity
            
            profit_percentage = ((1.0 / total_implied_prob) - 1.0) * 100
            
            return round(arb_percentage, 4), round(profit_percentage, 4)
            
        except Exception as e:
            logger.debug(f"Error calculating arbitrage: {e}")
            return None
    
    def _passes_arbitrage_filters(self, arb_percentage: float, profit_percentage: float, 
                                 filters: Optional[ArbitrageFilters]) -> bool:
        """Check if arbitrage passes filter criteria."""
        if not filters:
            # Use default minimum thresholds
            return (arb_percentage < 100.0 and 
                   profit_percentage >= self.min_arb_percentage)
        
        # Check minimum arbitrage percentage
        if filters.min_arb_percentage is not None:
            if profit_percentage < filters.min_arb_percentage:
                return False
        else:
            if profit_percentage < self.min_arb_percentage:
                return False
        
        # Must be a profitable arbitrage
        return arb_percentage < 100.0
    
    def _calculate_stakes(self, best_odds: Dict[str, OutcomeData], bankroll: float) -> List[StakeCalculation]:
        """Calculate optimal stake distribution for arbitrage."""
        stakes = []
        
        try:
            # Calculate total inverse odds
            total_inverse = sum(1.0 / outcome.odds for outcome in best_odds.values())
            
            for outcome_name, outcome in best_odds.items():
                # Calculate proportional stake
                stake_proportion = (1.0 / outcome.odds) / total_inverse
                stake_amount = bankroll * stake_proportion
                
                # Calculate potential profit for this outcome
                potential_return = stake_amount * outcome.odds
                potential_profit = potential_return - bankroll
                
                stake_calc = StakeCalculation(
                    outcome_name=outcome_name,
                    bookmaker=outcome.bookmaker,
                    stake_amount=round(stake_amount, 2),
                    potential_profit=round(potential_profit, 2),
                    url=outcome.url
                )
                
                stakes.append(stake_calc)
        
        except Exception as e:
            logger.error(f"Error calculating stakes: {e}")
        
        return stakes
    
    def _calculate_freshness_score(self, outcomes) -> float:
        """Calculate freshness score based on data age."""
        if not outcomes:
            return 0.0
        
        now = datetime.now()
        total_age = 0
        count = 0
        
        for outcome in outcomes:
            age_seconds = (now - outcome.last_seen).total_seconds()
            total_age += age_seconds
            count += 1
        
        avg_age_seconds = total_age / count
        
        # Convert to freshness score (1.0 = fresh, 0.0 = very stale)
        # Assume 300 seconds (5 minutes) is the maximum acceptable age
        max_acceptable_age = 300
        freshness = max(0.0, 1.0 - (avg_age_seconds / max_acceptable_age))
        
        return round(freshness, 3)
    
    def _detect_cross_market_arbitrages(self, event: MatchedEvent, 
                                       filters: Optional[ArbitrageFilters]) -> List[ArbitrageOpportunity]:
        """Detect arbitrages across different markets (advanced feature)."""
        # This is a complex feature that looks for arbitrages by combining
        # outcomes from different but related markets (e.g., different handicap lines)
        
        arbitrages = []
        
        try:
            # Group markets by type
            markets_by_type = {}
            for market_key, market in event.markets.items():
                market_type = market.market_type.value
                if market_type not in markets_by_type:
                    markets_by_type[market_type] = []
                markets_by_type[market_type].append((market_key, market))
            
            # Look for arbitrages in handicap markets with different lines
            if 'handicap' in markets_by_type:
                handicap_arbs = self._detect_handicap_line_arbitrages(
                    markets_by_type['handicap'], event, filters
                )
                arbitrages.extend(handicap_arbs)
            
            # Look for arbitrages in total markets with different lines
            if 'totals' in markets_by_type:
                totals_arbs = self._detect_totals_line_arbitrages(
                    markets_by_type['totals'], event, filters
                )
                arbitrages.extend(totals_arbs)
        
        except Exception as e:
            logger.debug(f"Error detecting cross-market arbitrages: {e}")
        
        return arbitrages
    
    def _detect_handicap_line_arbitrages(self, handicap_markets: List[Tuple], 
                                        event: MatchedEvent, 
                                        filters: Optional[ArbitrageFilters]) -> List[ArbitrageOpportunity]:
        """Detect arbitrages between different handicap lines."""
        arbitrages = []
        
        # For now, this is a placeholder for advanced handicap arbitrage detection
        # This would involve complex calculations considering different handicap lines
        # and finding middle opportunities
        
        return arbitrages
    
    def _detect_totals_line_arbitrages(self, totals_markets: List[Tuple], 
                                      event: MatchedEvent, 
                                      filters: Optional[ArbitrageFilters]) -> List[ArbitrageOpportunity]:
        """Detect arbitrages between different totals lines (middles)."""
        arbitrages = []
        
        try:
            # Look for middle opportunities between different total lines
            # Example: Over 2.5 at one book, Under 3.5 at another
            # If final score is exactly 3, both bets win
            
            if len(totals_markets) < 2:
                return arbitrages
            
            for i, (key1, market1) in enumerate(totals_markets):
                for j, (key2, market2) in enumerate(totals_markets[i+1:], i+1):
                    
                    line1 = market1.line
                    line2 = market2.line
                    
                    if line1 is None or line2 is None:
                        continue
                    
                    # Check if lines are suitable for middle
                    if isinstance(line1, (int, float)) and isinstance(line2, (int, float)):
                        if abs(line1 - line2) == 1.0:  # Lines differ by exactly 1
                            middle_arb = self._calculate_middle_opportunity(
                                market1, market2, line1, line2, event, filters
                            )
                            if middle_arb:
                                arbitrages.append(middle_arb)
        
        except Exception as e:
            logger.debug(f"Error detecting totals line arbitrages: {e}")
        
        return arbitrages
    
    def _calculate_middle_opportunity(self, market1, market2, line1: float, line2: float,
                                     event: MatchedEvent, 
                                     filters: Optional[ArbitrageFilters]) -> Optional[ArbitrageOpportunity]:
        """Calculate middle opportunity between two totals markets."""
        try:
            # This is a simplified middle calculation
            # In practice, this would involve more complex probability calculations
            
            # Get best odds for relevant outcomes
            outcomes = {}
            
            # Find Over for lower line and Under for higher line
            lower_line = min(line1, line2)
            higher_line = max(line1, line2)
            
            lower_market = market1 if line1 == lower_line else market2
            higher_market = market2 if line2 == higher_line else market1
            
            # Get Over odds for lower line
            for outcome_name, outcome in lower_market.outcomes.items():
                if 'over' in outcome_name.lower():
                    outcomes[f"Over {lower_line}"] = outcome
                    break
            
            # Get Under odds for higher line
            for outcome_name, outcome in higher_market.outcomes.items():
                if 'under' in outcome_name.lower():
                    outcomes[f"Under {higher_line}"] = outcome
                    break
            
            if len(outcomes) < 2:
                return None
            
            # Calculate if this creates an arbitrage or middle opportunity
            arb_calc = self._calculate_arbitrage(outcomes)
            if not arb_calc:
                return None
            
            arb_percentage, profit_percentage = arb_calc
            
            if not self._passes_arbitrage_filters(arb_percentage, profit_percentage, filters):
                return None
            
            # Create arbitrage opportunity
            bankroll = filters.bankroll if filters and filters.bankroll else self.default_bankroll
            stakes = self._calculate_stakes(outcomes, bankroll)
            guaranteed_profit = bankroll * (profit_percentage / 100)
            
            return ArbitrageOpportunity(
                event_name=event.event.canonical_name,
                start_time=event.event.start_time,
                sport=event.event.sport.value if event.event.sport else None,
                league=event.event.league,
                market_type=f"Middle {lower_line}-{higher_line}",
                line=f"{lower_line}/{higher_line}",
                outcomes=list(outcomes.values()),
                arb_percentage=arb_percentage,
                profit_percentage=profit_percentage,
                guaranteed_profit=guaranteed_profit,
                bankroll=bankroll,
                stakes=stakes,
                freshness_score=self._calculate_freshness_score(outcomes.values())
            )
        
        except Exception as e:
            logger.debug(f"Error calculating middle opportunity: {e}")
            return None