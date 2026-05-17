import marimo

__generated_with = "0.23.6"
app = marimo.App(width="medium")


@app.cell
def _():
    import time

    from everbar import Progress, detect_environment

    detect_environment()
    return Progress, time


@app.cell
def _():
    import marimo as mo

    mo.md("# everbar — Marimo smoke tests\n\nEach cell exercises one behavior. Run top-to-bottom and eyeball the bars.")
    return (mo,)


@app.cell
def _(mo):
    mo.md("""
    ## 1. Iterator form, known total
    """)
    return


@app.cell
def _(Progress, time):
    for _i in Progress(range(10), desc="Iterator"):
        time.sleep(0.05)
    return


@app.cell
def _(mo):
    mo.md("""
    ## 2. Iterator form, unknown total (generator)
    """)
    return


@app.cell
def _(Progress, time):
    def _gen():
        for _i in range(8):
            yield _i

    for _x in Progress(_gen(), desc="Unknown total"):
        time.sleep(0.05)
    return


@app.cell
def _(mo):
    mo.md("""
    ## 3. Context manager, manual update
    """)
    return


@app.cell
def _(Progress, time):
    with Progress(total=10, desc="Manual") as _bar:
        for _i in range(10):
            time.sleep(0.05)
            _bar.update(1)
    return


@app.cell
def _(mo):
    mo.md("""
    ## 4. set_postfix with numbers
    """)
    return


@app.cell
def _(Progress, time):
    with Progress(total=10, desc="Training") as _bar:
        for _i in range(10):
            time.sleep(0.05)
            _bar.set_postfix(loss=1.0 / (_i + 1), step=_i)
            _bar.update(1)
    return


@app.cell
def _(mo):
    mo.md("""
    ## 5. set_postfix with list (Rich-markup regression)
    """)
    return


@app.cell
def _(Progress, time):
    with Progress(total=5, desc="With list") as _bar:
        for _i in range(5):
            time.sleep(0.05)
            _bar.set_postfix(values=[1, 2, 3], i=_i)
            _bar.update(1)
    return


@app.cell
def _(mo):
    mo.md("""
    ## 6. Nested bars
    """)
    return


@app.cell
def _(Progress, time):
    for _epoch in Progress(range(3), desc="Epoch"):
        for _step in Progress(range(5), desc=f"  step (epoch {_epoch})"):
            time.sleep(0.02)
    return


@app.cell
def _(mo):
    mo.md("""
    ## 7. Exception inside context manager (should not leave the bar hanging)
    """)
    return


@app.cell
def _(Progress, time):
    try:
        with Progress(total=10, desc="Will fail") as _bar:
            for _i in range(10):
                time.sleep(0.05)
                if _i == 5:
                    raise RuntimeError("boom")
                _bar.update(1)
    except RuntimeError as _e:
        print(f"caught: {_e}")
    return


@app.cell
def _(mo):
    mo.md("""
    ## 8. disable=True (silent)
    """)
    return


@app.cell
def _(Progress):
    _out = list(Progress(range(5), desc="Silent", disable=True))
    assert _out == [0, 1, 2, 3, 4]
    "ok"
    return


@app.cell
def _(mo):
    mo.md("""
    ## 9. Failure state (one worker errors, job continues)
    """)
    return


@app.cell
def _(Progress, time):
    with Progress(total=10, desc="Batch") as _bar:
        for _i in range(10):
            time.sleep(0.05)
            if _i == 5:
                _bar.fail()
            _bar.update(1)
    return


if __name__ == "__main__":
    app.run()
