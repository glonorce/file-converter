import re
from typing import List
from docuforge.src.core.config import CleaningConfig

class TextCleaner:
    def __init__(self, config: CleaningConfig):
        self.config = config
        self.compiled_regex = [re.compile(p, re.IGNORECASE) for p in self.config.regex_blacklist]

    def clean_text(self, text: str) -> str:
        """
        Applies regex filters to remove known garbage patterns.
        """
        if not text:
            return ""
            
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            if self._is_garbage(line):
                continue
            cleaned_lines.append(line)
            
        result = "\n".join(cleaned_lines)
        
        # Remove trailing standalone page numbers (common in footers)
        # Matches newline followed by digits and end of string
        result = re.sub(r'(?:^|\n)\s*\d+\s*$', '', result)
        
        return result

    def _is_garbage(self, line: str) -> bool:
        """
        Check if a line matches any blacklist regex.
        """
        for pattern in self.compiled_regex:
            if pattern.search(line):
                return True
        return False
