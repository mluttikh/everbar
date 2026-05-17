"""Manual terminal smoke test for everbar.

Runs the same nine scenarios as the Jupyter / Marimo notebooks so the
terminal backend (tqdm or rich) can be eyeballed end-to-end.

Usage:
    python examples/terminal_smoke.py
    EVERBAR_BACKEND=rich python examples/terminal_smoke.py
    EVERBAR_BACKEND=non_tty python examples/terminal_smoke.py
"""

import time

from everbar import Progress, detect_environment


def _header(n: int, title: str) -> None:
    print(f"\n--- {n}. {title} ---")


def scenario_1() -> None:
    _header(1, "Iterator form, known total")
    for _ in Progress(range(10), desc="Iterator"):
        time.sleep(0.05)


def scenario_2() -> None:
    _header(2, "Iterator form, unknown total (generator)")

    def gen():
        yield from range(8)

    for _ in Progress(gen(), desc="Unknown total"):
        time.sleep(0.05)


def scenario_3() -> None:
    _header(3, "Context manager, manual update")
    with Progress(total=10, desc="Manual") as bar:
        for _ in range(10):
            time.sleep(0.05)
            bar.update(1)


def scenario_4() -> None:
    _header(4, "set_postfix with numbers")
    with Progress(total=10, desc="Training") as bar:
        for i in range(10):
            time.sleep(0.05)
            bar.set_postfix(loss=1.0 / (i + 1), step=i)
            bar.update(1)


def scenario_5() -> None:
    _header(5, "set_postfix with list (Rich-markup regression)")
    with Progress(total=5, desc="With list") as bar:
        for i in range(5):
            time.sleep(0.05)
            bar.set_postfix(values=[1, 2, 3], i=i)
            bar.update(1)


def scenario_6() -> None:
    _header(6, "Nested bars")
    for epoch in Progress(range(3), desc="Epoch"):
        for _ in Progress(range(5), desc=f"  step (epoch {epoch})"):
            time.sleep(0.02)


def scenario_7() -> None:
    _header(7, "Exception inside context manager")
    try:
        with Progress(total=10, desc="Will fail") as bar:
            for i in range(10):
                time.sleep(0.05)
                if i == 5:
                    raise RuntimeError("boom")
                bar.update(1)
    except RuntimeError as e:
        print(f"caught: {e}")


def scenario_8() -> None:
    _header(8, "disable=True (silent)")
    out = list(Progress(range(5), desc="Silent", disable=True))
    assert out == [0, 1, 2, 3, 4]
    print("ok")


def scenario_9() -> None:
    _header(9, "Failure state (one worker errors, job continues)")
    with Progress(total=10, desc="Batch") as bar:
        for i in range(10):
            time.sleep(0.05)
            if i == 5:
                bar.fail()
            bar.update(1)


def main() -> None:
    print(f"detected environment: {detect_environment()}")
    scenario_1()
    scenario_2()
    scenario_3()
    scenario_4()
    scenario_5()
    scenario_6()
    scenario_7()
    scenario_8()
    scenario_9()


if __name__ == "__main__":
    main()
