# everbar

A progress bar that works **everywhere** — terminal, Jupyter, JupyterLab, VS Code notebooks, Google Colab, Marimo, Pyodide, and CI logs. One API, the right backend per environment.

> Status: 0.1.0 — alpha. API may shift.

## Install

```bash
pip install everbar             # core only; uses text fallback if nothing else is installed
pip install "everbar[tqdm]"     # terminal + Jupyter via tqdm
pip install "everbar[all]"      # everything (tqdm, rich, ipywidgets, marimo)
```

## Use

```python
from everbar import Progress

for x in Progress(items, desc="Loading"):
    work(x)

with Progress(total=100, desc="Steps") as bar:
    for _ in range(100):
        do_step()
        bar.update(1)
```

### Live metrics with `set_postfix`

Show a live key/value suffix next to the bar — useful in training loops:

```python
with Progress(total=epochs, desc="Training") as bar:
    for epoch in range(epochs):
        loss, acc = train_one_epoch()
        bar.set_postfix(loss=loss, acc=acc)
        bar.update(1)
```

Calling `set_postfix` again replaces the previous suffix. Floats are
formatted compactly (e.g. `loss=0.424, acc=0.91`).

## Overrides

```python
Progress(items, backend="terminal")        # per-call
```

```bash
EVERBAR_BACKEND=terminal python script.py  # env var
```

```python
import everbar
everbar.set_default_backend("terminal")    # module-wide
```

## How it picks a backend

`everbar.detect_environment()` returns one of: `marimo`, `colab`, `kaggle`, `vscode_notebook`, `jupyter`, `jupyter_qt`, `spyder`, `databricks`, `pyodide`, `ipython_terminal`, `terminal`, `non_tty`. Each maps to a backend, with graceful fallback to a log-line text mode when nothing better is available.
