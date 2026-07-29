"""End-to-end tests for the Progress facade.

We force ``backend="non_tty"`` so tests don't depend on tqdm/marimo and don't
spam the terminal during CI.
"""

import io
import warnings

import pytest

from everbar import Progress, set_default_backend
from everbar._backends import (
    FallbackBackend,
    NullBackend,
    RichBackend,
    TqdmBackend,
)


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


def test_fail_on_null_backend_is_noop():
    p = Progress([1, 2, 3], disable=True)
    p.fail()
    assert list(p) == [1, 2, 3]


def test_fallback_fail_marks_log_lines():
    buf = io.StringIO()
    bar = FallbackBackend(total=3, desc="x", min_interval=0.0, stream=buf)
    with bar:
        bar.update(1)
        bar.fail()
        bar.update(1)
    output = buf.getvalue()
    assert "[failing]" in output


def test_rich_fail_prepends_marker_to_description():
    from rich.console import Console

    console = Console(file=io.StringIO(), force_terminal=False)
    bar = RichBackend(total=3, desc="Loading", console=console)
    with bar:
        bar.fail()
        description = bar._progress.tasks[bar._task_id].description
    assert "FAIL" in description
    assert "Loading" in description


def test_tqdm_fail_sets_red_colour():
    buf = io.StringIO()
    bar = TqdmBackend(total=3, desc="x", file=buf, disable=False)
    with bar:
        bar.fail()
    assert bar._inner.colour == "red"


def test_rich_fail_composes_with_postfix():
    from rich.console import Console

    console = Console(file=io.StringIO(), force_terminal=False)
    bar = RichBackend(total=3, desc="Loading", console=console)
    with bar:
        bar.set_postfix(loss=0.1)
        bar.fail()
        description = bar._progress.tasks[bar._task_id].description
    assert "FAIL" in description
    assert "loss=0.1" in description


def test_fallback_renders_unit():
    buf = io.StringIO()
    bar = FallbackBackend(total=4, min_interval=0.0, stream=buf, unit="files")
    with bar:
        bar.update(2)
    output = buf.getvalue()
    assert "2/4 files" in output


def test_rich_unit_does_not_crash():
    """Regression: passing unit used to TypeError because rich.Progress
    rejects an unknown kwarg. It should now route into a custom column."""
    from rich.console import Console

    console = Console(file=io.StringIO(), force_terminal=False)
    bar = RichBackend(total=3, desc="x", unit="files", console=console)
    with bar:
        bar.update(3)


def _render_rich(bar, buf):
    """Return the last rendered line of a rich bar."""
    lines = [line for line in buf.getvalue().splitlines() if line.strip()]
    return lines[-1] if lines else ""


def test_rich_unit_added_as_column():
    from rich.console import Console
    from rich.progress import TextColumn

    console = Console(file=io.StringIO(), force_terminal=False)
    bar = RichBackend(total=3, desc="x", unit="files", console=console)
    # The unit is rendered from a task field, so the column carries the
    # field reference and the value lives on the task.
    unit_columns = [
        c
        for c in bar._progress.columns
        if isinstance(c, TextColumn) and c.text_format == "{task.fields[unit]}"
    ]
    assert len(unit_columns) == 1
    assert bar._progress.tasks[bar._task_id].fields["unit"] == "files"


@pytest.mark.parametrize(
    "unit",
    ["files", "{files}", "{task.description}", "[bold]B", "[/]x"],
)
def test_rich_unit_is_rendered_literally(unit):
    """Regression: the unit was baked into TextColumn's format string and
    parsed as markup, so a unit containing braces raised KeyError (or
    silently interpolated task state) and one containing [...] was eaten
    as styling. It is caller data and must render verbatim."""
    from rich.console import Console

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=100)
    bar = RichBackend(total=3, desc="d", unit=unit, console=console)
    with bar:
        bar.update(1)
    assert unit in _render_rich(bar, buf)


def test_tqdm_forwards_unit():
    bar = TqdmBackend(total=3, desc="x", unit="files", file=io.StringIO())
    try:
        assert bar._inner.unit == "files"
    finally:
        bar._inner.close()


def test_unit_via_facade_threads_through():
    p = Progress(total=4, backend="non_tty", unit="files")
    assert p._impl._unit == "files"  # type: ignore[attr-defined]


def test_version_matches_installed_metadata():
    """Regression: __version__ was hardcoded and drifted from pyproject."""
    import importlib.metadata

    import everbar

    assert everbar.__version__ == importlib.metadata.version("everbar")


def test_py_typed_marker_is_packaged():
    """PEP 561: without py.typed, downstream type checkers ignore our hints."""
    from importlib.resources import files

    assert files("everbar").joinpath("py.typed").is_file()


def test_unknown_backend_name_raises():
    with pytest.raises(ValueError, match="termnal"):
        Progress([1, 2, 3], backend="termnal")


def test_set_default_backend_rejects_unknown_name():
    with pytest.raises(ValueError, match="bogus"):
        set_default_backend("bogus")


def test_unknown_env_var_warns_and_falls_back_to_detection(monkeypatch):
    from everbar import _progress

    monkeypatch.setattr(_progress, "_warned_env_values", set())
    monkeypatch.setenv("EVERBAR_BACKEND", "bogus")
    with pytest.warns(UserWarning, match="EVERBAR_BACKEND"):
        p = Progress([1, 2, 3])
    assert p._impl is not None


def test_explicit_backend_with_missing_dep_raises(monkeypatch):
    """Regression: backend="rich" without rich silently degraded to log lines."""
    from everbar import _backends

    class _Unavailable:
        def __init__(self, *args, **kwargs):
            raise ImportError("No module named 'rich'")

    monkeypatch.setattr(_backends, "RichBackend", _Unavailable)
    with pytest.raises(ImportError, match="requested explicitly"):
        Progress([1, 2, 3], backend="rich")


def test_autodetected_backend_with_missing_dep_falls_back(monkeypatch):
    from everbar import _backends, _progress

    class _Unavailable:
        def __init__(self, *args, **kwargs):
            raise ImportError("No module named 'tqdm'")

    monkeypatch.delenv("EVERBAR_BACKEND", raising=False)
    monkeypatch.setattr(_backends, "TqdmBackend", _Unavailable)
    monkeypatch.setattr(_progress, "detect_environment", lambda: "terminal")
    p = Progress([1, 2, 3])
    assert isinstance(p._impl, FallbackBackend)


def test_with_and_iter_mixed_does_not_double_enter():
    """Regression: ``with Progress(items) as bar: for x in bar`` entered the
    backend twice, duplicating the entry and done log lines."""
    buf = io.StringIO()
    with Progress(
        [1, 2, 3], backend="non_tty", min_interval=0.0, stream=buf
    ) as bar:
        assert list(bar) == [1, 2, 3]
    output = buf.getvalue()
    assert output.count("0/3") == 1
    assert output.count("[done]") == 1


def test_rich_calls_before_enter_do_not_crash():
    """Regression: update()/set_postfix()/fail() before __enter__ raised
    KeyError because the task was only created on entry."""
    from rich.console import Console

    console = Console(file=io.StringIO(), force_terminal=False)
    bar = RichBackend(total=3, desc="x", console=console)
    bar.update(1)
    bar.set_postfix(loss=0.1)
    bar.fail()
    with bar:
        bar.update(2)
    assert bar._progress.tasks[bar._task_id].completed == 3


def test_iter_without_iterable_raises_type_error():
    p = Progress(total=10, backend="non_tty")
    with pytest.raises(TypeError, match="without an iterable"):
        iter(p)


def test_fallback_fail_logs_only_the_transition():
    """Regression: every fail() call logged a line, bypassing min_interval."""
    buf = io.StringIO()
    bar = FallbackBackend(total=3, min_interval=60.0, stream=buf)
    with bar:
        bar.fail()
        bar.fail()
        bar.fail()
    # One [failing] line from the first fail(), one from the final exit
    # log (the sticky state keeps the marker); the repeats add nothing.
    assert buf.getvalue().count("[failing]") == 2


def test_env_var_backend_with_missing_dep_warns_and_falls_back(monkeypatch):
    """Regression: EVERBAR_BACKEND=rich without rich installed raised
    ImportError from every Progress construction; deploy-time config
    must degrade to the fallback (with a warning), not crash."""
    from everbar import _backends, _progress

    class _Unavailable:
        def __init__(self, *args, **kwargs):
            raise ImportError("No module named 'rich'")

    # The warning is deduped per process, so start from a clean set.
    monkeypatch.setattr(_progress, "_warned_env_values", set())
    monkeypatch.setenv("EVERBAR_BACKEND", "rich")
    monkeypatch.setattr(_backends, "RichBackend", _Unavailable)
    with pytest.warns(UserWarning, match="EVERBAR_BACKEND"):
        p = Progress([1, 2, 3])
    assert isinstance(p._impl, FallbackBackend)


def test_default_backend_pin_with_missing_dep_raises(monkeypatch):
    """set_default_backend is code-level intent, like backend= — a
    missing dependency must raise rather than degrade silently."""
    from everbar import _backends

    class _Unavailable:
        def __init__(self, *args, **kwargs):
            raise ImportError("No module named 'rich'")

    monkeypatch.delenv("EVERBAR_BACKEND", raising=False)
    monkeypatch.setattr(_backends, "RichBackend", _Unavailable)
    set_default_backend("rich")
    try:
        with pytest.raises(ImportError, match="requested explicitly"):
            Progress([1, 2, 3])
    finally:
        set_default_backend(None)


def test_tqdm_fail_after_mixed_form_loop_is_not_dropped():
    """Regression: tqdm's own iterator closes the bar on exhaustion
    (disable=True), so fail()/set_postfix() after a mixed-form loop were
    silently dropped. everbar now drives iteration itself."""
    buf = io.StringIO()
    with TqdmBackend([1, 2, 3], file=buf) as bar:
        assert list(bar) == [1, 2, 3]
        bar.fail()
        assert bar._inner.disable is False
        assert bar._inner.colour == "red"
    assert bar._inner.n == 3


def test_tqdm_manual_updates_survive_iteration():
    """Regression: tqdm's iterator finally-block overwrote n on
    exhaustion, discarding manual update() calls made during the loop."""
    bar = TqdmBackend([1, 2, 3], total=13, file=io.StringIO())
    it = iter(bar)
    next(it)
    bar.update(10)
    assert list(it) == [2, 3]
    assert bar._inner.n == 13


def test_rich_task_clock_starts_at_enter():
    """Regression: eager add_task started the task clock at construction,
    so elapsed/finished-time included the construct-to-enter gap."""
    from rich.console import Console

    console = Console(file=io.StringIO(), force_terminal=False)
    bar = RichBackend(total=3, desc="x", console=console)
    bar.update(1)  # pre-enter updates must not start the clock
    assert bar._progress.tasks[bar._task_id].start_time is None
    with bar:
        assert bar._progress.tasks[bar._task_id].start_time is not None
        assert bar._progress.tasks[bar._task_id].completed == 1


def test_env_var_ignored_when_backend_argument_wins(monkeypatch, recwarn):
    """Regression: an invalid EVERBAR_BACKEND warned even when backend=
    won precedence and the env var was never consulted."""
    monkeypatch.setenv("EVERBAR_BACKEND", "bogus")
    p = Progress([1, 2], backend="non_tty")
    assert isinstance(p._impl, FallbackBackend)
    assert not [w for w in recwarn if "EVERBAR_BACKEND" in str(w.message)]


def test_env_var_warning_fires_once_per_process(monkeypatch):
    """Regression: a stale EVERBAR_BACKEND warned on every construction,
    flooding logs (and crashing repeatedly under -W error)."""
    from everbar import _progress

    monkeypatch.setattr(_progress, "_warned_env_values", set())
    monkeypatch.setenv("EVERBAR_BACKEND", "bogus_once")
    with pytest.warns(UserWarning, match="EVERBAR_BACKEND"):
        Progress([1], backend=None)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        Progress([1], backend=None)  # second construction must not warn


def test_env_var_missing_dep_warning_fires_once_per_process(monkeypatch):
    """Regression: only the unknown-name warning was deduped, so a valid
    but uninstalled EVERBAR_BACKEND warned on every construction — and
    under -W error raised every time, re-opening the crash this path
    exists to prevent."""
    from everbar import _backends, _progress

    class _Unavailable:
        def __init__(self, *args, **kwargs):
            raise ImportError("No module named 'rich'")

    monkeypatch.setattr(_progress, "_warned_env_values", set())
    monkeypatch.setattr(_backends, "RichBackend", _Unavailable)
    monkeypatch.setenv("EVERBAR_BACKEND", "rich")
    with pytest.warns(UserWarning, match="dependencies are not installed"):
        Progress([1])
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        p = Progress([1])  # second construction must not warn
    assert isinstance(p._impl, FallbackBackend)


def test_disabled_bare_progress_iterates_empty():
    """Regression: the no-iterable TypeError also fired with disable=True,
    where it previously yielded nothing — disable must not change
    control flow."""
    assert list(Progress(total=5, disable=True)) == []


def test_iterator_created_inside_with_does_not_reenter_after_exit():
    """Regression: an iterator created while entered but consumed after
    the with-block re-entered the closed backend, emitting a second
    entry/done lifecycle."""
    buf = io.StringIO()
    with Progress(
        [1, 2, 3], backend="non_tty", min_interval=0.0, stream=buf
    ) as bar:
        it = iter(bar)
    assert list(it) == [1, 2, 3]
    output = buf.getvalue()
    # One entry line and one [done] line, both from the with-block; the
    # late consumption must not re-enter and start a second lifecycle.
    assert output.count("[progress] 0/3") == 1
    assert output.count("[done]") == 1


def test_break_does_not_log_done():
    """Regression: abandoning iteration (break) logged a '[done]' success
    marker for an aborted loop."""
    buf = io.StringIO()
    for _ in Progress(
        [1, 2, 3], backend="non_tty", min_interval=0.0, stream=buf
    ):
        break
    output = buf.getvalue()
    assert "[progress]" in output
    assert "[done]" not in output


def test_empty_string_backend_means_auto_detect():
    """Compat: a falsy backend (e.g. an argparse default of '') meant
    auto-detect before validation was added; '' must not raise."""
    p = Progress([1, 2], backend="")
    assert p._impl is not None


def test_known_zero_total_is_complete_not_unknown():
    """Regression: `if self._total:` treated a known total of 0 (an empty
    collection) as an unknown total, so `Progress([])` logged
    '0/? (?)' instead of reporting completion."""
    buf = io.StringIO()
    with Progress([], backend="non_tty", min_interval=0.0, stream=buf):
        pass
    output = buf.getvalue()
    assert "0/0 (100%)" in output
    assert "?" not in output


def test_unknown_total_still_renders_as_unknown():
    """The zero-total fix must not swallow the genuinely-unknown case."""
    buf = io.StringIO()
    bar = Progress(
        (x for x in range(3)),
        backend="non_tty",
        min_interval=0.0,
        stream=buf,
    )
    assert list(bar) == [0, 1, 2]
    assert "3/? (?)" in buf.getvalue()


def test_reiteration_restarts_instead_of_overshooting():
    """Regression: `_n` was never reset, so iterating a bar twice ended at
    '6/3 (200%)'."""
    buf = io.StringIO()
    bar = Progress([1, 2, 3], backend="non_tty", min_interval=0.0, stream=buf)
    assert list(bar) == [1, 2, 3]
    assert list(bar) == [1, 2, 3]
    assert "6/3" not in buf.getvalue()
    assert buf.getvalue().strip().splitlines()[-1].count("3/3 (100%)") == 1


def test_reiteration_after_break_also_restarts():
    """The reset is armed on entry, not completion — an abandoned loop
    unwinds via GeneratorExit, so a completion-time flag would be skipped
    and the next run would resume mid-count."""
    buf = io.StringIO()
    bar = Progress(
        [1, 2, 3, 4], backend="non_tty", min_interval=0.0, stream=buf
    )
    for _ in bar:
        break
    assert list(bar) == [1, 2, 3, 4]
    assert "4/4 (100%)" in buf.getvalue()
    assert "5/4" not in buf.getvalue()


def test_first_iteration_keeps_pre_iteration_updates():
    """The reset must apply only from the second owned run onwards, or
    manual update() calls made before iterating would be discarded."""
    buf = io.StringIO()
    bar = Progress(
        [1, 2, 3], total=13, backend="non_tty", min_interval=0.0, stream=buf
    )
    bar.update(10)
    assert list(bar) == [1, 2, 3]
    assert "13/13 (100%)" in buf.getvalue()


def test_reiteration_inside_with_block_does_not_reset():
    """A caller-owned context is one run: the inner loops share a count."""
    buf = io.StringIO()
    with Progress(
        [1, 2], total=4, backend="non_tty", min_interval=0.0, stream=buf
    ) as bar:
        assert list(bar) == [1, 2]
        assert list(bar) == [1, 2]
    assert "4/4 (100%)" in buf.getvalue()


def test_rich_reiteration_restarts():
    from rich.console import Console

    console = Console(file=io.StringIO(), force_terminal=False)
    bar = RichBackend([1, 2, 3], desc="x", console=console)
    list(bar)
    list(bar)
    assert bar._progress.tasks[bar._task_id].completed == 3


def test_tqdm_reiteration_restarts():
    bar = TqdmBackend([1, 2, 3], file=io.StringIO())
    list(bar)
    list(bar)
    assert bar._inner.n == 3
