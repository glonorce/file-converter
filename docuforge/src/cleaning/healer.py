# Copyright (c) 2025 GÖKSEL ÖZKAN
import re
import pkg_resources
from pathlib import Path
from typing import Literal, Set
from symspellpy import SymSpell, Verbosity

class TextHealer:
    """
    Healer 4.0: Dictionary-Backed Text Repair Engine.
    Uses SymSpell frequency analysis to validate merges preventing false positives.
    """
    def __init__(self):
        # 1. Initialize SymSpell
        # max_dictionary_edit_distance=2, prefix_length=7
        self.sym_spell = SymSpell(max_dictionary_edit_distance=2, prefix_length=7)
        
        self.loaded_langs = set()
        self._load_dictionaries()
        
        # 1. Hyphen Repair
        self.re_hyphen = re.compile(r'([a-zçğıöşü]{3,})\s?-\s?([a-zçğıöşü]{3,})')
        
        # 2. Hybrid Regex Patterns (Aggressive Helpers)
        # Suffix handling: "yap ı lar" -> "yapılar". Single char separated by space is suspicious.
        # Expanded list for "Healer Pro" coverage:
        # - Plurals: lar, ler
        # - Possessives: (i)m, (i)n, (s)i, (i)miz, (i)niz, leri
        # - Cases: (y)i, (y)e, de, da, den, dan, (n)in, (n)ın, (n)un, (n)ün
        # - Copula/Pred: dır, dir, dur, dür, tır, tir, tur, tür, yım, yim, yum, yüm, sın, sin, sun, sün, yız, yiz, yuz, yüz, sınız, siniz
        # - Derivational: lık, lik, lı, li, lu, lü, sız, siz, suz, süz, cı, ci, cu, cü, çı, çi, çu, çü, daş, deş
        suffixes = [
            r'lar', r'ler',
            r'nın', r'nin', r'nun', r'nün', r'ın', r'in', r'un', r'ün',
            r'dır', r'dir', r'dur', r'dür', r'tır', r'tir', r'tur', r'tür',
            r'lık', r'lik', r'luk', r'lük',
            r'sız', r'siz', r'suz', r'süz',
            r'cı', r'ci', r'cu', r'cü', r'çı', r'çi', r'çu', r'çü',
            r'da', r'de', r'dan', r'den', r'la', r'le',
            r'mış', r'miş', r'muş', r' müş', r'dı', r'di', r'du', r'dü', r'tı', r'ti', r'tu', r'tü',
            r'sa', r'se', r'malı', r'meli', r'ken',
            r'yım', r'yim', r'yum', r'yüm', r'sın', r'sin', r'sun', r'sün',
            r'yız', r'yiz', r'yuz', r'yüz', r'sınız', r'siniz' 
        ]
        suffix_pattern = r'\b([a-zA-ZçğıöşüÇĞİÖŞÜ]{3,})\s+(' + '|'.join(suffixes) + r')\b'
        self.re_orphaned_suffix = re.compile(suffix_pattern, re.IGNORECASE)
        
        # Hard-coded Safe Merges (Particles that are definitely one word but often split)
        # "kart vizit" -> "kartvizit" (if common), "fark et" -> "farket"? (TDK says fark et is separate usually, but...)
        # "v e y a" -> "veya", "ya da" (separate).
        # "bir çok" -> "birçok" (Common error)
        # "hiç bir" -> "hiçbir"
        self.re_hard_fixes = [
            (re.compile(r'\bv\s+e\s+y\s+a\b', re.IGNORECASE), "veya"),
            (re.compile(r'\bb\s+i\s+r\s+ç\s+o\s+k\b', re.IGNORECASE), "birçok"),
            (re.compile(r'\bh\s+i\s+ç\s+b\s+i\s+r\b', re.IGNORECASE), "hiçbir"),
            (re.compile(r'\bb\s+i\s+r\s+a\s+z\b', re.IGNORECASE), "biraz"),
            (re.compile(r'\bh\s+e\s+r\s+h\s+a\s+n\s+g\s+i\b', re.IGNORECASE), "herhangi"),
        ]
        
        # Single char glue: "k e l i m e". 
        # Captures sequence of 3+ single chars spaced out.
        self.re_explosion_strict = re.compile(r'\b(?:[a-zA-ZçğıöşüÇĞİÖŞÜ]\s+){2,}[a-zA-ZçğıöşüÇĞİÖŞÜ]\b')

    def _load_dictionaries(self):
        # A. Load English (SymSpell default)
        try:
            # Try raw path relative to package first (Safer than pkg_resources)
            import symspellpy
            base_path = Path(symspellpy.__file__).parent
            dictionary_path = base_path / "frequency_dictionary_en_82_765.txt"
            
            if dictionary_path.exists():
                self.sym_spell.load_dictionary(str(dictionary_path), term_index=0, count_index=1)
                self.loaded_langs.add('en')
            else:
                print(f"Warning: English dictionary not found at {dictionary_path}")
        except Exception as e:
            print(f"Error loading English dict: {e}")

        # B. Load Turkish (Local Downloaded)
        tr_path = Path(__file__).parent / "dicts" / "tr_freq.txt"
        
        # Auto-Download if missing
        if not tr_path.exists() or tr_path.stat().st_size == 0:
            print(f"Turkish dictionary missing at {tr_path}. Downloading...")
            try:
                import urllib.request
                url = "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/tr/tr_50k.txt"
                tr_path.parent.mkdir(parents=True, exist_ok=True)
                
                with urllib.request.urlopen(url) as response:
                    data = response.read().decode('utf-8')
                    
                lines_out = []
                for line in data.splitlines():
                    parts = line.strip().split(' ')
                    if len(parts) >= 2:
                        word = parts[0]
                        count = parts[1]
                        if len(word) > 1 and word.isalpha():
                            lines_out.append(f"{word} {count}")
                            
                tr_path.write_text("\n".join(lines_out), encoding="utf-8")
                print(f"Downloaded {len(lines_out)} words.")
            except Exception as e:
                print(f"Failed to auto-download dictionary: {e}")
        
        if tr_path.exists():
            # Format is now "word count" properly
            self.sym_spell.load_dictionary(str(tr_path), term_index=0, count_index=1)
            self.loaded_langs.add('tr')

    def detect_language(self, text: str) -> Literal['tr', 'en']:
        """Simple stop-word detection"""
        stops_tr = {'ve', 'bir', 'bu', 'için', 'ile', 'de', 'da', 'ki', 'ne', 'gibi'}
        stops_en = {'the', 'and', 'of', 'to', 'in', 'is', 'it', 'you', 'that', 'for'}
        words = set(text.lower().split())
        score_tr = len(words.intersection(stops_tr))
        score_en = len(words.intersection(stops_en))
        return 'en' if score_en > score_tr else 'tr'

    def check_vowel_harmony(self, base_word: str, suffix: str) -> bool:
        """
        Simple Major Vowel Harmony Check.
        Back Vowels (a, ı, o, u) -> suffix needs (a, ı, o, u) - usually 'a' or 'u'
        Front Vowels (e, i, ö, ü) -> suffix needs (e, i, ö, ü) - usually 'e' or 'ü'
        """
        # Last vowel of base_word
        vowels_back = set("aıouAIOU")
        vowels_front = set("eiöüEİÖÜ")
        
        last_vowel_type = None # 'back' or 'front'
        for char in reversed(base_word):
            if char in vowels_back:
                last_vowel_type = 'back'
                break
            elif char in vowels_front:
                last_vowel_type = 'front'
                break
        
        if not last_vowel_type:
            return True # No vowels found? Default to permissive.
            
        # First vowel of suffix
        suffix_vowel_type = None
        for char in suffix:
            if char in vowels_back:
                suffix_vowel_type = 'back'
                break
            elif char in vowels_front:
                suffix_vowel_type = 'front'
                break
        
        if not suffix_vowel_type:
            return True # Suffix has no vowels (e.g. 'm'?)
            
        return last_vowel_type == suffix_vowel_type

    def heal_document(self, text: str) -> str:
        if not text: return ""
        lang = self.detect_language(text)
        
        # 0. Hybrid Regex Pass (Aggressive Repair)
        # orphaned suffixes
        if lang == 'tr':
            # Hard Fixes First (Common patterns)
            for pattern, replacement in self.re_hard_fixes:
                text = pattern.sub(replacement, text)
            
            # Suffixes with Vowel Harmony Check
            def suffix_repl(m):
                base = m.group(1)
                suf = m.group(2)
                if self.check_vowel_harmony(base, suf):
                    return f"{base}{suf}"
                return m.group(0) # mismatched harmony, keep separate
                
            text = self.re_orphaned_suffix.sub(suffix_repl, text)
        
        # 1. Hyphen Repair
        text = self.re_hyphen.sub(r'\1\2', text)

        # 2. Explosions
        def explosion_repl(m):
            s = m.group(0)
            merged = s.replace(" ", "")
            # Hybrid: If strict explosion regex matched, trust it more? 
            # Or just rely on dictionary. Dictionary is safer.
            if len(merged) > 2:
                 if self.sym_spell.lookup(merged, Verbosity.TOP, max_edit_distance=0):
                     return merged
            return s
            
        text = self.re_explosion_strict.sub(explosion_repl, text)
        
        # 3. Token-Based Smart Merge (Iterative Sliding Window)
        # We split by whitespace but ensure we can reconstruct.
        # Actually, simpler: Split by Space, process, join. 
        # But we must preserve newlines/punctuation.
        # Use re.split to keep delimiters.
        tokens = re.split(r'(\s+)', text)
        # tokens: ['Plan', ' ', 'B', ' ', 'de', ...]
        
        # We assume ' ' or similar are separators.
        # We iterate and check word (space) word.
        
        MAX_PASSES = 3
        curr_tokens = tokens
        
        for _ in range(MAX_PASSES):
            new_tokens = []
            i = 0
            changed = False
            
            while i < len(curr_tokens):
                t1 = curr_tokens[i]
                
                # If t1 is not a word, just append
                # Check if it has word chars
                if not re.search(r'[a-zA-ZçğıöşüÇĞİÖŞÜ]', t1):
                    new_tokens.append(t1)
                    i += 1
                    continue
                
                # Look ahead for t2 (Skip space)
                if i + 2 < len(curr_tokens):
                    sep = curr_tokens[i+1]
                    t2 = curr_tokens[i+2]
                    
                    # Ensure sep is just whitespace (no newlines if we want to be safe? or allow line wrap?)
                    # Allow space/tab. Newline might mean paragraph break.
                    if re.match(r'^[ \t]+$', sep) and re.match(r'^[a-zA-ZçğıöşüÇĞİÖŞÜ]+$', t2):
                        # Candidate Pair found: t1 + t2
                        merged = t1 + t2
                        
                        # Apply checks
                        should_merge = False
                        
                        # Special Case Validations
                        if lang == 'en':
                           if len(t1) == 1 and t1.lower() in ('a', 'i'): pass
                           elif len(t2) == 1 and t2.lower() in ('a', 'i'): pass
                           else: should_merge = True
                        elif lang == 'tr':
                            if len(t1) == 1 and t1.lower() == 'o': pass
                            else: should_merge = True
                        
                        if should_merge:
                            # Dictionary Lookup
                            if self.sym_spell.lookup(merged, Verbosity.TOP, max_edit_distance=0):
                                # Success!
                                new_tokens.append(merged)
                                i += 3 # Skip sep and t2
                                changed = True
                                continue
                
                # If no merge, append t1
                new_tokens.append(t1)
                i += 1
            
            curr_tokens = new_tokens
            if not changed:
                break
                
        return "".join(curr_tokens)
