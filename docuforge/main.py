# Copyright (c) 2025 GÖKSEL ÖZKAN
# This software is released under the MIT License.
# https://github.com/glonorce/file-converter

import typer
from typing import Optional, List
from pathlib import Path
from rich.console import Console
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
    import pdfplumber
    from docuforge.src.cleaning.zones import ZoneCleaner
    from docuforge.src.cleaning.artifacts import TextCleaner
    from docuforge.src.extraction.tables import TableExtractor
    from docuforge.src.extraction.images import ImageExtractor
    from docuforge.src.extraction.structure import StructureExtractor
    from docuforge.src.ingestion.ocr import SmartOCR
    
    zone_cleaner = ZoneCleaner(config.cleaning)
    text_cleaner = TextCleaner(config.cleaning)
    table_extractor = TableExtractor(config.extraction)
    structure_extractor = StructureExtractor()
    smart_ocr = SmartOCR(config.ocr)
    
    image_extractor = ImageExtractor(config.extraction, output_dir=doc_output_dir)
    
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
                tables_md = table_extractor.extract_tables(chunk.temp_path, i + 1)
                images_md = image_extractor.extract_images(chunk.temp_path, i + 1)

                # Assembly
                page_md = f"\n\n## Page {page_num}\n"
                if images_md: page_md += "\n" + "\n".join(images_md) + "\n"
                if tables_md: page_md += "\n" + "\n".join(tables_md) + "\n"
                page_md += f"\n{clean_text}\n"
                
                chunk_md_content.append(page_md)
    except Exception as e:
        # return output so main thread can log it?
        return ""
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
    # chunk_size=10 gives better progress feedback and lower memory footprint per worker
    loader = PDFLoader(chunk_size=10) 
    
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

if __name__ == "__main__":
    app()
