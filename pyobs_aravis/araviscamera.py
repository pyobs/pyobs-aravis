import asyncio
import logging
import threading
import time
from collections.abc import Callable
from typing import Any

import numpy.typing as npt
from pyobs.interfaces import ExposureTimeState, IExposureTime
from pyobs.modules.camera import BaseVideo

log = logging.getLogger(__name__)

# aravis/GLib calls are blocking and are made directly on the event loop thread (see _run_blocking).
# If the camera has gone unresponsive, they can hang indefinitely, so we bound them with a timeout
# rather than let a single dead camera freeze the whole module.
_SDK_CALL_TIMEOUT = 5.0


class AravisCamera(BaseVideo, IExposureTime):
    """A pyobs module for Aravis cameras."""

    __module__ = "pyobs_aravis"

    def __init__(
        self,
        device: str,
        settings: dict[str, Any] | None = None,
        buffers: int = 5,
        **kwargs: Any,
    ):
        """Initializes a new AravisCamera.

        Args:
            device: Name of camera to connect to.
            settings: Dictionary of camera settings to apply on connect.
            buffers: Number of acquisition buffers.
        """
        BaseVideo.__init__(self, **kwargs)
        from . import aravis

        self._camera_device_name = device
        self._camera: aravis.Camera | None = None
        self._settings: dict[str, Any] = {} if settings is None else settings
        self._camera_lock = asyncio.Lock()
        self._buffers = buffers
        self._exposure_time: float = 0.0

        if device is not None:
            self.add_background_task(self._capture)
        else:
            log.error("No device name given, not connecting to any camera.")

    async def open(self) -> None:
        """Open module."""
        from . import aravis

        await BaseVideo.open(self)

        # device discovery is a blocking, network-based scan (GigE Vision/USB3 Vision devices
        # reply to a broadcast query) that can take multiple seconds -- run it like the other
        # aravis/GLib calls (see _run_blocking) instead of freezing the whole module's event
        # loop, and with it, the ability to respond to any other module, for that long
        ids: list[str] = []

        def _list_device_ids() -> None:
            ids.extend(aravis.get_device_ids())  # type: ignore[arg-type]

        if not await self._run_blocking(_list_device_ids):
            raise TimeoutError(f"Timed out listing available cameras after {_SDK_CALL_TIMEOUT}s.")

        if self._camera_device_name not in ids:
            raise ValueError("Could not find given device name in list of available cameras.")

        await self.activate_camera()

    async def close(self) -> None:
        """Close the module."""
        await BaseVideo.close(self)
        await self._deactivate_camera()

    def _open_camera(self) -> None:
        """Open camera."""
        from . import aravis

        log.info("Connecting to camera %s...", self._camera_device_name)
        self._camera = aravis.Camera(self._camera_device_name)  # type: ignore[assignment]
        log.info("Connected.")

        for key, value in self._settings.items():
            log.info("Setting value %s=%s...", key, value)
            self._camera.set_feature(key, value)  # type: ignore[union-attr]

        self._camera.start_acquisition_continuous(nb_buffers=self._buffers)  # type: ignore[union-attr]

    def _close_camera(self) -> None:
        """Close camera."""
        if self._camera is not None:
            log.info("Closing camera...")
            try:
                self._camera.stop_acquisition()  # type: ignore[union-attr]
                self._camera.shutdown()  # type: ignore[union-attr]
            except Exception:
                log.exception("Error closing camera.")
        self._camera = None

    @staticmethod
    async def _run_blocking(func: Callable[[], None], timeout: float = _SDK_CALL_TIMEOUT) -> bool:
        """Run a blocking aravis/GLib call in a daemon thread, so a hung call can't freeze the module.

        A plain executor isn't used here, since its worker threads are non-daemon and Python joins
        them on interpreter shutdown -- a hung call would then just move the freeze to process exit.

        Returns:
            True if func completed within timeout, False if it's still running in the background.
        """
        loop = asyncio.get_running_loop()
        future: asyncio.Future[None] = loop.create_future()

        def _wrapper() -> None:
            try:
                func()
            finally:
                loop.call_soon_threadsafe(future.set_result, None)

        threading.Thread(target=_wrapper, daemon=True).start()
        try:
            await asyncio.wait_for(future, timeout=timeout)
            return True
        except TimeoutError:
            return False

    async def _activate_camera(self) -> None:
        """Open camera on activation."""
        async with self._camera_lock:
            if not await self._run_blocking(self._open_camera):
                log.error("Timed out connecting to camera after %.1fs.", _SDK_CALL_TIMEOUT)
                self._camera = None

    async def _deactivate_camera(self) -> None:
        """Close camera on deactivation."""
        async with self._camera_lock:
            if not await self._run_blocking(self._close_camera):
                log.error("Timed out closing camera after %.1fs, abandoning cleanup.", _SDK_CALL_TIMEOUT)
                self._camera = None

    async def _capture(self) -> None:
        """Take new images in loop."""
        last = time.time()
        while True:
            try:
                if self._camera is None or not self.camera_active:
                    await asyncio.sleep(0.1)
                    continue

                frame: npt.NDArray[Any] = self._camera.pop_frame()  # type: ignore[union-attr]
                while frame is None:
                    await asyncio.sleep(0.01)
                    frame = self._camera.pop_frame()  # type: ignore[union-attr]

                if time.time() - last < self._interval:
                    await asyncio.sleep(0.01)
                    continue

                last = time.time()
                await self._set_image(frame)

            except Exception:
                await asyncio.sleep(1)

    async def set_exposure_time(self, exposure_time: float, **kwargs: Any) -> None:
        """Set the exposure time in seconds.

        Args:
            exposure_time: Exposure time in seconds.
        """
        await self.activate_camera()
        self._camera.set_exposure_time(exposure_time * 1e6)  # type: ignore[union-attr]
        self._exposure_time = exposure_time
        await self.comm.set_state(IExposureTime, ExposureTimeState(exposure_time=exposure_time))


__all__ = ["AravisCamera"]
