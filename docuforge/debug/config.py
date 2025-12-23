"""
DocuForge Debug System Configuration

Enable/disable specific debug areas by setting flags to True/False.
All debug logs go to: docuforge/debug/logs/

NOTE: logs/ folder is in .gitignore - only log files are ignored.
"""
from pathlib import Path

# Debug output directory (project-local)
DEBUG_LOG_DIR = Path(__file__).parent / "logs"

# ========================================
# DEBUG FLAGS - Set True to enable logging
# ========================================

DEBUG_FLAGS = {
    # Chunk Processing (multi-PDF issues, temp file management)
    "chunk_lifecycle": False,  # Tracks chunk creation, access, deletion
    
    # Extraction Pipeline  
    "text_extraction": False,  # Structure extraction, line reconstruction
    "table_extraction": False,  # Neural and legacy table detection
    "image_extraction": False,  # Image extraction process
    "chart_extraction": False,  # Chart/visual detection
    
    # OCR Processing
    "ocr_detection": False,  # OCR trigger decisions
    "ocr_processing": False,  # OCR execution details
    
    # Cleaning Pipeline
    "text_cleaning": False,  # Watermark removal, artifact cleaning
    "zone_cleaning": False,  # Header/footer detection
    
    # Memory & Performance
    "memory_usage": False,  # GC, memory cleanup events
    "performance": False,  # Timing information
    
    # API & Web
    "api_requests": False,  # Request/response logging
    "sse_events": False,  # SSE stream events
    
    # Executor & Multiprocessing
    "executor_lifecycle": False,  # Executor create/shutdown
}


def is_debug_enabled(area: str) -> bool:
    """Check if debug is enabled for a specific area."""
    return DEBUG_FLAGS.get(area, False)


def ensure_debug_dir():
    """Ensure debug log directory exists."""
    DEBUG_LOG_DIR.mkdir(parents=True, exist_ok=True)
