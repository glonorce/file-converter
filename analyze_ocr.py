"""
Analyze why OCR auto triggers on page 2 of test3.pdf
"""
import pdfplumber
from pathlib import Path

pdf_path = Path("test pdfleri/test3.pdf")

with pdfplumber.open(pdf_path) as pdf:
    # Page 2 (0-indexed: page 1)
    page = pdf.pages[1]  # İÇİNDEKİLER sayfası
    
    raw_text = page.filter(lambda obj: obj["object_type"] == "char").extract_text() or ""
    stripped_text = raw_text.strip()
    
    print(f"Page 2 Analysis:")
    print(f"  Text length: {len(stripped_text)}")
    print(f"  Space count: {stripped_text.count(' ')}")
    
    if len(stripped_text) >= 50:
        space_ratio = stripped_text.count(' ') / len(stripped_text)
        print(f"  Space ratio: {space_ratio:.4f} ({space_ratio*100:.2f}%)")
        
        if space_ratio < 0.05:
            print(f"  ❌ OCR WOULD TRIGGER (space_ratio < 5%)")
        else:
            print(f"  ✅ OCR would NOT trigger")
    elif len(stripped_text) < 50:
        print(f"  ❌ OCR WOULD TRIGGER (text < 50 chars)")
    
    print(f"\n--- First 500 chars ---")
    print(stripped_text[:500])
