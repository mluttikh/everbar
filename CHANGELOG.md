# Changelog

## Unreleased (0.3.0)

### Breaking

- `backend="jupyter_qt"` and `set_default_backend("jupyter_qt")` now
  raise `ValueError`. Detection never returned `jupyter_qt` (Qt console
  is detected as `jupyter`), so the name was dead; pick `"terminal"` or
  `"jupyter"` explicitly if you relied on it.
- Unknown backend names passed to `Progress(backend=...)` or
  `set_default_backend()` raise `ValueError` instead of silently
  falling back to the text backend. An unknown `EVERBAR_BACKEND` value
  warns once per process and is ignored.
- Requesting a backend in code (`backend=` or `set_default_backend`)
  whose dependency is not installed raises `ImportError` instead of
  silently degrading. `EVERBAR_BACKEND` degrades to the text fallback
  with a warning (once per process per value, like the unknown-name
  warning above); auto-detection degrades silently.
- Iterating a `Progress` constructed without an iterable raises
  `TypeError` (unless `disable=True`, which stays an empty loop).

### Fixed

- `__version__` now reports the installed version (was hardcoded
  `0.1.0`) and is resolved lazily so it no longer slows down
  `import everbar`.
- Shipped a `py.typed` marker so type checkers see the generic
  `Progress[T]` typing.
- Mixed context-manager + iterator form (`with Progress(items) as bar:
  for x in bar`) no longer double-enters, on any backend — including
  tqdm, where post-loop `fail()`/`set_postfix()` used to be silently
  dropped because tqdm auto-closes its own iterator.
- Marimo: `set_postfix()`/`fail()` during iterator-form iteration work
  on a kept handle; calls after the bar closes are safe no-ops; a
  cleared postfix actually clears; no contradictory "Done" line after
  `fail()`.
- Rich: `update()`/`set_postfix()`/`fail()` before `__enter__` no
  longer crash, and the task clock starts at `__enter__`, not at
  construction.
- The non-TTY fallback no longer logs a `[done]` success marker when a
  loop is aborted (`break`/exception), and `fail()` logs only the
  transition instead of every call.
- Iterables that reject truthiness testing (e.g. numpy arrays) iterate
  correctly on every backend.
- A known total of `0` (e.g. `Progress([])`) is reported as complete —
  `0/0 (100%)` — instead of being mistaken for an unknown total and
  logged as `0/? (?)`.
- Rich: `unit` is rendered verbatim. It was baked into the column's
  format string and parsed as console markup, so a unit containing
  braces (`unit="{files}"`) raised `KeyError` and one containing
  brackets (`unit="[bold]B"`) was silently swallowed as styling.
- Iterating a bar twice restarts it instead of running past the total
  (`list(bar); list(bar)` ended at `6/3 (200%)`). On marimo this also
  fixes an outright crash — its indicators reject updates once closed,
  so a second pass raised `RuntimeError`; tqdm bars, which ignore
  updates after `close()`, silently stayed at `0`. Manual `update()`
  calls made before the first iteration still count.
- First-call latency: environment detection no longer imports marimo or
  IPython in plain scripts (~325 ms → ~20 ms with all extras installed).

### Added

- `fail()` to mark a bar as failing (sticky, backend-specific
  rendering).
- `unit=` to label what's being counted.
- `Environment` exported for typing against `detect_environment()`.
- mypy in CI, making the `assert_type` typing contracts live.
- An internal `Backend` Protocol capturing the five-method backend
  contract. `Progress` now delegates through it instead of through
  `Any`, so a backend that drifts out of shape is caught by mypy rather
  than at runtime in whichever environment selects it.
