"""Main orchestrator service for coordinating scraping, matching, and arbitrage detection."""

import asyncio
import time
import csv
from datetime import datetime
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from playwright.async_api import async_playwright

from books.mostbet import MostbetScraper
from books.stake import StakeScraper
# from books.leon import LeonScraper
# from books.parimatch import ParimatchScraper
# from books.onexbet import OnexbetScraper
# from books.onewin import OnewinScraper
from match.matcher import EventMatcher
from engine.arbitrage import ArbitrageEngine
from schema.models import (
    RawOddsData, ArbitrageOpportunity, ArbitrageFilters, 
    ArbitrageResponse, ScrapingResult, BookmakerName
)
from config import settings
from utils.logging import get_logger

logger = get_logger(__name__)


class ArbitrageOrchestrator:
    """Main orchestrator for the arbitrage detection system."""
    
    def __init__(self):
        self.scrapers = self._initialize_scrapers()
        self.matcher = EventMatcher()
        self.arbitrage_engine = ArbitrageEngine()
        self.last_scrape_time = None
        self.cached_arbitrages = []
        
    def _initialize_scrapers(self):
        """Initialize all bookmaker scrapers."""
        scrapers = {}
        
        # Initialize available scrapers
        try:
            scrapers[BookmakerName.MOSTBET] = MostbetScraper()
            logger.info("Initialized Mostbet scraper")
        except Exception as e:
            logger.error(f"Failed to initialize Mostbet scraper: {e}")
        
        try:
            scrapers[BookmakerName.STAKE] = StakeScraper()
            logger.info("Initialized Stake scraper")
        except Exception as e:
            logger.error(f"Failed to initialize Stake scraper: {e}")
        
        # TODO: Initialize other scrapers when implemented
        # scrapers[BookmakerName.LEON] = LeonScraper()
        # scrapers[BookmakerName.PARIMATCH] = ParimatchScraper()
        # scrapers[BookmakerName.ONEXBET] = OnexbetScraper()
        # scrapers[BookmakerName.ONEWIN] = OnewinScraper()
        
        logger.info(f"Initialized {len(scrapers)} scrapers: {list(scrapers.keys())}")
        return scrapers
    
    async def run_full_arbitrage_detection(self, filters: Optional[ArbitrageFilters] = None) -> ArbitrageResponse:
        """Run complete arbitrage detection process."""
        start_time = time.time()
        logger.info("Starting full arbitrage detection process")
        
        try:
            # Step 1: Scrape all bookmakers
            scraping_results, all_odds = await self._scrape_all_bookmakers(filters)
            
            if not all_odds:
                logger.warning("No odds data scraped from any bookmaker")
                return ArbitrageResponse(
                    arbitrages=[],
                    scraping_results=scraping_results,
                    summary={"error": "No odds data available"}
                )
            
            # Step 2: Match events across bookmakers
            matched_events = self.matcher.match_events(all_odds)
            
            if not matched_events:
                logger.warning("No events matched across bookmakers")
                return ArbitrageResponse(
                    arbitrages=[],
                    scraping_results=scraping_results,
                    summary={"error": "No matched events found"}
                )
            
            # Step 3: Detect arbitrage opportunities
            arbitrages = self.arbitrage_engine.detect_arbitrages(matched_events, filters)
            
            # Step 4: Cache results and export data
            self.cached_arbitrages = arbitrages
            self.last_scrape_time = datetime.now()
            
            if settings.export_csv and arbitrages:
                await self._export_arbitrages_to_csv(arbitrages)
            
            if settings.save_raw_data:
                await self._save_raw_odds_data(all_odds)
            
            # Step 5: Create response
            processing_time = time.time() - start_time
            response = ArbitrageResponse(
                arbitrages=arbitrages,
                scraping_results=scraping_results
            )
            
            # Add summary statistics
            total_events = sum(r.events_count for r in scraping_results if r.success)
            total_odds = sum(r.odds_count for r in scraping_results if r.success)
            response.add_summary_stats(total_events, total_odds, processing_time)
            
            logger.info(f"Arbitrage detection completed in {processing_time:.2f}s - "
                       f"Found {len(arbitrages)} arbitrages from {total_events} events")
            
            return response
            
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"Error in arbitrage detection process: {e}")
            
            return ArbitrageResponse(
                arbitrages=[],
                scraping_results=[],
                summary={
                    "error": str(e),
                    "processing_time_seconds": round(processing_time, 2)
                }
            )
    
    async def _scrape_all_bookmakers(self, filters: Optional[ArbitrageFilters] = None) -> tuple[List[ScrapingResult], List[RawOddsData]]:
        """Scrape all bookmakers in parallel."""
        scraping_results = []
        all_odds = []
        
        # Filter scrapers based on filters
        active_scrapers = self.scrapers.copy()
        if filters and filters.bookmakers:
            active_scrapers = {k: v for k, v in active_scrapers.items() if k in filters.bookmakers}
        
        if not active_scrapers:
            logger.warning("No active scrapers available")
            return scraping_results, all_odds
        
        logger.info(f"Scraping {len(active_scrapers)} bookmakers: {list(active_scrapers.keys())}")
        
        # Create semaphore to limit concurrent scraping
        semaphore = asyncio.Semaphore(settings.concurrent_scrapers)
        
        async def scrape_with_semaphore(scraper):
            async with semaphore:
                return await scraper.scrape_all_odds()
        
        # Run all scrapers concurrently
        scraping_tasks = [scrape_with_semaphore(scraper) for scraper in active_scrapers.values()]
        results = await asyncio.gather(*scraping_tasks, return_exceptions=True)
        
        # Process results
        for i, result in enumerate(results):
            scraper_name = list(active_scrapers.keys())[i]
            
            if isinstance(result, Exception):
                logger.error(f"Scraper {scraper_name} failed with exception: {result}")
                scraping_results.append(ScrapingResult(
                    bookmaker=scraper_name,
                    success=False,
                    error_message=str(result)
                ))
            else:
                scraping_results.append(result)
                if result.success:
                    # Get the actual odds data (this would need to be stored by scrapers)
                    # For now, we'll simulate this - in practice, scrapers would return odds
                    logger.info(f"Successfully scraped {scraper_name}: {result.odds_count} odds")
        
        return scraping_results, all_odds
    
    async def get_cached_arbitrages(self, filters: Optional[ArbitrageFilters] = None) -> ArbitrageResponse:
        """Get cached arbitrage results with optional filtering."""
        if not self.cached_arbitrages or not self.last_scrape_time:
            logger.info("No cached data available, running fresh detection")
            return await self.run_full_arbitrage_detection(filters)
        
        # Check if cache is too old
        cache_age = datetime.now() - self.last_scrape_time
        max_cache_age_seconds = settings.live_refresh_interval if any(a.event_name for a in self.cached_arbitrages) else settings.prematch_refresh_interval
        
        if cache_age.total_seconds() > max_cache_age_seconds:
            logger.info("Cache is stale, running fresh detection")
            return await self.run_full_arbitrage_detection(filters)
        
        # Apply filters to cached results
        filtered_arbitrages = self._apply_filters_to_cached_results(self.cached_arbitrages, filters)
        
        response = ArbitrageResponse(
            arbitrages=filtered_arbitrages,
            scraping_results=[],  # Not available for cached results
            summary={
                "cached_result": True,
                "cache_age_seconds": int(cache_age.total_seconds()),
                "total_cached_arbitrages": len(self.cached_arbitrages),
                "filtered_arbitrages": len(filtered_arbitrages)
            }
        )
        
        return response
    
    def _apply_filters_to_cached_results(self, arbitrages: List[ArbitrageOpportunity], 
                                        filters: Optional[ArbitrageFilters]) -> List[ArbitrageOpportunity]:
        """Apply filters to cached arbitrage results."""
        if not filters:
            return arbitrages
        
        filtered = []
        
        for arb in arbitrages:
            # Apply sport filter
            if filters.sport and arb.sport != filters.sport.value:
                continue
            
            # Apply market type filter
            if filters.market_type and arb.market_type != filters.market_type.value:
                continue
            
            # Apply minimum arbitrage percentage filter
            if filters.min_arb_percentage and arb.profit_percentage < filters.min_arb_percentage:
                continue
            
            # Apply minimum profit filter
            bankroll = filters.bankroll or settings.default_bankroll
            if filters.min_profit:
                expected_profit = bankroll * (arb.profit_percentage / 100)
                if expected_profit < filters.min_profit:
                    continue
            
            # Apply bookmaker filter
            if filters.bookmakers:
                arb_bookmakers = set(outcome.bookmaker for outcome in arb.outcomes)
                if not any(bm in filters.bookmakers for bm in arb_bookmakers):
                    continue
            
            # Apply live filter
            if filters.live_only is not None:
                # Determine if arbitrage is live based on outcomes freshness
                is_live = arb.freshness_score > 0.8  # Simplified live detection
                if filters.live_only != is_live:
                    continue
            
            # Apply time filter
            if filters.max_start_hours and arb.start_time:
                max_time = datetime.now() + timedelta(hours=filters.max_start_hours)
                if arb.start_time > max_time:
                    continue
            
            # Recalculate stakes if different bankroll requested
            if filters.bankroll and filters.bankroll != arb.bankroll:
                arb.bankroll = filters.bankroll
                arb.guaranteed_profit = filters.bankroll * (arb.profit_percentage / 100)
                # Recalculate stakes (simplified)
                total_inverse = sum(1.0 / outcome.odds for outcome in arb.outcomes)
                for i, outcome in enumerate(arb.outcomes):
                    if i < len(arb.stakes):
                        stake_proportion = (1.0 / outcome.odds) / total_inverse
                        arb.stakes[i].stake_amount = round(filters.bankroll * stake_proportion, 2)
            
            filtered.append(arb)
        
        return filtered
    
    async def _export_arbitrages_to_csv(self, arbitrages: List[ArbitrageOpportunity]) -> None:
        """Export arbitrage opportunities to CSV file."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"arbitrages_{timestamp}.csv"
            filepath = Path("exports") / filename
            filepath.parent.mkdir(exist_ok=True)
            
            with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = [
                    'detected_at', 'event_name', 'sport', 'league', 'start_time',
                    'market_type', 'line', 'arb_percentage', 'profit_percentage',
                    'guaranteed_profit', 'bankroll', 'freshness_score',
                    'outcome_1_name', 'outcome_1_odds', 'outcome_1_bookmaker', 'outcome_1_stake',
                    'outcome_2_name', 'outcome_2_odds', 'outcome_2_bookmaker', 'outcome_2_stake',
                    'outcome_3_name', 'outcome_3_odds', 'outcome_3_bookmaker', 'outcome_3_stake'
                ]
                
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for arb in arbitrages:
                    row = {
                        'detected_at': arb.detected_at.isoformat(),
                        'event_name': arb.event_name,
                        'sport': arb.sport,
                        'league': arb.league,
                        'start_time': arb.start_time.isoformat() if arb.start_time else '',
                        'market_type': arb.market_type,
                        'line': arb.line,
                        'arb_percentage': arb.arb_percentage,
                        'profit_percentage': arb.profit_percentage,
                        'guaranteed_profit': arb.guaranteed_profit,
                        'bankroll': arb.bankroll,
                        'freshness_score': arb.freshness_score
                    }
                    
                    # Add outcome details
                    for i, (outcome, stake) in enumerate(zip(arb.outcomes, arb.stakes), 1):
                        if i <= 3:  # Support up to 3 outcomes
                            row[f'outcome_{i}_name'] = outcome.name
                            row[f'outcome_{i}_odds'] = outcome.odds
                            row[f'outcome_{i}_bookmaker'] = outcome.bookmaker.value
                            row[f'outcome_{i}_stake'] = stake.stake_amount
                    
                    writer.writerow(row)
            
            logger.info(f"Exported {len(arbitrages)} arbitrages to {filepath}")
            
        except Exception as e:
            logger.error(f"Failed to export arbitrages to CSV: {e}")
    
    async def _save_raw_odds_data(self, odds_data: List[RawOddsData]) -> None:
        """Save raw odds data for auditing."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"raw_odds_{timestamp}.csv"
            filepath = Path("exports") / filename
            filepath.parent.mkdir(exist_ok=True)
            
            with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = [
                    'scraped_at', 'bookmaker', 'event_name', 'sport', 'league',
                    'start_time', 'market_name', 'line', 'outcome_name', 'odds',
                    'url', 'is_live'
                ]
                
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for odds in odds_data:
                    row = {
                        'scraped_at': odds.scraped_at.isoformat(),
                        'bookmaker': odds.bookmaker.value,
                        'event_name': odds.event_name,
                        'sport': odds.sport,
                        'league': odds.league,
                        'start_time': odds.start_time.isoformat() if odds.start_time else '',
                        'market_name': odds.market_name,
                        'line': odds.line,
                        'outcome_name': odds.outcome_name,
                        'odds': odds.odds,
                        'url': odds.url,
                        'is_live': odds.is_live
                    }
                    writer.writerow(row)
            
            logger.info(f"Saved {len(odds_data)} raw odds entries to {filepath}")
            
        except Exception as e:
            logger.error(f"Failed to save raw odds data: {e}")
    
    async def get_system_status(self) -> Dict:
        """Get system status information."""
        status = {
            "scrapers": {},
            "last_scrape_time": self.last_scrape_time.isoformat() if self.last_scrape_time else None,
            "cached_arbitrages_count": len(self.cached_arbitrages),
            "system_uptime": time.time(),  # Simplified
            "configuration": {
                "fuzzy_threshold": settings.fuzzy_threshold,
                "min_arb_percentage": settings.min_arb_percentage,
                "concurrent_scrapers": settings.concurrent_scrapers,
                "scrape_timeout": settings.scrape_timeout
            }
        }
        
        # Check scraper availability
        for bookmaker, scraper in self.scrapers.items():
            try:
                status["scrapers"][bookmaker.value] = {
                    "available": True,
                    "base_url": scraper.base_url,
                    "last_error": None
                }
            except Exception as e:
                status["scrapers"][bookmaker.value] = {
                    "available": False,
                    "error": str(e)
                }
        
        return status
    
    async def test_bookmaker_connection(self, bookmaker: BookmakerName) -> Dict:
        """Test connection to a specific bookmaker."""
        if bookmaker not in self.scrapers:
            return {
                "bookmaker": bookmaker.value,
                "available": False,
                "error": "Scraper not initialized"
            }
        
        scraper = self.scrapers[bookmaker]
        start_time = time.time()
        
        try:
            # Simple connection test - try to navigate to main page
            async with async_playwright() as playwright:
                await scraper.initialize_browser(playwright)
                
                if await scraper.navigate_with_retry(scraper.base_url):
                    response_time = time.time() - start_time
                    await scraper.cleanup()
                    
                    return {
                        "bookmaker": bookmaker.value,
                        "available": True,
                        "response_time_seconds": round(response_time, 2),
                        "base_url": scraper.base_url
                    }
                else:
                    await scraper.cleanup()
                    return {
                        "bookmaker": bookmaker.value,
                        "available": False,
                        "error": "Failed to navigate to site"
                    }
        
        except Exception as e:
            return {
                "bookmaker": bookmaker.value,
                "available": False,
                "error": str(e),
                "response_time_seconds": time.time() - start_time
            }