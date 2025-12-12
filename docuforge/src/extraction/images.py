import fitz  # PyMuPDF
from pathlib import Path
from typing import List, Tuple
from loguru import logger
from docuforge.src.core.config import ExtractionConfig

class ImageExtractor:
    def __init__(self, config: ExtractionConfig, output_dir: Path):
        self.config = config
        self.images_dir = output_dir / "images"
        # Directory is created lazily in extract_images if needed

    def extract_images(self, pdf_path: Path, page_num: int) -> List[str]:
        """
        Extracts images from a page and saves them to disk.
        Returns a list of Markdown image links.
        """
        if not self.config.images_enabled:
            return []

        md_links = []
        try:
            doc = fitz.open(pdf_path)
            # fitz is 0-indexed for pages
            page_idx = page_num - 1 
            
            if page_idx >= len(doc):
                return []

            page = doc[page_idx]
            image_list = page.get_images(full=True)

            for img_index, img in enumerate(image_list):
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]
                
                # Filter by size if possible (simple byte check as proxy)
                if len(image_bytes) < 2048: # Skip tiny icons < 2KB
                    continue

                # Lazily create directory if it doesn't exist
                if not self.images_dir.exists():
                    self.images_dir.mkdir(parents=True, exist_ok=True)

                filename = f"img_p{page_num}_{img_index + 1}.{image_ext}"
                filepath = self.images_dir / filename
                
                with open(filepath, "wb") as f:
                    f.write(image_bytes)
                
                # Relative path for Markdown
                rel_path = f"images/{filename}"
                md_links.append(f"![Image]({rel_path})")

            doc.close()
        except Exception as e:
            logger.warning(f"Image extraction failed for {pdf_path} page {page_num}: {e}")
        
        return md_links
