from typing import List, Dict, Any, Tuple
import pdfplumber
from collections import Counter
import unicodedata

class StructureExtractor:
    def __init__(self):
        # PERF-P1-001: Create TextHealer once instead of per-line
        from docuforge.src.cleaning.healer import TextHealer
        self._healer = TextHealer()
        
        # PERF: Cache watermark tags to avoid loading config for every line
        try:
            from docuforge.src.core.tag_manager import TagManager
            self._watermark_tags = TagManager().load_user_tags()
        except:
            self._watermark_tags = set()

    def _normalize_text(self, text: str) -> str:
        """Apply Unicode normalization to fix font encoding issues."""
        if not text:
            return text
        # NFC normalization: Composed form (é instead of e + combining accent)
        text = unicodedata.normalize('NFC', text)
        
        # Bullet point normalization: Various bullet chars → markdown dash
        # PDF fonts often encode bullets as #, 9, *, ●, ◦, ▪, etc.
        bullet_chars = {
            '•': '-',  # Standard bullet
            '●': '-',  # Black circle
            '○': '-',  # White circle  
            '◦': '-',  # White bullet
            '▪': '-',  # Black square
            '▫': '-',  # White square
            '►': '-',  # Arrow
            '▶': '-',  # Play symbol
            '◆': '-',  # Diamond
            '■': '-',  # Black square
            '□': '-',  # White square
            '✓': '-',  # Checkmark
            '✔': '-',  # Heavy checkmark
            '→': '-',  # Arrow
        }
        for bullet, replacement in bullet_chars.items():
            text = text.replace(bullet, replacement)
        
        return text

    def _extract_lines_from_chars(self, page: pdfplumber.page.Page, crop_box=None, ignore_regions=None) -> List[Dict[str, Any]]:
        """
        Manually reconstructs text lines from raw characters.
        This bypasses pdfplumber's word grouping logic completely.
        Returns list of lines, where each line is a dictionary containing text and max_font_size.
        """
        if crop_box:
            try:
                page = page.crop(bbox=crop_box)
            except Exception:
                pass
                
        chars = page.chars
        if not chars:
            return []
            
        # Sort characters by Line (Y) then Position (X)
        # Rounding 'top' to nearest integer groups characters on the same visual line
        chars = sorted(chars, key=lambda c: (round(c['top']), c['x0']))
        
        reconstructed_lines = []
        current_line_chars = []
        current_y = None
        y_tolerance = 7  # Increased from 5 to help separate overlay watermarks
        
        # dynamic gap threshold logic
        def get_gap_threshold(font_size):
            # Normal space is usually 0.2-0.3 of EM.
            # We want to merge if gap is smaller than a space.
            # Turkish broken fonts often have 0.1-0.15 gaps.
            return font_size * 0.4 
            
        for char in chars:
            char_y = round(char['top'])
            char_text = self._normalize_text(char.get('text', ''))
            char_size = char.get('size', 10)
            
            if not char_text or char_text.isspace():
                continue
                
            # Check if char is in ignored region (e.g. table)
            if ignore_regions:
                cx = (char['x0'] + char['x1']) / 2
                cy = (char['top'] + char['bottom']) / 2
                is_ignored = False
                for r_x0, r_y0, r_x1, r_y1 in ignore_regions:
                    if r_x0 <= cx <= r_x1 and r_y0 <= cy <= r_y1:
                        is_ignored = True
                        break
                if is_ignored:
                    continue
                
            if current_y is None:
                current_y = char_y
                
            # New Line Detection
            if abs(char_y - current_y) > y_tolerance:
                if current_line_chars:
                    # Filter watermark chars before processing
                    filtered_chars = self._filter_watermark_chars(current_line_chars)
                    reconstructed_lines.append(self._process_line_chars(filtered_chars))
                current_line_chars = []
                current_y = char_y
            
            current_line_chars.append(char)

        if current_line_chars:
            # Filter watermark chars before processing
            filtered_chars = self._filter_watermark_chars(current_line_chars)
            reconstructed_lines.append(self._process_line_chars(filtered_chars))
            
        return reconstructed_lines

    def _filter_watermark_chars(self, chars: List[Dict]) -> List[Dict]:
        """
        Filter out watermark characters based on font size AND tag matching.
        
        SAFE APPROACH:
        1. Find minority font chars (different size than dominant)
        2. Check if minority chars form a watermark pattern (from user tags)
        3. Only remove if pattern matches - preserves important emphasized text
        """
        if len(chars) < 5:
            return chars
        
        # Get font sizes (rounded to 1 decimal)
        sizes = [round(c.get('size', 10), 1) for c in chars]
        if not sizes:
            return chars
        
        # Find dominant font size (most common)
        from collections import Counter
        size_counts = Counter(sizes)
        dominant_size, dominant_count = size_counts.most_common(1)[0]
        
        # If no clear dominant (>60%), don't filter
        if dominant_count <= len(chars) * 0.6:
            return chars
        
        # Separate dominant and minority chars
        tolerance = dominant_size * 0.15
        minority_chars = [c for c in chars if abs(round(c.get('size', dominant_size), 1) - dominant_size) > tolerance]
        
        # If no minority chars, nothing to filter
        if not minority_chars:
            return chars
        
        # Use cached watermark tags (loaded once in __init__)
        user_tags = self._watermark_tags
        
        # If no tags defined, DON'T filter (safe default - preserves all text)
        if not user_tags:
            return chars
        
        # Build text from minority chars
        minority_text = ''.join([c.get('text', '') for c in minority_chars]).strip()
        
        # Check if minority text matches any watermark tag
        import re
        is_watermark = False
        for tag in user_tags:
            # Normalize both for comparison (remove spaces, lowercase)
            tag_normalized = re.sub(r'\s+', '', tag.lower())
            minority_normalized = re.sub(r'\s+', '', minority_text.lower())
            
            # Check if tag appears in minority text
            if tag_normalized in minority_normalized or minority_normalized in tag_normalized:
                is_watermark = True
                break
        
        # Only filter if minority matches a watermark tag
        if is_watermark:
            dominant_chars = [c for c in chars if abs(round(c.get('size', dominant_size), 1) - dominant_size) <= tolerance]
            return dominant_chars if len(dominant_chars) > len(chars) * 0.5 else chars
        
        # Not a watermark - keep all chars (including emphasized text)
        return chars

    def _process_line_chars(self, chars: List[Dict]) -> Dict[str, Any]:
        """Merges characters in a line into words based on distance."""
        if not chars:
            return {"text": "", "max_size": 0}
        
        # --- SAFE NOISE FILTER ---
        # Purpose: Remove chart axis numbers (e.g., "100   80   60") from text flow
        text_content = "".join([c.get('text', '') for c in chars]).strip()
        
        # Filter criteria:
        # 1. Line is short (<30 chars)
        # 2. More than 50% is digits
        # 3. Multiple separate parts (spaced numbers)
        digit_count = sum(c.isdigit() for c in text_content)
        
        if len(text_content) < 30 and digit_count > len(text_content) * 0.5:
            parts = text_content.split()
            if len(parts) > 2:  # Like "100 80 60"
                return {"text": "", "max_size": 0}  # Silently skip
        # --- END NOISE FILTER ---
            
        words = []
        current_word = []
        
        # Sort by X
        chars = sorted(chars, key=lambda c: c['x0'])
        
        # Calculate gaps first to determine dynamic threshold
        gaps = []
        for i in range(1, len(chars)):
            gap = chars[i]['x0'] - chars[i-1]['x1']
            size = chars[i].get('size', 10)
            if gap > 0:  # Only positive gaps
                gaps.append(gap / size)
        
        # Dynamic threshold: use the 75th percentile of gaps
        # Words are separated by larger-than-average gaps
        if gaps:
            sorted_gaps = sorted(gaps)
            idx = int(len(sorted_gaps) * 0.75)
            dynamic_threshold = sorted_gaps[idx] * 0.85  # Slightly below 75th percentile
            # Fallback bounds
            dynamic_threshold = max(0.15, min(0.35, dynamic_threshold))
        else:
            dynamic_threshold = 0.25
        
        for i, char in enumerate(chars):
            text = self._normalize_text(char.get('text', ''))
            size = char.get('size', 10)
            
            if not current_word:
                current_word.append(text)
                continue
                
            prev_char = chars[i-1]
            gap = char['x0'] - prev_char['x1']
            
            # Use dynamic threshold adjusted by font size
            threshold = size * dynamic_threshold
            
            if gap > threshold:
                words.append("".join(current_word))
                current_word = [text]
            else:
                current_word.append(text)
                
        if current_word:
            words.append("".join(current_word))
            
        full_line_text = " ".join(words)
        max_size = max([c['size'] for c in chars])
        
        return {"text": full_line_text, "max_size": max_size}

    def extract_text_with_structure(self, page: pdfplumber.page.Page, crop_box=None, ignore_regions: List[Tuple[float, float, float, float]] = None) -> str:
        """
        Extracts text identifying Headers based on font size.
        Uses raw character reconstruction.
        
        Args:
            page: PDF page
            crop_box: Optional crop box (x0, top, x1, bottom)
            ignore_regions: Optional list of (x0, top, x1, bottom) regions to exclude (e.g. tables)
        """
        lines = self._extract_lines_from_chars(page, crop_box, ignore_regions)
        if not lines:
            return ""
            
        # Calculate body font size mode
        all_sizes = [line['max_size'] for line in lines for _ in range(len(line['text']))] # Weighted by length approx
        # Better: just use max_size of lines
        line_sizes = [l['max_size'] for l in lines]
        if not line_sizes: return ""
        
        body_size = Counter(line_sizes).most_common(1)[0][0]
        header_threshold = body_size * 1.3  # Increased from 1.2 to reduce false positives
        min_size_diff = 2  # Minimum 2pt difference to be considered a heading
        max_heading_length = 150  # Headings typically aren't this long
        
        md_lines = []
        for line in lines:
            text = line['text']
            max_size = line['max_size']
            
            # Apply Healer
            text = self._healer.heal_document(text)
            
            # Heading detection with extra conditions to reduce false positives
            is_heading = (
                max_size >= header_threshold and
                max_size - body_size >= min_size_diff and  # Must be at least 2pt larger
                len(text) < max_heading_length  # Long lines aren't headings
            )
            
            if is_heading:
                 # Determine H1 vs H2 vs H3
                if max_size > body_size * 2:
                    prefix = "# "
                elif max_size > body_size * 1.5:
                    prefix = "## "
                else:
                    prefix = "### "
                md_lines.append(f"\n{prefix}{text}\n")
            else:
                md_lines.append(text)
                
        return "\n".join(md_lines)

