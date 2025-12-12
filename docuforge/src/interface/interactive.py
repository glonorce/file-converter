import typer
from rich.console import Console
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.panel import Panel
from pathlib import Path
from docuforge.src.core.config import AppConfig

console = Console()

class InteractiveWizard:
    def run(self) -> AppConfig:
        console.clear()
        console.print(Panel.fit(
            "[bold cyan]DocuForge Intelligence Engine[/bold cyan]\n"
            "[dim]Batch PDF to Markdown Converter[/dim]",
            border_style="cyan"
        ))
        
        config = AppConfig()
        
        # 1. Input Directory
        while True:
            path_str = Prompt.ask("[bold green]?[/bold green] Input Directory (containing PDFs)")
            path = Path(path_str)
            if path.exists() and path.is_dir():
                config.input_dir = path
                break
            console.print("[red]Error: Directory does not exist![/red]")

        # 2. Output Directory
        default_out = config.input_dir / "output"
        out_str = Prompt.ask("[bold green]?[/bold green] Output Directory", default=str(default_out))
        config.output_dir = Path(out_str)
        
        # 3. Worker Threads
        config.workers = IntPrompt.ask("[bold green]?[/bold green] Number of Parallel Workers", default=4)
        
        # 4. Advanced Options
        if Confirm.ask("[bold yellow]?[/bold yellow] Configure Advanced Options? (OCR, Tables, Images)", default=False):
            config.ocr.enable = Prompt.ask("OCR Mode", choices=["auto", "on", "off"], default="auto")
            config.extraction.tables_enabled = Confirm.ask("Enable Table Extraction?", default=True)
            config.extraction.images_enabled = Confirm.ask("Enable Image Extraction?", default=True)
            config.cleaning.repeated_text_ratio = float(Prompt.ask("Header/Footer Removal Sensitivity (0.0-1.0)", default="0.6"))

        console.print("\n[bold green]Configuration Ready![/bold green]")
        return config
