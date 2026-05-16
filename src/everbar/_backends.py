"""Progress backends.

Each backend implements the same minimal surface:

    __enter__ / __exit__   — context-manager use
    __iter__               — iterator-wrapper use
    update(n=1)            — manual advance

Backends are constructed lazily by ``Progress``. Optional third-party
dependencies (``tqdm``, ``marimo``) are imported only inside the backend
that needs them, so ``everbar`` itself has zero required deps.
"""

import sys
import time
from collections.abc import Iterable, Iterator
from contextlib import nullcontext
from typing import Any, Self


def _len_or_none(obj: Any) -> int | None:
    try:
        return len(obj)
    except (TypeError, AttributeError):
        return None


class NullBackend(nullcontext):
    """No-op backend used when ``disable=True``."""

    def __init__(self, iterable: Iterable[Any] | None = None, **_: Any) -> None:
        super().__init__()
        self._iterable = iterable

    def __iter__(self) -> Iterator[Any]:
        return iter(self._iterable or ())

    def update(self, n: int = 1) -> None:  # noqa: ARG002 — protocol shape
        return None


class FallbackBackend:
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
        **_: Any,
    ) -> None:
        self._iterable = iterable
        self._total = total if total is not None else _len_or_none(iterable)
        self._desc = desc
        self._min_interval = min_interval
        self._stream = stream if stream is not None else sys.stderr
        self._n = 0
        self._t0 = 0.0
        self._last_log = 0.0
        self._entered = False

    def __enter__(self) -> Self:
        self._t0 = time.monotonic()
        self._last_log = self._t0
        self._entered = True
        self._log(final=False)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._log(final=True)
        self._entered = False

    def __iter__(self) -> Iterator[Any]:
        with self:
            for item in self._iterable or ():
                yield item
                self.update(1)

    def update(self, n: int = 1) -> None:
        self._n += n
        now = time.monotonic()
        if now - self._last_log >= self._min_interval:
            self._last_log = now
            self._log(final=False)

    def _log(self, *, final: bool) -> None:
        elapsed = time.monotonic() - self._t0 if self._t0 else 0.0
        if self._total:
            pct = f"{100 * self._n / self._total:.0f}%"
            total_str = str(self._total)
        else:
            pct = "?"
            total_str = "?"
        marker = "done" if final else "progress"
        desc = f" {self._desc}" if self._desc else ""
        line = (
            f"[{marker}]{desc} {self._n}/{total_str}"
            f" ({pct}) elapsed={elapsed:.1f}s"
        )
        print(line, file=self._stream, flush=True)


class TqdmBackend:
    """Wraps ``tqdm``.

    Aggregates rather than subclasses so Marimo's function-style monkey-patch
    of ``tqdm_notebook`` (#4016) can't break us.
    """

    def __init__(
        self,
        iterable: Iterable[Any] | None = None,
        total: int | None = None,
        desc: str = "",
        *,
        notebook: bool = False,
        **kwargs: Any,
    ) -> None:
        if notebook:
            from tqdm.notebook import tqdm as _tqdm
        else:
            from tqdm import tqdm as _tqdm
        self._inner = _tqdm(iterable, total=total, desc=desc, **kwargs)

    def __enter__(self) -> Self:
        self._inner.__enter__()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Any:
        return self._inner.__exit__(exc_type, exc_val, exc_tb)

    def __iter__(self) -> Iterator[Any]:
        return iter(self._inner)

    def update(self, n: int = 1) -> None:
        self._inner.update(n)


class RichBackend:
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
        **kwargs: Any,
    ) -> None:
        from rich.progress import Progress as _RichProgress

        self._iterable = iterable
        self._total = total if total is not None else _len_or_none(iterable)
        self._desc = desc
        self._progress = _RichProgress(**kwargs)
        self._task_id: Any = None

    def __enter__(self) -> Self:
        self._progress.__enter__()
        self._task_id = self._progress.add_task(self._desc, total=self._total)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Any:
        return self._progress.__exit__(exc_type, exc_val, exc_tb)

    def __iter__(self) -> Iterator[Any]:
        with self:
            for item in self._iterable or ():
                yield item
                self.update(1)

    def update(self, n: int = 1) -> None:
        self._progress.update(self._task_id, advance=n)


class MarimoBackend:
    """Marimo-native bar via ``marimo.status.progress_bar``."""

    def __init__(
        self,
        iterable: Iterable[Any] | None = None,
        total: int | None = None,
        desc: str = "",
        **_: Any,
    ) -> None:
        import marimo as mo

        self._inner = mo.status.progress_bar(
            iterable,
            total=total if total is not None else _len_or_none(iterable),
            title=desc or None,
        )

    def __enter__(self) -> Self:
        self._inner.__enter__()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Any:
        return self._inner.__exit__(exc_type, exc_val, exc_tb)

    def __iter__(self) -> Iterator[Any]:
        return iter(self._inner)

    def update(self, n: int = 1) -> None:
        self._inner.update(n)
