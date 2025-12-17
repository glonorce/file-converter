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
import uvicorn
import tkinter as tk
from tkinter import filedialog

# Suppress noisy PDFMiner warnings
logging.getLogger("pdfminer").setLevel(logging.ERROR)

from docuforge.src.core.config import AppConfig
from docuforge.src.ingestion.loader import PDFLoader
# NEW: Import Centralized Controller
from docuforge.src.core.controller import PipelineController

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
    workers: int,
    progress_callback=None
) -> str:
    """
    Process a single PDF using PipelineController (DRY).
    """
    # Watermark Analysis - Pre-scan to find true watermarks (>60% of pages)
    from docuforge.src.cleaning.watermark_analyzer import WatermarkAnalyzer
    analyzer = WatermarkAnalyzer(input_path)
    validated_watermarks = analyzer.analyze()
    
    loader = PDFLoader(chunk_size=10)
    chunks = list(loader.stream_chunks(input_path))
    
    if progress_callback:
        total_pages = sum(chunk.end_page - chunk.start_page + 1 for chunk in chunks)
        progress_callback('start', 0, total_pages)
    
    results = []
    pages_done = 0
    
    with ProcessPoolExecutor(max_workers=workers) as executor:
        # Use PipelineController.process_chunk with validated_watermarks
        futures = {
            executor.submit(PipelineController.process_chunk, chunk, config, doc_output_dir, validated_watermarks): chunk
            for chunk in chunks
        }
        
        for future in as_completed(futures):
            chunk = futures[future]
            chunk_pages = chunk.end_page - chunk.start_page + 1
            try:
                res = future.result()
                results.append((chunk.start_page, res))
                pages_done += chunk_pages
                
                if progress_callback:
                    total_pages = sum(c.end_page - c.start_page + 1 for c in chunks)
                    progress_callback('progress', pages_done, total_pages)
                    
            except Exception as e:
                logging.error(f"Chunk error pages {chunk.start_page}-{chunk.end_page}: {e}")
                results.append((chunk.start_page, f"\n\n[ERROR: {e}]\n"))
                pages_done += chunk_pages
    
    results.sort(key=lambda x: x[0])
    return "\n".join([r[1] for r in results])


@app.post("/api/convert-stream")
async def convert_pdfs_stream(
    files: List[UploadFile] = File(...),
    output_path: Optional[str] = Form(None),
    workers: int = Form(4),
    tables: bool = Form(True),
    ocr: str = Form("auto"),
    images: bool = Form(False),
    charts: bool = Form(False)
):
    """
    SSE-based streaming conversion using PipelineController.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    async def event_stream() -> AsyncGenerator[str, None]:
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
            config.workers = workers

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

                    # Unified Pipeline Logic
                    loader = PDFLoader(chunk_size=10)
                    chunks = list(loader.stream_chunks(input_path))
                    total_pages = sum(chunk.end_page - chunk.start_page + 1 for chunk in chunks)
                    
                    # Watermark Analysis - Pre-scan to find true watermarks (>60% of pages)
                    from docuforge.src.cleaning.watermark_analyzer import WatermarkAnalyzer
                    analyzer = WatermarkAnalyzer(input_path)
                    validated_watermarks = analyzer.analyze()
                    
                    results = []
                    pages_done = 0
                    
                    with ProcessPoolExecutor(max_workers=workers) as executor:
                        futures = {
                            executor.submit(PipelineController.process_chunk, chunk, config, doc_output_dir, validated_watermarks): chunk
                            for chunk in chunks
                        }
                        
                        for future in as_completed(futures):
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
