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
        """
        if self.config.enable == "off":
            return original_text
            
        if self.config.enable == "on":
            return self._run_ocr(pdf_path, page_num)

        # "auto" mode logic
        # 1. Check text length/density
        msg_density = len(original_text.strip())
        
        # If text is extremely short (e.g. < 50 chars for a full page), it's likely a scan or corrupted
        if msg_density < 50: 
            logger.info(f"Page {page_num}: Low text density ({msg_density} chars). Triggering Smart OCR.")
            return self._run_ocr(pdf_path, page_num)
            
        # 2. Check for "gidble garble" (optional advanced heuristic, skipped for speed)
        
        return original_text

    def _run_ocr(self, pdf_path: Path, page_num: int) -> str:
        import tempfile
        import shutil
        
        # Create a unique temp directory for this page's OCR operation
        with tempfile.TemporaryDirectory() as temp_dir:
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
                    
                # Run Tesseract
                text = pytesseract.image_to_string(images[0], lang=self.config.langs)
                
                # Explicitly close image to release handle before temp dir cleanup
                try:
                    for img in images:
                        if hasattr(img, 'close'):
                            img.close()
                except:
                    pass
                    
                return text
                
            except Exception as e:
                # logger.error(f"OCR Failed for page {page_num}: {e}") # Reduce noise
                return ""
            # Context manager handles cleanup of temp_dir

