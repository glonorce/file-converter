import shutil
import tempfile
import os
import logging
import asyncio
import json
from pathlib import Path
from typing import List, Optional, AsyncGenerator
from concurrent.futures import ProcessPoolExecutor, as_completed
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn
import tkinter as tk
from tkinter import filedialog

# Suppress noisy PDFMiner warnings
logging.getLogger("pdfminer").setLevel(logging.ERROR)

from docuforge.src.core.config import AppConfig
from docuforge.src.ingestion.loader import PDFLoader
# NEW: Import Centralized Controller
from docuforge.src.core.controller import PipelineController

# STARTUP: Clean up orphaned temp files from previous runs
def _startup_cleanup():
    """Clean orphaned temp files from previous/crashed runs."""
    import glob
    from docuforge.src.core.utils import SafeFileManager
    
    # Clean Public/DocuForge/Temp (chunk PDFs + PNG files from Ghostscript)
    SafeFileManager.cleanup_global_temp()
    
    # Also clean any orphaned files in local temp (legacy cleanup)
    temp_dir = tempfile.gettempdir()
    for f in glob.glob(os.path.join(temp_dir, "docuforge_*.pdf")):
        try:
            os.unlink(f)
        except Exception:
            pass

# EXIT: Clean up all temp files when application closes
def _exit_cleanup():
    """Clean all temp files when application closes."""
    import time
    import shutil
    
    temp_dir = Path("C:/Users/Public/DocuForge/Temp")
    
    def clean_dir():
        if temp_dir.exists():
            try:
                shutil.rmtree(temp_dir)
                temp_dir.mkdir(parents=True, exist_ok=True)
            except:
                for f in temp_dir.iterdir():
                    try:
                        f.unlink()
                    except:
                        pass
    
    # First cleanup
    clean_dir()
    # Wait for late file writes
    time.sleep(2)
    # Second cleanup (catches files written during delay)
    clean_dir()

import atexit
atexit.register(_exit_cleanup)

# Background cleanup thread - runs every 2 seconds
_cleanup_running = True
def _background_cleanup():
    """Background thread that cleans PNG temp files every 2 seconds.
    
    NOTE: Only cleans PNG files (from Ghostscript/pdf2image).
    PDF chunks (docuforge_*.pdf) are NOT cleaned here - they're cleaned
    after each chunk is processed by the worker.
    """
    import time
    from pathlib import Path
    
    temp_dir = Path("C:/Users/Public/DocuForge/Temp")
    
    while _cleanup_running:
        try:
            if temp_dir.exists():
                now = time.time()
                for f in temp_dir.iterdir():
                    try:
                        # Only clean PNG files (Ghostscript output)
                        # Do NOT clean PDF chunks - workers need them
                        if f.suffix.lower() == '.png' and now - f.stat().st_mtime > 10:
                            f.unlink()
                    except:
                        pass
        except:
            pass
        time.sleep(2)

# Start cleanup thread
import threading
_cleanup_thread = threading.Thread(target=_background_cleanup, daemon=True)
_cleanup_thread.start()

_startup_cleanup()

app = FastAPI(title="DocuForge API", version="2.1.0")

# SEC-P0-001: Restricted CORS to localhost only
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Accept"],
)

static_dir = Path(__file__).parent / "web"

# --- Cancellation Support ---
_cancel_requested = False
_active_executor = None  # Global reference to current executor

@app.post("/api/cancel")
def cancel_processing():
    """Cancel current processing - IMMEDIATELY kills ALL worker processes."""
    global _cancel_requested, _active_executor
    _cancel_requested = True
    
    killed_count = 0
    
    # Suppress stderr to prevent terminal pollution from killed processes
    import sys
    import io
    old_stderr = sys.stderr
    sys.stderr = io.StringIO()
    
    try:
        # Method 1: Try executor._processes
        if _active_executor is not None:
            try:
                for pid, proc in list(_active_executor._processes.items()):
                    try:
                        proc.kill()
                        killed_count += 1
                    except:
                        pass
                _active_executor.shutdown(wait=False, cancel_futures=True)
                _active_executor = None
            except:
                pass
        
        # Method 2: Use psutil to kill ALL child processes (more reliable on Windows)
        try:
            import psutil
            current_process = psutil.Process(os.getpid())
            children = current_process.children(recursive=True)
            for child in children:
                try:
                    child.kill()
                    killed_count += 1
                except:
                    pass
        except ImportError:
            pass  # psutil not installed
        except:
            pass
    finally:
        # Restore stderr
        sys.stderr = old_stderr
    
    # Background temp cleanup - retry for 30 seconds (processes need time to release files)
    def cleanup_temp():
        import time
        import datetime
        temp_dir = Path("C:/Users/Public/DocuForge/Temp")
        for attempt in range(30):  # Try for 30 seconds
            if temp_dir.exists():
                remaining = list(temp_dir.iterdir())
                for f in remaining:
                    try:
                        f.unlink()
                    except:
                        pass
                # Check if clean
                if not list(temp_dir.iterdir()):
                    break  # All cleaned, stop early
            time.sleep(1)
    
    cleanup_thread = threading.Thread(target=cleanup_temp, daemon=True)
    cleanup_thread.start()
    
    return {"status": "cancelled", "killed": killed_count}

# --- API Routes ---

@app.get("/api/info")
def get_system_info():
    count = os.cpu_count() or 4
    return {
        "cpu_count": count,
        "optimal_workers": max(1, int(count * 0.75))
    }

# --- Tag Management API ---

@app.get("/api/tags")
def list_tags():
    """Get all user-defined removable tags."""
    from docuforge.src.core.tag_manager import TagManager
    manager = TagManager()
    return {"tags": manager.list_tags()}

@app.post("/api/tags")
def add_tag(pattern: str = Form(...)):
    """Add a new removable tag pattern."""
    from docuforge.src.core.tag_manager import TagManager
    manager = TagManager()
    
    if not pattern.strip():
        raise HTTPException(status_code=400, detail="Pattern cannot be empty")
    
    if manager.add_tag(pattern.strip()):
        return {"success": True, "message": f"Added: {pattern}"}
    else:
        return {"success": False, "message": f"Already exists: {pattern}"}

@app.delete("/api/tags")
def remove_tag(pattern: str = Form(...)):
    """Remove a tag pattern."""
    from docuforge.src.core.tag_manager import TagManager
    manager = TagManager()
    
    if manager.remove_tag(pattern):
        return {"success": True, "message": f"Removed: {pattern}"}
    else:
        raise HTTPException(status_code=404, detail=f"Pattern not found: {pattern}")

# --- MD Viewer API ---

class RenderMdRequest(BaseModel):
    content: str
    filename: str = "document"

@app.post("/api/render-md")
def render_markdown(request: RenderMdRequest):
    """
    Render markdown content as styled HTML.
    Same styling as view_markdown but accepts content directly.
    """
    import markdown
    
    md_content = request.content
    file_name = request.filename.replace('.md', '')
    
    # Convert MD to HTML with extensions
    html_content = markdown.markdown(md_content, extensions=['tables', 'fenced_code', 'toc'])
    
    # Wrap tables in responsive container
    html_content = html_content.replace('<table>', '<div class="table-responsive"><table>')
    html_content = html_content.replace('</table>', '</table></div>')
    
    # Full styled HTML page (same as view_markdown)
    html_page = f'''<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{file_name} - DocuForge</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: linear-gradient(135deg, #0f0f23 0%, #1a1a2e 100%);
            color: #e0e0e0;
            padding: 40px;
            line-height: 1.8;
            min-height: 100vh;
        }}
        .container {{
            max-width: 95vw;
            margin: 0 auto;
            background: rgba(26, 26, 46, 0.9);
            border: 1px solid rgba(99, 102, 241, 0.3);
            border-radius: 16px;
            padding: 40px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        }}
        h1, h2, h3, h4 {{ color: #a78bfa; margin: 1em 0 0.5em; }}
        h1 {{ font-size: 2em; border-bottom: 2px solid #6366f1; padding-bottom: 10px; }}
        h2 {{ font-size: 1.5em; color: #818cf8; }}
        p {{ margin: 1em 0; }}
        .table-responsive {{ width: 100%; margin: 1em 0; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: rgba(30, 30, 50, 0.5);
            border-radius: 8px;
            table-layout: fixed;
        }}
        th, td {{
            padding: 8px 10px;
            border: 1px solid rgba(99, 102, 241, 0.2);
            text-align: left;
            word-wrap: break-word;
        }}
        th {{ background: rgba(99, 102, 241, 0.2); color: #a78bfa; font-size: 0.85em; }}
        td {{ font-size: 0.8em; }}
        tr:hover {{ background: rgba(99, 102, 241, 0.1); }}
        code {{
            background: rgba(99, 102, 241, 0.15);
            padding: 2px 6px;
            border-radius: 4px;
            font-family: 'Consolas', monospace;
            color: #c4b5fd;
        }}
        pre {{ background: #0d0d1a; padding: 16px; border-radius: 8px; overflow-x: auto; margin: 1em 0; }}
        pre code {{ background: none; padding: 0; }}
        a {{ color: #818cf8; }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 20px;
            border-bottom: 1px solid rgba(99, 102, 241, 0.2);
        }}
        .header h1 {{ border: none; margin: 0; padding: 0; }}
        .badge {{
            background: linear-gradient(135deg, #6366f1, #8b5cf6);
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 0.8em;
        }}
        .download-btn {{
            background: linear-gradient(135deg, #10b981, #059669);
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 20px;
            cursor: pointer;
            font-size: 0.85em;
            font-weight: 600;
        }}
        .download-btn:hover {{ transform: scale(1.05); }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📄 {file_name}</h1>
            <div style="display:flex;gap:10px;align-items:center;">
                <button class="download-btn" onclick="downloadHTML()">💾 HTML İndir</button>
                <span class="badge">DocuForge</span>
            </div>
        </div>
        {html_content}
    </div>
    <script>
        function downloadHTML() {{
            const b = new Blob([document.documentElement.outerHTML], {{ type: 'text/html' }});
            const a = document.createElement('a');
            a.href = URL.createObjectURL(b);
            a.download = '{file_name}.html';
            a.click();
        }}
    </script>
</body>
</html>'''
    
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html_page)

@app.get("/api/view-md")
def view_markdown(path: str):
    """
    Render a Markdown file as styled HTML for browser viewing.
    Returns full HTML page that opens in new tab.
    """
    from pathlib import Path as P
    import markdown
    
    file_path = P(path)
    
    # Security: Only allow .md files
    if not file_path.suffix.lower() == '.md':
        raise HTTPException(status_code=400, detail="Only .md files allowed")
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    
    try:
        md_content = file_path.read_text(encoding='utf-8')
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {e}")
    
    # Convert MD to HTML with extensions
    html_content = markdown.markdown(md_content, extensions=['tables', 'fenced_code', 'toc'])
    
    # Wrap tables in responsive container
    html_content = html_content.replace('<table>', '<div class="table-responsive"><table>')
    html_content = html_content.replace('</table>', '</table></div>')
    
    # Full styled HTML page
    html_page = f'''<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{file_path.stem} - DocuForge</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: linear-gradient(135deg, #0f0f23 0%, #1a1a2e 100%);
            color: #e0e0e0;
            padding: 40px;
            line-height: 1.8;
            min-height: 100vh;
        }}
        .container {{
            max-width: 95vw;
            margin: 0 auto;
            background: rgba(26, 26, 46, 0.9);
            border: 1px solid rgba(99, 102, 241, 0.3);
            border-radius: 16px;
            padding: 40px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        }}
        h1, h2, h3, h4 {{ color: #a78bfa; margin: 1em 0 0.5em; }}
        h1 {{ font-size: 2em; border-bottom: 2px solid #6366f1; padding-bottom: 10px; }}
        h2 {{ font-size: 1.5em; color: #818cf8; }}
        p {{ margin: 1em 0; }}
        .table-responsive {{ width: 100%; margin: 1em 0; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: rgba(30, 30, 50, 0.5);
            border-radius: 8px;
            table-layout: fixed;
        }}
        th, td {{
            padding: 8px 10px;
            border: 1px solid rgba(99, 102, 241, 0.2);
            text-align: left;
            word-wrap: break-word;
            overflow-wrap: break-word;
        }}
        th {{ background: rgba(99, 102, 241, 0.2); color: #a78bfa; font-size: 0.85em; }}
        td {{ font-size: 0.8em; }}
        tr:hover {{ background: rgba(99, 102, 241, 0.1); }}
        .table-responsive.cols-10 table {{ font-size: 0.75em; }}
        .table-responsive.cols-15 table {{ font-size: 0.65em; }}
        .table-responsive.cols-20 table {{ font-size: 0.55em; }}
        code {{
            background: rgba(99, 102, 241, 0.15);
            padding: 2px 6px;
            border-radius: 4px;
            font-family: 'Consolas', monospace;
            color: #c4b5fd;
        }}
        pre {{
            background: #0d0d1a;
            padding: 16px;
            border-radius: 8px;
            overflow-x: auto;
            margin: 1em 0;
        }}
        pre code {{ background: none; padding: 0; }}
        img {{ max-width: 100%; border-radius: 8px; margin: 1em 0; }}
        a {{ color: #818cf8; }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 20px;
            border-bottom: 1px solid rgba(99, 102, 241, 0.2);
        }}
        .header h1 {{ border: none; margin: 0; padding: 0; }}
        .badge {{
            background: linear-gradient(135deg, #6366f1, #8b5cf6);
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 0.8em;
        }}
        .header-actions {{ display: flex; gap: 10px; align-items: center; }}
        .download-btn {{
            background: linear-gradient(135deg, #10b981, #059669);
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 20px;
            cursor: pointer;
            font-size: 0.85em;
            font-weight: 600;
            transition: transform 0.2s;
        }}
        .download-btn:hover {{ transform: scale(1.05); }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📄 {file_path.stem}</h1>
            <div class="header-actions">
                <button class="download-btn" onclick="downloadHTML()">💾 HTML İndir</button>
                <span style="color: #06b6d4; font-size: 0.7em; margin-right: 10px; display: flex; flex-direction: column; text-align: right;">
                    <span>Output may contain errors</span>
                    <span style="opacity: 0.7; font-size: 0.9em;">Verification recommended</span>
                </span>
                <span class="badge">DocuForge</span>
            </div>
        </div>
        {html_content}
    </div>
    <script>
        document.querySelectorAll('.table-responsive').forEach(w => {{
            const t = w.querySelector('table');
            if (t) {{
                const c = t.querySelector('tr')?.children.length || 0;
                if (c >= 20) w.classList.add('cols-20');
                else if (c >= 15) w.classList.add('cols-15');
                else if (c >= 10) w.classList.add('cols-10');
            }}
        }});
        async function downloadHTML() {{
            try {{
                const r = await fetch('/api/browse', {{ method: 'POST' }});
                const d = await r.json();
                if (d.path) {{
                    const s = await fetch('/api/save-html', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{ folder: d.path, filename: '{file_path.stem}.html', content: document.documentElement.outerHTML }})
                    }});
                    const j = await s.json();
                    alert(j.success ? '✅ Kaydedildi: ' + j.path : '❌ Hata: ' + j.error);
                }}
            }} catch (e) {{
                const b = new Blob([document.documentElement.outerHTML], {{ type: 'text/html' }});
                const a = document.createElement('a');
                a.href = URL.createObjectURL(b);
                a.download = '{file_path.stem}.html';
                a.click();
            }}
        }}
    </script>
</body>
</html>'''
    
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html_page)

@app.post("/api/browse")
def browse_folder():
    """
    Opens a native folder picker dialog on the server (User's PC).
    Returns the selected absolute path.
    """
    try:
        # High-DPI fix for Windows
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

        root = tk.Tk()
        root.withdraw() 
        root.attributes('-topmost', True) 
        
        folder_path = filedialog.askdirectory(title="Select Output Folder")
        
        root.destroy()
        return {"path": folder_path}
    except Exception as e:
        return {"error": str(e)}

from pydantic import BaseModel

class SaveHTMLRequest(BaseModel):
    folder: str
    filename: str
    content: str

@app.post("/api/save-html")
def save_html(request: SaveHTMLRequest):
    """Save HTML content to the specified folder."""
    try:
        from pathlib import Path as P
        
        folder = P(request.folder)
        if not folder.exists():
            return {"success": False, "error": "Folder does not exist"}
        
        file_path = folder / request.filename
        file_path.write_text(request.content, encoding='utf-8')
        
        return {"success": True, "path": str(file_path)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def process_single_pdf_parallel(
    input_path: Path, 
    doc_output_dir: Path, 
    config: AppConfig, 
    workers: int,  # Kept for API compatibility but not used
    progress_callback=None
) -> str:
    """
    Process a single PDF page-by-page WITHOUT creating temp files.
    
    Chunking removed because it created temp PDFs that weren't being deleted.
    Now processes directly from original PDF - no temp files, no memory bloat.
    """
    import pdfplumber
    import gc
    
    # Import processing components
    from docuforge.src.cleaning.zones import ZoneCleaner
    from docuforge.src.cleaning.artifacts import TextCleaner
    from docuforge.src.extraction.tables import TableExtractor
    from docuforge.src.extraction.structure import StructureExtractor
    from docuforge.src.ingestion.ocr import SmartOCR
    from docuforge.src.extraction.engine_neural import NeuralSpatialEngine
    from docuforge.src.extraction.images import ImageExtractor
    from docuforge.src.extraction.visuals import VisualExtractor
    
    # Watermark Analysis - Pre-scan
    from docuforge.src.cleaning.watermark_analyzer import WatermarkAnalyzer
    analyzer = WatermarkAnalyzer(input_path)
    validated_watermarks = analyzer.analyze()
    
    # Initialize processors
    zone_cleaner = ZoneCleaner(config.cleaning)
    text_cleaner = TextCleaner(config.cleaning, validated_watermarks=validated_watermarks)
    table_extractor = TableExtractor(config.extraction)
    structure_extractor = StructureExtractor()
    smart_ocr = SmartOCR(config.ocr)
    neural_engine = NeuralSpatialEngine(config.extraction)
    image_extractor = ImageExtractor(config.extraction, output_dir=doc_output_dir)
    visual_extractor = VisualExtractor(config.extraction, output_dir=doc_output_dir)
    
    all_md_content = []
    
    # Open PDF ONCE and process page by page - NO temp files!
    with pdfplumber.open(input_path) as pdf:
        total_pages = len(pdf.pages)
        
        if progress_callback:
            progress_callback('start', 0, total_pages)
        
        for page_num, page in enumerate(pdf.pages, start=1):
            try:
                # A. Zone Analysis
                crop_box = zone_cleaner.get_crop_box(page)
                
                # B. Smart OCR / Text Extraction
                raw_text_check = page.filter(lambda obj: obj["object_type"] == "char").extract_text() or ""
                ocr_text = smart_ocr.process_page(input_path, page_num, raw_text_check)
                
                if ocr_text and ocr_text != raw_text_check:
                    # OCR Path
                    clean_text = text_cleaner.clean_text(ocr_text)
                    all_md_content.append(f"\n\n## Page {page_num}\n\n{clean_text}\n")
                else:
                    # C. Visual Extraction
                    tables_md = []
                    charts_md = []
                    ignore_regions = []
                    
                    # Neural Engine
                    if config.extraction.use_neural_engine and config.extraction.tables_enabled:
                        try:
                            neural_tables, neural_charts, table_bboxes = neural_engine.process_page(page, page_num)
                            tables_md.extend(neural_tables)
                            ignore_regions.extend(table_bboxes)
                            for chart in neural_charts:
                                if config.extraction.charts_enabled:
                                    charts_md.append(f"📊 *Chart detected on Page {page_num}* ({chart.chart_type})")
                                ignore_regions.append((chart.bbox.x0, chart.bbox.y0, chart.bbox.x1, chart.bbox.y1))
                        except Exception:
                            pass
                    
                    # Legacy fallback
                    if not tables_md and config.extraction.neural_fallback_to_legacy:
                        legacy_tables = table_extractor.extract_tables(input_path, page_num, page)
                        tables_md.extend(legacy_tables)
                    
                    # Structure extraction
                    structured_text = structure_extractor.extract_text_with_structure(page, crop_box, ignore_regions)
                    clean_text = text_cleaner.clean_text(structured_text)
                    
                    # Images
                    images_md = image_extractor.extract_images(input_path, page_num)
                    
                    # Charts
                    if config.extraction.charts_enabled and not charts_md:
                        chart_results = visual_extractor.extract_visuals(input_path, page_num)
                        charts_md.extend([link for link, bbox in chart_results])
                    
                    # Assembly
                    page_md = f"\n\n## Page {page_num}\n"
                    if charts_md: page_md += "\n" + "\n".join(charts_md) + "\n"
                    if images_md: page_md += "\n" + "\n".join(images_md) + "\n"
                    if tables_md: page_md += "\n" + "\n".join(tables_md) + "\n"
                    page_md += f"\n{clean_text}\n"
                    
                    all_md_content.append(page_md)
                    
                    # Cleanup per-page variables
                    del tables_md, charts_md, images_md, ignore_regions, structured_text, clean_text
                
            except Exception as e:
                logging.error(f"Page {page_num} error: {e}")
                all_md_content.append(f"\n\n## Page {page_num}\n\n[ERROR: {e}]\n")
            
            # AGGRESSIVE MEMORY CLEANUP - every page
            try:
                page.flush_cache()
            except:
                pass
            
            # Progress update PER PAGE (smoother progress bar)
            if progress_callback:
                progress_callback('progress', page_num, total_pages)
            
            # Garbage collection every 10 pages (balance speed vs memory)
            if page_num % 10 == 0:
                gc.collect()
    
    return "\n".join(all_md_content)


@app.post("/api/convert-stream")
async def convert_pdfs_stream(
    files: List[UploadFile] = File(...),
    output_path: Optional[str] = Form(None),
    workers: int = Form(4),  # Kept for API compatibility
    tables: bool = Form(True),
    ocr: str = Form("auto"),
    images: bool = Form(False),
    charts: bool = Form(False)
):
    """
    SSE-based streaming conversion - PAGE BY PAGE processing.
    No temp files, no ProcessPoolExecutor.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    async def event_stream() -> AsyncGenerator[str, None]:
        import pdfplumber
        import gc
        
        # Import processing components
        from docuforge.src.cleaning.zones import ZoneCleaner
        from docuforge.src.cleaning.artifacts import TextCleaner
        from docuforge.src.extraction.tables import TableExtractor
        from docuforge.src.extraction.structure import StructureExtractor
        from docuforge.src.ingestion.ocr import SmartOCR
        from docuforge.src.extraction.engine_neural import NeuralSpatialEngine
        from docuforge.src.extraction.images import ImageExtractor
        from docuforge.src.extraction.visuals import VisualExtractor
        from docuforge.src.cleaning.watermark_analyzer import WatermarkAnalyzer
        
        use_local_path = False
        target_dir = None
        
        # Path traversal check
        if output_path:
            target_path = Path(output_path).resolve()
            allowed_roots = [Path.home().resolve(), Path("C:/Users/Public").resolve()]
            is_safe = any(str(target_path).startswith(str(root)) for root in allowed_roots)
            
            if is_safe and target_path.exists():
                target_dir = target_path
                use_local_path = True
            elif not is_safe:
                logging.warning(f"Path traversal attempt blocked: {output_path}")

        with tempfile.TemporaryDirectory() as request_temp:
            request_temp_path = Path(request_temp)
            
            config = AppConfig()
            config.extraction.tables_enabled = tables
            config.extraction.images_enabled = images
            config.extraction.charts_enabled = charts
            config.ocr.enable = ocr

            for file_idx, file in enumerate(files):
                if not file.filename.endswith('.pdf'):
                    continue

                try:
                    yield f"data: {json.dumps({'type': 'file_start', 'file': file.filename, 'file_idx': file_idx})}\n\n"
                    
                    input_path = request_temp_path / file.filename
                    with open(input_path, "wb") as buffer:
                        shutil.copyfileobj(file.file, buffer)
                    
                    if use_local_path:
                        doc_output_dir = target_dir
                        if images: (doc_output_dir / "images").mkdir(exist_ok=True)
                    else:
                        doc_output_dir = request_temp_path / "output" / Path(file.filename).stem
                        doc_output_dir.mkdir(parents=True, exist_ok=True)

                    # Quick page count for immediate correct progress bar
                    import pdfplumber
                    with pdfplumber.open(input_path) as pdf:
                        quick_page_count = len(pdf.pages)
                    
                    # Immediate progress with correct total
                    yield f"data: {json.dumps({'type': 'progress', 'file': file.filename, 'file_idx': file_idx, 'pages_done': 0, 'total_pages': quick_page_count, 'percent': 0, 'status': 'Analyzing...'})}\n\n"
                    await asyncio.sleep(0.01)
                    
                    # Watermark Analysis
                    from docuforge.src.cleaning.watermark_analyzer import WatermarkAnalyzer
                    analyzer = WatermarkAnalyzer(input_path)
                    validated_watermarks = analyzer.analyze()
                    
                    # PARALLEL PROCESSING with ProcessPoolExecutor
                    loader = PDFLoader(chunk_size=10)
                    chunks = list(loader.stream_chunks(input_path))
                    total_pages = sum(chunk.end_page - chunk.start_page + 1 for chunk in chunks)
                    
                    # Progress ready to process
                    yield f"data: {json.dumps({'type': 'progress', 'file': file.filename, 'file_idx': file_idx, 'pages_done': 0, 'total_pages': total_pages, 'percent': 0, 'status': 'Processing...'})}\n\n"
                    await asyncio.sleep(0.01)
                    
                    results = []
                    pages_done = 0
                    cancelled = False
                    
                    # Reset cancel flag at start of processing
                    global _cancel_requested, _active_executor
                    _cancel_requested = False
                    
                    # Enforce worker limit to CPU count
                    cpu_count = os.cpu_count() or 4
                    actual_workers = min(workers, cpu_count)
                    
                    # Use limited worker count and store executor globally for cancellation
                    executor = ProcessPoolExecutor(max_workers=actual_workers)
                    _active_executor = executor
                    
                    try:
                        # Debug: Executor lifecycle tracking (guarded to avoid I/O when disabled)
                        from docuforge.debug import debug_log, is_debug_enabled
                        if is_debug_enabled("executor_lifecycle"):
                            temp_dir_debug = Path("C:/Users/Public/DocuForge/Temp")
                            chunk_status = {c.temp_path.name: c.temp_path.exists() for c in chunks}
                            debug_log("executor_lifecycle", "BEFORE_SUBMIT",
                                file=file.filename,
                                temp_dir_contents=[f.name for f in temp_dir_debug.iterdir()],
                                chunks_exist=chunk_status)
                        
                        futures = {
                            executor.submit(PipelineController.process_chunk, chunk, config, doc_output_dir, validated_watermarks): chunk
                            for chunk in chunks
                        }
                        
                        for future in as_completed(futures):
                            # Check if cancellation requested
                            if _cancel_requested:
                                cancelled = True
                                break
                            
                            chunk = futures[future]
                            chunk_pages = chunk.end_page - chunk.start_page + 1
                            
                            try:
                                res = future.result()
                                results.append((chunk.start_page, res))
                            except Exception as e:
                                results.append((chunk.start_page, f"\n\n[ERROR: {e}]\n"))
                            
                            pages_done += chunk_pages
                            percent = int((pages_done / total_pages) * 100)
                            
                            yield f"data: {json.dumps({'type': 'progress', 'file': file.filename, 'file_idx': file_idx, 'pages_done': pages_done, 'total_pages': total_pages, 'percent': percent})}\n\n"
                            await asyncio.sleep(0.01)
                    finally:
                        executor.shutdown(wait=True)  # Wait for workers to complete before next PDF
                        _active_executor = None
                        
                        # Debug: Executor lifecycle tracking (guarded to avoid I/O when disabled)
                        from docuforge.debug import debug_log, is_debug_enabled
                        if is_debug_enabled("executor_lifecycle"):
                            temp_dir_debug = Path("C:/Users/Public/DocuForge/Temp")
                            temp_contents = [f.name for f in temp_dir_debug.iterdir()] if temp_dir_debug.exists() else "DIR_NOT_EXISTS"
                            debug_log("executor_lifecycle", "AFTER_SHUTDOWN",
                                file=file.filename,
                                temp_dir_contents=temp_contents)
                    
                    # Skip save if cancelled
                    if cancelled:
                        continue
                    
                    results.sort(key=lambda x: x[0])
                    final_md = "\n".join([r[1] for r in results])
                    
                    if use_local_path:
                        md_path = doc_output_dir / f"{input_path.stem}.md"
                        md_path.write_text(final_md, encoding="utf-8")
                        yield f"data: {json.dumps({'type': 'file_done', 'file': file.filename, 'file_idx': file_idx, 'status': 'saved', 'path': str(md_path)})}\n\n"
                    else:
                        yield f"data: {json.dumps({'type': 'file_done', 'file': file.filename, 'file_idx': file_idx, 'status': 'processed'})}\n\n"
                        
                except Exception as e:
                    logging.error(f"Error processing {file.filename}: {e}")
                    yield f"data: {json.dumps({'type': 'file_error', 'file': file.filename, 'file_idx': file_idx, 'error': str(e)})}\n\n"

            # FINAL CLEANUP: Clean all temp files after all files processed
            temp_dir = Path("C:/Users/Public/DocuForge/Temp")
            if temp_dir.exists():
                for f in temp_dir.iterdir():
                    try:
                        f.unlink()
                    except:
                        pass
            
            yield f"data: {json.dumps({'type': 'complete', 'total_files': len(files)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/convert")
async def convert_pdfs(
    files: List[UploadFile] = File(...),
    output_path: Optional[str] = Form(None),
    workers: int = Form(4),
    tables: bool = Form(True),
    ocr: str = Form("auto"),
    images: bool = Form(False),
    charts: bool = Form(False)
):
    """Synchronous endpoint with multiprocessing"""
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    results = []
    
    use_local_path = False
    target_dir = None
    
    if output_path:
        target_path = Path(output_path).resolve()
        allowed_roots = [Path.home().resolve(), Path("C:/Users/Public").resolve()]
        is_safe = any(str(target_path).startswith(str(root)) for root in allowed_roots)
        
        if is_safe and target_path.exists():
            target_dir = target_path
            use_local_path = True
        elif not is_safe:
            logging.warning(f"Path traversal attempt blocked: {output_path}")

    with tempfile.TemporaryDirectory() as request_temp:
        request_temp_path = Path(request_temp)
        
        config = AppConfig()
        config.extraction.tables_enabled = tables
        config.extraction.images_enabled = images
        config.extraction.charts_enabled = charts
        config.ocr.enable = ocr
        config.workers = workers

        for file in files:
            if not file.filename.endswith('.pdf'):
                continue

            try:
                input_path = request_temp_path / file.filename
                with open(input_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
                
                if use_local_path:
                    doc_output_dir = target_dir
                    if images: (doc_output_dir / "images").mkdir(exist_ok=True)
                else:
                    doc_output_dir = request_temp_path / "output" / Path(file.filename).stem
                    doc_output_dir.mkdir(parents=True, exist_ok=True)

                final_md = process_single_pdf_parallel(
                    input_path, doc_output_dir, config, workers
                )
                
                if use_local_path:
                    md_path = doc_output_dir / f"{input_path.stem}.md"
                    md_path.write_text(final_md, encoding="utf-8")
                    results.append({
                        "filename": file.filename,
                        "status": "saved",
                        "path": str(md_path)
                    })
                else:
                    results.append({
                        "filename": file.filename,
                        "status": "processed",
                        "markdown_preview": final_md[:500] + "..." 
                    })
                    
            except Exception as e:
                logging.error(f"Error processing {file.filename}: {e}")
                results.append({"filename": file.filename, "status": "error", "error": str(e)})

    return {
        "summary": f"Processed {len(files)} files",
        "results": results,
        "mode": "local_save" if use_local_path else "preview"
    }

app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

def start_server():
    print("Serving on http://127.0.0.1:8000")
    uvicorn.run("docuforge.api:app", host="127.0.0.1", port=8000, log_level="error")
