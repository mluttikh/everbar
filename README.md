# everbar

A progress bar that works **everywhere** — terminal, Jupyter, JupyterLab, VS Code notebooks, Google Colab, Marimo, Pyodide, and CI logs. One API, the right backend per environment.

> Status: 0.2.0 — alpha. API may shift.

## Install

```bash
pip install everbar             # core only; uses text fallback if nothing else is installed
pip install "everbar[tqdm]"     # terminal + Jupyter via tqdm
pip install "everbar[notebook]" # tqdm + ipywidgets for notebook front-ends
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

Other options:

```python
Progress(items, unit="files")   # label what's being counted
Progress(items, disable=True)   # render nothing (e.g. behind a quiet flag)
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

### Signal failure with `fail()`

Mark the bar as failing without stopping it — useful when one task in a
batch errors but the overall job continues:

```python
with Progress(total=len(jobs), desc="Batch") as bar:
    for job in jobs:
        if not run(job):
            bar.fail()
        bar.update(1)
```

Rendering is backend-specific: red bar in tqdm, `FAIL` marker in Rich,
`[failing]` log lines in non-TTY mode, a red badge in Marimo. The state
is sticky.

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

Precedence: the `backend=` argument wins, then `EVERBAR_BACKEND`, then
`set_default_backend`, then auto-detection.

Unknown backend names raise `ValueError` (`EVERBAR_BACKEND` warns and is
ignored instead, so a stale deploy-time value can't crash a script). If
you request a backend explicitly and its dependency isn't installed, you
get an `ImportError` — auto-detection falls back to the text backend
silently.

Extra keyword arguments to `Progress` are forwarded to the selected
backend, so they are environment-specific by nature (tqdm's `colour`,
Rich's `console`, the fallback's `min_interval`). Stick to the named
parameters in code that must run everywhere.

## How it picks a backend

`everbar.detect_environment()` returns one of: `marimo`, `colab`, `kaggle`, `vscode_notebook`, `jupyter`, `spyder`, `databricks`, `pyodide`, `ipython_terminal`, `terminal`, `non_tty`. Each maps to a backend, with graceful fallback to a log-line text mode when nothing better is available.
