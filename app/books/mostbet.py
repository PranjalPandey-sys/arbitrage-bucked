"""Mostbet scraper implementation."""

import asyncio
import random
from datetime import datetime
from typing import List, Dict, Optional
from urllib.parse import urljoin

from books.base import BaseScraper
from schema.models import RawOddsData, BookmakerName
from utils.logging import get_logger

logger = get_logger(__name__)


class MostbetScraper(BaseScraper):
    """Scraper for Mostbet sportsbook."""
    
    def __init__(self):
        super().__init__(BookmakerName.MOSTBET)
    
    def get_base_url(self) -> str:
        return "https://mostbet.com"
    
    async def scrape_all_odds(self) -> List[RawOddsData]:
        """
        Scrape all available odds from this bookmaker and return them
        in the normalized format expected by the orchestrator.
        """
        all_odds = []
        
        try:
            # Initialize browser if needed
            if not self.page:
                logger.info("Mostbet: Browser not initialized, skipping scraping")
                return all_odds
            
            # Scrape sports odds
            logger.info("Mostbet: Starting sports odds scraping")
            sports_odds = await self.scrape_sports_odds()
            all_odds.extend(sports_odds)
            logger.info(f"Mostbet: Scraped {len(sports_odds)} sports odds")
            
            # Scrape esports odds
            logger.info("Mostbet: Starting esports odds scraping")
            esports_odds = await self.scrape_esports_odds()
            all_odds.extend(esports_odds)
            logger.info(f"Mostbet: Scraped {len(esports_odds)} esports odds")
            
            logger.info(f"Mostbet: Total odds scraped: {len(all_odds)}")
            
        except Exception as e:
            logger.error(f"Mostbet: Error in scrape_all_odds: {e}")
        
        return all_odds
    
    async def scrape_sports_odds(self) -> List[RawOddsData]:
        """Scrape sports odds from Mostbet."""
        all_odds = []
        
        # Sports sections to scrape
        sports_urls = {
            'football': '/en/sports/football',
            'basketball': '/en/sports/basketball', 
            'tennis': '/en/sports/tennis',
            'cricket': '/en/sports/cricket',
            'baseball': '/en/sports/baseball',
            'hockey': '/en/sports/ice-hockey'
        }
        
        for sport, url_path in sports_urls.items():
            try:
                odds = await self._scrape_sport_section(sport, url_path)
                all_odds.extend(odds)
                await asyncio.sleep(random.uniform(2, 4))
            except Exception as e:
                logger.error(f"Mostbet: Failed to scrape {sport}: {e}")
        
        return all_odds
    
    async def scrape_esports_odds(self) -> List[RawOddsData]:
        """Scrape esports odds from Mostbet."""
        all_odds = []
        
        esports_urls = {
            'csgo': '/en/sports/e-sports/counter-strike',
            'dota2': '/en/sports/e-sports/dota-2',
            'lol': '/en/sports/e-sports/league-of-legends',
            'valorant': '/en/sports/e-sports/valorant',
            'pubg': '/en/sports/e-sports/pubg'
        }
        
        for esport, url_path in esports_urls.items():
            try:
                odds = await self._scrape_sport_section(esport, url_path)
                all_odds.extend(odds)
                await asyncio.sleep(random.uniform(2, 4))
            except Exception as e:
                logger.error(f"Mostbet: Failed to scrape {esport}: {e}")
        
        return all_odds
    
    async def _scrape_sport_section(self, sport: str, url_path: str) -> List[RawOddsData]:
        """Scrape a specific sport section."""
        odds = []
        url = urljoin(self.base_url, url_path)
        
        if not await self.navigate_with_retry(url):
            return odds
        
        await self.handle_cookie_banner()
        await asyncio.sleep(random.uniform(2, 4))
        
        try:
            # Wait for matches to load
            await self.page.wait_for_selector('[data-testid="event-item"], .event-item, .match-item', timeout=10000)
            
            # Find all match/event containers
            event_selectors = [
                '[data-testid="event-item"]',
                '.event-item',
                '.match-item',
                '.sport-event',
                '[class*="event"][class*="item"]'
            ]
            
            events_found = False
            for selector in event_selectors:
                try:
                    events = await self.page.query_selector_all(selector)
                    if events:
                        logger.info(f"Mostbet: Found {len(events)} events with selector {selector}")
                        events_found = True
                        break
                except Exception:
                    continue
            
            if not events_found:
                # Try to find events by examining page structure
                events = await self._find_events_by_structure()
            
            for event in events:
                try:
                    event_odds = await self._extract_event_odds(event, sport)
                    odds.extend(event_odds)
                except Exception as e:
                    logger.debug(f"Mostbet: Failed to extract odds from event: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"Mostbet: Error scraping {sport} section: {e}")
        
        logger.info(f"Mostbet: Extracted {len(odds)} odds from {sport}")
        return odds
    
    async def _find_events_by_structure(self) -> List:
        """Find events by analyzing page structure when standard selectors fail."""
        try:
            # Look for common patterns in Mostbet HTML structure
            potential_selectors = [
                'div[class*="match"]',
                'div[class*="game"]',
                'div[class*="event"]',
                'tr[class*="event"]',
                'li[class*="match"]',
                '[data-key*="event"]',
                '[data-id*="match"]'
            ]
            
            for selector in potential_selectors:
                elements = await self.page.query_selector_all(selector)
                if elements:
                    # Filter elements that likely contain odds
                    valid_events = []
                    for element in elements:
                        text_content = await element.text_content()
                        if text_content and any(char.isdigit() for char in text_content):
                            # Check if contains odds-like numbers
                            if any(word in text_content for word in ['vs', '-', 'v']):
                                valid_events.append(element)
                    
                    if valid_events:
                        logger.info(f"Mostbet: Found {len(valid_events)} events via structure analysis")
                        return valid_events
            
            return []
            
        except Exception as e:
            logger.error(f"Mostbet: Error in structure analysis: {e}")
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
            
            # Extract odds from different market types
            markets_odds = await self._extract_market_odds(event_element)
            
            for market_name, market_odds in markets_odds.items():
                normalized_market, line = self.extract_line_from_market(market_name)
                
                for outcome_name, odds_value in market_odds.items():
                    if odds_value and odds_value >= 1.01:
                        odds_data = RawOddsData(
                            event_name=event_name,
                            start_time=event_time,
                            sport=sport,
                            league=None,  # Extract league if available
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
            logger.debug(f"Mostbet: Error extracting event odds: {e}")
        
        return odds
    
    async def _extract_event_name(self, event_element) -> Optional[str]:
        """Extract event name from event element."""
        try:
            # Try different selectors for event name
            name_selectors = [
                '[data-testid="event-name"]',
                '.event-name',
                '.match-name',
                '.teams',
                '[class*="name"]',
                '[class*="title"]',
                'h3', 'h4', 'h5'
            ]
            
            for selector in name_selectors:
                try:
                    name_element = await event_element.query_selector(selector)
                    if name_element:
                        name = await name_element.text_content()
                        if name and name.strip():
                            return name.strip()
                except Exception:
                    continue
            
            # Fallback: get text content and try to extract team names
            full_text = await event_element.text_content()
            if full_text:
                # Look for patterns like "Team A vs Team B" or "Team A - Team B"
                import re
                vs_pattern = r'(.+?)\s+(?:vs?\.?|[-–—])\s+(.+?)(?:\s|$)'
                match = re.search(vs_pattern, full_text, re.IGNORECASE)
                if match:
                    team1, team2 = match.groups()
                    # Clean up team names
                    team1 = re.sub(r'^\d+\.?\s*', '', team1).strip()
                    team2 = re.sub(r'^\d+\.?\s*', '', team2).strip()
                    if team1 and team2:
                        return f"{team1} vs {team2}"
            
            return None
            
        except Exception as e:
            logger.debug(f"Mostbet: Error extracting event name: {e}")
            return None
    
    async def _extract_event_time(self, event_element) -> Optional[datetime]:
        """Extract event start time."""
        try:
            time_selectors = [
                '[data-testid="event-time"]',
                '.event-time',
                '.match-time',
                '.time',
                '[class*="time"]',
                '[class*="date"]'
            ]
            
            for selector in time_selectors:
                try:
                    time_element = await event_element.query_selector(selector)
                    if time_element:
                        time_text = await time_element.text_content()
                        if time_text:
                            return self.parse_event_time(time_text.strip())
                except Exception:
                    continue
            
            return None
            
        except Exception as e:
            logger.debug(f"Mostbet: Error extracting event time: {e}")
            return None
    
    async def _is_live_event(self, event_element) -> bool:
        """Check if event is live."""
        try:
            # Look for live indicators
            live_selectors = [
                '[data-testid="live-indicator"]',
                '.live',
                '.in-play',
                '[class*="live"]',
                '[class*="inplay"]'
            ]
            
            for selector in live_selectors:
                live_element = await event_element.query_selector(selector)
                if live_element:
                    return True
            
            # Check text content for live indicators
            text_content = await event_element.text_content()
            if text_content:
                live_keywords = ['live', 'in-play', 'playing', '●', 'red dot']
                return any(keyword in text_content.lower() for keyword in live_keywords)
            
            return False
            
        except Exception:
            return False
    
    async def _extract_event_url(self, event_element) -> Optional[str]:
        """Extract clickable URL for the event."""
        try:
            # Look for clickable links
            link_element = await event_element.query_selector('a[href]')
            if link_element:
                href = await link_element.get_attribute('href')
                if href:
                    return urljoin(self.base_url, href)
            
            # Check if the element itself is clickable
            onclick = await event_element.get_attribute('onclick')
            if onclick and 'event' in onclick.lower():
                return self.page.url  # Return current page as fallback
            
            return self.page.url
            
        except Exception:
            return self.page.url
    
    async def _extract_market_odds(self, event_element) -> Dict[str, Dict[str, float]]:
        """Extract odds for different markets from event element."""
        markets = {}
        
        try:
            # Look for odds containers
            odds_selectors = [
                '[data-testid*="odds"]',
                '.odds',
                '.coefficient',
                '[class*="odds"]',
                '[class*="coef"]',
                'button[class*="bet"]'
            ]
            
            odds_elements = []
            for selector in odds_selectors:
                elements = await event_element.query_selector_all(selector)
                odds_elements.extend(elements)
            
            # Group odds by market type
            for odds_element in odds_elements:
                try:
                    odds_value = await self._extract_odds_value(odds_element)
                    if not odds_value:
                        continue
                    
                    # Try to determine market and outcome
                    market_info = await self._determine_market_and_outcome(odds_element, event_element)
                    if market_info:
                        market_name, outcome_name = market_info
                        
                        if market_name not in markets:
                            markets[market_name] = {}
                        
                        markets[market_name][outcome_name] = odds_value
                
                except Exception as e:
                    logger.debug(f"Mostbet: Error processing odds element: {e}")
                    continue
            
            # If no specific markets found, try to extract basic 1X2/Moneyline
            if not markets:
                markets = await self._extract_basic_odds(event_element)
        
        except Exception as e:
            logger.debug(f"Mostbet: Error extracting market odds: {e}")
        
        return markets
    
    async def _extract_odds_value(self, odds_element) -> Optional[float]:
        """Extract numerical odds value from element."""
        try:
            # Try to get odds from different attributes
            for attr in ['data-odds', 'data-coefficient', 'data-value']:
                value = await odds_element.get_attribute(attr)
                if value:
                    return self.parse_decimal_odds(value)
            
            # Get text content
            text = await odds_element.text_content()
            if text:
                return self.parse_decimal_odds(text.strip())
            
            return None
            
        except Exception:
            return None
    
    async def _determine_market_and_outcome(self, odds_element, event_element) -> Optional[tuple]:
        """Determine market type and outcome name for an odds element."""
        try:
            # Look for market context in parent elements
            parent = odds_element
            for _ in range(3):  # Check up to 3 levels up
                try:
                    parent_text = await parent.text_content()
                    if parent_text:
                        # Check for common market patterns
                        if any(keyword in parent_text.lower() for keyword in ['1x2', 'match result', 'winner']):
                            # Determine outcome based on position or text
                            odds_text = await odds_element.text_content()
                            if '1' in odds_text or 'home' in odds_text.lower():
                                return ('1X2', '1')
                            elif 'x' in odds_text.lower() or 'draw' in odds_text.lower():
                                return ('1X2', 'X')
                            elif '2' in odds_text or 'away' in odds_text.lower():
                                return ('1X2', '2')
                        
                        elif 'over' in parent_text.lower():
                            return ('Totals', 'Over')
                        elif 'under' in parent_text.lower():
                            return ('Totals', 'Under')
                    
                    parent = await parent.query_selector('..')
                    if not parent:
                        break
                        
                except Exception:
                    break
            
            # Default fallback
            return ('Moneyline', 'Win')
            
        except Exception:
            return None
    
    async def _extract_basic_odds(self, event_element) -> Dict[str, Dict[str, float]]:
        """Extract basic 1X2/Moneyline odds as fallback."""
        markets = {}
        
        try:
            # Look for any numeric values that could be odds
            all_text = await event_element.text_content()
            if not all_text:
                return markets
            
            import re
            # Find numbers that look like odds (1.xx format)
            odds_pattern = r'\b([1-9]\.\d{1,3})\b'
            potential_odds = re.findall(odds_pattern, all_text)
            
            if len(potential_odds) >= 2:
                # Assume first two are 1X2 or Moneyline
                markets['1X2'] = {}
                
                if len(potential_odds) >= 3:
                    # Three-way market (1X2)
                    markets['1X2']['1'] = float(potential_odds[0])
                    markets['1X2']['X'] = float(potential_odds[1])
                    markets['1X2']['2'] = float(potential_odds[2])
                else:
                    # Two-way market (Moneyline)
                    markets['Moneyline'] = {
                        'Home': float(potential_odds[0]),
                        'Away': float(potential_odds[1])
                    }
        
        except Exception as e:
            logger.debug(f"Mostbet: Error extracting basic odds: {e}")
        
        return markets