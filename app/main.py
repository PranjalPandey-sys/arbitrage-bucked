"""Main FastAPI application for arbitrage detection backend."""

import asyncio
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from datetime import datetime

from api.routes import router
from config import settings
from utils.logging import get_logger, setup_logging

# Setup logging
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("Starting arbitrage detection backend...")
    
    # Startup tasks
    try:
        # Initialize playwright browsers
        from playwright.async_api import async_playwright
        playwright = await async_playwright().start()
        app.state.playwright = playwright
        logger.info("Playwright initialized")
        
        # Test system components
        logger.info("System startup completed successfully")
        
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise
    
    yield
    
    # Shutdown tasks
    logger.info("Shutting down arbitrage detection backend...")
    
    try:
        # Clean up playwright
        if hasattr(app.state, 'playwright'):
            await app.state.playwright.stop()
            logger.info("Playwright cleanup completed")
            
    except Exception as e:
        logger.error(f"Shutdown error: {e}")


# Create FastAPI application
app = FastAPI(
    title="Arbitrage Detection API",
    description="""
    Production-grade arbitrage detection backend for sports betting.
    
    ## Features
    - Real-time scraping from 6 major bookmakers
    - Event matching across bookmakers
    - Arbitrage opportunity detection
    - Comprehensive filtering and sorting
    - Live and pre-match odds support
    - CSV export functionality
    
    ## Supported Bookmakers
    - Mostbet
    - Stake  
    - Leon
    - Parimatch
    - 1xBet
    - 1Win
    
    ## Supported Sports
    - Football, Basketball, Tennis, Cricket, Baseball, Hockey
    - Esports: CS:GO, Dota 2, League of Legends, Valorant, PUBG
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# Add middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)

# Include API routes
app.include_router(router, tags=["arbitrage"])


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "service": "Arbitrage Detection API",
        "version": "1.0.0",
        "status": "operational",
        "timestamp": datetime.now().isoformat(),
        "endpoints": {
            "arbitrages": "/api/arbs",
            "live_arbitrages": "/api/arbs/live", 
            "best_arbitrages": "/api/arbs/best",
            "system_status": "/api/status",
            "documentation": "/docs",
            "health_check": "/health"
        },
        "features": [
            "Real-time bookmaker scraping",
            "Event matching and normalization", 
            "Arbitrage detection and calculation",
            "Comprehensive filtering options",
            "Live odds support",
            "CSV data export",
            "System health monitoring"
        ],
        "supported_bookmakers": [
            "Mostbet", "Stake", "Leon", "Parimatch", "1xBet", "1Win"
        ]
    }


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler."""
    logger.error(f"Unhandled exception on {request.url}: {exc}")
    
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "timestamp": datetime.now().isoformat(),
            "path": str(request.url)
        }
    )


@app.middleware("http")
async def logging_middleware(request, call_next):
    """Log all HTTP requests."""
    start_time = datetime.now()
    
    response = await call_next(request)
    
    process_time = (datetime.now() - start_time).total_seconds()
    
    logger.info(
        f"{request.method} {request.url} - "
        f"Status: {response.status_code} - "
        f"Time: {process_time:.3f}s"
    )
    
    return response


if __name__ == "__main__":
    # Run with uvicorn
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        workers=1 if settings.debug else settings.workers,
        log_level=settings.log_level.lower(),
        access_log=True
    )