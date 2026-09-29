"""Unit tests for the non-hardware logic in AravisCamera: the _run_blocking timeout
wrapper. gi/Aravis are not needed for these.
"""

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock

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


@pytest.mark.asyncio
async def test_run_blocking_late_completion_does_not_raise() -> None:
    # a func finishing after the timeout must not call set_result on the cancelled future
    done = threading.Event()
    errors: list[dict[str, object]] = []
    asyncio.get_running_loop().set_exception_handler(lambda loop, ctx: errors.append(ctx))

    def slow() -> None:
        done.wait()

    assert await AravisCamera._run_blocking(slow, timeout=0.01) is False
    done.set()
    await asyncio.sleep(0.05)

    assert errors == []


@pytest.mark.asyncio
async def test_wait_for_frame_timeout_does_not_leak_threads() -> None:
    # the camera never delivers a frame, so every wait times out
    camera = AravisCamera.__new__(AravisCamera)
    camera._device_lock = threading.Lock()
    camera._camera = MagicMock()
    camera._camera.try_pop_frame.return_value = None
    before = threading.active_count()

    for _ in range(5):
        assert await camera._wait_for_frame(timeout=0.05) is None
    await asyncio.sleep(0.1)

    assert threading.active_count() == before
