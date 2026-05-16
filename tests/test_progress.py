"""End-to-end tests for the Progress facade.

We force ``backend="non_tty"`` so tests don't depend on tqdm/marimo and don't
spam the terminal during CI.
"""

import io

from everbar import Progress, set_default_backend
from everbar._backends import FallbackBackend, NullBackend, RichBackend


def test_iterator_form_yields_all_items():
    items = [1, 2, 3, 4, 5]
    out = list(Progress(items, backend="non_tty"))
    assert out == items


def test_context_manager_updates():
    with Progress(total=10, backend="non_tty") as bar:
        for _ in range(10):
            bar.update(1)
    assert bar._impl._n == 10  # type: ignore[attr-defined]


def test_disable_uses_null_backend():
    p = Progress([1, 2, 3], disable=True)
    assert isinstance(p._impl, NullBackend)
    assert list(p) == [1, 2, 3]


def test_explicit_backend_overrides_detection():
    p = Progress([1, 2, 3], backend="non_tty")
    assert isinstance(p._impl, FallbackBackend)


def test_env_var_overrides(monkeypatch):
    monkeypatch.setenv("EVERBAR_BACKEND", "non_tty")
    p = Progress([1, 2, 3])
    assert isinstance(p._impl, FallbackBackend)


def test_set_default_backend(monkeypatch):
    monkeypatch.delenv("EVERBAR_BACKEND", raising=False)
    set_default_backend("non_tty")
    try:
        p = Progress([1, 2, 3])
        assert isinstance(p._impl, FallbackBackend)
    finally:
        set_default_backend(None)


def test_rich_backend_selected():
    p = Progress([1, 2, 3], backend="rich")
    assert isinstance(p._impl, RichBackend)


def test_rich_iterator_yields_all_items():
    from rich.console import Console

    console = Console(file=io.StringIO(), force_terminal=False)
    bar = RichBackend([1, 2, 3], total=3, desc="x", console=console)
    assert list(bar) == [1, 2, 3]


def test_rich_context_manager_updates():
    from rich.console import Console

    console = Console(file=io.StringIO(), force_terminal=False)
    bar = RichBackend(total=5, desc="x", console=console)
    with bar:
        for _ in range(5):
            bar.update(1)


def test_fallback_writes_lines(monkeypatch):
    buf = io.StringIO()
    bar = FallbackBackend(total=3, desc="x", min_interval=0.0, stream=buf)
    with bar:
        for _ in range(3):
            bar.update(1)
    output = buf.getvalue()
    assert "[progress]" in output or "[done]" in output
    assert "x" in output
