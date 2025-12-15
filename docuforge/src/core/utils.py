import os
import sys
import shutil
import time
import tempfile
import logging
from pathlib import Path
from contextlib import contextmanager

@contextmanager
def suppress_stderr():
    """
    Context manager to suppress low-level C stderr output (like OpenCV/Ghostscript warnings).
    """
    with open(os.devnull, 'w') as devnull:
        try:
            old_stderr = os.dup(sys.stderr.fileno())
            os.dup2(devnull.fileno(), sys.stderr.fileno())
            yield
        except Exception:
            yield
        finally:
            try:
                os.dup2(old_stderr, sys.stderr.fileno())
                os.close(old_stderr)
            except Exception:
                pass

def ensure_windows_temp_compatibility():
    """
    Fixes Windows User Data with Non-ASCII characters (e.g. 'göksel') breaking Camelot/Ghostscript/OpenCV.
    Forces the process to use a safe ASCII path for TEMP.
    """
    if os.name != 'nt':
        return

    import ctypes
    def get_short_path(path):
        try:
            buf = ctypes.create_unicode_buffer(256)
            ret = ctypes.windll.kernel32.GetShortPathNameW(path, buf, 256)
            if ret > 0:
                return buf.value
        except Exception:
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
                
    if safe_temp != current_temp and safe_temp and str(safe_temp).isascii():
        os.environ["TEMP"] = str(safe_temp)
        os.environ["TMP"] = str(safe_temp)
        tempfile.tempdir = str(safe_temp)

class SafeFileManager:
    """
    Robust file management for Windows to handle file locking issues.
    """
    @staticmethod
    def safe_delete(path: Path, max_retries=5, delay=0.5):
        if not path.exists():
            return
        
        for i in range(max_retries):
            try:
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    path.unlink()
                break
            except PermissionError:
                if i < max_retries - 1:
                    time.sleep(delay)
                else:
                    logging.warning(f"Failed to delete {path} after {max_retries} attempts.")
            except Exception as e:
                logging.warning(f"Error deleting {path}: {e}")
                break

    @staticmethod
    def patch_shutil_for_windows():
        """
        Monkeypatch shutil.rmtree to be resilient on Windows exit.
        """
        if os.name == 'nt':
            original_rmtree = shutil.rmtree
            def safe_rmtree(path, ignore_errors=False, onerror=None, **kwargs):
                try:
                    original_rmtree(path, ignore_errors=True, onerror=None, **kwargs)
                except Exception:
                    pass
            shutil.rmtree = safe_rmtree

    @staticmethod
    def cleanup_global_temp():
        """
        Cleans up orphaned 'DocuForge/Temp' directory in Public Documents.
        This handles debris left by previous crashed runs.
        """
        public_temp = Path("C:/Users/Public/DocuForge/Temp")
        if not public_temp.exists():
            return
            
        # Log basic info
        # print(f"Cleaning cleanup: {public_temp}")
        
        # We try to delete the entire folder contents, but if a file is locked 
        # (e.g. by another running instance), we skip it silently.
        for item in public_temp.iterdir():
            if item.is_dir():
                SafeFileManager.safe_delete(item, max_retries=1) # Fast fail, don't wait
            else:
                try:
                    item.unlink()
                except Exception:
                    pass
