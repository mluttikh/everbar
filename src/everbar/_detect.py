"""Runtime environment detection.

Heuristic — the caller can override via the ``backend`` argument on ``Progress``
or the ``EVERBAR_BACKEND`` environment variable.
"""

import os
import sys
from typing import Literal

Environment = Literal[
    "marimo",
    "colab",
    "kaggle",
    "vscode_notebook",
    "jupyter",
    "jupyter_qt",
    "spyder",
    "databricks",
    "pyodide",
    "ipython_terminal",
    "terminal",
    "non_tty",
]


def detect_environment() -> Environment:
    """Return a string identifying the runtime environment."""
    # 1. Marimo — official API
    try:
        import marimo  # type: ignore

        if marimo.running_in_notebook():
            return "marimo"
    except Exception:
        pass

    # 2. Pyodide / JupyterLite
    if "pyodide" in sys.modules or sys.platform == "emscripten":
        return "pyodide"

    # 3. Databricks
    if "DATABRICKS_RUNTIME_VERSION" in os.environ:
        return "databricks"

    # 4. IPython-based environments
    try:
        from IPython import get_ipython  # type: ignore

        ip = get_ipython()
    except Exception:
        ip = None

    if ip is not None:
        shell = ip.__class__.__name__
        mods = sys.modules

        if "google.colab" in mods:
            return "colab"
        if "kaggle_secrets" in mods or "KAGGLE_KERNEL_RUN_TYPE" in os.environ:
            return "kaggle"
        if "VSCODE_PID" in os.environ or (
            hasattr(ip, "user_ns") and "__vsc_ipynb_file__" in ip.user_ns
        ):
            return "vscode_notebook"
        if "spyder_kernels" in mods or "SPY_TESTING" in os.environ:
            return "spyder"
        if shell == "ZMQInteractiveShell":
            return "jupyter"
        if shell == "TerminalInteractiveShell":
            return "ipython_terminal"

    # 5. Plain Python
    if sys.stdout is not None and hasattr(sys.stdout, "isatty"):
        try:
            if sys.stdout.isatty():
                return "terminal"
        except Exception:
            pass
    return "non_tty"
