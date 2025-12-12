import os
import sys
from contextlib import contextmanager

@contextmanager
def suppress_stderr():
    """
    Context manager to suppress low-level C stderr output (like OpenCV/Ghostscript warnings).
    """
    # Open a null file
    with open(os.devnull, 'w') as devnull:
        # Save original stderr
        try:
            old_stderr = os.dup(sys.stderr.fileno())
            # Redirect stderr to null
            os.dup2(devnull.fileno(), sys.stderr.fileno())
            yield
        except Exception:
            # If redirection fails (e.g. restricted env), just yield
            yield
        finally:
            try:
                # Restore stderr
                os.dup2(old_stderr, sys.stderr.fileno())
                os.close(old_stderr)
            except Exception:
                pass
