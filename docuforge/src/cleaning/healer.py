# Copyright (c) 2025 GÖKSEL ÖZKAN
# This software is released under the MIT License.
# https://github.com/glonorce/file-converter

import re
from typing import List, Literal

class TextHealer:
    """
    Advanced linguistic repair module with Language Awareness.
    Auto-detects language (TR/EN) and applies specific healing rules to prevent
    over-correction (e.g. merging 'a book' -> 'abook' in English).
    """
    def __init__(self):
        # --- Language Detection ---
        # Expanded stop words for better robust detection
        self.stops_tr = {'ve', 'bir', 'bu', 'için', 'ile', 'de', 'da', 'ki', 'ne', 'gibi', 'her', 'çok', 'en', 'daha'}
        self.stops_en = {'the', 'and', 'of', 'to', 'in', 'is', 'it', 'you', 'that', 'for', 'are', 'on', 'with', 'as', 'at'}
        
        # --- TURKISH RULES (Aggressive) ---
        # 1. Broken Conjunctions: "v e" -> "ve", "d e" -> "de", "k i" -> "ki"
        self.re_tr_conjunctions = re.compile(r'\b([vVdDkK]) ([eEiİ])\b')
        
        # 2. Heuristic Merge (Consonants + Word)
        # Excludes 'o' (pronoun). Merges "b ulunan" -> "bulunan".
        # Excludes 'a'? In TR, 'a' is not a word (except dialect/slang "a" exclamation). 
        # Merging 'a' + 'cil' -> 'acil' is good.
        # But 'o' + 'kul' -> 'okul'? 'o' is dangerous.
        self.re_tr_merge_general = re.compile(r'\b([a-np-zA-NP-ZçğıöşüÇĞİÖŞÜ]) ([a-zçğıöşü]{2,})\b')
        
        # 3. 'O' Exception: Merge if followed by specific stems (l, k, m, n, r, t) -> ol, ok, om, on, or, ot
        self.re_tr_merge_o = re.compile(r'\b([oO]) ([lLmMkKzsSnNrR][a-zçğıöşü]{1,})\b')
        
        # 4. Explicit Particle Fixes (High Priority)
        # Prevents "e nönemlileri", "b u", "d ave", "a z"
        # We manually map frequent broken particles.
        # \b(start) (rest)\b checks.
        # "e n..." -> "en..."
        # "b u..." -> "bu..."
        # "d a..." -> "da..."
        # "n e..." -> "ne..."
        # "ş u..." -> "şu..."
        # "a z..." -> "az..."
        # "y ani..." -> "yani..."
        # "i le..." -> "ile..." (Rare but possible)
        # We catch these specifically.
        # Regex: Single specific char + space + any word chars (1 ot more).
        # This covers "b u" (bu) and "b uyazıyı" (buyazıyı).
        self.re_tr_particles = re.compile(r'\b([bBdDnNşŞaAyYiIgGkK]) ([a-zçğıöşü]+)\b')
        # Note: This is VERY aggressive for the specified letters.
        # b -> bu, bir, b...
        # d -> de, da...
        # n -> ne...
        # ş -> şu...
        # a -> az...
        # y -> ya...
        # i -> ile... (i le)
        # k -> ki...
        # But wait, "b a" -> "ba" (baba?). "b a" is not a word. "b" + "ab..." -> "bab...".
        # This is safe because "b" alone is never valid in TR text (except list item 'b)', handled by \b checks hopefully).
        
        # "e" + "n..." needs separate handling because "e" is common.
        self.re_tr_particle_e = re.compile(r'\b([eE]) ([nN][a-zçğıöşü]*)\b') # Catch "e n", "e n...", "e ni..."

        # 5. Hyphen Healing (Text-wrapping fixes)
        # "prob- lem", "prob - lem", "prob-lem" -> "problem"
        # Be careful of "High-Level".
        # Safe heuristic: strictly lowercase word + hyphen + space + lowercase word
        self.re_hyphen = re.compile(r'([a-zçğıöşü]{3,})\s?-\s?([a-zçğıöşü]{3,})')

        # --- ENGLISH RULES (Conservative) ---
        # 1. Specific broken starts common in English PDF extraction
        # "t he" -> "the", "w ith" -> "with", "t hat" -> "that", "w ill" -> "will"
        # We can use a general merge BUT must strictly exclude 'a' and 'I'.
        # Exclude: a, A, i, I.
        # Regex: Single char (not A/a/I/i) + space + word(2+)
        self.re_en_merge = re.compile(r'\b([b-hj-np-zB-HJ-NP-Z]) ([a-z]{2,})\b')  # Excludes A, I. Included: B..H, J..N, P..Z

        # 2. "W Is" problem? "W h i c h" -> "Which". (Wide caps handled separately)

        # --- SHARED RULES ---
        # Wide Caps: "T I T L E" -> "TITLE" (Context agnostic mostly, but risk of "A I" -> "AI" vs "A I" (two vars))
        # We'll allow 3+ caps merge.
        self.re_wide_caps = re.compile(r'\b([A-ZÇĞİÖŞÜ])\s+([A-ZÇĞİÖŞÜ])\s+([A-ZÇĞİÖŞÜ])\b')

    def detect_language(self, text: str) -> Literal['tr', 'en']:
        """
        Stop-word based detection.
        Robust, fast, and sufficient for layout/spacing contexts.
        """
        if not text:
            return 'tr'
            
        words = set(text.lower().split())
        score_tr = len(words.intersection(self.stops_tr))
        score_en = len(words.intersection(self.stops_en))
        
        # Bias towards EN if scores are equal? Or TR?
        # User is Turkish context. Bias TR.
        if score_en > score_tr:
            return 'en'
        return 'tr'

    def heal_line(self, text: str, lang: str = 'tr') -> str:
        if not text or len(text) < 3:
            return text
            
        if lang == 'tr':
            return self._heal_tr(text)
        else:
            return self._heal_en(text)

    def _heal_tr(self, text: str) -> str:
        # Run multiple passes for deeply broken text
        prev_text = ""
        passes = 0
        max_passes = 5
        
        while text != prev_text and passes < max_passes:
            prev_text = text
            passes += 1
            
            # 0. Clean multi-space sequences between single letters (deeply broken text)
            # "d ü ş ü n c e" -> "düşünce"
            # Pattern: letter + space + letter + space + letter... (3+ chars)
            text = re.sub(r'\b([a-zA-ZçğıöşüÇĞİÖŞÜ]) ([a-zA-ZçğıöşüÇĞİÖŞÜ]) ([a-zA-ZçğıöşüÇĞİÖŞÜ])\b', r'\1\2\3', text)
            
            # 1. Conjunctions (v e)
            text = self.re_tr_conjunctions.sub(r'\1\2', text)
            
            # 2. Explicit Particles (b u, d a, n e...)
            text = self.re_tr_particles.sub(r'\1\2', text)
            text = self.re_tr_particle_e.sub(r'\1\2', text)
            
            # 3. Special 'O'
            text = self.re_tr_merge_o.sub(r'\1\2', text)
            
            # 4. Hyphens
            text = self.re_hyphen.sub(r'\1\2', text)
            
            # 5. General Merge (Cleanup for anything missed, e.g. other letters)
            text = self.re_tr_merge_general.sub(r'\1\2', text)
            
            # 6. Common broken Turkish words (font encoding issues)
            # These are high-frequency patterns from corrupted PDFs
            broken_patterns = [
                # (broken, fixed)
                (r'şı', 'şı'),  # normalize
                (r'ğı', 'ğı'),  # normalize
                (r'\bba ar', 'başar'),  # başarı, başarılı
                (r'\bgiri im', 'girişim'),  # girişim, girişimci
                (r'\bdü ün', 'düşün'),  # düşünce, düşündü
                (r'\bile i', 'işleş'),  # işleyiş
                (r'\byap lar', 'yapılar'),
                (r'\bsistem n', 'sistemin'),
                (r'\bgörünme yen', 'görünmeyen'),
                (r'\bmekanizma lar', 'mekanizmalar'),
                (r'\bba l', 'başl'),  # başlı, başlangıç
                (r'\bele tir', 'eleştir'),  # eleştiri
                (r'\ban lay', 'anlay'),  # anlayış
                (r'\bkaz nd', 'kazandı'),
                (r'\bgerçekle ti', 'gerçekleşti'),
                (r'ışş', 'ış'),  # cleanup double ş artifacts
                (r'ığı', 'ığı'),  # normalize
                (r'şğ', 'ş'),  # artifact cleanup
            ]
            for pattern, replacement in broken_patterns:
                text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
        return text

    def _heal_en(self, text: str) -> str:
        # 1. Conservative Merge (No 'a', 'I')
        # Fixes "t he" -> "the", "s he" -> "she"
        text = self.re_en_merge.sub(r'\1\2', text)
        return text

    def heal_document(self, text: str) -> str:
        """Run on full text block with auto-detection"""
        lang = self.detect_language(text)
        lines = text.split('\n')
        # Process lines with correct language context
        return "\n".join([self.heal_line(l, lang) for l in lines])
