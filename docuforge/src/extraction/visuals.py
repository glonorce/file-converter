import fitz  # PyMuPDF
import pdfplumber
from pathlib import Path
from typing import List, Tuple
from loguru import logger

class VisualExtractor:
    """
    Extracts visual elements that are NOT standard images but vector graphics 
    (Charts, Graphs, Diagrams) composed of lines, rects, and curves.
    """
    def __init__(self, config, output_dir: Path):
        self.config = config
        self.images_dir = output_dir / "images"

    def extract_visuals(self, pdf_path: Path, page_num: int) -> List[Tuple[str, Tuple[float, float, float, float]]]:
        """
        Detects vector clusters (charts) on the page and renders them as images.
        Returns list of (markdown_link, bbox).
        bbox format: (x0, top, x1, bottom)
        """
        results = []
        try:
            # 1. Detection Phase (pdfplumber)
            clusters = []
            with pdfplumber.open(pdf_path) as pdf:
                if page_num > len(pdf.pages): return []
                page = pdf.pages[page_num - 1]
                vectors = page.rects + page.lines + page.curves + page.images
                if len(vectors) < 10: return []
                clusters = self._cluster_vectors(vectors, page.width, page.height)

            # 2. Rendering Phase (PyMuPDF)
            if clusters:
                doc = fitz.open(pdf_path)
                page_fitz = doc[page_num - 1]
                
                if not self.images_dir.exists():
                    self.images_dir.mkdir(parents=True, exist_ok=True)

                for i, bbox in enumerate(clusters):
                    pad = 10
                    rect = fitz.Rect(bbox[0]-pad, bbox[1]-pad, bbox[2]+pad, bbox[3]+pad)
                    rect = rect & page_fitz.rect
                    
                    if rect.width < 50 or rect.height < 50: continue

                    mat = fitz.Matrix(2, 2)
                    pix = page_fitz.get_pixmap(matrix=mat, clip=rect)
                    
                    filename = f"chart_p{page_num}_{i+1}.png"
                    filepath = self.images_dir / filename
                    pix.save(filepath)
                    
                    rel_path = f"images/{filename}"
                    md_link = f"![Chart/Diagram]({rel_path})"
                    
                    # Store (Link, BBox)
                    # BBox is (x0, top, x1, bottom)
                    results.append((md_link, bbox))
                
                doc.close()

        except Exception as e:
            logger.warning(f"Visual extraction failed for {pdf_path} page {page_num}: {e}")
            
        return results

    def _cluster_vectors(self, vectors: List[dict], page_w, page_h) -> List[Tuple[float, float, float, float]]:
        """
        Groups vector objects into clusters based on proximity.
        Returns list of (x0, y0, x1, y1) tuples.
        """
        # Convert all to simple boxes (x0, y0, x1, y1)
        # pdfplumber rect/line/curve/image objs all have x0, top, x1, bottom (or detected via bounds)
        boxes = []
        for v in vectors:
            # Handle different object types
            if 'x0' in v and 'top' in v:
                b = (v['x0'], v['top'], v['x1'], v['bottom'])
            elif 'pts' in v: # Curve/Line sometimes needs bounds calc
                xs = [p[0] for p in v['pts']]
                ys = [p[1] for p in v['pts']]
                b = (min(xs), min(ys), max(xs), max(ys))
            else:
                continue
            boxes.append(b)

        if not boxes: return []

        # Merge intersecting or close boxes
        # Simple iterative merger
        merged = []
        tolerance = 15 # pixels gap allowed
        
        while boxes:
            # Pop one
            current = list(boxes.pop(0)) # [x0, y0, x1, y1]
            
            # Try to merge with everything else in boxes
            has_merged = True
            while has_merged:
                has_merged = False
                unmerged = []
                for other in boxes:
                    # Check overlap with tolerance
                    # Overlap logic: not (r1.x1 < r2.x0 or r1.x0 > r2.x1 ...)
                    if not (current[2] + tolerance < other[0] or 
                            current[0] - tolerance > other[2] or 
                            current[3] + tolerance < other[1] or 
                            current[1] - tolerance > other[3]):
                        
                        # Merge
                        current[0] = min(current[0], other[0])
                        current[1] = min(current[1], other[1])
                        current[2] = max(current[2], other[2])
                        current[3] = max(current[3], other[3])
                        has_merged = True
                    else:
                        unmerged.append(other)
                boxes = unmerged
            
            merged.append(tuple(current))
            
        # Filter: Remove page-sized boxes (borders) or tiny specks
        final_clusters = []
        for b in merged:
            w = b[2] - b[0]
            h = b[3] - b[1]
            
            # Explicitly ignore page borders (common in PDFs)
            if w > page_w * 0.9 and h > page_h * 0.9:
                continue
            
            # Keep if significant size (e.g. 100x100)
            if w > 100 and h > 100:
                final_clusters.append(b)
                
        return final_clusters
