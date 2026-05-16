"""Smoke tests for detect_environment()."""

from everbar import detect_environment

VALID = {
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
}


def test_returns_known_environment():
    env = detect_environment()
    assert env in VALID


def test_idempotent():
    assert detect_environment() == detect_environment()
