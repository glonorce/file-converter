from pathlib import Path
from typing import Generator, List, Optional
from dataclasses import dataclass
import pikepdf
from loguru import logger

@dataclass
class PDFChunk:
    source_path: Path
    start_page: int  # 1-indexed
    end_page: int    # 1-indexed
    temp_path: Path

class PDFLoader:
    def __init__(self, chunk_size: int = 2):  # 2 pages per chunk for granular progress
        self.chunk_size = chunk_size

    def stream_chunks(self, pdf_path: Path) -> Generator[PDFChunk, None, None]:
        """
        Yields chunks of the PDF as temporary files to avoid memory overload.
        Uses pikepdf to split efficienty without re-compressing streams.
        """
        try:
            with pikepdf.open(pdf_path) as pdf:
                total_pages = len(pdf.pages)

                for start_idx in range(0, total_pages, self.chunk_size):
                    end_idx = min(start_idx + self.chunk_size, total_pages)
                    
                    # 1-indexed range for display/logging
                    start_page = start_idx + 1
                    end_page = end_idx
                    
                    # Create a temporary subset
                    # Use a UUID-based name to prevent collisions across runs/processes
                    import uuid
                    
                    # Use Public/DocuForge/Temp instead of local temp
                    # This keeps all temp files in one place and avoids local temp pollution
                    chunk_temp_dir = Path("C:/Users/Public/DocuForge/Temp")
                    chunk_temp_dir.mkdir(parents=True, exist_ok=True)
                    
                    chunk_name = f"docuforge_{uuid.uuid4().hex}.pdf"
                    chunk_path = chunk_temp_dir / chunk_name

                    try:
                        new_pdf = pikepdf.new()
                        # Copy pages
                        for i in range(start_idx, end_idx):
                            new_pdf.pages.append(pdf.pages[i])
                        
                        new_pdf.save(chunk_path)
                        
                        # Debug: Chunk lifecycle tracking (guarded to avoid I/O when disabled)
                        from docuforge.debug import debug_log, is_debug_enabled
                        if is_debug_enabled("chunk_lifecycle"):
                            if chunk_path.exists():
                                temp_files = [f.name for f in chunk_temp_dir.iterdir()]
                                debug_log("chunk_lifecycle", "Chunk CREATED",
                                    path=str(chunk_path),
                                    size=chunk_path.stat().st_size,
                                    temp_dir_contents=temp_files)
                            else:
                                debug_log("chunk_lifecycle", "Chunk NOT CREATED", path=str(chunk_path))
                        
                        yield PDFChunk(
                            source_path=pdf_path,
                            start_page=start_page,
                            end_page=end_page,
                            temp_path=chunk_path
                        )
                    except Exception as e:
                        logger.error(f"Failed to create chunk {start_page}-{end_page}: {e}")
                    finally:
                        # The worker is responsible for unlinking this specific file.
                        pass

        except Exception as e:
            logger.error(f"Failed to open PDF {pdf_path}: {e}")
            raise e
