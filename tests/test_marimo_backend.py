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


def test_bar_unit_appears_in_subtitle():
    bar = MarimoBackend(total=5, desc="x", unit="files")
    assert bar._inner.progress.subtitle == "files"


def test_bar_unit_combines_with_postfix():
    with MarimoBackend(total=5, desc="x", unit="files") as bar:
        bar.set_postfix(loss=0.1)
    subtitle = bar._inner.progress.subtitle
    assert "files" in subtitle
    assert "loss=0.1" in subtitle
    assert " | " in subtitle


def test_spinner_unit_replaces_items_in_subtitle():
    with MarimoBackend(desc="x", unit="files") as bar:
        bar.update(3)
    subtitle = bar._inner.spinner.subtitle
    assert "3 files" in subtitle
    assert "items" not in subtitle


def test_spinner_unit_without_postfix():
    with MarimoBackend(desc="x", unit="rows") as bar:
        bar.update(7)
    assert bar._inner.spinner.subtitle == "7 rows"


def test_bar_iterator_form_set_postfix_with_kept_handle():
    """Regression: set_postfix during iterator-form iteration raised
    AttributeError because the tracker was never set."""
    bar = MarimoBackend([1, 2, 3], desc="x")
    it = iter(bar)
    next(it)
    bar.set_postfix(loss=0.1)
    assert "loss=0.1" in bar._inner.progress.subtitle
    assert list(it) == [2, 3]
    assert bar._n == 3


def test_bar_iterator_form_fail_sets_title():
    """Regression: fail() during iterator-form iteration was silently
    dropped by the tracker-is-None guard."""
    bar = MarimoBackend([1, 2, 3], desc="x")
    it = iter(bar)
    next(it)
    bar.fail()
    assert bar._inner.progress.title == "[FAILING] x"


def test_bar_update_before_enter_records_progress():
    bar = MarimoBackend(total=5, desc="x")
    bar.update(2)
    assert bar._inner.progress.current == 2


def test_spinner_updates_before_enter_sync_on_entry():
    bar = MarimoBackend(desc="x")
    bar.update(2)  # no tracker yet — must not crash
    bar.set_postfix(loss=0.5)
    with bar:
        subtitle = bar._inner.spinner.subtitle
    assert "2 items" in subtitle
    assert "loss=0.5" in subtitle


def test_calls_after_iteration_completes_are_noops():
    """Regression: the eagerly-grabbed bar-mode tracker stayed live after
    marimo closed the bar on exit, so fail()/set_postfix()/update() in
    summary code after the loop raised marimo's RuntimeError."""
    bar = MarimoBackend([1, 2, 3], desc="x")
    assert list(bar) == [1, 2, 3]
    bar.fail()  # must not raise; badge is still announced
    bar.set_postfix(loss=0.5)
    bar.update(1)
    assert bar._failing
    assert bar._n == 4


def test_calls_after_context_exit_are_noops():
    with MarimoBackend(total=3, desc="x") as bar:
        bar.update(1)
    bar.update(1)
    bar.set_postfix(loss=0.5)
    bar.fail()
    assert bar._n == 2


def test_bar_set_postfix_clears_without_unit():
    """Regression: clearing the postfix with no unit sent subtitle=None,
    which marimo treats as 'leave unchanged' — the stale value stuck."""
    bar = MarimoBackend(total=3)
    bar.set_postfix(loss=0.5)
    assert bar._inner.progress.subtitle == "loss=0.5"
    bar.set_postfix()
    assert bar._inner.progress.subtitle == ""


def test_spinner_exit_after_fail_does_not_announce_done(monkeypatch):
    """Regression: a failing spinner still appended 'Done — ...' on clean
    exit, contradicting the FAILED badge."""
    from types import SimpleNamespace

    bar = MarimoBackend(desc="x")  # spinner mode
    recorded: list[tuple[str, str]] = []
    stub = SimpleNamespace(
        output=SimpleNamespace(append=recorded.append),
        md=lambda text: ("md", text),
        Html=lambda text: ("html", text),
    )
    monkeypatch.setattr(bar, "_mo", stub)
    with bar:
        bar.update(1)
        bar.fail()
    kinds = [kind for kind, _ in recorded]
    assert kinds == ["html"]  # the FAILED badge only, no Done markdown


def test_reiteration_rebuilds_the_indicator():
    """Regression: marimo indicators are single-use — re-entering one after
    exit raised 'cannot be updated after exiting'. A fresh run builds a
    fresh indicator."""
    bar = MarimoBackend([1, 2, 3], desc="x")
    assert list(bar) == [1, 2, 3]
    assert list(bar) == [1, 2, 3]
    assert bar._n == 3
    assert bar._inner.progress.current == 3


def test_reiteration_keeps_failing_state_sticky():
    bar = MarimoBackend([1, 2], desc="x")
    list(bar)
    bar.fail()
    list(bar)
    assert bar._failing is True


def test_spinner_reiteration_restarts_count():
    def gen():
        yield from range(3)

    bar = MarimoBackend(gen(), desc="x")
    assert bar._mode == "spinner"
    list(bar)
    list(bar)  # generator is exhausted; count restarts and stays at 0
    assert bar._n == 0
