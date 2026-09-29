"""Unit tests for the non-hardware logic in AravisCamera: the _run_blocking timeout
wrapper, frames() and _apply_settings(). gi/Aravis are not needed for these.
"""

import asyncio
import threading
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import numpy.typing as npt
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


class FakeCamera:
    """Stands in for pyobs_aravis.aravis.Camera: frames come from a list, calls are recorded."""

    def __init__(self, frames: list[npt.NDArray[Any]] | None = None) -> None:
        self.frames = [] if frames is None else frames
        self.calls: list[Any] = []
        self.exposure_us = 1000.0

    def try_pop_frame(self) -> npt.NDArray[Any] | None:
        return self.frames.pop(0) if self.frames else None

    def start_acquisition_continuous(self, nb_buffers: int) -> None:
        self.calls.append("start")

    def stop_acquisition(self) -> None:
        self.calls.append("stop")

    def flush(self) -> None:
        self.calls.append("flush")

    def set_exposure_time(self, us: float) -> None:
        self.calls.append(("set", us))
        # cameras round the exposure time to their own step size
        self.exposure_us = round(us / 7) * 7

    def get_exposure_time(self) -> float:
        return self.exposure_us


def _camera(fake: FakeCamera, buffers: int = 5) -> AravisCamera:
    # AravisCamera.__init__ imports gi/Aravis, unavailable here -- set up just what frames() and
    # _apply_settings() need
    camera = AravisCamera.__new__(AravisCamera)
    camera._device_lock = threading.Lock()
    camera._generation_lock = threading.Lock()
    camera._camera = fake  # type: ignore[assignment]
    camera._buffers = buffers
    camera._exposure_time = 0.001
    camera._acquiring = False
    camera._generation = 0
    camera.activate_camera = AsyncMock()  # type: ignore[method-assign]
    comm = MagicMock()
    comm.set_state = AsyncMock()
    camera._comm = comm
    return camera


def _frame(value: int) -> npt.NDArray[Any]:
    return np.full((2, 2), value, dtype=np.uint16)


@pytest.mark.asyncio
async def test_frames_yields_in_order_and_stops_acquisition_on_close() -> None:
    fake = FakeCamera([_frame(i) for i in range(3)])
    camera = _camera(fake)
    before = threading.active_count()

    iterator = camera.frames()
    frames = [await anext(iterator) for _ in range(3)]
    await iterator.aclose()
    await asyncio.sleep(0.05)

    assert [int(f.data[0, 0]) for f in frames] == [0, 1, 2]
    assert all(f.generation == 0 and f.exposure_time == 0.001 and f.start is None for f in frames)
    assert fake.calls == ["start", "stop", "flush"]
    assert camera._acquiring is False
    assert threading.active_count() == before


@pytest.mark.asyncio
async def test_set_exposure_time_restarts_acquisition_and_bumps_generation() -> None:
    fake = FakeCamera()
    camera = _camera(fake)
    camera._acquiring = True

    await camera.set_exposure_time(0.5)

    assert fake.calls == ["stop", "flush", ("set", 500000.0), "start"]
    assert camera.generation == 1
    # the read-back value, not the requested one
    assert camera._exposure_time == fake.exposure_us / 1e6 != 0.5
    state = camera.comm.set_state.await_args.args[1]  # type: ignore[attr-defined]
    assert state.exposure_time == camera._exposure_time


@pytest.mark.asyncio
async def test_set_exposure_time_without_acquisition_does_not_restart() -> None:
    fake = FakeCamera()
    camera = _camera(fake)

    await camera.set_exposure_time(0.5)

    assert fake.calls == [("set", 500000.0)]
    assert camera.generation == 1


@pytest.mark.asyncio
async def test_frames_after_settings_change_carry_new_generation() -> None:
    fake = FakeCamera([_frame(0)])
    camera = _camera(fake)
    iterator = camera.frames()

    first = await anext(iterator)
    await camera.set_exposure_time(0.5)
    fake.frames.append(_frame(1))
    second = await anext(iterator)
    await iterator.aclose()

    assert (first.generation, first.exposure_time) == (0, 0.001)
    assert (second.generation, second.exposure_time) == (1, fake.exposure_us / 1e6)


@pytest.mark.asyncio
async def test_frames_drops_oldest_when_consumer_is_slow() -> None:
    fake = FakeCamera([_frame(0)])
    camera = _camera(fake, buffers=2)
    iterator = camera.frames()

    await anext(iterator)
    fake.frames.extend(_frame(i) for i in range(1, 10))
    await asyncio.sleep(0.2)
    rest = [int((await anext(iterator)).data[0, 0]) for _ in range(2)]
    await iterator.aclose()

    assert rest == [8, 9]


@pytest.mark.asyncio
async def test_frames_raises_when_reader_fails() -> None:
    # an exception in the reader thread must end frames(), not leave it waiting for frames forever
    fake = FakeCamera([_frame(0)])
    camera = _camera(fake)
    iterator = camera.frames()
    await anext(iterator)

    def failing() -> None:
        raise ValueError("Unsupported pixel format 0")

    fake.try_pop_frame = failing  # type: ignore[method-assign,assignment]
    with pytest.raises(ValueError, match="Unsupported pixel format"):
        await asyncio.wait_for(anext(iterator), timeout=1.0)

    # acquisition was stopped on the way out
    assert fake.calls == ["start", "stop", "flush"]
    assert camera._acquiring is False


@pytest.mark.asyncio
async def test_apply_settings_without_camera_raises() -> None:
    camera = _camera(FakeCamera())
    camera._camera = None

    with pytest.raises(RuntimeError, match="not connected"):
        await camera._apply_settings(lambda cam: None)
    assert camera.generation == 0
