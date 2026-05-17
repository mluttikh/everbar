"""Public ``Progress`` facade. Picks a backend and delegates."""

import os
from collections.abc import Iterable, Iterator
from typing import Any, Self

from everbar._detect import detect_environment

_DEFAULT_BACKEND: str | None = None

_NOTEBOOK_ENVS = {"jupyter", "colab", "kaggle", "vscode_notebook", "databricks"}
_TQDM_STD_ENVS = {"terminal", "ipython_terminal", "spyder", "jupyter_qt"}


def set_default_backend(name: str | None) -> None:
    """Pin the backend globally. Pass ``None`` to restore auto-detection.

    Valid names: ``"marimo"``, ``"jupyter"``, ``"colab"``, ``"kaggle"``,
    ``"vscode_notebook"``, ``"jupyter_qt"``, ``"spyder"``, ``"databricks"``,
    ``"ipython_terminal"``, ``"terminal"``, ``"pyodide"``, ``"non_tty"``,
    ``"rich"``.
    """
    global _DEFAULT_BACKEND  # noqa: PLW0603 — module-level pin is the API
    _DEFAULT_BACKEND = name


class Progress:
    """A progress bar that adapts to its environment.

    Iterator form:

        for x in Progress(items, desc="Loading"):
            work(x)

    Context-manager form:

        with Progress(total=100, desc="Steps") as bar:
            for _ in range(100):
                do_step()
                bar.update(1)
    """

    def __init__(
        self,
        iterable: Iterable[Any] | None = None,
        total: int | None = None,
        desc: str = "",
        backend: str | None = None,
        *,
        disable: bool = False,
        **kwargs: Any,
    ) -> None:
        self._iterable = iterable
        self._total = total
        self._desc = desc
        self._kwargs = kwargs

        chosen = (
            backend or os.environ.get("EVERBAR_BACKEND") or _DEFAULT_BACKEND
        )
        self._env: str = chosen or detect_environment()
        self._impl = self._make_impl(disable=disable)

    def _make_impl(self, *, disable: bool) -> Any:
        from everbar import _backends

        if disable:
            return _backends.NullBackend(iterable=self._iterable)

        common = {"total": self._total, "desc": self._desc, **self._kwargs}

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
        except ImportError:
            pass

        return _backends.FallbackBackend(self._iterable, **common)

    def __iter__(self) -> Iterator[Any]:
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
