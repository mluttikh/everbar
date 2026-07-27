# Landscape — Python progress bar libraries

Notes on existing libraries in this space, with a focus on those that abstract
over multiple display backends (the niche everbar competes in).

## Libraries that abstract over multiple backends

### tqdm.auto

The OG of environment dispatch. `from tqdm.auto import tqdm` selects
`tqdm.notebook` in Jupyter and `tqdm.std` in the terminal at import time.

- **Scope**: only its own backends. No Rich, no Marimo.
- **Notable extras**: `tqdm.write()` for printing without smearing the bar.
- **Repo**: https://github.com/tqdm/tqdm

### fastprogress (fast.ai)

Built for fast.ai training loops; notebook + console dispatch via
`is_notebook()` / `is_terminal()`.

- **Nested bars** with explicit parent/child: `progress_bar(..., parent=mb)`
  resets the child each outer iteration.
- **Live in-loop graphing** via `update_graph()` — niche but distinctive.
- **`mb.write()`** for output that survives stdout redirection (only `.write`
  output ends up in the file).
- **In-loop comment updates**: `mb.main_bar.comment = "..."`.
- **Repo**: https://github.com/AnswerDotAI/fastprogress

### enlighten

Terminal-focused, but the `Manager` coordinates multiple bars. Closer to a
"how do bars compose with other I/O" library than an environment-abstraction
library.

- **Killer feature**: concurrent `print()` / `log()` without smearing the bar
  display — no redirection or wrapper code needed.
- **Multi-bar manager** is its central abstraction.
- **Experimental Jupyter support**.
- **Repo**: https://github.com/Rockhopper-Technologies/enlighten

## Single-backend libraries worth knowing

### rich.progress

Terminal only, but with the most expressive layout system in the space.

- **Composable columns**: build a bar from `TextColumn`, `BarColumn`,
  `TimeRemainingColumn`, `SpinnerColumn`, etc.
- **Multiple concurrent tasks** in one `Progress` instance.
- **Theme/style integration** with the rest of Rich.
- **Docs**: https://rich.readthedocs.io/en/latest/progress.html

### alive-progress

Terminal only, animation-heavy. Doesn't fit our abstraction story but useful
for context on the "polish" end of the space.

### progiter

A single-threaded tqdm-alike — same API surface, no threading. Useful with
heavy multiprocessing.

- **Repo**: https://github.com/Erotemic/progiter

## Domain-specific abstractions

### PyMC's `progress_bar/`

Not a general library, but interesting prior art for a multi-backend
progress abstraction.

- **`ProgressBackend` Protocol** with `update(task_id, advance, failing, stats,
  is_last, total)`.
- **Multi-chain / multi-task tracking** via `task_id` routing — one backend
  instance hosts N bars rendered as a single table.
- **Failure state** with per-task color/CSS class changes (red bar on chain
  divergence).
- **Adaptive speed units**: switches between `it/s` and `s/it` based on rate.
- **Dynamic total updates** mid-run.
- **Backend split**: `rich_progress.py` (terminal) and `marimo_progress.py`
  (notebook) sit behind one `ProgressBarManager`.
- **Source**: https://github.com/pymc-devs/pymc/tree/main/pymc/progress_bar

## Cross-cutting features worth borrowing

Themes that appear in multiple libraries and would slot into everbar:

1. **Safe `write()` / `print()`** — tqdm, fastprogress, enlighten. Print
   alongside a running bar in terminal mode without breaking the carriage
   return / cursor dance. Universal pain point, smallest lift.
2. **Multi-bar manager** — enlighten, fastprogress (`master_bar` + child),
   rich (multiple tasks per `Progress`), PyMC (`task_id` routing). The most
   common differentiator in this space.
3. **Explicit parent/child nesting** — fastprogress. Distinct from "two
   independent bars stacked"; child auto-resets each outer iteration.
4. **Composable column layout** — rich, PyMC. Replaces `set_postfix`-as-string
   with structured per-column values that backends render their own way.
5. **Failure state / per-task color change** — PyMC. Recolors when a worker
   errors but the job continues.
6. **Adaptive rate units** — PyMC, tqdm. Auto-switch `it/s` ↔ `s/it`.
7. **Dynamic total** — PyMC. `bar.set_total(n)` when the size is discovered
   mid-run.

## How everbar already differs

- **Broader environment dispatch**: tqdm.auto covers two envs (terminal vs
  notebook); fastprogress covers the same two. everbar dispatches across
  Marimo, Rich, tqdm-notebook, tqdm-std, and a non-TTY fallback, with
  explicit overrides via `backend=` / `EVERBAR_BACKEND` / `set_default_backend`.
- **Lazy backend imports**: tqdm/rich/marimo are optional deps; the relevant
  one is imported only when its backend is selected.
- **Generic over item type**: `Progress[T]` preserves the iterated type for
  IDE / type-checker support.
- **`set_postfix`** is supported across all backends, including the Marimo
  spinner subtitle.

## Candidate next moves, ranked by everbar-fit

1. **Safe `write()`** — universally useful, only meaningful for an
   abstraction library (each backend handles it differently). Smallest lift.
2. **Multi-bar manager** — where most of the differentiation lives in this
   space. Bigger lift, distinctive.
3. **Failure state** — small, slots cleanly into the existing per-backend
   interface, ships as a real new capability.
4. **Adaptive rate units** — small QoL; tqdm already does it, FallbackBackend
   and Marimo subtitle would need it.
5. **Composable columns** — invasive; replaces or augments `set_postfix`.
   Defer unless someone asks.
