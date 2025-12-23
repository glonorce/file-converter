import logging
import warnings
from pathlib import Path
from typing import Optional, List, Tuple
import pdfplumber

from docuforge.src.core.config import AppConfig
from docuforge.src.ingestion.loader import PDFChunk
from docuforge.src.core.utils import ensure_windows_temp_compatibility, SafeFileManager

# Lazy imports to avoid circular dependencies/performance hit at startup
# These will be imported inside the worker process

class PipelineController:
    """
    Centralized controller for processing PDF chunks.
    Ensures that CLI, Web API, and Workers use the IDENTICAL logic.
    """
    
    @staticmethod
    def initialize_worker():
        """
        Called once when a worker process starts.
        Sets up environment variants.
        """
        ensure_windows_temp_compatibility()
        
        # Suppress noisy warnings from PDF parsers
        warnings.filterwarnings('ignore', message='.*FontBBox.*')
        warnings.filterwarnings('ignore', message='.*Could get FontBBox.*')
        warnings.filterwarnings('ignore', message='.*non-stroke.*')
        warnings.filterwarnings('ignore', message='.*invalid float.*')
        warnings.filterwarnings('ignore', message='.*pkg_resources.*')
        
        # Suppress pdfminer and fitz logging
        logging.getLogger('pdfminer').setLevel(logging.CRITICAL)
        logging.getLogger('fitz').setLevel(logging.CRITICAL)
        
        # Redirect pdfminer stderr output (it uses print directly)
        import sys
        import io
        
        class StderrFilter:
            """Filter stderr to suppress pdfminer noise."""
            def __init__(self, original):
                self.original = original
            def write(self, msg):
                if 'Cannot set gray' not in msg and 'non-stroke' not in msg:
                    self.original.write(msg)
            def flush(self):
                self.original.flush()
        
        sys.stderr = StderrFilter(sys.stderr)

    @staticmethod
    def process_chunk(chunk: PDFChunk, config: AppConfig, doc_output_dir: Path, validated_watermarks: Optional[set] = None) -> str:
        """
        Process a single chunk of pages.
        Returns the Markdown string.
        
        Args:
            chunk: PDF chunk to process
            config: Application configuration
            doc_output_dir: Output directory for this document
            validated_watermarks: Set of watermark patterns validated by WatermarkAnalyzer
                                  (patterns that appear on >60% of pages)
        """
        # 1. Initialize Worker Environment (Idempotent-ish check)
        # In ProcessPoolExecutor, this runs every simple task if we don't use an initializer,
        # but calling it here is safe.
        PipelineController.initialize_worker()

        # 2. Local Imports (Prevent pickling issues + Circular deps)
        # Core modules - always needed
        from docuforge.src.cleaning.zones import ZoneCleaner
        from docuforge.src.cleaning.artifacts import TextCleaner
        from docuforge.src.extraction.structure import StructureExtractor
        from loguru import logger
        
        # 3. Instantiate Core Engines (always needed)
        zone_cleaner = ZoneCleaner(config.cleaning)
        text_cleaner = TextCleaner(config.cleaning, validated_watermarks=validated_watermarks)
        structure_extractor = StructureExtractor()
        
        # 4. LAZY LOADING - Only import/instantiate enabled modules
        # Tables (Legacy + Neural)
        table_extractor = None
        neural_engine = None
        if config.extraction.tables_enabled:
            from docuforge.src.extraction.tables import TableExtractor
            table_extractor = TableExtractor(config.extraction)
            
            if config.extraction.use_neural_engine:
                from docuforge.src.extraction.engine_neural import NeuralSpatialEngine
                neural_engine = NeuralSpatialEngine(config.extraction)
        
        # Images
        image_extractor = None
        if config.extraction.images_enabled:
            from docuforge.src.extraction.images import ImageExtractor
            image_extractor = ImageExtractor(config.extraction, output_dir=doc_output_dir)
        
        # Charts/Visuals
        visual_extractor = None
        if config.extraction.charts_enabled:
            from docuforge.src.extraction.visuals import VisualExtractor
            visual_extractor = VisualExtractor(config.extraction, output_dir=doc_output_dir)
        
        # OCR (only if not 'off') - CORRECT: use 'enable' not 'mode'
        smart_ocr = None
        if config.ocr.enable != 'off':
            from docuforge.src.ingestion.ocr import SmartOCR
            smart_ocr = SmartOCR(config.ocr)
        
        chunk_md_content = []
        
        try:
            # Check chunk file exists (may be deleted by race condition)
            import time
            from docuforge.debug import debug_log, is_debug_enabled
            
            # Debug: Chunk access tracking (guarded)
            if is_debug_enabled("chunk_lifecycle"):
                debug_log("chunk_lifecycle", "Chunk ACCESSING",
                    path=str(chunk.temp_path),
                    exists=chunk.temp_path.exists())
            
            if not chunk.temp_path.exists():
                # Brief retry - file might still be writing
                time.sleep(0.5)
                if not chunk.temp_path.exists():
                    if is_debug_enabled("chunk_lifecycle"):
                        debug_log("chunk_lifecycle", "Chunk MISSING AFTER RETRY",
                            path=str(chunk.temp_path))
                    from loguru import logger
                    logger.error(f"Chunk file not found: {chunk.temp_path}")
                    return f"\n\n[ERROR: Chunk file missing for pages {chunk.start_page}-{chunk.end_page}]\n"
            
            with pdfplumber.open(chunk.temp_path) as pdf:
                for i, page in enumerate(pdf.pages):
                    page_num = chunk.start_page + i
                    
                    # A. Zone Analysis
                    crop_box = zone_cleaner.get_crop_box(page)

                    # B. Smart OCR / Text Extraction (if OCR is enabled)
                    raw_text_check = page.filter(lambda obj: obj["object_type"] == "char").extract_text() or ""
                    ocr_text = smart_ocr.process_page(chunk.temp_path, i + 1, raw_text_check) if smart_ocr else None
                    
                    if ocr_text and ocr_text != raw_text_check:
                        # OCR Path
                        clean_text = text_cleaner.clean_text(ocr_text)
                        chunk_md_content.append(f"\n\n## Page {page_num}\n\n{clean_text}\n")
                        continue

                    # C. Visual Extraction (Tables, Images, Charts)
                    tables_md = []
                    charts_md = []
                    ignore_regions = []
                    
                    # C1. Try Neural-Spatial Engine First (if enabled and loaded)
                    if neural_engine and config.extraction.use_neural_engine and config.extraction.tables_enabled:
                        try:
                            # Now returns table_bboxes as third value
                            neural_tables, neural_charts, table_bboxes = neural_engine.process_page(page, page_num)
                            tables_md.extend(neural_tables)
                            ignore_regions.extend(table_bboxes)
                            
                            # Mark detected charts
                            # Mark detected charts (for visual output)
                            for chart in neural_charts:
                                if config.extraction.charts_enabled:
                                    charts_md.append(f"📊 *Chart detected on Page {page_num}* ({chart.chart_type})")
                                
                                # ALWAYS ignore chart regions in text extraction to avoid word salad
                                ignore_regions.append((chart.bbox.x0, chart.bbox.y0, chart.bbox.x1, chart.bbox.y1))
                                    
                        except Exception as e:
                            logger.warning(f"Page {page_num}: Neural engine failed, falling back: {e}")
                    
                    # C2. Fallback to Legacy Extractor (if Neural found nothing or is disabled)
                    if table_extractor and not tables_md and config.extraction.neural_fallback_to_legacy:
                        legacy_tables = table_extractor.extract_tables(chunk.temp_path, i + 1, page)
                        tables_md.extend(legacy_tables)

                    # B. Structure Extraction (Text) - Now with Masking!
                    # Pass ignore_regions (tables/charts) to prevent double extraction
                    structured_text = structure_extractor.extract_text_with_structure(page, crop_box, ignore_regions)
                    clean_text = text_cleaner.clean_text(structured_text)
                    
                    # C3. Image Extraction (if enabled)
                    images_md = image_extractor.extract_images(chunk.temp_path, i + 1) if image_extractor else []
                    
                    # C4. Chart Extraction (legacy visual extractor, if enabled and loaded)
                    if visual_extractor and config.extraction.charts_enabled and not charts_md:
                        chart_results = visual_extractor.extract_visuals(chunk.temp_path, i + 1)
                        charts_md.extend([link for link, bbox in chart_results])

                    # D. Assembly
                    page_md = f"\n\n## Page {page_num}\n"
                    if charts_md: page_md += "\n" + "\n".join(charts_md) + "\n"
                    if images_md: page_md += "\n" + "\n".join(images_md) + "\n"
                    if tables_md: page_md += "\n" + "\n".join(tables_md) + "\n"
                    page_md += f"\n{clean_text}\n"
                    
                    chunk_md_content.append(page_md)
                    
                    # CRITICAL: Memory cleanup for worker processes
                    del tables_md, charts_md, images_md, ignore_regions
                    del structured_text, clean_text, raw_text_check
                    
                    # Flush pdfplumber cache to release memory
                    try:
                        page.flush_cache()
                    except:
                        pass
                    
                    # GC every 5 pages (more aggressive for memory optimization)
                    if (i + 1) % 5 == 0:
                        import gc
                        gc.collect()
                    
        except Exception as e:
            from loguru import logger
            logger.error(f"Chunk processing failed for {chunk.source_path} (pages {chunk.start_page}-{chunk.end_page}): {e}")
            return f"\n\n[ERROR: Failed to process pages {chunk.start_page}-{chunk.end_page}: {str(e)}]\n"
        finally:
            # E. Safe Cleanup
            from docuforge.debug import debug_log, is_debug_enabled
            if is_debug_enabled("chunk_lifecycle"):
                debug_log("chunk_lifecycle", "Chunk CONTROLLER_DELETE", path=str(chunk.temp_path))
            SafeFileManager.safe_delete(chunk.temp_path)
                
        return "\n".join(chunk_md_content)

