from typing import List, Optional
from pathlib import Path
import camelot
import pandas as pd
from loguru import logger
from docuforge.src.core.config import ExtractionConfig

class TableExtractor:
    def __init__(self, config: ExtractionConfig):
        self.config = config

    def extract_tables(self, pdf_path: Path, page_num: int) -> List[str]:
        """
        Extracts tables from a specific page using Camelot.
        Returns a list of Markdown strings for each table.
        """
        if not self.config.tables_enabled:
            return []

        try:
            # Safe execution wrapper for Camelot
            # Camelot is fragile with temp files and ghostscript on Windows
            tables = camelot.read_pdf(
                str(pdf_path),
                pages=str(page_num),
                flavor='lattice', # Use lattice for bordered tables (most common in technical docs)
                suppress_stdout=True
            )
            
            md_tables = []
            for i, table in enumerate(tables):
                # Convert to markdown
                df = table.df
                if df.empty:
                    continue
                # Clean headers
                try:
                    md = df.to_markdown(index=False)
                    md_tables.append(f"\n**Table {page_num}-{i+1}**\n{md}\n")
                except ImportError:
                     # Fallback if tabulate/markdown specific lib missing, though pandas usually has it
                    logger.warning("Pandas markdown export failed. Is 'tabulate' installed?")
                    md_tables.append(f"\n[Table found but markdown conversion failed]\n")
                
            return md_tables

        except Exception as e:
            logger.warning(f"Table extraction failed for {pdf_path} page {page_num}: {e}")
            return []
