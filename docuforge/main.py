# Copyright (c) 2025 GÖKSEL ÖZKAN
# This software is released under the MIT License.
# https://github.com/glonorce/file-converter

import typer
from typing import Optional, List
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
from concurrent.futures import ProcessPoolExecutor, as_completed
import traceback

from docuforge.src.core.config import AppConfig
from docuforge.src.ingestion.loader import PDFLoader, PDFChunk

# Initialize outside to be picklable/global if needed, but for MP we usually re-init classes inside worker
# or pass config.

app = typer.Typer(help="DocuForge: PDF Intelligence Engine")
console = Console()

# REDEFINING THE WRAPPER CORRECTLY BEFORE THE MAIN APP
def worker_process_chunk(chunk: PDFChunk, config: AppConfig, doc_output_dir: Path) -> str:
    # FIX: Windows User Data with Non-ASCII characters (e.g. 'göksel') breaks Camelot/Ghostscript/OpenCV
    # We force the process to use a safe ASCII path for TEMP.
    import os
    import tempfile
    from pathlib import Path
    
    if os.name == 'nt':
        import ctypes
        def get_short_path(path):
            try:
                buf = ctypes.create_unicode_buffer(256)
                ret = ctypes.windll.kernel32.GetShortPathNameW(path, buf, 256)
                if ret > 0:
                    return buf.value
            except Exception as e:
                # Log but continue with original path
                pass
            return path

        current_temp = tempfile.gettempdir()
        safe_temp = current_temp
        
        if not current_temp.isascii():
            short_path = get_short_path(current_temp)
            if short_path.isascii():
                safe_temp = short_path
            else:
                public_temp = Path("C:/Users/Public/DocuForge/Temp")
                try:
                    public_temp.mkdir(parents=True, exist_ok=True)
                    safe_temp = str(public_temp)
                except Exception:
                    pass
                    
        if safe_temp != current_temp and safe_temp.isascii():
            os.environ["TEMP"] = safe_temp
            os.environ["TMP"] = safe_temp
            tempfile.tempdir = safe_temp

    # Suppress noisy FontBBox warnings from pdfminer (must be before pdfplumber import)
    import warnings
    warnings.filterwarnings('ignore', message='.*FontBBox.*')
    warnings.filterwarnings('ignore', message='.*Could get FontBBox.*')
    # Also suppress the specific pdfminer messages via logging
    import logging
    logging.getLogger('pdfminer').setLevel(logging.ERROR)

    import pdfplumber
    from docuforge.src.cleaning.zones import ZoneCleaner
    from docuforge.src.cleaning.artifacts import TextCleaner
    from docuforge.src.extraction.tables import TableExtractor
    from docuforge.src.extraction.images import ImageExtractor
    from docuforge.src.extraction.visuals import VisualExtractor  # NEW: Chart extraction
    from docuforge.src.extraction.structure import StructureExtractor
    from docuforge.src.ingestion.ocr import SmartOCR
    
    zone_cleaner = ZoneCleaner(config.cleaning)
    text_cleaner = TextCleaner(config.cleaning)
    table_extractor = TableExtractor(config.extraction)
    structure_extractor = StructureExtractor()
    smart_ocr = SmartOCR(config.ocr)
    
    image_extractor = ImageExtractor(config.extraction, output_dir=doc_output_dir)
    visual_extractor = VisualExtractor(config.extraction, output_dir=doc_output_dir)  # NEW
    
    chunk_md_content = []
    
    try:
        with pdfplumber.open(chunk.temp_path) as pdf:
            for i, page in enumerate(pdf.pages):
                page_num = chunk.start_page + i
                
                # Operations
                crop_box = zone_cleaner.get_crop_box(page)

                # 1.5 Smart OCR Check
                raw_text_check = page.filter(lambda obj: obj["object_type"] == "char").extract_text() or ""
                ocr_text = smart_ocr.process_page(chunk.temp_path, i + 1, raw_text_check)
                
                if ocr_text != raw_text_check:
                    # OCR was triggered
                    clean_text = text_cleaner.clean_text(ocr_text)
                    chunk_md_content.append(f"\n\n## Page {page_num} (OCR)\n\n{clean_text}\n")
                    continue

                structured_text = structure_extractor.extract_text_with_structure(page, crop_box)
                clean_text = text_cleaner.clean_text(structured_text)
                
                # Pass page object to table extractor for reuse
                tables_md = table_extractor.extract_tables(chunk.temp_path, i + 1, page)
                images_md = image_extractor.extract_images(chunk.temp_path, i + 1)
                
                # NEW: Extract charts and graphs
                charts_md = []
                if config.extraction.charts_enabled:
                    chart_results = visual_extractor.extract_visuals(chunk.temp_path, i + 1)
                    charts_md = [link for link, bbox in chart_results]

                # Assembly
                page_md = f"\n\n## Page {page_num}\n"
                if charts_md: page_md += "\n" + "\n".join(charts_md) + "\n"  # Charts first
                if images_md: page_md += "\n" + "\n".join(images_md) + "\n"
                if tables_md: page_md += "\n" + "\n".join(tables_md) + "\n"
                page_md += f"\n{clean_text}\n"
                
                chunk_md_content.append(page_md)
    except Exception as e:
        # SEC-P1-001: Log errors instead of silently swallowing
        from loguru import logger
        logger.error(f"Chunk processing failed for {chunk.source_path} (pages {chunk.start_page}-{chunk.end_page}): {e}")
        return f"\n\n[ERROR: Failed to process pages {chunk.start_page}-{chunk.end_page}: {str(e)}]\n"
    finally:
        if chunk.temp_path.exists():
            import time
            import os
            # Retry mechanism for Windows file locking
            for attempt in range(5):
                try:
                    chunk.temp_path.unlink()
                    break
                except PermissionError:
                    time.sleep(0.5)
                except Exception:
                    break
                
    return "\n".join(chunk_md_content)


@app.command()
def convert(
    input_dir: Optional[Path] = typer.Option(None, "--input", "-i", help="Directory containing PDFs"),
    output_dir: Optional[Path] = typer.Option(None, "--output", "-o", help="Directory for output Markdown"),
    config_path: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to config.yaml"),
    workers: int = typer.Option(4, "--workers", "-w", help="Number of parallel workers"),
):
    """
    Convert a batch of PDFs to Markdown.
    Runs in Interactive Wizard mode if no arguments are provided.
    """
    # 1. Load Base Config
    if config_path:
        config = AppConfig.load(config_path)
    else:
        config = AppConfig()

    # 2. Interactive Mode if no input provided
    if input_dir is None:
        from docuforge.src.interface.interactive import InteractiveWizard
        wizard = InteractiveWizard()
        try:
            config = wizard.run()
            # Sync local vars for main loop validation
            input_dir = config.input_dir
            output_dir = config.output_dir
            workers = config.workers
        except KeyboardInterrupt:
            raise typer.Exit()
    else:
        # Override config with CLI args
        config.input_dir = input_dir
        if output_dir:
            config.output_dir = output_dir
        config.workers = workers

    # 3. Validation
    if not config.input_dir or not config.input_dir.exists():
        console.print(f"[bold red]Error:[/bold red] Input directory {config.input_dir} does not exist.")
        raise typer.Exit(code=1)
    
    # Use config values for the rest of flow
    input_dir = config.input_dir
    output_dir = config.output_dir
    if not output_dir:
        output_dir = input_dir / "output"
        config.output_dir = output_dir

    output_dir.mkdir(parents=True, exist_ok=True)
    
    console.print(f"[bold green]DocuForge initialized![/bold green]")
    console.print(f"Input: {input_dir}")
    console.print(f"Output: {output_dir}")
    console.print(f"Workers: {workers}")

    # Initialize Loader
    # chunk_size=2 gives granular progress feedback (every 2 pages)
    loader = PDFLoader(chunk_size=2) 
    
    pdfs = list(input_dir.glob("*.pdf"))
    if not pdfs:
        console.print("[yellow]No PDFs found in input directory.[/yellow]")
        return
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console
    ) as progress:
        
        main_task = progress.add_task(f"[green]Total Processing ({len(pdfs)} files)", total=len(pdfs))
        
        for pdf_path in pdfs:
            progress.update(main_task, description=f"[green]Processing: {pdf_path.name}")
            
            # Context dir for assets (images/tables) if needed
            # We do NOT create it upfront anymore.
            doc_context_dir = output_dir / pdf_path.stem
            
            # Prepare chunks
            chunks = list(loader.stream_chunks(pdf_path))
            file_task = progress.add_task(f"  {pdf_path.name}", total=len(chunks))
            
            doc_full_md = []
            
            # Parallel Execution
            with ProcessPoolExecutor(max_workers=workers) as executor:
                # Submit all chunks
                # We map future -> (start_page) so we can sort results later!
                futures = {
                    executor.submit(worker_process_chunk, chunk, config, doc_context_dir): chunk.start_page 
                    for chunk in chunks
                }
                
                results = []
                for future in as_completed(futures):
                    start_page = futures[future]
                    try:
                        res = future.result()
                        results.append((start_page, res))
                    except Exception as e:
                        console.print(f"[red]Error in chunk starting page {start_page}: {e}[/red]")
                    
                    progress.advance(file_task)
            
            # Sort results by page number to maintain order!
            results.sort(key=lambda x: x[0])
            doc_full_md = [r[1] for r in results]
            
            if doc_full_md:
                final_md = "\n".join(doc_full_md)
                # Flat output: output_dir / filename.md
                (output_dir / f"{pdf_path.stem}.md").write_text(final_md, encoding="utf-8")
            
            progress.remove_task(file_task)
            progress.advance(main_task)
            
    console.print(f"[bold green]Batch Completed! Output at: {output_dir}[/bold green]")

@app.command()
def web():
    """
    Launch the Web Interface & API Server (Localhost).
    """
    console.print(Panel.fit(
        "[bold cyan]DocuForge Web Server[/bold cyan]\n"
        "[green]http://127.0.0.1:8000[/green]\n"
        "[dim]Press Ctrl+C to stop[/dim]",
        border_style="cyan"
    ))
    
    try:
        from docuforge.api import start_server
        start_server()
    except ImportError:
        console.print("[bold red]Error: Web dependencies missing![/bold red]")
        console.print("Please run: [yellow]pip install fastapi uvicorn python-multipart[/yellow]")

if __name__ == "__main__":
    # PATCH: Suppress annoying Windows PermissionError on exit due to file locking
    # This happens when background libs (Camelot/Ghostscript) hold file handles during cleanup
    import shutil
    import os
    
    if os.name == 'nt':
        original_rmtree = shutil.rmtree
        def safe_rmtree(path, ignore_errors=False, onerror=None, **kwargs):
            try:
                original_rmtree(path, ignore_errors=True, onerror=None, **kwargs)
            except Exception:
                pass
        shutil.rmtree = safe_rmtree

    app()
