"""FastAPI routes for arbitrage detection API."""

from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Query, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse

from schema.models import ArbitrageFilters, ArbitrageResponse, SportType, MarketType, BookmakerName
from service.orchestrator import ArbitrageOrchestrator
from utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()
orchestrator = ArbitrageOrchestrator()


@router.get("/api/arbs", response_model=ArbitrageResponse)
async def get_arbitrages(
    sport: Optional[SportType] = Query(None, description="Filter by sport type"),
    market_type: Optional[MarketType] = Query(None, description="Filter by market type"),
    min_arb_percentage: Optional[float] = Query(None, ge=0, description="Minimum arbitrage profit percentage"),
    min_profit: Optional[float] = Query(None, ge=0, description="Minimum profit amount"),
    bookmakers: Optional[List[BookmakerName]] = Query(None, description="Filter by bookmakers"),
    live_only: Optional[bool] = Query(None, description="Only live events"),
    max_start_hours: Optional[int] = Query(None, ge=0, le=168, description="Maximum hours until event start"),
    bankroll: Optional[float] = Query(None, gt=0, description="Bankroll for stake calculations"),
    use_cache: bool = Query(True, description="Use cached results if available"),
    background_tasks: BackgroundTasks = None
):
    """
    Get arbitrage opportunities.
    
    Main endpoint for retrieving arbitrage opportunities with comprehensive filtering options.
    """
    try:
        # Create filters object
        filters = ArbitrageFilters(
            sport=sport,
            market_type=market_type,
            min_arb_percentage=min_arb_percentage,
            min_profit=min_profit,
            bookmakers=bookmakers,
            live_only=live_only,
            max_start_hours=max_start_hours,
            bankroll=bankroll
        )
        
        # Get arbitrages (cached or fresh)
        if use_cache:
            response = await orchestrator.get_cached_arbitrages(filters)
        else:
            response = await orchestrator.run_full_arbitrage_detection(filters)
        
        logger.info(f"Returned {len(response.arbitrages)} arbitrages")
        return response
        
    except Exception as e:
        logger.error(f"Error in get_arbitrages: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/arbs/refresh")
async def refresh_arbitrages(
    sport: Optional[SportType] = None,
    market_type: Optional[MarketType] = None,
    bookmakers: Optional[List[BookmakerName]] = None,
    background_tasks: BackgroundTasks = None
):
    """
    Force refresh of arbitrage data.
    
    Triggers fresh scraping of all bookmakers and arbitrage detection.
    """
    try:
        filters = ArbitrageFilters(
            sport=sport,
            market_type=market_type,
            bookmakers=bookmakers
        )
        
        # Force fresh detection
        response = await orchestrator.run_full_arbitrage_detection(filters)
        
        return {
            "message": "Refresh completed",
            "arbitrages_found": len(response.arbitrages),
            "processing_time": response.summary.get("processing_time_seconds", 0),
            "scraped_bookmakers": len(response.scraping_results)
        }
        
    except Exception as e:
        logger.error(f"Error in refresh_arbitrages: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/sports")
async def get_supported_sports():
    """Get list of supported sports."""
    return {
        "sports": [sport.value for sport in SportType],
        "description": "List of all supported sports and esports"
    }


@router.get("/api/markets")
async def get_supported_markets():
    """Get list of supported market types."""
    return {
        "markets": [market.value for market in MarketType],
        "description": "List of all supported market types"
    }


@router.get("/api/bookmakers")
async def get_supported_bookmakers():
    """Get list of supported bookmakers."""
    return {
        "bookmakers": [bookmaker.value for bookmaker in BookmakerName],
        "description": "List of all supported bookmakers"
    }


@router.get("/api/status")
async def get_system_status():
    """
    Get system status and health information.
    """
    try:
        status = await orchestrator.get_system_status()
        return status
        
    except Exception as e:
        logger.error(f"Error getting system status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/bookmakers/{bookmaker}/test")
async def test_bookmaker(bookmaker: BookmakerName):
    """
    Test connection to a specific bookmaker.
    """
    try:
        result = await orchestrator.test_bookmaker_connection(bookmaker)
        
        if result["available"]:
            return result
        else:
            raise HTTPException(
                status_code=503,
                detail=f"Bookmaker {bookmaker.value} is not available: {result.get('error', 'Unknown error')}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error testing bookmaker {bookmaker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/arbs/live")
async def get_live_arbitrages(
    sport: Optional[SportType] = Query(None),
    min_arb_percentage: Optional[float] = Query(0.5, ge=0),
    bankroll: Optional[float] = Query(1000, gt=0)
):
    """
    Get live arbitrage opportunities only.
    
    Specialized endpoint for live betting arbitrages with faster refresh.
    """
    try:
        filters = ArbitrageFilters(
            sport=sport,
            min_arb_percentage=min_arb_percentage,
            bankroll=bankroll,
            live_only=True
        )
        
        # Always use fresh data for live arbitrages
        response = await orchestrator.run_full_arbitrage_detection(filters)
        
        # Add live-specific metadata
        response.summary["live_arbitrages_only"] = True
        response.summary["refresh_recommended_seconds"] = 10
        
        return response
        
    except Exception as e:
        logger.error(f"Error in get_live_arbitrages: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/arbs/best")
async def get_best_arbitrages(
    limit: int = Query(10, ge=1, le=50, description="Maximum number of arbitrages to return"),
    min_profit: Optional[float] = Query(20, ge=0, description="Minimum profit amount"),
    bankroll: Optional[float] = Query(1000, gt=0)
):
    """
    Get the best arbitrage opportunities sorted by profit percentage.
    """
    try:
        filters = ArbitrageFilters(
            min_profit=min_profit,
            bankroll=bankroll
        )
        
        response = await orchestrator.get_cached_arbitrages(filters)
        
        # Sort by profit percentage and limit results
        response.arbitrages.sort(key=lambda x: x.profit_percentage, reverse=True)
        response.arbitrages = response.arbitrages[:limit]
        
        response.summary["limited_to_best"] = limit
        response.summary["sort_criteria"] = "profit_percentage_desc"
        
        return response
        
    except Exception as e:
        logger.error(f"Error in get_best_arbitrages: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/arbs/export")
async def export_arbitrages(
    format: str = Query("json", regex="^(json|csv)$", description="Export format"),
    sport: Optional[SportType] = Query(None),
    min_arb_percentage: Optional[float] = Query(None, ge=0),
    background_tasks: BackgroundTasks = None
):
    """
    Export arbitrage opportunities in different formats.
    """
    try:
        filters = ArbitrageFilters(
            sport=sport,
            min_arb_percentage=min_arb_percentage
        )
        
        response = await orchestrator.get_cached_arbitrages(filters)
        
        if format == "json":
            return response
        
        elif format == "csv":
            # Return CSV data (simplified for now)
            import csv
            import io
            
            output = io.StringIO()
            fieldnames = ['event_name', 'sport', 'market_type', 'profit_percentage', 'guaranteed_profit']
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            
            for arb in response.arbitrages:
                writer.writerow({
                    'event_name': arb.event_name,
                    'sport': arb.sport or '',
                    'market_type': arb.market_type,
                    'profit_percentage': arb.profit_percentage,
                    'guaranteed_profit': arb.guaranteed_profit
                })
            
            csv_content = output.getvalue()
            output.close()
            
            return JSONResponse(
                content={"csv_data": csv_content, "count": len(response.arbitrages)},
                media_type="application/json"
            )
        
    except Exception as e:
        logger.error(f"Error in export_arbitrages: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/events/{event_name}/arbs")
async def get_event_arbitrages(
    event_name: str,
    bankroll: Optional[float] = Query(1000, gt=0)
):
    """
    Get arbitrage opportunities for a specific event.
    """
    try:
        filters = ArbitrageFilters(bankroll=bankroll)
        response = await orchestrator.get_cached_arbitrages(filters)
        
        # Filter for specific event
        event_arbs = [arb for arb in response.arbitrages if event_name.lower() in arb.event_name.lower()]
        
        if not event_arbs:
            raise HTTPException(status_code=404, detail=f"No arbitrages found for event: {event_name}")
        
        return {
            "event_name": event_name,
            "arbitrages": event_arbs,
            "total_found": len(event_arbs)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_event_arbitrages: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/bookmakers/{bookmaker}/arbs")
async def get_bookmaker_arbitrages(
    bookmaker: BookmakerName,
    bankroll: Optional[float] = Query(1000, gt=0)
):
    """
    Get arbitrage opportunities involving a specific bookmaker.
    """
    try:
        filters = ArbitrageFilters(
            bookmakers=[bookmaker],
            bankroll=bankroll
        )
        
        response = await orchestrator.get_cached_arbitrages(filters)
        
        return {
            "bookmaker": bookmaker.value,
            "arbitrages": response.arbitrages,
            "total_found": len(response.arbitrages)
        }
        
    except Exception as e:
        logger.error(f"Error in get_bookmaker_arbitrages: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/stats")
async def get_arbitrage_statistics():
    """
    Get statistical overview of arbitrage opportunities.
    """
    try:
        # Get all cached arbitrages for analysis
        response = await orchestrator.get_cached_arbitrages()
        arbitrages = response.arbitrages
        
        if not arbitrages:
            return {
                "total_arbitrages": 0,
                "message": "No arbitrages available for analysis"
            }
        
        # Calculate statistics
        profit_percentages = [arb.profit_percentage for arb in arbitrages]
        guaranteed_profits = [arb.guaranteed_profit for arb in arbitrages]
        
        stats = {
            "total_arbitrages": len(arbitrages),
            "profit_percentage_stats": {
                "min": min(profit_percentages),
                "max": max(profit_percentages),
                "average": sum(profit_percentages) / len(profit_percentages),
                "median": sorted(profit_percentages)[len(profit_percentages) // 2]
            },
            "guaranteed_profit_stats": {
                "min": min(guaranteed_profits),
                "max": max(guaranteed_profits),
                "average": sum(guaranteed_profits) / len(guaranteed_profits),
                "total": sum(guaranteed_profits)
            },
            "sports_distribution": {},
            "market_distribution": {},
            "bookmaker_pairs": {},
            "freshness_distribution": {
                "very_fresh": 0,  # > 0.9
                "fresh": 0,       # 0.7 - 0.9
                "acceptable": 0,  # 0.5 - 0.7
                "stale": 0        # < 0.5
            }
        }
        
        # Calculate distributions
        for arb in arbitrages:
            # Sports distribution
            sport = arb.sport or "unknown"
            stats["sports_distribution"][sport] = stats["sports_distribution"].get(sport, 0) + 1
            
            # Market distribution
            market = arb.market_type
            stats["market_distribution"][market] = stats["market_distribution"].get(market, 0) + 1
            
            # Bookmaker pairs
            bookmaker_names = [outcome.bookmaker.value for outcome in arb.outcomes]
            if len(bookmaker_names) >= 2:
                pair_key = f"{bookmaker_names[0]} vs {bookmaker_names[1]}"
                stats["bookmaker_pairs"][pair_key] = stats["bookmaker_pairs"].get(pair_key, 0) + 1
            
            # Freshness distribution
            if arb.freshness_score > 0.9:
                stats["freshness_distribution"]["very_fresh"] += 1
            elif arb.freshness_score > 0.7:
                stats["freshness_distribution"]["fresh"] += 1
            elif arb.freshness_score > 0.5:
                stats["freshness_distribution"]["acceptable"] += 1
            else:
                stats["freshness_distribution"]["stale"] += 1
        
        # Round floating point numbers
        for key in ["min", "max", "average", "median"]:
            stats["profit_percentage_stats"][key] = round(stats["profit_percentage_stats"][key], 2)
            stats["guaranteed_profit_stats"][key] = round(stats["guaranteed_profit_stats"][key], 2)
        
        stats["guaranteed_profit_stats"]["total"] = round(stats["guaranteed_profit_stats"]["total"], 2)
        
        return stats
        
    except Exception as e:
        logger.error(f"Error in get_arbitrage_statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """
    Simple health check endpoint.
    """
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "arbitrage-detection-api"
    }


# Error handlers are handled by the global exception handler in main.py