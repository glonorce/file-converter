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


class OcrQualityDictionary:
    """Manages a dictionary for OCR quality checks (from OCRmyPDF).
    
    Validates OCR output by measuring how many words match a known dictionary.
    """
    
    def __init__(self, wordlist: set = None):
        """Construct a dictionary from a set of words."""
        if wordlist is None:
            # Default Turkish + English common words
            wordlist = {
                # Turkish common
                've', 'bir', 'bu', 'için', 'ile', 'da', 'de', 'ne', 'var', 'olan',
                'gibi', 'daha', 'çok', 'nasıl', 'neden', 'kadar', 'sonra', 'önce',
                'olarak', 'arasında', 'üzerinde', 'ise', 'ya', 'veya', 'hem', 'ancak',
                # English common
                'the', 'and', 'for', 'is', 'in', 'to', 'of', 'a', 'an', 'it',
                'that', 'this', 'with', 'from', 'have', 'are', 'was', 'were', 'be',
                # Turkish economics (subset)
                'ekonomi', 'enflasyon', 'faiz', 'bütçe', 'vergi', 'gelir', 'yatırım',
                'piyasa', 'fiyat', 'talep', 'arz', 'üretim', 'tüketim', 'büyüme',
            }
        self.dictionary = wordlist
    
    def measure_words_matched(self, ocr_text: str) -> float:
        """Check how many unique words in OCR text match dictionary.
        
        Returns:
            Ratio of matched words (0.0 to 1.0)
        """
        # Clean text: remove numbers and punctuation
        text = re.sub(r"[0-9_]+", ' ', ocr_text)
        text = re.sub(r'\W+', ' ', text)
        
        # Get unique words (min length 3)
        text_words = {w for w in text.split() if len(w) >= 3}
        
        if not text_words:
            return 0.0
        
        matches = 0
        for word in text_words:
            # Check exact match or lowercase match
            if word in self.dictionary or word.lower() in self.dictionary:
                matches += 1
        
        return matches / len(text_words) if text_words else 0.0


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
        self._setup_user_words()
        # Quality dictionary for OCR validation (OCRmyPDF technique)
        self._quality_dict = OcrQualityDictionary()
    
    def _setup_languages(self):
        """Setup language configuration."""
        # README downloads best models as 'eng.traineddata' and 'tur.traineddata'
        # So we just use the configured languages directly
        self._langs = self.config.langs
        logger.debug(f"OCR using languages: {self._langs}")
    
    def _setup_user_words(self):
        """Setup user words file for better OCR accuracy (OCRmyPDF technique)."""
        # Look for user words file in docuforge/data/
        import os
        module_dir = Path(__file__).parent.parent.parent
        self._user_words_path = module_dir / "data" / "turkish_economics.txt"
        self._user_patterns_path = module_dir / "data" / "turkish_patterns.txt"
        
        if self._user_words_path.exists():
            logger.debug(f"Using user-words: {self._user_words_path}")
        else:
            self._user_words_path = None
            logger.debug("No user-words file found")
        
        if self._user_patterns_path.exists():
            logger.debug(f"Using user-patterns: {self._user_patterns_path}")
        else:
            self._user_patterns_path = None
        
        # OCRmyPDF technique: Limit Tesseract threads to avoid CPU contention
        # When running parallel OCR, limit each Tesseract instance to fewer threads
        os.environ.setdefault('OMP_THREAD_LIMIT', '3')
        logger.debug(f"OMP_THREAD_LIMIT set to {os.environ.get('OMP_THREAD_LIMIT')}")
    
    def _downsample_large_image(self, image):
        """Downsample large images to fit Tesseract limits (OCRmyPDF technique).
        
        Tesseract has limits:
        - Max 32767 pixels in either dimension
        - Max 2^31 bytes total
        
        This prevents Tesseract errors on large scanned documents.
        """
        from PIL import Image
        from math import floor, sqrt
        
        max_size = 32767
        max_bytes = (2**31) - 1
        
        width, height = image.size
        
        # Check dimension limit
        if width <= max_size and height <= max_size:
            # Check byte limit (estimate 4 bytes per pixel for RGB)
            bpp = 4 if image.mode in ('RGB', 'RGBA') else 1
            if width * height * bpp <= max_bytes:
                return image  # No downsampling needed
        
        # Calculate scale factor
        scale_factor = 1.0
        if width > max_size or height > max_size:
            scale_factor = min(scale_factor, max_size / max(width, height))
        
        bpp = 4 if image.mode in ('RGB', 'RGBA') else 1
        if width * height * bpp > max_bytes:
            bytes_scale = sqrt(max_bytes / (width * height * bpp))
            scale_factor = min(scale_factor, bytes_scale)
        
        if scale_factor < 1.0:
            new_width = floor(width * scale_factor)
            new_height = floor(height * scale_factor)
            
            # Preserve DPI if available
            original_dpi = image.info.get('dpi', (300, 300))
            
            image = image.resize(
                (new_width, new_height),
                resample=Image.Resampling.BICUBIC
            )
            
            # Adjust DPI to match new size
            image.info['dpi'] = (
                round(original_dpi[0] * scale_factor),
                round(original_dpi[1] * scale_factor)
            )
            logger.debug(f"Downsampled image from {width}x{height} to {new_width}x{new_height}")
        
        return image

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
        """Run OCR with adaptive strategy and preprocessing fallback."""
        from PIL import ImageFilter, Image, ImageEnhance, ImageOps
        from io import BytesIO
        
        try:
            # Render page at 300 DPI (better for OCR than 400)
            images = convert_from_path(
                str(pdf_path), 
                first_page=page_num, 
                last_page=page_num,
                dpi=300
            )
            
            if images:
                ocr_image = images[0]
            else:
                # Fallback to embedded image
                ocr_image = self._extract_embedded_image(pdf_path, page_num)
                if ocr_image is None:
                    return ""
            
            # OCRmyPDF Phase 3A: Downsample large images to fit Tesseract limits
            ocr_image = self._downsample_large_image(ocr_image)
            
            # Strategy: Try simple grayscale first (Tesseract Sauvola works best on raw grayscale)
            simple_processed = self._simple_preprocess(ocr_image)
            best_text, best_score = self._ocr_with_modes(simple_processed)
            
            # If poor result, try advanced preprocessing
            if best_score < 40:
                processed = self._preprocess_image(ocr_image)
                adv_text, adv_score = self._ocr_with_modes(processed)
                if adv_score > best_score:
                    best_text = adv_text
                    best_score = adv_score
            
            # Post-process
            result = self._clean_ocr_output(best_text)
            result = self._normalize_symbols(result)
            
            if result:
                logger.debug(f"Page {page_num}: OCR extracted {len(result)} chars")
            
            return result
            
        except Exception as e:
            logger.debug(f"Page {page_num}: OCR failed: {e}")
            return ""
    
    def _ocr_with_modes(self, processed_image) -> tuple:
        """Multi-pass OCR with Sauvola thresholding and user-words for best results.
        
        Uses OCRmyPDF techniques:
        - Multiple thresholding strategies
        - User words dictionary for Turkish economics terms
        - Early exit on high confidence
        """
        best_text = ""
        best_score = 0
        
        # Build user-words and user-patterns config if available (OCRmyPDF technique)
        extra_config = ""
        if self._user_words_path and self._user_words_path.exists():
            extra_config += f" --user-words {self._user_words_path}"
        if self._user_patterns_path and self._user_patterns_path.exists():
            extra_config += f" --user-patterns {self._user_patterns_path}"
        
        # Multi-pass strategies (ordered by speed, most common first)
        strategies = [
            # Pass 1: Default (fast, good for clean text)
            f"--oem 1 --psm 6{extra_config}",
            # Pass 2: Sauvola thresholding (best for colored backgrounds)
            f"--oem 1 --psm 6 -c thresholding_method=2 -c thresholding_kfactor=0.3{extra_config}",
            # Pass 3: Aggressive Sauvola (for difficult images)
            f"--oem 1 --psm 6 -c thresholding_method=2 -c thresholding_kfactor=0.2{extra_config}",
            # Pass 4: Sparse text mode (for scattered text)
            f"--oem 1 --psm 11 -c thresholding_method=2 -c thresholding_kfactor=0.3{extra_config}",
        ]
        
        for config in strategies:
            try:
                text = pytesseract.image_to_string(
                    processed_image, 
                    lang=self._langs,
                    config=config
                )
                
                score = self._score_ocr_result(text)
                if score > best_score:
                    best_score = score
                    best_text = text
                    
                    # Early exit if excellent result
                    if score > 80:
                        break
            except:
                continue
        
        return best_text, best_score
    
    def _simple_preprocess(self, img):
        """Minimal preprocessing: Grayscale only - let Tesseract's Sauvola handle thresholding.
        
        Note: Bilateral+CLAHE was tested but damages some pages (e.g. page 17 gibberish).
        Raw grayscale with Tesseract's internal Sauvola gives best results.
        """
        import cv2
        import numpy as np
        from PIL import Image
        
        # Convert PIL to numpy
        if hasattr(img, 'mode'):
            if img.mode == 'RGBA':
                img = img.convert('RGB')
            img_np = np.array(img)
        else:
            img_np = img
        
        # Convert to grayscale
        if len(img_np.shape) == 3:
            gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_np
        
        # Scale up small images only
        h, w = gray.shape[:2]
        if w < 1000 or h < 1000:
            scale = max(2, 1500 // min(w, h))
            gray = cv2.resize(gray, (w * scale, h * scale), interpolation=cv2.INTER_LANCZOS4)
        
        # Return grayscale - Tesseract's Sauvola thresholding will handle the rest
        return Image.fromarray(gray)
    
    def _get_deskew_angle(self, img) -> float:
        """Get deskew angle using Tesseract PSM 2 (OCRmyPDF technique).
        
        This is more accurate than Hough transform as Tesseract analyzes
        actual text lines rather than arbitrary edges.
        
        Returns:
            Deskew angle in degrees (positive = counterclockwise rotation needed)
        """
        from math import pi
        import tempfile
        import os
        
        try:
            # Save image to temp file for Tesseract
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
                temp_path = f.name
                img.save(temp_path)
            
            # Use PSM 2 to get deskew angle (OCRmyPDF technique)
            output = pytesseract.image_to_osd(
                temp_path, 
                config='--psm 0',
                output_type=pytesseract.Output.DICT
            )
            
            # Get rotation angle
            rotate_angle = output.get('rotate', 0)
            
            # Clean up temp file
            os.unlink(temp_path)
            
            logger.debug(f"Tesseract deskew angle: {rotate_angle}°")
            return float(rotate_angle)
            
        except Exception as e:
            logger.debug(f"Deskew detection failed: {e}")
            return 0.0
    
    def _deskew_image(self, img):
        """Detect and correct skew using Tesseract (OCRmyPDF technique).
        
        Uses Tesseract's internal text line analysis for more accurate
        deskew than Hough transform edge detection.
        """
        from PIL import Image, ImageColor
        
        angle = self._get_deskew_angle(img)
        
        if abs(angle) < 0.5:  # Skip tiny corrections
            return img
        
        if angle == 0:
            return img
        
        # Rotate to correct the skew
        # Use BICUBIC resampling and white fill (OCRmyPDF technique)
        deskewed = img.rotate(
            angle,
            resample=Image.Resampling.BICUBIC,
            expand=True,
            fillcolor='white'
        )
        
        logger.debug(f"Applied deskew correction: {angle}°")
        return deskewed
    
    def _apply_threshold(self, img_cv):
        """Apply Otsu binarization for cleaner text."""
        import cv2
        
        if len(img_cv.shape) == 3:
            gray = cv2.cvtColor(img_cv, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_cv
        
        # Otsu's binarization
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return binary
    
    def _remove_noise(self, img_cv):
        """Remove salt-and-pepper noise using median blur."""
        import cv2
        return cv2.medianBlur(img_cv, 3)
    
    def _morphological_cleanup(self, img_cv):
        """Apply morphological operations to clean text edges."""
        import cv2
        import numpy as np
        
        kernel = np.ones((1, 1), np.uint8)
        img_cv = cv2.dilate(img_cv, kernel, iterations=1)
        img_cv = cv2.erode(img_cv, kernel, iterations=1)
        return img_cv
    
    def _preprocess_image(self, img) -> 'Image':
        """Enhanced preprocessing pipeline with deskew, Otsu, noise removal."""
        from PIL import ImageFilter, Image, ImageEnhance, ImageOps
        import cv2
        import numpy as np
        
        # 1. Convert to RGB if needed
        if img.mode == 'RGBA':
            img = img.convert('RGB')
        
        # 2. Scale up small images
        if img.width < 1000 or img.height < 1000:
            scale = max(2, 1500 // min(img.width, img.height))
            img = img.resize(
                (img.width * scale, img.height * scale),
                Image.Resampling.LANCZOS
            )
        
        # 3. Auto-rotation via OSD
        try:
            gray_for_osd = img.convert('L')
            osd = pytesseract.image_to_osd(gray_for_osd, output_type=pytesseract.Output.DICT)
            rotate_angle = osd.get('rotate', 0)
            if rotate_angle != 0:
                img = img.rotate(-rotate_angle, expand=True, fillcolor='white')
        except:
            pass
        
        # 4. NEW: Deskew (skew angle correction)
        try:
            img = self._deskew_image(img)
        except:
            pass
        
        # 5. Convert to grayscale and auto-contrast
        gray = img.convert('L')
        gray = ImageOps.autocontrast(gray, cutoff=1)
        
        # 6. Convert to OpenCV for advanced processing
        img_cv = np.array(gray)
        
        # 7. NEW: Otsu Thresholding
        binary = self._apply_threshold(img_cv)
        
        # 8. NEW: Noise removal
        denoised = self._remove_noise(binary)
        
        # 9. NEW: Morphological cleanup
        cleaned = self._morphological_cleanup(denoised)
        
        # 10. Convert back to PIL and apply UnsharpMask
        processed = Image.fromarray(cleaned)
        processed = processed.filter(ImageFilter.UnsharpMask(radius=2, percent=150))
        
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
        """Normalize arrows, symbols, and fix common OCR misreads for Turkish."""
        result = text
        
        # Fix arrow patterns
        for pattern, replacement in self.ARROW_PATTERNS:
            result = re.sub(pattern, replacement, result)
        
        # Fix common OCR misreads for Turkish
        # Down arrow often misread as 'v' in Turkish text
        turkish_fixes = [
            ('↓e', 've'),      # ve (and)
            ('↓E', 'VE'),
            ('↓a', 'va'),      # va- prefix
            ('a↓', 'av'),      # av- prefix  
            ('e↓', 'ev'),      # ev (house)
            ('↓i', 'vi'),
            ('↓ı', 'vı'),
            ('↓u', 'vu'),
            ('↓ü', 'vü'),
            ('↓o', 'vo'),
            ('↓ö', 'vö'),
            ('Ce↓', 'Cev'),    # Cevap
            ('ha↓a', 'hava'),  # hava
            ('de↓', 'dev'),    # dev-
            ('↓ar', 'var'),    # var
            ('↓er', 'ver'),    # ver
            ('se↓', 'sev'),    # sev-
            ('ya↓', 'yav'),    # yav-
            # General: isolated ↓ between letters likely means v
            (r'(\w)↓(\w)', r'\1v\2'),
        ]
        
        for pattern, replacement in turkish_fixes:
            if '\\' in pattern:  # regex pattern
                result = re.sub(pattern, replacement, result)
            else:
                result = result.replace(pattern, replacement)
        
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
            if avg_len < 2.1:  # Lowered from 2.5 for Turkish
                return ""
        
        result = '\n\n'.join(clean_lines)  # Double newline for markdown paragraphs
        
        # Final alphanumeric check
        if result:
            alnum_ratio = sum(c.isalnum() for c in result) / len(result)
            if alnum_ratio < 0.4:
                return ""
        
        # Check for gibberish patterns (charts, graphs, random text)
        if result and len(all_words) > 3:
            # Count unusual character sequences (4+ consonants in a row)
            consonant_runs = re.findall(r'[bcdfghjklmnpqrstvwxyzBCDFGHJKLMNPQRSTVWXYZ]{4,}', result)
            if len(consonant_runs) > len(all_words) * 0.15:  # Stricter: 0.2 -> 0.15
                return ""
            
            # Check for too many uppercase in unusual positions
            words_with_mid_caps = sum(1 for w in all_words if re.search(r'[a-z][A-Z]', w))
            if words_with_mid_caps > len(all_words) * 0.25:  # Stricter: 0.3 -> 0.25
                return ""
            
            # NEW: Check for chart/graph gibberish (too many ALL-CAPS short words)
            short_caps = sum(1 for w in all_words if len(w) <= 3 and w.isupper())
            if short_caps > len(all_words) * 0.3:
                return ""
            
            # NEW: Check for excessive single/double character words (chart labels)
            very_short = sum(1 for w in all_words if len(re.sub(r'[^\w]', '', w)) <= 2)
            if len(all_words) > 15 and very_short > len(all_words) * 0.5:
                return ""
            
            # NEW: Check for repeated random patterns (e.g., "e e e", "a a a")
            unique_words = set(w.lower() for w in all_words)
            if len(all_words) > 20 and len(unique_words) < len(all_words) * 0.3:
                return ""
            
            # Check for common Turkish/English words - if none found, likely garbage
            common_words = {
                've', 'bir', 'bu', 'için', 'ile', 'da', 'de', 'ne', 'var', 'olan',
                'the', 'and', 'for', 'is', 'in', 'to', 'of', 'a', 'an', 'it',
                'gibi', 'daha', 'çok', 'nasıl', 'neden', 'kadar', 'sonra', 'önce',
                'olarak', 'arasında', 'üzerinde', 'altında', 'hakkında', 'göre',
                'olarak', 'ise', 'ya', 'veya', 'hem', 'ancak', 'fakat', 'çünkü',
                'that', 'this', 'with', 'from', 'have', 'are', 'was', 'were', 'be'
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
