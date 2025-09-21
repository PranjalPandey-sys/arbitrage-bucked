"""Logging configuration and utilities."""

import logging
import logging.handlers
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

from config import settings


def setup_logging() -> None:
    """Setup logging configuration for the application."""
    
    # Create logs directory
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create formatter
    formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        filename=logs_dir / settings.log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # Error file handler
    error_handler = logging.handlers.RotatingFileHandler(
        filename=logs_dir / 'errors.log',
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=3,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    root_logger.addHandler(error_handler)
    
    # Scraping activity log
    scraping_handler = logging.handlers.RotatingFileHandler(
        filename=logs_dir / 'scraping.log',
        maxBytes=20 * 1024 * 1024,  # 20MB
        backupCount=10,
        encoding='utf-8'
    )
    scraping_handler.setLevel(logging.DEBUG)
    scraping_handler.setFormatter(formatter)
    
    # Add scraping handler to scraping-related loggers
    scraping_loggers = [
        'books.mostbet', 'books.stake', 'books.leon', 
        'books.parimatch', 'books.onexbet', 'books.onewin',
        'service.orchestrator'
    ]
    
    for logger_name in scraping_loggers:
        logger = logging.getLogger(logger_name)
        logger.addHandler(scraping_handler)
    
    # Set specific log levels for third-party libraries
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('selenium').setLevel(logging.WARNING)
    logging.getLogger('playwright').setLevel(logging.WARNING)
    
    root_logger.info("Logging system initialized")


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the specified name."""
    return logging.getLogger(name)


class ArbitrageLogFilter(logging.Filter):
    """Custom log filter for arbitrage-related events."""
    
    def filter(self, record):
        """Filter log records for arbitrage events."""
        arbitrage_keywords = [
            'arbitrage', 'arb', 'profit', 'surebet', 
            'opportunity', 'guaranteed'
        ]
        
        return any(keyword in record.getMessage().lower() 
                  for keyword in arbitrage_keywords)


class ScrapingLogFilter(logging.Filter):
    """Custom log filter for scraping-related events."""
    
    def filter(self, record):
        """Filter log records for scraping events."""
        scraping_keywords = [
            'scraping', 'scraped', 'odds', 'bookmaker',
            'navigate', 'extract', 'browser'
        ]
        
        return any(keyword in record.getMessage().lower() 
                  for keyword in scraping_keywords)


def log_arbitrage_found(logger: logging.Logger, arb_data: dict) -> None:
    """Log arbitrage opportunity discovery with structured data."""
    logger.info(
        f"ARBITRAGE FOUND: {arb_data.get('event_name', 'Unknown Event')} | "
        f"Profit: {arb_data.get('profit_percentage', 0):.2f}% | "
        f"Amount: ${arb_data.get('guaranteed_profit', 0):.2f} | "
        f"Market: {arb_data.get('market_type', 'Unknown')} | "
        f"Bookmakers: {', '.join(arb_data.get('bookmakers', []))}"
    )


def log_scraping_result(logger: logging.Logger, bookmaker: str, 
                       odds_count: int, events_count: int, 
                       duration: float, success: bool = True) -> None:
    """Log scraping result with performance metrics."""
    if success:
        logger.info(
            f"SCRAPING SUCCESS: {bookmaker} | "
            f"Odds: {odds_count} | Events: {events_count} | "
            f"Duration: {duration:.2f}s | "
            f"Rate: {odds_count/duration:.1f} odds/sec"
        )
    else:
        logger.error(
            f"SCRAPING FAILED: {bookmaker} | "
            f"Duration: {duration:.2f}s"
        )


def log_matching_result(logger: logging.Logger, raw_events: int, 
                       matched_events: int, efficiency: float) -> None:
    """Log event matching results."""
    logger.info(
        f"MATCHING RESULT: {raw_events} raw events → "
        f"{matched_events} matched events | "
        f"Efficiency: {efficiency:.1f}%"
    )


class PerformanceLogger:
    """Context manager for logging performance metrics."""
    
    def __init__(self, logger: logging.Logger, operation: str):
        self.logger = logger
        self.operation = operation
        self.start_time = None
    
    def __enter__(self):
        self.start_time = datetime.now()
        self.logger.debug(f"Starting {self.operation}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = (datetime.now() - self.start_time).total_seconds()
        
        if exc_type is None:
            self.logger.info(f"Completed {self.operation} in {duration:.2f}s")
        else:
            self.logger.error(
                f"Failed {self.operation} after {duration:.2f}s: {exc_val}"
            )


def setup_structured_logging() -> None:
    """Setup structured logging for better log analysis."""
    
    import json
    
    class JSONFormatter(logging.Formatter):
        """JSON formatter for structured logging."""
        
        def format(self, record):
            log_entry = {
                'timestamp': datetime.fromtimestamp(record.created).isoformat(),
                'level': record.levelname,
                'logger': record.name,
                'message': record.getMessage(),
                'module': record.module,
                'function': record.funcName,
                'line': record.lineno
            }
            
            # Add exception info if present
            if record.exc_info:
                log_entry['exception'] = self.formatException(record.exc_info)
            
            # Add extra fields
            for key, value in record.__dict__.items():
                if key not in ['name', 'msg', 'args', 'levelname', 'levelno', 
                              'pathname', 'filename', 'module', 'lineno', 
                              'funcName', 'created', 'msecs', 'relativeCreated', 
                              'thread', 'threadName', 'processName', 'process',
                              'getMessage', 'exc_info', 'exc_text', 'stack_info']:
                    log_entry[key] = value
            
            return json.dumps(log_entry, ensure_ascii=False)
    
    # Create structured log file
    logs_dir = Path("logs")
    structured_handler = logging.handlers.RotatingFileHandler(
        filename=logs_dir / 'structured.json',
        maxBytes=50 * 1024 * 1024,  # 50MB
        backupCount=5,
        encoding='utf-8'
    )
    structured_handler.setFormatter(JSONFormatter())
    
    # Add to root logger
    root_logger = logging.getLogger()
    root_logger.addHandler(structured_handler)