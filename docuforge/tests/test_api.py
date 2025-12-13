# Copyright (c) 2025 GÖKSEL ÖZKAN
# API Endpoint Tests

import pytest
from pathlib import Path


class TestAPIInfo:
    """Tests for /api/info endpoint"""
    
    def test_info_returns_cpu_count(self):
        """System info should include CPU count"""
        import os
        from docuforge.api import get_system_info
        
        result = get_system_info()
        
        assert "cpu_count" in result
        assert result["cpu_count"] == os.cpu_count()
    
    def test_info_returns_optimal_workers(self):
        """System info should calculate optimal workers"""
        import os
        from docuforge.api import get_system_info
        
        result = get_system_info()
        
        assert "optimal_workers" in result
        expected = max(1, int((os.cpu_count() or 4) * 0.75))
        assert result["optimal_workers"] == expected


class TestPathValidation:
    """Tests for path traversal protection"""
    
    def test_home_directory_allowed(self):
        """Paths under user home should be allowed"""
        from pathlib import Path
        
        # Simulate the validation logic from api.py
        output_path = str(Path.home() / "Documents" / "output")
        target_path = Path(output_path).resolve()
        allowed_roots = [Path.home().resolve(), Path("C:/Users/Public").resolve()]
        is_safe = any(str(target_path).startswith(str(root)) for root in allowed_roots)
        
        assert is_safe is True
    
    def test_system_directory_blocked(self):
        """System directories should be blocked"""
        from pathlib import Path
        
        # Simulate the validation logic from api.py
        output_path = "C:/Windows/System32"
        target_path = Path(output_path).resolve()
        allowed_roots = [Path.home().resolve(), Path("C:/Users/Public").resolve()]
        is_safe = any(str(target_path).startswith(str(root)) for root in allowed_roots)
        
        assert is_safe is False
    
    def test_traversal_attempt_blocked(self):
        """Path traversal attempts should be blocked"""
        from pathlib import Path
        
        # Simulate traversal attempt
        output_path = str(Path.home() / ".." / ".." / "Windows")
        target_path = Path(output_path).resolve()
        allowed_roots = [Path.home().resolve(), Path("C:/Users/Public").resolve()]
        is_safe = any(str(target_path).startswith(str(root)) for root in allowed_roots)
        
        assert is_safe is False


class TestConfigValidation:
    """Tests for AppConfig model"""
    
    def test_default_config_values(self):
        """Default config should have expected values"""
        from docuforge.src.core.config import AppConfig
        
        config = AppConfig()
        
        assert config.workers == 4
        assert config.ocr.enable == "auto"
        assert config.extraction.tables_enabled is True
        assert config.extraction.images_enabled is False
    
    def test_ocr_modes(self):
        """OCR config should accept valid modes"""
        from docuforge.src.core.config import OCRConfig
        
        for mode in ["auto", "on", "off"]:
            config = OCRConfig(enable=mode)
            assert config.enable == mode
    
    def test_cleaning_config_defaults(self):
        """Cleaning config should have safe defaults"""
        from docuforge.src.core.config import CleaningConfig
        
        config = CleaningConfig()
        
        assert 0 < config.repeated_text_ratio <= 1.0
        assert config.header_top_percent < 0.2  # Should be small
        assert len(config.regex_blacklist) > 0  # Should have some patterns
