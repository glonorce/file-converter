# DocuForge Test Configuration
import pytest
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

@pytest.fixture
def sample_turkish_text():
    """Sample Turkish text with broken spacing (pre-heal)"""
    return "B u kitap v e diğerleri d e önemlidir."

@pytest.fixture
def sample_english_text():
    """Sample English text with broken spacing (pre-heal)"""
    return "T he quick brown fox jumps over t he lazy dog."

@pytest.fixture
def sample_config():
    """Provides default AppConfig for testing"""
    from docuforge.src.core.config import AppConfig
    return AppConfig()
