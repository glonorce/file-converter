# Copyright (c) 2025 GÖKSEL ÖZKAN
# Smart Content Classifier - Hybrid Table/Chart Extraction
# This software is released under the MIT License.

"""
ZoneClassifier: Intelligent content type detection for PDF regions.

Distinguishes between:
- TABLES: Grid-aligned rectangles → Extract as Markdown text
- CHARTS: Curves, diagonals, circles → Extract as PNG image

Uses geometric analysis (no GPU required).
"""

import math
from typing import List, Dict, Tuple, Optional, Literal
from dataclasses import dataclass
from pathlib import Path

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False


ContentType = Literal["TABLE", "CHART", "TEXT", "UNKNOWN"]


@dataclass
class Zone:
    """A detected region on a PDF page."""
    x0: float
    y0: float
    x1: float
    y1: float
    content_type: ContentType
    confidence: float
    objects: List[Dict]
    
    @property
    def width(self) -> float:
        return self.x1 - self.x0
    
    @property
    def height(self) -> float:
        return self.y1 - self.y0
    
    @property
    def area(self) -> float:
        return self.width * self.height
    
    @property
    def bbox(self) -> Tuple[float, float, float, float]:
        return (self.x0, self.y0, self.x1, self.y1)


class ZoneClassifier:
    """
    Classifies PDF page regions as TABLE, CHART, or TEXT.
    
    Detection Strategy:
    1. Find regions with visual elements (lines, rects, curves)
    2. Analyze geometric properties of each region
    3. Classify based on:
       - Line angles (90° only = TABLE, diagonal = CHART)
       - Shape types (rects only = TABLE, curves = CHART)
       - Text alignment (grid = TABLE, scattered = CHART)
    """
    
    # Thresholds for classification
    MIN_ZONE_AREA = 5000  # Minimum area to consider
    DIAGONAL_THRESHOLD = 5  # Max diagonal lines for TABLE
    CURVE_THRESHOLD = 0  # Any curve = CHART
    MIN_RECTS_FOR_TABLE = 2  # Minimum rects for TABLE detection
    
    def __init__(self):
        self.zones: List[Zone] = []
    
    def classify_page(self, page) -> List[Zone]:
        """
        Detect and classify all visual zones on a page.
        
        Args:
            page: pdfplumber page object
            
        Returns:
            List of Zone objects with content_type assigned
        """
        self.zones = []
        
        if not PDFPLUMBER_AVAILABLE:
            return []
        
        # Step 1: Extract all visual objects
        lines = page.lines or []
        rects = page.rects or []
        curves = page.curves or []
        
        # Step 2: Find zone boundaries (clusters of visual elements)
        all_objects = []
        
        for line in lines:
            all_objects.append({
                'type': 'line',
                'x0': line['x0'], 'y0': line['top'],
                'x1': line['x1'], 'y1': line['bottom'],
                'angle': self._calculate_angle(line)
            })
        
        for rect in rects:
            all_objects.append({
                'type': 'rect',
                'x0': rect['x0'], 'y0': rect['top'],
                'x1': rect['x1'], 'y1': rect['bottom'],
                'angle': 0
            })
        
        for curve in curves:
            # Curves are typically paths with multiple points
            if 'pts' in curve:
                pts = curve['pts']
                if pts:
                    xs = [p[0] for p in pts]
                    ys = [p[1] for p in pts]
                    all_objects.append({
                        'type': 'curve',
                        'x0': min(xs), 'y0': min(ys),
                        'x1': max(xs), 'y1': max(ys),
                        'angle': None
                    })
        
        if not all_objects:
            return []
        
        # Step 3: Cluster objects into zones
        zones = self._cluster_objects(all_objects, page.width, page.height)
        
        # Step 4: Classify each zone
        for zone in zones:
            zone.content_type = self._classify_zone(zone.objects)
            zone.confidence = self._calculate_confidence(zone)
        
        self.zones = zones
        return zones
    
    def _calculate_angle(self, line: Dict) -> float:
        """Calculate angle of a line in degrees (0-180)."""
        dx = line['x1'] - line['x0']
        dy = line['bottom'] - line['top']
        
        if dx == 0:
            return 90.0  # Vertical
        
        angle = abs(math.degrees(math.atan(dy / dx)))
        return angle
    
    def _is_axis_aligned(self, angle: float, tolerance: float = 5.0) -> bool:
        """Check if angle is horizontal (0°) or vertical (90°) within tolerance."""
        return angle <= tolerance or abs(angle - 90) <= tolerance
    
    def _cluster_objects(self, objects: List[Dict], 
                         page_width: float, page_height: float) -> List[Zone]:
        """
        Group nearby objects into zones using simple spatial clustering.
        """
        if not objects:
            return []
        
        # For simplicity, find the bounding box of all objects
        # and check if it should be split
        # This is a basic implementation - can be enhanced with DBSCAN
        
        x0 = min(obj['x0'] for obj in objects)
        y0 = min(obj['y0'] for obj in objects)
        x1 = max(obj['x1'] for obj in objects)
        y1 = max(obj['y1'] for obj in objects)
        
        # Create single zone for now
        zone = Zone(
            x0=x0, y0=y0, x1=x1, y1=y1,
            content_type="UNKNOWN",
            confidence=0.0,
            objects=objects
        )
        
        # Filter out zones that are too small
        if zone.area >= self.MIN_ZONE_AREA:
            return [zone]
        
        return []
    
    def _classify_zone(self, objects: List[Dict]) -> ContentType:
        """
        Classify a zone based on its objects.
        
        Rules:
        - Any curves → CHART
        - Many diagonal lines → CHART
        - Only axis-aligned lines + rects → TABLE
        - No visual elements → TEXT
        """
        if not objects:
            return "TEXT"
        
        # Count object types
        curves = [o for o in objects if o['type'] == 'curve']
        rects = [o for o in objects if o['type'] == 'rect']
        lines = [o for o in objects if o['type'] == 'line']
        
        diagonal_lines = [l for l in lines 
                         if l['angle'] is not None 
                         and not self._is_axis_aligned(l['angle'])]
        axis_lines = [l for l in lines 
                     if l['angle'] is not None 
                     and self._is_axis_aligned(l['angle'])]
        
        # Decision logic
        if len(curves) > self.CURVE_THRESHOLD:
            return "CHART"  # Has curves → definitely a chart
        
        if len(diagonal_lines) > self.DIAGONAL_THRESHOLD:
            return "CHART"  # Many diagonal lines → likely a chart/diagram
        
        if len(rects) >= self.MIN_RECTS_FOR_TABLE or len(axis_lines) >= 4:
            return "TABLE"  # Rectangles or axis-aligned grid → table
        
        return "UNKNOWN"
    
    def _calculate_confidence(self, zone: Zone) -> float:
        """Calculate confidence score for the classification."""
        if zone.content_type == "UNKNOWN":
            return 0.0
        
        objects = zone.objects
        curves = len([o for o in objects if o['type'] == 'curve'])
        rects = len([o for o in objects if o['type'] == 'rect'])
        
        if zone.content_type == "CHART":
            # More curves = higher confidence
            return min(0.5 + (curves * 0.1), 1.0)
        
        if zone.content_type == "TABLE":
            # More rects = higher confidence
            return min(0.5 + (rects * 0.05), 1.0)
        
        return 0.5
    
    def get_tables(self) -> List[Zone]:
        """Get all zones classified as TABLE."""
        return [z for z in self.zones if z.content_type == "TABLE"]
    
    def get_charts(self) -> List[Zone]:
        """Get all zones classified as CHART."""
        return [z for z in self.zones if z.content_type == "CHART"]


def crop_zone_to_image(pdf_path: Path, page_num: int, zone: Zone, 
                       output_path: Path, dpi: int = 150) -> Optional[Path]:
    """
    Crop a zone from a PDF page and save as PNG image.
    
    Args:
        pdf_path: Path to PDF file
        page_num: Page number (0-indexed)
        zone: Zone to crop
        output_path: Where to save the image
        dpi: Image resolution
        
    Returns:
        Path to saved image or None if failed
    """
    if not PYMUPDF_AVAILABLE:
        return None
    
    try:
        doc = fitz.open(str(pdf_path))
        page = doc[page_num]
        
        # Convert zone bbox to PyMuPDF rect
        clip = fitz.Rect(zone.x0, zone.y0, zone.x1, zone.y1)
        
        # Render page region to image
        mat = fitz.Matrix(dpi / 72, dpi / 72)  # Scale factor
        pix = page.get_pixmap(matrix=mat, clip=clip)
        
        # Save as PNG
        pix.save(str(output_path))
        
        doc.close()
        return output_path
        
    except Exception as e:
        return None


def classify_and_route(page, pdf_path: Path = None, page_num: int = 0,
                       output_dir: Path = None) -> Dict:
    """
    Main entry point: Classify page content and route to appropriate handlers.
    
    Returns:
        {
            'tables': List of Zone objects (for table extraction),
            'charts': List of (Zone, image_path) tuples,
            'text_zones': List of Zone objects
        }
    """
    classifier = ZoneClassifier()
    zones = classifier.classify_page(page)
    
    result = {
        'tables': [],
        'charts': [],
        'text_zones': []
    }
    
    for zone in zones:
        if zone.content_type == "TABLE":
            result['tables'].append(zone)
            
        elif zone.content_type == "CHART":
            if pdf_path and output_dir:
                img_name = f"chart_p{page_num}_{int(zone.x0)}_{int(zone.y0)}.png"
                img_path = output_dir / img_name
                saved = crop_zone_to_image(pdf_path, page_num, zone, img_path)
                result['charts'].append((zone, saved))
            else:
                result['charts'].append((zone, None))
                
        else:
            result['text_zones'].append(zone)
    
    return result
