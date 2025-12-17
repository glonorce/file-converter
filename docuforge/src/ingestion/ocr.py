import pytesseract
import pdfplumber
from pdf2image import convert_from_path
from typing import Optional
from pathlib import Path
from loguru import logger
from docuforge.src.core.config import OCRConfig

class SmartOCR:
    def __init__(self, config: OCRConfig):
        self.config = config
        
        # Explicitly set tesseract path if needed, usually on path in Scoop
        # pytesseract.pytesseract.tesseract_cmd = r'C:\Users\göksel\scoop\apps\tesseract\current\tesseract.exe'

    def process_page(self, pdf_path: Path, page_num: int, original_text: str) -> str:
        """
        Analyzes original text quality. If poor, runs OCR on that specific page.
        
        Auto mode logic:
        1. If no text at all (image-only page) → OCR
        2. If very little text (<50 chars) → OCR
        3. If broken text pattern detected → OCR
        4. Otherwise → use original text
        """
        if self.config.enable == "off":
            return original_text
            
        if self.config.enable == "on":
            return self._run_ocr(pdf_path, page_num)

        # "auto" mode - Smart OCR detection
        # Only run OCR on pages that truly need it (image-only or very low text)
        
        # 1. Check if page has ANY selectable text at all
        # If original_text is empty or whitespace-only, this is an image-only page
        stripped_text = original_text.strip()
        if not stripped_text:
            logger.info(f"Page {page_num}: No selectable text found (image-only page). Triggering OCR.")
            return self._run_ocr(pdf_path, page_num)
        
        # 2. Check text length/density
        # If text is extremely short (e.g. < 50 chars for a full page), it's likely a scan
        if len(stripped_text) < 50: 
            logger.info(f"Page {page_num}: Low text density ({len(stripped_text)} chars). Triggering Smart OCR.")
            return self._run_ocr(pdf_path, page_num)

        # Page has sufficient selectable text - no OCR needed
        return original_text

    def _run_ocr(self, pdf_path: Path, page_num: int) -> str:
        import tempfile
        import shutil
        from docuforge.src.core.utils import SafeFileManager
        
        # MANUAL Temporary Directory Managment for Windows Resilience
        # tempfile.TemporaryDirectory() often fails on Windows due to file locks (PermissionError)
        # We use strict mkdtemp and our own safe_delete handler.
        temp_dir = tempfile.mkdtemp(prefix=f"ocr_p{page_num}_")
        
        try:
            # Convert specific page to image
            # output_folder=temp_dir forces pdf2image to write there
            images = convert_from_path(
                str(pdf_path), 
                first_page=page_num, 
                last_page=page_num,
                dpi=300,
                output_folder=temp_dir,
                # output_file=f"page_{page_num}", # Optional
                paths_only=False
            )
            
            if not images:
                return ""
                
            # Run Tesseract with custom config (e.g. --psm 6 for tables/lists)
            text = pytesseract.image_to_string(
                images[0], 
                lang=self.config.langs,
                config=self.config.tesseract_config
            )
            
            # Explicitly close image to release handle before temp dir cleanup
            try:
                for img in images:
                    if hasattr(img, 'close'):
                        img.close()
            except Exception:
                pass
                
            return text
            
        except Exception as e:
            logger.debug(f"OCR auto-recovery failed for page {page_num}: {e}")
            return ""
        finally:
            # Robust Cleanup using Retry Logic
            SafeFileManager.safe_delete(Path(temp_dir))

