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

        # 1.1 Recursive Option (Moved per user request)
        if Confirm.ask("[bold green]?[/bold green] Enable Recursive Processing (Include subfolders)?", default=False):
            config.extraction.recursive = True
        
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
        if Confirm.ask("[bold yellow]?[/bold yellow] Configure Advanced Options? (OCR, Tables, Images, Charts)", default=False):
            config.ocr.enable = Prompt.ask("OCR Mode", choices=["auto", "on", "off"], default="auto")
            config.extraction.tables_enabled = Confirm.ask("Enable Table Extraction?", default=True)
            config.extraction.images_enabled = Confirm.ask("Enable Image Extraction?", default=False)
            config.extraction.charts_enabled = Confirm.ask("Enable Chart Extraction (Experimental)?", default=False) 
            config.cleaning.repeated_text_ratio = float(Prompt.ask("Header/Footer Removal Sensitivity (0.0-1.0)", default="0.6"))

        if Confirm.ask("[bold yellow]?[/bold yellow] Configure Removable Tags? (e.g., 'Watermark')", default=False):
            tag_result = self._manage_tags()
            console.print(f"[green]✓ Tag settings saved ({tag_result} custom tags)[/green]")
        
        console.print("\n[bold green]Configuration Ready![/bold green]")
        return config
    
    def _manage_tags(self) -> int:
        """Interactive tag management menu. Returns tag count."""
        from docuforge.src.core.tag_manager import TagManager
        
        manager = TagManager()
        
        while True:
            menu_lines = [
                "",
                "[bold cyan]Tag Management:[/bold cyan]",
                "  [1] View current tags",
                "  [2] Add new tag",
                "  [3] Remove tag",
                "  [4] Save & Continue"
            ]
            for line in menu_lines:
                console.print(line)
            
            choice = Prompt.ask("Select option", choices=["1", "2", "3", "4"], default="4")
            
            if choice == "1":
                # View tags
                tags = manager.list_tags()
                if not tags:
                    console.print("[yellow]No custom tags defined.[/yellow]")
                else:
                    console.print("[cyan]Current tags:[/cyan]")
                    for i, tag in enumerate(tags, 1):
                        console.print(f"  {i}. {tag}")
            
            elif choice == "2":
                # Add tag
                pattern = Prompt.ask("Enter tag pattern to remove")
                if pattern.strip():
                    if manager.add_tag(pattern.strip()):
                        console.print(f"[green]✓ Added: {pattern}[/green]")
                    else:
                        console.print(f"[yellow]Already exists: {pattern}[/yellow]")
            
            elif choice == "3":
                # Remove tag
                tags = manager.list_tags()
                if not tags:
                    console.print("[yellow]No tags to remove.[/yellow]")
                else:
                    console.print("[cyan]Current tags:[/cyan]")
                    for i, tag in enumerate(tags, 1):
                        console.print(f"  {i}. {tag}")
                    
                    idx_str = Prompt.ask("Enter tag number to remove")
                    try:
                        idx = int(idx_str)
                        if 1 <= idx <= len(tags):
                            removed = tags[idx - 1]
                            manager.remove_tag(removed)
                            console.print(f"[green]✓ Removed: {removed}[/green]")
                        else:
                            console.print("[red]Invalid number.[/red]")
                    except ValueError:
                        console.print("[red]Please enter a number.[/red]")
            
            elif choice == "4":
                # Save & Continue
                return len(manager.list_tags())

