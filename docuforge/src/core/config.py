from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field
from ruamel.yaml import YAML

yaml = YAML()

class OCRConfig(BaseModel):
    enable: str = "auto"  # auto, on, off
    langs: str = "eng+tur"  # English + Turkish (scoop install tesseract-languages)
    force_for_low_text_ratio: float = 0.15
    broken_text_threshold: int = 4  # Matches for "s p a c e d" text to trigger OCR
    tesseract_config: str = "--psm 6"  # Page Segmentation Mode (6=Block, best for tables/mixed content)

class CleaningConfig(BaseModel):
    repeated_text_ratio: float = 0.6
    header_top_percent: float = 0.02 # Reduced from 0.10 to prevent cutting valid text
    footer_bottom_percent: float = 0.05 # Reduced for safety
    regex_blacklist: List[str] = []  # Empty by default - user adds watermarks via CLI/Web

class ExtractionConfig(BaseModel):
    tables_enabled: bool = True
    images_enabled: bool = False
    charts_enabled: bool = False  # OFF by default, user must enable explicitly
    recursive: bool = False # Process subdirectories (Tree mode)
    table_fallback_stream: bool = True  # NEW: Try 'stream' if 'lattice' fails
    min_table_accuracy: float = 0.7  # NEW: Minimum Camelot accuracy score
    min_image_dpi: int = 200
    
    # Neural-Spatial Engine Settings
    use_neural_engine: bool = True  # Enable new engine by default
    neural_min_table_rows: int = 2  # Minimum rows for valid table
    neural_adaptive_threshold: float = 0.3  # Min fill ratio for standard rows
    neural_chart_curve_threshold: int = 5  # Curves above this → CHART
    neural_fallback_to_legacy: bool = True  # Fallback to Camelot/pdfplumber if Neural fails

class AppConfig(BaseModel):
    input_dir: Optional[Path] = None
    output_dir: Optional[Path] = None
    workers: int = 4
    ocr: OCRConfig = Field(default_factory=OCRConfig)
    cleaning: CleaningConfig = Field(default_factory=CleaningConfig)
    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)

    @classmethod
    def load(cls, path: Path) -> "AppConfig":
        if not path.exists():
            return cls()
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.load(f) or {}
        return cls(**data)

    def save(self, path: Path):
        # Dump model to dict then to yaml
        data = self.model_dump(mode='json')
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)
