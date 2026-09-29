import asyncio
import logging
import threading
import time
from collections.abc import AsyncGenerator, Callable
from typing import Any

from pyobs.images import Image
from pyobs.interfaces import ExposureTimeState, IExposureTime
from pyobs.modules.camera import BaseVideo, Frame
from pyobs.utils.enums import ImageType

log = logging.getLogger(__name__)

# aravis/GLib calls are blocking and are made directly on the event loop thread (see _run_blocking).
# If the camera has gone unresponsive, they can hang indefinitely, so we bound them with a timeout
# rather than let a single dead camera freeze the whole module.
_SDK_CALL_TIMEOUT = 5.0

# frames() warns if no frame arrived for this long. Frames legitimately take up to the camera's
# own frame interval/exposure time, so this is much more generous than _SDK_CALL_TIMEOUT.
_FRAME_WAIT_TIMEOUT = 30.0


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
            device: Name or IP address of camera to connect to. An IP address connects directly,
                without relying on the network's broadcast-based device discovery -- useful on
                networks that block or drop that broadcast traffic even though unicast GVCP
                control traffic works fine (verify with e.g. `arv-tool-0.8 -a <ip> features`).
            settings: Dictionary of camera settings to apply on connect.
            buffers: Number of acquisition buffers.
        """
        BaseVideo.__init__(self, **kwargs)
        from . import aravis

        self._camera_device_name = device
        self._camera: aravis.Camera | None = None
        self._settings: dict[str, Any] = {} if settings is None else settings
        self._camera_lock = asyncio.Lock()
        # Serializes access to self._camera between the SDK threads spawned by _run_blocking and
        # the reader thread in frames(): they run on daemon threads rather than the event loop,
        # so the async _camera_lock can't cover them.
        self._device_lock = threading.Lock()
        # generation bumps come from SDK threads (under _device_lock) and from the event loop
        self._generation_lock = threading.Lock()
        self._buffers = buffers
        self._exposure_time: float = 0.0
        # whether frames() has acquisition running, so _apply_settings() knows to restart it
        self._acquiring = False

        if device is None:
            log.error("No device name given, not connecting to any camera.")
        if hasattr(type(self), "_capture"):
            log.error(
                "%s overrides _capture(), which AravisCamera no longer runs; implement frames() instead.",
                type(self).__name__,
            )

    async def open(self) -> None:
        """Open module."""
        await BaseVideo.open(self)

        # connecting (see _open_camera) validates the device itself -- no separate discovery
        # pre-check here, since that relies on a network-wide broadcast query that some networks
        # block or drop even though unicast GVCP control traffic (i.e. the actual connection)
        # works fine
        await self.activate_camera()

        # publish initial exposure-time state -- otherwise a caller doing wait_for_state()
        # before the first set_exposure_time() call would time out with nothing ever published
        await self.comm.set_state(IExposureTime, ExposureTimeState(exposure_time=self._exposure_time))

    async def close(self) -> None:
        """Close the module."""
        await BaseVideo.close(self)
        await self._deactivate_camera()

    async def _finish_image(self, image: Image, broadcast: bool, image_type: ImageType) -> tuple[Image, str]:
        """Add device identity/settings headers, then finish up as usual (BaseVideo has no
        per-frame header hook of its own, so this is the earliest point after add_fits_headers()
        and before the image is serialized to bytes)."""
        image.header["INSTRUME"] = (self._camera_device_name, "Name of instrument")
        for key, value in self._settings.items():
            if key.lower() == "gain":
                image.header["GAIN"] = (value, "Gain used for exposure")
            elif key.lower() == "triggermode":
                image.header["TRIGMODE"] = (value, "Trigger mode used for exposure")
        return await super()._finish_image(image, broadcast, image_type)

    def _open_camera(self) -> None:
        """Open camera."""
        from . import aravis

        log.info("Connecting to camera %s...", self._camera_device_name)
        with self._device_lock:
            self._camera = aravis.Camera(self._camera_device_name)  # type: ignore[assignment]
            log.info("Connected.")

            for key, value in self._settings.items():
                log.info("Setting value %s=%s...", key, value)
                self._camera.set_feature(key, value)  # type: ignore[union-attr]

            # a new connection with (re)applied settings: frames from before don't count anymore
            try:
                self._exposure_time = self._camera.get_exposure_time() / 1e6  # type: ignore[union-attr]
            except Exception:
                log.warning("Could not read exposure time from camera.", exc_info=True)
            self._new_generation()

    def _close_camera(self) -> None:
        """Close camera."""
        with self._device_lock:
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

        Raises:
            Whatever exception func() raised, if it completed within timeout.
        """
        loop = asyncio.get_running_loop()
        future: asyncio.Future[None] = loop.create_future()
        error: list[BaseException] = []

        def _wrapper() -> None:
            try:
                func()
            except BaseException as exc:
                error.append(exc)
            finally:
                # after a timeout, wait_for() has already cancelled the future
                loop.call_soon_threadsafe(lambda: future.done() or future.set_result(None))

        threading.Thread(target=_wrapper, daemon=True).start()
        try:
            await asyncio.wait_for(future, timeout=timeout)
        except TimeoutError:
            return False
        if error:
            raise error[0]
        return True

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

    def _new_generation(self) -> int:
        """Start a new settings generation, thread-safe (called from SDK threads, too)."""
        with self._generation_lock:
            return super()._new_generation()

    async def frames(self) -> AsyncGenerator[Frame, None]:
        """Start acquisition and yield frames until BaseVideo closes the iterator.

        A single reader thread polls try_pop_frame() for the whole activation and hands frames to
        the event loop, instead of one thread per frame. Each frame is stamped with the settings
        generation and exposure time in effect when it was popped, read under the same lock that
        _apply_settings() holds while it restarts acquisition, so the stamp is always right.
        """
        loop = asyncio.get_running_loop()
        # frames, or the exception that ended the reader thread
        queue: asyncio.Queue[Frame | Exception] = asyncio.Queue(maxsize=self._buffers)
        stop = threading.Event()

        def _start() -> None:
            with self._device_lock:
                if self._camera is None:
                    raise RuntimeError("Camera not connected.")
                self._camera.start_acquisition_continuous(nb_buffers=self._buffers)
                self._acquiring = True

        def _put(item: Frame | Exception) -> None:
            # latest wins: a stalled event loop mustn't grow memory
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(item)

        def _read() -> None:
            # an exception would silently end this thread and leave frames() waiting forever, so
            # hand it over to frames() instead, which raises it and lets BaseVideo restart
            try:
                _read_loop()
            except Exception as e:
                try:
                    loop.call_soon_threadsafe(_put, e)
                except RuntimeError:
                    # event loop closed (shutdown)
                    pass

        def _read_loop() -> None:
            while not stop.is_set():
                # Hold the device lock only for the (non-blocking) try_pop_frame() call, so
                # _apply_settings()/_close_camera() can take it between polls.
                with self._device_lock:
                    camera = self._camera
                    if camera is None:
                        return
                    data = camera.try_pop_frame()
                    generation, exposure_time = self.generation, self._exposure_time
                # try_pop_frame() can return a non-None array that's empty along axis 0 instead of
                # None -- treat that the same as "not ready yet" rather than a real frame
                if data is not None and data.size != 0:
                    frame = Frame(data=data, exposure_time=exposure_time, generation=generation)
                    try:
                        loop.call_soon_threadsafe(_put, frame)
                    except RuntimeError:
                        # event loop closed (shutdown)
                        return
                else:
                    time.sleep(0.01)

        def _stop() -> None:
            with self._device_lock:
                self._acquiring = False
                if self._camera is not None:
                    self._camera.stop_acquisition()
                    self._camera.flush()

        if not await self._run_blocking(_start):
            raise TimeoutError("Timed out starting acquisition.")
        threading.Thread(target=_read, daemon=True).start()
        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=_FRAME_WAIT_TIMEOUT)
                except TimeoutError:
                    log.warning("No frame from camera for %.1fs.", _FRAME_WAIT_TIMEOUT)
                    continue
                if isinstance(item, Exception):
                    raise item
                yield item
        finally:
            # don't join the reader: if it hangs in the SDK, it must not block deactivation
            stop.set()
            try:
                if not await self._run_blocking(_stop):
                    log.error("Timed out stopping acquisition after %.1fs.", _SDK_CALL_TIMEOUT)
            except Exception:
                log.exception("Error stopping acquisition.")

    async def _apply_settings(self, func: Callable[[Any], None]) -> None:
        """Change camera settings and start a new settings generation.

        During acquisition, func() is applied while the camera keeps streaming, and the frames
        still queued in the stream are flushed, since those were exposed with the old settings.
        Only if the camera rejects that, acquisition is stopped around func() -- some GigE cameras
        (e.g. the IAG VT fibercamera) then deliver no frames for up to a minute, so a restart is
        the last resort. The one frame exposing during the change may carry the new generation
        although exposed (partly) with the old settings. The exposure time is read back
        afterwards, as the camera may round it. Subclasses use this for their own setters.

        Args:
            func: Called with the aravis camera, under the device lock, on an SDK thread.

        Raises:
            RuntimeError: If the camera is not connected.
            TimeoutError: If the SDK didn't respond in time.
        """

        def _apply() -> None:
            with self._device_lock:
                camera = self._camera
                if camera is None:
                    raise RuntimeError("Camera not connected.")
                if not self._acquiring:
                    func(camera)
                else:
                    try:
                        func(camera)
                        camera.flush()
                    except Exception:
                        log.info("Camera rejected setting during acquisition, restarting acquisition for it.")
                        camera.stop_acquisition()
                        camera.flush()
                        try:
                            func(camera)
                        finally:
                            camera.start_acquisition_continuous(nb_buffers=self._buffers)
                self._exposure_time = camera.get_exposure_time() / 1e6
                self._new_generation()

        if not await self._run_blocking(_apply):
            raise TimeoutError("Timed out applying camera settings.")

    async def set_exposure_time(self, exposure_time: float, **kwargs: Any) -> None:
        """Set the exposure time in seconds.

        Args:
            exposure_time: Exposure time in seconds.
        """
        await self.activate_camera()
        await self._apply_settings(lambda camera: camera.set_exposure_time(exposure_time * 1e6))
        await self.comm.set_state(IExposureTime, ExposureTimeState(exposure_time=self._exposure_time))

    async def reset(self, **kwargs: Any) -> None:
        """Reset image type, data pipeline and exposure time to their defaults."""
        await BaseVideo.reset(self, **kwargs)
        await self.set_exposure_time(0.0)


__all__ = ["AravisCamera"]
