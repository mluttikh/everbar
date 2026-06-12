"""everbar — a progress bar that works everywhere."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

from everbar._detect import Environment, detect_environment
from everbar._progress import Progress, set_default_backend

__all__ = [
    "Environment",
    "Progress",
    "detect_environment",
    "set_default_backend",
]

try:
    __version__ = _version("everbar")
except PackageNotFoundError:  # pragma: no cover — running from a source tree
    __version__ = "0.0.0+unknown"
