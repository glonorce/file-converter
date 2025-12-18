"""
Enhanced Tesseract OCR Engine
- Parallel processing for multi-page PDFs
- Adaptive PSM strategy (tries multiple modes, picks best)
- Smart preprocessing based on image characteristics
- Better language models (tur_best, eng_best)
- Symbol/arrow detection and normalization
- Image table detection hints
"""
import pytesseract
import pdfplumber
from pdf2image import convert_from_path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List, Tuple
from pathlib import Path
from loguru import logger
from docuforge.src.core.config import OCRConfig
import re


class SmartOCR:
    """Enhanced OCR engine with adaptive strategies."""
    
    # PSM modes to try in adaptive mode
    PSM_MODES = [6, 3, 4, 11]  # Block, Auto, Single column, Sparse
    
    # Arrow patterns to normalize
    ARROW_PATTERNS = [
        (r'[-=]+>', '→'),
        (r'<[-=]+', '←'),
        (r'\^+', '↑'),
        (r'v+', '↓'),
        (r'->+', '→'),
        (r'<-+', '←'),
    ]
    
    def __init__(self, config: OCRConfig):
        self.config = config
        # Use best models if available
        self._setup_languages()
    
    def _setup_languages(self):
        """Setup language configuration."""
        # README downloads best models as 'eng.traineddata' and 'tur.traineddata'
        # So we just use the configured languages directly
        self._langs = self.config.langs
        logger.debug(f"OCR using languages: {self._langs}")

    def process_page(self, pdf_path: Path, page_num: int, original_text: str) -> str:
        """
        Analyzes original text quality. If poor, runs OCR on that specific page.
        """
        if self.config.enable == "off":
            return original_text
            
        if self.config.enable == "on":
            return self._run_ocr(pdf_path, page_num)

        # "auto" mode - Smart OCR detection
        stripped_text = original_text.strip()
        
        # 1. Image-only page
        if not stripped_text:
            return self._run_ocr(pdf_path, page_num)
        
        # 2. Low text density
        if len(stripped_text) < 50:
            return self._run_ocr(pdf_path, page_num)
        
        # 3. Merged words (no spaces)
        if len(stripped_text) >= 50:
            space_ratio = stripped_text.count(' ') / len(stripped_text)
            if space_ratio < 0.05:
                return self._run_ocr(pdf_path, page_num)

        return original_text
    
    def process_pages_parallel(self, pdf_path: Path, page_nums: List[int], original_texts: List[str]) -> List[str]:
        """Process multiple pages in parallel for better performance."""
        results = [''] * len(page_nums)
        
        # First pass: identify which pages need OCR
        ocr_tasks = []
        for i, (page_num, original_text) in enumerate(zip(page_nums, original_texts)):
            if self._needs_ocr(original_text):
                ocr_tasks.append((i, page_num))
            else:
                results[i] = original_text
        
        if not ocr_tasks:
            return results
        
        # Parallel OCR processing (max 4 threads)
        with ThreadPoolExecutor(max_workers=min(4, len(ocr_tasks))) as executor:
            future_to_idx = {
                executor.submit(self._run_ocr, pdf_path, page_num): idx
                for idx, page_num in ocr_tasks
            }
            
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    logger.debug(f"Parallel OCR failed: {e}")
                    results[idx] = ''
        
        return results
    
    def _needs_ocr(self, text: str) -> bool:
        """Check if text needs OCR processing."""
        if self.config.enable == "off":
            return False
        if self.config.enable == "on":
            return True
            
        stripped = text.strip()
        if not stripped or len(stripped) < 50:
            return True
        if len(stripped) >= 50:
            space_ratio = stripped.count(' ') / len(stripped)
            if space_ratio < 0.05:
                return True
        return False

    def _run_ocr(self, pdf_path: Path, page_num: int) -> str:
        """Run OCR with adaptive strategy."""
        from PIL import ImageFilter, Image, ImageEnhance, ImageOps
        from io import BytesIO
        
        try:
            # Get image (embedded or rendered)
            ocr_image = self._extract_embedded_image(pdf_path, page_num)
            
            if ocr_image is None:
                images = convert_from_path(
                    str(pdf_path), 
                    first_page=page_num, 
                    last_page=page_num,
                    dpi=400
                )
                if not images:
                    return ""
                ocr_image = images[0]
            
            # Preprocess
            processed = self._preprocess_image(ocr_image)
            
            # Adaptive OCR - try multiple PSM modes
            best_text = ""
            best_score = 0
            
            for psm in self.PSM_MODES:
                try:
                    config = f"--psm {psm}"
                    text = pytesseract.image_to_string(
                        processed, 
                        lang=self._langs,
                        config=config
                    )
                    
                    # Score by word count and quality
                    score = self._score_ocr_result(text)
                    if score > best_score:
                        best_score = score
                        best_text = text
                        
                        # Early exit if good enough
                        if score > 50:
                            break
                except:
                    continue
            
            # Post-process
            result = self._clean_ocr_output(best_text)
            result = self._normalize_symbols(result)
            
            if result:
                logger.debug(f"Page {page_num}: OCR extracted {len(result)} chars")
            
            return result
            
        except Exception as e:
            logger.debug(f"Page {page_num}: OCR failed: {e}")
            return ""
    
    def _preprocess_image(self, img) -> 'Image':
        """Smart preprocessing based on image characteristics."""
        from PIL import ImageFilter, Image, ImageEnhance, ImageOps
        
        # Convert to RGB if needed
        if img.mode == 'RGBA':
            img = img.convert('RGB')
        
        # Scale up small images
        if img.width < 1000 or img.height < 1000:
            scale = max(2, 1500 // min(img.width, img.height))
            img = img.resize(
                (img.width * scale, img.height * scale),
                Image.Resampling.LANCZOS
            )
        
        # Try to detect and fix rotation
        try:
            gray_for_osd = img.convert('L')
            osd = pytesseract.image_to_osd(gray_for_osd, output_type=pytesseract.Output.DICT)
            rotate_angle = osd.get('rotate', 0)
            if rotate_angle != 0:
                img = img.rotate(-rotate_angle, expand=True, fillcolor='white')
        except:
            pass  # OSD may fail on some images
        
        # Convert to grayscale
        gray = img.convert('L')
        
        # Auto-contrast for low contrast images
        gray = ImageOps.autocontrast(gray, cutoff=1)
        
        # Apply UnsharpMask for edge enhancement
        processed = gray.filter(ImageFilter.UnsharpMask(radius=2, percent=150))
        
        return processed
    
    def _score_ocr_result(self, text: str) -> int:
        """Score OCR result quality (higher = better)."""
        if not text:
            return 0
        
        words = text.split()
        if not words:
            return 0
        
        # Base score: word count
        score = len(words)
        
        # Bonus for longer words (real words)
        avg_len = sum(len(w) for w in words) / len(words)
        if avg_len > 4:
            score += 10
        
        # Penalty for too many short words (noise)
        short_words = sum(1 for w in words if len(w) <= 2)
        if short_words > len(words) * 0.5:
            score -= 20
        
        # Penalty for low alphanumeric ratio
        alnum = sum(c.isalnum() for c in text)
        if len(text) > 0 and alnum / len(text) < 0.5:
            score -= 15
        
        return max(0, score)
    
    def _normalize_symbols(self, text: str) -> str:
        """Normalize arrows and symbols."""
        result = text
        for pattern, replacement in self.ARROW_PATTERNS:
            result = re.sub(pattern, replacement, result)
        return result
    
    def _clean_ocr_output(self, text: str) -> str:
        """Clean OCR output and filter garbage results while preserving line structure."""
        if not text:
            return ""
        
        # Remove noise patterns
        noise_patterns = [
            r'[—–\-]{2,}',
            r'[\.]{3,}',
            r'[\'\"\'\"]{2,}',
            r'[\/\\]{2,}',
            r'\s*[<>{}|]\s*',
            r'[=]{2,}',
            r'[\*]{2,}',
            r'[_]{2,}',
        ]
        
        cleaned = text
        for pattern in noise_patterns:
            cleaned = re.sub(pattern, ' ', cleaned)
        
        # Process line by line to preserve structure
        valid_single_chars = set('0123456789abcdeişığüöçABCDEİŞIĞÜÖÇ')
        clean_lines = []
        all_words = []
        
        for line in cleaned.split('\n'):
            words = line.split()
            meaningful_words = []
            
            for word in words:
                clean_word = re.sub(r'[^\w]', '', word)
                if len(clean_word) == 0:
                    continue
                elif len(clean_word) == 1:
                    if clean_word in valid_single_chars:
                        meaningful_words.append(word)
                else:
                    meaningful_words.append(word)
            
            if meaningful_words:
                clean_lines.append(' '.join(meaningful_words))
                all_words.extend(meaningful_words)
        
        # Check for garbage (too many short words across all lines)
        if len(all_words) > 10:
            avg_len = sum(len(re.sub(r'[^\w]', '', w)) for w in all_words) / len(all_words)
            if avg_len < 2.5:
                return ""
        
        result = '\n\n'.join(clean_lines)  # Double newline for markdown paragraphs
        
        # Final alphanumeric check
        if result:
            alnum_ratio = sum(c.isalnum() for c in result) / len(result)
            if alnum_ratio < 0.4:
                return ""
        
        # Check for gibberish patterns (reversed text, random chars)
        if result and len(all_words) > 3:
            # Count unusual character sequences (4+ consonants in a row)
            consonant_runs = re.findall(r'[bcdfghjklmnpqrstvwxyzBCDFGHJKLMNPQRSTVWXYZ]{4,}', result)
            if len(consonant_runs) > len(all_words) * 0.2:
                return ""
            
            # Check for too many uppercase in unusual positions
            words_with_mid_caps = sum(1 for w in all_words if re.search(r'[a-z][A-Z]', w))
            if words_with_mid_caps > len(all_words) * 0.3:
                return ""
            
            # Check for common Turkish/English words - if none found, likely garbage
            common_words = {
                've', 'bir', 'bu', 'için', 'ile', 'da', 'de', 'ne', 'var', 'olan',
                'the', 'and', 'for', 'is', 'in', 'to', 'of', 'a', 'an', 'it',
                'gibi', 'daha', 'çok', 'nasıl', 'neden', 'kadar', 'sonra', 'önce',
                'olarak', 'arasında', 'üzerinde', 'altında', 'hakkında', 'göre'
            }
            lower_words = [w.lower() for w in all_words if len(w) > 1]
            common_found = sum(1 for w in lower_words if w in common_words)
            
            # If text has many words but no common words, likely garbage
            if len(all_words) > 8 and common_found == 0:
                return ""
        
        return result.strip()
    
    def _extract_embedded_image(self, pdf_path: Path, page_num: int):
        """Extract embedded image from PDF page."""
        from PIL import Image
        from io import BytesIO
        
        try:
            with pdfplumber.open(pdf_path) as pdf:
                if page_num > len(pdf.pages):
                    return None
                page = pdf.pages[page_num - 1]
                
                if not page.images:
                    return None
                
                largest = max(page.images, key=lambda x: x.get('width', 0) * x.get('height', 0))
                stream = largest.get('stream')
                
                if stream:
                    data = stream.get_data()
                    return Image.open(BytesIO(data))
        except:
            pass
        return None
    
    def detect_table_in_image(self, img) -> bool:
        """Detect if image contains a table (grid lines)."""
        from PIL import ImageFilter
        import numpy as np
        
        try:
            # Convert to grayscale and detect edges
            gray = img.convert('L')
            edges = gray.filter(ImageFilter.FIND_EDGES)
            
            # Convert to numpy for analysis
            arr = np.array(edges)
            
            # Look for horizontal and vertical lines
            # Tables have many regular edges
            edge_ratio = np.sum(arr > 128) / arr.size
            
            # If more than 5% edges, likely has structure
            return edge_ratio > 0.05
        except:
            return False
