"""Progress backends.

Each backend implements the same minimal surface:

    __enter__ / __exit__   — context-manager use
    __iter__               — iterator-wrapper use
    update(n=1)            — manual advance
    set_postfix(**kwargs)  — live key/value suffix (e.g. loss=0.42)
    fail()                 — mark the bar as failing (sticky)

Both forms may be mixed (``with Progress(items) as bar: for x in bar``),
and ``update()``/``set_postfix()``/``fail()`` are safe before the
context is entered — state is recorded, though the Rich backend only
starts rendering once entered. ``__iter__`` enters the context for the
duration of the loop if the caller hasn't already.

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
from typing import TYPE_CHECKING, Any, Self, cast

if TYPE_CHECKING:
    from collections.abc import Collection


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

    Host classes provide ``_iterable``, ``_entered``, ``update()``, and
    the context-manager protocol. ``__iter__`` enters the backend for
    the duration of the loop unless the caller already has (mixed
    context-manager + iterator form). The ``is None`` check (rather
    than truthiness) matters: iterables like numpy arrays raise on
    ``__bool__``.
    """

    _iterable: Iterable[Any] | None
    _entered: bool

    if TYPE_CHECKING:

        def __enter__(self) -> Self: ...

        def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Any: ...

        def update(self, n: int = 1) -> None: ...

    def __iter__(self) -> Iterator[Any]:
        if self._entered:
            yield from self._iter_updating()
        else:
            with self:
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
        self._log(final=True)
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

    def _log(self, *, final: bool) -> None:
        elapsed = time.monotonic() - self._t0 if self._t0 else 0.0
        if self._total:
            pct = f"{100 * self._n / self._total:.0f}%"
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
        self._inner = _tqdm(
            total=total if total is not None else _len_or_none(iterable),
            desc=desc,
            **kwargs,
        )

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
            columns = (
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                TextColumn(unit),
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
            self._desc, total=self._total, start=False
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

        resolved_total = total if total is not None else _len_or_none(iterable)
        if resolved_total is None:
            self._mode = "spinner"
            # remove_on_exit=True so the animation stops; we render a
            # static "done" line in __exit__ since Marimo's spinner has
            # no done state (upstream TODO). The Spinner tracker only
            # exists once entered, so updates before __enter__ are
            # recorded in our own state and synced on entry.
            self._inner = mo.status.spinner(
                title=desc or None, remove_on_exit=True
            )
        else:
            self._mode = "bar"
            if iterable is None:
                self._inner = mo.status.progress_bar(
                    total=resolved_total,
                    title=desc or None,
                    subtitle=unit or None,
                )
            else:
                # The cast satisfies marimo's overloads; bar mode implies
                # the iterable is sized or an explicit total was given.
                self._inner = mo.status.progress_bar(
                    cast("Collection[Any]", iterable),
                    total=resolved_total,
                    title=desc or None,
                    subtitle=unit or None,
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
        if self._mode == "spinner" and exc_type is None:
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

    def _bar_subtitle(self) -> str | None:
        parts = []
        if self._unit:
            parts.append(self._unit)
        if self._postfix:
            parts.append(self._postfix)
        return " | ".join(parts) if parts else None

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
