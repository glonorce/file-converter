# Copyright (c) 2025 GÖKSEL ÖZKAN
# Neural-Spatial Extraction Engine v1.0
# "İnsan Gibi Gör, Makine Gibi Ayrıştır"

"""
Neural-Spatial Engine: Next-generation table and chart extraction using 
visual-semantic analysis without relying on fragile heuristics.

Key innovations:
- Multi-table detection on single page
- Adaptive thresholding for sparse rows (BEL 1982 fix)
- Chart/Graph detection to prevent "broken table" parsing
- Fallback chain: Neural → Raw Text Reconstruction
"""

from typing import List, Dict, Any, Tuple, Optional, Literal
from dataclasses import dataclass, field
from collections import defaultdict
import math
import numpy as np
import pdfplumber
from loguru import logger

from docuforge.src.core.config import ExtractionConfig
from docuforge.src.cleaning.healer import TextHealer


# =============================================================================
# DATA MODELS
# =============================================================================

@dataclass
class BBox:
    """Bounding box with utility methods."""
    x0: float
    y0: float
    x1: float
    y1: float
    
    @property
    def width(self) -> float:
        return self.x1 - self.x0
    
    @property
    def height(self) -> float:
        return self.y1 - self.y0
    
    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2
    
    @property
    def center_y(self) -> float:
        return (self.y0 + self.y1) / 2
    
    @property
    def area(self) -> float:
        return self.width * self.height
    
    def contains_point(self, x: float, y: float) -> bool:
        return self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1
    
    def overlaps(self, other: "BBox", threshold: float = 0.5) -> bool:
        """Check if boxes overlap by at least threshold ratio."""
        dx = min(self.x1, other.x1) - max(self.x0, other.x0)
        dy = min(self.y1, other.y1) - max(self.y0, other.y0)
        if dx <= 0 or dy <= 0:
            return False
        intersection = dx * dy
        min_area = min(self.area, other.area)
        return (intersection / min_area) >= threshold if min_area > 0 else False


@dataclass
class GridLine:
    """A detected grid line (horizontal or vertical)."""
    position: float  # x for vertical, y for horizontal
    start: float     # Starting coordinate
    end: float       # Ending coordinate
    is_horizontal: bool
    strength: float = 1.0  # Line weight/thickness indicator


@dataclass
class GridStructure:
    """Detected grid of horizontal and vertical lines."""
    horizontal_lines: List[GridLine] = field(default_factory=list)
    vertical_lines: List[GridLine] = field(default_factory=list)
    bbox: Optional[BBox] = None
    
    def get_row_boundaries(self) -> List[float]:
        """Get Y-positions of horizontal lines (row separators)."""
        return sorted([l.position for l in self.horizontal_lines])
    
    def get_column_boundaries(self) -> List[float]:
        """Get X-positions of vertical lines (column separators)."""
        return sorted([l.position for l in self.vertical_lines])


@dataclass
class TableRegion:
    """A detected table region with metadata."""
    bbox: BBox
    grid: Optional[GridStructure] = None
    is_bordered: bool = False
    confidence: float = 0.0
    
    
@dataclass 
class ChartMarker:
    """Marks a detected chart region."""
    bbox: BBox
    chart_type: str = "unknown"  # pie, bar, line, etc.
    confidence: float = 0.0


RegionType = Literal["TABLE", "CHART", "TEXT", "UNKNOWN"]


# =============================================================================
# VISION CORTEX: Visual Layout Analysis
# =============================================================================

class VisionCortex:
    """
    Analyzes page geometry and visual elements.
    Uses pdfplumber line objects + NumPy for spatial analysis.
    """
    
    def __init__(self, config: ExtractionConfig):
        self.config = config
        self.chart_curve_threshold = getattr(config, 'neural_chart_curve_threshold', 5)
    
    def analyze_layout(self, page: pdfplumber.page.Page) -> Dict[str, Any]:
        """
        Extract comprehensive layout features from a page.
        
        Returns:
            dict with keys: 'lines', 'words', 'grid', 'visual_density', etc.
        """
        lines = page.lines or []
        rects = page.rects or []
        curves = page.curves or []
        words = page.extract_words(keep_blank_chars=True) or []
        
        # Classify lines by orientation
        horizontal_lines = []
        vertical_lines = []
        diagonal_lines = []
        
        for line in lines:
            angle = self._line_angle(line)
            grid_line = GridLine(
                position=line['top'] if abs(angle) < 10 else line['x0'],
                start=line['x0'] if abs(angle) < 10 else line['top'],
                end=line['x1'] if abs(angle) < 10 else line['bottom'],
                is_horizontal=(abs(angle) < 10),
                strength=max(abs(line.get('linewidth', 1)), 0.5)
            )
            
            if abs(angle) < 10:  # Near horizontal
                horizontal_lines.append(grid_line)
            elif abs(angle - 90) < 10:  # Near vertical
                grid_line.position = line['x0']
                grid_line.start = line['top']
                grid_line.end = line['bottom']
                grid_line.is_horizontal = False
                vertical_lines.append(grid_line)
            else:
                diagonal_lines.append(line)
        
        return {
            'horizontal_lines': horizontal_lines,
            'vertical_lines': vertical_lines,
            'diagonal_lines': diagonal_lines,
            'rects': rects,
            'curves': curves,
            'words': words,
            'page_width': page.width,
            'page_height': page.height,
        }
    
    def _line_angle(self, line: Dict) -> float:
        """Calculate line angle in degrees (0=horizontal, 90=vertical)."""
        dx = line['x1'] - line['x0']
        dy = line['bottom'] - line['top']
        if dx == 0:
            return 90.0
        return abs(math.degrees(math.atan(dy / dx)))
    
    def find_whitespace_rivers(self, words: List[Dict], page_width: float) -> List[float]:
        """
        Find vertical whitespace "rivers" in word positions.
        These indicate column boundaries in borderless tables.
        
        Uses X-axis projection histogram with erosion.
        """
        if not words:
            return []
        
        width = int(page_width)
        histogram = np.zeros(width)
        
        for w in words:
            x0, x1 = int(w['x0']), int(w['x1'])
            # Aggressive erosion: shrink word boxes to create gaps
            if x1 - x0 > 6:
                x0 += 2
                x1 -= 2
            elif x1 - x0 > 2:
                x0 += 1
                x1 -= 1
            x0 = max(0, x0)
            x1 = min(width - 1, x1)
            if x0 < x1:
                histogram[x0:x1] += 1
        
        # Find rivers (gaps in histogram)
        rivers = [0.0]
        river_start = None
        noise_threshold = 1
        min_gap = 3
        
        for x, count in enumerate(histogram):
            if count <= noise_threshold:
                if river_start is None:
                    river_start = x
            else:
                if river_start is not None:
                    river_width = x - river_start
                    if river_width >= min_gap:
                        rivers.append((river_start + x) / 2)
                    river_start = None
        
        rivers.append(float(width))
        return rivers
    
    def detect_chart_indicators(self, layout: Dict[str, Any]) -> bool:
        """
        Determine if the page/region contains chart elements.
        
        Returns True if chart indicators exceed threshold.
        """
        curves = layout.get('curves', [])
        diagonals = layout.get('diagonal_lines', [])
        
        # Significant curves (not tiny bullets)
        significant_curves = [
            c for c in curves 
            if abs(c.get('x1', 0) - c.get('x0', 0)) > 10 
            or abs(c.get('y1', 0) - c.get('y0', 0)) > 10
        ]
        
        return len(significant_curves) > self.chart_curve_threshold or len(diagonals) > 10


# =============================================================================
# TABLE DETECTOR: Multi-table Detection
# =============================================================================

class TableDetector:
    """
    Detects table regions using line-based grid detection 
    and whitespace river analysis for borderless tables.
    """
    
    def __init__(self, config: ExtractionConfig):
        self.config = config
        self.min_table_rows = getattr(config, 'neural_min_table_rows', 2)
    
    def detect_tables(self, page: pdfplumber.page.Page, 
                      layout: Dict[str, Any]) -> List[TableRegion]:
        """
        Detect all tables on a page.
        
        Strategy:
        1. Try bordered table detection (line grids)
        2. Try borderless table detection (whitespace rivers)
        3. Merge overlapping regions
        """
        tables = []
        
        # Strategy 1: Bordered tables (line grids)
        bordered = self._detect_bordered_tables(layout)
        tables.extend(bordered)
        
        # Strategy 2: Borderless tables (if no bordered found)
        if not bordered:
            borderless = self._detect_borderless_tables(layout)
            tables.extend(borderless)
        
        # Remove overlapping detections
        tables = self._merge_overlapping(tables)
        
        return tables
    
    def _detect_bordered_tables(self, layout: Dict[str, Any]) -> List[TableRegion]:
        """Detect tables with visible borders using line intersections."""
        h_lines = layout.get('horizontal_lines', [])
        v_lines = layout.get('vertical_lines', [])
        
        if len(h_lines) < 2 or len(v_lines) < 2:
            return []
        
        # Find grid bounding box from line positions
        h_positions = sorted([l.position for l in h_lines])
        v_positions = sorted([l.position for l in v_lines])
        
        # Find contiguous grid regions
        tables = []
        
        # Cluster horizontal lines into groups (gap > 50px = new table)
        h_groups = self._cluster_positions(h_positions, gap_threshold=50)
        
        for h_group in h_groups:
            if len(h_group) < 2:
                continue
                
            # Find vertical lines that span this horizontal range
            y_min, y_max = min(h_group), max(h_group)
            relevant_v = [
                l for l in v_lines 
                if l.start <= y_max and l.end >= y_min
            ]
            
            if len(relevant_v) < 2:
                continue
            
            v_positions_local = sorted([l.position for l in relevant_v])
            x_min, x_max = min(v_positions_local), max(v_positions_local)
            
            grid = GridStructure(
                horizontal_lines=[l for l in h_lines if y_min <= l.position <= y_max],
                vertical_lines=relevant_v,
                bbox=BBox(x_min, y_min, x_max, y_max)
            )
            
            tables.append(TableRegion(
                bbox=BBox(x_min, y_min, x_max, y_max),
                grid=grid,
                is_bordered=True,
                confidence=0.9
            ))
        
        return tables
    
    def _detect_borderless_tables(self, layout: Dict[str, Any]) -> List[TableRegion]:
        """Detect tables without visible borders using word alignment."""
        words = layout.get('words', [])
        page_width = layout.get('page_width', 612)
        page_height = layout.get('page_height', 792)
        
        if len(words) < 10:
            return []
        
        # Get data zone (skip header region - top 15%)
        data_words = [w for w in words if w['top'] > page_height * 0.15]
        if len(data_words) < 10:
            data_words = words
        
        # Find column rivers
        rivers = VisionCortex(self.config).find_whitespace_rivers(data_words, page_width)
        
        if len(rivers) < 3:  # Need at least 2 columns
            return []
        
        # Determine table extent from word positions
        y_positions = [w['top'] for w in data_words]
        y_min, y_max = min(y_positions), max([w['bottom'] for w in data_words])
        
        # Create virtual grid from rivers
        grid = GridStructure(
            vertical_lines=[
                GridLine(position=r, start=y_min, end=y_max, is_horizontal=False)
                for r in rivers
            ],
            bbox=BBox(rivers[0], y_min, rivers[-1], y_max)
        )
        
        return [TableRegion(
            bbox=BBox(rivers[0], y_min, rivers[-1], y_max),
            grid=grid,
            is_bordered=False,
            confidence=0.7
        )]
    
    def _cluster_positions(self, positions: List[float], 
                           gap_threshold: float = 50) -> List[List[float]]:
        """Cluster positions into groups separated by large gaps."""
        if not positions:
            return []
        
        groups = [[positions[0]]]
        for pos in positions[1:]:
            if pos - groups[-1][-1] > gap_threshold:
                groups.append([pos])
            else:
                groups[-1].append(pos)
        
        return groups
    
    def _merge_overlapping(self, tables: List[TableRegion]) -> List[TableRegion]:
        """Remove or merge overlapping table detections."""
        if len(tables) <= 1:
            return tables
        
        # Sort by confidence descending
        tables = sorted(tables, key=lambda t: -t.confidence)
        result = []
        
        for table in tables:
            overlaps_existing = any(
                table.bbox.overlaps(existing.bbox, threshold=0.3) 
                for existing in result
            )
            if not overlaps_existing:
                result.append(table)
        
        return result
    
    def classify_region(self, region: BBox, layout: Dict[str, Any]) -> RegionType:
        """Classify a region as TABLE, CHART, or TEXT."""
        # Check for chart indicators in region
        curves = [
            c for c in layout.get('curves', [])
            if region.contains_point(c.get('x0', 0), c.get('y0', 0))
        ]
        
        if len(curves) > 5:
            return "CHART"
        
        # Check for table structure
        h_lines = [
            l for l in layout.get('horizontal_lines', [])
            if region.y0 <= l.position <= region.y1
        ]
        v_lines = [
            l for l in layout.get('vertical_lines', [])
            if region.x0 <= l.position <= region.x1
        ]
        
        if len(h_lines) >= 2 and len(v_lines) >= 2:
            return "TABLE"
        
        return "TEXT"


# =============================================================================
# CHARACTER RECONSTRUCTOR: Smart Word Merging from Raw Chars
# =============================================================================

class CharacterReconstructor:
    """
    Reconstructs proper words from raw PDF characters.
    Uses gap-based threshold (font_size * 0.20) to merge adjacent chars.
    This solves the "G ü ç" → "Güç" problem.
    """
    
    GAP_THRESHOLD_FACTOR = 0.20  # Tuned for Turkish kerning
    
    @staticmethod
    def normalize_text(text: str) -> str:
        """Apply Unicode normalization."""
        import unicodedata
        if not text:
            return text
        return unicodedata.normalize('NFC', text)
    
    @classmethod
    def reconstruct_words_in_bbox(cls, chars: List[Dict], bbox: BBox) -> List[Dict]:
        """
        Reconstruct proper words from characters within a bounding box.
        
        Args:
            chars: Raw character list from page.chars
            bbox: Bounding box to filter characters
            
        Returns:
            List of word dicts with 'text', 'x0', 'x1', 'top', 'bottom' keys
        """
        # Filter chars within bbox
        region_chars = [
            c for c in chars
            if bbox.contains_point(c['x0'], c['top'])
            and c.get('text', '').strip()  # Skip empty/whitespace
        ]
        
        if not region_chars:
            return []
        
        # Sort by Y (line) then X (position)
        region_chars = sorted(region_chars, key=lambda c: (round(c['top']), c['x0']))
        
        # Group into lines
        lines = []
        current_line = []
        current_y = None
        y_tolerance = 3
        
        for char in region_chars:
            char_y = round(char['top'])
            
            if current_y is None:
                current_y = char_y
                current_line = [char]
            elif abs(char_y - current_y) <= y_tolerance:
                current_line.append(char)
            else:
                if current_line:
                    lines.append(current_line)
                current_line = [char]
                current_y = char_y
        
        if current_line:
            lines.append(current_line)
        
        # Process each line to merge characters into words
        all_words = []
        for line_chars in lines:
            line_words = cls._merge_chars_to_words(line_chars)
            all_words.extend(line_words)
        
        return all_words
    
    @classmethod
    def _merge_chars_to_words(cls, chars: List[Dict]) -> List[Dict]:
        """Merge characters into words based on gap threshold."""
        if not chars:
            return []
        
        # Sort by X position
        chars = sorted(chars, key=lambda c: c['x0'])
        
        words = []
        current_word_chars = []
        current_word_texts = []
        
        for i, char in enumerate(chars):
            text = cls.normalize_text(char.get('text', ''))
            if not text or text.isspace():
                continue
            
            size = char.get('size', 10)
            threshold = size * cls.GAP_THRESHOLD_FACTOR
            
            if not current_word_chars:
                current_word_chars = [char]
                current_word_texts = [text]
                continue
            
            prev_char = current_word_chars[-1]
            gap = char['x0'] - prev_char['x1']
            
            if gap <= threshold:
                # Same word
                current_word_chars.append(char)
                current_word_texts.append(text)
            else:
                # New word - save current and start new
                words.append(cls._build_word_dict(current_word_chars, current_word_texts))
                current_word_chars = [char]
                current_word_texts = [text]
        
        # Don't forget last word
        if current_word_chars:
            words.append(cls._build_word_dict(current_word_chars, current_word_texts))
        
        return words
    
    @staticmethod
    def _build_word_dict(chars: List[Dict], texts: List[str]) -> Dict:
        """Build a word dict from merged characters."""
        return {
            'text': ''.join(texts),
            'x0': chars[0]['x0'],
            'x1': chars[-1]['x1'],
            'top': min(c['top'] for c in chars),
            'bottom': max(c['bottom'] for c in chars),
            'size': sum(c.get('size', 10) for c in chars) / len(chars),
        }


# =============================================================================
# STRUCTURE PARSER: Row/Column Mapping with Adaptive Thresholds
# =============================================================================

class StructureParser:
    """
    Parses table structure into rows and columns.
    Implements adaptive thresholding to solve "BEL 1982" paradox.
    """
    
    def __init__(self, config: ExtractionConfig):
        self.config = config
        self.adaptive_threshold = getattr(config, 'neural_adaptive_threshold', 0.3)
    
    def parse_table(self, region: TableRegion, 
                    words: List[Dict],
                    chars: Optional[List[Dict]] = None) -> List[List[str]]:
        """
        Parse words into a table matrix using the detected grid.
        
        Args:
            region: Detected table region with grid structure
            words: All words on the page (used as fallback)
            chars: Raw characters from page.chars (preferred for better reconstruction)
            
        Returns:
            2D list of cell contents
        """
        if not region.grid:
            return []
        
        # PRIORITY: Use character-level reconstruction if chars provided
        if chars:
            table_words = CharacterReconstructor.reconstruct_words_in_bbox(chars, region.bbox)
        else:
            # Fallback to pre-extracted words
            table_words = [
                w for w in words
                if region.bbox.contains_point(w['x0'], w['top'])
            ]
        
        if not table_words:
            return []
        
        # Get column and row boundaries
        col_bounds = region.grid.get_column_boundaries()
        row_bounds = region.grid.get_row_boundaries()
        
        # If no explicit row boundaries, cluster words by Y position
        if len(row_bounds) < 2:
            row_bounds = self._cluster_rows(table_words)
        
        # Map words to grid cells
        matrix = self._map_words_to_grid(table_words, row_bounds, col_bounds, region.grid)
        
        # Apply adaptive validation
        matrix = self._filter_rows_adaptive(matrix, region.grid)
        
        # Post-process: remove ghost columns
        matrix = self._prune_ghost_columns(matrix)
        
        # Post-process: remove footer rows (page numbers detected as table rows)
        matrix = self._prune_footer_rows(matrix)
        
        return matrix
    
    def _prune_footer_rows(self, matrix: List[List[str]]) -> List[List[str]]:
        """Remove rows that look like page footers (e.g. single number)."""
        import re
        if not matrix:
            return matrix
            
        # Check last row repeatedly (in case of multiple footer lines)
        while matrix:
            last_row = matrix[-1]
            non_empty = [c for c in last_row if c.strip()]
            
            if len(non_empty) == 1:
                content = non_empty[0].strip()
                # Match "12", "Page 12", "- 12 -", "12/50"
                # Also generic "Page X of Y"
                if re.match(r'^(?:(?:Page|Sayfa|Bölüm)\s*)?[\-]?\s*\d+(?:\s*[\-\/]\s*\d+)?\s*[\-]?$', content, re.IGNORECASE):
                    matrix.pop()
                    continue
            break
            
        return matrix

    def _cluster_rows(self, words: List[Dict]) -> List[float]:
        """Cluster words into rows based on Y-position."""
        if not words:
            return []
        
        words = sorted(words, key=lambda w: w['top'])
        row_bounds = [words[0]['top'] - 1]
        current_bottom = words[0]['bottom']
        
        for w in words[1:]:
            # New row if gap > tolerance
            if w['top'] > current_bottom + 3:
                row_bounds.append((current_bottom + w['top']) / 2)
            current_bottom = max(current_bottom, w['bottom'])
        
        row_bounds.append(current_bottom + 1)
        return row_bounds
    
    def _map_words_to_grid(self, words: List[Dict], 
                           row_bounds: List[float],
                           col_bounds: List[float],
                           grid: GridStructure) -> List[List[str]]:
        """Map words to grid cells based on position."""
        num_cols = len(col_bounds) - 1
        num_rows = len(row_bounds) - 1
        
        if num_cols <= 0 or num_rows <= 0:
            return []
        
        # Initialize matrix
        matrix = [[[] for _ in range(num_cols)] for _ in range(num_rows)]
        
        for w in words:
            # Find row
            row_idx = -1
            w_y = (w['top'] + w['bottom']) / 2
            for i in range(num_rows):
                if row_bounds[i] <= w_y < row_bounds[i + 1]:
                    row_idx = i
                    break
            
            # Find column
            col_idx = -1
            w_x = (w['x0'] + w['x1']) / 2
            for j in range(num_cols):
                if col_bounds[j] <= w_x < col_bounds[j + 1]:
                    col_idx = j
                    break
            
            if row_idx >= 0 and col_idx >= 0:
                matrix[row_idx][col_idx].append(w['text'])
        
        # Join cell words
        return [[' '.join(cell) for cell in row] for row in matrix]
    
    def _filter_rows_adaptive(self, matrix: List[List[str]], 
                              grid: GridStructure) -> List[List[str]]:
        """
        Apply adaptive thresholding to preserve sparse but valid rows.
        
        THE BEL 1982 FIX:
        - If a row geometrically aligns with grid lines → use lower threshold
        - Standard rows must meet normal fill ratio
        """
        if not matrix or not grid.horizontal_lines:
            # No grid lines to check against, use standard threshold
            return [
                row for row in matrix
                if sum(1 for c in row if c.strip()) / len(row) >= self.adaptive_threshold
            ]
        
        filtered = []
        row_positions = grid.get_row_boundaries()
        
        for i, row in enumerate(matrix):
            filled_count = sum(1 for c in row if c.strip())
            fill_ratio = filled_count / len(row) if row else 0
            
            # Check if row aligns with grid line
            row_y = row_positions[i] if i < len(row_positions) else 0
            is_on_grid = any(
                abs(row_y - line.position) < 3 
                for line in grid.horizontal_lines
            )
            
            # Adaptive threshold based on grid conformity
            if is_on_grid:
                # Geometric conformity → very permissive (1 cell is enough)
                threshold = 0.1
            else:
                threshold = self.adaptive_threshold
            
            if fill_ratio >= threshold or filled_count >= 1:
                filtered.append(row)
        
        return filtered
    
    def _prune_ghost_columns(self, matrix: List[List[str]], 
                             min_fill_ratio: float = 0.15) -> List[List[str]]:
        """Remove columns that are mostly empty.
        
        Increased min_fill_ratio from 0.05 to 0.15 and removed num_cols < 3 exception
        to properly handle single-column index tables that were showing as 2-column.
        """
        if not matrix:
            return matrix
        
        num_cols = len(matrix[0])
        num_rows = len(matrix)
        
        # Always check for ghost columns, even in 2-column tables
        valid_cols = []
        for col_idx in range(num_cols):
            filled = sum(
                1 for row in matrix 
                if col_idx < len(row) and row[col_idx].strip()
            )
            # Column must have at least 15% fill rate to be kept
            if filled / num_rows >= min_fill_ratio:
                valid_cols.append(col_idx)
        
        # Ensure at least one column remains
        if not valid_cols and num_cols > 0:
            valid_cols = [0]
        
        return [
            [row[i] for i in valid_cols if i < len(row)]
            for row in matrix
        ]
    
    def identify_headers(self, words: List[Dict], region: TableRegion) -> Optional[int]:
        """
        Identify which row(s) are headers based on:
        - Font size (larger = header)
        - Bold style
        - Position (top rows)
        - Content patterns (years, percentages, etc.)
        """
        if not words or not region.grid:
            return None
        
        table_words = [
            w for w in words
            if region.bbox.contains_point(w['x0'], w['top'])
        ]
        
        if not table_words:
            return None
        
        # Group words by row
        rows = defaultdict(list)
        for w in table_words:
            row_y = round(w['top'])
            rows[row_y].append(w)
        
        if not rows:
            return None
        
        # First row is likely header if it has different characteristics
        sorted_rows = sorted(rows.keys())
        first_row = rows[sorted_rows[0]]
        
        # Check for header indicators
        avg_size = sum(w.get('size', 10) for w in first_row) / len(first_row)
        body_sizes = [
            w.get('size', 10) 
            for y in sorted_rows[1:] 
            for w in rows[y]
        ]
        
        if body_sizes:
            body_avg = sum(body_sizes) / len(body_sizes)
            if avg_size > body_avg * 1.1:  # Header is notably larger
                return 1  # First row is header
        
        return 1  # Default: assume first row is header


# =============================================================================
# CONTENT HEALER: Fallback Extraction
# =============================================================================

class ContentHealer:
    """
    Provides fallback extraction when structured parsing fails.
    Attempts raw text reconstruction or marks for OCR.
    """
    
    def __init__(self, config: ExtractionConfig):
        self.config = config
    
    def fallback_extraction(self, region: TableRegion, 
                           words: List[Dict]) -> str:
        """
        Extract raw text from region when table parsing fails.
        Returns plain text with best-effort line breaks.
        """
        region_words = [
            w for w in words
            if region.bbox.contains_point(w['x0'], w['top'])
        ]
        
        if not region_words:
            return ""
        
        # Sort by position and reconstruct
        region_words.sort(key=lambda w: (round(w['top']), w['x0']))
        
        lines = []
        current_line = []
        current_y = region_words[0]['top']
        
        for w in region_words:
            if abs(w['top'] - current_y) > 5:  # New line
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [w['text']]
                current_y = w['top']
            else:
                current_line.append(w['text'])
        
        if current_line:
            lines.append(' '.join(current_line))
        
        return '\n'.join(lines)
    
    def needs_ocr(self, region: TableRegion, words: List[Dict]) -> bool:
        """
        Determine if a region needs OCR processing.
        Returns True if word extraction quality is too low.
        """
        region_words = [
            w for w in words
            if region.bbox.contains_point(w['x0'], w['top'])
        ]
        
        # If very few words relative to region size, might need OCR
        expected_words = (region.bbox.area / 5000)  # Rough estimate
        return len(region_words) < expected_words * 0.3


# =============================================================================
# CHART GUARD: Chart Detection
# =============================================================================

class ChartGuard:
    """
    Detects and marks chart/graph regions to prevent
    them from being incorrectly parsed as broken tables.
    """
    
    def __init__(self, config: ExtractionConfig):
        self.config = config
        self.curve_threshold = getattr(config, 'neural_chart_curve_threshold', 5)
    
    def is_chart(self, region: BBox, layout: Dict[str, Any]) -> bool:
        """
        Determine if a region contains a chart.
        
        Indicators:
        - Multiple curves (pie charts, line charts)
        - Diagonal lines (trend lines, axes at angles)
        - Color filled areas (bar charts)
        """
        curves = layout.get('curves', [])
        diagonals = layout.get('diagonal_lines', [])
        
        # Count elements within region
        region_curves = [
            c for c in curves
            if region.contains_point(c.get('x0', 0), c.get('y0', 0))
        ]
        
        region_diagonals = [
            l for l in diagonals
            if region.y0 <= l.get('top', 0) <= region.y1
        ]
        
        return len(region_curves) > self.curve_threshold or len(region_diagonals) > 5
    
    def mark_chart_region(self, region: BBox, chart_type: str = "unknown") -> ChartMarker:
        """Create a chart marker for the region."""
        return ChartMarker(
            bbox=region,
            chart_type=chart_type,
            confidence=0.8
        )
    
    def detect_chart_type(self, region: BBox, layout: Dict[str, Any]) -> str:
        """
        Attempt to identify chart type based on visual elements.
        Returns: 'pie', 'bar', 'line', or 'unknown'
        """
        curves = [
            c for c in layout.get('curves', [])
            if region.contains_point(c.get('x0', 0), c.get('y0', 0))
        ]
        
        rects = [
            r for r in layout.get('rects', [])
            if region.contains_point(r.get('x0', 0), r.get('top', 0))
        ]
        
        # Heuristics for chart type
        if len(curves) > 10:
            return "pie"  # Many curves = likely pie/donut
        elif len(rects) > 5:
            return "bar"  # Multiple rectangles = bar chart
        elif any(c for c in curves if 'pts' in c and len(c['pts']) > 10):
            return "line"  # Long curves with many points = line chart
        
        return "unknown"


# =============================================================================
# NEURAL-SPATIAL ENGINE: Main Entry Point
# =============================================================================

class NeuralSpatialEngine:
    """
    Main engine that orchestrates visual analysis and table extraction.
    
    Usage:
        engine = NeuralSpatialEngine(config)
        tables_md, charts = engine.process_page(page, page_num)
    """
    
    def __init__(self, config: ExtractionConfig):
        self.config = config
        self.vision_cortex = VisionCortex(config)
        self.table_detector = TableDetector(config)
        self.structure_parser = StructureParser(config)
        self.content_healer = ContentHealer(config)
        self.chart_guard = ChartGuard(config)
        # TextHealer for fixing broken words in table cells
        self._text_healer = TextHealer()
    
    def process_page(self, page: pdfplumber.page.Page, 
                     page_num: int) -> Tuple[List[str], List[ChartMarker], List[Tuple[float, float, float, float]]]:
        """
        Process a single page and extract tables and charts.
        
        Args:
            page: pdfplumber page object
            page_num: Page number for labeling
            
        Returns:
            (tables_md, chart_markers, table_bboxes)
        """
        tables_md = []
        charts = []
        table_bboxes = []
        
        try:
            # Step 1: Analyze page layout
            layout = self.vision_cortex.analyze_layout(page)
            words = layout.get('words', [])
            # Get raw characters for better word reconstruction
            chars = page.chars or []
            
            # Pre-filter: Numeric content ratio check
            # Tables typically contain high ratio of numbers (financial data, statistics)
            # If page has ≤15% digits, skip table detection (text-heavy page)
            # If page has >50% digits and no table found, force table detection
            digit_ratio = 0.0
            if words:
                all_text = ''.join(w.get('text', '') for w in words)
                if all_text:
                    digit_count = sum(1 for c in all_text if c.isdigit())
                    total_chars = len(all_text.replace(' ', ''))
                    if total_chars > 0:
                        digit_ratio = digit_count / total_chars
                        if digit_ratio <= 0.15:
                            # Text-heavy page - skip table detection entirely
                            return tables_md, charts, table_bboxes
            
            # Step 2: Check for chart-dominant page
            if self.vision_cortex.detect_chart_indicators(layout):
                logger.debug(f"Page {page_num}: Chart indicators detected")
                # Mark entire page as potential chart region
                chart_region = BBox(0, 0, page.width, page.height)
                if self.chart_guard.is_chart(chart_region, layout):
                    chart_type = self.chart_guard.detect_chart_type(chart_region, layout)
                    charts.append(self.chart_guard.mark_chart_region(chart_region, chart_type))
                    logger.debug(f"Page {page_num}: Detected as {chart_type} chart")
                    # Don't try to extract charts as tables
                    return tables_md, charts, []
            
            # Step 3: Detect table regions
            table_regions = self.table_detector.detect_tables(page, layout)
            logger.debug(f"Page {page_num}: Detected {len(table_regions)} table region(s)")
            
            # Step 4: Parse each table
            for i, region in enumerate(table_regions):
                # Check if this region is a chart
                if self.chart_guard.is_chart(region.bbox, layout):
                    chart_type = self.chart_guard.detect_chart_type(region.bbox, layout)
                    charts.append(self.chart_guard.mark_chart_region(region.bbox, chart_type))
                    continue
                
                # Parse table structure using character-level reconstruction
                matrix = self.structure_parser.parse_table(region, words, chars)
                
                if not matrix or len(matrix) < 2:
                    # Fallback: try raw text extraction
                    if self.content_healer.needs_ocr(region, words):
                        logger.warning(f"Page {page_num}, Table {i+1}: Needs OCR (skipping)")
                        continue
                    raw_text = self.content_healer.fallback_extraction(region, words)
                    if raw_text:
                        tables_md.append(f"\n**Raw Data {page_num}-{i+1}**\n```\n{raw_text}\n```\n")
                    continue
                
                # Add to successful table bboxes
                table_bboxes.append((
                    region.bbox.x0, region.bbox.y0, 
                    region.bbox.x1, region.bbox.y1
                ))
                
                # Convert to markdown
                md = self._matrix_to_markdown(matrix, page_num, i + 1, region.is_bordered)
                if md:
                    tables_md.append(md)
            
            # Step 5: If no tables found, try full-page borderless detection
            # Also force detection if digit_ratio > 50% (number-heavy page likely contains table)
            if not tables_md and not charts:
                # Check if this is a high-digit page that should be treated as table
                force_table = digit_ratio > 0.50
                
                # Try to detect any tabular structure in the entire page
                full_page_region = TableRegion(
                    bbox=BBox(0, page.height * 0.1, page.width, page.height * 0.95),
                    is_bordered=False,
                    confidence=0.5 if not force_table else 0.8
                )
                
                # Create grid from whitespace rivers
                rivers = self.vision_cortex.find_whitespace_rivers(words, page.width)
                # Lower threshold for high-digit pages (2 columns min instead of 3)
                min_rivers = 2 if force_table else 3
                if len(rivers) >= min_rivers:
                    full_page_region.grid = GridStructure(
                        vertical_lines=[
                            GridLine(r, 0, page.height, False) for r in rivers
                        ]
                    )
                    matrix = self.structure_parser.parse_table(full_page_region, words, chars)
                    if matrix and len(matrix) >= 2:
                        md = self._matrix_to_markdown(matrix, page_num, 1, False)
                        if md:
                            tables_md.append(md)
                            table_bboxes.append((
                                full_page_region.bbox.x0, full_page_region.bbox.y0, 
                                full_page_region.bbox.x1, full_page_region.bbox.y1
                            ))
        
        except Exception as e:
            logger.error(f"Page {page_num}: Neural extraction failed: {e}")
            # Return empty results on error
        
        return tables_md, charts, table_bboxes
    
    def _matrix_to_markdown(self, matrix: List[List[str]], 
                            page_num: int, table_idx: int,
                            is_bordered: bool) -> Optional[str]:
        """Convert a table matrix to Markdown format."""
        if not matrix or len(matrix) < 2:
            return None
        
        # Clean and heal cells - fix broken words like "G ü ç" -> "Güç"
        cleaned = []
        for row in matrix:
            cleaned_row = []
            for cell in row:
                # Step 1: Basic cleaning
                cell_text = str(cell).strip().replace('\n', ' ')
                # Step 2: Apply TextHealer to fix spacing issues
                if cell_text:
                    cell_text = self._text_healer.heal_document(cell_text)
                # Step 3: Escape markdown special chars
                cell_text = cell_text.replace('|', '\\|')
                cleaned_row.append(cell_text)
            cleaned.append(cleaned_row)
        
        # Ensure consistent column count
        max_cols = max(len(row) for row in cleaned)
        for row in cleaned:
            while len(row) < max_cols:
                row.append('')
        
        # Build markdown
        header = cleaned[0]
        lines = ["| " + " | ".join(header) + " |"]
        lines.append("| " + " | ".join(["---"] * max_cols) + " |")
        
        for row in cleaned[1:]:
            lines.append("| " + " | ".join(row[:max_cols]) + " |")
        
        return "\n".join(lines) + "\n"
