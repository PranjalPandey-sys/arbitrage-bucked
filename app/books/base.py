"""Base scraper class for all bookmaker scrapers."""

import asyncio
import random
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from datetime import datetime
from playwright.async_api import Page, Browser, BrowserContext

from schema.models import RawOddsData, BookmakerName
from utils.logging import get_logger

logger = get_logger(__name__)


class BaseScraper(ABC):
    """Abstract base class for all bookmaker scrapers."""
    
    def __init__(self, bookmaker: BookmakerName):
        """Initialize the scraper with bookmaker information."""
        self.bookmaker = bookmaker
        self.base_url = self.get_base_url()
        self.page: Optional[Page] = None
        self.context: Optional[BrowserContext] = None
        self.browser: Optional[Browser] = None
        
    @abstractmethod
    def get_base_url(self) -> str:
        """Get the base URL for the bookmaker."""
        pass
    
    @abstractmethod
    async def scrape_sports_odds(self) -> List[RawOddsData]:
        """Scrape sports odds from the bookmaker."""
        pass
    
    @abstractmethod 
    async def scrape_esports_odds(self) -> List[RawOddsData]:
        """Scrape esports odds from the bookmaker."""
        pass
        
    async def initialize_browser(self, playwright_or_browser) -> None:
        """Initialize browser context and page."""
        try:
            # If we get a Playwright instance, launch a browser first
            if hasattr(playwright_or_browser, 'chromium'):
                # This is a Playwright instance, launch browser
                self.browser = await playwright_or_browser.chromium.launch(headless=True)
            else:
                # This is already a Browser instance
                self.browser = playwright_or_browser
                
            self.context = await self.browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                extra_http_headers={
                    "Accept-Language": "en-US,en;q=0.9"
                }
            )
            self.page = await self.context.new_page()
            logger.info(f"{self.bookmaker}: Browser initialized")
            
        except Exception as e:
            logger.error(f"{self.bookmaker}: Failed to initialize browser: {e}")
            raise
            
    async def cleanup(self) -> None:
        """Clean up browser resources."""
        try:
            if self.page and not self.page.is_closed():
                await self.page.close()
            if self.context:
                await self.context.close()
            logger.info(f"{self.bookmaker}: Browser cleanup completed")
            
        except Exception as e:
            logger.error(f"{self.bookmaker}: Error during cleanup: {e}")
            
    async def navigate_with_retry(self, url: str, max_retries: int = 3) -> bool:
        """Navigate to URL with retries."""
        if not self.page:
            logger.error(f"{self.bookmaker}: Page not initialized")
            return False
            
        for attempt in range(max_retries):
            try:
                await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(random.uniform(1, 3))
                logger.info(f"{self.bookmaker}: Successfully navigated to {url}")
                return True
                
            except Exception as e:
                logger.warning(f"{self.bookmaker}: Navigation attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(random.uniform(2, 5))
                    
        logger.error(f"{self.bookmaker}: Failed to navigate to {url} after {max_retries} attempts")
        return False
        
    async def handle_cookie_banner(self) -> None:
        """Handle cookie consent banners."""
        if not self.page:
            return
            
        try:
            # Common cookie banner selectors
            cookie_selectors = [
                'button[id*="accept"]',
                'button[class*="accept"]',
                'button[id*="cookie"]',
                'button[class*="cookie"]',
                '[data-testid*="accept"]',
                '[data-testid*="cookie"]',
                '.cookie-accept',
                '.accept-cookies',
                '#accept-cookies',
                'button:has-text("Accept")',
                'button:has-text("OK")',
                'button:has-text("Agree")'
            ]
            
            for selector in cookie_selectors:
                try:
                    element = await self.page.query_selector(selector)
                    if element and await element.is_visible():
                        await element.click()
                        await asyncio.sleep(1)
                        logger.info(f"{self.bookmaker}: Cookie banner handled")
                        return
                except:
                    continue
                    
        except Exception as e:
            logger.debug(f"{self.bookmaker}: Error handling cookie banner: {e}")
            
    async def scroll_page(self, scrolls: int = 3) -> None:
        """Scroll page to load more content."""
        if not self.page:
            return
            
        try:
            for i in range(scrolls):
                await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(random.uniform(1, 2))
                
            # Scroll back to top
            await self.page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(1)
            
        except Exception as e:
            logger.debug(f"{self.bookmaker}: Error scrolling page: {e}")
            
    def parse_odds_value(self, odds_text: str) -> Optional[float]:
        """Parse odds value from text."""
        if not odds_text:
            return None
            
        try:
            # Clean the text
            cleaned = odds_text.strip().replace(',', '.')
            
            # Remove common prefixes/suffixes
            for prefix in ['@', '$', '€', '£']:
                cleaned = cleaned.replace(prefix, '')
                
            # Try to parse as decimal
            odds_value = float(cleaned)
            
            # Validate range
            if 1.0 <= odds_value <= 1000.0:
                return odds_value
                
        except (ValueError, TypeError):
            pass
            
        return None
        
    def normalize_team_name(self, team_name: str) -> str:
        """Normalize team name for matching."""
        if not team_name:
            return ""
            
        # Basic normalization
        normalized = team_name.strip().lower()
        
        # Remove common suffixes
        suffixes = [' fc', ' f.c.', ' cf', ' c.f.', ' united', ' city', ' town']
        for suffix in suffixes:
            if normalized.endswith(suffix):
                normalized = normalized[:-len(suffix)].strip()
                
        return normalized
        
    def parse_event_time(self, time_text: str) -> Optional[datetime]:
        """Parse event time from text."""
        # This is a simplified implementation
        # In a real system, you'd want more robust time parsing
        try:
            # Basic time parsing logic would go here
            # For now, return None to indicate live events
            return None
        except:
            return None