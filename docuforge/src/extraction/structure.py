from typing import List, Dict, Any
import pdfplumber
from collections import Counter

class StructureExtractor:
    def __init__(self):
        pass

    def extract_text_with_structure(self, page: pdfplumber.page.Page, crop_box=None) -> str:
        """
        Extracts text but tries to identify Headers based on font size.
        """
        if crop_box:
            try:
                page = page.crop(bbox=crop_box)
            except:
                pass # If crop fails, use full page

        # Analyze font sizes
        # distinct_fonts = set()
        # for char in page.chars:
        #     distinct_fonts.add((char['fontname'], char['size']))
        
        # Simple strategy: 
        # 1. Get average font size of the page (body text).
        # 2. Anything significantly larger (>1.2x) is a Header.
        
        # Extract words with higher x_tolerance to fix splitting (e.g. "t elif" -> "telif")
        # RAW PDF ANALYSIS SHOWS WIDE TRACKING. We need to INCREASE tolerance to bridge gaps.
        words = page.extract_words(
            keep_blank_chars=False, 
            extra_attrs=['size', 'fontname'],
            x_tolerance=6,  # Increased to bridge wide character spacing
            y_tolerance=3   # Tolerance for finding words on same line
        )
        if not words:
            return ""

        # Calculate mode font size (body text size)
        sizes = [w['size'] for w in words]
        if not sizes:
            return ""
        
        body_size = Counter(sizes).most_common(1)[0][0]
        header_threshold = body_size * 1.2

        # CLUSTERING: Group words into lines based on 'top' (y-axis) with tolerance
        # Simple integer rounding isn't enough for complex PDFs.
        
        lines = {} 
        # We will map "approximate y" to list of words
        
        for w in words:
            y = w['top']
            # Find an existing line close to this y
            found = False
            for existing_y in lines.keys():
                if abs(existing_y - y) < 3: # 3 pixel tolerance for line alignment
                    lines[existing_y].append(w)
                    found = True
                    break
            if not found:
                lines[y] = [w]
            
        sorted_y = sorted(lines.keys())
        
        md_lines = []
        for y in sorted_y:
            line_words = sorted(lines[y], key=lambda x: x['x0'])
            
            # Reconstruction: Join words with smart spacing
            # If distance between words is small, space. If large, tab? Markdown doesn't care.
            line_text = " ".join([w['text'] for w in line_words])
            
            # Check max size in this line for Header detection
            max_size = max([w['size'] for w in line_words])
            
            # Reconstruction with Heuristic Healing
            base_line = " ".join([w['text'] for w in line_words])
            
            # Use external Healer
            # We instantiate once (or global?), but here is fine.
            from docuforge.src.cleaning.healer import TextHealer
            # Optimization: Ideally Healer is passed in __init__, but for now we init here.
            # To detect language properly, we should ideally check the WHOLE page, but line-by-line is okay if we default to TR.
            # However, for mixed docs, per-line detection is too noisy (short text).
            # BETTER: Detect from the constructed 'base_line' context? No, too short.
            # BEST: Just default TR for now, OR if we had passed the full page text...
            # Let's trust the Healer's default ('tr') for short lines, but actually we want to be smart.
            # If we are inside a Class, we could store 'page_language'.
            # For this MVP step, let's create the Healer.
            
            healer = TextHealer()
            
            # Attempt simple language detection on the line itself if it's long enough
            # Otherwise default to 'tr' (User's context).
            # If line has "the" -> en.
            lang = healer.detect_language(base_line) 
            
            line_text = healer.heal_line(base_line, lang=lang)

            if max_size >= header_threshold:
                # Determine H1 vs H2 vs H3
                if max_size > body_size * 2:
                    prefix = "# "
                elif max_size > body_size * 1.5:
                    prefix = "## "
                else:
                    prefix = "### "
                
                md_lines.append(f"\n{prefix}{line_text}\n")
            else:
                # Optional: Detect if line ends with hyphen? (Not implemented for safety)
                md_lines.append(line_text)
                
        return "\n".join(md_lines)
