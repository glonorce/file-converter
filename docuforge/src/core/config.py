from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field
from ruamel.yaml import YAML

yaml = YAML()

class OCRConfig(BaseModel):
    enable: str = "auto"  # auto, on, off
    langs: str = "eng+tur"
    force_for_low_text_ratio: float = 0.15

class CleaningConfig(BaseModel):
    repeated_text_ratio: float = 0.6
    header_top_percent: float = 0.02 # Reduced from 0.10 to prevent cutting valid text
    footer_bottom_percent: float = 0.05 # Reduced for safety
    regex_blacklist: List[str] = [
        r"Google Translate",
        r"Translated by",
        r"Original text",
        r"Machine Translated by Google",
        r"Bu kitap",  # Too generic? No, user mentioned "gereksiz cümleler". 
        r"achine Tranşlated by Google"
    ]

class ExtractionConfig(BaseModel):
    tables_enabled: bool = True
    images_enabled: bool = False
    charts_enabled: bool = False  # OFF by default, user must enable explicitly
    table_fallback_stream: bool = True  # NEW: Try 'stream' if 'lattice' fails
    min_table_accuracy: float = 0.7  # NEW: Minimum Camelot accuracy score
    min_image_dpi: int = 200

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
