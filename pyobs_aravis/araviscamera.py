import asyncio
import logging
import time
from typing import Any, Dict, Optional

from . import aravis

from pyobs.interfaces import IExposureTime
from pyobs.modules.camera import BaseVideo


log = logging.getLogger(__name__)


class AravisCamera(BaseVideo, IExposureTime):
    """A pyobs module for Aravis cameras."""

    __module__ = "pyobs_aravis"

    def __init__(
        self, device: str, settings: Optional[Dict[str, Any]] = None, **kwargs: Any
    ):
        """Initializes a new AravisCamera.

        Args:
            device: Name of camera to connect to.
        """
        BaseVideo.__init__(self, **kwargs)

        # variables
        self._device_name = device
        self._camera: Optional[aravis.Camera] = None
        self._settings: Dict[str, Any] = {} if settings is None else settings
        self._camera_lock = asyncio.Lock()

        # thread
        if device is not None:
            self.add_background_task(self._capture)
        else:
            log.error("No device name given, not connecting to any camera.")

    async def open(self) -> None:
        """Open module."""
        await BaseVideo.open(self)

        # list devices
        ids = aravis.get_device_ids()
        if self._device_name not in ids:
            raise ValueError(
                "Could not find given device name in list of available cameras."
            )

        # open camera
        await self.activate_camera()

    async def close(self) -> None:
        """Close the module."""
        await BaseVideo.close(self)
        async with self._camera_lock:
            self._close_camera()

    def _open_camera(self) -> None:
        """Open camera."""

        # open camera
        log.info("Connecting to camera %s...", self._device_name)
        self._camera = aravis.Camera(self._device_name)
        log.info("Connected.")

        # settings
        for key, value in self._settings.items():
            log.info(f"Setting value {key}={value}...")
            self._camera.set_feature(key, value)

        # start acquisition
        self._camera.start_acquisition_continuous(nb_buffers=5)

    def _close_camera(self) -> None:
        """Close camera."""
        # stop camera
        if self._camera is not None:
            log.info("Closing camera...")
            self._camera.stop_acquisition()
            self._camera.shutdown()
        self._camera = None

    async def _activate_camera(self) -> None:
        """Can be overridden by derived class to implement inactivity sleep"""
        async with self._camera_lock:
            self._open_camera()

    async def _deactivate_camera(self) -> None:
        """Can be overridden by derived class to implement inactivity sleep"""
        async with self._camera_lock:
            self._close_camera()

    async def _capture(self) -> None:
        """Take new images in loop."""

        # loop until closing
        last = time.time()
        while True:
            # no camera or not active?
            if self._camera is None or not self.camera_active:
                # wait a little
                await asyncio.sleep(0.1)
                continue

            # if time since last image is too short, wait a little
            if time.time() - last < self._interval:
                await asyncio.sleep(0.01)
                continue

            # read frame
            frame = self._camera.pop_frame()
            last = time.time()

            # process it
            await self._set_image(frame)

    async def set_exposure_time(self, exposure_time: float, **kwargs: Any) -> None:
        """Set the exposure time in seconds.

        Args:
            exposure_time: Exposure time in seconds.

        Raises:
            ValueError: If exposure time could not be set.
        """
        await self.activate_camera()
        self._camera.set_exposure_time(exposure_time * 1e6)

    async def get_exposure_time(self, **kwargs: Any) -> float:
        """Returns the exposure time in seconds.

        Returns:
            Exposure time in seconds.
        """
        await self.activate_camera()
        return self._camera.get_exposure_time() / 1e6


__all__ = ["AravisCamera"]
