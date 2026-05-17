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


def test_rich_postfix_appears_in_description():
    """Regression: brackets like [i=9] were being stripped as Rich markup."""
    from rich.console import Console

    console = Console(file=io.StringIO(), force_terminal=False)
    bar = RichBackend(total=3, desc="Loading", console=console)
    with bar:
        bar.set_postfix(i=9, values=[1, 2, 3])
        description = bar._progress.tasks[bar._task_id].description
    assert "i=9" in description
    assert "[1, 2, 3]" in description


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


def test_fallback_renders_postfix():
    buf = io.StringIO()
    bar = FallbackBackend(total=2, min_interval=0.0, stream=buf)
    with bar:
        bar.set_postfix(loss=0.4242, step=7)
        bar.update(1)
    output = buf.getvalue()
    assert "loss=0.424" in output
    assert "step=7" in output


def test_set_postfix_on_null_backend_is_noop():
    p = Progress([1, 2, 3], disable=True)
    p.set_postfix(loss=0.1)
    assert list(p) == [1, 2, 3]


def test_set_postfix_via_facade():
    p = Progress(total=3, backend="non_tty")
    with p:
        p.set_postfix(loss=0.5)
        p.update(1)
    assert p._impl._postfix == "loss=0.5"  # type: ignore[attr-defined]
