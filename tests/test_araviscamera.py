"""Unit tests for the non-hardware logic in AravisCamera: the _run_blocking timeout
wrapper. gi/Aravis are not needed for these.
"""

import asyncio
import threading

import pytest

from pyobs_aravis import AravisCamera


@pytest.mark.asyncio
async def test_run_blocking_runs_func_and_returns_true() -> None:
    ran: list[bool] = []

    def fast() -> None:
        ran.append(True)

    assert await AravisCamera._run_blocking(fast) is True
    assert ran == [True]


@pytest.mark.asyncio
async def test_run_blocking_times_out() -> None:
    done = threading.Event()

    def slow() -> None:
        done.wait()

    assert await AravisCamera._run_blocking(slow, timeout=0.01) is False
    done.set()
    await asyncio.sleep(0.05)
