"""Unit tests for the non-hardware logic in AravisCamera: the _run_blocking timeout
wrapper. gi/Aravis are not needed for these.
"""

import asyncio
import threading
from unittest.mock import AsyncMock

import pytest
from pyobs.modules.camera import BaseVideo

from pyobs_aravis import AravisCamera


@pytest.mark.asyncio
async def test_reset_restores_exposure_time(monkeypatch: pytest.MonkeyPatch) -> None:
    # AravisCamera.__init__ imports gi/Aravis, unavailable here -- __new__ skips it, since
    # reset() only touches self.set_exposure_time and the (monkeypatched) base reset().
    camera = AravisCamera.__new__(AravisCamera)
    base_reset = AsyncMock()
    monkeypatch.setattr(BaseVideo, "reset", base_reset)
    camera.set_exposure_time = AsyncMock()  # type: ignore[method-assign]

    await camera.reset()

    base_reset.assert_awaited_once_with(camera)
    camera.set_exposure_time.assert_awaited_once_with(0.0)


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


@pytest.mark.asyncio
async def test_run_blocking_reraises_func_exception() -> None:
    def failing() -> None:
        raise ValueError("camera not found")

    with pytest.raises(ValueError, match="camera not found"):
        await AravisCamera._run_blocking(failing)
