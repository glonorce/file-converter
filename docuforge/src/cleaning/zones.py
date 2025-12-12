from typing import List, Tuple
import pdfplumber
from docuforge.src.core.config import CleaningConfig

class ZoneCleaner:
    def __init__(self, config: CleaningConfig):
        self.config = config

    def get_crop_box(self, page: pdfplumber.page.Page) -> Tuple[float, float, float, float]:
        """
        Calculates the crop box to exclude header and footer.
        Returns (x0, top, x1, bottom) compatible with pdfplumber cropping.
        """
        width = page.width
        height = page.height
        
        # Calculate cutoffs
        top_cutoff = height * self.config.header_top_percent
        bottom_cutoff = height * (1 - self.config.footer_bottom_percent)
        
        # (x0, top, x1, bottom)
        # We start from top_cutoff and go to bottom_cutoff
        return (0, top_cutoff, width, bottom_cutoff)

    def filter_text_by_zone(self, page: pdfplumber.page.Page) -> str:
        """
        Extracts text only from the safe zone.
        """
        crop_box = self.get_crop_box(page)
        # pdfplumber crop args: (x0, top, x1, bottom) 
        # CAUTION: pdfplumber coordinate system can be tricky (top-down vs bottom-up).
        # pdfplumber uses (x0, top, x1, bottom) where (0,0) is top-left usually.
        
        try:
            cropped = page.crop(bbox=crop_box)
            return cropped.extract_text() or ""
        except Exception as e:
            # Fallback if cropping fails (e.g. empty page)
            return ""
