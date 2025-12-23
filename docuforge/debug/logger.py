"""
DocuForge Debug Logger Utility

Centralized debug logging that writes to text files instead of terminal.
Each debug area has its own log file for easy filtering.
"""
import datetime
from pathlib import Path
from typing import Any
from .config import DEBUG_LOG_DIR, is_debug_enabled, ensure_debug_dir


class DebugLogger:
    """Thread-safe debug logger that writes to text files."""
    
    _initialized = False
    
    @classmethod
    def _ensure_init(cls):
        if not cls._initialized:
            ensure_debug_dir()
            cls._initialized = True
    
    @classmethod
    def log(cls, area: str, message: str, **context):
        """
        Log a debug message if the area is enabled.
        
        Args:
            area: Debug area name (must match key in DEBUG_FLAGS)
            message: Human-readable log message
            **context: Additional context key-value pairs
        """
        if not is_debug_enabled(area):
            return
        
        cls._ensure_init()
        
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        log_file = DEBUG_LOG_DIR / f"{area}.txt"
        
        # Format log line
        log_line = f"[{timestamp}] {message}"
        if context:
            ctx_str = " | ".join(f"{k}={v}" for k, v in context.items())
            log_line += f" | {ctx_str}"
        
        # Write to file (append mode)
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(log_line + "\n")
        except Exception:
            pass  # Silently ignore log errors
    
    @classmethod
    def log_section(cls, area: str, title: str, content: Any):
        """Log a multi-line section with title."""
        if not is_debug_enabled(area):
            return
        
        cls._ensure_init()
        
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        log_file = DEBUG_LOG_DIR / f"{area}.txt"
        
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"\n[{timestamp}] ═══ {title} ═══\n")
                f.write(str(content) + "\n")
                f.write("═" * 50 + "\n\n")
        except Exception:
            pass


# Convenience function
def debug_log(area: str, message: str, **context):
    """Shortcut for DebugLogger.log()"""
    DebugLogger.log(area, message, **context)
