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
        import os
        
        cpu_count = os.cpu_count() or 4
        # Optimization: Use ~75% of cores to keep OS responsive (User suggestion)
        optimal_workers = max(1, int(cpu_count * 0.75))
        
        while True:
            workers = IntPrompt.ask(
                f"[bold green]?[/bold green] Number of Parallel Workers (Recommended: {optimal_workers}, Cores: {cpu_count})", 
                default=optimal_workers
            )
            
            # 3.1 Strict Guard for "Absurd" numbers (> 1.5x cores)
            if workers > cpu_count * 1.5:
                console.print(f"[bold red]!!! DANGER !!![/bold red] [red]You requested {workers} workers on a {cpu_count}-core system.[/red]")
                console.print("This will likely FREEZE your computer due to RAM exhaustion.")
                
                if Confirm.ask("[bold yellow]Prevent system freeze and revert to safe limits?[/bold yellow]", default=True):
                    console.print(f"[green]✓ Reverted to optimal: {optimal_workers}[/green]")
                    workers = optimal_workers
                    break
                else:
                    console.print("[bold red]Override accepted. Proceeding at your own risk...[/bold red]")
                    break 

            # 3.2 Soft Guard for High Load (> Cores)
            elif workers > cpu_count:
                 console.print(f"[yellow]Warning: {workers} workers exceeds your physical core count ({cpu_count}).[/yellow]")
                 console.print("Performance may degrade due to context switching.")
                 if Confirm.ask("Do you want to continue with this number?", default=True):
                     break
                 # If no, loop continues to ask again
            else:
                break
                
        config.workers = workers
        
        # 4. Advanced Options
        if Confirm.ask("[bold yellow]?[/bold yellow] Configure Advanced Options? (OCR, Tables, Images)", default=False):
            config.ocr.enable = Prompt.ask("OCR Mode", choices=["auto", "on", "off"], default="auto")
            config.extraction.tables_enabled = Confirm.ask("Enable Table Extraction?", default=True)
            config.extraction.images_enabled = Confirm.ask("Enable Image Extraction?", default=True)
            config.cleaning.repeated_text_ratio = float(Prompt.ask("Header/Footer Removal Sensitivity (0.0-1.0)", default="0.6"))

        console.print("\n[bold green]Configuration Ready![/bold green]")
        return config
