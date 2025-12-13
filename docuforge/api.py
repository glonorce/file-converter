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

# Import core logic
from docuforge.main import worker_process_chunk, AppConfig
from docuforge.src.ingestion.loader import PDFLoader

app = FastAPI(title="DocuForge API", version="2.1.0")

# SEC-P0-001: Restricted CORS to localhost only (was wildcard "*")
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

@app.post("/api/browse")
def browse_folder():
    """
    Opens a native folder picker dialog on the server (User's PC).
    Returns the selected absolute path.
    """
    try:
        # High-DPI fix for Windows (Prevents Blurry Dialog)
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

        # Create a hidden root window
        root = tk.Tk()
        root.withdraw() # Hide it
        root.attributes('-topmost', True) # Bring to front
        
        folder_path = filedialog.askdirectory(title="Select Output Folder")
        
        root.destroy()
        return {"path": folder_path}
    except Exception as e:
        return {"error": str(e)}


def process_single_pdf_parallel(
    input_path: Path, 
    doc_output_dir: Path, 
    config: AppConfig, 
    workers: int,
    progress_callback=None
) -> str:
    """
    Process a single PDF using multiprocessing (same as CLI).
    Returns the full markdown content.
    """
    loader = PDFLoader(chunk_size=2)  # 2 pages per chunk for granular progress
    chunks = list(loader.stream_chunks(input_path))
    total_chunks = len(chunks)
    
    if progress_callback:
        total_pages = sum(chunk.end_page - chunk.start_page + 1 for chunk in chunks)
        progress_callback('start', 0, total_pages)
    
    results = []
    pages_done = 0
    
    # Use ProcessPoolExecutor for parallel processing (like CLI)
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(worker_process_chunk, chunk, config, doc_output_dir): chunk
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
    
    # Sort by page number to maintain order
    results.sort(key=lambda x: x[0])
    return "\n".join([r[1] for r in results])


@app.post("/api/convert-stream")
async def convert_pdfs_stream(
    files: List[UploadFile] = File(...),
    output_path: Optional[str] = Form(None),
    workers: int = Form(4),
    tables: bool = Form(True),
    ocr: str = Form("auto"),
    images: bool = Form(False)
):
    """
    SSE-based streaming conversion with real-time progress per 2 pages.
    Uses multiprocessing for CLI-equivalent speed.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    async def event_stream() -> AsyncGenerator[str, None]:
        use_local_path = False
        target_dir = None
        
        # SEC-P1-002: Path traversal protection
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
            config.ocr.enable = ocr
            config.workers = workers

            for file_idx, file in enumerate(files):
                if not file.filename.endswith('.pdf'):
                    continue

                try:
                    # Send file start event
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

                    # Use multiprocessing for speed (like CLI)
                    loader = PDFLoader(chunk_size=2)
                    chunks = list(loader.stream_chunks(input_path))
                    total_pages = sum(chunk.end_page - chunk.start_page + 1 for chunk in chunks)
                    
                    results = []
                    pages_done = 0
                    
                    # Parallel processing with ProcessPoolExecutor
                    with ProcessPoolExecutor(max_workers=workers) as executor:
                        futures = {
                            executor.submit(worker_process_chunk, chunk, config, doc_output_dir): chunk
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
                            
                            # Send progress event every 2 pages
                            yield f"data: {json.dumps({'type': 'progress', 'file': file.filename, 'file_idx': file_idx, 'pages_done': pages_done, 'total_pages': total_pages, 'percent': percent})}\n\n"
                            
                            await asyncio.sleep(0.01)  # Allow event loop
                    
                    # Sort and join results
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

            # Send completion event
            yield f"data: {json.dumps({'type': 'complete', 'total_files': len(files)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/convert")
async def convert_pdfs(
    files: List[UploadFile] = File(...),
    output_path: Optional[str] = Form(None),
    workers: int = Form(4),
    tables: bool = Form(True),
    ocr: str = Form("auto"),
    images: bool = Form(False)
):
    """Original synchronous endpoint with multiprocessing (kept for compatibility)"""
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    results = []
    
    use_local_path = False
    target_dir = None
    
    # SEC-P1-002: Path traversal protection
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

                # Use parallel processing (like CLI)
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
    uvicorn.run("docuforge.api:app", host="127.0.0.1", port=8000)
