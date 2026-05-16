"""everbar — a progress bar that works everywhere."""

from everbar._detect import detect_environment
from everbar._progress import Progress, set_default_backend

__all__ = ["Progress", "detect_environment", "set_default_backend"]
__version__ = "0.1.0"
