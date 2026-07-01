import asyncio
import logging
import time
from typing import Any

import numpy.typing as npt
from pyobs.interfaces import ExposureTimeState, IExposureTime
from pyobs.modules.camera import BaseVideo

log = logging.getLogger(__name__)


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

        self._device_name = device
        self._camera: aravis.Camera | None = None
        self._settings: dict[str, Any] = {} if settings is None else settings
        self._camera_lock = asyncio.Lock()
        self._buffers = buffers

        if device is not None:
            self.add_background_task(self._capture)
        else:
            log.error("No device name given, not connecting to any camera.")

    async def open(self) -> None:
        """Open module."""
        from . import aravis

        await BaseVideo.open(self)

        ids: list[str] = aravis.get_device_ids()  # type: ignore[assignment]
        if self._device_name not in ids:
            raise ValueError("Could not find given device name in list of available cameras.")

        await self.activate_camera()

    async def close(self) -> None:
        """Close the module."""
        await BaseVideo.close(self)
        async with self._camera_lock:
            self._close_camera()

    def _open_camera(self) -> None:
        """Open camera."""
        from . import aravis

        log.info("Connecting to camera %s...", self._device_name)
        self._camera = aravis.Camera(self._device_name)  # type: ignore[assignment]
        log.info("Connected.")

        for key, value in self._settings.items():
            log.info("Setting value %s=%s...", key, value)
            self._camera.set_feature(key, value)  # type: ignore[union-attr]

        self._camera.start_acquisition_continuous(nb_buffers=self._buffers)  # type: ignore[union-attr]

    def _close_camera(self) -> None:
        """Close camera."""
        if self._camera is not None:
            log.info("Closing camera...")
            self._camera.stop_acquisition()  # type: ignore[union-attr]
            self._camera.shutdown()  # type: ignore[union-attr]
        self._camera = None

    async def _activate_camera(self) -> None:
        """Open camera on activation."""
        async with self._camera_lock:
            self._open_camera()

    async def _deactivate_camera(self) -> None:
        """Close camera on deactivation."""
        async with self._camera_lock:
            self._close_camera()

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
        await self.comm.set_state(IExposureTime, ExposureTimeState(exposure_time=exposure_time))


__all__ = ["AravisCamera"]
