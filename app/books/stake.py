"""Stake scraper implementation."""

import asyncio
import random
from datetime import datetime
from typing import List, Dict, Optional
from urllib.parse import urljoin

from books.base import BaseScraper
from schema.models import RawOddsData, BookmakerName
from utils.logging import get_logger

logger = get_logger(__name__)


class StakeScraper(BaseScraper):
    """Scraper for Stake sportsbook."""
    
    def __init__(self):
        super().__init__(BookmakerName.STAKE)
    
    def get_base_url(self) -> str:
        return "https://stake.com"
    
    async def scrape_all_odds(self) -> List[RawOddsData]:
        """
        Scrape all available odds from this bookmaker and return them
        in the normalized format expected by the orchestrator.
        """
        all_odds = []
        
        try:
            # Initialize browser if needed
            if not self.page:
                logger.info("Stake: Browser not initialized, skipping scraping")
                return all_odds
            
            # Scrape sports odds
            logger.info("Stake: Starting sports odds scraping")
            sports_odds = await self.scrape_sports_odds()
            all_odds.extend(sports_odds)
            logger.info(f"Stake: Scraped {len(sports_odds)} sports odds")
            
            # Scrape esports odds
            logger.info("Stake: Starting esports odds scraping")
            esports_odds = await self.scrape_esports_odds()
            all_odds.extend(esports_odds)
            logger.info(f"Stake: Scraped {len(esports_odds)} esports odds")
            
            logger.info(f"Stake: Total odds scraped: {len(all_odds)}")
            
        except Exception as e:
            logger.error(f"Stake: Error in scrape_all_odds: {e}")
        
        return all_odds
    
    async def scrape_sports_odds(self) -> List[RawOddsData]:
        """Scrape sports odds from Stake."""
        all_odds = []
        
        # Sports sections to scrape
        sports_urls = {
            'football': '/sports/soccer',
            'basketball': '/sports/basketball',
            'tennis': '/sports/tennis',
            'cricket': '/sports/cricket',
            'baseball': '/sports/baseball',
            'hockey': '/sports/ice-hockey'
        }
        
        for sport, url_path in sports_urls.items():
            try:
                odds = await self._scrape_sport_section(sport, url_path)
                all_odds.extend(odds)
                await asyncio.sleep(random.uniform(2, 4))
            except Exception as e:
                logger.error(f"Stake: Failed to scrape {sport}: {e}")
        
        return all_odds
    
    async def scrape_esports_odds(self) -> List[RawOddsData]:
        """Scrape esports odds from Stake."""
        all_odds = []
        
        esports_urls = {
            'csgo': '/sports/esports/counter-strike',
            'dota2': '/sports/esports/dota-2',
            'lol': '/sports/esports/league-of-legends',
            'valorant': '/sports/esports/valorant'
        }
        
        for esport, url_path in esports_urls.items():
            try:
                odds = await self._scrape_sport_section(esport, url_path)
                all_odds.extend(odds)
                await asyncio.sleep(random.uniform(2, 4))
            except Exception as e:
                logger.error(f"Stake: Failed to scrape {esport}: {e}")
        
        return all_odds
    
    async def _scrape_sport_section(self, sport: str, url_path: str) -> List[RawOddsData]:
        """Scrape a specific sport section."""
        odds = []
        url = urljoin(self.base_url, url_path)
        
        if not await self.navigate_with_retry(url):
            return odds
        
        await self.handle_cookie_banner()
        await asyncio.sleep(random.uniform(3, 5))
        
        try:
            # Wait for content to load
            await self.page.wait_for_selector('[data-testid="event"], .event-row, .match-row', timeout=15000)
            
            # Try scrolling to load more events
            for _ in range(3):
                await self.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await asyncio.sleep(2)
            
            # Find all event containers
            event_selectors = [
                '[data-testid="event"]',
                '[data-testid="match"]',
                '.event-row',
                '.match-row',
                '.sport-event',
                '[class*="event-item"]'
            ]
            
            events = []
            for selector in event_selectors:
                try:
                    found_events = await self.page.query_selector_all(selector)
                    if found_events:
                        events = found_events
                        logger.info(f"Stake: Found {len(events)} events with selector {selector}")
                        break
                except Exception:
                    continue
            
            if not events:
                # Fallback to structure analysis
                events = await self._find_events_by_structure()
            
            for event in events:
                try:
                    event_odds = await self._extract_event_odds(event, sport)
                    odds.extend(event_odds)
                except Exception as e:
                    logger.debug(f"Stake: Failed to extract odds from event: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"Stake: Error scraping {sport} section: {e}")
        
        logger.info(f"Stake: Extracted {len(odds)} odds from {sport}")
        return odds
    
    async def _find_events_by_structure(self) -> List:
        """Find events by analyzing Stake's page structure."""
        try:
            # Stake-specific selectors
            potential_selectors = [
                'div[data-cy*="event"]',
                'div[data-cy*="match"]',
                'div[role="button"][class*="event"]',
                'div[role="button"][class*="match"]',
                '[class*="EventRow"]',
                '[class*="MatchRow"]'
            ]
            
            for selector in potential_selectors:
                elements = await self.page.query_selector_all(selector)
                if elements:
                    # Filter for elements with odds-like content
                    valid_events = []
                    for element in elements:
                        try:
                            text_content = await element.text_content()
                            # Check for team names and odds patterns
                            if text_content and ('vs' in text_content.lower() or 'v ' in text_content):
                                # Look for decimal odds pattern
                                import re
                                if re.search(r'\d\.\d{2}', text_content):
                                    valid_events.append(element)
                        except Exception:
                            continue
                    
                    if valid_events:
                        logger.info(f"Stake: Found {len(valid_events)} events via structure analysis")
                        return valid_events
            
            return []
            
        except Exception as e:
            logger.error(f"Stake: Error in structure analysis: {e}")
            return []
    
    async def _extract_event_odds(self, event_element, sport: str) -> List[RawOddsData]:
        """Extract odds data from a single event element."""
        odds = []
        
        try:
            # Extract event name
            event_name = await self._extract_event_name(event_element)
            if not event_name:
                return odds
            
            # Extract event time
            event_time = await self._extract_event_time(event_element)
            
            # Check if live
            is_live = await self._is_live_event(event_element)
            
            # Extract event URL
            event_url = await self._extract_event_url(event_element)
            
            # Extract league info
            league = await self._extract_league(event_element)
            
            # Extract odds from different markets
            markets_odds = await self._extract_market_odds(event_element)
            
            for market_name, market_odds in markets_odds.items():
                normalized_market, line = self.extract_line_from_market(market_name)
                
                for outcome_name, odds_value in market_odds.items():
                    if odds_value and odds_value >= 1.01:
                        odds_data = RawOddsData(
                            event_name=event_name,
                            start_time=event_time,
                            sport=sport,
                            league=league,
                            market_name=normalized_market,
                            line=line,
                            outcome_name=outcome_name,
                            odds=odds_value,
                            bookmaker=self.bookmaker,
                            url=event_url or self.page.url,
                            is_live=is_live
                        )
                        
                        if self.validate_odds_data(odds_data):
                            odds.append(odds_data)
        
        except Exception as e:
            logger.debug(f"Stake: Error extracting event odds: {e}")
        
        return odds
    
    async def _extract_event_name(self, event_element) -> Optional[str]:
        """Extract event name from event element."""
        try:
            # Stake-specific selectors for team names
            name_selectors = [
                '[data-testid="team-name"]',
                '[data-cy*="team"]',
                '.team-name',
                '[class*="TeamName"]',
                '[class*="team-name"]'
            ]
            
            teams = []
            for selector in name_selectors:
                team_elements = await event_element.query_selector_all(selector)
                for team_elem in team_elements:
                    team_name = await team_elem.text_content()
                    if team_name and team_name.strip():
                        teams.append(team_name.strip())
            
            if len(teams) >= 2:
                return f"{teams[0]} vs {teams[1]}"
            
            # Fallback: look for event title or match name
            title_selectors = [
                '[data-testid="event-title"]',
                '[data-testid="match-title"]',
                '.event-title',
                '.match-title',
                'h3', 'h4'
            ]
            
            for selector in title_selectors:
                title_element = await event_element.query_selector(selector)
                if title_element:
                    title = await title_element.text_content()
                    if title and title.strip():
                        return title.strip()
            
            # Last resort: extract from full text
            full_text = await event_element.text_content()
            if full_text:
                import re
                # Look for team vs team pattern
                vs_pattern = r'(.+?)\s+(?:vs?\.?|v\.?|[-–—])\s+(.+?)(?:\s|$)'
                match = re.search(vs_pattern, full_text, re.IGNORECASE)
                if match:
                    team1, team2 = match.groups()
                    # Clean team names
                    team1 = re.sub(r'^\d+\.?\s*', '', team1).strip()
                    team2 = re.sub(r'^\d+\.?\s*', '', team2).strip()
                    if team1 and team2 and len(team1) > 2 and len(team2) > 2:
                        return f"{team1} vs {team2}"
            
            return None
            
        except Exception as e:
            logger.debug(f"Stake: Error extracting event name: {e}")
            return None
    
    async def _extract_event_time(self, event_element) -> Optional[datetime]:
        """Extract event start time."""
        try:
            time_selectors = [
                '[data-testid="event-time"]',
                '[data-testid="start-time"]',
                '[data-cy*="time"]',
                '.event-time',
                '.start-time',
                '[class*="Time"]'
            ]
            
            for selector in time_selectors:
                time_element = await event_element.query_selector(selector)
                if time_element:
                    time_text = await time_element.text_content()
                    if time_text:
                        parsed_time = self.parse_event_time(time_text.strip())
                        if parsed_time:
                            return parsed_time
            
            # Check for datetime attributes
            for attr in ['data-time', 'data-start-time', 'datetime']:
                time_value = await event_element.get_attribute(attr)
                if time_value:
                    parsed_time = self.parse_event_time(time_value)
                    if parsed_time:
                        return parsed_time
            
            return None
            
        except Exception as e:
            logger.debug(f"Stake: Error extracting event time: {e}")
            return None
    
    async def _is_live_event(self, event_element) -> bool:
        """Check if event is live."""
        try:
            live_indicators = [
                '[data-testid="live-indicator"]',
                '[data-cy*="live"]',
                '.live-indicator',
                '.is-live',
                '[class*="Live"]'
            ]
            
            for selector in live_indicators:
                live_element = await event_element.query_selector(selector)
                if live_element:
                    return True
            
            # Check text content
            text_content = await event_element.text_content()
            if text_content:
                live_keywords = ['live', 'in-play', '●', 'playing now']
                return any(keyword in text_content.lower() for keyword in live_keywords)
            
            return False
            
        except Exception:
            return False
    
    async def _extract_event_url(self, event_element) -> Optional[str]:
        """Extract clickable URL for the event."""
        try:
            # Check if element itself is clickable
            href = await event_element.get_attribute('href')
            if href:
                return urljoin(self.base_url, href)
            
            # Look for child links
            link_element = await event_element.query_selector('a[href]')
            if link_element:
                href = await link_element.get_attribute('href')
                if href:
                    return urljoin(self.base_url, href)
            
            # Check for data attributes that might contain URLs
            for attr in ['data-href', 'data-url', 'data-link']:
                url_value = await event_element.get_attribute(attr)
                if url_value:
                    return urljoin(self.base_url, url_value)
            
            return self.page.url
            
        except Exception:
            return self.page.url
    
    async def _extract_league(self, event_element) -> Optional[str]:
        """Extract league information."""
        try:
            league_selectors = [
                '[data-testid="league"]',
                '[data-testid="competition"]',
                '[data-cy*="league"]',
                '.league-name',
                '.competition-name',
                '[class*="League"]'
            ]
            
            for selector in league_selectors:
                league_element = await event_element.query_selector(selector)
                if league_element:
                    league_text = await league_element.text_content()
                    if league_text and league_text.strip():
                        return self.normalize_league_name(league_text.strip())
            
            return None
            
        except Exception:
            return None
    
    async def _extract_market_odds(self, event_element) -> Dict[str, Dict[str, float]]:
        """Extract odds for different markets."""
        markets = {}
        
        try:
            # Look for odds buttons/elements
            odds_selectors = [
                '[data-testid*="odds"]',
                '[data-cy*="odds"]',
                'button[class*="odds"]',
                '.odds-button',
                '[class*="OddsButton"]',
                '[role="button"][class*="bet"]'
            ]
            
            odds_elements = []
            for selector in odds_selectors:
                elements = await event_element.query_selector_all(selector)
                odds_elements.extend(elements)
            
            # Extract odds and determine markets
            for odds_element in odds_elements:
                try:
                    odds_value = await self._extract_odds_value(odds_element)
                    if not odds_value:
                        continue
                    
                    # Determine market and outcome
                    market_info = await self._determine_market_and_outcome(odds_element)
                    if market_info:
                        market_name, outcome_name = market_info
                        
                        if market_name not in markets:
                            markets[market_name] = {}
                        
                        markets[market_name][outcome_name] = odds_value
                
                except Exception as e:
                    logger.debug(f"Stake: Error processing odds element: {e}")
            
            # If no markets found, try basic extraction
            if not markets:
                markets = await self._extract_basic_odds(event_element)
        
        except Exception as e:
            logger.debug(f"Stake: Error extracting market odds: {e}")
        
        return markets
    
    async def _extract_odds_value(self, odds_element) -> Optional[float]:
        """Extract numerical odds value."""
        try:
            # Check data attributes first
            for attr in ['data-odds', 'data-price', 'data-value']:
                odds_attr = await odds_element.get_attribute(attr)
                if odds_attr:
                    return self.parse_decimal_odds(odds_attr)
            
            # Get text content
            text = await odds_element.text_content()
            if text:
                # Clean text and extract odds
                cleaned_text = text.strip()
                return self.parse_decimal_odds(cleaned_text)
            
            return None
            
        except Exception:
            return None
    
    async def _determine_market_and_outcome(self, odds_element) -> Optional[tuple]:
        """Determine market type and outcome name."""
        try:
            # Check for market context in attributes
            market_attr = await odds_element.get_attribute('data-market')
            outcome_attr = await odds_element.get_attribute('data-outcome')
            
            if market_attr and outcome_attr:
                return (market_attr, outcome_attr)
            
            # Check aria-label or title attributes
            aria_label = await odds_element.get_attribute('aria-label')
            title = await odds_element.get_attribute('title')
            
            context_text = aria_label or title or ''
            
            # Pattern matching for common markets
            if any(keyword in context_text.lower() for keyword in ['match result', '1x2', 'full time']):
                if '1' in context_text or 'home' in context_text.lower():
                    return ('1X2', '1')
                elif 'x' in context_text.lower() or 'draw' in context_text.lower():
                    return ('1X2', 'X')
                elif '2' in context_text or 'away' in context_text.lower():
                    return ('1X2', '2')
            
            elif 'moneyline' in context_text.lower() or 'winner' in context_text.lower():
                if 'home' in context_text.lower() or '1' in context_text:
                    return ('Moneyline', 'Home')
                elif 'away' in context_text.lower() or '2' in context_text:
                    return ('Moneyline', 'Away')
            
            elif 'total' in context_text.lower() or 'over/under' in context_text.lower():
                if 'over' in context_text.lower():
                    return ('Totals', 'Over')
                elif 'under' in context_text.lower():
                    return ('Totals', 'Under')
            
            # Check parent elements for context
            parent = odds_element
            for _ in range(2):
                try:
                    parent = await parent.query_selector('..')
                    if parent:
                        parent_text = await parent.text_content()
                        if 'over' in parent_text.lower():
                            return ('Totals', 'Over')
                        elif 'under' in parent_text.lower():
                            return ('Totals', 'Under')
                except Exception:
                    break
            
            # Default fallback
            return ('Moneyline', 'Win')
            
        except Exception:
            return None
    
    async def _extract_basic_odds(self, event_element) -> Dict[str, Dict[str, float]]:
        """Extract basic odds when specific selectors fail."""
        markets = {}
        
        try:
            # Get all numeric values that could be odds
            all_text = await event_element.text_content()
            if not all_text:
                return markets
            
            import re
            odds_pattern = r'\b([1-9]\.\d{2})\b'
            potential_odds = re.findall(odds_pattern, all_text)
            
            if len(potential_odds) >= 2:
                odds_values = [float(odd) for odd in potential_odds[:3]]
                
                if len(odds_values) == 3:
                    # Assume 1X2 market
                    markets['1X2'] = {
                        '1': odds_values[0],
                        'X': odds_values[1],
                        '2': odds_values[2]
                    }
                elif len(odds_values) == 2:
                    # Assume Moneyline
                    markets['Moneyline'] = {
                        'Home': odds_values[0],
                        'Away': odds_values[1]
                    }
        
        except Exception as e:
            logger.debug(f"Stake: Error extracting basic odds: {e}")
        
        return markets