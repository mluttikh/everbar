"""Static-typing contracts for the Progress facade.

These pass at runtime because ``assert_type`` is a no-op; they fail under
mypy (run in CI) if generic propagation regresses.
"""

from typing import Any, assert_type

from everbar import Progress


def test_iteration_preserves_int_type() -> None:
    for x in Progress(range(10), backend="non_tty"):
        assert_type(x, int)


def test_bare_construction_binds_to_any() -> None:
    """No iterable means T can't be inferred — the overload must bind it
    to Any so callers don't need an explicit ``Progress[...]`` annotation."""
    bar = Progress(total=10, backend="non_tty")
    assert_type(bar, Progress[Any])


def test_iteration_preserves_str_type() -> None:
    items: list[str] = ["a", "b"]
    for s in Progress(items, backend="non_tty"):
        assert_type(s, str)


def test_backends_satisfy_the_backend_protocol() -> None:
    """The facade delegates through ``Backend``; a backend that drifts out
    of shape must fail type-checking rather than at runtime in whichever
    environment happens to select it."""
    import io

    from rich.console import Console

    from everbar._backends import (
        Backend,
        FallbackBackend,
        NullBackend,
        RichBackend,
        TqdmBackend,
    )

    # Quiet sinks — these construct real bars, which would otherwise
    # write to the terminal during CI.
    backends: list[Backend] = [
        NullBackend(),
        FallbackBackend(stream=io.StringIO()),
        RichBackend(console=Console(file=io.StringIO())),
        TqdmBackend(file=io.StringIO()),
    ]
    for backend in backends:
        assert hasattr(backend, "fail")
