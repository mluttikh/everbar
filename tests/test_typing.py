"""Static-typing contracts for the Progress facade.

These pass at runtime because ``assert_type`` is a no-op; they fail under
mypy / pyright if generic propagation regresses.
"""

from typing import assert_type

from everbar import Progress


def test_iteration_preserves_int_type() -> None:
    for x in Progress(range(10), backend="non_tty"):
        assert_type(x, int)


def test_iteration_preserves_str_type() -> None:
    items: list[str] = ["a", "b"]
    for s in Progress(items, backend="non_tty"):
        assert_type(s, str)
