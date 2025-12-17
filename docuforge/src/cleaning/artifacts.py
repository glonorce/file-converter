import re
from typing import List, Set, Optional
from docuforge.src.core.config import CleaningConfig


class TextCleaner:
    def __init__(self, config: CleaningConfig, validated_watermarks: Optional[Set[str]] = None):
        """
        Initialize TextCleaner.
        
        Args:
            config: Cleaning configuration
            validated_watermarks: Set of patterns validated by WatermarkAnalyzer.
                                  Only these patterns will be removed.
                                  If None, no watermark removal is performed.
        """
        self.config = config
        
        # Only use validated watermarks (patterns confirmed to appear on >60% of pages)
        if validated_watermarks:
            self.user_patterns = [re.compile(re.escape(p), re.IGNORECASE) for p in validated_watermarks]
        else:
            self.user_patterns = []

    def clean_text(self, text: str) -> str:
        """
        Applies user-defined watermark removal.
        Smart removal: Only removes matched text if <80% of line, removes entire line if >80%.
        """
        if not text:
            return ""
        
        # Apply user tag removal (smart)
        for pattern in self.user_patterns:
            text = self._smart_remove_pattern(text, pattern)
            
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            
            # Fix bullet point encoding issues
            line = self._fix_bullet_encoding(line)
            
            # Skip empty lines that result from removal
            if line.strip():
                cleaned_lines.append(line)
            
        result = "\n".join(cleaned_lines)
        
        # Remove trailing standalone page numbers (common in footers)
        result = re.sub(r'(?:^|\n)\s*\d+\s*$', '', result)
        
        return result
    
    def _smart_remove_pattern(self, text: str, pattern: re.Pattern) -> str:
        """
        Smart pattern removal:
        - If pattern is the entire line content (>80%), remove the line
        - Otherwise, just remove the matched text
        """
        lines = text.split('\n')
        result_lines = []
        
        for line in lines:
            match = pattern.search(line)
            if match:
                matched_text = match.group()
                line_content = line.strip()
                
                # If matched text is >80% of line, remove entire line
                if len(line_content) > 0 and len(matched_text) / len(line_content) > 0.8:
                    continue  # Skip this line entirely
                else:
                    # Just remove the matched text
                    line = pattern.sub('', line)
                    # Clean up extra spaces
                    line = re.sub(r'\s{2,}', ' ', line)
            
            result_lines.append(line)
        
        return '\n'.join(result_lines)
    
    def _fix_bullet_encoding(self, line: str) -> str:
        """
        Fix PDF font encoding issues where bullets become # or 9.
        Only affects single chars at line start followed by space and text.
        """
        stripped = line.lstrip()
        if not stripped:
            return line
        
        # Pattern: line starts with # or 9, then space, then actual content
        if len(stripped) > 2 and stripped[0] in '#9' and stripped[1] == ' ':
            rest = stripped[2:].lstrip()
            if rest and (rest[0].isupper() or rest[0] in 'İĞÜÇÖŞ'):
                leading_space = line[:len(line) - len(stripped)]
                return leading_space + '-' + stripped[1:]
        
        return line
