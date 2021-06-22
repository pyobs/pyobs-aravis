import logging
import time
import aravis

from pyobs.interfaces import ICameraExposureTime
from pyobs.modules.camera import BaseVideo


log = logging.getLogger(__name__)


class AravisCamera(BaseVideo, ICameraExposureTime):
    """A pyobs module for Aravis cameras."""
    __module__ = 'pyobs_aravis'

    def __init__(self, device: str, *args, **kwargs):
        """Initializes a new AravisCamera.

        Args:
            device: Name of camera to connect to.
        """
        BaseVideo.__init__(self, *args, **kwargs)

        # variables
        self._device_name = device
        self._camera = None

        # thread
        self.add_thread_func(self._capture)

    def open(self):
        """Open module."""
        BaseVideo.open(self)

        # list devices
        ids = aravis.get_device_ids()
        if self._device_name not in ids:
            raise ValueError('Could not find given device name in list of available cameras.')

    def close(self):
        """Close the module."""
        BaseVideo.close(self)

        # stop camera
        self._camera.stop_acquisition()
        self._camera.shutdown()

    def _capture(self):
        # open camera
        self._camera = aravis.Camera(self._device_name)

        # start acquisition
        self._camera.start_acquisition_continuous(nb_buffers=2)

        # loop until closing
        last = time.time()
        while not self.closing.is_set():
            # read frame
            frame = self._camera.pop_frame()

            # if time since last image is too short, wait a little
            if time.time() - last < self._interval:
                self.closing.wait(0.01)
                continue
            last = time.time()

            # process it
            self._set_image(frame)

        # release camera
        self._camera.stop_acquisition()

    def set_exposure_time(self, exposure_time: float, *args, **kwargs):
        """Set the exposure time in seconds.

        Args:
            exposure_time: Exposure time in seconds.

        Raises:
            ValueError: If exposure time could not be set.
        """
        self._camera.set_exposure_time(int(exposure_time * 1e6))

    def get_exposure_time(self, *args, **kwargs) -> float:
        """Returns the exposure time in seconds.

        Returns:
            Exposure time in seconds.
        """
        return self._camera.get_exposure_time() / 1e6


__all__ = ['AravisCamera']
