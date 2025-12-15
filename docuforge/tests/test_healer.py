# Copyright (c) 2025 GÖKSEL ÖZKAN
# TextHealer Unit Tests

import pytest
from docuforge.src.cleaning.healer import TextHealer


class TestTextHealerLanguageDetection:
    """Tests for language detection functionality"""
    
    def setup_method(self):
        self.healer = TextHealer()
    
    def test_detect_turkish_text(self):
        """Turkish stop words should be detected"""
        text = "bu kitap ve diğer şeyler için yazılmıştır"
        assert self.healer.detect_language(text) == 'tr'
    
    def test_detect_english_text(self):
        """English stop words should be detected"""
        text = "the book and other things are written for you"
        assert self.healer.detect_language(text) == 'en'
    
    def test_empty_text_defaults_to_turkish(self):
        """Empty text should default to Turkish (user context bias)"""
        assert self.healer.detect_language("") == 'tr'
        assert self.healer.detect_language(None) == 'tr'
    
    def test_mixed_content_majority_wins(self):
        """Mixed content should detect based on majority"""
        # More English stop words
        text = "the and of to in için ve"  # 5 EN vs 2 TR
        assert self.healer.detect_language(text) == 'en'


class TestTextHealerTurkishHealing:
    """Tests for Turkish text repair"""
    
    def setup_method(self):
        self.healer = TextHealer()
    
    def test_heal_broken_ve_conjunction(self):
        """'v e' should become 've'"""
        broken = "kitap v e kalem"
        healed = self.healer.heal_document(broken)
        assert "ve" in healed
        assert "v e" not in healed
    
    def test_heal_broken_de_particle(self):
        """'d e' should become 'de'"""
        broken = "ben d e geliyorum"
        healed = self.healer.heal_document(broken)
        assert "de" in healed
        assert "d e" not in healed
    
    def test_heal_broken_bu_pronoun(self):
        """'b u' should become 'bu'"""
        broken = "b u kitap güzel"
        healed = self.healer.heal_document(broken)
        assert "bu" in healed
        assert "b u" not in healed
    
    def test_heal_hyphenated_word(self):
        """'prob- lem' should become 'problem'"""
        broken = "bu bir prob- lem"
        healed = self.healer.heal_document(broken)
        assert "problem" in healed

class TestTextHealerEnglishHealing:
    """Tests for English text repair (conservative mode)"""
    
    def setup_method(self):
        self.healer = TextHealer()
    
    def test_heal_broken_the(self):
        """'t he' should become 'the'"""
        broken = "t he quick brown fox"
        healed = self.healer.heal_document(broken)
        assert "the" in healed.lower()
        assert "t he" not in healed
    
    def test_preserve_article_a(self):
        """'a book' should NOT become 'abook' in English"""
        text = "this is a book"
        healed = self.healer.heal_document(text)
        assert "a book" in healed
        assert "abook" not in healed
    
    def test_preserve_pronoun_i(self):
        """'I am' should NOT become 'Iam' in English"""
        text = "I am here"
        healed = self.healer.heal_document(text)
        # I should remain separate
        assert "I am" in healed or "I " in healed


class TestTextHealerDocumentProcessing:
    """Tests for full document healing with auto-detection"""
    
    def setup_method(self):
        self.healer = TextHealer()
    
    def test_heal_document_turkish(self):
        """Full document should be healed with correct language"""
        doc = "Bu kitap v e diğerleri\nçok güzel d e"
        healed = self.healer.heal_document(doc)
        assert "ve" in healed
        assert "de" in healed
    
    def test_heal_document_preserves_newlines(self):
        """Newline structure should be preserved"""
        doc = "satır bir\nsatır iki\nsatır üç"
        healed = self.healer.heal_document(doc)
        assert healed.count('\n') == 2


class TestTextHealerEdgeCases:
    """Edge case and regression tests"""
    
    def setup_method(self):
        self.healer = TextHealer()
    
    def test_short_text_handling(self):
        """Very short text should not crash"""
        assert self.healer.heal_document("ab") == "ab"
        assert self.healer.heal_document("") == ""
    
    def test_unicode_handling(self):
        """Turkish special characters should be handled"""
        text = "Türkçe özel karakterler: ğ ü ş ı ö ç"
        healed = self.healer.heal_document(text)
        assert "ğ" in healed
        assert "ş" in healed

    def test_hybrid_suffix_repair(self):
        """Hybrid Regex: 'kitap lar' should become 'kitaplar'"""
        text = "bu kitap lar çok güzel"
        healed = self.healer.heal_document(text)
        assert "kitaplar" in healed
        
    def test_hybrid_explosion_repair(self):
        """Hybrid Regex: 'k e l i m e' should become 'kelime'"""
        text = "bu bir k e l i m e örneğidir"
        healed = self.healer.heal_document(text)
        assert "kelime" in healed
