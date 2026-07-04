"""everbar — a progress bar that works everywhere."""

from everbar._detect import Environment, detect_environment
from everbar._progress import Progress, set_default_backend

__all__ = [
    "Environment",
    "Progress",
    "detect_environment",
    "set_default_backend",
]


def __getattr__(name: str) -> str:
    # PEP 562: resolve __version__ lazily. The importlib.metadata import
    # chain is ~85% of the package's import cost, and most consumers
    # never read the version.
    if name == "__version__":
        from importlib.metadata import PackageNotFoundError, version

        try:
            v = version("everbar")
        except PackageNotFoundError:  # pragma: no cover — source tree
            v = "0.0.0+unknown"
        globals()["__version__"] = v  # cache for subsequent access
        return v
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
