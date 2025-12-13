# Copyright (c) 2025 GÖKSEL ÖZKAN
# Centralized Logging Configuration for DocuForge

import sys
from pathlib import Path
from loguru import logger

# Remove default handler
logger.remove()

def configure_logging(
    level: str = "INFO",
    log_to_file: bool = False,
    log_dir: Path = None
):
    """
    Configure centralized logging for DocuForge.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_to_file: Whether to also log to a file
        log_dir: Directory for log files (default: current working directory)
    """
    # Console output with colors
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=level,
        colorize=True
    )
    
    if log_to_file:
        if log_dir is None:
            log_dir = Path.cwd()
        
        log_path = log_dir / "docuforge_{time}.log"
        
        logger.add(
            str(log_path),
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level="DEBUG",  # File gets all logs
            rotation="10 MB",
            retention="7 days",
            compression="zip"
        )

def get_logger(name: str = "docuforge"):
    """
    Get a logger instance with the given name.
    
    Args:
        name: Logger name (typically module name)
    
    Returns:
        Configured logger instance
    """
    return logger.bind(name=name)

# Initialize with default settings when imported
configure_logging()
