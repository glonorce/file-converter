from typing import List, Dict, Any, Tuple, Optional
import pdfplumber
from collections import Counter, defaultdict  # Added defaultdict
from loguru import logger
import math
import numpy as np # Added numpy

class GeometricClassifier:
    """
    Analyzes page geometry to distinguish between Grid Tables, Charts, and Text Blocks.
    """
    
    @staticmethod
    def classify_page(page: pdfplumber.page.Page, threshold_curve: int = 10, threshold_grid: int = 15) -> str:
        """
        Returns: 'CHART', 'TABLE', or 'TEXT'
        """
        # 1. Analyze Curves (Pie Charts, Diagrams)
        curves = page.curves
        # Filter tiny curves (often just noise or small bullets)
        significant_curves = [c for c in curves if (c['x1'] - c['x0']) > 10 or (c['y1'] - c['y0']) > 10]
        
        if len(significant_curves) > threshold_curve:
            logger.debug(f"Page {page.page_number}: Detected CHART (Curves: {len(significant_curves)})")
            return "CHART"
            
        # 2. Analyze Lines (Tables)
        lines = page.lines
        # Simple heuristic: Tables have many lines.
        # Better: Tables have intersecting lines. But raw count is a good proxy for speed.
        if len(lines) > threshold_grid:
            # Check for grid-like structure (horizontal + vertical)
            horiz = [l for l in lines if abs(l['y0'] - l['y1']) < 2]
            vert = [l for l in lines if abs(l['x0'] - l['x1']) < 2]
            
            if len(horiz) > 2 and len(vert) > 2:
                logger.debug(f"Page {page.page_number}: Detected TABLE (H:{len(horiz)}, V:{len(vert)})")
                return "TABLE"
                
        return "TEXT"

class ChartMiner:
    """
    Extracts data from Pie Charts using Vector & Color analysis.
    """
    
    @staticmethod
    def extract_pie_data(page: pdfplumber.page.Page) -> Optional[str]:
        """
        Attempts to create a Markdown table from a Pie Chart.
        Returns: Markdown string or None if extraction fails/unreliable.
        """
        try:
            # 1. Component Extraction
            paths = page.curves + page.rects # Slices and Legend markers
            text_objs = page.chars
            
            if not paths or not text_objs:
                return None
                
            # 2. Color Mapping
            # Group text by color
            # Problem: Text usually black. Slices are colored.
            # Strategy: 
            #   Find Legend: Small Box (Color X) -> Near Text "Europe"
            #   Find Slice: Large Curve (Color X) -> Near Text "30%"
            
            # A. Find Legend Items (Small Rects/Curves followed by Text)
            color_label_map = {} # {(r,g,b): "Label"}
            
            # Simplification: Look for small rects aligned with text
            rects = [r for r in page.rects if r['width'] < 20 and r['height'] < 20] # Tiny markers
            
            # Fallback: If no rects, maybe simple text proximity to slice? 
            # Too complex for V1.
            
            # Let's implement a robust skip first. The user asked for "Skip or Extract".
            # If we detect a chart but can't confidently mine it, we return "" (Skip).
            # If we return None, the caller might try text extraction (which gives Word Salad).
            # So returning "" is the "Clean" option.
            
            return "" # Placeholder for V1: Just Skip to clean output.
            
            # TODO: Implement full V2 logic based on user plan:
            # 1. Map Colors -> Labels (Legend Analysis)
            # 2. Map Colors -> Slices -> Values
            # 3. Join
            
        except Exception as e:
            logger.warning(f"Chart Mining failed: {e}")
            return None

class SpatialTableExtractor:
    """
    Visionary Hybrid Engine: Extracts tables using X-Axis Projection Histograms.
    Ignores PDF line objects. Ignores local word spacing.
    Uses 'Whitespace Rivers' to mathematically define column boundaries.
    """
    
    def extract_table(self, page) -> List[List[str]]:
        words = page.extract_words()
        if not words:
            return []
            
        height = int(page.height)
        width = int(page.width)
        
        # 1. Detect Data Zone (Bottom 80% assumption to skip Header Noise)
        data_words = [w for w in words if w['top'] > height * 0.20] # Lowered to 20%
        if len(data_words) < 10: 
            data_words = words 
            
        # 2. Build X-Histogram with AGGRESSIVE EROSION
        histogram = np.zeros(width)
        for w in data_words:
            x0, x1 = int(w['x0']), int(w['x1'])
            
            # Aggressive Erosion: Shrink box by 2px on each side to force gaps
            # Only if word is wide enough (> 6px) to survive
            if x1 - x0 > 6:
                x0 += 2
                x1 -= 2
            elif x1 - x0 > 2:
                 x0 += 1
                 x1 -= 1
                 
            x0 = max(0, x0); x1 = min(width - 1, x1)
            histogram[x0:x1] += 1
            
        # 3. Find Rivers (Vertical Gaps)
        dividers = [0]
        current_river_start = None
        MIN_GAP = 1; NOISE_THRESHOLD = 1
        
        for x, count in enumerate(histogram):
            if count <= NOISE_THRESHOLD:
                if current_river_start is None: current_river_start = x
            else:
                if current_river_start is not None:
                    river_width = x - current_river_start
                    if river_width >= MIN_GAP: dividers.append((current_river_start + x) / 2)
                    current_river_start = None
        dividers.append(width)
        
        # 4. Map Words to Grid using ADAPTIVE ROW CLUSTERING
        words.sort(key=lambda w: w['top'])
        rows = []; current_row = []; current_row_bottom = -1; current_row_top = -1
        
        for w in words:
            top = float(w['top']); bottom = float(w['bottom'])
            if not current_row:
                current_row = [w]; current_row_top = top; current_row_bottom = bottom; continue
            
            vertical_overlap = min(bottom, current_row_bottom) - max(top, current_row_top)
            if top < (current_row_bottom - 2): # 2px Tolerance
                current_row.append(w)
                current_row_bottom = max(current_row_bottom, bottom)
                current_row_top = min(current_row_top, top)
            else:
                rows.append(current_row)
                current_row = [w]
                current_row_top = top
                current_row_bottom = bottom
        if current_row: rows.append(current_row)
            
        table_matrix = []
        for row_words in rows:
            row_words.sort(key=lambda w: w['x0'])
            row_slots = [""] * (len(dividers) - 1)
            for w in row_words:
                w_center = (w['x0'] + w['x1']) / 2
                found = False
                for i in range(len(dividers)-1):
                    if dividers[i] <= w_center < dividers[i+1]:
                        row_slots[i] += w['text'] + " "; found = True; break
                if not found:
                    if w_center < dividers[0]: row_slots[0] += w['text'] + " "
                    elif w_center > dividers[-1]: row_slots[-1] += w['text'] + " "
            
            clean_row = [s.strip() for s in row_slots]
            
            # FOOTER GUARD (Permissive - Bottom 10% only)
            row_text = " ".join(clean_row).lower()
            footer_triggers = ["hazırlamaktan sorumlu", "sorumlu kişiler", "yasal uyarı", "disclaimer", "bridgewater", "machine translated"]
            row_y_center = sum((w['top'] + w['bottom'])/2 for w in row_words) / len(row_words) if row_words else 0
            
            if any(t in row_text for t in footer_triggers):
                if row_y_center > height * 0.90: # Only abort if extremely low
                    break
                else:
                    continue # Skip mid-page triggers
            
            # PERMISSIVE FILTER: Allow all rows with at least 1 column
            # This ensures we don't lose the 'BEL' row even if it looks like a single block
            filled = sum(1 for c in clean_row if c)
            if filled >= 1:
                # Filter tiny noise (e.g. single letter 'a' in margin)
                if filled == 1 and len(clean_row[0]) < 2: 
                    # print(f"DEBUG: Rejected Noise Row: {clean_row}")
                    continue
                table_matrix.append(clean_row)
            else:
                # print(f"DEBUG: Rejected Empty Row: {clean_row}")
                pass

        # 4b. HEADER LOOKBACK (Visionary Hybrid V9)
        # Scan words in the top 20% (Header Zone) using the dividers found from the Body.
        # This ensures headers align with the body columns even if the body defined the grid.
        header_words = [w for w in words if w['top'] <= height * 0.20]
        if header_words and table_matrix:
            # Group words into lines but filter noise
            # User Complaint: "tek kalan boşluk yüzüne oluşan harfi tablo başlığı zannediyor"
            # Fix: Ignore single-char words in potential header zone
            header_rows = []
            
            # Sort by top position for row clustering
            header_words.sort(key=lambda w: w['top'])
            
            current_h_row = []
            if header_words:
                 current_h_top = float(header_words[0]['top'])
            
            for w in header_words:
                # NOISE FILTER: Skip single chars unless meaningful symbol
                if len(w['text']) < 2 and w['text'] not in ['%', '#', '$']:
                    continue
                    
                top = float(w['top'])
                # New Row Detection (3px tolerance)
                if top > (current_h_top + 3):
                    if current_h_row: header_rows.append(current_h_row)
                    current_h_row = [w]
                    current_h_top = top
                else:
                    current_h_row.append(w)
            
            if current_h_row: header_rows.append(current_h_row)
            
            # Map Header Rows to Dividers
            mapped_headers = []
            for h_row_words in header_rows:
                h_row_words.sort(key=lambda w: w['x0'])
                
                # Visionary V10: 1-to-1 Mapping Heuristic
                # If number of header items equals number of columns, assume perfect alignment order.
                # This solves "centered header" misalignment issues.
                num_body_cols = len(dividers) - 1
                if len(h_row_words) == num_body_cols:
                     clean_h_row = [w['text'] for w in h_row_words]
                     mapped_headers.append(clean_h_row)
                     continue

                # Standard Spatial Mapping (Relaxed)
                h_slots = [""] * num_body_cols
                for w in h_row_words:
                    w_center = (w['x0'] + w['x1']) / 2
                    found = False
                    for i in range(num_body_cols):
                        # Strict: dividers[i] <= w_center < dividers[i+1]
                        # Relaxed: Allow 10% overlap?
                        # Actually, just stick to center compliance for now.
                        if dividers[i] <= w_center < dividers[i+1]:
                            h_slots[i] += w['text'] + " "; found = True; break
                    if not found:
                        if w_center < dividers[0]: h_slots[0] += w['text'] + " "
                        elif w_center > dividers[-1]: h_slots[-1] += w['text'] + " "
                
                clean_h_row = [s.strip() for s in h_slots]
                # Only add if it looks relevant (at least 1 column or significant text)
                if sum(1 for c in clean_h_row if c) >= 1:
                     mapped_headers.append(clean_h_row)
            
            # Prepend found headers to the matrix
            if mapped_headers:
                table_matrix = mapped_headers + table_matrix

        # 5. POST-PROCESSING: Prune Ghost Columns
        if not table_matrix: return []
        num_cols = len(table_matrix[0]); num_rows = len(table_matrix)
        valid_col_indices = []
        for col_idx in range(num_cols):
             filled_count = sum(1 for row in table_matrix if len(row) > col_idx and row[col_idx].strip())
             if (filled_count / num_rows) > 0.05 or num_cols < 3: valid_col_indices.append(col_idx)
             
        pruned_matrix = []
        for row in table_matrix:
            pruned_matrix.append([row[i] for i in valid_col_indices if i < len(row)])
            
        return pruned_matrix
