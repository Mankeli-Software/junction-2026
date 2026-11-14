"""The live tests run only when SIMO_LIVE_URL names a running S.I.MO (#98).

They write to that app's database, call the live Valio API through it and open Gemini Live
sessions, so they are skipped in the normal `uv run pytest` and in CI.
"""

import os
from collections.abc import Iterator

import pytest

from tests.live.simo_live import Run


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if os.environ.get("SIMO_LIVE_URL"):
        return
    skip = pytest.mark.skip(reason="SIMO_LIVE_URL is not set")
    for item in items:
        if "/tests/live/" in str(item.path).replace(os.sep, "/"):
            item.add_marker(skip)


class Beats:
    """Plays the beats of a script one after another and keeps what failed, so one failing
    beat doesn't hide the ones after it."""

    def __init__(self, run: Run) -> None:
        self.run = run
        self.results: list[tuple[str, str | None]] = []

    def __call__(self, name: str) -> "Beats":
        self.run.case = name
        self._name = name
        return self

    def __enter__(self) -> None:
        print(f"\n== {self._name}")

    def __exit__(self, kind, error, traceback) -> bool:
        if error is not None and not isinstance(error, Exception):
            return False
        problem = None
        if error is not None:
            # The first line only: pytest adds the compared values below it.
            problem = f"{type(error).__name__}: {str(error).splitlines()[0]}"
        self.results.append((self._name, problem))
        if problem:
            print(f"  FAILED: {problem}")
        return True

    def passed(self, name: str) -> bool:
        return (name, None) in self.results

    def finish(self) -> None:
        print(f"\n== run {self.run.run_id}")
        for name, problem in self.results:
            print(f"  [{' ' if problem else 'x'}] {name}" + (f": {problem}" if problem else ""))
        failed = [name for name, problem in self.results if problem]
        if failed:
            pytest.fail(f"beats failed: {', '.join(failed)} (run {self.run.run_id})", pytrace=False)


@pytest.fixture
def run() -> Iterator[Run]:
    live = Run.start(os.environ["SIMO_LIVE_URL"])
    print(f"\nrun {live.run_id} against {live.base}")
    yield live


@pytest.fixture
def beats(run: Run) -> Beats:
    return Beats(run)
