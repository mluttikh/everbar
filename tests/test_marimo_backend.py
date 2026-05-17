"""Unit tests for MarimoBackend.

Marimo's progress/spinner objects are usable outside a notebook (their
output side-effects no-op), so we drive them directly and assert on the
inner state they expose.
"""

import pytest

marimo = pytest.importorskip("marimo")

from everbar._backends import MarimoBackend  # noqa: E402


def test_known_total_picks_bar_mode():
    bar = MarimoBackend(total=5, desc="x")
    assert bar._mode == "bar"


def test_unknown_total_picks_spinner_mode():
    bar = MarimoBackend()
    assert bar._mode == "spinner"


def test_sized_iterable_picks_bar_mode():
    bar = MarimoBackend([1, 2, 3])
    assert bar._mode == "bar"


def test_generator_picks_spinner_mode():
    def gen():
        yield from range(3)

    bar = MarimoBackend(gen())
    assert bar._mode == "spinner"


def test_bar_update_advances_count():
    """Regression: update() was called on the outer factory and AttributeError'd."""
    with MarimoBackend(total=5, desc="x") as bar:
        bar.update(2)
        bar.update(1)
        assert bar._inner.progress.current == 3


def test_bar_set_postfix_sets_subtitle():
    with MarimoBackend(total=3, desc="x") as bar:
        bar.set_postfix(loss=0.42, step=1)
    assert "loss=0.42" in bar._inner.progress.subtitle
    assert "step=1" in bar._inner.progress.subtitle


def test_bar_iteration_yields_items():
    bar = MarimoBackend([10, 20, 30], desc="x")
    assert list(bar) == [10, 20, 30]


def test_spinner_iteration_streams_generator():
    """Regression: unknown-length iterable used to raise; should stream lazily."""

    def gen():
        yield from range(4)

    bar = MarimoBackend(gen(), desc="x")
    assert list(bar) == [0, 1, 2, 3]
    assert bar._n == 4


def test_spinner_subtitle_shows_running_count():
    with MarimoBackend(desc="x") as bar:
        bar.update(1)
        bar.update(2)
    assert "3 items" in bar._inner.spinner.subtitle


def test_spinner_set_postfix_appears_in_subtitle():
    with MarimoBackend(desc="x") as bar:
        bar.update(1)
        bar.set_postfix(loss=0.1)
    subtitle = bar._inner.spinner.subtitle
    assert "1 items" in subtitle
    assert "loss=0.1" in subtitle


def test_spinner_exception_propagates_cleanly():
    """On error, __exit__ must propagate without raising trying to render done."""

    def _boom() -> None:
        raise RuntimeError("boom")

    bar = MarimoBackend(desc="x")
    with pytest.raises(RuntimeError, match="boom"), bar:
        _boom()


def test_bar_mode_no_iterable_supports_manual_updates():
    with MarimoBackend(total=10, desc="x") as bar:
        for _ in range(10):
            bar.update(1)
        assert bar._inner.progress.current == 10


def test_bar_fail_prefixes_title():
    with MarimoBackend(total=5, desc="loading") as bar:
        bar.fail()
    assert bar._inner.progress.title == "[FAILING] loading"


def test_spinner_fail_prefixes_title():
    with MarimoBackend(desc="loading") as bar:
        bar.fail()
    assert bar._inner.spinner.title == "[FAILING] loading"


def test_fail_without_desc_uses_bare_marker():
    with MarimoBackend(total=5) as bar:
        bar.fail()
    assert bar._inner.progress.title == "[FAILING]"


def test_fail_only_announces_once():
    with MarimoBackend(total=5, desc="x") as bar:
        bar.fail()
        bar.fail()
        bar.fail()
    assert bar._failure_announced is True
