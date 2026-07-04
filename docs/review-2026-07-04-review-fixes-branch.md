# Code review — `review-fixes` branch

*Reviewed 2026-07-04, scope `git diff main...HEAD` (commits `64a12f6` +
`41b4be4`) at extra-high effort: 10 finder angles → 26 deduped candidates
→ per-candidate verification (every kept finding was reproduced by
executing code against both this branch and main, or measured) → gap
sweep. 15 findings survived; 8 minor confirmed items were cut by the
report cap and are listed at the end.*

## Verdict

The branch genuinely fixes what it set out to fix, and fixes it well —
but four of the fixes introduced regressions of their own. Those four
are the top of the list and were **fixed on this branch after the
review** (status noted per finding).

## Findings (most severe first)

### 1. Valid-but-uninstalled `EVERBAR_BACKEND` crashes every `Progress()` — CONFIRMED, **fixed**

`src/everbar/_progress.py:133`. `self._explicit = chosen is not None`
treats the env var and `set_default_backend()` pins the same as an
explicit `backend=` argument, so `EVERBAR_BACKEND=rich` with rich not
installed raises `ImportError` from every construction — where main
silently fell back, and where the branch's own README claims a stale
deploy-time value can't crash a script. The warn-and-ignore path only
protects *misspelled* names. Verified by simulating a missing rich via
an import hook.

**Fix applied:** `backend=` and `set_default_backend()` (code-level
intent) still raise; `EVERBAR_BACKEND` now warns and degrades to the
text fallback.

### 2. tqdm backend breaks the new mixed-form contract — CONFIRMED, **fixed**

`src/everbar/_backends.py:197`. The new module docstring promises "Both
forms may be mixed", but `TqdmBackend.__iter__` returned
`iter(self._inner)`, and tqdm's iterator runs
`finally: self.n = n; self.close()` on exhaustion (`disable=True`). So
on the **default terminal backend**: post-loop `fail()` — the README's
own documented pattern — wrote 0 bytes (verified), `set_postfix()` was
dropped, and manual mid-loop `update()` calls were clobbered by the
`finally` writeback.

**Fix applied:** everbar now drives iteration itself (the iterable is no
longer handed to tqdm), via the same entered-state pattern as the other
backends.

### 3. Marimo calls after exit raise `RuntimeError` — CONFIRMED, **fixed**

`src/everbar/_backends.py:431`. The eager bar-mode tracker grab means
`_tracker` stays non-`None` after marimo closes the bar on exit, and the
`None`-guards only cover "spinner mode, before `__enter__`". So
`bar.fail()` in summary code after iterator-form iteration — a crash in
the error-reporting path itself — raises marimo's "cannot be updated
after exiting" `RuntimeError` (verified). Branch-introduced: main
silently dropped the call.

**Fix applied:** a `_closed` flag set on exit; post-exit
`update()`/`set_postfix()` record state only, `fail()` still announces
the badge but skips the dead tracker.

### 4. Rich task clock starts at construction; pre-enter renders nothing — CONFIRMED, **fixed**

`src/everbar/_backends.py:257`. Eager `add_task` (rich default
`start=True`) starts the task clock at construction: verified A/B,
`task.elapsed` 0.360 s vs 0.002 s on main after a 0.35 s
construct-to-enter gap. Skew surfaces in `TimeElapsedColumn` /
`finished_time` (default `TimeRemainingColumn` is unaffected — speed
uses update samples). Separately, a never-entered `RichBackend` renders
nothing at all while the comment claims it "matches the tqdm and
fallback backends", which both produce visible output.

**Fix applied:** `add_task(start=False)` + `start_task()` in
`__enter__`; comment and module docstring corrected.

### 5. `EVERBAR_BACKEND` warning fires when irrelevant and crashes under `-W error` — CONFIRMED, open

`src/everbar/_progress.py:119`. The unknown-name warning is emitted
before precedence is applied, so it fires even when `backend=` wins and
the env var is never consulted; and under warnings-as-errors (common in
CI/pytest) it raises — the exact crash the adjacent comment claims to
prevent. Validate only when the env var actually decides, or gate
once-per-process.

### 6. `disable=True` no longer suppresses the no-iterable `TypeError` — CONFIRMED, open

`src/everbar/_progress.py:175`. The facade's new `TypeError` fires
before the backend is consulted, so `list(Progress(total=n,
disable=True))` — an empty loop on main — now raises. `disable`
promised "render nothing", not "change control flow".

### 7. Entered-state machine has holes in both directions — CONFIRMED, open (retained from main)

`src/everbar/_backends.py:111`. The `if self._entered` check sits inside
a generator (runs at first `next()`, not at `iter()`), and `__enter__`
is unguarded. Verified: an iterator created inside a `with` block but
consumed after it re-enters the closed backend for a full second
`[progress]`/`[done]` lifecycle; iter-then-enter double-enters and the
`with`-exit tears down state the still-live generator needs
(`RuntimeError` mid-loop on marimo). The branch fixed the common case;
the new docstring makes the remaining holes contract violations.

### 8. Marimo bar mode can't clear a postfix when no unit is set — CONFIRMED, open (pre-existing)

`src/everbar/_backends.py:419`. `_bar_subtitle()` returns `None` when
unit and postfix are empty, and marimo treats `subtitle=None` as "leave
unchanged" — so `set_postfix()` to clear leaves the stale value rendered
forever (verified). Send `""` when clearing.

### 9. Marimo spinner announces "Done" after `fail()` — CONFIRMED, open (pre-existing)

`src/everbar/_backends.py:380`. `__exit__` appends "Done — …" whenever
`exc_type is None`, ignoring `self._failing` — the cell shows both the
red FAILED badge and a Done line (verified with instrumented
`mo.output.append`). The fallback backend keeps `[failing]` in its final
line instead.

### 10. `self._iterable or ()` truthiness breaks numpy-like iterables — CONFIRMED, **fixed incidentally**

`src/everbar/_backends.py:118` (and 279, 399). Truthiness on an
arbitrary iterable: an ndarray-style `__bool__` raises `ValueError`
mid-iteration; a falsy-but-nonempty iterable yields nothing silently
(both verified). Retained from main, but the facade's new `TypeError`
for `iterable=None` makes an `is None` guard free.

**Fixed incidentally:** the shared iteration mixin introduced for
finding 2 uses `is None`, removing the truthiness check from all
iterating backends (NullBackend's copy corrected too).

### 11. `jupyter_qt` removal is a hard compat break — CONFIRMED, open (accept or deprecate)

`src/everbar/_progress.py:109`. A previously documented, working backend
name now raises `ValueError` at construction with no deprecation path
(verified on both branches). If intended — detection never returned it —
call it out as breaking in the changelog, or accept the name as an alias
for the std tqdm backend for one release.

### 12. `break` logs a `[done]` success marker — CONFIRMED, open (retained from main)

`src/everbar/_backends.py:114`. Abandoning iteration drives `__exit__`
via `GeneratorExit`, so the fallback prints `[done] 1/5 (20%)` for an
aborted loop (verified) — a success marker in CI logs; deferred to an
arbitrary GC point on PyPy.

### 13. Eager version lookup makes `import everbar` ~8–13× slower — CONFIRMED, open

`src/everbar/__init__.py:17`. Measured: ~3–5 ms → ~25–38 ms; the
`importlib.metadata` chain is ~75–85 % of total import cost, paid by
every consumer. A PEP 562 module `__getattr__` resolving `__version__`
lazily preserves behavior (existing test still passes — verified).

### 14. `__iter__`/`_iter_updating` triplicated across backends — CONFIRMED, **fixed incidentally**

`src/everbar/_backends.py:110`. Byte-identical copies in Fallback, Rich,
and Marimo backends; the branch already had to apply the double-enter
fix three times, and finding 7 must otherwise be fixed in three places.

**Fixed incidentally:** fixing finding 2 would have added a *fourth*
copy, so the pattern was extracted into a shared `_IterUpdatingMixin`
(the consolidation was verified against the full test suite during
review).

### 15. Marimo collection argument is dead weight — CONFIRMED, open

`src/everbar/_backends.py:348`. Since this branch drives iteration
itself, marimo uses the passed collection for nothing everbar exercises
(verified against marimo 0.23.6 source and empirically — collapsing to
the bare `total=` call passes all tests). The two constructor branches,
the `cast`, and the `TYPE_CHECKING` import can collapse to one call.

## Confirmed but cut by the report cap

- `backend=""` now raises `ValueError` where main auto-detected (falsy
  passthrough) — decide if intentional strictness.
- Marimo FAILED badge is emitted pre-enter with no indicator on screen —
  arguably intended (visibility), low severity.
- Fallback pre-enter `update()` logs immediately (throttle state starts
  at 0.0) and `__enter__` discards pre-enter elapsed time.
- Re-iterating an exhausted bar overshoots past total (`6/3 (200%)`) —
  `_n` never resets; retained from main.
- `__version__` staleness in editable installs — standard accepted
  tradeoff of the `importlib.metadata` pattern.
- Unknown-backend message built three times in `_progress.py` — extract
  a `_validate_backend()` helper.
- `_VALID_BACKENDS` hand-mirrors the `Environment` literal — derivable
  via `frozenset(get_args(Environment)) | {"rich"}` (sets verified equal
  today).
- Marimo spinner-subtitle refresh call appears in three places.

## What was checked and cleared

The detection `sys.modules` guards are behaviorally equivalent to main's
unconditional imports in every reachable case; marimo's
`progress_bar(total=…)` no-collection overload, eager `.progress` grab,
and enter/exit semantics all match the branch's assumptions; rich's
eager `add_task` is safe (no `KeyError`); tqdm kwargs forwarding can't
collide on `unit`; the new tests are hygienic (proper `monkeypatch`,
no teardown asymmetry); the `@overload` pair, mypy config, and CI
workflow changes are sound; marimo per-item updates are debounced
internally (150 ms) so self-driven iteration adds no meaningful
overhead; the switch away from marimo's own iterator actually fixes an
over-count for stepped ranges.
