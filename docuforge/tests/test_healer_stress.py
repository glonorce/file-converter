import pytest
import sys
import os

# Ensure project root is in path
sys.path.append(os.getcwd())

from docuforge.src.cleaning.healer import TextHealer

@pytest.fixture
def healer():
    return TextHealer()

def test_healer_safety(healer):
    # Should NOT merge
    assert healer.heal_document("A Blok") == "A Blok"  # Capitalized single letter
    assert healer.heal_document("Plan B") == "Plan B"
    assert healer.heal_document("User X verification") == "User X verification"
    assert healer.heal_document("a book") == "a book" # English a
    assert healer.heal_document("I am") == "I am"     # English I

def test_healer_repair_tr(healer):
    # Should merge
    # "ve" is in dict
    assert "ve" in healer.heal_document("v e") 
    # "düşünce" is in dict
    assert "düşünce" in healer.heal_document("d ü ş ü n c e")
    # "yapılar"
    assert "yapılar" in healer.heal_document("yap ı lar")
    
def test_healer_repair_en(healer):
    # Should merge
    assert "the" in healer.heal_document("t he")
    assert "problem" in healer.heal_document("prob- lem")

def test_healer_mixed(healer):
    # Complex case
    text = "Plan B de t he implementation succeeded."
    # Plan B -> Kept
    # d e -> de (if 'de' in dict, which it is in TR, mixed lang might be tricky. 'de' also Latin/French... SymSpell EN dict might not have it?)
    # t he -> the
    result = healer.heal_document(text)
    assert "Plan B" in result
    assert "the" in result
    # "de" depends on language detection.
    # Text is mostly English ("implementation succeeded"). Detects EN.
    # In EN, "d e" -> "de"? 'de' is usually 'de-' prefix or foreign. 'de' is in EN freq dict? rare.
    # We'll see.
