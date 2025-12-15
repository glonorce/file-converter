from typing import List, Dict, Any
import pdfplumber
from collections import Counter
import unicodedata

class StructureExtractor:
    def __init__(self):
        # PERF-P1-001: Create TextHealer once instead of per-line
        from docuforge.src.cleaning.healer import TextHealer
        self._healer = TextHealer()

    def _normalize_text(self, text: str) -> str:
        """Apply Unicode normalization to fix font encoding issues."""
        if not text:
            return text
        # NFC normalization: Composed form (é instead of e + combining accent)
        return unicodedata.normalize('NFC', text)

    def _extract_lines_from_chars(self, page: pdfplumber.page.Page, crop_box=None) -> List[Dict[str, Any]]:
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
        y_tolerance = 3
        
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
                
            if current_y is None:
                current_y = char_y
                
            # New Line Detection
            if abs(char_y - current_y) > y_tolerance:
                if current_line_chars:
                    reconstructed_lines.append(self._process_line_chars(current_line_chars))
                current_line_chars = []
                current_y = char_y
            
            current_line_chars.append(char)

        if current_line_chars:
            reconstructed_lines.append(self._process_line_chars(current_line_chars))
            
        return reconstructed_lines

    def _process_line_chars(self, chars: List[Dict]) -> Dict[str, Any]:
        """Merges characters in a line into words based on distance."""
        if not chars:
            return {"text": "", "max_size": 0}
            
        words = []
        current_word = []
        
        # Sort by X
        chars = sorted(chars, key=lambda c: c['x0'])
        
        for i, char in enumerate(chars):
            text = self._normalize_text(char.get('text', ''))
            size = char.get('size', 10)
            
            if not current_word:
                current_word.append(text)
                continue
                
            prev_char = chars[i-1]
            gap = char['x0'] - prev_char['x1']
            
            # Threshold: If gap is small, it's the same word.
            # If gap is large, insert space.
            # 0.35 was too aggressive (caused "Güç,VizyonveSistem")
            # 0.10 was too weak (caused "G ü ç")
            # 0.20 is the sweet spot for Turkish kerning.
            threshold = size * 0.20 
            
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

    def extract_text_with_structure(self, page: pdfplumber.page.Page, crop_box=None) -> str:
        """
        Extracts text identifying Headers based on font size.
        Uses raw character reconstruction.
        """
        lines = self._extract_lines_from_chars(page, crop_box)
        if not lines:
            return ""
            
        # Calculate body font size mode
        all_sizes = [line['max_size'] for line in lines for _ in range(len(line['text']))] # Weighted by length approx
        # Better: just use max_size of lines
        line_sizes = [l['max_size'] for l in lines]
        if not line_sizes: return ""
        
        body_size = Counter(line_sizes).most_common(1)[0][0]
        header_threshold = body_size * 1.2
        
        md_lines = []
        for line in lines:
            text = line['text']
            max_size = line['max_size']
            
            # Apply Healer
            text = self._healer.heal_document(text)
            
            if max_size >= header_threshold:
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

