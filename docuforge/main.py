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
from docuforge.src.core.controller import PipelineController
from docuforge.src.core.controller import PipelineController
from docuforge.src.core.utils import SafeFileManager
from loguru import logger
import sys

# Configure Logger: clean output for user
logger.remove()
logger.add(sys.stderr, level="INFO")

app = typer.Typer(help="DocuForge: PDF Intelligence Engine")
console = Console()

@app.command()
def convert(
    input_dir: Optional[Path] = typer.Option(None, "--input", "-i", help="Directory containing PDFs"),
    output_dir: Optional[Path] = typer.Option(None, "--output", "-o", help="Directory for output Markdown"),
    config_path: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to config.yaml"),
    workers: int = typer.Option(4, "--workers", "-w", help="Number of parallel workers"),
    charts: bool = typer.Option(False, "--charts", help="Enable chart extraction (Experimental/Irregular support)"),
    recursive: bool = typer.Option(False, "--recursive", "-r", help="Analyze subdirectories recursively"),
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
        config.output_dir = output_dir or input_dir
        config.workers = workers
        config.extraction.charts_enabled = charts
        config.extraction.recursive = recursive

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
    loader = PDFLoader(chunk_size=50) 
    
    # 5. Recursive Scanning
    if config.extraction.recursive:
        pdfs = list(input_dir.rglob("*.pdf"))
    else:
        pdfs = list(input_dir.glob("*.pdf"))
        
    if not pdfs:
        console.print("[yellow]No PDFs found in input directory.[/yellow]")
        return
    
    total_pdfs = len(pdfs)
    console.print(f"Total Files to Process: [bold cyan]{total_pdfs}[/bold cyan]")
    
    # Suppress loguru console output to keep TUI clean
    from loguru import logger
    logger.remove()
    logger.add(lambda msg: None, level="INFO") # Swallow INFO logs
    # Optional: Log errors to file if needed, but keep console clean
    
    # Custom Progress Columns
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
        transient=True # Clear bars after completion
    ) as progress:
        
        main_task = progress.add_task(f"[green]Total Batch", total=total_pdfs)
        file_task = progress.add_task(f"Waiting...", total=100, visible=False) # Reuse this task
        
        for idx, pdf_path in enumerate(pdfs, 1):
            progress.update(main_task, description=f"[green]Total Batch [{idx}/{total_pdfs}]")
            
            # Smart Output Path
            if config.extraction.recursive:
                try:
                    rel_path = pdf_path.relative_to(input_dir).parent
                    target_dir = output_dir / rel_path
                except ValueError:
                    target_dir = output_dir
            else:
                target_dir = output_dir
                
            target_dir.mkdir(parents=True, exist_ok=True)
            doc_context_dir = target_dir / pdf_path.stem
            
            # Prepare chunks
            progress.update(file_task, description=f"[cyan]Reading: {pdf_path.name}", visible=True, total=None) # Indeterminate while reading
            chunks = list(loader.stream_chunks(pdf_path))
            total_chunks = len(chunks)
            
            progress.update(file_task, description=f"[cyan]Processing: {pdf_path.name}", total=total_chunks, completed=0)
            
            doc_full_md = []
            
            # Parallel Execution
            with ProcessPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(PipelineController.process_chunk, chunk, config, doc_context_dir): chunk.start_page 
                    for chunk in chunks
                }
                
                results = []
                for future in as_completed(futures):
                    start_page = futures[future]
                    try:
                        res = future.result()
                        results.append((start_page, res))
                    except Exception as e:
                        # Log error but don't break UI
                        pass 
                    
                    progress.advance(file_task)
            
            # Sort results
            results.sort(key=lambda x: x[0])
            doc_full_md = [r[1] for r in results]
            
            if doc_full_md:
                final_md = "\n".join(doc_full_md)
                (target_dir / f"{pdf_path.stem}.md").write_text(final_md, encoding="utf-8")
            
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
    # PATCH: Apply safe shutil patch globally for main process
    SafeFileManager.patch_shutil_for_windows()
    # CLEANUP: Remove orphaned temp files from previous runs
    SafeFileManager.cleanup_global_temp()
    app()
