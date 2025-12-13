# Copyright (c) 2025 GÖKSEL ÖZKAN
# Multi-strategy Table Extraction Module

from typing import List, Optional, Tuple
from pathlib import Path
import warnings
import pdfplumber
from loguru import logger
from docuforge.src.core.config import ExtractionConfig

# Suppress noisy FontBBox warnings from pdfminer
warnings.filterwarnings('ignore', message='.*FontBBox.*')
warnings.filterwarnings('ignore', message='.*Could get FontBBox.*')


class TableExtractor:
    """
    Hybrid table extraction using multiple strategies:
    1. pdfplumber (fast, no external deps)
    2. Camelot lattice (bordered tables)
    3. Camelot stream (borderless tables)
    """
    
    def __init__(self, config: ExtractionConfig):
        self.config = config
        self._camelot_available = None
    
    def _check_camelot(self) -> bool:
        """Lazy check if Camelot is available"""
        if self._camelot_available is None:
            try:
                import camelot
                self._camelot_available = True
            except ImportError:
                logger.warning("Camelot not available, using pdfplumber only")
                self._camelot_available = False
        return self._camelot_available

    def extract_tables(self, pdf_path: Path, page_num: int, page: pdfplumber.page.Page = None) -> List[str]:
        """
        Extract tables using multi-strategy approach.
        
        Args:
            pdf_path: Path to PDF file
            page_num: 1-indexed page number
            page: Optional pdfplumber page object (reuse if available)
        
        Returns:
            List of Markdown table strings
        """
        if not self.config.tables_enabled:
            return []
        
        all_tables = []
        
        # Strategy 1: Try Camelot FIRST (better for complex bordered tables)
        # Camelot handles merged cells and wide tables more reliably
        if self._check_camelot():
            camelot_tables = self._extract_camelot(pdf_path, page_num)
            if camelot_tables:
                all_tables.extend(camelot_tables)
        
        # Strategy 2: pdfplumber fallback (for simpler tables or if Camelot unavailable)
        if not all_tables:
            pdfplumber_tables = self._extract_pdfplumber(pdf_path, page_num, page)
            if pdfplumber_tables:
                all_tables.extend(pdfplumber_tables)
        
        return all_tables

    def _extract_pdfplumber(self, pdf_path: Path, page_num: int, page: pdfplumber.page.Page = None) -> List[str]:
        """Extract tables using pdfplumber's built-in table detection"""
        try:
            if page is None:
                with pdfplumber.open(pdf_path) as pdf:
                    if page_num > len(pdf.pages):
                        return []
                    page = pdf.pages[page_num - 1]
                    return self._process_pdfplumber_page(page, page_num)
            else:
                return self._process_pdfplumber_page(page, page_num)
        except Exception as e:
            logger.debug(f"pdfplumber table extraction failed: {e}")
            return []
    
    def _process_pdfplumber_page(self, page: pdfplumber.page.Page, page_num: int) -> List[str]:
        """Process a single page for tables with strict validation"""
        md_tables = []
        
        # FIXED: Use 'lines' strategy instead of 'text' to only detect bordered tables
        # 'text' strategy was too aggressive, detecting paragraphs as tables
        table_settings = {
            "vertical_strategy": "lines",  # Changed from 'text'
            "horizontal_strategy": "lines",  # Changed from 'text'
            "snap_tolerance": 5,
            "join_tolerance": 5,
            "edge_min_length": 10,
        }
        
        tables = page.extract_tables(table_settings=table_settings)
        
        for i, table in enumerate(tables):
            # Validate table structure
            if not self._is_valid_table(table):
                continue
            
            md = self._table_to_markdown(table, page_num, i + 1)
            if md:
                md_tables.append(md)
        
        return md_tables
    
    def _is_valid_table(self, table: List[List[str]]) -> bool:
        """
        Validate that a detected table is actually a table, not regular text.
        Returns False for false positives.
        """
        if not table:
            return False
        
        # Need at least 2 rows (header + data)
        if len(table) < 2:
            return False
        
        # Need at least 2 columns (otherwise it's just a list)
        if not table[0] or len(table[0]) < 2:
            return False
        
        # Check column consistency - all rows should have similar column count
        col_counts = [len(row) for row in table if row]
        if not col_counts:
            return False
        
        # If column counts vary too much, it's probably not a real table
        min_cols, max_cols = min(col_counts), max(col_counts)
        if max_cols > min_cols * 2:  # More than 2x variance
            return False
        
        # Check cell density - if >50% cells are empty, probably not a table
        total_cells = sum(len(row) for row in table if row)
        empty_cells = sum(1 for row in table if row for cell in row if not cell or not str(cell).strip())
        if total_cells > 0 and empty_cells / total_cells > 0.5:
            return False
        
        return True
    
    def _extract_camelot(self, pdf_path: Path, page_num: int) -> List[str]:
        """Extract tables using Camelot with lattice -> stream fallback"""
        import camelot
        
        md_tables = []
        
        # Try lattice first (bordered tables)
        try:
            tables = camelot.read_pdf(
                str(pdf_path),
                pages=str(page_num),
                flavor='lattice',
                suppress_stdout=True
            )
            
            for i, table in enumerate(tables):
                # Check accuracy score
                if table.accuracy >= self.config.min_table_accuracy * 100:
                    md = self._dataframe_to_markdown(table.df, page_num, i + 1, "lattice")
                    if md:
                        md_tables.append(md)
                else:
                    pass  # Table below accuracy threshold
                    
        except Exception:
            pass  # Camelot lattice failed, will try stream fallback
        
        # Try stream if lattice found nothing and fallback is enabled
        if not md_tables and self.config.table_fallback_stream:
            try:
                tables = camelot.read_pdf(
                    str(pdf_path),
                    pages=str(page_num),
                    flavor='stream',
                    suppress_stdout=True
                )
                
                for i, table in enumerate(tables):
                    if table.accuracy >= self.config.min_table_accuracy * 100:
                        md = self._dataframe_to_markdown(table.df, page_num, i + 1, "stream")
                        if md:
                            md_tables.append(md)
                            
            except Exception:
                pass  # Camelot stream failed
        
        return md_tables
    
    def _table_to_markdown(self, table: List[List[str]], page_num: int, table_idx: int) -> Optional[str]:
        """Convert a 2D list table to Markdown format"""
        if not table or len(table) < 2:
            return None
        
        # Clean cells
        cleaned = []
        for row in table:
            cleaned_row = [str(cell).strip().replace('\n', ' ') if cell else '' for cell in row]
            cleaned.append(cleaned_row)
        
        # Build markdown
        header = cleaned[0]
        num_cols = len(header)
        
        lines = []
        lines.append(f"\n**Table {page_num}-{table_idx}**\n")
        lines.append("| " + " | ".join(header) + " |")
        lines.append("| " + " | ".join(["---"] * num_cols) + " |")
        
        for row in cleaned[1:]:
            # Pad row if needed
            while len(row) < num_cols:
                row.append('')
            lines.append("| " + " | ".join(row[:num_cols]) + " |")
        
        return "\n".join(lines) + "\n"
    
    def _dataframe_to_markdown(self, df, page_num: int, table_idx: int, method: str) -> Optional[str]:
        """Convert pandas DataFrame to Markdown"""
        if df.empty:
            return None
        
        try:
            md = df.to_markdown(index=False)
            return f"\n**Table {page_num}-{table_idx}** _{method}_\n{md}\n"
        except ImportError:
            # Fallback without tabulate
            return self._table_to_markdown(df.values.tolist(), page_num, table_idx)
        except Exception as e:
            logger.debug(f"DataFrame to markdown failed: {e}")
            return None
