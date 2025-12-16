import os
import urllib.request
from pathlib import Path

def ensure_tr_dict(target_path: Path = None):
    if target_path is None:
        target_path = Path("docuforge/src/cleaning/dicts/tr_freq.txt")
        
    if target_path.exists() and target_path.stat().st_size > 0:
        print(f"Dictionary already exists at {target_path}")
        return # Already exists
        
    url = "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/tr/tr_50k.txt"
    # Ensure parent directory exists
    target_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"Downloading Turkish Dictionary from {url}...")
    try:
        with urllib.request.urlopen(url) as response:
            data = response.read().decode('utf-8')
            
        # Parse HermitDave format: "word count"
        lines_out = []
        for line in data.splitlines():
            parts = line.strip().split(' ')
            if len(parts) >= 2:
                word = parts[0]
                count = parts[1]
                # Basic validation
                if len(word) > 1 and word.isalpha():
                    lines_out.append(f"{word} {count}")
        
        target_path.write_text("\n".join(lines_out), encoding="utf-8")
        print(f"Saved {len(lines_out)} words to {target_path}")
        
    except Exception as e:
        print(f"Download failed: {e}")

if __name__ == "__main__":
    ensure_tr_dict()
