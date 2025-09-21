"""Main FastAPI application for arbitrage detection backend."""

import asyncio
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from datetime import datetime

# Updated imports for /app package structure
from app.api.routes import router
from app.config import settings
from app.utils.logging import get_logger, setup_logging
from app.schema.models import ArbitrageFilters, ArbitrageResponse, ArbitrageType, BookmakerName  # if used here

# Setup logging
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting arbitrage detection backend...")
    try:
        from playwright.async_api import async_playwright
        playwright = await async_playwright().start()
        app.state.playwright = playwright
        logger.info("Playwright initialized")
        logger.info("System startup completed successfully")
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise
    yield
    logger.info("Shutting down arbitrage detection backend...")
    try:
        if hasattr(app.state, 'playwright'):
            await app.state.playwright.stop()
            logger.info("Playwright cleanup completed")
    except Exception as e:
        logger.error(f"Shutdown error: {e}")


app = FastAPI(
    title="Arbitrage Detection API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)

app.include_router(router, tags=["arbitrage"])


@app.get("/")
async def root():
    return {
        "service": "Arbitrage Detection API",
        "version": "1.0.0",
        "status": "operational",
        "timestamp": datetime.now().isoformat()
    }


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
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
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        workers=1 if settings.debug else settings.workers,
        log_level=settings.log_level.lower(),
        access_log=True
)
