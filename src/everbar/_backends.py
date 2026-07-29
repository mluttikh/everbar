"""Progress backends.

Each backend implements the same minimal surface:

    __enter__ / __exit__   — context-manager use
    __iter__               — iterator-wrapper use
    update(n=1)            — manual advance
    set_postfix(**kwargs)  — live key/value suffix (e.g. loss=0.42)
    fail()                 — mark the bar as failing (sticky)

The ``Backend`` Protocol below states that surface for type-checking;
``Progress`` delegates through it.

Both forms may be mixed (``with Progress(items) as bar: for x in bar``),
and ``update()``/``set_postfix()``/``fail()`` are safe before the
context is entered — state is recorded, though the Rich backend only
starts rendering once entered. ``__iter__`` enters the context for the
duration of the loop if the caller hasn't already.

Iterating a bar a second time restarts it rather than continuing past
the total. Since tqdm and marimo indicators are single-use once closed,
"restart" means rebuilding the underlying object for those two; the
sticky ``fail()`` state carries across runs on every backend.

All backends additionally accept ``unit`` at construction time — a
label like ``"files"`` or ``"B"``. Rendering varies per backend; see
``Progress.__init__`` for the high-level behavior.

Backends are constructed lazily by ``Progress``. Optional third-party
dependencies (``tqdm``, ``marimo``) are imported only inside the backend
that needs them, so ``everbar`` itself has zero required deps.
"""

import sys
import time
from collections.abc import Iterable, Iterator
from contextlib import nullcontext
from typing import TYPE_CHECKING, Any, Protocol, Self


class Backend(Protocol):
    """The surface every backend implements, as ``Progress`` uses it.

    Spelling the contract as a Protocol (rather than leaving
    ``Progress._impl`` typed ``Any``) makes it machine-checked:
    ``Progress._make_impl`` is annotated to return a ``Backend``, so a
    backend that drifts out of shape fails type-checking at its return
    statement instead of at runtime in whichever environment happens to
    select it.
    """

    def __enter__(self) -> Any: ...

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Any: ...

    def __iter__(self) -> Iterator[Any]: ...

    def update(self, n: int = 1) -> None: ...

    def set_postfix(self, **kwargs: Any) -> None: ...

    def fail(self) -> None: ...


def _len_or_none(obj: Any) -> int | None:
    try:
        return len(obj)
    except (TypeError, AttributeError):
        return None


def _format_postfix(items: dict[str, Any]) -> str:
    parts = [
        f"{k}={v:.3g}" if isinstance(v, float) else f"{k}={v}"
        for k, v in items.items()
    ]
    return ", ".join(parts)


class _IterUpdatingMixin:
    """Shared iterator form: yield each item, advancing the bar by one.

    Host classes provide ``_iterable``, ``_entered``, ``update()``,
    ``_reset()``, and the context-manager protocol. ``__iter__`` enters
    the backend for the duration of the loop unless the caller already
    has (mixed context-manager + iterator form). The ``is None`` check
    (rather than truthiness) matters: iterables like numpy arrays raise
    on ``__bool__``.

    Each owned iteration after the first resets the count, so
    re-iterating a bar restarts it rather than accumulating past the
    total (``list(bar); list(bar)`` used to end at ``6/3 (200%)``). The
    reset is deliberately skipped for the *first* owned iteration so
    that manual ``update()`` calls made before iterating still count,
    and it happens before entering rather than in ``__enter__`` so that
    pre-enter state survives a plain ``with`` block.

    Entering the context *while* an iterator that owns it is mid-loop
    (``it = iter(bar); next(it); with bar: ...``) is unsupported.
    """

    _iterable: Iterable[Any] | None
    _entered: bool
    _owned_run_started: bool = False

    if TYPE_CHECKING:

        def __enter__(self) -> Self: ...

        def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Any: ...

        def update(self, n: int = 1) -> None: ...

        def _reset(self) -> None: ...

    def __iter__(self) -> Iterator[Any]:
        # Decide ownership NOW, not lazily inside the generator: an
        # iterator created while the context is entered must not
        # re-enter the backend even if consumed after the context exits.
        return self._iterate(owns_context=not self._entered)

    def _iterate(self, *, owns_context: bool) -> Iterator[Any]:
        if owns_context:
            # Flag set on entry, not on completion: a loop abandoned via
            # break unwinds through GeneratorExit, so anything after the
            # `with` below may never run.
            if self._owned_run_started:
                self._reset()
            self._owned_run_started = True
            with self:
                yield from self._iter_updating()
        else:
            yield from self._iter_updating()

    def _iter_updating(self) -> Iterator[Any]:
        if self._iterable is None:
            return
        for item in self._iterable:
            yield item
            self.update(1)


class NullBackend(nullcontext):
    """No-op backend used when ``disable=True``."""

    def __init__(self, iterable: Iterable[Any] | None = None, **_: Any) -> None:
        super().__init__()
        self._iterable = iterable

    def __iter__(self) -> Iterator[Any]:
        return iter(()) if self._iterable is None else iter(self._iterable)

    def update(self, n: int = 1) -> None:  # noqa: ARG002 — protocol shape
        return None

    def set_postfix(self, **kwargs: Any) -> None:  # noqa: ARG002 — protocol shape
        return None

    def fail(self) -> None:
        return None


class FallbackBackend(_IterUpdatingMixin):
    r"""Log-line backend for non-TTY environments.

    Emits one line every ``min_interval`` seconds. Suitable for CI logs,
    Kubernetes, CloudWatch — anywhere ``\r`` would just produce spam.
    """

    def __init__(
        self,
        iterable: Iterable[Any] | None = None,
        total: int | None = None,
        desc: str = "",
        *,
        min_interval: float = 2.0,
        stream: Any = None,
        unit: str | None = None,
        **_: Any,
    ) -> None:
        self._iterable = iterable
        self._total = total if total is not None else _len_or_none(iterable)
        self._desc = desc
        self._unit = unit
        self._min_interval = min_interval
        self._stream = stream if stream is not None else sys.stderr
        self._n = 0
        self._t0 = 0.0
        self._last_log = 0.0
        self._entered = False
        self._postfix = ""
        self._failing = False

    def __enter__(self) -> Self:
        self._t0 = time.monotonic()
        self._last_log = self._t0
        self._entered = True
        self._log(final=False)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        # Claim "done" only on a clean exit: an exception or an abandoned
        # iterator (GeneratorExit via break) must not log success.
        self._log(final=exc_type is None)
        self._entered = False

    def update(self, n: int = 1) -> None:
        self._n += n
        now = time.monotonic()
        if now - self._last_log >= self._min_interval:
            self._last_log = now
            self._log(final=False)

    def set_postfix(self, **kwargs: Any) -> None:
        self._postfix = _format_postfix(kwargs)

    def fail(self) -> None:
        # Log only the transition into the failing state; repeated fail()
        # calls (e.g. once per item after an error) must not spam the log.
        if self._failing:
            return
        self._failing = True
        self._log(final=False)

    def _reset(self) -> None:
        self._n = 0

    def _log(self, *, final: bool) -> None:
        elapsed = time.monotonic() - self._t0 if self._t0 else 0.0
        if self._total is not None:
            # `is not None`, not truthiness: total=0 (an empty collection)
            # is a known total, and there is nothing left to do, so it is
            # complete rather than unknown. Guarding the division keeps
            # the 0/0 case from raising.
            if self._total:
                pct = f"{100 * self._n / self._total:.0f}%"
            else:
                pct = "100%"
            total_str = str(self._total)
        else:
            pct = "?"
            total_str = "?"
        if self._failing:
            marker = "failing"
        elif final:
            marker = "done"
        else:
            marker = "progress"
        desc = f" {self._desc}" if self._desc else ""
        unit = f" {self._unit}" if self._unit else ""
        postfix = f" [{self._postfix}]" if self._postfix else ""
        line = (
            f"[{marker}]{desc} {self._n}/{total_str}{unit}"
            f" ({pct}) elapsed={elapsed:.1f}s{postfix}"
        )
        print(line, file=self._stream, flush=True)


class TqdmBackend(_IterUpdatingMixin):
    """Wraps ``tqdm``.

    Aggregates rather than subclasses so Marimo's function-style monkey-patch
    of ``tqdm_notebook`` (#4016) can't break us. Iteration is driven by
    everbar (the iterable is never handed to tqdm): tqdm's own iterator
    closes the bar on exhaustion, which would silently drop update()/
    set_postfix()/fail() calls made after a mixed-form loop finishes.
    """

    def __init__(
        self,
        iterable: Iterable[Any] | None = None,
        total: int | None = None,
        desc: str = "",
        *,
        notebook: bool = False,
        unit: str | None = None,
        **kwargs: Any,
    ) -> None:
        if notebook:
            from tqdm.notebook import tqdm as _tqdm
        else:
            from tqdm import tqdm as _tqdm
        if unit is not None:
            kwargs["unit"] = unit
        self._iterable = iterable
        self._entered = False
        # Constructor args are kept so a fresh run can rebuild the bar.
        self._tqdm_cls = _tqdm
        self._tqdm_kwargs: dict[str, Any] = {
            "total": total if total is not None else _len_or_none(iterable),
            "desc": desc,
            **kwargs,
        }
        self._inner = self._tqdm_cls(**self._tqdm_kwargs)

    def __enter__(self) -> Self:
        self._inner.__enter__()
        self._entered = True
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Any:
        self._entered = False
        return self._inner.__exit__(exc_type, exc_val, exc_tb)

    def update(self, n: int = 1) -> None:
        self._inner.update(n)

    def set_postfix(self, **kwargs: Any) -> None:
        self._inner.set_postfix(**kwargs)

    def fail(self) -> None:
        self._inner.colour = "red"
        self._inner.refresh()

    def _reset(self) -> None:
        # Not tqdm.reset(): __exit__ has already closed the bar, and
        # close() sets disable=True, so every subsequent update() is
        # dropped — reset() alone would leave the bar stuck at 0. Build a
        # fresh one instead, carrying over a red fail() colour so the
        # failing state stays sticky as it does on the other backends.
        colour = self._inner.colour
        if not self._inner.disable:
            self._inner.close()
        self._inner = self._tqdm_cls(**self._tqdm_kwargs)
        self._inner.colour = colour


class RichBackend(_IterUpdatingMixin):
    """Wraps ``rich.progress.Progress``.

    Opt-in only — selected via ``backend="rich"`` or ``EVERBAR_BACKEND=rich``.
    Extra kwargs are forwarded to ``rich.progress.Progress`` (e.g. pass
    ``console=Console(file=...)`` to redirect output in tests).
    """

    def __init__(
        self,
        iterable: Iterable[Any] | None = None,
        total: int | None = None,
        desc: str = "",
        unit: str | None = None,
        **kwargs: Any,
    ) -> None:
        from rich.progress import (
            BarColumn,
            MofNCompleteColumn,
            TaskProgressColumn,
            TextColumn,
            TimeRemainingColumn,
        )
        from rich.progress import (
            Progress as _RichProgress,
        )

        self._iterable = iterable
        self._total = total if total is not None else _len_or_none(iterable)
        self._desc = desc
        self._unit = unit
        if unit is not None:
            # Mirror rich's default column set, inserting a count + unit
            # block between the bar and the percentage.
            #
            # The unit is rendered from a task *field* rather than baked
            # into the column's format string, and with markup disabled.
            # Both matter because the unit is caller data: TextColumn
            # runs .format() on its text_format, so a literal unit like
            # "{files}" raised KeyError, and Text.from_markup would eat a
            # unit like "[bold]B" as styling. Via a field the value is
            # substituted, never re-parsed.
            columns = (
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                TextColumn("{task.fields[unit]}", markup=False),
                TaskProgressColumn(),
                TimeRemainingColumn(),
            )
            self._progress = _RichProgress(*columns, **kwargs)
        else:
            self._progress = _RichProgress(**kwargs)
        # Create the task eagerly (but unstarted) so update()/set_postfix()/
        # fail() before __enter__ record state without crashing. Rendering
        # and the task clock (elapsed / finished-time) start at __enter__.
        self._task_id = self._progress.add_task(
            self._desc, total=self._total, start=False, unit=unit or ""
        )
        self._entered = False
        self._postfix = ""
        self._failing = False

    def __enter__(self) -> Self:
        self._progress.__enter__()
        # Idempotent — start_task only sets start_time if it is unset.
        self._progress.start_task(self._task_id)
        self._entered = True
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Any:
        self._entered = False
        return self._progress.__exit__(exc_type, exc_val, exc_tb)

    def update(self, n: int = 1) -> None:
        self._progress.update(self._task_id, advance=n)

    def set_postfix(self, **kwargs: Any) -> None:
        self._postfix = _format_postfix(kwargs)
        self._progress.update(self._task_id, description=self._build_desc())

    def fail(self) -> None:
        self._failing = True
        self._progress.update(self._task_id, description=self._build_desc())

    def _reset(self) -> None:
        # start=False leaves the clock for __enter__ to start, matching
        # construction. Omitting description/fields preserves the sticky
        # FAIL prefix and the unit column.
        self._progress.reset(self._task_id, start=False)

    def _build_desc(self) -> str:
        # Rich parses [...] as markup, so escape the auto-formatted postfix
        # to avoid stripping values like loss=[1,2,3]. Description stays
        # unescaped — callers may pass intentional markup in desc.
        from rich.markup import escape

        prefix = "[red]FAIL[/red] " if self._failing else ""
        suffix = f" | {escape(self._postfix)}" if self._postfix else ""
        return f"{prefix}{self._desc}{suffix}"


class MarimoBackend(_IterUpdatingMixin):
    """Marimo-native bar via ``marimo.status.progress_bar``.

    Falls back to ``marimo.status.spinner`` when the total is unknown,
    since Marimo's progress bar requires a known total and has no
    indeterminate mode. The spinner shows a running count in its subtitle.

    Iteration is driven by everbar (never via marimo's own progress_bar
    iterator) so the tracker is live during the loop — set_postfix()/
    fail() on a kept handle must keep working.
    """

    def __init__(
        self,
        iterable: Iterable[Any] | None = None,
        total: int | None = None,
        desc: str = "",
        unit: str | None = None,
        **_: Any,
    ) -> None:
        import marimo as mo

        self._mo = mo
        self._iterable = iterable
        self._desc = desc
        self._unit = unit
        self._postfix = ""
        self._n = 0
        self._entered = False
        self._closed = False
        self._failing = False
        self._failure_announced = False
        self._inner: Any
        self._tracker: Any = None

        self._resolved_total = (
            total if total is not None else _len_or_none(iterable)
        )
        self._build_inner()

    def _build_inner(self) -> None:
        """Construct the marimo indicator. Also used to rebuild on reset.

        Marimo's indicators are single-use — once the context exits they
        raise on any update — so re-iterating means building a fresh one
        rather than rewinding the existing one.
        """
        if self._resolved_total is None:
            self._mode = "spinner"
            # remove_on_exit=True so the animation stops; we render a
            # static "done" line in __exit__ since Marimo's spinner has
            # no done state (upstream TODO). The Spinner tracker only
            # exists once entered, so updates before __enter__ are
            # recorded in our own state and synced on entry.
            self._inner = self._mo.status.spinner(
                title=self._desc or None, remove_on_exit=True
            )
            self._tracker = None
        else:
            self._mode = "bar"
            # The iterable is deliberately not handed to marimo: everbar
            # drives iteration itself and total is always passed, so the
            # collection would be dead weight.
            self._inner = self._mo.status.progress_bar(
                total=self._resolved_total,
                title=self._desc or None,
                subtitle=self._unit or None,
            )
            # The ProgressBar tracker exists from construction; grab it
            # eagerly so update()/set_postfix()/fail() work before
            # __enter__, matching the tqdm and fallback backends.
            self._tracker = self._inner.progress

    def __enter__(self) -> Self:
        self._tracker = self._inner.__enter__()
        self._entered = True
        if self._mode == "spinner" and (self._n or self._postfix):
            self._tracker.update(subtitle=self._spinner_subtitle())
        if self._failing:
            self._apply_failing_title()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Any:
        self._entered = False
        result = self._inner.__exit__(exc_type, exc_val, exc_tb)
        # Marimo raises if a closed indicator is updated; from here on,
        # update()/set_postfix()/fail() record state only.
        self._closed = True
        # No "Done" line after fail(): the FAILED badge already tells the
        # story, and announcing both would contradict the sticky state.
        if self._mode == "spinner" and exc_type is None and not self._failing:
            parts = [self._desc] if self._desc else []
            parts.append(f"{self._n} {self._unit or 'items'}")
            if self._postfix:
                parts.append(self._postfix)
            self._mo.output.append(self._mo.md(f"Done — {' — '.join(parts)}"))
        return result

    def update(self, n: int = 1) -> None:
        self._n += n
        if self._tracker is None or self._closed:
            # Spinner mode before __enter__, or any mode after exit —
            # record the count; there is no live tracker to render it.
            return
        if self._mode == "spinner":
            self._tracker.update(subtitle=self._spinner_subtitle())
        else:
            self._tracker.update(n)

    def set_postfix(self, **kwargs: Any) -> None:
        self._postfix = _format_postfix(kwargs)
        if self._tracker is None or self._closed:
            # Spinner mode before __enter__, or any mode after exit.
            return
        if self._mode == "spinner":
            self._tracker.update(subtitle=self._spinner_subtitle())
        else:
            self._tracker.update(increment=0, subtitle=self._bar_subtitle())

    def _bar_subtitle(self) -> str:
        parts = []
        if self._unit:
            parts.append(self._unit)
        if self._postfix:
            parts.append(self._postfix)
        # "" rather than None when empty: marimo treats subtitle=None as
        # "leave unchanged", which would make a cleared postfix stick.
        return " | ".join(parts)

    def fail(self) -> None:
        self._failing = True
        if self._tracker is not None and not self._closed:
            self._apply_failing_title()
        if not self._failure_announced:
            label = f"FAILED — {self._desc}" if self._desc else "FAILED"
            badge = (
                '<span style="display:inline-block;'
                "padding:2px 8px;margin-top:4px;"
                "background:#d62728;color:white;"
                "border-radius:4px;font-weight:600;"
                "font-size:0.85em;"
                'font-family:system-ui,sans-serif;">'
                f"{label}</span>"
            )
            self._mo.output.append(self._mo.Html(badge))
            self._failure_announced = True

    def _reset(self) -> None:
        # A closed marimo indicator raises on any update, so rebuild
        # rather than rewind. _failing / _failure_announced stay sticky:
        # the failure carries across runs (as it does on tqdm and rich)
        # and its badge is already in the cell output.
        self._n = 0
        self._closed = False
        self._build_inner()

    def _apply_failing_title(self) -> None:
        # Marimo's progress UI can't recolor the bar, so we rewrite the
        # title with an uppercase tag. PyMC's approach (custom HTML bar
        # via mo.output.replace) is the only way to recolor the bar.
        title = f"[FAILING] {self._desc}" if self._desc else "[FAILING]"
        if self._mode == "spinner":
            self._tracker.update(title=title)
        else:
            self._tracker.update(increment=0, title=title)

    def _spinner_subtitle(self) -> str:
        parts = [f"{self._n} {self._unit or 'items'}"]
        if self._postfix:
            parts.append(self._postfix)
        return " | ".join(parts)
