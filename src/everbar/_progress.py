"""Public ``Progress`` facade. Picks a backend and delegates."""

import os
import warnings
from collections.abc import Iterable, Iterator
from typing import Any, Generic, Self, TypeVar, overload

from everbar._detect import detect_environment

T = TypeVar("T")

_DEFAULT_BACKEND: str | None = None

_NOTEBOOK_ENVS = {"jupyter", "colab", "kaggle", "vscode_notebook", "databricks"}
_TQDM_STD_ENVS = {"terminal", "ipython_terminal", "spyder"}

_VALID_BACKENDS = frozenset(
    {"marimo", "rich", "pyodide", "non_tty"} | _NOTEBOOK_ENVS | _TQDM_STD_ENVS
)


def set_default_backend(name: str | None) -> None:
    """Pin the backend globally. Pass ``None`` to restore auto-detection.

    Valid names: ``"marimo"``, ``"jupyter"``, ``"colab"``, ``"kaggle"``,
    ``"vscode_notebook"``, ``"spyder"``, ``"databricks"``,
    ``"ipython_terminal"``, ``"terminal"``, ``"pyodide"``, ``"non_tty"``,
    ``"rich"``.

    Raises:
        ValueError: If ``name`` is not a known backend.
    """
    if name is not None and name not in _VALID_BACKENDS:
        raise ValueError(
            f"unknown backend {name!r}; valid backends: "
            f"{', '.join(sorted(_VALID_BACKENDS))}"
        )
    global _DEFAULT_BACKEND  # noqa: PLW0603 — module-level pin is the API
    _DEFAULT_BACKEND = name


class Progress(Generic[T]):
    """A progress bar that adapts to its environment.

    Iterator form (item type is preserved — ``x`` is inferred as ``int``):

        for x in Progress(range(10), desc="Loading"):
            work(x)

    Context-manager form:

        with Progress(total=100, desc="Steps") as bar:
            for _ in range(100):
                do_step()
                bar.update(1)

    Pass ``unit`` to label what's being counted (``"files"``, ``"B"``).
    Rendering is backend-specific: tqdm shows it in the rate column
    (``5files/s``), Rich adds a count + unit column, Marimo shows it in
    the bar subtitle, and the non-TTY fallback inlines it in the log
    line (``5/10 files (50%)``).

    Extra keyword arguments are forwarded to whichever backend is
    selected, so they are environment-specific by nature (tqdm's
    ``colour``, Rich's ``console``, the fallback's ``min_interval``).
    Code that must run everywhere should stick to the named parameters.
    """

    # Overloads so type checkers solve T: from the iterable when given,
    # to Any when constructed bare (e.g. Progress(total=10)) — without
    # them, mypy demands an explicit ``Progress[...]`` annotation.
    @overload
    def __init__(
        self,
        iterable: Iterable[T],
        total: int | None = None,
        desc: str = "",
        backend: str | None = None,
        *,
        disable: bool = False,
        unit: str | None = None,
        **kwargs: Any,
    ) -> None: ...

    @overload
    def __init__(
        self: "Progress[Any]",
        iterable: None = None,
        total: int | None = None,
        desc: str = "",
        backend: str | None = None,
        *,
        disable: bool = False,
        unit: str | None = None,
        **kwargs: Any,
    ) -> None: ...

    def __init__(
        self,
        iterable: Iterable[T] | None = None,
        total: int | None = None,
        desc: str = "",
        backend: str | None = None,
        *,
        disable: bool = False,
        unit: str | None = None,
        **kwargs: Any,
    ) -> None:
        if backend is not None and backend not in _VALID_BACKENDS:
            raise ValueError(
                f"unknown backend {backend!r}; valid backends: "
                f"{', '.join(sorted(_VALID_BACKENDS))}"
            )

        env_backend = os.environ.get("EVERBAR_BACKEND")
        if env_backend and env_backend not in _VALID_BACKENDS:
            # Warn-and-ignore rather than raise: a stale deploy-time env
            # var shouldn't crash scripts that never asked for it.
            warnings.warn(
                f"ignoring EVERBAR_BACKEND={env_backend!r}: not a known "
                f"backend (valid: {', '.join(sorted(_VALID_BACKENDS))})",
                stacklevel=2,
            )
            env_backend = None

        self._iterable = iterable
        self._total = total
        self._desc = desc
        self._unit = unit
        self._kwargs = kwargs

        chosen = backend or env_backend or _DEFAULT_BACKEND
        # backend= and set_default_backend() are code-level intent whose
        # missing dependencies should raise; EVERBAR_BACKEND is deploy-time
        # config, which degrades to the fallback with a warning instead.
        self._from_env = backend is None and bool(env_backend)
        self._explicit = chosen is not None and not self._from_env
        self._env: str = chosen or detect_environment()
        self._impl = self._make_impl(disable=disable)

    def _make_impl(self, *, disable: bool) -> Any:
        from everbar import _backends

        if disable:
            return _backends.NullBackend(iterable=self._iterable)

        common = {
            "total": self._total,
            "desc": self._desc,
            "unit": self._unit,
            **self._kwargs,
        }

        try:
            if self._env == "rich":
                return _backends.RichBackend(self._iterable, **common)
            if self._env == "marimo":
                return _backends.MarimoBackend(self._iterable, **common)
            if self._env in _NOTEBOOK_ENVS:
                return _backends.TqdmBackend(
                    self._iterable, notebook=True, **common
                )
            if self._env in _TQDM_STD_ENVS:
                return _backends.TqdmBackend(
                    self._iterable, notebook=False, **common
                )
        except ImportError as e:
            # Auto-detected environments degrade silently to the text
            # fallback; a backend requested in code must not.
            if self._explicit:
                raise ImportError(
                    f"backend {self._env!r} was requested explicitly but "
                    f"its dependencies are not installed: {e}"
                ) from e
            if self._from_env:
                warnings.warn(
                    f"EVERBAR_BACKEND={self._env!r} is set but its "
                    f"dependencies are not installed; using the text "
                    f"fallback: {e}",
                    stacklevel=3,
                )

        return _backends.FallbackBackend(self._iterable, **common)

    def __iter__(self) -> Iterator[T]:
        if self._iterable is None:
            raise TypeError(
                "this Progress was constructed without an iterable; "
                "drive it manually with update() instead"
            )
        return iter(self._impl)

    def __enter__(self) -> Self:
        self._impl.__enter__()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Any:
        return self._impl.__exit__(exc_type, exc_val, exc_tb)

    def update(self, n: int = 1) -> None:
        self._impl.update(n)

    def set_postfix(self, **kwargs: Any) -> None:
        """Set a live key/value suffix shown next to the bar.

        Numbers are formatted compactly (``loss=0.42, lr=0.001``).
        Calling again replaces the previous postfix.
        """
        self._impl.set_postfix(**kwargs)

    def fail(self) -> None:
        """Mark the bar as failing.

        Rendering is backend-specific: red bar in tqdm/Rich, ``[failing]``
        marker in non-TTY logs, ``[FAILING]`` title prefix plus a compact
        red ``FAILED`` badge in Marimo. The state is sticky — useful when
        one task in a batch errors but the overall job continues.
        """
        self._impl.fail()
