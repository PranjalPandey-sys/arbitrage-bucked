"""Event matching engine for arbitrage detection."""

import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Set
from rapidfuzz import fuzz, process
from collections import defaultdict

from schema.models import (
    RawOddsData, NormalizedEvent, NormalizedMarket, MatchedEvent, 
    OutcomeData, SportType, MarketType, BookmakerName
)
from config import settings
from utils.logging import get_logger

logger = get_logger(__name__)


class EventMatcher:
    """Matches events across different bookmakers for arbitrage detection."""
    
    def __init__(self):
        self.normalization_map = self._load_normalization_map()
        self.fuzzy_threshold = settings.fuzzy_threshold
        self.time_tolerance = timedelta(minutes=settings.time_tolerance_minutes)
        
    def _load_normalization_map(self) -> Dict:
        """Load normalization mappings."""
        try:
            with open("normalization_map.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load normalization map: {e}")
            return {}
    
    def match_events(self, all_odds: List[RawOddsData]) -> List[MatchedEvent]:
        """Match events across bookmakers and return merged events."""
        logger.info(f"Starting event matching for {len(all_odds)} odds entries")
        
        # Normalize individual odds data
        normalized_odds = self._normalize_odds_data(all_odds)
        logger.info(f"Normalized {len(normalized_odds)} odds entries")
        
        # Group by sport and league for better matching
        grouped_odds = self._group_odds_by_sport_league(normalized_odds)
        
        # Match events within each group
        matched_events = []
        for group_key, odds_group in grouped_odds.items():
            group_matches = self._match_events_in_group(odds_group)
            matched_events.extend(group_matches)
            logger.debug(f"Group {group_key}: {len(group_matches)} matched events")
        
        # Filter out events with insufficient bookmaker coverage
        filtered_events = self._filter_by_bookmaker_coverage(matched_events)
        
        logger.info(f"Event matching completed: {len(filtered_events)} matched events")
        return filtered_events
    
    def _normalize_odds_data(self, all_odds: List[RawOddsData]) -> List[RawOddsData]:
        """Apply normalization to raw odds data."""
        normalized_odds = []
        
        for odds_data in all_odds:
            try:
                # Normalize team names in event name
                normalized_event_name = self._normalize_event_name(odds_data.event_name)
                
                # Normalize market name
                normalized_market = self._normalize_market_name(odds_data.market_name)
                
                # Normalize league name
                normalized_league = None
                if odds_data.league:
                    normalized_league = self._normalize_league_name(odds_data.league)
                
                # Create normalized copy
                normalized_odds.append(RawOddsData(
                    event_name=normalized_event_name,
                    start_time=odds_data.start_time,
                    sport=odds_data.sport,
                    league=normalized_league,
                    market_name=normalized_market,
                    line=odds_data.line,
                    outcome_name=odds_data.outcome_name,
                    odds=odds_data.odds,
                    bookmaker=odds_data.bookmaker,
                    url=odds_data.url,
                    scraped_at=odds_data.scraped_at,
                    is_live=odds_data.is_live
                ))
                
            except Exception as e:
                logger.debug(f"Error normalizing odds data: {e}")
                # Keep original if normalization fails
                normalized_odds.append(odds_data)
        
        return normalized_odds
    
    def _normalize_event_name(self, event_name: str) -> str:
        """Normalize event name by standardizing team names."""
        if not event_name:
            return event_name
        
        # Split team names (handle various separators)
        separators = [' vs ', ' v ', ' - ', ' – ', ' — ', ' x ']
        teams = None
        
        for sep in separators:
            if sep in event_name:
                teams = [team.strip() for team in event_name.split(sep, 1)]
                break
        
        if not teams or len(teams) != 2:
            return event_name.strip()
        
        # Normalize individual team names
        normalized_teams = []
        for team in teams:
            normalized_team = self._normalize_team_name(team)
            normalized_teams.append(normalized_team)
        
        return f"{normalized_teams[0]} vs {normalized_teams[1]}"
    
    def _normalize_team_name(self, team_name: str) -> str:
        """Normalize individual team name."""
        team = team_name.strip()
        
        # Check regular teams mapping
        if team in self.normalization_map.get("teams", {}):
            return self.normalization_map["teams"][team]
        
        # Check esports teams mapping
        if team in self.normalization_map.get("esports_teams", {}):
            return self.normalization_map["esports_teams"][team]
        
        # Apply basic cleaning
        import re
        
        # Remove common prefixes/suffixes
        team = re.sub(r'^(FC|AC|AS|SC|CF|United|City)\s+', '', team, flags=re.IGNORECASE)
        team = re.sub(r'\s+(FC|AC|AS|SC|CF|United|City)$', '', team, flags=re.IGNORECASE)
        
        # Remove special characters and extra spaces
        team = re.sub(r'[^\w\s]', ' ', team)
        team = re.sub(r'\s+', ' ', team).strip()
        
        return team
    
    def _normalize_market_name(self, market_name: str) -> str:
        """Normalize market name."""
        if not market_name:
            return market_name
        
        # Check regular markets
        normalized = self.normalization_map.get("markets", {}).get(market_name, market_name)
        
        # Check esports markets if not found
        if normalized == market_name:
            normalized = self.normalization_map.get("esports_markets", {}).get(market_name, market_name)
        
        return normalized.strip()
    
    def _normalize_league_name(self, league_name: str) -> str:
        """Normalize league name."""
        if not league_name:
            return league_name
        
        return self.normalization_map.get("leagues", {}).get(league_name, league_name).strip()
    
    def _group_odds_by_sport_league(self, odds: List[RawOddsData]) -> Dict[str, List[RawOddsData]]:
        """Group odds by sport and league for more efficient matching."""
        groups = defaultdict(list)
        
        for odds_data in odds:
            sport = odds_data.sport or "unknown"
            league = odds_data.league or "unknown"
            group_key = f"{sport}_{league}"
            groups[group_key].append(odds_data)
        
        return groups
    
    def _match_events_in_group(self, odds_group: List[RawOddsData]) -> List[MatchedEvent]:
        """Match events within a sport/league group."""
        # Group odds by event name for initial clustering
        event_clusters = defaultdict(list)
        
        for odds_data in odds_group:
            event_clusters[odds_data.event_name].append(odds_data)
        
        # Find similar event names across clusters
        event_names = list(event_clusters.keys())
        matched_groups = self._find_similar_event_groups(event_names, event_clusters)
        
        # Create MatchedEvent objects
        matched_events = []
        for event_group in matched_groups:
            matched_event = self._merge_event_group(event_group)
            if matched_event:
                matched_events.append(matched_event)
        
        return matched_events
    
    def _find_similar_event_groups(self, event_names: List[str], 
                                  event_clusters: Dict[str, List[RawOddsData]]) -> List[List[RawOddsData]]:
        """Find groups of similar event names and merge their odds."""
        processed_names = set()
        matched_groups = []
        
        for event_name in event_names:
            if event_name in processed_names:
                continue
            
            # Find all similar event names
            similar_names = self._find_similar_names(event_name, event_names)
            
            # Combine odds from all similar events
            combined_odds = []
            for similar_name in similar_names:
                if similar_name not in processed_names:
                    # Additional time-based validation
                    if self._validate_time_compatibility(event_clusters[event_name], event_clusters[similar_name]):
                        combined_odds.extend(event_clusters[similar_name])
                        processed_names.add(similar_name)
            
            if combined_odds:
                matched_groups.append(combined_odds)
        
        return matched_groups
    
    def _find_similar_names(self, target_name: str, all_names: List[str]) -> List[str]:
        """Find event names similar to target using fuzzy matching."""
        similar_names = [target_name]  # Include the target itself
        
        for name in all_names:
            if name == target_name:
                continue
            
            # Calculate similarity score
            similarity = fuzz.ratio(target_name.lower(), name.lower())
            
            if similarity >= self.fuzzy_threshold:
                similar_names.append(name)
        
        return similar_names
    
    def _validate_time_compatibility(self, odds_group1: List[RawOddsData], 
                                   odds_group2: List[RawOddsData]) -> bool:
        """Validate that events have compatible start times."""
        # Get start times from both groups
        times1 = [odds.start_time for odds in odds_group1 if odds.start_time]
        times2 = [odds.start_time for odds in odds_group2 if odds.start_time]
        
        if not times1 or not times2:
            # If no times available, assume compatible
            return True
        
        # Check if any times in group1 are close to any times in group2
        for time1 in times1:
            for time2 in times2:
                if abs(time1 - time2) <= self.time_tolerance:
                    return True
        
        return False
    
    def _merge_event_group(self, odds_group: List[RawOddsData]) -> Optional[MatchedEvent]:
        """Merge a group of odds into a single MatchedEvent."""
        if not odds_group:
            return None
        
        try:
            # Create canonical event info
            canonical_name = self._get_canonical_event_name(odds_group)
            start_time = self._get_representative_start_time(odds_group)
            sport = self._get_representative_sport(odds_group)
            league = self._get_representative_league(odds_group)
            is_live = any(odds.is_live for odds in odds_group)
            
            # Track original names per bookmaker
            original_names = {}
            for odds in odds_group:
                original_names[odds.bookmaker] = odds.event_name
            
            # Create normalized event
            event = NormalizedEvent(
                canonical_name=canonical_name,
                start_time=start_time,
                sport=sport,
                league=league,
                original_names=original_names,
                is_live=is_live
            )
            
            # Create matched event and add all odds
            matched_event = MatchedEvent(event=event)
            
            for odds_data in odds_group:
                # Create outcome data
                outcome = OutcomeData(
                    name=odds_data.outcome_name,
                    odds=odds_data.odds,
                    bookmaker=odds_data.bookmaker,
                    url=odds_data.url,
                    last_seen=odds_data.scraped_at
                )
                
                # Determine market type
                market_type = self._determine_market_type(odds_data.market_name)
                
                # Add to matched event
                matched_event.add_market_outcome(market_type, odds_data.line, outcome)
            
            return matched_event
            
        except Exception as e:
            logger.error(f"Error merging event group: {e}")
            return None
    
    def _get_canonical_event_name(self, odds_group: List[RawOddsData]) -> str:
        """Get the most representative event name from the group."""
        event_names = [odds.event_name for odds in odds_group]
        
        # Count frequency of each name
        name_counts = {}
        for name in event_names:
            name_counts[name] = name_counts.get(name, 0) + 1
        
        # Return most common name, or first if tie
        return max(name_counts.keys(), key=lambda x: name_counts[x])
    
    def _get_representative_start_time(self, odds_group: List[RawOddsData]) -> Optional[datetime]:
        """Get representative start time from the group."""
        times = [odds.start_time for odds in odds_group if odds.start_time]
        if not times:
            return None
        
        # Return the median time to avoid outliers
        sorted_times = sorted(times)
        mid_index = len(sorted_times) // 2
        return sorted_times[mid_index]
    
    def _get_representative_sport(self, odds_group: List[RawOddsData]) -> Optional[SportType]:
        """Get representative sport from the group."""
        sports = [odds.sport for odds in odds_group if odds.sport]
        if not sports:
            return None
        
        # Count frequency and return most common
        sport_counts = {}
        for sport in sports:
            sport_counts[sport] = sport_counts.get(sport, 0) + 1
        
        most_common_sport = max(sport_counts.keys(), key=lambda x: sport_counts[x])
        
        # Convert to SportType enum
        try:
            return SportType(most_common_sport.lower())
        except ValueError:
            return None
    
    def _get_representative_league(self, odds_group: List[RawOddsData]) -> Optional[str]:
        """Get representative league from the group."""
        leagues = [odds.league for odds in odds_group if odds.league]
        if not leagues:
            return None
        
        # Count frequency and return most common
        league_counts = {}
        for league in leagues:
            league_counts[league] = league_counts.get(league, 0) + 1
        
        return max(league_counts.keys(), key=lambda x: league_counts[x])
    
    def _determine_market_type(self, market_name: str) -> MarketType:
        """Determine MarketType enum from market name."""
        if not market_name:
            return MarketType.MONEYLINE
        
        market_lower = market_name.lower()
        
        # Map market names to types
        market_mapping = {
            'moneyline': MarketType.MONEYLINE,
            'winner': MarketType.MONEYLINE,
            'match winner': MarketType.MONEYLINE,
            '1x2': MarketType.ONE_X_TWO,
            'match result': MarketType.ONE_X_TWO,
            'full time result': MarketType.ONE_X_TWO,
            'double chance': MarketType.DOUBLE_CHANCE,
            'totals': MarketType.TOTALS,
            'total': MarketType.TOTALS,
            'over/under': MarketType.TOTALS,
            'o/u': MarketType.TOTALS,
            'handicap': MarketType.HANDICAP,
            'spread': MarketType.HANDICAP,
            'asian handicap': MarketType.HANDICAP,
            'european handicap': MarketType.HANDICAP,
            'team totals': MarketType.TEAM_TOTALS,
            'team total': MarketType.TEAM_TOTALS,
            'player props': MarketType.PLAYER_PROPS,
            'map winner': MarketType.MAP_WINNER,
            'total maps': MarketType.TOTAL_MAPS,
            'round handicap': MarketType.ROUND_HANDICAP,
            'first blood': MarketType.FIRST_BLOOD,
            'kills over/under': MarketType.KILLS_OVER_UNDER,
            'total kills': MarketType.KILLS_OVER_UNDER
        }
        
        # Check exact matches first
        for key, market_type in market_mapping.items():
            if key in market_lower:
                return market_type
        
        # Default fallback
        return MarketType.MONEYLINE
    
    def _filter_by_bookmaker_coverage(self, matched_events: List[MatchedEvent]) -> List[MatchedEvent]:
        """Filter events to ensure sufficient bookmaker coverage for arbitrage."""
        filtered_events = []
        
        for event in matched_events:
            # Check if event has odds from at least 2 different bookmakers
            bookmakers_with_odds = set()
            
            for market in event.markets.values():
                for outcome in market.outcomes.values():
                    bookmakers_with_odds.add(outcome.bookmaker)
            
            # Require at least 2 bookmakers for arbitrage potential
            if len(bookmakers_with_odds) >= 2:
                filtered_events.append(event)
            else:
                logger.debug(f"Filtered out event {event.event.canonical_name} - insufficient bookmaker coverage")
        
        return filtered_events
    
    def get_matching_stats(self, all_odds: List[RawOddsData], matched_events: List[MatchedEvent]) -> Dict:
        """Get statistics about the matching process."""
        # Count unique events per bookmaker
        events_per_bookmaker = defaultdict(set)
        for odds in all_odds:
            events_per_bookmaker[odds.bookmaker].add(odds.event_name)
        
        # Count markets per event
        total_markets = sum(len(event.markets) for event in matched_events)
        
        # Count outcomes per market
        total_outcomes = 0
        bookmaker_coverage = defaultdict(int)
        
        for event in matched_events:
            for market in event.markets.values():
                total_outcomes += len(market.outcomes)
                market_bookmakers = set()
                for outcome in market.outcomes.values():
                    market_bookmakers.add(outcome.bookmaker)
                bookmaker_coverage[len(market_bookmakers)] += 1
        
        return {
            "total_raw_odds": len(all_odds),
            "unique_events_per_bookmaker": {str(bm): len(events) for bm, events in events_per_bookmaker.items()},
            "matched_events": len(matched_events),
            "total_markets": total_markets,
            "total_outcomes": total_outcomes,
            "average_markets_per_event": round(total_markets / len(matched_events) if matched_events else 0, 2),
            "bookmaker_coverage_distribution": dict(bookmaker_coverage),
            "matching_efficiency": round((len(matched_events) * 100) / len(set(odds.event_name for odds in all_odds)) if all_odds else 0, 2)
        }