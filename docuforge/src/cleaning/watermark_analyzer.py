"""
WatermarkAnalyzer: Frequency-based watermark detection.
Only removes patterns that appear on >60% of pages (true watermarks).
"""
import re
from pathlib import Path
from typing import List, Set
import pdfplumber
from docuforge.src.core.tag_manager import TagManager


class WatermarkAnalyzer:
    """
    Pre-scans a PDF to detect which user-defined patterns are true watermarks.
    A true watermark appears on >60% of pages.
    """
    
    WATERMARK_THRESHOLD = 0.6  # Pattern must appear on 60%+ of pages
    
    def __init__(self, pdf_path: Path):
        self.pdf_path = pdf_path
        self.total_pages = 0
        self.validated_patterns: Set[str] = set()
        
    def analyze(self) -> Set[str]:
        """
        Analyze PDF and return set of validated watermark patterns.
        Only patterns that appear on >60% of pages are considered watermarks.
        """
        user_tags = TagManager().load_user_tags()
        
        if not user_tags:
            return set()
        
        # Compile patterns for matching
        patterns = [(tag, re.compile(re.escape(tag), re.IGNORECASE)) for tag in user_tags]
        
        # Count occurrences per pattern
        pattern_page_counts = {tag: 0 for tag in user_tags}
        
        try:
            with pdfplumber.open(self.pdf_path) as pdf:
                self.total_pages = len(pdf.pages)
                
                if self.total_pages == 0:
                    return set()
                
                for page in pdf.pages:
                    try:
                        text = page.extract_text() or ""
                        
                        # Check each pattern against this page
                        for tag, pattern in patterns:
                            if pattern.search(text):
                                pattern_page_counts[tag] += 1
                    except Exception:
                        continue
        except Exception:
            return set()
        
        # Validate: Only keep patterns that appear on >60% of pages
        for tag, count in pattern_page_counts.items():
            ratio = count / self.total_pages if self.total_pages > 0 else 0
            if ratio >= self.WATERMARK_THRESHOLD:
                self.validated_patterns.add(tag)
        
        return self.validated_patterns
    
    def is_valid_watermark(self, pattern: str) -> bool:
        """Check if a pattern was validated as a true watermark."""
        return pattern.lower() in {p.lower() for p in self.validated_patterns}
